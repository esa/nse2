import subprocess


def run_in_container(container_name: str, command: str, debug_print: bool = False):
    """Executes a command inside a Docker container.

    Args:
        container_name: The name of the Docker container.
        command: The shell command to execute.
        debug_print: Whether to print the command before execution (default: False).

    Returns:
        The standard output from the executed command.

    Raises:
        SystemExit: If the command returns a non-zero exit code.
    """
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
        quit(1)
    return res.stdout


def set_on_all_interfaces(container_name: str, command: str, loss: float = 0.0):
    """Applies a tc netem rule to all ethernet interfaces in a container.

    Args:
        container_name: The name of the Docker container.
        command: The tc qdisc command operation (e.g., 'add', 'change', 'del').
        loss: Packet loss percentage to apply (default: 0.0).

    Returns:
        Standard output from the executed command.
    """
    res = run_in_container(
        container_name,
        "cat /proc/net/dev | awk \"{print \$1}\" | grep -E -o '^eth[0-9]+' | xargs -I @ tc qdisc "
        + command
        + " dev @ root netem loss "
        + str(loss)
        + "%",
    )
    return res


def set_on_interface(
    container_name: str,
    interface: str,
    command: str = "change",
    loss: float = 0.0,
    delay: float = 0,
    jitter: float = 0,
    bandwidth: str = "",
):
    """Applies network emulation (netem) rules to a specific container interface.

    Args:
        container_name: The name of the Docker container.
        interface: The network interface to modify (e.g., 'eth0').
        command: The tc qdisc command operation (e.g., 'add', 'change', 'del').
        loss: Packet loss percentage (default: 0.0).
        delay: Link delay in milliseconds (default: 0).
        jitter: Link delay jitter in milliseconds (default: 0).
        bandwidth: Bandwidth limit string, e.g., '100mbit' (default: "").

    Returns:
        Standard output from the executed command.
    """
    if delay > 1000:
        delay_str = f"{delay//1000}s"
    else:
        delay_str = f"{delay}ms"
    print(delay_str)
    cmd = f"tc qdisc {command} dev {interface} root netem loss {loss}% delay {delay_str} {jitter}ms"
    if bandwidth != "":
        cmd += f" rate {bandwidth}"
    res = run_in_container(
        container_name,
        cmd,
        debug_print=False,
    )
    return res
