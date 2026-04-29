#!/usr/bin/env python3

from datetime import datetime
from dateutil.parser import parse
import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    "-m", "--map-nodes", help="Map nodes, e.g., 'KIR=gs1,CEB=gs2,EO_orbiter=eosat'"
)
parser.add_argument(
    "-l",
    "--link-multiplicator",
    help="Link multiplicator, e.g., 'gs1_eosat=2,gs2_eosat=2'",
)
parser.add_argument(
    "-s",
    "--speedup",
    help="Speedup factor for simulation time",
)
parser.add_argument(
    "-S",
    "--symmetric-links",
    help="Generate only a single contact line per link, assume a symmetric connection.",
    action="store_true",
)
parser.add_argument(
    "--ignore-delay",
    help="Ignore delay in contacts file",
    action="store_true",
)
parser.add_argument("contacts", help="CSV file with contacts")
args = parser.parse_args()
mapping = {}
multiplicator = {}
if args.link_multiplicator:
    for pair in args.link_multiplicator.split(","):
        link, mult = pair.split("=")
        multiplicator[link] = int(mult)

if args.map_nodes:
    for pair in args.map_nodes.split(","):
        node, name = pair.split("=")
        mapping[node] = name

speedup = 1
if args.speedup:
    speedup = float(args.speedup)

contacts = []
sim_start = 0
with open(args.contacts) as f:
    # skip header
    hdr = f.readline()
    if "# Simulation starting time:" in hdr:
        sim_start = parse(hdr.split(":")[1].strip(), ignoretz=True)
        print(f"Simulation start: {sim_start}")

    for line in f:
        delay = 0
        if line.count(",") == 4:
            src, dst, start, end, duration = line.strip().split(",")
        elif line.count(",") == 5:
            src, dst, start, end, duration, delay = line.strip().split(",")
        else:
            print(f"Invalid line: {line}")
            continue
        src = src.strip()
        dst = dst.strip()
        if src in mapping:
            src = mapping[src]
        if dst in mapping:
            dst = mapping[dst]

        if args.ignore_delay:
            delay = 0

        contacts.append(
            (
                parse(start, ignoretz=True),
                parse(end, ignoretz=True),
                src,
                dst,
                float(duration),
                round(float(delay) * 1000),
            )
        )

# sort by start time
contacts.sort(key=lambda x: x[0])
if sim_start == 0:
    sim_start = contacts[0][0]

# print(f"First contact: {contacts[0][0]}")

# adjust start times relative in seconds to sim_start
contacts = [
    (
        int((start - sim_start).total_seconds()),
        int((end - sim_start).total_seconds()),
        src,
        dst,
        duration,
        delay,
    )
    for start, end, src, dst, duration, delay in contacts
]
# apply speedup
contacts = [
    (int(start / speedup), int(end / speedup), src, dst, duration, delay)
    for start, end, src, dst, duration, delay in contacts
]

for start, end, n1, n2, dur, delay in contacts:
    # print(f"{start} {end} {n1} {n2} {dur}")
    m = 1
    if f"{n1}_{n2}" in multiplicator:
        m = multiplicator[f"{n1}_{n2}"]
    elif f"{n2}_{n1}" in multiplicator:
        m = multiplicator[f"{n2}_{n1}"]

    link = [n1, n2]
    link.sort()
    link = "_".join(link)
    if m > 1:
        for i in range(m):
            print(
                f"a contact +{start} +{end} {n1} dev:{link}_{i+1} 1mbit 0.0 {delay} 0"
            )
            if not args.symmetric_links:
                print(
                    f"a contact +{start} +{end} {n2} dev:{link}_{i+1} 1mbit 0.0 {delay} 0"
                )
    else:
        print(f"a contact +{start} +{end} {n1} {n2} 1mbit 0.0 {delay} 0")
        if not args.symmetric_links:
            print(f"a contact +{start} +{end} {n2} {n1} 1mbit 0.0 {delay} 0")

    # print()
