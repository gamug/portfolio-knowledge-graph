"""Load ``schema/`` into the GraphDB repository, then verify it landed intact.

Each Turtle file goes wholesale into the graph named in ``schema/README.md``'s
file-to-graph table; ``instances.trig`` is self-describing. The load order is
``tbox -> shapes -> reference -> rules -> instances``. Re-running is safe: every
target graph is dropped first, so the result is the same as a load into a fresh
repository, and edits to ``schema/`` replace rather than accumulate.

The drops and uploads run in one transaction: if anything fails, nothing changes.

Verification parses the same files with ``rdflib`` and compares the asserted triple
count of every graph this loader owns (those in ``schema/``) against what GraphDB
reports (inferred statements excluded). Other graphs in the repository, such as
ingest graphs written later, are reported but never dropped or treated as errors. A
graph removed from ``schema/`` is likewise left in place; drop it by hand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import rdflib

from kg_store.graphdb import GraphDB, GraphDBError, schema_dir

#: (file, graph) in load order; ``None`` marks a TriG file that names its own graphs.
LOAD_PLAN: list[tuple[str, str | None]] = [
    ("tbox.ttl", "urn:graph:tbox"),
    ("shapes.ttl", "urn:graph:tbox"),
    ("reference.ttl", "urn:graph:reference"),
    ("rules.ttl", "urn:graph:rules:catalog"),
    ("instances.trig", None),
]


class SchemaError(RuntimeError):
    """The schema files cannot be loaded as they stand (unreadable, unparsable, ill-formed)."""


def expected_sizes(directory: Path) -> dict[str, int]:
    """Triples per named graph that a correct load must produce (parsed locally)."""
    ds = rdflib.Dataset(default_union=False)
    for name, graph in LOAD_PLAN:
        try:
            if graph is None:
                ds.parse(directory / name, format="trig")
            else:
                ds.graph(rdflib.URIRef(graph)).parse(directory / name, format="turtle")
        except OSError as exc:
            raise SchemaError(f"cannot read {directory / name}: {exc}") from exc
        except Exception as exc:  # rdflib raises a different parser error per syntax
            raise SchemaError(f"cannot parse {name}: {exc}") from exc
    if len(ds.default_context):
        raise SchemaError(
            "instances.trig has triples outside a GRAPH block; every triple must name its graph"
        )
    return {str(g.identifier): len(g) for g in ds.graphs() if len(g)}


def load(db: GraphDB, directory: Path) -> dict[str, int]:
    expected = expected_sizes(directory)
    with db.transaction() as txn:
        for graph in expected:
            txn.update(f"DROP SILENT GRAPH <{graph}>")
        for name, target in LOAD_PLAN:
            data = (directory / name).read_bytes()
            txn.add(data, "application/x-trig" if target is None else "text/turtle", target)
            print(f"loaded {name}" + (f" -> {target}" if target else ""))
    return expected


def verify(db: GraphDB, expected: dict[str, int]) -> tuple[list[str], list[str]]:
    """Compare the graphs this loader owns; also list the store's other graphs.

    Returns ``(problems, others)``: one message per owned graph whose asserted size
    differs from ``expected``, and the names of graphs in the store that are not
    in ``schema/`` (informational only).
    """
    actual = db.explicit_graph_sizes()
    problems = [
        f"{g}: expected {n}, store has {actual.get(g, 0)}"
        for g, n in expected.items()
        if actual.get(g, 0) != n
    ]
    return problems, sorted(g for g in actual if g not in expected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="schema directory (default: KG_SCHEMA_DIR or <repo>/schema)",
    )
    args = parser.parse_args(argv)
    directory = args.dir or schema_dir()
    try:
        db = GraphDB.from_env()
        expected = load(db, directory)
        problems, others = verify(db, expected)
    except (GraphDBError, SchemaError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    total = sum(expected.values())
    if problems:
        print("verification FAILED:", *problems, sep="\n  ", file=sys.stderr)
        return 1
    print(f"verified: {len(expected)} graphs, {total} asserted triples match the local parse")
    if others:
        print(f"note: {len(others)} other graph(s) in the store were left untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
