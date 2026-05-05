#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from nicegui import ui, events, core
from nicegui.elements.xterm import Xterm
from functools import partial
import shutil
import signal
from typing import TypedDict, cast
import pty
import fcntl
import struct
import termios
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

DOCKER_PATH = cast(str, shutil.which("docker"))
assert DOCKER_PATH is not None, "docker executable not found in PATH"

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


def attach_container_to_xterm(terminal: Xterm, node: Node) -> None:
    """Attaches a xterm terminal in the UI to /bin/bash in a docker container.

    Args:
        terminal: xterm.js terminal to attach input/output to.
        node: the specific node to attach to.
    """
    pty_pid, pty_fd = pty.fork()
    if pty_pid == pty.CHILD:
        os.execv(
            DOCKER_PATH,
            ["docker", "exec", "-it", node["name"], "/bin/bash"],
        )

    if core.loop is not None:

        @partial(core.loop.add_reader, pty_fd)
        def pty_to_terminal():  # pyright: ignore[reportUnusedFunction]
            try:
                data = os.read(pty_fd, 1024)
            except OSError:
                print("Stopping reading from pty")
                if core.loop is not None:
                    core.loop.remove_reader(pty_fd)
            else:
                terminal.write(data)

    @terminal.on_data
    def terminal_to_pty(event: events.XtermDataEventArguments) -> None:  # pyright: ignore[reportUnusedFunction]
        try:
            os.write(pty_fd, event.data.encode("utf-8"))
        except OSError:
            pass

    @terminal.on_resize
    def resize_terminal(event: events.XtermResizeEventArguments) -> None:  # pyright: ignore[reportUnusedFunction]
        try:
            fcntl.ioctl(
                pty_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", event.rows, event.cols, 0, 0),
            )
        except OSError:
            pass

    @ui.context.client.on_delete  # pyright: ignore[reportUnknownMemberType]
    def kill_bash() -> None:  # pyright: ignore[reportUnusedFunction]
        try:
            os.close(pty_fd)
        except OSError:
            pass
        os.kill(pty_pid, signal.SIGKILL)
        print("Terminal closed")


def build_terminal_footer(nodes: list[Node]) -> None:
    """Creates the UI elements for the terminal panel in the footer.

    Args:
        nodes: list of nodes to create terminals for.
    """
    terminal_panel_expanded = False
    with ui.footer().classes("w-full p-0 flex-col gap-0"):
        # bar with the individual tabs for every node
        with ui.row().classes("w-full items-center bg-blue-500 px-2 relative"):
            with ui.tabs().classes("flex-1") as tabs:
                for node in nodes:
                    ui.tab(node["name"], icon=node["type"])
            # chevron toggle button on the right
            chevron = ui.button(icon="expand_less").props("flat dense color=white")

            # invisible div element added on top of the tab bar that acts as a handle to resize the footer
            # js changes the height of the terminal-panel
            ui.element("div").classes(
                "absolute top-0 left-0 w-full cursor-row-resize"
            ).style("height: 6px; z-index: 10;").on(
                "mousedown",
                js_handler="""
                    (e) => {
                        e.preventDefault();
                        const footer = e.target.closest('footer');
                        const panel = footer.querySelector('.terminal-panel');
                        const startY = e.clientY;
                        const startH = panel.offsetHeight;
                        const onMove = (e) => {
                            const newH = startH - (e.clientY - startY);
                            panel.style.height = Math.max(100, newH) + 'px';
                        };
                        const onUp = () => {
                            window.removeEventListener('mousemove', onMove);
                            window.removeEventListener('mouseup', onUp);
                        };
                        window.addEventListener('mousemove', onMove);
                        window.addEventListener('mouseup', onUp);
                    }
                """,
            )
        # content of each tab
        with (
            ui.column()
            .classes("w-full terminal-panel")
            .style("height: 300px; min-height: 100px;") as panel
        ):
            with ui.tab_panels(tabs, value=nodes[0]["name"]).classes(
                "w-full h-full p-0"
            ):
                for node in nodes:
                    with ui.tab_panel(node["name"]).classes("w-full p-0"):
                        terminal = ui.xterm().classes("w-full h-full")
                        ui.element("q-resize-observer").on("resize", terminal.fit)
                        attach_container_to_xterm(terminal, node)
            panel.set_visibility(terminal_panel_expanded)

        # toggle logic
        def toggle_panel():
            nonlocal terminal_panel_expanded
            terminal_panel_expanded = not terminal_panel_expanded
            panel.set_visibility(terminal_panel_expanded)
            chevron.props(
                "icon=expand_more"
                if not terminal_panel_expanded
                else "icon=expand_less"
            )

        def open_panel():
            nonlocal terminal_panel_expanded
            terminal_panel_expanded = True
            panel.set_visibility(True)
            chevron.props("icon=expand_less")

        chevron.on_click(toggle_panel)
        # clicking a tab also opens the panel if collapsed
        tabs.on("update:model-value", lambda _: open_panel())


with ui.card().classes("no-shadow self-center w-[1200px]") as card:
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
    log = ui.log().classes("w-full")

build_terminal_footer(config["nodes"])


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
