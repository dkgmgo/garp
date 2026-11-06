import gzip
import xml.etree.ElementTree as ET

import pytest

from garp import cli
from garp.tools.country_subgraphs import country_filename

NS = "{http://graphml.graphdrawing.org/xmlns}"

WORLD = """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="key0" for="node" attr.name="Country" attr.type="string" />
  <key id="key1" for="edge" attr.name="weight" attr.type="int" />
  <graph id="G" edgedefault="undirected">
    <node id="n0"><data key="key0">FR</data></node>
    <node id="n1"><data key="key0">FR</data></node>
    <node id="n2"><data key="key0">DE</data></node>
    <node id="n3"><data key="key0">US</data></node>
    <node id="n4"><data key="key0">FR</data></node>
    <node id="n5"><data key="key0">fr</data></node>
    <edge id="e0" source="n0" target="n1"><data key="key1">1</data></edge>
    <edge id="e1" source="n1" target="n2"><data key="key1">2</data></edge>
    <edge id="e2" source="n2" target="n3"><data key="key1">3</data></edge>
    <edge id="e3" source="n3" target="n5"><data key="key1">4</data></edge>
  </graph>
</graphml>
"""


@pytest.fixture
def world(tmp_path):
    path = tmp_path / "processed_world.graphml"
    path.write_text(WORLD)
    return path


def read(path):
    graph = ET.parse(path).getroot().find(NS + "graph")
    nodes = {n.get("id"): {d.get("key"): d.text for d in n} for n in graph.findall(NS + "node")}
    edges = [(e.get("id"), e.get("source"), e.get("target")) for e in graph.findall(NS + "edge")]
    return nodes, edges


def test_one_file_per_country(world, tmp_path):
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(world), "-o", str(out), "--cross-border"]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "DE_world.graphml", "FR_world.graphml", "US_world.graphml", "fr_world.graphml",
    ]


def test_default_keeps_only_links_inside_the_country(world, tmp_path):
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(world), "-o", str(out)]) == 0
    # n4 has no edges at all; e1 to DE is dropped, n2 with it.
    nodes, edges = read(out / "FR_world.graphml")
    assert [d["key_original_id"] for d in nodes.values()] == ["n0", "n1", "n4"]
    assert [e[0] for e in edges] == ["e0"]


def test_default_writes_country_without_inner_links(world, tmp_path):
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "DE"]) == 0
    nodes, edges = read(out / "DE_world.graphml")
    assert [d["key_original_id"] for d in nodes.values()] == ["n2"]
    assert edges == []


def test_warns_when_country_is_absent(world, tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "XX"]) == 0
    assert not out.exists() or not list(out.iterdir())
    assert "no nodes kept for country 'XX'" in capsys.readouterr().err


def test_keeps_cross_border_edges_and_renumbers(world, tmp_path):
    out = tmp_path / "out"
    cli.main(["country-subgraphs", str(world), "-o", str(out), "--cross-border"])
    nodes, edges = read(out / "FR_world.graphml")
    # n0, n1, n4 (no edges) in FR; n2 (DE) kept via e1.
    assert [d["key_original_id"] for d in nodes.values()] == ["n0", "n1", "n2", "n4"]
    assert list(nodes) == ["n0", "n1", "n2", "n3"]
    assert [e[0] for e in edges] == ["e0", "e1"]


def test_renumber_maps_edges(world, tmp_path):
    out = tmp_path / "out"
    cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "US", "--cross-border"])
    nodes, edges = read(out / "US_world.graphml")
    orig = {nid: d["key_original_id"] for nid, d in nodes.items()}
    assert list(nodes) == ["n0", "n1", "n2"]
    assert [(e, orig[s], orig[t]) for e, s, t in edges] == [("e2", "n2", "n3"), ("e3", "n3", "n5")]


def test_no_renumber_keeps_ids(world, tmp_path):
    out = tmp_path / "out"
    cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "US", "--no-renumber", "--cross-border"])
    nodes, _ = read(out / "US_world.graphml")
    assert list(nodes) == ["n2", "n3", "n5"]
    assert all("key_original_id" not in d for d in nodes.values())


def test_case_insensitive_merges(world, tmp_path):
    out = tmp_path / "out"
    cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "fr", "--case-insensitive", "--cross-border"])
    assert [p.name for p in out.iterdir()] == ["FR_world.graphml"]
    nodes, _ = read(out / "FR_world.graphml")
    assert [d["key_original_id"] for d in nodes.values()] == ["n0", "n1", "n2", "n3", "n4", "n5"]


def test_gzip_in_and_out(world, tmp_path):
    gz = tmp_path / "processed_world.graphml.gz"
    with gzip.open(gz, "wt") as f:
        f.write(WORLD)
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(gz), "-o", str(out), "--countries", "DE", "--cross-border"]) == 0
    with gzip.open(out / "DE_world.graphml.gz") as f:
        nodes, _ = read(f)
    assert len(nodes) == 3


def test_output_must_be_directory(world, tmp_path):
    with pytest.raises(SystemExit, match="must be a directory"):
        cli.main(["country-subgraphs", str(world)])


def test_countries_takes_a_list(world, tmp_path):
    out = tmp_path / "out"
    assert cli.main(["country-subgraphs", str(world), "-o", str(out), "--countries", "DE", "US", "--cross-border"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["DE_world.graphml", "US_world.graphml"]
