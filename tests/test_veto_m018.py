"""Configuration-keyed m018 projection for the final delivery (Work item 46, T-850)."""

from __future__ import annotations

from pathlib import Path

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db, final_scenario_rows, load_catalog

from projection.backtest import ProjectionError, SourceProjection, project_source
from projection.source import FinancialSource

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
GRAPH = "urn:graph:derived:backtest:final:P1:system_with_hierarchy"


def _project(tmp_path: Path) -> SourceProjection:
    rows = final_scenario_rows("P1")
    rows["backtest_test"].append(
        {
            "backtest_run_id": 1,
            "segment": "P1",
            "arm_a": "TOPN_MV_GUARD_NO_NLP",
            "arm_b": "MARKOWITZ_BASE",
            "test": "memmel_jk",
            "statistic": 1.0,
            "p_value": 0.1,
            "n_obs": 100,
            "params_json": None,
        }
    )
    source = FinancialSource.open(backtest_db(tmp_path, rows=rows))
    try:
        return project_source(
            source,
            ASSETS,
            load_catalog(),
            "final",
            configuration="SYSTEM_WITH_HIERARCHY",
            window="P1",
            book_code="TOPN_MV_GUARD_NO_NLP",
            book_id=3,
        )
    finally:
        source.close()


def test_the_configured_book_gets_the_configuration_keyed_graph_and_iri(tmp_path: Path) -> None:
    projected = _project(tmp_path)
    assert set(projected.projection.graphs) == {GRAPH}
    book = KG.Book_final_P1_system_with_hierarchy
    graph = rdflib.Graph()
    for triple in projected.projection.graphs[GRAPH].triples:
        graph.add(triple)
    assert (book, rdflib.RDF.type, KG.StrategyBook) in graph
    assert (book, KG.configuration, KG.Configuration_SystemWithHierarchy) in graph
    assert (book, KG.armCode, rdflib.Literal("TOPN_MV_GUARD_NO_NLP")) in graph


def test_the_twin_book_and_its_actions_are_filtered_out(tmp_path: Path) -> None:
    projected = _project(tmp_path)
    assert projected.filter is not None
    assert projected.filter.configuration == "SYSTEM_WITH_HIERARCHY"
    assert projected.filter.removed["v_book"] == 3  # the fixture has four books; one is kept
    assert projected.filter.removed["v_guard_action"] > 0
    graph = rdflib.Graph()
    for triple in projected.projection.graphs[GRAPH].triples:
        graph.add(triple)
    assert not list(graph.subjects(KG.armCode, rdflib.Literal("TOPN_MV_NOGUARD")))
    assert not list(graph.subjects(KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))


def test_the_configuration_keyed_iris_and_tests_are_used(tmp_path: Path) -> None:
    projected = _project(tmp_path)
    graph = rdflib.Graph()
    for triple in projected.projection.graphs[GRAPH].triples:
        graph.add(triple)
    alerts = set(graph.subjects(rdflib.RDF.type, KG.GuardAlert))
    tests = set(graph.subjects(rdflib.RDF.type, KG.BacktestTest))
    assert alerts
    assert all("system_with_hierarchy" in str(alert) for alert in alerts)
    assert tests
    assert all("system_with_hierarchy" in str(test) for test in tests)
    assert all(
        graph.value(test, KG.armA)
        in (rdflib.Literal("TOPN_MV_GUARD_NO_NLP"), rdflib.Literal("MARKOWITZ_BASE"))
        and graph.value(test, KG.armB)
        in (rdflib.Literal("TOPN_MV_GUARD_NO_NLP"), rdflib.Literal("MARKOWITZ_BASE"))
        for test in tests
    )


def test_a_removed_guard_rule_stops_the_load(tmp_path: Path) -> None:
    rows = final_scenario_rows("P1")
    rows["guard_alert"][0]["rule_id"] = "L1_STOP_LOSS"
    source = FinancialSource.open(backtest_db(tmp_path, rows=rows))
    try:
        with pytest.raises(ProjectionError, match="not a GUARD rule"):
            project_source(
                source,
                ASSETS,
                load_catalog(),
                "final",
                configuration="SYSTEM_WITH_HIERARCHY",
                window="P1",
                book_code="TOPN_MV_GUARD_NO_NLP",
                book_id=3,
            )
    finally:
        source.close()
