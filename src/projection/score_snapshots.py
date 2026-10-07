"""``v_score_snapshot`` -> ``:ScoreSnapshot`` Turtle, one batch per target graph (T-031).

The first lane-by-lane step of the write path (``PLAN.md`` Work item 4). It reads the view
through the boundary (:mod:`projection.boundary`), turns each surviving row into a
``:ScoreSnapshot`` and groups the snapshots by the named graph ``docs/07`` assigns them. Writing
a batch is :mod:`kg_store.gate`'s job; :func:`run` calls it and keeps the late-key file in step.

Per lane (``score_type`` = ``:agentOrigin``):

=============  ======================  =====================  ================================
score_type     ``:metricType``         ``:normalizedScore``   graph
=============  ======================  =====================  ================================
FUNDAMENTAL    ScoreFinanciero         not projected (T-171)  ``ingest:FUNDAMENTAL:{Y}-Q{n}``
VALORIZATION   ScoreCuantitativo       ``1 - n/100``          ``ingest:VALORIZATION:{run day}``
TECHNICAL      ScoreTecnico            ``1 - n/100``          ``ingest:TECHNICAL:{run day}``
SECTOR         SectorRelativeMomentum  ``1 - n/100``          ``ingest:SECTOR:{run day}``
=============  ======================  =====================  ================================

``:rawValue`` is upstream's ``raw_value`` verbatim, for every lane. The shape bounds only SECTOR's
(``[-100, 100]``); FUNDAMENTAL's range waits for upstream's Q6, and VALORIZATION's and TECHNICAL's
are left unbounded until it is decided. SEMANTIC is not projected here (T-158, T-081).

A FUNDAMENTAL snapshot goes to the graph of the quarter its ``available_at`` falls in: the day the
filing became usable, as ``schema/instances.trig``'s worked example does. The other lanes are
dated by ingestion, so they go to a graph named for the day of the run.

Every one of these graphs is append-only: the gate never adds to one that exists. So a graph is
written once, and a new row whose graph already exists is not written there (``SPEC.md`` §13
item 10). For FUNDAMENTAL that row is lost for its quarter (listed in the report's ``lost``, as a
``graph_written`` outcome), which is why a quarter is written only once it is complete: its
quarter is before the run day's, and a *full* upstream analysis run (``v_analysis_run``, see
:meth:`AnalysisRun.covers`) has looked at it from a later quarter, as of a day no later than the
run day. Upstream computes in batches after the fact, so the calendar alone is not enough, and a
row's ``computed_at`` is not either: a run scoped to one ticker, one form or a few years, or a
run whose ``as_of`` is earlier than its ``computed_at``, says nothing about the rest of the
quarter. The assumption is that upstream's first full run after a quarter covers every filing
usable in it. A filing it failed on (``failed_units``) or computes later still is lost, and
listed. For a cycle lane the row waits for the next run day's graph.

The run day is also the as-of day of a replay: a row is projected only once its ``available_at``
is on or before it, so a replay over past days (into a store that is not production; the CLI
enforces that) writes each row into the first day it was usable. ``:availableAt`` stays the
row's own, whatever graph it lands in, and remains the date a point-in-time query filters on.
A replay reads upstream as it is now, so a replay graph's date means "usable by", not "known on":
it holds rows computed after that day, counts full runs that finished after it, and may hold rows
production lost. A replay store answers point-in-time questions by ``availableAt``; it is not a
transaction-time record and not a copy of production.

Skipped by design (no later run writes them), counted in the report, never dropped silently:

* a cycle-lane row with a NULL ``available_at`` (every one before upstream's T-144): never filled in;
  the boundary counts it (the look-ahead pair's "skip"), so this module does not count it again;
* a row whose ticker is not a well-formed symbol, or not an asset of the universe database;
* a row without the value its lane's shape requires (``raw_value`` for FUNDAMENTAL and SECTOR,
  ``normalized_score`` for VALORIZATION and TECHNICAL).

Deferred (a later run writes them), counted apart in :attr:`Projection.deferred`:

* a row not yet available on the run day;
* a FUNDAMENTAL row whose quarter has not closed by the run day, or no full run has covered yet;
* on a write, a cycle-lane row whose run-day graph already exists (see above).

``:runId``, ``:codeVersion`` and ``:engineVersion`` are not emitted: the run-identity rule
(T-151) is not implemented yet, and the view exposes no engine version.
"""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import rdflib

