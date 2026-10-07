"""The boundary expectations for upstream's ``v_*`` views, loaded from one JSON file per view (T-162).

``view_expectations/<view>.json`` states what a view's rows must look like before the projection
reads them (``PLAN.md`` Work item 16, decided in ``SPEC.md`` §13 item 10): types, NULL rates,
ranges, formats, natural keys, row count, the D2 ordered pair, group means and the view's
quarantine cap. ``view_expectations/_source.json`` holds the one aggregate check on the database
itself. This module only parses and validates those files, strictly, so a typo fails at load and
not on the first real run. Running them over rows is T-163's job.

Column names are checked against :data:`projection.view_contract.VIEW_COLUMNS`, so the column list
is not repeated here. A column or a whole view upstream has not shipped yet is declared under
``pending_columns`` (or ``pending``) with the reason; once the pin gains it, the loader rejects the
stale marker, which is the prompt to move the rule over.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

from projection.view_contract import VIEW_COLUMNS

EXPECTATIONS_DIR = Path(__file__).resolve().parent / "view_expectations"
SOURCE_FILE = "_source.json"

TYPES = frozenset({"integer", "number", "string"})
FORMATS = frozenset({"utc_timestamp", "forensic_flags"})
OPS = frozenset({">", "=", ">=", "<", "<="})
NULL_POLICIES = frozenset({"fail", "skip"})

_VIEW_KEYS = {
    "view",
    "pending",
    "pending_columns",
    "keys",
    "row_count",
    "cap",
    "cap_reason",
    "types",
    "null_rate",
    "ranges",
    "formats",
    "ordered_pairs",
    "group_means",
}
_SOURCE_KEYS = {"schema_version_floor", "forbidden_cycle_types"}

Where = dict[str, tuple[Any, ...]]


class ExpectationError(ValueError):
    """An expectation file is malformed; the message lists every problem found in it."""


@dataclass(frozen=True)
class NullRate:
    column: str
    max: float | None  # None: the column is NULL on every row, by design
    until: str | None  # the upstream task that fills it, for an all-NULL column


@dataclass(frozen=True)
class Range:
    column: str
    min: float | None
    max: float | None
    where: Where


@dataclass(frozen=True)
class OrderedPair:
    left: str
    op: str
    right: str
    where: Where
    null: str  # "fail", or "skip": a NULL is skipped by design and counted
    until: str | None


@dataclass(frozen=True)
class GroupMean:
    column: str
    group_by: tuple[str, ...]
    target: float
    tolerance: float
    where: Where


@dataclass(frozen=True)
class ViewExpectation:
    view: str
    pending: str | None
    keys: tuple[tuple[str, ...], ...]
    row_count_min: int | None
    cap: float
    cap_reason: str | None
    types: Mapping[str, str]
    null_rates: tuple[NullRate, ...]
    ranges: tuple[Range, ...]
    formats: Mapping[str, str]
    ordered_pairs: tuple[OrderedPair, ...]
    group_means: tuple[GroupMean, ...]


@dataclass(frozen=True)
class SourceExpectation:
    schema_version_floor: int
    forbidden_cycle_types: tuple[str, ...]


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


class _Checker:
    """Collects problems for one file so a single load reports all of them."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.problems: list[str] = []
        self.allowed: set[str] = set()  # the columns a rule may name: pinned plus pending

    def bad(self, where: str, why: str) -> None:
        self.problems.append(f"{where}: {why}")

    def raise_if_any(self) -> None:
        if self.problems:
            raise ExpectationError(f"{self.name}: " + "; ".join(self.problems))

    def unknown_keys(self, where: str, data: Mapping[str, Any], allowed: set[str]) -> None:
        for key in sorted(set(data) - allowed):
            self.bad(where, f"unknown key {key!r}")

    def entries(self, data: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
        """The list of objects under ``key``, or ``[]`` (with a problem noted) if it is not one."""
        raw = data.get(key, [])
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            self.bad(key, "must be a list of objects")
            return []
        return raw

    def column(self, where: str, column: object) -> str:
        if not isinstance(column, str) or column not in self.allowed:
            self.bad(where, f"column {column!r} is neither pinned nor pending")
            return ""
        return column

    def where_clause(self, where: str, raw: object) -> Where:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            self.bad(where, "'where' must map a column to a list of values")
            return {}
        out: Where = {}
        for column, values in raw.items():
            self.column(f"{where}.where", column)
            if not (
                isinstance(values, list)
                and values
                and all(_text(v) or _is_number(v) for v in values)
            ):
                self.bad(
                    f"{where}.where.{column}", "must be a non-empty list of strings or numbers"
                )
                continue
            out[column] = tuple(values)
        return out


def _scope(chk: _Checker, name: str, data: Mapping[str, Any]) -> str | None:
    """Check the view's identity and which columns exist; returns the ``pending`` reason."""
    chk.unknown_keys("file", data, _VIEW_KEYS)
    if data.get("view") != name:
        chk.bad("view", f"must equal the file name {name!r}, got {data.get('view')!r}")

    pending = data.get("pending")
    if pending is not None and not _text(pending):
        chk.bad("pending", "must be the reason the view is not pinned yet")
        pending = None
    pinned = VIEW_COLUMNS.get(name)
    if pending is None and pinned is None:
        chk.bad("view", "is not in VIEW_COLUMNS; a view upstream has not shipped needs 'pending'")
    if pending is not None and pinned is not None:
        chk.bad("pending", "is stale: the view is pinned now, so drop the marker")

    pending_columns = data.get("pending_columns", {})
    if not isinstance(pending_columns, dict) or not all(
        _text(c) and _text(r) for c, r in pending_columns.items()
    ):
        chk.bad("pending_columns", "must map each not-yet-pinned column to its reason")
        pending_columns = {}
    for column in pending_columns:
        if pinned is not None and column in pinned:
            chk.bad("pending_columns", f"{column!r} is pinned now, so drop the marker")
    chk.allowed = set(pinned or ()) | set(pending_columns)
    return pending


def _keys(chk: _Checker, data: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    raw = data.get("keys", [])
    if not isinstance(raw, list) or not all(
        isinstance(k, list) and k and all(isinstance(c, str) for c in k) for k in raw
    ):
        chk.bad("keys", "must be a list of non-empty column lists")
        return ()
    return tuple(tuple(chk.column("keys", c) for c in key) for key in raw)


def _row_count(chk: _Checker, data: Mapping[str, Any]) -> int | None:
    raw = data.get("row_count")
    if raw is None:
        return None
    if (
        not isinstance(raw, dict)
        or set(raw) != {"min"}
        or not _is_int(raw["min"])
        or raw["min"] < 0
    ):
        chk.bad("row_count", "must be {'min': a non-negative integer}")
        return None
    return raw["min"]


def _cap(chk: _Checker, data: Mapping[str, Any]) -> tuple[float, str | None]:
    cap = data.get("cap")
    if not _is_number(cap) or not 0 <= cap <= 1:
        chk.bad("cap", "is required and must be a share between 0 and 1")
        return 0.0, None
    reason = data.get("cap_reason")
    if reason is not None and not _text(reason):
        chk.bad("cap_reason", "must be text")
    elif cap > 0 and reason is None:
        chk.bad("cap_reason", "is required when the cap is above 0: say why the view may lose rows")
    elif cap == 0 and reason is not None:
        chk.bad("cap_reason", "belongs to a cap above 0")
    return float(cap), reason


def _named(
    chk: _Checker, data: Mapping[str, Any], key: str, vocabulary: frozenset[str]
) -> dict[str, str]:
    """A ``column -> value`` map whose values come from ``vocabulary`` (types, formats)."""
    raw = data.get(key, {})
    if not isinstance(raw, dict):
        chk.bad(key, "must map a column to a value")
        return {}
    out: dict[str, str] = {}
    for column, value in raw.items():
        chk.column(key, column)
        if isinstance(value, str) and value in vocabulary:
            out[column] = value
        else:
            chk.bad(
                f"{key}.{column}", f"unknown value {value!r}, expected one of {sorted(vocabulary)}"
            )
    return out


def _null_rates(chk: _Checker, data: Mapping[str, Any]) -> tuple[NullRate, ...]:
    out: list[NullRate] = []
    for i, item in enumerate(chk.entries(data, "null_rate")):
        where = f"null_rate[{i}]"
        chk.unknown_keys(where, item, {"column", "max", "all_null", "until"})
        column = chk.column(where, item.get("column"))
        if item.get("all_null") is True:
            if "max" in item:
                chk.bad(where, "'all_null' and 'max' are exclusive")
            if not _text(item.get("until")):
                chk.bad(where, "an all-NULL column needs 'until': the task that fills it")
            out.append(NullRate(column, None, item.get("until")))
            continue
        limit = item.get("max")
        if "all_null" in item or not _is_number(limit) or not 0 <= limit <= 1:
            chk.bad(where, "needs 'max', a share between 0 and 1 (or 'all_null': true)")
            continue
        out.append(NullRate(column, float(limit), None))
    return tuple(out)


def _ranges(chk: _Checker, data: Mapping[str, Any]) -> tuple[Range, ...]:
    out: list[Range] = []
    for i, item in enumerate(chk.entries(data, "ranges")):
        where = f"ranges[{i}]"
        chk.unknown_keys(where, item, {"column", "min", "max", "where"})
        column = chk.column(where, item.get("column"))
        low, high = item.get("min"), item.get("max")
        if low is None and high is None:
            chk.bad(where, "needs 'min' or 'max'")
        if any(b is not None and not _is_number(b) for b in (low, high)):
            chk.bad(where, "'min' and 'max' must be numbers")
        elif low is not None and high is not None and low > high:
            chk.bad(where, "'min' is above 'max'")
        out.append(Range(column, low, high, chk.where_clause(where, item.get("where"))))
    return tuple(out)


def _ordered_pairs(chk: _Checker, data: Mapping[str, Any]) -> tuple[OrderedPair, ...]:
    out: list[OrderedPair] = []
    for i, item in enumerate(chk.entries(data, "ordered_pairs")):
        where = f"ordered_pairs[{i}]"
        chk.unknown_keys(where, item, {"left", "op", "right", "where", "null", "until"})
        left = chk.column(where, item.get("left"))
        right = chk.column(where, item.get("right"))
        op = item.get("op")
        if not (isinstance(op, str) and op in OPS):
            chk.bad(where, f"'op' must be one of {sorted(OPS)}")
        policy = item.get("null", "fail")
        if not (isinstance(policy, str) and policy in NULL_POLICIES):
            chk.bad(where, f"'null' must be one of {sorted(NULL_POLICIES)}")
        if policy == "skip" and not _text(item.get("until")):
            chk.bad(where, "skipping a NULL needs 'until': the task that fills it")
        clause = chk.where_clause(where, item.get("where"))
        out.append(OrderedPair(left, str(op), right, clause, str(policy), item.get("until")))
    return tuple(out)


def _group_means(chk: _Checker, data: Mapping[str, Any]) -> tuple[GroupMean, ...]:
    out: list[GroupMean] = []
    for i, item in enumerate(chk.entries(data, "group_means")):
        where = f"group_means[{i}]"
        chk.unknown_keys(where, item, {"column", "group_by", "target", "tolerance", "where"})
        column = chk.column(where, item.get("column"))
        raw_group = item.get("group_by")
        if not isinstance(raw_group, list) or not raw_group:
            chk.bad(where, "'group_by' must be a non-empty list of columns")
            raw_group = []
        group = tuple(chk.column(where, c) for c in raw_group)
        target, tolerance = item.get("target"), item.get("tolerance")
        if not _is_number(target):
            chk.bad(where, "'target' must be a number")
            target = 0.0
        if not _is_number(tolerance) or tolerance <= 0:
            chk.bad(
                where, "'tolerance' must be a positive number: a mean is never held to equality"
            )
            tolerance = 0.0
        clause = chk.where_clause(where, item.get("where"))
        out.append(GroupMean(column, group, float(target), float(tolerance), clause))
    return tuple(out)


def parse_view_expectation(name: str, data: Mapping[str, Any]) -> ViewExpectation:
    """Validate one view's file; raises :class:`ExpectationError` listing every problem."""
    chk = _Checker(name)
    pending = _scope(chk, name, data)
    cap, cap_reason = _cap(chk, data)
    parsed = ViewExpectation(
        view=name,
        pending=pending,
        keys=_keys(chk, data),
        row_count_min=_row_count(chk, data),
        cap=cap,
        cap_reason=cap_reason,
        types=_named(chk, data, "types", TYPES),
        null_rates=_null_rates(chk, data),
        ranges=_ranges(chk, data),
        formats=_named(chk, data, "formats", FORMATS),
        ordered_pairs=_ordered_pairs(chk, data),
        group_means=_group_means(chk, data),
    )
    chk.raise_if_any()
    return parsed


def load_source(directory: Path = EXPECTATIONS_DIR) -> SourceExpectation:
    """The aggregate check on the source database: the ``schema_version`` floor, no forbidden run type."""
    data = _read(directory / SOURCE_FILE)
    chk = _Checker(SOURCE_FILE)
    chk.unknown_keys("file", data, _SOURCE_KEYS)
    floor = data.get("schema_version_floor")
    if not _is_int(floor) or floor < 1:
        chk.bad("schema_version_floor", "must be a positive integer")
        floor = 0
    forbidden = data.get("forbidden_cycle_types")
    if not isinstance(forbidden, list) or not forbidden or not all(_text(t) for t in forbidden):
        chk.bad("forbidden_cycle_types", "must be a non-empty list of cycle types")
        forbidden = []
    chk.raise_if_any()
    return SourceExpectation(floor, tuple(forbidden))


def load_expectations(directory: Path = EXPECTATIONS_DIR) -> dict[str, ViewExpectation]:
    """Every view's expectations, keyed by view name.

    Each file must be a pinned view (or declare itself ``pending``), and every pinned view must
    have a file: a view with nothing said about it would be read unchecked.
    """
    loaded = {
        path.stem: parse_view_expectation(path.stem, _read(path))
        for path in sorted(directory.glob("*.json"))
        if path.name != SOURCE_FILE
    }
    missing = sorted(set(VIEW_COLUMNS) - set(loaded))
    if missing:
        raise ExpectationError(f"no expectation file for pinned view(s): {', '.join(missing)}")
    return loaded


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    except FileNotFoundError:
        raise ExpectationError(f"{path.name}: file not found") from None
    except json.JSONDecodeError as exc:
        raise ExpectationError(f"{path.name}: not valid JSON ({exc})") from None
    except _DuplicateKeyError as exc:
        raise ExpectationError(f"{path.name}: key {exc} appears twice in one object") from None
    if not isinstance(data, dict):
        raise ExpectationError(f"{path.name}: must be a JSON object")
    return data


class _DuplicateKeyError(Exception):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``json.loads`` keeps the last of two equal keys; a strict loader refuses them instead."""
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKeyError(repr(key))
        out[key] = value
    return out
