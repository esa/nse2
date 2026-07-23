#!/usr/bin/env python3

import sys
from nicegui import ui, run
import subprocess
import socket
import os
import re
import networkx as nx
import asyncio

from tools.mgr.helpers import *

# regex to extract rate, delay, loss, jitter from tc output
tc_rate = re.compile(r"rate ([0-9]+[KMG]bit)")
tc_loss = re.compile(r"loss ([0-9]+)%")

tc_delay = re.compile(r"delay ([0-9.e+]+)(ms|s)")
tc_jitter = re.compile(r"jitter ([0-9.e+]+)(ms|s)")


async def health_check_timer(compose_file: str, status_label: ui.label):
    # print("Health check timer")
    if await run.io_bound(is_scenario_running, compose_file):
        status_label.text = "UP"
        status_label.classes(replace="text-green-500")
    else:
        status_label.text = "DOWN"
        status_label.classes(replace="text-red-500")


time_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
time_sock.settimeout(1)


async def timesync_timer(lbl_time: ui.label, lbl_next_event: ui.label):
    try:
        time_sock.sendto("time".encode(), ("localhost", 9966))
        # receive response
        data, addr = time_sock.recvfrom(1024)
        # print(f"Received: {data.decode()}")
        cur_time, next_event = data.decode().split(" ")
        lbl_time.text = cur_time + "s"
        lbl_time.classes(replace="text-green-500")
        lbl_next_event.text = next_event
        lbl_next_event.classes(replace="text-green-500")
    except Exception as e:
        print(e)
        lbl_time.text = "N/A"
        lbl_time.classes(replace="text-red-500")
        lbl_next_event.text = "N/A"
        lbl_next_event.classes(replace="text-red-500")


async def linkstate_timer(
    compose_file: str, links_area: ui.scroll_area, map_area: ui.scroll_area
):
    global modal_dialog
    if await run.io_bound(is_scenario_running, compose_file) and not modal_dialog:
        await draw_links(links_area, compose_file)
        draw_map(map_area)


async def jump_to_next_event(
    compose_file: str,
    lbl_time: ui.label,
    lbl_next_event: ui.label,
    links_area: ui.scroll_area,
    map_area: ui.scroll_area,
):
    try:
        time_sock.sendto("next".encode(), ("localhost", 9966))
    except Exception as e:
        print(e)
    await timesync_timer(lbl_time, lbl_next_event)
    await linkstate_timer(compose_file, links_area, map_area)


def pause_resume_scenario(btn: ui.button):
    print("Pause/Resume: " + btn.text)
    if btn.text == "Pause":
        try:
            time_sock.sendto("pause".encode(), ("localhost", 9966))
            btn.text = "Resume"
        except Exception as e:
            print(e)
    else:
        try:
            time_sock.sendto("resume".encode(), ("localhost", 9966))
            btn.text = "Pause"
        except Exception as e:
            print(e)


def open_xterm(container: str):
    print(f"Opening xterm for container {container}")
    os.system(f'xterm -e "docker exec -it {container} /bin/bash" &')


def open_log(compose_file: str, container: str):
    print(f"Opening logs for container {container}")
    os.system(f'xterm -e "docker compose -f {compose_file} logs -f {container}" &')


link_memory = {}


async def do_link_toggle(
    switch: ui.switch, link: dict, links_area: ui.scroll_area, compose_file: str
):
    print(f"Switch: {switch.value}, Link: {link}")
    if switch.value == True:
        print("Activate link")
        bw = ""
        if link["bw"] != "inf":
            bw = link["bw"]
        loss = 0.0
        if link["container"] in link_memory:
            if link["interface"] in link_memory[link["container"]]:
                link2 = link_memory[link["container"]][link["interface"]]
                if "loss" in link2:
                    loss = float(link2["loss"])
        await run.io_bound(
            set_on_interface,
            link["container"],
            link["interface"],
            loss=loss,
            bandwidth=bw,
            delay=int(link["delay"]),
            jitter=int(link["jitter"]),
        )
        # set_on_interface(
        #     link["container"],
        #     link["interface"],
        #     loss=loss,
        #     bandwidth=link["bw"],
        #     delay=int(link["delay"]),
        #     jitter=int(link["jitter"]),
        # )
    else:
        print("Deactivate link")
        if link["container"] not in link_memory:
            link_memory[link["container"]] = {}
        if link["interface"] not in link_memory[link["container"]]:
            link_memory[link["container"]][link["interface"]] = {}
        link_memory[link["container"]][link["interface"]] = link

        bw = ""
        if link["bw"] != "inf":
            bw = link["bw"]

        # set_on_interface(
        #     link["container"],
        #     link["interface"],
        #     loss=100.0,
        #     bandwidth=bw,
        #     delay=int(link["delay"]),
        #     jitter=int(link["jitter"]),
        # )
        await run.io_bound(
            set_on_interface,
            link["container"],
            link["interface"],
            loss=100.0,
            bandwidth=bw,
            delay=int(link["delay"]),
            jitter=int(link["jitter"]),
        )
    await draw_links(links_area, compose_file)


