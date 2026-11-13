"""The pilot detail file through the event projector (Work item 46, T-854-T-859, opt-in).

Run with ``-m integration``. The pilot is read-only; no store is contacted. The test reproduces the
design's per-class counts, proves no price-derived triple reaches the batch, and validates the
combined m018 + detail + selection graph against ``shapes.ttl``.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pyshacl
import pytest
import rdflib
from rdflib.namespace import RDF

from projection.backtest import (
    AssetInfo,
    load_guard_catalog,
    load_selection_catalog,
    project_selection_source,
    project_source,
    validation_context,
)
from projection.source import FinancialSource
from projection.veto_events import (
    KG,
    parse_detail_file,
    read_asset_tickers,
    selection_index,
)

PILOT_DB = Path(
    "/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/piloto_H1C_P1/H1C-B5-P1.db"
)
PILOT_JSONL = Path(
    "/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/piloto_H1C_P1/"
    "H1C-B5-P1.cartera_v1_3.kg.jsonl"
)
MASK = Path(
    "/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/mascara_tiingo/"
    "tiingo_assets.csv"
)

DESIGN_COUNTS = {
    "DecisionEvent": 221,  # 140 resolved + 81 refilled links
    "FormationTarget": 80,
    "RetentionDecision": 154,  # 130 design + 20 shape-required retentionOfBook/retentionDate
    "RetentionHold": 110,
    "RetentionRejection": 36,
    "StopEvent": 1423,
    "DestinationOption": 429,
    "StopRejectionSummary": 211,
    "StopMemory": 239,
    "ReplacementPurchase": 85,  # 84 + the replacementStoppedBy link
    "ReplacementCheck": 25,
}


def _pilot() -> tuple[Path, Path]:
    value = os.environ.get("VETO_PILOT_DIR")
    if value:
        folder = Path(value)
        return folder / "H1C-B5-P1.db", folder / "H1C-B5-P1.cartera_v1_3.kg.jsonl"
    if not PILOT_DB.is_file() or not PILOT_JSONL.is_file():
        pytest.skip("VETO_PILOT_DIR is not set and the pilot files are absent")
    return PILOT_DB, PILOT_JSONL


def _masked_tickers() -> set[str]:
    if not MASK.is_file():
        return set()
    with MASK.open(newline="", encoding="utf-8") as handle:
        return {row["ticker"] for row in csv.DictReader(handle) if row.get("ticker")}


@pytest.mark.integration
def test_the_pilot_detail_counts_and_shacl() -> None:  # noqa: C901, PLR0912
    db_path, jsonl_path = _pilot()
    detail = parse_detail_file(jsonl_path)
    source = FinancialSource.open(db_path)
    try:
        tickers = read_asset_tickers(source)
        assets = {ticker: AssetInfo(ticker, None) for ticker in tickers.values()}
        selection = selection_index(
            source,
            "final",
            "P1",
            "SYSTEM_WITH_HIERARCHY",
            [str(line["date"]) for line in detail.decisions],
            configured_names=False,
        )
        m018 = project_source(
            source,
            assets,
            load_guard_catalog("schema/rules.ttl"),
            "final",
            configuration="SYSTEM_WITH_HIERARCHY",
            window="P1",
            book_code="TOPN_MV_GUARD_NO_NLP",
            book_id=3,
            detail=detail,
            asset_tickers=tickers,
            selection=selection,
        )
        selection_projection = project_selection_source(
            source, assets, load_selection_catalog("schema/rules.ttl"), "final"
        )
    finally:
        source.close()
    assert m018.projection.detail is not None
    assert dict(m018.projection.detail.triples_by_class()) == DESIGN_COUNTS
    detail_graph = rdflib.Graph()
    for triple in m018.projection.detail.triples:
        detail_graph.add(triple)
    assert len(detail_graph) == 3013
    for prop in (
        KG.stopDistancePct,
        KG.closePrice,
        KG.dailyReturn,
        KG.alertValue,
        KG.alertThreshold,
    ):
        assert not list(detail_graph.triples((None, prop, None))), prop
    graph = rdflib.Graph()
    for projection in (m018.projection, selection_projection.projection):
        for builder in projection.graphs.values():
            for triple in builder.triples:
                graph.add(triple)
    for triple in validation_context(assets, load_guard_catalog("schema/rules.ttl")):
        graph.add(triple)
    masked = _masked_tickers()
    for ticker in masked:
        for prop in (
            KG.stopDistancePct,
            KG.closePrice,
            KG.dailyReturn,
            KG.alertValue,
            KG.alertThreshold,
        ):
            assert not list(graph.triples((KG[ticker], prop, None))), (ticker, prop)
    for alert in graph.subjects(KG.alertRule, None):
        rule = str(graph.value(alert, KG.alertRule))
        if "#Rule_L1_BP_" not in rule:
            continue
        assert (alert, KG.alertValue, None) not in graph, alert
        assert (alert, KG.alertThreshold, None) not in graph, alert
    for ticker in assets:
        graph.add((KG[ticker], KG.cikNumber, rdflib.Literal("0000000000")))
    tbox = rdflib.Graph().parse("schema/tbox.ttl", format="turtle")
    for configuration in tbox.subjects(RDF.type, KG.BacktestConfiguration):
        for predicate, value in tbox.predicate_objects(configuration):
            graph.add((configuration, predicate, value))
    shapes = rdflib.Graph().parse("schema/shapes.ttl", format="turtle")
    conforms, results, _ = pyshacl.validate(graph, shacl_graph=shapes)
    assert conforms, results.serialize(format="turtle")[:8000]
