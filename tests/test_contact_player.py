"""Tests for the ContactPlayer lifecycle and link-set logic.

These tests target the current ``ContactPlayer`` implementation in
``tools/contact_player/contact_player.py``. Socket-bound players are always
created with ``CONTROL_PORT=0`` (ephemeral) and closed afterwards via the
:func:`player_scope` context manager to avoid port-9966 collisions and socket
leaks between tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
    LinkProperties,
)
from tools.contact_player.contact_player import ContactPlayer
from tools.contact_player.scenario import NetworkInterface, Node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_node(name: str, node_id: str, nets: list[str]) -> Node:
    """Build a Node with one interface per network, dev = '{net}_0'."""
    idx = int(node_id)
    interfaces: dict[str, NetworkInterface] = {}
    for j, net in enumerate(nets):
        interfaces[net] = NetworkInterface(
            ip=f"10.{idx}.{j}.1",
            dev=f"{net}_0",
        )
    return Node(name, node_id, f"ipn:{node_id}.0", interfaces=interfaces)


def _make_plan(contacts: list[Contact], loop: bool = False) -> ContactPlan:
    """Build a ContactPlan with given contacts all initially INACTIVE."""
    return ContactPlan(
        ccp_path=Path("."),
        contacts={c: ContactState.INACTIVE for c in contacts},
        loop=loop,
    )


@contextmanager
def player_scope(player: ContactPlayer):
    """Yield a player and guarantee its socket is closed afterwards."""
    try:
        yield player
    finally:
        player.sock.close()


class _CallRecorder:
    """Record every ``set_on_interface`` call as ``(args, kwargs)`` tuples."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def __call__(self, *args: str, **kwargs: object) -> str:
        self.calls.append((args, kwargs))
        return "ok"

    def reset(self) -> None:
        self.calls.clear()


