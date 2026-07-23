#!/usr/bin/env python3
import argparse
import signal
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Literal

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
)
from tools.contact_player.scenario import Node, load_scenario
from tools.contact_player.tc_netem import (
    ContainerCommand,
    make_tc_command,
    run_in_containers_parallel,
)


@dataclass
class ContactHandler(ABC):
    """Base class for contact-plan side effects.

    A handler owns one ContactPlan and reacts to simulation-time transitions.
    Different handlers may apply physical effects, notify containers or expose
    topology state for external outputs.
    Subclasses must implement setup, cleanup, and command generation for contact transitions.
    """

    plan: ContactPlan
    nodes: dict[str, Node]

    @property
    def unique_contact_links(self) -> set[tuple[Node, Node, str]]:
        """Unique directed contact links as source node, destination node, and network."""
        return {(c.src, c.dst, c.network) for c in self.plan.contacts}

    @property
    def static_links(self) -> set[frozenset[Node]]:
        """Undirected physical links not controlled by dynamic contacts, but defined by the compose file."""
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
        """Currently active dynamic links in the topology."""
        return {
            frozenset((c.src, c.dst))
            for c, state in self.plan.contacts.items()
            if state == ContactState.ACTIVE and c.end != -1
        }

    @abstractmethod
    def setup(self) -> None:
        pass

    def process_time(self, time: int) -> None:
        """Process contact transitions due at the given simulation time."""
        transitions = (
            (self.plan.contacts_to_activate(time), ContactState.ACTIVE),
            (self.plan.contacts_to_deactivate(time), ContactState.INACTIVE),
        )

        for contacts, target_state in transitions:
            commands = [
                self._transition_command(time, contact, target_state)
                for contact in contacts
            ]
            run_in_containers_parallel(commands)

            for contact in contacts:
                self.plan.contacts[contact] = target_state

    @abstractmethod
    def _transition_command(
        self,
        time: int,
        contact: Contact,
        target_state: ContactState,
    ) -> ContainerCommand:
        """Build and log the command for one contact transition."""

    def next_event(self, after: int) -> int | None:
        return self.plan.next_contact_event(after)

    @abstractmethod
    def cleanup(self) -> None:
        pass


@dataclass
class CommandContactHandler(ContactHandler):
    """Notifies containers about planned contact changes.

    For each directed contact, the configured command is executed inside the
    source container. Contact/link metadata is passed via environment variables.
    """

    command: str

    def setup(self) -> None:
        """Notify containers about all known planned links before playback starts."""
        commands = [
            (src.name, self.command, self._env("setup", src, dst, net))
            for src, dst, net in self.unique_contact_links
        ]
        run_in_containers_parallel(commands)

    def _transition_command(
        self,
        time: int,
        contact: Contact,
        target_state: ContactState,
    ) -> ContainerCommand:
        event = "activate" if target_state == ContactState.ACTIVE else "deactivate"

        print(f"[ {time} ] Signal {event.upper()} to {contact}")

        return (
            contact.src.name,
            self.command,
            self._env(
                event,
                contact.src,
                contact.dst,
                contact.network,
                contact,
            ),
        )

    def cleanup(self) -> None:
        """Notify containers about all known planned links before shutdown."""
        commands = [
            (src.name, self.command, self._env("cleanup", src, dst, net))
            for src, dst, net in self.unique_contact_links
        ]
        run_in_containers_parallel(commands, raise_on_error=False)

    def _env(
        self,
        event: Literal["setup", "cleanup", "activate", "deactivate"],
        src: Node,
        dst: Node,
        network: str,
        contact: Contact | None = None,
    ) -> dict[str, str]:
        """Build the environment passed to the container command."""
        env = {
            "NSE2_EVENT": event,
            "NSE2_SRC": src.name,
            "NSE2_DST": dst.name,
            "NSE2_SRC_EID": src.eid,
            "NSE2_DST_EID": dst.eid,
            "NSE2_NETWORK": network,
        }
        if contact is not None:
            env |= {
                "NSE2_BEGIN": str(contact.begin),
                "NSE2_END": str(contact.end),
                "NSE2_BANDWIDTH": contact.props.bandwidth,
                "NSE2_LOSS": str(contact.props.loss),
                "NSE2_DELAY": str(contact.props.delay),
                "NSE2_JITTER": str(contact.props.jitter),
            }

        return env


