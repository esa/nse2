import importlib.util
import sys
from pathlib import Path


def _load(name):
    path = Path(__file__).parents[1] / "tools" / "helpers" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(module):
    return [
        module.ParsedRow("a", "b", 0, -1, 1000, 0.1, "high"),
        module.ParsedRow("a", "b", 0, -1, 2000, 0.2, "hi"),
    ]


def test_compose_disambiguates_shortened_label_collision(tmp_path):
    module = _load("csv_to_compose.py")
    csv_path = tmp_path / "contacts.csv"
    csv_path.write_text(
        "src,dst,start,end,bw,delay,label\n"
        "a,b,0,-1,1000,0.1,high\n"
        "a,b,0,-1,2000,0.2,hi\n"
    )
    graph = module.get_graph_from_csv(str(csv_path), {})
    assert graph.number_of_edges() == 2
    assert {data["label"] for *_, data in graph.edges(data=True)} == {"high", "hi"}


def test_ccp_disambiguates_shortened_label_collision():
    module = _load("csv_to_ccp.py")
    rows = _rows(module)
    fixed, _ = module.convert_rows(
        [(row, False) for row in rows], module.compute_multi_pairs(rows)
    )
    destinations = {row[1] for row in fixed}
    assert destinations == {"dev:a_b_high", "dev:a_b_hi"}
