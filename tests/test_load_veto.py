"""The one Veto Hierarchy loader CLI: draft dry run and production write guard (T-866)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
import rdflib
from fixtures.backtest_rows import (
    ASSETS,
    backtest_db,
    final_scenario_rows,
    load_catalog,
    universe_db,
)
from fixtures.dataset_store import DatasetStore

from kg_store import gate
from projection import load_veto
from projection.backtest import validation_context
from projection.load_veto import build_delivery, main
from projection.veto_manifest import read_manifest

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "delivery"
    folder.mkdir()
    universe = universe_db(tmp_path)
    mask = folder / "mask.csv"
    mask.write_text("ticker\nAAA\n")
    config = folder / "config_final.md"
    config.write_text(
        "---\nlabel: final\ncode_commit: abc1234\npr: 158\nresults_doc: docs/results.md\n---\n"
        "Frozen body with & and '.\n"
    )
    dbs: dict[str, Path] = {}
    for name, rows in (
        ("system_with", final_scenario_rows("P1")),
        ("system_without", final_scenario_rows("P1")),
        ("markowitz", final_scenario_rows("P1")),
    ):
        dbs[name] = backtest_db(folder, name=f"{name}.db", rows=rows)
    series = folder / "series"
    series.mkdir()
    series_files = {}
    for name in ("mv_daily.csv", "mv_weights.csv", "mv_agg.json", "spy_daily.csv"):
        path = series / name
        path.write_text("date,value\n")
        series_files[name] = path
    runs = []
    for configuration, file_name, book_code, book_id in (
        ("SYSTEM_WITH_HIERARCHY", "system_with", "TOPN_MV_GUARD_NO_NLP", 3),
        ("SYSTEM_WITHOUT_HIERARCHY", "system_without", "TOPN_MV_NOGUARD", 2),
        ("MARKOWITZ_BASE", "markowitz", "MARKOWITZ_BASE", 1),
    ):
        path = dbs[file_name]
        runs.append(
            {
                "configuration": configuration,
                "name_es": configuration,
                "name_en": configuration,
                "source_kind": "engine_db",
                "runs": [
                    {
                        "window": "P1",
                        "db_file": str(path.relative_to(folder)),
                        "db_sha256": _hash(path),
                        "run_id": 1,
                        "book_code": book_code,
                        "book_id": book_id,
                    }
                ],
            }
        )
    runs.extend(
        [
            {
                "configuration": "MARKOWITZ_MV",
                "name_es": "MV",
                "name_en": "MV",
                "source_kind": "series_csv",
                "runs": [
                    {
                        "window": "P1",
                        "daily_file": str(series_files["mv_daily.csv"].relative_to(folder)),
                        "daily_sha256": _hash(series_files["mv_daily.csv"]),
                        "weights_file": str(series_files["mv_weights.csv"].relative_to(folder)),
                        "weights_sha256": _hash(series_files["mv_weights.csv"]),
                        "aggregates_file": str(series_files["mv_agg.json"].relative_to(folder)),
                        "aggregates_sha256": _hash(series_files["mv_agg.json"]),
                    }
                ],
            },
            {
                "configuration": "SPY",
                "name_es": "SPY",
                "name_en": "SPY",
                "source_kind": "series_csv",
                "runs": [
                    {
                        "window": "P1",
                        "daily_file": str(series_files["spy_daily.csv"].relative_to(folder)),
                        "daily_sha256": _hash(series_files["spy_daily.csv"]),
                    }
                ],
            },
        ]
    )
    manifest = {
        "manifest_version": "pilot",
        "status": "BORRADOR",
        "label": "final",
        "created_at": "2026-11-13",
        "key": ["label", "configuration", "window"],
        "windows": ["P1", "H1", "P3", "H2", "P2", "H3", "C1"],
        "price_mask": {"file": "mask.csv", "sha256": _hash(mask), "rule": "none"},
        "prereg": {"SPEC.md": "a" * 64},
        "configurations": runs,
        "control_counts": "PENDIENTE",
    }
    path = folder / "manifest_final.json"
    path.write_text(json.dumps(manifest))
    return path, universe


def test_a_draft_manifest_dry_run_projects_every_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    assert main(["--manifest", str(path)]) == 0
    out = capsys.readouterr().out
    assert "dry run complete" in out
    assert "urn:graph:derived:backtest:final:P1:system_with_hierarchy" in out
    assert "urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy" in out
    assert "urn:graph:derived:backtest:final:P1:markowitz_base" in out


def test_a_draft_manifest_cannot_be_written_to_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)

    class Production:
        repository = "portfolio"
        host = "test"

    monkeypatch.setattr(load_veto.GraphDB, "from_env", classmethod(lambda cls: Production()))
    assert main(["--manifest", str(path), "--write", "--to-production"]) == 2
    assert "draft manifest cannot be written to production" in capsys.readouterr().err


def test_a_dry_run_never_opens_the_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: pytest.fail("a dry run must not contact the store")),
    )
    assert main(["--manifest", str(path)]) == 0


def test_the_manifest_label_must_match(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    with pytest.raises(ValueError, match="differs from --label"):
        build_delivery(read_manifest(path), "other", assets_db=tmp_path / "missing.db")


class _Store:
    repository = "portfolio_test"
    host = "test"


def test_a_draft_manifest_can_be_written_to_a_scratch_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(load_veto.GraphDB, "from_env", classmethod(lambda cls: _Store()))
    monkeypatch.setattr(load_veto, "plan_delivery", lambda store, result, minimum_free_pct=8.0: [])
    monkeypatch.setattr(load_veto, "write_delivery", lambda store, plans: ((), None))
    monkeypatch.setattr(load_veto, "verify_delivery", lambda store, result, manifest: None)
    assert main(["--manifest", str(path), "--write"]) == 0


def test_check_store_does_not_require_the_production_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: type("P", (), {"repository": "portfolio", "host": "test"})()),
    )
    monkeypatch.setattr(load_veto, "plan_delivery", lambda store, result, minimum_free_pct=8.0: [])
    assert main(["--manifest", str(path), "--check-store"]) == 0


def test_write_to_production_without_the_flag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: type("P", (), {"repository": "portfolio", "host": "test"})()),
    )
    assert main(["--manifest", str(path), "--write"]) == 2
    assert "needs --to-production" in capsys.readouterr().err


def _plan_store() -> DatasetStore:
    """A store holding the TBox, assets and rules the projection references."""
    dataset = rdflib.Dataset(default_union=True)
    dataset.graph(rdflib.URIRef("urn:graph:tbox")).parse(
        load_veto.config.schema_dir() / "tbox.ttl", format="turtle"
    )
    dataset.graph(rdflib.URIRef("urn:graph:rules:catalog")).parse(
        load_veto.config.schema_dir() / "rules.ttl", format="turtle"
    )
    context = dataset.graph(rdflib.URIRef("urn:graph:test:context"))
    for triple in validation_context(ASSETS, load_catalog()):
        context.add(triple)
    return DatasetStore(dataset)


def _delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> load_veto.LoadResult:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    return build_delivery(read_manifest(path), "final", assets_db=universe)


def _batch_graph(
    result: load_veto.LoadResult, configuration: str, kind: str
) -> load_veto.VetoGraph:
    batch = next(batch for batch in result.batches if batch.key[1] == configuration)
    return next(graph for graph in batch.graphs if graph.kind == kind)


def test_preflight_plans_all_graphs_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _delivery(tmp_path, monkeypatch)
    dataset_store = _plan_store()
    plans = load_veto.plan_delivery(cast(load_veto.GraphDB, dataset_store), result)
    assert dataset_store.writes == []
    assert {plan.graph for plan in plans} == {
        graph.graph for graph in load_veto._all_graphs(result)
    }
    assert len(plans) == 6
    assert "would-be-written" in capsys.readouterr().out


def _cross_reference_batch(  # noqa: PLR0915 -- one small graph of every required shape
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: load_veto.LoadResult | None = None
) -> tuple[rdflib.Graph, rdflib.Graph, str]:
    """An m018 batch that points at one cycle and one snapshot declared only in selection."""
    result = result or _delivery(tmp_path, monkeypatch)
    m018_graph = _batch_graph(result, "SYSTEM_WITH_HIERARCHY", "m018")
    batch = rdflib.Graph().parse(data=m018_graph.data, format="turtle")
    selection = rdflib.Graph()
    book = next(batch.subjects(rdflib.RDF.type, KG.StrategyBook))
    rebalance = next(batch.subjects(rdflib.RDF.type, KG.BookRebalance))
    asset = next(batch.objects(None, KG.holdingAsset))
    cycle = KG.CycleBoundaryTest
    snapshot = KG.SnapshotBoundaryTest
    day = rdflib.Literal("2022-01-05", datatype=rdflib.XSD.date)
    now = rdflib.Literal("2022-01-04", datatype=rdflib.XSD.date)
    stamp = rdflib.Literal("2022-01-04T00:00:00+00:00", datatype=rdflib.XSD.dateTime)

    selection.add((cycle, rdflib.RDF.type, KG.SelectionCycle))
    selection.add((cycle, KG.cycleRunId, rdflib.Literal(1)))
    selection.add((cycle, KG.cycleType, rdflib.Literal("SELECTION")))
    selection.add((cycle, KG.runAsOf, now))
    selection.add((cycle, KG.runId, rdflib.Literal("cycle_run:1")))
    selection.add((cycle, KG.status, rdflib.Literal("completed")))
    selection.add((cycle, KG.runLabel, rdflib.Literal("final")))
    selection.add((cycle, KG.windowId, rdflib.Literal("P1")))
    selection.add((cycle, KG.backtestRunId, rdflib.Literal(1)))
    selection.add((snapshot, rdflib.RDF.type, KG.AttractivenessSnapshot))
    selection.add((snapshot, KG.attractivenessOfAsset, asset))
    selection.add(
        (snapshot, KG.attractivenessScore, rdflib.Literal("0.5", datatype=rdflib.XSD.decimal))
    )
    selection.add((snapshot, KG.computedAt, stamp))
    selection.add((snapshot, KG.computedWithScheme, KG.SchemeBoundaryTest))
    selection.add((snapshot, KG.rankingOfCycle, cycle))
    selection.add((snapshot, KG.rankPosition, rdflib.Literal(1)))
    selection.add((snapshot, KG.selectedForBook, rdflib.Literal(True)))
    selection.add((snapshot, KG.vetoedAtRanking, rdflib.Literal(False)))
    selection.add((snapshot, KG.rankingTicker, rdflib.Literal("AAA")))

    decision = KG.DecisionBoundaryTest
    batch.add((decision, rdflib.RDF.type, KG.DecisionEvent))
    batch.add((decision, KG.decisionOfBook, book))
    batch.add((decision, KG.decisionDate, day))
    batch.add((decision, KG.filterState, rdflib.Literal(True)))
    batch.add((decision, KG.filterDecisionDate, day))
    batch.add((decision, KG.coreWeightInForce, rdflib.Literal("0.5", datatype=rdflib.XSD.decimal)))
    batch.add((decision, KG.exposureScale, rdflib.Literal("1.0", datatype=rdflib.XSD.decimal)))
    batch.add((decision, KG.candidatePoolSize, rdflib.Literal(60)))
    batch.add((decision, KG.candidateSetSize, rdflib.Literal(60)))
    batch.add((decision, KG.blockedCount, rdflib.Literal(0)))
    batch.add((decision, KG.retainedCountOnDecision, rdflib.Literal(1)))
    batch.add((decision, KG.selectionCycle, cycle))
    batch.add((decision, KG.bookRebalance, rebalance))
    batch.add((decision, KG.knowledgeDate, now))

    retention = KG.RetentionBoundaryTest
    batch.add((retention, rdflib.RDF.type, KG.RetentionDecision))
    batch.add((retention, KG.retentionOfBook, book))
    batch.add((retention, KG.retentionDate, day))
    batch.add((retention, KG.poolSize, rdflib.Literal(60)))
    batch.add((retention, KG.heldOutsidePoolCount, rdflib.Literal(0)))
    batch.add((retention, KG.retainedCount, rdflib.Literal(1)))
    batch.add((retention, KG.rejectedCount, rdflib.Literal(0)))
    batch.add((retention, KG.counterDroppedCount, rdflib.Literal(0)))
    batch.add((retention, KG.keptCount, rdflib.Literal(1)))
    batch.add((retention, KG.keptWeight, rdflib.Literal("0.1", datatype=rdflib.XSD.decimal)))
    batch.add((retention, KG.maxDecisions, rdflib.Literal(3)))
    batch.add((retention, KG.candidateSetSize, rdflib.Literal(60)))
    batch.add((retention, KG.retentionEnabled, rdflib.Literal(True)))
    batch.add((retention, KG.knowledgeDate, now))

    hold = KG.RetentionHoldBoundaryTest
    batch.add((hold, rdflib.RDF.type, KG.RetentionHold))
    batch.add((hold, KG.holdOfDecision, retention))
    batch.add((hold, KG.retainedAsset, asset))
    batch.add((hold, KG.retentionCounter, rdflib.Literal(1)))
    batch.add((hold, KG.rankingSnapshot, snapshot))
    return batch, selection, m018_graph.graph


def _delivery_with_cross_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> load_veto.LoadResult:
    result = _delivery(tmp_path, monkeypatch)
    batch, selection, m018_name = _cross_reference_batch(tmp_path, monkeypatch, result)
    original = next(item for item in result.batches if item.key[1] == "SYSTEM_WITH_HIERARCHY")
    selection_name = original.graphs[1].graph
    m018 = load_veto.VetoGraph(
        m018_name,
        batch.serialize(format="turtle").encode(),
        len(batch),
        "m018",
        original.key[1],
        original.key[2],
    )
    selection_graph = load_veto.VetoGraph(
        selection_name,
        selection.serialize(format="turtle").encode(),
        len(selection),
        "selection",
        original.key[1],
        original.key[2],
    )
    replaced = load_veto.VetoBatch(
        original.key,
        [m018, selection_graph],
        batch,
        selection,
        original.detail,
    )
    batches = tuple(replaced if item.key == original.key else item for item in result.batches)
    return load_veto.LoadResult(batches, result.meta)


def test_preflight_uses_the_sibling_for_a_cross_graph_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch, selection, graph = _cross_reference_batch(tmp_path, monkeypatch)
    store = cast(load_veto.GraphDB, _plan_store())
    data = batch.serialize(format="turtle").encode()
    with pytest.raises(gate.ShaclRejected):
        gate.plan(store, data, graph)
    plan = gate.plan(store, data, graph, context=selection)
    assert plan.status is gate.IngestPlanStatus.WOULD_WRITE


def test_preflight_passes_the_sibling_selection_to_plan_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _delivery_with_cross_reference(tmp_path, monkeypatch)
    dataset_store = _plan_store()
    plans = load_veto.plan_delivery(cast(load_veto.GraphDB, dataset_store), result)
    assert len(plans) == 6
    assert dataset_store.writes == []
    assert {plan.graph for plan in plans} == {
        graph.graph for graph in load_veto._all_graphs(result)
    }


def test_preflight_refuses_a_reference_in_neither_sibling_nor_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch, selection, graph = _cross_reference_batch(tmp_path, monkeypatch)
    store = cast(load_veto.GraphDB, _plan_store())
    batch.remove((KG.DecisionBoundaryTest, KG.selectionCycle, None))
    batch.add((KG.DecisionBoundaryTest, KG.selectionCycle, KG.MissingCycle))
    with pytest.raises(gate.ShaclRejected, match="SelectionCycle"):
        gate.plan(
            store,
            batch.serialize(format="turtle").encode(),
            graph,
            context=selection,
        )


def test_preflight_writes_exactly_the_planned_batch_not_its_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _delivery(tmp_path, monkeypatch)
    dataset_store = _plan_store()
    store = cast(load_veto.GraphDB, dataset_store)
    plans = load_veto.plan_delivery(store, result)
    m018 = _batch_graph(result, "SYSTEM_WITH_HIERARCHY", "m018")
    plan = next(item for item in plans if item.graph == m018.graph)
    gate.write(store, plan)
    written = dataset_store.dataset.graph(rdflib.URIRef(m018.graph))
    assert set(written) == set(plan.batch)
    assert len(written) == plan.triples
