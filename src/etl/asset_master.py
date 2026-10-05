"""Populate the ``:Asset`` / ``:classifiedAs`` / ``:UniverseMembership`` population.

Reads ``portfolio-data-mining``'s point-in-time ``universe.db`` (SCD-2
``universe_membership``: one row per membership stint with ``valid_from`` /
``valid_to``) and emits, for every symbol ever in the S&P 500 index:

* one ``:Asset`` (skipped when ``schema/reference.ttl`` already declares it),
* one ``:UniverseMembership`` per stint, in the single ``:SP500Index``
  ``:Universe``, with ``validFrom`` and (for a closed stint) ``validTo``.

``validTo`` is exclusive, matching upstream's own predicate
``valid_from <= D AND (valid_to IS NULL OR valid_to > D)``. ``valid_from`` is
written as upstream has it: ``1976-07-01`` on a current member means "in the
index before upstream's records begin", not a literal join date.

This is the "canonical population" step, not a replacement for
``reference.ttl`` (which still owns the GICS Sector/Industry taxonomy these
Assets classify against). It reads the file read-only through
``portfolio_common.db`` and touches no SEC EDGAR or pricing source.

Known limits (``SPEC.md`` §2.6 D1):

* ``universe.db`` is refreshed by hand upstream, so it can lag the index;
  :class:`UniverseSummary` carries what the caller needs to show that.
* A closed stint has no CIK, sector or sub-industry upstream. An ``:Asset``
  for a symbol that left the index has only ``tickerSymbol`` and
  ``companyName`` (``AssetShape`` allows that only when every membership is
  closed).
* One ``:Asset`` per symbol, so a ticker reused by different companies over
  time (``Q``, ``CEG``, ``DELL``, ...) is one ``:Asset``, described by its most
  recent stint.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from portfolio_common.db import Database

from etl.common import gics_rollup
from etl.common.turtle_util import date_lit, str_lit

#: ``:Universe`` individual every emitted membership belongs to.
UNIVERSE_IRI = ":SP500Index"

_SQL_STINTS = """
    SELECT symbol, security, gics_sector, gics_sub_industry, cik, valid_from, valid_to
    FROM universe_membership
    ORDER BY symbol, valid_from