# ===================================================================
# unique_interfaces
# ===================================================================
class TestUniqueInterfaces:
    def test_dedup_same_src_and_network(self) -> None:
        n1 = _make_node("n1", "1", ["net"])
        n2 = _make_node("n2", "2", ["net"])
        n3 = _make_node("n3", "3", ["net"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        # Two contacts from n1 on the same network must dedup to one interface
        c1 = Contact(n1, n2, "net", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        c2 = Contact(n1, n3, "net", 30, 40, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([c1, c2])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            assert player.unique_interfaces == {(n1, "net_0")}

    def test_multiple_networks_multiple_entries(self) -> None:
        n1 = _make_node("n1", "1", ["netA", "netB"])
        n2 = _make_node("n2", "2", ["netA", "netB"])
        nodes = {"n1": n1, "n2": n2}

        ca = Contact(n1, n2, "netA", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        cb = Contact(n1, n2, "netB", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([ca, cb])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            assert player.unique_interfaces == {
                (n1, "netA_0"),
                (n1, "netB_0"),
            }


# ===================================================================
# static_links / active_dynamic_links
# ===================================================================
class TestLinkSets:
    def test_compose_link_no_contact(self) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        contact = Contact(n1, n2, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([contact])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            # n2-n3 is a physical link with no contact -> static
            assert frozenset({n2, n3}) in player.static_links
            # n1-n2 has a dynamic contact -> not static
            assert frozenset({n1, n2}) not in player.static_links
            assert player.active_dynamic_links == set()

    def test_fixed_link_in_static_not_dynamic(self) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2"])
        nodes = {"n1": n1, "n2": n2}

        fixed = Contact(n1, n2, "n1_n2", 0, -1, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([fixed])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            assert frozenset({n1, n2}) in player.static_links
            assert frozenset({n1, n2}) not in player.active_dynamic_links

    def test_dynamic_contact_lifecycle(self) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        contact = Contact(n2, n3, "n2_n3", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([contact])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            pair = frozenset({n2, n3})
            # Initially inactive
            assert pair not in player.static_links
            assert pair not in player.active_dynamic_links

            # Activate
            player.plan.contacts[contact] = ContactState.ACTIVE
            assert pair in player.active_dynamic_links
            assert pair not in player.static_links

            # Deactivate
            player.plan.contacts[contact] = ContactState.INACTIVE
            assert pair not in player.active_dynamic_links
            assert pair not in player.static_links

    def test_pair_with_both_fixed_and_dynamic(self) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2"])
        nodes = {"n1": n1, "n2": n2}

        fixed = Contact(n1, n2, "n1_n2", 0, -1, LinkProperties("1mbit", 0, 0, 0))
        dynamic = Contact(n1, n2, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([fixed, dynamic])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            pair = frozenset({n1, n2})
            # Dynamic contact makes the pair a dynamic link (even if inactive)
            assert pair not in player.static_links
            assert pair not in player.active_dynamic_links

    def test_one_directional_dynamic_removes_pair(self) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        # Only one directed contact n1->n2 (not symmetric)
        contact = Contact(n1, n2, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([contact])

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            pair = frozenset({n1, n2})
            # The undirected pair counts as dynamic
            assert pair not in player.static_links
            assert pair not in player.active_dynamic_links  # inactive


# ===================================================================
# setup()
# ===================================================================
class TestSetup:
    def test_one_add_per_unique_interface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        fixed = Contact(n1, n2, "n1_n2", 0, -1, LinkProperties("100mbit", 0, 0, 0))
        dynamic = Contact(n2, n3, "n2_n3", 20, 40, LinkProperties("2mbit", 0, 0, 0))
        plan = _make_plan([fixed, dynamic])

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.setup()

            # One "add" call per unique (node, dev)
            assert len(recorder.calls) == 2
            seen: set[tuple[str, str]] = set()
            for args, kwargs in recorder.calls:
                assert args[0] in ("n1", "n2")
                assert args[2] == "add"
                assert kwargs.get("loss") == 100
                seen.add((args[0], args[1]))
            assert seen == {("n1", "n1_n2_0"), ("n2", "n2_n3_0")}

    def test_same_network_two_contacts_one_add(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2"])
        nodes = {"n1": n1, "n2": n2}

        c1 = Contact(n1, n2, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        c2 = Contact(n1, n2, "n1_n2", 30, 40, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([c1, c2])

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.setup()
            # Same network -> one deduplicated add
            assert len(recorder.calls) == 1
            args, kwargs = recorder.calls[0]
            assert args == ("n1", "n1_n2_0", "add")
            assert kwargs == {"loss": 100}

    def test_symmetric_contact_adds_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2"])
        nodes = {"n1": n1, "n2": n2}

        c1 = Contact(n1, n2, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        c2 = Contact(n2, n1, "n1_n2", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([c1, c2])

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.setup()
            assert len(recorder.calls) == 2
            seen = {(a[0], a[1]) for a, _ in recorder.calls}
            assert seen == {("n1", "n1_n2_0"), ("n2", "n1_n2_0")}
            for _, kwargs in recorder.calls:
                assert kwargs == {"loss": 100}


# ===================================================================
# cleanup()
# ===================================================================
class TestCleanup:
    def test_one_del_per_interface_and_truncates_netmap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        fixed = Contact(n1, n2, "n1_n2", 0, -1, LinkProperties("100mbit", 0, 0, 0))
        dynamic = Contact(n2, n3, "n2_n3", 20, 40, LinkProperties("2mbit", 0, 0, 0))
        plan = _make_plan([fixed, dynamic])

        netmap = tmp_path / "topo.netmap"
        netmap.write_text("stale content\n")

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(
                plan, Path("x.compose"), nodes, netmap_path=netmap, CONTROL_PORT=0
            )
        ) as player:
            player.cleanup()

            # One "del" per unique interface
            assert len(recorder.calls) == 2
            seen = {(a[0], a[1]) for a, _ in recorder.calls}
            assert seen == {("n1", "n1_n2_0"), ("n2", "n2_n3_0")}
            for _args, kwargs in recorder.calls:
                assert kwargs == {"command": "del"}

            # netmap truncated
            assert netmap.read_text() == ""
            # socket closed
            assert player.sock._closed is True

    def test_resilient_to_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup is best-effort: a failing set_on_interface does not
        propagate and the remaining interfaces are still processed."""
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        fixed = Contact(n1, n2, "n1_n2", 0, -1, LinkProperties("100mbit", 0, 0, 0))
        dynamic = Contact(n2, n3, "n2_n3", 20, 40, LinkProperties("2mbit", 0, 0, 0))
        plan = _make_plan([fixed, dynamic])

        calls: list[tuple[object, object]] = []

        def failing(name: object, interface: object, **_kwargs: object) -> str:
            calls.append((name, interface))
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", failing
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            # Should NOT propagate
            player.cleanup()

            # All unique interfaces were attempted despite the errors
            attempted = {(c[0], c[1]) for c in calls}
            assert attempted == {("n1", "n1_n2_0"), ("n2", "n2_n3_0")}
            assert player.sock._closed is True


# ===================================================================
# activate() / deactivate()
# ===================================================================
class TestActivateDeactivate:
    def test_activate_passes_contact_props(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        n1 = _make_node("n1", "1", ["net"])
        n2 = _make_node("n2", "2", ["net"])
        nodes = {"n1": n1, "n2": n2}
        contact = Contact(n1, n2, "net", 10, 20, LinkProperties("1mbit", 5, 10, 2))
        plan = _make_plan([contact])

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.activate(contact)

            assert len(recorder.calls) == 1
            args, kwargs = recorder.calls[0]
            assert args == ("n1", "net_0")
            assert kwargs == {
                "command": "change",
                "loss": 5.0,
                "delay": 10.0,
                "jitter": 2.0,
                "bandwidth": "1mbit",
            }
            assert plan.contacts[contact] == ContactState.ACTIVE

    def test_deactivate_forces_loss_100(self, monkeypatch: pytest.MonkeyPatch) -> None:
        n1 = _make_node("n1", "1", ["net"])
        n2 = _make_node("n2", "2", ["net"])
        nodes = {"n1": n1, "n2": n2}
        contact = Contact(n1, n2, "net", 10, 20, LinkProperties("1mbit", 5, 10, 2))
        plan = _make_plan([contact])
        plan.contacts[contact] = ContactState.ACTIVE

        recorder = _CallRecorder()
        monkeypatch.setattr(
            "tools.contact_player.contact_player.set_on_interface", recorder
        )

        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.deactivate(contact)

            assert len(recorder.calls) == 1
            args, kwargs = recorder.calls[0]
            assert args == ("n1", "net_0")
            # loss forced to 100.0, other props still forwarded
            assert kwargs == {
                "command": "change",
                "loss": 100.0,
                "delay": 10.0,
                "jitter": 2.0,
                "bandwidth": "1mbit",
            }
            assert plan.contacts[contact] == ContactState.INACTIVE


# ===================================================================
# update_netmap()
# ===================================================================
class TestUpdateNetmap:
    def test_writes_static_and_active_dynamic(self, tmp_path: Path) -> None:
        n1 = _make_node("n1", "1", ["n1_n2"])
        n2 = _make_node("n2", "2", ["n1_n2", "n2_n3"])
        n3 = _make_node("n3", "3", ["n2_n3"])
        nodes = {"n1": n1, "n2": n2, "n3": n3}

        # n1-n2 has no contact -> static; n2-n3 dynamic and active
        dynamic = Contact(n2, n3, "n2_n3", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([dynamic])
        plan.contacts[dynamic] = ContactState.ACTIVE

        netmap = tmp_path / "topo.netmap"

        with player_scope(
            ContactPlayer(
                plan, Path("x.compose"), nodes, netmap_path=netmap, CONTROL_PORT=0
            )
        ) as player:
            player.update_netmap()

            lines = {line for line in netmap.read_text().splitlines() if line}
            # link endpoints come from a frozenset, so order is nondeterministic
            assert {"n1 - n2", "n2 - n1"} & lines
            assert {"n2 . n3", "n3 . n2"} & lines
            assert len(lines) == 2

    def test_no_netmap_path_is_noop(self) -> None:
        n1 = _make_node("n1", "1", ["net"])
        n2 = _make_node("n2", "2", ["net"])
        nodes = {"n1": n1, "n2": n2}
        contact = Contact(n1, n2, "net", 10, 20, LinkProperties("1mbit", 0, 0, 0))
        plan = _make_plan([contact])

        # No netmap_path -> update_netmap should simply return without error
        with player_scope(
            ContactPlayer(plan, Path("x.compose"), nodes, CONTROL_PORT=0)
        ) as player:
            player.update_netmap()
