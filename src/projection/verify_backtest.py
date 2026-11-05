"""Verify one stored backtest graph against a fresh in-memory projection of its source.

    uv run python cli/verify_backtest.py --graph urn:graph:derived:backtest:rule:P1:1 \\
        --db /path/to/rule_P1.db --label rule
    uv run python cli/verify_backtest.py \\
        --graph urn:graph:derived:backtest:selection:rule:P1:1 \\
        --db /path/to/rule_P1.db --label rule

The verifier is read-only: it issues SPARQL ``SELECT`` queries only, never an update, a graph
write or a repository change. It reads the same ``--db`` through :mod:`projection.backtest`'s
deterministic projector (no store, no SHACL pass), then compares the result with the named graph in
the repository selected by the environment (``KG_HOST``/``KG_REPOSITORY``, as every other store
CLI). One ``PASS``/``FAIL`` line is printed per check; the exit status is 0 only when every check
passes, 1 when a check fails or the source/store cannot be read, 2 on a bad argument.

The graph name selects the side: an m018 graph checks the eight backtest/GUARD views, and a
selection graph (Work item 29) checks the six selection views plus the cross-graph link from the
m018 graph's TOPN ``BookRebalance`` rows to its ``SelectionCycle`` rows. The m018 checks are
unchanged: the graph's name and its stored ``:runLabel``/``:windowId``/``:backtestRunId`` agree with
the label, window and run id; its triple count equals the re-projection; each class has one
individual per source row; ``:holdingAsset``/``:guardAsset`` link the tickers the source can link,
and no more rows are unlinked than the projector reports; the GuardAlert rule/layer/state groups,
GuardAction statuses, last NAV per arm and CASH rows equal the source; every period summary's
``:nGuardActions`` equals the ``APPLIED`` actions by ``decision_date`` inside its segment from both
the source and the graph; the Basing Points alerts equal the source count and carry no
``:alertThreshold``; and every individual carries ``:runLabel`` through its book (where the model
has that link) and ``:knowledgeDate``.

Selection checks: graph identity, total triples, one individual per projected source row for
``SelectionCycle``, ``AttractivenessSnapshot``, ``AttractivenessWeightScheme``, ``Veto`` and the
configured/effective ``WeightComponent`` links; the UNSCORED/UNPRICED placeholder count;
``:attractivenessOfAsset``/``:vetoOfAsset`` links and the unlinked-ticker ceiling; vetoes grouped
by resolved rule; and every ``:cycleRunId`` of a TOPN ``BookRebalance`` in the m018 graph having
its ``SelectionCycle`` in the selection graph (the ``MARKOWITZ`` arms have none).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import rdflib

from etl import config
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB, GraphDBError
from projection.backtest import (
    GRAPH_PREFIX,
    RUN_LABEL_PATTERN,
    SELECTION_GRAPH_PREFIX,
    WINDOW_PATTERN,
    AssetInfo,
    GraphBuilder,
    GuardCatalog,
    Projection,
    ProjectionError,
    SelectionRuleCatalog,
    graph_name,
    load_guard_catalog,
    load_selection_catalog,
    project_selection_source,
    project_source,
    universe_assets,
)
from projection.boundary import BoundaryError, Row
from projection.source import FinancialSource

#: The eight views, their one Contract v18 class and the natural key each check reports.
VIEW_CLASS: tuple[tuple[str, str], ...] = (
    ("v_book", "StrategyBook"),
    ("v_book_rebalance", "BookRebalance"),
    ("v_guard_alert", "GuardAlert"),
    ("v_guard_action", "GuardAction"),
    ("v_book_weight_daily", "BookWeightDaily"),
    ("v_book_daily_performance", "BookDailyPerformance"),
    ("v_portfolio_period_summary", "PortfolioPeriodSummary"),
    ("v_backtest_test", "BacktestTest"),
)

PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"
# The queries below read only GraphDB's explicit-statements graph (`EXPLICIT_GRAPH` from
# `kg_store.graphdb`): inferred triples cannot make a stored graph look different from its batch.

_GRAPH = re.compile(
    rf"{re.escape(GRAPH_PREFIX)}"
    rf"(?P<label>{RUN_LABEL_PATTERN}):(?P<window>{WINDOW_PATTERN}):(?P<run>[1-9][0-9]*)"
)
_SELECTION_GRAPH = re.compile(
    rf"{re.escape(SELECTION_GRAPH_PREFIX)}"
    rf"(?P<label>{RUN_LABEL_PATTERN}):(?P<window>{WINDOW_PATTERN}):(?P<run>[1-9][0-9]*)"
)
_CASH = "CASH"
_KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


class VerificationError(ValueError):
    """The verifier itself cannot run (a malformed label, a missing source, ...)."""


class ReadableStore(Protocol):
    """What the verifier needs of a store: SPARQL ``SELECT`` and nothing else."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


