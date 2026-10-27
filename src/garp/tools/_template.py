"""One-line summary shown by `garp --help`.

Longer description, shown by `garp my-tool -h`.
Copy this file to `my_tool.py` and it becomes `garp my-tool`.

example:
  garp my-tool input.txt -o out.txt
  garp my-tool data/ --glob '*.graphml' -o clean/
"""
from __future__ import annotations

import logging

from garp.common.io import add_input, add_output, iter_jobs, iter_lines, open_text

log = logging.getLogger(__name__)


def add_arguments(parser):
    add_input(parser)
    add_output(parser)
    # parser.add_argument("--threshold", type=float, default=0.5, help="...")


def processed(name):
    """Output file name from input file name: input.txt -> input_processed.txt."""
    stem, _, ext = name.partition(".")
    return f"{stem}_processed.{ext}" if ext else f"{stem}_processed"


def run(args):
    # Put heavy imports (networkx, pandas, numpy...) inside run() so they
    # never slow down the other tools or `garp --help`.
    # Optional: rename=processed gives out_dir/input_processed.txt instead of
    # out_dir/input.txt. Applies only when -o is a directory.
    for src, dst in iter_jobs(args):  # iter_jobs(args, rename=processed)
        n = 0
        with open_text(dst, "w") as out:
            for line in iter_lines(src):
                out.write(line + "\n")
                n += 1
        log.info("%s: %d lines processed", src, n)
    return 0  # non-zero = failure exit code
