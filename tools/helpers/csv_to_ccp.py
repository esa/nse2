#!/usr/bin/env python3

import argparse
import csv
import dataclasses
import datetime
import hashlib
import os
import sys
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import TextIO

FixedRow = tuple[str, str, str, str, str, str, str]
"""Converted fixed row: (src, dst, bw, loss, delay, jitter, eq)."""

ContactRow = tuple[str, str, str, str, str, str, str, str, str]
"""Converted contact row: (start, end, src, dst, bw, loss, delay, jitter, eq)."""

HEADER: str = """# Contact Plan
# Defines scheduled contacts and fixed links between nodes.
#
# Directives:
#   s loop <n>        : loop behaviour — 1 to repeat indefinitely, 0 (or omit) for no loop
#   a <contact|fixed> : add a fixed link or a fluctuating contact with properties described below 
#
# Columns:
#   type      : 'a contact' for scheduled links, 'a fixed' for fixed links
#   start     : contact start time relative to scenario start (seconds, +offset)
#   end       : contact end time relative to scenario start (seconds, +offset)
#   src       : source node (node ID | node name)
#   dst       : destination node (node ID | node name | `dev:<interfacename>`)
#   bw        : bandwidth (e.g. 30mbit)
#   loss      : packet loss percentage (e.g. 0.0)
#   delay     : one-way propagation delay (ms)
#   jitter    : delay jitter (ms)
#   symmetric : '=' to apply the link in both directions, omit for one-way
"""


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


def shorten_label(label: str) -> str:
    """Shorten known label parts used in generated interface/network names."""
    LABEL_REPLACEMENTS = {
        "high": "hi",
        "low": "lo",
    }
    return "_".join(LABEL_REPLACEMENTS.get(part, part) for part in label.split("_"))


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
    key = shorten_label(strip_dir_suffix(label))
    ifname = f"{a}_{b}_{key}" if key else f"{a}_{b}"
    if len(ifname) >= 14:
        ifname_md5 = hashlib.md5(ifname.encode()).hexdigest()[:12]
        print(
            f"WARNING: name {ifname} is too long - using truncated md5 hash {ifname_md5} instead",
            file=sys.stderr,
        )
        return ifname_md5
    return ifname


def bps_to_human(bps: int) -> str:
    """Convert bps integer to human-readable bandwidth string."""
    if bps >= 1_000_000_000 and bps % 1_000_000_000 == 0:
        return f"{bps // 1_000_000_000}gbit"
    if bps >= 1_000_000 and bps % 1_000_000 == 0:
        return f"{bps // 1_000_000}mbit"
    if bps >= 1_000 and bps % 1_000 == 0:
        return f"{bps // 1_000}kbit"
    return f"{bps}bit"


def apply_speedup_and_scale(
    rows: list[ParsedRow], speedup: float, bw_scale: float
) -> list[ParsedRow]:
    """Return a new row list of of contacts with timestamps divided by speedup
    and bandwidth multiplied by bw_scale."""
    result: list[ParsedRow] = []
    for r in rows:
        ts_start, ts_end = r.ts_start, r.ts_end
        if speedup != 1.0 and ts_end != -1:
            ts_start = round(ts_start / speedup)
            ts_end = round(ts_end / speedup)
        bw = int(round(r.bw * bw_scale))
        result.append(dataclasses.replace(r, ts_start=ts_start, ts_end=ts_end, bw=bw))
    return result


def merge_symmetric_rows(rows: list[ParsedRow]) -> list[tuple[ParsedRow, bool]]:
    """Collapse symmetric reversed-pair rows into single '=' entries.

    Two rows are merged only when they refer to the same connection
    in opposite directions (A->B and B->A) with matching timestamps,
    bandwidth, and delay. Returns each row paired with a symmetric flag.
    """
    groups: defaultdict[tuple[str, str, str], list[ParsedRow]] = defaultdict(list)
    for r in rows:
        a, b = tuple(sorted([r.src, r.dst]))
        groups[(a, b, r.label)].append(r)

    result: list[tuple[ParsedRow, bool]] = []
    for group_rows in groups.values():
        if len(group_rows) == 2:
            r1, r2 = group_rows
            if (
                r1.src == r2.dst
                and r1.dst == r2.src
                and r1.ts_start == r2.ts_start
                and r1.ts_end == r2.ts_end
                and r1.bw == r2.bw
                and r1.delay == r2.delay
            ):
                result.append((r1, True))
                continue
        result.extend((r, False) for r in group_rows)
    return result


