"""Manifest control_counts against Reviewer A's pilot and the comparison rules (T-867/T-868)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixtures.backtest_rows import AssetInfo

from projection.backtest import load_guard_catalog, project_source
from projection.control_counts import (
    GROUP_5,
    ControlCountError,
    _check_identities,
    _compare_value,
    compare_control_counts,
    compute_control_counts,
)
from projection.source import FinancialSource
from projection.veto_events import (
    parse_detail_file,
    read_asset_tickers,
    read_rankings,
    selection_index,
)

PILOT = Path("/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/piloto_H1C_P1")
A_FILE = Path(
    "/workspaces/thesis/knoledge graph/2026-11-13_llaves_control_counts/"
    "18b_A_control_counts_piloto_P1.json"
)


def _pilot_control() -> dict:
    if not PILOT.is_dir() or not A_FILE.is_file():
        pytest.skip("the pilot or Reviewer A's control-count file is absent")
    source = FinancialSource.open(PILOT / "H1C-B5-P1.db")
    try:
        tickers = read_asset_tickers(source)
        assets = {ticker: AssetInfo(ticker, None) for ticker in tickers.values()}
        detail = parse_detail_file(PILOT / "H1C-B5-P1.cartera_v1_3.kg.jsonl")
        rankings = read_rankings(PILOT / "H1C-B5-P1.rankings.json")
        selection = selection_index(
            source,
            "final",
            "P1",
            "SYSTEM_WITH_HIERARCHY",
            [str(line["date"]) for line in detail.decisions],
        )
        sh = project_source(
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
            rankings_by_date=rankings,
        )
        mb = project_source(
            source,
            assets,
            load_guard_catalog("schema/rules.ttl"),
            "final",
            configuration="MARKOWITZ_BASE",
            window="P1",
            book_code="MARKOWITZ_BASE",
            book_id=1,
        )
    finally:
        source.close()
    assert sh.projection.detail is not None
    return {
        "SYSTEM_WITH_HIERARCHY": compute_control_counts(
            "SYSTEM_WITH_HIERARCHY",
            "P1",
            rows=sh.rows,
            detail=detail,
            memory_rows=sh.projection.detail.rows,
            rankings=rankings,
            files={"scales_file": PILOT / "H1C-B5-P1.scales.json"},
        ),
        "MARKOWITZ_BASE": compute_control_counts(
            "MARKOWITZ_BASE",
            "P1",
            rows=mb.rows,
            detail=None,
            memory_rows={},
            rankings=None,
            files={},
        ),
    }


@pytest.mark.integration
def test_the_pilot_counts_match_reviewer_a_exactly() -> None:
    expected = json.loads(A_FILE.read_text(encoding="utf-8"))["control_counts"]
    computed = _pilot_control()
    # A's pilot JSON omits these two group-5 keys; both files are null, so they are null.
    for key in GROUP_5:
        expected["SYSTEM_WITH_HIERARCHY"]["P1"].setdefault(key, None)
    compare_control_counts(
        expected, "SYSTEM_WITH_HIERARCHY", "P1", computed["SYSTEM_WITH_HIERARCHY"], final=True
    )
    compare_control_counts(expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True)


def _base() -> tuple[dict, dict]:
    expected = json.loads(A_FILE.read_text(encoding="utf-8"))["control_counts"]
    computed = {
        "MARKOWITZ_BASE": {
            "alerts_by_rule": {
                rule: 0
                for rule in (
                    "L0_CARTERA_ACTIVATION",
                    "L0_CARTERA_SCALE_CHANGE",
                    "L0_CARTERA_RECOVERY",
                    "L1_BP_STOP",
                    "L1_BP_STOP_BLOCKED",
                    "L1_BP_REENTRY",
                )
            },
            "actions_by_status": {"APPLIED": 0, "BLOCKED": 0},
            "rebalances": 10,
            "daily_rows": 196,
            "weight_daily_rows": 6663,
            "final_values": {
                "cumulative_return": -0.10553589345091785,
                "annualized_return": -0.1335894112850785,
                "annualized_vol": 0.14478292216370525,
                "max_drawdown": 0.1525258529798067,
                "total_turnover": 2.372145696423579,
            },
        }
    }
    return expected, computed


def test_a_changed_integer_fails() -> None:
    expected, computed = _base()
    expected["MARKOWITZ_BASE"]["P1"]["rebalances"] += 1
    with pytest.raises(ControlCountError, match="rebalances"):
        compare_control_counts(
            expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True
        )


def test_a_real_beyond_the_tolerance_fails() -> None:
    expected, computed = _base()
    expected["MARKOWITZ_BASE"]["P1"]["final_values"]["cumulative_return"] += 1e-9
    with pytest.raises(ControlCountError, match="cumulative_return"):
        compare_control_counts(
            expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True
        )


def test_a_missing_key_is_fatal_only_in_a_final_manifest() -> None:
    expected, computed = _base()
    del expected["MARKOWITZ_BASE"]["P1"]["rebalances"]
    with pytest.raises(ControlCountError, match="missing control count"):
        compare_control_counts(
            expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True
        )
    compare_control_counts(
        expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=False
    )


def test_an_unknown_key_fails() -> None:
    expected, computed = _base()
    expected["MARKOWITZ_BASE"]["P1"]["surprise"] = 1
    with pytest.raises(ControlCountError, match="unknown control count"):
        compare_control_counts(
            expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True
        )


def test_an_object_with_a_missing_subkey_fails() -> None:
    expected, computed = _base()
    del expected["MARKOWITZ_BASE"]["P1"]["alerts_by_rule"]["L1_BP_REENTRY"]
    with pytest.raises(ControlCountError, match="expected keys"):
        compare_control_counts(
            expected, "MARKOWITZ_BASE", "P1", computed["MARKOWITZ_BASE"], final=True
        )


def test_a_broken_identity_fails() -> None:
    with pytest.raises(ControlCountError, match="identity fails"):
        _check_identities(
            "SYSTEM_WITH_HIERARCHY",
            "P1",
            {
                "memory_episodes": 10,
                "memory_released_price": 1,
                "memory_released_not_ranked": 0,
                "memory_open_at_end": 1,
            },
            source="manifest",
        )


def test_a_null_group5_value_does_not_hide_a_non_null_file() -> None:
    with pytest.raises(ControlCountError, match="manager_calls"):
        _compare_value("SYSTEM_WITH_HIERARCHY", "P1", "manager_calls", None, 1)


def test_decision_close_episodes_is_compared_like_the_other_counts() -> None:
    with pytest.raises(ControlCountError, match="decision_close_episodes"):
        _compare_value("SYSTEM_WITH_HIERARCHY", "P1", "decision_close_episodes", 1, 0)
