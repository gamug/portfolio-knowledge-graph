"""The selection-side projector: six views -> one sibling graph per run (Work item 26).

Hermetic, over the synthetic two-label, two-window backtest database of
``tests/fixtures/backtest_rows.py``. The real-database row-count test is opt-in and lives in
``tests/test_selection_real.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db

from kg_store import gate
from projection.asset_link import ticker_cik_map
from projection.backtest import (
    SELECTION_VIEWS,
    AssetInfo,
    Projection,
    ProjectionError,
    load_selection_catalog,
    project_selection,
    read_view,
    run_selection,
    selection_graph_name,
)
from projection.boundary import check_backtest_source, validate
from projection.expectations import load_expectations, load_source
from projection.source import FinancialSource

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)
CATALOG = load_selection_catalog(Path(__file__).resolve().parent.parent / "schema" / "rules.ttl")


def _rows(tmp_path: Path, window: str = "P1") -> dict[str, list[dict[str, Any]]]:
    source = FinancialSource.open(backtest_db(tmp_path, window=window))
    try:
        rows = {view: read_view(source, view) for view in ("v_book", *SELECTION_VIEWS)}
        rows["v_ticker_history"] = read_view(source, "v_ticker_history")
    finally:
        source.close()
    return cast(dict[str, list[dict[str, Any]]], rows)


def _projection(tmp_path: Path, label: str = "rule", window: str = "P1") -> Projection:
    rows = _rows(tmp_path, window)
    return project_selection(
        rows,
        ASSETS,
        CATALOG,
        label,
        ticker_cik_map(rows["v_ticker_history"]),
    )


def _graph(projection: Projection, label: str = "rule", window: str = "P1") -> rdflib.Graph:
    name = selection_graph_name(label, window, 1)
    return rdflib.Graph().parse(data=projection.turtle(name), format="turtle")


# --- graph name and the gate --------------------------------------------------------------------


def test_the_selection_graph_is_a_sibling_of_the_m018_graph() -> None:
    assert selection_graph_name("rule", "P1", 1) == "urn:graph:derived:backtest:selection:rule:P1:1"
    assert gate.check_target("urn:graph:derived:backtest:selection:rule:P1:1") is True
    assert gate.check_target("urn:graph:derived:backtest:selection:champ_v1:P12:999") is True


@pytest.mark.parametrize(
    "name",
    [
        "urn:graph:derived:backtest:selection:Rule:P1:1",
        "urn:graph:derived:backtest:selection:rule:P1a:1",
        "urn:graph:derived:backtest:selection:rule:P1:0",
        "urn:graph:derived:backtest:selection:rule:P1:1/extra",
        "urn:graph:derived:backtest:selection:rule:P1",
    ],
)
def test_a_malformed_selection_graph_is_refused(name: str) -> None:
    with pytest.raises(gate.IngestRejected, match="not an ingest target"):
        gate.check_target(name)


def test_the_m018_graph_name_is_still_accepted_and_distinct() -> None:
    assert gate.check_target("urn:graph:derived:backtest:rule:P1:1") is True


# --- boundary and projection --------------------------------------------------------------------


def test_the_synthetic_selection_passes_the_boundary(tmp_path: Path) -> None:
    source = FinancialSource.open(backtest_db(tmp_path))
    try:
        rows = {view: read_view(source, view) for view in ("v_book", *SELECTION_VIEWS)}
        failures = check_backtest_source(source.schema_version, rows["v_book"], load_source())
    finally:
        source.close()
    result = validate(
        {view: rows[view] for view in SELECTION_VIEWS},
        {view: load_expectations()[view] for view in SELECTION_VIEWS},
        source_failures=failures,
    )
    assert result.report.stopped is False
    assert result.report.quarantined == []
    assert result.report.inactive == []


def test_every_selection_row_becomes_one_individual(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    assert set(projection.graphs) == {"urn:graph:derived:backtest:selection:rule:P1:1"}
    assert projection.individuals == {
        "SelectionCycle": 7,
        "AttractivenessWeightScheme": 7,
        "WeightComponent": 33,  # 21 configured + 12 effective
        "AttractivenessSnapshot": 5,
        "Veto": 3,
    }
    rows = _rows(tmp_path)
    assert sum(projection.individuals.values()) == sum(len(rows[view]) for view in SELECTION_VIEWS)


def test_the_selection_graph_is_shacl_valid(tmp_path: Path) -> None:
    source = FinancialSource.open(backtest_db(tmp_path))
    try:
        result = run_selection(source, ASSETS, CATALOG, "rule")
    finally:
        source.close()
    assert result.report.stopped is False
    assert result.checked == ["urn:graph:derived:backtest:selection:rule:P1:1"]
    assert result.written == {}
    assert result.store_consulted is False


# --- ranking, components and placeholders -------------------------------------------------------


def test_a_ranking_links_its_cycle_scheme_and_asset(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path))
    snap = KG["Snap_rule_P1_7_1"]
    assert (snap, rdflib.RDF.type, KG.AttractivenessSnapshot) in graph
    assert (snap, KG.attractivenessOfAsset, KG.AAA) in graph
    assert (snap, KG.rankingTicker, rdflib.Literal("AAA")) in graph
    assert (snap, KG.rankingOfCycle, KG["Cycle_rule_P1_7"]) in graph
    assert (snap, KG.computedWithScheme, KG["Scheme_rule_P1_7"]) in graph
    assert (
        snap,
        KG.rankPosition,
        rdflib.Literal("1", datatype=rdflib.XSD.integer),
    ) in graph
    assert (
        snap,
        KG.selectedForBook,
        rdflib.Literal("true", datatype=rdflib.XSD.boolean),
    ) in graph
    assert (
        snap,
        KG.targetWeight,
        rdflib.Literal("0.5", datatype=rdflib.XSD.decimal),
    ) in graph
    components = set(graph.objects(snap, KG.hasEffectiveWeight))
    assert {str(graph.value(c, KG.weightMetricName)) for c in components} == {
        "ScoreFinanciero",
        "ScoreCuantitativo",
        "ScoreTecnico",
    }
    assert (
        KG["Cycle_rule_P1_7"],
        KG.cycleRunId,
        rdflib.Literal("7", datatype=rdflib.XSD.integer),
    ) in graph


def test_an_unlinked_ticker_keeps_its_literal_and_is_counted(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    graph = _graph(projection)
    snap = KG["Snap_rule_P1_7_4"]  # ZZZ is in the backtest database, not the universe fixture
    assert (snap, KG.rankingTicker, rdflib.Literal("ZZZ")) in graph
    assert (snap, KG.attractivenessOfAsset, None) not in graph
    assert projection.asset_unlinked["v_cycle_ranking"] == 1
    assert projection.asset_unlinked["v_veto"] == 1


def test_a_selection_ticker_uses_the_unique_same_cik_asset(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    rows["v_cycle_ranking"][0]["ticker"] = "FBIN"
    assets = {**ASSETS, "FBHS": AssetInfo("FBHS", "0001519751")}
    projection = project_selection(rows, assets, CATALOG, "rule", {"FBIN": "0001519751"})
    graph = _graph(projection)
    snap = KG["Snap_rule_P1_7_1"]
    assert (snap, KG.attractivenessOfAsset, KG.FBHS) in graph
    assert (snap, KG.rankingTicker, rdflib.Literal("FBIN")) in graph


def test_a_selection_ticker_with_an_ambiguous_cik_stays_unlinked(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    rows["v_cycle_ranking"][0]["ticker"] = "GOOGX"
    assets = {
        **ASSETS,
        "GOOG": AssetInfo("GOOG", "0001652044"),
        "GOOGL": AssetInfo("GOOGL", "0001652044"),
    }
    projection = project_selection(rows, assets, CATALOG, "rule", {"GOOGX": "0001652044"})
    graph = _graph(projection)
    snap = KG["Snap_rule_P1_7_1"]
    assert (snap, KG.attractivenessOfAsset, None) not in graph
    assert projection.asset_unlinked["v_cycle_ranking"] == 2  # GOOGX + ZZZ


def test_a_selection_ticker_with_no_cik_and_no_exact_asset_stays_unlinked(
    tmp_path: Path,
) -> None:
    rows = _rows(tmp_path)
    rows["v_cycle_ranking"][0]["ticker"] = "NEW"
    projection = project_selection(rows, ASSETS, CATALOG, "rule", {})
    graph = _graph(projection)
    snap = KG["Snap_rule_P1_7_1"]
    assert (snap, KG.attractivenessOfAsset, None) not in graph
    assert projection.asset_unlinked["v_cycle_ranking"] == 2  # NEW + ZZZ


def test_a_no_component_row_stays_a_visible_placeholder(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path))
    snap = KG["Snap_rule_P1_7_3"]  # BRK.B: components_json has three nulls
    score = graph.value(snap, KG.attractivenessScore)
    assert isinstance(score, rdflib.Literal) and float(str(score)) == 0.0
    assert set(graph.objects(snap, KG.hasEffectiveWeight)) == set()
    assert (
        snap,
        KG.vetoedAtRanking,
        rdflib.Literal("true", datatype=rdflib.XSD.boolean),
    ) in graph
    assert (
        snap,
        KG.vetoRulesJson,
        rdflib.Literal('["UNSCORED"]'),
    ) in graph


def test_a_non_completed_cycle_run_skips_its_ranking_and_components(
    tmp_path: Path,
) -> None:
    rows = _rows(tmp_path)
    rows["v_cycle_run"][6]["status"] = "failed"
    rows["v_cycle_ranking"] = [{**row, "status": "failed"} for row in rows["v_cycle_ranking"]]
    projection = project_selection(rows, ASSETS, CATALOG, "rule")
    assert projection.individuals["AttractivenessSnapshot"] == 0
    assert projection.individuals["WeightComponent"] == 21  # configured only
    assert projection.skipped["v_cycle_ranking: run is not completed"] == 5
    assert projection.skipped["v_cycle_ranking_component: ranking row not projected"] == 12


# --- vetoes and rule resolution -----------------------------------------------------------------


def test_a_liquidity_veto_resolves_to_the_definition_in_force_on_the_run_date(
    tmp_path: Path,
) -> None:
    graph = _graph(_projection(tmp_path))
    for veto in graph.subjects(rdflib.RDF.type, KG.Veto):
        if graph.value(veto, KG.vetoTicker) == rdflib.Literal("BBB"):
            assert graph.value(veto, KG.appliesRule) == KG.Rule_LIQUIDITY_DISTRESS_v11
            assert graph.value(veto, KG.primaryRule) == KG.Rule_LIQUIDITY_DISTRESS_v11
            assert graph.value(veto, KG.raisedOn) == rdflib.Literal(
                "2021-12-01", datatype=rdflib.XSD.date
            )
            assert graph.value(veto, KG.clearedOn) == rdflib.Literal(
                "2021-12-15", datatype=rdflib.XSD.date
            )
            break
    else:
        pytest.fail("no BBB veto")


def test_an_unknown_rule_id_stops_with_the_id_and_the_run_date(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    rows["v_veto"][0]["rule_id"] = "NOT_A_RULE"
    with pytest.raises(ProjectionError) as stop:
        project_selection(rows, ASSETS, CATALOG, "rule")
    message = str(stop.value)
    assert "NOT_A_RULE" in message
    assert "2026-10-31" in message
    assert "unknown ruleId" in message


def test_a_veto_links_its_asset_or_keeps_its_ticker(tmp_path: Path) -> None:
    graph = _graph(_projection(tmp_path))
    linked = KG["Veto_rule_P1_1"]  # CCC
    unlinked = KG["Veto_rule_P1_3"]  # ZZZ
    assert (linked, KG.vetoOfAsset, KG.CCC) in graph
    assert (unlinked, KG.vetoTicker, rdflib.Literal("ZZZ")) in graph
    assert (unlinked, KG.vetoOfAsset, None) not in graph


def test_evidence_json_is_not_projected(tmp_path: Path) -> None:
    text = _projection(tmp_path).turtle("urn:graph:derived:backtest:selection:rule:P1:1").decode()
    assert "123.45" not in text
    assert "evidence" not in text.lower()
    assert "current_ratio" not in text


# --- labels and windows -------------------------------------------------------------------------


def test_two_labels_on_one_window_get_distinct_graphs_and_iris(tmp_path: Path) -> None:
    first = _projection(tmp_path, "rule", "P1")
    second = _projection(tmp_path, "champ_v1", "P1")
    assert set(first.graphs) == {"urn:graph:derived:backtest:selection:rule:P1:1"}
    assert set(second.graphs) == {"urn:graph:derived:backtest:selection:champ_v1:P1:1"}
    first_iris = {subject for builder in first.graphs.values() for subject, _, _ in builder.triples}
    second_iris = {
        subject for builder in second.graphs.values() for subject, _, _ in builder.triples
    }
    assert first_iris.isdisjoint(second_iris)


# --- writing through the gate -------------------------------------------------------------------


def _run_selection(path: Path, store: Any = None) -> Any:
    source = FinancialSource.open(path)
    try:
        return run_selection(source, ASSETS, CATALOG, "rule", store)
    finally:
        source.close()


def test_a_write_hands_the_selection_graph_to_the_gate(
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
    result = _run_selection(backtest_db(tmp_path), store=store.db)
    assert written == ["urn:graph:derived:backtest:selection:rule:P1:1"]
    assert result.written == {
        "urn:graph:derived:backtest:selection:rule:P1:1": result.graphs[
            "urn:graph:derived:backtest:selection:rule:P1:1"
        ]
    }
    assert result.store_consulted


def test_a_selection_graph_that_already_exists_is_not_written_again(
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
    result = _run_selection(backtest_db(tmp_path), store=store.db)
    assert result.already_in_store == ["urn:graph:derived:backtest:selection:rule:P1:1"]
    assert result.written == {}
