import yaml
from pydantic import BaseModel


class NodeNetworkConfig(BaseModel):
    ipv4_address: str


class ScenarioService(BaseModel):
    hostname: str
    container_name: str
    image: str
    cap_add: list[str]
    networks: dict[str, NodeNetworkConfig]
    environment: list[str] | dict[str, str]
    priviledged: bool = False
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


class ScenarioNetworkConfig(BaseModel):
    driver: str = "bridge"
    external: bool = False


class ScenarioFile(BaseModel):
    """Model of the Docker compose file."""

    services: dict[str, ScenarioService]
    networks: dict[str, ScenarioNetworkConfig] = {}

    @classmethod
    def from_yaml(cls, path: str):
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


class NetworkInterface(BaseModel):
    dev: str
    ip: str


class Node(BaseModel):
    eid: str
    id: str
    name: str
    networks: dict[str, bool]
    ips: dict[str, str]
    interfaces: dict[str, NetworkInterface] = {}


def nodes_from_compose(path: str) -> dict[str, Node]:
    """Returns dictionary with the nodes specified in a Docker compose file.

    Args:
        - path: path of the compose file.

    Returns:
        - dict[str, Node]
    """
    print(f"Loading scenario from {path}.")
    compose = ScenarioFile.from_yaml(path)
    nodes: dict[str, Node] = {}

    for name, service in compose.services.items():
        env = service.env_as_dict()
        node_id = env["NODE_ID"]
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
