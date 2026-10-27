# GARP: Graph Artifacts Raw Preparation

garp is a preprocessing tool made to smash, shape and clean graph data before it gets into an analysis pipeline.

## Install

Requires Python 3.10+.

```bash
pip install . # core
pip install -e ".[dev]" # editable, + pytest
```

Without installing: `python -m garp ...` (from `src/`, or with `PYTHONPATH=src`).

## Usage

```bash
garp # list tools
garp <tool> -h # tool help
garp <tool> input.txt # file -> stdout
garp <tool> input.txt -o out.txt # file -> file
garp <tool> data/ --glob '*.edges' -o clean/ # directory -> directory (same file names)
```

- Directory input is not recursive; `--glob` filters top-level files (default `*`).
- `.gz`, `.bz2`, `.xz` files are read and written compressed, based on their extension.
- Every tool takes `-v` (info), `-vv` (debug) or `-q` (errors only).

## Adding a tool

Copy `src/garp/tools/_template.py` to `src/garp/tools/my_tool.py`. It becomes `garp my-tool`; no registration needed.

A tool module defines:

- a docstring: first line is shown in `garp`, the whole thing in `garp my-tool -h`
- `add_arguments(parser)`: add options (do not reuse `-v`/`-q`)
- `run(args)`: do the work, return an exit code (0 = success)

Shared I/O helpers live in `garp.common.io`. Keep heavy imports inside `run()`.

## Tests

```bash
pytest
```
