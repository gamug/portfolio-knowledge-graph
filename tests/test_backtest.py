"""``projection.backtest``: the eight m018 views -> one graph per run (T-207).

The synthetic database is built from handoff §3.2's literal DDL and view SQL in
``tests/fixtures/backtest_rows.py``; every §3.3 nullable case is present, and two windows share
run/book ids so the tests can prove the IRIs and graph names are window- and label-qualified
(T-231/T-232).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.backtest_rows import (
    ASSETS,
    backtest_db,
    load_catalog,
    scenario_rows,
)

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.backtest import (
    VIEWS,
    Projection,
    ProjectionError,
    RunResult,
    graph_name,
    project,
    read_view,
    run,
    universe_assets,
    validation_context,
)
from projection.boundary import (
    BoundaryError,
    check_backtest_source,
    check_source,
    validate,
)
from projection.expectations import load_expectations, load_source
from projection.source import FinancialSource

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)


def _rows(source: FinancialSource) -> dict[str, list[Mapping[str, Any]]]:
    return {view: read_view(source, view) for view in VIEWS}


def _projection(tmp_path: Path, window: str = "P1", label: str = "rule") -> Projection:
    source = FinancialSource.open(backtest_db(tmp_path, window=window))
    try:
        return project(_rows(source), ASSETS, load_catalog(), label)
    finally:
        source.close()


def _graph(projection: Projection, name: str) -> rdflib.Graph:
    return rdflib.Graph().parse(data=projection.turtle(name), format="turtle")


def _run(path: Path, store: GraphDB | None = None, label: str = "rule") -> RunResult:
    source = FinancialSource.open(path)
    try:
        return run(source, ASSETS, load_catalog(), label, store)
    finally:
        source.close()


# --- the boundary and the source check ----------------------------------------------------------


def test_the_synthetic_scenario_passes_the_boundary(tmp_path: Path) -> None:
    source = FinancialSource.open(backtest_db(tmp_path))
    try:
        rows = _rows(source)
        result = validate(
            rows,
            {view: load_expectations()[view] for view in VIEWS},
            source_failures=check_backtest_source(
                source.schema_version, rows["v_book"], load_source()
            ),
        )
    finally:
        source.close()
    assert result.report.stopped is False
    assert result.report.quarantined == []
    assert result.report.inactive == []
    assert {view: len(result.rows[view]) for view in VIEWS} == {
        view: len(rows[view]) for view in VIEWS
    }


def test_a_non_completed_run_is_refused_before_projection(tmp_path: Path) -> None:
    path = backtest_db(tmp_path, status="running")
    source = FinancialSource.open(path)
    try:
        with pytest.raises(BoundaryError) as stop:
            run(source, ASSETS, load_catalog(), "rule")
        assert "backtest_run_status" in str(stop.value)
        assert "not 'completed'" in str(stop.value)
    finally:
        source.close()


def test_the_live_source_check_still_refuses_replay(tmp_path: Path) -> None:
    path = backtest_db(tmp_path, cycle_types=("REPLAY",))
    source = FinancialSource.open(path)
    try:
        failures = check_source(source, load_source())
    finally:
        source.close()
    assert [(failure.view, failure.check) for failure in failures] == [
        ("v_cycle_run", "forbidden_cycle_type")
    ]


# --- identifiers --------------------------------------------------------------------------------


def test_each_run_gets_a_label_and_window_qualified_graph(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    assert set(projection.graphs) == {"urn:graph:derived:backtest:rule:P1:1"}
    assert graph_name("rule", "P1", 1) == "urn:graph:derived:backtest:rule:P1:1"
    assert all(gate.check_target(name) for name in projection.graphs)


def test_two_windows_with_the_same_ids_get_distinct_iris(tmp_path: Path) -> None:
    first = _projection(tmp_path, "P1")
    second = _projection(tmp_path, "P2")
    assert set(first.graphs) == {"urn:graph:derived:backtest:rule:P1:1"}
    assert set(second.graphs) == {"urn:graph:derived:backtest:rule:P2:1"}
    first_iris = {subject for graph in first.graphs.values() for subject, _, _ in graph.triples}
    second_iris = {subject for graph in second.graphs.values() for subject, _, _ in graph.triples}
    assert not first_iris & second_iris


def test_two_labels_with_the_same_window_get_distinct_graphs_and_iris(tmp_path: Path) -> None:
    """The label is the run identity the views do not expose (T-230/T-231)."""
    first = _projection(tmp_path, "P1", "rule")
    second = _projection(tmp_path, "P1", "champ_v1")
    assert set(first.graphs) == {"urn:graph:derived:backtest:rule:P1:1"}
    assert set(second.graphs) == {"urn:graph:derived:backtest:champ_v1:P1:1"}
    first_iris = {subject for graph in first.graphs.values() for subject, _, _ in graph.triples}
    second_iris = {subject for graph in second.graphs.values() for subject, _, _ in graph.triples}
    assert not first_iris & second_iris
    assert graph_name("rule", "P1", 1) != graph_name("champ_v1", "P1", 1)


@pytest.mark.parametrize("label", ["Rule", "r", "rule-1", "rule v2", "_rule", "r" * 33])
def test_a_malformed_run_label_is_refused(tmp_path: Path, label: str) -> None:
    with pytest.raises(ProjectionError, match="run label"):
        graph_name(label, "P1", 1)
    with pytest.raises(ProjectionError, match="run label"):
        _projection(tmp_path, "P1", label)


@pytest.mark.parametrize("window", ["P1", "P2", "P3", "P4", "P12"])
def test_the_window_vocabulary_accepts_any_p_number(tmp_path: Path, window: str) -> None:
    """T-234: the closed P1|P2|P3 list became a pattern, so new data needs no schema change."""
    assert graph_name("rule", window, 1) == f"urn:graph:derived:backtest:rule:{window}:1"
    projection = _projection(tmp_path, window)
    assert set(projection.graphs) == {f"urn:graph:derived:backtest:rule:{window}:1"}


@pytest.mark.parametrize("window", ["Q1", "P", "P1a", "p1", "P-1", "P1 "])
def test_a_malformed_window_is_refused(window: str) -> None:
    with pytest.raises(ProjectionError, match="window_id"):
        graph_name("rule", window, 1)


def test_the_iri_stems_are_the_documented_ones(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path), "urn:graph:derived:backtest:rule:P1:1")
    assert (KG.Book_rule_P1_MARKOWITZ_BASE, rdflib.RDF.type, KG.StrategyBook) in graph
    assert (
        KG.Rebalance_rule_P1_MARKOWITZ_BASE_20220104,
        rdflib.RDF.type,
        KG.BookRebalance,
    ) in graph
    assert (KG.GuardAlert_rule_P1_1, rdflib.RDF.type, KG.GuardAlert) in graph
    assert (KG.GuardAction_rule_P1_1, rdflib.RDF.type, KG.GuardAction) in graph
    assert (
        KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_AAA,
        rdflib.RDF.type,
        KG.BookWeightDaily,
    ) in graph
    assert (
        KG.BookPerf_rule_P1_MARKOWITZ_BASE_20220104,
        rdflib.RDF.type,
        KG.BookDailyPerformance,
    ) in graph
    assert (
        KG.PeriodSummary_rule_P1_MARKOWITZ_BASE_P1,
        rdflib.RDF.type,
        KG.PortfolioPeriodSummary,
    ) in graph
    assert (
        KG.BacktestTest_rule_P1_P1_MARKOWITZ_BASE_TOPN_MV_NOGUARD_memmel_jk,
        rdflib.RDF.type,
        KG.BacktestTest,
    ) in graph


# --- determinism and SHACL ----------------------------------------------------------------------


def test_the_turtle_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first = _projection(tmp_path)
    second = _projection(tmp_path)
    for name in first.graphs:
        assert first.turtle(name) == second.turtle(name)


def test_every_graph_conforms_through_the_ingest_gate(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    context = validation_context(ASSETS, load_catalog())
    for name in projection.graphs:
        gate.validate(gate.parse_batch(projection.turtle(name)), context=context)


# --- nullable columns and links -----------------------------------------------------------------


def test_cash_rows_have_no_asset_node_or_link(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    graph = _graph(projection, "urn:graph:derived:backtest:rule:P1:1")
    cash = KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_CASH
    assert (cash, rdflib.RDF.type, KG.BookWeightDaily) in graph
    assert (cash, KG.holdingAsset, None) not in graph
    assert (KG.CASH, rdflib.RDF.type, KG.Asset) not in graph
    assert projection.cash_rows["v_book_weight_daily"] == 3


def test_the_view_masks_are_omitted_not_invented(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    graph = _graph(projection, "urn:graph:derived:backtest:rule:P1:1")
    layer_one = KG.GuardAlert_rule_P1_1
    assert (layer_one, KG.alertValue, None) not in graph
    assert (KG.GuardAlert_rule_P1_3, KG.alertValue, None) in graph  # layer 2 keeps its value
    layer_three = KG.GuardAlert_rule_P1_4
    assert (layer_three, KG.guardAsset, None) not in graph
    assert (layer_three, KG.guardTicker, None) not in graph
    action_one = KG.GuardAction_rule_P1_1
    assert (action_one, KG.weightBefore, None) not in graph
    assert (action_one, KG.weightAfter, None) not in graph
    assert (KG.GuardAction_rule_P1_3, KG.weightBefore, None) in graph
    ordinary = KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220105_AAA
    assert (ordinary, KG.markowitzTargetWeight, None) not in graph
    assert (ordinary, KG.finalTargetWeight, None) not in graph
    execution = KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_AAA
    assert (execution, KG.markowitzTargetWeight, None) in graph
    assert (KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_CASH, KG.holdingName, None) not in graph


def test_a_book_links_its_children_and_actions_link_alerts(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path), "urn:graph:derived:backtest:rule:P1:1")
    book = KG.Book_rule_P1_MARKOWITZ_BASE
    rebalance = KG.Rebalance_rule_P1_MARKOWITZ_BASE_20220104
    action = KG.GuardAction_rule_P1_1
    alert = KG.GuardAlert_rule_P1_1
    assert (book, KG.bookHasRebalance, rebalance) in graph
    assert (rebalance, KG.rebalanceOfBook, book) in graph
    assert (book, KG.bookHasGuardAction, action) in graph
    assert (action, KG.actionOfBook, book) in graph
    assert (action, KG.actionAlert, alert) in graph
    assert (alert, KG.alertHasGuardAction, action) in graph
    assert (
        book,
        KG.bookHasWeight,
        KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_AAA,
    ) in graph
    assert (
        book,
        KG.bookHasPerformance,
        KG.BookPerf_rule_P1_MARKOWITZ_BASE_20220104,
    ) in graph
    assert (
        book,
        KG.bookHasSummary,
        KG.PeriodSummary_rule_P1_MARKOWITZ_BASE_P1,
    ) in graph


def test_an_asset_is_linked_only_when_the_universe_has_it(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    graph = _graph(projection, "urn:graph:derived:backtest:rule:P1:1")
    assert (KG.GuardAlert_rule_P1_1, KG.guardAsset, KG.AAA) in graph
    assert (KG.GuardAction_rule_P1_1, KG.guardAsset, KG.AAA) in graph
    assert (KG.BookWeight_rule_P1_MARKOWITZ_BASE_20220104_AAA, KG.holdingAsset, KG.AAA) in graph
    zzz = KG.BookWeight_rule_P1_TOPN_MV_NOGUARD_20220106_ZZZ
    assert (zzz, KG.holdingAsset, None) not in graph
    assert (zzz, KG.holdingKey, rdflib.Literal("ZZZ")) in graph
    assert projection.asset_unlinked["v_book_weight_daily"] == 1
    assert projection.asset_unlinked["v_guard_alert"] == 0
    assert projection.asset_unlinked["v_guard_action"] == 0


def test_datatypes_follow_the_ontology(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path), "urn:graph:derived:backtest:rule:P1:1")
    book = KG.Book_rule_P1_MARKOWITZ_BASE
    assert (book, KG.bookId, rdflib.Literal("1", datatype=rdflib.XSD.integer)) in graph
    assert (book, KG.runLabel, rdflib.Literal("rule")) in graph
    assert (
        KG.BacktestTest_rule_P1_P1_MARKOWITZ_BASE_TOPN_MV_NOGUARD_memmel_jk,
        KG.runLabel,
        rdflib.Literal("rule"),
    ) in graph
    assert (
        book,
        KG.excludeHardVetoed,
        rdflib.Literal("false", datatype=rdflib.XSD.boolean),
    ) in graph
    assert (book, KG.guardLayers, None) not in graph  # MARKOWITZ_BASE: NULL, never "[]"
    assert (
        KG.Book_rule_P1_TOPN_MV_GUARD_NO_NLP,
        KG.guardLayers,
        rdflib.Literal("[1, 3, 4]"),
    ) in graph
    assert (
        book,
        KG.knowledgeDate,
        rdflib.Literal("2026-10-31", datatype=rdflib.XSD.date),
    ) in graph
    assert (
        KG.GuardAlert_rule_P1_3,
        KG.alertValue,
        rdflib.Literal("0.3", datatype=rdflib.XSD.decimal),
    ) in graph


def test_every_row_becomes_one_individual(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    assert sum(projection.individuals.values()) == sum(projection.rows.values())
    assert projection.skipped == Counter()
    assert projection.individuals["StrategyBook"] == 3
    assert projection.individuals["GuardAlert"] == 5


def test_the_guard_catalog_maps_the_five_rule_ids_to_their_layers() -> None:
    catalog = load_catalog()
    assert {rule_id: rule.layer for rule_id, rule in catalog.by_id.items()} == {
        "L1_STOP_LOSS": 1,
        "L1_REENTRY": 1,
        "L2_NEWS": 2,
        "L3_VOL": 3,
        "L4_DD": 4,
    }
    assert all(rule.iri == KG[f"Rule_{rule.rule_id}"] for rule in catalog.by_id.values())


# --- refusals -----------------------------------------------------------------------------------


def test_an_unknown_rule_id_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["guard_alert"][0]["rule_id"] = "NOPE"
    with pytest.raises(ProjectionError, match="not a GUARD rule"):
        _run(backtest_db(tmp_path, rows=rows))


def test_a_layer_that_disagrees_with_its_rule_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["guard_alert"][0]["layer"] = 2  # L1_STOP_LOSS is layer 1
    with pytest.raises(ProjectionError, match="disagrees"):
        _run(backtest_db(tmp_path, rows=rows))


def test_a_cash_row_with_an_asset_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["book_weight_daily"][1]["asset_id"] = 1  # the CASH row
    with pytest.raises(ProjectionError, match="CASH row cannot carry"):
        _run(backtest_db(tmp_path, rows=rows))


def test_a_holding_key_that_cannot_form_an_iri_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["book_weight_daily"][0]["holding_key"] = "BAD KEY"
    with pytest.raises(ProjectionError, match="valid IRI local name"):
        _run(backtest_db(tmp_path, rows=rows))


def test_an_action_without_its_alert_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["guard_action"][0]["alert_id"] = 99
    with pytest.raises(ProjectionError, match="not a v_guard_alert row"):
        _run(backtest_db(tmp_path, rows=rows))


def test_a_duplicate_book_iri_is_refused(tmp_path: Path) -> None:
    rows = scenario_rows()
    second_run = dict(rows["backtest_run"][0])
    second_run["id"] = 2
    rows["backtest_run"].append(second_run)
    rows["strategy_book"].append(
        {
            "id": 4,
            "backtest_run_id": 2,
            "arm_code": "MARKOWITZ_BASE",
            "objective": "min_var",
            "exclude_hard_vetoed": 0,
            "guard_layers": None,
        }
    )
    with pytest.raises(ProjectionError, match="share the IRI"):
        _run(backtest_db(tmp_path, rows=rows))


@pytest.mark.parametrize("segment", ["P2a", "P2b", "P2c", "P12z"])
def test_a_new_sub_period_segment_is_accepted(tmp_path: Path, segment: str) -> None:
    """T-234: the closed segment list became P<number>[a-z]?, so a new sub-period needs no edit."""
    rows = scenario_rows()
    for row in rows["backtest_summary"] + rows["backtest_test"]:
        row["segment"] = segment
    source = FinancialSource.open(backtest_db(tmp_path, rows=rows))
    try:
        projection = project(_rows(source), ASSETS, load_catalog(), "rule")
    finally:
        source.close()
    assert set(projection.graphs) == {"urn:graph:derived:backtest:rule:P1:1"}
    assert KG[f"PeriodSummary_rule_P1_MARKOWITZ_BASE_{segment}"] in {
        subject
        for subject, _, _ in projection.graphs["urn:graph:derived:backtest:rule:P1:1"].triples
    }


@pytest.mark.parametrize("segment", ["Q1", "P", "P1A", "p1a", "P1 "])
def test_a_malformed_segment_is_refused(tmp_path: Path, segment: str) -> None:
    rows = scenario_rows()
    rows["backtest_summary"][0]["segment"] = segment
    with pytest.raises(ProjectionError, match="segment"):
        _run(backtest_db(tmp_path, rows=rows))


def test_a_write_hands_the_graph_to_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: Any
) -> None:
    store = make_db()
    written: list[str] = []

    def plan(_store: Any, data: bytes, graph: str, *_args: Any) -> gate.IngestPlan:
        batch = gate.parse_batch(data)
        return gate.IngestPlan(graph, batch, gate.IngestPlanStatus.WOULD_WRITE, len(batch))

    def write(_store: Any, plan: gate.IngestPlan) -> int:
        written.append(plan.graph)
        return plan.triples

    monkeypatch.setattr("projection.backtest.gate.plan", plan)
    monkeypatch.setattr("projection.backtest.gate.write", write)
    result = _run(backtest_db(tmp_path), store=store.db)
    assert written == ["urn:graph:derived:backtest:rule:P1:1"]
    assert result.written == {
        "urn:graph:derived:backtest:rule:P1:1": result.graphs[
            "urn:graph:derived:backtest:rule:P1:1"
        ]
    }
    assert result.store_consulted


def test_a_graph_that_already_exists_is_not_written_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: Any
) -> None:
    store = make_db(rows=[{"s": "x", "p": "x", "o": "x"}])

    def plan(_store: Any, data: bytes, graph: str, *_args: Any) -> gate.IngestPlan:
        return gate.IngestPlan(
            graph,
            gate.parse_batch(data),
            gate.IngestPlanStatus.ALREADY_IN_STORE,
            0,
        )

    monkeypatch.setattr("projection.backtest.gate.plan", plan)
    monkeypatch.setattr(
        "projection.backtest.gate.write",
        lambda *_args, **_kwargs: pytest.fail("a graph that exists must not be written"),
    )
    result = _run(backtest_db(tmp_path), store=store.db)
    assert result.already_in_store == ["urn:graph:derived:backtest:rule:P1:1"]
    assert result.written == {}


def test_the_universe_reader_groups_the_real_stints(tmp_path: Path) -> None:
    path = tmp_path / "universe.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
        "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
    )
    conn.executemany(
        "INSERT INTO universe_membership VALUES (?, ?, NULL, NULL, ?, ?, ?)",
        [
            ("AAA", "AAA Inc.", "0000000001", "2000-01-01", None),
            ("AAA", "AAA Inc.", "0000000001", "1990-01-01", "1999-12-31"),
            ("BBB", "BBB Inc.", None, "2000-01-01", None),
        ],
    )
    conn.commit()
    conn.close()
    assets = universe_assets(path)
    assert assets["AAA"].cik == "0000000001"
    assert assets["AAA"].stints == (
        ("1990-01-01", "1999-12-31"),
        ("2000-01-01", None),
    )
    assert assets["BBB"].cik is None
