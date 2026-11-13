"""Manifest ``control_counts``: compute from the loaded sources and compare exactly (T-867/T-868).

The shape is ``control_counts -> configuration -> window -> key -> value``. The loader never trusts
the manifest for a value: it computes each key from the same filtered rows, detail file and manifest
files it projects, then compares. Reviewer A's letter (2026-11-13) is the definition source.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

TOLERANCE = 1e-12

CONFIGURATIONS = (
    "SYSTEM_WITH_HIERARCHY",
    "SYSTEM_WITHOUT_HIERARCHY",
    "MARKOWITZ_BASE",
    "MARKOWITZ_MV",
    "SPY",
)
GH = "SYSTEM_WITH_HIERARCHY"
SS = "SYSTEM_WITHOUT_HIERARCHY"
MB = "MARKOWITZ_BASE"
SERIES = ("MARKOWITZ_MV", "SPY")

GROUP_1 = (
    "alerts_by_rule",
    "actions_by_status",
    "rebalances",
    "daily_rows",
    "weight_daily_rows",
    "final_values",
)
GROUP_2 = (
    "decision_events",
    "formation_targets",
    "stop_events",
    "stops_by_destination",
    "stops_cash_by_cause",
    "destination_options",
    "stop_rejection_summaries",
    "replacement_purchases",
    "replacement_checks",
    "replacements_stopped",
    "blocked_records",
    "reentry_records",
    "memory_episodes",
    "decision_close_episodes",
    "memory_released_price",
    "memory_released_not_ranked",
    "memory_open_at_end",
    "scale_changes",
)
GROUP_3 = (
    "retention_decisions",
    "retention_holds",
    "retention_rejections",
    "retention_counter_drops",
    "retention_rejections_by_cause",
)
GROUP_4 = ("ranking_decisions", "ranking_rows")
GROUP_5 = (
    "manager_calls",
    "manager_fallbacks",
    "manager_repairs",
    "narrator_texts",
    "news_pool_actions",
    "news_date_records",
)
GROUP_6 = ("daily_rows",)

EXPECTED_KEYS: Mapping[str, tuple[str, ...]] = {
    GH: GROUP_1 + GROUP_2 + GROUP_3 + GROUP_4 + GROUP_5,
    SS: GROUP_1 + GROUP_2 + GROUP_3 + GROUP_4,
    MB: GROUP_1,
    "MARKOWITZ_MV": GROUP_6,
    "SPY": GROUP_6,
}
FINAL_VALUE_KEYS = (
    "cumulative_return",
    "annualized_return",
    "annualized_vol",
    "max_drawdown",
    "total_turnover",
)
ALERT_RULES = (
    "L0_CARTERA_ACTIVATION",
    "L0_CARTERA_SCALE_CHANGE",
    "L0_CARTERA_RECOVERY",
    "L1_BP_STOP",
    "L1_BP_STOP_BLOCKED",
    "L1_BP_REENTRY",
)
ACTION_STATUSES = ("APPLIED", "BLOCKED")
FINAL_VALUES = (
    "cumulative_return",
    "annualized_return",
    "annualized_vol",
    "max_drawdown",
    "total_turnover",
)
DESTINATIONS = ("stock", "spy", "cash")
CASH_CAUSES = ("FILTER_OFF", "SCALE_BELOW_ONE", "NO_SIGNAL", "NO_ALLOWED_DESTINATION")
REJECTION_CAUSES = (
    "not_ranked",
    "hard_veto",
    "soft_penalty",
    "news_veto",
    "no_risk_model",
    "no_scenario",
    "memory",
    "counter",
)


class ControlCountError(ValueError):
    """A control count is missing, unknown, inconsistent or differs from the loaded value."""


def compute_control_counts(  # noqa: PLR0913 -- the source bundle is explicit
    configuration: str,
    window: str,
    *,
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    detail: object | None,
    memory_rows: Mapping[str, int],
    rankings: Mapping[str, frozenset[int]] | None,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    """Compute every key for one engine configuration/window from the filtered sources."""
    if configuration in (GH, SS, MB):
        values = _group_1(rows)
        if configuration in (GH, SS):
            values.update(_group_2(configuration, detail, memory_rows, files))
            values.update(_group_3(configuration, detail))
            values.update(_group_4(rankings, files))
        if configuration == GH:
            values.update(_group_5(files))
        return values
    raise ControlCountError(f"{configuration}: no engine control counts")


def compute_series_counts(
    window: str, files: Mapping[str, Path], *, window_filter: bool = False
) -> dict[str, int]:
    """Group 6 ``daily_rows`` from a reference series CSV."""
    path = files.get("daily_file")
    if path is None:
        raise ControlCountError(f"{window}: no daily_file for the reference series")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ControlCountError(f"{path}: the daily CSV has no header")
        if not window_filter:
            return {"daily_rows": sum(1 for _ in reader)}
        if "window" not in reader.fieldnames:
            raise ControlCountError(f"{path}: the series daily CSV has no window column")
        return {"daily_rows": sum(1 for row in reader if row.get("window") == window)}


def validate_control_counts(  # noqa: C901 -- one branch per malformed level
    control_counts: object,
    configurations: Sequence[str],
    windows: Sequence[str],
    *,
    final: bool,
) -> None:
    """Reject unknown configurations/windows and non-object windows before comparing runs."""
    if control_counts is None:
        if final:
            raise ControlCountError("the final manifest has no control_counts")
        return
    if not isinstance(control_counts, dict):
        if final:
            raise ControlCountError("control_counts must be an object")
        return
    unknown = sorted(set(control_counts) - set(configurations))
    if unknown:
        raise ControlCountError(f"control_counts: unknown configuration(s): {', '.join(unknown)}")
    for configuration, by_window in control_counts.items():
        if not isinstance(by_window, dict):
            raise ControlCountError(f"control_counts.{configuration}: must be an object")
        unknown_windows = sorted(set(by_window) - set(windows))
        if unknown_windows:
            raise ControlCountError(
                f"control_counts.{configuration}: unknown window(s): {', '.join(unknown_windows)}"
            )
        for window, values in by_window.items():
            if not isinstance(values, dict):
                raise ControlCountError(
                    f"control_counts.{configuration}.{window}: must be an object"
                )


def compare_control_counts(
    control_counts: object,
    configuration: str,
    window: str,
    computed: Mapping[str, Any],
    *,
    final: bool,
) -> None:
    """Compare one configuration/window; final requires every key, draft compares present ones."""
    if not isinstance(control_counts, dict):
        if final:
            raise ControlCountError(
                f"{configuration}/{window}: the final manifest has no control_counts"
            )
        print(f"control counts not provided for {configuration}/{window}")
        return
    expected_all = EXPECTED_KEYS[configuration]
    windows = control_counts.get(configuration)
    if not isinstance(windows, dict) or window not in windows:
        if final:
            raise ControlCountError(f"{configuration}/{window}: control_counts is missing")
        print(f"control counts not provided for {configuration}/{window}")
        return
    expected = windows[window]
    if not isinstance(expected, dict):
        raise ControlCountError(f"{configuration}/{window}: control_counts must be an object")
    unknown = sorted(set(expected) - set(expected_all))
    if unknown:
        raise ControlCountError(
            f"{configuration}/{window}: unknown control count(s): {', '.join(unknown)}"
        )
    missing = sorted(set(expected_all) - set(expected))
    if final and missing:
        raise ControlCountError(
            f"{configuration}/{window}: missing control count(s): {', '.join(missing)}"
        )
    for key, value in expected.items():
        if key not in computed:
            raise ControlCountError(f"{configuration}/{window}: no computed value for {key}")
        _compare_value(configuration, window, key, value, computed[key])
    _check_identities(configuration, window, expected, source="manifest")
    _check_identities(configuration, window, computed, source="loaded")


def _compare_value(  # noqa: C901, PLR0912 -- one branch per value shape
    configuration: str, window: str, key: str, expected: Any, actual: Any
) -> None:
    if key == "final_values":
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            raise ControlCountError(f"{configuration}/{window}.{key}: must be objects")
        if set(expected) != set(FINAL_VALUE_KEYS):
            raise ControlCountError(
                f"{configuration}/{window}.{key}: expected keys {FINAL_VALUE_KEYS}, got "
                f"{sorted(expected)}"
            )
        for subkey in FINAL_VALUE_KEYS:
            _compare_number(
                configuration, window, f"{key}.{subkey}", expected[subkey], actual[subkey]
            )
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            raise ControlCountError(
                f"{configuration}/{window}.{key}: expected keys {sorted(expected)}, "
                f"got {sorted(actual) if isinstance(actual, dict) else actual!r}"
            )
        for subkey, value in expected.items():
            if value is None or actual[subkey] is None:
                if value is not actual[subkey]:
                    raise ControlCountError(
                        f"{configuration}/{window}.{key}.{subkey}: expected {value!r}, "
                        f"loaded {actual[subkey]!r}"
                    )
            elif isinstance(value, float):
                _compare_number(configuration, window, f"{key}.{subkey}", value, actual[subkey])
            elif value != actual[subkey]:
                raise ControlCountError(
                    f"{configuration}/{window}.{key}.{subkey}: expected {value!r}, "
                    f"loaded {actual[subkey]!r}"
                )
        return
    if expected is None or actual is None:
        if expected is not actual:
            raise ControlCountError(
                f"{configuration}/{window}.{key}: expected {expected!r}, loaded {actual!r}"
            )
        return
    if isinstance(expected, float):
        _compare_number(configuration, window, key, expected, actual)
    elif expected != actual:
        raise ControlCountError(
            f"{configuration}/{window}.{key}: expected {expected!r}, loaded {actual!r}"
        )


def _compare_number(
    configuration: str, window: str, key: str, expected: float, actual: Any
) -> None:
    try:
        difference = abs(float(expected) - float(actual))
    except (TypeError, ValueError):
        raise ControlCountError(
            f"{configuration}/{window}.{key}: expected {expected!r}, loaded {actual!r}"
        ) from None
    if difference > TOLERANCE:
        raise ControlCountError(
            f"{configuration}/{window}.{key}: expected {expected!r}, loaded {actual!r}"
        )


def _check_identities(
    configuration: str, window: str, values: Mapping[str, Any], *, source: str
) -> None:
    if source == "manifest" and not isinstance(values, Mapping):
        return
    if "alerts_by_rule" in values and "scale_changes" in values:
        by_rule = values["alerts_by_rule"]
        if isinstance(by_rule, dict):
            expected = sum(
                int(by_rule.get(rule, 0))
                for rule in (
                    "L0_CARTERA_ACTIVATION",
                    "L0_CARTERA_SCALE_CHANGE",
                    "L0_CARTERA_RECOVERY",
                )
            )
            if expected != values["scale_changes"]:
                raise ControlCountError(
                    f"{configuration}/{window}: {source} identity fails: scale_changes "
                    f"{values['scale_changes']} != sum L0 alerts {expected}"
                )
    if "memory_episodes" in values:
        total = values["memory_episodes"]
        parts = (
            values.get("memory_released_price", 0)
            + values.get("memory_released_not_ranked", 0)
            + values.get("memory_open_at_end", 0)
        )
        if total != parts:
            raise ControlCountError(
                f"{configuration}/{window}: {source} identity fails: memory_episodes "
                f"{total} != {parts}"
            )
    if "retention_counter_drops" in values and "retention_rejections_by_cause" in values:
        by_cause = values["retention_rejections_by_cause"]
        if isinstance(by_cause, dict) and int(by_cause.get("counter", 0)) != int(
            values["retention_counter_drops"]
        ):
            raise ControlCountError(
                f"{configuration}/{window}: {source} identity fails: retention_counter_drops "
                f"{values['retention_counter_drops']} != counter {by_cause.get('counter', 0)}"
            )


# --- group computations -------------------------------------------------------------------------


def _group_1(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    alerts = rows.get("v_guard_alert", ())
    actions = rows.get("v_guard_action", ())
    alert_rule = {int(row["alert_id"]): str(row["rule_id"]) for row in alerts}
    counts: Counter[str] = Counter()
    for alert_id in {int(row["alert_id"]) for row in actions if row.get("alert_id") is not None}:
        counts[alert_rule.get(alert_id, "")] += 1
    summary = rows.get("v_portfolio_period_summary", ())
    if not summary:
        raise ControlCountError("v_portfolio_period_summary has no row for the loaded book")
    final = summary[0]
    return {
        "alerts_by_rule": {rule: counts.get(rule, 0) for rule in ALERT_RULES},
        "actions_by_status": {
            status: sum(1 for row in actions if str(row.get("status")) == status)
            for status in ACTION_STATUSES
        },
        "rebalances": len(rows.get("v_book_rebalance", ())),
        "daily_rows": len(rows.get("v_book_daily_performance", ())),
        "weight_daily_rows": len(rows.get("v_book_weight_daily", ())),
        "final_values": {key: float(final[key]) for key in FINAL_VALUES},
    }


def _group_2(
    configuration: str,
    detail: object | None,
    memory_rows: Mapping[str, int],
    files: Mapping[str, Path],
) -> dict[str, Any]:
    if detail is None:
        detail = _empty_detail()
    decisions = list(getattr(detail, "decisions", ()))
    stops = list(getattr(detail, "stops", ()))
    first_decision = min(decisions, key=lambda line: str(line["date"])) if decisions else {}
    first_target = first_decision.get("target", {}) if first_decision else {}
    destinations: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    options = 0
    summaries = 0
    for stop in stops:
        chosen = stop.get("chosen") or {}
        if chosen.get("cash") is True or chosen.get("asset_id") is None:
            destinations["cash"] += 1
        elif chosen.get("is_spy") is True:
            destinations["spy"] += 1
        else:
            destinations["stock"] += 1
        if stop.get("cause") is not None:
            causes[str(stop["cause"])] += 1
        options += len(stop.get("menu") or ())
        counts = stop.get("eligible_counts") or {}
        if any(int(value) != 0 for key, value in counts.items() if key != "zone_evaluated"):
            summaries += 1
    values = {
        "decision_events": len(decisions),
        "formation_targets": len(first_target),
        "stop_events": len(stops),
        "stops_by_destination": {key: destinations.get(key, 0) for key in DESTINATIONS},
        "stops_cash_by_cause": {key: causes.get(key, 0) for key in CASH_CAUSES},
        "destination_options": options,
        "stop_rejection_summaries": summaries,
        "replacement_purchases": len(getattr(detail, "replacement_bought", ())),
        "replacement_checks": len(getattr(detail, "replacement_checks", ())),
        "replacements_stopped": len(getattr(detail, "replacement_stopped", ())),
        "blocked_records": len(getattr(detail, "blocked", ())),
        "reentry_records": len(getattr(detail, "reentry", ())),
        "memory_episodes": int(memory_rows.get("memory_episodes", 0)),
        "decision_close_episodes": int(memory_rows.get("memory_episodes_decision_close", 0)),
        "memory_released_price": int(memory_rows.get("memory_released_price", 0)),
        "memory_released_not_ranked": int(memory_rows.get("memory_released_not_ranked", 0)),
        "memory_open_at_end": int(memory_rows.get("memory_open_at_end", 0)),
        "scale_changes": _scale_changes(files),
    }
    if configuration == SS:
        nonzero = {key: value for key, value in values.items() if _nonzero(value)}
        if nonzero:
            raise ControlCountError(
                f"{SS}: its JSON-lines only carries retention_decision, but group-2 "
                f"control count(s) are not zero: {nonzero}"
            )
    return values


def _nonzero(value: object) -> bool:
    if isinstance(value, dict):
        return any(_nonzero(item) for item in value.values())
    return value not in (0, None)


def _group_3(configuration: str, detail: object | None) -> dict[str, Any]:
    if detail is None:
        detail = _empty_detail()
    if configuration == GH:
        retentions = [
            line["retention"]
            for line in getattr(detail, "decisions", ())
            if line.get("retention", {}).get("enabled") is True
        ]
    else:
        retentions = list(getattr(detail, "retention_decisions", ()))
    holds = sum(len(item.get("retained", ())) for item in retentions)
    rejections = sum(len(item.get("rejected", ())) for item in retentions)
    drops = sum(len(item.get("counter_dropped", ())) for item in retentions)
    causes: Counter[str] = Counter()
    for item in retentions:
        for rejected in item.get("rejected", ()):
            causes[str(rejected.get("cause"))] += 1
    return {
        "retention_decisions": len(retentions),
        "retention_holds": holds,
        "retention_rejections": rejections,
        "retention_counter_drops": drops,
        "retention_rejections_by_cause": {key: causes.get(key, 0) for key in REJECTION_CAUSES},
    }


def _group_4(
    rankings: Mapping[str, frozenset[int]] | None, files: Mapping[str, Path]
) -> dict[str, int]:
    if rankings is None:
        raise ControlCountError("rankings are required for ranking_decisions/ranking_rows")
    path = files.get("rankings_file")
    if path is not None:
        payload = _json_payload(path)
        if not isinstance(payload, dict):
            raise ControlCountError(f"{path}: rankings must be an object keyed by decision date")
        rows_total = 0
        for date, item in payload.items():
            rows = item.get("rows") if isinstance(item, dict) else item
            if not isinstance(rows, list):
                raise ControlCountError(f"{path}: {date}: rankings must carry a rows list")
            rows_total += len(rows)
        return {"ranking_decisions": len(rankings), "ranking_rows": rows_total}
    return {
        "ranking_decisions": len(rankings),
        "ranking_rows": sum(len(rows) for rows in rankings.values()),
    }


def _group_5(files: Mapping[str, Path]) -> dict[str, Any]:
    manager = files.get("manager_calls_file")
    narrator = files.get("narrator_file")
    news = files.get("news_actions_file")
    return {
        "manager_calls": _manager(manager)[0],
        "manager_fallbacks": _manager(manager)[1],
        "manager_repairs": _manager(manager)[2],
        "narrator_texts": None if narrator is None else len(_records(narrator)),
        "news_pool_actions": _news(news)[0],
        "news_date_records": _news(news)[1],
    }


def _manager(path: Path | None) -> tuple[int | None, int | None, int | None]:
    if path is None:
        return None, None, None
    records = _records(path)
    fallbacks = sum(
        1
        for row in records
        if isinstance(row.get("fallback"), dict) and row["fallback"].get("cause") is not None
    )
    repairs = sum(1 for row in records if row.get("repair_used") is True)
    return len(records), fallbacks, repairs


def _news(path: Path | None) -> tuple[dict[str, int] | None, int | None]:
    if path is None:
        return None, None
    records = _records(path)
    actions: Counter[str] = Counter()
    date_records = 0
    for row in records:
        action = row.get("action")
        if action in ("veto", "promotion"):
            actions[str(action)] += 1
        if _is_date_record(row):
            date_records += 1
    return {"veto": actions.get("veto", 0), "promotion": actions.get("promotion", 0)}, date_records


def _is_date_record(row: Mapping[str, Any]) -> bool:
    kind = str(row.get("kind", "")).lower().replace("-", "_")
    if kind in ("date_record", "daterecord"):
        return True
    if "coverage_first" in row:
        return True
    return (
        "decision_date" in row and "coverage" in row and "admitted" in row and "action" not in row
    )


def _scale_changes(files: Mapping[str, Path]) -> int:
    path = files.get("scales_file")
    if path is None:
        return 0
    return len(_records(path))


def _json_payload(path: Path) -> object:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ControlCountError(f"{path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ControlCountError(f"{path}: invalid JSON: {exc}") from exc


def _records(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ControlCountError(f"{path}: {exc}") from exc
    if raw.lstrip().startswith("["):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ControlCountError(f"{path}: invalid JSON: {exc}") from exc
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ControlCountError(f"{path}: expected a JSON array of objects")
        return value
    records = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ControlCountError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ControlCountError(f"{path}:{number}: expected a JSON object")
        records.append(row)
    return records


def _empty_detail() -> object:
    return type(
        "EmptyDetail",
        (),
        {
            "decisions": (),
            "stops": (),
            "replacement_bought": (),
            "replacement_checks": (),
            "replacement_stopped": (),
            "blocked": (),
            "reentry": (),
            "retention_decisions": (),
        },
    )()


class ReadableStore(Protocol):
    def select(self, sparql: str) -> list[dict[str, str]]: ...


STORE_NON_VERIFIABLE: Mapping[str, str] = {
    "ranking_decisions": "the rankings file is not projected into a graph",
    "ranking_rows": "the rankings file is not projected into a graph",
    "scale_changes": "the scales file is not projected into a graph",
    "blocked_records": "blocked detail records are not individual graph nodes",
    "reentry_records": "reentry detail records are not individual graph nodes",
    "manager_calls": "manager calls are not loaded",
    "manager_fallbacks": "manager calls are not loaded",
    "manager_repairs": "manager calls are not loaded",
    "narrator_texts": "narrator texts are not loaded",
    "news_pool_actions": "news actions are not loaded",
    "news_date_records": "news date records are not loaded",
}


def store_control_counts(store: ReadableStore, graph: str, configuration: str) -> dict[str, Any]:
    """Derive the store-verifiable control keys from one loaded m018 graph."""
    prefix = "PREFIX : <https://thesis.local/kg/portfolio#>\n"

    def count(where: str) -> int:
        rows = store.select(
            prefix + f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ {where} }} }}"
        )
        return int(rows[0]["n"]) if rows and "n" in rows[0] else 0

    def grouped(query: str) -> dict[str, int]:
        rows = store.select(
            prefix
            + f"SELECT ?k (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ {query} }} }} GROUP BY ?k"
        )
        return {str(row["k"]): int(row["n"]) for row in rows}

    alerts = grouped('?a a :GuardAlert ; :alertRule ?r . BIND(STRAFTER(STR(?r), "#Rule_") AS ?k)')
    statuses = grouped("?a a :GuardAction ; :status ?k")
    cash_causes = grouped("?s a :StopEvent ; :stopCashCause ?k")
    rejection_causes = grouped("?s a :RetentionRejection ; :rejectionCause ?k")
    values: dict[str, Any] = {
        "rebalances": count("?s a :BookRebalance"),
        "daily_rows": count("?s a :BookDailyPerformance"),
        "weight_daily_rows": count("?s a :BookWeightDaily"),
        "decision_events": count("?s a :DecisionEvent"),
        "formation_targets": count("?s a :FormationTarget"),
        "stop_events": count("?s a :StopEvent"),
        "destination_options": count("?s a :DestinationOption"),
        "stop_rejection_summaries": count("?s a :StopRejectionSummary"),
        "replacement_purchases": count("?s a :ReplacementPurchase"),
        "replacement_checks": count("?s a :ReplacementCheck"),
        "replacements_stopped": count("?s a :ReplacementPurchase ; :replacementStoppedBy ?stop"),
        "memory_episodes": count("?s a :StopMemory"),
        "decision_close_episodes": count('?s a :StopMemory ; :memoryStartKind "decision_close"'),
        "retention_decisions": count("?s a :RetentionDecision"),
        "retention_holds": count("?s a :RetentionHold"),
        "retention_rejections": count("?s a :RetentionRejection"),
        "retention_counter_drops": count("?s :counterDroppedAsset ?asset"),
        "alerts_by_rule": {rule: alerts.get(rule, 0) for rule in ALERT_RULES},
        "actions_by_status": {status: statuses.get(status, 0) for status in ACTION_STATUSES},
        "stops_by_destination": {
            "cash": count("?s a :StopEvent ; :chosenCash true"),
            "spy": count("?s a :StopEvent ; :chosenOption ?o . ?o :optionIsSpy true"),
            "stock": count("?s a :StopEvent ; :chosenOption ?o . ?o :optionIsSpy false"),
        },
        "stops_cash_by_cause": {cause: cash_causes.get(cause, 0) for cause in CASH_CAUSES},
        "retention_rejections_by_cause": {
            cause: rejection_causes.get(cause, 0) for cause in REJECTION_CAUSES
        },
    }
    rows = store.select(
        prefix
        + f"SELECT ?cumulative ?annualized ?vol ?drawdown ?turnover WHERE {{ GRAPH <{graph}> {{ "
        + "?s a :PortfolioPeriodSummary ; :cumulativeReturn ?cumulative ; :annualizedReturn ?annualized ; "
        + ":annualizedVol ?vol ; :maxDrawdown ?drawdown ; :totalTurnover ?turnover } }"
    )
    if rows:
        row = rows[0]
        values["final_values"] = {
            "cumulative_return": float(row["cumulative"]),
            "annualized_return": float(row["annualized"]),
            "annualized_vol": float(row["vol"]),
            "max_drawdown": float(row["drawdown"]),
            "total_turnover": float(row["turnover"]),
        }
    if configuration in ("MARKOWITZ_MV", "SPY"):
        values.pop("daily_rows", None)
    return values


def verify_store_control_counts(
    store: ReadableStore,
    graph: str,
    configuration: str,
    window: str,
    control_counts: object,
) -> list[str]:
    """Compare the store-derivable keys; return failures and print the non-verifiable list."""
    expected = expected_control_counts(control_counts, configuration, window)
    if expected is None:
        print(f"control counts not provided for {configuration}/{window}")
        return []
    actual = store_control_counts(store, graph, configuration)
    failures: list[str] = []
    for key, value in expected.items():
        if key not in actual:
            if key == "final_values":
                failures.append(
                    f"{configuration}/{window}.final_values: "
                    "the store has no PortfolioPeriodSummary for the graph"
                )
                continue
            reason = STORE_NON_VERIFIABLE.get(key, "not derivable from the loaded graph")
            print(f"control count not store-verifiable: {configuration}/{window}.{key}: {reason}")
            continue
        try:
            _compare_value(configuration, window, key, value, actual[key])
        except ControlCountError as exc:
            failures.append(str(exc))
    return failures


def expected_control_counts(
    control_counts: object, configuration: str, window: str
) -> Mapping[str, Any] | None:
    if not isinstance(control_counts, dict):
        return None
    configurations = control_counts.get("configurations", control_counts)
    if not isinstance(configurations, dict):
        return None
    windows = configurations.get(configuration)
    if not isinstance(windows, dict):
        return None
    value = windows.get(window)
    return value if isinstance(value, dict) else None
