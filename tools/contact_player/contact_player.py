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
    """Common interface for contact-plan side effects.

    A handler owns one ContactPlan and reacts to simulation-time transitions.
    Different handlers may apply physical effects, notify containers, or expose
    topology state for external outputs.
    """

    plan: ContactPlan
    nodes: dict[str, Node]

    @property
    def unique_contact_links(self) -> set[tuple[Node, Node, str]]: ...

    """Unique directed contact links as source node, destination node, and network."""

    @property
    def static_links(self) -> set[frozenset[Node]]: ...

    """Undirected physical links not controlled by dynamic contacts, but defined by the compose file."""

    @property
    def active_dynamic_links(self) -> set[frozenset[Node]]: ...

    """Currently active dynamic links in the topology."""

    def setup(self) -> None: ...

    def process_time(self, time: int) -> None: ...

    def next_event(self, after: int) -> int | None: ...

    def cleanup(self) -> None: ...


@dataclass
class CommandContactHandler:
    """Notifies containers about planned contact changes.

    For each directed contact, the configured command is executed inside the
    source container. Contact/link metadata is passed via environment variables.
    """

    plan: ContactPlan
    nodes: dict[str, Node]
    command: str

    @property
    def unique_contact_links(self) -> set[tuple[Node, Node, str]]:
        """Unique directed contact links as source node, destination node, and network."""
        return {(c.src, c.dst, c.network) for c in self.plan.contacts}

    @property
    def static_links(self) -> set[frozenset[Node]]:
        raise NotImplementedError

    @property
    def active_dynamic_links(self) -> set[frozenset[Node]]:
        raise NotImplementedError

    def setup(self) -> None:
        """Notify containers about all known planned links before playback starts."""
        for src, dst, net in self.unique_contact_links:
            self._run_link("setup", src, dst, net, time=0)

    def cleanup(self) -> None:
        """Notify containers about all known planned links before shutdown."""
        for src, dst, net in self.unique_contact_links:
            self._run_link("cleanup", src, dst, net, time=0)

    def process_time(self, time: int) -> None:
        """Emit activate/deactivate notifications due at the given simulation time."""
        for contact in self.plan.contacts_to_activate(time):
            print(f"[ {time} ] Signal ACTIVATE to {contact}")
            self._run_contact("activate", contact, time)
            self.plan.contacts[contact] = ContactState.ACTIVE
        for contact in self.plan.contacts_to_deactivate(time):
            print(f"[ {time} ] Signal DEACTIVATE to {contact}")
            self._run_contact("deactivate", contact, time)
            self.plan.contacts[contact] = ContactState.INACTIVE

    def next_event(self, after: int) -> int | None:
        return self.plan.next_contact_event(after)

    def _run_contact(self, event: str, contact: Contact, time: int) -> None:
        self._run_link(
            event, contact.src, contact.dst, contact.network, time, contact=contact
        )

    def _run_link(
        self,
        event: str,
        src: Node,
        dst: Node,
        network: str,
        time: int,
        contact: Contact | None = None,
    ) -> None:
        """Run the command for either a scheduled contact or generic link event."""
        run_in_container(
            src.name,
            self.command,
            env=self._env(event, src, dst, network, time, contact),
        )

    def _env(
        self,
        event: str,
        src: Node,
        dst: Node,
        network: str,
        time: int,
        contact: Contact | None = None,
    ) -> dict[str, str]:
        """Build the environment passed to the container command."""
        env = {
            "NSE2_EVENT": event,
            "NSE2_TIME": str(time),
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
class TcNetemContactHandler:
    """Applies actual contact changes to Docker interfaces using tc/netem.

    This handler defines the physical emulated topology. Interfaces used by
    contacts are initially blocked and later changed according to contact state.
    """

    plan: ContactPlan
    nodes: dict[str, Node]

    # derived topology state
    @property
    def unique_contact_links(self) -> set[tuple[Node, Node, str]]:
        """Unique directed contact links as source node, destination node, and network."""
        return {(c.src, c.dst, c.network) for c in self.plan.contacts}

    # the following two link properties are used for generating the netmap and
    # answer the socket. This implementation and the API should see some reworking
    # to allow more things, like drawing deactivated connections etc
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
            for c, s in self.plan.contacts.items()
            if s == ContactState.ACTIVE and c.end != -1
        }

    # lifecycle
    def setup(self) -> None:
        """Initialize all managed interfaces as blocking."""
        for src, _, net in self.unique_contact_links:
            set_on_interface(src.name, src.interfaces[net].dev, "add", loss=100)
            print(
                f"[INIT] Initialize contact: interface {src.interfaces[net].dev} on node {src.name}"
            )

    def cleanup(self) -> None:
        """Remove qdiscs from all interfaces managed by this handler."""
        for src, _, net in self.unique_contact_links:
            try:
                set_on_interface(src.name, src.interfaces[net].dev, command="del")
            except RuntimeError as e:
                print(f"ERROR: {e}")

    def process_time(self, time: int) -> None:
        """Apply actual contact transitions due at the given simulation time."""
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
    """Drives contact handlers according to simulation time and UDP commands.

    The player owns scheduling, looping, control commands, and netmap output.
    Contact-specific side effects are delegated to the configured handlers.
    """

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
            for a, b in self.handlers[0].static_links:
                f.write(f"{a.name} - {b.name}\n")
            for a, b in self.handlers[0].active_dynamic_links:
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