g = nx.Graph()

modal_dialog = False


def create_link_dialog(link: dict):
    with ui.dialog() as dialog, ui.card():
        with ui.grid(columns=2):
            ui.label("Container: ")
            c = ui.label(link["container"])
            ui.label("Interface: ")
            i = ui.label(link["interface"])
            ui.label("Bandwidth: ")
            bw = ui.input(value=link["bw"])
            ui.label("Loss: ")
            loss = ui.input(value=link["loss"])
            ui.label("Delay: ")
            delay = ui.input(value=link["delay"])
            ui.label("Jitter: ")
            jitter = ui.input(value=link["jitter"])

            ui.button(
                "Apply",
                on_click=lambda: dialog.submit(
                    {
                        "container": c.text,
                        "interface": i.text,
                        "bw": bw.value,
                        "loss": float(loss.value),
                        "delay": int(delay.value),
                        "jitter": int(jitter.value),
                    }
                ),
            )
            ui.button("Cancel", on_click=lambda: dialog.close())
    return dialog


async def show_link_dialog(link: dict, links_area: ui.scroll_area, compose_file: str):
    global modal_dialog
    modal_dialog = True
    print(f"Showing link dialog for {link}")
    dialog = create_link_dialog(link)
    result = await dialog
    dialog.clear()
    modal_dialog = False
    if result:
        print(result)
        set_on_interface(
            result["container"],
            result["interface"],
            loss=result["loss"],
            bandwidth=result["bw"],
            delay=result["delay"],
            jitter=result["jitter"],
        )
        await draw_links(links_area, compose_file)
    else:
        print("Dialog cancelled")


drawing_links_in_progress = False


async def draw_links(links_area: ui.scroll_area, compose_file: str):
    global drawing_links_in_progress
    if drawing_links_in_progress:
        return
    drawing_links_in_progress = True
    global g
    with links_area:
        interfaces = await run.io_bound(get_container_interfaces, compose_file)
        links_area.clear()
        for c, ifs in interfaces.items():
            for i, v in ifs.items():
                # print(f"Container: {c}, Interface: {i}, Value: {v}")
                is_active = True
                bw = "inf"
                loss = "0"
                delay = "0"
                delay_unit = "ms"
                jitter = "0"
                jitter_unit = "ms"

                m = tc_rate.search(v)
                if m:
                    bw = m.group(1)

                m = tc_loss.search(v)
                if m:
                    loss = m.group(1)

                m = tc_delay.search(v)
                if m:
                    delay = float(m.group(1))
                    delay_unit = m.group(2)

                m = tc_jitter.search(v)
                if m:
                    jitter = m.group(1)
                    jitter_unit = m.group(2)

                if "loss 100%" in v:
                    is_active = False

                if_fields = i.split("_")
                if is_active:
                    if len(if_fields) > 1:
                        if (
                            (if_fields[0] == c or if_fields[1] == c)
                            and if_fields[0] in g.nodes()
                            and if_fields[1] in g.nodes()
                        ):
                            # print(f"Adding edge: {if_fields[0]} -> {if_fields[1]}")
                            g.add_edge(if_fields[0], if_fields[1])
                else:
                    if len(if_fields) > 1:
                        if (
                            (if_fields[0] == c or if_fields[1] == c)
                            and if_fields[0] in g.nodes()
                            and if_fields[1] in g.nodes()
                        ):
                            # print(f"Removing edge: {if_fields[0]} -> {if_fields[1]}")
                            try:
                                g.remove_edge(if_fields[0], if_fields[1])
                            except Exception as e:
                                try:
                                    g.remove_edge(if_fields[1], if_fields[2])
                                except Exception as e:
                                    print(e)

                bg = "#f3f4f6" if is_active else "#fde8e8"
                with ui.row().classes("place-items-center w-full").style(
                    f"background-color: {bg}"
                ):
                    if is_active:
                        ui.icon("cloud_done").classes("text-green-500").style(
                            "width: 40px"
                        )
                    else:
                        ui.icon("cloud_off").classes("text-red-500").style(
                            "width: 40px"
                        )
                    ui.markdown(f"**{c}**").classes("text-lg").style("width: 250px")
                    ui.label(f"{i}").classes("text-lg").style("width: 250px")
                    ui.markdown(
                        f"**bw:** {bw} **loss:** {loss}% **delay:** {delay}{delay_unit} **jitter:** {jitter}{jitter_unit}"
                    ).classes("text-lg")
                    ui.space()
                    link = {
                        "container": c,
                        "interface": i,
                        "bw": bw,
                        "loss": loss,
                        "delay": delay,
                        "jitter": jitter,
                    }
                    ui.button(
                        "Edit",
                        on_click=lambda link=link: show_link_dialog(
                            link, links_area, compose_file
                        ),
                    )
                    active_toggle = ui.switch("Active", value=is_active)
                    active_toggle.on_value_change(
                        lambda link=link, active_toggle=active_toggle: do_link_toggle(
                            active_toggle, link, links_area, compose_file
                        )
                    )
    drawing_links_in_progress = False


