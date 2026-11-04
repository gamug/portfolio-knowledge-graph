"""The selection-side projector over a real completed backtest database (Work item 26, opt-in).

Run with ``-m integration`` and ``BACKTEST_DB=<path to rule_P1.db, rule_P2.db or rule_P3.db>``.
The file is opened read-only. It checks the Step 0 row counts and that every selection row becomes
one individual, plus the measured unlinked-ticker counts. The universe database and
``schema/rules.ttl`` are read the way the CLI reads them; if the universe file is absent the test
skips rather than guessing an asset set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from etl import config
from projection.backtest import (
    SELECTION_VIEWS,
    load_selection_catalog,
    run_selection,
    universe_assets,
)
from projection.source import FinancialSource

ENV_VAR = "BACKTEST_DB"

EXPECTED = {
    "P1": {
        "v_cycle_run": 22,
        "v_weight_scheme": 22,
        "v_weight_component": 66,
        "v_cycle_ranking": 10_484,
        "v_cycle_ranking_component": 30_664,
        "v_veto": 1_442,
        "individuals": {
            "SelectionCycle": 22,
            "AttractivenessWeightScheme": 22,
            "WeightComponent": 30_730,
            "AttractivenessSnapshot": 10_484,
            "Veto": 1_442,
        },
        "unlinked": {"v_cycle_ranking": 34, "v_veto": 9},
    },
    "P2": {
        "v_cycle_run": 20,
        "v_weight_scheme": 20,
        "v_weight_component": 60,
        "v_cycle_ranking": 10_060,
        "v_cycle_ranking_component": 29_745,
        "v_veto": 1_354,
        "individuals": {
            "SelectionCycle": 20,
            "AttractivenessWeightScheme": 20,
            "WeightComponent": 29_805,
            "AttractivenessSnapshot": 10_060,
            "Veto": 1_354,
        },
        "unlinked": {"v_veto": 2},
    },
    "P3": {
        "v_cycle_run": 22,
        "v_weight_scheme": 22,
        "v_weight_component": 66,
        "v_cycle_ranking": 11_066,
        "v_cycle_ranking_component": 32_568,
        "v_veto": 1_696,
        "individuals": {
            "SelectionCycle": 22,
            "AttractivenessWeightScheme": 22,
            "WeightComponent": 32_634,
            "AttractivenessSnapshot": 11_066,
            "Veto": 1_696,
        },
        "unlinked": {"v_cycle_ranking": 2, "v_veto": 3},
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
def test_the_real_database_projects_every_selection_row_once() -> None:
    path = _database()
    universe = config.universe_db_path()
    if not universe.is_file():
        pytest.skip(f"SQL_UNIVERSE_DB={universe} is not a file")
    source = FinancialSource.open(path)
    try:
        window = str(source.execute("SELECT window_id FROM v_book LIMIT 1").fetchone()[0])
        result = run_selection(
            source,
            universe_assets(universe),
            load_selection_catalog(config.schema_dir() / "rules.ttl"),
            "rule",
        )
    finally:
        source.close()
    expected = EXPECTED[window]
    assert result.report.stopped is False
    assert result.rows == {view: expected[view] for view in SELECTION_VIEWS}
    assert result.individuals == expected["individuals"]
    assert {key: value for key, value in result.asset_unlinked.items() if value} == expected[
        "unlinked"
    ]
    assert result.skipped == {}
    assert result.checked == [f"urn:graph:derived:backtest:selection:rule:{window}:1"]
    assert result.written == {}
    print(
        f"\n{path.name}: window {window}, {sum(result.rows.values())} rows, {len(result.graphs)} graph(s)"
    )
    print(f"  individuals: {dict(result.individuals)}")
    print(f"  asset links omitted: {dict(result.asset_unlinked)}")
