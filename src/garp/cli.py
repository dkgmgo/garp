import os
import ast
import sys
import difflib
import logging
import argparse
import importlib
from pathlib import Path

from garp import __version__
from garp.common.log import setup_logging

TOOLS_DIR = Path(__file__).parent / "tools"
TOOLS_PKG = "garp.tools"


def discover() -> dict[str, Path]:
    return {
        p.stem.replace("_", "-"): p
        for p in sorted(TOOLS_DIR.glob("*.py"))
        if not p.stem.startswith("_") and p.stem.isidentifier()
    }


def summary(path: Path):
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    except SyntaxError as e:
        return f"<syntax error: {e.msg}, line {e.lineno}>"
    except UnicodeDecodeError:
        return "<not valid utf-8>"
    return doc.strip().splitlines()[0] if doc else ""


def print_tool_list(tools: dict[str, Path]) -> None:
    width = max((len(n) for n in tools), default=0)
    print(f"garp {__version__}\n\nusage: garp <tool_name> [params]   (garp <tool_name> -h for details)\n\ntools:")
    for name, path in tools.items():
        print(f"  {name:<{width}}  {summary(path)}")


def load(name: str):
    module = importlib.import_module(f"{TOOLS_PKG}.{name.replace('-', '_')}")
    for attr in ("add_arguments", "run"):
        if not callable(getattr(module, attr, None)):
            raise SystemExit(f"tool '{name}' is broken: missing function {attr}()")
    return module


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    tools = discover()

    if not argv or argv[0] in ("-h", "--help", "list"):
        print_tool_list(tools)
        return 0
    if argv[0] in ("-V", "--version"):
        print(__version__)
        return 0

    name = argv[0].replace("_", "-")
    if name not in tools:
        hint = difflib.get_close_matches(name, tools, n=1)
        msg = f"unknown tool '{argv[0]}'" + (f" — did you mean '{hint[0]}'?" if hint else "")
        print(msg, file=sys.stderr)
        return 2

    try:
        module = load(name)
    except Exception:
        setup_logging()
        logging.getLogger(name).exception("tool failed to load")
        return 1
    doc = (module.__doc__ or "").strip()
    parser = argparse.ArgumentParser(
        prog=f"garp {name}",
        description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Options shared by every tool, defined once here. Tools must not reuse -v/-q.
    shared = parser.add_mutually_exclusive_group()
    shared.add_argument("-v", "--verbose", action="count", default=0, help="-v info, -vv debug")
    shared.add_argument("-q", "--quiet", action="store_true", help="errors only")
    module.add_arguments(parser)

    args = parser.parse_args(argv[1:])
    setup_logging(args.verbose, args.quiet)
    try:
        return int(module.run(args) or 0)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    except Exception:
        logging.getLogger(name).exception("tool failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())