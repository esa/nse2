"""Tests for CCP parsing and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.contact_player.ccp import (
    Contact,
    ContactPlan,
    ContactState,
    LinkProperties,
    RawCcpContact,
    RawCcpContactPlan,
    _resolve_contacts,
    _resolve_destination,
    _resolve_node,
)
from tools.contact_player.scenario import NetworkInterface, Node


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_nodes() -> dict[str, Node]:
    """Two nodes sharing one network: n1 and n2 on n1_n2."""
    return {
        "n1": Node("n1", "1", "ipn:1.0"),
        "n2": Node("n2", "2", "ipn:2.0"),
    }


@pytest.fixture
def multi_net_nodes() -> dict[str, Node]:
    """Three nodes with pairwise shared networks."""
    return {
        "n1": Node(
            "n1",
            "1",
            "ipn:1.0",
            interfaces={
                "n1_n2": NetworkInterface("10.0.0.1", "n1_n2_0"),
                "n1_n3": NetworkInterface("10.0.1.1", "n1_n3_0"),
            },
        ),
        "n2": Node(
            "n2",
            "2",
            "ipn:2.0",
            interfaces={
                "n1_n2": NetworkInterface("10.0.0.2", "n1_n2_0"),
                "n2_n3": NetworkInterface("10.0.2.1", "n2_n3_0"),
            },
        ),
        "n3": Node(
            "n3",
            "3",
            "ipn:3.0",
            interfaces={
                "n1_n3": NetworkInterface("10.0.1.2", "n1_n3_0"),
                "n2_n3": NetworkInterface("10.0.2.2", "n2_n3_0"),
            },
        ),
    }


# ===================================================================
# RawCcpContact.from_string
# ===================================================================
class TestRawCcpContactFromString:
    def test_valid_contact_line(self) -> None:
        r = RawCcpContact.from_string("a contact +20 +40 n2 n3 2mbit 0.0 10 0.0")
        assert r.begin == 20
        assert r.end == 40
        assert r.src == "n2"
        assert r.dst == "n3"
        assert r.props == LinkProperties("2mbit", 0.0, 10.0, 0.0)
        assert not r.symmetric

    def test_valid_fixed_line(self) -> None:
        r = RawCcpContact.from_string("a fixed n1 n2 100mbit 0.0 100 0.0")
        assert r.begin == 0
        assert r.end == -1
        assert r.src == "n1"
        assert r.dst == "n2"
        assert r.props == LinkProperties("100mbit", 0.0, 100.0, 0.0)
        assert not r.symmetric

    def test_contact_with_symmetric_suffix(self) -> None:
        r = RawCcpContact.from_string("a contact 0 10 n1 n2 1mbit 0 0 0 =")
        assert r.begin == 0
        assert r.end == 10
        assert r.symmetric is True

    def test_fixed_with_symmetric_suffix(self) -> None:
        r = RawCcpContact.from_string("a fixed n1 n2 1mbit 0 0 0 =")
        assert r.begin == 0
        assert r.end == -1
        assert r.symmetric is True

    def test_no_symmetric_equals(self) -> None:
        r = RawCcpContact.from_string("a contact 0 10 n1 n2 1mbit 0 0 0")
        assert r.symmetric is False

    def test_contact_too_few_fields(self) -> None:
        with pytest.raises(ValueError, match="Invalid Contact line"):
            RawCcpContact.from_string("a contact 0 10 n1 n2 1mbit")

    def test_contact_too_many_fields(self) -> None:
        with pytest.raises(ValueError, match="Invalid Contact line"):
            RawCcpContact.from_string("a contact 0 10 n1 n2 1mbit 0 0 0 = extra")

    def test_fixed_too_few_fields(self) -> None:
        with pytest.raises(ValueError, match="Invalid Fixed Link line"):
            RawCcpContact.from_string("a fixed n1 n2 1mbit 0 0")

    def test_fixed_too_many_fields(self) -> None:
        with pytest.raises(ValueError, match="Invalid Fixed Link line"):
            RawCcpContact.from_string("a fixed n1 n2 1mbit 0 0 0 = extra")

    def test_bad_prefix(self) -> None:
        with pytest.raises(ValueError, match="Invalid CoreContact line"):
            RawCcpContact.from_string("a foo n1 n2 1mbit 0 0 0")

    def test_props_as_float(self) -> None:
        r = RawCcpContact.from_string("a contact 0 10 n1 n2 1mbit 0 5 2")
        assert r.props.loss == 0.0
        assert r.props.delay == 5.0
        assert r.props.jitter == 2.0


# ===================================================================
# RawCcpContactPlan.from_file
# ===================================================================
SIMPLE_CCP = """s loop 1

a fixed   n1    n2   100mbit  0.0    100     0.0
a fixed   n2    n1   100mbit  0.0    100     0.0

