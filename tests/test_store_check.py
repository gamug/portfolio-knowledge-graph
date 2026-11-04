"""``projection.store_check``: report would-be-written, skipped and refused graphs (Work item 29)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection import store_check

GRAPH = "urn:graph:derived:backtest:rule:P1:1"
GOOD = b'@prefix : <https://thesis.local/kg/portfolio#> .\n:a a :Asset ; :tickerSymbol "AAA" .\n'


def _plan(status: gate.IngestPlanStatus) -> gate.IngestPlan:
    return gate.IngestPlan(GRAPH, gate.parse_batch(GOOD), status, 2)


def test_a_new_graph_is_reported_as_would_be_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        store_check.gate, "plan", lambda *_args, **_kwargs: _plan(gate.IngestPlanStatus.WOULD_WRITE)
    )
    assert (
        store_check.check_graphs(
            cast(GraphDB, object()), {GRAPH: GOOD}, Path("schema"), label="run"
        )
        is False
    )
    printed = capsys.readouterr().out
    assert f"would-be-written: {GRAPH}" in printed


def test_an_existing_graph_is_reported_as_skipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        store_check.gate,
        "plan",
        lambda *_args, **_kwargs: _plan(gate.IngestPlanStatus.ALREADY_IN_STORE),
    )
    assert store_check.check_graphs(cast(GraphDB, object()), {GRAPH: GOOD}, label="run") is False
    assert f"already-in-the-store: {GRAPH}" in capsys.readouterr().out


def test_a_refused_graph_is_reported_and_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> gate.IngestPlan:
        raise gate.IngestRejected("an individual already exists")

    monkeypatch.setattr(store_check.gate, "plan", refuse)
    assert store_check.check_graphs(cast(GraphDB, object()), {GRAPH: GOOD}, label="run") is True
    printed = capsys.readouterr().out
    assert f"refused: {GRAPH}" in printed
    assert "an individual already exists" in printed
