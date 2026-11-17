"""Manifest control_counts against Reviewer A's pilot and the comparison rules (T-867/T-868)."""

from __future__ import annotations

import json
import re
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
    _group_5,
    _news,
    compare_control_counts,
    compute_control_counts,
    compute_series_counts,
    expected_control_counts,
    store_agent_counts,
    store_control_counts,
    validate_control_counts,
    verify_agent_control_counts,
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
        if "LIMIT 1" in query:
            return []
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


class _DestinationStore:
    def __init__(self, destination_options: int = 60) -> None:
        self.destination_options = destination_options

    def select(self, query: str) -> list[dict[str, str]]:
        if ":DestinationOption" in query:
            return [{"n": str(self.destination_options)}]
        if "GROUP BY" in query or "?cumulative" in query:
            return []
        return [{"n": "0"}]


def _detail_with_cash_menus(cash_entries: int) -> object:
    stops = tuple({"menu": [{"cash": True}, {"asset_id": 1}]} for _ in range(cash_entries))
    return type("Detail", (), {"stops": stops})()


def test_destination_options_subtract_the_cash_menu_entries() -> None:
    expected = {"SYSTEM_WITH_HIERARCHY": {"P1": {"destination_options": 67}}}
    failures = verify_store_control_counts(
        _DestinationStore(),
        "urn:graph:derived:backtest:final:P1:system_with_hierarchy",
        "SYSTEM_WITH_HIERARCHY",
        "P1",
        expected,
        detail=_detail_with_cash_menus(7),
        label="final",
    )
    assert failures == []


def test_destination_options_without_the_detail_file_fail() -> None:
    expected = {"SYSTEM_WITH_HIERARCHY": {"P1": {"destination_options": 67}}}
    failures = verify_store_control_counts(
        _DestinationStore(),
        "urn:graph:derived:backtest:final:P1:system_with_hierarchy",
        "SYSTEM_WITH_HIERARCHY",
        "P1",
        expected,
        label="final",
    )
    assert any(
        "destination_options" in failure and "detail file" in failure for failure in failures
    )


def _summary_rows() -> list[dict[str, str]]:
    return [
        {
            "cumulative": "-0.1",
            "annualized": "-0.2",
            "vol": "0.3",
            "drawdown": "0.4",
            "turnover": "5.0",
        },
        {
            "cumulative": "0.1",
            "annualized": "0.2",
            "vol": "0.3",
            "drawdown": "0.4",
            "turnover": "5.0",
        },
        {
            "cumulative": "0.0569",
            "annualized": "0.07",
            "vol": "0.15",
            "drawdown": "0.2",
            "turnover": "4.0",
        },
    ]


class _SummaryStore:
    def __init__(self, *, whole_window: bool = True) -> None:
        self.whole_window = whole_window

    def select(self, query: str) -> list[dict[str, str]]:
        if "PeriodSummary_final_P2_system_with_hierarchy_P2" in query:
            return _summary_rows()[2:] if self.whole_window else []
        if "?cumulative" in query:
            return _summary_rows()
        if "GROUP BY" in query:
            return []
        return [{"n": "0"}]


def test_final_values_use_the_whole_window_summary_not_rows_zero() -> None:
    expected = {
        "SYSTEM_WITH_HIERARCHY": {
            "P2": {
                "final_values": {
                    "cumulative_return": 0.0569,
                    "annualized_return": 0.07,
                    "annualized_vol": 0.15,
                    "max_drawdown": 0.2,
                    "total_turnover": 4.0,
                }
            }
        }
    }
    failures = verify_store_control_counts(
        _SummaryStore(),
        "urn:graph:derived:backtest:final:P2:system_with_hierarchy",
        "SYSTEM_WITH_HIERARCHY",
        "P2",
        expected,
        label="final",
    )
    assert failures == []


def test_a_missing_whole_window_summary_fails() -> None:
    expected = {
        "SYSTEM_WITH_HIERARCHY": {
            "P2": {
                "final_values": {
                    "cumulative_return": 0.0569,
                    "annualized_return": 0.07,
                    "annualized_vol": 0.15,
                    "max_drawdown": 0.2,
                    "total_turnover": 4.0,
                }
            }
        }
    }
    failures = verify_store_control_counts(
        _SummaryStore(whole_window=False),
        "urn:graph:derived:backtest:final:P2:system_with_hierarchy",
        "SYSTEM_WITH_HIERARCHY",
        "P2",
        expected,
        label="final",
    )
    assert any("no PortfolioPeriodSummary" in failure for failure in failures)


