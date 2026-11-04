"""Populate the ``:Asset`` / ``:classifiedAs`` / ``:UniverseMembership`` population.

Reads ``portfolio-data-mining``'s point-in-time ``universe.db`` (SCD-2
``universe_membership``: one row per membership stint with ``valid_from`` /
``valid_to``) and emits, for every company line (CIK) or CIK-less symbol in
the S&P 500 index:

* one ``:Asset`` (skipped when ``schema/reference.ttl`` already declares it),
* one ``:UniverseMembership`` per stint, in the single ``:SP500Index``
  ``:Universe``, with ``validFrom`` and (for a closed stint) ``validTo``.

A company that renamed its ticker (``FB``→``META``, ``WLTW``→``WTW``) is ONE
``:Asset``, named by the latest symbol, carrying every stint. Concurrent share
classes under one CIK (``GOOG``/``GOOGL``) stay one ``:Asset`` per symbol, and a
mixed pattern (a rename plus overlapping classes, ``DISCA``/``DISCK``/``WBD``)
is not guessed: it also stays per symbol. A CIK-less stint is grouped by its
symbol. The IRI stays ``:TICKER``; former tickers are not stored here (a later
work item projects ``v_ticker_history``).

``validTo`` is INCLUSIVE, matching upstream's own predicate
``valid_from <= D AND (valid_to IS NULL OR valid_to >= D)``: it is the last day
of membership, so a one-day stint (``valid_from == valid_to``) is real. The
source dates are kept exactly as upstream has them; this module never adds a
day. ``valid_from`` is written as upstream has it: ``1976-07-01`` on a current
member means "in the index before upstream's records begin", not a literal join
date.

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
* One ``:Asset`` per company line when its symbols are a pure succession, and
  one per symbol for concurrent classes, a mixed CIK or a CIK-less stint. A
  ticker reused by different companies over time (``Q``, ``CEG``, ``DELL``, ...)
  is one ``:Asset`` only while the kept stints share its latest ticker; two kept
  CIKs claiming the same latest ticker stop the load rather than silently merge.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
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
    """One ``universe_membership`` row: ``symbol`` was in the index over the
    INCLUSIVE interval ``[valid_from, valid_to]``; ``valid_to`` is ``None`` while it still is."""

    symbol: str
    security: str
    sector: str | None
    sub_industry: str | None
    cik: str | None
    valid_from: str
    valid_to: str | None


@dataclass(frozen=True, slots=True)
class UniverseSummary:
    """What :func:`build_assets` wrote, plus how fresh ``universe.db`` is.

    ``tickers`` is the resolved ``:Asset`` local-name set (a rename chain's
    latest symbol, one per kept company or share class), not every source
    symbol; ``assets_written`` excludes the ``reference.ttl`` assets.
    """

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
    is a stint with ``valid_to < valid_from``: that interval holds on no date.
    A one-day stint (``valid_to == valid_from``) is kept: ``validTo`` is
    inclusive, so it is a real one-day membership.
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
            if row["valid_to"] is not None and row["valid_to"] < row["valid_from"]:
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
                f"asset_master: {len(empty)} universe.db stint(s) end before they start "
                f"(so the inclusive interval holds on no date) and were skipped: "
                + ", ".join(sorted(empty))
            )
    return sorted(stints, key=lambda st: (st.symbol, st.valid_from))


class AssetResolutionError(ValueError):
    """Two kept company groups would claim the same ``:Asset`` IRI (same latest ticker)."""


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    """One ``:Asset`` the loader writes and every stint that belongs to it.

    ``symbol`` is the IRI local name: the latest stint's symbol. ``pattern`` is
    ``single`` (one symbol), ``succession`` (one CIK, non-overlapping symbols),
    ``concurrent`` (one CIK, all symbols overlap: share classes), ``mixed`` (one
    CIK with both patterns, kept per symbol) or ``symbol`` (no CIK).
    """

    symbol: str
    cik: str | None
    stints: tuple[Stint, ...]
    pattern: str

    @property
    def latest(self) -> Stint:
        """The stint that describes the asset today: the latest ``valid_from``."""
        return _latest_stint(list(self.stints))


def _overlaps(left: Stint, right: Stint) -> bool:
    """Whether two stints share at least one day; both intervals are inclusive."""
    left_end = left.valid_to or "9999-12-31"
    right_end = right.valid_to or "9999-12-31"
    return left.valid_from <= right_end and right.valid_from <= left_end


def _pattern(stints: tuple[Stint, ...] | list[Stint]) -> str:
    """Classify one CIK's stints: single, succession, concurrent or mixed."""
    symbols = sorted({stint.symbol for stint in stints})
    if len(symbols) == 1:
        return "single"
    overlapping: set[tuple[str, str]] = set()
    for index, left in enumerate(stints):
        for right in stints[index + 1 :]:
            if left.symbol != right.symbol and _overlaps(left, right):
                first, second = sorted((left.symbol, right.symbol))
                overlapping.add((first, second))
    if not overlapping:
        return "succession"
    all_pairs = {
        (left, right) for index, left in enumerate(symbols) for right in symbols[index + 1 :]
    }
    return "concurrent" if overlapping == all_pairs else "mixed"


