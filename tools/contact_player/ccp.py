from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import override


class ContactState(Enum):
    """Contact state enumeration."""

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

    def at(self, time: int) -> list[tuple[CoreContact, ContactState]]:
        """Returns the list of contacts at the given time."""
        if self.loop:
            time = time % self.get_max_time()
        return [
            (c, s)
            for c, s in self.contacts.items()
            if c.timespan[0] <= time and c.timespan[1] >= time
        ]

    def need_activation(self, time: int) -> list[tuple[CoreContact, ContactState]]:
        """Returns the list of contacts at the given time that need to be activated."""
        all = self.at(time)
        return [(c, s) for (c, s) in all if s == ContactState.PRE]

    def need_deactivation(self, time: int) -> list[tuple[CoreContact, ContactState]]:
        """Returns the list of contacts at the given time that need to be deactivated."""
        return [
            (c, s)
            for c, s in self.contacts.items()
            if time >= c.timespan[1] and s == ContactState.LIVE
        ]

    def next_activation(self, time: int) -> int | None:
        """Returns the next activation time."""
        activations = [
            c.timespan[0]
            for c, s in self.contacts.items()
            if s == ContactState.PRE and c.timespan[0] >= time
        ]
        if len(activations) == 0:
            return None
        return min(activations)

    def next_deactivation(self, time: int) -> int | None:
        """Returns the next deactivation time."""
        deactivations = [
            c.timespan[1]
            for c, s in self.contacts.items()
            if s == ContactState.LIVE and c.timespan[1] >= time
        ]
        if len(deactivations) == 0:
            return None
        return min(deactivations)

    def reset(self) -> None:
        """Resets the contact plan to its initial state."""
        for c in self.contacts:
            self.contacts[c] = ContactState.PRE

    def get_max_time(self) -> int:
        """Returns the maximum time in the contact plan."""
        return max([c.timespan[1] for c in self.contacts])

    # TODO: unused.. remove..?
    def has_contact(self, simtime: int, node1: str, node2: str) -> bool:
        current_contacts = self.at(simtime)
        # print("[ %f ] has_contact: %d %d | %s" % (simtime, node1, node2, current_contacts[0]))
        for c in current_contacts:
            if c[0].nodes[0] == node1 and c[0].nodes[1] == node2:
                return True
            if c[0].nodes[0] == node2 and c[0].nodes[1] == node1:
                return True
        return False

    def all_contacts(self) -> list[tuple[str, str]]:
        all = [(c.nodes[0], c.nodes[1]) for c in self.contacts]
        # remove duplicates
        return list(set(all))