"""

_SECONDS_PER_DAY = 86_400

#: A symbol that is safe to use as a Turtle local name: letters/digits plus an
#: optional ``.X`` share-class suffix (``BRK.B``).
_TICKER_RE = re.compile(r"[A-Z0-9]{1,6}(\.[A-Z])?")


@dataclass(frozen=True, slots=True)
class Stint:
    """One ``universe_membership`` row: ``symbol`` was in the index over
    ``[valid_from, valid_to)``; ``valid_to`` is ``None`` while it still is."""

    symbol: str
    security: str
    sector: str | None
    sub_industry: str | None
    cik: str | None
    valid_from: str
    valid_to: str | None


@dataclass(frozen=True, slots=True)
class UniverseSummary:
    """What :func:`build_assets` wrote, plus how fresh ``universe.db`` is."""

    tickers: set[str]
    assets_written: int
    memberships: int
    open_memberships: int
    latest_valid_from: str | None
    file_mtime: float | None

    @property
    def closed_memberships(self) -> int:
        return self.memberships - self.open_memberships

    def freshness_line(self, now: float | None = None) -> str:
        """One line for the end-of-run summary.

        ``latest_valid_from`` is the latest recorded index *change*, not the
        refresh date: a quiet stretch with no changes looks the same as a
        stale file, so the file's modification date is shown beside it.
        """
        now = time.time() if now is None else now
        latest = self.latest_valid_from or "n/a"
        if self.file_mtime is None:
            return f"universe.db latest recorded change (valid_from): {latest}"
        modified = time.strftime("%Y-%m-%d", time.localtime(self.file_mtime))
        age_days = int((now - self.file_mtime) // _SECONDS_PER_DAY)
        return (
            f"universe.db latest recorded change (valid_from): {latest}; "
            f"file last modified {modified} ({age_days} days ago)"
        )


def _clean_symbol(raw: str) -> str:
    """Drop the stray `` |`` that upstream's change-log scrape left on a few
    symbols (``'JCP |'``, ``'ITT |'``)."""
    return raw.strip().rstrip("|").strip()


def read_stints(db_path: str | Path, warnings: list[str] | None = None) -> list[Stint]:
    """Read every membership stint from ``universe.db``, read-only.

    A symbol that is still not a plain ticker after :func:`_clean_symbol` is
    skipped (it cannot be a Turtle local name) and reported in ``warnings``. So
    is a stint with ``valid_to <= valid_from``: ``validTo`` is exclusive, so it
    holds on no date.
    """
    stints: list[Stint] = []
    cleaned: set[str] = set()
    skipped: set[str] = set()
    empty: set[str] = set()
    db = Database.connect(db_path, read_only=True)
    try:
        for row in db.execute(_SQL_STINTS).fetchall():
            symbol = _clean_symbol(row["symbol"])
            if not _TICKER_RE.fullmatch(symbol):
                skipped.add(row["symbol"])
                continue
            if row["valid_to"] is not None and row["valid_to"] <= row["valid_from"]:
                empty.add(f"{symbol} ({row['valid_from']}..{row['valid_to']})")
                continue
            if symbol != row["symbol"]:
                cleaned.add(f"{row['symbol']!r}->{symbol!r}")
            stints.append(
                Stint(
                    symbol=symbol,
                    security=row["security"],
                    sector=row["gics_sector"],
                    sub_industry=row["gics_sub_industry"],
                    cik=row["cik"] or None,
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                )
            )
    finally:
        db.close()
    if warnings is not None:
        if cleaned:
            warnings.append(
                f"asset_master: {len(cleaned)} universe.db symbol(s) carried a stray '|' from "
                f"upstream's change-log scrape and were cleaned: " + ", ".join(sorted(cleaned))
            )
        if skipped:
            warnings.append(
                f"asset_master: {len(skipped)} universe.db symbol(s) are not plain tickers and "
                f"were skipped: " + ", ".join(sorted(map(repr, skipped)))
            )
        if empty:
            warnings.append(
                f"asset_master: {len(empty)} universe.db stint(s) end on or before they start "
                f"(validTo is exclusive, so they hold on no date) and were skipped: "
                + ", ".join(sorted(empty))
            )
    return sorted(stints, key=lambda st: (st.symbol, st.valid_from))


def _latest_stint(stints: list[Stint]) -> Stint:
    """The stint that describes the asset today: the latest ``valid_from``."""
    return max(stints, key=lambda s: s.valid_from)


def _asset_triples(latest: Stint, industry_local: str | None) -> list[str]:
    """Build the predicate-object lines for one ``:Asset`` block."""
    triples = [
        f"    :tickerSymbol {str_lit(latest.symbol)}",
        f"    :companyName {str_lit(latest.security)}",
    ]
    if latest.cik:
        triples.append(f"    :cikNumber {str_lit(latest.cik)}")
    if industry_local is not None:
        triples.append(f"    :classifiedAs :{industry_local}")
    return triples


def _membership_iri(stint: Stint) -> str:
    return f":UM_{stint.symbol}_{stint.valid_from}"


def _write_membership(out_fh: TextIO, stint: Stint) -> None:
    iri = _membership_iri(stint)
    lines = [
        f"{iri}\n    a :UniverseMembership ;\n",
        f"    :membershipAsset :{stint.symbol} ;\n",
        f"    :membershipUniverse {UNIVERSE_IRI} ;\n",
        f"    :validFrom {date_lit(stint.valid_from)}",
    ]
    if stint.valid_to is not None:
        lines.append(f" ;\n    :validTo {date_lit(stint.valid_to)}")
    lines.append(f" .\n:{stint.symbol} :hasUniverseMembership {iri} .\n\n")
    out_fh.write("".join(lines))


def build_assets(
    stints: list[Stint],
    out_fh: TextIO,
    warnings: list[str],
    already_defined: set[str] | None = None,
    file_mtime: float | None = None,
) -> UniverseSummary:
    """Write the ``:Universe``, one ``:Asset`` per symbol and one
    ``:UniverseMembership`` per stint to ``out_fh``.

    Tickers in ``already_defined`` (those ``schema/reference.ttl`` already
    declares as ``:Asset`` individuals) get their memberships but are NOT
    re-emitted as ``:Asset`` -- ``reference.ttl`` stays authoritative for them,
    so re-stating a divergent ``cikNumber`` or ``companyName`` here can't raise
    a functional-property / ``sh:maxCount 1`` conflict once both files load
    together. They are still returned in ``tickers`` so :mod:`etl.news_to_rdf`
    can resolve ``scoreSnapshotOfAsset`` against them.
    """
    already_defined = already_defined or set()
    by_symbol: dict[str, list[Stint]] = {}
    for stint in stints:
        by_symbol.setdefault(stint.symbol, []).append(stint)

    out_fh.write("#################################################################\n")
    out_fh.write("# Section A: Asset / Sector-Industry classification / UniverseMembership\n")
    out_fh.write("# Source: portfolio-data-mining's universe.db (point-in-time, read-only).\n")
    out_fh.write("# One :Asset per symbol ever in the index, one :UniverseMembership per\n")
    out_fh.write("# stint (validTo exclusive). :Sector/:Industry individuals (:Sec_*/:Ind_*)\n")
    out_fh.write("# referenced below are declared in reference.ttl, NOT redeclared here --\n")
    out_fh.write("# load reference.ttl first. Tickers already defined as :Asset in\n")
    out_fh.write("# reference.ttl get memberships but are not re-emitted as :Asset.\n")
    out_fh.write("#################################################################\n\n")
    out_fh.write(f"{UNIVERSE_IRI}\n    a :Universe ;\n")
    out_fh.write('    rdfs:label "S&P 500 index membership (universe.db)" .\n\n')

    unmapped_sub_industries: set[str] = set()
    sector_mismatches: list[tuple[str, str, str, str]] = []
    assets_written = 0

    for symbol, symbol_stints in by_symbol.items():
        if symbol not in already_defined:
            latest = _latest_stint(symbol_stints)
            industry_local = None
            if latest.sub_industry:
                industry_local = gics_rollup.lookup(latest.sub_industry)
                if industry_local is None:
                    unmapped_sub_industries.add(latest.sub_industry)
                elif latest.sector and not gics_rollup.sector_matches(
                    industry_local, latest.sector
                ):
                    sector_mismatches.append(
                        (symbol, latest.sub_industry, industry_local, latest.sector)
                    )
            out_fh.write(f":{symbol}\n    a :Asset ;\n")
            out_fh.write(" ;\n".join(_asset_triples(latest, industry_local)))
            out_fh.write(" .\n\n")
            assets_written += 1
        for stint in symbol_stints:
            _write_membership(out_fh, stint)

    _record_warnings(warnings, unmapped_sub_industries, sector_mismatches)
    return UniverseSummary(
        tickers=set(by_symbol),
        assets_written=assets_written,
        memberships=len(stints),
        open_memberships=sum(1 for s in stints if s.valid_to is None),
        latest_valid_from=max((s.valid_from for s in stints), default=None),
        file_mtime=file_mtime,
    )


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
