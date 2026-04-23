#!/usr/bin/env python3

import argparse
import os
import signal
import socket
import sys
import time
from itertools import combinations
from typing import cast
from tools.contact_player.ccp import ContactState, CoreContact, CoreContactPlan
from tools.contact_player.tc_netem import run_in_container, set_on_interface
from tools.lib.scenario import NetworkInterface, Node, nodes_from_compose


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments.

    Returns:
        Namespace with attributes: ``scenario`` (str), ``contact_plan`` (str),
        ``loop`` (bool | None), ``map_network`` (bool).
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


args = parse_args()

nodes = nodes_from_compose(args.scenario)

netmap = cast(bool, args.map_network)

mapping = {}

for node in nodes.values():
    mapping[node.id] = node.name

    for net_name, ip in node.ips.items():
        res = run_in_container(node.name, f"ip a | grep {ip}")
        if not res:
            print(f"Error: IP {ip} not found in container {node.name}")
            continue
        dev = res.rsplit(" ", maxsplit=1)[1].strip()
        node.interfaces[net_name] = NetworkInterface(dev=dev, ip=ip)


def find_common_subnet_between_nodes(
    node1: str, node2: str, nodes: dict[str, Node]
) -> str | None:
    for k in nodes[node1].interfaces.keys():
        if k in nodes[node2].interfaces:
            return k
    return None


def get_dev_for_subnet(node: str, subnet: str, nodes: dict[str, Node]) -> str:
    return nodes[node].interfaces[subnet].dev


def set_link(
    contact: CoreContact, deactivate: bool = False, command: str = "change"
) -> None:
    node1 = contact.nodes[0]
    node2 = contact.nodes[1]

    loss = contact.loss
    if deactivate:
        loss = 100.0

    if node2.startswith("dev:"):
        network = node2.split(":")[1]
        net_dev = network + "_0"
        for node in nodes.values():
            if network in node.interfaces and node.name != node1:
                node2 = node.name
        link = find_common_subnet_between_nodes(node1, node2, nodes)
        if link is None:
            print("WARNING: Link not found for %s, %s" % (node1, node2))
            return
    else:
        link = find_common_subnet_between_nodes(node1, node2, nodes)
        if link is None:
            print("WARNING: Link not found for %s, %s" % (node1, node2))
            return
        net_dev = get_dev_for_subnet(node1, link, nodes)

    set_on_interface(
        node1,
        net_dev,
        command=command,
        loss=loss,
        delay=contact.delay,
        jitter=contact.jitter,
        bandwidth=contact.bw,
    )

    # set links symmetrically, so also on the second node
    if contact.symmetric:
        set_on_interface(
            node2,
            get_dev_for_subnet(node2, link, nodes),
            command=command,
            loss=loss,
            delay=contact.delay,
            jitter=contact.jitter,
        )


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


print(links)

plan = CoreContactPlan.from_file(args.contact_plan, mapping=mapping)

# get list of unique nodes from all contacts in plan
container_devs: list[tuple[str, str]] = []

for contact in plan.contacts:
    node1 = contact.nodes[0]
    node2 = contact.nodes[1]

    if node2.startswith("dev"):
        network = node2.split(":")[1]
        container_devs.append((node1, network + "_0"))
        if contact.symmetric:
            for node in nodes.values():
                if network in node.interfaces and node.name != node1:
                    node2 = node.name
                    container_devs.append(
                        (node2, get_dev_for_subnet(node2, network, nodes))
                    )
        continue
    subnet = find_common_subnet_between_nodes(node1, node2, nodes)
    if subnet is None:
        print("Error: No common subnet found")
        continue
    for node in contact.nodes:
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


# setup handler to intercept ctrl c
def signal_handler(sig, frame):
    global args
    print("You pressed Ctrl+C")
    fixed = plan.fixed
    for contact in fixed:
        print("Deactivating fixed contact %s" % contact)
        set_link(contact, command="del")
    for c, d in container_devs:
        print(f"Removing tc netem for {c} on device {d}")
        set_on_interface(c, d, command="del", loss=0.0)

    sys.exit(0)


# setting packet loss to 100% for all dynamic contacts
for c, d in container_devs:
    print(f"Setting up tc for {c} on device {d} with 100% loss")
    set_on_interface(c, d, command="add", loss=100.0)

signal.signal(signal.SIGINT, signal_handler)

fixed = plan.fixed
for contact in fixed:
    print("Activating fixed contact %s" % contact)
    set_link(contact, command="add")

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
            for t in [plan.next_activation(cur_time), plan.next_deactivation(cur_time)]
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
                response = "\n".join([f"{l[0]} {l[2]} {l[1]}" for l in pure_node_links])
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
    for contact, state in plan.need_activation(cur_time):
        print("[ %d ] Activating %s" % (cur_time, contact))
        set_link(contact)
        l = sorted([contact.nodes[0], contact.nodes[1]])
        l.append(".")
        static_link = (l[0], l[1], "-")
        if static_link in links:
            links.remove(static_link)
        links.append(tuple(l))

        plan.contacts[contact] = ContactState.LIVE

    for contact, state in plan.need_deactivation(cur_time):
        print("[ %d ] Deactivating %s" % (cur_time, contact))
        set_link(contact, deactivate=True)
        l = sorted([contact.nodes[0], contact.nodes[1]])
        l.append(".")
        try:
            links.remove(tuple(l))
        except ValueError:
            pass
        plan.contacts[contact] = ContactState.POST

    links = list(set([tuple(l) for l in links]))
    update_netmap(netmap, scenario_name, links)


# setting packet loss to 0% for all dynamic contacts, remove netem
for c, d in container_devs:
    print(f"Removing tc netem for {c} on device {d}")
    set_on_interface(c, d, command="del", loss=0.0)

links = []
update_netmap(netmap, scenario_name, links)
