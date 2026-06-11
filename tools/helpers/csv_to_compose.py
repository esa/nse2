#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from contextlib import nullcontext
from typing import Any

import networkx as nx
import yaml


def strip_prefix(name: str, prefix: str) -> str:
    """Remove a prefix from a node name if present."""
    if prefix and name.startswith(prefix):
        return name[len(prefix) :]
    return name


def get_netif(node1: str, node2: str, label: str) -> str:
    """Generate a docker-compatible network name for a connection.

    Ground links (labels without underscores like ``eth``, ``fiber``)
    use just the sorted node pair.  Space links (labels with underscores
    like ``low_ul``) append the first word of the label as a short suffix.

    Names exceeding 14 characters are replaced with their MD5 hash to
    respect the Docker / Linux interface name length limit.
    """
    a, b = tuple(sorted([node1, node2]))
    if "_" in label:
        ifname = f"{a}_{b}_{label.split('_')[0]}"
    else:
        ifname = f"{a}_{b}"
    if len(ifname) >= 14:
        ifname = hashlib.md5(ifname.encode()).hexdigest()[:12]
    return ifname


def get_graph_from_csv(
    csvfile: str,
    mapping: dict[str, Any],
    prefix: str = "",
) -> nx.MultiDiGraph[str]:
    """Build a directed multi-graph from a CCSDS contact CSV file.

    `mapping` is a dict used to look up / auto-assign node IDs.
    It is mutated in place: new nodes get ``{"id": N}`` entries under
    ``mapping["nodes"]``.
    """
    G: nx.MultiDiGraph[str] = nx.MultiDiGraph()
    with open(csvfile) as f:
        f.readline()
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 6 or len(row) == 7:
                node1 = strip_prefix(row[0], prefix)
                node2 = strip_prefix(row[1], prefix)
                ts_start = float(row[2])
                ts_end = float(row[3])
                bw = int(row[4])
                delay = float(row[5])
                label = row[6] if len(row) == 7 else ""

                for node in (node1, node2):
                    if node not in mapping["nodes"]:
                        mapping["nodes"][node] = {
                            "id": len(mapping["nodes"]) + 1,
                        }
                    if node not in G.nodes:
                        G.add_node(
                            node,
                            name=node,
                            type="Host",
                            id=mapping["nodes"][node]["id"],
                        )

                dynamic_link = not (ts_start == 0 and ts_end == -1)

                if not G.has_edge(node1, node2, key=label):
                    G.add_edge(
                        node1,
                        node2,
                        key=label,
                        dynamic_link=dynamic_link,
                        bw=bw,
                        delay=delay,
                        loss=0,
                        jitter=0,
                        label=label,
                    )
            else:
                print(
                    f"WARNING: skipping row with {len(row)} columns: {row!r}",
                    file=sys.stderr,
                )
    return G


def export_graphml(G: nx.Graph[str], output_path: str) -> None:
    """Write the topology graph to a GraphML file."""
    x = 64
    y = 64
    for _, data in G.nodes(data=True):
        data["x"] = x
        data["y"] = y
        x += 64
        if x > 1024:
            x = 64
            y += 64

    nx.write_graphml(G, output_path)


def graph_to_compose(
    G: nx.Graph[str],
    *,
    name: str,
    base_subnet: str,
    image: str,
    entrypoint: str | None = None,
    build: str | None = None,
    node_volumes: str | None = None,
    compose_volume: bool = False,
    output: str = "-",
) -> None:
    """Write a docker-compose.yml from a topology graph."""
    if node_volumes is not None and not os.path.isdir(node_volumes):
        os.makedirs(node_volumes)

    compose_file = output if output != "-" else "compose.yml"
    base_name = os.path.basename(compose_file)

    compose: dict[str, Any] = {
        "name": name,
        "services": {},
        "networks": {},
    }

    for node_name, data in G.nodes(data=True):
        volumes: list[str] = []
        if compose_volume:
            volumes.append(f"./{base_name}:/docker-compose.yml:ro")
        if node_volumes:
            volumes.append(f"./{node_volumes}/{node_name}:/data")
            os.makedirs(f"{node_volumes}/{node_name}", exist_ok=True)
        svc: dict[str, Any] = {
            "container_name": node_name,
            "hostname": node_name,
            "cap_add": ["NET_ADMIN"],
            "privileged": "true",
            "environment": [f"NODE_ID={data['id']}", f"TYPE={data['type']}"],
            "networks": {},
        }
        if volumes:
            svc["volumes"] = volumes
        if build:
            svc["build"] = build
        else:
            svc["image"] = image
        if entrypoint and not build:
            svc["entrypoint"] = entrypoint
        compose["services"][node_name] = svc

    subnet_count = 0
    subnets: dict[str, str] = {}
    for src, dst, edge_data in G.edges(data=True):
        node1, node2 = tuple(sorted([src, dst]))
        label: str = edge_data["label"]
        net_name: str = get_netif(node1, node2, label)

        if net_name not in subnets:
            subnets[net_name] = f"{base_subnet}.{subnet_count}"
            subnet_count += 1
            compose["networks"][net_name] = {
                "driver": "bridge",
                "ipam": {"config": [{"subnet": subnets[net_name] + ".0/24"}]},
                "driver_opts": {
                    "com.docker.network.container_iface_prefix": net_name + "_"
                },
            }

        compose["services"][node1]["networks"][net_name] = {
            "ipv4_address": subnets[net_name] + ".2"
        }
        compose["services"][node2]["networks"][net_name] = {
            "ipv4_address": subnets[net_name] + ".3"
        }

    with open(output, "w") if output != "-" else nullcontext(sys.stdout) as out:
        print(yaml.dump(compose, default_flow_style=False, sort_keys=False), file=out)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("csvfile", type=str)
    parser.add_argument("--output", "-o", type=str, default="-")
    parser.add_argument(
        "--strip-prefix",
        type=str,
        default="",
        help="Remove this prefix from all node names (e.g. --strip-prefix eo)",
    )
    parser.add_argument("--mapping", type=str, required=False)
    parser.add_argument(
        "--entrypoint",
        "-e",
        type=str,
        default='sh -c "apk add iproute2 bash && tail -f /dev/null"',
        help="Container entrypoint (default installs iproute2+bash and keeps alive)",
    )
    parser.add_argument("--base-subnet", type=str, default="172.33")
    parser.add_argument("--name", "-n", type=str, default="autogenerated from csv file")
    parser.add_argument("--image", "-i", type=str, default="alpine")
    parser.add_argument("--export-graphml", "-g", type=str)
    parser.add_argument(
        "--node-volumes",
        type=str,
        help="generate volumes for nodes under given directory",
    )
    parser.add_argument(
        "--build",
        "-b",
        type=str,
        help="use this build path instead of a pre-built image",
    )
    parser.add_argument(
        "--mount-compose",
        action="store_true",
        help="mount the compose file as a volume in each container",
    )

    args = parser.parse_args()

    mapping: dict[str, Any] = {}
    if args.mapping is not None:
        with open(args.mapping) as f:
            mapping = json.load(f)
    if "nodes" not in mapping:
        mapping["nodes"] = {}

    G = get_graph_from_csv(
        args.csvfile,
        mapping,
        prefix=args.strip_prefix,
    )

    graph_to_compose(
        G,
        name=args.name,
        base_subnet=args.base_subnet,
        image=args.image,
        entrypoint=args.entrypoint,
        build=args.build,
        node_volumes=args.node_volumes,
        compose_volume=args.mount_compose,
        output=args.output,
    )

    if args.export_graphml:
        export_graphml(G, args.export_graphml)


if __name__ == "__main__":
    main()
