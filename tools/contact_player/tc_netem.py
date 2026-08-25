from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess


ContainerCommand = tuple[str, str, Mapping[str, str] | None]
"""A single parallel execution unit: (container_name, command, env | None)."""


def run_in_container(
    container_name: str,
    command: str,
    env: Mapping[str, str] | None = None,
    debug_print: bool = False,
) -> str:
    """Run a shell command inside a Docker container and return stdout."""
    if debug_print:
        print(f"Running command in container {container_name}: {command}")
    args = ["docker", "exec"]
    if env:
        for k, v in env.items():
            args += ["-e", f"{k}={v}"]
    args += [container_name, "bash", "-c", command]

    res = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed in container {container_name}: {command}\n"
            f"stderr: {res.stderr}"
        )
    return res.stdout


def make_tc_command(
    interface: str,
    command: str = "change",
    loss: float = 0.0,
    delay: float = 0,
    jitter: float = 0,
    bandwidth: str = "",
) -> str:
    """Build a tc-netem qdisc command string without executing it."""
    if delay > 1000:
        delay_str = f"{delay // 1000}s"
    else:
        delay_str = f"{delay}ms"
    cmd = f"tc qdisc {command} dev {interface} root netem loss {loss}% delay {delay_str} {jitter}ms"
    if bandwidth != "":
        cmd += f" rate {bandwidth}"
    return cmd


def run_in_containers_parallel(
    commands: Sequence[ContainerCommand],
    max_workers: int = 8,
    raise_on_error: bool = True,
) -> None:
    """Run multiple docker exec commands concurrently via a thread pool.

    Each element is a ``(container_name, command, env | None)`` tuple.
    When ``raise_on_error`` is True (default) a ``RuntimeError`` listing all
    failures is raised if any command fails. When False, failures are reported
    via ``print`` and the call returns normally, allowing best-effort cleanup
    of the remaining commands even if one of them fails.
    """
    errors: list[tuple[int, str, str, Exception]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(run_in_container, container, cmd, env): i
            for i, (container, cmd, env) in enumerate(commands)
        }
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                i = futures[fut]
                errors.append((i, commands[i][0], commands[i][1], e))

    if not errors:
        return

    lines = [f"  [{i}] {container}: {cmd}\n    {e}" for i, container, cmd, e in errors]
    message = f"{len(errors)}/{len(commands)} parallel commands failed:\n" + "\n".join(
        lines
    )
    if raise_on_error:
        raise RuntimeError(message)
    print(message)
