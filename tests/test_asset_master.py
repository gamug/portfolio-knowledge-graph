"""Ticker skip-set logic of ``etl.asset_master.read_stints`` (T-133, ``SPEC.md`` §10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl import asset_master


@pytest.fixture
def universe_db(tmp_path: Path) -> Path:
    path = tmp_path / "universe.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
        "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
    )
    rows = [
        (
            "AAPL",
            "Apple",
            "Information Technology",
            "Technology Hardware",
            "0000320193",
            "1976-07-01",
            None,
        ),
        (
            "BRK.B",
            "Berkshire",
            "Financials",
            "Multi-Sector Holdings",
            "0001067983",
            "2010-02-16",
            None,
        ),
        ("JCP |", "J. C. Penney", None, None, None, "1976-07-01", "2015-01-01"),  # cleaned
        ("BAD SYM", "Junk", None, None, None, "2000-01-01", None),  # not a ticker: skipped
        ("brk", "lowercase", None, None, None, "2000-01-01", None),  # skipped
        ("TOOLONGX", "Too long", None, None, None, "2000-01-01", None),  # skipped
        ("EMPT", "Empty stint", None, None, None, "2020-01-01", "2020-01-01"),  # skipped
        ("EMPT", "Empty stint", None, None, None, "2020-01-01", "2019-01-01"),  # skipped
    ]
    con.executemany("INSERT INTO universe_membership VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_read_stints_keeps_plain_tickers_and_cleans_stray_pipe(universe_db: Path) -> None:
    stints = asset_master.read_stints(universe_db)
    assert [s.symbol for s in stints] == ["AAPL", "BRK.B", "JCP"]
    assert stints[2].valid_to == "2015-01-01"
    assert stints[0].cik == "0000320193"


def test_read_stints_reports_each_skip_class_in_warnings(universe_db: Path) -> None:
    warnings: list[str] = []
    asset_master.read_stints(universe_db, warnings)
    text = "\n".join(warnings)
    assert "carried a stray '|'" in text and "'JCP |'->'JCP'" in text
    assert "3 universe.db symbol(s) are not plain tickers" in text
    assert "'BAD SYM'" in text and "'brk'" in text and "'TOOLONGX'" in text
    assert "2 universe.db stint(s) end on or before they start" in text


def test_read_stints_is_quiet_for_clean_data(tmp_path: Path) -> None:
    path = tmp_path / "u.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
        "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
    )
    con.execute(
        "INSERT INTO universe_membership VALUES ('MSFT','Microsoft',NULL,NULL,'','1994-06-01',NULL)"
    )
    con.commit()
    con.close()
    warnings: list[str] = []
    stints = asset_master.read_stints(path, warnings)
    assert warnings == [] and stints[0].cik is None
