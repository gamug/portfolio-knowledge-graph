"""``projection.boundary``: the expectations run over synthetic rows (T-163, ``PLAN.md`` Work item 16).

T-164 widens this to a passing and a failing case per check kind; here each behaviour T-163 names
(source first, stop, quarantine, cascade, late or lost, skipped by design, pending) has one test.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from projection.boundary import (
    BoundaryError,
    check_source,
    validate,
)
from projection.expectations import (
    ViewExpectation,
    load_expectations,
    load_source,
    parse_view_expectation,
)


class _Db:
    """The two things ``check_source`` asks of ``portfolio_common.db.Database``."""

    def __init__(self, version: int, cycle_types: tuple[str, ...] = ()) -> None:
        self.schema_version = version
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("CREATE TABLE v_cycle_run (run_id INTEGER, cycle_type TEXT)")
        self._conn.executemany(
            "INSERT INTO v_cycle_run VALUES (?, ?)", list(enumerate(cycle_types, 1))
        )

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)


@pytest.fixture(scope="module")
def shipped() -> dict[str, ViewExpectation]:
    return load_expectations()


def snapshot(i: int, score_type: str = "TECHNICAL", **over: Any) -> dict[str, Any]:
    row = {
        "id": i,
        "ticker": f"T{i}",
        "asset_id": i,
        "score_type": score_type,
        "event_time": "2026-10-01",
        "available_at": "2026-10-01",
        "computed_at": "2026-10-01T06:00:00+00:00",
        "raw_value": 1.0,
        "normalized_score": 50.0,
        "run_kind": "cycle_run",
        "run_id": 1,
    }
    return row | over


def view(**fields: Any) -> ViewExpectation:
    base: dict[str, Any] = {
        "view": "v_weight_scheme",
        "keys": [["cycle_run_id"]],
        "cap": 0,
    }
    return parse_view_expectation("v_weight_scheme", base | fields)


def scheme(run: int, **over: Any) -> dict[str, Any]:
    return {"cycle_run_id": run, "top_n": 10} | over


# --- the source check --------------------------------------------------------------------------


def test_source_check_passes_a_current_database_without_replay() -> None:
    assert check_source(_Db(9, ("SELECTION", "MONITORING")), load_source()) == []


def test_source_check_names_a_stale_schema_and_a_replay_run() -> None:
    failures = check_source(_Db(8, ("SELECTION", "REPLAY", "REPLAY")), load_source())
    assert [(f.view, f.check) for f in failures] == [
        ("source", "schema_version"),
        ("v_cycle_run", "forbidden_cycle_type"),
    ]
    assert "2 run(s) of type REPLAY" in failures[1].detail


def test_a_source_failure_stops_before_any_row_is_read(
    shipped: dict[str, ViewExpectation],
) -> None:
    failures = check_source(_Db(8), load_source())
    with pytest.raises(BoundaryError) as stop:
        validate({}, shipped, source_failures=failures)
    assert stop.value.report.stop_reasons == ["the source database fails its check"]
    assert "below the floor 9" in str(stop.value)


# --- the shipped expectations over clean rows --------------------------------------------------


def test_clean_score_rows_pass_and_pending_guards_are_listed(
    shipped: dict[str, ViewExpectation],
) -> None:
    rows = {"v_score_snapshot": [snapshot(1), snapshot(2, "VALORIZATION")]}
    only = {"v_score_snapshot": shipped["v_score_snapshot"]}
    result = validate(rows, only)
    assert result.rows["v_score_snapshot"] == rows["v_score_snapshot"]
    assert not result.report.stopped
    assert any(i.startswith("v_score_snapshot.forensic_flags_json") for i in result.report.inactive)


def test_a_pending_view_is_listed_and_not_read(
    shipped: dict[str, ViewExpectation],
) -> None:
    result = validate({}, {"v_cycle_ranking_component": shipped["v_cycle_ranking_component"]})
    assert result.rows == {}
    assert result.report.inactive == [
        "v_cycle_ranking_component: view not pinned yet "
        + "(not pinned yet: upstream T-144 adds it, projected by T-155)"
    ]


# --- aggregate failures stop the run -----------------------------------------------------------


def test_a_cohort_whose_mean_drifted_stops_and_names_the_group(
    shipped: dict[str, ViewExpectation],
) -> None:
    rows = [snapshot(i, normalized_score=0.5) for i in range(1, 4)]  # moved to [0, 1]
    with pytest.raises(BoundaryError) as stop:
        validate(
            {"v_score_snapshot": rows},
            {"v_score_snapshot": shipped["v_score_snapshot"]},
        )
    [failure] = stop.value.report.aggregate_failures
    assert (failure.view, failure.check, failure.column) == (
        "v_score_snapshot",
        "group_mean",
        "normalized_score",
    )
    assert failure.group == ("cycle_run", 1, "TECHNICAL")


def test_row_count_and_null_rate_have_no_row_to_drop() -> None:
    exp = view(row_count={"min": 2}, null_rate=[{"column": "cycle_run_id", "max": 0}])
    with pytest.raises(BoundaryError) as stop:
        validate(
            {"v_weight_scheme": [scheme(1, cycle_run_id=None)]},
            {"v_weight_scheme": exp},
        )
    assert {f.check for f in stop.value.report.aggregate_failures} == {
        "row_count",
        "null_rate",
    }


def test_an_all_null_column_that_gains_values_is_reported_with_its_task() -> None:
    exp = view(null_rate=[{"column": "top_n", "all_null": True, "until": "T-154"}])
    with pytest.raises(BoundaryError) as stop:
        validate({"v_weight_scheme": [scheme(1)]}, {"v_weight_scheme": exp})
    assert "until T-154" in stop.value.report.aggregate_failures[0].detail


def test_a_pinned_column_the_rows_lack_is_an_aggregate_failure() -> None:
    exp = view(types={"top_n": "integer"})
    with pytest.raises(BoundaryError) as stop:
        validate({"v_weight_scheme": [{"cycle_run_id": 1}]}, {"v_weight_scheme": exp})
    assert stop.value.report.aggregate_failures[0].check == "missing_column"


def test_an_aggregate_stop_still_reports_the_row_failures_of_the_same_pass() -> None:
    exp = view(row_count={"min": 3}, ranges=[{"column": "top_n", "min": 1}])
    with pytest.raises(BoundaryError) as stop:
        validate({"v_weight_scheme": [full(1), full(2, top_n=0)]}, {"v_weight_scheme": exp})
    report = stop.value.report
    assert [f.check for f in report.aggregate_failures] == ["row_count"]
    assert [(f.check, f.key) for f in report.row_failures] == [("range", (2,))]
    assert report.quarantined == []
    assert "row (not quarantined, run stopped): v_weight_scheme.top_n row (2,)" in str(stop.value)


# --- row-level failures -------------------------------------------------------------------------


def lenient(exp_fields: dict[str, Any]) -> ViewExpectation:
    """A view that may lose every row, so the quarantine itself can be looked at."""
    return view(cap=1, cap_reason="test", **exp_fields)


def full(run: int, **over: Any) -> dict[str, Any]:
    return {
        "cycle_run_id": run,
        "cycle_type": "SELECTION",
        "cycle_date": "2026-10-01",
        "scheme_id": "s",
        "weights_json": "{}",
        "top_n": 10,
        "max_name_weight": 0.1,
        "max_sector_weight": 0.3,
        "soft_veto_penalty": 0.1,
    } | over


def test_a_failing_row_is_quarantined_and_named_by_view_column_and_key() -> None:
    exp = lenient({"ranges": [{"column": "top_n", "min": 1}]})
    result = validate({"v_weight_scheme": [full(1), full(2, top_n=0)]}, {"v_weight_scheme": exp})
    assert [r["cycle_run_id"] for r in result.rows["v_weight_scheme"]] == [1]
    [failure] = result.report.quarantined
    assert str(failure).startswith("v_weight_scheme.top_n row (2,): range:")


def test_the_default_cap_of_zero_stops_on_the_first_quarantined_row() -> None:
    exp = view(ranges=[{"column": "top_n", "min": 1}])
    with pytest.raises(BoundaryError) as stop:
        validate({"v_weight_scheme": [full(1), full(2, top_n=0)]}, {"v_weight_scheme": exp})
    assert "1/2 rows quarantined, over the cap 0" in stop.value.report.stop_reasons[0]


def test_a_share_at_the_cap_passes_and_above_it_stops() -> None:
    exp = view(cap=0.5, cap_reason="test", ranges=[{"column": "top_n", "min": 1}])
    ok = [full(1), full(2, top_n=0)]
    assert (
        len(validate({"v_weight_scheme": ok}, {"v_weight_scheme": exp}).rows["v_weight_scheme"])
        == 1
    )
    with pytest.raises(BoundaryError):
        validate({"v_weight_scheme": [full(1, top_n=0), *ok]}, {"v_weight_scheme": exp})


def test_a_duplicate_natural_key_quarantines_every_copy() -> None:
    result = validate({"v_weight_scheme": [full(1), full(1)]}, {"v_weight_scheme": lenient({})})
    assert result.rows["v_weight_scheme"] == []
    assert {f.check for f in result.report.quarantined} == {"unique"}


def test_type_and_format_failures_quarantine_the_row() -> None:
    exp = lenient({"types": {"top_n": "integer"}, "formats": {"cycle_date": "utc_timestamp"}})
    ok = "2026-10-01T06:00:00Z"
    rows = [
        full(1, top_n=True, cycle_date=ok),
        full(2, cycle_date="2026-10-01T06:00:00+02:00"),
        full(3, cycle_date=ok),
    ]
    result = validate({"v_weight_scheme": rows}, {"v_weight_scheme": exp})
    assert [r["cycle_run_id"] for r in result.rows["v_weight_scheme"]] == [3]
    assert {f.check for f in result.report.quarantined} == {"type", "format"}


# --- the D2 look-ahead pair and rows skipped by design -----------------------------------------


def test_a_fundamental_row_available_before_its_event_is_quarantined(
    shipped: dict[str, ViewExpectation],
) -> None:
    only = {"v_score_snapshot": shipped["v_score_snapshot"]}
    early = snapshot(1, "FUNDAMENTAL", event_time="2026-09-30", available_at="2026-09-30")
    with pytest.raises(BoundaryError) as stop:
        validate(
            {
                "v_score_snapshot": [
                    early,
                    snapshot(2, "FUNDAMENTAL", available_at="2026-10-02"),
                ]
            },
            only,
        )
    assert "ordered_pair" in str(stop.value)


def test_a_cycle_lane_null_available_at_is_counted_not_failed(
    shipped: dict[str, ViewExpectation],
) -> None:
    only = {"v_score_snapshot": shipped["v_score_snapshot"]}
    rows = [snapshot(1, available_at=None), snapshot(2, available_at=None)]
    result = validate({"v_score_snapshot": rows}, only)
    assert len(result.rows["v_score_snapshot"]) == 2
    assert result.report.skipped_by_design == {
        ("v_score_snapshot", "available_at is NULL until upstream T-144"): 2
    }


# --- the cascade --------------------------------------------------------------------------------


def test_a_failing_component_takes_its_scheme_and_that_runs_rankings(
    shipped: dict[str, ViewExpectation],
) -> None:
    exps = {
        "v_weight_scheme": shipped["v_weight_scheme"],
        "v_weight_component": parse_view_expectation(
            "v_weight_component",
            {
                "view": "v_weight_component",
                "cap": 1,
                "cap_reason": "test",
                "keys": [["cycle_run_id", "score_type"]],
                "ranges": [{"column": "weight", "min": 0, "max": 1}],
            },
        ),
        "v_cycle_ranking": parse_view_expectation(
            "v_cycle_ranking",
            {"view": "v_cycle_ranking", "cap": 1, "cap_reason": "test"},
        ),
    }
    exps["v_weight_scheme"] = parse_view_expectation(
        "v_weight_scheme", {"view": "v_weight_scheme", "cap": 1, "cap_reason": "test"}
    )
    rows = {
        "v_weight_scheme": [full(1), full(2)],
        "v_weight_component": [
            {"cycle_run_id": 1, "score_type": "TECHNICAL", "weight": 0.5},
            {
                "cycle_run_id": 1,
                "score_type": "SECTOR",
                "weight": 7.0,
            },  # the failing row
            {"cycle_run_id": 2, "score_type": "TECHNICAL", "weight": 0.5},
        ],
        "v_cycle_ranking": [
            {"cycle_run_id": 1, "asset_id": 1},
            {"cycle_run_id": 2, "asset_id": 1},
        ],
    }
    result = validate(rows, exps)
    assert [r["cycle_run_id"] for r in result.rows["v_weight_scheme"]] == [2]
    assert [r["cycle_run_id"] for r in result.rows["v_weight_component"]] == [2]
    assert [r["cycle_run_id"] for r in result.rows["v_cycle_ranking"]] == [2]
    cascaded = [f for f in result.report.quarantined if f.check == "cascade"]
    assert {f.view for f in cascaded} == {
        "v_weight_scheme",
        "v_cycle_ranking",
        "v_weight_component",
    }
    assert all(f.cascaded_from for f in cascaded)


def test_each_cascaded_row_counts_against_its_own_views_cap() -> None:
    components = parse_view_expectation(
        "v_weight_component",
        {
            "view": "v_weight_component",
            "cap": 1,
            "cap_reason": "test",
            "ranges": [{"column": "weight", "min": 0, "max": 1}],
        },
    )
    schemes = view()  # cap 0: the scheme the component takes is over its own cap
    rows = {
        "v_weight_scheme": [full(1)],
        "v_weight_component": [{"cycle_run_id": 1, "score_type": "SECTOR", "weight": 7.0}],
    }
    with pytest.raises(BoundaryError) as stop:
        validate(rows, {"v_weight_scheme": schemes, "v_weight_component": components})
    assert [r.split(":")[0] for r in stop.value.report.stop_reasons] == ["v_weight_scheme"]


# --- late or lost -------------------------------------------------------------------------------


def snapshot_view(**fields: Any) -> ViewExpectation:
    return parse_view_expectation(
        "v_score_snapshot",
        {
            "view": "v_score_snapshot",
            "cap": 1,
            "cap_reason": "test",
            "keys": [["id"]],
            "ranges": [{"column": "normalized_score", "min": 0, "max": 100}],
        }
        | fields,
    )


def test_a_row_for_an_ingestion_dated_graph_is_late_and_its_key_persisted(
    tmp_path: Path,
) -> None:
    rows = [snapshot(1), snapshot(2, "VALORIZATION", normalized_score=101.0)]
    path = tmp_path / "late.json"
    result = validate(
        {"v_score_snapshot": rows},
        {"v_score_snapshot": snapshot_view()},
        late_keys_path=path,
    )
    assert [f.key for f in result.report.late] == [(2,)]
    assert result.report.lost == []
    assert json.loads(path.read_text()) == {"v_score_snapshot": [[2]]}


def test_a_fundamental_row_and_any_other_view_is_lost(tmp_path: Path) -> None:
    path = tmp_path / "late.json"
    rows = [snapshot(1, "FUNDAMENTAL", normalized_score=101.0, available_at="2026-10-02")]
    result = validate(
        {"v_score_snapshot": rows},
        {"v_score_snapshot": snapshot_view()},
        late_keys_path=path,
    )
    assert [f.key for f in result.report.lost] == [(1,)]
    assert result.report.late == []
    assert json.loads(path.read_text()) == {}
    other = validate(
        {"v_weight_scheme": [full(1, top_n=0)]},
        {"v_weight_scheme": lenient({"ranges": [{"column": "top_n", "min": 1}]})},
    )
    assert len(other.report.lost) == 1
