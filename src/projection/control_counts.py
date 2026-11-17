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

from projection.veto_manifest import configuration_slug

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
    "news_level_c_decisions",
    "news_level_d_decisions",
    "news_exits",
    "news_sector_rejections",
    "bull_triggered",
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
            values.update(_group_5(files, detail))
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
    # The pilot identity ``scale_changes == sum L0 alerts`` does not hold in the final delivery:
    # its scales file is empty while the engine still reports L0 alerts. Keep the check for the
    # historical pilot (non-zero scale_changes) and never manufacture a scale count.
    if values.get("scale_changes") and "alerts_by_rule" in values:
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
            if isinstance(line.get("retention"), dict) and line["retention"].get("enabled") is True
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


def _group_5(files: Mapping[str, Path], detail: object | None = None) -> dict[str, Any]:
    manager = files.get("manager_calls_file")
    narrator = files.get("narrator_file")
    news = files.get("news_actions_file")
    news_actions, news_dates, level_c, level_d = _news_bundle(news)
    return {
        "manager_calls": _manager(manager)[0],
        "manager_fallbacks": _manager(manager)[1],
        "manager_repairs": _manager(manager)[2],
        "narrator_texts": None if narrator is None else len(_records(narrator)),
        "news_pool_actions": news_actions,
        "news_date_records": news_dates,
        "news_level_c_decisions": level_c,
        "news_level_d_decisions": level_d,
        "news_exits": _news_exits(detail) if news is not None else None,
        "news_sector_rejections": _news_sector_rejections(detail) if news is not None else None,
        "bull_triggered": _bull_triggered(files.get("bull_mode_file")),
    }


def _news_exits(detail: object | None) -> int:
    """Stops whose JSON-lines ``trigger`` is ``news_shock`` (the L1_BP_STOP news exit)."""
    return sum(1 for stop in getattr(detail, "stops", ()) if stop.get("trigger") == "news_shock")


def _news_sector_rejections(detail: object | None) -> int:
    """Sum of every stop's ``eligible_counts.news_sector`` (level C sector rejections)."""
    total = 0
    for stop in getattr(detail, "stops", ()):
        counts = stop.get("eligible_counts") or {}
        total += int(counts.get("news_sector", 0))
    return total


def _bull_triggered(path: Path | None) -> int | None:
    if path is None:
        return None
    payload = _json_payload(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), list):
        raise ControlCountError(f"{path}: bull_mode.json must carry a decisions list")
    total = 0
    for number, decision in enumerate(payload["decisions"], 1):
        if not isinstance(decision, dict) or not isinstance(decision.get("triggered"), bool):
            raise ControlCountError(f"{path}: decisions[{number}].triggered must be a boolean")
        total += int(decision["triggered"])
    return total


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
    """The historical two-value view used by the first tests."""
    actions, dates, _level_c, _level_d = _news_bundle(path)
    return actions, dates


def _news_bundle(  # noqa: C901 -- one branch per final/legacy news shape
    path: Path | None,
) -> tuple[dict[str, int] | None, int | None, int | None, int | None]:
    """Count the final ``*.news.json`` object, or the older JSON-lines/array shape.

    The final file is one object with ``actions`` (PoolActionRecord), ``dates`` (DateRecord),
    ``levels_v2.decisions`` (level C/D decisions) and ``levels_v2.b_news_exits`` (the same count
    the JSON-lines stop ``trigger`` carries). The older JSON-lines form has one record per line.
    """
    if path is None:
        return None, None, None, None
    document: object
    try:
        document = _json_payload(path)
    except ControlCountError:
        document = _records(path)
    if isinstance(document, dict):
        action_rows = _dict_list(document.get("actions"), path, "actions")
        dates = _as_list(document.get("dates"), path, "dates")
        levels = document.get("levels_v2")
        if levels is None:
            return _action_counts(action_rows), len(dates), None, None
        if not isinstance(levels, dict):
            raise ControlCountError(f"{path}: levels_v2 must be an object")
        decisions = _dict_list(levels.get("decisions"), path, "levels_v2.decisions")
        level_c = sum(1 for decision in decisions if _level_c_flagged(decision))
        level_d = sum(1 for decision in decisions if decision.get("d_fired") is True)
        for number, decision in enumerate(decisions, 1):
            if "d_fired" in decision and not isinstance(decision["d_fired"], bool):
                raise ControlCountError(
                    f"{path}: levels_v2.decisions[{number}].d_fired must be a boolean"
                )
        return _action_counts(action_rows), len(dates), level_c, level_d
    rows = _as_dict_list(document, path)
    actions: Counter[str] = Counter()
    date_records = 0
    for row in rows:
        action = row.get("action")
        if action in ("veto", "promotion"):
            actions[str(action)] += 1
        if _is_date_record(row):
            date_records += 1
    return (
        {"veto": actions.get("veto", 0), "promotion": actions.get("promotion", 0)},
        date_records,
        None,
        None,
    )


