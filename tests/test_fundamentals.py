"""The fundamentals block C loader: parser, mask, projector and gate (Work item 45)."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import cast

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from fixtures.fundamentals_rows import (
    METRICS as FIXTURE_METRICS,
)
from fixtures.fundamentals_rows import (
    UNIVERSE_ROWS,
    Fixture,
    write_fixture,
    write_manifest,
)
from rdflib.namespace import OWL, RDF, RDFS, XSD

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection import fundamentals
from projection.fundamentals import (
    FORBIDDEN_PROPERTIES,
    METRIC_PROPERTIES,
    FundamentalsError,
    ManifestError,
    assessment_iri,
    graph_name,
    load_file,
    metric_set_iri,
    parse_delivery,
    project,
    statistics,
    validation_graph,
    verify_manifest,
    verify_stored,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
SCHEMA = Path(__file__).resolve().parent.parent / "schema"


def _fixture(tmp_path: Path) -> Fixture:
    return write_fixture(tmp_path)


def _load(
    fixture: Fixture,
    *,
    manifest_sha256: str | None = None,
    mask_sha256: str | None = None,
    universe_db: Path | None = None,
) -> fundamentals.FundamentalsFile:
    return load_file(
        "final",
        fixture.directory,
        mask_path=fixture.mask,
        universe_db=universe_db or fixture.universe_db,
        expected_manifest_sha256=manifest_sha256 or fixture.manifest_sha256,
        expected_mask_sha256=mask_sha256 or fixture.mask_sha256,
    )


def _rewrite_metrics(fixture: Fixture, rows: list[list[object]]) -> str:
    path = fixture.directory / "metrics.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fundamentals.METRICS_HEADER)
        writer.writerows(rows)
    return write_manifest(fixture.directory)


def _metric_rows() -> list[list[object]]:
    return [list(row) for row in FIXTURE_METRICS]


def _universe_without(path: Path, excluded: set[str]) -> Path:
    target = path.with_name("universe_without.db")
    connection = sqlite3.connect(target)
    try:
        connection.execute(
            "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
            "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
        )
        connection.executemany(
            "INSERT INTO universe_membership VALUES (?, ?, NULL, NULL, ?, ?, ?)",
            [
                (symbol, security, cik, start, end)
                for symbol, security, cik, start, end in UNIVERSE_ROWS
                if symbol not in excluded
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return target


def test_the_fixture_has_the_expected_identity(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    data = _load(fixture)
    assert len(data.filings) == 4
    assert len(data.metrics) == 16
    assert len(data.assessments) == 4
    assert len(data.mask) == 2
    assert data.manifest_sha256 == fixture.manifest_sha256
    assert data.mask_sha256 == fixture.mask_sha256
    assert data.source_db == "scored_llm.db"
    assert set(data.assets) == {"A", "ABBV", "ABMD", "APA", "FRC"}


def test_the_fixture_batch_has_147_triples(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    assert len(builder) == 147
    triples = builder.triples
    assert sum(1 for _, p, o in triples if p == RDF.type and o == KG.SECFiling) == 4
    assert sum(1 for _, p, o in triples if p == RDF.type and o == KG.FundamentalMetricSet) == 4
    assert sum(1 for _, p, o in triples if p == RDF.type and o == KG.FundamentalAssessment) == 4
    assert sum(1 for _, p, _ in triples if p == KG.pricesNotPublished) == 2


def test_the_statistics_match_the_batch(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    stats = statistics(data)
    assert stats.filings == 4
    assert stats.metric_sets == 4
    assert stats.metric_rows == 16
    assert stats.metric_values == 11
    assert stats.null_values == 1
    assert stats.value_inputs_rows == 4
    assert stats.masked_value_inputs_rows == 1
    assert stats.assessments == 4
    assert stats.scored == 3
    assert stats.rule_rows == 1
    assert stats.strengths == 12
    assert stats.risks == 12
    assert stats.masked_flags == 2


def test_a_null_metric_has_no_triple(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    abmd = metric_set_iri("final", 76)
    assert not any(s == abmd and p == KG.interestCoverage for s, p, _ in builder.triples)
    assert any(s == abmd and p == KG.returnOnEquity for s, p, _ in builder.triples)


def test_a_scientific_notation_value_becomes_an_xsd_decimal(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    set_node = metric_set_iri("final", 62)
    assert (
        set_node,
        KG.netMargin,
        rdflib.Literal("0.019550102249488752", datatype=XSD.decimal),
    ) in builder.triples


def test_the_two_timestamp_filing_keeps_the_latest_computed_at(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    set_node = metric_set_iri("final", 62)
    values = [o for s, p, o in builder.triples if s == set_node and p == KG.computedAt]
    assert values == [rdflib.Literal("2026-10-23T03:49:27+00:00", datatype=XSD.dateTime)]


def test_value_inputs_rows_are_discarded_for_every_asset(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    assert not any(
        "valueInputs" in str(p) or "value_inputs" in str(p) for _, p, _ in builder.triples
    )
    stats = statistics(data)
    assert stats.value_inputs_rows == 4
    assert stats.masked_value_inputs_rows == 1


def test_the_five_valuation_metrics_load_for_the_unmasked_asset(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    unmasked = metric_set_iri("final", 1)
    masked = metric_set_iri("final", 76)
    for name in (
        "enterprise_fcf_yield",
        "enterprise_value",
        "free_cash_flow_yield",
        "market_capitalization",
        "sbc_adjusted_fcf_yield",
    ):
        assert any(
            s == unmasked and p == KG[METRIC_PROPERTIES[name]] for s, p, _ in builder.triples
        )
        assert not any(
            s == masked and p == KG[METRIC_PROPERTIES[name]] for s, p, _ in builder.triples
        )


def test_the_masked_assets_flag_includes_the_one_without_filings(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    assert (KG.ABMD, KG.pricesNotPublished, rdflib.Literal(True)) in builder.triples
    assert (KG.FRC, KG.pricesNotPublished, rdflib.Literal(True)) in builder.triples
    assert not any(s == KG.FRC and p == RDF.type for s, p, _ in builder.triples)
    assert not any(s == KG.ABMD and p == RDF.type for s, p, _ in builder.triples)


def test_the_rule_row_has_no_score_or_rating(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    rule = assessment_iri("final", 36)
    assert (
        rule,
        KG.generatedByLanguageModel,
        rdflib.Literal(False, datatype=XSD.boolean),
    ) in builder.triples
    assert not any(s == rule and p in (KG.scoreRaw0to100, KG.rating) for s, p, _ in builder.triples)
    scored = assessment_iri("final", 535)
    assert (scored, KG.scoreRaw0to100, rdflib.Literal("73.2", datatype=XSD.decimal)) in (
        builder.triples
    )
    assert (scored, KG.rating, rdflib.Literal("bullish")) in builder.triples


def test_the_batch_has_no_prompt_hash_metric_ids_or_score_snapshot(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    predicates = {str(p) for _, p, _ in builder.triples}
    assert "https://thesis.local/kg/portfolio#promptHash" not in predicates
    assert "https://thesis.local/kg/portfolio#metricIdsJson" not in predicates
    assert "https://thesis.local/kg/portfolio#assessmentOfSnapshot" not in predicates
    assert not any(o == KG.ScoreSnapshot for _, _, o in builder.triples)


def test_the_batch_has_no_price_or_daily_return_property(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    predicates = {str(p) for _, p, _ in builder.triples}
    for name in FORBIDDEN_PROPERTIES:
        assert f"https://thesis.local/kg/portfolio#{name}" not in predicates
    for _, p, o in builder.triples:
        assert o != KG.PriceObservation
        assert "dailyReturn" not in str(p)


def test_the_batch_conforms_to_shacl(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    payload = project(data).turtle()
    gate.validate(gate.parse_batch(payload), context=validation_graph(data))


def test_the_37_metric_properties_are_the_schema_ones() -> None:
    tbox = rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")
    assert len(METRIC_PROPERTIES) == 37
    for name, prop in METRIC_PROPERTIES.items():
        node = KG[prop]
        assert (node, RDF.type, OWL.DatatypeProperty) in tbox, name
        assert (node, RDFS.domain, KG.FundamentalMetricSet) in tbox, name
        assert (node, RDFS.range, XSD.decimal) in tbox, name
    assert (KG.valueInputs, RDF.type, OWL.DatatypeProperty) not in tbox


def test_a_masked_valuation_row_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    rows = _metric_rows()
    rows.append(
        [
            999999,
            76,
            "valuation",
            "market_capitalization",
            "1.0",
            "usd",
            "metrics-v10",
            "2026-10-23T03:50:06+00:00",
            "2022-02-04",
        ]
    )
    manifest = _rewrite_metrics(fixture, rows)
    with pytest.raises(FundamentalsError, match="valuation row of a masked asset") as info:
        _load(fixture, manifest_sha256=manifest)
    assert "metric_id 999999" in str(info.value)
    assert "ABMD" in str(info.value)


def test_a_masked_value_inputs_row_is_discarded_not_an_error(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    data = _load(fixture)
    assert statistics(data).masked_value_inputs_rows == 1


def test_an_unknown_mask_ticker_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    universe = _universe_without(fixture.universe_db, {"FRC"})
    with pytest.raises(FundamentalsError, match="FRC") as info:
        _load(fixture, universe_db=universe)
    assert "do not resolve" in str(info.value)


def test_an_unknown_metric_name_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    rows = _metric_rows()
    rows.append(
        [
            999999,
            1,
            "profitability",
            "not_a_metric",
            "1.0",
            "ratio",
            "metrics-v10",
            "2026-10-23T03:46:24+00:00",
            "2022-03-04",
        ]
    )
    manifest = _rewrite_metrics(fixture, rows)
    with pytest.raises(FundamentalsError, match="unknown metric_name"):
        _load(fixture, manifest_sha256=manifest)


def test_a_duplicate_metric_key_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    rows = _metric_rows()
    rows.append(
        [
            999999,
            76,
            "profitability",
            "return_on_equity",
            "0.1",
            "ratio",
            "metrics-v10",
            "2026-10-23T03:50:06+00:00",
            "2022-02-04",
        ]
    )
    manifest = _rewrite_metrics(fixture, rows)
    with pytest.raises(FundamentalsError, match="duplicate"):
        _load(fixture, manifest_sha256=manifest)


def test_a_tampered_data_file_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    path = fixture.directory / "metrics.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        _load(fixture)


def test_a_tampered_manifest_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest = fixture.directory / "SHA256SUMS"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        verify_manifest(
            fixture.directory,
            expected_manifest_sha256=fixture.manifest_sha256,
        )


def test_a_duplicate_snapshot_id_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    path = fixture.directory / "assessments.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([*lines, lines[0]]) + "\n", encoding="utf-8")
    manifest = write_manifest(fixture.directory)
    with pytest.raises(FundamentalsError, match="duplicate snapshot_id"):
        _load(fixture, manifest_sha256=manifest)


def test_a_provenance_mismatch_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    path = fixture.directory / "assessments.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace(
        "generated by a language model from computed ratios; not a verified fact",
        "generated by a language model from computed ratios; a verified fact",
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = write_manifest(fixture.directory)
    with pytest.raises(FundamentalsError, match="provenance_note differs"):
        _load(fixture, manifest_sha256=manifest)


def test_an_assessment_available_at_mismatch_stops_the_load(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    path = fixture.directory / "assessments.jsonl"
    document = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    document["available_at"] = "2021-11-09"
    path.write_text(
        json.dumps(document) + "\n" + path.read_text(encoding="utf-8").split("\n", 1)[1],
        encoding="utf-8",
    )
    manifest = write_manifest(fixture.directory)
    with pytest.raises(FundamentalsError, match="available_at"):
        _load(fixture, manifest_sha256=manifest)


def test_the_check_store_plan_reads_and_writes_nothing(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    dataset = rdflib.Dataset()
    for triple in validation_graph(data):
        dataset.default_graph.add(triple)
    store = DatasetStore(dataset)
    plan = gate.plan(cast(GraphDB, store), builder.turtle(), graph_name("final"))
    assert plan.status is gate.IngestPlanStatus.WOULD_WRITE
    assert store.writes == []
    assert not any("INSERT" in query or "DELETE" in query for query in store.queries)


def test_verify_stored_compares_the_written_graph(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    builder = project(data)
    dataset = rdflib.Dataset()
    for triple in validation_graph(data):
        dataset.default_graph.add(triple)
    store = DatasetStore(dataset)
    plan = gate.plan(cast(GraphDB, store), builder.turtle(), graph_name("final"))
    assert gate.write(cast(GraphDB, store), plan) == 147
    check = verify_stored(store, data, builder)
    assert check.passed
    assert "equal the batch" in check.detail


def test_the_graph_name_is_the_fundamentals_target(tmp_path: Path) -> None:
    data = _load(_fixture(tmp_path))
    assert graph_name("final") == "urn:graph:derived:fundamentals:final"
    assert graph_name(data.label) == "urn:graph:derived:fundamentals:final"
    with pytest.raises(FundamentalsError, match="run label"):
        graph_name("Final")


def test_parse_delivery_does_not_need_the_universe(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    data = parse_delivery(
        fixture.directory,
        "final",
        mask_path=fixture.mask,
        expected_manifest_sha256=fixture.manifest_sha256,
        expected_mask_sha256=fixture.mask_sha256,
    )
    assert data.assets == {}
    assert len(data.assessments) == 4


def test_the_declared_hash_is_part_of_the_fixture(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert hashlib.sha256((fixture.directory / "SHA256SUMS").read_bytes()).hexdigest() == (
        fixture.manifest_sha256
    )
    assert hashlib.sha256(fixture.mask.read_bytes()).hexdigest() == fixture.mask_sha256
