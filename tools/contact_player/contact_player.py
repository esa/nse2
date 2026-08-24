#!/usr/bin/env python3


from tc_netem import *
from ccp import *
import argparse
import time
import signal
import sys
import os
import yaml
import socket


def load_scenario(path):
    """
    Loads the docker compose scenario from the passed filepath.
    """
    print(f"Loading scenario from {path}.")
    nodes: dict[str, dict] = {}

    with open(path) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        if "x-description" in config:
            print(f"Description: {config['x-description']}")

        services: dict[str, dict[str, list[str]]] = config["services"]
        for name, item in services.items():
            env_vars: list[str] = item["environment"]
            node_id = next(var for var in env_vars if var.startswith("NODE_ID"))
            node_eID = f"ipn:{node_id.split('=')[1]}.0"
            new_node: dict[str, str] = {
                "eid": node_eID,
                "name": name,
                "networks": {},
                "IPs": {},
            }

            for net_name, value in item["networks"].items():
                new_node["networks"][net_name] = True
                new_node["IPs"][net_name] = value["ipv4_address"]
                print(
                    f"Node {node_eID} connected to network {net_name} with {value['ipv4_address']}"
                )

            nodes[node_eID] = new_node

    print(f"Created {len(nodes)} nodes.")
    return nodes


def find_common_subnet_between_nodes(
    node1: str, node2: str, nodes: dict[str, dict[str, dict[str, str]]]
) -> str | None:
    for k in nodes[node1].keys():
        if k in nodes[node2]:
            return k
    return None


def get_dev_for_subnet(
    node: str, subnet: str, nodes: dict[str, dict[str, dict[str, str]]]
) -> str:
    return nodes[node][subnet]["dev"]


def get_network_for_interface(
    node: str, interface: str, nodes: dict[str, dict[str, dict[str, str]]]
) -> str | None:
    for network, net_conf in nodes[node].items():
        if net_conf["dev"] == interface:
            return network
    print(
        f"WARNING: could not find a network for interface {interface} on node {node}!"
    )
    return None


def contact_to_node_iface(
    contact: CoreContact, nodes: dict[str, dict[str, dict[str, str]]]
) -> list[tuple[str, str]]:
    """
    Resolve a contact into the list of (node, interface) tuples, taking (a)symmetry of the contact into account.
    """

    node1 = contact.nodes[0]
    node2 = contact.nodes[1]

    node_iface_tuples: list[tuple[str, str]] = []

    if node2.startswith("dev:"):
        node1_iface = node2.split(":")[1] + "_0"

        node_iface_tuples.append((node1, node1_iface))

        if contact.symmetric:
            network = get_network_for_interface(node1, node1_iface, nodes)
            if network is None:
                return node_iface_tuples

            node2_iface: str | None = None
            for candidate_node, candidate_networks in nodes.items():
                if candidate_node == node1:
                    continue

                if network in candidate_networks:
                    node2_iface = candidate_networks[network]["dev"]
                    node2 = candidate_node
            if node2_iface is None:
                print(
                    f"WARNING: Could not apply symmetric rule for {node1} <-> {node2}"
                )
                return node_iface_tuples
            node_iface_tuples.append((node2, node2_iface))

        return node_iface_tuples

    network = find_common_subnet_between_nodes(node1, node2, nodes)
    if network is None:
        print(f"WARNING: No common network between {node1} and {node2}")
        return []
    node1_iface = get_dev_for_subnet(node1, network, nodes)
    node_iface_tuples.append((node1, node1_iface))

    if contact.symmetric:
        node2_iface = get_dev_for_subnet(node2, network, nodes)
        node_iface_tuples.append((node2, node2_iface))

    return node_iface_tuples


def set_link(
    nodes: dict[str, dict[str, dict[str, str]]],
    contact: CoreContact,
    deactivate=False,
    command="change",
):
    loss = contact.loss
    if deactivate:
        loss = 100.0

    node_iface_tuples = contact_to_node_iface(contact, nodes)

    for node, iface in node_iface_tuples:
        set_on_interface(
            node,
            iface,
            command=command,
            loss=loss,
            delay=contact.delay,
            jitter=contact.jitter,
            bandwidth=contact.bw,
        )


def get_pure_node_links(links: list) -> set:
    pure_node_links = set()
    for l in links:
        # print("Link: ", l)
        nodes = [l[0], l[1]]
        link_type = l[2]

        if l[0].startswith("dev:"):
            dev_str = l[0].split(":")[1]
            other_node = l[1]
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
            other_node = l[0]
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


def update_netmap(netmap: bool, scenario_name: str, links: list):
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
    # parse scenario filename from args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l", "--loop", metavar="LOOP", type=bool, help="Override looping"
    )
    parser.add_argument(
        "-m", "--map-network", help="Map network links", action="store_true"
    )
    parser.add_argument("scenario", help="scenario file to load")
    parser.add_argument("ccp", help="core contact plan to load")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)

    netmap = args.map_network

    mapping = {}
    nodes: dict[str, dict[str, dict[str, str]]] = {}
    links = []

    for k, v in scenario.items():
        # extract node number from key
        node_id = k.split(":")[1].split(".")[0]
        mapping[node_id] = v.get("name")
        for k, v2 in v["IPs"].items():
            res = run_in_container(v.get("name"), f"ip a | grep {v2}")
            if len(res) == 0:
                print("Error: IP not found")
                continue
            net_if = res.rsplit(" ", maxsplit=1)[1].strip()
            v["IPs"][k] = {"dev": net_if, "ip": v2}
        nodes[v.get("name")] = v["IPs"]

    # check all node combinations for common subnets/links

    for n1 in nodes.keys():
        for n2 in nodes.keys():
            if n1 == n2:
                continue
            link = find_common_subnet_between_nodes(n1, n2, nodes)
            if link is not None:
                # sort n1 and n2 to avoid duplicates
                l = sorted([n1, n2])
                l.append("-")
                links.append(l)
    links = list(set([tuple(l) for l in links]))

    # print(mapping)
    # print(nodes)
    # print(links)

    scenario_name = os.path.basename(args.scenario)
    scenario_name = os.path.splitext(scenario_name)[0]

    print(links)

    plan = CoreContactPlan.from_file(args.ccp, mapping=mapping)

    # get list of unique nodes from all contacts in plan
    container_devs: list[tuple[str, str]] = []

    for contact in plan.contacts:
        node_iface_tuples = contact_to_node_iface(contact, nodes)
        container_devs += node_iface_tuples

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
            set_link(nodes, contact, command="del")
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
        set_link(nodes, contact, command="add")

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
                    print(f"cmd: Current scenario is {args.scenario} with {args.ccp}")
                    response = f"{args.scenario} {args.ccp}"
                    control_socket.sendto(response.encode(), addr)

                if data == b"links":
                    pure_node_links = get_pure_node_links(links)
                    print(f"cmd: Current links are {pure_node_links}")
                    response = "\n".join(
                        [f"{l[0]} {l[2]} {l[1]}" for l in pure_node_links]
                    )
                    control_socket.sendto(response.encode(), addr)

            except socket.error as e:
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
            set_link(nodes, contact)
            l = sorted([contact.nodes[0], contact.nodes[1]])
            l.append(".")
            static_link = (l[0], l[1], "-")
            if static_link in links:
                links.remove(static_link)
            links.append(tuple(l))

            plan.contacts[contact] = ContactState.LIVE

        for contact, state in plan.need_deactivation(cur_time):
            print("[ %d ] Deactivating %s" % (cur_time, contact))
            set_link(nodes, contact, deactivate=True)
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


if __name__ == "__main__":
    main()
