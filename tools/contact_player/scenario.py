from dataclasses import dataclass, field
from typing import TypeAlias, TypedDict, override


@dataclass
class NetworkInterface:
    ip: str
    dev: str = ""


NetworkName: TypeAlias = str


@dataclass(frozen=True)
class Node:
    name: str
    id: str
    eid: str
    interfaces: dict[NetworkName, NetworkInterface] = field(
        default_factory=dict,
        compare=False,
    )


class Service(TypedDict):
    environment: list[str]
    networks: dict[str, dict[str, str]]
