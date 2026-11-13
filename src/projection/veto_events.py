"""Strict reader and projector for ``*.cartera_v1_3.kg.jsonl`` (Work item 46, T-853-T-859).

The detail file is the engine's audit trail, not a second m018 source. The reader rejects an
unknown ``kind`` or field, a duplicate unique key, a null in a required field and any price-looking
key before the projector sees a line. ``stop_distance_pct`` is accepted and deliberately never
projected. ``blocked`` and ``reentry`` are cross-checks against the loaded guard alerts, not new
individuals.
"""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from projection.veto_manifest import configuration_slug

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORBIDDEN_KEYS = frozenset({"close", "level", "stop", "stop_level"})

KINDS = (
    "decision",
    "stop",
    "replacement_bought",
    "replacement_check",
    "replacement_stopped",
    "blocked",
    "reentry",
    "retention_decision",
)

_DECISION_KEYS = frozenset(
    {
        "kind",
        "date",
        "filter",
        "filter_decision",
        "core_weight_in_force",
        "scale",
        "blocked",
        "candidate_ids",
        "optimizer_target",
        "retention",
        "target",
    }
)
_RETENTION_KEYS = frozenset(
    {
        "enabled",
        "max_decisions",
        "pool_size",
        "pool_ids",
        "held_outside",
        "retained",
        "rejected",
        "rejections",
        "counter_dropped",
        "kept",
        "kept_weight",
        "candidate_size",
    }
)
_STOP_KEYS = frozenset(
    {
        "kind",
        "date",
        "asset_id",
        "weight_before",
        "filter",
        "filter_decision",
        "scale",
        "rho_w0",
        "rho",
        "chooser",
        "cash_left",
        "portfolio_check",
        "cause",
        "eligible",
        "eligible_counts",
        "zone_evaluated",
        "zone_pass",
        "a_star",
        "size_fraction",
        "chosen",
        "menu",
        "rho_delta",
        "weight_after_e3",
        "stop_distance_pct",
    }
)
_REPLACEMENT_BOUGHT_KEYS = frozenset(
    {
        "kind",
        "date",
        "asset_id",
        "order_date",
        "execution_date",
        "machine_entry_session",
        "first_evaluation",
        "weight",
        "size_fraction",
        "rank",
        "bucket",
        "filter",
        "filter_decision",
        "stop_distance_pct",
    }
)
_REPLACEMENT_CHECK_KEYS = frozenset({"kind", "date", "asset_id", "candidate", "kept"})
_REPLACEMENT_STOPPED_KEYS = frozenset({"kind", "date", "asset_id"})
_BLOCKED_KEYS = frozenset({"kind", "date", "asset_id", "stop_distance_pct"})
_REENTRY_KEYS = frozenset({"kind", "date", "asset_id", "stop_distance_pct"})
_RETENTION_DECISION_KEYS = frozenset(
    {
        "kind",
        "date",
        "arm",
        "pool_size",
        "pool_ids",
        "candidate_ids",
        "candidate_size",
        "held_outside",
        "retained",
        "rejected",
        "rejections",
        "counter_dropped",
        "kept",
        "kept_weight",
        "target",
    }
)
_KIND_KEYS = {
    "decision": _DECISION_KEYS,
    "stop": _STOP_KEYS,
    "replacement_bought": _REPLACEMENT_BOUGHT_KEYS,
    "replacement_check": _REPLACEMENT_CHECK_KEYS,
    "replacement_stopped": _REPLACEMENT_STOPPED_KEYS,
    "blocked": _BLOCKED_KEYS,
    "reentry": _REENTRY_KEYS,
    "retention_decision": _RETENTION_DECISION_KEYS,
}
_OPTION_KEYS = frozenset(
    {"R", "asset_id", "beta", "is_spy", "rank", "rho", "score", "sector", "size_fraction", "weight"}
)
_CHOSEN_KEYS = frozenset({"asset_id", "cash"}) | _OPTION_KEYS
_KEPT_KEYS = frozenset({"asset_id", "weight"})
_HOLD_KEYS = frozenset({"asset_id", "counter", "counter_before"})
_REJECTION_KEYS = frozenset({"asset_id", "cause", "counter"})
_PORTFOLIO_CHECK_KEYS = frozenset({"passed", "reasons"})
_RHO_DELTA_KEYS = frozenset({"min", "median", "max"})
_ELIGIBLE_KEYS = frozenset(
    {
        "hard_veto",
        "soft_penalty",
        "news_veto",
        "held",
        "memory",
        "not_ranked",
        "no_risk_model",
        "no_bar",
        "missing_return",
        "trend_break",
        "sector_cap",
        "spy_limit",
        "zone_high",
        "zone_no_signal",
        "zone_evaluated",
        "NO_ALLOWED_DESTINATION",
    }
)

_REJECTION_PROPERTIES = {
    "hard_veto": "rejectedHardVeto",
    "soft_penalty": "rejectedSoftPenalty",
    "news_veto": "rejectedNewsVeto",
    "held": "rejectedHeld",
    "memory": "rejectedMemory",
    "not_ranked": "rejectedNotRanked",
    "no_risk_model": "rejectedNoRiskModel",
    "no_bar": "rejectedNoBar",
    "missing_return": "rejectedMissingReturn",
    "trend_break": "rejectedTrendBreak",
    "sector_cap": "rejectedSectorCap",
    "spy_limit": "rejectedSpyLimit",
    "zone_high": "rejectedZoneHigh",
    "zone_no_signal": "rejectedZoneNoSignal",
    "NO_ALLOWED_DESTINATION": "rejectedNoAllowedDestination",
}


class DetailError(ValueError):
    """The detail file, its keys or a cross-check cannot be accepted."""


@dataclass(frozen=True)
class DetailFile:
    """Every validated line, grouped by ``kind``."""

    path: Path
    decisions: tuple[dict[str, Any], ...]
    stops: tuple[dict[str, Any], ...]
    replacement_bought: tuple[dict[str, Any], ...]
    replacement_checks: tuple[dict[str, Any], ...]
    replacement_stopped: tuple[dict[str, Any], ...]
    blocked: tuple[dict[str, Any], ...]
    reentry: tuple[dict[str, Any], ...]
    retention_decisions: tuple[dict[str, Any], ...]

    @property
    def lines(self) -> int:
        return (
            len(self.decisions)
            + len(self.stops)
            + len(self.replacement_bought)
            + len(self.replacement_checks)
            + len(self.replacement_stopped)
            + len(self.blocked)
            + len(self.reentry)
            + len(self.retention_decisions)
        )