a contact   20      40    n2    n3   2mbit  0.0    10       0.0
a contact   20      40    n3    n2   2mbit  0.0    10       0.0
"""


class TestRawCcpContactPlanFromFile:
    def test_full_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text(SIMPLE_CCP)
        plan = RawCcpContactPlan.from_file(path)
        assert len(plan.contacts) == 2
        assert len(plan.fixed_contacts) == 2
        assert plan.loop is True
        # Spot-check first contact
        c = plan.contacts[0]
        assert c.src == "n2"
        assert c.dst == "n3"
        assert c.begin == 20
        assert c.end == 40
        assert c.props.bandwidth == "2mbit"

    def test_loop_false(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("s loop 0\n")
        plan = RawCcpContactPlan.from_file(path)
        assert plan.loop is False

    def test_loop_true(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("s loop 1\n")
        plan = RawCcpContactPlan.from_file(path)
        assert plan.loop is True

    def test_unknown_record_type(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("a foo n1 n2 1mbit 0 0 0\n")
        with pytest.raises(ValueError) as exc_info:
            RawCcpContactPlan.from_file(path)
        assert "line 1" in str(exc_info.value)

    def test_malformed_line_with_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("# comment\n\ns loop 1\n\na contact 0 10 n1 n2 1mbit\n")
        with pytest.raises(ValueError) as exc_info:
            RawCcpContactPlan.from_file(path)
        msg = str(exc_info.value)
        assert "line 5" in msg
        assert "a contact 0 10 n1 n2 1mbit" in msg

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("")
        plan = RawCcpContactPlan.from_file(path)
        assert plan.contacts == []
        assert plan.fixed_contacts == []
        assert plan.loop is False

    def test_comment_only_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.ccp"
        path.write_text("# just a comment\n# another one\n")
        plan = RawCcpContactPlan.from_file(path)
        assert plan.contacts == []
        assert plan.fixed_contacts == []
        assert plan.loop is False


# ===================================================================
# _resolve_node
# ===================================================================
class TestResolveNode:
    def test_by_name(self, sample_nodes: dict[str, Node]) -> None:
        assert _resolve_node("n1", sample_nodes) is sample_nodes["n1"]

    def test_by_id(self, sample_nodes: dict[str, Node]) -> None:
        assert _resolve_node("1", sample_nodes) is sample_nodes["n1"]

    def test_unknown_node(self, sample_nodes: dict[str, Node]) -> None:
        with pytest.raises(ValueError, match="Could not resolve node"):
            _resolve_node("nope", sample_nodes)


# ===================================================================
# _resolve_destination
# ===================================================================
class TestResolveDestination:
    def test_single_shared_net(self, multi_net_nodes: dict[str, Node]) -> None:
        n1 = multi_net_nodes["n1"]
        dst, net = _resolve_destination(n1, "n2", multi_net_nodes)
        assert dst is multi_net_nodes["n2"]
        assert net == "n1_n2"

    def test_no_shared_net(self) -> None:
        # Remove the network they share
        n1 = Node(
            "n1", "1", "ipn:1.0", interfaces={"netA": NetworkInterface("10.0.0.1")}
        )
        n2 = Node(
            "n2", "2", "ipn:2.0", interfaces={"netB": NetworkInterface("10.0.0.2")}
        )
        nodes = {"n1": n1, "n2": n2}
        with pytest.raises(ValueError, match="No shared network"):
            _resolve_destination(n1, "n2", nodes)

    def test_multiple_shared_nets(self) -> None:
        n1 = Node(
            "n1",
            "1",
            "ipn:1.0",
            interfaces={
                "netA": NetworkInterface("10.0.0.1"),
                "netB": NetworkInterface("10.0.1.1"),
            },
        )
        n2 = Node(
            "n2",
            "2",
            "ipn:2.0",
            interfaces={
                "netA": NetworkInterface("10.0.0.2"),
                "netB": NetworkInterface("10.0.1.2"),
            },
        )
        nodes = {"n1": n1, "n2": n2}
        with pytest.raises(ValueError, match="Ambiguous: multiple networks"):
            _resolve_destination(n1, "n2", nodes)

    def test_dev_syntax(self, multi_net_nodes: dict[str, Node]) -> None:
        n1 = multi_net_nodes["n1"]
        # n1 has interface with dev="n1_n2_0" on network "n1_n2"
        dst, net = _resolve_destination(n1, "dev:n1_n2", multi_net_nodes)
        assert dst is multi_net_nodes["n2"]
        assert net == "n1_n2"

    def test_dev_no_matching_interface(self, multi_net_nodes: dict[str, Node]) -> None:
        n1 = multi_net_nodes["n1"]
        with pytest.raises(ValueError, match="No interface"):
            _resolve_destination(n1, "dev:nope", multi_net_nodes)

    def test_dev_ambiguous_multiple_peers(
        self,
    ) -> None:
        # Put n1, n2, n3 all on a "shared" network
        n1 = Node(
            "n1",
            "1",
            "ipn:1.0",
            interfaces={"shared": NetworkInterface("10.0.0.1", "shared_0")},
        )
        n2 = Node(
            "n2",
            "2",
            "ipn:2.0",
            interfaces={"shared": NetworkInterface("10.0.0.2", "shared_0")},
        )
        n3 = Node(
            "n3",
            "3",
            "ipn:3.0",
            interfaces={"shared": NetworkInterface("10.0.0.3", "shared_0")},
        )
        nodes = {"n1": n1, "n2": n2, "n3": n3}
        with pytest.raises(ValueError, match="Ambiguous: multiple peers on network"):
            _resolve_destination(n1, "dev:shared", nodes)


# ===================================================================
# _resolve_contacts / ContactPlan.from_ccp_file
# ===================================================================
class TestResolveContacts:
    def test_asymmetric_contact_one_directed(
        self, multi_net_nodes: dict[str, Node]
    ) -> None:
        raw = [
            RawCcpContact(
                "n1", "n2", 10, 20, LinkProperties("1mbit", 0, 0, 0), symmetric=False
            ),
        ]

        contacts = _resolve_contacts(raw, multi_net_nodes)
        assert len(contacts) == 1
        c = contacts[0]
        assert c.src is multi_net_nodes["n1"]
        assert c.dst is multi_net_nodes["n2"]
        assert c.network == "n1_n2"
        assert c.begin == 10
        assert c.end == 20

    def test_symmetric_contact_two_directed(
        self, multi_net_nodes: dict[str, Node]
    ) -> None:
        raw = [
            RawCcpContact(
                "n1", "n2", 10, 20, LinkProperties("1mbit", 0, 0, 0), symmetric=True
            ),
        ]

        contacts = _resolve_contacts(raw, multi_net_nodes)
        assert len(contacts) == 2
        src_set = {c.src for c in contacts}
        dst_set = {c.dst for c in contacts}
        assert src_set == {multi_net_nodes["n1"], multi_net_nodes["n2"]}
        assert dst_set == {multi_net_nodes["n2"], multi_net_nodes["n1"]}
        for c in contacts:
            assert c.network == "n1_n2"

    def test_props_match_raw(self, multi_net_nodes: dict[str, Node]) -> None:
        props = LinkProperties("5mbit", 1.5, 30.0, 2.5)
        raw = [RawCcpContact("n1", "n2", 0, 100, props, symmetric=False)]

        contacts = _resolve_contacts(raw, multi_net_nodes)
        assert contacts[0].props == props

    def test_from_ccp_file_merges_fixed_and_contacts(
        self, multi_net_nodes: dict[str, Node], tmp_path: Path
    ) -> None:
        ccp = """s loop 0
