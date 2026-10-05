"""Drift check: the pinned ``v_*`` read contract vs. upstream's ``kg_schema/views.py``.

Builds upstream's views in an in-memory database from an ``portfolio-financial-analysis``
checkout and compares each view's columns, in order, with
:data:`projection.view_contract.VIEW_COLUMNS` (``SPEC.md`` §13 item 10).

Only ``kg_schema`` is imported from upstream (it needs nothing but ``portfolio_common``).
The three agent-owned run tables (``analysis_run``, ``pricing_run``, ``quant_run``) are
created by agent modules with heavier dependencies, so they are stubbed here with just the
columns their views select; a renamed column then makes SQLite reject the view and it is
reported as missing -- still a failure, with a less precise message.
"""

from __future__ import annotations

import sys
from pathlib import Path

from portfolio_common.db import Database

from projection.view_contract import NOT_READ, VIEW_COLUMNS

_RUN_UNITS = (
    "id INTEGER PRIMARY KEY, as_of TEXT, code_version TEXT, status TEXT, started_at TEXT, "
    "finished_at TEXT, universe_size INTEGER, planned_units INTEGER, completed_units INTEGER, "
    "skipped_units INTEGER, failed_units INTEGER, params_json TEXT"
)
_STUB_TABLES = (
    f"CREATE TABLE analysis_run ({_RUN_UNITS})",
    f"CREATE TABLE pricing_run ({_RUN_UNITS})",
    (
        "CREATE TABLE quant_run (id INTEGER PRIMARY KEY, command TEXT, as_of TEXT, code_version TEXT, "
        "engine_version TEXT, status TEXT, started_at TEXT, finished_at TEXT, error TEXT, "
        "params_json TEXT)"
    ),
)
# Pre-kg_schema tables the agents create themselves (upstream tests/test_kg_schema.py).
_LEGACY_TABLES = (
    "CREATE TABLE sectors (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)",
    (
        "CREATE TABLE assets (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL UNIQUE, company_name TEXT, "
        "cik TEXT, sector_id INTEGER, sub_industry TEXT)"
    ),
    (
        "CREATE TABLE sec_filings (id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL, form TEXT NOT "
        "NULL, fiscal_year INTEGER NOT NULL, fiscal_period TEXT NOT NULL, filing_date TEXT, "
        "accession_number TEXT, period_end TEXT, retrieved_at TEXT NOT NULL, "
        "UNIQUE (asset_id, form, fiscal_period))"
    ),
    (
        "CREATE TABLE financial_facts (id INTEGER PRIMARY KEY, filing_id INTEGER NOT NULL, statement "
        "TEXT NOT NULL, concept TEXT NOT NULL, standard_concept TEXT, label TEXT, period_key TEXT NOT "
        "NULL, value REAL, UNIQUE (filing_id, statement, concept, period_key))"
    ),
    (
        "CREATE TABLE fundamental_metrics (id INTEGER PRIMARY KEY, filing_id INTEGER NOT NULL, "
        "metric_group TEXT NOT NULL, metric_name TEXT NOT NULL, value REAL, unit TEXT, inputs_json "
        "TEXT, computed_at TEXT NOT NULL, UNIQUE (filing_id, metric_group, metric_name))"
    ),
    (
        "CREATE TABLE fundamental_snapshot (id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL, "
        "filing_id INTEGER NOT NULL, form TEXT NOT NULL, fiscal_period TEXT NOT NULL, score REAL NOT "
        "NULL, rating TEXT NOT NULL, narrative TEXT NOT NULL, strengths_json TEXT, risks_json TEXT, "
        "model TEXT NOT NULL, metrics_json TEXT, created_at TEXT NOT NULL, "
        "UNIQUE (asset_id, form, fiscal_period))"
    ),
)


def upstream_view_columns(upstream_repo: Path) -> dict[str, list[str]]:
    """Every upstream ``v_*`` view -> its column names in order ([] if it did not build)."""
    sys.path.insert(0, str(upstream_repo / "src"))
    try:
        import kg_schema  # noqa: PLC0415 - importable only once the checkout is on sys.path
        from kg_schema.views import VIEWS  # noqa: PLC0415 - same: upstream is path-injected

        db = Database.connect(":memory:")
        for ddl in (*_LEGACY_TABLES, *_STUB_TABLES):
            db.execute(ddl)
        kg_schema.ensure(db, run_migrations=True)
        return {v: [r[1] for r in db.execute(f"PRAGMA table_info({v})").fetchall()] for v in VIEWS}
    finally:
        sys.path.remove(str(upstream_repo / "src"))


def check(upstream_repo: Path) -> list[str]:
    """Return one message per drift between the pin and upstream (empty = no drift)."""
    actual = upstream_view_columns(upstream_repo)
    problems: list[str] = []
    for view, pinned in VIEW_COLUMNS.items():
        got = actual.get(view)
        if got is None:
            problems.append(f"{view}: no longer defined upstream")
        elif not got:
            problems.append(f"{view}: did not build (a base table or column it selects changed)")
        elif got != list(pinned):
            gone, new = sorted(set(pinned) - set(got)), sorted(set(got) - set(pinned))
            order = "" if (gone or new) else " (same columns, different order)"
            problems.append(f"{view}: removed {gone}, added {new}{order}")
    for view in sorted(set(actual) - set(VIEW_COLUMNS) - set(NOT_READ)):
        problems.append(f"{view}: new upstream view, neither pinned nor listed in NOT_READ")
    return problems
