"""The reference/process projector over a real v18 database (T-357, opt-in).

Run with ``-m integration`` and ``REFERENCE_DB=<path to rule_P1.db, rule_P2.db, rule_P3.db or
financial.db>``. The file is opened read-only. The universe database is read the way the CLI reads
it; if it is absent the test skips rather than guessing an asset set.
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import RDF

from etl import config
from projection.backtest import universe_assets
from projection.reference import KG, VIEWS, Projection, project, read_view
from projection.source import FinancialSource

ENV_VAR = "REFERENCE_DB"


def _database() -> Path:
    value = os.environ.get(ENV_VAR)
    if not value:
        pytest.skip(f"{ENV_VAR} is not set")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{ENV_VAR}={value} is not a file")
    return path


def _graph(projection: Projection, name: str) -> rdflib.Graph:
    graph = rdflib.Graph()
    for triple in projection.graphs[name].triples:
        graph.add(triple)
    return graph


@pytest.mark.integration
def test_the_real_database_projects_one_individual_per_row_and_links_safely() -> None:
    path = _database()
    universe = config.universe_db_path()
    if not universe.is_file():
        pytest.skip(f"SQL_UNIVERSE_DB={universe} is not a file")
    source = FinancialSource.open(path)
    try:
        rows = {view: read_view(source, view) for view in VIEWS}
    finally:
        source.close()

    assets = universe_assets(universe)
    projection = project(rows, assets, "rule", "2026-11-04")
    total_rows = sum(len(rows[view]) for view in VIEWS)
    assert sum(projection.individuals.values()) == total_rows
    assert sum(projection.asset_exact.values()) + sum(projection.asset_cik.values()) + sum(
        projection.asset_unlinked.values()
    ) == len(rows["v_ticker_history"])

    # The history and the catalog must agree on the latest symbol of every CIK line.
    by_cik: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows["v_ticker_history"]:
        by_cik[str(row["cik"])].append(row)
    for cik, group in by_cik.items():
        latest = max(group, key=lambda row: str(row["valid_from"]))
        assert str(latest["canonical_symbol"]) == str(latest["symbol"]), cik

    ticker_graphs = [
        graph
        for graph in projection.graphs
        if graph.startswith("urn:graph:derived:ticker-history:")
    ]
    assert len(ticker_graphs) == (1 if rows["v_ticker_history"] else 0)
    if ticker_graphs:
        graph = _graph(projection, ticker_graphs[0])
        assert len(list(graph.subjects(RDF.type, KG.TickerHistory))) == len(
            rows["v_ticker_history"]
        )
        if "FBHS" in assets:
            assert any(
                str(graph.value(subject, KG.tickerHistoryAsset))
                == "https://thesis.local/kg/portfolio#FBHS"
                for subject in graph.subjects(RDF.type, KG.TickerHistory)
                if str(graph.value(subject, KG.canonicalSymbol)) == "FBIN"
            )
        if "GPS" in assets:
            assert any(
                str(graph.value(subject, KG.tickerHistoryAsset))
                == "https://thesis.local/kg/portfolio#GPS"
                for subject in graph.subjects(RDF.type, KG.TickerHistory)
                if str(graph.value(subject, KG.canonicalSymbol)) == "GAP"
            )

    print(
        f"\n{path.name}: ticker {len(rows['v_ticker_history'])} rows, "
        f"run {len(rows['v_orchestrator_run'])}, step {len(rows['v_orchestrator_step'])}; "
        f"exact {projection.asset_exact['v_ticker_history']}, "
        f"by CIK {projection.asset_cik['v_ticker_history']}, "
        f"unlinked {projection.asset_unlinked['v_ticker_history']}"
    )
    print(f"  graphs: {sorted(projection.graphs)}")
