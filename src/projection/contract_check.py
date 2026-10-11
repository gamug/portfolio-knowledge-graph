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
a renamed column then makes SQLite reject the view as ``kg_schema.ensure`` creates it, so
``ensure`` raises ``sqlite3.OperationalError`` and the check fails loudly with that error
(the CLI exits non-zero) instead of producing a drift report. A view that is created but
reports no columns is the "did not build" drift below.

The same comparison runs against a running service (T-173): :func:`fetch_contract` reads
``GET /api/v1/contract`` (the columns, from upstream's code) and, if offered,
``GET /api/v1/contract/database`` (what the connected database holds), and
:func:`check_service` adds the two version checks, which compare different numbers:

* ``contract_version`` (the code's highest migration) must equal the one the pin records
  (``_source.json``, written by T-157's re-pin); a pin without the key skips this check with a
  note, never silently;
* the database's ``schema_version`` must not be below the pin's ``schema_version_floor``. Above
  it passes on its number: whether views drifted is decided by the column lists, because a
  version only ever adds columns. A database below the declared ``contract_version`` lags its
  code, which is a note and never fails. A pinned view the database lacks is drift (a
  projector reading it would fail); a view we do not pin is a note.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from types import ModuleType
from typing import Any

from portfolio_common.db import Database

from projection.expectations import SourceExpectation, is_int
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
            v: [
                r[0]
                for r in db.execute(
                    "SELECT name FROM pragma_table_info(?) ORDER BY cid", (v,)
                ).fetchall()
            ]
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
    return compare_columns(upstream_view_columns(upstream_repo))


def compare_columns(actual: dict[str, list[str]]) -> ContractReport:
    """Compare the pin with every upstream view -> its column names in order."""
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


class ContractFetchError(RuntimeError):
    """The service could not be read, or answered something that is not the contract."""


@dataclass(frozen=True)
class DatabaseState:
    """``GET /api/v1/contract/database``: what the database the service is pointed at holds."""

    schema_version: int
    views_present: tuple[str, ...]
    views_missing: tuple[str, ...]


@dataclass(frozen=True)
class DeclaredContract:
    """``GET /api/v1/contract`` and, if the service offers it, ``/contract/database``."""

    contract_version: int
    code_version: str
    columns: dict[str, list[str]]
    database: DatabaseState | None


Fetch = Callable[[str], Any]
_TIMEOUT_SECONDS = 15
#: The real body is a few tens of kilobytes; anything past this is not the contract.
_MAX_BODY_BYTES = 5_000_000


def _get_json(url: str) -> Any:
    """GET ``url`` and parse the JSON body; ``urllib.error.HTTPError`` carries the status."""
    with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) checked by the caller
        body = response.read(_MAX_BODY_BYTES + 1)
    if len(body) > _MAX_BODY_BYTES:
        raise ValueError(f"the answer is longer than {_MAX_BODY_BYTES} bytes")
    return json.loads(body)


def _names(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ContractFetchError(f"{what} must be a list of names")
    return tuple(value)


def _declared_columns(body: dict[str, Any]) -> dict[str, list[str]]:
    views = body.get("views")
    if not isinstance(views, list):
        raise ContractFetchError("/contract has no 'views' list")
    columns: dict[str, list[str]] = {}
    for view in views:
        name = view.get("name") if isinstance(view, dict) else None
        cols = view.get("columns") if isinstance(view, dict) else None
        if not isinstance(name, str) or not isinstance(cols, list):
            raise ContractFetchError(f"/contract: malformed view entry {view!r}")
        if not all(isinstance(c, dict) and isinstance(c.get("name"), str) for c in cols):
            raise ContractFetchError(f"/contract: {name}: columns must be objects with a name")
        if name in columns:
            raise ContractFetchError(f"/contract: view {name} appears twice")
        columns[name] = [c["name"] for c in cols]
    return columns


def _database_state(raw: Any, columns: dict[str, list[str]]) -> DatabaseState:
    """``/contract/database``'s body as a :class:`DatabaseState`, refusing one that breaks the
    documented shape: the two view lists together are exactly the views of ``/contract``."""
    if not isinstance(raw, dict) or not is_int(raw.get("schema_version")):
        raise ContractFetchError("/contract/database has no integer 'schema_version'")
    state = DatabaseState(
        raw["schema_version"],
        _names(raw.get("views_present"), "views_present"),
        _names(raw.get("views_missing"), "views_missing"),
    )
    if sorted((*state.views_present, *state.views_missing)) != sorted(columns):
        raise ContractFetchError(
            "/contract/database: views_present and views_missing must together be exactly "
            "the views of /contract"
        )
    return state


def fetch_contract(base_url: str, fetch: Fetch = _get_json) -> DeclaredContract:
    """Read the service's contract; ``base_url`` ends at the API prefix (``…/api/v1``).

    ``/contract/database`` is optional: a 404 means the service does not offer it, and any
    other failure of that route is an error like one of ``/contract``.
    """
    if not base_url.startswith(("http://", "https://")):
        raise ContractFetchError(f"not an http(s) URL: {base_url}")
    base = base_url.rstrip("/")
    try:
        body = fetch(f"{base}/contract")
    except urllib.error.HTTPError as exc:
        hint = (
            " (the URL should end at the API prefix, for example http://HOST:PORT/api/v1)"
            if exc.code == HTTPStatus.NOT_FOUND
            else ""
        )
        raise ContractFetchError(f"cannot read {base}/contract: {exc}{hint}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ContractFetchError(f"cannot read {base}/contract: {exc}") from exc
    if not isinstance(body, dict) or not is_int(body.get("contract_version")):
        raise ContractFetchError("/contract has no integer 'contract_version'")
    code_version = body.get("code_version")
    columns = _declared_columns(body)
    database: DatabaseState | None = None
    try:
        raw = fetch(f"{base}/contract/database")
    except urllib.error.HTTPError as exc:
        if exc.code != HTTPStatus.NOT_FOUND:
            raise ContractFetchError(f"cannot read {base}/contract/database: {exc}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ContractFetchError(f"cannot read {base}/contract/database: {exc}") from exc
    else:
        database = _database_state(raw, columns)
    return DeclaredContract(
        body["contract_version"],
        code_version if isinstance(code_version, str) else "",
        columns,
        database,
    )


def check_service(declared: DeclaredContract, expected: SourceExpectation) -> ContractReport:
    """The column comparison plus the two version checks (see the module docstring)."""
    report = compare_columns(declared.columns)
    if expected.contract_version is None:
        report.notes.append(
            f"service declares contract_version {declared.contract_version}; the pin records none "
            "(T-157's re-pin writes it), so the contract_version check is skipped"
        )
    elif declared.contract_version != expected.contract_version:
        report.drift.append(
            f"contract_version: the service declares {declared.contract_version}, the pin "
            f"records {expected.contract_version} (re-pin, T-157)"
        )
    db = declared.database
    if db is None:
        report.notes.append("the service does not offer /contract/database; its state is unchecked")
        return report
    if db.schema_version < expected.schema_version_floor:
        report.drift.append(
            f"database: schema_version {db.schema_version} is below the floor "
            f"{expected.schema_version_floor} (a store reader would refuse it)"
        )
    if db.schema_version < declared.contract_version:
        report.notes.append(
            f"database lags its code: schema_version {db.schema_version}, contract_version "
            f"{declared.contract_version}"
        )
    elif db.schema_version > declared.contract_version:
        report.notes.append(
            f"database is newer than its code: schema_version {db.schema_version}, "
            f"contract_version {declared.contract_version} (the service should be upgraded)"
        )
    pinned_missing = [v for v in db.views_missing if v in VIEW_COLUMNS]
    if pinned_missing:
        report.drift.append(
            f"database lacks pinned views {pinned_missing} (a projector reading them would fail)"
        )
    if other := [v for v in db.views_missing if v not in VIEW_COLUMNS]:
        report.notes.append(f"database lacks views we do not pin {other}")
    return report
