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
   ``:supersededBy``; the object must be an IRI) or an ``xsd:date`` ``:validTo`` or
   ``:clearedOn`` (closing a record or a Veto stint). Anything else would let a batch quietly
   add values to an existing, immutable observation;
5. it conforms to ``shapes.ttl`` under ``pyshacl``, together with what the store holds about
   the individuals it points at (``references``/``fetch_context``, T-146): a batch of
   co-occurrences or quant numbers names Assets and Portfolios it does not declare, and the
   shapes check their class and (for a Portfolio) its kind. A reference the store does not hold
   fails the class check; and
6. no typed individual in it already exists in the store (any graph, explicit statements):
   a batch only introduces new individuals, so an immutable observation cannot be
   re-declared with a second value; and
7. every closing triple (point 4) closes a stored individual of a class that is closed by that
   property (``CLOSABLE``: ``validTo``: a membership, position, rule or design-history weight
   scheme; ``clearedOn``: a Veto) which is not closed yet, on a date after it opened (and, for a
   Veto, not before the latest ``lastSeenOn``, T-185), and closes it once (T-180). Read, then written, not atomic: see the limit below.

Anything else raises :class:`IngestRejected` with the reason and nothing reaches the
store. What is written is the validated triples (as N-Triples), not the submitted text.
Shapes target by class; a batch is validated with the stored triples of the individuals it
references (and nothing else of the store), so it need not repeat them.

Validation uses ``tbox.ttl``/``shapes.ttl`` from ``schema/`` on disk, the versioned
source, read once per process. ``cli/load_schema.py`` is what brings the store's copy
in line; reload after a schema edit.

