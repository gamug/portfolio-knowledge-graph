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
   ``:clearedOn`` (closing a record or a Veto stint) or ``:lastSeenOn`` (a later cycle saw the
   stint, T-194). Anything else would let a batch quietly add values to an existing, immutable
   observation;
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
   Veto, not before the latest ``lastSeenOn``, T-185), and closes it once (T-180). A
   ``lastSeenOn`` appended to a stored Veto (``APPENDABLE``, T-194) must be a Veto that is not cleared,
   on a date not before it was raised, after its latest ``lastSeenOn`` (an equal date is a replay) and
   not after the ``clearedOn`` the same batch gives it. Read, then written, not atomic: see the limit below; and
8. a restatement (``:supersededBy``, T-032) points from a ``SECFilingSection``, stored or declared,
   to a new ``SECFilingSection`` the same batch declares, with the same ``:itemLabel`` when both have
   one: a section gets one replacement, a new section replaces one section, a section does not
   replace itself, no chain in the batch loops, and a stored section already superseded is not
   superseded again (the next correction replaces the latest section). So the restatements of an
   item form one chain and its current section is its one section not superseded. The batch alone
   decides all but the stored side (``validate``, so ``--check`` too); ``ingest`` reads the rest.

Anything else raises :class:`IngestRejected` with the reason and nothing reaches the
store. What is written is the validated triples (as N-Triples), not the submitted text.
Shapes target by class; a batch is validated with the stored triples of the individuals it
references (and nothing else of the store), so it need not repeat them.

Validation uses ``tbox.ttl``/``shapes.ttl`` from ``schema/`` on disk, the versioned
source, read once per process. ``cli/load_schema.py`` is what brings the store's copy
in line; reload after a schema edit.

Limit: this is a code path, not a server-side lock: two batches closing the same record, or
declaring the same individual, can both pass checks 6 and 7 before either is written; so can two batches
restating the same stored section (check 8), leaving it with two ``:supersededBy`` values, which the
functional property forbids and nothing at the read boundary catches; so can a sighting
and the clearing of the same Veto, leaving a ``lastSeenOn`` after its ``clearedOn`` (T-192's check at the read
boundary is what catches it). A client
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
#: The one property a later cycle appends to a stored record without re-declaring it: the date it saw a
#: Veto stint still raised (``lastSeenOn``, an ``xsd:date``, one value per cycle; T-194).
APPENDING_PROPERTIES = frozenset({_PORTFOLIO.lastSeenOn})
#: Every property allowed on a subject untyped in the batch whose date is checked against the store.
STORED_DATE_PROPERTIES = CLOSING_PROPERTIES | APPENDING_PROPERTIES

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
        elif p in STORED_DATE_PROPERTIES:
            if not isinstance(s, rdflib.URIRef):
                problems.append(
                    f"{s.n3(nm)} {p.n3(nm)} (a closure or a sighting needs the IRI of a stored record)"
                )
            elif not (
                isinstance(o, rdflib.Literal) and o.datatype == XSD.date and _calendar_date(str(o))
            ):
                problems.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} (must be an xsd:date literal)")
        else:
            problems.append(f"{s.n3(nm)} {p.n3(nm)}")
    return sorted(problems)


def closing_values(batch: rdflib.Graph) -> dict[tuple[rdflib.term.Node, rdflib.URIRef], list[str]]:
    """The closing and appended-sighting triples about subjects with no ``rdf:type`` in the batch:
    (subject, property) -> the dates written."""
    typed = set(batch.subjects(RDF.type, None))
    closing: dict[tuple[rdflib.term.Node, rdflib.URIRef], list[str]] = {}
    for s, p, o in batch:
        if s not in typed and isinstance(s, rdflib.URIRef) and p in STORED_DATE_PROPERTIES:
            closing.setdefault((s, cast(rdflib.URIRef, p)), []).append(str(o))
    return closing


#: Per closing property: the classes whose records it closes, the property holding the date the record
#: opened (the closing date must be later: the shapes' ``sh:lessThan``, which the stored record is never
#: validated against here) and, for a Veto, the ``lastSeenOn`` it may not precede. Explicit, not read from
#: the shapes: a class is closable because its design says so (``07``), and ``PortfolioPositionShape``
#: does not mention ``validTo``.
class Closable(NamedTuple):
    """What a closing property closes: the classes, the date they opened, and (``last_seen``, T-185) the
    multi-valued date the closing may not precede."""

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


