"""The aggregates-file parser, manifest, projector, gate and verifier (Work item 37)."""

from __future__ import annotations

import copy
import datetime
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.aggregates_rows import (
    aggregates_document,
    p2_rows,
    reference_pair,
    write_aggregates,
)
from fixtures.backtest_rows import backtest_db, scenario_rows
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, SH

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.aggregates import (
    AggregatesError,
    AggregatesFile,
    ManifestError,
    ReferenceReturnRow,
    TrendFilterRow,
    Verification,
    aggregates_set_iri,
    batch,
    parse_aggregates,
    project,
    read_manifest,
    reference_return_iri,
    trend_filter_iri,
    verify_manifest,
    verify_sources,
    verify_stored,
    with_manifest,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
SCHEMA = Path(__file__).resolve().parent.parent / "schema"
GRAPH = "urn:graph:derived:backtest:aggregates:rule"


def _folder(
    tmp_path: Path, document: dict[str, object] | None = None
) -> tuple[Path, AggregatesFile]:
    """A full synthetic folder: the file/manifest and the P1/P2 source databases."""
    doc = copy.deepcopy(document) if document is not None else aggregates_document()
    path = write_aggregates(tmp_path, doc)
    p1 = scenario_rows("P1")
    p1["book_rebalance"] += [
        {
            "id": 4,
            "book_id": 2,
            "decision_date": "2022-02-01",
            "execution_date": "2022-02-02",
            "quant_portfolio_id": 13,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
        {
            "id": 5,
            "book_id": 3,
            "decision_date": "2022-02-01",
            "execution_date": "2022-02-02",
            "quant_portfolio_id": 14,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
    ]
    backtest_db(tmp_path, name="rule_P1.db", window="P1", rows=p1)
    backtest_db(tmp_path, name="rule_P2.db", window="P2", rows=p2_rows())
    return tmp_path, with_manifest(parse_aggregates(path, label="rule"), tmp_path, path.name)


def _verifier(tmp_path: Path, document: dict[str, object] | None = None) -> Verification:
    directory, data = _folder(tmp_path, document)
    return verify_sources(data, directory)


def test_the_synthetic_file_has_the_real_shape() -> None:
    document = aggregates_document()
    assert set(document) == {
        "label",
        "config_id",
        "trend_filter_applies_to_arms",
        "sources",
        "dictionary",
        "trend_filter",
        "reference_returns",
    }
    assert document["trend_filter_applies_to_arms"] == [
        "TOPN_MV_NOGUARD",
        "TOPN_MV_GUARD_NO_NLP",
    ]
    assert {row["spy_vs_sma210"] for row in document["trend_filter"]} >= {"not_evaluable"}
    assert {row["segment"] for row in document["reference_returns"]} >= {"P2a", "P2b"}
    assert {row["reference"] for row in document["reference_returns"]} == {
        "SPY",
        "SP500_EW_INTERNAL",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda doc: doc.update({"extra": 1}), "unknown 'extra'"),
        (lambda doc: doc.pop("dictionary"), "missing 'dictionary'"),
        (lambda doc: doc["trend_filter"][0].update({"level": 1}), "unknown 'level'"),
        (
            lambda doc: doc["trend_filter"][0].update({"spy_vs_sma210": "on"}),
            "not one of",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"reference": "QQQ"}),
            "not one of",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"segment": "P1x2"}),
            "segment pattern",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"segment": "H1"}),
            "not the window",
        ),
        (
            lambda doc: doc["trend_filter"][1].update({"decision_date": "20220201"}),
            "strict",
        ),
        (
            lambda doc: doc["trend_filter"][1].update({"cash_fraction": True}),
            "JSON number",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"n_sessions": 0}),
            "positive count",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"max_drawdown": -0.1}),
            "negative",
        ),
        (
            lambda doc: doc["reference_returns"][0].update({"total_return": "0.1"}),
            "JSON number",
        ),
        (lambda doc: doc["sources"].update({"extra": "x"}), "unknown 'extra'"),
        (
            lambda doc: doc["sources"].update({"spy_total_return_series_sha256": "ABC"}),
            "64 lowercase",
        ),
        (
            lambda doc: doc["dictionary"]["trend_filter"].update({"window": ""}),
            "non-empty",
        ),
        (lambda doc: doc["trend_filter_applies_to_arms"].reverse(), "expected"),
    ],
)
def test_the_parser_rejects_an_unknown_or_malformed_value(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], object], message: str
) -> None:
    document = aggregates_document()
    mutation(document)
    path = write_aggregates(tmp_path, document)
    with pytest.raises(AggregatesError, match=message):
        parse_aggregates(path, label="rule")