def classify_ciks(stints: list[Stint]) -> dict[str, str]:
    """CIK -> pattern for every CIK with at least one stint (the Work item 23 report)."""
    grouped: defaultdict[str, list[Stint]] = defaultdict(list)
    for stint in stints:
        if stint.cik:
            grouped[stint.cik].append(stint)
    return {cik: _pattern(cik_stints) for cik, cik_stints in sorted(grouped.items())}


def _by_symbol(stints: list[Stint]) -> dict[str, list[Stint]]:
    grouped: defaultdict[str, list[Stint]] = defaultdict(list)
    for stint in stints:
        grouped[stint.symbol].append(stint)
    return {
        symbol: sorted(symbol_stints, key=lambda stint: (stint.valid_from, stint.symbol))
        for symbol, symbol_stints in grouped.items()
    }


def resolve_assets(stints: list[Stint]) -> list[ResolvedAsset]:
    """Group stints into the ``:Asset`` individuals the loader writes (T-264).

    One CIK whose symbols' inclusive stints do not overlap is a pure ticker
    succession: ONE asset, named by its latest symbol, carrying every stint.
    Concurrent share classes stay one asset per symbol; a mixed CIK is not
    guessed and also stays per symbol. A CIK-less stint is grouped by symbol.
    A CIK-less stint whose symbol already names a kept asset joins that asset
    (the old ticker-reuse behaviour), and two kept CIKs that would claim the
    same latest ticker stop the load with :class:`AssetResolutionError`.
    """
    by_cik: defaultdict[str, list[Stint]] = defaultdict(list)
    cik_less: defaultdict[str, list[Stint]] = defaultdict(list)
    for stint in stints:
        if stint.cik:
            by_cik[stint.cik].append(stint)
        else:
            cik_less[stint.symbol].append(stint)

    assets: list[ResolvedAsset] = []
    for cik, cik_stints in sorted(by_cik.items()):
        cik_stints.sort(key=lambda stint: (stint.valid_from, stint.symbol))
        pattern = _pattern(cik_stints)
        if pattern == "succession":
            latest = _latest_stint(cik_stints)
            assets.append(ResolvedAsset(latest.symbol, cik, tuple(cik_stints), pattern))
            continue
        for symbol, symbol_stints in _by_symbol(cik_stints).items():
            assets.append(ResolvedAsset(symbol, cik, tuple(symbol_stints), pattern))

    _attach_cik_less(assets, cik_less)
    _refuse_ticker_conflicts(assets)
    return sorted(assets, key=lambda asset: asset.symbol)


def _attach_cik_less(assets: list[ResolvedAsset], cik_less: dict[str, list[Stint]]) -> None:
    """Join a CIK-less stint to the one kept asset that already uses its symbol.

    With no such asset it stays its own symbol asset. If several CIK assets
    already use the symbol, the conflict check refuses the build after this
    pass; choosing one of them here would be a guess.
    """
    by_symbol: defaultdict[str, list[ResolvedAsset]] = defaultdict(list)
    for asset in assets:
        by_symbol[asset.symbol].append(asset)
    for symbol, symbol_stints in sorted(cik_less.items()):
        candidates = by_symbol.get(symbol, [])
        if len(candidates) != 1:
            assets.append(
                ResolvedAsset(
                    symbol,
                    None,
                    tuple(sorted(symbol_stints, key=lambda stint: stint.valid_from)),
                    "symbol",
                )
            )
            continue
        existing = candidates[0]
        combined = (*existing.stints, *symbol_stints)
        replacement = ResolvedAsset(
            existing.symbol,
            existing.cik,
            tuple(sorted(combined, key=lambda stint: (stint.valid_from, stint.symbol))),
            existing.pattern,
        )
        assets[assets.index(existing)] = replacement
        by_symbol[symbol] = [replacement]


def _refuse_ticker_conflicts(assets: list[ResolvedAsset]) -> None:
    """Stop when two kept company groups would produce the same ``:Asset`` IRI."""
    claims: defaultdict[str, list[ResolvedAsset]] = defaultdict(list)
    for asset in assets:
        claims[asset.symbol].append(asset)
    conflicts = {symbol: claimed for symbol, claimed in claims.items() if len(claimed) > 1}
    if not conflicts:
        return
    details = "; ".join(
        f"{symbol}: "
        + ", ".join(
            f"{asset.cik or 'no CIK'} (" + "→".join(stint.symbol for stint in asset.stints) + ")"
            for asset in claimed
        )
        for symbol, claimed in sorted(conflicts.items())
    )
    raise AssetResolutionError(
        f"{len(conflicts)} latest ticker(s) are claimed by more than one kept company: {details}"
    )


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


