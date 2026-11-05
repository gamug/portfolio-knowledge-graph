"""``v_ticker_history``, ``v_orchestrator_run`` and ``v_orchestrator_step`` -> named graphs (T-352/T-353).

The three views are not m018 output. ``v_ticker_history`` (m016) is reference-like: a snapshot of
the symbols each CIK line used over inclusive intervals. The two m015 orchestrator views are
process provenance: one immutable record per run and per step. This module reads them through the
boundary, builds deterministic Turtle and writes one graph per ticker-history snapshot and one
graph per orchestrator run.

Ticker history lives in ``urn:graph:derived:ticker-history:{label}:{snapshot_date}``. The snapshot
is append-only; a later refresh writes a new graph, never an edit. Because the gate also refuses a
typed individual that already exists in any graph, every ``TickerHistory`` IRI carries the label and
the snapshot date: ``TickerHistory_{label}_{YYYYMMDD}_{cik}_{symbol}_{validFrom}``. A stable IRI
would make the second snapshot impossible even though its graph name is new.

An orchestrator run lives in ``urn:graph:derived:orchestrator:{label}:{run_id}`` with
``OrchestratorRun_{label}_{run_id}`` and ``OrchestratorStep_{label}_{run_id}_{ordinal}``. A later
run has a new id and a new graph, never an append to the previous one.

``:tickerHistoryAsset`` is resolved by :func:`projection.asset_link.resolve_asset`: the exact
canonical symbol first, then the one loaded ``:Asset`` carrying the row's CIK (``FBIN`` ->
``:FBHS``, ``GAP`` -> ``:GPS``), otherwise no link and a count. No asset is invented.

Every optional view column is omitted when NULL, never filled. A multi-date
``v_ticker_history.evidence_date`` is not one ``xsd:date``: that property is omitted and counted.
The two orchestrator views may be empty: then no orchestrator graph is built and the report says
there is nothing to write.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import rdflib
from rdflib.namespace import RDF, XSD
from rdflib.term import Node

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.asset_link import resolve_asset
from projection.backtest import (
    RUN_LABEL_PATTERN,
    AssetInfo,
    GraphBuilder,
    ProjectionError,
)
from projection.boundary import (
    BoundaryReport,
    Row,
    check_schema_floor,
    validate,
)
from projection.expectations import load_expectations, load_source
from projection.source import FinancialSource
from projection.view_contract import VIEW_COLUMNS

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

#: The three Contract v18 views this projector reads, in report order.
VIEWS = ("v_ticker_history", "v_orchestrator_run", "v_orchestrator_step")

#: The natural-key order each view is read in, so the Turtle is deterministic.
ORDER: dict[str, tuple[str, ...]] = {
    "v_ticker_history": ("cik", "symbol", "valid_from"),
    "v_orchestrator_run": ("run_id",),
    "v_orchestrator_step": ("orchestrator_run_id", "ordinal"),
}

TICKER_GRAPH_PREFIX = "urn:graph:derived:ticker-history:"
ORCHESTRATOR_GRAPH_PREFIX = "urn:graph:derived:orchestrator:"

_RUN_LABEL = re.compile(RUN_LABEL_PATTERN)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SAFE_PART = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


class StoreInterrupted(RuntimeError):
    """The store failed partway through the writes; ``result`` holds what was done before it."""

    def __init__(self, result: ReferenceRunResult, cause: Exception) -> None:
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


# --- identifiers and values ---------------------------------------------------------------------


def _n3(term: Node) -> str:
    return term.n3()


def _name(term: Node) -> str:
    if isinstance(term, rdflib.URIRef) and str(term).startswith(NS):
        local = str(term)[len(NS) :]
        if _SAFE_PART.fullmatch(local):
            return f":{local}"
    return _n3(term)


def _safe(value: object, what: str, where: str) -> str:
    text = str(value)
    if not _SAFE_PART.fullmatch(text):
        raise ProjectionError(f"{where}: {what} {text!r} cannot form a valid IRI local name")
    return text


def _where(view: str, row: Row, key: str) -> str:
    return f"{view} {key}={row.get(key)}"


def _required(row: Row, column: str, where: str) -> Any:
    value = row.get(column)
    if value is None:
        raise ProjectionError(f"{where}: {column} is NULL")
    return value


def _text(value: object, column: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionError(f"{where}: {column} {value!r} is not a non-empty string")
    return value


def _day(value: object, column: str, where: str) -> str:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ProjectionError(f"{where}: {column} {value!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise ProjectionError(f"{where}: {column} {value!r} is not a real date") from None
    return value


def _integer(value: object, column: str, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectionError(f"{where}: {column} {value!r} is not an integer")
    return value


def _positive(value: object, column: str, where: str) -> int:
    number = _integer(value, column, where)
    if number < 1:
        raise ProjectionError(f"{where}: {column} {number!r} is not a positive integer")
    return number


def _datetime(value: object, column: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionError(f"{where}: {column} {value!r} is not an ISO 8601 timestamp")
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise ProjectionError(f"{where}: {column} {value!r} is not an ISO 8601 timestamp") from None
    return parsed.isoformat()


def _day_lit(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.date)


def _datetime_lit(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.dateTime)


def _int_lit(value: int) -> rdflib.Literal:
    return rdflib.Literal(str(value), datatype=XSD.integer)


def _uri_lit(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.anyURI)


def _snapshot_key(snapshot: str) -> str:
    return snapshot.replace("-", "")


def ticker_graph_name(label: str, snapshot: str) -> str:
    """The append-only graph of one ticker-history snapshot (``docs/07``)."""
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    _day(snapshot, "snapshot_date", "ticker history snapshot")
    return f"{TICKER_GRAPH_PREFIX}{label}:{snapshot}"


def orchestrator_graph_name(label: str, run_id: int) -> str:
    """The append-only graph of one orchestrator run (``docs/07``)."""
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ProjectionError(f"orchestrator run_id {run_id!r} is not a positive integer")
    return f"{ORCHESTRATOR_GRAPH_PREFIX}{label}:{run_id}"


def _ticker_iri(label: str, snapshot: str, cik: str, symbol: str, valid_from: str) -> rdflib.URIRef:
    return KG[
        f"TickerHistory_{label}_{_snapshot_key(snapshot)}_"
        f"{cik}_{symbol}_{valid_from.replace('-', '')}"
    ]


def _run_iri(label: str, run_id: int) -> rdflib.URIRef:
    return KG[f"OrchestratorRun_{label}_{run_id}"]


def _step_iri(label: str, run_id: int, ordinal: int) -> rdflib.URIRef:
    return KG[f"OrchestratorStep_{label}_{run_id}_{ordinal}"]


# --- the projection -----------------------------------------------------------------------------


@dataclass
class Projection:
    """The per-graph batches and the counts a dry run or write reports."""

    graphs: dict[str, GraphBuilder] = field(default_factory=dict)
    rows: Counter[str] = field(default_factory=Counter)
    individuals: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    asset_exact: Counter[str] = field(default_factory=Counter)
    asset_cik: Counter[str] = field(default_factory=Counter)
    asset_unlinked: Counter[str] = field(default_factory=Counter)

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


@dataclass(frozen=True)
class _Ticker:
    row: Row
    cik: str
    symbol: str
    valid_from: str
    valid_to: str | None
    canonical: str
    iri: rdflib.URIRef


def _ticker_rows(rows: Sequence[Row], label: str, snapshot: str) -> list[_Ticker]:
    tickers: list[_Ticker] = []
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_ticker_history", row, "cik")
        cik = _safe(_text(_required(row, "cik", where), "cik", where), "cik", where)
        symbol = _safe(_text(_required(row, "symbol", where), "symbol", where), "symbol", where)
        valid_from = _day(_required(row, "valid_from", where), "valid_from", where)
        valid_to_value = row.get("valid_to")
        valid_to = None if valid_to_value is None else _day(valid_to_value, "valid_to", where)
        if valid_to is not None and valid_to < valid_from:
            raise ProjectionError(f"{where}: valid_to {valid_to} is before valid_from {valid_from}")
        canonical = _text(_required(row, "canonical_symbol", where), "canonical_symbol", where)
        iri = _ticker_iri(label, snapshot, cik, symbol, valid_from)
        if iri in seen:
            raise ProjectionError(f"{where}: two rows would share the IRI {_n3(iri)}")
        seen.add(iri)
        tickers.append(_Ticker(row, cik, symbol, valid_from, valid_to, canonical, iri))
    return tickers


def _check_canonical_latest(tickers: Sequence[_Ticker]) -> None:
    """Refuse a latest row whose canonical symbol is not one of the CIK line's latest symbols.

    Older rows may carry another canonical symbol on purpose: in a mixed CIK such as
    ``DISCA``/``DISCK``/``WBD`` the concurrent ``DISCK`` keeps its own symbol while the later
    ``WBD`` row carries ``WBD``. The invariant is on the latest row(s): a pure rename's latest
    symbol must be the canonical one, and a tie must include the canonical symbol.
    """
    by_cik: defaultdict[str, list[_Ticker]] = defaultdict(list)
    for ticker in tickers:
        by_cik[ticker.cik].append(ticker)
    for cik, group in sorted(by_cik.items()):
        latest = max(ticker.valid_from for ticker in group)
        latest_rows = [ticker for ticker in group if ticker.valid_from == latest]
        latest_symbols = {ticker.symbol for ticker in latest_rows}
        for ticker in latest_rows:
            if ticker.canonical not in latest_symbols:
                named = ", ".join(sorted(latest_symbols))
                raise ProjectionError(
                    f"v_ticker_history cik={cik}: canonical_symbol {ticker.canonical!r} is "
                    f"not the latest symbol ({named}, from {latest}); refusing to project a "
                    "disagreement"
                )


def _ticker_history(
    rows: Sequence[Row],
    assets: Mapping[str, AssetInfo],
    label: str,
    snapshot: str,
    out: Projection,
) -> None:
    tickers = _ticker_rows(rows, label, snapshot)
    _check_canonical_latest(tickers)
    graph = ticker_graph_name(label, snapshot)
    for ticker in tickers:
        row = ticker.row
        where = _where("v_ticker_history", row, "cik")
        builder = out.individual(graph, ticker.iri, "TickerHistory")
        builder.add(ticker.iri, KG.tickerHistoryCik, rdflib.Literal(ticker.cik))
        builder.add(ticker.iri, KG.historicalSymbol, rdflib.Literal(ticker.symbol))
        builder.add(ticker.iri, KG.canonicalSymbol, rdflib.Literal(ticker.canonical))
        builder.add(ticker.iri, KG.validFrom, _day_lit(ticker.valid_from))
        if ticker.valid_to is not None:
            builder.add(ticker.iri, KG.validTo, _day_lit(ticker.valid_to))
        if row.get("evidence_url") is not None:
            url = _text(row["evidence_url"], "evidence_url", where)
            builder.add(ticker.iri, KG.evidenceUrl, _uri_lit(url))
        if row.get("evidence_date") is not None:
            evidence = _text(row["evidence_date"], "evidence_date", where)
            if ";" in evidence:
                out.skipped["v_ticker_history.evidence_date: more than one date"] += 1
            else:
                builder.add(
                    ticker.iri,
                    KG.evidenceDate,
                    _day_lit(_day(evidence, "evidence_date", where)),
                )
        if row.get("rules") is not None:
            builder.add(
                ticker.iri,
                KG.tickerHistoryRules,
                rdflib.Literal(_text(row["rules"], "rules", where)),
            )
        link = resolve_asset(ticker.canonical, ticker.cik, assets)
        if link.iri is None:
            out.asset_unlinked["v_ticker_history"] += 1
        else:
            builder.add(ticker.iri, KG.tickerHistoryAsset, KG[link.iri])
            if link.how == "symbol":
                out.asset_exact["v_ticker_history"] += 1
            else:
                out.asset_cik["v_ticker_history"] += 1


def _optional_text(  # noqa: PLR0913, PLR0917 -- explicit row/column/predicate reads better here
    builder: GraphBuilder,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    row: Row,
    column: str,
    where: str,
) -> None:
    if row.get(column) is not None:
        builder.add(subject, predicate, rdflib.Literal(_text(row[column], column, where)))


def _optional_day(  # noqa: PLR0913, PLR0917 -- explicit row/column/predicate reads better here
    builder: GraphBuilder,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    row: Row,
    column: str,
    where: str,
) -> None:
    if row.get(column) is not None:
        builder.add(subject, predicate, _day_lit(_day(row[column], column, where)))


def _optional_datetime(  # noqa: PLR0913, PLR0917 -- explicit row/column/predicate reads better here
    builder: GraphBuilder,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    row: Row,
    column: str,
    where: str,
) -> None:
    if row.get(column) is not None:
        builder.add(subject, predicate, _datetime_lit(_datetime(row[column], column, where)))


def _optional_integer(  # noqa: PLR0913, PLR0917 -- explicit row/column/predicate reads better here
    builder: GraphBuilder,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    row: Row,
    column: str,
    where: str,
) -> None:
    if row.get(column) is not None:
        builder.add(subject, predicate, _int_lit(_integer(row[column], column, where)))


def _orchestrator_runs(
    rows: Sequence[Row], label: str, out: Projection
) -> dict[int, rdflib.URIRef]:
    runs: dict[int, rdflib.URIRef] = {}
    for row in rows:
        where = _where("v_orchestrator_run", row, "run_id")
        run_id = _positive(_required(row, "run_id", where), "run_id", where)
        if run_id in runs:
            raise ProjectionError(f"{where}: two runs would share run_id {run_id}")
        graph = orchestrator_graph_name(label, run_id)
        iri = _run_iri(label, run_id)
        runs[run_id] = iri
        builder = out.individual(graph, iri, "OrchestratorRun")
        builder.add(iri, KG.orchestratorRunId, _int_lit(run_id))
        for column, predicate in (
            ("handle", KG.handle),
            ("kind", KG.runKind),
            ("code_version", KG.codeVersion),
            ("status", KG.status),
            ("settings_json", KG.settingsJson),
            ("surface", KG.surface),
        ):
            _optional_text(builder, iri, predicate, row, column, where)
        _optional_day(builder, iri, KG.runAsOf, row, "as_of", where)
        _optional_datetime(builder, iri, KG.startedAt, row, "started_at", where)
        _optional_datetime(builder, iri, KG.finishedAt, row, "finished_at", where)
    return runs


def _orchestrator_steps(
    rows: Sequence[Row],
    runs: Mapping[int, rdflib.URIRef],
    label: str,
    out: Projection,
) -> None:
    seen: set[rdflib.URIRef] = set()
    for row in rows:
        where = _where("v_orchestrator_step", row, "orchestrator_run_id")
        run_id = _positive(
            _required(row, "orchestrator_run_id", where), "orchestrator_run_id", where
        )
        ordinal = _positive(_required(row, "ordinal", where), "ordinal", where)
        run = runs.get(run_id)
        if run is None:
            raise ProjectionError(f"{where}: no v_orchestrator_run row for run {run_id}")
        iri = _step_iri(label, run_id, ordinal)
        if iri in seen:
            raise ProjectionError(f"{where}: two steps would share ordinal {ordinal}")
        seen.add(iri)
        graph = orchestrator_graph_name(label, run_id)
        builder = out.individual(graph, iri, "OrchestratorStep")
        builder.add(iri, KG.stepOfOrchestratorRun, run)
        builder.add(iri, KG.ordinal, _int_lit(ordinal))
        for column, predicate in (
            ("handle", KG.handle),
            ("step", KG.stepName),
            ("status", KG.status),
            ("run_kind", KG.runKind),
            ("reason", KG.reason),
            ("argv_json", KG.argvJson),
            ("output_tail", KG.outputTail),
        ):
            _optional_text(builder, iri, predicate, row, column, where)
        _optional_datetime(builder, iri, KG.startedAt, row, "started_at", where)
        _optional_datetime(builder, iri, KG.finishedAt, row, "finished_at", where)
        _optional_integer(builder, iri, KG.exitCode, row, "exit_code", where)
        if row.get("run_id") is not None:
            step_run_id = _integer(row["run_id"], "run_id", where)
            run_kind = row.get("run_kind")
            text = f"{run_kind}:{step_run_id}" if run_kind else str(step_run_id)
            builder.add(iri, KG.runId, rdflib.Literal(text))


def project(
    rows: Mapping[str, Sequence[Row]],
    assets: Mapping[str, AssetInfo],
    label: str,
    snapshot: str,
) -> Projection:
    """Turn the validated rows into deterministic batches; no store and no SHACL."""
    if not _RUN_LABEL.fullmatch(label):
        raise ProjectionError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    _day(snapshot, "snapshot_date", "ticker history snapshot")
    out = Projection()
    for view in VIEWS:
        out.rows[view] = len(rows.get(view, ()))
    _ticker_history(rows.get("v_ticker_history", ()), assets, label, snapshot, out)
    runs = _orchestrator_runs(rows.get("v_orchestrator_run", ()), label, out)
    _orchestrator_steps(rows.get("v_orchestrator_step", ()), runs, label, out)
    return out


# --- reading, validating and writing ------------------------------------------------------------


@dataclass
class ReferenceRunResult:
    """What one database's reference/process projection did."""

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
    asset_exact: Counter[str] = field(default_factory=Counter)
    asset_cik: Counter[str] = field(default_factory=Counter)
    asset_unlinked: Counter[str] = field(default_factory=Counter)
    store_consulted: bool = True
    in_doubt: str | None = None

    def summary(self) -> str:
        lines = [self.report.summary()]
        lines += [f"  rows: {view}: {n}" for view, n in self.rows.items()]
        lines += [f"  individuals: {kind}: {n}" for kind, n in sorted(self.individuals.items())]
        lines += [f"  triples: {kind}: {n}" for kind, n in sorted(self.triples_by_class.items())]
        lines += [f"  graph: {graph}: {n} triples" for graph, n in sorted(self.graphs.items())]
        lines += [f"  skipped: {reason}: {n}" for reason, n in sorted(self.skipped.items())]
        for view in sorted(set(self.asset_exact) | set(self.asset_cik) | set(self.asset_unlinked)):
            lines.append(
                f"  asset links: {view}: {self.asset_exact[view]} exact, "
                f"{self.asset_cik[view]} by CIK"
            )
            if self.asset_unlinked[view]:
                lines.append(f"  asset link omitted: {view}: {self.asset_unlinked[view]}")
        if not self.rows.get("v_ticker_history"):
            lines.append("  ticker history: 0 rows: nothing to write")
        if not self.rows.get("v_orchestrator_run") and not self.rows.get("v_orchestrator_step"):
            lines.append(
                "  orchestrator: v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: "
                "nothing to write"
            )
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
    """One source database after the boundary and the projector, before any store is touched."""

    report: BoundaryReport
    rows: dict[str, list[Row]]
    projection: Projection


