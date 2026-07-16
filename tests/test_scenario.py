"""Smoke tests for scenario loading and compose parsing."""

from __future__ import annotations

from pathlib import Path

from tools.contact_player.scenario import _parse_compose_nodes


def test_parse_compose_nodes_simple_scenario() -> None:
    """Smoke-test _parse_compose_nodes on the real scenarios/simple/compose.yml."""
    repo_root = Path(__file__).parent.parent
    compose_path = repo_root / "scenarios" / "simple" / "compose.yml"

    nodes = _parse_compose_nodes(compose_path)

    assert len(nodes) == 3
    assert set(nodes.keys()) == {"n1", "n2", "n3"}

    n1 = nodes["n1"]
    assert n1.id == "1"
    assert n1.eid == "ipn:1.0"

    n2 = nodes["n2"]
    assert n2.id == "2"
    assert n2.eid == "ipn:2.0"
    assert set(n2.interfaces.keys()) == {"n1_n2", "n2_n3"}
    assert n2.interfaces["n1_n2"].ip == "172.33.0.3"
    assert n2.interfaces["n2_n3"].ip == "172.33.1.2"

    n3 = nodes["n3"]
    assert n3.id == "3"
    assert n3.eid == "ipn:3.0"
    assert n3.interfaces["n2_n3"].ip == "172.33.1.3"