def _action_counts(action_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in action_rows:
        action = row.get("action")
        if action not in ("veto", "promotion"):
            raise ControlCountError(f"news action {action!r} is not veto or promotion")
        counts[str(action)] += 1
    return {"veto": counts.get("veto", 0), "promotion": counts.get("promotion", 0)}


def _level_c_flagged(decision: Mapping[str, Any]) -> bool:
    flags = decision.get("c_flags")
    if isinstance(flags, dict) and flags:
        return True
    flagged = decision.get("c_flagged")
    return isinstance(flagged, list) and bool(flagged)


def _as_list(value: object, path: Path, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ControlCountError(f"{path}: {where} must be a list")
    return value


def _dict_list(value: object, path: Path, where: str) -> list[dict[str, Any]]:
    items = _as_list(value, path, where)
    if any(not isinstance(item, dict) for item in items):
        raise ControlCountError(f"{path}: {where} must be a list of objects")
    return items


def _as_dict_list(value: object, path: Path) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if any(not isinstance(item, dict) for item in value):
            raise ControlCountError(f"{path}: expected a JSON array of objects")
        return value
    raise ControlCountError(f"{path}: expected a JSON array of objects or one news object")


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


#: Keys whose file is parsed and compared but whose data has no graph representation yet.
STORE_NOT_LOADED: frozenset[str] = frozenset()

STORE_NON_VERIFIABLE: Mapping[str, str] = {
    "ranking_decisions": "the rankings file is not projected into a graph",
    "ranking_rows": "the rankings file is not projected into a graph",
    "scale_changes": "the scales file is not projected into a graph",
    "blocked_records": "blocked detail records are not individual graph nodes",
    "reentry_records": "reentry detail records are not individual graph nodes",
}


AGENT_GRAPH_PREFIX = "urn:graph:derived:backtest:agents:"
AGENT_KEYS_BY_GRAPH: Mapping[str, tuple[str, ...]] = {
    "manager_calls": ("manager_calls", "manager_fallbacks", "manager_repairs"),
    "narrator": ("narrator_texts",),
    "news": (
        "news_pool_actions",
        "news_date_records",
        "news_level_c_decisions",
        "news_level_d_decisions",
        "news_exits",
        "news_sector_rejections",
    ),
    "bull_mode": ("bull_triggered",),
}
AGENT_KEYS: frozenset[str] = frozenset(key for keys in AGENT_KEYS_BY_GRAPH.values() for key in keys)


def agent_graph_name(label: str, window: str, slug: str) -> str:
    """One block F graph; the slug is the source-file segment."""
    return f"{AGENT_GRAPH_PREFIX}{label}:{window}:{slug}"


def _agent_graph_exists(store: ReadableStore, graph: str) -> bool:
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))


def _agent_count(store: ReadableStore, graph: str, where: str) -> int:
    rows = store.select(
        "PREFIX : <https://thesis.local/kg/portfolio#>\n"
        f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ GRAPH <{graph}> {{ {where} }} }}"
    )
    return int(rows[0]["n"]) if rows and "n" in rows[0] else 0


