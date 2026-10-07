"""SHACL ingest gate: the one sanctioned path for writing ABox batches into the store.

A batch is Turtle destined for one named graph. It is written only if

1. the target graph is named as ``07-ontology-topology.md`` prescribes
   (``urn:graph:ingest:{agent}:{date}``, ``urn:graph:derived:entity-resolution:{date}``,
   ``urn:graph:derived:quant:{date}``,
   ``urn:graph:universe:{year}-Q{n}``, or ``urn:graph:portfolio:current``); the TBox,
   reference and rule-catalog graphs are loaded by ``cli/load_schema.py``;
2. the graph is new, for the append-only ones (an ingest graph is never edited after
   creation; only ``portfolio:current`` is mutated in place);
3. every IRI is absolute, and every ``rdf:type`` is one of the leaf classes of the
   ontology (the ``owl:AllDisjointClasses`` members). A typo such as ``:ScoreSnapshott``,
   or an individual typed only as an abstract category, would otherwise match no shape
   and be accepted unchecked;
4. a subject with no ``rdf:type`` in the batch, which no shape can see, is only given
   relations to other individuals (object properties, e.g. ``:hasScoreObservation``,
   ``:supersededBy``; the object must be an IRI) or an ``xsd:date`` ``:validTo`` (closing a
   record). Anything else would let a batch quietly add values to an existing, immutable
   observation;
5. it conforms to ``shapes.ttl`` under ``pyshacl``; and
6. no typed individual in it already exists in the store (any graph, explicit statements):
   a batch only introduces new individuals, so an immutable observation cannot be
   re-declared with a second value.

Anything else raises :class:`IngestRejected` with the reason and nothing reaches the
store. What is written is the validated triples (as N-Triples), not the submitted text.
Shapes target by class and never reference other individuals, so a batch is validated
on its own, without the data already in the store.

Validation uses ``tbox.ttl``/``shapes.ttl`` from ``schema/`` on disk, the versioned
source, read once per process. ``cli/load_schema.py`` is what brings the store's copy
in line; reload after a schema edit.

Limit: this is a code path, not a server-side lock. A client holding the GraphDB
write credentials can still write around it; run ingestion through this module.
"""

from __future__ import annotations

import datetime
import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pyshacl
import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from kg_store.graphdb import GraphDB, schema_dir

_PORTFOLIO = rdflib.Namespace("https://thesis.local/kg/portfolio#")
#: The one datatype property allowed on a subject untyped in the batch (closing a record).
CLOSING_PROPERTY = _PORTFOLIO.validTo

MUTABLE_GRAPHS = ("urn:graph:portfolio:current",)
_DATE = r"\d{4}-\d{2}-\d{2}"
_QUARTER = r"\d{4}-Q[1-4]"
#: Append-only graph names (``07``): agents write a dated graph; FUNDAMENTAL writes per
#: quarter; EDGAR and entity resolution take a date or a quarter; universes are quarterly.
APPEND_ONLY_PATTERNS = (
    re.compile(
        rf"urn:graph:ingest:(SEMANTIC|VALORIZATION|TECHNICAL|SECTOR|ORCHESTRATOR):({_DATE})"
    ),
    re.compile(rf"urn:graph:ingest:FUNDAMENTAL:({_QUARTER})"),
    re.compile(rf"urn:graph:ingest:EDGAR:({_DATE}|{_QUARTER})"),
    re.compile(rf"urn:graph:derived:entity-resolution:({_DATE}|{_QUARTER})"),
    re.compile(rf"urn:graph:derived:quant:({_DATE})"),
    re.compile(rf"urn:graph:universe:({_QUARTER})"),
)

#: Base IRI given to the parser so that relative IRIs can be recognised and refused.
_RELATIVE_BASE = "http://relative.invalid/"


class IngestRejected(RuntimeError):
    """The batch was refused; the message says why. Nothing was written."""