def test_an_ambiguous_whole_window_summary_fails() -> None:
    class _AmbiguousSummaryStore(_SummaryStore):
        def select(self, query: str) -> list[dict[str, str]]:
            if "PeriodSummary_final_P2_system_with_hierarchy_P2" in query:
                return _summary_rows()[1:]
            return super().select(query)

    with pytest.raises(ControlCountError, match="ambiguous"):
        store_control_counts(
            _AmbiguousSummaryStore(),
            "urn:graph:derived:backtest:final:P2:system_with_hierarchy",
            "SYSTEM_WITH_HIERARCHY",
            label="final",
            window="P2",
        )


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


def test_group_5_reads_the_final_files(tmp_path: Path) -> None:
    manager = tmp_path / "manager.jsonl"
    manager.write_text(
        '{"fallback": {"cause": null}, "repair_used": false}\n'
        '{"fallback": {"cause": "validator"}, "repair_used": true}\n',
        encoding="utf-8",
    )
    narrator = tmp_path / "narrator.jsonl"
    narrator.write_text(
        "".join('{"generated_by_language_model": true}\n' for _ in range(3)),
        encoding="utf-8",
    )
    news = tmp_path / "news.json"
    news.write_text(
        json.dumps(
            {
                "actions": [
                    {"action": "veto"},
                    {"action": "veto"},
                    {"action": "promotion"},
                ],
                "dates": [{"decision_date": "2022-01-03"}, {"decision_date": "2022-02-01"}],
                "levels_v2": {
                    "decisions": [
                        {"date": "2022-01-03", "c_flags": {"3": {}}, "d_fired": True},
                        {"date": "2022-02-01", "c_flags": {}, "d_fired": False},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    bull = tmp_path / "bull_mode.json"
    bull.write_text(
        json.dumps({"decisions": [{"triggered": True}, {"triggered": False}, {"triggered": True}]}),
        encoding="utf-8",
    )
    detail = type(
        "Detail",
        (),
        {
            "stops": (
                {"trigger": "news_shock", "eligible_counts": {"news_sector": 4}},
                {"trigger": None, "eligible_counts": {"news_sector": 2}},
            )
        },
    )()
    values = _group_5(
        {
            "manager_calls_file": manager,
            "narrator_file": narrator,
            "news_actions_file": news,
            "bull_mode_file": bull,
        },
        detail,
    )
    assert values == {
        "manager_calls": 2,
        "manager_fallbacks": 1,
        "manager_repairs": 1,
        "narrator_texts": 3,
        "news_pool_actions": {"veto": 2, "promotion": 1},
        "news_date_records": 2,
        "news_level_c_decisions": 1,
        "news_level_d_decisions": 1,
        "news_exits": 1,
        "news_sector_rejections": 6,
        "bull_triggered": 2,
    }


def test_group_5_is_null_when_the_final_files_are_absent() -> None:
    values = _group_5({}, None)
    assert all(value is None for value in values.values())


class _RecordingStore:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def select(self, query: str) -> list[dict[str, str]]:
        self.queries.append(query)
        return [{"n": "0"}]


def test_agent_count_queries_do_not_reuse_an_aggregate_alias() -> None:
    store = _RecordingStore()
    store_agent_counts(store, "final", "P1")
    assert store.queries
    for query in store.queries:
        for inner, alias in re.findall(
            r"\((?:SUM|COUNT|MIN|MAX|AVG)\(\s*(?:DISTINCT\s+)?\?([A-Za-z_]\w*)\s*\)"
            r"\s+AS\s+\?([A-Za-z_]\w*)\s*\)",
            query,
        ):
            assert alias != inner, query


def test_absent_agent_graphs_are_printed_without_failing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = {
        "SYSTEM_WITH_HIERARCHY": {
            "P1": {
                "news_exits": 2,
                "news_sector_rejections": 853,
                "bull_triggered": 0,
            }
        }
    }
    failures = verify_agent_control_counts(_EmptyStore(), "final", "P1", expected)
    assert failures == []
    output = capsys.readouterr().out
    assert "not store-verifiable" in output
    assert "SYSTEM_WITH_HIERARCHY/P1.news_exits" in output
    assert "SYSTEM_WITH_HIERARCHY/P1.news_sector_rejections" in output
    assert "SYSTEM_WITH_HIERARCHY/P1.bull_triggered" in output


def test_a_new_count_mismatch_is_a_failure() -> None:
    with pytest.raises(ControlCountError, match="news_exits"):
        _compare_value("SYSTEM_WITH_HIERARCHY", "P1", "news_exits", 2, 1)
