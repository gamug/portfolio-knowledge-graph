"""``cli/load_universe.py`` as a subprocess: the entry point really runs (T-220).

The loader's logic lives in ``kg_store.universe`` and is tested in ``test_universe_load.py``;
these run the script itself, as constitution Project structure #10 asks, over a synthetic
``universe.db`` passed through the environment. None of them writes or contacts the store.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.universe_rows import Row, universe_db

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_universe.py"

_HISTORICAL_ROWS: list[Row] = [
    (
        "LUMN",
        "Lumen Technologies",
        "Communication Services",
        "Alternative Carriers",
        "0000018926",
        "1976-07-01",
        None,
    ),
    (
        "WBA",
        "Walgreens Boots Alliance",
        "Consumer Staples",
        "Drug Retail",
        "0001618921",
        "1976-07-01",
        None,
    ),
    (
        "MHK",
        "Mohawk Industries",
        "Consumer Discretionary",
        "Home Furnishings",
        "0000851968",
        "2013-12-23",
        None,
    ),
    (
        "WHR",
        "Whirlpool Corporation",
        "Consumer Discretionary",
        "Household Appliances",
        "0000106640",
        "1976-07-01",
        None,
    ),
    (
        "NWL",
        "Newell Brands",
        "Consumer Discretionary",
        "Housewares & Specialties",
        "0000814453",
        "1976-07-01",
        None,
    ),
    (
        "PBCT",
        "People's United Financial",
        "Financials",
        "Thrifts & Mortgage Finance",
        "0001378946",
        "1976-07-01",
        None,
    ),
]


def _run(
    tmp_path: Path,
    *args: str,
    db: Path | None = None,
    repository: str = "test",
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        # The shell's environment wins over .env (load_env does not override it).
        "SQL_UNIVERSE_DB": str(db or tmp_path / "universe.db"),
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
    }
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, tmp_path arguments
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )


def test_a_dry_run_reports_the_catalog_and_writes_nothing(tmp_path: Path) -> None:
    db = universe_db(tmp_path / "universe.db")
    result = _run(tmp_path, "--as-of", "2026-11-03", db=db)
    assert result.returncode == 0, result.stderr
    assert "kept 4 of 6 stint(s) over 4 symbol(s)" in result.stdout
    assert "dropped 2 stint(s) over 2 symbol(s)" in result.stdout
    assert (
        "Assets: 3 written, 1 already in reference.ttl (4 symbol(s) -> 4 asset(s))" in result.stdout
    )
    assert "Memberships: 4 (3 open, 1 closed)" in result.stdout
    assert "urn:graph:universe:2026-Q4" in result.stdout
    assert "triples: 37" in result.stdout
    assert "SHACL: conforms" in result.stdout
    assert "dry run, nothing written" in result.stdout


def test_a_dry_run_maps_the_historical_sub_industries_without_a_warning(
    tmp_path: Path,
) -> None:
    db = universe_db(tmp_path / "universe.db", _HISTORICAL_ROWS)
    result = _run(tmp_path, "--as-of", "2026-11-03", db=db)
    assert result.returncode == 0, result.stderr
    assert "had no rollup entry" not in result.stdout
    for name in (
        "Alternative Carriers",
        "Drug Retail",
        "Home Furnishings",
        "Household Appliances",
        "Housewares & Specialties",
        "Thrifts & Mortgage Finance",
    ):
        assert name not in result.stdout


def test_as_of_names_the_quarter_graph(tmp_path: Path) -> None:
    db = universe_db(tmp_path / "universe.db")
    result = _run(tmp_path, "--as-of", "2027-01-01", db=db)
    assert result.returncode == 0, result.stderr
    assert "urn:graph:universe:2027-Q1" in result.stdout


def test_a_bad_date_is_a_bad_argument(tmp_path: Path) -> None:
    db = universe_db(tmp_path / "universe.db")
    result = _run(tmp_path, "--since", "yesterday", db=db)
    assert result.returncode == 2
    assert "not a YYYY-MM-DD date" in result.stderr


def test_to_production_without_write_exits_2(tmp_path: Path) -> None:
    db = universe_db(tmp_path / "universe.db")
    result = _run(tmp_path, "--to-production", db=db)
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    db = universe_db(tmp_path / "universe.db")
    result = _run(tmp_path, "--write", db=db, repository="portfolio")
    assert result.returncode == 2
    assert "needs --to-production" in result.stderr


def test_two_kept_ciks_claiming_one_ticker_stop_the_run(tmp_path: Path) -> None:
    rows: list[Row] = [
        ("CEG", "Constellation Energy Group", None, None, "0000000001", "1990-01-01",
         "2012-03-12"),
        ("CEG", "Constellation Energy", "Utilities", "Electric Utilities", "0000000002",
         "2022-02-02", None),
    ]  # fmt: skip
    db = universe_db(tmp_path / "universe.db", rows=rows)
    result = _run(tmp_path, "--since", "1900-01-01", db=db)
    assert result.returncode == 1
    assert "STOPPED" in result.stderr
    assert "latest ticker" in result.stderr
    assert "0000000001" in result.stderr and "0000000002" in result.stderr


def test_a_missing_database_exits_1(tmp_path: Path) -> None:
    result = _run(tmp_path)  # no database was written at tmp_path/universe.db
    assert result.returncode == 1
    assert "source error:" in result.stderr