from etl.asset_master import read_stints
from kg_store import gate
from kg_store.graphdb import GraphDB, GraphDBError
from projection.boundary import (
    GRAPH_WRITTEN,
    BoundaryReport,
    Failure,
    Row,
    check_source,
    load_late_keys,
    mark_written,
    validate,
    write_json_atomically,
)
from projection.expectations import load_expectations, load_source
from projection.score_scale import to_normalized_score
from projection.source import FinancialSource

VIEW = "v_score_snapshot"

#: The columns this projection reads: what a snapshot is built from, plus what the view's
#: expectations name (the run group of the cohort mean, the look-ahead pair).
COLUMNS = (
    "id",
    "ticker",
    "asset_id",
    "score_type",
    "raw_value",
    "normalized_score",
    "event_time",
    "computed_at",
    "run_id",
    "run_kind",
    "available_at",
)

#: score_type -> (``:metricType``, stem of the snapshot's local name).
LANES: dict[str, tuple[str, str]] = {
    "FUNDAMENTAL": ("ScoreFinanciero", "Fin"),
    "VALORIZATION": ("ScoreCuantitativo", "Quant"),
    "TECHNICAL": ("ScoreTecnico", "Tec"),
    "SECTOR": ("SectorRelativeMomentum", "Sector"),
}
#: The lanes written to a graph dated by the data (a quarter), not by the day of the run.
DATA_DATED = frozenset({"FUNDAMENTAL"})
#: The lanes that have no ``:normalizedScore`` (T-171).
RAW_ONLY = frozenset({"FUNDAMENTAL"})
#: The lanes whose shape requires a ``:rawValue``.
RAW_REQUIRED = frozenset({"FUNDAMENTAL", "SECTOR"})