@dataclass(frozen=True)
class GraphIdentity:
    """The label, window and run id a backtest graph name carries."""

    label: str
    window: str
    run_id: int


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line."""

    name: str
    passed: bool
    detail: str


@dataclass
class Verification:
    """The checks run against one repository graph and their result."""

    repository: str
    host: str
    graph: str
    label: str
    database: Path
    checks: list[Check]
    triples: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    @property
    def failed(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    def summary(self) -> str:
        """The header, one ``PASS``/``FAIL`` line per check and the total."""
        lines = [
            f"repository: {self.repository}" + (f" ({self.host})" if self.host else ""),
            f"graph: {self.graph}",
            f"source: {self.database} (label {self.label})",
        ]
        lines += [
            f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}"
            for check in self.checks
        ]
        passed = sum(check.passed for check in self.checks)
        lines.append(
            f"{len(self.checks)} checks: {passed} passed, {len(self.checks) - passed} failed"
        )
        return "\n".join(lines)


# --- source-side expectations -------------------------------------------------------------------


def graph_identity(graph: str) -> GraphIdentity | None:
    """The identity a backtest graph name carries, or ``None`` for any other name."""
    match = _GRAPH.fullmatch(graph)
    if match is None:
        return None
    return GraphIdentity(match.group("label"), match.group("window"), int(match.group("run")))


def selection_graph_identity(graph: str) -> GraphIdentity | None:
    """The identity a selection graph name carries, or ``None`` for any other name."""
    match = _SELECTION_GRAPH.fullmatch(graph)
    if match is None:
        return None
    return GraphIdentity(match.group("label"), match.group("window"), int(match.group("run")))


def _run_rows(rows: Sequence[Row], run_id: int) -> list[Row]:
    """The rows of one backtest run (the other seven views all carry ``backtest_run_id``)."""
    selected: list[Row] = []
    for row in rows:
        value = row.get("backtest_run_id")
        if value is None:
            continue
        try:
            if int(value) == run_id:
                selected.append(row)
        except (TypeError, ValueError):
            continue
    return selected


def _decimal(value: object, where: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise VerificationError(f"{where}: {value!r} is not a decimal") from None
    if not number.is_finite():
        raise VerificationError(f"{where}: {value!r} is not finite")
    return number


def _unlinked_weights(rows: Sequence[Row], assets: Mapping[str, AssetInfo]) -> int:
    return sum(
        1
        for row in rows
        if str(row.get("holding_key")) != _CASH and str(row.get("holding_key")) not in assets
    )


def _unlinked_guard(rows: Sequence[Row], assets: Mapping[str, AssetInfo]) -> int:
    return sum(
        1 for row in rows if row.get("ticker") is not None and str(row["ticker"]) not in assets
    )


def _expected_links(
    weights: Sequence[Row],
    alerts: Sequence[Row],
    actions: Sequence[Row],
    assets: Mapping[str, AssetInfo],
) -> tuple[int, int]:
    """The distinct linked tickers the source expects for ``:holdingAsset`` and ``:guardAsset``."""
    holdings = {
        str(row["holding_key"])
        for row in weights
        if str(row.get("holding_key")) != _CASH and str(row.get("holding_key")) in assets
    }
    guard = {
        str(row["ticker"])
        for row in (*alerts, *actions)
        if row.get("ticker") is not None and str(row["ticker"]) in assets
    }
    return len(holdings), len(guard)


def _expected_alert_groups(rows: Sequence[Row]) -> Counter[tuple[str, str, str]]:
    return Counter((str(row["rule_id"]), str(int(row["layer"])), str(row["state"])) for row in rows)


def _expected_action_statuses(rows: Sequence[Row]) -> Counter[str]:
    return Counter(str(row["status"]) for row in rows)


def _last_nav(rows: Sequence[Row]) -> dict[str, tuple[str, Decimal]]:
    """The last performance date and NAV of each arm (the source expects one per arm)."""
    last: dict[str, tuple[str, Decimal]] = {}
    for row in rows:
        arm = str(row["arm_code"])
        day = str(row["date"])
        nav = _decimal(row["nav"], f"v_book_daily_performance {arm} {day}")
        current = last.get(arm)
        if current is None or day > current[0]:
            last[arm] = (day, nav)
        elif day == current[0] and nav != current[1]:
            raise VerificationError(
                f"v_book_daily_performance {arm} {day}: two NAV values ({current[1]}, {nav})"
            )
    return last


def _cash_rows(rows: Sequence[Row]) -> int:
    return sum(1 for row in rows if str(row.get("holding_key")) == _CASH)


def _source_guard_summaries(
    books: Sequence[Row],
    summaries: Sequence[Row],
    actions: Sequence[Row],
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """``(book, arm, segment) -> (stored summary count, source APPLIED count)``.

    An ``APPLIED`` action counts for a segment when its ``decision_date`` lies inside
    ``[date_from, date_to]`` inclusive. This is deliberately not ``effective_date``: the summary
    uses the decision session, so an action decided before the segment and effective on its first
    day stays outside (the pilot P2 279-vs-280 case, Work item 34).
    """
    arms = {int(row["book_id"]): str(row["arm_code"]) for row in books}
    expected: dict[tuple[str, str, str], tuple[int, int]] = {}
    for row in summaries:
        book = int(row["book_id"])
        arm = arms.get(book)
        if arm is None:
            raise VerificationError(f"v_portfolio_period_summary book_id {book} is not in v_book")
        date_from, date_to = str(row["date_from"]), str(row["date_to"])
        computed = sum(
            1
            for action in actions
            if int(action["book_id"]) == book
            and str(action["status"]) == "APPLIED"
            and date_from <= str(action["decision_date"]) <= date_to
        )
        key = (str(book), arm, str(row["segment"]))
        if key in expected:
            raise VerificationError(
                f"v_portfolio_period_summary: two rows for book {book}, arm {arm}, "
                f"segment {row['segment']}"
            )
        expected[key] = (int(row["n_guard_actions"]), computed)
    return expected


def _basing_points_alerts(alerts: Sequence[Row]) -> int:
    return sum(1 for row in alerts if str(row.get("rule_id", "")).startswith("L1_BP_"))


# --- store-side reads ---------------------------------------------------------------------------


def _scalar(store: ReadableStore, graph: str, expression: str, pattern: str) -> int:
    query = (
        f"{PREFIX}SELECT ({expression} AS ?n) FROM <{EXPLICIT_GRAPH}> "  # noqa: S608
        f"WHERE {{ GRAPH <{graph}> {{ {pattern} }} }}"
    )
    rows = store.select(query)
    if len(rows) != 1 or "n" not in rows[0]:
        raise VerificationError(f"the store did not answer the count query for {graph}")
    return int(rows[0]["n"])


def _count(store: ReadableStore, graph: str, pattern: str) -> int:
    """Distinct subjects matching ``pattern`` (one per individual the check names)."""
    return _scalar(store, graph, "COUNT(DISTINCT ?s)", pattern)


def _select(
    store: ReadableStore, graph: str, projection: str, pattern: str, group_by: str = ""
) -> list[dict[str, str]]:
    query = (
        f"{PREFIX}SELECT {projection} FROM <{EXPLICIT_GRAPH}> "  # noqa: S608
        f"WHERE {{ GRAPH <{graph}> {{ {pattern} }} }}"
        + (f" GROUP BY {group_by}" if group_by else "")
    )
    return store.select(query)


def _store_book_identities(store: ReadableStore, graph: str) -> set[tuple[str, str, str]]:
    rows = _select(
        store,
        graph,
        "DISTINCT ?label ?window ?run",
        "?s a :StrategyBook ; :runLabel ?label ; :windowId ?window ; :backtestRunId ?run .",
    )
    return {
        (row["label"], row["window"], row["run"])
        for row in rows
        if {"label", "window", "run"} <= row.keys()
    }


def _store_alert_groups(
    store: ReadableStore, graph: str, catalog: GuardCatalog
) -> Counter[tuple[str, str, str]]:
    """The stored alerts grouped by rule id, layer and state (the rule IRI is resolved locally)."""
    rows = _select(
        store,
        graph,
        "?rule_iri ?layer ?state (COUNT(DISTINCT ?s) AS ?n)",
        "?s a :GuardAlert ; :alertRule ?rule_iri ; :guardLayer ?layer ; :alertState ?state .",
        "?rule_iri ?layer ?state",
    )
    by_iri = {str(rule.iri): rule_id for rule_id, rule in catalog.by_id.items()}
    groups = Counter[tuple[str, str, str]]()
    for row in rows:
        rule = by_iri.get(row["rule_iri"], row["rule_iri"])
        groups[(rule, str(int(row["layer"])), row["state"])] += int(row["n"])
    return groups


def _store_action_statuses(store: ReadableStore, graph: str) -> Counter[str]:
    rows = _select(
        store,
        graph,
        "?status (COUNT(DISTINCT ?s) AS ?n)",
        "?s a :GuardAction ; :status ?status .",
        "?status",
    )
    return Counter({row["status"]: int(row["n"]) for row in rows})


def _store_guard_summaries(
    store: ReadableStore, graph: str
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """``(book, arm, segment) -> (stored summary count, stored APPLIED count)``."""
    summaries = _select(
        store,
        graph,
        "?book ?arm ?segment ?n ?dateFrom ?dateTo",
        "?s a :PortfolioPeriodSummary ; :bookId ?book ; :armCode ?arm ; :segment ?segment ; "
        ":dateFrom ?dateFrom ; :dateTo ?dateTo ; :nGuardActions ?n .",
    )
    actions = _select(
        store,
        graph,
        "?book ?arm ?date",
        "?s a :GuardAction ; :bookId ?book ; :armCode ?arm ; :decisionDate ?date ; "
        ':status "APPLIED" .',
    )
    counts = Counter((row["book"], row["arm"], row["date"]) for row in actions)
    stored: dict[tuple[str, str, str], tuple[int, int]] = {}
    for row in summaries:
        book, arm, segment = str(int(row["book"])), row["arm"], row["segment"]
        computed = sum(
            count
            for (action_book, action_arm, day), count in counts.items()
            if action_book == book and action_arm == arm and row["dateFrom"] <= day <= row["dateTo"]
        )
        stored[(book, arm, segment)] = (int(row["n"]), computed)
    return stored


def _store_last_nav(store: ReadableStore, graph: str) -> dict[str, tuple[str, Decimal]]:
    rows = _select(
        store,
        graph,
        "?arm ?date ?nav",
        "?s a :BookDailyPerformance ; :armCode ?arm ; :performanceDate ?date ; :nav ?nav .",
    )
    last: dict[str, tuple[str, Decimal]] = {}
    for row in rows:
        arm, day, nav = (
            row["arm"],
            row["date"],
            _decimal(row["nav"], f"stored NAV {row['arm']}"),
        )
        current = last.get(arm)
        if current is None or day > current[0]:
            last[arm] = (day, nav)
    return last


# --- selection-side expectations ----------------------------------------------------------------


def _subjects_of_type(builder: GraphBuilder, class_name: str) -> set[rdflib.URIRef]:
    wanted = _KG[class_name]
    return {
        subject
        for subject, predicate, value in builder.triples
        if predicate == rdflib.RDF.type and value == wanted and isinstance(subject, rdflib.URIRef)
    }


def _linked_objects(builder: GraphBuilder, predicate: rdflib.URIRef) -> set[rdflib.URIRef]:
    return {
        value
        for _, stored, value in builder.triples
        if stored == predicate and isinstance(value, rdflib.URIRef)
    }


def _expected_placeholders(builder: GraphBuilder) -> int:
    """Snapshots the projector leaves without an effective weight (the 0.0 placeholders)."""
    snapshots = _subjects_of_type(builder, "AttractivenessSnapshot")
    weighted = {
        subject for subject, predicate, _ in builder.triples if predicate == _KG.hasEffectiveWeight
    }
    return len(snapshots - weighted)


def _expected_veto_groups(builder: GraphBuilder) -> Counter[str]:
    """Vetoes grouped by the resolved rule IRI the projector wrote."""
    vetoes = _subjects_of_type(builder, "Veto")
    groups: Counter[str] = Counter()
    for subject, predicate, value in builder.triples:
        if subject in vetoes and predicate == _KG.appliesRule:
            groups[str(value)] += 1
    return groups


def _store_selection_identities(store: ReadableStore, graph: str) -> set[tuple[str, str, str]]:
    rows = _select(
        store,
        graph,
        "DISTINCT ?label ?window ?run",
        "?s a :SelectionCycle ; :runLabel ?label ; :windowId ?window ; :backtestRunId ?run .",
    )
    return {
        (row["label"], row["window"], row["run"])
        for row in rows
        if {"label", "window", "run"} <= row.keys()
    }


def _store_veto_groups(store: ReadableStore, graph: str) -> Counter[str]:
    rows = _select(
        store,
        graph,
        "?rule (COUNT(DISTINCT ?s) AS ?n)",
        "?s a :Veto ; :appliesRule ?rule .",
        "?rule",
    )
    return Counter({row["rule"]: int(row["n"]) for row in rows})


def _cycle_ids(rows: Sequence[Mapping[str, str]]) -> set[str]:
    """The canonical text of each ``?cycle`` value (a stored ``xsd:integer`` or a literal)."""
    return {str(int(row["cycle"])) for row in rows if row.get("cycle")}


def _store_cycle_ids(store: ReadableStore, graph: str, pattern: str) -> set[str]:
    return _cycle_ids(_select(store, graph, "DISTINCT ?cycle", pattern))


# --- the verifier -------------------------------------------------------------------------------


def _describe_difference(expected: Mapping[Any, Any], actual: Mapping[Any, Any]) -> str:
    """A short, deterministic account of a mapping difference."""
    missing = sorted(set(expected) - set(actual), key=str)
    extra = sorted(set(actual) - set(expected), key=str)
    changed = sorted(
        (key for key in set(expected) & set(actual) if expected[key] != actual[key]),
        key=str,
    )
    parts = [f"{len(expected)} expected, {len(actual)} stored"]
    if missing:
        parts.append(f"missing {len(missing)}: {missing[:3]}")
    if extra:
        parts.append(f"extra {len(extra)}: {extra[:3]}")
    if changed:
        parts.append(f"different {len(changed)}: {changed[:3]}")
    return "; ".join(parts)


def verify(  # noqa: C901, PLR0912, PLR0913, PLR0915 -- the one public verifier
    store: ReadableStore,
    graph: str,
    db_path: str | Path,
    label: str,
    *,
    assets: Mapping[str, AssetInfo] | None = None,
    catalog: GuardCatalog | None = None,
    selection_catalog: SelectionRuleCatalog | None = None,
    repository: str = "",
    host: str = "",
) -> Verification:
    """Re-project ``db_path`` in memory and compare it with ``graph`` in ``store``.

    ``assets``, ``catalog`` and ``selection_catalog`` default to the configured universe database
    and ``schema/rules.ttl``, exactly as the projectors read them; tests pass fixtures. The source
    is opened read-only by :class:`projection.source.FinancialSource`; the store is only asked
    ``SELECT`` queries. A selection graph dispatches to :func:`verify_selection`; every other name
    follows the m018 path unchanged.
    """
    if not re.fullmatch(RUN_LABEL_PATTERN, label):
        raise VerificationError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    if graph.startswith(SELECTION_GRAPH_PREFIX):
        return verify_selection(
            store,
            graph,
            db_path,
            label,
            assets=assets,
            catalog=selection_catalog,
            repository=repository,
            host=host,
        )
    identity = graph_identity(graph)
    if identity is None:
        return Verification(
            repository=repository,
            host=host,
            graph=graph,
            label=label,
            database=Path(db_path),
            checks=[
                Check(
                    "graph",
                    False,
                    f"{graph!r} is not a backtest graph name "
                    f"({GRAPH_PREFIX}{{label}}:{{P<number>}}:{{run id}})",
                )
            ],
        )

    assets = universe_assets(config.universe_db_path()) if assets is None else assets
    catalog = load_guard_catalog(config.schema_dir() / "rules.ttl") if catalog is None else catalog
    source = FinancialSource.open(db_path)
    try:
        source_projection = project_source(source, assets, catalog, label)
    finally:
        source.close()

    rows = source_projection.rows
    projection: Projection = source_projection.projection
    expected_graphs = set(projection.graphs)
    expected_triples = len(projection.graphs[graph].triples) if graph in projection.graphs else None
    stored_triples = _scalar(store, graph, "COUNT(*)", "?s ?p ?o")
    book_identities = _store_book_identities(store, graph)
    wanted_identity = {(label, identity.window, str(identity.run_id))}

    checks: list[Check] = []
    name_problems: list[str] = []
    if identity.label != label:
        name_problems.append(f"the graph's label is {identity.label!r}, not {label!r}")
    if graph not in expected_graphs:
        name_problems.append(
            "the source projects " + (", ".join(sorted(expected_graphs)) or "no graph")
        )
    if stored_triples == 0:
        name_problems.append("the graph does not exist in the store")
    if book_identities != wanted_identity:
        name_problems.append(
            f"stored book metadata {sorted(book_identities)} is not {sorted(wanted_identity)}"
        )
    checks.append(
        Check(
            "graph",
            not name_problems,
            (
                f"{graph} exists with {stored_triples:,} triples; label, window "
                f"{identity.window} and run {identity.run_id} agree"
                if not name_problems
                else "; ".join(name_problems)
            ),
        )
    )

    if expected_triples is None:
        checks.append(
            Check(
                "triples",
                False,
                f"the source does not project {graph}; it projects "
                + (", ".join(sorted(expected_graphs)) or "nothing"),
            )
        )
    else:
        checks.append(
            Check(
                "triples",
                stored_triples == expected_triples,
                f"{graph}: {stored_triples:,} stored, {expected_triples:,} re-projected",
            )
        )

    # The eight views, one individual per surviving row.
    for view, class_name in VIEW_CLASS:
        expected = len(_run_rows(rows.get(view, ()), identity.run_id))
        stored = _count(store, graph, f"?s a :{class_name} .")
        checks.append(
            Check(
                f"individuals {class_name}",
                stored == expected,
                f"{view}: {stored:,} stored, {expected:,} source rows",
            )
        )

    weights = _run_rows(rows.get("v_book_weight_daily", ()), identity.run_id)
    alerts = _run_rows(rows.get("v_guard_alert", ()), identity.run_id)
    actions = _run_rows(rows.get("v_guard_action", ()), identity.run_id)
    expected_holding_links, expected_guard_links = _expected_links(weights, alerts, actions, assets)
    stored_holding_links = _scalar(
        store, graph, "COUNT(DISTINCT ?asset)", "?s :holdingAsset ?asset ."
    )
    stored_guard_links = _scalar(store, graph, "COUNT(DISTINCT ?asset)", "?s :guardAsset ?asset .")
    checks.append(
        Check(
            "holding links",
            stored_holding_links == expected_holding_links,
            f"distinct tickers with :holdingAsset: {stored_holding_links:,} stored, "
            f"{expected_holding_links:,} expected",
        )
    )
    checks.append(
        Check(
            "guard links",
            stored_guard_links == expected_guard_links,
            f"distinct tickers with :guardAsset: {stored_guard_links:,} stored, "
            f"{expected_guard_links:,} expected",
        )
    )

    for view, expected, pattern in (
        (
            "v_book_weight_daily",
            _unlinked_weights(weights, assets),
            (
                '?s a :BookWeightDaily ; :holdingKey ?key . FILTER (?key != "CASH") '
                "FILTER NOT EXISTS { ?s :holdingAsset ?asset }"
            ),
        ),
        (
            "v_guard_alert",
            _unlinked_guard(alerts, assets),
            (
                "?s a :GuardAlert ; :guardTicker ?ticker . "
                "FILTER NOT EXISTS { ?s :guardAsset ?asset }"
            ),
        ),
        (
            "v_guard_action",
            _unlinked_guard(actions, assets),
            (
                "?s a :GuardAction ; :guardTicker ?ticker . "
                "FILTER NOT EXISTS { ?s :guardAsset ?asset }"
            ),
        ),
    ):
        stored = _count(store, graph, pattern)
        checks.append(
            Check(
                f"unlinked {view}",
                stored <= expected,
                f"{stored:,} stored, {expected:,} reported by the projector"
                + ("" if stored <= expected else " (more unlinked rows than the source allows)"),
            )
        )

    expected_groups = _expected_alert_groups(alerts)
    stored_groups = _store_alert_groups(store, graph, catalog)
    checks.append(
        Check(
            "GuardAlert by rule, layer and state",
            stored_groups == expected_groups,
            _describe_difference(expected_groups, stored_groups),
        )
    )
    expected_statuses = _expected_action_statuses(actions)
    stored_statuses = _store_action_statuses(store, graph)
    checks.append(
        Check(
            "GuardAction by status",
            stored_statuses == expected_statuses,
            _describe_difference(expected_statuses, stored_statuses),
        )
    )

    source_guard = _source_guard_summaries(
        _run_rows(rows.get("v_book", ()), identity.run_id),
        _run_rows(rows.get("v_portfolio_period_summary", ()), identity.run_id),
        actions,
    )
    stored_guard = _store_guard_summaries(store, graph)
    source_inconsistent = {
        key: value for key, value in source_guard.items() if value[0] != value[1]
    }
    stored_inconsistent = {
        key: value for key, value in stored_guard.items() if value[0] != value[1]
    }
    guard_problems: list[str] = []
    if source_guard != stored_guard:
        guard_problems.append(_describe_difference(source_guard, stored_guard))
    if source_inconsistent:
        guard_problems.append(
            "source summary differs from its APPLIED-by-decision-date count: "
            + ", ".join(
                f"{key} {value[0]}!={value[1]}"
                for key, value in sorted(source_inconsistent.items())
            )
        )
    if stored_inconsistent:
        guard_problems.append(
            "stored summary differs from its APPLIED-by-decision-date count: "
            + ", ".join(
                f"{key} {value[0]}!={value[1]}"
                for key, value in sorted(stored_inconsistent.items())
            )
        )
    checks.append(
        Check(
            "nGuardActions by decision date",
            not guard_problems,
            (
                f"{len(stored_guard)} (book, arm, segment) summary row(s): source and graph "
                "APPLIED counts inside [dateFrom, dateTo] agree with :nGuardActions"
                if not guard_problems
                else "; ".join(guard_problems)
            ),
        )
    )

    expected_basing_points = _basing_points_alerts(alerts)
    basing_points_pattern = (
        '?s a :GuardAlert ; :alertRule ?rule . FILTER (CONTAINS(STR(?rule), "#Rule_L1_BP_"))'
    )
    stored_basing_points = _scalar(store, graph, "COUNT(DISTINCT ?s)", basing_points_pattern)
    stored_basing_thresholds = _scalar(
        store,
        graph,
        "COUNT(DISTINCT ?s)",
        basing_points_pattern + " ?s :alertThreshold ?threshold .",
    )
    publication_ok = (
        stored_basing_points == expected_basing_points and stored_basing_thresholds == 0
    )
    checks.append(
        Check(
            "Basing Points publication",
            publication_ok,
            f"{stored_basing_points:,} stored, {expected_basing_points:,} source "
            f"L1_BP_* alerts; {stored_basing_thresholds:,} :alertThreshold triple(s)",
        )
    )

    expected_nav = _last_nav(_run_rows(rows.get("v_book_daily_performance", ()), identity.run_id))
    stored_nav = _store_last_nav(store, graph)
    nav_details = ", ".join(
        f"{arm}: {stored_nav.get(arm, ('missing', Decimal(0)))[0]} "
        f"{stored_nav.get(arm, ('missing', Decimal(0)))[1]}"
        for arm in sorted(set(expected_nav) | set(stored_nav))
    )
    checks.append(
        Check(
            "last NAV per arm",
            stored_nav == expected_nav,
            f"{len(stored_nav)} stored, {len(expected_nav)} expected"
            + (f" ({nav_details})" if nav_details else ""),
        )
    )
    expected_cash = _cash_rows(weights)
    stored_cash = _count(store, graph, '?s a :BookWeightDaily ; :holdingKey "CASH" .')
    checks.append(
        Check(
            "CASH rows",
            stored_cash == expected_cash,
            f"{stored_cash:,} stored, {expected_cash:,} source rows",
        )
    )

    missing_labels = _count(
        store,
        graph,
        "VALUES ?type { :StrategyBook :BookRebalance :GuardAction :BookWeightDaily "
        ":BookDailyPerformance :PortfolioPeriodSummary :BacktestTest } "
        "?s a ?type . "
        "FILTER NOT EXISTS { { ?s :runLabel ?label } UNION { ?s ?link ?book . "
        "VALUES ?link { :rebalanceOfBook :actionOfBook :weightOfBook :performanceOfBook "
        ":summaryOfBook } ?book :runLabel ?label } }",
    )
    checks.append(
        Check(
            "runLabel through the book",
            missing_labels == 0,
            f"{missing_labels:,} individual(s) without a direct or book-linked :runLabel",
        )
    )
    missing_dates = _count(
        store,
        graph,
        "VALUES ?type { :StrategyBook :BookRebalance :GuardAlert :GuardAction :BookWeightDaily "
        ":BookDailyPerformance :PortfolioPeriodSummary :BacktestTest } "
        "?s a ?type . FILTER NOT EXISTS { ?s :knowledgeDate ?date }",
    )
    checks.append(
        Check(
            "knowledgeDate",
            missing_dates == 0,
            f"{missing_dates:,} individual(s) without :knowledgeDate",
        )
    )

    return Verification(
        repository=repository,
        host=host,
        graph=graph,
        label=label,
        database=Path(db_path),
        checks=checks,
        triples=stored_triples,
    )


# --- the selection-side verifier ----------------------------------------------------------------


def verify_selection(  # noqa: C901, PLR0912, PLR0913, PLR0915 -- the one selection verifier
    store: ReadableStore,
    graph: str,
    db_path: str | Path,
    label: str,
    *,
    assets: Mapping[str, AssetInfo] | None = None,
    catalog: SelectionRuleCatalog | None = None,
    repository: str = "",
    host: str = "",
) -> Verification:
    """Re-project the selection views and compare them with one selection graph.

    The source's exact projector (:func:`projection.backtest.project_selection_source`) supplies
    every expected count, link and group. The m018 sibling is derived from the selection graph's
    own label/window/run id; the cross-graph check fails when it is absent, because then the
    proof that each TOPN rebalance points at a projected cycle cannot be made.
    """
    identity = selection_graph_identity(graph)
    if identity is None:
        return Verification(
            repository=repository,
            host=host,
            graph=graph,
            label=label,
            database=Path(db_path),
            checks=[
                Check(
                    "graph",
                    False,
                    f"{graph!r} is not a selection graph name "
                    f"({SELECTION_GRAPH_PREFIX}{{label}}:{{P<number>}}:{{run id}})",
                )
            ],
        )

    assets = universe_assets(config.universe_db_path()) if assets is None else assets
    catalog = (
        load_selection_catalog(config.schema_dir() / "rules.ttl") if catalog is None else catalog
    )
    source = FinancialSource.open(db_path)
    try:
        source_projection = project_selection_source(source, assets, catalog, label)
    finally:
        source.close()

    rows = source_projection.rows
    projection = source_projection.projection
    expected_graphs = set(projection.graphs)
    builder = projection.graphs.get(graph)
    expected_triples = len(builder.triples) if builder is not None else None
    stored_triples = _scalar(store, graph, "COUNT(*)", "?s ?p ?o")
    identities = _store_selection_identities(store, graph)
    wanted_identity = {(label, identity.window, str(identity.run_id))}

    checks: list[Check] = []
    name_problems: list[str] = []
    if identity.label != label:
        name_problems.append(f"the graph's label is {identity.label!r}, not {label!r}")
    if graph not in expected_graphs:
        name_problems.append(
            "the source projects " + (", ".join(sorted(expected_graphs)) or "no selection graph")
        )
    if stored_triples == 0:
        name_problems.append("the graph does not exist in the store")
    if identities != wanted_identity:
        name_problems.append(
            f"stored cycle metadata {sorted(identities)} is not {sorted(wanted_identity)}"
        )
    checks.append(
        Check(
            "graph",
            not name_problems,
            (
                f"{graph} exists with {stored_triples:,} triples; label, window "
                f"{identity.window} and run {identity.run_id} agree"
                if not name_problems
                else "; ".join(name_problems)
            ),
        )
    )

    if expected_triples is None:
        checks.append(
            Check(
                "triples",
                False,
                f"the source does not project {graph}; it projects "
                + (", ".join(sorted(expected_graphs)) or "nothing"),
            )
        )
    else:
        checks.append(
            Check(
                "triples",
                stored_triples == expected_triples,
                f"{graph}: {stored_triples:,} stored, {expected_triples:,} re-projected",
            )
        )

    def count_check(
        name: str,
        expected: int,
        pattern: str,
        detail: str,
        expression: str = "COUNT(DISTINCT ?s)",
    ) -> None:
        stored = _scalar(store, graph, expression, pattern)
        checks.append(
            Check(name, stored == expected, f"{detail}: {stored:,} stored, {expected:,} expected")
        )

    count_check(
        "individuals SelectionCycle",
        len(rows.get("v_cycle_run", ())),
        "?s a :SelectionCycle .",
        "v_cycle_run",
    )
    count_check(
        "individuals AttractivenessSnapshot",
        projection.individuals["AttractivenessSnapshot"],
        "?s a :AttractivenessSnapshot .",
        "v_cycle_ranking projected",
    )
    count_check(
        "individuals AttractivenessWeightScheme",
        len(rows.get("v_weight_scheme", ())),
        "?s a :AttractivenessWeightScheme .",
        "v_weight_scheme",
    )
    count_check(
        "individuals Veto",
        len(rows.get("v_veto", ())),
        "?s a :Veto .",
        "v_veto",
    )
    if builder is not None:
        expected_effective = len(_linked_objects(builder, _KG.hasEffectiveWeight))
        expected_configured = len(_linked_objects(builder, _KG.hasWeightComponent))
        expected_attractiveness_links = len(_linked_objects(builder, _KG.attractivenessOfAsset))
        expected_veto_links = len(_linked_objects(builder, _KG.vetoOfAsset))
        expected_placeholders = _expected_placeholders(builder)
    else:
        expected_effective = expected_configured = 0
        expected_attractiveness_links = expected_veto_links = 0
        expected_placeholders = 0

    count_check(
        "effective WeightComponent",
        expected_effective,
        "?snapshot :hasEffectiveWeight ?component .",
        "v_cycle_ranking_component",
        "COUNT(DISTINCT ?component)",
    )
    count_check(
        "configured WeightComponent",
        expected_configured,
        "?scheme :hasWeightComponent ?component .",
        "v_weight_component",
        "COUNT(DISTINCT ?component)",
    )
    count_check(
        "UNSCORED/UNPRICED placeholders",
        expected_placeholders,
        "?s a :AttractivenessSnapshot ; :vetoRulesJson ?rules . "
        "FILTER NOT EXISTS { ?s :hasEffectiveWeight ?component } "
        'FILTER (CONTAINS(STR(?rules), "UNSCORED") || CONTAINS(STR(?rules), "UNPRICED"))',
        "snapshots without :hasEffectiveWeight",
    )
    count_check(
        "attractiveness links",
        expected_attractiveness_links,
        "?s :attractivenessOfAsset ?asset .",
        "distinct tickers with :attractivenessOfAsset",
        "COUNT(DISTINCT ?asset)",
    )
    count_check(
        "veto links",
        expected_veto_links,
        "?s :vetoOfAsset ?asset .",
        "distinct tickers with :vetoOfAsset",
        "COUNT(DISTINCT ?asset)",
    )

    for view, expected, pattern in (
        (
            "v_cycle_ranking",
            projection.asset_unlinked["v_cycle_ranking"],
            (
                "?s a :AttractivenessSnapshot ; :rankingTicker ?ticker . "
                "FILTER NOT EXISTS { ?s :attractivenessOfAsset ?asset }"
            ),
        ),
        (
            "v_veto",
            projection.asset_unlinked["v_veto"],
            ("?s a :Veto ; :vetoTicker ?ticker . FILTER NOT EXISTS { ?s :vetoOfAsset ?asset }"),
        ),
    ):
        stored = _count(store, graph, pattern)
        checks.append(
            Check(
                f"unlinked {view}",
                stored <= expected,
                f"{stored:,} stored, {expected:,} reported by the projector"
                + ("" if stored <= expected else " (more unlinked rows than the source allows)"),
            )
        )

    expected_groups = _expected_veto_groups(builder) if builder is not None else Counter[str]()
    stored_groups = _store_veto_groups(store, graph)
    checks.append(
        Check(
            "vetoes by resolved rule",
            stored_groups == expected_groups,
            _describe_difference(expected_groups, stored_groups),
        )
    )

    m018_graph = graph_name(identity.label, identity.window, identity.run_id)
    rebalances = _select(
        store,
        m018_graph,
        "DISTINCT ?arm ?cycle",
        "?r a :BookRebalance ; :cycleRunId ?cycle ; :rebalanceOfBook ?book . "
        "?book a :StrategyBook ; :armCode ?arm .",
    )
    # Work item 34: both MARKOWITZ arms are independent controls with no cycle link; every other
    # arm (TOPN_MV_NOGUARD, TOPN_MV_GUARD_NO_NLP, TOPN_MV_GUARD) shares the replay cycle.
    markowitz = [row for row in rebalances if str(row.get("arm", "")).startswith("MARKOWITZ")]
    topn_cycles = _cycle_ids(
        [row for row in rebalances if not str(row.get("arm", "")).startswith("MARKOWITZ")]
    )
    selection_cycles = _store_cycle_ids(
        store,
        graph,
        "?s a :SelectionCycle ; :cycleRunId ?cycle .",
    )
    missing_cycles = topn_cycles - selection_cycles
    cross_problems: list[str] = []
    if not rebalances:
        cross_problems.append(f"{m018_graph} has no BookRebalance with a :cycleRunId")
    if markowitz:
        cross_problems.append(f"a MARKOWITZ arm has {len(markowitz)} cycle link(s)")
    if missing_cycles:
        cross_problems.append(
            "missing SelectionCycle for cycle " + ", ".join(sorted(missing_cycles, key=int))
        )
    checks.append(
        Check(
            "cross-graph SelectionCycle",
            not cross_problems,
            (
                f"{len(topn_cycles)} TOPN cycle id(s) from {m018_graph} are in this graph; "
                "the MARKOWITZ arms have 0"
                if not cross_problems
                else "; ".join(cross_problems)
            ),
        )
    )

    return Verification(
        repository=repository,
        host=host,
        graph=graph,
        label=label,
        database=Path(db_path),
        checks=checks,
        triples=stored_triples,
    )


# --- the command line ---------------------------------------------------------------------------


def _label(text: str) -> str:
    if not re.fullmatch(RUN_LABEL_PATTERN, text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in rule)"
        )
    return text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--graph",
        required=True,
        metavar="GRAPH",
        help="the stored graph to verify, e.g. urn:graph:derived:backtest:rule:P1:1",
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        metavar="PATH",
        help="the completed backtest database the graph was projected from",
    )
    parser.add_argument(
        "--label",
        required=True,
        type=_label,
        metavar="LABEL",
        help="the run label used when the graph was projected ([a-z][a-z0-9_]{1,31})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        store = GraphDB.from_env()
        verification = verify(
            store,
            args.graph,
            args.db,
            args.label,
            repository=store.repository,
            host=store.host,
        )
    except (BoundaryError, ProjectionError, VerificationError) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:  # a missing database, or one without the m018 views
        print(f"source error: {exc} (--db PATH)", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    print(verification.summary())
    return 0 if verification.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
