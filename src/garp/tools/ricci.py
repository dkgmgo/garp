"""Ollivier-Ricci curvature of the edges of a GraphML, or its discrete Ricci flow (needs fricci).

Without --flow: adds `curv` (curvature) and `ot` (transport cost) to every edge.
With --flow N: runs up to N flow steps and writes the resulting graph. Edges get
`distance`, `curv`, `ot` (after the flow), `ocurv`, `oot` (before), `pdistance`,
`pcurv`, `pot` (previous step); nodes merged by surgery are named "a|b". See
the fricci documentation for the models and their presets.
With --every K: also saves the graph every K steps, in a directory named after
the input next to the output: <out dir>/<input name>/<input name>.<step>.graphml

Needs the fricci library in the same Python environment as garp.

example:
  garp ricci world.graphml -o world_curv.graphml
  garp ricci world.graphml -o processed_world.graphml --flow 40 --model LLY
  garp ricci graphs/ --glob '*.graphml' -o flowed/ --flow 20 --model GRC --core 2 --threads 8
  garp ricci world.graphml -o flowed/ --flow 40 --every 10
"""
from __future__ import annotations

import argparse
import logging

from garp.common.io import OPENERS, add_input, add_output, iter_jobs, open_binary

ALIAS = "gomu-gomu"  # Like Luffy's rubber, the flow stretches and shrinks edges' distances

log = logging.getLogger(__name__)

# Flow presets apply unless overridden; "--tol none" (None) differs from no --tol at all.
FLOW_SETTINGS = ("step", "surgery_eps", "tol")
# Edge attributes fricci writes; --weight must not be one, except "distance" (restart from saved flow)
FRICCI_OUTPUTS = ("distance", "curv", "ot", "ocurv", "oot", "pdistance", "pcurv", "pot")


def float_or_none(value):
    if value.lower() == "none":
        return None
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number or 'none', got '{value}'")


def add_arguments(parser):
    add_input(parser)
    add_output(parser)
    parser.add_argument("--flow", type=int, metavar="N", help="run the Ricci flow for up to N steps (default: curvature only)")
    parser.add_argument("--model", choices=("LLY", "GRC"), default="LLY", help="curvature and flow preset Lin-Lu-Yau vs GraphRicciCurvature (default: %(default)s)")
    parser.add_argument("--weight", default="weight", help="edge attribute with the input weights, 1 when missing (default: %(default)s)")
    parser.add_argument("--threads", type=int, help="OpenMP threads (default: all cores)")
    flow = parser.add_argument_group("flow options (with --flow)")
    flow.add_argument("--core", type=int, metavar="K", help="keep only the K-core before the flow")
    flow.add_argument(
        "--every", type=int, metavar="K",
        help="also save the graph every K steps, in <out dir>/<input name>/<input name>.<step>.graphml",
    )
    flow.add_argument("--step", type=float, default=argparse.SUPPRESS, help="override the preset step")
    flow.add_argument(
        "--surgery-eps", type=float_or_none, default=argparse.SUPPRESS,
        help="contract edges shorter than this; 'none' disables surgery",
    )
    flow.add_argument(
        "--tol", type=float_or_none, default=argparse.SUPPRESS,
        help="early stop when max - min curvature < tol; 'none' disables",
    )


def stem(path):
    """world.graphml.gz -> world (dots inside the name are kept)."""
    name = path.name.removesuffix(path.suffix) if path.suffix in OPENERS else path.name
    return name.removesuffix(".graphml")


def to_simple_undirected(G, nx, src):
    if G.is_directed():
        log.warning("%s: directed graph, edge directions dropped", src)
        G = G.to_undirected()
    if G.is_multigraph():
        log.warning("%s: parallel edges merged (attributes of one of them kept)", src)
        G = nx.Graph(G)
    return G


def run(args):
    try:
        import fricci
    except ImportError:
        log.error("fricci is not installed in this Python environment; install it first")
        return 1
    import networkx as nx

    if args.weight in FRICCI_OUTPUTS and args.weight != "distance":
        raise SystemExit(f"--weight {args.weight}: fricci writes this attribute; keep the input weights under another name")
    flow_settings = {k: getattr(args, k) for k in FLOW_SETTINGS if hasattr(args, k)}
    if args.flow is None:
        given = [f"--{k}" for k in ("core", "every") if getattr(args, k) is not None]
        given += [f"--{k.replace('_', '-')}" for k in flow_settings]
        if given:
            raise SystemExit(f"{', '.join(given)}: needs --flow N")
    elif args.flow < 1:
        raise SystemExit("--flow needs at least 1 step")
    elif args.every is not None and args.every < 1:
        raise SystemExit("--every needs at least 1 step")
    overrides = {"n_threads": args.threads} if args.threads else {}

    for src, dst in iter_jobs(args):
        with open_binary(src) as f:
            G = to_simple_undirected(nx.read_graphml(f), nx, src)
        log.info("%s: %d nodes, %d edges", src, G.number_of_nodes(), G.number_of_edges())

        # curvature only
        if args.flow is None:
            H = fricci.ollivier_ricci_curvature(G, model=args.model, weight=args.weight, **overrides)
            log_curvature(src, [c for _, _, c in H.edges(data="curv")])
            with open_binary(dst, "w") as out:
                nx.write_graphml(H, out)
            continue

        # The flow runs on CSRGraph; the networkx graph is built only for the steps written.
        g = fricci.CSRGraph.from_networkx(G, weight=args.weight)
        callback = None
        if args.every:
            if dst is None:
                raise SystemExit("--every needs -o/--output (snapshots go next to it)")
            snap_dir = dst.parent / stem(src)
            snap_dir.mkdir(parents=True, exist_ok=True)

            def callback(state, G=G, g=g, src=src, snap_dir=snap_dir):
                if state.iterations % args.every == 0:
                    write_graphml(nx, fricci.flow_graph(G, g, state, args.weight), snap_dir / f"{stem(src)}.{state.iterations}.graphml")
                    log.debug("%s: snapshot at step %d", src, state.iterations)

        r = fricci.discrete_ricci_flow(
            g, args.flow, model=(args.model, args.model), core=args.core,
            callback=callback, **flow_settings, **overrides,
        )
        log.info("%s: %d steps, %d nodes, %d edges after the flow", src, r.iterations, r.graph.n_nodes, r.graph.n_edges)
        log_curvature(src, r.kappa.tolist())
        write_graphml(nx, fricci.flow_graph(G, g, r, args.weight), dst)
    return 0


def write_graphml(nx, H, path):
    # TODO: nx.write_graphml is most of the time spent per snapshot. A custom writer rendering
    # GraphML straight from fricci's arrays was ~20x faster.
    with open_binary(path, "w") as out:
        nx.write_graphml(H, out)


def log_curvature(src, curv):
    if curv:
        log.info("%s: curvature min %.4f, mean %.4f, max %.4f", src, min(curv), sum(curv) / len(curv), max(curv))