@dataclass
class TcNetemContactHandler(ContactHandler):
    """Applies actual contact changes to Docker interfaces using tc/netem.

    Interfaces used by contacts are initially blocked and later changed
    according to contact state.
    """

    def setup(self) -> None:
        """Initialize all managed interfaces as blocking."""
        commands: list[ContainerCommand] = []

        for src, _, net in self.unique_contact_links:
            commands.append(
                (
                    src.name,
                    make_tc_command(src.interfaces[net].dev, "add", loss=100),
                    None,
                )
            )
            print(
                "[INIT] Initialize contact: interface",
                f"{src.interfaces[net].dev} on node {src.name}",
            )

        run_in_containers_parallel(commands)

    def _transition_command(
        self,
        time: int,
        contact: Contact,
        target_state: ContactState,
    ) -> ContainerCommand:
        interface = contact.src.interfaces[contact.network].dev

        if target_state == ContactState.ACTIVE:
            print(f"[ {time} ] Activating {contact}")
            command = make_tc_command(
                interface,
                loss=contact.props.loss,
                delay=contact.props.delay,
                jitter=contact.props.jitter,
                bandwidth=contact.props.bandwidth,
            )
        else:
            print(f"[ {time} ] Deactivating {contact}")
            command = make_tc_command(interface, loss=100)

        return contact.src.name, command, None

    def cleanup(self) -> None:
        """Remove qdiscs from all interfaces managed by this handler."""
        commands = [
            (
                src.name,
                make_tc_command(src.interfaces[net].dev, "del"),
                None,
            )
            for src, _, net in self.unique_contact_links
        ]
        run_in_containers_parallel(commands, raise_on_error=False)


@dataclass
class ContactPlayer:
    """Drives contact handlers according to simulation time and UDP commands.

    The player owns scheduling, looping, control commands, and netmap output.
    Contact-specific side effects are delegated to the configured handlers.
    """

    handlers: list[ContactHandler]
    scenario_path: Path
    netmap_path: Path | None = None

    CONTROL_PORT: int = 9966
    TICK: float = 0.1
    # Delay after setup so freshly-created tc qdiscs have time to take effect
    # before the first contact transition is applied.
    SETTLE_DELAY: float = 2.0

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
            time.sleep(self.SETTLE_DELAY)

            while not self.stop:
                for handler in self.handlers:
                    handler.process_time(current_time)

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
        """Return the earliest upcoming event across all handlers."""
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
            for a, b in sorted(self.handlers[0].static_links):
                f.write(f"{a.name} - {b.name}\n")
            for a, b in sorted(self.handlers[0].active_dynamic_links):
                f.write(f"{a.name} . {b.name}\n")

    def cleanup(self) -> None:
        """Clean up handlers, netmap state, and the UDP control socket."""
        for handler in self.handlers:
            handler.cleanup()

        if self.netmap_path is not None:
            self.netmap_path.write_text("")

        self.sock.close()

    # runtime control
    def _sleep_until(self, target: int, current: int) -> None:
        """Wait for the next event while still processing control commands."""
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
            elif cmd == "scenario":
                response = f"{self.scenario_path} {self.handlers[0].plan.ccp_path}"
                print(f"cmd: Current scenario is {response}")
            elif cmd == "links":
                lines = [
                    f"{a.name} - {b.name}"
                    for a, b in sorted(self.handlers[0].static_links)
                ]
                lines.extend(
                    [
                        f"{a.name} . {b.name}"
                        for a, b in sorted(self.handlers[0].active_dynamic_links)
                    ]
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
    """Load CLI configuration and start the contact player."""
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
