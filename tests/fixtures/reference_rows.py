"""Synthetic ticker-history and orchestrator databases for the reference projector tests (T-356).

The table DDL is the m015/m016 schema; the three ``CREATE VIEW`` statements are copied from the
completed v18 database. The default scenario covers the exact, unique-CIK and unlinked asset-link
cases, the inclusive ticker interval, a multi-date evidence cell, and full/minimal orchestrator
rows so the optional-property path is exercised without inventing values.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from projection.backtest import AssetInfo

#: The loaded catalog the projector must see. ``FBIN`` and ``GAP`` are deliberately absent;
#: their companies are present under the older symbols ``FBHS`` and ``GPS`` (same CIK).
ASSETS: dict[str, AssetInfo] = {
    "META": AssetInfo("META", "0001326801", (("2013-12-23", "2022-06-08"), ("2022-06-09", None))),
    "FBHS": AssetInfo("FBHS", "0001519751", (("2016-06-22", "2022-12-18"),)),
    "GPS": AssetInfo("GPS", "0000039911", (("1976-07-01", "2022-02-02"),)),
    "WBD": AssetInfo("WBD", "0001437107", (("2022-04-11", None),)),
}

_DDL = """
CREATE TABLE schema_version (version INTEGER, applied_at TEXT, description TEXT);
INSERT INTO schema_version VALUES (18, 'x', 'x');

CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    company_name TEXT,
    cik TEXT
);

CREATE TABLE ticker_history (
    cik              TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    valid_from       TEXT NOT NULL,
    valid_to         TEXT,
    canonical_symbol TEXT NOT NULL,
    evidence_url     TEXT NOT NULL,
    evidence_date    TEXT NOT NULL,
    rules            TEXT,
    PRIMARY KEY (cik, symbol, valid_from)
);

CREATE TABLE orchestrator_run (
    id            INTEGER PRIMARY KEY,
    handle        TEXT,
    kind          TEXT,
    as_of         TEXT,
    surface       TEXT,
    settings_json TEXT,
    status        TEXT,
    started_at    TEXT,
    finished_at   TEXT,
    code_version  TEXT
);

CREATE TABLE orchestrator_step (
    id                  INTEGER PRIMARY KEY,
    orchestrator_run_id INTEGER NOT NULL REFERENCES orchestrator_run(id),
    ordinal             INTEGER NOT NULL,
    step                TEXT,
    argv_json           TEXT,
    status              TEXT,
    started_at          TEXT,
    finished_at         TEXT,
    exit_code           INTEGER,
    run_kind            TEXT,
    run_id              INTEGER,
    reason              TEXT,
    output_tail         TEXT,
    UNIQUE (orchestrator_run_id, ordinal)
);
"""

_VIEWS = """
CREATE VIEW v_ticker_history AS
        SELECT t.cik, t.symbol, t.valid_from, t.valid_to, t.canonical_symbol,
               a.id AS asset_id, t.evidence_url, t.evidence_date, t.rules
        FROM ticker_history t
        LEFT JOIN assets a ON a.cik = t.cik AND a.ticker = t.canonical_symbol;

CREATE VIEW v_orchestrator_run AS
        SELECT id AS run_id, kind, as_of, code_version, status, started_at, finished_at,
               settings_json, handle, surface
        FROM orchestrator_run;

CREATE VIEW v_orchestrator_step AS
        SELECT s.orchestrator_run_id, r.handle, s.ordinal, s.step, s.status,
               s.started_at, s.finished_at, s.exit_code, s.run_kind, s.run_id, s.reason,
               s.argv_json, s.output_tail
        FROM orchestrator_step s JOIN orchestrator_run r ON r.id = s.orchestrator_run_id;
