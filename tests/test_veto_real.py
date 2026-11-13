"""The pilot delivery through the Veto Hierarchy key (Work item 46, T-852, opt-in).

Run with ``-m integration`` and ``VETO_PILOT_DB=<path to H1C-B5-P1.db>``. The pilot is opened
read-only; no store is contacted. It exercises the manifest key against real m018 rows: the
with-hierarchy System book, its loaded actions/alerts and its four System-vs-Markowitz tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import rdflib

from projection.backtest import load_guard_catalog, project_source, read_view, reference_assets
from projection.source import FinancialSource

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
PILOT = Path(
    "/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/piloto_H1C_P1/H1C-B5-P1.db"
)
GRAPH = "urn:graph:derived:backtest:final:P1:system_with_hierarchy"


def _pilot() -> Path:
    value = os.environ.get("VETO_PILOT_DB")
    path = Path(value) if value else PILOT
    if not path.is_file():
        pytest.skip(f"VETO_PILOT_DB={path} is not a file")
    return path


@pytest.mark.integration
def test_the_pilot_system_book_projects_under_the_configuration_key() -> None:
    source = FinancialSource.open(_pilot())
    try:
        books = read_view(source, "v_book")
        book = next(row for row in books if row["book_id"] == 3)
        projected = project_source(
            source,
            reference_assets("schema/reference.ttl"),
            load_guard_catalog("schema/rules.ttl"),
            "final",
            configuration="SYSTEM_WITH_HIERARCHY",
            window=str(book["window_id"]),
            book_code="TOPN_MV_GUARD_NO_NLP",
            book_id=3,
        )
    finally:
        source.close()
    assert set(projected.projection.graphs) == {GRAPH}
    assert projected.projection.individuals == {
        "BookWeightDaily": 5506,
        "GuardAction": 321,
        "GuardAlert": 251,
        "BookDailyPerformance": 196,
        "BookRebalance": 10,
        "BacktestTest": 4,
        "StrategyBook": 1,
        "PortfolioPeriodSummary": 1,
    }
    assert projected.filter is not None
    assert projected.filter.removed["v_book"] == 2
    graph = rdflib.Graph()
    for triple in projected.projection.graphs[GRAPH].triples:
        graph.add(triple)
    book_iri = KG.Book_final_P1_system_with_hierarchy
    assert (book_iri, KG.configuration, KG.Configuration_SystemWithHierarchy) in graph
    assert not list(graph.subjects(KG.alertRule, KG.Rule_L1_STOP_LOSS))
    assert not list(graph.subjects(KG.alertRule, KG.Rule_L2_NEWS))
    for alert in graph.subjects(KG.alertRule, KG.Rule_L1_BP_STOP):
        assert (alert, KG.alertThreshold, None) not in graph
        assert (alert, KG.alertValue, None) not in graph