class ShaclRejected(IngestRejected):
    """The batch failed ``shapes.ttl``; ``results`` is pyshacl's results graph.

    Callers that need to know *what* failed read the ``sh:ValidationResult`` nodes (focus node,
    path, constraint component) from ``results`` instead of matching the wording of the text
    report in the message, which belongs to pyshacl and may change between versions.
    """

    def __init__(self, report: str, results: rdflib.Graph) -> None:
        super().__init__("SHACL validation failed:\n" + report)
        self.results = results


def check_target(graph: str) -> bool:
    """Validate the target graph name; return True if it is append-only."""
    if graph in MUTABLE_GRAPHS:
        return False
    for pattern in APPEND_ONLY_PATTERNS:
        m = pattern.fullmatch(graph)
        if m:
            if not _date_ok(m.group(m.lastindex or 0)):
                raise IngestRejected(f"{graph} has an impossible date")
            return True
    raise IngestRejected(
        f"{graph} is not an ingest target. Allowed: urn:graph:ingest:"
        "{SEMANTIC|VALORIZATION|TECHNICAL|SECTOR|ORCHESTRATOR}:YYYY-MM-DD, "
        "urn:graph:ingest:FUNDAMENTAL:YYYY-Qn, urn:graph:ingest:EDGAR:{date|quarter}, "
        "urn:graph:derived:entity-resolution:{date|quarter}, urn:graph:derived:quant:YYYY-MM-DD, "
        "urn:graph:universe:YYYY-Qn, "
        f"{', '.join(MUTABLE_GRAPHS)}"
    )


def _date_ok(text: str) -> bool:
    """True for a quarter label or a real calendar date."""
    if "Q" in text:
        return True
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def parse_batch(data: bytes, fmt: str = "turtle") -> rdflib.Graph:
    g = rdflib.Graph()
    try:
        g.parse(data=data, format=fmt, publicID=_RELATIVE_BASE)
    except Exception as exc:  # rdflib raises a different parser error per syntax
        raise IngestRejected(f"cannot parse batch as {fmt}: {exc}") from exc
    if not len(g):
        raise IngestRejected("batch is empty")
    relative = {str(t) for t in {x for tr in g for x in tr} if str(t).startswith(_RELATIVE_BASE)}
    if relative:
        raise IngestRejected("relative IRIs are not allowed: " + ", ".join(sorted(relative)))
    return g


@dataclass(frozen=True)
class GateSchema:
    """What the gate needs from ``tbox.ttl``/``shapes.ttl``, read once."""

    tbox: rdflib.Graph
    shapes: rdflib.Graph
    leaf_classes: frozenset[rdflib.term.Node]
    relations: frozenset[rdflib.term.Node]


@functools.cache
def load_gate_schema(directory: Path) -> GateSchema:
    tbox = rdflib.Graph().parse(directory / "tbox.ttl", format="turtle")
    shapes = rdflib.Graph().parse(directory / "shapes.ttl", format="turtle")
    leaves: set[rdflib.term.Node] = set()
    for decl in tbox.subjects(RDF.type, OWL.AllDisjointClasses):
        for members in tbox.objects(decl, OWL.members):
            leaves.update(Collection(tbox, members))
    return GateSchema(
        tbox,
        shapes,
        frozenset(leaves),
        frozenset(tbox.subjects(RDF.type, OWL.ObjectProperty)),
    )


def unknown_types(batch: rdflib.Graph, schema: GateSchema) -> set[str]:
    """``rdf:type`` objects in the batch that are not leaf classes of the ontology."""
    return {str(t) for t in set(batch.objects(None, RDF.type)) if t not in schema.leaf_classes}


