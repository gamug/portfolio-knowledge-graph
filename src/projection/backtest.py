"""``v_book`` … ``v_backtest_test`` -> one append-only graph per backtest run (T-207, T-231).

The eight m018 views are a completed ``portfolio-financial-analysis`` backtest run's own output,
not an agent's daily batch. This module reads them through the boundary
(:mod:`projection.boundary`), turns each surviving row into one individual of the Contract v18
classes and writes the batch for each run into
``urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}`` (``docs/07``). The window
qualifies the name because the three run databases (P1, P2 and P3) each start their ids at 1; the
label qualifies it further because the views expose no run identity (no input hash, no
parameters), so several result families (``rule``, ``champ_v1``, …) can live in one repository.
The label reaches every IRI stem too, so two families never share an individual.

Every individual carries ``:knowledgeDate`` exactly as its view gives it. A NULL column is
omitted, never filled: the handoff §3.3 masks layer-1 alert values, layer-3/4 assets, asset-level
action weights, ordinary-session target weights and CASH's asset/name. A CASH weight row has no
``:holdingAsset`` and never creates an ``:Asset`` node. An asset link is written only for a ticker
that exists in the universe database; a former S&P 500 member absent from that small database
keeps its ``:guardTicker``/``:holdingKey`` and is counted, not dropped.

The window and segment vocabularies are patterns, not closed lists: ``windowId`` is ``P<number>``
and ``segment`` is ``P<number>`` with an optional lowercase sub-period suffix (``P2a``), so a new
window needs no schema change (T-234). The arm vocabulary stays closed.


A GUARD alert's ``:alertRule`` points at the matching ``:Rule_{rule_id}`` in ``schema/rules.ttl``;
an unknown rule id, or a view layer that disagrees with the rule's ``:guardLayer``, stops the run.
No rule, asset or value is invented. Writing is :mod:`kg_store.gate`'s job; :func:`run` calls it
only when a store is given.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import rdflib
from rdflib.namespace import RDF, XSD
from rdflib.term import Node

from etl.asset_master import Stint, read_stints
from kg_store import gate
from kg_store.graphdb import GraphDB, GraphDBError
from projection.boundary import (
    BoundaryReport,
    Failure,
    Row,
    check_backtest_source,
    validate,
)
from projection.expectations import load_expectations, load_source
from projection.source import FinancialSource
from projection.view_contract import VIEW_COLUMNS

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

#: The eight m018 views this projector reads, in report order.
VIEWS = (
    "v_book",
    "v_book_rebalance",
    "v_guard_alert",
    "v_guard_action",
    "v_book_weight_daily",
    "v_book_daily_performance",
    "v_portfolio_period_summary",
    "v_backtest_test",
)

#: The natural-key order each view is read in, so the Turtle is deterministic.
ORDER: dict[str, tuple[str, ...]] = {
    "v_book": ("book_id",),
    "v_book_rebalance": ("rebalance_id",),
    "v_guard_alert": ("alert_id",),
    "v_guard_action": ("action_id",),
    "v_book_weight_daily": ("book_id", "date", "holding_key"),
    "v_book_daily_performance": ("book_id", "date"),
    "v_portfolio_period_summary": ("book_id", "segment"),
    "v_backtest_test": ("backtest_run_id", "segment", "arm_a", "arm_b", "test"),
    # Work item 26: the selection-side views, in dependency order.
    "v_cycle_run": ("run_id",),
    "v_weight_scheme": ("cycle_run_id",),
    "v_weight_component": ("cycle_run_id", "score_type"),
    "v_cycle_ranking": ("cycle_run_id", "asset_id"),
    "v_cycle_ranking_component": ("cycle_run_id", "asset_id", "score_type"),
    "v_veto": ("id",),
}

#: The six selection-side views (Work item 26): the cycle run log, the configured scheme, the
#: per-asset ranking and its effective weights, and the veto stints.
SELECTION_VIEWS = (
    "v_cycle_run",
    "v_weight_scheme",
    "v_weight_component",
    "v_cycle_ranking",
    "v_cycle_ranking_component",
    "v_veto",
)

#: ``v_cycle_ranking_component.score_type`` -> our ``:weightMetricName`` (the same fixed pairing
#: ``ScoreSnapshotShape`` uses). SECTOR has no upstream weight and never appears here.
SCORE_TYPE_METRICS: dict[str, str] = {
    "FUNDAMENTAL": "ScoreFinanciero",
    "VALORIZATION": "ScoreCuantitativo",
    "TECHNICAL": "ScoreTecnico",
    "SEMANTIC": "Sentiment",
    "SECTOR": "SectorRelativeMomentum",
}

GRAPH_PREFIX = "urn:graph:derived:backtest:"
SELECTION_GRAPH_PREFIX = "urn:graph:derived:backtest:selection:"
#: A run label: the operator's name for one result family (``--db LABEL=PATH``). Lowercase,
#: 2-32 characters, and the same pattern SHACL's ``:runLabel`` enforces (T-233).
RUN_LABEL_PATTERN = r"[a-z][a-z0-9_]{1,31}"
#: A window id. It was the closed set ``P1|P2|P3``; it is now open to ``P<number>`` so new data
#: needs no schema change (T-234).
WINDOW_PATTERN = r"P[0-9]+"
#: A segment: a window id plus an optional lowercase sub-period suffix (``P2a``, ``P2b``).
SEGMENT_PATTERN = r"P[0-9]+[a-z]?"
ARMS = frozenset({"MARKOWITZ_BASE", "TOPN_MV_NOGUARD", "TOPN_MV_GUARD_NO_NLP", "TOPN_MV_GUARD"})

_RUN_LABEL = re.compile(RUN_LABEL_PATTERN)
_WINDOW = re.compile(WINDOW_PATTERN)
_SEGMENT = re.compile(SEGMENT_PATTERN)

_PREFIXES = (
    "@prefix : <https://thesis.local/kg/portfolio#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
#: A local name that is safe in both an IRI and a Turtle prefixed name: starts and ends
#: alphanumeric, and carries only letters, digits, ``_``, ``.`` and ``-`` in between.
_SAFE_PART = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


class ProjectionError(ValueError):
    """A row passed the boundary but cannot be projected; the message names it."""


class StoreInterrupted(RuntimeError):
    """The store failed partway through the writes; ``result`` holds what was done before it."""

    def __init__(self, result: RunResult, cause: GraphDBError) -> None:
        super().__init__(str(cause))
        self.result = result


# --- reading ------------------------------------------------------------------------------------


def read_view(db: FinancialSource, view: str) -> list[Row]:
    """Every row of ``view`` (the pinned columns only), ordered by its natural key."""
    columns = VIEW_COLUMNS[view]
    order = ORDER[view]
    cursor = db.execute(
        f"SELECT {', '.join(columns)} FROM {view} ORDER BY {', '.join(order)}"  # noqa: S608 -- constants from the pin
    )
    return [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]


@dataclass(frozen=True)
class AssetInfo:
    """What the projector needs of one universe asset: its CIK and its membership stints."""

    symbol: str
    cik: str | None
    stints: tuple[tuple[str, str | None], ...] = ()


def universe_assets(path: str | Path) -> dict[str, AssetInfo]:
    """The universe database's assets, read the way :func:`projection.score_snapshots.universe_symbols` is."""
    grouped: defaultdict[str, list[Stint]] = defaultdict(list)
    for stint in read_stints(path):
        grouped[stint.symbol].append(stint)
    assets: dict[str, AssetInfo] = {}
    for symbol, stints in sorted(grouped.items()):
        stints.sort(key=lambda stint: stint.valid_from)
        assets[symbol] = AssetInfo(
            symbol,
            next((stint.cik for stint in stints if stint.cik), None),
            tuple((stint.valid_from, stint.valid_to) for stint in stints),
        )
    return assets


@dataclass(frozen=True)
class GuardRule:
    """One ``:category "GUARD"`` rule: its ``ruleId``, IRI and protection layer."""

    rule_id: str
    iri: rdflib.URIRef
    layer: int


@dataclass
class GuardCatalog:
    """The GUARD rules of ``schema/rules.ttl`` and the graph they were read from.

    The graph is also the SHACL context a dry run needs: a batch only points at the rule, so the
    rule's ``rdf:type``/``:guardLayer`` must come from outside the batch (the store holds them on
    a write).
    """

    by_id: dict[str, GuardRule]
    graph: rdflib.Graph


