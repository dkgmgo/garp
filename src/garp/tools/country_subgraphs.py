"""Split a world AS-level BGP graph (GraphML) into one subgraph per country.

A country's subgraph keeps all its ASes, even isolated, and the edges with both endpoints in that country.
With --cross-border it also keeps the edges going outside, and the foreign ASes they reach.

Output goes to a directory, one file per (input, country). The name is the
input name with "processed" replaced by the country code, or prefixed with
"<CC>_" when it has no "processed":
  processed_graphdumps1199167200.1199170800.graphml
    -> FR_graphdumps1199167200.1199170800.graphml

Node ids are rewritten as n0..n(k-1); the old id is kept in a new
"originalId" node attribute (disable with --no-renumber).

example:
  garp country-subgraphs world.graphml -o countries/
  garp country-subgraphs Archive3/ --glob 'processed_*.graphml' -o All_Countries/
  garp country-subgraphs world.graphml.gz -o countries/ --countries FR DE US
  garp country-subgraphs world.graphml -o countries/ --cross-border
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import defaultdict

from garp.common.io import add_input, add_output, iter_jobs, open_text

ALIAS = "bara"  # Buggy's chop-chop fruit cut the world in pieces

log = logging.getLogger(__name__)

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"
ORIGINAL_ID_KEY = "key_original_id"


def qn(tag):
    return f"{{{GRAPHML_NS}}}{tag}"


def add_arguments(parser):
    add_input(parser)
    add_output(parser)
    parser.add_argument(
        "--attr-name", default="Country", help="node attribute holding the country (default: %(default)s)"
    )
    parser.add_argument(
        "--countries", nargs="+", metavar="CC", help="only extract these countries, e.g. --countries FR DE (default: all)"
    )
    parser.add_argument(
        "--case-insensitive", action="store_true", help="treat 'fr' and 'FR' as the same country"
    )
    parser.add_argument(
        "--cross-border", action="store_true", help="also keep links to other countries, and the foreign nodes they reach"
    )
    parser.add_argument("--no-renumber", action="store_true", help="keep original node ids")


def country_filename(name, country):
    country = country.replace("/", "_")
    if "processed" in name:
        return name.replace("processed", country, 1)
    return f"{country}_{name}"


def find_key_id(root, attr_name):
    """Id of the node <key> named attr_name. Exact name wins over a case-insensitive match."""
    keys = [k for k in root.findall(qn("key")) if k.get("for") == "node"]
    for k in keys:
        if k.get("attr.name") == attr_name:
            return k.get("id")
    for k in keys:
        if k.get("attr.name", "").lower() == attr_name.lower():
            return k.get("id")
    return None


def node_value(node, key_id):
    for data in node.iter(qn("data")):
        if data.get("key") == key_id:
            return (data.text or "").strip()
    return ""


def build_subgraph(root, graph, nodes, edges, renumber):
    """New GraphML root holding `nodes` and `edges`. The source tree is not modified."""
    sub = ET.Element(root.tag, root.attrib)
    for child in root:
        if child is graph:
            if renumber:
                ET.SubElement(
                    sub, qn("key"),
                    {"id": ORIGINAL_ID_KEY, "for": "node", "attr.name": "originalId", "attr.type": "string"},
                )
            break
        sub.append(child)  # <key> elements are shared, not copied
    sub_graph = ET.SubElement(sub, graph.tag, graph.attrib)

    id_map = {}
    for i, node in enumerate(nodes):
        old_id = node.get("id")
        new_id = f"n{i}" if renumber else old_id
        id_map[old_id] = new_id
        new = ET.SubElement(sub_graph, node.tag, {**node.attrib, "id": new_id})
        new.extend(node)
        if renumber:
            ET.SubElement(new, qn("data"), {"key": ORIGINAL_ID_KEY}).text = old_id

    for edge in edges:
        new = ET.SubElement(
            sub_graph, edge.tag,
            {**edge.attrib, "source": id_map[edge.get("source")], "target": id_map[edge.get("target")]},
        )
        new.extend(edge)

    ET.indent(sub, space="  ")
    return ET.ElementTree(sub)


def run(args):
    ET.register_namespace("", GRAPHML_NS)
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    norm = str.upper if args.case_insensitive else str
    wanted = {norm(c) for c in args.countries} if args.countries else None

    for src, dst in iter_jobs(args, many=True):  # dst: base path, one file per country next to it
        log.info("%s: parsing", src)
        with open_text(src) as f:
            root = ET.parse(f).getroot()
        graph = root.find(qn("graph"))
        if graph is None:
            raise SystemExit(f"{src}: no <graph> element")
        key_id = find_key_id(root, args.attr_name)
        if key_id is None:
            raise SystemExit(f"{src}: no node attribute named '{args.attr_name}' (see --attr-name)")

        nodes = graph.findall(qn("node"))
        position = {n.get("id"): i for i, n in enumerate(nodes)}
        country_of = {n.get("id"): norm(node_value(n, key_id)) for n in nodes}

        # An edge belongs to the country of each endpoint (1 or 2 countries);
        # one between 2 countries is dropped unless --cross-border.
        edges_of = defaultdict(list)
        nodes_of = defaultdict(set)
        for edge in graph.iter(qn("edge")):
            countries = {country_of.get(edge.get("source")), country_of.get(edge.get("target"))}
            if len(countries) > 1 and not args.cross_border:
                continue
            for c in countries:
                if c and (wanted is None or c in wanted):
                    edges_of[c].append(edge)
                    nodes_of[c].update((edge.get("source"), edge.get("target")))
        for n, c in country_of.items():  # the country's own nodes, even isolated
            if c and (wanted is None or c in wanted):
                nodes_of[c].add(n)

        if wanted:
            for c in sorted(wanted - nodes_of.keys()):
                log.warning("%s: no nodes kept for country '%s', nothing written", src, c)
        log.info("%s: %d nodes, %d countries to write", src, len(nodes), len(nodes_of))

        for country in sorted(nodes_of):
            edges = edges_of[country]
            kept = nodes_of[country]
            sub_nodes = [nodes[i] for i in sorted(position[n] for n in kept)]
            n_local = sum(1 for n in kept if country_of[n] == country)

            out_path = dst.parent / country_filename(dst.name, country)
            tree = build_subgraph(root, graph, sub_nodes, edges, renumber=not args.no_renumber)
            with open_text(out_path, "w") as out:
                out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(out, encoding="unicode")
                out.write("\n")
            log.debug(
                "%s: %d nodes in country, %d foreign, %d edges -> %s",
                country, n_local, len(kept) - n_local, len(edges), out_path,
            )
    return 0