def test_the_parser_rejects_duplicate_rows(tmp_path: Path) -> None:
    document = aggregates_document()
    document["trend_filter"].append(dict(document["trend_filter"][0]))
    path = write_aggregates(tmp_path, document)
    with pytest.raises(AggregatesError, match="duplicate trend_filter row"):
        parse_aggregates(path, label="rule")
    document = aggregates_document()
    document["reference_returns"].append(dict(document["reference_returns"][0]))
    path = write_aggregates(tmp_path, document)
    with pytest.raises(AggregatesError, match="duplicate reference_returns row"):
        parse_aggregates(path, label="rule")


def test_a_segment_needs_both_references(tmp_path: Path) -> None:
    document = aggregates_document()
    document["reference_returns"] = [
        row for row in document["reference_returns"] if row["reference"] != "SPY"
    ]
    path = write_aggregates(tmp_path, document)
    with pytest.raises(AggregatesError, match="needs exactly"):
        parse_aggregates(path, label="rule")


def test_the_label_must_match_the_file(tmp_path: Path) -> None:
    path = write_aggregates(tmp_path, aggregates_document("rule"))
    with pytest.raises(AggregatesError, match="the file's label is 'rule'"):
        parse_aggregates(path, label="candidate")


def test_the_manifest_matches_and_refuses_a_mismatch(tmp_path: Path) -> None:
    path = write_aggregates(tmp_path, aggregates_document())
    assert verify_manifest(tmp_path, path.name) == read_manifest(tmp_path / "SHA256SUMS")[path.name]
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ManifestError) as error:
        verify_manifest(tmp_path, path.name)
    assert "manifest says" in str(error.value)
    assert "the file has" in str(error.value)


def test_the_manifest_must_list_the_file(tmp_path: Path) -> None:
    path = write_aggregates(tmp_path, aggregates_document())
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  other.json\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="is not listed"):
        verify_manifest(tmp_path, path.name)


