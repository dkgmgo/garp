import sys

import pytest

from garp import cli

nx = pytest.importorskip("networkx")


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / "g.graphml"
    G = nx.karate_club_graph()
    G.graph.clear()
    nx.write_graphml(G, path)
    return path


def test_missing_fricci_returns_1(graph, tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "fricci", None)
    assert cli.main(["ricci", str(graph), "-o", str(tmp_path / "out.graphml")]) == 1
    assert "fricci is not installed" in capsys.readouterr().err


def test_flow_options_need_flow(graph):
    pytest.importorskip("fricci")
    with pytest.raises(SystemExit, match="--core, --tol: needs --flow N"):
        cli.main(["ricci", str(graph), "--core", "2", "--tol", "none"])


def test_bad_surgery_eps_is_argparse_error(graph):
    with pytest.raises(SystemExit) as e:
        cli.main(["ricci", str(graph), "--flow", "2", "--surgery-eps", "bad"])
    assert e.value.code == 2


def test_curvature_matches_fricci(graph, tmp_path):
    fricci = pytest.importorskip("fricci")
    out = tmp_path / "out.graphml.xz"
    assert cli.main(["gomu", str(graph), "-o", str(out)]) == 0
    import lzma
    with lzma.open(out) as f:
        H = nx.read_graphml(f)
    ref = fricci.ollivier_ricci_curvature(nx.read_graphml(graph))
    assert all(abs(H.edges[e]["curv"] - ref.edges[e]["curv"]) < 1e-12 for e in ref.edges())
    assert all("ot" in d for _, _, d in H.edges(data=True))


def test_flow_writes_flow_attributes(graph, tmp_path):
    pytest.importorskip("fricci")
    out = tmp_path / "out.graphml"
    assert cli.main(["ricci", str(graph), "-o", str(out), "--flow", "3", "--model", "LLY", "--tol", "none"]) == 0
    F = nx.read_graphml(out)
    assert F.graph["iterations"] == 3
    attrs = set(next(iter(F.edges(data=True)))[2])
    assert {"distance", "curv", "ot", "ocurv", "oot", "pdistance"} <= attrs


def assert_same_flow(path, graph, steps):
    """The file at `path` reads back as the networkx flow of `graph` after `steps` steps."""
    fricci = pytest.importorskip("fricci")
    got = nx.read_graphml(path)
    expected = fricci.discrete_ricci_flow(nx.read_graphml(graph), steps)
    assert dict(got.nodes(data=True)) == dict(expected.nodes(data=True))
    assert {frozenset(e): d for *e, d in got.edges(data=True)} == {frozenset(e): d for *e, d in expected.edges(data=True)}
    assert got.graph["iterations"] == steps


def test_every_snapshots_match_networkx_flow(graph, tmp_path):
    pytest.importorskip("fricci")
    out = tmp_path / "out"
    out.mkdir()
    assert cli.main(["ricci", str(graph), "-o", str(out), "--flow", "6", "--every", "2"]) == 0
    snaps = sorted((out / "g").iterdir())
    assert [p.name for p in snaps] == ["g.2.graphml", "g.4.graphml", "g.6.graphml"]
    for p in snaps:
        assert_same_flow(p, graph, int(p.name.split(".")[1]))
    assert_same_flow(out / "g.graphml", graph, 6)


def test_every_needs_output_and_positive_step(graph):
    pytest.importorskip("fricci")
    with pytest.raises(SystemExit, match="--every needs -o"):
        cli.main(["ricci", str(graph), "--flow", "2", "--every", "1"])
    with pytest.raises(SystemExit, match="at least 1 step"):
        cli.main(["ricci", str(graph), "--flow", "2", "--every", "0"])
    with pytest.raises(SystemExit, match="--every: needs --flow N"):
        cli.main(["ricci", str(graph), "--every", "2"])


def test_stem():
    from pathlib import Path

    from garp.tools.ricci import stem
    assert stem(Path("processed_graphdumps1199167200.1199170800.graphml")) == "processed_graphdumps1199167200.1199170800"
    assert stem(Path("world.graphml.gz")) == "world"
    assert stem(Path("world.xml")) == "world.xml"


@pytest.mark.parametrize("flow", [[], ["--flow", "2"]])
def test_output_attribute_as_weight_rejected_early(graph, flow, monkeypatch):
    fricci = pytest.importorskip("fricci")
    monkeypatch.setattr(fricci, "discrete_ricci_flow", lambda *a, **k: pytest.fail("flow ran"))
    with pytest.raises(SystemExit, match="--weight curv: fricci writes this attribute"):
        cli.main(["ricci", str(graph), "--weight", "curv", *flow])


def test_flow_warns_on_disconnected_graph(tmp_path, capsys):
    pytest.importorskip("fricci")
    path = tmp_path / "two.graphml"
    G = nx.disjoint_union(nx.karate_club_graph(), nx.path_graph(3))
    G.graph.clear()
    nx.write_graphml(G, path)
    assert cli.main(["ricci", str(path), "-o", str(tmp_path / "out.graphml"), "--flow", "2"]) == 0
    assert "disconnected graph, 2 components (nodes: 34, 3)" in capsys.readouterr().err
