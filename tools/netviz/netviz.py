#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from nicegui import ui, events
from typing import TypedDict, cast
import argparse
import json
import os
import time
import subprocess
import select


class Node(TypedDict):
    name: str
    type: str
    x: int
    y: int
    color: str


class VisConfig(TypedDict):
    title: str
    description: str
    background: str
    links: str
    nodes: list[Node]


def load_config(path: str) -> VisConfig:
    with open(path) as config_file:
        return json.load(config_file)


print("Starting Network Visualization")
parser = argparse.ArgumentParser()
parser.add_argument("config", help="network visualization config file to load")
args = parser.parse_args()

vizjson_filename = args.config
config = load_config(vizjson_filename)
if "background" in config:
    background = config["background"]
else:
    background = "background.jpg"
# print(config)

if "links" not in config:
    print("WARNING: No links file provided in config")
    netmap_filename = None
else:
    netmap_filename = config["links"]

# load background file as base64 string
# with open(background, "rb") as f:
#     background = f.read()
# convert bytes to base64
# background = "data:image/jpeg;base64," + base64.b64encode(background).decode("utf-8")


def add_marker(x: int, y: int, label: str, color: str):
    marker = f'<circle cx="{x}" cy="{y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
    marker += f'<text x="{x}" y="{y+40}" fill="{color}" font-size="20" text-anchor="middle">{label}</text>'
    return marker


def add_link(
    node1: Node, node2: Node, color: str = "green", dashed: bool = False
) -> str:
    if dashed:
        now = int(time.time() * 10) % 5
        return f'<line x1="{node1["x"]}" y1="{node1["y"]}" x2="{node2["x"]}" y2="{node2["y"]}" stroke="{color}" stroke-width="4" stroke-dasharray="5,5" stroke-dashoffset="{now*2}" />'
    else:
        return f'<line x1="{node1["x"]}" y1="{node1["y"]}" x2="{node2["x"]}" y2="{node2["y"]}" stroke="{color}" stroke-width="4"/>'


def mouse_handler(e: events.MouseEventArguments):
    color = "SkyBlue" if e.type == "mousedown" else "SteelBlue"
    ii.content += f'<circle cx="{e.image_x}" cy="{e.image_y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
    ui.notify(f"{e.type} at ({e.image_x:.1f}, {e.image_y:.1f})")
    print(f"{e.type} at ({e.image_x:.1f}, {e.image_y:.1f})")


def load_netmap():
    global links
    links = []
    if not netmap_filename:
        return
    with open(netmap_filename) as f:
        for line in f:
            node1, link_type, node2 = line.split()
            links.append((node1, node2, link_type))


def draw_netmap():
    content = ""

    for node in config["nodes"]:
        content += add_marker(node["x"], node["y"], node["name"], node["color"])
    # content += add_marker(500, 500, "node1", "SkyBlue")

    global links

    for node1, node2, link_type in links:
        node1 = next((node for node in config["nodes"] if node["name"] == node1), None)
        node2 = next((node for node in config["nodes"] if node["name"] == node2), None)
        content += add_link(node1, node2, dashed=(link_type == "."))

    ii.content = content


def btn_click(node_name: str):
    ui.notify("Opening terminal on " + node_name)
    cmd = f"docker exec -it {node_name} /bin/bash"
    xcmd = f"xterm -bg black -fg white -geometry 100x30 -title {node_name} -e {cmd} &"

    os.system(xcmd)
    # print("clicked: " + node_name)


with ui.card().classes("no-shadow self-center w-[1200px]") as card:
    with ui.column():
        ui.markdown(
            f"""
        ## {config["title"]}

        *{config["description"]}*

                    """
        )
        with ui.row():
            ii = ui.interactive_image(
                background,
                content="",
                on_mouse=mouse_handler,
                events=["mousedown", "mouseup"],
                cross=True,
            )

            with ui.column():
                for node in config["nodes"]:
                    print(node["name"])
                    ui.button(
                        node["name"],
                        icon=node["type"],
                        on_click=lambda n=node["name"]: btn_click(n),
                    )
        log = ui.log().classes("w-full")

log_file = "tmp/main.log"
f = subprocess.Popen(
    ["stdbuf", "-oL", "tail", "-F", log_file, "-n", "+0"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
p = select.poll()
p.register(f.stdout)

log.push("Network Visualization started")
log.push(f"Waiting for log messages in {log_file}...")


def check_logfile():
    if p.poll(0.1):
        line = f.stdout.readline().decode("utf-8").strip()
        log.push(line)


ui.timer(interval=0.1, callback=check_logfile, once=False)
# spawn background worker to follow tmp/main.log and append new lines to log widget

ui.timer(interval=1, callback=load_netmap, once=False)
ui.timer(interval=0.1, callback=draw_netmap, once=False)
dark = ui.dark_mode()
dark.enable()

ui.run(title="Network Visualization", reload=True, host="127.0.0.1", show=False)
