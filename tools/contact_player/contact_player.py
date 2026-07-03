#!/usr/bin/env python3
import argparse
import signal
import socket
import time
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Protocol

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
)
from tools.contact_player.scenario import Node, load_scenario
from tools.contact_player.tc_netem import run_in_container, set_on_interface


class ContactHandler(Protocol):
    """Side-effect interface for contact state changes.

    The scheduler invokes these methods; handlers decide what (if anything)
    happens when contacts are set up, activated, or deactivated.
    """

    plan: ContactPlan
    nodes: dict[str, Node]

    @property
    def static_links(self) -> set[frozenset[Node]]: ...

    @property
    def active_dynamic_links(self) -> set[frozenset[Node]]: ...

    def setup(self) -> None: ...

    def process_time(self, time: int) -> None: ...

    def next_event(self, after: int) -> int | None: ...

    def cleanup(self) -> None: ...


@dataclass
class CommandContactHandler:
    """Invokes a container-supplied script on contact state changes.

    Passes contact information to the script through environment variables.
    The script is expected to live inside the source container and is run
    via `docker exec -e K=V ... <container> <command>`.
    """

    plan: ContactPlan
    nodes: dict[str, Node]
    command: str

    @property
    def static_links(self) -> set[frozenset[Node]]:
        return NotImplemented

    @property
    def active_dynamic_links(self) -> set[frozenset[Node]]:
        return NotImplemented

    def setup(self) -> None:
        # TODO: call each node with event=setup for each interface, just like the TcNetemContactHandler
        pass

    def process_time(self, time: int) -> None:
        for contact in self.plan.contacts_to_activate(time):
            print(f"[ {time} ] Signal ACTIVATE to {contact}")
            self._run(contact, "activate", time)
            self.plan.contacts[contact] = ContactState.ACTIVE
        for contact in self.plan.contacts_to_deactivate(time):
            print(f"[ {time} ] Signal DEACTIVATE to {contact}")
            self._run(contact, "deactivate", time)
            self.plan.contacts[contact] = ContactState.INACTIVE

    def next_event(self, after: int) -> int | None:
        return self.plan.next_contact_event(after)

    def cleanup(self) -> None:
        # TODO: see setup()
        pass

    def _run(self, contact: Contact, event: str, time: int) -> None:
        run_in_container(
            contact.src.name, self.command, env=self._env(contact, event, time)
        )

    def _env(self, contact: Contact, event: str, time: int) -> dict[str, str]:
        return {
            "NSE2_EVENT": event,
            "NSE2_TIME": str(time),
            "NSE2_SRC": contact.src.name,
            "NSE2_DST": contact.dst.name,
            "NSE2_SRC_EID": contact.src.eid,
            "NSE2_DST_EID": contact.dst.eid,
            "NSE2_NETWORK": contact.network,
            "NSE2_INTERFACE": contact.src.interfaces[contact.network].dev,
            "NSE2_BEGIN": str(contact.begin),
            "NSE2_END": str(contact.end),
            "NSE2_BANDWIDTH": contact.props.bandwidth,
            "NSE2_LOSS": str(contact.props.loss),
            "NSE2_DELAY": str(contact.props.delay),
            "NSE2_JITTER": str(contact.props.jitter),
        }


@dataclass
class TcNetemContactHandler:
    plan: ContactPlan
    nodes: dict[str, Node]

    # derived topology state
    @property
    def unique_interfaces(self) -> set[tuple[Node, str]]:
        """Unique set of interfaces on nodes, used by contacts"""
        # TODO: update docs
        return {(c.src, c.src.interfaces[c.network].dev) for c in self.plan.contacts}

    # the following two link properties are used for generating the netmap and
    # answer the socket. This implementation and the API should see some reworking
    # to allow more things, like drawing deactivated connections etc
    @property
    def static_links(self) -> set[frozenset[Node]]:
        """Links, represented as pairs of nodes, implied by the compose file without the dynamic contacts."""
        all_physical_links = {
            frozenset((a, b))
            for a, b in combinations(self.nodes.values(), 2)
            if a.interfaces.keys() & b.interfaces.keys()
        }
        dynamic_links = {
            frozenset((c.src, c.dst)) for c in self.plan.contacts if c.end != -1
        }
        return all_physical_links - dynamic_links

    @property
    def active_dynamic_links(self) -> set[frozenset[Node]]:
        """Links, represented as pairs of nodes, that are currently active dynamic contacts."""
        return {
            frozenset((c.src, c.dst))
            for c, s in self.plan.contacts.items()
            if s == ContactState.ACTIVE and c.end != -1
        }

    # lifecycle
    def setup(self) -> None:
        """Initialize all interfaces used by contacts with 100% loss."""
        for node, interface in self.unique_interfaces:
            set_on_interface(node.name, interface, "add", loss=100)
            print(
                f"[INIT] Initialize contact: interface {interface} on node {node.name}"
            )

    def cleanup(self) -> None:
        """Remove configured qdiscs and clear generated runtime state."""
        for node, interface in self.unique_interfaces:
            try:
                set_on_interface(node.name, interface, command="del")
            except RuntimeError as e:
                print(f"ERROR: {e}")

    def process_time(self, time: int) -> None:
        for contact in self.plan.contacts_to_activate(time):
            print(f"[ {time} ] Activating {contact}")
            self._apply_contact(contact)
            self.plan.contacts[contact] = ContactState.ACTIVE

        for contact in self.plan.contacts_to_deactivate(time):
            print(f"[ {time} ] Deactivating {contact}")
            self._apply_contact(contact, deactivate=True)
            self.plan.contacts[contact] = ContactState.INACTIVE

    def next_event(self, after: int) -> int | None:
        return self.plan.next_contact_event(after)

    def _apply_contact(self, contact: Contact, deactivate: bool = False) -> None:
        """Apply a contact's link properties to its source interface."""
        set_on_interface(
            contact.src.name,
            contact.src.interfaces[contact.network].dev,
            command="change",
            loss=100.0 if deactivate else contact.props.loss,
            delay=contact.props.delay,
            jitter=contact.props.jitter,
            bandwidth=contact.props.bandwidth,
        )


