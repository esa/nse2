from __future__ import annotations

from enum import Enum
from typing import override


class ContactState(Enum):
    """Contact state enumeration."""

    PRE = 0
    LIVE = 1
    POST = 2


class CoreContact(object):
    def __init__(
        self,
        timespan: tuple[int, int],
        nodes: tuple[str, str],
        bw: str,
        loss: float,
        delay: float,
        jitter: float,
        symmetric: bool = False,
    ) -> None:
        self.timespan: tuple[int, int] = timespan
        self.nodes: tuple[str, str] = nodes
        self.bw: str = bw
        self.loss: float = loss
        self.delay: float = delay
        self.jitter: float = jitter
        self.symmetric: bool = symmetric

    @override
    def __str__(self) -> str:
        return (
            f"CoreContact(timespan={self.timespan}, nodes={self.nodes}, bw={self.bw}, loss={self.loss}, "
            + f"delay={self.delay}, jitter={self.jitter}, symmetric={self.symmetric})"
        )

    @classmethod
    def from_string(cls, line: str, mapping: dict[str, str]) -> "CoreContact":
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
        if not fixed_link and not 8 <= len(fields) <= 9:
            raise ValueError(f"Invalid Contact line with content: `{line}`")
        if fixed_link and not 6 <= len(fields) <= 7:
            raise ValueError(f"Invalid Fixed Link line with content: `{line}`")

        if fixed_link:
            timespan = (0, 0)
            start_field = 0
        else:
            timespan = (int(fields[0]), int(fields[1]))
            start_field = 2

        src = fields[start_field]
        if src in mapping:
            src = mapping[src]

        dst = fields[start_field + 1]
        if dst in mapping:
            dst = mapping[dst]

        nodes = (src, dst)
        bw = fields[start_field + 2]
        loss = float(fields[start_field + 3])
        delay = float(fields[start_field + 4])
        jitter = float(fields[start_field + 5])
        try:
            symmetric = True if fields[start_field + 6] == "=" else False
        except IndexError:
            symmetric = False
        return cls(timespan, nodes, bw, loss, delay, jitter, symmetric)


class CoreContactPlan(object):
    """A CoreContactPlan file."""

    def __init__(
        self,
        filename: str | None = None,
        contacts: dict[CoreContact, ContactState] = {},
        fixed: list[CoreContact] = [],
        mapping: dict[str, str] = {},
    ) -> None:
        self.loop: bool = False
        self.contacts: dict[CoreContact, ContactState] = contacts
        self.fixed: list[CoreContact] = fixed
        if filename:
            self.load(filename, mapping=mapping)

    @classmethod
    def from_file(cls, filename: str, mapping: dict[str, str] = {}) -> CoreContactPlan:
        plan = cls(filename, mapping=mapping)
        return plan

    @override
    def __str__(self) -> str:
        return f"CoreContactPlan(loop={self.loop}, #contacts={len(self.contacts)})"

    def load(self, filename: str, mapping: dict[str, str] = {}) -> None:
        contacts: dict[CoreContact, ContactState] = {}
        fixed: list[CoreContact] = []
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                fields = line.split()
                if len(fields) == 3 and fields[0] == "s":
                    if fields[1] == "loop":
                        if fields[2] == "1":
                            self.loop = True
                        else:
                            self.loop = False
                elif len(fields) > 4 and fields[0] == "a":
                    if fields[1] == "contact":
                        contact = CoreContact.from_string(line, mapping=mapping)
                        print(contact)
                        contacts[contact] = ContactState.PRE
                    if fields[1] == "fixed":
                        fixed_contact = CoreContact.from_string(line, mapping=mapping)
                        print(fixed_contact)
                        fixed.append(fixed_contact)

        self.contacts = contacts
        self.fixed = fixed

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
