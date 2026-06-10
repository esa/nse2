#!/usr/bin/env python3

import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from contextlib import nullcontext
from typing import TextIO

Contact = tuple[str, str, float, float, int, float, str, bool]
"""Raw parsed CSV row: (src, dst, ts_start, ts_end, bw_bps, delay_sec, label, symmetric)."""

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


def bps_to_human(bps: int) -> str:
    """Convert bps integer to human-readable bandwidth string."""
    if bps >= 1_000_000_000 and bps % 1_000_000_000 == 0:
        return f"{bps // 1_000_000_000}gbit"
    if bps >= 1_000_000 and bps % 1_000_000 == 0:
        return f"{bps // 1_000_000}mbit"
    if bps >= 1_000 and bps % 1_000 == 0:
        return f"{bps // 1_000}kbit"
    return f"{bps}bit"


def strip_prefix(name: str, prefix: str) -> str:
    """Remove a prefix from a node name if present."""
    if prefix and name.startswith(prefix):
        return name[len(prefix) :]
    return name


def merge_symmetric_rows(rows: list[Contact]) -> list[Contact]:
    """Collapse symmetric reversed-pair rows into single ``=`` lines.

    Two rows are merged only when they refer to the same connection
    in opposite directions (``A->B`` and ``B->A``) with matching timestamps,
    bandwidth, and delay.
    """
    groups: defaultdict[tuple[str, str, str], list[Contact]] = defaultdict(list)
    for row in rows:
        a, b = tuple(sorted([row[0], row[1]]))
        groups[(a, b, row[6])].append(row)

    result: list[Contact] = []
    for group_rows in groups.values():
        if len(group_rows) == 2:
            r1, r2 = group_rows
            if (
                r1[0] == r2[1]
                and r1[1] == r2[0]
                and r1[2] == r2[2]
                and r1[3] == r2[3]
                and r1[4] == r2[4]
                and r1[5] == r2[5]
            ):
                result.append((r1[0], r1[1], r1[2], r1[3], r1[4], r1[5], r1[6], True))
                continue
        result.extend(group_rows)
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


def convert_rows(rows: list[Contact]) -> tuple[list[FixedRow], list[ContactRow]]:
    """Convert raw parsed rows into printable fixed and contact row tuples.

    All values are transformed to their final string form here, so the
    formatting step operates on ready-to-print data only.
    """
    fixed: list[FixedRow] = []
    contact: list[ContactRow] = []

    for src, dst_orig, ts_start, ts_end, bw_bps, delay_sec, label, symmetric in rows:
        bw = bps_to_human(bw_bps)
        delay = str(int(round(delay_sec * 1000)))
        eq = "=" if symmetric else ""

        if label and "_" in label:
            a, b = tuple(sorted([src, dst_orig]))
            ifname = f"{a}_{b}_{label.split('_')[0]}"
            if len(ifname) >= 14:
                ifname = hashlib.md5(ifname.encode()).hexdigest()[:12]
            dst = f"dev:{ifname}"
        else:
            dst = dst_orig

        if ts_start == 0 and ts_end == -1:
            fixed.append((src, dst, bw, "0.0", delay, "0.0", eq))
        else:
            contact.append(
                (
                    f"+{int(round(ts_start))}",
                    f"+{int(round(ts_end))}",
                    src,
                    dst,
                    bw,
                    "0.0",
                    delay,
                    "0.0",
                    eq,
                )
            )

    return fixed, contact


def format_and_output(rows: list[Contact], out: TextIO) -> None:
    """Convert rows and write column-aligned CCP output."""
    fixed, contact = convert_rows(rows)
    contact.sort(key=lambda r: int(r[0]))

    for line in _format_block(
        "fixed",
        ("<src>", "<dst>", "[bw]", "[loss]", "[delay]", "[jitter]", "[=]"),
        fixed,
        (False, False, True, True, True, True, True),
    ):
        print(line, file=out)

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

    args = parser.parse_args()

    rows: list[Contact] = []
    with open(args.csvfile) as f:
        f.readline()
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 6 or len(row) == 7:
                src = strip_prefix(row[0], args.strip_prefix)
                dst = strip_prefix(row[1], args.strip_prefix)
                ts_start = float(row[2])
                ts_end = float(row[3])
                bw_bps = int(row[4])
                delay_sec = float(row[5])
                label = row[6] if len(row) == 7 else ""
                rows.append(
                    (src, dst, ts_start, ts_end, bw_bps, delay_sec, label, False)
                )
            else:
                print(
                    f"WARNING: skipping row with {len(row)} columns: {row!r}",
                    file=sys.stderr,
                )

    rows = merge_symmetric_rows(rows)

    with (
        open(args.output, "w") if args.output != "-" else nullcontext(sys.stdout)
    ) as out:
        print(HEADER.rstrip(), file=out)
        print(file=out)
        print("s loop 1", file=out)
        print(file=out)
        format_and_output(rows, out)


if __name__ == "__main__":
    main()