Limit: this is a code path, not a server-side lock: two batches closing the same record, or
declaring the same individual, can both pass checks 6 and 7 before either is written. A client
holding the GraphDB write credentials can still write around it; run ingestion through this module.
"""

from __future__ import annotations

import datetime
import functools
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, cast

import pyshacl
import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from kg_store.graphdb import AnswerLost, GraphDB, GraphDBError, schema_dir

_PORTFOLIO = rdflib.Namespace("https://thesis.local/kg/portfolio#")
#: The datatype properties allowed on a subject untyped in the batch: closing a valid-time
#: record (``validTo``) or a Veto stint (``clearedOn``), both an ``xsd:date``.
CLOSING_PROPERTIES = frozenset({_PORTFOLIO.validTo, _PORTFOLIO.clearedOn})

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


class WriteInDoubt(GraphDBError):
    """The batch was sent but the store's answer was lost: it may have been appended. Any other
    ``GraphDBError`` from :func:`ingest` (a check before sending, an HTTP error) means it was not."""


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


def _calendar_date(text: str) -> datetime.date | None:
    """The date of a strict ``YYYY-MM-DD`` text, else None (``fromisoformat`` alone also takes
    ``20260101`` and ``2026-W01-1``, which are no ``xsd:date``)."""
    if not re.fullmatch(_DATE, text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


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
        elif p in CLOSING_PROPERTIES:
            if not isinstance(s, rdflib.URIRef):
                problems.append(
                    f"{s.n3(nm)} {p.n3(nm)} (a closure needs the IRI of a stored record)"
                )
            elif not (
                isinstance(o, rdflib.Literal) and o.datatype == XSD.date and _calendar_date(str(o))
            ):
                problems.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} (must be an xsd:date literal)")
        else:
            problems.append(f"{s.n3(nm)} {p.n3(nm)}")
    return sorted(problems)


def closing_values(batch: rdflib.Graph) -> dict[tuple[rdflib.term.Node, rdflib.URIRef], list[str]]:
    """The closing triples about subjects with no ``rdf:type`` in the batch: (subject, property) ->
    the dates written."""
    typed = set(batch.subjects(RDF.type, None))
    closing: dict[tuple[rdflib.term.Node, rdflib.URIRef], list[str]] = {}
    for s, p, o in batch:
        if s not in typed and isinstance(s, rdflib.URIRef) and p in CLOSING_PROPERTIES:
            closing.setdefault((s, cast(rdflib.URIRef, p)), []).append(str(o))
    return closing


#: Per closing property: the classes whose records it closes and the property holding the date the
#: record opened (the closing date must be later: the shapes' ``sh:lessThan``, which the stored
#: record is never validated against here). Explicit, not read from the shapes: a class is closable
#: because its design says so (``07``), and ``PortfolioPositionShape`` does not mention ``validTo``.
class Closable(NamedTuple):
    """What a closing property closes: the classes, the property holding the date they opened, and
    (if any) the multi-valued property whose latest date the closing date may not precede."""

    classes: frozenset[rdflib.URIRef]
    opened: rdflib.URIRef
    last_seen: rdflib.URIRef | None = None


CLOSABLE: Mapping[rdflib.URIRef, Closable] = MappingProxyType(
    {
        _PORTFOLIO.validTo: Closable(
            frozenset(
                {
                    _PORTFOLIO.UniverseMembership,
                    _PORTFOLIO.PortfolioPosition,
                    _PORTFOLIO.RuleDefinition,
                    _PORTFOLIO.AttractivenessWeightScheme,
                }
            ),
            _PORTFOLIO.validFrom,
        ),
        # A cycle that still saw the stint raised (``lastSeenOn``, one per cycle) is not undone by a
        # later clearing dated before it (T-185).
        _PORTFOLIO.clearedOn: Closable(
            frozenset({_PORTFOLIO.Veto}), _PORTFOLIO.raisedOn, _PORTFOLIO.lastSeenOn
        ),
    }
)
#: A per-run weight scheme (it has a ``cycleDate``) is an observation, never closed (``tbox.ttl``).
_PER_RUN_MARKER = _PORTFOLIO.cycleDate


#: subject IRI -> {property: lexical values the store holds}, as :func:`fetch_closing_state` reads it.
ClosingState = dict[str, dict[rdflib.URIRef, set[str]]]


def fetch_closing_state(db: GraphDB, subjects: set[rdflib.term.Node]) -> ClosingState:
    """What the store holds (explicit statements, any graph) about ``subjects`` that decides whether
    they can be closed: subject -> {property: lexical values} for ``rdf:type``, the closing
    properties, the opening dates and ``cycleDate``."""
    iris = sorted(str(s) for s in subjects)
    _refuse_illegal_iris(iris)
    read = {
        rdflib.URIRef(RDF.type),
        _PER_RUN_MARKER,
        *CLOSING_PROPERTIES,
        *(c.opened for c in CLOSABLE.values()),
        *(c.last_seen for c in CLOSABLE.values() if c.last_seen),
    }
    state: ClosingState = {}
    for i in range(0, len(iris), 200):
        values = " ".join(f"<{iri}>" for iri in iris[i : i + 200])
        rows = db.select(
            "SELECT ?s ?p ?o FROM <http://www.ontotext.com/explicit> "  # noqa: S608 - IRIs checked above
            f"WHERE {{ VALUES ?s {{ {values} }} VALUES ?p {{ {_iri_list(read)} }} ?s ?p ?o }}"
        )
        for row in rows:
            p = rdflib.URIRef(row.get("p", ""))
            if {"s", "o"} <= row.keys() and p in read:
                state.setdefault(row["s"], {}).setdefault(p, set()).add(row["o"])
    return state


def _date_order(closes_on: str, began: set[str], opened: rdflib.URIRef) -> str | None:
    """Why a closing date is refused against the stored opening date(s), or None."""
    if len(began) > 1:
        name = opened.rpartition("#")[2]
        return f"the store holds {len(began)} values for {name}, so not when it opened"
    if not began:
        return None
    closes, opens = _calendar_date(closes_on), _calendar_date(next(iter(began)))
    if opens is None or closes is None:
        return f"{closes_on} cannot be compared with the stored {next(iter(began))}"
    return f"{closes_on} is not after the date it opened on, {opens}" if closes <= opens else None


def _refusal(p: rdflib.URIRef, dates: list[str], held: dict[rdflib.URIRef, set[str]]) -> str | None:
    """Why the closing of one stored subject by ``p`` is refused, or None."""
    classes, opened, last_seen = CLOSABLE[p]
    types = {rdflib.URIRef(t) for t in held.get(rdflib.URIRef(RDF.type), set())}
    if len(dates) > 1:
        return f"is given {len(dates)} dates in the batch"
    if not types:
        return "the store does not hold it"
    if not types & classes or held.get(_PER_RUN_MARKER):
        return f"it is not a record that {p.rpartition('#')[2]} closes"
    if held.get(p):
        was = sorted(held[p])[0]
        retry = (
            ": the same date, so perhaps this batch was already written" if was == dates[0] else ""
        )
        return f"it is already closed ({was}{retry})"
    return _date_order(dates[0], held.get(opened, set()), opened) or (
        _before_last_seen(dates[0], held.get(last_seen, set())) if last_seen else None
    )


def _before_last_seen(closes_on: str, seen: set[str]) -> str | None:
    """Why a closing date is refused against the latest date a cycle saw the record, or None."""
    if not seen:
        return None
    dates = [_calendar_date(text) for text in seen]
    closes = _calendar_date(closes_on)
    if closes is None or None in dates:
        return f"{closes_on} cannot be compared with the stored last seen dates"
    latest = max(cast(list[datetime.date], dates))
    return (
        f"{closes_on} is before the latest date a cycle saw it, {latest}"
        if closes < latest
        else None
    )


def refused_closures(batch: rdflib.Graph, state: ClosingState) -> list[str]:
    """Closing triples that do not close a stored, still open record, on a date after it opened, or
    that give one subject two dates."""
    nm = batch.namespace_manager
    problems: list[str] = []
    for (s, p), dates in sorted(
        closing_values(batch).items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        if why := _refusal(p, dates, state.get(str(s), {})):
            problems.append(f"{s.n3(nm)} {p.n3(nm)}: {why}")
    return problems


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


def _refuse_illegal_iris(iris: list[str]) -> None:
    """IRIs go into a SPARQL ``VALUES`` list, so refuse any with a character that could end it."""
    bad = [iri for iri in iris if re.search(r'[\s<>"{}|^`\\]', iri)]
    if bad:
        raise IngestRejected("IRIs with characters that are illegal in an IRI: " + ", ".join(bad))


def references(batch: rdflib.Graph, schema: GateSchema) -> set[rdflib.URIRef]:
    """IRIs the batch points at by an object property but does not type itself."""
    typed = set(batch.subjects(RDF.type, None))
    return {
        o
        for _, p, o in batch
        if p in schema.relations and isinstance(o, rdflib.URIRef) and o not in typed
    }


def _paths_below(shapes: rdflib.Graph, starts: list[rdflib.term.Node]) -> set[rdflib.URIRef]:
    """Every ``sh:path`` IRI reachable from ``starts`` through a shape's own blank nodes (property
    shapes, ``sh:or`` lists) and ``sh:node`` links."""
    sh = rdflib.namespace.SH
    paths: set[rdflib.URIRef] = set()
    seen: set[rdflib.term.Node] = set()
    todo = list(starts)
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for _, p, o in shapes.triples((node, None, None)):
            if p == sh.path and isinstance(o, rdflib.URIRef):
                paths.add(o)
            elif isinstance(o, rdflib.BNode) or p == sh.node:
                todo.append(o)
    return paths


def context_predicates(
    batch: rdflib.Graph, refs: set[rdflib.URIRef], schema: GateSchema
) -> set[rdflib.URIRef]:
    """The properties of ``refs`` that a shape reads: ``rdf:type`` and the ``sh:path``s of the shapes
    that target the class required where the batch points at a reference (the ``sh:class`` of the
    relation it uses), or a subclass of it.

    A referenced Asset also has a link per snapshot per day and more; none of them is read, so
    none is fetched (the context would otherwise grow with the store's history). A relation with no
    ``sh:class`` requires nothing of its target, so only ``rdf:type`` is fetched for it.
    """
    sh = rdflib.namespace.SH
    used = {p for _, p, o in batch if o in refs}
    classes: set[rdflib.term.Node] = set()
    for prop in schema.shapes.subjects(sh.path, None):
        if schema.shapes.value(prop, sh.path) in used:
            classes.update(schema.shapes.objects(prop, sh["class"]))
    wanted = {sub for c in classes for sub in schema.tbox.transitive_subjects(RDFS.subClassOf, c)}
    targets = [
        shape
        for shape in schema.shapes.subjects(sh.targetClass, None)
        if wanted & set(schema.shapes.objects(shape, sh.targetClass))
    ]
    return {rdflib.URIRef(RDF.type)} | _paths_below(schema.shapes, targets)


def nested_paths(schema: GateSchema, relation: rdflib.URIRef) -> set[rdflib.URIRef]:
    """The properties a shape reads on the individuals reached through ``relation`` (its
    ``sh:node``): for ``hasUniverseMembership``, the ``validTo`` of the Asset's CIK-or-closed rule."""
    sh = rdflib.namespace.SH
    starts = [
        node
        for prop in schema.shapes.subjects(sh.path, relation)
        for node in schema.shapes.objects(prop, sh.node)
    ]
    return _paths_below(schema.shapes, starts)


def fetch_context(
    db: GraphDB, refs: set[rdflib.URIRef], schema: GateSchema, batch: rdflib.Graph
) -> rdflib.Graph:
    """What the store holds (explicit statements, any graph) about ``refs``, as a graph.

    Only the properties the shapes read for what ``batch`` expects of ``refs`` are fetched
    (:func:`context_predicates`, and :func:`nested_paths` one step further when a shape reads
    through a relation, as the Asset shape does through its memberships).

    Each value keeps the term type and datatype the store holds it with (T-181), so where a shape
    constrains a property's datatype or values (``sh:datatype``, ``sh:in``, ``sh:hasValue``) a
    stored literal of another datatype fails it, instead of passing as the declared one. A string
    is a plain literal, as in the batches. A subject or predicate that is not an IRI raises
    :class:`GraphDBError`.
    """
    iris = sorted(str(r) for r in refs)
    _refuse_illegal_iris(iris)
    paths = context_predicates(batch, refs, schema)
    restrict = f"VALUES ?p {{ {_iri_list(paths)} }} "
    hops: dict[rdflib.URIRef, set[rdflib.URIRef]] = {}
    for relation in sorted(paths, key=str):
        if nested := nested_paths(schema, relation):
            hops[relation] = nested
    context = rdflib.Graph()
    for i in range(0, len(iris), 200):
        values = " ".join(f"<{iri}>" for iri in iris[i : i + 200])
        hop_queries = "".join(
            f" UNION {{ ?r <{relation}> ?s . ?s ?p ?o . VALUES ?p {{ {_iri_list(nested)} }} }}"
            for relation, nested in hops.items()
        )
        rows = db.select_terms(
            "SELECT ?s ?p ?o FROM <http://www.ontotext.com/explicit> "  # noqa: S608 - IRIs checked above
            f"WHERE {{ VALUES ?r {{ {values} }} "
            f"{{ {restrict}?r ?p ?o . BIND(?r AS ?s) }}{hop_queries} }}"
        )
        for row in rows:
            if not {"s", "p", "o"} <= row.keys():
                continue
            s, p = row["s"], row["p"]
            if not (isinstance(s, rdflib.URIRef) and isinstance(p, rdflib.URIRef)):
                raise GraphDBError(
                    f"the store returned a statement ({s.n3()} {p.n3()}) whose subject or predicate "
                    "is not an IRI"
                )
            context.add((s, p, row["o"]))
    return context


def _iri_list(iris: set[rdflib.URIRef]) -> str:
    return " ".join(f"<{p}>" for p in sorted(iris, key=str))


def validate(
    batch: rdflib.Graph,
    directory: Path | None = None,
    context: rdflib.Graph | Callable[[], rdflib.Graph] | None = None,
) -> None:
    """Raise :class:`IngestRejected` unless ``batch`` passes the checks, run in this order: the types,
    the untyped subjects, then the shapes beside ``context``.

    ``context`` holds what is already known about the individuals the batch points at
    (:func:`fetch_context`).

    It may be a callable, called once and only after the first two checks pass, so a batch refused
    by them costs no query.

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
            "individuals and an xsd:date :validTo or :clearedOn are allowed there): "
            + ", ".join(stray)
        )
    if callable(context):
        context = context()
    data = batch
    if context is not None and len(context):
        data = rdflib.Graph()
        data += batch
        data += context
    conforms, results, report = pyshacl.validate(
        with_superclass_types(data, schema), shacl_graph=schema.shapes, inference="none"
    )
    if not conforms:
        # pyshacl returns the results as a Graph unless asked for another serialization.
        raise ShaclRejected(str(report), cast(rdflib.Graph, results))


def existing_subjects(db: GraphDB, batch: rdflib.Graph) -> list[str]:
    """Typed IRI subjects of ``batch`` that already have statements in the store."""
    iris = sorted({str(s) for s in batch.subjects(RDF.type, None) if isinstance(s, rdflib.URIRef)})
    _refuse_illegal_iris(iris)
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
    """Validate a Turtle batch and, only if it passes, append it to ``graph``. Returns triples written.

    The store is read for the individuals the batch points at, whether the graph exists (append-only
    ones), the closing triples' subjects and the typed individuals it declares, in that order, each
    only after the checks before it passed."""
    append_only = check_target(graph)
    batch = parse_batch(data)
    schema = load_gate_schema((directory or schema_dir()).resolve())
    refs = references(batch, schema)
    # Every store query comes after validate's store-free checks, so a batch they refuse costs none:
    # the context is fetched lazily, and the two checks below it run on a batch that passed.
    validate(batch, directory, (lambda: fetch_context(db, refs, schema, batch)) if refs else None)
    if append_only and db.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"):
        raise IngestRejected(f"{graph} already exists and is append-only; write a new dated graph")
    closing = {s for s, _ in closing_values(batch)}
    if closing:
        stray = refused_closures(batch, fetch_closing_state(db, closing))
        if stray:
            raise IngestRejected(
                "closing triples that do not close a stored, open record (T-180): "
                + "; ".join(stray)
            )
    taken = existing_subjects(db, batch)
    if taken:
        raise IngestRejected(
            "individuals that already exist in the store (observations are immutable; use a "
            "new IRI, or :validTo / :clearedOn to close one): " + ", ".join(taken)
        )
    try:
        db.add(batch.serialize(format="nt").encode(), "application/n-triples", graph)
    except AnswerLost as exc:
        raise WriteInDoubt(str(exc)) from exc
    return len(batch)