class Appendable(NamedTuple):
    """What a property appended by a later cycle is added to: the classes, the date they opened, the
    property that ends them (no more is appended once it is set; the appended date may not follow it)."""

    classes: frozenset[rdflib.URIRef]
    opened: rdflib.URIRef
    ended: rdflib.URIRef


APPENDABLE: Mapping[rdflib.URIRef, Appendable] = MappingProxyType(
    {
        _PORTFOLIO.lastSeenOn: Appendable(
            frozenset({_PORTFOLIO.Veto}), _PORTFOLIO.raisedOn, _PORTFOLIO.clearedOn
        )
    }
)
#: A restatement (T-032): the old section points at the new one, which the same batch declares.
SUPERSEDED_BY = _PORTFOLIO.supersededBy
_SECTION = _PORTFOLIO.SECFilingSection
_ITEM_LABEL = _PORTFOLIO.itemLabel
#: A per-run weight scheme (it has a ``cycleDate``) is an observation, never closed (``tbox.ttl``).
_PER_RUN_MARKER = _PORTFOLIO.cycleDate


#: subject IRI -> {property: lexical values the store holds}, as :func:`fetch_closing_state` reads it.
#: Named for closings (check 7); the restated sections of check 8 are read into it too.
ClosingState = dict[str, dict[rdflib.URIRef, set[str]]]


