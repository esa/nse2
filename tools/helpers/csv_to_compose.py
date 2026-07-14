#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import sys
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import networkx as nx
import yaml


@dataclass(frozen=True)
class ParsedRow:
    src: str
    dst: str
    ts_start: float
    ts_end: float
    bw: int
    delay: float
    label: str


def parse_csv_rows(csvfile: str, prefix: str = "") -> list[ParsedRow]:
    """Parse a contact CSV into ParsedRow objects, stripping `prefix` from
    node names. Invalid rows are dropped with a warning."""
    rows: list[ParsedRow] = []
    with open(csvfile) as f:
        f.readline()
        for row in csv.reader(f):
            if len(row) not in (6, 7):
                print(
                    f"WARNING: skipping row with {len(row)} columns: {row!r}",
                    file=sys.stderr,
                )
                continue
            rows.append(
                ParsedRow(
                    src=strip_prefix(row[0], prefix),
                    dst=strip_prefix(row[1], prefix),
                    ts_start=float(row[2]),
                    ts_end=float(row[3]),
                    bw=int(row[4]),
                    delay=float(row[5]),
                    label=row[6] if len(row) == 7 else "",
                )
            )
    return rows


def strip_prefix(name: str, prefix: str) -> str:
    """Remove a prefix from a node name if present."""
    if prefix and name.startswith(prefix):
        return name[len(prefix) :]
    return name


def strip_dir_suffix(label: str) -> str:
    """Remove a trailing _ul or _dl direction suffix, if present."""
    if label.endswith("_ul") or label.endswith("_dl"):
        return label[: -len("_ul")]
    return label


def compute_multi_pairs(rows: list[ParsedRow]) -> set[tuple[str, str]]:
    """Return node pairs needing a dedicated interface: those with more
    than one distinct label after stripping _ul/_dl suffixes."""
    pair_keys: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rows:
        pair_keys[tuple(sorted([r.src, r.dst]))].add(strip_dir_suffix(r.label))  # pyright: ignore[reportArgumentType]
    return {pair for pair, keys in pair_keys.items() if len(keys) > 1}


def make_ifname(
    node1: str, node2: str, label: str, multi_pairs: set[tuple[str, str]]
) -> str | None:
    """Build an interface name for this pair+label, or None if the pair
    should just use the plain node name. Falls back to a 12-char MD5 hash
    if the name would exceed the 14-char interface limit."""
    a, b = tuple(sorted([node1, node2]))
    if (a, b) not in multi_pairs:
        return None
    key = strip_dir_suffix(label)
    ifname = f"{a}_{b}_{key}" if key else f"{a}_{b}"
    if len(ifname) >= 14:
        ifname = hashlib.md5(ifname.encode()).hexdigest()[:12]
    return ifname


def load_nodes(path: str | None, prefix: str = "") -> dict[str, dict[str, str]]:
    """Load optional node metadata indexed by stripped node label."""
    if path is None or not os.path.isfile(path):
        print(
            "WARNING: no nodes.json found; generating node metadata from CSV labels",
            file=sys.stderr,
        )
        return {}

    with open(path) as f:
        raw_nodes = json.load(f)

    nodes: dict[str, dict[str, str]] = {}
    for node in raw_nodes:
        label = strip_prefix(node["node_label"], prefix)
        nodes[label] = {
            "node_label": label,
            "node_name": node["node_name"],
            "node_id": node["node_id"],
        }

    return nodes


def get_graph_from_csv(
    csvfile: str,
    nodes: dict[str, dict[str, str]],
    prefix: str = "",
) -> nx.MultiDiGraph[str]:
    """Build a directed multi-graph from a CCSDS contact CSV file."""
    G: nx.MultiDiGraph[str] = nx.MultiDiGraph()
    rows = parse_csv_rows(csvfile, prefix=prefix)
    multi_pairs = compute_multi_pairs(rows)
    G.graph["multi_pairs"] = multi_pairs

    for r in rows:
        for node in (r.src, r.dst):
            if node not in nodes:
                node_id = str(len(nodes) + 1)
                print(
                    f"WARNING: node {node!r} missing from nodes.json; ",
                    f"using generated ID {node_id!r}",
                    file=sys.stderr,
                )
                nodes[node] = {
                    "node_label": node,
                    "node_name": node,
                    "node_id": node_id,
                }

            if node not in G.nodes:
                G.add_node(
                    node,
                    node_label=nodes[node]["node_label"],
                    node_name=nodes[node]["node_name"],
                    node_id=nodes[node]["node_id"],
                    type="Host",
                )

        dynamic_link = not (r.ts_start == 0 and r.ts_end == -1)
        edge_key = make_ifname(r.src, r.dst, r.label, multi_pairs) or r.label

        if not G.has_edge(r.src, r.dst, key=edge_key):
            G.add_edge(
                r.src,
                r.dst,
                key=edge_key,
                dynamic_link=dynamic_link,
                bw=r.bw,
                delay=r.delay,
                loss=0,
                jitter=0,
                label=r.label,
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
    header: str = "",
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
            "privileged": True,
            "environment": [
                # f"NODE_LABEL={data['node_label']}",
                f"NODE_NAME={data['node_name']}",
                f"NODE_ID={data['node_id'].removeprefix('ipn:').removesuffix('.0')}",
                f"TYPE={data['type']}",
            ],
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

    multi_pairs = G.graph.get("multi_pairs", set())
    subnet_count = 0
    subnets: dict[str, str] = {}
    for src, dst, edge_data in G.edges(data=True):
        node1, node2 = tuple(sorted([src, dst]))
        label: str = edge_data["label"]
        net_name: str = (
            make_ifname(node1, node2, label, multi_pairs) or f"{node1}_{node2}"
        )

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
        if header:
            print(header, file=out)
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
    parser.add_argument(
        "--nodes",
        "--mapping",
        dest="nodes",
        type=str,
        help="JSON file defining node labels, names, and IDs",
    )
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

    date_str = datetime.date.today().isoformat()
    cmd_str = f"{os.path.basename(sys.argv[0])} {' '.join(sys.argv[1:])}"
    header = f"# Generated: {date_str}\n# Command: {cmd_str}\n"

    nodes = load_nodes(args.nodes, prefix=args.strip_prefix)

    G = get_graph_from_csv(
        args.csvfile,
        nodes,
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
        header=header,
        output=args.output,
    )

    if args.export_graphml:
        export_graphml(G, args.export_graphml)


if __name__ == "__main__":
    main()
