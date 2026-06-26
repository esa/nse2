#!/usr/bin/env python3
import argparse
import signal
import socket
import time
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Literal

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
)
from tools.contact_player.scenario import (
    NetworkName,
    Node,
    load_scenario,
)
from tools.contact_player.tc_netem import set_on_interface

LinkKind = Literal["static", "active"]


@dataclass(frozen=True)
class Link:
    src: Node
    dst: Node
    network: NetworkName
    kind: LinkKind


@dataclass
class ContactPlayer:
    plan: ContactPlan
    scenario_path: Path
    nodes: dict[str, Node]
    netmap_path: Path | None = None

    CONTROL_PORT: int = 9966
    TICK: float = 0.1

    # internal fields to control the behavior of the run() function
    paused: bool = False
    stop: bool = False
    skip: bool = False
    sock: socket.socket = field(init=False)

    def __post_init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", self.CONTROL_PORT))
        self.sock.setblocking(False)

    # derived topology state
    @property
    def unique_interfaces(self) -> set[tuple[Node, NetworkName]]:
        """Interfaces used by dynamic contacts and initialized with netem."""
        return {(c.src, c.network) for c in self.plan.contacts}

    @property
    def physical_links(self) -> set[Link]:
        """All physical links implied by shared compose networks."""
        return {
            Link(a, b, network, "static")
            for a, b in combinations(self.nodes.values(), 2)
            for network in a.interfaces.keys() & b.interfaces.keys()
        }

    @property
    def fixed_links(self) -> set[Link]:
        """Always-visible links defined as fixed CCP contacts."""
        return {
            Link(c.src, c.dst, c.network, "static") for c in self.plan.fixed_contacts
        }

    @property
    def active_links(self) -> set[Link]:
        """Currently active dynamic contact links."""
        return {
            Link(c.src, c.dst, c.network, "active")
            for c, state in self.plan.contacts.items()
            if state == ContactState.LIVE
        }

    @property
    def visible_links(self) -> set[Link]:
        """Links currently visible in the network map (static + fixed + active)."""
        dynamic_keys = {
            (*sorted((c.src.name, c.dst.name)), c.network) for c in self.plan.contacts
        }

        static_links = {
            l
            for l in self.physical_links
            if (*sorted((l.src.name, l.dst.name)), l.network) not in dynamic_keys
        }
        return static_links | self.fixed_links | self.active_links

    # lifecycle
    def setup(self) -> None:
        """Initialize dynamic contacts as blocked and enable fixed contacts."""
        for node, network in self.unique_interfaces:
            iface = node.interfaces[network].dev
            print(f"[INIT] Initialize contact: interface {iface} on node {node.name}")

            set_on_interface(node.name, iface, command="add", loss=100.0)

        for contact in self.plan.fixed_contacts:
            print(
                f"[INIT] Initialize fixed contact: interface {contact.src.interfaces[contact.network].dev} on node {contact.src.name}"
            )
            self._apply_contact(contact, command="add")

        self.update_netmap()

    def cleanup(self) -> None:
        """Remove configured qdiscs and clear generated runtime state."""
        for node, network in self.unique_interfaces:
            try:
                set_on_interface(node.name, node.interfaces[network].dev, command="del")
            except RuntimeError as e:
                print(f"ERROR: {e}")

        for contact in self.plan.fixed_contacts:
            try:
                set_on_interface(
                    contact.src.name,
                    contact.src.interfaces[contact.network].dev,
                    command="del",
                )
            except RuntimeError as e:
                print(f"ERROR: {e}")

        if self.netmap_path is not None:
            with open(self.netmap_path, "w"):
                pass

        self.sock.close()

    def run(self, loop_override: bool = False) -> None:
        """Run the contact plan until completion, stop request, or loop restart."""
        signal.signal(signal.SIGINT, lambda *_: self._request_stop())

        current_time = 0
        try:
            self.setup()

            while not self.stop:
                next_time = self.plan.next_event_time(current_time)
                if next_time is None:
                    if self.plan.loop or loop_override:
                        print("Reached the end of the loop... looping...")
                        current_time = 0
                        self.plan.reset()
                        continue
                    print("No more events... exiting...")
                    break
                print(f"[ {current_time} ] Next event(s) at {next_time}")

                self._sleep_until(next_time, current_time)
                if self.stop:
                    break
                current_time = next_time

                for contact in self.plan.contacts_to_activate(current_time):
                    print(f"[ {current_time} ] Activating {contact}")
                    self.activate(contact)
                for contact in self.plan.contacts_to_deactivate(current_time):
                    print(f"[ {current_time} ] Deactivating {contact}")
                    self.deactivate(contact)

                self.update_netmap()
        finally:
            self.cleanup()

    # contact state changes
    def activate(self, contact: Contact) -> None:
        """Apply a contact and mark it as live."""
        self._apply_contact(contact)
        self.plan.contacts[contact] = ContactState.LIVE

    def deactivate(self, contact: Contact) -> None:
        """Block a contact and mark it as completed."""
        self._apply_contact(contact, deactivate=True)
        self.plan.contacts[contact] = ContactState.POST

    def _apply_contact(
        self, contact: Contact, command: str = "change", deactivate: bool = False
    ) -> None:
        """Apply a contact's link properties to its source interface."""
        loss = contact.props.loss
        if deactivate:
            loss = 100.0
        set_on_interface(
            contact.src.name,
            contact.src.interfaces[contact.network].dev,
            command=command,
            loss=loss,
            delay=contact.props.delay,
            jitter=contact.props.jitter,
            bandwidth=contact.props.bandwidth,
        )

    # external outputs
    def update_netmap(self) -> None:
        """Write the current visible network topology to the netmap file."""
        if self.netmap_path is None:
            return
        self.netmap_path.parent.mkdir(parents=True, exist_ok=True)

        links = sorted(
            self.visible_links,
            key=lambda l: (l.src.name, l.dst.name, l.network),
        )

        with open(self.netmap_path, "w") as f:
            for link in links:
                symbol = "." if link.kind == "active" else "-"
                f.write(f"{link.src.name} {symbol} {link.dst.name}\n")

    # runtime control
    def _sleep_until(self, target: int, current: int) -> None:
        """Sleep until the next event while processing control commands."""
        slept = 0.0
        duration = target - current

        while slept < duration and not self.stop:
            self._handle_commands(current + int(slept), target)
            if self.skip:
                self.skip = False
                return
            if self.paused:
                time.sleep(self.TICK)
                continue

            step = min(self.TICK, duration - slept)
            time.sleep(step)
            slept += step

    def _handle_commands(self, current_time: int, next_time: int) -> None:
        """Process pending UDP control commands without blocking the player loop."""
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
            except BlockingIOError:
                return

            cmd = data.decode().strip()

            if cmd == "resume" and self.paused:
                self.paused = False
                print("cmd: Resuming normal operation")
                response = "resumed"
            elif cmd == "pause" and not self.paused:
                self.paused = True
                print("cmd: Pausing, waiting for 'resume' message to continue")
                response = "paused"
            elif cmd == "next":
                self.skip = True
                self.paused = False
                print("cmd: Skipping to next")
                response = "skipped"
            elif cmd == "time":
                response = f"{current_time} {next_time}"
                print(f"cmd: Current time is {current_time}")
            elif data == b"scenario":
                response = f"{self.scenario_path} {self.plan.ccp_path}"
                print(f"cmd: Current scenario is {response}")
            elif cmd == "links":
                response = "\n".join(
                    f"{l.src.name} {'.' if l.kind == 'active' else '-'} {l.dst.name}"
                    for l in sorted(
                        self.visible_links,
                        key=lambda l: (l.src.name, l.dst.name, l.network),
                    )
                )
                print(f"cmd 'links': {response}")
            else:
                response = f"unknown command: {cmd}"

            self.sock.sendto(response.encode(), addr)

    def _request_stop(self) -> None:
        """Request graceful shutdown at the next safe point."""
        print("Stopping contact player...")
        self.stop = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--loop", action="store_true", help="Override looping")
    parser.add_argument(
        "-m", "--map-network", action="store_true", help="Generate/update netmap file"
    )
    parser.add_argument(
        "--control-port", type=int, default=9966, help="UDP control port"
    )
    parser.add_argument("scenario", help="scenario file to load")
    parser.add_argument("ccp", help="core contact plan to load")
    args = parser.parse_args()

    scenario_path = Path(args.scenario)
    ccp_path = Path(args.ccp)
    netmap_path = (
        Path("tmp") / f"{scenario_path.stem}.netmap" if args.map_network else None
    )

    nodes = load_scenario(scenario_path)
    plan = ContactPlan.from_ccp_file(ccp_path, nodes)

    player = ContactPlayer(
        plan=plan,
        scenario_path=scenario_path,
        nodes=nodes,
        netmap_path=netmap_path,
        CONTROL_PORT=args.control_port,
    )
    player.run(loop_override=args.loop)


if __name__ == "__main__":
    main()
