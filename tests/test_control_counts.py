"""Manifest control_counts against Reviewer A's pilot and the comparison rules (T-867/T-868)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixtures.backtest_rows import AssetInfo

from projection.backtest import load_guard_catalog, project_source
from projection.control_counts import (
    ACTION_STATUSES,
    ALERT_RULES,
    CASH_CAUSES,
    GROUP_5,
    REJECTION_CAUSES,
    ControlCountError,
    _check_identities,
    _compare_value,
    _group_2,
    _group_4,
    _news,
    compare_control_counts,
    compute_control_counts,
    compute_series_counts,
    expected_control_counts,
    store_control_counts,
    validate_control_counts,
    verify_store_control_counts,
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
            files={
                "scales_file": PILOT / "H1C-B5-P1.scales.json",
                "rankings_file": PILOT / "H1C-B5-P1.rankings.json",
            },
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


def _ss_detail(**attributes: object) -> object:
    values: dict[str, object] = {"decisions": (), "stops": ()}
    values.update(attributes)
    return type("Detail", (), values)()


def test_ss_group2_is_zero_and_computed_from_its_file(tmp_path: Path) -> None:
    scales = tmp_path / "scales.json"
    scales.write_text("[]", encoding="utf-8")
    values = _group_2(
        "SYSTEM_WITHOUT_HIERARCHY",
        _ss_detail(),
        {},
        {"scales_file": scales},
    )
    assert values["decision_events"] == 0
    assert values["stop_events"] == 0
    assert values["memory_episodes"] == 0
    assert values["scale_changes"] == 0


def test_ss_group2_fails_when_its_file_carries_an_engine_stop(tmp_path: Path) -> None:
    scales = tmp_path / "scales.json"
    scales.write_text("[]", encoding="utf-8")
    detail = _ss_detail(stops=({"chosen": {"cash": True}},))
    with pytest.raises(ControlCountError, match="not zero"):
        _group_2("SYSTEM_WITHOUT_HIERARCHY", detail, {}, {"scales_file": scales})


def test_ss_group2_fails_when_its_scales_file_is_not_empty(tmp_path: Path) -> None:
    scales = tmp_path / "scales.json"
    scales.write_text('[{"rule_id": "L0_CARTERA_ACTIVATION"}]', encoding="utf-8")
    with pytest.raises(ControlCountError, match="scale_changes"):
        _group_2("SYSTEM_WITHOUT_HIERARCHY", _ss_detail(), {}, {"scales_file": scales})


def test_formation_targets_use_the_first_decision_by_date() -> None:
    detail = _ss_detail(
        decisions=(
            {"date": "2022-02-01", "target": {"a": 1}},
            {"date": "2022-01-03", "target": {"a": 1, "b": 1, "c": 1}},
        )
    )
    values = _group_2("SYSTEM_WITH_HIERARCHY", detail, {}, {})
    assert values["formation_targets"] == 3


def test_ranking_rows_count_raw_rows_including_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "rankings.json"
    path.write_text(
        json.dumps(
            {
                "2022-01-03": {"rows": [{"asset_id": 1}, {"asset_id": 1}, {"asset_id": 2}]},
                "2022-02-01": {"rows": [{"asset_id": 3}]},
            }
        ),
        encoding="utf-8",
    )
    rankings = {"2022-01-03": frozenset({1, 2}), "2022-02-01": frozenset({3})}
    assert _group_4(rankings, {"rankings_file": path}) == {
        "ranking_decisions": 2,
        "ranking_rows": 4,
    }


def test_news_reads_date_records_and_pool_actions_without_a_kind_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "news.jsonl"
    records = [
        {
            "decision_date": "2022-10-12",
            "coverage": {"first": "2020-01-02", "last": "2022-10-11"},
            "admitted": 10,
            "actions": [{"action": "veto"}],
        },
        {
            "decision_date": "2022-10-12",
            "asset_id": 42,
            "ticker": "XYZ",
            "action": "veto",
        },
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    assert _news(path) == ({"veto": 1, "promotion": 0}, 1)


def test_a_spy_csv_without_a_window_column_fails(tmp_path: Path) -> None:
    path = tmp_path / "spy.csv"
    path.write_text("date,value\n2022-01-03,1\n", encoding="utf-8")
    with pytest.raises(ControlCountError, match="window"):
        compute_series_counts("P1", {"daily_file": path}, window_filter=True)


class _EmptyStore:
    def select(self, query: str) -> list[dict[str, str]]:
        if "GROUP BY" in query or "?cumulative" in query:
            return []
        return [{"n": "0"}]


def test_store_grouped_counts_keep_the_full_zero_filled_key_sets() -> None:
    values = store_control_counts(_EmptyStore(), "urn:graph:test", "MARKOWITZ_BASE")
    assert set(values["alerts_by_rule"]) == set(ALERT_RULES)
    assert set(values["actions_by_status"]) == set(ACTION_STATUSES)
    assert set(values["stops_cash_by_cause"]) == set(CASH_CAUSES)
    assert set(values["retention_rejections_by_cause"]) == set(REJECTION_CAUSES)
    assert all(value == 0 for value in values["alerts_by_rule"].values())


def test_an_unknown_configuration_or_window_fails_even_in_a_draft() -> None:
    with pytest.raises(ControlCountError, match="unknown configuration"):
        validate_control_counts(
            {"SURPRISE": {"P1": {}}},
            ("SYSTEM_WITH_HIERARCHY",),
            ("P1",),
            final=False,
        )
    with pytest.raises(ControlCountError, match="unknown window"):
        validate_control_counts(
            {"SYSTEM_WITH_HIERARCHY": {"P9": {}}},
            ("SYSTEM_WITH_HIERARCHY",),
            ("P1",),
            final=False,
        )


def test_a_final_manifest_must_carry_control_counts() -> None:
    with pytest.raises(ControlCountError, match="has no control_counts"):
        validate_control_counts(None, ("SYSTEM_WITH_HIERARCHY",), ("P1",), final=True)
    validate_control_counts(None, ("SYSTEM_WITH_HIERARCHY",), ("P1",), final=False)


class _MemoryStore:
    def __init__(
        self,
        *,
        memory_released_price: int = 42,
        memory_released_not_ranked: int = 0,
        memory_open_at_end: int = 28,
    ) -> None:
        self.memory_released_price = memory_released_price
        self.memory_released_not_ranked = memory_released_not_ranked
        self.memory_open_at_end = memory_open_at_end

    def select(self, query: str) -> list[dict[str, str]]:
        if 'memoryReleaseCause "price"' in query:
            return [{"n": str(self.memory_released_price)}]
        if 'memoryReleaseCause "not_ranked"' in query:
            return [{"n": str(self.memory_released_not_ranked)}]
        if "memoryReleasedOn" in query:
            return [{"n": str(self.memory_open_at_end)}]
        if "GROUP BY" in query or "?cumulative" in query:
            return []
        return [{"n": "0"}]


@pytest.mark.parametrize(
    ("key", "loaded"),
    [
        ("memory_released_price", 41),
        ("memory_released_not_ranked", 1),
        ("memory_open_at_end", 27),
    ],
)
def test_a_store_memory_release_mismatch_names_the_key(key: str, loaded: int) -> None:
    expected = {
        "SYSTEM_WITH_HIERARCHY": {
            "P1": {
                "memory_released_price": 42,
                "memory_released_not_ranked": 0,
                "memory_open_at_end": 28,
            }
        }
    }
    failures = verify_store_control_counts(
        _MemoryStore(**{key: loaded}),
        "urn:graph:test",
        "SYSTEM_WITH_HIERARCHY",
        "P1",
        expected,
    )
    assert len(failures) == 1
    assert f"SYSTEM_WITH_HIERARCHY/P1.{key}" in failures[0]


def test_a_wrapped_final_manifest_is_rejected() -> None:
    wrapped: object = {"configurations": {"SYSTEM_WITH_HIERARCHY": {"P1": {}}}}
    with pytest.raises(ControlCountError, match=r"unknown configuration\(s\): configurations"):
        validate_control_counts(wrapped, ("SYSTEM_WITH_HIERARCHY",), ("P1",), final=True)
    assert expected_control_counts(wrapped, "SYSTEM_WITH_HIERARCHY", "P1") is None
