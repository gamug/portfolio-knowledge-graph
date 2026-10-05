"""Drift check: the pinned ``v_*`` read contract vs. upstream's ``kg_schema/views.py``.

Builds upstream's views in an in-memory database from a ``portfolio-financial-analysis``
checkout and compares each view's columns with
:data:`projection.view_contract.VIEW_COLUMNS` (``SPEC.md`` §13 item 10). A pinned column
that is gone, a pinned view that is gone or no longer builds, and a new view that is
neither pinned nor in ``NOT_READ`` are drift. A column upstream *added*, or a changed
column order, is reported as a note only: the projector reads columns by name.

Only ``kg_schema`` is loaded from upstream (it needs nothing but ``portfolio_common``),
under a private module name and without touching ``sys.path``, so a ``kg_schema`` already
imported from elsewhere is never reused. The three agent-owned run tables
(``analysis_run``, ``pricing_run``, ``quant_run``) are created by agent modules with
heavier dependencies, so they are stubbed here with just the columns their views select;
a renamed column then makes SQLite reject the view and it is reported as not building --
still drift, with a less precise message.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

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


_UPSTREAM_MODULE = "_upstream_kg_schema"


def _load_kg_schema(upstream_repo: Path) -> ModuleType:
    """Load the checkout's ``kg_schema`` package under :data:`_UPSTREAM_MODULE`."""
    init = upstream_repo / "src" / "kg_schema" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        _UPSTREAM_MODULE, init, submodule_search_locations=[str(init.parent)]
    )
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"no kg_schema package at {init.parent}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_UPSTREAM_MODULE] = module  # its relative imports resolve through this entry
    spec.loader.exec_module(module)
    return module


def _unload_kg_schema() -> None:
    for name in [m for m in sys.modules if m.split(".")[0] == _UPSTREAM_MODULE]:
        del sys.modules[name]


def upstream_view_columns(upstream_repo: Path) -> dict[str, list[str]]:
    """Every upstream ``v_*`` view -> its column names in order ([] if it did not build)."""
    try:
        kg_schema = _load_kg_schema(upstream_repo)
        db = Database.connect(":memory:")
        for ddl in (*_LEGACY_TABLES, *_STUB_TABLES):
            db.execute(ddl)
        kg_schema.ensure(db, run_migrations=True)
        return {
            v: [r[1] for r in db.execute(f"PRAGMA table_info({v})").fetchall()]
            for v in kg_schema.views.VIEWS
        }
    finally:
        _unload_kg_schema()


@dataclass
class ContractReport:
    """``drift`` fails the check; ``notes`` are additive changes worth a look."""

    drift: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check(upstream_repo: Path) -> ContractReport:
    """Compare the pin with upstream's views (see the module docstring for what is drift)."""
    actual = upstream_view_columns(upstream_repo)
    report = ContractReport()
    for view, pinned in VIEW_COLUMNS.items():
        got = actual.get(view)
        if got is None:
            report.drift.append(f"{view}: no longer defined upstream")
        elif not got:
            report.drift.append(
                f"{view}: did not build (a base table or column it selects changed)"
            )
        else:
            if gone := [c for c in pinned if c not in got]:
                report.drift.append(f"{view}: pinned columns removed {gone}")
            if new := [c for c in got if c not in pinned]:
                report.notes.append(f"{view}: columns added upstream {new}")
            if not gone and [c for c in got if c in pinned] != list(pinned):
                report.notes.append(f"{view}: column order changed")
    for view in sorted(set(actual) - set(VIEW_COLUMNS) - set(NOT_READ)):
        report.drift.append(f"{view}: new upstream view, neither pinned nor listed in NOT_READ")
    return report
