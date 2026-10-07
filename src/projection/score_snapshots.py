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

Skipped by design, and counted in the report, never dropped silently:

* a cycle-lane row with a NULL ``available_at`` (every one before upstream's T-144): never filled in;
  the boundary counts it (the look-ahead pair's "skip"), so this module does not count it again;
* a row whose ticker is not an asset of the universe database;
* a row without the value its lane's shape requires (``raw_value`` for FUNDAMENTAL and SECTOR,
  ``normalized_score`` for VALORIZATION and TECHNICAL).

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

SKIP_NOT_AN_ASSET = "ticker is not an asset of the universe database"
SKIP_NO_VALUE = "the lane's required value is NULL"


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


def graph_name(score_type: str, available_at: str, run_day: str) -> str:
    """The named graph a snapshot of ``score_type`` belongs in (``docs/07``'s table)."""
    if score_type in DATA_DATED:
        year, month = int(available_at[:4]), int(available_at[5:7])
        return f"urn:graph:ingest:{score_type}:{year}-Q{(month - 1) // 3 + 1}"
    return f"urn:graph:ingest:{score_type}:{run_day}"


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
        if not _TICKER.fullmatch(row["ticker"]) or row["ticker"] not in assets:
            out.skipped[SKIP_NOT_AN_ASSET] += 1
            continue
        if row["available_at"] is None:
            continue  # counted by the boundary (the ordered pair's "skip"), not again here
        needed = "raw_value" if score_type in RAW_REQUIRED else "normalized_score"
        if row[needed] is None:
            out.skipped[SKIP_NO_VALUE] += 1
            continue
        block = snapshot_block(row)
        graph = graph_name(score_type, _day(row["available_at"], "available_at", row), run_day)
        out.graphs[graph].append(block)
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

    def summary(self) -> str:
        lines = [self.report.summary()]
        lines += [f"  not projected: {reason}: {n}" for reason, n in self.skipped.items()]
        lines += [f"  already in the store: {self.already_in_store}"]
        lines += [f"  written: {g}: {n} triples" for g, n in sorted(self.written.items())]
        lines += [f"  accepted by the gate, not written: {g}" for g in self.checked]
        lines += [f"  rejected: {g}: {why}" for g, why in sorted(self.rejected.items())]
        lines += [f"  late key not found in the re-read: {k}" for k in self.late_not_found]
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
    so a dry run reports what the gate would say. The late-key file is re-read every run (the
    whole view is read, so a late row comes back with the rest) and a key leaves it only once
    its snapshot is in the store.
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
    if late_keys_path is not None:
        # A key whose row upstream no longer has can never be re-read: report it and drop it.
        present = {int(r["id"]) for r in read}
        stored = load_late_keys(late_keys_path).get(VIEW, {"keys": []})["keys"]
        gone = [k for k in stored if k[0] not in present]
        out.late_not_found = [f"{VIEW} id={k[0]}" for k in gone]
        mark_written(late_keys_path, VIEW, gone)

    for graph in sorted(projection.graphs):
        blocks = projection.graphs[graph]
        taken = _existing(store, gate.parse_batch(projection.turtle(graph)))
        have = {b.iri for b in blocks if f"{_NS}{b.iri}" in taken}
        out.already_in_store += len(have)
        fresh = [b for b in blocks if b.iri not in have]
        if not fresh:
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
        if late_keys_path is not None and store is not None:
            mark_written(late_keys_path, VIEW, [[b.key] for b in fresh])
    return out


_NS = "https://thesis.local/kg/portfolio#"


def _existing(store: GraphDB | None, batch: rdflib.Graph) -> set[str]:
    if store is None:
        return set()
    return set(gate.existing_subjects(store, batch))
