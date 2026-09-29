"""Shared NiceGUI footer for container shells and logs."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import shutil
import signal
import struct
import termios
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from nicegui import core, events, ui
from nicegui.element import Element
from nicegui.elements.button import Button
from nicegui.elements.log import Log
from nicegui.elements.splitter import Splitter
from nicegui.elements.tabs import Tab, TabPanel, TabPanels, Tabs
from nicegui.elements.xterm import Xterm

Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")
KINDS: tuple[tuple[str, str], ...] = (("shell", "terminal"), ("logs", "article"))
FOCUSED_TAB_STYLE = "background-color: rgba(255, 255, 255, 0.35); border-radius: 4px;"
OTHER_VIEW_TAB_STYLE = (
    "background-color: rgba(255, 255, 255, 0.25); border-radius: 4px;"
)

DRAG_HANDLE_JS = """
    (e) => {
        e.preventDefault();
        const footer = e.target.closest('footer');
        const panel = footer.querySelector('.console-panel');
        const startY = e.clientY;
        const startHeight = panel.offsetHeight;
        const onMove = (event) => {
            panel.style.height = Math.max(100, startHeight - (event.clientY - startY)) + 'px';
        };
        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }
"""


@dataclass
class ConsoleState:
    open: bool
    split: bool
    focus: Side
    left: str
    right: str


@dataclass
class ConsoleView:
    tabs: Tabs
    chevron: Button
    panel: Element
    single: Element
    splitter: Splitter
    left_content: Element
    left_split_host: Element


class ConsoleFooter:
    """Unified tabs and optional split view for pre-created container consoles."""

    def __init__(
        self,
        containers: list[str],
        node_icons: Mapping[str, str] | None = None,
    ) -> None:
        if len(set(containers)) != len(containers):
            raise ValueError("Container names must be unique")

        self.containers: list[str] = sorted(containers)
        self.node_icons: dict[str, str] = dict(node_icons or {})
        self.keys: list[str] = [
            f"{name}:{kind}" for name in self.containers for kind, _ in KINDS
        ]
        self.state: ConsoleState = ConsoleState(
            open=False,
            split=False,
            focus="left",
            left=self.keys[0] if self.keys else "",
            right=self.keys[1] if len(self.keys) > 1 else "",
        )
        self.terminals: dict[Side, dict[str, Xterm]] = {"left": {}, "right": {}}
        self.logs: dict[Side, dict[str, Log]] = {"left": {}, "right": {}}
        self.groups: dict[Side, TabPanels] = {}
        self.tab_widgets: dict[str, Tab] = {}
        self.log_tasks: list[asyncio.Task[None]] = []
        self.started: set[tuple[Side, str]] = set()
        self._view: ConsoleView | None = None

    @property
    def view(self) -> ConsoleView:
        if self._view is None:
            raise RuntimeError("Build the console footer before using it")
        return self._view

    def build(self) -> None:
        """Create the footer and all shell/log tabs in the current UI context."""
        if not self.keys:
            return

        with ui.footer().classes("w-full p-0 flex-col gap-0"):
            with ui.row().classes(
                "w-full items-center no-wrap bg-blue-8 px-2 relative"
            ):
                with (
                    ui.tabs()
                    .classes("col min-w-0 text-white")
                    .props("dense mobile-arrows outside-arrows") as tabs
                ):
                    for container in self.containers:
                        for kind, default_icon in KINDS:
                            key = f"{container}:{kind}"
                            icon = (
                                (self.node_icons.get(container) or default_icon)
                                if kind == "shell"
                                else default_icon
                            )
                            self.tab_widgets[key] = ui.tab(
                                key, label=container, icon=icon
                            ).tooltip("Shell" if kind == "shell" else "Logs")
                ui.button(icon="splitscreen", on_click=self.toggle_split).props(
                    "flat dense color=white"
                ).tooltip("Split / unsplit")
                chevron = ui.button(
                    icon="expand_less", on_click=self.toggle_open
                ).props("flat dense color=white")
                ui.element("div").classes(
                    "absolute top-0 left-0 w-full cursor-row-resize"
                ).style("height: 6px; z-index: 10;").on(
                    "mousedown", js_handler=DRAG_HANDLE_JS
                )

            with (
                ui.column()
                .classes("w-full gap-0 console-panel")
                .style("height: 300px; min-height: 100px;") as panel
            ):
                with ui.column().classes("w-full h-full gap-0") as single:
                    with (
                        ui.column()
                        .classes("w-full h-full gap-0")
                        .style("min-width: 0;") as left_content
                    ):
                        self._make_group("left")

                with (
                    ui.splitter(value=50, limits=(20, 80))
                    .classes("w-full h-full")
                    .props(
                        "before-class=overflow-hidden after-class=overflow-hidden"
                    ) as splitter
                ):
                    with splitter.before:
                        with (
                            ui.column()
                            .classes("w-full h-full gap-0")
                            .style("min-width: 0;")
                            .on(
                                "mousedown", lambda _: self.focus("left")
                            ) as left_split_host
                        ):
                            pass
                    with splitter.after:
                        with (
                            ui.column()
                            .classes("w-full h-full gap-0")
                            .style("min-width: 0;")
                            .on("mousedown", lambda _: self.focus("right"))
                        ):
                            self._make_group("right")

        self._view = ConsoleView(
            tabs=tabs,
            chevron=chevron,
            panel=panel,
            single=single,
            splitter=splitter,
            left_content=left_content,
            left_split_host=left_split_host,
        )
        tabs.set_value(self.state.left)
        tabs.on_value_change(self.select_tab)
        panel.set_visibility(False)
        splitter.set_visibility(False)
        ui.context.client.on_delete(self._cancel_log_tasks)  # pyright: ignore[reportUnknownMemberType]
        self.refresh()

    def _make_group(self, side: Side) -> None:
        with ui.tab_panels(value=self._selected(side)).classes(
            "w-full h-full p-0"
        ) as group:
            for container in self.containers:
                shell_key = f"{container}:shell"
                with ui.tab_panel(shell_key).classes("w-full h-full p-0"):
                    terminal = ui.xterm().classes("w-full h-full")
                    ui.element("q-resize-observer").on("resize", terminal.fit)
                    self.terminals[side][shell_key] = terminal

                log_key = f"{container}:logs"
                with ui.tab_panel(log_key).classes("w-full h-full p-0"):
                    log = ui.log(max_lines=500).classes(
                        "w-full h-full bg-grey-10 text-white"
                    )
                    self.logs[side][log_key] = log

        self.groups[side] = group

    def _selected(self, side: Side) -> str:
        return self.state.left if side == "left" else self.state.right

    def fit_visible(self) -> None:
        """Fit each terminal currently shown in the visible pane(s)."""
        sides: tuple[Side, ...] = SIDES if self.state.split else ("left",)
        for side in sides:
            terminal = self.terminals[side].get(self._selected(side))
            if terminal is not None:
                terminal.fit()

    def refresh(self) -> None:
        """Update footer visibility and selected tab emphasis."""
        view = self.view
        view.panel.set_visibility(self.state.open)
        view.single.set_visibility(not self.state.split)
        view.splitter.set_visibility(self.state.split)
        view.chevron.props(
            f"icon={'expand_more' if self.state.open else 'expand_less'}"
        )

        active_side = self.state.focus if self.state.split else "left"
        inactive_side: Side = "right" if active_side == "left" else "left"
        active_key = self._selected(active_side)
        inactive_key = self._selected(inactive_side) if self.state.split else None
        for key, tab in self.tab_widgets.items():
            if key == active_key:
                tab.style(replace=FOCUSED_TAB_STYLE)
            elif key == inactive_key:
                tab.style(replace=OTHER_VIEW_TAB_STYLE)
            else:
                tab.style(replace="")

        if self.state.open:
            ui.timer(0.1, self.fit_visible, once=True)

    def toggle_open(self) -> None:
        self.state.open = not self.state.open
        if self.state.open:
            self._start_selected("left")
            if self.state.split:
                self._start_selected("right")
        self.refresh()

    def toggle_split(self) -> None:
        self.state.open = True
        self.state.split = not self.state.split
        self.state.focus = "left"

        if self.state.split:
            if self.state.right == self.state.left:
                self.state.right = next(
                    key for key in self.keys if key != self.state.left
                )
            self.view.left_content.move(self.view.left_split_host)
            self.groups["right"].set_value(self.state.right)
        else:
            self.view.left_content.move(self.view.single)

        self._start_selected("left")
        if self.state.split:
            self._start_selected("right")
        self.view.tabs.set_value(self.state.left)
        self.refresh()

    def select_tab(
        self,
        event: events.ValueChangeEventArguments[str | Tab | TabPanel | None],
    ) -> None:
        if isinstance(event.value, str):
            self.select_key(event.value)

    def focus(self, side: Side) -> None:
        self.state.focus = side
        self._start_selected(side)
        self.view.tabs.set_value(self._selected(side))
        self.refresh()

    def open_shell(self, container: str) -> None:
        self.select_key(f"{container}:shell")

    def open_logs(self, container: str) -> None:
        self.select_key(f"{container}:logs")

    def select_key(self, key: str) -> None:
        if key not in self.keys:
            return

        self.state.open = True
        side = self.state.focus if self.state.split else "left"
        other: Side = "right" if side == "left" else "left"
        if self.state.split and self._selected(other) == key:
            self.state.focus = other
            self._start_selected(other)
        else:
            if side == "left":
                self.state.left = key
            else:
                self.state.right = key
            self.groups[side].set_value(key)
            self._start_selected(side)

        if self.view.tabs.value != key:
            self.view.tabs.set_value(key)
        self.refresh()

    def _start_selected(self, side: Side) -> None:
        """Attach a backend the first time its pre-created panel is selected."""
        key = self._selected(side)
        if (side, key) in self.started:
            return

        container, kind = key.rsplit(":", maxsplit=1)
        if kind == "shell":
            attach_container_to_xterm(self.terminals[side][key], container)
        else:
            self.log_tasks.append(
                asyncio.create_task(follow_docker_logs(self.logs[side][key], container))
            )
        self.started.add((side, key))

    def _cancel_log_tasks(self) -> None:
        for task in self.log_tasks:
            task.cancel()


def attach_container_to_xterm(terminal: Xterm, container: str) -> None:
    """Connect an xterm.js widget to a Docker shell through a pseudo-terminal."""
    docker_path = shutil.which("docker")
    if docker_path is None:
        raise RuntimeError("docker executable not found in PATH")

    pty_pid, pty_fd = pty.fork()
    if pty_pid == pty.CHILD:
        try:
            os.execv(docker_path, ["docker", "exec", "-it", container, "/bin/bash"])
        except OSError as error:
            os.write(pty_fd, f"Unable to start Docker shell: {error}\r\n".encode())
            os._exit(127)

    loop = core.loop
    if loop is not None:

        def pty_to_terminal() -> None:
            try:
                data = os.read(pty_fd, 1024)
            except OSError:
                loop.remove_reader(pty_fd)
            else:
                terminal.write(data)

        loop.add_reader(pty_fd, pty_to_terminal)

    def terminal_to_pty(event: events.XtermDataEventArguments) -> None:
        with contextlib.suppress(OSError):
            os.write(pty_fd, event.data.encode("utf-8"))

    def resize_terminal(event: events.XtermResizeEventArguments) -> None:
        with contextlib.suppress(OSError):
            fcntl.ioctl(
                pty_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", event.rows, event.cols, 0, 0),
            )

    terminal.on_data(terminal_to_pty)
    terminal.on_resize(resize_terminal)

    closed = False

    def cleanup() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        if loop is not None:
            loop.remove_reader(pty_fd)
        with contextlib.suppress(OSError):
            os.close(pty_fd)
        with contextlib.suppress(ProcessLookupError):
            os.kill(pty_pid, signal.SIGKILL)
        with contextlib.suppress(ChildProcessError):
            os.waitpid(pty_pid, 0)

    ui.context.client.on_delete(cleanup)  # pyright: ignore[reportUnknownMemberType]


async def follow_docker_logs(log: Log, container: str) -> None:
    """Stream a container's recent and new Docker logs into a NiceGUI log."""
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            "--follow",
            "--tail",
            "500",
            "--timestamps",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if process.stdout is not None:
            async for line in process.stdout:
                log.push(line.decode("utf-8", errors="replace").rstrip())
        if process.returncode == 0:
            log.push("Log stream ended.")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        log.push(f"Unable to follow logs: {error}")
    finally:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
