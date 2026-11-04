"""``projection.reference``: ticker history and the orchestrator views (T-352/T-353)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.reference_rows import ASSETS, reference_db, rows_without, scenario_rows
from rdflib.namespace import RDF, XSD
from rdflib.term import URIRef

from kg_store import gate
from projection.backtest import ProjectionError
from projection.reference import (
    KG,
    ORDER,
    VIEWS,
    orchestrator_graph_name,
    project,
    project_source,
    read_view,
    run,
    ticker_graph_name,
    validation_context,
)
from projection.source import FinancialSource

SNAPSHOT = "2026-11-04"
LABEL = "fixture"
TICKER_GRAPH = "urn:graph:derived:ticker-history:fixture:2026-11-04"


def _rows(path: Path) -> dict[str, list[Mapping[str, Any]]]:
    source = FinancialSource.open(path)
    try:
        return {view: list(read_view(source, view)) for view in VIEWS}
    finally:
        source.close()


def _projection(path: Path, label: str = LABEL) -> Any:
    return project(_rows(path), ASSETS, label, SNAPSHOT)


def _graph(projection: Any, name: str) -> rdflib.Graph:
    graph = rdflib.Graph()
    for triple in projection.graphs[name].triples:
        graph.add(triple)
    return graph


def _ticker(graph: rdflib.Graph, cik: str, symbol: str, valid_from: str) -> URIRef:
    for subject in graph.subjects(RDF.type, KG.TickerHistory):
        if (
            str(graph.value(subject, KG.tickerHistoryCik)) == cik
            and str(graph.value(subject, KG.historicalSymbol)) == symbol
            and str(graph.value(subject, KG.validFrom)) == valid_from
        ):
            assert isinstance(subject, URIRef)
            return subject
    raise AssertionError(f"no TickerHistory {cik}/{symbol}/{valid_from}")


def test_the_three_views_are_read_in_natural_key_order(tmp_path: Path) -> None:
    assert VIEWS == ("v_ticker_history", "v_orchestrator_run", "v_orchestrator_step")
    assert ORDER["v_ticker_history"] == ("cik", "symbol", "valid_from")
    rows = _rows(reference_db(tmp_path))
    assert len(rows["v_ticker_history"]) == 9
    assert [(row["cik"], row["symbol"]) for row in rows["v_ticker_history"]] == sorted(
        (row["cik"], row["symbol"]) for row in rows["v_ticker_history"]
    )


def test_the_snapshot_graph_and_every_iri_carry_the_label_and_date(tmp_path: Path) -> None:
    assert ticker_graph_name(LABEL, SNAPSHOT) == TICKER_GRAPH
    projection = _projection(reference_db(tmp_path))
    assert TICKER_GRAPH in projection.graphs
    graph = _graph(projection, TICKER_GRAPH)
    for subject in graph.subjects(RDF.type, KG.TickerHistory):
        assert str(subject).startswith(
            "https://thesis.local/kg/portfolio#TickerHistory_fixture_20261104_"
        )


def test_ticker_history_keeps_the_inclusive_interval(tmp_path: Path) -> None:
    graph = _graph(_projection(reference_db(tmp_path)), TICKER_GRAPH)
    fb = _ticker(graph, "0001326801", "FB", "2013-12-23")
    assert graph.value(fb, KG.validFrom) == rdflib.Literal("2013-12-23", datatype=XSD.date)
    assert graph.value(fb, KG.validTo) == rdflib.Literal("2022-06-08", datatype=XSD.date)
    meta = _ticker(graph, "0001326801", "META", "2022-06-09")
    assert graph.value(meta, KG.validTo) is None
    assert graph.value(meta, KG.canonicalSymbol) == rdflib.Literal("META")


def test_exact_canonical_symbols_link_and_the_rest_use_the_unique_cik(
    tmp_path: Path,
) -> None:
    projection = _projection(reference_db(tmp_path))
    graph = _graph(projection, TICKER_GRAPH)

    fb = _ticker(graph, "0001326801", "FB", "2013-12-23")
    assert graph.value(fb, KG.tickerHistoryAsset) == KG.META

    fbhs = _ticker(graph, "0001519751", "FBHS", "2016-06-22")
    assert graph.value(fbhs, KG.tickerHistoryAsset) == KG.FBHS
    fbin = _ticker(graph, "0001519751", "FBIN", "2022-12-15")
    assert graph.value(fbin, KG.tickerHistoryAsset) == KG.FBHS

    gps = _ticker(graph, "0000039911", "GPS", "1976-07-01")
    gap = _ticker(graph, "0000039911", "GAP", "2024-08-22")
    assert graph.value(gps, KG.tickerHistoryAsset) == KG.GPS
    assert graph.value(gap, KG.tickerHistoryAsset) == KG.GPS

    zzz = _ticker(graph, "0000000009", "ZZZ", "2020-01-01")
    assert graph.value(zzz, KG.tickerHistoryAsset) is None
    assert projection.asset_exact["v_ticker_history"] == 4
    assert projection.asset_cik["v_ticker_history"] == 4
    assert projection.asset_unlinked["v_ticker_history"] == 1


def test_a_multi_date_evidence_cell_is_omitted_and_counted(tmp_path: Path) -> None:
    projection = _projection(reference_db(tmp_path))
    graph = _graph(projection, TICKER_GRAPH)
    disca = _ticker(graph, "0001437107", "DISCA", "1976-07-01")
    assert graph.value(disca, KG.evidenceDate) is None
    assert graph.value(disca, KG.evidenceUrl) == rdflib.Literal(
        "https://example.test/a ; https://example.test/b", datatype=XSD.anyURI
    )
    assert projection.skipped["v_ticker_history.evidence_date: more than one date"] == 1
    wbd = _ticker(graph, "0001437107", "WBD", "2022-04-11")
    assert graph.value(wbd, KG.evidenceDate) == rdflib.Literal("2022-04-10", datatype=XSD.date)


def test_a_canonical_symbol_that_is_not_the_latest_symbol_stops_the_run() -> None:
    rows = scenario_rows()
    for row in rows["v_ticker_history"]:
        if row["cik"] == "0001326801":
            row["canonical_symbol"] = "FB"
    with pytest.raises(ProjectionError, match="is not the latest symbol"):
        project(rows, ASSETS, LABEL, SNAPSHOT)


def test_a_mixed_cik_keeps_an_older_rows_own_canonical_symbol() -> None:
    # DISCK is a concurrent class: its row says DISCK even though the same CIK later says WBD.
    # Only the latest row must agree with the latest symbol.
    rows = scenario_rows()
    rows["v_ticker_history"].append(
        {
            "cik": "0001437107",
            "symbol": "DISCK",
            "valid_from": "2014-08-06",
            "valid_to": "2022-04-10",
            "canonical_symbol": "DISCK",
            "evidence_url": "https://example.test/disck",
            "evidence_date": "2022-04-10",
            "rules": "L-11;APP-10a",
        }
    )
    projection = project(rows, ASSETS, LABEL, SNAPSHOT)
    assert projection.individuals["TickerHistory"] == 10


def test_one_graph_per_orchestrator_run_and_natural_keys_only(tmp_path: Path) -> None:
    projection = _projection(reference_db(tmp_path))
    assert set(projection.graphs) == {
        TICKER_GRAPH,
        "urn:graph:derived:orchestrator:fixture:1",
        "urn:graph:derived:orchestrator:fixture:2",
    }
    assert orchestrator_graph_name("fixture", 1) == ("urn:graph:derived:orchestrator:fixture:1")
    first = _graph(projection, "urn:graph:derived:orchestrator:fixture:1")
    run_one = KG.OrchestratorRun_fixture_1
    step_one = KG.OrchestratorStep_fixture_1_1
    step_two = KG.OrchestratorStep_fixture_1_2
    assert first.value(run_one, KG.orchestratorRunId) == rdflib.Literal("1", datatype=XSD.integer)
    assert first.value(run_one, KG.runKind) == rdflib.Literal("pipeline")
    assert first.value(run_one, KG.runAsOf) == rdflib.Literal("2026-11-03", datatype=XSD.date)
    assert first.value(run_one, KG.startedAt) == rdflib.Literal(
        "2026-11-03T10:00:00+00:00", datatype=XSD.dateTime
    )
    assert first.value(step_one, KG.stepOfOrchestratorRun) == run_one
    assert first.value(step_one, KG.ordinal) == rdflib.Literal("1", datatype=XSD.integer)
    assert first.value(step_one, KG.runId) == rdflib.Literal("analysis:7")
    assert first.value(step_two, KG.runId) == rdflib.Literal("cycle:8")
    assert first.value(step_two, KG.reason) == rdflib.Literal("boom")
    assert first.value(step_two, KG.outputTail) is None

    second = _graph(projection, "urn:graph:derived:orchestrator:fixture:2")
    run_two = KG.OrchestratorRun_fixture_2
    assert set(second.predicate_objects(run_two)) == {
        (RDF.type, KG.OrchestratorRun),
        (KG.orchestratorRunId, rdflib.Literal("2", datatype=XSD.integer)),
    }
    step_three = KG.OrchestratorStep_fixture_2_1
    assert second.value(step_three, KG.stepOfOrchestratorRun) == run_two
    assert second.value(step_three, KG.ordinal) == rdflib.Literal("1", datatype=XSD.integer)


def test_empty_orchestrator_views_build_no_graph_and_say_so(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["v_orchestrator_run"] = []
    rows["v_orchestrator_step"] = []
    projection = project(rows, ASSETS, LABEL, SNAPSHOT)
    assert set(projection.graphs) == {TICKER_GRAPH}
    source = FinancialSource.open(reference_db(tmp_path, rows=rows))
    try:
        result = run(source, ASSETS, LABEL, SNAPSHOT)
    finally:
        source.close()
    assert "orchestrator: v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows" in (
        result.summary()
    )
    assert "nothing to write" in result.summary()
    assert result.checked == [TICKER_GRAPH]


def test_empty_ticker_history_builds_no_snapshot(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["v_ticker_history"] = []
    projection = project(rows, ASSETS, LABEL, SNAPSHOT)
    assert TICKER_GRAPH not in projection.graphs
    source = FinancialSource.open(reference_db(tmp_path, rows=rows))
    try:
        result = run(source, ASSETS, LABEL, SNAPSHOT)
    finally:
        source.close()
    assert "ticker history: 0 rows: nothing to write" in result.summary()


def test_a_step_without_its_run_stops_the_run() -> None:
    rows = scenario_rows()
    rows = rows_without(rows, "v_orchestrator_run", 1)  # remove run 2
    with pytest.raises(ProjectionError, match="no v_orchestrator_run row for run 2"):
        project(rows, ASSETS, LABEL, SNAPSHOT)


def test_a_dry_run_shacl_validates_every_graph(tmp_path: Path) -> None:
    source = FinancialSource.open(reference_db(tmp_path))
    try:
        result = run(source, ASSETS, LABEL, SNAPSHOT)
    finally:
        source.close()
    assert result.report.stopped is False
    assert result.checked == sorted(result.graphs)
    assert result.rejected == {}
    assert result.store_consulted is False
    assert result.individuals["TickerHistory"] == 9
    assert result.individuals["OrchestratorRun"] == 2
    assert result.individuals["OrchestratorStep"] == 3


def test_the_dry_run_context_types_every_linked_asset() -> None:
    context = validation_context(ASSETS)
    assert set(context.subjects(RDF.type, KG.Asset)) == {
        KG.META,
        KG.FBHS,
        KG.GPS,
        KG.WBD,
    }


def test_a_write_hands_each_graph_to_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: Any
) -> None:
    store = make_db()
    written: list[str] = []

    def ingest(_store: Any, data: bytes, graph: str) -> int:
        written.append(graph)
        return len(gate.parse_batch(data))

    monkeypatch.setattr("projection.reference.gate.ingest", ingest)
    source = FinancialSource.open(reference_db(tmp_path))
    try:
        result = run(source, ASSETS, LABEL, SNAPSHOT, store=store.db)
    finally:
        source.close()
    assert written == sorted(result.graphs)
    assert result.written == {graph: result.graphs[graph] for graph in sorted(result.graphs)}
    assert result.store_consulted


def test_a_graph_that_already_exists_is_not_written_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: Any
) -> None:
    store = make_db(rows=[{"s": "x", "p": "x", "o": "x"}])
    monkeypatch.setattr(
        "projection.reference.gate.ingest",
        lambda *_args, **_kwargs: pytest.fail("a graph that exists must not be written"),
    )
    source = FinancialSource.open(reference_db(tmp_path))
    try:
        result = run(source, ASSETS, LABEL, SNAPSHOT, store=store.db)
    finally:
        source.close()
    assert result.already_in_store == sorted(result.graphs)
    assert result.written == {}


def test_project_source_passes_the_boundary_rows_to_the_projector(tmp_path: Path) -> None:
    source = FinancialSource.open(reference_db(tmp_path))
    try:
        result = project_source(source, ASSETS, LABEL, SNAPSHOT)
    finally:
        source.close()
    assert result.report.stopped is False
    assert set(result.rows) == set(VIEWS)
    assert result.projection.individuals["TickerHistory"] == 9


def test_a_row_with_a_bad_date_is_quarantined(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["v_ticker_history"][0]["valid_from"] = "2022-06-08T00:00:00"
    source = FinancialSource.open(reference_db(tmp_path, rows=rows))
    try:
        with pytest.raises(ProjectionError, match="valid_from"):
            project_source(source, ASSETS, LABEL, SNAPSHOT)
    finally:
        source.close()
