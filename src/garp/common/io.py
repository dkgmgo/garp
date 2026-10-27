"""Input/output helpers shared by tools.

Input is a file or a directory (top-level files matching --glob).
Output mirrors the input: a file (or stdout when -o is omitted), or a
directory receiving one output file per input file, same name.
Files ending in .gz, .bz2 or .xz are (de)compressed transparently.
"""
from __future__ import annotations

import argparse
import bz2
import contextlib
import gzip
import lzma
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

OPENERS = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}


def _existing_path(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"no such file or directory: {value}")
    return path


def add_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=_existing_path, help="input file or directory")
    parser.add_argument(
        "--glob", default="*", help="file pattern when input is a directory (default: %(default)s)"
    )


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-o", "--output", type=Path, help="output file or directory (default: stdout, file input only)"
    )


def iter_jobs(args: argparse.Namespace, rename: Callable[[str], str] | None = None, many: bool = False) -> Iterator[tuple[Path, Path | None]]:
    """Yield (input_file, output_file) pairs. output_file is None for stdout.

    rename(input_name) -> output_name applies whenever the output name is
    derived from the input name (output is a directory). An explicit
    `-o FILE` is always kept as typed.

    many=True is for tools writing several files per input: -o must be a
    directory (created if missing), and output_file is a base path inside it,
    never None. Write next to it with names derived from it, e.g.
    `dst.parent / f"{part}_{dst.name}"`.
    """
    src, dst = args.input, args.output
    name = rename or (lambda n: n)
    if many:
        if dst is None or (dst.exists() and not dst.is_dir()):
            raise SystemExit("-o/--output must be a directory (several output files per input)")
        dst.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        if dst is not None and dst.is_dir():
            dst = dst / name(src.name)
        yield src, dst
        return

    if dst is None:
        raise SystemExit("directory input needs -o/--output DIR")
    if dst.exists() and not dst.is_dir():
        raise SystemExit(f"output '{dst}' is a file, expected a directory")
    if dst.resolve() == src.resolve():
        raise SystemExit("output directory must differ from input directory")

    files = sorted(p for p in src.glob(args.glob) if p.is_file())
    if not files:
        raise SystemExit(f"no files matching '{args.glob}' in {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for path in files:
        yield path, dst / name(path.name)

#TODO for later: another helper that does many to one and another one for many folders


def open_text(path: Path | None, mode: str = "r") -> contextlib.AbstractContextManager[IO[str]]:
    """Open a text file, decompressing by extension. None means stdin/stdout."""
    if path is None:
        return contextlib.nullcontext(sys.stdout if "w" in mode or "a" in mode else sys.stdin)
    if "w" in mode or "a" in mode:
        path.parent.mkdir(parents=True, exist_ok=True)
    opener = OPENERS.get(path.suffix, open)
    return opener(path, mode.replace("t", "") + "t", encoding="utf-8")


def open_binary(path: Path | None, mode: str = "r") -> contextlib.AbstractContextManager[IO[bytes]]:
    """Same as open_text, in bytes (for libraries writing bytes, e.g. networkx.write_graphml)."""
    if path is None:
        return contextlib.nullcontext((sys.stdout if "w" in mode or "a" in mode else sys.stdin).buffer)
    if "w" in mode or "a" in mode:
        path.parent.mkdir(parents=True, exist_ok=True)
    opener = OPENERS.get(path.suffix, open)
    return opener(path, mode.replace("b", "") + "b")


def iter_lines(path: Path | None) -> Iterator[str]:
    """Yield lines without their trailing newline."""
    with open_text(path) as f:
        for line in f:
            yield line.rstrip("\r\n")
