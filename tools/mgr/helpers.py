import subprocess
import networkx as nx
import yaml


def expand_human_bitrates(bandwidth: str) -> int:
    """
    Converts a human-readable bitrate to bits per second.
    """
    bandwidth = bandwidth.strip()
    bandwidth = bandwidth.lower()
    bandwidth.replace("kbit", "000")
    bandwidth.replace("mbit", "000000")
    bandwidth.replace("gbit", "000000000")
    bandwidth.replace("tbit", "000000000000")
    return int(bandwidth)


def run_in_container(container_name: str, command: str, debug_print: bool = False):
    if debug_print:
        print(f"Running command in container {container_name}: {command}")
    res = subprocess.run(
        f"docker exec {container_name} bash -c '{command}'",
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if res.returncode != 0:
        print("Error executing subprocess:")
        print(f"Args: {res.args}")
        print(f"stderr: {res.stderr}")
        raise Exception("Error executing subprocess", res.returncode, res.stderr)
    return res.stdout


def run_on_host(command: str, debug_print=False):
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
        print(f"Args: {res.args}")
        print(f"stderr: {res.stderr}")
        quit(1)
    return res.stdout


def get_container_names(compose_file: str):
    out = run_on_host(f"docker compose -f {compose_file} config --services")
    container_names = out.split("\n")
    container_names = [container for container in container_names if len(container) > 0]
    return container_names


def get_container_interfaces(compose_file: str):
    container_names = sorted(get_container_names(compose_file))
    print(container_names)
    container_ifs = {}

    for c in container_names:
        # print(f"Retrieving interfaces for container {c}")
        try:
            tc_out = run_in_container(
                c, "tc qdisc show | grep netem", debug_print=False
            )
            # print(f"TC on {c}: \n{tc_out}")
            lines = tc_out.split("\n")
            container_ifs[c] = {}
            for line in lines:
                if len(line) == 0:
                    continue
                # extract interface name
                interface = line.split()[4]
                # print(f"Interface: {interface}")
                container_ifs[c][interface] = line
        except Exception as e:
            if e.args[1] == 1:
                print(f"Container {c} has no netem rules")
            else:
                print(e)
                raise Exception("Error retrieving interfaces")
    return container_ifs


def get_netem_from_if(container_name: str):
    try:
        ifaces = {}
        tc_out = run_in_container(
            container_name, f"tc qdisc show| grep netem", debug_print=False
        )
        lines = tc_out.split("\n")
        lines = [line for line in lines if len(line) > 0]
        for line in lines:
            if len(line) == 0:
                continue
            # extract interface name
            interface = line.split()[4]
            ifaces[interface] = line
        return (container_name, ifaces)
    except Exception as e:
        # if e.args[1] == 1:
        #     print(
        #         f"Container {container_name} has no netem rules on interface {interface}"
        #     )
        return (container_name, [])
    # else:
    #     print(e)
    #     raise Exception("Error retrieving interfaces")


def get_container_interfaces_parallel(compose_file: str):
    from multiprocessing import Pool

    pool = Pool()

    container_names = sorted(get_container_names(compose_file))
    container_ifs = {}

    results = pool.map(get_netem_from_if, container_names)
    # results = pool.map(add_1, container_names)
    pool.close()
    pool.join()
    # print(results)
    for container_name, interfaces in results:
        container_ifs[container_name] = interfaces
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


def set_on_interface(
    container_name: str,
    interface: str,
    command: str = "change",
    loss: float = 0.0,
    delay: int = 0,
    jitter: int = 0,
    bandwidth: str = "",
):
    """
    Sets the command on the specified interface of the container.
    """
    cmd = f"tc qdisc {command} dev {interface} root netem loss {loss}% delay {delay}ms {jitter}ms"
    if bandwidth != "":
        cmd += f" rate {bandwidth}"
    res = run_in_container(
        container_name,
        cmd,
        debug_print=False,
    )
    return res


def load_graph_from_file(compose_file: str) -> nx.Graph:
    G = nx.Graph()
    with open(compose_file, "r") as f:
        data = yaml.safe_load(f)
        for service in data["services"]:
            G.add_node(service)

        for service in data["services"]:
            nets = data["services"][service]["networks"]
            for link in nets:
                for other in data["services"]:
                    if service != other and link in data["services"][other]["networks"]:
                        G.add_edge(service, other)
    # isolates = list(nx.isolates(G))
    # for node in isolates:
    #     G.remove_node(node)
    return G