def _write_membership(out_fh: TextIO, asset_symbol: str, stint: Stint) -> None:
    """One stint as a membership of ``asset_symbol``; the IRI keeps the stint's own symbol.

    A rename chain's old stint therefore keeps ``:UM_FB_…`` while pointing at the
    single ``:META`` asset: the membership's identity and dates do not change
    when the company is folded.
    """
    iri = _membership_iri(stint)
    lines = [
        f"{iri}\n    a :UniverseMembership ;\n",
        f"    :membershipAsset :{asset_symbol} ;\n",
        f"    :membershipUniverse {UNIVERSE_IRI} ;\n",
        f"    :validFrom {date_lit(stint.valid_from)}",
    ]
    if stint.valid_to is not None:
        lines.append(f" ;\n    :validTo {date_lit(stint.valid_to)}")
    lines.append(f" .\n:{asset_symbol} :hasUniverseMembership {iri} .\n\n")
    out_fh.write("".join(lines))


def build_assets(
    stints: list[Stint],
    out_fh: TextIO,
    warnings: list[str],
    already_defined: set[str] | None = None,
    file_mtime: float | None = None,
) -> UniverseSummary:
    """Write the ``:Universe``, the resolved ``:Asset``s and one membership per stint.

    ``resolve_assets`` folds a pure CIK ticker succession into one asset (named
    by its latest symbol) and keeps concurrent share classes, mixed CIKs and
    CIK-less symbols separate. Tickers in ``already_defined`` (those
    ``schema/reference.ttl`` already declares as ``:Asset`` individuals) get
    their memberships but are NOT re-emitted as ``:Asset`` -- ``reference.ttl``
    stays authoritative for them, so re-stating a divergent ``cikNumber`` or
    ``companyName`` here can't raise a functional-property / ``sh:maxCount 1``
    conflict once both files load together. They are still returned in
    ``tickers`` so :mod:`etl.news_to_rdf` can resolve ``scoreSnapshotOfAsset``
    against them; a ticker reused by a different company under another kept CIK
    stops the build instead of being silently merged.
    """
    already_defined = already_defined or set()
    assets = resolve_assets(stints)

    out_fh.write("#################################################################\n")
    out_fh.write("# Section A: Asset / Sector-Industry classification / UniverseMembership\n")
    out_fh.write("# Source: portfolio-data-mining's universe.db (point-in-time, read-only).\n")
    out_fh.write("# One :Asset per company line for a pure ticker succession, or per symbol for\n")
    out_fh.write("# concurrent classes / a mixed CIK / a CIK-less symbol; one membership per\n")
    out_fh.write(
        "# stint (validTo inclusive: its last day of membership). :Sector/:Industry individuals (:Sec_*/:Ind_*)\n"
    )
    out_fh.write("# referenced below are declared in reference.ttl, NOT redeclared here --\n")
    out_fh.write("# load reference.ttl first. Tickers already defined as :Asset in\n")
    out_fh.write("# reference.ttl get memberships but are not re-emitted as :Asset.\n")
    out_fh.write("#################################################################\n\n")
    out_fh.write(f"{UNIVERSE_IRI}\n    a :Universe ;\n")
    out_fh.write('    rdfs:label "S&P 500 index membership (universe.db)" ;\n')
    out_fh.write(
        "    rdfs:seeAlso "
        "<https://spec.edmcouncil.org/fibo/ontology/IND/MarketIndices/BasketIndices/EquityIndex> .\n\n"
    )

    unmapped_sub_industries: set[str] = set()
    sector_mismatches: list[tuple[str, str, str, str]] = []
    assets_written = 0

    for asset in assets:
        latest = asset.latest
        if asset.symbol not in already_defined:
            industry_local = None
            if latest.sub_industry:
                industry_local = gics_rollup.lookup(latest.sub_industry)
                if industry_local is None:
                    unmapped_sub_industries.add(latest.sub_industry)
                elif latest.sector and not gics_rollup.sector_matches(
                    industry_local, latest.sector
                ):
                    sector_mismatches.append(
                        (asset.symbol, latest.sub_industry, industry_local, latest.sector)
                    )
            out_fh.write(f":{asset.symbol}\n    a :Asset ;\n")
            out_fh.write(" ;\n".join(_asset_triples(latest, industry_local)))
            out_fh.write(" .\n\n")
            assets_written += 1
        for stint in asset.stints:
            _write_membership(out_fh, asset.symbol, stint)

    _record_warnings(warnings, unmapped_sub_industries, sector_mismatches)
    return UniverseSummary(
        tickers={asset.symbol for asset in assets},
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
