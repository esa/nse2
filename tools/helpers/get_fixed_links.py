#!/usr/bin/env python3

import networkx as nx
import sys

if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <graphml-file>")
    sys.exit(1)

G = nx.read_graphml(sys.argv[1])

nodemap = {}
for node_id, data in G.nodes(data=True):
    if data["type"] == "Host":
        nodemap[node_id] = data["name"]


def bw_to_human_readable(bw):
    if bw == 0:
        return "0"
    if bw > 1_000 and bw < 1_000_000:
        return f"{bw // 1_000}kbit"
    if bw >= 1_000_000 and bw < 1_000_000_000:
        return f"{bw // 1_000_000}mbit"
    if bw >= 1_000_000_000:
        return f"{bw // 1_000_000_000}gbit"

    return f"{bw}"


for u, v, data in G.edges(data=True):
    if not "bw" in data:
        print(f"Skipping {u} {v} because no bw", file=sys.stderr)
        continue
    bw = bw_to_human_readable(data["bw"])
    print(
        f"a fixed {nodemap[u]} {nodemap[v]} {bw} {data['loss']} {data['delay']} {data['jitter']}"
    )
    print(
        f"a fixed {nodemap[v]} {nodemap[u]} {bw} {data['loss']} {data['delay']} {data['jitter']}"
    )
    print()
