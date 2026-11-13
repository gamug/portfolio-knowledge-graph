"""Strict detail-file parsing and the price mask (Work item 46, T-853/T-858)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from projection.veto_events import (
    KG,
    DetailError,
    DetailFile,
    EventContext,
    SelectionIndex,
    build_detail_batch,
    parse_detail_file,
)

DECISION: dict[str, Any] = {
    "kind": "decision",
    "date": "2022-01-03",
    "filter": True,
    "filter_decision": "2021-12-31",
    "core_weight_in_force": 0.5,
    "scale": 1.0,
    "blocked": [],
    "candidate_ids": [1],
    "optimizer_target": {"1": 0.1},
    "target": {"1": 0.1},
    "retention": {
        "enabled": True,
        "max_decisions": 3,
        "pool_size": 1,
        "pool_ids": [1],
        "held_outside": [],
        "retained": [],
        "rejected": [],
        "rejections": {},
        "counter_dropped": [],
        "kept": [],
        "kept_weight": 0,
        "candidate_size": 1,
    },
}


def _write(tmp_path: Path, lines: list[dict[str, Any]]) -> Path:
    path = tmp_path / "detail.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def test_a_valid_detail_file_parses(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            DECISION,
            {"kind": "blocked", "date": "2022-02-01", "asset_id": 1, "stop_distance_pct": -12.5},
            {"kind": "reentry", "date": "2022-02-01", "asset_id": 1, "stop_distance_pct": 1.2},
        ],
    )
    detail = parse_detail_file(path)
    assert detail.lines == 3
    assert detail.decisions[0]["date"] == "2022-01-03"
    assert detail.blocked[0]["stop_distance_pct"] == -12.5
    assert detail.reentry[0]["asset_id"] == 1


def test_an_unknown_kind_is_refused_with_its_line(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"kind": "surprise", "date": "2022-01-03"}])
    with pytest.raises(DetailError, match=r":1: unknown kind"):
        parse_detail_file(path)


def test_an_unknown_field_is_refused_with_its_line(tmp_path: Path) -> None:
    line = dict(DECISION, extra_field=1)
    path = _write(tmp_path, [line])
    with pytest.raises(DetailError, match=r":1: decision: unknown field"):
        parse_detail_file(path)


def test_a_duplicate_unique_key_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, [DECISION, DECISION])
    with pytest.raises(DetailError, match=r":2: decision: duplicate"):
        parse_detail_file(path)


def test_a_null_in_a_required_field_is_refused(tmp_path: Path) -> None:
    line = dict(DECISION, scale=None)
    path = _write(tmp_path, [line])
    with pytest.raises(DetailError, match="scale must be a number"):
        parse_detail_file(path)


@pytest.mark.parametrize("field", ["close", "level", "stop", "stop_level"])
def test_a_price_field_is_refused(tmp_path: Path, field: str) -> None:
    line = dict(DECISION, **{field: 12.5})
    path = _write(tmp_path, [line])
    with pytest.raises(DetailError, match=f"{field}: a price field"):
        parse_detail_file(path)


def test_a_nested_price_field_is_refused(tmp_path: Path) -> None:
    line = dict(DECISION)
    line["target"] = {"1": 0.1, "level": 1}
    path = _write(tmp_path, [line])
    with pytest.raises(DetailError, match="level: a price field"):
        parse_detail_file(path)


def test_stop_distance_pct_is_accepted(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [{"kind": "blocked", "date": "2022-02-01", "asset_id": 1, "stop_distance_pct": -12.5}],
    )
    assert parse_detail_file(path).blocked


def test_without_hierarchy_retention_lines_are_loaded_without_decision_events(
    tmp_path: Path,
) -> None:
    line = {
        "kind": "retention_decision",
        "date": "2022-02-01",
        "arm": "TOPN_MV_NOGUARD",
        "pool_size": 1,
        "pool_ids": [1],
        "candidate_ids": [1, 2],
        "candidate_size": 2,
        "held_outside": [2],
        "retained": [{"asset_id": 2, "counter": 1}],
        "rejected": [],
        "rejections": {},
        "counter_dropped": [],
        "kept": [{"asset_id": 2, "weight": 0.1}],
        "kept_weight": 0.1,
        "target": {"2": 0.1},
    }
    detail = DetailFile(
        tmp_path / "detail.jsonl",
        decisions=(),
        stops=(),
        replacement_bought=(),
        replacement_checks=(),
        replacement_stopped=(),
        blocked=(),
        reentry=(),
        retention_decisions=(line,),
    )
    selection = SelectionIndex(
        {"2022-02-01": 7},
        {"2022-02-01": frozenset({1})},
        lambda date, asset: KG[f"Snap_final_P1_{date}_{asset}"],
        lambda date: KG[f"Cycle_final_P1_{date}"],
    )
    context = EventContext(
        label="final",
        window="P1",
        configuration="SYSTEM_WITHOUT_HIERARCHY",
        graph="urn:graph:derived:backtest:final:P1:system_without_hierarchy",
        book_iri=KG.Book_final_P1_system_without_hierarchy,
        book_code="TOPN_MV_NOGUARD",
        assets={"AAA": None},
        asset_tickers={2: "AAA"},
        alerts={},
        selection=selection,
        rebalance_by_date={},
    )
    batch = build_detail_batch(detail, context)
    assert "DecisionEvent" not in batch.individuals
    assert batch.individuals["RetentionDecision"] == 1
    assert batch.individuals["RetentionHold"] == 1
    assert not any(value == KG.DecisionEvent for _, _, value in batch.triples)


def test_a_stop_without_its_loaded_alert_is_a_hard_error(tmp_path: Path) -> None:
    decision = dict(DECISION)
    detail = DetailFile(
        tmp_path / "detail.jsonl",
        decisions=(decision,),
        stops=({"date": "2022-01-03", "asset_id": 1},),
        replacement_bought=(),
        replacement_checks=(),
        replacement_stopped=(),
        blocked=(),
        reentry=(),
        retention_decisions=(),
    )
    context = EventContext(
        label="final",
        window="P1",
        configuration="SYSTEM_WITH_HIERARCHY",
        graph="urn:graph:derived:backtest:final:P1:system_with_hierarchy",
        book_iri=KG.Book_final_P1_system_with_hierarchy,
        book_code="TOPN_MV_GUARD_NO_NLP",
        assets={"AAA": None},
        asset_tickers={1: "AAA"},
        alerts={},
        selection=SelectionIndex(
            {"2022-01-03": 1},
            {"2022-01-03": frozenset({1})},
            lambda date, asset: KG.Snap,
            lambda date: KG.Cycle,
        ),
        rebalance_by_date={"2022-01-03": KG.Rebalance_final_P1_system_with_hierarchy_20220103},
    )
    with pytest.raises(DetailError, match="matches no loaded L1_BP_STOP alert"):
        build_detail_batch(detail, context)
