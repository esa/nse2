import subprocess


def run_in_container(container_name: str, command: str, debug_print: bool = False):
    """Run a shell command inside a Docker container and return stdout."""
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
        raise RuntimeError(
            f"Command failed in container {res.args}:\n" + f"stderr: {res.stderr}"
        )
    return res.stdout


def set_on_interface(
    container_name: str,
    interface: str,
    command: str = "change",
    loss: float = 0.0,
    delay: float = 0,
    jitter: float = 0,
    bandwidth: str = "",
):
    """Apply tc/netem settings to one interface in a Docker container."""
    if delay > 1000:
        delay_str = f"{delay // 1000}s"
    else:
        delay_str = f"{delay}ms"
    cmd = f"tc qdisc {command} dev {interface} root netem loss {loss}% delay {delay_str} {jitter}ms"
    if bandwidth != "":
        cmd += f" rate {bandwidth}"
    res = run_in_container(
        container_name,
        cmd,
        debug_print=False,
    )
    return res
