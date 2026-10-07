"""The boundary expectations load strictly and say what T-162 requires (``PLAN.md`` Work item 16).

The shipped files are the unit under test, so this stays hermetic: no database, no upstream
checkout. The loader's rejections are tried on synthetic dicts, one mutation each.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from projection.expectations import (
    EXPECTATIONS_DIR,
    ExpectationError,
    ViewExpectation,
    load_expectations,
    load_source,
    parse_view_expectation,
)
from projection.view_contract import VIEW_COLUMNS

CYCLE_LANES = ("VALORIZATION", "TECHNICAL", "SECTOR")


@pytest.fixture(scope="module")
def shipped() -> dict[str, ViewExpectation]:
    return load_expectations()


# --- the shipped files -------------------------------------------------------------------------


def test_every_pinned_view_has_a_file(shipped: dict[str, ViewExpectation]) -> None:
    assert set(VIEW_COLUMNS) <= set(shipped)
    assert {v for v in shipped if v not in VIEW_COLUMNS} == {"v_cycle_ranking_component"}
    assert shipped["v_cycle_ranking_component"].pending


def test_no_view_may_lose_rows_yet(shipped: dict[str, ViewExpectation]) -> None:
    """Every cap is the default 0; raising one needs a ``cap_reason``, so this lists the exceptions."""
    assert {v: e.cap for v, e in shipped.items() if e.cap} == {}


def test_the_source_check_is_the_documented_one() -> None:
    source = load_source()
    assert source.schema_version_floor == 9
    assert source.forbidden_cycle_types == ("REPLAY",)


def test_score_snapshot_carries_the_documented_rules(shipped: dict[str, ViewExpectation]) -> None:
    e = shipped["v_score_snapshot"]
    assert e.formats == {"computed_at": "utc_timestamp", "forensic_flags_json": "forensic_flags"}

    normalized = next(r for r in e.ranges if r.column == "normalized_score")
    assert (normalized.min, normalized.max) == (0, 100)
    sector = next(r for r in e.ranges if r.column == "raw_value")
    assert (sector.min, sector.max, sector.where) == (-100, 100, {"score_type": ("SECTOR",)})

    strict, cycle = e.ordered_pairs
    assert (strict.op, strict.where, strict.null) == (">", {"score_type": ("FUNDAMENTAL",)}, "fail")
    assert (cycle.op, cycle.where["score_type"], cycle.null) == ("=", CYCLE_LANES, "skip")
    assert cycle.until == "upstream T-144"

    (mean,) = e.group_means
    # run ids are reused across the four run tables (D7), so run_kind is part of the cohort
    assert (mean.target, mean.group_by) == (50, ("run_kind", "run_id", "score_type"))
    assert 0 < mean.tolerance < 50
    assert mean.where["score_type"] == CYCLE_LANES  # FUNDAMENTAL mixes cohorts (D17)


def test_the_fundamental_mean_runs_over_the_ranking_component(
    shipped: dict[str, ViewExpectation],
) -> None:
    (mean,) = shipped["v_cycle_ranking_component"].group_means
    assert mean.column == "component_value"
    assert mean.group_by == ("cycle_run_id", "score_type")
    assert "FUNDAMENTAL" in mean.where["score_type"]
    assert "SEMANTIC" not in mean.where["score_type"]  # not on 0-100


def test_the_documented_all_null_columns_expire_with_their_task(
    shipped: dict[str, ViewExpectation],
) -> None:
    nulls = {n.column: n for n in shipped["v_shared_executive_edge"].null_rates}
    assert [(nulls[c].max, nulls[c].until) for c in ("first_seen", "last_seen")] == [
        (None, "T-154")
    ] * 2


def test_ranking_and_scheme_ranges(shipped: dict[str, ViewExpectation]) -> None:
    ranking = {r.column: (r.min, r.max) for r in shipped["v_cycle_ranking"].ranges}
    assert ranking == {"rank": (1, None), "blended_score": (None, 100), "target_weight": (0, 1)}
    scheme = {r.column: (r.min, r.max) for r in shipped["v_weight_scheme"].ranges}
    assert scheme["max_name_weight"] == scheme["max_sector_weight"] == (0, 1)
    assert scheme["soft_veto_penalty"] == (0, None)  # a penalty is never negative


def test_a_natural_key_is_never_nullable(shipped: dict[str, ViewExpectation]) -> None:
    for view, e in shipped.items():
        required = {n.column for n in e.null_rates if n.max == 0}
        for key in e.keys:
            assert set(key) <= required, view


# --- the loader's rejections -------------------------------------------------------------------

VALID: dict[str, Any] = {
    "view": "v_weight_component",
    "keys": [["cycle_run_id", "score_type"]],
    "row_count": {"min": 1},
    "cap": 0,
    "types": {"weight": "number"},
    "null_rate": [{"column": "weight", "max": 0}],
    "ranges": [{"column": "weight", "min": 0, "max": 1}],
    "formats": {"weight": "utc_timestamp"},
    "ordered_pairs": [{"left": "weight", "op": ">", "right": "weight"}],
    "group_means": [
        {
            "column": "weight",
            "group_by": ["score_type"],
            "target": 50,
            "tolerance": 5,
            "where": {"score_type": ["TECHNICAL"]},
        }
    ],
}


def _mutated(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(VALID)
    for key, value in changes.items():
        if value is _DROP:
            del data[key]
        else:
            data[key] = value
    return data


_DROP = object()


def test_a_valid_file_parses() -> None:
    e = parse_view_expectation("v_weight_component", VALID)
    assert e.cap == 0 and e.row_count_min == 1 and e.keys == (("cycle_run_id", "score_type"),)


@pytest.mark.parametrize(
    ("data", "why"),
    [
        (_mutated(view="v_other"), "must equal the file name"),
        (_mutated(extra=1), "unknown key 'extra'"),
        (_mutated(cap=_DROP), "cap: is required"),
        (_mutated(cap=1.5), "cap: is required"),
        (_mutated(cap=True), "cap: is required"),
        (_mutated(cap=0.05), "cap_reason: is required"),
        (_mutated(cap=0.05, cap_reason="  "), "cap_reason: must be text"),
        (_mutated(cap_reason="a reason with no cap"), "belongs to a cap above 0"),
        (_mutated(keys=[["no_such_column"]]), "neither pinned nor pending"),
        (_mutated(keys=[[]]), "non-empty column lists"),
        (_mutated(row_count={"min": -1}), "non-negative integer"),
        (_mutated(types={"weight": "decimal"}), "unknown value 'decimal'"),
        (_mutated(types={"no_such_column": "number"}), "neither pinned nor pending"),
        (_mutated(null_rate=[{"column": "weight", "max": 2}]), "share between 0 and 1"),
        (_mutated(null_rate=[{"column": "weight", "all_null": True}]), "needs 'until'"),
        (
            _mutated(null_rate=[{"column": "weight", "max": 0, "all_null": True, "until": "T-1"}]),
            "exclusive",
        ),
        (_mutated(ranges=[{"column": "weight"}]), "needs 'min' or 'max'"),
        (_mutated(ranges=[{"column": "weight", "min": 2, "max": 1}]), "'min' is above 'max'"),
        (_mutated(ranges=[{"column": "weight", "min": "0"}]), "must be numbers"),
        (
            _mutated(ranges=[{"column": "weight", "min": 0, "where": {"score_type": []}}]),
            "non-empty list",
        ),
        (
            _mutated(ranges=[{"column": "weight", "min": 0, "where": {"nope": ["x"]}}]),
            "neither pinned nor pending",
        ),
        (_mutated(formats={"weight": "iso"}), "unknown value 'iso'"),
        (
            _mutated(ordered_pairs=[{"left": "weight", "op": "!=", "right": "weight"}]),
            "'op' must be one of",
        ),
        (
            _mutated(
                ordered_pairs=[{"left": "weight", "op": ">", "right": "weight", "null": "ignore"}]
            ),
            "'null' must be one of",
        ),
        (
            _mutated(
                ordered_pairs=[{"left": "weight", "op": ">", "right": "weight", "null": "skip"}]
            ),
            "needs 'until'",
        ),
        (
            _mutated(
                group_means=[{"column": "weight", "group_by": [], "target": 50, "tolerance": 5}]
            ),
            "'group_by'",
        ),
        (
            _mutated(
                group_means=[
                    {"column": "weight", "group_by": ["score_type"], "target": 50, "tolerance": 0}
                ]
            ),
            "positive",
        ),
        (_mutated(pending="not shipped"), "is stale"),
        (_mutated(pending_columns={"weight": "T-1"}), "is pinned now"),
        (_mutated(null_rate="all of them"), "must be a list of objects"),
        (_mutated(types={"weight": ["number"]}), "unknown value"),
        (_mutated(formats={"weight": [1]}), "unknown value"),
        (
            _mutated(ordered_pairs=[{"left": "weight", "op": [">"], "right": "weight"}]),
            "'op' must be one of",
        ),
        (
            _mutated(ordered_pairs=[{"left": "weight", "op": ">", "right": "weight", "null": [1]}]),
            "'null' must be one of",
        ),
    ],
)
def test_a_malformed_file_is_rejected(data: dict[str, Any], why: str) -> None:
    with pytest.raises(ExpectationError, match=why):
        parse_view_expectation("v_weight_component", data)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ExpectationError) as caught:
        parse_view_expectation("v_weight_component", _mutated(cap=2, types={"weight": "decimal"}))
    assert "cap:" in str(caught.value) and "types.weight" in str(caught.value)


def test_a_cap_above_zero_with_a_reason_is_accepted() -> None:
    e = parse_view_expectation(
        "v_weight_component", _mutated(cap=0.02, cap_reason="two stale runs")
    )
    assert (e.cap, e.cap_reason) == (0.02, "two stale runs")


def test_an_unshipped_view_must_say_so() -> None:
    soon = {"view": "v_soon", "cap": 0}
    with pytest.raises(ExpectationError, match="needs 'pending'"):
        parse_view_expectation("v_soon", soon)
    pending = {
        **soon,
        "pending": "upstream T-999",
        "pending_columns": {"x": "T-999"},
        "keys": [["x"]],
    }
    assert parse_view_expectation("v_soon", pending).pending == "upstream T-999"


def test_a_pending_column_is_usable_until_it_is_pinned() -> None:
    data = _mutated(pending_columns={"later": "T-999"}, types={"later": "string"})
    assert parse_view_expectation("v_weight_component", data).types == {"later": "string"}


# --- the directory loader ----------------------------------------------------------------------


def _directory(tmp_path: Path, drop: str | None = None) -> Path:
    for src in EXPECTATIONS_DIR.glob("*.json"):
        if src.stem != drop:
            (tmp_path / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_the_copied_directory_loads(tmp_path: Path) -> None:
    assert set(load_expectations(_directory(tmp_path))) >= set(VIEW_COLUMNS)


def test_a_pinned_view_without_a_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExpectationError, match=r"no expectation file.*v_sector"):
        load_expectations(_directory(tmp_path, drop="v_sector"))


def test_a_file_named_for_another_view_is_rejected(tmp_path: Path) -> None:
    directory = _directory(tmp_path)
    (directory / "v_sector.json").write_text(json.dumps({"view": "v_industry", "cap": 0}))
    with pytest.raises(ExpectationError, match="must equal the file name"):
        load_expectations(directory)


def test_invalid_json_and_non_objects_are_rejected(tmp_path: Path) -> None:
    directory = _directory(tmp_path)
    (directory / "v_sector.json").write_text("{not json")
    with pytest.raises(ExpectationError, match="not valid JSON"):
        load_expectations(directory)
    (directory / "v_sector.json").write_text("[]")
    with pytest.raises(ExpectationError, match="must be a JSON object"):
        load_expectations(directory)


@pytest.mark.parametrize(
    ("source", "why"),
    [
        ({"schema_version_floor": 0, "forbidden_cycle_types": ["REPLAY"]}, "schema_version_floor"),
        ({"schema_version_floor": 9, "forbidden_cycle_types": []}, "forbidden_cycle_types"),
        (
            {"schema_version_floor": 9, "forbidden_cycle_types": ["REPLAY"], "x": 1},
            "unknown key 'x'",
        ),
    ],
)
def test_a_malformed_source_file_is_rejected(
    tmp_path: Path, source: dict[str, Any], why: str
) -> None:
    (tmp_path / "_source.json").write_text(json.dumps(source))
    with pytest.raises(ExpectationError, match=why):
        load_source(tmp_path)


def test_a_duplicate_key_is_rejected(tmp_path: Path) -> None:
    """``json.loads`` would keep the second value silently."""
    directory = _directory(tmp_path)
    (directory / "v_sector.json").write_text('{"view": "v_sector", "cap": 0, "cap": 0.5}')
    with pytest.raises(ExpectationError, match="key 'cap' appears twice"):
        load_expectations(directory)


def test_a_missing_source_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExpectationError, match="file not found"):
        load_source(tmp_path)
