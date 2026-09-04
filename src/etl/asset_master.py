"""Populate the full S&P 500 ``:Asset`` / ``:classifiedAs`` population.

Reads the "List of S&P 500 companies" table (Symbol, Security, GICS Sector,
GICS Sub-Industry, CIK) from Wikipedia and extends the 5 worked-example Assets
in ``schema/reference.ttl`` to the real ~503-constituent universe. This is the
"canonical population" step, not a replacement for ``reference.ttl`` (which
still owns the GICS Sector/Industry taxonomy these Assets classify against).

Deliberately does NOT touch SEC EDGAR or any pricing/trading source -- the CIK
value used here is Wikipedia's own CIK column (originally sourced from SEC, but
read from the table this ETL parses, not fetched from an EDGAR service). No
filing or pricing data is fetched.
"""

from __future__ import annotations

import urllib.request
from html.parser import HTMLParser
from typing import TextIO

from etl.common import gics_rollup
from etl.common.turtle_util import str_lit

#: Minimum cell count for a row of the constituent table to be treated as data
#: (Symbol, Security, GICS Sector, GICS Sub-Industry, HQ, Date added, CIK, ...).
_MIN_TABLE_COLS = 7

#: Column indices within a data row.
_COL_TICKER = 0
_COL_COMPANY = 1
_COL_SECTOR = 2
_COL_SUB_INDUSTRY = 3
_COL_CIK = 6


class _SP500TableParser(HTMLParser):
    """Extracts the first ``wikitable``-classed table's rows as lists of cell text."""

    def __init__(self) -> None:
        super().__init__()
        self.in_target_table: bool = False
        self.found_first_table: bool = False
        self.rows: list[list[str]] = []
        self.cur_row: list[str] | None = None
        self.cur_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        cls = attr_map.get("class") or ""
        if tag == "table" and not self.found_first_table and "wikitable" in cls:
            self.in_target_table = True
            self.found_first_table = True
        elif tag == "tr" and self.in_target_table:
            self.cur_row = []
        elif tag in ("td", "th") and self.in_target_table:
            self.cur_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.in_target_table:
            self.in_target_table = False
        elif tag == "tr" and self.in_target_table and self.cur_row is not None:
            self.rows.append(self.cur_row)
            self.cur_row = None
        elif tag in ("td", "th") and self.in_target_table and self.cur_cell is not None:
            if self.cur_row is not None:
                self.cur_row.append("".join(self.cur_cell).strip())
            self.cur_cell = None

    def handle_data(self, data: str) -> None:
        if self.in_target_table and self.cur_cell is not None:
            self.cur_cell.append(data)


def fetch_sp500_rows(source_url: str) -> list[dict[str, str]]:
    """Return one dict per constituent: ``ticker, company, sector, sub_industry, cik``."""
    if not source_url.startswith(("http://", "https://")):
        raise ValueError(f"source_url must be an http(s) URL, got: {source_url!r}")

    req = urllib.request.Request(  # noqa: S310 - scheme validated just above
        source_url, headers={"User-Agent": "Mozilla/5.0 (thesis research script)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - same guard
        html = resp.read().decode("utf-8", errors="replace")

    parser = _SP500TableParser()
    parser.feed(html)
    data_rows = [r for r in parser.rows if len(r) >= _MIN_TABLE_COLS][1:]  # drop header

    return [
        {
            "ticker": r[_COL_TICKER].strip(),
            "company": r[_COL_COMPANY].strip(),
            "sector": r[_COL_SECTOR].strip(),
            "sub_industry": r[_COL_SUB_INDUSTRY].strip(),
            "cik": r[_COL_CIK].strip(),
        }
        for r in data_rows
    ]


def _asset_triples(row: dict[str, str], industry_local: str | None) -> list[str]:
    """Build the predicate-object lines for one ``:Asset`` block."""
    triples = [
        f"    :tickerSymbol {str_lit(row['ticker'])}",
        f"    :companyName {str_lit(row['company'])}",
    ]
    if row["cik"]:
        triples.append(f"    :cikNumber {str_lit(row['cik'])}")
    if industry_local is not None:
        triples.append(f"    :classifiedAs :{industry_local}")
    return triples


def build_assets(
    rows: list[dict[str, str]],
    out_fh: TextIO,
    warnings: list[str],
    already_defined: set[str] | None = None,
) -> set[str]:
    """Write one Turtle block per ``:Asset`` to ``out_fh``.

    Tickers in ``already_defined`` (those ``schema/reference.ttl`` already
    declares as ``:Asset`` individuals) are NOT re-emitted -- ``reference.ttl``
    stays authoritative for them, so re-stating a divergent ``cikNumber`` or
    ``companyName`` here can't raise a functional-property / ``sh:maxCount 1``
    conflict once both files load together. They are still returned in the
    written-tickers set so :mod:`etl.news_to_rdf` can resolve
    ``scoreSnapshotOfAsset`` against them.

    Returns the set of tickers usable as ``:Asset`` targets.
    """
    already_defined = already_defined or set()
    written_tickers: set[str] = set()
    unmapped_sub_industries: set[str] = set()
    sector_mismatches: list[tuple[str, str, str, str]] = []
    skipped = 0

    out_fh.write("#################################################################\n")
    out_fh.write("# Section A: Asset / Sector-Industry classification\n")
    out_fh.write('# Source: Wikipedia "List of S&P 500 companies" (fetched at build time).\n')
    out_fh.write("# Extends schema/reference.ttl's worked-example Assets to the full\n")
    out_fh.write("# current S&P 500 constituent list. :Sector/:Industry individuals\n")
    out_fh.write("# (:Sec_*/:Ind_*) referenced below are declared in reference.ttl,\n")
    out_fh.write("# NOT redeclared here -- load reference.ttl first. Tickers already\n")
    out_fh.write("# defined as :Asset in reference.ttl are skipped below by design.\n")
    out_fh.write("#################################################################\n\n")

    for row in rows:
        ticker = row["ticker"]
        written_tickers.add(ticker)
        if ticker in already_defined:
            skipped += 1
            continue

        industry_local = gics_rollup.lookup(row["sub_industry"])
        if industry_local is None:
            unmapped_sub_industries.add(row["sub_industry"])
        elif not gics_rollup.sector_matches(industry_local, row["sector"]):
            sector_mismatches.append((ticker, row["sub_industry"], industry_local, row["sector"]))

        out_fh.write(f":{ticker}\n    a :Asset ;\n")
        out_fh.write(" ;\n".join(_asset_triples(row, industry_local)))
        out_fh.write(" .\n\n")

    if skipped:
        out_fh.write(f"# ({skipped} ticker(s) already in reference.ttl were not re-emitted.)\n\n")
    _record_warnings(warnings, unmapped_sub_industries, sector_mismatches)
    return written_tickers


def _record_warnings(
    warnings: list[str],
    unmapped_sub_industries: set[str],
    sector_mismatches: list[tuple[str, str, str, str]],
) -> None:
    if unmapped_sub_industries:
        warnings.append(
            f"asset_master: {len(unmapped_sub_industries)} GICS Sub-Industry value(s) had no "
            f"rollup entry in etl/common/gics_rollup.py (Asset written WITHOUT classifiedAs): "
            + ", ".join(sorted(unmapped_sub_industries))
        )
    if sector_mismatches:
        warnings.append(
            f"asset_master: {len(sector_mismatches)} ticker(s) whose rolled-up Industry's sector "
            f"disagrees with the row's own GICS Sector column (possible rollup-table typo): "
            + ", ".join(f"{t}({si}->{il} vs {sec})" for t, si, il, sec in sector_mismatches)
        )
