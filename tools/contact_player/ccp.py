from pydantic import BaseModel

from tools.lib.scenario import (
    NetworkConfig,
    NetworkInterface,
    NetworkName,
    Node,
    NodeMap,
)


class LinkProperties(BaseModel, frozen=True):
    """Network properties associated with a link.

    Attributes:
        bandwidth: The bandwidth of the link (e.g., '100mbit').
        loss: Packet loss percentage (default: 0.0).
        delay: Link delay in milliseconds (default: 0.0).
        jitter: Link delay jitter in milliseconds (default: 0.0).
    """

    bandwidth: str
    loss: float = 0.0
    delay: float = 0.0
    jitter: float = 0.0


class _RawLink(BaseModel):
    """Raw link data as read from a contact plan file."""

    src: str
    dst: str
    props: LinkProperties


class _RawContact(_RawLink):
    """Raw contact data as read from a contact plan file."""

    begin: int
    end: int


class FixedLink(BaseModel, frozen=True):
    """A persistent network link between two nodes.

    Attributes:
        src: The source node of the link.
        iface: The interface on the source node.
        network: The name of the network this link belongs to.
        dst: The destination node of the link.
        props: Network properties of the link.
    """

    src: Node
    iface: NetworkInterface
    network: NetworkName
    dst: Node
    props: LinkProperties


class Contact(FixedLink, frozen=True):
    """A scheduled network contact between two nodes.

    Attributes:
        begin: Simulation time when the contact begins.
        end: Simulation time when the contact ends.
    """

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
    - dst_raw is "dev:eosat_gs1_lo" → network is a direct key into src.networks
    - dst_raw is a node name/id     → find shared network via set intersection
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
    """A collection of fixed links and scheduled contacts.

    Attributes:
        loop: Whether the plan should loop when it reaches the end.
        fixed_links: The permanent links in the network.
        contacts: The scheduled contacts that activate and deactivate.
    """

    loop: bool
    fixed_links: list[FixedLink]
    contacts: list[Contact]

    @classmethod
    def from_file(cls, path: str, nodes: NodeMap) -> "ContactPlan":
        raw_fixed: list[_RawLink] = []
        raw_contacts: list[_RawContact] = []
        loop = False

        with open(path) as f:
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
                        elif fields[1] == "contact":
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
                        else:
                            raise ValueError(f"Unknown record type '{fields[1]}'")
                except (IndexError, ValueError) as e:
                    raise ValueError(
                        f"Failed to parse contact plan at line {line_num} '{line}': {e}"
                    ) from e

        fixed_links: list[FixedLink] = []
        for raw in raw_fixed:
            src, dst, src_net_conf = _resolve_link(raw, nodes)
            fixed_links.append(
                FixedLink(
                    src=src,
                    dst=dst,
                    iface=src_net_conf.iface,
                    network=src_net_conf.network,
                    props=raw.props,
                )
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
                    network=src_net_conf.network,
                    props=raw.props,
                )
            )

        return cls(loop=loop, fixed_links=fixed_links, contacts=contacts)

    def get_max_time(self) -> int:
        """Returns the maximum time in the contact plan."""
        return max([c.end for c in self.contacts])