def project_source(
    source: FinancialSource,
    assets: Mapping[str, AssetInfo],
    label: str,
    snapshot: str,
) -> SourceProjection:
    """Read the three views, run the boundary and project them; no store and no SHACL."""
    rows = {view: read_view(source, view) for view in VIEWS}
    expectations = load_expectations()
    failures = check_schema_floor(source.schema_version, load_source())
    result = validate(
        rows,
        {view: expectations[view] for view in VIEWS},
        source_failures=failures,
    )
    return SourceProjection(
        result.report, result.rows, project(result.rows, assets, label, snapshot)
    )


def validation_context(assets: Mapping[str, AssetInfo]) -> rdflib.Graph:
    """The loaded assets a dry run needs beside a ticker-history batch (a write fetches them).

    This mirrors what the universe loader stores: an asset's type, ticker and CIK, or, when it has
    no CIK, its closed memberships (``AssetShape``'s CIK-or-closed rule). The graph is validation
    context only; none of it is written.
    """
    context = rdflib.Graph()
    context.add((KG.SP500Index, RDF.type, KG.Universe))
    for symbol, info in assets.items():
        asset = KG[symbol]
        for kind in info.types:
            context.add((asset, RDF.type, KG[kind]))
        context.add((asset, KG.tickerSymbol, rdflib.Literal(symbol)))
        if info.cik is not None:
            context.add((asset, KG.cikNumber, rdflib.Literal(info.cik)))
        for index, (valid_from, valid_to) in enumerate(info.stints):
            membership = KG[f"Membership_{symbol}_{index}"]
            context.add((membership, RDF.type, KG.UniverseMembership))
            context.add((membership, KG.membershipAsset, asset))
            context.add((membership, KG.membershipUniverse, KG.SP500Index))
            context.add((membership, KG.validFrom, _day_lit(valid_from)))
            if valid_to is not None:
                context.add((membership, KG.validTo, _day_lit(valid_to)))
            context.add((asset, KG.hasUniverseMembership, membership))
    return context


