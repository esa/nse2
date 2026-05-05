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
        Namespace containing parsed arguments.
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
    """Drives tc netem rules on container interfaces according to a contact schedule.

    Attributes:
        scenario_name: Name of the scenario, used for netmap file output.
        fixed_links: Links with static properties applied once on startup.
        contacts: Scheduled contacts and their current activation state (PRE, LIVE, DONE).
        permanent_links: Always-active node pairs from the compose topology
                         not overridden by the contact schedule.
    """

    def __init__(
        self,
        scenario_name: str,
        plan: ContactPlan,
        nodes: NodeMap,
        symmetric: bool = False,
    ) -> None:
        """
        Args:
            scenario_name: Name of the scenario, used for netmap file naming.
            plan: The parsed contact plan defining fixed links and scheduled contacts.
            nodes: The compose topology, used to derive permanent links.
            symmetric: If True, each contact in the plan is duplicated in the reverse
                       direction, so that link properties are applied on both endpoints.
        """
        self.scenario_name: str = scenario_name

        contacts = plan.contacts
        if symmetric:
            contacts += [
                Contact(
                    src=c.dst,
                    iface=c.dst.networks[c.network].iface,
                    network=c.network,
                    dst=c.src,
                    props=c.props,
                    begin=c.begin,
                    end=c.end,
                )
                for c in contacts
            ]

        self.contacts: dict[Contact, ContactState] = {
            c: ContactState.PRE for c in contacts
        }
        self.fixed_links: list[FixedLink] = plan.fixed_links

        # links from the compose topology that are not managed contacts (that have changing properties)
        managed = {frozenset([link.src.name, link.dst.name]) for link in plan.contacts}
        self.permanent_links: set[frozenset[str]] = find_link_pairs(nodes) - managed

    def reset(self) -> None:
        """Reset all contacts to the PRE state, so that the simulation can start over."""
        for c in self.contacts:
            self.contacts[c] = ContactState.PRE

    def active_contact_links(self) -> set[frozenset[str]]:
        """Return the set of active contact links as undirected node pairs without duplicates."""
        return {
            frozenset([c.src.name, c.dst.name])
            for c, s in self.contacts.items()
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
        for contact, state in self.contacts.items():
            if contact.is_active(time):
                if state == ContactState.PRE:
                    print(f"[ {time} ] Activating {contact}")
                    self.apply(contact)
                    self.contacts[contact] = ContactState.LIVE
            else:
                if state == ContactState.LIVE:
                    print(f"[ {time} ] Deactivating {contact}")
                    self.apply(contact, deactivate=True)
                    self.contacts[contact] = ContactState.POST

    def next_event_time(self, after: int) -> int | None:
        """Return the next simulation time at which a contact changes state.

        Args:
            after: The simulation time after which to find the next event.

        Returns:
            The next event time, or None if there are no upcoming events.
        """
        candidates: list[int] = []
        for contact, state in self.contacts.items():
            if state == ContactState.PRE and contact.begin >= after:
                candidates.append(contact.begin)
            if state == ContactState.LIVE and contact.end >= after:
                candidates.append(contact.end)
        return min(candidates) if candidates else None

    def apply(
        self,
        contact: Contact | FixedLink,
        deactivate: bool = False,
        command: str = "change",
    ) -> None:
        """Applies netem link properties to the given contact or fixed link.

        Args:
            contact: The Contact or FixedLink to modify.
            deactivate: If True, fully degrades the link (100% loss) instead of
                applying the contact's actual properties.
            command: The tc qdisc command ('add', 'change', 'del').
        """
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

    def teardown(self) -> None:
        """Remove all tc netem rules set by this player and delete the generated netmap file."""
        for link in self.fixed_links:
            print(
                f"Removing tc netem rules for: node {link.src.name} on interface {link.iface}"
            )
            set_on_interface(link.src.name, link.iface, command="del")

        for node, iface in {(c.src.name, c.iface) for c in self.contacts}:
            print(f"Removing tc netem rules for: node {node} on interface {iface}")
            set_on_interface(node, iface, command="del")

        # delete the netmap file
        netmap_file = Path("tmp") / f"{self.scenario_name}.netmap"
        netmap_file.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    update_netmap_file: bool = args.map_network
    scenario_path = Path(args.scenario)
    nodes = nodes_from_compose(scenario_path)
    plan = ContactPlan.from_file(args.contact_plan, nodes)
    player = ContactPlayer(scenario_path.stem, plan, nodes, symmetric=args.symmetric)

    print("Permanent links: ", player.permanent_links)
    print("Fluctuating Contacts: ", player.contacts.keys())

    for link in player.fixed_links:
        print(
            f"Initilizing netem rules for: node {link.src.name} on interface {link.iface}"
        )
        player.apply(link, command="add")

    for node, iface in {(c.src.name, c.iface) for c in player.contacts}:
        print(f"Initilizing netem rules for: node {node} on interface {iface}")
        set_on_interface(node, iface, command="add", loss=100)

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

    should_loop = args.loop if args.loop is not None else plan.loop
    cur_time = 0
    while True:
        if update_netmap_file:
            player.update_netmap()
        next_t = player.next_event_time(after=cur_time)
        if next_t is None:
            if should_loop:
                print("Looping")
                cur_time = 0
                player.reset()
                continue
            else:
                print("No more events")
                break

        print(f"[ {cur_time} ] Next event(s) at {next_t}")

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
                    lines = [f"{a} - {b}" for a, b in player.permanent_links]
                    lines.extend(
                        [f"{a} . {b}" for a, b in player.active_contact_links()]
                    )
                    response = "\n".join(lines)
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