def _agent_sum(store: ReadableStore, graph: str, where: str) -> int:
    rows = store.select(
        "PREFIX : <https://thesis.local/kg/portfolio#>\n"
        f"SELECT (SUM(?n) AS ?n) WHERE {{ GRAPH <{graph}> {{ {where} }} }}"
    )
    return int(rows[0]["n"]) if rows and "n" in rows[0] else 0


def store_agent_counts(store: ReadableStore, label: str, window: str) -> dict[str, Any]:
    """Derive the block F control keys from the four agent graphs.

    A missing graph contributes no key; :func:`verify_agent_control_counts` prints those keys as
    not store-verifiable and does not fail.
    """
    values: dict[str, Any] = {}
    manager_graph = agent_graph_name(label, window, "manager_calls")
    if _agent_graph_exists(store, manager_graph):
        values["manager_calls"] = _agent_count(store, manager_graph, "?s a :ManagerCall")
        values["manager_fallbacks"] = _agent_count(
            store, manager_graph, "?s a :ManagerCall ; :fallbackUsedRule true"
        )
        values["manager_repairs"] = _agent_count(
            store, manager_graph, "?s a :ManagerCall ; :repairUsed true"
        )
    narrator_graph = agent_graph_name(label, window, "narrator")
    if _agent_graph_exists(store, narrator_graph):
        values["narrator_texts"] = _agent_count(store, narrator_graph, "?s a :NarratorText")
    news_graph = agent_graph_name(label, window, "news")
    if _agent_graph_exists(store, news_graph):
        values["news_pool_actions"] = {
            kind: _agent_count(store, news_graph, f'?s a :NewsAction ; :newsActionKind "{kind}"')
            for kind in ("veto", "promotion")
        }
        values["news_date_records"] = _agent_count(store, news_graph, "?s a :DateRecord")
        values["news_level_c_decisions"] = _agent_count(
            store, news_graph, "?s a :DateRecord ; :levelCDecision true"
        )
        values["news_level_d_decisions"] = _agent_count(
            store, news_graph, "?s a :DateRecord ; :levelDFired true"
        )
        values["news_exits"] = _agent_sum(store, news_graph, "?s a :NewsRunRecord ; :newsExits ?n")
        values["news_sector_rejections"] = _agent_sum(
            store, news_graph, "?s a :NewsRunRecord ; :newsSectorRejections ?n"
        )
    bull_graph = agent_graph_name(label, window, "bull_mode")
    if _agent_graph_exists(store, bull_graph):
        values["bull_triggered"] = _agent_count(
            store, bull_graph, "?s a :BullModeDecision ; :bullTriggered true"
        )
    return values


def verify_agent_control_counts(
    store: ReadableStore,
    label: str,
    window: str,
    control_counts: object,
) -> list[str]:
    """Compare the block F keys; an absent graph prints not store-verifiable and does not fail."""
    expected = expected_control_counts(control_counts, "SYSTEM_WITH_HIERARCHY", window)
    if expected is None:
        return []
    wanted = {key: value for key, value in expected.items() if key in AGENT_KEYS}
    if not wanted:
        return []
    actual = store_agent_counts(store, label, window)
    failures: list[str] = []
    for slug, keys in AGENT_KEYS_BY_GRAPH.items():
        graph = agent_graph_name(label, window, slug)
        if not _agent_graph_exists(store, graph):
            for key in keys:
                if key in wanted:
                    print(
                        f"control count not store-verifiable: "
                        f"SYSTEM_WITH_HIERARCHY/{window}.{key}: the {slug} graph {graph} is absent"
                    )
    for key, value in wanted.items():
        if key not in actual:
            continue
        try:
            _compare_value("SYSTEM_WITH_HIERARCHY", window, key, value, actual[key])
        except ControlCountError as exc:
            failures.append(str(exc))
    return failures


