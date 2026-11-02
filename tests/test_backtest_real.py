"""The m018 projector over a real completed backtest database (T-207, opt-in).

Run with ``-m integration`` and ``BACKTEST_DB=<path to rule_P1.db, rule_P2.db or rule_P3.db>``
(exported). The file is opened read-only. It checks the handoff §4 row counts for the database's
window and that the projection produces one individual per row except the reported skips. The
universe database and ``schema/rules.ttl`` are read the way the CLI reads them; if the universe
file is absent the test skips rather than guessing an asset set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from etl import config
from projection.backtest import VIEWS, load_guard_catalog, project, read_view, universe_assets
from projection.boundary import check_backtest_source, validate
from projection.expectations import load_expectations, load_source
from projection.source import FinancialSource

ENV_VAR = "BACKTEST_DB"

EXPECTED = {
    "P1": {
        "v_book": 3,
        "v_book_rebalance": 30,
        "v_guard_alert": 734,
        "v_guard_action": 1083,
        "v_book_weight_daily": 15615,
        "v_book_daily_performance": 588,
        "v_portfolio_period_summary": 3,
        "v_backtest_test": 6,
    },
    "P3": {
        "v_book": 3,
        "v_book_rebalance": 30,
        "v_guard_alert": 362,
        "v_guard_action": 416,
        "v_book_weight_daily": 18025,
        "v_book_daily_performance": 576,
        "v_portfolio_period_summary": 3,
        "v_backtest_test": 6,
    },
    "P2": {
        "v_book": 3,
        "v_book_rebalance": 24,
        "v_guard_alert": 424,
        "v_guard_action": 560,
        "v_book_weight_daily": 15641,
        "v_book_daily_performance": 450,
        "v_portfolio_period_summary": 9,
        "v_backtest_test": 18,
    },
}


def _database() -> Path:
    value = os.environ.get(ENV_VAR)
    if not value:
        pytest.skip(f"{ENV_VAR} is not set")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{ENV_VAR}={value} is not a file")
    return path


@pytest.mark.integration
def test_the_real_database_has_the_handoff_counts_and_projects_one_per_row() -> None:
    path = _database()
    universe = config.universe_db_path()
    if not universe.is_file():
        pytest.skip(f"SQL_UNIVERSE_DB={universe} is not a file")
    source = FinancialSource.open(path)
    try:
        books = read_view(source, "v_book")
        window = str(books[0]["window_id"])
        rows = {view: read_view(source, view) for view in VIEWS}
        source_failures = check_backtest_source(source.schema_version, books, load_source())
    finally:
        source.close()
    assert source_failures == []
    assert {row["window_id"] for row in books} == {window}
    assert {view: len(rows[view]) for view in VIEWS} == EXPECTED[window]

    result = validate(
        rows,
        {view: load_expectations()[view] for view in VIEWS},
        source_failures=source_failures,
    )
    assert not result.report.stopped
    projection = project(
        result.rows,
        universe_assets(universe),
        load_guard_catalog(config.schema_dir() / "rules.ttl"),
    )
    total_rows = sum(len(rows[view]) for view in VIEWS)
    assert sum(projection.individuals.values()) == total_rows
    assert sum(projection.skipped.values()) == 0
    print(f"\n{path.name}: window {window}, {total_rows} rows, {len(projection.graphs)} graph(s)")
    print(f"  individuals: {dict(projection.individuals)}")
    print(f"  asset links omitted: {dict(projection.asset_unlinked)}")
    print(f"  CASH rows: {dict(projection.cash_rows)}")


@pytest.mark.integration
def test_the_three_real_databases_have_disjoint_window_qualified_iris() -> None:
    path = _database()
    universe = config.universe_db_path()
    if not universe.is_file():
        pytest.skip(f"SQL_UNIVERSE_DB={universe} is not a file")
    siblings = [path.parent / name for name in ("rule_P1.db", "rule_P2.db", "rule_P3.db")]
    if not all(sibling.is_file() for sibling in siblings):
        pytest.skip("the three rule_P1/P2/P3 databases are not beside BACKTEST_DB")
    assets = universe_assets(universe)
    catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
    iris: set[object] = set()
    for sibling in siblings:
        source = FinancialSource.open(sibling)
        try:
            rows = {view: read_view(source, view) for view in VIEWS}
        finally:
            source.close()
        projection = project(rows, assets, catalog)
        for graph in projection.graphs.values():
            iris.update(subject for subject, _, _ in graph.triples)
    assert len(iris) == 18_062 + 17_129 + 19_421
    assert len({graph for graph in iris if str(graph).endswith("_CASH")}) == 588 + 450 + 576
