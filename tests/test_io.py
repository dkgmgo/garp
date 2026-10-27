import argparse
import bz2
import lzma

import pytest

from garp.common.io import add_input, add_output, iter_jobs, iter_lines, open_text


def parse(*argv):
    parser = argparse.ArgumentParser()
    add_input(parser)
    add_output(parser)
    return parser.parse_args([str(a) for a in argv])


def test_missing_input_is_argparse_error(tmp_path):
    with pytest.raises(SystemExit):
        parse(tmp_path / "nope.txt")


@pytest.mark.parametrize("suffix, opener", [(".bz2", bz2.open), (".xz", lzma.open)])
def test_compressed_roundtrip(tmp_path, suffix, opener):
    path = tmp_path / f"a.txt{suffix}"
    with open_text(path, "w") as f:
        f.write("1 2\r\n3 4\n")
    with opener(path, "rt") as f:
        assert f.read().splitlines() == ["1 2", "3 4"]
    assert list(iter_lines(path)) == ["1 2", "3 4"]


def test_file_into_existing_dir(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x\n")
    out = tmp_path / "out"
    out.mkdir()
    assert list(iter_jobs(parse(src, "-o", out))) == [(src, out / "a.txt")]


def test_file_without_output_is_stdout(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x\n")
    assert list(iter_jobs(parse(src))) == [(src, None)]


def test_directory_requires_output(tmp_path):
    with pytest.raises(SystemExit, match="needs -o"):
        list(iter_jobs(parse(tmp_path)))


def test_directory_output_cannot_be_input(tmp_path):
    (tmp_path / "a.txt").write_text("x\n")
    with pytest.raises(SystemExit, match="must differ"):
        list(iter_jobs(parse(tmp_path, "-o", tmp_path)))


def test_directory_output_cannot_be_file(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_text("x\n")
    target = tmp_path / "out.txt"
    target.write_text("")
    with pytest.raises(SystemExit, match="is a file"):
        list(iter_jobs(parse(data, "-o", target)))


def test_directory_no_matches(tmp_path):
    (tmp_path / "a.txt").write_text("x\n")
    with pytest.raises(SystemExit, match="no files matching"):
        list(iter_jobs(parse(tmp_path, "--glob", "*.edges", "-o", tmp_path / "out")))


def tag(name):
    stem, _, ext = name.partition(".")
    return f"{stem}_processed.{ext}"


def test_rename_file_into_dir(tmp_path):
    src = tmp_path / "input.txt"
    src.write_text("x\n")
    out = tmp_path / "out"
    out.mkdir()
    assert list(iter_jobs(parse(src, "-o", out), rename=tag)) == [(src, out / "input_processed.txt")]


def test_rename_directory(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.edges.gz").write_text("")
    (data / "b.txt").write_text("")
    out = tmp_path / "out"
    jobs = list(iter_jobs(parse(data, "-o", out), rename=tag))
    assert [dst.name for _, dst in jobs] == ["a_processed.edges.gz", "b_processed.txt"]


def test_rename_ignored_for_explicit_file_and_stdout(tmp_path):
    src = tmp_path / "input.txt"
    src.write_text("x\n")
    target = tmp_path / "result.txt"
    assert list(iter_jobs(parse(src, "-o", target), rename=tag)) == [(src, target)]
    assert list(iter_jobs(parse(src), rename=tag)) == [(src, None)]
