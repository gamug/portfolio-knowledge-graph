"""The shared symbol -> :Asset link rule (T-351)."""

from __future__ import annotations

from projection.asset_link import resolve_asset, ticker_cik_map
from projection.backtest import AssetInfo

ASSETS = {
    "META": AssetInfo("META", "0001326801"),
    "FBHS": AssetInfo("FBHS", "0001519751"),
    "GPS": AssetInfo("GPS", "0000039911"),
    "GOOG": AssetInfo("GOOG", "0001652044"),
    "GOOGL": AssetInfo("GOOGL", "0001652044"),
}


def test_an_exact_symbol_wins() -> None:
    link = resolve_asset("META", "0001326801", ASSETS)
    assert link.iri == "META"
    assert link.how == "symbol"


def test_a_unique_same_cik_asset_is_the_fallback() -> None:
    # The catalog still names the company FBHS; the view's canonical symbol is FBIN.
    fb = resolve_asset("FBIN", "0001519751", ASSETS)
    gap = resolve_asset("GAP", "0000039911", ASSETS)
    assert (fb.iri, fb.how) == ("FBHS", "cik")
    assert (gap.iri, gap.how) == ("GPS", "cik")


def test_an_unknown_symbol_and_cik_are_unlinked() -> None:
    link = resolve_asset("ZZZ", "0000000009", ASSETS)
    assert (link.iri, link.how) == (None, "none")


def test_a_cikless_unknown_symbol_is_unlinked() -> None:
    link = resolve_asset("ZZZ", None, ASSETS)
    assert (link.iri, link.how) == (None, "none")


def test_several_same_cik_assets_are_not_guessed() -> None:
    # Concurrent share classes (GOOG/GOOGL) share a CIK: no unique link, so none.
    link = resolve_asset("GOOGL", "0001652044", ASSETS)
    assert link.iri == "GOOGL"  # exact symbol still wins
    link = resolve_asset("GOOGX", "0001652044", ASSETS)
    assert (link.iri, link.how) == (None, "none")


def test_the_ticker_cik_map_uses_both_symbols() -> None:
    rows = [
        {"cik": "0001519751", "symbol": "FBHS", "canonical_symbol": "FBIN"},
        {"cik": "0000039911", "symbol": "GPS", "canonical_symbol": "GAP"},
    ]
    assert ticker_cik_map(rows) == {
        "FBHS": "0001519751",
        "FBIN": "0001519751",
        "GPS": "0000039911",
        "GAP": "0000039911",
    }


def test_the_ticker_cik_map_drops_an_ambiguous_symbol() -> None:
    rows = [
        {"cik": "0000000001", "symbol": "XYZ", "canonical_symbol": "XYZ"},
        {"cik": "0000000002", "symbol": "XYZ", "canonical_symbol": "XYZ"},
    ]
    assert ticker_cik_map(rows) == {}


def test_the_ticker_cik_map_skips_a_missing_cik() -> None:
    rows = [{"cik": None, "symbol": "XYZ", "canonical_symbol": "XYZ"}]
    assert ticker_cik_map(rows) == {}
