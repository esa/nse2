#!/usr/bin/env python3

import argparse
import signal
import socket
import sys
import time
from enum import Enum, auto
from pathlib import Path

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    FixedLink,
)
from tools.contact_player.tc_netem import set_on_interface
from tools.lib.scenario import NodeMap, find_link_pairs, nodes_from_compose


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments.

    Returns:
        Namespace with attributes: ``scenario`` (str), ``contact_plan`` (str),
        ``loop`` (bool | None), ``symmetric`` (bool), ``map_network`` (bool).
    """
    parser = argparse.ArgumentParser(
        description="Read out the network connections for the DTN simulation scenario from a Docker Compose file and contact plan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-l",
        "--loop",
        action=argparse.BooleanOptionalAction,
        help="Override looping behaviour defined in the contact plan",
    )
    parser.add_argument(
        "-s",
        "--symmetric",
        action="store_true",
        help="Treat all contacts as symmetric (bidirectional)",
    )
    parser.add_argument(
        "-m",
        "--map-network",
        action="store_true",
        help="Discover and write network links to tmp/<scenario>.netmap",
    )
    parser.add_argument(
        "scenario", help="Path to the Docker Compose scenario file (.yml)"
    )
    parser.add_argument(
        "contact_plan", help="Path to the core contact plan file (.ccp)"
    )
    return parser.parse_args()


class ContactState(Enum):
    PRE = auto()
    LIVE = auto()
    POST = auto()


class ContactPlayer:
    """Plays out a contact plan over a network simulation scenario.

    Manages the state of scheduled contacts and applies network emulation (netem)
    rules to the corresponding interfaces as the simulation time advances.

    Attributes:
        scenario_name: The name of the scenario.
        plan: The contact plan containing the scheduled contacts.
        nodes: A mapping of node names to Node objects in the scenario.
        contact_states: A dictionary tracking the current activation state of each scheduled contact.
        permanent_links: A set of node pairs representing links in the topology that are not managed dynamically by the contact plan.
    """

    def __init__(self, scenario_name: str, plan: ContactPlan, nodes: NodeMap) -> None:
        self.scenario_name: str = scenario_name
        self.plan: ContactPlan = plan
        self.nodes: NodeMap = nodes

        # scheduled contacts and their current activation state
        self.contact_states: dict[Contact, ContactState] = {
            c: ContactState.PRE for c in plan.contacts
        }

        # links from the compose topology that are not managed contacts (that have changing properties)
        managed = {frozenset([link.src.name, link.dst.name]) for link in plan.contacts}
        self.permanent_links: set[frozenset[str]] = find_link_pairs(nodes) - managed

    def reset(self) -> None:
        """Reset all contacts to the PRE state, so that the simulation can start over."""
        for c in self.contact_states:
            self.contact_states[c] = ContactState.PRE

    def active_contact_links(self) -> set[frozenset[str]]:
        """Return the set of active contact links as undirected node pairs without duplicates."""
        return {
            frozenset([c.src.name, c.dst.name])
            for c, s in self.contact_states.items()
            if s == ContactState.LIVE
        }

    def update_netmap(self) -> None:
        """Write the permanent and current active contact links to ./tmp/{scenario_name}.netmap."""
        out_dir = Path("tmp")
        out_dir.mkdir(exist_ok=True)

        netmap_file = out_dir / f"{self.scenario_name}.netmap"
        print(f"Updating network map {netmap_file}")

        with netmap_file.open("w") as f:
            for a, b in self.permanent_links:
                f.write(f"{a} - {b}\n")
            for a, b in self.active_contact_links():
                f.write(f"{a} . {b}\n")

    def tick(self, time: int) -> None:
        """Advance the simulation to the given time and update contact states.

        Changes contacts from PRE to LIVE when they become active and from LIVE
        to POST when they are no longer active.

        Args:
            time: The current simulation time.
        """
        time_effective = (time % self.plan.get_max_time()) if self.plan.loop else time

        for contact, state in self.contact_states.items():
            if contact.is_active(time_effective):
                if state == ContactState.PRE:
                    print("[ %d ] Activating %s" % (time, contact))
                    self.apply(contact)
                    self.contact_states[contact] = ContactState.LIVE
            else:
                if state == ContactState.LIVE:
                    print("[ %d ] Deactivating %s" % (time, contact))
                    self.apply(contact, deactivate=True)
                    self.contact_states[contact] = ContactState.POST

    def next_event_time(self, after: int) -> int | None:
        """Return the next simulation time at which a contact changes state.

        Args:
            after: The simulation time after which to find the next event.

        Returns:
            The next event time, or None if there are no upcoming events.
        """
        # TODO: is "effective" here neccesary?
        effective = (after % self.plan.get_max_time()) if self.plan.loop else after

        candidates: list[int] = []
        for contact, state in self.contact_states.items():
            if state == ContactState.PRE and contact.begin >= effective:
                candidates.append(contact.begin)
            if state == ContactState.LIVE and contact.end >= effective:
                candidates.append(contact.end)
        return min(candidates) if candidates else None

    def apply(
        self,
        contact: Contact | FixedLink,
        deactivate: bool = False,
        command: str = "change",
        symmetric: bool = False,
    ) -> None:
        loss = contact.props.loss
        if deactivate:
            loss = 100.0

        set_on_interface(
            contact.src.name,
            contact.iface,
            command=command,
            loss=loss,
            delay=contact.props.delay,
            jitter=contact.props.jitter,
            bandwidth=contact.props.bandwidth,
        )
        if symmetric:
            iface = contact.dst.interfaces_toward(contact.src)
            if not iface:
                print(
                    f"Error: did not find interface from node {contact.dst} to {contact.src}"
                )
            else:
                set_on_interface(
                    contact.dst.name,
                    iface[0],
                    command=command,
                    loss=loss,
                    delay=contact.props.delay,
                    jitter=contact.props.jitter,
                    bandwidth=contact.props.bandwidth,
                )

    def teardown(self) -> None:
        """Remove all tc netem rules set by this player and delete the generated netmap file."""
        for link in self.plan.fixed_links:
            self.apply(link, command="del")
        for contact in self.contact_states:
            # TODO: I think this can also be `self.apply`, check that!
            set_on_interface(contact.src.name, contact.iface, command="del", loss=0.0)
        # delete the netmap file
        netmap_file = Path("tmp") / f"{self.scenario_name}.netmap"
        netmap_file.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    update_netmap_file: bool = args.map_network
    scenario_path = Path(args.scenario)
    nodes = nodes_from_compose(scenario_path)
    plan = ContactPlan.from_file(args.contact_plan, nodes)
    player = ContactPlayer(scenario_path.stem, plan, nodes)

    print("Permanent links: ", player.permanent_links)
    print("Fluctuating Contacts: ", player.contact_states.keys())

    # apply initial network configuration to fluctuating contacts and fixed links
    for contact in player.contact_states:
        player.apply(contact, command="add", deactivate=True)
    for link in player.plan.fixed_links:
        player.apply(link, command="add")

    # setup handler to intercept ctrl c
    def handle_sigint(sig, frame) -> None:
        print("\nInterrupted --- tearing down links.")
        player.teardown()
        control_socket.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    # Open a UDP socket for reading control messages on localhost
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.bind(("localhost", 9966))
    control_socket.setblocking(False)

    cur_time = 0
    while True:
        if update_netmap_file:
            player.update_netmap()
        next_t = player.next_event_time(after=cur_time)
        if next_t is None:
            if plan.loop or args.loop:
                print("Looping")
                cur_time = 0
                player.reset()
                continue
            else:
                print("No more events")
                break

        print("[ %d ] Next event(s) at %d" % (cur_time, next_t))

        sleep_time = next_t - cur_time
        time_slept = 0
        SLEEP_DELAY = 0.1
        paused = False
        while time_slept < sleep_time:
            try:
                data, addr = control_socket.recvfrom(1024)
                data = data.strip()
                print(f"Received control message: {data}")
                if data == b"resume" and paused:
                    paused = False
                    print("cmd: Resuming normal operation")
                    continue
                if data == b"pause" and not paused:
                    paused = True
                    print("cmd: Pausing, waiting for 'resume' message to continue")
                if data == b"next":
                    print("cmd: Skipping to next")
                    break
                if data == b"time":
                    print(f"cmd: Current time is {cur_time + time_slept}")
                    control_socket.sendto(
                        f"{cur_time + int(time_slept)} {next_t}".encode(), addr
                    )
                if data == b"scenario":
                    print(
                        f"cmd: Current scenario is {args.scenario} with {args.contact_plan}"
                    )
                    response = f"{args.scenario} {args.contact_plan}"
                    control_socket.sendto(response.encode(), addr)
                if data == b"links":
                    print(f"cmd: Permanent links are {player.permanent_links}")
                    print(
                        f"cmd: Current active links are {player.active_contact_links()}"
                    )
                    response = "\n".join(
                        [f"{a} - {b}" for a, b in player.permanent_links]
                    )
                    response += "\n".join(
                        [f"{a} . {b}" for a, b in player.active_contact_links()]
                    )
                    control_socket.sendto(response.encode(), addr)

            except socket.error:
                pass

            if sleep_time - time_slept < 1:
                time.sleep(sleep_time - time_slept)
                break
            else:
                time.sleep(SLEEP_DELAY)
                if not paused:
                    time_slept += SLEEP_DELAY
        cur_time = next_t
        player.tick(cur_time)

    player.teardown()


if __name__ == "__main__":
    main()