"""


def scenario_rows() -> dict[str, list[dict[str, Any]]]:
    """The default scenario: 9 ticker rows (4 exact, 4 by CIK, 1 unlinked) and 2 runs."""
    evidence = "https://example.test/rename"
    return {
        "v_ticker_history": [
            # FB -> META: a pure rename, canonical symbol loaded exactly.
            {
                "cik": "0001326801",
                "symbol": "FB",
                "valid_from": "2013-12-23",
                "valid_to": "2022-06-08",
                "canonical_symbol": "META",
                "evidence_url": evidence,
                "evidence_date": "2022-05-31",
                "rules": "L-11;APP-10a",
            },
            {
                "cik": "0001326801",
                "symbol": "META",
                "valid_from": "2022-06-09",
                "valid_to": None,
                "canonical_symbol": "META",
                "evidence_url": evidence,
                "evidence_date": "2022-05-31",
                "rules": "L-11;APP-10a",
            },
            # FBHS -> FBIN: the catalog still names the company FBHS, same CIK.
            {
                "cik": "0001519751",
                "symbol": "FBHS",
                "valid_from": "2016-06-22",
                "valid_to": "2022-12-14",
                "canonical_symbol": "FBIN",
                "evidence_url": evidence,
                "evidence_date": "2022-12-15",
                "rules": "L-11;APP-10a",
            },
            {
                "cik": "0001519751",
                "symbol": "FBIN",
                "valid_from": "2022-12-15",
                "valid_to": None,
                "canonical_symbol": "FBIN",
                "evidence_url": evidence,
                "evidence_date": "2022-12-15",
                "rules": "L-11;APP-10a",
            },
            # GPS -> GAP: the same fallback.
            {
                "cik": "0000039911",
                "symbol": "GPS",
                "valid_from": "1976-07-01",
                "valid_to": "2024-08-21",
                "canonical_symbol": "GAP",
                "evidence_url": evidence,
                "evidence_date": "2024-08-08",
                "rules": "L-11;APP-10a",
            },
            {
                "cik": "0000039911",
                "symbol": "GAP",
                "valid_from": "2024-08-22",
                "valid_to": None,
                "canonical_symbol": "GAP",
                "evidence_url": evidence,
                "evidence_date": "2024-08-08",
                "rules": "L-11;APP-10a",
            },
            # DISCA -> WBD: exact canonical, but two evidence dates in one cell.
            {
                "cik": "0001437107",
                "symbol": "DISCA",
                "valid_from": "1976-07-01",
                "valid_to": "2022-04-10",
                "canonical_symbol": "WBD",
                "evidence_url": "https://example.test/a ; https://example.test/b",
                "evidence_date": "2022-04-07 ; 2022-04-10",
                "rules": "L-11;APP-10a",
            },
            {
                "cik": "0001437107",
                "symbol": "WBD",
                "valid_from": "2022-04-11",
                "valid_to": None,
                "canonical_symbol": "WBD",
                "evidence_url": evidence,
                "evidence_date": "2022-04-10",
                "rules": "L-11;APP-10a",
            },
            # No :ZZZ and no other asset under this CIK: must stay unlinked and be counted.
            {
                "cik": "0000000009",
                "symbol": "ZZZ",
                "valid_from": "2020-01-01",
                "valid_to": None,
                "canonical_symbol": "ZZZ",
                "evidence_url": evidence,
                "evidence_date": "2020-01-01",
                "rules": None,
            },
        ],
        "v_orchestrator_run": [
            {
                "run_id": 1,
                "handle": "run-1",
                "kind": "pipeline",
                "as_of": "2026-11-03",
                "surface": "cli",
                "settings_json": '{"universe": "SP500"}',
                "status": "completed",
                "started_at": "2026-11-03T10:00:00+00:00",
                "finished_at": "2026-11-03T10:05:00+00:00",
                "code_version": "v1",
            },
            {
                "run_id": 2,
                "handle": None,
                "kind": None,
                "as_of": None,
                "surface": None,
                "settings_json": None,
                "status": None,
                "started_at": None,
                "finished_at": None,
                "code_version": None,
            },
        ],
        "v_orchestrator_step": [
            {
                "orchestrator_run_id": 1,
                "ordinal": 1,
                "step": "analysis",
                "argv_json": "[]",
                "status": "completed",
                "started_at": "2026-11-03T10:00:00+00:00",
                "finished_at": "2026-11-03T10:01:00+00:00",
                "exit_code": 0,
                "run_kind": "analysis",
                "run_id": 7,
                "reason": None,
                "output_tail": "[]",
            },
            {
                "orchestrator_run_id": 1,
                "ordinal": 2,
                "step": "cycle",
                "argv_json": '["cycle", "monitor"]',
                "status": "failed",
                "started_at": None,
                "finished_at": None,
                "exit_code": 1,
                "run_kind": "cycle",
                "run_id": 8,
                "reason": "boom",
                "output_tail": None,
            },
            {
                "orchestrator_run_id": 2,
                "ordinal": 1,
                "step": None,
                "argv_json": None,
                "status": None,
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "run_kind": None,
                "run_id": None,
                "reason": None,
                "output_tail": None,
            },
        ],
    }


def reference_db(
    tmp_path: Path,
    *,
    name: str | None = None,
    rows: dict[str, list[dict[str, Any]]] | None = None,
) -> Path:
    """Write one synthetic v18 database with the three views and return its path."""
    path = tmp_path / (name or "reference.db")
    path.unlink(missing_ok=True)
    data = scenario_rows() if rows is None else rows
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.executescript(_VIEWS)
    conn.executemany(
        "INSERT INTO assets VALUES (?, ?, ?, ?)",
        [
            (1, "META", "Meta Platforms", "0001326801"),
            (2, "FBHS", "Fortune Brands", "0001519751"),
            (3, "GPS", "Gap", "0000039911"),
            (4, "WBD", "Warner Bros. Discovery", "0001437107"),
        ],
    )
    for view, table_rows in data.items():
        if not table_rows:
            continue
        table = view.removeprefix("v_")
        columns = list(table_rows[0])
        if view == "v_orchestrator_run":
            columns = ["id" if column == "run_id" else column for column in columns]
        elif view == "v_orchestrator_step":
            columns = [column for column in columns if column != "id"]
        sources = [
            "run_id" if view == "v_orchestrator_run" and column == "id" else column
            for column in columns
        ]
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES "  # noqa: S608 -- test constants
            f"({', '.join('?' for _ in columns)})",
            [[row[source] for source in sources] for row in table_rows],
        )
    conn.commit()
    conn.close()
    return path


def rows_without(
    data: dict[str, list[dict[str, Any]]], table: str, index: int = 0
) -> dict[str, list[dict[str, Any]]]:
    """A copy of ``data`` with one row removed from ``table``."""
    copy = {name: [dict(row) for row in rows] for name, rows in data.items()}
    del copy[table][index]
    return copy
