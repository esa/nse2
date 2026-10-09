#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import select
import subprocess
import time
from typing import NotRequired, TypedDict, cast

from nicegui import ui

from tools.webui.console import ConsoleFooter


class Node(TypedDict):
    name: str
    type: str
    x: float
    y: float
    color: str


class VisConfig(TypedDict):
    title: str
    description: str
    nodes: list[Node]
    background: NotRequired[str]
    links: NotRequired[str]


def load_config(path: str) -> VisConfig:
    with open(path) as config_file:
        return cast(VisConfig, json.load(config_file))


def main() -> None:
    print("Starting Network Visualization")
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", help="bind address for web interface to listen on", default="127.0.0.1")
    parser.add_argument("-p", "--port", help="port for web interface to listen on", default=8000)
    parser.add_argument("config", help="network visualization config file to load")
    args = parser.parse_args()

    vizjson_filename = args.config
    config = load_config(vizjson_filename)
    background = config.get("background", "background.jpg")
    netmap_filename = config.get("links")
    if netmap_filename is None:
        print("WARNING: No links file provided in config")

    def add_marker(x: float, y: float, label: str, color: str) -> str:
        marker = f'<circle cx="{x}" cy="{y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
        marker += f'<text x="{x}" y="{y + 40}" fill="{color}" font-size="20" text-anchor="middle">{label}</text>'
        return marker

    def add_link(
        node1: Node, node2: Node, color: str = "green", dashed: bool = False
    ) -> str:
        if dashed:
            now = int(time.time() * 10) % 5
            return f'<line x1="{node1["x"]}" y1="{node1["y"]}" x2="{node2["x"]}" y2="{node2["y"]}" stroke="{color}" stroke-width="4" stroke-dasharray="5,5" stroke-dashoffset="{now * 2}" />'
        else:
            return f'<line x1="{node1["x"]}" y1="{node1["y"]}" x2="{node2["x"]}" y2="{node2["y"]}" stroke="{color}" stroke-width="4"/>'

    def build_page() -> None:
        links: list[tuple[str, str, str]] = []
        containers: list[str] = [node["name"] for node in config["nodes"]]
        node_icons = {node["name"]: node["type"] for node in config["nodes"]}
        console = ConsoleFooter(containers, node_icons=node_icons)

        def load_netmap() -> None:
            links.clear()
            if not netmap_filename:
                return
            try:
                with open(netmap_filename) as netmap_file:
                    for line in netmap_file:
                        node1, link_type, node2 = line.split()
                        links.append((node1, node2, link_type))
            except FileNotFoundError:
                return

        def draw_netmap() -> None:
            content = ""

            for node in config["nodes"]:
                content += add_marker(node["x"], node["y"], node["name"], node["color"])

            for node1_name, node2_name, link_type in links:
                node1 = next(
                    (node for node in config["nodes"] if node["name"] == node1_name),
                    None,
                )
                node2 = next(
                    (node for node in config["nodes"] if node["name"] == node2_name),
                    None,
                )

                if node1 is not None and node2 is not None:
                    content += add_link(node1, node2, dashed=(link_type == "."))

            ii.content = content

        with ui.card().classes("no-shadow self-center w-full max-w-[1200px]"):
            ui.markdown(
                f"""
            ## {config["title"]}

            *{config["description"]}*

                        """
            )
            ii = ui.interactive_image(background, content="").classes("w-full")
            log = ui.log().classes("w-full")

        console.build()

        log_file = "tmp/main.log"
        f: subprocess.Popen[bytes] = subprocess.Popen(
            ["stdbuf", "-oL", "tail", "-F", log_file, "-n", "+0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        p = select.poll()
        p.register(f.stdout)

        log.push("Network Visualization started")
        log.push(f"Waiting for log messages in {log_file}...")

        def check_logfile() -> None:
            if p.poll(0.1):
                line = f.stdout.readline().decode("utf-8").strip()
                log.push(line)

        def stop_log_follower() -> None:
            if f.poll() is None:
                f.terminate()

        ui.context.client.on_delete(stop_log_follower)
        ui.timer(interval=0.1, callback=check_logfile, once=False)
        # spawn background worker to follow tmp/main.log and append new lines to log widget

        ui.timer(interval=1, callback=load_netmap, once=False)
        ui.timer(interval=0.1, callback=draw_netmap, once=False)
        dark = ui.dark_mode()
        dark.enable()

    try:
        ui.run(
            root=build_page,
            title="Network Visualization",
            reload=False,
            host=args.bind,
            port=args.port,
            show=False,
        )
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
