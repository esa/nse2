#!/usr/bin/env python3

import networkx as nx
import json
import sys


def gml2viz(gml_filename, viz_filename):
    G = nx.read_graphml(gml_filename)
    nodes = list(G.nodes(data=True))
    links = list(G.edges)
    nodes_viz = [
        {
            "name": val["name"],
            "x": val["x"],
            "y": val["y"],
            "e_id": f"ipn:{n}.0",
            "color": "#0384fc",
            "type": "computer",
        }
        for n, val in nodes
    ]

    config = {
        "title": "scenario title",
        "description": "scenario description",
        "background": "extras/background.jpg",
        "links": "scenario.netmap",
        "nodes": nodes_viz,
        # "links": [{"source": link[0], "target": link[1]} for link in links]
    }

    # with open(viz_filename, "w") as f:
    #     json.dump(config, f, indent=4)
    print(json.dumps(config, indent=2))


if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <graphml_filename>")
    sys.exit(1)


gml2viz(sys.argv[1], "test.json")