def fetch_closing_state(db: GraphDB, subjects: set[rdflib.term.Node]) -> ClosingState:
    """What the store holds (explicit statements, any graph) about ``subjects`` that decides whether
    they can be closed or superseded: subject -> {property: lexical values} for ``rdf:type``, the
    closing properties, the opening dates, the sightings, ``cycleDate``, and ``supersededBy`` and
    ``itemLabel`` (check 8)."""
    iris = sorted(str(s) for s in subjects)
    _refuse_illegal_iris(iris)
    read = {
        rdflib.URIRef(RDF.type),
        _PER_RUN_MARKER,
        *CLOSING_PROPERTIES,
        *(c.opened for c in CLOSABLE.values()),
        *(c.last_seen for c in CLOSABLE.values() if c.last_seen),
        SUPERSEDED_BY,
        _ITEM_LABEL,
        *APPENDABLE,
        *(a.opened for a in APPENDABLE.values()),
        *(a.ended for a in APPENDABLE.values()),
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


def _append_refusal(
    p: rdflib.URIRef,
    dates: list[str],
    held: dict[rdflib.URIRef, set[str]],
    ends_on: list[str],
) -> str | None:
    """Why appending ``dates`` of ``p`` to one stored subject is refused, or None. ``ends_on`` is
    what the same batch gives it as ``Appendable.ended`` (a sighting is not after that)."""
    classes, opened, ended = APPENDABLE[p]
    types = {rdflib.URIRef(t) for t in held.get(rdflib.URIRef(RDF.type), set())}
    if len(dates) > 1:
        return f"is given {len(dates)} dates in the batch"
    if not types:
        return "the store does not hold it"
    if not types & classes:
        return f"it is not a record that {p.rpartition('#')[2]} is added to"
    if held.get(ended):
        return f"it is already closed ({sorted(held[ended])[0]}), so no cycle saw it after"
    return (
        _not_before_opening(dates[0], held.get(opened, set()), opened)
        or _repeats_or_precedes(dates[0], held.get(p, set()))
        or _after_ending(dates[0], ends_on, ended)
    )


def _repeats_or_precedes(seen_on: str, seen: set[str]) -> str | None:
    """Why a sighting is refused against the stored ones, or None: a cycle's date is new (one value per
    cycle, at least 15 days apart), so an equal date is a replay, not a second cycle."""
    if why := _before_last_seen(seen_on, seen, "sighting"):
        return why
    day = _calendar_date(seen_on)
    if any(_calendar_date(t) == day for t in seen):
        return f"{seen_on} is already a stored sighting: perhaps this batch was already written"
    return None


def _not_before_opening(seen_on: str, began: set[str], opened: rdflib.URIRef) -> str | None:
    """Why a sighting date is refused against the stored opening date (the same day passes), or None."""
    if len(began) > 1:
        return f"the store holds {len(began)} values for {opened.rpartition('#')[2]}, so not when it opened"
    if not began:
        return None
    seen, opens = _calendar_date(seen_on), _calendar_date(next(iter(began)))
    if seen is None or opens is None:
        return f"{seen_on} cannot be compared with the stored {next(iter(began))}"
    return f"{seen_on} is before the date it opened on, {opens}" if seen < opens else None


def _after_ending(seen_on: str, ends_on: list[str], ended: rdflib.URIRef) -> str | None:
    """Why a sighting is refused for following the end date the same batch gives the record, or None."""
    end, seen = _calendar_date(ends_on[0]) if ends_on else None, _calendar_date(seen_on)
    if end and seen and seen > end:
        return f"{seen_on} is after the {ended.rpartition('#')[2]} the batch gives it, {end}"
    return None


def _before_last_seen(
    closes_on: str, seen: set[str], what: str = "date a cycle saw it"
) -> str | None:
    """Why a closing (or, with ``what``, a sighting) date is refused against the latest date a cycle
    saw the record, or None."""
    if not seen:
        return None
    dates = [_calendar_date(text) for text in seen]
    closes = _calendar_date(closes_on)
    if closes is None or None in dates:
        bad = sorted(seen)
        return f"{closes_on} cannot be compared with the stored last seen dates {bad}"
    latest = max(cast(list[datetime.date], dates))
    return f"{closes_on} is before the latest {what}, {latest}" if closes < latest else None


def refused_closures(batch: rdflib.Graph, state: ClosingState) -> list[str]:
    """Closing and sighting triples that do not close a stored, still open record, on a date after it
    opened, add a sighting the record may not take, or give one subject two dates."""
    nm = batch.namespace_manager
    problems: list[str] = []
    values = closing_values(batch)
    for (s, p), dates in sorted(values.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        held = state.get(str(s), {})
        if p in APPENDABLE:
            why = _append_refusal(p, dates, held, values.get((s, APPENDABLE[p].ended), []))
        else:
            why = _refusal(p, dates, held)
        if why:
            problems.append(f"{s.n3(nm)} {p.n3(nm)}: {why}")
    return problems


def superseded_sections(batch: rdflib.Graph) -> set[rdflib.term.Node]:
    """Subjects of ``:supersededBy`` triples that the batch does not declare: the stored sections it
    restates."""
    typed = set(batch.subjects(RDF.type, None))
    return {
        s
        for s in batch.subjects(SUPERSEDED_BY, None)
        if s not in typed and isinstance(s, rdflib.URIRef)
    }


def _other_label(old: set[str], new: rdflib.term.Node | None) -> str | None:
    """Why a replacement's ``:itemLabel`` is refused against the old section's, or None. Compared only
    when both have one (no shape requires it); two stored labels are refused, as two opening dates are
    (``:itemLabel`` is functional, but nothing enforces it)."""
    if len(old) > 1:
        return f"the store holds {len(old)} values for itemLabel, so not which item it is"
    if not old or new is None or str(new) in old:
        return None
    return f"its replacement is labelled {new}, it is labelled {next(iter(old))}: a restatement replaces the same item"


def _loops(batch: rdflib.Graph) -> list[list[rdflib.term.Node]]:
    """The ``:supersededBy`` cycles inside the batch, each once, from its smallest member."""
    nxt = {s: o for s, o in batch.subject_objects(SUPERSEDED_BY) if s != o}
    loops: list[list[rdflib.term.Node]] = []
    for start in sorted(nxt, key=str):
        path, cur = [start], nxt[start]
        while cur in nxt and cur not in path:
            path.append(cur)
            cur = nxt[cur]
        if cur == start and min(path, key=str) == start:
            loops.append(path)
    return loops


def _replacement_refusal(
    batch: rdflib.Graph,
    s: rdflib.term.Node,
    targets: list[rdflib.term.Node],
    typed: set[rdflib.term.Node],
    sections: set[rdflib.term.Node],
) -> str | None:
    """Why one subject's ``:supersededBy`` is refused on the batch alone, or None."""
    new = targets[0]
    if len(targets) > 1:
        return f"is given {len(targets)} replacements in the batch"
    if new == s:
        return "a section does not replace itself"
    if new not in sections:
        return "its replacement is not a SECFilingSection this batch declares (a restatement is a new section)"
    if s not in typed:  # a stored section: refused_supersessions reads it
        return (
            None
            if isinstance(s, rdflib.URIRef)
            else "a restated section needs the IRI of a stored one"
        )
    if s not in sections:
        return "it is not a SECFilingSection"
    label = batch.value(s, _ITEM_LABEL)
    return _other_label({str(label)} if label is not None else set(), batch.value(new, _ITEM_LABEL))


def restatement_problems(batch: rdflib.Graph) -> list[str]:
    """The half of check 8 the batch alone decides (T-032), run by :func:`validate`, so also by
    ``--check``: each ``:supersededBy`` gets one replacement, a ``SECFilingSection`` the batch declares,
    other than itself and with the same ``:itemLabel``; an old section the batch declares is a
    ``SECFilingSection``; a new section replaces one section; and no chain loops."""
    nm = batch.namespace_manager
    typed = set(batch.subjects(RDF.type, None))
    sections = set(batch.subjects(RDF.type, _SECTION))
    problems: list[str] = []
    replaces: dict[rdflib.term.Node, list[rdflib.term.Node]] = {}
    for s in sorted(set(batch.subjects(SUPERSEDED_BY, None)), key=str):
        targets = sorted(set(batch.objects(s, SUPERSEDED_BY)), key=str)
        why = _replacement_refusal(batch, s, targets, typed, sections)
        if why:
            problems.append(f"{s.n3(nm)} {SUPERSEDED_BY.n3(nm)}: {why}")
        else:
            replaces.setdefault(targets[0], []).append(s)
    for new, olds in sorted(replaces.items(), key=lambda kv: str(kv[0])):
        if len(olds) > 1:
            names = ", ".join(o.n3(nm) for o in olds)
            problems.append(
                f"{new.n3(nm)} replaces {len(olds)} sections ({names}): a new section replaces one"
            )
    for loop in _loops(batch):
        chain = " -> ".join(n.n3(nm) for n in [*loop, loop[0]])
        problems.append(f"{SUPERSEDED_BY.n3(nm)} loops ({chain}): no section would be current")
    return problems


def refused_supersessions(batch: rdflib.Graph, state: ClosingState) -> list[str]:
    """The half of check 8 the store decides (T-032), for the old sections the batch does not declare
    (:func:`superseded_sections`): each is a stored ``SECFilingSection``, not yet superseded (the next
    correction replaces the latest section), with the replacement's ``:itemLabel`` when both have one."""
    nm = batch.namespace_manager
    problems: list[str] = []
    for s in sorted(superseded_sections(batch), key=str):
        held = state.get(str(s), {})
        types = held.get(rdflib.URIRef(RDF.type), set())
        why = None
        if not types:
            why = "the store does not hold it"
        elif str(_SECTION) not in types:
            why = "it is not a SECFilingSection"
        elif held.get(SUPERSEDED_BY):
            why = (
                f"it is already superseded by {sorted(held[SUPERSEDED_BY])[0]}: "
                "the next correction replaces the latest section"
            )
        else:
            new = batch.value(s, SUPERSEDED_BY)  # one: validate refused more
            why = _other_label(held.get(_ITEM_LABEL, set()), batch.value(new, _ITEM_LABEL))
        if why:
            problems.append(f"{s.n3(nm)} {SUPERSEDED_BY.n3(nm)}: {why}")
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
    the untyped subjects, the restatements the batch alone decides (check 8's first half), then the
    shapes beside ``context``.

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
            "individuals and an xsd:date :validTo, :clearedOn or :lastSeenOn are allowed there): "
            + ", ".join(stray)
        )
    restating = restatement_problems(batch)
    if restating:
        raise IngestRejected("restatements that cannot be written (T-032): " + "; ".join(restating))
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
    ones), the closing triples' subjects and the stored sections it restates, and the typed individuals
    it declares, in that order, each only after the checks before it passed."""
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
    restated = superseded_sections(batch)
    if closing or restated:
        state = fetch_closing_state(db, closing | restated)
        stray = refused_closures(batch, state)
        if stray:
            raise IngestRejected(
                "closing or sighting triples the stored record cannot take (T-180, T-194): "
                + "; ".join(stray)
            )
        bad = refused_supersessions(batch, state)
        if bad:
            raise IngestRejected(
                "restatements the stored section cannot take (T-032): " + "; ".join(bad)
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
