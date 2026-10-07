"""``etl.asset_master`` and the ``reference.ttl`` ticker skip-set (T-133, ``SPEC.md`` §10).

The skip-set (``SPEC.md`` ETL build steps 1-2, ``src/etl/README.md``) is the tickers
``schema/reference.ttl`` already declares as ``:Asset``: ``reference_asset_tickers()`` reads it
and ``build_assets(already_defined=...)`` writes their memberships but no ``:Asset`` block.
``read_stints``'s ticker-shape and empty-stint filters are tested here too.
"""

from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import pytest
from portfolio_common.db import Database

from etl import asset_master, build_data_ttl
from etl.asset_master import Stint
from etl.common import gics_rollup

_DDL = (
    "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
    "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
)
_INSERT = "INSERT INTO universe_membership VALUES (?,?,?,?,?,?,?)"

Row = tuple[str, str, str | None, str | None, str | None, str, str | None]


def _make_universe_db(path: Path, rows: list[Row]) -> Path:
    db = Database.connect(path)
    try:
        db.execute(_DDL)
        db.executemany(_INSERT, rows)
        db.commit()
    finally:
        db.close()
    return path


def _stint(symbol: str, *, sector: str | None = None, sub_industry: str | None = None) -> Stint:
    """An open stint from 2000-01-01; vary other fields with :func:`dataclasses.replace`."""
    return Stint(symbol, f"{symbol} Inc.", sector, sub_industry, None, "2000-01-01", None)


# --- read_stints: ticker shape and empty stints -----------------------------------------
@pytest.fixture
def universe_db(tmp_path: Path) -> Path:
    rows: list[Row] = [
        ("AAPL", "Apple", "Information Technology", "Technology Hardware", "0000320193",
         "1976-07-01", None),
        ("BRK.B", "Berkshire", "Financials", "Multi-Sector Holdings", "0001067983",
         "2010-02-16", None),
        ("JCP |", "J. C. Penney", None, None, None, "1976-07-01", "2015-01-01"),  # cleaned
        ("BAD SYM", "Junk", None, None, None, "2000-01-01", None),  # not a ticker: skipped
        ("brk", "lowercase", None, None, None, "2000-01-01", None),  # skipped
        ("TOOLONGX", "Too long", None, None, None, "2000-01-01", None),  # skipped
        ("EMPT", "Empty stint", None, None, None, "2020-01-01", "2020-01-01"),  # skipped
        ("EMPT", "Empty stint", None, None, None, "2020-01-01", "2019-01-01"),  # skipped
    ]  # fmt: skip
    return _make_universe_db(tmp_path / "universe.db", rows)


def test_read_stints_keeps_plain_tickers_and_cleans_stray_pipe(universe_db: Path) -> None:
    stints = asset_master.read_stints(universe_db)
    assert [s.symbol for s in stints] == ["AAPL", "BRK.B", "JCP"]
    assert stints[2].valid_to == "2015-01-01"
    assert stints[0].cik == "0000320193"


def test_read_stints_reports_each_filter_in_warnings(universe_db: Path) -> None:
    warnings: list[str] = []
    asset_master.read_stints(universe_db, warnings)
    text = "\n".join(warnings)
    assert "carried a stray '|'" in text and "'JCP |'->'JCP'" in text
    assert "3 universe.db symbol(s) are not plain tickers" in text
    assert "'BAD SYM'" in text and "'brk'" in text and "'TOOLONGX'" in text
    assert "2 universe.db stint(s) end on or before they start" in text


def test_read_stints_is_quiet_for_clean_data(tmp_path: Path) -> None:
    path = _make_universe_db(
        tmp_path / "u.db", [("MSFT", "Microsoft", None, None, "", "1994-06-01", None)]
    )
    warnings: list[str] = []
    stints = asset_master.read_stints(path, warnings)
    assert warnings == [] and stints[0].cik is None


# --- the reference.ttl skip-set ---------------------------------------------------------
def test_reference_asset_tickers_reads_only_asset_tickers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "reference.ttl").write_text(
        "@prefix : <https://thesis.local/kg/portfolio#> .\n"
        ':AAA a :Asset ; :tickerSymbol "AAA" .\n'
        ':BBB a :Asset ; :tickerSymbol "BBB" .\n'
        ':Ind_X a :Industry ; :tickerSymbol "NOTANASSET" .\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KG_SCHEMA_DIR", str(tmp_path))
    assert build_data_ttl.reference_asset_tickers() == {"AAA", "BBB"}


def test_reference_asset_tickers_on_the_real_reference_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KG_SCHEMA_DIR", raising=False)
    assert {"AAPL", "JPM", "XOM", "JNJ", "PG"} <= build_data_ttl.reference_asset_tickers()


def test_build_assets_skips_already_defined_asset_but_keeps_its_memberships() -> None:
    stints = [
        replace(_stint("AAPL"), cik="0000320193"),
        replace(_stint("AAPL"), valid_from="1990-01-01", valid_to="1995-01-01"),
        _stint("MSFT"),
    ]
    out = io.StringIO()
    summary = asset_master.build_assets(stints, out, [], already_defined={"AAPL"})
    ttl = out.getvalue()
    assert ":AAPL\n    a :Asset" not in ttl
    assert ":MSFT\n    a :Asset" in ttl
    assert ttl.count(":membershipAsset :AAPL") == 2
    assert summary.tickers == {"AAPL", "MSFT"}
    assert summary.assets_written == 1
    assert (summary.memberships, summary.open_memberships) == (3, 2)


def test_build_assets_without_skip_set_writes_every_asset() -> None:
    out = io.StringIO()
    summary = asset_master.build_assets([_stint("AAPL"), _stint("MSFT")], out, [])
    assert summary.assets_written == 2
    assert ":AAPL\n    a :Asset" in out.getvalue()


# --- build_assets: GICS rollup warnings -------------------------------------------------
def test_build_assets_warns_on_unmapped_sub_industry_and_omits_classified_as() -> None:
    out = io.StringIO()
    warnings: list[str] = []
    asset_master.build_assets([_stint("NEWCO", sub_industry="Space Elevators")], out, warnings)
    assert ":classifiedAs" not in out.getvalue()
    assert len(warnings) == 1 and "Space Elevators" in warnings[0]


def test_build_assets_warns_on_sector_mismatch() -> None:
    sub, industry = next(iter(gics_rollup.SUB_INDUSTRY_TO_INDUSTRY.items()))
    sector_local = gics_rollup.INDUSTRY_TO_SECTOR[industry]
    right = next(k for k, v in gics_rollup.SECTOR_LOCAL_NAME.items() if v == sector_local)
    wrong = next(k for k, v in gics_rollup.SECTOR_LOCAL_NAME.items() if v != sector_local)

    ok: list[str] = []
    out = io.StringIO()
    asset_master.build_assets([_stint("GOOD", sub_industry=sub, sector=right)], out, ok)
    assert ok == [] and f":classifiedAs :{industry}" in out.getvalue()

    bad: list[str] = []
    asset_master.build_assets([_stint("BAD", sub_industry=sub, sector=wrong)], io.StringIO(), bad)
    assert len(bad) == 1 and "BAD(" in bad[0] and wrong in bad[0]
