"""SHACL ingest gate: the one sanctioned path for writing ABox batches into the store.

A batch is Turtle destined for one named graph. It is written only if

1. the target graph is one a batch may be written to (``urn:graph:ingest:*``,
   ``urn:graph:derived:*``, ``urn:graph:universe:*``, ``urn:graph:portfolio:current``);
   the TBox, reference and rule-catalog graphs are loaded by ``cli/load_schema.py``;
2. the graph is new, for the append-only ones (``07-ontology-topology.md``: an ingest graph
   is never edited after creation; only ``portfolio:current`` is mutated in place);
3. every ``rdf:type`` it uses is a class defined in ``tbox.ttl`` (a typo such as
   ``:ScoreSnapshott`` would otherwise match no shape and be accepted unchecked); and
4. it conforms to ``shapes.ttl`` under ``pyshacl``.

Anything else raises :class:`IngestRejected` with the reason and nothing reaches the
store. Shapes target by class and never reference other individuals, so a batch is
validated on its own, without the data already in the store.

Limit: this is a code path, not a server-side lock. A client holding the GraphDB
write credentials can still write around it; run ingestion through this module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pyshacl
import rdflib
from rdflib.namespace import OWL, RDF

from kg_store.graphdb import GraphDB, schema_dir

#: Graph name prefixes a batch may be written to, and whether each is append-only.
APPEND_ONLY_PREFIXES = ("urn:graph:ingest:", "urn:graph:derived:", "urn:graph:universe:")
MUTABLE_GRAPHS = ("urn:graph:portfolio:current",)

#: The graph name is interpolated into SPARQL, so allow only characters legal in an IRI.
_SAFE_IRI = re.compile(r"[A-Za-z0-9:._~/@!$&'()*+,;=%-]+")


class IngestRejected(RuntimeError):
    """The batch was refused; the message says why. Nothing was written."""


def check_target(graph: str) -> bool:
    """Validate the target graph name; return True if it is append-only."""
    if not _SAFE_IRI.fullmatch(graph):
        raise IngestRejected(f"{graph!r} is not a valid graph IRI")
    if graph in MUTABLE_GRAPHS:
        return False
    if graph.startswith(APPEND_ONLY_PREFIXES):
        return True
    raise IngestRejected(
        f"{graph} is not an ingest target; allowed: "
        f"{', '.join(p + '*' for p in APPEND_ONLY_PREFIXES)}, {', '.join(MUTABLE_GRAPHS)}"
    )


def parse_batch(data: bytes, fmt: str = "turtle") -> rdflib.Graph:
    g = rdflib.Graph()
    try:
        g.parse(data=data, format=fmt)
    except Exception as exc:  # rdflib raises a different parser error per syntax
        raise IngestRejected(f"cannot parse batch as {fmt}: {exc}") from exc
    if not len(g):
        raise IngestRejected("batch is empty")
    return g


def unknown_types(batch: rdflib.Graph, tbox: rdflib.Graph) -> set[str]:
    """``rdf:type`` objects in the batch that ``tbox.ttl`` does not define as classes."""
    known = set(tbox.subjects(RDF.type, OWL.Class))
    return {str(t) for t in set(batch.objects(None, RDF.type)) if t not in known}


def validate(batch: rdflib.Graph, directory: Path | None = None) -> None:
    """Raise :class:`IngestRejected` unless ``batch`` passes the type check and the shapes."""
    directory = directory or schema_dir()
    tbox = rdflib.Graph().parse(directory / "tbox.ttl", format="turtle")
    shapes = rdflib.Graph().parse(directory / "shapes.ttl", format="turtle")
    unknown = unknown_types(batch, tbox)
    if unknown:
        raise IngestRejected("types not defined in tbox.ttl: " + ", ".join(sorted(unknown)))
    conforms, _, report = pyshacl.validate(batch, shacl_graph=shapes, inference="none")
    if not conforms:
        raise IngestRejected("SHACL validation failed:\n" + str(report))


def ingest(db: GraphDB, data: bytes, graph: str, directory: Path | None = None) -> int:
    """Validate a Turtle batch and, only if it passes, append it to ``graph``. Returns triples written."""
    append_only = check_target(graph)
    batch = parse_batch(data)
    validate(batch, directory)
    if append_only and db.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"):
        raise IngestRejected(f"{graph} already exists and is append-only; write a new dated graph")
    db.add(data, "text/turtle", graph)
    return len(batch)