_PREFIXES = (
    "@prefix : <https://thesis.local/kg/portfolio#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
)
_TICKER = re.compile(r"[A-Z0-9]{1,6}(\.[A-Z])?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

SKIP_BAD_TICKER = "ticker is not a well-formed symbol"
SKIP_NOT_AN_ASSET = "ticker is not an asset of the universe database"
SKIP_NO_VALUE = "the lane's required value is NULL"
DEFER_NOT_AVAILABLE = "not available by the run day"
DEFER_QUARTER_OPEN = "FUNDAMENTAL quarter has not closed by the run day"
DEFER_QUARTER_UNCOVERED = "no full upstream analysis run has covered the quarter since it closed"
DEFER_DAY_WRITTEN = "the run day's graph is already written; waits for a later run day"
#: Why a row that passed the boundary is not written, when it is not counted here.
LEFT_NULL_AVAILABLE_AT = "available_at is NULL"
LEFT_IN_STORE = "already in the store"
LEFT_LOST = "lost: its FUNDAMENTAL quarter graph is already written"


class ProjectionError(ValueError):
    """A row passed the boundary but cannot be projected; the message names it."""


class StoreInterrupted(RuntimeError):
    """The store failed partway through the writes; ``result`` holds what was done before it."""

    def __init__(self, result: RunResult, cause: GraphDBError) -> None:
        super().__init__(str(cause))
        self.result = result


def _decimal(value: float | int | Decimal) -> str:
    """A plain (never exponent) ``xsd:decimal`` lexical form of an upstream number."""
    return format(Decimal(str(value)), "f")


def _timestamp(text: str) -> str:
    """``computed_at`` (``+00:00`` or ``Z``, checked at the boundary) as an ``xsd:dateTime`` in UTC."""
    moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ProjectionError(f"computed_at {text!r} carries no UTC offset")
    return moment.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _where(row: Row) -> str:
    """How a failure names a ``v_score_snapshot`` row."""
    return f"{VIEW} id={row.get('id')}"


def _day(text: object, column: str, where: str) -> str:
    """``text`` as a ``YYYY-MM-DD`` day; ``where`` names the view and row in the error."""
    if not isinstance(text, str) or not _ISO_DATE.fullmatch(text[:10]):
        raise ProjectionError(f"{where}: {column} {text!r} is not a date")
    return text[:10]


def _quarter(day: str) -> tuple[int, int]:
    return int(day[:4]), (int(day[5:7]) - 1) // 3 + 1


def graph_name(score_type: str, available_at: str, run_day: str) -> str:
    """The named graph a snapshot of ``score_type`` belongs in (``docs/07``'s table)."""
    if score_type in DATA_DATED:
        year, quarter = _quarter(available_at)
        return f"urn:graph:ingest:{score_type}:{year}-Q{quarter}"
    return f"urn:graph:ingest:{score_type}:{run_day}"


def lane_of(graph: str) -> str:
    """The ``score_type`` of a graph :func:`graph_name` named."""
    return graph.split(":")[3]


def snapshot_iri(row: Row) -> str:
    """The snapshot's local name: ticker, lane stem, event day and the upstream row id."""
    _, stem = LANES[row["score_type"]]
    day = _day(row["event_time"], "event_time", _where(row)).replace("-", "")
    return f"Snap_{row['ticker']}_{stem}_{day}_{row['id']}"


@dataclass(frozen=True)
class Block:
    """One row's Turtle, with the key the late-key file knows it by."""

    key: int
    iri: str
    turtle: str


def snapshot_block(row: Row) -> Block:
    """The Turtle for one validated, projectable row."""
    score_type = row["score_type"]
    metric, _ = LANES[score_type]
    iri = snapshot_iri(row)
    available = _day(row["available_at"], "available_at", _where(row))
    lines = [
        f":{iri} a :ScoreSnapshot ;",
        f'    :agentOrigin "{score_type}" ;',
        f'    :metricType "{metric}" ;',
        f'    :timestamp "{_timestamp(row["computed_at"])}"^^xsd:dateTime ;',
        f'    :eventTime "{_day(row["event_time"], "event_time", _where(row))}"^^xsd:date ;',
        f'    :availableAt "{available}"^^xsd:date',
    ]
    if row["raw_value"] is not None:
        lines[-1] += " ;"
        lines.append(f'    :rawValue "{_decimal(row["raw_value"])}"^^xsd:decimal')
    if score_type not in RAW_ONLY and row["normalized_score"] is not None:
        # to_normalized_score is the one place the 0-100 strength becomes a 0-1 risk reading.
        lines[-1] += " ;"
        lines.append(
            f'    :normalizedScore "{to_normalized_score(score_type, row["normalized_score"])}"'
            "^^xsd:decimal"
        )
    lines[-1] += f" .\n:{row['ticker']} :hasScoreObservation :{iri} .\n"
    return Block(int(row["id"]), iri, "\n".join(lines))


ANALYSIS_RUNS = "v_analysis_run"
#: The columns of ``v_analysis_run`` that say what a run looked at.
RUN_COLUMNS = ("run_id", "as_of", "status", "failed_units", "params_json")
#: The forms a full run reads: every FUNDAMENTAL snapshot comes from one of them.
FULL_FORMS = frozenset({"10-K", "10-Q"})
#: The ``params_json`` keys whose value narrows a run; each must be present for a run to be full.
_SCOPE_KEYS = ("tickers", "limit", "forms", "since_year", "until_year")


@dataclass(frozen=True)
class AnalysisRun:
    """One upstream analysis run: its ``as_of`` day, its status and what it was asked to read."""

    run_id: int
    as_of: str
    status: str
    params: dict[str, object]

    @classmethod
    def from_row(cls, row: Row) -> AnalysisRun:
        where = f"{ANALYSIS_RUNS} run_id={row.get('run_id')}"
        try:
            params = json.loads(row["params_json"])
        except (TypeError, ValueError):
            raise ProjectionError(f"{where}: params_json is not JSON") from None
        if not isinstance(params, dict):
            raise ProjectionError(f"{where}: params_json is not an object")
        return cls(int(row["run_id"]), _day(row["as_of"], "as_of", where), row["status"], params)

    def covers(self, year: int) -> bool:
        """Whether this run read every filing, of every asset, that can be usable in ``year``.

        Full scope: completed, every ticker (``tickers`` and ``limit`` null), both forms, and a
        year range that reaches ``year`` (a NULL bound is open). The year bounds are read as
        fiscal years, so a filing usable in ``year`` may belong to ``year - 1``: the range must
        start by then. A missing scope key means the run is not known to be full. Upstream's
        unit counts are not compared, since ``planned_units`` and ``completed_units`` do not
        count the same thing; a run with ``failed_units`` still covers (its failures are lost).
        Which fields define a full run is a question for upstream (``SPEC.md`` Q7).
        """
        p = self.params
        if self.status != "completed" or any(k not in p for k in _SCOPE_KEYS):
            return False
        forms = p["forms"]
        since, until = p["since_year"], p["until_year"]
        return (
            p["tickers"] is None
            and p["limit"] is None
            and isinstance(forms, list)
            and set(forms) >= FULL_FORMS
            and (since is None or (isinstance(since, int) and since <= year - 1))
            and (until is None or (isinstance(until, int) and until >= year))
        )


def quarter_covered(quarter: tuple[int, int], runs: Sequence[AnalysisRun], run_day: str) -> bool:
    """Whether a full run as of a later quarter, and no later than ``run_day``, covered ``quarter``."""
    return any(
        _quarter(r.as_of) > quarter and r.as_of <= run_day and r.covers(quarter[0]) for r in runs
    )


@dataclass
class Projection:
    """The blocks of one run, per target graph, and what was skipped or deferred."""

    graphs: dict[str, list[Block]] = field(default_factory=lambda: defaultdict(list))
    #: Rows left out by design, per reason: no later run writes them.
    skipped: Counter[str] = field(default_factory=Counter)
    #: Rows a later run writes, per reason.
    deferred: Counter[str] = field(default_factory=Counter)
    #: key -> why: the rows left out by design that no later run would write either.
    left_out: dict[int, str] = field(default_factory=dict)

    def leave_out(self, row: Row, reason: str, *, counted: bool = True) -> None:
        if counted:
            self.skipped[reason] += 1
        self.left_out[int(row["id"])] = reason

    def turtle(self, graph: str, drop: Collection[str] = ()) -> bytes:
        """The graph's batch, without the snapshots named in ``drop``."""
        body = "\n".join(b.turtle for b in self.graphs[graph] if b.iri not in drop)
        return (_PREFIXES + body).encode()


def project(
    rows: Sequence[Row],
    assets: Collection[str],
    run_day: str,
    runs: Sequence[AnalysisRun] = (),
) -> Projection:
    """Group the validated rows into per-graph blocks; count every row left out, and why.

    ``runs`` are upstream's analysis runs: a FUNDAMENTAL quarter is written only once one of
    them covers it (:func:`quarter_covered`).
    """
    out = Projection()
    for row in rows:
        score_type = row["score_type"]
        if score_type not in LANES:
            raise ProjectionError(f"{VIEW} id={row['id']}: no lane for score_type {score_type!r}")
        if not _TICKER.fullmatch(row["ticker"]):
            out.leave_out(row, SKIP_BAD_TICKER)
            continue
        if row["ticker"] not in assets:
            out.leave_out(row, SKIP_NOT_AN_ASSET)
            continue
        if row["available_at"] is None:
            # counted by the boundary (the ordered pair's "skip"), not again here
            out.leave_out(row, LEFT_NULL_AVAILABLE_AT, counted=False)
            continue
        needed = "raw_value" if score_type in RAW_REQUIRED else "normalized_score"
        if row[needed] is None:
            out.leave_out(row, SKIP_NO_VALUE)
            continue
        available = _day(row["available_at"], "available_at", _where(row))
        # Deferred, not "left out" (no late key would close): a later run writes these.
        if available > run_day:
            out.deferred[DEFER_NOT_AVAILABLE] += 1
            continue
        if score_type in DATA_DATED and _quarter(available) >= _quarter(run_day):
            out.deferred[DEFER_QUARTER_OPEN] += 1
            continue
        if score_type in DATA_DATED and not quarter_covered(_quarter(available), runs, run_day):
            out.deferred[DEFER_QUARTER_UNCOVERED] += 1
            continue
        block = snapshot_block(row)
        out.graphs[graph_name(score_type, available, run_day)].append(block)
    return out


# --- reading and writing ------------------------------------------------------------------------


def read_rows(db: FinancialSource) -> list[Row]:
    """Every row of ``v_score_snapshot`` (the columns this projection uses), as plain dicts."""
    cursor = db.execute(f"SELECT {', '.join(COLUMNS)} FROM {VIEW} ORDER BY id")  # noqa: S608 -- constants
    return [dict(zip(COLUMNS, r, strict=True)) for r in cursor.fetchall()]


def read_runs(db: FinancialSource) -> list[Row]:
    """Every row of ``v_analysis_run`` (the columns that say what a run covered), as plain dicts."""
    cursor = db.execute(
        f"SELECT {', '.join(RUN_COLUMNS)} FROM {ANALYSIS_RUNS} ORDER BY run_id"  # noqa: S608 -- constants
    )
    return [dict(zip(RUN_COLUMNS, r, strict=True)) for r in cursor.fetchall()]


def universe_symbols(path: str | Path) -> set[str]:
    """Every symbol of the universe database: the assets a snapshot can point at."""
    return {stint.symbol for stint in read_stints(path)}


@dataclass
class RunResult:
    report: BoundaryReport
    skipped: Counter[str]  # left out by design; also in ``report.skipped_by_design``
    deferred: Counter[str] = field(default_factory=Counter)  # a later run writes these
    written: dict[str, int] = field(default_factory=dict)  # graph -> triples
    checked: list[str] = field(default_factory=list)  # dry run: SHACL-valid graphs
    already_in_store: int = 0
    rejected: dict[str, str] = field(default_factory=dict)  # graph -> why the gate refused it
    late_not_found: list[str] = field(default_factory=list)
    late_closed: list[str] = field(default_factory=list)  # late keys closed without a write
    lost_before: int = 0  # losses an earlier run already listed (with a late-key file)
    store_consulted: bool = True  # False on a dry run: ``already_in_store`` was not checked
    runs_not_counted: int = 0  # analysis runs that are not ``completed``: never full, not parsed
    #: The graph being written when the store failed: its answer was lost, so it may be written.
    in_doubt: str | None = None

    def summary(self) -> str:
        lines = [self.report.summary()]
        if self.lost_before:
            lines += [f"  lost in an earlier run (listed then): {self.lost_before}"]
        lines += [f"  deferred: {reason}: {n}" for reason, n in self.deferred.items()]
        if self.store_consulted:
            lines += [f"  already in the store: {self.already_in_store}"]
        else:
            lines += ["  already in the store: not checked (dry run)"]
        if self.runs_not_counted:
            lines += [f"  analysis runs not completed, not counted: {self.runs_not_counted}"]
        lines += [f"  written: {g}: {n} triples" for g, n in sorted(self.written.items())]
        lines += [f"  SHACL-valid, not written (store not consulted): {g}" for g in self.checked]
        lines += [f"  rejected: {g}: {why}" for g, why in sorted(self.rejected.items())]
        if self.in_doubt:
            lines += [
                f"  in doubt: {self.in_doubt}: the store failed while it was being written, so it "
                "may be written too; the next run finds its snapshots already in the store"
            ]
        lines += [f"  late key not found in the re-read: {k}" for k in self.late_not_found]
        lines += [f"  late key closed without a write: {k}" for k in self.late_closed]
        return "\n".join(lines)


def run(
    source: FinancialSource,
    assets: Collection[str],
    store: GraphDB | None,
    run_day: str,
    *,
    late_keys_path: Path | None = None,
) -> RunResult:
    """Read, check, project and (when ``store`` is given) write ``v_score_snapshot``.

    ``v_analysis_run`` is read through the boundary too: its completed runs say which
    FUNDAMENTAL quarters upstream has covered (:func:`quarter_covered`). A run in any other
    status is counted in ``runs_not_counted`` and never parsed, so a run upstream has just
    started (which may still lack its ``as_of`` or ``params_json``) never stops a projection.

    With ``store=None`` nothing is written: the batches are still checked against ``shapes.ttl``.
    A dry run does not consult the store, so it cannot tell which graphs already exist: a graph
    it lists as SHACL-valid may still be skipped by a write.

    A graph that already exists is never written to, so a re-run never fails on a graph an
    earlier run wrote. Its new rows are reported instead: a FUNDAMENTAL row in ``report.lost``
    (a ``graph_written`` outcome; SPEC §13 item 10), a cycle-lane row as
    :data:`DEFER_DAY_WRITTEN`, written by the next run day. A loss does not fail the run (the
    exit status stays 0), as a boundary loss within its cap does not: the row stays in the view,
    so a failing status would fail every later run too. So that a new loss stands out, a run
    with a late-key file keeps the keys of lost rows beside it (:func:`lost_keys_path`, on a
    write): a loss already there is counted in ``lost_before`` and dropped from ``report.lost``,
    which then lists only this run's new losses.

    The late-key file is re-read every run (the whole view is read, so a late row comes back
    with the rest). On a write, a key leaves it once its row is settled: written, already in the
    store, or left out by design (``Projection.left_out``, listed in ``late_closed``), or gone
    from upstream (listed in ``late_not_found``). A key whose row waits for a later graph, or
    whose graph the gate refused, stays. A dry run never removes a key and never writes the
    lost-key file, but the boundary still records the keys of the rows it delays.

    Both key files, and their folder, are checked before upstream is read, so a missing folder
    or a malformed file stops the run before anything is written (the CLI creates the folder).

    If the store fails partway, the graphs written so far are settled in both key files and
    :class:`StoreInterrupted` carries the result up to that point. A failure while a graph is
    being sent leaves that graph in doubt (``RunResult.in_doubt``): the store may have applied it
    before the answer was lost, so it is neither counted as written nor settled, and the next
    run finds its snapshots already in the store.

    The key files must belong to ``store``'s repository: this function does not check it. The
    CLI keeps a non-production repository's files apart (``projection.project_scores``'s
    ``key_file``), so a replay never settles or hides production's rows.
    """
    # Before anything is read or written, so a key file never stops a run after a write.
    if late_keys_path is not None and not late_keys_path.parent.is_dir():
        raise ProjectionError(f"{late_keys_path.parent}: the key files' folder does not exist")
    if late_keys_path is not None:
        try:
            load_late_keys(late_keys_path)  # the boundary reads it again; this names the failure
        except ValueError as exc:
            raise ProjectionError(str(exc)) from exc
    lost_path = lost_keys_path(late_keys_path) if late_keys_path is not None else None
    known_lost = load_lost_keys(lost_path) if lost_path is not None else {}
    read = read_rows(source)
    result = validate(
        {VIEW: read, ANALYSIS_RUNS: read_runs(source)},
        {name: load_expectations()[name] for name in (VIEW, ANALYSIS_RUNS)},
        source_failures=check_source(source, load_source()),
        late_keys_path=late_keys_path,
    )
    # Only a completed run can be full; another (running, failed) may still lack its as_of or
    # params, so it is counted and never parsed. A completed run without them stops the run.
    completed = [r for r in result.rows[ANALYSIS_RUNS] if r["status"] == "completed"]
    runs = [AnalysisRun.from_row(r) for r in completed]
    projection = project(result.rows[VIEW], assets, run_day, runs)
    for reason, n in projection.skipped.items():
        result.report.skip(VIEW, reason, n)
    out = RunResult(result.report, projection.skipped, projection.deferred)
    out.store_consulted = store is not None
    out.runs_not_counted = len(result.rows[ANALYSIS_RUNS]) - len(completed)
    # key -> why not written (None: written)
    settled: dict[int, str | None] = dict(projection.left_out)

    def finish() -> None:
        if late_keys_path is not None and lost_path is not None:
            _settle_late_keys(late_keys_path, read, settled, out, drop=store is not None)
            _sort_losses(lost_path, known_lost, out, save=store is not None)

    try:
        for graph in sorted(projection.graphs):
            _write_graph(store, projection, graph, out, settled)
    except GraphDBError as exc:
        finish()
        raise StoreInterrupted(out, exc) from exc
    finish()
    return out


def _write_graph(
    store: GraphDB | None,
    projection: Projection,
    graph: str,
    out: RunResult,
    settled: dict[int, str | None],
) -> None:
    """Check or write one graph's batch, and record each of its rows' outcome."""
    blocks = projection.graphs[graph]
    taken = _existing(store, gate.parse_batch(projection.turtle(graph)))
    have = {b.iri for b in blocks if f"{_NS}{b.iri}" in taken}
    out.already_in_store += len(have)
    settled.update({b.key: LEFT_IN_STORE for b in blocks if b.iri in have})
    fresh = [b for b in blocks if b.iri not in have]
    if not fresh:
        return
    if store is not None and _graph_exists(store, graph):
        if lane_of(graph) in DATA_DATED:  # lost for its quarter: no later run writes it
            out.report.lost += [
                Failure(
                    VIEW,
                    GRAPH_WRITTEN,
                    None,
                    f"{graph} is already written; {b.iri} is lost for that quarter",
                    key=(b.key,),
                )
                for b in fresh
            ]
            settled.update({b.key: LEFT_LOST for b in fresh})
        else:
            out.deferred[DEFER_DAY_WRITTEN] += len(fresh)
        return
    data = projection.turtle(graph, drop=have)
    try:
        if store is None:
            gate.validate(gate.parse_batch(data))
            out.checked.append(graph)
        else:
            try:
                out.written[graph] = gate.ingest(store, data, graph)
            except GraphDBError:
                # Sent, but the answer never came (or came as an error): it may be in the store.
                out.in_doubt = graph
                raise
    except gate.IngestRejected as exc:
        out.rejected[graph] = str(exc)
        return
    if store is not None:
        settled.update({b.key: None for b in fresh})


def _settle_late_keys(
    path: Path, read: Sequence[Row], settled: dict[int, str | None], out: RunResult, *, drop: bool
) -> None:
    """Report the late keys this run settled or cannot find; on a write, remove them."""
    present = {int(r["id"]) for r in read}
    stored = load_late_keys(path).get(VIEW, {"keys": []})["keys"]
    gone = [k for k in stored if k[0] not in present]
    out.late_not_found = [f"{VIEW} id={k[0]}" for k in gone]
    done = [k for k in stored if k[0] in settled]
    out.late_closed = [
        f"{VIEW} id={k[0]} ({settled[k[0]]})" for k in done if settled[k[0]] is not None
    ]
    if drop:
        mark_written(path, VIEW, gone + done)


def lost_keys_path(late_keys_path: Path) -> Path:
    """The lost-key file kept beside a late-key file: ``late.json`` -> ``late.lost.json``."""
    return late_keys_path.with_name(f"{late_keys_path.stem}.lost.json")


LostKeys = dict[str, list[list[object]]]


def load_lost_keys(path: Path) -> LostKeys:
    """The keys of the rows earlier runs listed as lost, per view; ``{}`` if none yet.

    The file maps a view to the keys of its lost rows (JSON). A lost row stays in the view, so
    every later run finds the same loss again: the file is what tells a new one apart.
    """
    try:
        known = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        raise ProjectionError(f"{path}: the lost-key file is not JSON") from None
    if not isinstance(known, dict) or not all(isinstance(v, list) for v in known.values()):
        raise ProjectionError(f"{path}: the lost-key file must map a view to a list of keys")
    return known


def _sort_losses(path: Path, known: LostKeys, out: RunResult, *, save: bool) -> None:
    """Keep only this run's new losses in ``report.lost``; on a write, remember them in ``path``.

    ``known`` is what :func:`load_lost_keys` read before the run. The file is replaced
    atomically, and not created while there is nothing to keep.
    """
    new = []
    for failure in out.report.lost:
        key = list(failure.key) if failure.key is not None else None
        if key is not None and key in known.get(failure.view, []):
            out.lost_before += 1
        else:
            new.append(failure)
            if key is not None:
                known.setdefault(failure.view, []).append(key)
    out.report.lost[:] = new
    if save and (known or path.exists()):
        write_json_atomically(path, known)


_NS = "https://thesis.local/kg/portfolio#"


def _existing(store: GraphDB | None, batch: rdflib.Graph) -> set[str]:
    if store is None:
        return set()
    return set(gate.existing_subjects(store, batch))


def _graph_exists(store: GraphDB, graph: str) -> bool:
    """Whether ``graph`` holds any statement: the gate's own test for an append-only graph."""
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))
