#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import re
import socket
from argparse import Namespace
from typing import TypedDict, cast

import networkx as nx
from nicegui import run, ui
from nicegui.elements.button import Button
from nicegui.elements.dialog import Dialog
from nicegui.elements.label import Label
from nicegui.elements.scroll_area import ScrollArea
from nicegui.elements.switch import Switch

from tools.contact_player.tc_netem import set_on_interface
from tools.mgr.helpers import (
    get_container_interfaces,
    get_container_names,
    is_scenario_running,
    load_graph_from_file,
)
from tools.webui.console import ConsoleFooter

TC_RATE_RE: re.Pattern[str] = re.compile(r"rate ([0-9]+[KMG]bit)")
TC_LOSS_RE: re.Pattern[str] = re.compile(r"loss ([0-9]+)%")
TC_DELAY_RE: re.Pattern[str] = re.compile(r"delay ([0-9.e+]+)(ms|s)")
TC_JITTER_RE: re.Pattern[str] = re.compile(r"jitter ([0-9.e+]+)(ms|s)")
TC_BANDWIDTH_RE: re.Pattern[str] = re.compile(r"[0-9]+[KMGT]bit", re.IGNORECASE)


def validate_bandwidth(value: str) -> str | None:
    bandwidth = value.strip()
    if not bandwidth:
        return None
    if bandwidth.lower() == "inf":
        return None
    return None if TC_BANDWIDTH_RE.fullmatch(bandwidth) else "Use e.g. 10kbit, 1mbit or inf"


def validate_percentage(value: str) -> str | None:
    try:
        percentage = float(value)
    except ValueError:
        return "Not a number"
    if not 0.0 <= percentage <= 100.0:
        return "Must be between 0 and 100"
    return None


def validate_non_negative(value: str) -> str | None:
    try:
        delay = float(value)
    except ValueError:
        return "Not a number"
    if delay < 0 or delay == float("inf"):
        return "Must be a non-negative number"
    return None


class Link(TypedDict):
    container: str
    interface: str
    bandwidth: str
    loss: float
    delay: float
    delay_unit: str
    jitter: float
    jitter_unit: str


class ManagerArguments(Namespace):
    compose_file: str = ""
    contact_plan: str = ""
    bind: str = "127.0.0.1"
    port: int = 8800


def delay_to_milliseconds(value: float, unit: str) -> int:
    return int(value * 1000) if unit == "s" else int(value)


