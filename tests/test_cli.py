import gzip

import pytest

from garp import __version__, cli


def test_list_shows_tools_and_summary(tools_dir, capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "echo" in out
    assert "One-line summary" in out


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_unknown_tool_suggests_close_match(tools_dir, capsys):
    assert cli.main(["ecko"]) == 2
    assert "did you mean 'echo'" in capsys.readouterr().err


def test_non_importable_file_names_are_hidden(tools_dir):
    (tools_dir / "bad-name.py").write_text('"""x"""\n')
    (tools_dir / "_private.py").write_text('"""x"""\n')
    assert list(cli.discover()) == ["echo"]


def test_broken_tool_returns_1(tools_dir):
    (tools_dir / "broken.py").write_text('"""Broken."""\nimport nonexistent_mod_xyz\n')
    assert cli.main(["broken"]) == 1


def test_tool_missing_run_exits(tools_dir):
    (tools_dir / "norun.py").write_text('"""No run."""\ndef add_arguments(p): pass\n')
    with pytest.raises(SystemExit, match="missing function run"):
        cli.main(["norun"])


def test_verbose_and_quiet_conflict(tools_dir, tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x\n")
    with pytest.raises(SystemExit) as e:
        cli.main(["echo", str(src), "-v", "-q"])
    assert e.value.code == 2


def test_template_file_to_stdout(tools_dir, tmp_path, capsys):
    src = tmp_path / "a.txt"
    src.write_text("1 2\n2 3\n")
    assert cli.main(["echo", str(src)]) == 0
    assert capsys.readouterr().out == "1 2\n2 3\n"


def test_template_directory_mirrors_with_glob(tools_dir, tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    (data / "a.edges").write_text("1 2\n")
    with gzip.open(data / "b.edges.gz", "wt") as f:
        f.write("3 4\n")
    (data / "skip.txt").write_text("nope\n")
    (data / "sub").mkdir()
    (data / "sub" / "c.edges").write_text("deep\n")

    assert cli.main(["echo", str(data), "--glob", "*.edges*", "-o", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["a.edges", "b.edges.gz"]
    assert (out / "a.edges").read_text() == "1 2\n"
    with gzip.open(out / "b.edges.gz", "rt") as f:
        assert f.read() == "3 4\n"