def untyped_writes(batch: rdflib.Graph, schema: GateSchema) -> list[str]:
    """Triples about a subject with no ``rdf:type`` here, other than relations or closing."""
    typed = set(batch.subjects(RDF.type, None))
    nm = batch.namespace_manager
    problems: list[str] = []
    for s, p, o in batch:
        if s in typed:
            continue
        if p in schema.relations:
            if isinstance(o, rdflib.Literal):
                problems.append(
                    f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} (a relation needs an individual, not a literal)"
                )
        elif p == CLOSING_PROPERTY:
            if not (isinstance(o, rdflib.Literal) and o.datatype == XSD.date and _date_ok(str(o))):
                problems.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} (must be an xsd:date literal)")
        else:
            problems.append(f"{s.n3(nm)} {p.n3(nm)}")
    return sorted(problems)


def with_superclass_types(batch: rdflib.Graph, schema: GateSchema) -> rdflib.Graph:
    """Copy of ``batch`` where each typed individual also has its superclasses' types.

    SHACL targets a class's subclass instances only if the subclass triples are in the data
    graph; the batch carries no TBox, so add just those (no domain/range inference, which
    could target individuals the batch never typed).
    """
    expanded = rdflib.Graph()
    expanded += batch
    for s, t in set(batch.subject_objects(RDF.type)):
        for sup in schema.tbox.transitive_objects(t, RDFS.subClassOf):
            if sup is not None:
                expanded.add((s, RDF.type, sup))
    return expanded


def validate(batch: rdflib.Graph, directory: Path | None = None) -> None:
    """Raise :class:`IngestRejected` unless ``batch`` passes the type, untyped-subject and shape checks.

    A shape failure raises :class:`ShaclRejected`, which carries the results graph.
    """
    schema = load_gate_schema((directory or schema_dir()).resolve())
    unknown = unknown_types(batch, schema)
    if unknown:
        raise IngestRejected(
            "types that are not leaf classes of the ontology: " + ", ".join(sorted(unknown))
        )
    stray = untyped_writes(batch, schema)
    if stray:
        raise IngestRejected(
            "triples about a subject with no rdf:type in the batch (only relations between "
            "individuals and an xsd:date :validTo are allowed there): " + ", ".join(stray)
        )
    conforms, results, report = pyshacl.validate(
        with_superclass_types(batch, schema), shacl_graph=schema.shapes, inference="none"
    )
    if not conforms:
        # pyshacl returns the results as a Graph unless asked for another serialization.
        raise ShaclRejected(str(report), cast(rdflib.Graph, results))


def existing_subjects(db: GraphDB, batch: rdflib.Graph) -> list[str]:
    """Typed IRI subjects of ``batch`` that already have statements in the store."""
    iris = sorted({str(s) for s in batch.subjects(RDF.type, None) if isinstance(s, rdflib.URIRef)})
    bad = [iri for iri in iris if re.search(r'[\s<>"{}|^`\\]', iri)]
    if bad:
        raise IngestRejected("IRIs with characters that are illegal in an IRI: " + ", ".join(bad))
    found: list[str] = []
    for i in range(0, len(iris), 200):
        values = " ".join(f"<{iri}>" for iri in iris[i : i + 200])
        rows = db.select(
            "SELECT DISTINCT ?s FROM <http://www.ontotext.com/explicit> "  # noqa: S608 - IRIs checked above
            f"WHERE {{ VALUES ?s {{ {values} }} ?s ?p ?o }}"
        )
        found.extend(r["s"] for r in rows)
    return found


def ingest(db: GraphDB, data: bytes, graph: str, directory: Path | None = None) -> int:
    """Validate a Turtle batch and, only if it passes, append it to ``graph``. Returns triples written."""
    append_only = check_target(graph)
    batch = parse_batch(data)
    validate(batch, directory)
    if append_only and db.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"):
        raise IngestRejected(f"{graph} already exists and is append-only; write a new dated graph")
    taken = existing_subjects(db, batch)
    if taken:
        raise IngestRejected(
            "individuals that already exist in the store (observations are immutable; use a "
            "new IRI, or :validTo to close one): " + ", ".join(taken)
        )
    db.add(batch.serialize(format="nt").encode(), "application/n-triples", graph)
    return len(batch)
