from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import override

from tools.contact_player.scenario import NetworkName, Node


# runtime state / basic value objects
class ContactState(Enum):
    """Contact state  of a dynamic contact."""

    PRE = 0
    LIVE = 1
    POST = 2


@dataclass(frozen=True)
class LinkProperties:
    """Network properties applied to a contact link."""

    bandwidth: str
    loss: float = 0.0
    delay: float = 0.0
    jitter: float = 0.0


# raw CCP model and parsing
@dataclass(frozen=True)
class RawCcpContact:
    """Unresolved contact entry parsed directly from a CCP file."""

    src: str
    dst: str
    begin: int
    end: int
    props: LinkProperties
    symmetric: bool = False

    @classmethod
    def from_string(cls, line: str) -> "RawCcpContact":
        """Parse one CCP contact or fixed-link line."""
        line = line.strip()
        fixed_link = False
        if line.startswith("a contact"):
            line = line[9:].strip()
        elif line.startswith("a fixed"):
            line = line[7:].strip()
            fixed_link = True
        else:
            raise ValueError("Invalid CoreContact line: %s" % line)

        fields = line.split()
        if not fixed_link and not 8 <= len(fields) <= 9:
            raise ValueError(f"Invalid Contact line with content: `{line}`")
        if fixed_link and not 6 <= len(fields) <= 7:
            raise ValueError(f"Invalid Fixed Link line with content: `{line}`")

        if fixed_link:
            begin = 0
            end = -1
            start_field = 0
        else:
            begin = int(fields[0])
            end = int(fields[1])
            start_field = 2

        src = fields[start_field]
        dst = fields[start_field + 1]
        bw = fields[start_field + 2]
        loss = float(fields[start_field + 3])
        delay = float(fields[start_field + 4])
        jitter = float(fields[start_field + 5])
        props = LinkProperties(bw, loss, delay, jitter)
        symmetric = len(fields) > start_field + 6 and fields[start_field + 6] == "="

        return cls(src, dst, begin, end, props, symmetric)


@dataclass(frozen=True)
class RawCcpContactPlan:
    """Raw CCP file contents before node and interface resolution."""

    contacts: list[RawCcpContact] = field(default_factory=list)
    fixed_contacts: list[RawCcpContact] = field(default_factory=list)
    loop: bool = False

    @classmethod
    def from_file(cls, path: str | PathLike[str]) -> "RawCcpContactPlan":
        """Parse a CCP file into unresolved contacts and fixed contacts."""
        contacts: list[RawCcpContact] = []
        fixed: list[RawCcpContact] = []
        loop = False

        with open(path, "r") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                fields = line.split()

                try:
                    if fields[0] == "s" and fields[1] == "loop":
                        loop = bool(int(fields[2]))
                    elif fields[0] == "a":
                        if fields[1] == "fixed":
                            fixed.append(RawCcpContact.from_string(line))
                        elif fields[1] == "contact":
                            contacts.append(RawCcpContact.from_string(line))
                        else:
                            raise ValueError(
                                f"Unknown record type '{fields[1]}'. Does not match 'fixed' or 'contact'"
                            )
                except (IndexError, ValueError) as e:
                    raise ValueError(
                        f"Failed to parse contact plan at line {line_num} '{line}': {e}"
                    ) from e

        return cls(contacts, fixed, loop)


# resolution helpers
def _resolve_node(raw_node: str, nodes: dict[str, Node]) -> Node:
    """Resolve a CCP node reference by name or node ID."""
    if raw_node in nodes:
        return nodes[raw_node]
    for node in nodes.values():
        if node.id == raw_node:
            return node
    raise ValueError(f"Could not resolve node '{raw_node}'")


