"""Guard layers and L3 thresholds are data, not a fixed ``[1, 3, 4]`` assumption (Work item 34).

The final backtest has arms with different ``guard_layers`` and portfolio-level L3_VOL thresholds
that change over time. These hermetic cases prove the projector and verifier never assume a fixed
layer set or a fixed threshold.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.backtest_rows import (
    ASSETS,
    backtest_db,
    guard_layer_scenario_rows,
    load_catalog,
    varying_threshold_scenario_rows,
)
from fixtures.dataset_store import DatasetStore

from projection.backtest import Projection, project_source
from projection.source import FinancialSource
from projection.verify_backtest import Verification, verify

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)
GRAPH = "urn:graph:derived:backtest:rule:P1:1"


def _project_and_verify(
    tmp_path: Path, rows: dict[str, list[dict[str, Any]]]
) -> tuple[Projection, Verification]:
    path = backtest_db(tmp_path, rows=rows)
    source = FinancialSource.open(path)
    try:
        projection = project_source(source, ASSETS, load_catalog(), "rule")
    finally:
        source.close()
    dataset = rdflib.Dataset(default_union=True)
    for name, builder in projection.projection.graphs.items():
        graph = dataset.graph(rdflib.URIRef(name))
        for triple in builder.triples:
            graph.add(triple)
    store = DatasetStore(dataset)
    result = verify(
        store,
        GRAPH,
        path,
        "rule",
        assets=ASSETS,
        catalog=load_catalog(),
        repository=store.repository,
    )
    return projection.projection, result


@pytest.mark.parametrize(
    ("layers", "rules", "present", "absent"),
    [
        (
            "[1]",
            ("L1_STOP_LOSS", "L1_REENTRY", "L1_BP_STOP", "L1_BP_REENTRY"),
            (),
            ("L3_VOL", "L4_DD"),
        ),
        (
            "[1, 4]",
            ("L1_STOP_LOSS", "L1_REENTRY", "L1_BP_STOP", "L1_BP_REENTRY", "L4_DD"),
            ("L4_DD",),
            ("L3_VOL",),
        ),
    ],
)
def test_a_guard_arm_uses_only_the_layers_it_declares(
    tmp_path: Path,
    layers: str,
    rules: tuple[str, ...],
    present: tuple[str, ...],
    absent: tuple[str, ...],
) -> None:
    rows = guard_layer_scenario_rows(guard_layers=layers, alert_rules=rules)
    projection, result = _project_and_verify(tmp_path, rows)
    graph = rdflib.Graph()
    for triple in projection.graphs[GRAPH].triples:
        graph.add(triple)

    for arm in ("TOPN_MV_GUARD_NO_NLP", "MARKOWITZ_BASE_GUARD"):
        book = KG[f"Book_rule_P1_{arm}"]
        assert graph.value(book, KG.guardLayers) == rdflib.Literal(layers)
    alert_rules = set(graph.objects(None, KG.alertRule))
    for rule in present:
        assert KG[f"Rule_{rule}"] in alert_rules
    for rule in absent:
        assert KG[f"Rule_{rule}"] not in alert_rules

    assert result.ok, result.summary()
    assert len(result.checks) == 23


def test_l3_vol_thresholds_may_change_by_date(tmp_path: Path) -> None:
    rows = varying_threshold_scenario_rows()
    projection, result = _project_and_verify(tmp_path, rows)
    graph = rdflib.Graph()
    for triple in projection.graphs[GRAPH].triples:
        graph.add(triple)

    alerts = list(graph.subjects(KG.alertRule, KG.Rule_L3_VOL))
    assert len(alerts) == 2
    by_date = {
        str(graph.value(alert, KG.alertDate)): Decimal(str(graph.value(alert, KG.alertThreshold)))
        for alert in alerts
    }
    assert by_date == {"2022-01-03": Decimal("0.20"), "2022-01-05": Decimal("0.25")}
    assert all(graph.value(alert, KG.guardAsset) is None for alert in alerts)

    assert result.ok, result.summary()
    assert len(result.checks) == 23