def draw_map(map_area: ui.scroll_area):
    global g
    with map_area:
        map_area.clear()

        with ui.matplotlib(figsize=(8, 5)).figure as fig:

            # x = np.linspace(0.0, 5.0)
            # y = np.cos(2 * np.pi * x) * np.exp(-x)
            ax = fig.gca()
            nx.draw(
                g,
                with_labels=True,
                font_weight="bold",
                ax=ax,
                pos=nx.circular_layout(g),
            )
            # ax.plot(x, y, "-")


def ui_main(compose_file: str, contact_plan: str):
    global g
    g = load_graph_from_file(compose_file)
    print(g)
    print(g.edges())

    with ui.element("div").classes("w-full h-screen"):
        # ui.markdown("### Docker TestBed Manager")
        with ui.row().classes("items-center"):
            ui.label("Scenario: ")
            lbl_compose_file = ui.label(compose_file).classes("text-blue-500")
            ui.label("Contact Plan: ")
            lbl_contact_plan = ui.label(contact_plan).classes("text-blue-500")
            ui.label("Status: ")
            lbl_status = ui.label("DOWN").classes("text-red-500")
            ui.label("Simulation Time: ")
            lbl_time = ui.label("N/A").classes("text-red-500")
            ui.label("Next Event: ")
            lbl_next_event = ui.label("N/A").classes("text-red-500")
            ui.space()
            btn_next = ui.button(
                "Jump to next event",
            )
            btn_pause = ui.button("Pause")
            btn_pause.on_click(lambda: pause_resume_scenario(btn_pause))

        with ui.tabs().classes("w-full") as tabs:
            tab_overview = ui.tab("Overview")
            tab_links = ui.tab("Links")
            tab_map = ui.tab("Map")
        with ui.tab_panels(tabs, value=tab_overview).classes("w-full h-full"):
            with ui.tab_panel(tab_overview):
                with ui.scroll_area().classes("h-2/3 border"):
                    containers = get_container_names(compose_file)
                    for c in containers:
                        with ui.row():
                            ui.label(c).classes("text-lg").style("width: 250px")
                            ui.space()
                            ui.button(
                                "Shell",
                                on_click=lambda c=c: open_xterm(c),
                            )
                            ui.button(
                                "Log", on_click=lambda c=c: open_log(compose_file, c)
                            )
            with ui.tab_panel(tab_links):
                # draw_overview()
                ui.button(
                    "Refresh",
                    on_click=lambda: draw_links(links_area, compose_file),
                )
                links_area = ui.scroll_area().classes("h-2/3 border")
                # draw_links(links_area, compose_file)
            with ui.tab_panel(tab_map):
                map_area = ui.scroll_area().classes("h-2/3 border")

                draw_map(map_area)
        btn_next.on_click(
            lambda: jump_to_next_event(
                compose_file, lbl_time, lbl_next_event, links_area, map_area
            )
        )
        # draw_links()

    ui.timer(
        10.0,
        lambda: health_check_timer(compose_file, lbl_status),
    )
    ui.timer(
        2.0,
        lambda: timesync_timer(lbl_time, lbl_next_event),
    )
    ui.timer(
        5.0,
        lambda: linkstate_timer(compose_file, links_area, map_area),
    )
    ui.run(
        reload=True,
        title="Docker TestBed Manager",
        show=False,
        port=8800,
        host="127.0.0.1",
    )


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <compose-file> <contact-plan>")
        quit(1)
    compose_file = sys.argv[1]
    contact_plan = sys.argv[2]
    if not is_scenario_running(compose_file):
        print("Scenario is not running")
        quit(1)

    print("Retrieving container names...")
    container_names = get_container_names(compose_file)
    print(container_names)

    # import time

    # s = time.time()
    # print(get_container_interfaces(compose_file))
    # print(f"Elapsed time: {time.time() - s}")
    # print()
    # s = time.time()
    # print(get_container_interfaces_parallel(compose_file))
    # print(f"Elapsed time: {time.time() - s}")
    ui_main(compose_file, contact_plan)


if __name__ in {"__main__", "__mp_main__"}:
    main()
