"""Synthetic ``v_score_snapshot`` rows, analysis runs, databases and a live fake store.

Built in memory and shared by ``test_score_snapshots.py``, ``test_project_scores.py`` and
``test_cli_project_scores.py`` (T-031), under ``tests/fixtures/`` as constitution Project
structure #10 places shared fixtures.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from projection import score_snapshots as ss
from projection.source import FinancialSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]

NS = "https://thesis.local/kg/portfolio#"
ASSETS = {"AAA", "BBB", "CCC", "BF.B"}


def snapshot_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "ticker": "AAA",
        "asset_id": 1,
        "score_type": "TECHNICAL",
        "raw_value": 70.0,
        "normalized_score": 60.0,
        "event_time": "2026-07-09",
        "computed_at": "2026-10-04T18:28:56+00:00",
        "run_id": 1,
        "run_kind": "cycle",
        "available_at": "2026-07-09",
    }
    row.update(over)
    return row


def fundamental_row(**over: Any) -> dict[str, Any]:
    return snapshot_row(
        **{
            "score_type": "FUNDAMENTAL",
            "raw_value": 44.0,
            "normalized_score": 44.0,
            "event_time": "2024-12-31",
            "available_at": "2025-03-03",
            "run_kind": "analysis",
            **over,
        }
    )


def full_run(run_id: int = 1, as_of: str = "2026-10-05", **params: Any) -> ss.AnalysisRun:
    """An upstream analysis run of full scope, unless ``params`` narrows it."""
    scope: dict[str, object] = {
        "analysis_date": as_of,
        "forms": ["10-K", "10-Q"],
        "since_year": 2020,
        "until_year": 2026,
        "limit": None,
        "tickers": None,
        "fresh": False,
    }
    scope.update(params)
    return ss.AnalysisRun(run_id, as_of, "completed", scope)


RUNS = [full_run()]


_DDL = """
CREATE TABLE schema_version (version INTEGER, applied_at TEXT, description TEXT);
INSERT INTO schema_version VALUES (9, 'x', 'x');
CREATE TABLE v_cycle_run (run_id INTEGER, cycle_type TEXT);
INSERT INTO v_cycle_run VALUES (1, 'SELECTION');
CREATE TABLE v_score_snapshot (
  id INTEGER, ticker TEXT, asset_id INTEGER, score_type TEXT, raw_value REAL, normalized_score REAL,
  event_time TEXT, computed_at TEXT, run_id INTEGER, run_kind TEXT, available_at TEXT);
CREATE TABLE v_analysis_run (
  run_id INTEGER, as_of TEXT, code_version TEXT, status TEXT, started_at TEXT, finished_at TEXT,
  universe_size INTEGER, planned_units INTEGER, completed_units INTEGER, skipped_units INTEGER,
  failed_units INTEGER, params_json TEXT);
"""


def financial_db(
    tmp_path: Path,
    rows: list[dict[str, Any]],
    version: int = 9,
    runs: list[ss.AnalysisRun] | None = None,
) -> FinancialSource:
    """A financial database holding ``rows`` and ``runs`` (default: one full analysis run)."""
    path = tmp_path / "financial.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.execute("UPDATE schema_version SET version = ?", (version,))
    for run in RUNS if runs is None else runs:
        conn.execute(
            "INSERT INTO v_analysis_run (run_id, as_of, status, failed_units, params_json) "
            "VALUES (?, ?, ?, 0, ?)",
            (run.run_id, run.as_of, run.status, json.dumps(run.params)),
        )
    for r in rows:
        conn.execute(
            f"INSERT INTO v_score_snapshot ({', '.join(ss.COLUMNS)}) VALUES "  # noqa: S608
            f"({', '.join('?' for _ in ss.COLUMNS)})",
            [r[c] for c in ss.COLUMNS],
        )
    conn.commit()
    conn.close()
    return FinancialSource.open(path)


def live_store(make_db: MakeDB) -> Any:
    """A fake store that remembers what was added: graphs exist, and subjects are held, once written."""
    store = make_db()

    def select(sparql: str) -> list[dict[str, str]]:
        written = {g: d for d, _, g in store.added}
        if "LIMIT 1" in sparql and "GRAPH <" in sparql:
            graph = sparql.split("GRAPH <", 1)[1].split(">", 1)[0]
            return [{"s": "x", "p": "x", "o": "x"}] if graph in written else []
        held = b"".join(written.values())
        return [
            {"s": f"{NS}{name}"}
            for name in re.findall(re.escape(NS) + r"([^>]+)>", sparql)
            if f"<{NS}{name}> ".encode() in held  # gate.ingest adds N-Triples
        ]

    store.select = select  # type: ignore[method-assign]
    return store
