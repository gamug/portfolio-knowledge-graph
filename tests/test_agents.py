"""Block F agent traceability: manifest, parsing, projection and store checks (Work item 46)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
import rdflib
from fixtures.agents_delivery import DATE, WINDOW, refresh_hashes, write_delivery
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, XSD

from kg_store.graphdb import GraphDB
from projection import agents
from projection.agents import (
    AgentsError,
    AgentsManifestError,
    graph_name,
    load_delivery,
    project,
    verify_stored,
)
from projection.control_counts import store_agent_counts, verify_agent_control_counts
from projection.veto_manifest import read_manifest

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


def _loaded(tmp_path: Path) -> agents.Delivery:
    root = write_delivery(tmp_path)
    return load_delivery("final", root, [WINDOW])


def test_manifest_hashes_and_counts_are_checked(tmp_path: Path) -> None:
    delivery = _loaded(tmp_path)
    data = delivery.by_window(WINDOW)
    assert data.counts.manager_calls == 1
    assert data.counts.narrator_texts == 2
    assert data.counts.news_pool_actions == {"veto": 1, "promotion": 0}
    assert data.counts.news_level_c_decisions == 0
    assert data.counts.news_level_d_decisions == 1
    assert data.counts.news_exits == 1
    assert data.counts.news_sector_rejections == 4
    assert data.counts.bull_triggered == 1


def test_a_changed_file_is_a_hash_mismatch(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "SYSTEM_WITH_HIERARCHY" / WINDOW / "H1B-A2g-P1.news.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(AgentsManifestError, match="SHA-256 mismatch"):
        load_delivery("final", root, [WINDOW])


def test_a_control_count_mismatch_is_refused(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    manifest = root / "manifest_final.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["control_counts"]["SYSTEM_WITH_HIERARCHY"][WINDOW]["news_exits"] = 99
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    sums = root / "SHA256SUMS"
    lines = [
        line
        for line in sums.read_text(encoding="utf-8").splitlines()
        if not line.endswith("manifest_final.json")
    ]
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AgentsManifestError, match="control_counts"):
        load_delivery("final", root, [WINDOW])


def test_a_duplicate_narrator_key_is_refused(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "SYSTEM_WITH_HIERARCHY" / WINDOW / "H1B-A2g-P1.narrator.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows.append(rows[0])
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    refresh_hashes(root)
    with pytest.raises(AgentsError, match="duplicate"):
        load_delivery("final", root, [WINDOW])


def test_a_fill_must_match_the_veto_action(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "SYSTEM_WITH_HIERARCHY" / WINDOW / "H1B-A2g-P1.news.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fills"][0]["asset_id"] = 999
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    refresh_hashes(root)
    with pytest.raises(AgentsError, match="fill"):
        load_delivery("final", root, [WINDOW])


def test_news_and_bull_dates_must_agree(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "SYSTEM_WITH_HIERARCHY" / WINDOW / "H1B-A2g-P1.bull_mode.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decisions"][0]["date"] = "2022-01-04"
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    refresh_hashes(root)
    with pytest.raises(AgentsError, match="dates"):
        load_delivery("final", root, [WINDOW])


def test_the_four_graphs_carry_the_typed_core(tmp_path: Path) -> None:
    data = _loaded(tmp_path).by_window(WINDOW)
    builders = project(data, "final")
    assert set(builders) == set(agents.SLUGS)
    manager = builders["manager_calls"]
    narrator = builders["narrator"]
    news = builders["news"]
    bull = builders["bull_mode"]
    assert len(manager) > 20
    assert len(narrator) > 20
    assert len(news) > 20
    assert len(bull) > 20

    manager_graph = rdflib.Graph().parse(data=manager.turtle(), format="turtle")
    call = KG[f"ManagerCall_final_{WINDOW}_0"]
    assert (call, RDF.type, KG.ManagerCall) in manager_graph
    assert (
        call,
        KG.callOfStop,
        KG[f"Stop_final_{WINDOW}_system_with_hierarchy_{DATE}_1"],
    ) in manager_graph
    assert (
        call,
        KG.generatedByLanguageModel,
        rdflib.Literal(True, datatype=XSD.boolean),
    ) in manager_graph
    # The prompt and answer text never enter the graph; only their hashes do.
    text = manager.turtle().decode()
    assert "SECRET SYSTEM PROMPT" not in text
    assert "SECRET RAW ANSWER" not in text
    assert "sourceLineNumber" in text

    narrator_graph = rdflib.Graph().parse(data=narrator.turtle(), format="turtle")
    model_text = KG[f"NarratorText_final_{WINDOW}_stop_{DATE}_1"]
    template_text = KG[f"NarratorText_final_{WINDOW}_blocked_{DATE}_1"]
    assert (
        model_text,
        KG.provenanceNote,
        rdflib.Literal(agents.MODEL_PROVENANCE),
    ) in narrator_graph
    assert (
        template_text,
        KG.provenanceNote,
        rdflib.Literal(agents.TEMPLATE_PROVENANCE),
    ) in narrator_graph
    assert (
        template_text,
        KG.generatedByLanguageModel,
        rdflib.Literal(False, datatype=XSD.boolean),
    ) in narrator_graph

    news_graph = rdflib.Graph().parse(data=news.turtle(), format="turtle")
    action = KG[f"NewsAction_final_{WINDOW}_{DATE}_1_veto"]
    evidence = KG[f"NewsEvidence_final_{WINDOW}_{DATE}_1"]
    assert (action, RDF.type, KG.NewsAction) in news_graph
    assert (evidence, RDF.type, KG.NewsEvidence) in news_graph
    assert (
        evidence,
        KG.newsPNegativeNumerator,
        rdflib.Literal(1, datatype=XSD.integer),
    ) in news_graph
    assert (
        evidence,
        KG.newsPNegativeDenominator,
        rdflib.Literal(2, datatype=XSD.integer),
    ) in news_graph
    assert (action, KG.newsActionFilled, rdflib.Literal(True, datatype=XSD.boolean)) in news_graph
    assert (evidence, KG.newsItem, KG.NewsItem_body_10_AAA) in news_graph
    assert "10:AAA" in news.turtle().decode()

    bull_graph = rdflib.Graph().parse(data=bull.turtle(), format="turtle")
    decision = KG[f"BullModeDecision_final_{WINDOW}_{DATE}"]
    assert (decision, RDF.type, KG.BullModeDecision) in bull_graph
    assert (decision, KG.bullTriggered, rdflib.Literal(True, datatype=XSD.boolean)) in bull_graph


def test_the_gate_accepts_the_agents_graph_name() -> None:
    assert agents.gate.check_target(graph_name("final", "C1", "news")) is True
    with pytest.raises(agents.gate.IngestRejected):
        agents.gate.check_target("urn:graph:derived:backtest:agents:final:C1:other")


def test_graph_names_are_window_and_slug_qualified() -> None:
    assert graph_name("final", "C1", "news") == "urn:graph:derived:backtest:agents:final:C1:news"
    with pytest.raises(AgentsError):
        graph_name("Final", "C1", "news")
    with pytest.raises(AgentsError):
        graph_name("final", "C1", "other")


def test_the_gate_plans_the_four_graphs_against_a_store(tmp_path: Path) -> None:
    data = load_delivery("final", write_delivery(tmp_path), [WINDOW]).by_window(WINDOW)
    builders = project(data, "final")
    dataset = rdflib.Dataset()
    context_graph = dataset.graph(rdflib.URIRef("urn:graph:test:context"))
    for triple in agents._asset_context(data, "final"):
        context_graph.add(triple)
    store = DatasetStore(dataset)
    for slug, builder in builders.items():
        plan = agents.gate.plan(
            cast(GraphDB, store),
            builder.turtle(),
            graph_name("final", WINDOW, slug),
            context=agents._asset_context(data, "final"),
        )
        assert plan.status is agents.gate.IngestPlanStatus.WOULD_WRITE
        assert plan.triples == len(builder)


def test_store_counts_match_and_an_absent_graph_is_not_failing(tmp_path: Path) -> None:
    delivery = load_delivery("final", write_delivery(tmp_path), [WINDOW])
    data = delivery.by_window(WINDOW)
    builders = project(data, "final")
    dataset = rdflib.Dataset()
    for slug, builder in builders.items():
        graph = dataset.graph(rdflib.URIRef(graph_name("final", WINDOW, slug)))
        for triple in rdflib.Graph().parse(data=builder.turtle(), format="turtle"):
            graph.add(triple)
    store = DatasetStore(dataset)
    checks = verify_stored(store, "final", data)
    assert all(check.passed for check in checks), [check.detail for check in checks]
    dataset.remove_graph(rdflib.URIRef(graph_name("final", WINDOW, "narrator")))
    checks = verify_stored(store, "final", data)
    absent = [check for check in checks if "narrator" in check.name]
    assert absent and absent[0].passed and "not store-verifiable" in absent[0].detail


def test_a_wrong_stored_count_fails(tmp_path: Path) -> None:
    delivery = load_delivery("final", write_delivery(tmp_path), [WINDOW])
    data = delivery.by_window(WINDOW)
    builders = project(data, "final")
    dataset = rdflib.Dataset()
    for slug, builder in builders.items():
        graph = dataset.graph(rdflib.URIRef(graph_name("final", WINDOW, slug)))
        for triple in rdflib.Graph().parse(data=builder.turtle(), format="turtle"):
            graph.add(triple)
    store = DatasetStore(dataset)
    graph = dataset.graph(rdflib.URIRef(graph_name("final", WINDOW, "manager_calls")))
    subject = KG[f"ManagerCall_final_{WINDOW}_0"]
    graph.add((subject, KG.fallbackUsedRule, rdflib.Literal(True, datatype=XSD.boolean)))
    checks = verify_stored(store, "final", data, only=["manager_calls"])
    assert not checks[0].passed
    assert "manager_fallbacks" in checks[0].detail


def test_agent_control_counts_are_store_verifiable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    delivery = load_delivery("final", write_delivery(tmp_path), [WINDOW])
    data = delivery.by_window(WINDOW)
    builds = project(data, "final")
    dataset = rdflib.Dataset()
    for slug, builder in builds.items():
        graph = dataset.graph(rdflib.URIRef(graph_name("final", WINDOW, slug)))
        for triple in rdflib.Graph().parse(data=builder.turtle(), format="turtle"):
            graph.add(triple)
    store = DatasetStore(dataset)
    counts = store_agent_counts(store, "final", WINDOW)
    assert counts["manager_calls"] == 1
    assert counts["narrator_texts"] == 2
    assert counts["news_pool_actions"] == {"veto": 1, "promotion": 0}
    assert counts["news_exits"] == 1
    assert counts["news_sector_rejections"] == 4
    assert counts["bull_triggered"] == 1
    expected = {
        "SYSTEM_WITH_HIERARCHY": {
            WINDOW: {
                "manager_calls": 1,
                "manager_fallbacks": 0,
                "manager_repairs": 0,
                "narrator_texts": 2,
                "news_pool_actions": {"veto": 1, "promotion": 0},
                "news_date_records": 1,
                "news_level_c_decisions": 0,
                "news_level_d_decisions": 1,
                "news_exits": 1,
                "news_sector_rejections": 4,
                "bull_triggered": 1,
            }
        }
    }
    assert verify_agent_control_counts(store, "final", WINDOW, expected) == []
    dataset.remove_graph(rdflib.URIRef(graph_name("final", WINDOW, "narrator")))
    assert verify_agent_control_counts(store, "final", WINDOW, expected) == []
    assert "not store-verifiable" in capsys.readouterr().out
    graph = dataset.graph(rdflib.URIRef(graph_name("final", WINDOW, "manager_calls")))
    subject = KG[f"ManagerCall_final_{WINDOW}_0"]
    graph.add((subject, KG.fallbackUsedRule, rdflib.Literal(True, datatype=XSD.boolean)))
    failures = verify_agent_control_counts(store, "final", WINDOW, expected)
    assert failures and "manager_fallbacks" in failures[0]


@pytest.mark.integration
def test_master_manifest_and_loader_resolve_the_same_files() -> None:
    """The final delivery is read by B's parser and by this loader; both name the same paths."""
    root = Path("/workspaces/thesis/knoledge graph/2026-11-17_final")
    manifest_path = root / "manifest_final.json"
    if not manifest_path.is_file():
        pytest.skip("the final delivery is absent")
    parsed = read_manifest(manifest_path)
    by_key = {(run.configuration, run.window): run for run in parsed.runs}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    for window in agents.WINDOWS:
        entry = agents._manifest_run(raw, window)
        run = by_key[("SYSTEM_WITH_HIERARCHY", window)]
        for key in ("manager_calls_file", "narrator_file", "news_actions_file", "bull_mode_file"):
            assert run.files[key] == root / str(entry[key])


def test_a_test_row_without_a_news_row_fails_clearly(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "news" / "news_rows.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["item_id"] = "999"
    path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")
    refresh_hashes(root)
    with pytest.raises(AgentsError, match=r"test rows without a news_rows\.jsonl row"):
        load_delivery("final", root, [WINDOW])


def test_one_test_row_with_two_item_kinds_fails_clearly(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "news" / "news_rows.jsonl"
    first = json.loads(path.read_text(encoding="utf-8"))
    second = dict(first)
    second["item_kind"] = "sub_news"
    path.write_text(
        json.dumps(first, separators=(",", ":"))
        + "\n"
        + json.dumps(second, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifest_final.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["news_rows_file"]["rows"] = 2
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    refresh_hashes(root)
    with pytest.raises(AgentsError, match="maps to both"):
        load_delivery("final", root, [WINDOW])
