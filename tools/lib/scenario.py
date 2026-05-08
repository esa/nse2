from os import PathLike
from typing import override

import yaml
from pydantic import BaseModel

NetworkName = str
IPAddress = str


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


class NetworkInterface(BaseModel):
    dev: str
    ip: str


class Node(BaseModel, frozen=True):
    eid: str
    id: int
    name: str
    networks: dict[str, bool]
    ips: dict[str, str]
    interfaces: dict[str, NetworkInterface] = {}

    @override
    def __hash__(self) -> int:
        return hash(id)


def nodes_from_compose(path: str | PathLike[str]) -> dict[str, Node]:
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

        ips = {net: cfg.ipv4_address for net, cfg in service.networks.items()}
        network_flags = {net: True for net in service.networks}

        for net, ip in ips.items():
            print(f"Node {node_eid} connected to network {net} with {ip}")

        nodes[name] = Node(
            eid=node_eid, id=node_id, name=name, networks=network_flags, ips=ips
        )

    print(f"Created {len(nodes)} nodes.")
    return nodes
