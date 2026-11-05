"""The final-backtest shape: six windows, four arms, P2 segments and SPY (Work item 34).

The fixture is deliberately small, but it carries every structural feature the real delivery has:
``P1``/``H1``/``P3``/``H2``/``P2``/``H3``, the fourth arm, ``P2a``/``P2b`` summaries, ``SPY`` in the
daily weights and ``L1_BP_*`` alerts whose source threshold must not be published. Both projectors
and the verifier run over it with no store and no real database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import rdflib
from fixtures.backtest_rows import (
    ASSETS,
    FINAL_ARMS,
    FINAL_WINDOWS,
    SCHEMA,
    final_backtest_db,
    load_catalog,
)
from fixtures.dataset_store import DatasetStore

from projection.backtest import (
    SelectionSourceProjection,
    SourceProjection,
    load_selection_catalog,
    project_selection_source,
    project_source,
    selection_graph_name,
)
from projection.source import FinancialSource
from projection.verify_backtest import verify

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)


def _projections(path: Path) -> tuple[SourceProjection, SelectionSourceProjection]:
    source = FinancialSource.open(path)
    try:
        m018 = project_source(source, ASSETS, load_catalog(), "rule")
        selection = project_selection_source(
            source, ASSETS, load_selection_catalog(SCHEMA / "rules.ttl"), "rule"
        )
    finally:
        source.close()
    return m018, selection


@pytest.mark.parametrize("window", list(FINAL_WINDOWS))
def test_every_window_projects_and_verifies(tmp_path: Path, window: str) -> None:
    path = final_backtest_db(tmp_path, window)
    m018, selection = _projections(path)
    graph_name = f"urn:graph:derived:backtest:rule:{window}:1"
    selection_name = selection_graph_name("rule", window, 1)

    dataset = rdflib.Dataset(default_union=True)
    for source_projection in (m018, selection):
        for name, builder in source_projection.projection.graphs.items():
            graph = dataset.graph(rdflib.URIRef(name))
            for triple in builder.triples:
                graph.add(triple)

    stored = dataset.graph(rdflib.URIRef(graph_name))
    assert {str(arm) for arm in stored.objects(None, KG.armCode)} == set(FINAL_ARMS)
    assert next(stored.subjects(KG.holdingAsset, KG.SPY), None) is not None

    # The Basing Points alerts are present and carry no threshold; fixed-parameter alerts do.
    bp_alerts = [
        alert
        for alert in stored.subjects(rdflib.RDF.type, KG.GuardAlert)
        if str(stored.value(alert, KG.alertRule)).startswith(NS + "Rule_L1_BP_")
    ]
    assert bp_alerts
    assert all(stored.value(alert, KG.alertThreshold) is None for alert in bp_alerts)
    assert any(
        stored.value(alert, KG.alertThreshold) is not None
        for alert in stored.subjects(rdflib.RDF.type, KG.GuardAlert)
    )

    store = DatasetStore(dataset)
    m018_result = verify(
        store,
        graph_name,
        path,
        "rule",
        assets=ASSETS,
        catalog=load_catalog(),
        repository=store.repository,
    )
    assert m018_result.ok, m018_result.summary()
    selection_result = verify(
        store,
        selection_name,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=load_selection_catalog(SCHEMA / "rules.ttl"),
        repository=store.repository,
    )
    assert selection_result.ok, selection_result.summary()


def test_the_windows_are_chronological_not_alphabetical() -> None:
    assert list(FINAL_WINDOWS) == ["P1", "H1", "P3", "H2", "P2", "H3"]
    assert FINAL_WINDOWS["P3"][0] < FINAL_WINDOWS["P2"][0]
