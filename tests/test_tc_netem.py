"""Unit tests for the tc_netem module.

Two functions are exercised:

* ``set_on_interface`` — builds the tc command string and delegates to
  ``run_in_container``. We monkeypatch ``run_in_container`` and assert the
  constructed command string and pass-through arguments.
* ``run_in_container`` — shells out via ``subprocess.run``. We monkeypatch
  ``subprocess.run`` and assert command construction, return value, and the
  ``RuntimeError`` raised on non-zero exit codes.
"""

from __future__ import annotations

import subprocess

import pytest

from tools.contact_player import tc_netem
from tools.contact_player.tc_netem import run_in_container, set_on_interface


# ---------------------------------------------------------------------------
# run_in_container fixtures
# ---------------------------------------------------------------------------
class _FakeResult:
    """Minimal stand-in for ``subprocess.CompletedProcess``."""

    returncode: int
    stdout: str
    stderr: str
    args: str

    def __init__(self, returncode: int, stdout: str, stderr: str, args: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.args = args


# ===================================================================
# set_on_interface — command construction
# ===================================================================
class TestSetOnInterface:
    @pytest.fixture
    def fake_run(self, monkeypatch: pytest.MonkeyPatch):
        """Monkeypatch run_in_container to capture the command it receives."""
        captured: list[tuple[str, str]] = []

        def _fake(container: str, command: str, **_rest: object) -> str:
            captured.append((container, command))
            return "stdout"

        monkeypatch.setattr(tc_netem, "run_in_container", _fake)
        return captured

    def test_default_command_is_change(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0")
        _container, command = fake_run[0]
        assert "qdisc change" in command

    def test_command_string_defaults(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0")
        _container, command = fake_run[0]
        assert command == "tc qdisc change dev eth0 root netem loss 0.0% delay 0ms 0ms"

    def test_delay_above_1000_uses_seconds(self, fake_run: list[tuple[str, str]]) -> None:
        # 1500 // 1000 == 1 -> "delay 1s"
        set_on_interface("c", "eth0", delay=1500)
        _container, command = fake_run[0]
        assert "delay 1s " in command or command.endswith("delay 1s")

    def test_delay_boundary_1000_uses_ms(self, fake_run: list[tuple[str, str]]) -> None:
        # 1000 is NOT > 1000, so it stays in milliseconds
        set_on_interface("c", "eth0", delay=1000)
        _container, command = fake_run[0]
        assert "delay 1000ms" in command

    def test_delay_below_1000_uses_ms(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0", delay=500)
        _container, command = fake_run[0]
        assert "delay 500ms" in command

    def test_delay_zero(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0", delay=0)
        _container, command = fake_run[0]
        assert "delay 0ms" in command

    def test_loss_interpolated(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0", loss=5.5)
        _container, command = fake_run[0]
        assert "loss 5.5%" in command

    def test_loss_default_is_zero(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0")
        _container, command = fake_run[0]
        assert "loss 0.0%" in command

    def test_jitter_interpolated(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface("c", "eth0", jitter=2.5)
        _container, command = fake_run[0]
        assert "2.5ms" in command

    def test_bandwidth_appended_when_nonempty(
        self, fake_run: list[tuple[str, str]]
    ) -> None:
        set_on_interface("c", "eth0", bandwidth="100mbit")
        _container, command = fake_run[0]
        assert "rate 100mbit" in command

    def test_bandwidth_omitted_when_empty(
        self, fake_run: list[tuple[str, str]]
    ) -> None:
        set_on_interface("c", "eth0")
        _container, command = fake_run[0]
        assert "rate" not in command

    def test_full_command_structure(self, fake_run: list[tuple[str, str]]) -> None:
        set_on_interface(
            "c", "eth0", command="add", loss=10.0, delay=200, jitter=5, bandwidth="1gbit"
        )
        _container, command = fake_run[0]
        assert command == (
            "tc qdisc add dev eth0 root netem loss 10.0% delay 200ms 5ms rate 1gbit"
        )

    def test_returns_run_in_container_stdout(
        self, fake_run: list[tuple[str, str]]
    ) -> None:
        assert set_on_interface("c", "eth0") == "stdout"
        # run_in_container was actually delegated to with the right container
        assert len(fake_run) == 1
        assert fake_run[0][0] == "c"

    def test_passes_through_container_and_interface(
        self, fake_run: list[tuple[str, str]]
    ) -> None:
        set_on_interface("mycontainer", "myiface", command="del")
        container, command = fake_run[0]
        assert container == "mycontainer"
        assert "dev myiface" in command
        assert "qdisc del" in command


# ===================================================================
# run_in_container — subprocess delegation
# ===================================================================
class TestRunInContainer:
    def test_success_returns_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def _fake(args: str, **_kwargs: object) -> _FakeResult:
            captured["args"] = args
            return _FakeResult(0, "hello out", "", args)

        monkeypatch.setattr(subprocess, "run", _fake)

        out = run_in_container("node1", "tc qdisc show")
        assert out == "hello out"
        assert captured["args"] == "docker exec node1 bash -c 'tc qdisc show'"

    def test_failure_raises_runtimeerror_with_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake(args: str, **_kwargs: object) -> _FakeResult:
            return _FakeResult(1, "", "something broke", args)

        monkeypatch.setattr(subprocess, "run", _fake)

        with pytest.raises(RuntimeError, match="something broke"):
            run_in_container("node1", "bad command")

    def test_debug_print_does_not_break(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake(args: str, **_kwargs: object) -> _FakeResult:
            return _FakeResult(0, "ok", "", args)

        monkeypatch.setattr(subprocess, "run", _fake)

        # debug_print=True must not change behaviour
        assert run_in_container("node1", "echo hi", debug_print=True) == "ok"
