from __future__ import annotations

import subprocess
from typing import TypedDict, cast

import networkx as nx
import yaml
from tools.contact_player.tc_netem import run_in_container


class ComposeService(TypedDict):
    networks: dict[str, object]


class ComposeConfig(TypedDict):
    services: dict[str, ComposeService]


def run_on_host(command: str, debug_print: bool = False) -> str:
    if debug_print:
        print(f"Running command on host: {command}")
    res = subprocess.run(
        f"{command}",
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if res.returncode != 0:
        print("Error executing subprocess:")
        print(f"stderr: {res.stderr}")
        raise RuntimeError(f"Host command failed: {res.stderr}")
    return res.stdout


def get_container_names(compose_file: str) -> list[str]:
    out = run_on_host(f"docker compose -f {compose_file} config --services")
    return [container for container in out.splitlines() if container]


def get_container_interfaces(compose_file: str) -> dict[str, dict[str, str]]:
    container_names = sorted(get_container_names(compose_file))
    container_ifs: dict[str, dict[str, str]] = {}

    for container in container_names:
        tc_output = run_in_container(container, "tc qdisc show")
        interfaces: dict[str, str] = {}
        for line in tc_output.splitlines():
            fields = line.split()
            if len(fields) >= 5 and fields[0] == "qdisc" and fields[1] == "netem":
                interfaces[fields[4]] = line
        container_ifs[container] = interfaces
    return container_ifs


def is_scenario_running(compose_file: str) -> bool:
    num_services = int(
        run_on_host(f"docker compose -f {compose_file} config --services | wc -l")
    )
    running = int(
        run_on_host(
            f"docker compose -f {compose_file} ps --services --filter status=running | wc -l"
        )
    )
    return num_services == running


def load_graph_from_file(
    compose_file: str,
) -> nx.Graph[str, dict[str, object], dict[str, object]]:
    graph: nx.Graph[str, dict[str, object], dict[str, object]] = nx.Graph()
    with open(compose_file, "r") as f:
        config = cast(ComposeConfig, yaml.safe_load(f))
        services = config["services"]

        for service in services:
            graph.add_node(service)

        for service, config in services.items():
            networks = config["networks"]
            for network in networks:
                for other, other_config in services.items():
                    if service != other and network in other_config["networks"]:
                        graph.add_edge(service, other)
    return graph