def test_the_manifest_format_is_strict(tmp_path: Path) -> None:
    (tmp_path / "SHA256SUMS").write_text("ABC  file.json\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="expected"):
        read_manifest(tmp_path / "SHA256SUMS")


def test_deterministic_iris_and_dictionary_comments() -> None:
    assert aggregates_set_iri("rule") == KG.AggregatesSet_rule
    trend = TrendFilterRow("P1", datetime.date(2022, 2, 1), "below", Decimal("0.5"))
    assert trend_filter_iri("rule", trend) == KG.TrendFilter_rule_P1_20220201
    reference = ReferenceReturnRow(
        "P2",
        "P2a",
        datetime.date(2025, 2, 19),
        datetime.date(2025, 5, 6),
        54,
        "SP500_EW_INTERNAL",
        Decimal("-0.02"),
        Decimal("0.12"),
    )
    assert reference_return_iri("rule", reference) == KG.RefReturn_rule_P2a_SP500_EW_INTERNAL
    assert aggregates_document()["dictionary"]["trend_filter"]["window"] == (
        "backtest window id (P1, H1, P3, H2, P2, H3)"
    )


def test_the_batch_is_deterministic_and_conforms(tmp_path: Path) -> None:
    _directory, data = _folder(tmp_path)
    first = project(data)
    second = project(data)
    assert first.turtle() == second.turtle()
    graph, turtle = batch(data)
    assert graph == GRAPH
    batch_graph = gate.parse_batch(turtle)
    gate.validate(batch_graph)
    assert (KG.AggregatesSet_rule, RDF.type, KG.AggregatesSet) in batch_graph
    assert len(first) == len(batch_graph)
    # sources.spy_total_return_series_sha256 is validated but never projected.
    assert b"spy_total_return_series_sha256" not in turtle
    assert aggregates_document()["sources"]["spy_total_return_series_sha256"].encode() not in turtle


def test_the_shapes_close_the_lists() -> None:
    shapes = rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")

    def listed(shape: rdflib.URIRef) -> set[str]:
        return {
            str(item)
            for prop in shapes.objects(shape, SH.property)
            for values in shapes.objects(prop, SH["in"])
            for item in shapes.items(values)
        }

    assert listed(KG.TrendFilterStateShape) >= {
        "below",
        "at_or_above",
        "not_evaluable",
        "TOPN_MV_NOGUARD",
        "TOPN_MV_GUARD_NO_NLP",
    }
    assert listed(KG.ReferenceReturnShape) == {"SPY", "SP500_EW_INTERNAL"}


def test_the_shapes_reject_an_unknown_state_or_reference(tmp_path: Path) -> None:
    _directory, data = _folder(tmp_path)
    batch_graph = rdflib.Graph()
    batch_graph.parse(data=project(data).turtle(), format="turtle")
    subject = KG.TrendFilter_rule_P1_20220201
    batch_graph.remove((subject, KG.trendState, None))
    batch_graph.add((subject, KG.trendState, rdflib.Literal("on")))
    with pytest.raises(gate.ShaclRejected, match="trendState"):
        gate.validate(batch_graph)

    batch_graph = rdflib.Graph()
    batch_graph.parse(data=project(data).turtle(), format="turtle")
    subject = KG.RefReturn_rule_P1_SPY
    batch_graph.remove((subject, KG.referenceName, None))
    batch_graph.add((subject, KG.referenceName, rdflib.Literal("QQQ")))
    with pytest.raises(gate.ShaclRejected, match="referenceName"):
        gate.validate(batch_graph)


def test_the_gate_accepts_the_graph_once_and_refuses_a_second_write(
    tmp_path: Path,
) -> None:
    _directory, data = _folder(tmp_path)
    graph, turtle = batch(data)
    assert gate.check_target(graph) is True
    store = cast(GraphDB, DatasetStore(rdflib.Dataset()))
    plan = gate.plan(store, turtle, graph)
    assert plan.status is gate.IngestPlanStatus.WOULD_WRITE
    assert gate.write(store, plan) == len(project(data))
    second = gate.plan(store, turtle, graph)
    assert second.status is gate.IngestPlanStatus.ALREADY_IN_STORE
    with pytest.raises(gate.IngestRejected, match="already exists"):
        gate.write(store, second)


def test_the_gate_target_cannot_collide_with_the_other_backtest_names() -> None:
    assert gate.check_target("urn:graph:derived:backtest:aggregates:rule")
    assert gate.check_target("urn:graph:derived:backtest:meta:rule")
    assert gate.check_target("urn:graph:derived:backtest:rule:P1:1")
    assert gate.check_target("urn:graph:derived:backtest:selection:rule:P1:1")
    with pytest.raises(gate.IngestRejected):
        gate.check_target("urn:graph:derived:backtest:aggregates:Rule")


def test_the_verifier_accepts_the_synthetic_folder(tmp_path: Path) -> None:
    verification = _verifier(tmp_path)
    assert verification.ok, verification.summary()
    names = {check.name for check in verification.checks}
    assert "manifest" in names
    assert "trend filter P1" in names
    assert "reference returns P2a" in names
    assert "cash fractions" in names
    assert "P2 compounding" in names


def test_the_verifier_reports_a_window_whose_dates_differ(tmp_path: Path) -> None:
    document = aggregates_document()
    document["trend_filter"].append(
        {
            "window": "P1",
            "decision_date": "2022-03-01",
            "spy_vs_sma210": "at_or_above",
            "cash_fraction": 0.0,
        }
    )
    verification = _verifier(tmp_path, document)
    failed = [check for check in verification.checks if not check.passed]
    assert failed
    assert any("P1" in check.detail and "2022-03-01" in check.detail for check in failed)


def test_the_verifier_reports_a_reference_date_mismatch(tmp_path: Path) -> None:
    document = aggregates_document()
    document["reference_returns"][0]["date_from"] = "2022-01-04"
    verification = _verifier(tmp_path, document)
    failed = [check for check in verification.checks if not check.passed]
    assert any("segment P1" in check.detail and "date_from" in check.detail for check in failed)


def test_the_verifier_rejects_a_bad_cash_fraction(tmp_path: Path) -> None:
    document = aggregates_document()
    document["trend_filter"][1]["cash_fraction"] = 0.0
    verification = _verifier(tmp_path, document)
    failed = [check for check in verification.checks if not check.passed]
    assert any(
        check.name == "cash fractions" and "below with cash 0" in check.detail for check in failed
    )


def test_the_verifier_reports_uncompounded_p2(tmp_path: Path) -> None:
    document = aggregates_document()
    document["reference_returns"][2]["total_return"] = 0.2
    verification = _verifier(tmp_path, document)
    failed = [check for check in verification.checks if not check.passed]
    assert any(check.name == "P2 compounding" and "differs" in check.detail for check in failed)


def test_the_stored_graph_equals_the_file(tmp_path: Path) -> None:
    _directory, data = _folder(tmp_path)
    builder = project(data)
    store = cast(GraphDB, DatasetStore(rdflib.Dataset()))
    graph, turtle = batch(data)
    gate.write(store, gate.plan(store, turtle, graph))
    assert verify_stored(store, data, builder).passed
    altered = copy.copy(builder)
    altered.triples = set(builder.triples)
    first = next(iter(altered.triples))
    altered.triples.remove(first)
    altered.triples.add((first[0], first[1], rdflib.Literal("changed")))
    assert not verify_stored(store, data, altered).passed


def test_a_manifest_mismatch_stops_the_verifier(tmp_path: Path) -> None:
    directory, data = _folder(tmp_path)
    path = directory / "aggregates_rule.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    verification = verify_sources(data, directory)
    assert not verification.ok
    assert verification.checks[0].name == "manifest"
    assert not verification.checks[0].passed


def test_a_missing_database_is_reported_by_window(tmp_path: Path) -> None:
    directory, data = _folder(tmp_path)
    (directory / "rule_P2.db").unlink()
    verification = verify_sources(data, directory)
    failed = [check for check in verification.checks if not check.passed]
    assert any("P2" in check.name or "P2" in check.detail for check in failed)


def test_reference_rows_are_projected_from_the_file_not_hard_coded(
    tmp_path: Path,
) -> None:
    document = aggregates_document()
    document["trend_filter"] = [row for row in document["trend_filter"] if row["window"] == "P1"]
    document["trend_filter"][1]["cash_fraction"] = 0.25
    document["reference_returns"] = [
        *reference_pair("P1", "P1", "2022-01-03", "2022-10-12", 196, (0.01, 0.02), (0.03, 0.04))
    ]
    path = write_aggregates(tmp_path, document)
    data = with_manifest(parse_aggregates(path, label="rule"), tmp_path, path.name)
    graph = project(data)
    cash = [
        value
        for subject, predicate, value in graph.triples
        if subject == KG.TrendFilter_rule_P1_20220201 and predicate == KG.cashFraction
    ]
    assert cash == [rdflib.Literal("0.25", datatype=rdflib.XSD.decimal)]
