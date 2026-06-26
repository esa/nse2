from dataclasses import dataclass, field
from os import PathLike
from typing import Any, TypeAlias, TypedDict, cast

import yaml

from tools.contact_player.tc_netem import run_in_container

NetworkName: TypeAlias = str
"""Name of a Docker compose network."""


class ComposeService(TypedDict):
    """Relevant subset of a Docker compose service definition."""

    environment: list[str]
    networks: dict[str, dict[str, str]]


# scenario model
@dataclass
class NetworkInterface:
    """Network interface configuration for one node on one network."""

    ip: str
    dev: str = ""


@dataclass(frozen=True)
class Node:
    """Scenario node resolved from a Docker compose service."""

    name: str
    id: str
    eid: str
    interfaces: dict[NetworkName, NetworkInterface] = field(
        default_factory=dict,
        compare=False,
    )


# public loading API
def load_scenario(path: str | PathLike[str]) -> dict[str, Node]:
    """Load scenario nodes from compose and discover container interfaces."""
    nodes = _parse_compose_nodes(path)
    _discover_interfaces(nodes)
    return nodes


def _parse_compose_nodes(path: str | PathLike[str]) -> dict[str, Node]:
    """Parse nodes and network IPs from a Docker compose scenario file."""
    print(f"Loading scenario from {path}.")
    nodes: dict[str, Node] = {}

    with open(path) as f:
        config: dict[str, Any] = yaml.load(f, Loader=yaml.FullLoader)
        if "x-description" in config:
            print(f"Description: {config['x-description']}")

        services = cast(dict[str, ComposeService], config["services"])
        for name, item in services.items():
            env_vars: list[str] = item["environment"]
            node_id_var = next(var for var in env_vars if var.startswith("NODE_ID="))
            node_id = node_id_var.split("=", maxsplit=1)[1]
            node_eid = f"ipn:{node_id}.0"
            node = Node(name, node_id, node_eid)

            for net_name, conf in item["networks"].items():
                node.interfaces[net_name] = NetworkInterface(conf["ipv4_address"])
                print(
                    f"Node {node_eid} connected to network {net_name} with {conf['ipv4_address']}"
                )

            nodes[name] = node

    print(f"Created {len(nodes)} nodes.")
    return nodes


def _discover_interfaces(nodes: dict[str, Node]) -> None:
    """Populate interface device names by inspecting running containers."""
    for node in nodes.values():
        for net_name, iface in node.interfaces.items():
            res = run_in_container(node.name, f"ip a | grep {iface.ip}")
            if len(res) == 0:
                print("Error: IP not found")
                continue
            res_dev = res.rsplit(" ", maxsplit=1)[1].strip()

            node.interfaces[net_name].dev = res_dev
