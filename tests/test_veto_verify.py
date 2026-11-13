"""Read-only Veto Hierarchy store checks (T-868)."""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import pytest

from projection.load_veto import (
    LoadResult,
    LoadVetoError,
    VetoGraph,
    _masked_asset_prices,
    _old_rule_alerts,
    _price_properties,
    verify_delivery,
)
from projection.veto_manifest import VetoManifest


class FakeStore:
    """A minimal SELECT-only store: counts from ``counts`` and canned check rows."""

    def __init__(
        self,
        counts: dict[str, int],
        *,
        old: Sequence[dict[str, str]] = (),
        prices: Sequence[dict[str, str]] = (),
        masked: Sequence[dict[str, str]] = (),
    ) -> None:
        self.counts = counts
        self._rows = {"old": list(old), "prices": list(prices), "masked": list(masked)}

    def select(self, query: str) -> list[dict[str, str]]:
        if "COUNT(*)" in query:
            graph = query.split("GRAPH <", 1)[1].split(">", 1)[0]
            return [{"n": str(self.counts.get(graph, 0))}]
        if "Rule_L1_STOP_LOSS" in query:
            return self._rows["old"]
        if "pricesNotPublished" in query:
            return self._rows["masked"]
        return self._rows["prices"]


def _result() -> LoadResult:
    meta = VetoGraph("urn:graph:derived:backtest:meta:final", b"", 3, "meta", None, None)
    return LoadResult((), meta)


def test_the_removed_rule_and_price_queries_report_their_rows() -> None:
    store = FakeStore(
        {},
        old=[{"graph": "g", "rule": "Rule_L1_STOP_LOSS"}],
        prices=[{"graph": "g", "alert": "a", "p": "alertValue"}],
        masked=[{"graph": "g", "asset": "FMC", "p": "alertThreshold"}],
    )
    assert _old_rule_alerts(store) == ["g:Rule_L1_STOP_LOSS"]  # type: ignore[arg-type]
    assert _price_properties(store) == ["g:a:alertValue"]  # type: ignore[arg-type]
    assert _masked_asset_prices(store) == ["g:FMC:alertThreshold"]  # type: ignore[arg-type]


def test_a_stored_graph_with_the_projected_count_passes() -> None:
    store = FakeStore({"urn:graph:derived:backtest:meta:final": 3})
    verify_delivery(store, _result(), cast(VetoManifest, SimpleNamespace(control_counts={})))  # type: ignore[arg-type]


def test_a_control_count_mismatch_fails() -> None:
    store = FakeStore({"urn:graph:derived:backtest:meta:final": 2})
    manifest = SimpleNamespace(
        control_counts={"graphs": {"urn:graph:derived:backtest:meta:final": 3}}
    )
    with pytest.raises(LoadVetoError, match="control count"):
        verify_delivery(store, _result(), cast(VetoManifest, manifest))  # type: ignore[arg-type]