def _resolve_destination(
    src: Node, dst_raw: str, nodes: dict[str, Node]
) -> tuple[Node, NetworkName]:
    """Resolve a destination reference to a peer node and shared network."""
    if dst_raw.startswith("dev:"):
        src_dev = dst_raw[4:] + "_0"
        shared_network = next(
            (net for (net, iface) in src.interfaces.items() if iface.dev == src_dev),
            None,
        )
        if shared_network is None:
            raise ValueError(
                f"No interface '{src_dev}' found on node '{src.name}'.\n Full node config: {src}"
            )

        peers = [
            n for n in nodes.values() if n is not src and shared_network in n.interfaces
        ]
        if not peers:
            raise ValueError(f"No peer node found for network '{shared_network}'")
        if len(peers) > 1:
            raise ValueError(f"Ambiguous: multiple peers on network '{shared_network}'")

        return peers[0], shared_network

    dst = _resolve_node(dst_raw, nodes)
    shared_networks = src.interfaces.keys() & dst.interfaces.keys()

    if not shared_networks:
        raise ValueError(f"No shared network between '{src.name}' and '{dst.name}'")
    if len(shared_networks) > 1:
        raise ValueError(
            f"Ambiguous: multiple networks between '{src.name}' and '{dst.name}': {shared_networks}. Use dev: syntax to be explicit."
        )
    return dst, shared_networks.pop()


def _resolve_link(
    raw: RawCcpContact, nodes: dict[str, Node]
) -> tuple[Node, Node, NetworkName]:
    """Resolve a raw CCP contact into source node, destination node, and network."""
    src = _resolve_node(raw.src, nodes)
    dst, net = _resolve_destination(src, raw.dst, nodes)
    return src, dst, net


def _resolve_contacts(
    raw_contacts: list[RawCcpContact],
    nodes: dict[str, Node],
) -> list[Contact]:
    """Resolve raw CCP contacts and expand symmetric contacts into directed ones."""
    contacts: list[Contact] = []

    for raw in raw_contacts:
        src, dst, net = _resolve_link(raw, nodes)
        directions = [(src, dst), (dst, src)] if raw.symmetric else [(src, dst)]

        for link_src, link_dst in directions:
            contacts.append(
                Contact(link_src, link_dst, net, raw.begin, raw.end, raw.props)
            )
    return contacts


# resolved contact model and contact plan
@dataclass(frozen=True)
class Contact:
    """Resolved unidirectional contact applied to one source interface."""

    src: Node
    dst: Node
    network: NetworkName
    begin: int
    end: int
    props: LinkProperties

    def is_active(self, time: int) -> bool:
        """Return whether the contact is active at the given simulation time."""
        return self.end <= 0 or self.begin <= time <= self.end

    @override
    def __str__(self) -> str:
        return f"Contact ({self.src.name} -> {self.dst.name} via {self.network}, {self.begin}-{self.end})"

    @override
    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class ContactPlan:
    """Resolved contact plan with runtime state for dynamic contacts."""

    ccp_path: Path
    contacts: dict[Contact, ContactState] = field(default_factory=dict)
    fixed_contacts: list[Contact] = field(default_factory=list)
    loop: bool = False

    @classmethod
    def from_ccp_file(
        cls, path: str | PathLike[str], nodes: dict[str, Node]
    ) -> "ContactPlan":
        """Load and resolve a CCP file against the scenario nodes."""
        raw_plan = RawCcpContactPlan.from_file(path)
        contacts = _resolve_contacts(raw_plan.contacts, nodes)
        fixed_contacts = _resolve_contacts(raw_plan.fixed_contacts, nodes)

        return cls(
            Path(path),
            {c: ContactState.PRE for c in contacts},
            fixed_contacts,
            raw_plan.loop,
        )

    def contacts_to_activate(self, time: int) -> list[Contact]:
        """Returns the list of contacts at the given time that need to be activated."""
        contacts = [
            c
            for c, s in self.contacts.items()
            if c.is_active(time) and s == ContactState.PRE
        ]
        return contacts

    def contacts_to_deactivate(self, time: int) -> list[Contact]:
        """Returns the list of contacts at the given time that need to be deactivated."""
        contacts = [
            c
            for c, s in self.contacts.items()
            if c.end <= time and s == ContactState.LIVE
        ]
        return contacts

    def next_event_time(self, after: int) -> int | None:
        """Return the next time at which any contact changes state."""
        candidates: list[int] = []
        for c, s in self.contacts.items():
            if s == ContactState.PRE and c.begin >= after:
                candidates.append(c.begin)
            if s == ContactState.LIVE and c.end >= after:
                candidates.append(c.end)
        return min(candidates) if candidates else None

    def reset(self) -> None:
        """Resets the contact plan to its initial state."""
        for c in self.contacts:
            self.contacts[c] = ContactState.PRE