def load_guard_catalog(path: str | Path) -> GuardCatalog:
    """Read the five GUARD ``RuleDefinition``s from ``rules.ttl``; refuse an inconsistent one."""
    graph = rdflib.Graph().parse(path, format="turtle")
    rules: dict[str, GuardRule] = {}
    for subject in graph.subjects(RDF.type, KG.RuleDefinition):
        if not isinstance(subject, rdflib.URIRef):
            raise ProjectionError(f"{_n3(subject)}: a GUARD rule needs an IRI")
        if str(graph.value(subject, KG.category)) != "GUARD":
            continue
        rule_id_value = graph.value(subject, KG.ruleId)
        layer_value = graph.value(subject, KG.guardLayer)
        if not isinstance(rule_id_value, rdflib.Literal) or not isinstance(
            layer_value, rdflib.Literal
        ):
            raise ProjectionError(f"{_n3(subject)}: a GUARD rule needs :ruleId and :guardLayer")
        rule_id = str(rule_id_value)
        expected = KG[f"Rule_{rule_id}"]
        if subject != expected:
            raise ProjectionError(
                f"{_n3(subject)}: the GUARD rule IRI must be {_n3(expected)} (T-207)"
            )
        if rule_id in rules:
            raise ProjectionError(f"{rule_id}: two GUARD rule definitions share the id")
        rules[rule_id] = GuardRule(rule_id, subject, int(str(layer_value)))
    if not rules:
        raise ProjectionError(f'{path}: no :category "GUARD" rule definitions')
    return GuardCatalog(rules, graph)


@dataclass(frozen=True)
class SelectionRule:
    """One ``:RuleDefinition`` that applies to selection vetoes: its id, IRI and valid interval."""

    rule_id: str
    iri: rdflib.URIRef
    valid_from: str
    valid_to: str | None


@dataclass
class SelectionRuleCatalog:
    """The selection rules of ``schema/rules.ttl`` and the graph they were read from."""

    by_id: dict[str, tuple[SelectionRule, ...]]
    graph: rdflib.Graph


class RuleGraph(Protocol):
    """What :func:`validation_context` needs of a rule catalog."""

    graph: rdflib.Graph


def load_selection_catalog(path: str | Path) -> SelectionRuleCatalog:
    """Read every non-GUARD ``RuleDefinition`` from ``rules.ttl``, keyed by ``:ruleId``.

    A rule id may have more than one definition over time (``LIQUIDITY_DISTRESS`` has two); the
    resolver below picks the one in force on the backtest run's date.
    """
    graph = rdflib.Graph().parse(path, format="turtle")
    rules: defaultdict[str, list[SelectionRule]] = defaultdict(list)
    for subject in graph.subjects(RDF.type, KG.RuleDefinition):
        if not isinstance(subject, rdflib.URIRef):
            raise ProjectionError(f"{_n3(subject)}: a selection rule needs an IRI")
        rule_id_value = graph.value(subject, KG.ruleId)
        valid_from_value = graph.value(subject, KG.validFrom)
        if not isinstance(rule_id_value, rdflib.Literal) or not isinstance(
            valid_from_value, rdflib.Literal
        ):
            raise ProjectionError(f"{_n3(subject)}: a selection rule needs :ruleId and :validFrom")
        if str(graph.value(subject, KG.category)) == "GUARD":
            continue
        rule_id = str(rule_id_value)
        valid_to_value = graph.value(subject, KG.validTo)
        valid_to = None if valid_to_value is None else str(valid_to_value)
        valid_from = str(valid_from_value)
        _day(valid_from, "validFrom", _n3(subject))
        if valid_to is not None:
            _day(valid_to, "validTo", _n3(subject))
        rules[rule_id].append(SelectionRule(rule_id, subject, valid_from, valid_to))
    if not rules:
        raise ProjectionError(f"{path}: no selection rule definitions")
    return SelectionRuleCatalog(
        {rule_id: tuple(definitions) for rule_id, definitions in rules.items()}, graph
    )


def resolve_rule(catalog: SelectionRuleCatalog, rule_id: str, on_date: str) -> rdflib.URIRef:
    """The one definition of ``rule_id`` in force on ``on_date`` (``validFrom <= d < validTo``)."""
    definitions = catalog.by_id.get(rule_id)
    if not definitions:
        raise ProjectionError(
            f"unknown ruleId {rule_id!r}: no :RuleDefinition with that :ruleId is in force on "
            f"{on_date} (schema/rules.ttl)"
        )
    active = [
        rule
        for rule in definitions
        if rule.valid_from <= on_date and (rule.valid_to is None or on_date < rule.valid_to)
    ]
    if len(active) != 1:
        found = "none" if not active else "several: " + ", ".join(_n3(rule.iri) for rule in active)
        raise ProjectionError(
            f"ruleId {rule_id!r}: expected exactly one definition in force on {on_date}, found "
            f"{found}"
        )
    return active[0].iri


def validation_context(assets: Mapping[str, AssetInfo], catalog: RuleGraph) -> rdflib.Graph:
    """The rules and the assets a dry run needs beside a batch (a write fetches them from the store).

    Assets get their type, ticker and CIK (or, without a CIK, their real memberships) so the
    ``sh:class :Asset`` and ``AssetShape`` checks see what the universe would have loaded. This
    graph is validation context only: none of it is written.
    """
    context = rdflib.Graph()
    for triple in catalog.graph:
        context.add(triple)
    # T-227: `:membershipUniverse` carries `sh:class :Universe`; a membership the context adds must
    # point at a typed Universe, and the store would hold that type for `:SP500Index`.
    context.add((KG.SP500Index, RDF.type, KG.Universe))
    for symbol, info in assets.items():
        asset = KG[symbol]
        context.add((asset, RDF.type, KG.Asset))
        context.add((asset, KG.tickerSymbol, rdflib.Literal(symbol)))
        if info.cik is not None:
            context.add((asset, KG.cikNumber, rdflib.Literal(info.cik)))
        for index, (valid_from, valid_to) in enumerate(info.stints):
            membership = KG[f"Membership_{symbol}_{index}"]
            context.add((membership, RDF.type, KG.UniverseMembership))
            context.add((membership, KG.membershipAsset, asset))
            context.add((membership, KG.membershipUniverse, KG.SP500Index))
            context.add(
                (
                    membership,
                    KG.validFrom,
                    rdflib.Literal(valid_from, datatype=XSD.date),
                )
            )
            if valid_to is not None:
                context.add(
                    (
                        membership,
                        KG.validTo,
                        rdflib.Literal(valid_to, datatype=XSD.date),
                    )
                )
            context.add((asset, KG.hasUniverseMembership, membership))
    return context


# --- deterministic Turtle -----------------------------------------------------------------------


def _n3(term: Node) -> str:
    """A term in N3, for an error message only."""
    return term.n3()