def _where(path: Path, line: int) -> str:
    return f"{path}:{line}"


def _bad(where: str, message: str) -> DetailError:
    return DetailError(f"{where}: {message}")


def parse_detail_file(path: str | Path) -> DetailFile:
    """Read the JSONL file and validate every line before any projection."""
    detail_path = Path(path)
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    seen: dict[str, set[tuple[object, ...]]] = {kind: set() for kind in KINDS}
    try:
        handle = detail_path.open(encoding="utf-8")
    except OSError as exc:
        raise DetailError(f"{detail_path}: {exc}") from exc
    with handle:
        for number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            where = _where(detail_path, number)
            try:
                line = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise _bad(where, f"invalid JSON: {exc}") from exc
            if not isinstance(line, dict):
                raise _bad(where, "a detail line must be a JSON object")
            kind = line.get("kind")
            if kind not in _KIND_KEYS:
                raise _bad(where, f"unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
            _forbidden(line, where, "")
            unknown = sorted(set(line) - _KIND_KEYS[str(kind)])
            if unknown:
                raise _bad(where, f"{kind}: unknown field(s): {', '.join(unknown)}")
            _validate_line(str(kind), line, where)
            key = _unique_key(str(kind), line)
            if key in seen[str(kind)]:
                raise _bad(where, f"{kind}: duplicate unique key {key!r}")
            seen[str(kind)].add(key)
            grouped[str(kind)].append(line)
    if not any(grouped.values()):
        raise DetailError(f"{detail_path}: the detail file is empty")
    return DetailFile(
        path=detail_path,
        decisions=tuple(grouped["decision"]),
        stops=tuple(grouped["stop"]),
        replacement_bought=tuple(grouped["replacement_bought"]),
        replacement_checks=tuple(grouped["replacement_check"]),
        replacement_stopped=tuple(grouped["replacement_stopped"]),
        blocked=tuple(grouped["blocked"]),
        reentry=tuple(grouped["reentry"]),
        retention_decisions=tuple(grouped["retention_decision"]),
    )


def _forbidden(value: object, where: str, prefix: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_KEYS:
                raise _bad(where, f"{prefix}{key}: a price field is not allowed")
            _forbidden(child, where, f"{prefix}{key}.")
    elif isinstance(value, list):
        for child in value:
            _forbidden(child, where, prefix)


def _unique_key(kind: str, line: Mapping[str, Any]) -> tuple[object, ...]:  # noqa: PLR0911
    if kind == "decision":
        return (line["date"],)
    if kind == "stop":
        return (line["date"], line["asset_id"])
    if kind == "replacement_bought":
        return (line["order_date"], line["asset_id"])
    if kind == "replacement_check":
        return (line["date"], line["asset_id"])
    if kind == "replacement_stopped":
        return (line["date"], line["asset_id"])
    if kind in {"blocked", "reentry"}:
        return (line["date"], line["asset_id"])
    return (line["date"], line["arm"])


def _validate_line(  # noqa: C901, PLR0912, PLR0915 -- one branch per kind
    kind: str, line: Mapping[str, Any], where: str
) -> None:
    _date(line, "date", where)
    if kind == "decision":
        _bool(line, "filter", where)
        _date(line, "filter_decision", where)
        _number(line, "core_weight_in_force", where)
        _number(line, "scale", where)
        _int_list(line, "blocked", where)
        _int_list(line, "candidate_ids", where)
        _number_map(line, "optimizer_target", where)
        _number_map(line, "target", where)
        retention = _object(line, "retention", where)
        unknown = sorted(set(retention) - _RETENTION_KEYS)
        if unknown:
            raise _bad(where, f"decision.retention: unknown field(s): {', '.join(unknown)}")
        _retention(retention, where)
        _bool(retention, "enabled", where, "retention.")
        _positive_int(retention, "max_decisions", where, "retention.")
    elif kind == "stop":
        _positive_int(line, "asset_id", where)
        _number(line, "weight_before", where)
        _bool(line, "filter", where)
        _date(line, "filter_decision", where)
        _number(line, "scale", where)
        _number(line, "rho_w0", where)
        _number(line, "rho", where)
        _string(line, "chooser", where)
        _number(line, "cash_left", where)
        check = _object(line, "portfolio_check", where)
        unknown = sorted(set(check) - _PORTFOLIO_CHECK_KEYS)
        if unknown:
            raise _bad(where, f"stop.portfolio_check: unknown field(s): {', '.join(unknown)}")
        _bool(check, "passed", where, "stop.portfolio_check")
        reasons = check.get("reasons")
        if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
            raise _bad(where, "stop.portfolio_check.reasons must be a list of strings")
        if line.get("cause") is not None:
            _string(line, "cause", where)
        _optional_int(line, "eligible", where)
        _optional_int(line, "zone_evaluated", where)
        _optional_int(line, "zone_pass", where)
        _optional_number(line, "a_star", where)
        _optional_number(line, "size_fraction", where)
        _optional_number(line, "weight_after_e3", where)
        if line.get("stop_distance_pct") is not None:
            _number(line, "stop_distance_pct", where)
        if line.get("eligible_counts") is not None:
            counts = _object(line, "eligible_counts", where)
            unknown = sorted(set(counts) - _ELIGIBLE_KEYS)
            if unknown:
                raise _bad(where, f"stop.eligible_counts: unknown field(s): {', '.join(unknown)}")
            for key, value in counts.items():
                _non_negative_int(value, f"stop.eligible_counts.{key}", where)
        chosen = _object(line, "chosen", where)
        _chosen(chosen, where)
        menu = line.get("menu")
        if menu is not None:
            if not isinstance(menu, list):
                raise _bad(where, "stop.menu must be a list or null")
            for index, option in enumerate(menu):
                _option(
                    _object_value(option, where, f"stop.menu[{index}]"),
                    where,
                    f"stop.menu[{index}]",
                )
        if line.get("rho_delta") is not None:
            delta = _object(line, "rho_delta", where)
            unknown = sorted(set(delta) - _RHO_DELTA_KEYS)
            if unknown:
                raise _bad(where, f"stop.rho_delta: unknown field(s): {', '.join(unknown)}")
            for key in _RHO_DELTA_KEYS:
                _number(delta, key, where, "stop.rho_delta")
    elif kind == "replacement_bought":
        _positive_int(line, "asset_id", where)
        _date(line, "order_date", where)
        _date(line, "execution_date", where)
        _date(line, "machine_entry_session", where)
        _optional_date(line, "first_evaluation", where)
        _number(line, "weight", where)
        _number(line, "size_fraction", where)
        _int(line, "rank", where)
        _string(line, "bucket", where)
        _bool(line, "filter", where)
        _date(line, "filter_decision", where)
        if line.get("stop_distance_pct") is not None:
            _number(line, "stop_distance_pct", where)
    elif kind == "replacement_check":
        _positive_int(line, "asset_id", where)
        _bool(line, "candidate", where)
        _bool(line, "kept", where)
    elif kind == "replacement_stopped":
        _positive_int(line, "asset_id", where)
    elif kind in ("blocked", "reentry"):
        _positive_int(line, "asset_id", where)
        if line.get("stop_distance_pct") is not None:
            _number(line, "stop_distance_pct", where)
    else:
        _string(line, "arm", where)
        _positive_int(line, "pool_size", where)
        _int_list(line, "pool_ids", where)
        _int_list(line, "candidate_ids", where)
        _positive_int(line, "candidate_size", where)
        _int_list(line, "held_outside", where)
        _retention(line, where)


def _retention(retention: Mapping[str, Any], where: str) -> None:  # noqa: C901
    _positive_int(retention, "pool_size", where, "retention.")
    _int_list(retention, "pool_ids", where, "retention.")
    _int_list(retention, "held_outside", where, "retention.")
    _int_list(retention, "counter_dropped", where, "retention.")
    _positive_int(retention, "candidate_size", where, "retention.")
    _number(retention, "kept_weight", where, "retention.")
    retained = retention.get("retained")
    if not isinstance(retained, list):
        raise _bad(where, "retention.retained must be a list")
    for index, item in enumerate(retained):
        obj = _object_value(item, where, f"retention.retained[{index}].")
        unknown = sorted(set(obj) - _HOLD_KEYS)
        if unknown:
            raise _bad(
                where, f"retention.retained[{index}]: unknown field(s): {', '.join(unknown)}"
            )
        _positive_int(obj, "asset_id", where, f"retention.retained[{index}].")
        _non_negative_int(obj.get("counter"), "counter", where, f"retention.retained[{index}].")
        if "counter_before" in obj:
            _non_negative_int(
                obj.get("counter_before"), "counter_before", where, f"retention.retained[{index}]."
            )
    rejected = retention.get("rejected")
    if not isinstance(rejected, list):
        raise _bad(where, "retention.rejected must be a list")
    for index, item in enumerate(rejected):
        obj = _object_value(item, where, f"retention.rejected[{index}]")
        unknown = sorted(set(obj) - _REJECTION_KEYS)
        if unknown:
            raise _bad(
                where, f"retention.rejected[{index}]: unknown field(s): {', '.join(unknown)}"
            )
        _positive_int(obj, "asset_id", where, f"retention.rejected[{index}]")
        _string(obj, "cause", where, f"retention.rejected[{index}]")
        _non_negative_int(obj.get("counter"), "counter", where, f"retention.rejected[{index}].")
    kept = retention.get("kept")
    if not isinstance(kept, list):
        raise _bad(where, "retention.kept must be a list")
    for index, item in enumerate(kept):
        obj = _object_value(item, where, f"retention.kept[{index}]")
        unknown = sorted(set(obj) - _KEPT_KEYS)
        if unknown:
            raise _bad(where, f"retention.kept[{index}]: unknown field(s): {', '.join(unknown)}")
        _positive_int(obj, "asset_id", where, f"retention.kept[{index}]")
        _number(obj, "weight", where, f"retention.kept[{index}]")
    rejections = retention.get("rejections")
    if not isinstance(rejections, dict):
        raise _bad(where, "retention.rejections must be an object")
    for key, value in rejections.items():
        _non_negative_int(value, f"retention.rejections.{key}", where)


def _chosen(chosen: Mapping[str, Any], where: str) -> None:
    unknown = sorted(set(chosen) - _CHOSEN_KEYS)
    if unknown:
        raise _bad(where, f"stop.chosen: unknown field(s): {', '.join(unknown)}")
    if chosen.get("cash") is True:
        if set(chosen) - {"asset_id", "cash"}:
            raise _bad(where, "stop.chosen: a cash choice carries no option fields")
        if chosen.get("asset_id") is not None:
            raise _bad(where, "stop.chosen: a cash choice has no asset_id")
        return
    _option(chosen, where, "stop.chosen")


def _option(option: Mapping[str, Any], where: str, prefix: str) -> None:
    unknown = sorted(set(option) - _OPTION_KEYS)
    if unknown:
        raise _bad(where, f"{prefix}: unknown field(s): {', '.join(unknown)}")
    _positive_int(option, "asset_id", where, prefix)
    _bool(option, "is_spy", where, prefix)
    _number(option, "rho", where, prefix)
    _number(option, "R", where, prefix)
    _number(option, "beta", where, prefix)
    _int(option, "rank", where, prefix)
    _number(option, "score", where, prefix)
    _int(option, "sector", where, prefix)
    _number(option, "size_fraction", where, prefix)
    _number(option, "weight", where, prefix)


def _object(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> Mapping[str, Any]:
    return _object_value(line.get(key), where, f"{prefix}{key}")


def _object_value(value: object, where: str, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _bad(where, f"{name} must be an object")
    return value


def _date(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    _string(line, key, where, prefix)
    value = line[key]
    if not _DATE.fullmatch(value):
        raise _bad(where, f"{prefix}{key} {value!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise _bad(where, f"{prefix}{key} {value!r} is not a real date") from None


def _optional_date(line: Mapping[str, Any], key: str, where: str) -> None:
    if line.get(key) is not None:
        _date(line, key, where)


def _string(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    value = line.get(key)
    if not isinstance(value, str) or not value:
        raise _bad(where, f"{prefix}{key} must be a non-empty string")


def _bool(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    if not isinstance(line.get(key), bool):
        raise _bad(where, f"{prefix}{key} must be a boolean")


def _int(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    value = line.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(where, f"{prefix}{key} must be an integer")


def _positive_int(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    _int(line, key, where, prefix)
    if line[key] < 1:
        raise _bad(where, f"{prefix}{key} must be a positive integer")


def _optional_int(line: Mapping[str, Any], key: str, where: str) -> None:
    if line.get(key) is not None:
        _int(line, key, where)


def _non_negative_int(value: object, name: str, where: str, prefix: str = "") -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _bad(where, f"{prefix}{name} must be a non-negative integer")


def _number(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    value = line.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(where, f"{prefix}{key} must be a number")


def _optional_number(line: Mapping[str, Any], key: str, where: str) -> None:
    if line.get(key) is not None:
        _number(line, key, where)


def _int_list(line: Mapping[str, Any], key: str, where: str, prefix: str = "") -> None:
    value = line.get(key)
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise _bad(where, f"{prefix}{key} must be a list of integers")
    if len(set(value)) != len(value):
        raise _bad(where, f"{prefix}{key} carries a duplicate integer")


def _number_map(line: Mapping[str, Any], key: str, where: str) -> None:
    value = line.get(key)
    if not isinstance(value, dict):
        raise _bad(where, f"{key} must be an object")
    for name, number in value.items():
        if not isinstance(name, str) or not name.isdigit():
            raise _bad(where, f"{key} has a non-integer asset key {name!r}")
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise _bad(where, f"{key}[{name}] must be a number")


# --- projection ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionIndex:
    """Decision-only selection facts the detail cross-checks need.

    ``selected_by_date`` is the ordinary pool P; ``snapshot_iri`` and ``cycle_iri`` let the caller
    choose the naming (the design uses the configuration key; the pilot's existing selection graph
    still uses the old one).
    """

    cycle_by_date: Mapping[str, int]
    selected_by_date: Mapping[str, frozenset[int]]
    snapshot_iri: Callable[[str, int], rdflib.URIRef]
    cycle_iri: Callable[[str], rdflib.URIRef]


@dataclass(frozen=True)
class EventContext:
    """Everything the detail projector needs from the m018/manifest side."""

    label: str
    window: str
    configuration: str
    graph: str
    book_iri: rdflib.URIRef
    book_code: str
    assets: Mapping[str, object]
    asset_tickers: Mapping[int, str]
    alerts: Mapping[tuple[str, int, str], rdflib.URIRef]
    selection: SelectionIndex
    rebalance_by_date: Mapping[str, rdflib.URIRef]
    rankings_by_date: Mapping[str, frozenset[int]] = field(default_factory=dict)


@dataclass
class DetailBatch:
    """Triples and counts produced by one detail file; the caller merges them into its graphs."""

    graph: str
    triples: list[tuple[rdflib.Node, rdflib.Node, rdflib.Node]] = field(default_factory=list)
    individuals: Counter[str] = field(default_factory=Counter)
    rows: Counter[str] = field(default_factory=Counter)
    unlinked_assets: Counter[str] = field(default_factory=Counter)

    def individual(self, iri: rdflib.URIRef, rdf_type: str) -> None:
        self.add(iri, RDF.type, KG[rdf_type])
        self.individuals[rdf_type] += 1

    def add(self, subject: rdflib.Node, predicate: rdflib.Node, value: rdflib.Node) -> None:
        self.triples.append((subject, predicate, value))

    def triples_by_class(self) -> Counter[str]:
        types = {
            subject: value
            for subject, predicate, value in self.triples
            if predicate == RDF.type and isinstance(value, rdflib.URIRef)
        }
        counts: Counter[str] = Counter()
        for subject, _, _ in self.triples:
            kind = types.get(subject)
            if kind is not None:
                counts[str(kind).rsplit("#", 1)[-1]] += 1
        return counts


def build_detail_batch(detail: DetailFile, context: EventContext) -> DetailBatch:
    """Project one validated detail file into the configuration-keyed graph."""
    batch = DetailBatch(context.graph)
    batch.rows["detail_lines"] = detail.lines
    if context.configuration == "SYSTEM_WITH_HIERARCHY":
        _decisions(detail, context, batch)
        _retention_from_decisions(detail, context, batch)
    elif context.configuration == "SYSTEM_WITHOUT_HIERARCHY":
        if detail.decisions or detail.stops:
            raise DetailError(
                f"{detail.path}: the without-hierarchy detail may only carry retention_decision lines"
            )
        _retention_lines(detail, context, batch)
    else:
        raise DetailError(
            f"{detail.path}: configuration {context.configuration!r} has no detail events"
        )
    _stops(detail, context, batch)
    _replacements(detail, context, batch)
    _memory(detail, context, batch)
    return batch


def _decisions(detail: DetailFile, context: EventContext, batch: DetailBatch) -> None:
    if not detail.decisions:
        raise DetailError(f"{detail.path}: the with-hierarchy detail has no decision lines")
    first = min(str(line["date"]) for line in detail.decisions)
    for line in detail.decisions:
        date = str(line["date"])
        _cycle(context, date)
        selected = _selected(context, date)
        retained = line["retention"]["retained"]
        retained_ids = {int(item["asset_id"]) for item in retained}
        candidate_ids = [int(item) for item in line["candidate_ids"]]
        refilled = [
            asset for asset in candidate_ids if asset not in selected and asset not in retained_ids
        ]
        blocked = [int(item) for item in line["blocked"]]
        pool_size = int(line["retention"]["pool_size"])
        if pool_size != len(selected):
            raise DetailError(
                f"{detail.path}: decision {date}: retention.pool_size {pool_size} differs from "
                f"the selection pool {len(selected)}"
            )
        expected_candidate = len(selected) + len(retained)
        if len(candidate_ids) != expected_candidate:
            raise DetailError(
                f"{detail.path}: decision {date}: candidate_set {len(candidate_ids)} differs from "
                f"pool {len(selected)} + retained {len(retained)} = {expected_candidate}"
            )
        if len(blocked) != len(_alert_keys(context, date, "L1_BP_STOP_BLOCKED")):
            raise DetailError(
                f"{detail.path}: decision {date}: blocked count {len(blocked)} differs from the "
                "loaded L1_BP_STOP_BLOCKED alerts"
            )
        iri = KG[f"Decision_{context.label}_{context.window}_{_slug(context)}_{date}"]
        batch.individual(iri, "DecisionEvent")
        batch.add(iri, KG.decisionOfBook, context.book_iri)
        batch.add(iri, KG.decisionDate, _date_lit(date))
        batch.add(iri, KG.filterState, _bool_lit(bool(line["filter"])))
        batch.add(iri, KG.filterDecisionDate, _date_lit(str(line["filter_decision"])))
        batch.add(iri, KG.coreWeightInForce, _dec_lit(line["core_weight_in_force"]))
        batch.add(iri, KG.exposureScale, _dec_lit(line["scale"]))
        batch.add(iri, KG.candidatePoolSize, _int_lit(len(selected)))
        batch.add(iri, KG.candidateSetSize, _int_lit(len(candidate_ids)))
        batch.add(iri, KG.blockedCount, _int_lit(len(blocked)))
        batch.add(iri, KG.retainedCountOnDecision, _int_lit(len(retained)))
        batch.add(iri, KG.selectionCycle, context.selection.cycle_iri(date))
        batch.add(iri, KG.bookRebalance, _rebalance(context, date))
        batch.add(iri, KG.knowledgeDate, _date_lit(date))
        for asset in refilled:
            _link_asset(batch, iri, KG.refilledCandidate, asset, context, "DecisionEvent")
        if date == first:
            _formation(line, iri, context, batch)


def _formation(
    line: Mapping[str, Any], decision: rdflib.URIRef, context: EventContext, batch: DetailBatch
) -> None:
    target = line.get("target")
    if not isinstance(target, dict):
        raise DetailError(f"{context.label}/{context.window}: the first decision has no target")
    for raw_asset, weight in target.items():
        asset = int(raw_asset)
        iri = KG[
            f"FormationTarget_{context.label}_{context.window}_{_slug(context)}_{line['date']}_{asset}"
        ]
        batch.individual(iri, "FormationTarget")
        batch.add(iri, KG.targetOfDecision, decision)
        _link_asset(batch, iri, KG.targetAsset, asset, context, "FormationTarget")
        batch.add(iri, KG.formationTargetWeight, _dec_lit(weight))


def _retention_from_decisions(
    detail: DetailFile, context: EventContext, batch: DetailBatch
) -> None:
    for line in detail.decisions:
        date = str(line["date"])
        retention = line["retention"]
        iri = _retention_iri(context, date)
        _retention_common(
            iri,
            date,
            retention,
            context,
            batch,
            decision=KG[f"Decision_{context.label}_{context.window}_{_slug(context)}_{date}"],
        )
        for item in retention["retained"]:
            _hold(iri, date, item, context, batch)
        for item in retention["rejected"]:
            _rejection(iri, date, item, context, batch)
        for asset in retention["counter_dropped"]:
            _link_asset(
                batch, iri, KG.counterDroppedAsset, int(asset), context, "RetentionDecision"
            )
    if detail.retention_decisions and any(
        str(line.get("arm")) == context.book_code for line in detail.retention_decisions
    ):
        raise DetailError(
            f"{detail.path}: with-hierarchy retention comes from the decision lines; "
            f"a {context.book_code} retention_decision line is a duplicate"
        )


def _retention_lines(detail: DetailFile, context: EventContext, batch: DetailBatch) -> None:
    loaded = [line for line in detail.retention_decisions if str(line["arm"]) == context.book_code]
    if len(loaded) != len(detail.retention_decisions):
        raise DetailError(
            f"{detail.path}: retention_decision arm differs from the manifest book {context.book_code!r}"
        )
    for line in loaded:
        date = str(line["date"])
        iri = _retention_iri(context, date)
        _retention_common(iri, date, line, context, batch, decision=None)
        for item in line["retained"]:
            _hold(iri, date, item, context, batch)
        for item in line["rejected"]:
            _rejection(iri, date, item, context, batch)
        for asset in line["counter_dropped"]:
            _link_asset(
                batch, iri, KG.counterDroppedAsset, int(asset), context, "RetentionDecision"
            )


def _retention_iri(context: EventContext, date: str) -> rdflib.URIRef:
    return KG[f"Retention_{context.label}_{context.window}_{_slug(context)}_{date}"]


def _retention_common(  # noqa: PLR0913 -- one explicit keyword-only decision
    iri: rdflib.URIRef,
    date: str,
    retention: Mapping[str, Any],
    context: EventContext,
    batch: DetailBatch,
    *,
    decision: rdflib.URIRef | None,
) -> None:
    batch.individual(iri, "RetentionDecision")
    batch.add(iri, KG.retentionOfBook, context.book_iri)
    if decision is not None:
        batch.add(iri, KG.retentionOfDecision, decision)
    batch.add(iri, KG.retentionDate, _date_lit(date))
    batch.add(iri, KG.poolSize, _int_lit(retention["pool_size"]))
    batch.add(iri, KG.heldOutsidePoolCount, _int_lit(len(retention["held_outside"])))
    batch.add(iri, KG.retainedCount, _int_lit(len(retention["retained"])))
    batch.add(iri, KG.rejectedCount, _int_lit(len(retention["rejected"])))
    batch.add(iri, KG.counterDroppedCount, _int_lit(len(retention["counter_dropped"])))
    batch.add(iri, KG.keptCount, _int_lit(len(retention["kept"])))
    batch.add(iri, KG.keptWeight, _dec_lit(retention["kept_weight"]))
    batch.add(iri, KG.candidateSetSize, _int_lit(retention["candidate_size"]))
    batch.add(iri, KG.maxDecisions, _int_lit(retention.get("max_decisions", 3)))
    batch.add(iri, KG.retentionEnabled, _bool_lit(bool(retention.get("enabled", True))))
    batch.add(iri, KG.knowledgeDate, _date_lit(date))


def _hold(
    retention: rdflib.URIRef,
    date: str,
    item: Mapping[str, Any],
    context: EventContext,
    batch: DetailBatch,
) -> None:
    asset = int(item["asset_id"])
    iri = KG[f"RetentionHold_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}"]
    batch.individual(iri, "RetentionHold")
    batch.add(iri, KG.holdOfDecision, retention)
    _link_asset(batch, iri, KG.retainedAsset, asset, context, "RetentionHold")
    batch.add(iri, KG.retentionCounter, _int_lit(item["counter"]))
    batch.add(iri, KG.rankingSnapshot, context.selection.snapshot_iri(date, asset))


def _rejection(
    retention: rdflib.URIRef,
    date: str,
    item: Mapping[str, Any],
    context: EventContext,
    batch: DetailBatch,
) -> None:
    asset = int(item["asset_id"])
    iri = KG[f"RetentionRejection_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}"]
    batch.individual(iri, "RetentionRejection")
    batch.add(iri, KG.rejectionOfDecision, retention)
    _link_asset(batch, iri, KG.rejectedAsset, asset, context, "RetentionRejection")
    batch.add(iri, KG.rejectionCause, rdflib.Literal(str(item["cause"])))
    batch.add(iri, KG.retentionCounter, _int_lit(item["counter"]))
    batch.add(iri, KG.rankingSnapshot, context.selection.snapshot_iri(date, asset))


def _stops(  # noqa: C901, PLR0912 -- one branch per optional stop field
    detail: DetailFile, context: EventContext, batch: DetailBatch
) -> None:
    for line in detail.stops:
        date = str(line["date"])
        asset = int(line["asset_id"])
        _one_alert(context, detail, date, asset, "L1_BP_STOP")
        iri = _stop_iri(context, date, asset)
        batch.individual(iri, "StopEvent")
        batch.add(iri, KG.stopOfBook, context.book_iri)
        batch.add(iri, KG.stopDate, _date_lit(date))
        _link_asset(batch, iri, KG.stoppedAsset, asset, context, "StopEvent")
        batch.add(iri, KG.stopWeightBefore, _dec_lit(line["weight_before"]))
        batch.add(iri, KG.filterState, _bool_lit(bool(line["filter"])))
        batch.add(iri, KG.filterDecisionDate, _date_lit(str(line["filter_decision"])))
        batch.add(iri, KG.exposureScale, _dec_lit(line["scale"]))
        batch.add(iri, KG.rhoW0, _dec_lit(line["rho_w0"]))
        batch.add(iri, KG.rho, _dec_lit(line["rho"]))
        batch.add(iri, KG.chooser, rdflib.Literal(str(line["chooser"])))
        batch.add(iri, KG.cashLeft, _dec_lit(line["cash_left"]))
        batch.add(iri, KG.portfolioCheckPassed, _bool_lit(bool(line["portfolio_check"]["passed"])))
        batch.add(iri, KG.knowledgeDate, _date_lit(date))
        if line.get("cause") is not None:
            batch.add(iri, KG.stopCashCause, rdflib.Literal(str(line["cause"])))
        for key, prop in (
            ("eligible", "eligibleCount"),
            ("zone_evaluated", "zoneEvaluated"),
            ("zone_pass", "zonePass"),
        ):
            if line.get(key) is not None:
                batch.add(iri, KG[prop], _int_lit(line[key]))
        for key, prop in (("a_star", "aStar"), ("size_fraction", "sizeFraction")):
            if line.get(key) is not None:
                batch.add(iri, KG[prop], _dec_lit(line[key]))
        if line.get("weight_after_e3") is not None:
            batch.add(iri, KG.weightAfterE3, _dec_lit(line["weight_after_e3"]))
        if line.get("rho_delta") is not None:
            for key, prop in (
                ("min", "rhoDeltaMin"),
                ("median", "rhoDeltaMedian"),
                ("max", "rhoDeltaMax"),
            ):
                batch.add(iri, KG[prop], _dec_lit(line["rho_delta"][key]))
        chosen = line["chosen"]
        if chosen.get("cash") is True:
            batch.add(iri, KG.chosenCash, _bool_lit(True))
        else:
            menu = line.get("menu") or []
            position = next(
                (
                    index
                    for index, option in enumerate(menu, 1)
                    if int(option["asset_id"]) == int(chosen["asset_id"])
                ),
                None,
            )
            if position is None:
                raise DetailError(
                    f"{detail.path}: stop {date}/{asset}: the chosen asset is not in its menu"
                )
            option_iri = _option_iri(context, date, asset, position)
            batch.add(iri, KG.chosenOption, option_iri)
        menu = line.get("menu") or []
        for position, option in enumerate(menu, 1):
            _option_node(context, batch, date, asset, position, option)
        if line.get("eligible_counts") is not None:
            _summary(context, batch, date, asset, line["eligible_counts"])


def _summary(
    context: EventContext,
    batch: DetailBatch,
    date: str,
    asset: int,
    counts: Mapping[str, Any],
) -> None:
    iri = KG[f"StopSummary_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}"]
    batch.individual(iri, "StopRejectionSummary")
    batch.add(iri, KG.summaryOfStop, _stop_iri(context, date, asset))
    for key, value in counts.items():
        if key == "zone_evaluated" or value == 0:
            continue
        prop = _REJECTION_PROPERTIES.get(key)
        if prop is None:
            raise DetailError(f"stop {date}/{asset}: unknown rejection cause {key!r}")
        batch.add(iri, KG[prop], _int_lit(value))


def _option_node(  # noqa: PLR0913, PLR0917 -- the menu fields are explicit
    context: EventContext,
    batch: DetailBatch,
    date: str,
    asset: int,
    position: int,
    option: Mapping[str, Any],
) -> rdflib.URIRef:
    iri = _option_iri(context, date, asset, position)
    batch.individual(iri, "DestinationOption")
    batch.add(iri, KG.optionOfStop, _stop_iri(context, date, asset))
    _link_asset(batch, iri, KG.optionAsset, int(option["asset_id"]), context, "DestinationOption")
    batch.add(iri, KG.optionIsSpy, _bool_lit(bool(option["is_spy"])))
    batch.add(iri, KG.optionRho, _dec_lit(option["rho"]))
    batch.add(iri, KG.optionR, _dec_lit(option["R"]))
    batch.add(iri, KG.optionBeta, _dec_lit(option["beta"]))
    batch.add(iri, KG.optionRank, _int_lit(option["rank"]))
    batch.add(iri, KG.optionScore, _dec_lit(option["score"]))
    batch.add(iri, KG.optionSector, _int_lit(option["sector"]))
    batch.add(iri, KG.optionSizeFraction, _dec_lit(option["size_fraction"]))
    batch.add(iri, KG.optionWeight, _dec_lit(option["weight"]))
    batch.add(iri, KG.menuPosition, _int_lit(position))
    return iri


def _replacements(detail: DetailFile, context: EventContext, batch: DetailBatch) -> None:
    purchases: dict[int, rdflib.URIRef] = {}
    for line in detail.replacement_bought:
        date = str(line["order_date"])
        asset = int(line["asset_id"])
        stop = _stop_for_replacement(context, detail, date, asset)
        iri = KG[f"Replacement_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}"]
        purchases[asset] = iri
        batch.individual(iri, "ReplacementPurchase")
        batch.add(iri, KG.purchaseOfStop, stop)
        _link_asset(batch, iri, KG.replacementAsset, asset, context, "ReplacementPurchase")
        batch.add(iri, KG.orderDate, _date_lit(date))
        batch.add(iri, KG.replacementExecutionDate, _date_lit(str(line["execution_date"])))
        batch.add(iri, KG.machineEntrySession, _date_lit(str(line["machine_entry_session"])))
        batch.add(iri, KG.replacementWeight, _dec_lit(line["weight"]))
        batch.add(iri, KG.sizeFraction, _dec_lit(line["size_fraction"]))
        batch.add(iri, KG.replacementRank, _int_lit(line["rank"]))
        batch.add(iri, KG.rankBucket, rdflib.Literal(str(line["bucket"])))
        batch.add(iri, KG.filterState, _bool_lit(bool(line["filter"])))
        batch.add(iri, KG.filterDecisionDate, _date_lit(str(line["filter_decision"])))
    for line in detail.replacement_checks:
        asset = int(line["asset_id"])
        purchase = purchases.get(asset)
        if purchase is None:
            raise DetailError(
                f"{detail.path}: replacement_check {line['date']}/{asset} has no purchase"
            )
        iri = KG[
            f"ReplacementCheck_{context.label}_{context.window}_{_slug(context)}_{line['date']}_{asset}"
        ]
        batch.individual(iri, "ReplacementCheck")
        batch.add(iri, KG.checkOfPurchase, purchase)
        batch.add(iri, KG.checkDate, _date_lit(str(line["date"])))
        batch.add(iri, KG.candidate, _bool_lit(bool(line["candidate"])))
        batch.add(iri, KG.kept, _bool_lit(bool(line["kept"])))
    for line in detail.replacement_stopped:
        asset = int(line["asset_id"])
        date = str(line["date"])
        purchase = purchases.get(asset)
        if purchase is None:
            raise DetailError(f"{detail.path}: replacement_stopped {date}/{asset} has no purchase")
        _one_alert(context, detail, date, asset, "L1_BP_STOP")
        batch.add(purchase, KG.replacementStoppedBy, _stop_iri(context, date, asset))


@dataclass
class _Episode:
    asset: int
    since: str
    kind: str
    release: str | None = None
    cause: str | None = None


def _memory(detail: DetailFile, context: EventContext, batch: DetailBatch) -> None:
    """One :StopMemory per episode, including decision-close episodes, plus the complete control rule."""
    episodes = [_Episode(int(line["asset_id"]), str(line["date"]), "stop") for line in detail.stops]
    blocked = {(str(line["date"]), int(line["asset_id"])) for line in detail.blocked}
    _add_decision_close_episodes(detail, context, episodes, blocked)
    _derive_releases(detail, context, episodes, blocked)
    _enforce_no_overlap(detail, episodes)
    _memory_control(detail, context, episodes, blocked)
    batch.rows["memory_episodes_stop"] = sum(1 for item in episodes if item.kind == "stop")
    batch.rows["memory_episodes_decision_close"] = sum(
        1 for item in episodes if item.kind == "decision_close"
    )
    for episode in sorted(episodes, key=lambda item: (item.since, item.asset)):
        iri = _memory_iri(context, episode.asset, episode.since)
        batch.individual(iri, "StopMemory")
        batch.add(iri, KG.memoryOfBook, context.book_iri)
        _link_asset(batch, iri, KG.memoryAsset, episode.asset, context, "StopMemory")
        batch.add(iri, KG.memorySince, _date_lit(episode.since))
        batch.add(iri, KG.memoryStartKind, rdflib.Literal(episode.kind))
        if episode.release is not None:
            batch.add(iri, KG.memoryReleasedOn, _date_lit(episode.release))
            batch.add(iri, KG.memoryReleaseCause, rdflib.Literal(str(episode.cause)))


def _memory_iri(context: EventContext, asset: int, since: str) -> rdflib.URIRef:
    return KG[f"StopMemory_{context.label}_{context.window}_{_slug(context)}_{asset}_{since}"]


def _active(episode: _Episode, date: str) -> bool:
    return episode.since <= date and (episode.release is None or episode.release >= date)


def _add_decision_close_episodes(
    detail: DetailFile,
    context: EventContext,
    episodes: list[_Episode],
    blocked: set[tuple[str, int]],
) -> None:
    """A blocked asset with no open episode starts a decision_close episode at that date."""
    changed = True
    while changed:
        changed = False
        _derive_releases(detail, context, episodes, blocked)
        for date in sorted(context.rankings_by_date):
            for asset in sorted(asset for day, asset in blocked if day == date):
                if any(item.asset == asset and _active(item, date) for item in episodes):
                    continue
                episodes.append(_Episode(asset, date, "decision_close"))
                changed = True


def _derive_releases(
    detail: DetailFile,
    context: EventContext,
    episodes: list[_Episode],
    blocked: set[tuple[str, int]],
) -> None:
    for episode in episodes:
        later = [
            item.since
            for item in episodes
            if item.asset == episode.asset and item.since > episode.since
        ]
        next_start = min(later) if later else None
        price = sorted(
            str(item["date"])
            for item in detail.reentry
            if int(item["asset_id"]) == episode.asset
            and str(item["date"]) >= episode.since
            and (next_start is None or str(item["date"]) < next_start)
        )
        ranking = sorted(
            date
            for date in context.rankings_by_date
            if date > episode.since
            and (next_start is None or date < next_start)
            and (date, episode.asset) not in blocked
            and episode.asset not in context.rankings_by_date[date]
        )
        candidates: list[tuple[str, str]] = []
        if price:
            candidates.append((price[0], "price"))
        if ranking:
            candidates.append((ranking[0], "not_ranked"))
        episode.release, episode.cause = min(candidates) if candidates else (None, None)


def _enforce_no_overlap(detail: DetailFile, episodes: Sequence[_Episode]) -> None:
    by_asset: dict[int, list[_Episode]] = defaultdict(list)
    for episode in episodes:
        by_asset[episode.asset].append(episode)
    for asset, items in by_asset.items():
        ordered = sorted(items, key=lambda item: item.since)
        for previous, current in pairwise(ordered):
            if previous.release is None or previous.release >= current.since:
                raise DetailError(
                    f"{detail.path}: overlapping memory episodes for asset {asset}: "
                    f"{previous.since} releases {previous.release}, next starts {current.since}"
                )


def _memory_control(
    detail: DetailFile,
    context: EventContext,
    episodes: Sequence[_Episode],
    blocked: set[tuple[str, int]],
) -> None:
    """At every decision, memory splits exactly into price + ranking releases + blocked."""
    for date in sorted(context.rankings_by_date):
        active = {item.asset for item in episodes if _active(item, date)}
        price = {item.asset for item in episodes if item.release == date and item.cause == "price"}
        ranking = {
            item.asset for item in episodes if item.release == date and item.cause == "not_ranked"
        }
        blocked_today = {asset for day, asset in blocked if day == date}
        parts = price | ranking | blocked_today
        if parts != active or price & ranking or price & blocked_today or ranking & blocked_today:
            missing = sorted(active - parts)
            extra = sorted(parts - active)
            overlap = sorted(
                (price & ranking) | (price & blocked_today) | (ranking & blocked_today)
            )
            raise DetailError(
                f"{detail.path}: stop-memory control fails at {date}: missing {missing}, "
                f"extra {extra}, overlap {overlap}"
            )


def _stop_for_replacement(
    context: EventContext, detail: DetailFile, order_date: str, asset: int
) -> rdflib.URIRef:
    matches = [
        line
        for line in detail.stops
        if str(line["date"]) == order_date
        and isinstance(line["chosen"], dict)
        and line["chosen"].get("cash") is not True
        and int(line["chosen"].get("asset_id", -1)) == asset
    ]
    if len(matches) != 1:
        raise DetailError(
            f"{detail.path}: replacement {order_date}/{asset} matches {len(matches)} stops, expected 1"
        )
    return _stop_iri(context, order_date, int(matches[0]["asset_id"]))


def _one_alert(
    context: EventContext, detail: DetailFile, date: str, asset: int, rule: str
) -> rdflib.URIRef:
    try:
        return context.alerts[(date, asset, rule)]
    except KeyError:
        raise DetailError(f"{detail.path}: {date}/{asset} matches no loaded {rule} alert") from None


def _alert_keys(context: EventContext, date: str, rule: str) -> list[rdflib.URIRef]:
    return [
        iri
        for (alert_date, _asset, alert_rule), iri in context.alerts.items()
        if alert_date == date and alert_rule == rule
    ]


def _cycle(context: EventContext, date: str) -> int:
    try:
        return context.selection.cycle_by_date[date]
    except KeyError:
        raise DetailError(f"decision {date}: no selection cycle for that date") from None


def _selected(context: EventContext, date: str) -> frozenset[int]:
    try:
        return context.selection.selected_by_date[date]
    except KeyError:
        raise DetailError(f"decision {date}: no selected pool for that date") from None


def _rebalance(context: EventContext, date: str) -> rdflib.URIRef:
    try:
        return context.rebalance_by_date[date]
    except KeyError:
        raise DetailError(f"decision {date}: no loaded BookRebalance for that date") from None


def _stop_iri(context: EventContext, date: str, asset: int) -> rdflib.URIRef:
    return KG[f"Stop_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}"]


def _option_iri(context: EventContext, date: str, asset: int, position: int) -> rdflib.URIRef:
    return KG[f"Option_{context.label}_{context.window}_{_slug(context)}_{date}_{asset}_{position}"]


def _slug(context: EventContext) -> str:
    return configuration_slug(context.configuration)


def _link_asset(  # noqa: PLR0913, PLR0917 -- the call sites read better with names
    batch: DetailBatch,
    subject: rdflib.URIRef,
    predicate: rdflib.URIRef,
    asset: int,
    context: EventContext,
    kind: str,
) -> None:
    ticker = context.asset_tickers.get(asset)
    if ticker is None:
        raise DetailError(f"{kind}: engine asset_id {asset} has no ticker")
    if ticker in context.assets:
        batch.add(subject, predicate, KG[ticker])
    else:
        batch.unlinked_assets[kind] += 1


def _date_lit(value: object) -> rdflib.Literal:
    return rdflib.Literal(str(value), datatype=XSD.date)


def _int_lit(value: object) -> rdflib.Literal:
    return rdflib.Literal(str(int(str(value))), datatype=XSD.integer)


def _dec_lit(value: object) -> rdflib.Literal:
    return rdflib.Literal(str(value), datatype=XSD.decimal)


def _bool_lit(value: bool) -> rdflib.Literal:
    return rdflib.Literal("true" if value else "false", datatype=XSD.boolean)


class _Source(Protocol):
    """The one method this module needs from ``FinancialSource``."""

    def execute(self, sql: str, parameters: Sequence[object] = ...) -> Any: ...


def read_asset_tickers(source: _Source) -> dict[int, str]:
    """The engine asset id -> ticker map; no price or PII is read."""
    rows = source.execute("SELECT id, ticker FROM assets ORDER BY id").fetchall()
    return {int(row[0]): str(row[1]) for row in rows}


def selection_index(
    source: _Source,
    label: str,
    window: str,
    configuration: str,
    decision_dates: Sequence[str],
) -> SelectionIndex:
    """Build the decision-only selection index from the engine DB, never from rankings.json."""
    cycle_by_date: dict[str, int] = {}
    selected_by_date: dict[str, frozenset[int]] = {}
    slug = configuration_slug(configuration)
    for date in decision_dates:
        cycles = source.execute(
            "SELECT id FROM cycle_run WHERE cycle_date = ? AND cycle_type = 'REPLAY' "
            "AND status = 'completed' ORDER BY id",
            (date,),
        ).fetchall()
        if len(cycles) != 1:
            raise DetailError(
                f"selection {label}/{window}: decision {date} has {len(cycles)} completed REPLAY "
                "cycles, expected one"
            )
        cycle_id = int(cycles[0][0])
        rows = source.execute(
            "SELECT asset_id FROM cycle_ranking WHERE cycle_run_id = ? AND selected = 1 "
            "ORDER BY asset_id",
            (cycle_id,),
        ).fetchall()
        cycle_by_date[date] = cycle_id
        selected_by_date[date] = frozenset(int(row[0]) for row in rows)

    def snapshot(date: str, asset: int) -> rdflib.URIRef:
        return KG[f"Snap_{label}_{window}_{slug}_{cycle_by_date[date]}_{asset}"]

    def cycle_iri(date: str) -> rdflib.URIRef:
        return KG[f"Cycle_{label}_{window}_{slug}_{cycle_by_date[date]}"]

    return SelectionIndex(cycle_by_date, selected_by_date, snapshot, cycle_iri)


def read_rankings(path: str | Path) -> dict[str, frozenset[int]]:
    """Read a run's ``rankings.json`` as decision date -> ranked engine asset ids.

    The file is used only for the stop-memory release derivation and the control rule; it is never
    projected. A malformed date or row stops the load.
    """
    rankings_path = Path(path)
    try:
        payload = json.loads(rankings_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DetailError(f"{rankings_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DetailError(f"{rankings_path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DetailError(f"{rankings_path}: rankings must be an object keyed by decision date")
    out: dict[str, frozenset[int]] = {}
    for date, item in payload.items():
        if not isinstance(date, str) or not _DATE.fullmatch(date):
            raise DetailError(f"{rankings_path}: {date!r} is not a decision date")
        rows = item.get("rows") if isinstance(item, dict) else item
        if not isinstance(rows, list):
            raise DetailError(f"{rankings_path}: {date}: rankings must carry a rows list")
        ids: set[int] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get("asset_id"), int):
                raise DetailError(f"{rankings_path}: {date}.rows[{index}] has no integer asset_id")
            ids.add(int(row["asset_id"]))
        out[date] = frozenset(ids)
    return out
