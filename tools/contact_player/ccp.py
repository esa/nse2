from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from pydantic import BaseModel

from tools.lib.scenario import (
    NetworkConfig,
    NetworkInterface,
    NetworkName,
    Node,
    NodeMap,
)


class LinkProperties(BaseModel, frozen=True):
    bandwidth: str
    loss: float = 0.0
    delay: float = 0.0
    jitter: float = 0.0


class _RawLink(BaseModel):
    src: str
    dst: str
    props: LinkProperties


class _RawContact(_RawLink):
    begin: int
    end: int


class FixedLink(BaseModel, frozen=True):
    src: Node
    iface: NetworkInterface
    dst: Node
    props: LinkProperties


class Contact(FixedLink, frozen=True):
    begin: int
    end: int

    def is_active(self, time: int) -> bool:
        """Return True when the contact is active at the given time."""
        return self.begin <= time < self.end


def _resolve_node(raw: str, nodes: NodeMap) -> Node:
    """Resolve a raw node (name or integer ID) to a Node."""
    if raw in nodes:
        return nodes[raw]
    elif raw.isdigit():
        for node in nodes.values():
            if node.id == int(raw):
                return node
        raise ValueError(f"No node found with id {raw}")
    raise ValueError(f"No node found with name '{raw}'")


def _resolve_iface(
    src: Node, dst_raw: str, nodes: NodeMap
) -> tuple[Node, NetworkConfig]:
    """Resolve a raw dst token to a (dst: Node, src_network: NetworkConfig) pair.

    Either:
    - dst_raw is "dev:eosat_gs1_lo" → iface is a direct key into src.networks
    - dst_raw is a node name/id     → find shared interface via set intersection
    """
    if dst_raw.startswith("dev:"):
        shared_network: NetworkName = dst_raw[4:]
        if shared_network not in src.networks:
            raise ValueError(
                f"Network '{shared_network}' not found on node '{src.name}'"
            )
        # find the peer node by searching for nodes connected to the same network
        dst = next(
            (
                n
                for n in nodes.values()
                if n is not src and shared_network in n.networks
            ),
            None,
        )
        if dst is None:
            raise ValueError(f"No peer node found for network '{shared_network}'")
        return dst, src.networks[shared_network]
    else:
        dst = _resolve_node(dst_raw, nodes)
        shared_networks = [net for net in src.networks if net in dst.networks]
        if not shared_networks:
            raise ValueError(f"No shared network between '{src.name}' and '{dst.name}'")
        if len(shared_networks) > 1:
            raise ValueError(
                f"Ambiguous: multiple networks between '{src.name}' and '{dst.name}': {shared_networks}. Use dev: syntax to be explicit."
            )
        shared_network = shared_networks[0]
    return dst, src.networks[shared_network]


def _resolve_link(raw: _RawLink, nodes: NodeMap) -> tuple[Node, Node, NetworkConfig]:
    """Full resolution of a raw link into (src: Node, dst: Node, src_net_config: NetworkConfig)."""
    src = _resolve_node(raw.src, nodes)
    dst, net_conf = _resolve_iface(src, raw.dst, nodes)
    return src, dst, net_conf


class ContactPlan(BaseModel):
    loop: bool
    fixed_links: list[FixedLink]
    contacts: list[Contact]

    @classmethod
    def from_file(cls, path: str, nodes: NodeMap) -> "ContactPlan":
        raw_fixed: list[_RawLink] = []
        raw_contacts: list[_RawContact] = []
        loop = False

        with open(path) as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                fields = line.split()

                if len(fields) == 3 and fields[0] == "s" and fields[1] == "loop":
                    loop = bool(int(fields[2]))
                elif len(fields) > 4 and fields[0] == "a":
                    if fields[1] == "fixed":
                        raw_fixed.append(
                            _RawLink(
                                src=fields[2],
                                dst=fields[3],
                                props=LinkProperties(
                                    bandwidth=fields[4],
                                    loss=float(fields[5]),
                                    delay=float(fields[6]),
                                    jitter=float(fields[7]),
                                ),
                            )
                        )
                    if fields[1] == "contact":
                        raw_contacts.append(
                            _RawContact(
                                begin=int(fields[2]),
                                end=int(fields[3]),
                                src=fields[4],
                                dst=fields[5],
                                props=LinkProperties(
                                    bandwidth=fields[6],
                                    loss=float(fields[7]),
                                    delay=float(fields[8]),
                                    jitter=float(fields[9]),
                                ),
                            )
                        )
        fixed_links: list[FixedLink] = []
        for raw in raw_fixed:
            src, dst, src_net_conf = _resolve_link(raw, nodes)
            fixed_links.append(
                FixedLink(src=src, dst=dst, iface=src_net_conf.iface, props=raw.props)
            )

        contacts: list[Contact] = []
        for raw in raw_contacts:
            src, dst, src_net_conf = _resolve_link(raw, nodes)
            contacts.append(
                Contact(
                    begin=raw.begin,
                    end=raw.end,
                    src=src,
                    dst=dst,
                    iface=src_net_conf.iface,
                    props=raw.props,
                )
            )

        return cls(loop=loop, fixed_links=fixed_links, contacts=contacts)

    def get_max_time(self) -> int:
        """Returns the maximum time in the contact plan."""
        return max([c.end for c in self.contacts])


class ContactState(Enum):
    """Contact state enumeration."""

    PRE = 0
    LIVE = 1
    POST = 2


class CoreContact(object):
    def __init__(
        self,
        timespan: Tuple[int, int],
        nodes: Tuple[str, str],
        bw: str,
        loss: float,
        delay: float,
        jitter: float,
    ) -> None:
        self.timespan = timespan
        self.nodes = nodes
        self.bw = bw
        self.loss = loss
        self.delay = delay
        self.jitter = jitter

    def __str__(self) -> str:
        return (
            "CoreContact(timespan=%r, nodes=%r, bw=%s, loss=%f, delay=%f, jitter=%f)"
            % (self.timespan, self.nodes, self.bw, self.loss, self.delay, self.jitter)
        )

    @classmethod
    def from_string(cls, line: str, mapping: Dict[int, str] = {}) -> "CoreContact":
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
        print(fields, len(fields))
        if (len(fields) != 8 and not fixed_link) or (len(fields) != 6 and fixed_link):
            raise ValueError("Invalid CoreContact line: %s" % line)

        if fixed_link:
            timespan = (0, 0)
            start_field = 0
        else:
            timespan = (int(fields[0]), int(fields[1]))
            start_field = 2

        src = fields[start_field]
        if src in mapping:
            src = mapping[fields[2]]

        dst = fields[start_field + 1]
        if dst in mapping:
            dst = mapping[fields[3]]

        nodes = (src, dst)
        bw = fields[start_field + 2]
        loss = float(fields[start_field + 3])
        delay = float(fields[start_field + 4])
        jitter = float(fields[start_field + 5])
        return cls(timespan, nodes, bw, loss, delay, jitter)