class GraphBuilder:
    """A graph of triples with one deterministic Turtle serialization.

    Subjects, predicates and values are sorted, so the same input always gives byte-identical
    Turtle. Objects are literals or IRIs; this projector creates no blank nodes.
    """

    def __init__(self) -> None:
        self.triples: set[tuple[rdflib.URIRef, rdflib.URIRef, Node]] = set()

    def add(self, subject: rdflib.URIRef, predicate: rdflib.URIRef, value: Node) -> None:
        self.triples.add((subject, predicate, value))

    def __len__(self) -> int:
        return len(self.triples)

    def turtle(self) -> bytes:
        by_subject: defaultdict[rdflib.URIRef, dict[rdflib.URIRef, list[Node]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for subject, predicate, value in self.triples:
            by_subject[subject][predicate].append(value)
        lines = [_PREFIXES.rstrip("\n")]
        for subject in sorted(by_subject, key=str):
            lines.append("")
            properties = by_subject[subject]
            head = _n3(subject)
            if RDF.type in properties:
                types = ", ".join(_name(term) for term in sorted(properties[RDF.type], key=str))
                head = f"{head} a {types}"
            predicates = sorted((p for p in properties if p != RDF.type), key=str)
            if not predicates:
                lines.append(f"{head} .")
                continue
            lines.append(f"{head} ;")
            for index, predicate in enumerate(predicates):
                values = ", ".join(
                    _name(term)
                    for term in sorted(
                        properties[predicate],
                        key=lambda term: (str(term), type(term).__name__),
                    )
                )
                end = " ." if index == len(predicates) - 1 else " ;"
                lines.append(f"    {_name(predicate)} {values}{end}")
        return ("\n".join(lines) + "\n").encode()


def _name(term: Node) -> str:
    """A prefixed name when the term is in the portfolio namespace, else its N3 form."""
    if isinstance(term, rdflib.URIRef) and str(term).startswith(NS):
        local = str(term)[len(NS) :]
        if _SAFE_PART.fullmatch(local):
            return f":{local}"
    return _n3(term)


# --- identifiers and value checks ---------------------------------------------------------------


def graph_name(label: str, window: str, run_id: int) -> str:
    """The named graph of one completed backtest run (``docs/07``)."""
    return f"{GRAPH_PREFIX}{_graph_suffix(label, window, run_id)}"


def selection_graph_name(label: str, window: str, run_id: int) -> str:
    """The sibling graph of one run's selection side (Work item 26, ``docs/07``)."""
    return f"{SELECTION_GRAPH_PREFIX}{_graph_suffix(label, window, run_id)}"


def _graph_suffix(label: str, window: str, run_id: int) -> str:
    """The label/window/id part both backtest graph names share."""
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    if not _WINDOW.fullmatch(window):
        raise ProjectionError(f"window_id {window!r} does not match {WINDOW_PATTERN}")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ProjectionError(f"backtest_run_id {run_id!r} is not a positive integer")
    return f"{label}:{window}:{run_id}"


def _window(value: object, where: str) -> str:
    """A window id: ``P<number>`` (T-234)."""
    text = str(value)
    if not _WINDOW.fullmatch(text):
        raise ProjectionError(f"{where}: window_id {text!r} does not match {WINDOW_PATTERN}")
    return text


def _segment(value: object, where: str) -> str:
    """A segment: ``P<number>`` plus an optional lowercase sub-period suffix (T-234)."""
    text = str(value)
    if not _SEGMENT.fullmatch(text):
        raise ProjectionError(f"{where}: segment {text!r} does not match {SEGMENT_PATTERN}")
    return text


def _safe(value: object, what: str, where: str) -> str:
    text = str(value)
    if not _SAFE_PART.fullmatch(text):
        raise ProjectionError(f"{where}: {what} {text!r} cannot form a valid IRI local name")
    return text


def _where(view: str, row: Row, key: str = "id") -> str:
    return f"{view} {key}={row.get(key)}"


def _required(row: Row, column: str, where: str) -> Any:
    value = row.get(column)
    if value is None:
        raise ProjectionError(f"{where}: {column} is NULL")
    return value


def _day(value: object, column: str, where: str) -> str:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ProjectionError(f"{where}: {column} {value!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise ProjectionError(f"{where}: {column} {value!r} is not a real date") from None
    return value


def _timestamp(value: object, column: str, where: str) -> str:
    """An upstream ISO timestamp with an offset, normalized to a UTC ``xsd:dateTime``."""
    if not isinstance(value, str):
        raise ProjectionError(f"{where}: {column} {value!r} is not a timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ProjectionError(f"{where}: {column} {value!r} is not a timestamp") from None
    if moment.tzinfo is None:
        raise ProjectionError(f"{where}: {column} {value!r} carries no UTC offset")
    return moment.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _integer(value: object, column: str, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectionError(f"{where}: {column} {value!r} is not an integer")
    return value


def _decimal(value: object, column: str, where: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionError(f"{where}: {column} {value!r} is not a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ProjectionError(f"{where}: {column} {value!r} is not a decimal") from None
    if not number.is_finite():
        raise ProjectionError(f"{where}: {column} {value!r} is not finite")
    return format(number, "f")


def _day_lit(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.date)


def _int_lit(value: int) -> rdflib.Literal:
    return rdflib.Literal(str(value), datatype=XSD.integer)


def _dec_lit(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.decimal)


def _bool_lit(value: int) -> rdflib.Literal:
    return rdflib.Literal("true" if value else "false", datatype=XSD.boolean)


# --- the projection -----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Book:
    row: Row
    graph: str
    label: str
    window: str
    run_id: int
    arm: str
    iri: rdflib.URIRef


@dataclass
class Projection:
    """The per-graph batches and the counts a dry run or write reports."""

    graphs: dict[str, GraphBuilder] = field(default_factory=dict)
    rows: Counter[str] = field(default_factory=Counter)
    individuals: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    asset_unlinked: Counter[str] = field(default_factory=Counter)
    cash_rows: Counter[str] = field(default_factory=Counter)

    def builder(self, graph: str) -> GraphBuilder:
        return self.graphs.setdefault(graph, GraphBuilder())

    def individual(self, graph: str, iri: rdflib.URIRef, rdf_type: str) -> GraphBuilder:
        builder = self.builder(graph)
        builder.add(iri, RDF.type, KG[rdf_type])
        self.individuals[rdf_type] += 1
        return builder

    def turtle(self, graph: str) -> bytes:
        return self.graphs[graph].turtle()

    def triples_by_class(self) -> Counter[str]:
        """Triples per Contract v18 class, counted over every graph's batch."""
        counts: Counter[str] = Counter()
        for builder in self.graphs.values():
            types = {
                subject: value
                for subject, predicate, value in builder.triples
                if predicate == RDF.type and isinstance(value, rdflib.URIRef)
            }
            for subject, _, _ in builder.triples:
                kind = types.get(subject)
                if kind is not None:
                    counts[str(kind).rsplit("#", 1)[-1]] += 1
        return counts


def project(
    rows: Mapping[str, Sequence[Row]],
    assets: Mapping[str, AssetInfo],
    catalog: GuardCatalog,
    label: str,
) -> Projection:
    """Turn the validated rows into one deterministic batch per backtest run.

    Every row that reaches here becomes one individual; the projection refuses (rather than
    silently drops) a row it cannot identify, link or type. ``label`` names the run family and
    reaches the graph name and every IRI stem.
    """
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    out = Projection()
    for view in VIEWS:
        out.rows[view] = len(rows.get(view, ()))
    books = _books(rows.get("v_book", ()), label, out)
    by_book_id = {_int_row(book.row, "book_id", "v_book"): book for book in books}
    runs: dict[int, str] = {}
    for book in books:
        if runs.setdefault(book.run_id, book.window) != book.window:
            raise ProjectionError(
                f"v_book: run {book.run_id} appears in windows {runs[book.run_id]} and {book.window}"
            )
    alerts = _alerts(rows.get("v_guard_alert", ()), runs, assets, catalog, label, out)
    _rebalances(rows.get("v_book_rebalance", ()), by_book_id, out)
    _actions(rows.get("v_guard_action", ()), by_book_id, alerts, assets, out)
    _weights(rows.get("v_book_weight_daily", ()), by_book_id, assets, out)
    _performance(rows.get("v_book_daily_performance", ()), by_book_id, out)
    _summaries(rows.get("v_portfolio_period_summary", ()), by_book_id, out)
    _tests(rows.get("v_backtest_test", ()), runs, label, out)
    return out


def _int_row(row: Row, column: str, view: str, key: str = "id") -> int:
    return _integer(_required(row, column, _where(view, row, key)), column, _where(view, row, key))


def _books(rows: Sequence[Row], label: str, out: Projection) -> list[_Book]:
    books: list[_Book] = []
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_book", row, "book_id")
        window = _window(_required(row, "window_id", where), where)
        run_id = _int_row(row, "backtest_run_id", "v_book", "book_id")
        arm = _safe(_required(row, "arm_code", where), "arm_code", where)
        if arm not in ARMS:
            raise ProjectionError(f"{where}: arm_code {arm!r} is not a Contract v18 arm")
        iri = KG[f"Book_{label}_{window}_{arm}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two books would share the IRI {_n3(iri)}")
        seen.add(iri)
        book = _Book(row, graph_name(label, window, run_id), label, window, run_id, arm, iri)
        books.append(book)
        builder = out.individual(book.graph, iri, "StrategyBook")
        builder.add(iri, KG.bookId, _int_lit(_int_row(row, "book_id", "v_book", "book_id")))
        builder.add(iri, KG.backtestRunId, _int_lit(run_id))
        builder.add(iri, KG.runLabel, rdflib.Literal(label))
        builder.add(iri, KG.windowId, rdflib.Literal(window))
        builder.add(
            iri,
            KG.backtestStartDate,
            _day_lit(_day(_required(row, "d_start", where), "d_start", where)),
        )
        builder.add(
            iri,
            KG.backtestEndDate,
            _day_lit(_day(_required(row, "d_end", where), "d_end", where)),
        )
        builder.add(iri, KG.runStatus, rdflib.Literal(str(_required(row, "run_status", where))))
        builder.add(iri, KG.armCode, rdflib.Literal(arm))
        builder.add(iri, KG.objective, rdflib.Literal(str(_required(row, "objective", where))))
        builder.add(
            iri,
            KG.excludeHardVetoed,
            _bool_lit(_int_row(row, "exclude_hard_vetoed", "v_book", "book_id")),
        )
        if row.get("guard_layers") is not None:
            builder.add(iri, KG.guardLayers, rdflib.Literal(str(row["guard_layers"])))
        if row.get("formation_date") is not None:
            builder.add(
                iri,
                KG.formationDate,
                _day_lit(_day(row["formation_date"], "formation_date", where)),
            )
        if row.get("code_version") is not None:
            builder.add(iri, KG.codeVersion, rdflib.Literal(str(row["code_version"])))
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )
    return books


def _alerts(  # noqa: PLR0913, PLR0917 -- the call site reads better with the names explicit
    rows: Sequence[Row],
    runs: Mapping[int, str],
    assets: Mapping[str, AssetInfo],
    catalog: GuardCatalog,
    label: str,
    out: Projection,
) -> dict[tuple[str, int], rdflib.URIRef]:
    iris: dict[tuple[str, int], rdflib.URIRef] = {}
    for row in rows:
        where = _where("v_guard_alert", row, "alert_id")
        run_id = _int_row(row, "backtest_run_id", "v_guard_alert", "alert_id")
        window = _window(_required(row, "window_id", where), where)
        if runs.get(run_id) != window:
            raise ProjectionError(
                f"{where}: run {run_id} belongs to window {runs.get(run_id)!r}, not {window!r}"
            )
        alert_id = _int_row(row, "alert_id", "v_guard_alert", "alert_id")
        rule_id = str(_required(row, "rule_id", where))
        rule = catalog.by_id.get(rule_id)
        if rule is None:
            raise ProjectionError(f"{where}: rule_id {rule_id!r} is not a GUARD rule in rules.ttl")
        layer = _int_row(row, "layer", "v_guard_alert", "alert_id")
        if layer != rule.layer:
            raise ProjectionError(
                f"{where}: layer {layer} disagrees with {rule_id}'s guardLayer {rule.layer}"
            )
        iri = KG[f"GuardAlert_{label}_{window}_{alert_id}"]
        key = (window, alert_id)
        if key in iris:
            raise ProjectionError(f"{where}: two alerts would share the IRI {_n3(iri)}")
        iris[key] = iri
        graph = graph_name(label, window, run_id)
        builder = out.individual(graph, iri, "GuardAlert")
        builder.add(iri, KG.alertId, _int_lit(alert_id))
        builder.add(iri, KG.backtestRunId, _int_lit(run_id))
        builder.add(iri, KG.windowId, rdflib.Literal(window))
        builder.add(
            iri,
            KG.alertDate,
            _day_lit(_day(_required(row, "date", where), "date", where)),
        )
        builder.add(iri, KG.guardLayer, _int_lit(layer))
        builder.add(iri, KG.alertRule, rule.iri)
        if row.get("ticker") is not None:
            ticker = _safe(row["ticker"], "ticker", where)
            builder.add(iri, KG.guardTicker, rdflib.Literal(ticker))
            _link_asset(builder, iri, KG.guardAsset, ticker, assets, "v_guard_alert", out)
        if row.get("value") is not None:
            builder.add(
                iri,
                KG.alertValue,
                _dec_lit(_decimal(row["value"], "value", where)),
            )
        builder.add(
            iri,
            KG.alertThreshold,
            _dec_lit(_decimal(_required(row, "threshold", where), "threshold", where)),
        )
        builder.add(iri, KG.alertState, rdflib.Literal(str(_required(row, "state", where))))
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )
    return iris


def _link_asset(  # noqa: PLR0913, PLR0917 -- the call sites read better with the names explicit
    builder: GraphBuilder,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    ticker: str,
    assets: Mapping[str, AssetInfo],
    view: str,
    out: Projection,
) -> None:
    """Link to ``:{TICKER}`` only when the universe database has it; count the rest."""
    if ticker in assets:
        builder.add(subject, predicate, KG[ticker])
    else:
        out.asset_unlinked[view] += 1


def _day_key(day: str) -> str:
    """``YYYY-MM-DD`` -> ``YYYYMMDD``: a local name with no character a Python identifier dislikes."""
    return day.replace("-", "")


def _rebalances(rows: Sequence[Row], books: Mapping[int, _Book], out: Projection) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_book_rebalance", row, "rebalance_id")
        book = books.get(_int_row(row, "book_id", "v_book_rebalance", "rebalance_id"))
        if book is None:
            raise ProjectionError(f"{where}: book_id is not a v_book row")
        _same_book(row, book, where)
        execution = _day(_required(row, "execution_date", where), "execution_date", where)
        iri = KG[f"Rebalance_{book.label}_{book.window}_{book.arm}_{_day_key(execution)}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two rebalances would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(book.graph, iri, "BookRebalance")
        builder.add(
            iri,
            KG.rebalanceId,
            _int_lit(_int_row(row, "rebalance_id", "v_book_rebalance", "rebalance_id")),
        )
        builder.add(
            iri, KG.bookId, _int_lit(_int_row(row, "book_id", "v_book_rebalance", "rebalance_id"))
        )
        builder.add(iri, KG.backtestRunId, _int_lit(book.run_id))
        builder.add(iri, KG.armCode, rdflib.Literal(book.arm))
        builder.add(
            iri,
            KG.decisionDate,
            _day_lit(_day(_required(row, "decision_date", where), "decision_date", where)),
        )
        builder.add(iri, KG.executionDate, _day_lit(execution))
        builder.add(iri, KG.status, rdflib.Literal(str(_required(row, "status", where))))
        for column, prop in (
            ("quant_portfolio_id", KG.quantPortfolioId),
            ("cycle_run_id", KG.cycleRunId),
            ("risk_model_id", KG.riskModelId),
        ):
            if row.get(column) is not None:
                builder.add(
                    iri, prop, _int_lit(_int_row(row, column, "v_book_rebalance", "rebalance_id"))
                )
        builder.add(iri, KG.rebalanceOfBook, book.iri)
        builder.add(book.iri, KG.bookHasRebalance, iri)
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


def _same_book(row: Row, book: _Book, where: str) -> None:
    """A child row must agree with the book its ``book_id`` resolved to."""
    run_id = _integer(_required(row, "backtest_run_id", where), "backtest_run_id", where)
    if run_id != book.run_id:
        raise ProjectionError(
            f"{where}: backtest_run_id {run_id} disagrees with the book's {book.run_id}"
        )
    arm = str(row.get("arm_code"))
    if arm != book.arm:
        raise ProjectionError(f"{where}: arm_code {arm!r} disagrees with the book's {book.arm!r}")


def _actions(
    rows: Sequence[Row],
    books: Mapping[int, _Book],
    alerts: Mapping[tuple[str, int], rdflib.URIRef],
    assets: Mapping[str, AssetInfo],
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_guard_action", row, "action_id")
        book = books.get(_int_row(row, "book_id", "v_guard_action", "action_id"))
        if book is None:
            raise ProjectionError(f"{where}: book_id is not a v_book row")
        _same_book(row, book, where)
        alert_id = _int_row(row, "alert_id", "v_guard_action", "action_id")
        alert_iri = alerts.get((book.window, alert_id))
        if alert_iri is None:
            raise ProjectionError(
                f"{where}: alert_id {alert_id} is not a v_guard_alert row of window {book.window}"
            )
        action_id = _int_row(row, "action_id", "v_guard_action", "action_id")
        iri = KG[f"GuardAction_{book.label}_{book.window}_{action_id}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two actions would share the IRI {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(book.graph, iri, "GuardAction")
        builder.add(iri, KG.actionId, _int_lit(action_id))
        builder.add(
            iri,
            KG.bookId,
            _int_lit(_int_row(row, "book_id", "v_guard_action", "action_id")),
        )
        builder.add(iri, KG.backtestRunId, _int_lit(book.run_id))
        builder.add(iri, KG.armCode, rdflib.Literal(book.arm))
        builder.add(
            iri,
            KG.decisionDate,
            _day_lit(_day(_required(row, "decision_date", where), "decision_date", where)),
        )
        builder.add(
            iri,
            KG.effectiveDate,
            _day_lit(_day(_required(row, "effective_date", where), "effective_date", where)),
        )
        builder.add(iri, KG.status, rdflib.Literal(str(_required(row, "status", where))))
        builder.add(iri, KG.actionOfBook, book.iri)
        builder.add(book.iri, KG.bookHasGuardAction, iri)
        builder.add(iri, KG.actionAlert, alert_iri)
        builder.add(alert_iri, KG.alertHasGuardAction, iri)
        if row.get("ticker") is not None:
            ticker = _safe(row["ticker"], "ticker", where)
            builder.add(iri, KG.guardTicker, rdflib.Literal(ticker))
            _link_asset(builder, iri, KG.guardAsset, ticker, assets, "v_guard_action", out)
        if row.get("weight_before") is not None:
            builder.add(
                iri,
                KG.weightBefore,
                _dec_lit(_decimal(row["weight_before"], "weight_before", where)),
            )
        if row.get("weight_after") is not None:
            builder.add(
                iri,
                KG.weightAfter,
                _dec_lit(_decimal(row["weight_after"], "weight_after", where)),
            )
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


def _weights(
    rows: Sequence[Row],
    books: Mapping[int, _Book],
    assets: Mapping[str, AssetInfo],
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_book_weight_daily", row, "date")
        book = books.get(_int_row(row, "book_id", "v_book_weight_daily", "date"))
        if book is None:
            raise ProjectionError(f"{where}: book_id is not a v_book row")
        _same_book(row, book, where)
        day = _day(_required(row, "date", where), "date", where)
        holding_key = _safe(_required(row, "holding_key", where), "holding_key", where)
        iri = KG[f"BookWeight_{book.label}_{book.window}_{book.arm}_{_day_key(day)}_{holding_key}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two weight rows would share the IRI {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(book.graph, iri, "BookWeightDaily")
        builder.add(
            iri,
            KG.bookId,
            _int_lit(_int_row(row, "book_id", "v_book_weight_daily", "date")),
        )
        builder.add(iri, KG.backtestRunId, _int_lit(book.run_id))
        builder.add(iri, KG.armCode, rdflib.Literal(book.arm))
        builder.add(iri, KG.weightDate, _day_lit(day))
        builder.add(iri, KG.holdingKey, rdflib.Literal(holding_key))
        if holding_key == "CASH":
            if row.get("asset_id") is not None:
                raise ProjectionError(f"{where}: a CASH row cannot carry an asset_id")
            out.cash_rows["v_book_weight_daily"] += 1
        else:
            # The view has no separate ticker column; holding_key is the ticker.
            _link_asset(
                builder,
                iri,
                KG.holdingAsset,
                holding_key,
                assets,
                "v_book_weight_daily",
                out,
            )
        if row.get("holding_name") is not None:
            builder.add(iri, KG.holdingName, rdflib.Literal(str(row["holding_name"])))
        if row.get("markowitz_target_weight") is not None:
            builder.add(
                iri,
                KG.markowitzTargetWeight,
                _dec_lit(
                    _decimal(row["markowitz_target_weight"], "markowitz_target_weight", where)
                ),
            )
        if row.get("final_target_weight") is not None:
            builder.add(
                iri,
                KG.finalTargetWeight,
                _dec_lit(_decimal(row["final_target_weight"], "final_target_weight", where)),
            )
        builder.add(iri, KG.weightOfBook, book.iri)
        builder.add(book.iri, KG.bookHasWeight, iri)
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


def _performance(rows: Sequence[Row], books: Mapping[int, _Book], out: Projection) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_book_daily_performance", row, "date")
        book = books.get(_int_row(row, "book_id", "v_book_daily_performance", "date"))
        if book is None:
            raise ProjectionError(f"{where}: book_id is not a v_book row")
        _same_book(row, book, where)
        if str(row.get("window_id")) != book.window:
            raise ProjectionError(
                f"{where}: window_id {row.get('window_id')!r} disagrees with the book's {book.window!r}"
            )
        day = _day(_required(row, "date", where), "date", where)
        iri = KG[f"BookPerf_{book.label}_{book.window}_{book.arm}_{_day_key(day)}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two performance rows would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(book.graph, iri, "BookDailyPerformance")
        builder.add(
            iri,
            KG.bookId,
            _int_lit(_int_row(row, "book_id", "v_book_daily_performance", "date")),
        )
        builder.add(iri, KG.backtestRunId, _int_lit(book.run_id))
        builder.add(iri, KG.armCode, rdflib.Literal(book.arm))
        builder.add(iri, KG.windowId, rdflib.Literal(book.window))
        builder.add(iri, KG.performanceDate, _day_lit(day))
        for column, prop in (
            ("gross_return", KG.grossReturn),
            ("turnover", KG.turnover),
            ("cost_return", KG.costReturn),
            ("net_return", KG.netReturn),
            ("nav", KG.nav),
            ("drawdown", KG.drawdown),
            ("cash_weight", KG.cashWeight),
        ):
            builder.add(
                iri,
                prop,
                _dec_lit(_decimal(_required(row, column, where), column, where)),
            )
        builder.add(
            iri,
            KG.nEquity,
            _int_lit(_int_row(row, "n_equity", "v_book_daily_performance", "date")),
        )
        if row.get("benchmark_return") is not None:
            builder.add(
                iri,
                KG.benchmarkReturn,
                _dec_lit(_decimal(row["benchmark_return"], "benchmark_return", where)),
            )
        builder.add(iri, KG.performanceOfBook, book.iri)
        builder.add(book.iri, KG.bookHasPerformance, iri)
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


def _summaries(rows: Sequence[Row], books: Mapping[int, _Book], out: Projection) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_portfolio_period_summary", row, "segment")
        book = books.get(_int_row(row, "book_id", "v_portfolio_period_summary", "segment"))
        if book is None:
            raise ProjectionError(f"{where}: book_id is not a v_book row")
        _same_book(row, book, where)
        if str(row.get("window_id")) != book.window:
            raise ProjectionError(
                f"{where}: window_id {row.get('window_id')!r} disagrees with the book's {book.window!r}"
            )
        segment = _segment(_required(row, "segment", where), where)
        iri = KG[f"PeriodSummary_{book.label}_{book.window}_{book.arm}_{segment}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two summaries would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(book.graph, iri, "PortfolioPeriodSummary")
        builder.add(
            iri,
            KG.bookId,
            _int_lit(_int_row(row, "book_id", "v_portfolio_period_summary", "segment")),
        )
        builder.add(iri, KG.backtestRunId, _int_lit(book.run_id))
        builder.add(iri, KG.armCode, rdflib.Literal(book.arm))
        builder.add(iri, KG.windowId, rdflib.Literal(book.window))
        builder.add(iri, KG.segment, rdflib.Literal(segment))
        builder.add(
            iri,
            KG.dateFrom,
            _day_lit(_day(_required(row, "date_from", where), "date_from", where)),
        )
        builder.add(
            iri,
            KG.dateTo,
            _day_lit(_day(_required(row, "date_to", where), "date_to", where)),
        )
        for column, prop in (
            ("cumulative_return", KG.cumulativeReturn),
            ("annualized_return", KG.annualizedReturn),
            ("annualized_vol", KG.annualizedVol),
            ("ex_post_sharpe", KG.exPostSharpe),
            ("max_drawdown", KG.maxDrawdown),
            ("total_turnover", KG.totalTurnover),
            ("total_cost_bps", KG.totalCostBps),
        ):
            builder.add(
                iri,
                prop,
                _dec_lit(_decimal(_required(row, column, where), column, where)),
            )
        builder.add(
            iri,
            KG.nRebalances,
            _int_lit(_int_row(row, "n_rebalances", "v_portfolio_period_summary", "segment")),
        )
        builder.add(
            iri,
            KG.nGuardActions,
            _int_lit(_int_row(row, "n_guard_actions", "v_portfolio_period_summary", "segment")),
        )
        builder.add(iri, KG.summaryOfBook, book.iri)
        builder.add(book.iri, KG.bookHasSummary, iri)
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


def _tests(rows: Sequence[Row], runs: Mapping[int, str], label: str, out: Projection) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_backtest_test", row, "test")
        run_id = _int_row(row, "backtest_run_id", "v_backtest_test", "test")
        window = _window(_required(row, "window_id", where), where)
        if runs.get(run_id) != window:
            raise ProjectionError(
                f"{where}: run {run_id} belongs to window {runs.get(run_id)!r}, not {window!r}"
            )
        segment = _segment(_required(row, "segment", where), where)
        arm_a = _safe(_required(row, "arm_a", where), "arm_a", where)
        arm_b = _safe(_required(row, "arm_b", where), "arm_b", where)
        test = _safe(_required(row, "test", where), "test", where)
        iri = KG[f"BacktestTest_{label}_{window}_{segment}_{arm_a}_{arm_b}_{test}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two tests would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(graph_name(label, window, run_id), iri, "BacktestTest")
        builder.add(iri, KG.backtestRunId, _int_lit(run_id))
        builder.add(iri, KG.runLabel, rdflib.Literal(label))
        builder.add(iri, KG.windowId, rdflib.Literal(window))
        builder.add(iri, KG.segment, rdflib.Literal(segment))
        builder.add(iri, KG.armA, rdflib.Literal(arm_a))
        builder.add(iri, KG.armB, rdflib.Literal(arm_b))
        builder.add(iri, KG.testName, rdflib.Literal(test))
        builder.add(
            iri,
            KG.statistic,
            _dec_lit(_decimal(_required(row, "statistic", where), "statistic", where)),
        )
        builder.add(
            iri,
            KG.pValue,
            _dec_lit(_decimal(_required(row, "p_value", where), "p_value", where)),
        )
        builder.add(iri, KG.nObs, _int_lit(_int_row(row, "n_obs", "v_backtest_test", "test")))
        if row.get("params_json") is not None:
            builder.add(iri, KG.paramsJson, rdflib.Literal(str(row["params_json"])))
        builder.add(
            iri,
            KG.knowledgeDate,
            _day_lit(_day(_required(row, "knowledge_date", where), "knowledge_date", where)),
        )


# --- the selection side (Work item 26) ---------------------------------------------------------


@dataclass(frozen=True)
class _SelectionContext:
    """The one backtest run a selection database belongs to."""

    label: str
    window: str
    run_id: int
    graph: str
    rule_date: str


@dataclass(frozen=True)
class _Cycle:
    iri: rdflib.URIRef
    cycle_id: int
    as_of: str
    status: str
    finished_at: str | None


@dataclass(frozen=True)
class _Scheme:
    iri: rdflib.URIRef
    cycle_id: int


def _selection_context(books: Sequence[Row], label: str) -> _SelectionContext:
    """The run id, window and knowledge date shared by every ``v_book`` row."""
    if not books:
        raise ProjectionError("v_book: no backtest run to attach the selection side to")
    runs: set[int] = set()
    windows: set[str] = set()
    days: set[str] = set()
    for row in books:
        where = _where("v_book", row, "book_id")
        runs.add(_int_row(row, "backtest_run_id", "v_book", "book_id"))
        windows.add(_window(_required(row, "window_id", where), where))
        days.add(_day(_required(row, "knowledge_date", where), "knowledge_date", where))
    if len(runs) != 1 or len(windows) != 1:
        raise ProjectionError(
            f"v_book: one database must hold one backtest run, found run ids {sorted(runs)} and "
            f"windows {sorted(windows)}"
        )
    if len(days) != 1:
        raise ProjectionError(
            "v_book: the arms disagree on knowledge_date; the rule-resolution date is ambiguous: "
            + ", ".join(sorted(days))
        )
    run_id = next(iter(runs))
    window = next(iter(windows))
    return _SelectionContext(
        label,
        window,
        run_id,
        selection_graph_name(label, window, run_id),
        next(iter(days)),
    )


def _metric(score_type: str, where: str) -> str:
    metric = SCORE_TYPE_METRICS.get(score_type)
    if metric is None:
        raise ProjectionError(f"{where}: score_type {score_type!r} has no metricType name")
    return metric


def _cycles(rows: Sequence[Row], context: _SelectionContext, out: Projection) -> dict[int, _Cycle]:
    cycles: dict[int, _Cycle] = {}
    for row in rows:
        where = _where("v_cycle_run", row, "run_id")
        cycle_id = _int_row(row, "run_id", "v_cycle_run", "run_id")
        if cycle_id in cycles:
            raise ProjectionError(f"{where}: two v_cycle_run rows share run_id {cycle_id}")
        as_of = _day(_required(row, "as_of", where), "as_of", where)
        status = str(_required(row, "status", where))
        finished = row.get("finished_at")
        finished_at = None if finished is None else _timestamp(finished, "finished_at", where)
        iri = KG[f"Cycle_{context.label}_{context.window}_{cycle_id}"]
        builder = out.individual(context.graph, iri, "SelectionCycle")
        builder.add(iri, KG.cycleRunId, _int_lit(cycle_id))
        builder.add(iri, KG.cycleType, rdflib.Literal(str(_required(row, "cycle_type", where))))
        builder.add(iri, KG.runAsOf, _day_lit(as_of))
        builder.add(iri, KG.runId, rdflib.Literal(f"cycle_run:{cycle_id}"))
        builder.add(iri, KG.status, rdflib.Literal(status))
        builder.add(iri, KG.runLabel, rdflib.Literal(context.label))
        builder.add(iri, KG.windowId, rdflib.Literal(context.window))
        builder.add(iri, KG.backtestRunId, _int_lit(context.run_id))
        if row.get("code_version") is not None:
            builder.add(iri, KG.codeVersion, rdflib.Literal(str(row["code_version"])))
        if row.get("started_at") is not None:
            builder.add(
                iri,
                KG.startedAt,
                rdflib.Literal(
                    _timestamp(row["started_at"], "started_at", where),
                    datatype=XSD.dateTime,
                ),
            )
        if finished_at is not None:
            builder.add(iri, KG.finishedAt, rdflib.Literal(finished_at, datatype=XSD.dateTime))
        cycles[cycle_id] = _Cycle(iri, cycle_id, as_of, status, finished_at)
    return cycles


def _schemes(
    rows: Sequence[Row],
    context: _SelectionContext,
    cycles: Mapping[int, _Cycle],
    out: Projection,
) -> dict[int, _Scheme]:
    schemes: dict[int, _Scheme] = {}
    for row in rows:
        where = _where("v_weight_scheme", row, "cycle_run_id")
        cycle_id = _int_row(row, "cycle_run_id", "v_weight_scheme", "cycle_run_id")
        if cycle_id not in cycles:
            raise ProjectionError(f"{where}: cycle_run_id {cycle_id} is not a v_cycle_run row")
        if cycle_id in schemes:
            raise ProjectionError(
                f"{where}: two v_weight_scheme rows share cycle_run_id {cycle_id}"
            )
        iri = KG[f"Scheme_{context.label}_{context.window}_{cycle_id}"]
        builder = out.individual(context.graph, iri, "AttractivenessWeightScheme")
        builder.add(iri, KG.schemeId, rdflib.Literal(f"cycle_run:{cycle_id}"))
        builder.add(
            iri,
            KG.cycleDate,
            _day_lit(_day(_required(row, "cycle_date", where), "cycle_date", where)),
        )
        builder.add(iri, KG.cycleRunId, _int_lit(cycle_id))
        builder.add(iri, KG.runId, rdflib.Literal(f"cycle_run:{cycle_id}"))
        builder.add(
            iri,
            KG.bookWeightingRule,
            rdflib.Literal(str(_required(row, "scheme_id", where))),
        )
        builder.add(
            iri,
            KG.topN,
            _int_lit(_int_row(row, "top_n", "v_weight_scheme", "cycle_run_id")),
        )
        for column, prop in (
            ("max_name_weight", KG.maxNameWeight),
            ("max_sector_weight", KG.maxSectorWeight),
            ("soft_veto_penalty", KG.softVetoPenalty),
        ):
            if row.get(column) is not None:
                builder.add(iri, prop, _dec_lit(_decimal(row[column], column, where)))
        schemes[cycle_id] = _Scheme(iri, cycle_id)
    return schemes


def _configured_components(
    rows: Sequence[Row],
    context: _SelectionContext,
    schemes: Mapping[int, _Scheme],
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    counts: Counter[int] = Counter()
    for row in rows:
        where = _where("v_weight_component", row, "cycle_run_id")
        cycle_id = _int_row(row, "cycle_run_id", "v_weight_component", "cycle_run_id")
        scheme = schemes.get(cycle_id)
        if scheme is None:
            raise ProjectionError(f"{where}: cycle_run_id {cycle_id} has no v_weight_scheme row")
        score_type = str(_required(row, "score_type", where))
        metric = _metric(score_type, where)
        iri = KG[f"Weight_{context.label}_{context.window}_{cycle_id}_{metric}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two configured components would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(context.graph, iri, "WeightComponent")
        builder.add(iri, KG.weightMetricName, rdflib.Literal(metric))
        builder.add(
            iri,
            KG.weightValue,
            _dec_lit(_decimal(_required(row, "weight", where), "weight", where)),
        )
        builder.add(scheme.iri, KG.hasWeightComponent, iri)
        counts[cycle_id] += 1
    missing = sorted(set(schemes) - set(counts))
    if missing:
        raise ProjectionError(
            "v_weight_component: the scheme(s) of cycle_run "
            + ", ".join(str(cycle_id) for cycle_id in missing)
            + " have no component rows"
        )


def _rankings(  # noqa: PLR0913, PLR0917 -- the call site reads better with the names explicit
    rows: Sequence[Row],
    context: _SelectionContext,
    cycles: Mapping[int, _Cycle],
    schemes: Mapping[int, _Scheme],
    assets: Mapping[str, AssetInfo],
    out: Projection,
) -> dict[tuple[int, int], rdflib.URIRef]:
    iris: dict[tuple[int, int], rdflib.URIRef] = {}
    for row in rows:
        where = _where("v_cycle_ranking", row, "cycle_run_id")
        cycle_id = _int_row(row, "cycle_run_id", "v_cycle_ranking", "cycle_run_id")
        cycle = cycles.get(cycle_id)
        if cycle is None:
            raise ProjectionError(f"{where}: cycle_run_id {cycle_id} is not a v_cycle_run row")
        if cycle.status != "completed":
            out.skipped["v_cycle_ranking: run is not completed"] += 1
            continue
        scheme = schemes.get(cycle_id)
        if scheme is None:
            raise ProjectionError(f"{where}: cycle_run_id {cycle_id} has no v_weight_scheme row")
        if cycle.finished_at is None:
            raise ProjectionError(f"{where}: completed cycle_run {cycle_id} has no finished_at")
        asset_id = _int_row(row, "asset_id", "v_cycle_ranking", "cycle_run_id")
        key = (cycle_id, asset_id)
        if key in iris:
            raise ProjectionError(f"{where}: two ranking rows share cycle_run_id/asset_id {key}")
        ticker = str(_required(row, "ticker", where))
        iri = KG[f"Snap_{context.label}_{context.window}_{cycle_id}_{asset_id}"]
        iris[key] = iri
        builder = out.individual(context.graph, iri, "AttractivenessSnapshot")
        builder.add(iri, KG.backtestRunId, _int_lit(context.run_id))
        builder.add(iri, KG.runLabel, rdflib.Literal(context.label))
        builder.add(iri, KG.windowId, rdflib.Literal(context.window))
        builder.add(iri, KG.rankingTicker, rdflib.Literal(ticker))
        _link_asset(
            builder,
            iri,
            KG.attractivenessOfAsset,
            ticker,
            assets,
            "v_cycle_ranking",
            out,
        )
        builder.add(iri, KG.rankingOfCycle, cycle.iri)
        builder.add(iri, KG.computedWithScheme, scheme.iri)
        builder.add(
            iri,
            KG.attractivenessScore,
            _dec_lit(
                format(
                    Decimal(
                        _decimal(
                            _required(row, "blended_score", where),
                            "blended_score",
                            where,
                        )
                    )
                    / 100,
                    "f",
                )
            ),
        )
        builder.add(iri, KG.computedAt, rdflib.Literal(cycle.finished_at, datatype=XSD.dateTime))
        builder.add(
            iri,
            KG.rankPosition,
            _int_lit(_int_row(row, "rank", "v_cycle_ranking", "cycle_run_id")),
        )
        builder.add(
            iri,
            KG.selectedForBook,
            _bool_lit(_int_row(row, "selected", "v_cycle_ranking", "cycle_run_id")),
        )
        builder.add(
            iri,
            KG.vetoedAtRanking,
            _bool_lit(_int_row(row, "vetoed", "v_cycle_ranking", "cycle_run_id")),
        )
        if row.get("veto_rules_json") is not None:
            builder.add(iri, KG.vetoRulesJson, rdflib.Literal(str(row["veto_rules_json"])))
        if row.get("target_weight") is not None:
            builder.add(
                iri,
                KG.targetWeight,
                _dec_lit(_decimal(row["target_weight"], "target_weight", where)),
            )
    return iris


def _effective_components(
    rows: Sequence[Row],
    context: _SelectionContext,
    rankings: Mapping[tuple[int, int], rdflib.URIRef],
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_cycle_ranking_component", row, "cycle_run_id")
        cycle_id = _int_row(row, "cycle_run_id", "v_cycle_ranking_component", "cycle_run_id")
        asset_id = _int_row(row, "asset_id", "v_cycle_ranking_component", "cycle_run_id")
        snapshot = rankings.get((cycle_id, asset_id))
        if snapshot is None:
            out.skipped["v_cycle_ranking_component: ranking row not projected"] += 1
            continue
        score_type = str(_required(row, "score_type", where))
        metric = _metric(score_type, where)
        iri = KG[f"RankComp_{context.label}_{context.window}_{cycle_id}_{asset_id}_{metric}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two effective components would share {_n3(iri)}")
        seen.add(iri)
        builder = out.individual(context.graph, iri, "WeightComponent")
        builder.add(iri, KG.weightMetricName, rdflib.Literal(metric))
        builder.add(
            iri,
            KG.weightValue,
            _dec_lit(
                _decimal(_required(row, "effective_weight", where), "effective_weight", where)
            ),
        )
        builder.add(
            iri,
            KG.componentValue,
            _dec_lit(_decimal(_required(row, "component_value", where), "component_value", where)),
        )
        builder.add(snapshot, KG.hasEffectiveWeight, iri)


def _vetoes(  # noqa: PLR0913, PLR0917 -- the call site reads better with the names explicit
    rows: Sequence[Row],
    context: _SelectionContext,
    cycles: Mapping[int, _Cycle],
    assets: Mapping[str, AssetInfo],
    catalog: SelectionRuleCatalog,
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_veto", row, "id")
        veto_id = _int_row(row, "id", "v_veto", "id")
        iri = KG[f"Veto_{context.label}_{context.window}_{veto_id}"]
        if iri in seen:
            raise ProjectionError(f"{where}: two v_veto rows share id {veto_id}")
        seen.add(iri)
        rule_id = str(_required(row, "rule_id", where))
        rule = resolve_rule(catalog, rule_id, context.rule_date)
        ticker = str(_required(row, "ticker", where))
        run_id = _int_row(row, "run_id", "v_veto", "id")
        builder = out.individual(context.graph, iri, "Veto")
        builder.add(iri, KG.vetoTicker, rdflib.Literal(ticker))
        _link_asset(builder, iri, KG.vetoOfAsset, ticker, assets, "v_veto", out)
        builder.add(iri, KG.appliesRule, rule)
        builder.add(iri, KG.primaryRule, rule)
        builder.add(iri, KG.vetoSeverity, rdflib.Literal(str(_required(row, "severity", where))))
        builder.add(
            iri,
            KG.raisedOn,
            _day_lit(_day(_required(row, "raised_on", where), "raised_on", where)),
        )
        if row.get("cleared_on") is not None:
            builder.add(
                iri,
                KG.clearedOn,
                _day_lit(_day(row["cleared_on"], "cleared_on", where)),
            )
        if row.get("last_seen_on") is not None:
            builder.add(
                iri,
                KG.lastSeenOn,
                _day_lit(_day(row["last_seen_on"], "last_seen_on", where)),
            )
        if row.get("expires_on") is not None:
            builder.add(
                iri,
                KG.expiresOn,
                _day_lit(_day(row["expires_on"], "expires_on", where)),
            )
        builder.add(iri, KG.runId, rdflib.Literal(f"cycle_run:{run_id}"))
        builder.add(iri, KG.runLabel, rdflib.Literal(context.label))
        builder.add(iri, KG.windowId, rdflib.Literal(context.window))
        builder.add(iri, KG.backtestRunId, _int_lit(context.run_id))
        cycle = cycles.get(run_id)
        if cycle is not None:
            builder.add(iri, KG.runAsOf, _day_lit(cycle.as_of))


def project_selection(
    rows: Mapping[str, Sequence[Row]],
    assets: Mapping[str, AssetInfo],
    catalog: SelectionRuleCatalog,
    label: str,
) -> Projection:
    """Turn the validated selection rows into one deterministic batch per backtest run.

    ``rows`` carries ``v_book`` (for the run id, window, knowledge date and rule-resolution date)
    and the six :data:`SELECTION_VIEWS`. Every row becomes one individual; a ranking row with no
    component rows stays as an upstream placeholder (score 0.0, no ``:hasEffectiveWeight``).
    """
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    context = _selection_context(rows.get("v_book", ()), label)
    out = Projection()
    for view in SELECTION_VIEWS:
        out.rows[view] = len(rows.get(view, ()))
    cycles = _cycles(rows.get("v_cycle_run", ()), context, out)
    schemes = _schemes(rows.get("v_weight_scheme", ()), context, cycles, out)
    _configured_components(rows.get("v_weight_component", ()), context, schemes, out)
    rankings = _rankings(rows.get("v_cycle_ranking", ()), context, cycles, schemes, assets, out)
    _effective_components(rows.get("v_cycle_ranking_component", ()), context, rankings, out)
    _vetoes(rows.get("v_veto", ()), context, cycles, assets, catalog, out)
    return out


# --- reading, validating and writing ------------------------------------------------------------


@dataclass
class RunResult:
    """What one database's projection did."""

    report: BoundaryReport
    rows: Counter[str]
    individuals: Counter[str]
    triples_by_class: Counter[str] = field(default_factory=Counter)
    graphs: dict[str, int] = field(default_factory=dict)  # graph -> triples
    checked: list[str] = field(default_factory=list)  # dry run: SHACL-valid graphs
    written: dict[str, int] = field(default_factory=dict)  # graph -> triples
    already_in_store: list[str] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)  # graph -> why the gate refused it
    skipped: Counter[str] = field(default_factory=Counter)
    asset_unlinked: Counter[str] = field(default_factory=Counter)
    cash_rows: Counter[str] = field(default_factory=Counter)
    store_consulted: bool = True
    in_doubt: str | None = None

    def summary(self) -> str:
        lines = [self.report.summary()]
        lines += [f"  rows: {view}: {n}" for view, n in self.rows.items()]
        lines += [f"  individuals: {kind}: {n}" for kind, n in sorted(self.individuals.items())]
        lines += [f"  triples: {kind}: {n}" for kind, n in sorted(self.triples_by_class.items())]
        lines += [f"  graph: {graph}: {n} triples" for graph, n in sorted(self.graphs.items())]
        lines += [f"  skipped: {reason}: {n}" for reason, n in sorted(self.skipped.items())]
        lines += [
            f"  asset link omitted: {view}: {n}" for view, n in sorted(self.asset_unlinked.items())
        ]
        lines += [f"  CASH rows: {n}" for n in [sum(self.cash_rows.values())] if n]
        if self.store_consulted:
            lines += [f"  already in the store: {graph}" for graph in self.already_in_store]
        else:
            lines += ["  already in the store: not checked (dry run)"]
        lines += [f"  SHACL-valid, not written: {graph}" for graph in self.checked]
        lines += [f"  written: {graph}: {n} triples" for graph, n in sorted(self.written.items())]
        lines += [f"  rejected: {graph}: {why}" for graph, why in sorted(self.rejected.items())]
        if self.in_doubt:
            lines += [
                (
                    f"  in doubt: {self.in_doubt}: it was sent but the store's answer was lost, "
                    "so it may be written"
                )
            ]
        return "\n".join(lines)


@dataclass
class SourceProjection:
    """One source database after the boundary and the projector, before any store is touched.

    ``rows`` is the rows that passed the boundary, keyed by view; ``projection`` is the
    deterministic batch built from them. A dry run and a write share this exactly, so a verifier
    can rebuild the expected graph without writing it (T-280).
    """

    report: BoundaryReport
    rows: dict[str, list[Row]]
    projection: Projection


def project_source(
    source: FinancialSource,
    assets: Mapping[str, AssetInfo],
    catalog: GuardCatalog,
    label: str,
) -> SourceProjection:
    """Read the eight views, run the boundary and project them; no store and no SHACL.

    ``label`` is the operator's name for this run family (``--db LABEL=PATH``): the views expose
    no run identity, so it is what keeps two families' graphs and individuals apart. The source
    check runs before the other seven views are read: a database whose backtest run is not
    ``completed`` is refused, never projected partially. The boundary then checks every view
    against its shipped expectation file.
    """
    books = read_view(source, "v_book")
    source_failures = check_backtest_source(source.schema_version, books, load_source())
    rows = {"v_book": books}
    rows.update({view: read_view(source, view) for view in VIEWS if view != "v_book"})
    expectations = load_expectations()
    result = validate(
        rows,
        {view: expectations[view] for view in VIEWS},
        source_failures=source_failures,
    )
    return SourceProjection(
        result.report, result.rows, project(result.rows, assets, catalog, label)
    )


def run(
    source: FinancialSource,
    assets: Mapping[str, AssetInfo],
    catalog: GuardCatalog,
    label: str,
    store: GraphDB | None = None,
) -> RunResult:
    """Read, check, project and (when ``store`` is given) write the eight m018 views.

    A dry run validates each graph beside the rules and assets from ``schema/``/the universe
    database; a write hands the batches to the ingest gate, which fetches that context from the
    store.
    """
    source_projection = project_source(source, assets, catalog, label)
    projection = source_projection.projection
    out = RunResult(
        source_projection.report,
        projection.rows,
        projection.individuals,
        triples_by_class=projection.triples_by_class(),
        graphs={graph: len(builder) for graph, builder in projection.graphs.items()},
        skipped=projection.skipped,
        asset_unlinked=projection.asset_unlinked,
        cash_rows=projection.cash_rows,
        store_consulted=store is not None,
    )
    context = validation_context(assets, catalog) if store is None else None
    for graph in sorted(projection.graphs):
        data = projection.turtle(graph)
        batch = gate.parse_batch(data)
        if store is None:
            gate.validate(batch, context=context)
            out.checked.append(graph)
            continue
        if _graph_exists(store, graph):
            out.already_in_store.append(graph)
            continue
        try:
            out.written[graph] = gate.ingest(store, data, graph)
        except gate.WriteInDoubt as exc:
            out.in_doubt = graph
            raise StoreInterrupted(out, exc) from exc
        except gate.IngestRejected as exc:
            out.rejected[graph] = str(exc)
    return out


def run_selection(
    source: FinancialSource,
    assets: Mapping[str, AssetInfo],
    catalog: SelectionRuleCatalog,
    label: str,
    store: GraphDB | None = None,
) -> RunResult:
    """Read, check, project and (when ``store`` is given) write the six selection views.

    ``v_book`` supplies the one backtest run and its 2026-10-31 knowledge date; the source check is
    the m018 one (the backtest run must be ``completed``). ``v_cycle_run`` is not checked against
    the live REPLAY refusal: a backtest database's cycle runs are REPLAY by construction, and this
    projector is writing a frozen backtest artifact, not a live ingest graph. A ranking row whose
    cycle run is not ``completed`` is counted as skipped; its components are counted too.
    """
    books = read_view(source, "v_book")
    source_failures = check_backtest_source(source.schema_version, books, load_source())
    rows = {"v_book": books}
    rows.update({view: read_view(source, view) for view in SELECTION_VIEWS})
    expectations = load_expectations()
    result = validate(
        {view: rows[view] for view in SELECTION_VIEWS},
        {view: expectations[view] for view in SELECTION_VIEWS},
        source_failures=source_failures,
    )
    projection = project_selection({**result.rows, "v_book": books}, assets, catalog, label)
    out = RunResult(
        result.report,
        projection.rows,
        projection.individuals,
        triples_by_class=projection.triples_by_class(),
        graphs={graph: len(builder) for graph, builder in projection.graphs.items()},
        skipped=projection.skipped,
        asset_unlinked=projection.asset_unlinked,
        store_consulted=store is not None,
    )
    context = validation_context(assets, catalog) if store is None else None
    for graph in sorted(projection.graphs):
        data = projection.turtle(graph)
        batch = gate.parse_batch(data)
        if store is None:
            gate.validate(batch, context=context)
            out.checked.append(graph)
            continue
        if _graph_exists(store, graph):
            out.already_in_store.append(graph)
            continue
        try:
            out.written[graph] = gate.ingest(store, data, graph)
        except gate.WriteInDoubt as exc:
            out.in_doubt = graph
            raise StoreInterrupted(out, exc) from exc
        except gate.IngestRejected as exc:
            out.rejected[graph] = str(exc)
    return out


def _graph_exists(store: GraphDB, graph: str) -> bool:
    """Whether ``graph`` holds any statement: the gate's own test for an append-only graph."""
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))


#: A ``Failure`` import keeps the module's public report types together for callers/tests.
__all__ = [
    "ARMS",
    "GRAPH_PREFIX",
    "RUN_LABEL_PATTERN",
    "SCORE_TYPE_METRICS",
    "SEGMENT_PATTERN",
    "SELECTION_GRAPH_PREFIX",
    "SELECTION_VIEWS",
    "VIEWS",
    "WINDOW_PATTERN",
    "AssetInfo",
    "BoundaryReport",
    "Failure",
    "GuardCatalog",
    "GuardRule",
    "Projection",
    "ProjectionError",
    "RunResult",
    "SelectionRule",
    "SelectionRuleCatalog",
    "SourceProjection",
    "StoreInterrupted",
    "graph_name",
    "load_guard_catalog",
    "load_selection_catalog",
    "project",
    "project_selection",
    "project_source",
    "read_view",
    "resolve_rule",
    "run",
    "run_selection",
    "selection_graph_name",
    "universe_assets",
    "validation_context",
]
