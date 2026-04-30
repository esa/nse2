from itertools import combinations
from os import PathLike
from typing import override

import yaml
from pydantic import BaseModel

from tools.contact_player.tc_netem import run_in_container

NetworkName = str
NetworkInterface = str
IPAddress = str


class NetworkConfig(BaseModel):
    iface: NetworkInterface
    ipv4: IPAddress


class _NodeNetworkConfig(BaseModel):
    ipv4_address: IPAddress


class _ScenarioService(BaseModel):
    """Represents a single service definition from a Docker Compose file.

    Maps directly to a service entry under the ``services`` key in a
    ``docker-compose.yml`` file. Each service corresponds to a network node
    in the simulation scenario.

    Attributes:
        hostname: Hostname assigned to the container.
        container_name: Explicit container name used by Docker.
        image: Docker image to use for this service.
        cap_add: List of Linux capabilities added to the container,
            e.g. ``["NET_ADMIN"]``.
        networks: Mapping of network name to network configuration,
            defining which subnets this service is connected to and
            its static IP address on each.
        environment: Environment variables for the container, either as
            a list of ``"KEY=VALUE"`` strings or as a plain dictionary.
        privileged: Whether the container runs in privileged mode.
            Defaults to ``False``.
        entrypoint: Entrypoint command override for the container.
    """

    hostname: str
    container_name: str
    image: str
    cap_add: list[str]
    networks: dict[NetworkName, _NodeNetworkConfig]
    environment: list[str] | dict[str, str]
    privileged: bool = False
    entrypoint: str

    def env_as_dict(self) -> dict[str, str]:
        """Return environment variables as parsed dictionary, instead of list."""
        if isinstance(self.environment, dict):
            return self.environment
        result: dict[str, str] = {}
        for env in self.environment:
            if "=" in env:
                k, v = env.split("=", 1)
                result[k] = v
            else:
                result[env] = ""
        return result


class _ScenarioFile(BaseModel):
    """Model of the Docker compose file."""

    services: dict[str, _ScenarioService]

    @classmethod
    def from_yaml(cls, path: str | PathLike[str]):
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


class Node(BaseModel, frozen=True):
    eid: str
    id: int
    name: str
    networks: dict[NetworkName, NetworkConfig]

    @override
    def __hash__(self) -> int:
        return hash(id)

    def interfaces_toward(self, neighbor: "Node") -> list[NetworkInterface] | None:
        """Return list of interfaces towards `neighbor`."""
        shared = self.networks.keys() & neighbor.networks.keys()
        return [self.networks[net].iface for net in shared] if shared else None


NodeMap = dict[str, Node]


def nodes_from_compose(path: str | PathLike[str]) -> NodeMap:
    """Returns dictionary with the nodes specified in a Docker compose file.

    Args:
        - path: path of the compose file.

    Returns:
        - dict[str, Node]
    """
    print(f"Loading scenario from {path}.")
    compose = _ScenarioFile.from_yaml(path)
    nodes: dict[str, Node] = {}

    for name, service in compose.services.items():
        env = service.env_as_dict()
        node_id = int(env["NODE_ID"])
        node_eid = f"ipn:{node_id}.0"

        # legacy method for getting the interface names
        # since Docker version v28 interface names are just network names with _0 appended
        networks: dict[NetworkName, NetworkConfig] = {}
        for network, conf in service.networks.items():
            res = run_in_container(name, f"ip a | grep {conf.ipv4_address}")
            if len(res) == 0:
                print("Error: IP not found")
                continue
            iface = res.rsplit(" ", maxsplit=1)[1].strip()
            networks[network] = NetworkConfig(iface=iface, ipv4=conf.ipv4_address)

        # new method for getting interface names
        # networks = {
        #     network: NetworkConfig(iface=f"{network}_0", ipv4=conf.ipv4_address)
        #     for network, conf in service.networks.items()
        # }

        nodes[name] = Node(eid=node_eid, id=node_id, name=name, networks=networks)

    print(f"Created {len(nodes)} nodes.")
    return nodes


def find_link_pairs(nodes: NodeMap) -> set[frozenset[str]]:
    """Return the set of all undirected node pairs that share at least one common network.

    Args:
        nodes: Mapping from node names to Node objects.

    Returns:
        Set of frozensets, each containing two node names that are connected
        via a shared network."""
    return {
        frozenset([a.name, b.name])
        for a, b in combinations(nodes.values(), 2)
        if a.networks.keys() & b.networks.keys()
    }