class ManagerController:
    """Own shared Manager state and provide callbacks for its UI."""

    def __init__(self, compose_file: str, contact_plan: str) -> None:
        self.compose_file: str = compose_file
        self.contact_plan: str = contact_plan
        self.network_graph: nx.Graph[
            str, dict[str, object], dict[str, object]
        ] = load_graph_from_file(compose_file)
        self.time_socket: socket.socket = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        )
        self.time_socket.settimeout(1)
        self.modal_dialog: bool = False
        self.link_memory: dict[str, dict[str, Link]] = {}
        self.draw_links_lock: asyncio.Lock = asyncio.Lock()

    def close(self) -> None:
        self.time_socket.close()

    async def health_check_timer(self, status_label: Label) -> None:
        if await run.io_bound(is_scenario_running, self.compose_file):
            status_label.text = "UP"
            status_label.classes(replace="text-green-500")
        else:
            status_label.text = "DOWN"
            status_label.classes(replace="text-red-500")

    async def timesync_timer(
        self, lbl_time: Label, lbl_next_event: Label
    ) -> None:
        try:
            self.time_socket.sendto(b"time", ("localhost", 9966))
            data = self.time_socket.recvfrom(1024)[0]
            cur_time, next_event = data.decode().split()
            lbl_time.text = cur_time + "s"
            lbl_time.classes(replace="text-green-500")
            lbl_next_event.text = next_event
            lbl_next_event.classes(replace="text-green-500")
        except (OSError, ValueError) as error:
            print(f"Unable to read simulation time: {error}")
            lbl_time.text = "N/A"
            lbl_time.classes(replace="text-red-500")
            lbl_next_event.text = "N/A"
            lbl_next_event.classes(replace="text-red-500")

    async def linkstate_timer(
        self, links_area: ScrollArea, map_area: ScrollArea
    ) -> None:
        if (
            await run.io_bound(is_scenario_running, self.compose_file)
            and not self.modal_dialog
        ):
            await self.draw_links(links_area)
            self.draw_map(map_area)

    async def jump_to_next_event(
        self,
        lbl_time: Label,
        lbl_next_event: Label,
        links_area: ScrollArea,
        map_area: ScrollArea,
    ) -> None:
        try:
            self.time_socket.sendto(b"next", ("localhost", 9966))
        except OSError as error:
            print(f"Unable to advance simulation: {error}")
        await self.timesync_timer(lbl_time, lbl_next_event)
        await self.linkstate_timer(links_area, map_area)

    def pause_resume_scenario(self, button: Button) -> None:
        if button.text == "Pause":
            try:
                self.time_socket.sendto(b"pause", ("localhost", 9966))
                button.text = "Resume"
            except OSError as error:
                print(f"Unable to pause simulation: {error}")
        else:
            try:
                self.time_socket.sendto(b"resume", ("localhost", 9966))
                button.text = "Pause"
            except OSError as error:
                print(f"Unable to resume simulation: {error}")

    async def do_link_toggle(
        self, switch: Switch, link: Link, links_area: ScrollArea
    ) -> None:
        container = link["container"]
        interface = link["interface"]
        saved_links = self.link_memory.setdefault(container, {})
        bandwidth = "" if link["bandwidth"] == "inf" else link["bandwidth"]

        if switch.value:
            saved_link = saved_links.get(interface)
            loss = saved_link["loss"] if saved_link is not None else 0.0
        else:
            saved_links[interface] = link
            loss = 100.0

        try:
            await run.io_bound(
                set_on_interface,
                container,
                interface,
                loss=loss,
                bandwidth=bandwidth,
                delay=delay_to_milliseconds(link["delay"], link["delay_unit"]),
                jitter=delay_to_milliseconds(link["jitter"], link["jitter_unit"]),
            )
        except (OSError, RuntimeError) as error:
            ui.notify(f"Failed to apply link settings: {error}", type="negative")
        await self.draw_links(links_area)

    def create_link_dialog(self, link: Link) -> Dialog:
        with ui.dialog() as dialog, ui.card():
            with ui.grid(columns=2):
                ui.label("Container: ")
                container_label = ui.label(link["container"])
                ui.label("Interface: ")
                interface_label = ui.label(link["interface"])
                ui.label("Bandwidth: ")
                bandwidth_input = ui.input(
                    value=link["bandwidth"], validation=validate_bandwidth
                )
                ui.label("Loss (%): ")
                loss_input = ui.input(
                    value=str(link["loss"]), validation=validate_percentage
                )
                ui.label(f"Delay ({link['delay_unit']}): ")
                delay_input = ui.input(
                    value=str(link["delay"]), validation=validate_non_negative
                )
                ui.label(f"Jitter ({link['jitter_unit']}): ")
                jitter_input = ui.input(
                    value=str(link["jitter"]), validation=validate_non_negative
                )

                def submit_link() -> None:
                    valid = all(
                        [
                            bandwidth_input.validate(),
                            loss_input.validate(),
                            delay_input.validate(),
                            jitter_input.validate(),
                        ]
                    )
                    if not valid:
                        ui.notify(
                            "Invalid link parameters", type="negative"
                        )
                        return
                    try:
                        dialog.submit(
                            Link(
                                container=container_label.text,
                                interface=interface_label.text,
                                bandwidth=bandwidth_input.value or "inf",
                                loss=float(loss_input.value or "0"),
                                delay=float(delay_input.value or "0"),
                                delay_unit=link["delay_unit"],
                                jitter=float(jitter_input.value or "0"),
                                jitter_unit=link["jitter_unit"],
                            )
                        )
                    except ValueError:
                        ui.notify("Invalid link parameters", type="negative")

                ui.button("Apply", on_click=submit_link)
                ui.button("Cancel", on_click=lambda: dialog.close())
        return dialog

    async def show_link_dialog(self, link: Link, links_area: ScrollArea) -> None:
        dialog = self.create_link_dialog(link)
        self.modal_dialog = True
        try:
            result = cast(Link | None, await dialog)
        finally:
            if not dialog.is_deleted:
                dialog.clear()
            self.modal_dialog = False

        if result is not None:
            try:
                await run.io_bound(
                    set_on_interface,
                    result["container"],
                    result["interface"],
                    loss=result["loss"],
                    bandwidth=(
                        "" if result["bandwidth"] == "inf" else result["bandwidth"]
                    ),
                    delay=delay_to_milliseconds(result["delay"], result["delay_unit"]),
                    jitter=delay_to_milliseconds(
                        result["jitter"], result["jitter_unit"]
                    ),
                )
            except (OSError, RuntimeError) as error:
                ui.notify(f"Failed to apply link settings: {error}", type="negative")
            await self.draw_links(links_area)

    async def draw_links(self, links_area: ScrollArea) -> None:
        if self.draw_links_lock.locked():
            return
        async with self.draw_links_lock:
            interfaces = await run.io_bound(
                get_container_interfaces, self.compose_file
            ) or {}
            with links_area:
                links_area.clear()
                for container, container_interfaces in interfaces.items():
                    for interface, qdisc in container_interfaces.items():
                        rate_match = TC_RATE_RE.search(qdisc)
                        loss_match = TC_LOSS_RE.search(qdisc)
                        delay_match = TC_DELAY_RE.search(qdisc)
                        jitter_match = TC_JITTER_RE.search(qdisc)

                        bandwidth = rate_match.group(1) if rate_match else "inf"
                        loss = float(loss_match.group(1)) if loss_match else 0.0
                        delay = float(delay_match.group(1)) if delay_match else 0.0
                        delay_unit = delay_match.group(2) if delay_match else "ms"
                        jitter = float(jitter_match.group(1)) if jitter_match else 0.0
                        jitter_unit = jitter_match.group(2) if jitter_match else "ms"
                        is_active = loss < 100

                        endpoints = interface.split("_")
                        if (
                            len(endpoints) >= 2
                            and container in endpoints[:2]
                            and all(
                                endpoint in self.network_graph
                                for endpoint in endpoints[:2]
                            )
                        ):
                            edge = endpoints[0], endpoints[1]
                            if is_active:
                                self.network_graph.add_edge(*edge)
                            elif self.network_graph.has_edge(*edge):
                                self.network_graph.remove_edge(*edge)

                        link: Link = {
                            "container": container,
                            "interface": interface,
                            "bandwidth": bandwidth,
                            "loss": loss,
                            "delay": delay,
                            "delay_unit": delay_unit,
                            "jitter": jitter,
                            "jitter_unit": jitter_unit,
                        }
                        background = "#f3f4f6" if is_active else "#fde8e8"
                        with ui.row().classes("place-items-center w-full").style(
                            f"background-color: {background}"
                        ):
                            icon = "cloud_done" if is_active else "cloud_off"
                            color = "text-green-500" if is_active else "text-red-500"
                            ui.icon(icon).classes(color).style("width: 40px")
                            ui.markdown(f"**{container}**").classes("text-lg").style(
                                "width: 250px"
                            )
                            ui.label(interface).classes("text-lg").style(
                                "width: 250px"
                            )
                            ui.markdown(
                                f"**bw:** {bandwidth} **loss:** {loss:g}% "
                                f"**delay:** {delay:g}{delay_unit} "
                                f"**jitter:** {jitter:g}{jitter_unit}"
                            ).classes("text-lg")
                            ui.space()
                            ui.button(
                                "Edit",
                                on_click=lambda _, link=link: self.show_link_dialog(
                                    link, links_area
                                ),
                            )
                            active_toggle = ui.switch("Active", value=is_active)
                            active_toggle.on_value_change(
                                lambda _, link=link, switch=active_toggle: self.do_link_toggle(
                                    switch, link, links_area
                                )
                            )

    def draw_map(self, map_area: ScrollArea) -> None:
        with map_area:
            map_area.clear()
            with ui.matplotlib(figsize=(8, 5)).figure as figure:
                axes = figure.gca()
                nx.draw(
                    self.network_graph,
                    with_labels=True,
                    font_weight="bold",
                    ax=axes,
                    pos=nx.circular_layout(self.network_graph),
                )

    def build_ui(self) -> None:
        containers = get_container_names(self.compose_file)
        console = ConsoleFooter(containers)
        links_area: ScrollArea
        map_area: ScrollArea

        with ui.element("div").classes("w-full h-screen"):
            with ui.row().classes("items-center"):
                ui.label("Scenario: ")
                ui.label(self.compose_file).classes("text-blue-500")
                ui.label("Contact Plan: ")
                ui.label(self.contact_plan).classes("text-blue-500")
                ui.label("Status: ")
                status_label: Label = ui.label("DOWN").classes("text-red-500")
                ui.label("Simulation Time: ")
                lbl_time: Label = ui.label("N/A").classes("text-red-500")
                ui.label("Next Event: ")
                lbl_next_event: Label = ui.label("N/A").classes("text-red-500")
                ui.space()
                btn_next: Button = ui.button("Jump to next event")
                btn_pause: Button = ui.button("Pause")
                btn_pause.on_click(lambda: self.pause_resume_scenario(btn_pause))

            with ui.tabs().classes("w-full") as tabs:
                tab_links = ui.tab("Links")
                tab_map = ui.tab("Map")
            with ui.tab_panels(tabs, value=tab_links).classes("w-full h-full"):
                with ui.tab_panel(tab_links):
                    ui.button(
                        "Refresh",
                        on_click=lambda: self.draw_links(links_area),
                    )
                    links_area = ui.scroll_area().classes("h-2/3 border")
                with ui.tab_panel(tab_map):
                    map_area = ui.scroll_area().classes("h-2/3 border")
                    self.draw_map(map_area)
            btn_next.on_click(
                lambda: self.jump_to_next_event(
                    lbl_time, lbl_next_event, links_area, map_area
                )
            )

        console.build()

        ui.timer(10.0, lambda: self.health_check_timer(status_label))
        ui.timer(2.0, lambda: self.timesync_timer(lbl_time, lbl_next_event))
        ui.timer(5.0, lambda: self.linkstate_timer(links_area, map_area))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage an NSE2 Docker scenario")
    parser.add_argument("compose_file", help="Docker Compose file for the scenario")
    parser.add_argument("contact_plan", help="scenario contact plan")
    parser.add_argument(
        "-b",
        "--bind",
        help="bind address for web interface to listen on",
        default="127.0.0.1",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="port for web interface to listen on",
        default=8800,
    )
    args = parser.parse_args(namespace=ManagerArguments())
    if not is_scenario_running(args.compose_file):
        parser.error("Scenario is not running")

    manager = ManagerController(args.compose_file, args.contact_plan)
    try:
        ui.run(
            root=manager.build_ui,
            reload=False,
            title="Docker TestBed Manager",
            show=False,
            port=args.port,
            host=args.bind,
        )
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        manager.close()


if __name__ in {"__main__", "__mp_main__"}:
    main()
