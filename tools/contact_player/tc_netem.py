import subprocess


class SubprocessError(Exception):
    """Raised when a command inside a Docker container fails."""

    pass


def run_in_container(
    container_name: str, command: str, debug_print: bool = False
) -> subprocess.CompletedProcess[str]:
    """Executes a command inside a Docker container.

    Args:
        container_name: The name of the Docker container.
        command: The shell command to execute.
        debug_print: Whether to print the command before execution (default: False).

    Returns:
        The completed process result, including returncode, stdout, and stderr.

    Raises:
        SubprocessError: If the command returns a non-zero exit code.
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
        print(
            "Error executing subprocess:\n"
            + f"  Container: {container_name}\n"
            + f"  Command:   {res.args}\n"
            + f"  stderr:    {res.stderr.strip()}"
        )
        raise SubprocessError(
            f"Command failed in container '{container_name}' "
            + f"(exit {res.returncode}): {res.stderr.strip()}"
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
) -> str:
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
        delay_str = f"{delay // 1000}s"
    else:
        delay_str = f"{delay}ms"
    cmd = f"tc qdisc {command} dev {interface} root netem loss {loss}% delay {delay_str} {jitter}ms"
    if bandwidth != "":
        cmd += f" rate {bandwidth}"
    res = run_in_container(container_name, cmd)
    return res.stdout
