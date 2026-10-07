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
item 10). For FUNDAMENTAL that row is lost for its quarter, which is why a quarter is written only
once it has closed (its quarter is before the run day's): a write during the quarter would lose
the quarter's later filings. For a cycle lane the row waits for the next run day's graph.

Skipped by design, and counted in the report, never dropped silently:

* a cycle-lane row with a NULL ``available_at`` (every one before upstream's T-144): never filled in;
  the boundary counts it (the look-ahead pair's "skip"), so this module does not count it again;
* a row whose ticker is not a well-formed symbol, or not an asset of the universe database;
* a row without the value its lane's shape requires (``raw_value`` for FUNDAMENTAL and SECTOR,
  ``normalized_score`` for VALORIZATION and TECHNICAL);
* a FUNDAMENTAL row whose quarter has not closed by the run day;
* on a write, a new row whose graph already exists (see above).

``:runId``, ``:codeVersion`` and ``:engineVersion`` are not emitted: the run-identity rule
(T-151) is not implemented yet, and the view exposes no engine version.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import rdflib

from etl.asset_master import read_stints
from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.boundary import (
    BoundaryReport,
    Row,
    check_source,
    load_late_keys,
    mark_written,
    validate,
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
SKIP_QUARTER_OPEN = "FUNDAMENTAL quarter has not closed by the run day"
SKIP_QUARTER_WRITTEN = "lost: its FUNDAMENTAL quarter graph is already written"
SKIP_DAY_WRITTEN = "the run day's graph is already written; waits for a later run day"
#: Why a row that passed the boundary is not written, when it is not counted here.
LEFT_NULL_AVAILABLE_AT = "available_at is NULL"
LEFT_IN_STORE = "already in the store"


class ProjectionError(ValueError):
    """A row passed the boundary but cannot be projected; the message names it."""


def _decimal(value: float | int | Decimal) -> str:
    """A plain (never exponent) ``xsd:decimal`` lexical form of an upstream number."""
    return format(Decimal(str(value)), "f")


def _timestamp(text: str) -> str:
    """``computed_at`` (``+00:00`` or ``Z``, checked at the boundary) as an ``xsd:dateTime`` in UTC."""
    moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ProjectionError(f"computed_at {text!r} carries no UTC offset")
    return moment.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(text: object, column: str, row: Row) -> str:
    if not isinstance(text, str) or not _ISO_DATE.fullmatch(text[:10]):
        raise ProjectionError(f"{VIEW} id={row.get('id')}: {column} {text!r} is not a date")
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
    day = _day(row["event_time"], "event_time", row).replace("-", "")
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
    available = _day(row["available_at"], "available_at", row)
    lines = [
        f":{iri} a :ScoreSnapshot ;",
        f'    :agentOrigin "{score_type}" ;',
        f'    :metricType "{metric}" ;',
        f'    :timestamp "{_timestamp(row["computed_at"])}"^^xsd:dateTime ;',
        f'    :eventTime "{_day(row["event_time"], "event_time", row)}"^^xsd:date ;',
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


@dataclass
class Projection:
    """The blocks of one run, per target graph, and what was skipped."""

    graphs: dict[str, list[Block]] = field(default_factory=lambda: defaultdict(list))
    skipped: Counter[str] = field(default_factory=Counter)
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


def project(rows: Sequence[Row], assets: Collection[str], run_day: str) -> Projection:
    """Group the validated rows into per-graph blocks; count every row left out, and why."""
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
        available = _day(row["available_at"], "available_at", row)
        if score_type in DATA_DATED and _quarter(available) >= _quarter(run_day):
            # not "left out": a run after the quarter closes writes it
            out.skipped[SKIP_QUARTER_OPEN] += 1
            continue
        block = snapshot_block(row)
        out.graphs[graph_name(score_type, available, run_day)].append(block)
    return out


# --- reading and writing ------------------------------------------------------------------------


def read_rows(db: FinancialSource) -> list[Row]:
    """Every row of ``v_score_snapshot`` (the columns this projection uses), as plain dicts."""
    cursor = db.execute(f"SELECT {', '.join(COLUMNS)} FROM {VIEW} ORDER BY id")  # noqa: S608 -- constants
    return [dict(zip(COLUMNS, r, strict=True)) for r in cursor.fetchall()]


def universe_symbols(path: str | Path) -> set[str]:
    """Every symbol of the universe database: the assets a snapshot can point at."""
    return {stint.symbol for stint in read_stints(path)}


@dataclass
class RunResult:
    report: BoundaryReport
    skipped: Counter[str]
    written: dict[str, int] = field(default_factory=dict)  # graph -> triples
    checked: list[str] = field(default_factory=list)  # dry run: graphs the gate accepts
    already_in_store: int = 0
    rejected: dict[str, str] = field(default_factory=dict)  # graph -> why the gate refused it
    late_not_found: list[str] = field(default_factory=list)
    late_closed: list[str] = field(default_factory=list)  # late keys closed without a write

    def summary(self) -> str:
        lines = [self.report.summary()]
        lines += [f"  not projected: {reason}: {n}" for reason, n in self.skipped.items()]
        lines += [f"  already in the store: {self.already_in_store}"]
        lines += [f"  written: {g}: {n} triples" for g, n in sorted(self.written.items())]
        lines += [f"  accepted by the gate, not written: {g}" for g in self.checked]
        lines += [f"  rejected: {g}: {why}" for g, why in sorted(self.rejected.items())]
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

    With ``store=None`` nothing is written: the batches are still checked against ``shapes.ttl``,
    so a dry run reports what the gate would say (it cannot see which graphs the store holds).

    A graph that already exists is never written to: its new rows are counted instead
    (:data:`SKIP_QUARTER_WRITTEN`, :data:`SKIP_DAY_WRITTEN`), so a re-run never fails on a graph
    an earlier run wrote.

    The late-key file is re-read every run (the whole view is read, so a late row comes back
    with the rest). On a write, a key leaves it once its row is settled: written, already in the
    store, or left out by design (``Projection.left_out``, listed in ``late_closed``), or gone
    from upstream (listed in ``late_not_found``). A key whose row waits for a later graph, or
    whose graph the gate refused, stays. A dry run reports but removes no key; the boundary
    still adds the keys of the rows it delays.
    """
    read = read_rows(source)
    result = validate(
        {VIEW: read},
        {VIEW: load_expectations()[VIEW]},
        source_failures=check_source(source, load_source()),
        late_keys_path=late_keys_path,
    )
    projection = project(result.rows[VIEW], assets, run_day)
    for reason, n in projection.skipped.items():
        result.report.skip(VIEW, reason, n)
    out = RunResult(result.report, projection.skipped)
    settled: dict[int, str | None] = dict(
        projection.left_out
    )  # key -> why not written (None: written)

    for graph in sorted(projection.graphs):
        blocks = projection.graphs[graph]
        taken = _existing(store, gate.parse_batch(projection.turtle(graph)))
        have = {b.iri for b in blocks if f"{_NS}{b.iri}" in taken}
        out.already_in_store += len(have)
        settled.update({b.key: LEFT_IN_STORE for b in blocks if b.iri in have})
        fresh = [b for b in blocks if b.iri not in have]
        if not fresh:
            continue
        if store is not None and _graph_exists(store, graph):
            data_dated = lane_of(graph) in DATA_DATED
            reason = SKIP_QUARTER_WRITTEN if data_dated else SKIP_DAY_WRITTEN
            out.skipped[reason] += len(fresh)
            result.report.skip(VIEW, reason, len(fresh))
            if data_dated:  # lost for its quarter: no later run writes it either
                settled.update({b.key: reason for b in fresh})
            continue
        data = projection.turtle(graph, drop=have)
        try:
            if store is None:
                gate.validate(gate.parse_batch(data))
                out.checked.append(graph)
            else:
                out.written[graph] = gate.ingest(store, data, graph)
        except gate.IngestRejected as exc:
            out.rejected[graph] = str(exc)
            continue
        if store is not None:
            settled.update({b.key: None for b in fresh})

    if late_keys_path is not None:
        _settle_late_keys(late_keys_path, read, settled, out, drop=store is not None)
    return out


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


_NS = "https://thesis.local/kg/portfolio#"


def _existing(store: GraphDB | None, batch: rdflib.Graph) -> set[str]:
    if store is None:
        return set()
    return set(gate.existing_subjects(store, batch))


def _graph_exists(store: GraphDB, graph: str) -> bool:
    """Whether ``graph`` holds any statement: the gate's own test for an append-only graph."""
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))
