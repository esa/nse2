from dataclasses import dataclass, field
from typing import TypeAlias, TypedDict, override


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