@dataclass
class ContactPlayer:
    handlers: list[ContactHandler]
    scenario_path: Path
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

    def run(self, loop_override: bool = False) -> None:
        """Run the contact plan until completion, stop request, or loop restart."""
        signal.signal(signal.SIGINT, lambda *_: self._request_stop())

        current_time = 0
        try:
            for handler in self.handlers:
                handler.setup()

            while not self.stop:
                for handler in self.handlers:
                    handler.process_time(current_time)
                    # for c in rt.plan.contacts_to_activate(current_time):
                    #     print(f"[ {current_time} ] Activating {c}")
                    #     rt.activate(c)
                    # for c in rt.plan.contacts_to_deactivate(current_time):
                    #     print(f"[ {current_time} ] Deactivating {c}")
                    #     rt.deactivate(c)

                self.update_netmap()

                next_time = self._next_event(current_time)
                if next_time is None:
                    if self.handlers[0].plan.loop or loop_override:
                        print("Reached the end of the loop... looping...")
                        current_time = 0
                        continue
                    print("No more events... exiting...")
                    break

                print(f"[ {current_time} ] Next event(s) at {next_time}")
                self._sleep_until(next_time, current_time)

                current_time = next_time
        finally:
            self.cleanup()

    def _next_event(self, after: int) -> int | None:
        events = [
            t
            for handler in self.handlers
            if (t := handler.next_event(after)) is not None
        ]
        return min(events) if events else None

    # external outputs
    def update_netmap(self) -> None:
        """Write the current visible network topology to the netmap file."""
        if self.netmap_path is None:
            return
        self.netmap_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.netmap_path, "w") as f:
            for a, b in self.handlers[0].static_links:
                f.write(f"{a.name} - {b.name}\n")
            for a, b in self.handlers[0].active_dynamic_links:
                f.write(f"{a.name} . {b.name}\n")

    def cleanup(self) -> None:
        for handler in self.handlers:
            handler.cleanup()

        if self.netmap_path is not None:
            self.netmap_path.write_text("")

        self.sock.close()

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
                response = f"{self.scenario_path} {self.handlers[0].plan.ccp_path}"
                print(f"cmd: Current scenario is {response}")
            elif cmd == "links":
                lines = [f"{a} - {b}" for a, b in self.handlers[0].static_links]
                lines.extend(
                    [f"{a} . {b}" for a, b in self.handlers[0].active_dynamic_links]
                )
                response = "\n".join(lines)
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
    parser.add_argument(
        "--planned-contacts", type=Path, help="planned core contact plan to load"
    )
    parser.add_argument(
        "--planned-command",
        help="Command to run inside the source container for planned contact changes",
    )
    parser.add_argument("scenario", type=Path, help="scenario file to load")
    parser.add_argument(
        "actual_contacts", type=Path, help="actual core contact plan to load"
    )
    args = parser.parse_args()

    if bool(args.planned_contacts) != bool(args.planned_command):
        parser.error("--planned-contacts and --planned-command must be used together")

    netmap_path = (
        Path("tmp") / f"{args.scenario.stem}.netmap" if args.map_network else None
    )
    nodes = load_scenario(args.scenario)
    actual_plan = ContactPlan.from_ccp_file(args.actual_contacts, nodes)
    handlers: list[ContactHandler] = [TcNetemContactHandler(actual_plan, nodes)]

    if args.planned_contacts:
        planned_plan = ContactPlan.from_ccp_file(args.planned_contacts, nodes)
        handlers.append(
            CommandContactHandler(planned_plan, nodes, command=args.planned_command)
        )

    player = ContactPlayer(
        handlers=handlers,
        scenario_path=args.scenario,
        netmap_path=netmap_path,
        CONTROL_PORT=args.control_port,
    )
    player.run(loop_override=args.loop)


if __name__ == "__main__":
    main()
