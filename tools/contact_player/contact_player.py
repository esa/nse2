#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
import signal
import socket
import sys
import time
from itertools import combinations
from typing import cast

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
    CoreContact,
    CoreContactPlan,
    FixedLink,
)
from tools.contact_player.tc_netem import set_on_interface
from tools.lib.scenario import (
    Node,
    NodeMap,
    nodes_from_compose,
)


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


class ContactPlayer:
    def __init__(self, scenario_name: str, plan: ContactPlan, nodes: NodeMap) -> None:
        self.scenario_name: str = scenario_name
        self.plan: ContactPlan = plan
        self.nodes: NodeMap = nodes

        # scheduled contacts and their current activation state
        self.contact_states: dict[Contact, ContactState] = {
            c: ContactState.PRE for c in plan.contacts
        }

    def tick(self, time: int) -> None:
        """Advance simulation to time t, activating and deactivating contacts"""
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


def find_common_subnet_between_nodes(
    node1: str, node2: str, nodes: dict[str, Node]
) -> str | None:
    for k in nodes[node1].interfaces.keys():
        if k in nodes[node2].interfaces:
            return k
    return None


def get_dev_for_subnet(node: str, subnet: str, nodes: dict[str, Node]) -> str:
    return nodes[node].interfaces[subnet].dev


# TODO: maybe completely useless, since `links` should never be that, I think
# but not sure. Therefor check if needed, maybe remove this function if not
def get_pure_node_links(links: list[tuple[str, str, str]]) -> set[tuple[str, str, str]]:
    """Resolves interface identifiers to node names and deduplicates links.

    Converts links that reference specific network interfaces (e.g. ``dev:pcc_gs1``)
    into plain node-to-node links, then deduplicates by sorting each pair
    so that ``(pcc, gs1)`` and ``(gs1, pcc)`` are treated as the same link.

    Args:
        links: Raw link tuples of the form ``(endpoint_a, endpoint_b, link_type)``,
            where either endpoint may be a ``dev:<node>_<node>`` interface reference.

    Returns:
        A set of deduplicated 3-tuples ``(node_a, node_b, link_type)`` with
        node names sorted alphabetically and all interface references resolved.
    """
    pure_node_links: set[tuple[str, str, str]] = set()
    for l in links:
        # print("Link: ", l)
        nodes = [l[0], l[1]]
        link_type = l[2]

        if l[0].startswith("dev:"):
            dev_str = l[0].split(":")[1]
            components = dev_str.split("_")
            if len(components) >= 2:
                if components[0] == l[1]:
                    nodes = [components[1], l[1]]
                if components[1] == l[1]:
                    nodes = [components[0], l[1]]
            else:
                print(
                    f"Warning: Dev string {dev_str} not mappable to nodes, skipping link."
                )
        if l[1].startswith("dev:"):
            dev_str = l[1].split(":")[1]
            components = dev_str.split("_")
            if len(components) >= 2:
                if components[0] == l[0]:
                    nodes = [l[0], components[1]]
                if components[1] == l[0]:
                    nodes = [l[0], components[0]]
            else:
                print(
                    f"Warning: Dev string {dev_str} not mappable to nodes, skipping link."
                )
        nodes = sorted(nodes)
        # print("new link: ", (nodes[0], nodes[1], link_type))
        pure_node_links.add((nodes[0], nodes[1], link_type))
    return pure_node_links


def update_netmap(
    netmap: bool, scenario_name: str, links: list[tuple[str, str, str]]
) -> None:
    """Writes or updates resolved node links to a .netmap file in the tmp/ directory.

    Args:
        netmap: When False, this function does nothing.
        scenario_name: Used as the output filename (tmp/<scenario_name>.netmap).
        links: Raw link tuples to resolve and write.
    """
    if netmap:
        # check if tmp directory exists
        if not os.path.exists("tmp"):
            os.makedirs("tmp")

        pure_node_links = get_pure_node_links(links)

        print(f"Updating network map tmp/{scenario_name}.netmap")
        with open(f"tmp/{scenario_name}.netmap", "w") as f:
            for l in pure_node_links:
                f.write(f"{l[0]} {l[2]} {l[1]}\n")