a fixed n1 n2 1mbit 0 0 0
a contact 10 20 n2 n3 2mbit 0 5 0
"""
        path = tmp_path / "test.ccp"
        path.write_text(ccp)
        plan = ContactPlan.from_ccp_file(path, multi_net_nodes)
        # 1 fixed + 1 contact = 2 raw, but fixed n1→n2 + contact n2→n3 = 2 resolved
        assert len(plan.contacts) == 2
        # Both should be INACTIVE initially
        assert all(s == ContactState.INACTIVE for s in plan.contacts.values())

    def test_from_ccp_file_carries_loop(
        self, multi_net_nodes: dict[str, Node], tmp_path: Path
    ) -> None:
        ccp = "s loop 1\na fixed n1 n2 1mbit 0 0 0\n"
        path = tmp_path / "test.ccp"
        path.write_text(ccp)
        plan = ContactPlan.from_ccp_file(path, multi_net_nodes)
        assert plan.loop is True


# ===================================================================
# Contact.is_active
# ===================================================================
class TestContactIsActive:
    def _make_contact(self, begin: int, end: int) -> Contact:
        return Contact(
            src=Node("s", "1", "ipn:1.0"),
            dst=Node("d", "2", "ipn:2.0"),
            network="net",
            begin=begin,
            end=end,
            props=LinkProperties("1mbit", 0, 0, 0),
        )

    def test_active_during_interval(self) -> None:
        c = self._make_contact(10, 20)
        assert c.is_active(10) is True
        assert c.is_active(15) is True
        assert c.is_active(19) is True

    def test_inactive_before_and_after(self) -> None:
        c = self._make_contact(10, 20)
        assert c.is_active(9) is False
        assert c.is_active(20) is False

    def test_fixed_always_active(self) -> None:
        c = self._make_contact(0, -1)
        assert c.is_active(0) is True
        assert c.is_active(100) is True
        assert c.is_active(1000000) is True
