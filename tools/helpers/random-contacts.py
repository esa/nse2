#!/usr/bin/env python3

"""Randomize contact windows in an existing CCP file.

Fixed links are preserved verbatim.  For each unique dynamic contact
direction in the original file, random start/end times are generated
while keeping the per-direction link properties unchanged.
"""

import argparse
import datetime
import random
import sys

from tools.contact_player.ccp import LinkProperties, RawCcpContactPlan


def _fmt(v: float) -> str:
    """Format a float: 100.0 -> '100', 0.5 -> '0.5'."""
    return str(int(v)) if v == int(v) else str(v)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Randomize contact timings in an existing CCP file."
    )
    parser.add_argument("contacts", help="Input .ccp file")
    parser.add_argument("output", help="Output .ccp file")
    parser.add_argument(
        "--length", "-l", type=int, default=60,
        help="Contact plan duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--min-contact", type=int, default=5,
        help="Minimum contact length in seconds (default: 5)",
    )
    parser.add_argument(
        "--max-contact", type=int, default=15,
        help="Maximum contact length in seconds (default: 15)",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed (default: none)",
    )
    args = parser.parse_args()

    if args.min_contact > args.max_contact:
        parser.error("--min-contact must be <= --max-contact")

    if args.seed is not None:
        random.seed(args.seed)

    plan = RawCcpContactPlan.from_file(args.contacts)

    # Unique directed links: (src, dst, props, symmetric)
    dirs: list[tuple[str, str, LinkProperties, bool]] = []
    seen: set[tuple[str, str, LinkProperties, bool]] = set()
    for c in plan.contacts:
        key = (c.src, c.dst, c.props, c.symmetric)
        if key not in seen:
            seen.add(key)
            dirs.append(key)

    # Generate random contacts per direction
    lines: list[str] = []
    for src, dst, props, symmetric in dirs:
        start = random.randrange(0, args.length - args.max_contact)
        end = start + random.randint(args.min_contact, args.max_contact)
        eq = " =" if symmetric else ""
        lines.append(
            f"a contact +{start} +{end} {src} {dst} "
            f"{props.bandwidth} {_fmt(props.loss)} {_fmt(props.delay)} "
            f"{_fmt(props.jitter)}{eq}"
        )

    lines.sort(key=lambda l: int(l.split()[2]))

    # Write output
    cmd = " ".join([sys.argv[0].split("/")[-1]] + sys.argv[1:])
    with open(args.output, "w") as f:
        print(f"# Generated: {datetime.date.today().isoformat()}", file=f)
        print(f"# Command: {cmd}", file=f)
        print(f"s loop {int(plan.loop)}", file=f)
        print(file=f)
        for c in plan.fixed_contacts:
            eq = " =" if c.symmetric else ""
            print(
                f"a fixed  {c.src} {c.dst} "
                f"{c.props.bandwidth} {_fmt(c.props.loss)} "
                f"{_fmt(c.props.delay)} {_fmt(c.props.jitter)}{eq}",
                file=f,
            )
        print(file=f)
        for line in lines:
            print(line, file=f)


if __name__ == "__main__":
    main()