def main() -> None:
    args = parse_args()
    update_netmap_file: bool = args.map_network
    scenario_path = Path(args.scenario)
    nodes = nodes_from_compose(scenario_path)
    plan = ContactPlan.from_file(args.contact_plan, nodes)
    player = ContactPlayer(scenario_path.stem, plan, nodes)

    args = parse_args()

    nodes = nodes_from_compose(args.scenario)

    netmap = cast(bool, args.map_network)

    # check all node combinations for common subnets/links
    links: list[tuple[str, str, str]] = [
        (a, b, "-")
        for a, b in combinations(nodes, 2)
        if find_common_subnet_between_nodes(a, b, nodes) is not None
    ]

    # print(mapping)
    # print(nodes)
    # print(links)

    scenario_name = os.path.basename(args.scenario)
    scenario_name = os.path.splitext(scenario_name)[0]

    print(links)

    mapping = {node.id: node.name for node in nodes.values()}
    plan = CoreContactPlan.from_file(args.contact_plan, mapping=mapping)

    # get list of unique nodes from all contacts in plan
    container_devs = []

    for contact in plan.all_contacts():
        if contact[1].startswith("dev:"):
            container_devs.append((contact[0], contact[1].split(":")[1] + "_0"))
            continue

        subnet = find_common_subnet_between_nodes(contact[0], contact[1], nodes)
        if subnet is None:
            print("Error: No common subnet found")
            continue
        for node in contact:
            node_dev = get_dev_for_subnet(node, subnet, nodes)
            container_devs.append((node, node_dev))

    # remove duplicates in container_devs
    container_devs = list(set(container_devs))

    all_contacts = plan.all_contacts()
    all_contacts_sorted_pairs = [tuple(sorted(c)) for c in all_contacts]
    # add "." to sorted pairs to match format in links
    all_contacts_sorted_pairs = [
        tuple([c[0], c[1], "-"]) for c in all_contacts_sorted_pairs
    ]
    all_contacts_sorted_pairs2 = []
    for c in all_contacts_sorted_pairs:
        c = list(c)
        if c[0].startswith("dev:"):
            dev_str = c[0].split(":")[1]
            components = dev_str.split("_")
            if len(components) >= 2:
                if components[0] == c[1]:
                    c[0] = components[1]
                if components[1] == c[1]:
                    c[0] = components[0]
            else:
                print(
                    f"Warning: Dev string {dev_str} not mappable to nodes, skipping link."
                )
        if c[1].startswith("dev:"):
            dev_str = c[1].split(":")[1]
            components = dev_str.split("_")
            if len(components) >= 2:
                if components[0] == c[0]:
                    c[1] = components[1]
                if components[1] == c[0]:
                    c[1] = components[0]
            else:
                print(
                    f"Warning: Dev string {dev_str} not mappable to nodes, skipping link."
                )
        all_contacts_sorted_pairs2.append(tuple(c))
    print("all contacts sorted pairs: ", all_contacts_sorted_pairs2)

    # remove sorted contact pairs from list of links
    links = [l for l in links if tuple(l) not in all_contacts_sorted_pairs2]
    print("links: ", links)

    update_netmap(netmap, scenario_name, links)

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

    cur_time = 0

    # Open a UDP socket for reading control messages on localhost
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.bind(("localhost", 9966))
    control_socket.setblocking(False)

    while True:
        if (
            plan.next_activation(cur_time) == None
            and plan.next_deactivation(cur_time) == None
        ):
            if plan.loop or args.loop:
                print("Looping")
                cur_time = 0
                plan.reset()
                continue
            else:
                print("No more events")
                break
        next_event = min(
            [
                t
                for t in [
                    plan.next_activation(cur_time),
                    plan.next_deactivation(cur_time),
                ]
                if t is not None
            ]
        )
        print("[ %d ] Next event(s) at %d" % (cur_time, next_event))
        sleep_time = next_event - cur_time
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
                        f"{cur_time + int(time_slept)} {next_event}".encode(), addr
                    )
                if data == b"scenario":
                    print(
                        f"cmd: Current scenario is {args.scenario} with {args.contact_plan}"
                    )
                    response = f"{args.scenario} {args.contact_plan}"
                    control_socket.sendto(response.encode(), addr)

                if data == b"links":
                    pure_node_links = get_pure_node_links(links)
                    print(f"cmd: Current links are {pure_node_links}")
                    response = "\n".join(
                        [f"{l[0]} {l[2]} {l[1]}" for l in pure_node_links]
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
        cur_time = next_event
        player.tick(cur_time)

        update_netmap(netmap, scenario_name, links)

    player.teardown()


if __name__ == "__main__":
    main()