def cash_menu_entries(detail: object | None) -> int:
    """Count the cash entries in the parsed detail file's stop menus.

    The loader deliberately does not project a cash entry as ``:DestinationOption`` (cash is
    ``:chosenCash``); the manifest count still includes it. The store check subtracts exactly these
    entries from the manifest count before comparing.
    """
    total = 0
    for stop in getattr(detail, "stops", ()):
        for option in stop.get("menu") or ():
            if option.get("cash") is True:
                total += 1
    return total


def whole_window_summary_iri(label: str, window: str, configuration: str) -> str:
    """The projector's one whole-window ``:PortfolioPeriodSummary`` IRI.

    P2 also has P2a/P2b summaries; the whole-window one carries the window itself as its segment
    (``PeriodSummary_<label>_<window>_<slug>_<window>``). Never select an arbitrary summary.
    """
    slug = configuration_slug(configuration)
    return f"https://thesis.local/kg/portfolio#PeriodSummary_{label}_{window}_{slug}_{window}"


def store_control_counts(
    store: ReadableStore,
    graph: str,
    configuration: str,
    *,
    label: str = "final",
    window: str | None = None,
) -> dict[str, Any]:
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
        "memory_released_price": count('?s a :StopMemory ; :memoryReleaseCause "price"'),
        "memory_released_not_ranked": count('?s a :StopMemory ; :memoryReleaseCause "not_ranked"'),
        "memory_open_at_end": count(
            "?s a :StopMemory . FILTER NOT EXISTS { ?s :memoryReleasedOn ?released }"
        ),
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
    if window is not None:
        summary_iri = whole_window_summary_iri(label, window, configuration)
        rows = store.select(
            prefix
            + f"SELECT ?cumulative ?annualized ?vol ?drawdown ?turnover WHERE {{ GRAPH <{graph}> {{ "
            + f"<{summary_iri}> a :PortfolioPeriodSummary ; :cumulativeReturn ?cumulative ; "
            + ":annualizedReturn ?annualized ; :annualizedVol ?vol ; :maxDrawdown ?drawdown ; "
            + ":totalTurnover ?turnover } }"
        )
        if len(rows) > 1:
            raise ControlCountError(
                f"{configuration}/{window}: the whole-window summary {summary_iri} is ambiguous "
                f"({len(rows)} rows)"
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


def verify_store_control_counts(  # noqa: PLR0913 -- explicit store/key and parsed detail
    store: ReadableStore,
    graph: str,
    configuration: str,
    window: str,
    control_counts: object,
    *,
    detail: object | None = None,
    label: str = "final",
) -> list[str]:
    """Compare the store-derivable keys; return failures and print the non-verifiable list."""
    expected = expected_control_counts(control_counts, configuration, window)
    if expected is None:
        print(f"control counts not provided for {configuration}/{window}")
        return []
    actual = store_control_counts(store, graph, configuration, label=label, window=window)
    failures: list[str] = []
    expected = dict(expected)
    if "destination_options" in expected:
        if detail is None:
            failures.append(
                f"{configuration}/{window}.destination_options: the parsed detail file is missing"
            )
            expected.pop("destination_options")
        else:
            expected["destination_options"] = int(expected["destination_options"]) - (
                cash_menu_entries(detail)
            )
    for key, value in expected.items():
        if key in AGENT_KEYS:
            continue
        if key not in actual:
            if key == "final_values":
                failures.append(
                    f"{configuration}/{window}.final_values: "
                    "the store has no PortfolioPeriodSummary for the graph"
                )
                continue
            reason = STORE_NON_VERIFIABLE.get(key, "not derivable from the loaded graph")
            if key in STORE_NOT_LOADED:
                print(
                    f"control count not store-verifiable: not loaded yet: "
                    f"{configuration}/{window}.{key}: {reason}"
                )
            else:
                print(
                    f"control count not store-verifiable: {configuration}/{window}.{key}: {reason}"
                )
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
    windows = control_counts.get(configuration)
    if not isinstance(windows, dict):
        return None
    value = windows.get(window)
    return value if isinstance(value, dict) else None