def run(
    source: FinancialSource,
    assets: Mapping[str, AssetInfo],
    label: str,
    snapshot: str,
    store: GraphDB | None = None,
) -> ReferenceRunResult:
    """Read, check, project and (when ``store`` is given) write the three views."""
    source_projection = project_source(source, assets, label, snapshot)
    projection = source_projection.projection
    out = ReferenceRunResult(
        source_projection.report,
        projection.rows,
        projection.individuals,
        triples_by_class=projection.triples_by_class(),
        graphs={graph: len(builder) for graph, builder in projection.graphs.items()},
        skipped=projection.skipped,
        asset_exact=projection.asset_exact,
        asset_cik=projection.asset_cik,
        asset_unlinked=projection.asset_unlinked,
        store_consulted=store is not None,
    )
    context = validation_context(assets) if store is None else None
    for graph in sorted(projection.graphs):
        data = projection.turtle(graph)
        batch = gate.parse_batch(data)
        if store is None:
            gate.validate(batch, context=context)
            out.checked.append(graph)
            continue
        try:
            plan = gate.plan(store, data, graph)
        except gate.IngestRejected as exc:
            out.rejected[graph] = str(exc)
            continue
        if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
            out.already_in_store.append(graph)
            continue
        try:
            out.written[graph] = gate.write(store, plan)
        except gate.WriteInDoubt as exc:
            out.in_doubt = graph
            raise StoreInterrupted(out, exc) from exc
        except gate.IngestRejected as exc:
            out.rejected[graph] = str(exc)
    return out


#: Keep the public report/link helpers together for callers and tests.
__all__ = [
    "KG",
    "NS",
    "ORCHESTRATOR_GRAPH_PREFIX",
    "ORDER",
    "TICKER_GRAPH_PREFIX",
    "VIEWS",
    "Projection",
    "ProjectionError",
    "ReferenceRunResult",
    "SourceProjection",
    "StoreInterrupted",
    "orchestrator_graph_name",
    "project",
    "project_source",
    "read_view",
    "run",
    "ticker_graph_name",
    "validation_context",
]
