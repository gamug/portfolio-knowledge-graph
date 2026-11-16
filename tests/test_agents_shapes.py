"""Synthetic negative cases for the block F shapes (Work item 46, T-900-T-909)."""

from __future__ import annotations

from pathlib import Path

import pytest
import rdflib
from fixtures.agents_delivery import DATE, WINDOW, write_delivery
from rdflib.namespace import XSD

from kg_store import gate
from projection import agents

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


def _valid(tmp_path: Path) -> tuple[agents.WindowData, rdflib.Graph]:
    data = agents.load_delivery("final", write_delivery(tmp_path), [WINDOW]).by_window(WINDOW)
    graph = rdflib.Graph()
    for builder in agents.project(data, "final").values():
        graph += rdflib.Graph().parse(data=builder.turtle(), format="turtle")
    return data, graph


def _validate(data: agents.WindowData, graph: rdflib.Graph) -> None:
    gate.validate(graph, context=agents._asset_context(data, "final"))


def test_the_synthetic_batch_conforms(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    _validate(data, graph)


def test_manager_call_without_its_stop_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    call = KG[f"ManagerCall_final_{WINDOW}_0"]
    graph.remove((call, KG.callOfStop, None))
    with pytest.raises(gate.IngestRejected, match="callOfStop"):
        _validate(data, graph)


def test_narrator_text_without_provenance_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    text = KG[f"NarratorText_final_{WINDOW}_blocked_{DATE}_1"]
    graph.remove((text, KG.provenanceNote, None))
    with pytest.raises(gate.IngestRejected, match="provenanceNote"):
        _validate(data, graph)


def test_news_action_with_an_unknown_kind_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    action = KG[f"NewsAction_final_{WINDOW}_{DATE}_1_veto"]
    graph.remove((action, KG.newsActionKind, None))
    graph.add((action, KG.newsActionKind, rdflib.Literal("hold")))
    with pytest.raises(gate.IngestRejected, match="newsActionKind"):
        _validate(data, graph)


def test_news_evidence_fraction_must_be_an_integer_pair(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    evidence = KG[f"NewsEvidence_final_{WINDOW}_{DATE}_1"]
    graph.remove((evidence, KG.newsPNegativeNumerator, None))
    graph.add(
        (
            evidence,
            KG.newsPNegativeNumerator,
            rdflib.Literal("0.5", datatype=XSD.decimal),
        )
    )
    with pytest.raises(gate.IngestRejected, match="newsPNegativeNumerator"):
        _validate(data, graph)


def test_the_price_filter_is_a_boolean_flag_never_a_price(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    record = KG[f"DateRecord_final_{WINDOW}_{DATE}"]
    graph.remove((record, KG.filterPriceFlag, None))
    graph.add((record, KG.filterPriceFlag, rdflib.Literal("10.5", datatype=XSD.decimal)))
    with pytest.raises(gate.IngestRejected, match="filterPriceFlag"):
        _validate(data, graph)
    graph.remove((record, KG.filterPriceFlag, None))
    graph.add((record, KG.filterPriceFlag, rdflib.Literal(True, datatype=XSD.boolean)))
    graph.add((record, KG.closePrice, rdflib.Literal("10.5", datatype=XSD.decimal)))
    with pytest.raises(gate.IngestRejected, match="price"):
        _validate(data, graph)


def test_news_run_without_its_exit_count_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    run = KG[f"NewsRun_final_{WINDOW}"]
    graph.remove((run, KG.newsExits, None))
    with pytest.raises(gate.IngestRejected, match="newsExits"):
        _validate(data, graph)


def test_bull_decision_with_an_unknown_t1_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    decision = KG[f"BullModeDecision_final_{WINDOW}_{DATE}"]
    graph.remove((decision, KG.bullT1, None))
    graph.add((decision, KG.bullT1, rdflib.Literal("unknown")))
    with pytest.raises(gate.IngestRejected, match="bullT1"):
        _validate(data, graph)


def test_bull_record_without_a_beta_target_fails(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    record = KG[f"BullMode_final_{WINDOW}"]
    graph.remove((record, KG.bullBetaTarget, None))
    with pytest.raises(gate.IngestRejected, match="bullBetaTarget"):
        _validate(data, graph)


def test_an_agent_record_may_not_carry_a_price(tmp_path: Path) -> None:
    data, graph = _valid(tmp_path)
    call = KG[f"ManagerCall_final_{WINDOW}_0"]
    graph.add((call, KG.closePrice, rdflib.Literal("10.5", datatype=XSD.decimal)))
    with pytest.raises(gate.IngestRejected, match="price"):
        _validate(data, graph)