def _format_block(
    directive: str,
    header: tuple[str, ...],
    rows: list[tuple[str, ...]],
    right_align: tuple[bool, ...],
) -> list[str]:
    """Return column-aligned lines for a CCP block (guide comment + data rows)."""
    if not rows:
        return []
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]

    guide_prefix = f"# <{directive}>"
    data_prefix = f"a {directive}"
    data_prefix += " " * max(0, len(guide_prefix) - len(data_prefix))

    lines: list[str] = []
    guide = " ".join(
        f"{col:>{widths[i]}}" if right_align[i] else f"{col:<{widths[i]}}"
        for i, col in enumerate(header)
    )
    lines.append(f"{guide_prefix} {guide}")

    for row in rows:
        data = " ".join(
            f"{row[i]:>{widths[i]}}" if right_align[i] else f"{row[i]:<{widths[i]}}"
            for i in range(len(header))
        )
        lines.append(f"{data_prefix} {data}")
    return lines


def convert_rows(
    rows: list[tuple[ParsedRow, bool]], multi_pairs: set[tuple[str, str]]
) -> tuple[list[FixedRow], list[ContactRow]]:
    """Convert merged rows into printable fixed and contact row tuples.

    All values are transformed to their final string form here, so the
    formatting step operates on ready-to-print data only.
    """
    fixed: list[FixedRow] = []
    contact: list[ContactRow] = []

    for r, symmetric in rows:
        bw = bps_to_human(r.bw)
        delay = str(int(round(r.delay * 1000)))
        eq = "=" if symmetric else ""

        ifname = make_ifname(r.src, r.dst, r.label, multi_pairs)
        dst = f"dev:{ifname}" if ifname else r.dst

        if r.ts_start == 0 and r.ts_end == -1:
            fixed.append((r.src, dst, bw, "0.0", delay, "0.0", eq))
        else:
            contact.append(
                (
                    f"+{int(round(r.ts_start))}",
                    f"+{int(round(r.ts_end))}",
                    r.src,
                    dst,
                    bw,
                    "0.0",
                    delay,
                    "0.0",
                    eq,
                )
            )

    return fixed, contact


def format_and_output(
    rows: list[tuple[ParsedRow, bool]],
    multi_pairs: set[tuple[str, str]],
    out: TextIO,
) -> None:
    """Convert rows and write column-aligned CCP output."""
    fixed, contact = convert_rows(rows, multi_pairs)
    contact.sort(key=lambda r: int(r[0]))

    for line in _format_block(
        "fixed",
        ("<src>", "<dst>", "[bw]", "[loss]", "[delay]", "[jitter]", "[=]"),
        fixed,
        (False, False, True, True, True, True, True),
    ):
        print(line, file=out)
    print(file=out)

    for line in _format_block(
        "contact",
        (
            "<start>",
            "<end>",
            "<src>",
            "<dst>",
            "[bw]",
            "[loss]",
            "[delay]",
            "[jitter]",
            "[=]",
        ),
        contact,
        (True, True, False, False, True, True, True, True, True),
    ):
        print(line, file=out)


def main() -> None:
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
        "--speedup",
        type=float,
        default=1.0,
        help="Divide contact timestamps by this factor (e.g. --speedup 100 for 100x faster)",
    )
    parser.add_argument(
        "--bw-scale",
        "--bandwidth-scale",
        dest="bw_scale",
        type=float,
        default=1.0,
        help="Multiply bandwidth values by this factor (e.g. --bw-scale 0.1 for 10%)",
    )

    args = parser.parse_args()

    date_str = datetime.date.today().isoformat()
    cmd_str = f"{os.path.basename(sys.argv[0])} " + " ".join(sys.argv[1:])

    rows = parse_csv_rows(args.csvfile, prefix=args.strip_prefix)
    rows = apply_speedup_and_scale(rows, args.speedup, args.bw_scale)
    multi_pairs = compute_multi_pairs(rows)
    merged = merge_symmetric_rows(rows)

    with (
        open(args.output, "w") if args.output != "-" else nullcontext(sys.stdout)
    ) as out:
        print(f"# Generated: {date_str}", file=out)
        print(f"# Command: {cmd_str}", file=out)
        print(file=out)
        print(HEADER.rstrip(), file=out)
        print(file=out)
        print("s loop 1", file=out)
        print(file=out)
        format_and_output(merged, multi_pairs, out)


if __name__ == "__main__":
    main()
