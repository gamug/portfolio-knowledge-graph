"""Run the boundary expectations over upstream's rows (T-163, ``PLAN.md`` Work item 16).

:func:`validate` takes the rows read from each ``v_*`` view and the expectations T-162 loads, and
returns the rows that may reach the triple builder plus a :class:`BoundaryReport`. The policy is
the one ``SPEC.md`` §13 item 10 records:

* a **source** or **aggregate** failure (schema floor, REPLAY run, row count, NULL rate, group
  mean, a column missing from the rows) has no row to drop, so the run stops;
* a **row-level** failure (type, range, format, duplicate key, ordered pair) quarantines the row
  and its group (:data:`CASCADES`), and the run stops if a view's quarantined share exceeds its
  cap (default 0);
* a row skipped by design (a NULL ``available_at`` on a cycle lane, before upstream's T-144) is
  counted per view and reason, never failed;
* a ``pending`` view or column is listed, so an inactive guard is visible.

A quarantined row is *late* if its target graph is dated by ingestion, its view has a natural key,
and the caller persists the late keys (``late_keys_path``) for the next run to re-read; otherwise it
is *lost*. ``validate`` only adds keys to that file; a key leaves it through :func:`mark_written`,
which the caller calls once the row is written to the store, so a failed write never loses one.
Re-reading those keys is T-031's, as is counting the rows T-151 and T-155 skip, through
:meth:`BoundaryReport.skip`. A re-read row must be merged into the read by its natural key, never
appended: a second copy of a row is a duplicate key, which quarantines both copies and, under the
default cap of 0, stops the run.

Nothing here reads a database except :func:`check_source`; rows are plain mappings, so the same
code runs over ``portfolio_common.db`` rows and over the synthetic rows of T-164.
"""

from __future__ import annotations

import json
import math
import operator
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, Protocol, TypeGuard

from projection.expectations import (
    OrderedPair,
    SourceExpectation,
    ViewExpectation,
    Where,
)

Row = Mapping[str, Any]
Key = tuple[Any, ...]

# Views whose rows go to an ingestion-dated graph (``docs/07``): ``view -> {column: values}``.
# Every other view, and any row outside the filter, targets a data-dated graph, so a quarantined
# row there is lost for that date.
INGESTION_DATED: dict[str, Where] = {
    "v_score_snapshot": {"score_type": ("SEMANTIC", "VALORIZATION", "TECHNICAL", "SECTOR")},
}

# Row-level cascades: a failing row of ``view`` takes the rows of ``target`` that share ``on``.
# ``v_cycle_ranking_component`` is pending, so its links apply once it is read.
CASCADES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "v_cycle_ranking": (("v_cycle_ranking_component", ("cycle_run_id", "asset_id")),),
    "v_cycle_ranking_component": (("v_cycle_ranking", ("cycle_run_id", "asset_id")),),
    "v_weight_scheme": (
        ("v_weight_component", ("cycle_run_id",)),
        ("v_cycle_ranking", ("cycle_run_id",)),
    ),
    "v_weight_component": (("v_weight_scheme", ("cycle_run_id",)),),
}

# ISO 8601 with a ``T`` separator and a UTC offset written ``+00:00`` (upstream's form) or ``Z``.
_UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)")
FORENSIC_FLAGS = frozenset(
    {
        "data_error_suspected",
        "negative_equity_buyback",
        "value_destroyer_sub_wacc",
        "severe_sbc_dilution",
    }
)


# Every ``Failure.check`` the runner may write. A new kind is added here (``Failure`` refuses any
# other name) and gets its passing and failing case in ``tests/test_boundary.py`` (T-164).
SOURCE_CHECKS = frozenset({"schema_version", "forbidden_cycle_type"})
VIEW_CHECKS = frozenset(
    {
        "missing_column",
        "row_count",
        "null_rate",
        "type",
        "range",
        "format",
        "unique",
        "ordered_pair",
        "group_mean",
    }
)
CASCADE = "cascade"  # not a check: the row was taken with a failing row of its group
CHECK_KINDS = SOURCE_CHECKS | VIEW_CHECKS | {CASCADE}


class Source(Protocol):
    """What :func:`check_source` needs of ``portfolio_common.db.Database``."""

    @property
    def schema_version(self) -> int: ...

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any: ...


@dataclass(frozen=True)
class Failure:
    """One failed check. ``key`` names the row for a row-level check, ``group`` the group for an
    aggregate one; neither is set for a view-wide check."""

    view: str
    check: str
    column: str | None
    detail: str
    key: Key | None = None
    group: Key | None = None
    # The failing row that started the cascade this row was taken in; None if the row failed itself.
    # On a later hop it is not the row this one was taken with: ``detail`` names that one.
    cascaded_from: str | None = None

    def __str__(self) -> str:
        where = f"{self.view}.{self.column}" if self.column else self.view
        scope = f" row {self.key}" if self.key is not None else ""
        scope += f" group {self.group}" if self.group is not None else ""
        cause = f" (cascade started by {self.cascaded_from})" if self.cascaded_from else ""
        return f"{where}{scope}: {self.check}: {self.detail}{cause}"

    def __post_init__(self) -> None:
        # A TypeError, not the ValueError ``validate`` raises for a caller's bad input: an unknown
        # kind is a bug in the runner.
        if self.check not in CHECK_KINDS:
            raise TypeError(
                f"unknown check kind {self.check!r}: add it to CHECK_KINDS with its test"
            )


@dataclass
class BoundaryReport:
    stopped: bool = False
    stop_reasons: list[str] = field(default_factory=list)
    aggregate_failures: list[Failure] = field(default_factory=list)
    quarantined: list[Failure] = field(default_factory=list)
    late: list[Failure] = field(default_factory=list)  # quarantined, re-read by the next run
    lost: list[Failure] = field(default_factory=list)  # quarantined, gone for that date
    skipped_by_design: Counter[tuple[str, str]] = field(default_factory=Counter)
    inactive: list[str] = field(default_factory=list)  # pending views and columns, with reasons
    # Row-level failures found in a run an aggregate failure stopped: reported, not quarantined.
    row_failures: list[Failure] = field(default_factory=list)
    # Late keys stored under key columns the view no longer uses: they can never match a row
    # again, so they are dropped from the key file and listed here instead of lingering.
    stale_late_keys: list[str] = field(default_factory=list)

    def skip(self, view: str, reason: str, n: int = 1) -> None:
        """Count ``n`` rows of ``view`` skipped by design (T-031, T-151, T-155): never failed."""
        if n < 1:
            raise ValueError(f"skip count must be at least 1, got {n}")
        self.skipped_by_design[(view, reason)] += n

    def summary(self) -> str:
        lines = [f"stopped: {self.stopped}"]
        lines += [f"  stop: {r}" for r in self.stop_reasons]
        lines += [f"  aggregate: {f}" for f in self.aggregate_failures]
        lines += [f"  late: {f}" for f in self.late]
        lines += [f"  lost: {f}" for f in self.lost]
        lines += [
            f"  skipped by design: {v} / {r}: {n}" for (v, r), n in self.skipped_by_design.items()
        ]
        lines += [f"  inactive: {i}" for i in self.inactive]
        lines += [f"  row (not quarantined, run stopped): {f}" for f in self.row_failures]
        lines += [f"  stale late key: {k}" for k in self.stale_late_keys]
        return "\n".join(lines)


class BoundaryError(RuntimeError):
    """The run must stop; ``report`` says why, naming the view, the column and the row or group."""

    def __init__(self, report: BoundaryReport) -> None:
        super().__init__(report.summary())
        self.report = report


@dataclass(frozen=True)
class BoundaryResult:
    rows: dict[str, list[Row]]
    report: BoundaryReport


# --- the source check --------------------------------------------------------------------------


def check_source(db: Source, expected: SourceExpectation) -> list[Failure]:
    """The aggregate check on the database itself: the ``schema_version`` floor, no forbidden run."""
    failures: list[Failure] = []
    version = db.schema_version
    if version < expected.schema_version_floor:
        failures.append(
            Failure(
                "source",
                "schema_version",
                None,
                f"{version} is below the floor {expected.schema_version_floor}",
            )
        )
    marks = ", ".join("?" for _ in expected.forbidden_cycle_types)
    found = db.execute(
        f"SELECT cycle_type, COUNT(*) FROM v_cycle_run WHERE cycle_type IN ({marks}) "  # noqa: S608 -- only "?" placeholders are interpolated
        "GROUP BY cycle_type",
        expected.forbidden_cycle_types,
    ).fetchall()
    failures += [
        Failure(
            "v_cycle_run",
            "forbidden_cycle_type",
            "cycle_type",
            f"{n} run(s) of type {kind}",
        )
        for kind, n in found
    ]
    return failures


# --- value predicates --------------------------------------------------------------------------


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_string(value: object) -> bool:
    return isinstance(value, str)


_TYPE_TESTS: dict[str, Callable[[object], bool]] = {
    "integer": _is_integer,
    "number": _is_number,
    "string": _is_string,
}


def _when(value: object) -> datetime | None:
    """A date or an ISO timestamp as an aware UTC datetime; naive values are taken as UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _forensic_flags_ok(value: object) -> bool:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return False
    return (
        isinstance(value, dict)
        and set(value) == FORENSIC_FLAGS
        and all(isinstance(v, bool) for v in value.values())
    )


def _format_ok(kind: str, value: object) -> bool:
    if kind == "utc_timestamp":
        return (
            isinstance(value, str)
            and _UTC_TIMESTAMP.fullmatch(value) is not None
            and _when(value) is not None
        )
    return _forensic_flags_ok(value)


_OPS: dict[str, Callable[[datetime, datetime], bool]] = {
    ">": operator.gt,
    "=": operator.eq,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def _matches(row: Row, where: Where) -> bool:
    return all(row.get(column) in values for column, values in where.items())


def _key(row: Row, columns: Sequence[str]) -> Key:
    return tuple(row.get(c) for c in columns)


# --- one view ----------------------------------------------------------------------------------


class _View:
    """The checks of one view over its rows, split into aggregate and per-row failures."""

    def __init__(self, exp: ViewExpectation, rows: Sequence[Row], report: BoundaryReport) -> None:
        self.exp = exp
        self.rows = rows
        self.report = report
        self.aggregate: list[Failure] = []
        self.by_row: dict[int, list[Failure]] = defaultdict(list)  # row index -> failures
        self.row_key = exp.keys[0] if exp.keys else ()

    def _agg(self, check: str, column: str | None, detail: str, group: Key | None = None) -> None:
        self.aggregate.append(Failure(self.exp.view, check, column, detail, group=group))

    def key_of(self, index: int) -> Key:
        """The row's natural key, or its index in the read for a view that declares none."""
        return _key(self.rows[index], self.row_key) if self.row_key else (index,)

    def _row(self, index: int, check: str, column: str | None, detail: str) -> None:
        self.by_row[index].append(
            Failure(self.exp.view, check, column, detail, key=self.key_of(index))
        )

    def run(self) -> None:
        self._missing_columns()
        self._row_count()
        self._null_rates()
        self._types()
        self._ranges()
        self._formats()
        self._keys()
        self._ordered_pairs()
        self._group_means()

    def _present(self, column: str) -> bool:
        # The first row stands for all: rows from one SELECT share their columns. Synthetic rows
        # must do the same (``_missing_columns`` checks the named columns on that row too).
        return not self.rows or column in self.rows[0]

    def _named_columns(self) -> set[str]:
        exp = self.exp
        named = {c for key in exp.keys for c in key} | set(exp.types) | set(exp.formats)
        named |= {r.column for r in exp.null_rates} | {r.column for r in exp.ranges}
        named |= {c for p in exp.ordered_pairs for c in (p.left, p.right)}
        named |= {g.column for g in exp.group_means} | {
            c for g in exp.group_means for c in g.group_by
        }
        for where in [r.where for r in exp.ranges] + [p.where for p in exp.ordered_pairs]:
            named |= set(where)
        named |= {c for g in exp.group_means for c in g.where}
        return named - set(exp.pending_columns)

    def _missing_columns(self) -> None:
        """A column an expectation names must be in the rows; the rest of the pin may be unread."""
        if not self.rows:
            return
        for column in sorted(self._named_columns() - set(self.rows[0])):
            self._agg(
                "missing_column",
                column,
                "the rows do not carry a column the expectation names",
            )

    def _row_count(self) -> None:
        minimum = self.exp.row_count_min
        if minimum is not None and len(self.rows) < minimum:
            self._agg(
                "row_count",
                None,
                f"{len(self.rows)} row(s), expected at least {minimum}",
            )

    def _null_rates(self) -> None:
        total = len(self.rows)
        for rule in self.exp.null_rates:
            if not total or not self._present(rule.column):
                continue
            nulls = sum(1 for r in self.rows if r.get(rule.column) is None)
            if rule.max is None:
                if nulls < total:
                    self._agg(
                        "null_rate",
                        rule.column,
                        f"{total - nulls} row(s) hold a value; expected NULL on every row"
                        + (f" until {rule.until}" if rule.until else ""),
                    )
            elif nulls / total > rule.max:
                self._agg(
                    "null_rate",
                    rule.column,
                    f"NULL on {nulls}/{total} rows, over the {rule.max} limit",
                )

    def _types(self) -> None:
        for column, kind in self.exp.types.items():
            if not self._present(column):
                continue
            for i, row in enumerate(self.rows):
                value = row.get(column)
                if value is not None and not _TYPE_TESTS[kind](value):
                    self._row(i, "type", column, f"{value!r} is not {kind}")

    def _ranges(self) -> None:
        for rule in self.exp.ranges:
            if not self._present(rule.column):
                continue
            for i, row in enumerate(self.rows):
                value = row.get(rule.column)
                if value is None or not _matches(row, rule.where) or not _is_number(value):
                    continue  # NULL is the NULL-rate check's; a non-number is the type check's
                if (rule.min is not None and value < rule.min) or (
                    rule.max is not None and value > rule.max
                ):
                    self._row(
                        i,
                        "range",
                        rule.column,
                        f"{value!r} is outside [{rule.min}, {rule.max}]",
                    )

    def _formats(self) -> None:
        for column, kind in self.exp.formats.items():
            if not self._present(column):
                continue
            for i, row in enumerate(self.rows):
                value = row.get(column)
                if kind == "utc_timestamp" and value is None:
                    continue  # NULL is the NULL-rate check's
                if kind == "forensic_flags" and value is None:
                    continue  # NULL on every row today, by design
                if not _format_ok(kind, value):
                    self._row(i, "format", column, f"{value!r} is not a {kind}")

    def _keys(self) -> None:
        for columns in self.exp.keys:
            if not all(self._present(c) for c in columns):
                continue
            seen: defaultdict[Key, list[int]] = defaultdict(list)
            for i, row in enumerate(self.rows):
                key = _key(row, columns)
                if None not in key:  # a NULL key is the NULL-rate check's
                    seen[key].append(i)
            for key, indexes in seen.items():
                if len(indexes) > 1:
                    for i in indexes:
                        self._row(
                            i,
                            "unique",
                            ",".join(columns),
                            f"key {key} appears {len(indexes)} times",
                        )

    def _ordered_pairs(self) -> None:
        for pair in self.exp.ordered_pairs:
            if self._present(pair.left) and self._present(pair.right):
                for i, row in enumerate(self.rows):
                    if _matches(row, pair.where):
                        self._pair(i, row, pair)

    def _pair(self, index: int, row: Row, pair: OrderedPair) -> None:
        left, right = row.get(pair.left), row.get(pair.right)
        if left is None or right is None:
            if pair.null == "skip":
                until = f" until {pair.until}" if pair.until else ""
                self.report.skip(self.exp.view, f"{pair.left} is NULL{until}")
            else:
                self._row(
                    index,
                    "ordered_pair",
                    pair.left,
                    f"{pair.left} or {pair.right} is NULL",
                )
            return
        a, b = _when(left), _when(right)
        if a is None or b is None:
            self._row(
                index,
                "ordered_pair",
                pair.left,
                f"cannot read {left!r} / {right!r} as dates",
            )
        elif not _OPS[pair.op](a, b):
            self._row(
                index,
                "ordered_pair",
                pair.left,
                f"{left} {pair.op} {right} does not hold",
            )

    def _group_means(self) -> None:
        for rule in self.exp.group_means:
            if not self._present(rule.column) or not all(self._present(c) for c in rule.group_by):
                continue
            groups: defaultdict[Key, list[float]] = defaultdict(list)
            for row in self.rows:
                value = row.get(rule.column)
                if _matches(row, rule.where) and _is_number(value):
                    groups[_key(row, rule.group_by)].append(float(value))
            for group, values in groups.items():
                mean = sum(values) / len(values)
                if abs(mean - rule.target) > rule.tolerance:
                    self._agg(
                        "group_mean",
                        rule.column,
                        f"mean {mean:.2f} over {len(values)} row(s) is not within {rule.tolerance} of "
                        f"{rule.target} (grouped by {', '.join(rule.group_by)})",
                        group=group,
                    )


# --- the whole read path -----------------------------------------------------------------------


def validate(
    rows: Mapping[str, Sequence[Row]],
    expectations: Mapping[str, ViewExpectation],
    *,
    source_failures: Sequence[Failure] = (),
    late_keys_path: Path | None = None,
) -> BoundaryResult:
    """Check every view's rows; return the survivors and the report, or raise :class:`BoundaryError`.

    ``rows`` maps a view name to the rows read from it. A view with no entry is treated as read
    empty, so its row-count minimum fails. ``source_failures`` come from :func:`check_source`,
    which the caller runs first; any of them stops the run before a row is looked at.
    """
    report = BoundaryReport()
    report.aggregate_failures.extend(source_failures)
    if source_failures:
        _stop(report, "the source database fails its check")

    _check_inputs(rows, expectations)
    # Read the key file before the checks, so a malformed one fails fast, not after a full pass.
    stored = load_late_keys(late_keys_path) if late_keys_path is not None else {}

    views: dict[str, _View] = {}
    for name, exp in sorted(expectations.items()):
        if exp.pending:
            report.inactive.append(f"{name}: view not pinned yet ({exp.pending})")
            continue
        report.inactive += [
            f"{name}.{column}: {why}" for column, why in sorted(exp.pending_columns.items())
        ]
        view = _View(exp, rows.get(name, ()), report)
        view.run()
        views[name] = view
        report.aggregate_failures += view.aggregate
    if report.aggregate_failures:
        _keep_row_evidence(views, report)
        _stop(report, "an aggregate check failed")

    dropped = _cascade(views)
    for name, view in views.items():
        for index in sorted(dropped.get(name, ())):
            for failure in view.by_row[index]:
                report.quarantined.append(failure)
        _classify(view, dropped.get(name, set()), report, persisted=late_keys_path is not None)
    _enforce_caps(views, dropped, report)
    kept = {
        name: [r for i, r in enumerate(view.rows) if i not in dropped.get(name, set())]
        for name, view in views.items()
    }
    if late_keys_path is not None:
        _persist_late(report, views, stored, late_keys_path)
    return BoundaryResult(kept, report)


def _check_inputs(
    rows: Mapping[str, Sequence[Row]], expectations: Mapping[str, ViewExpectation]
) -> None:
    """Every view given rows must have expectations and be readable (not ``pending``)."""
    unknown = sorted(set(rows) - set(expectations))
    if unknown:
        raise ValueError(f"rows for view(s) with no expectations: {', '.join(unknown)}")
    unread = sorted(name for name in rows if expectations[name].pending)
    if unread:  # a pending view cannot be read; dropping its rows here would be silent
        raise ValueError(f"rows for pending view(s), which cannot be read yet: {', '.join(unread)}")


def _keep_row_evidence(views: Mapping[str, _View], report: BoundaryReport) -> None:
    """An aggregate stop drops no row, but the same pass found row failures: report them too."""
    for view in views.values():
        report.row_failures += [f for i in sorted(view.by_row) for f in view.by_row[i]]


def _stop(report: BoundaryReport, why: str) -> NoReturn:
    report.stopped = True
    report.stop_reasons.append(why)
    raise BoundaryError(report)


def _cascade(views: Mapping[str, _View]) -> dict[str, set[int]]:
    """Row indexes to drop per view: the failing rows plus everything they take with them.

    A taken row names the failing row that started the cascade (``cascaded_from``), not the row
    it was taken with when that row was itself taken; the detail names that intermediate hop.
    When several failing rows reach the same row, it names one of them, the first to reach it;
    the others are each in the report as failures of their own.
    """
    dropped: dict[str, set[int]] = {
        n: {i for i, f in v.by_row.items() if f} for n, v in views.items()
    }
    # (view, row index, the failing row that started this cascade)
    queue = [(n, i, f"{n} {views[n].key_of(i)}") for n, idxs in dropped.items() for i in idxs]
    while queue:
        name, index, root = queue.pop()
        source = views[name]
        here = f"{name} {source.key_of(index)}"
        for target_name, on in CASCADES.get(name, ()):
            target = views.get(target_name)
            if target is None:
                continue
            key = _key(source.rows[index], on)
            if None in key:
                continue
            via = "the failing row" if here == root else here
            for j, row in enumerate(target.rows):
                if j not in dropped[target_name] and _key(row, on) == key:
                    dropped[target_name].add(j)
                    target.by_row[j].append(
                        Failure(
                            target_name,
                            CASCADE,
                            None,
                            f"shares {', '.join(on)} {key} with {via}",
                            key=target.key_of(j),
                            cascaded_from=root,
                        )
                    )
                    queue.append((target_name, j, root))
    return dropped


def _is_late(view: _View, row: Row, *, persisted: bool) -> bool:
    """Late only if the next run can find the row again: an ingestion-dated graph, a natural key
    (a row index means nothing to the next run) and a file the keys are persisted to."""
    where = INGESTION_DATED.get(view.exp.view)
    return persisted and bool(view.row_key) and where is not None and _matches(row, where)


def _classify(view: _View, dropped: set[int], report: BoundaryReport, *, persisted: bool) -> None:
    for index in sorted(dropped):
        failure = view.by_row[index][0]
        late = _is_late(view, view.rows[index], persisted=persisted)
        (report.late if late else report.lost).append(failure)


def _enforce_caps(
    views: Mapping[str, _View], dropped: Mapping[str, set[int]], report: BoundaryReport
) -> None:
    for name, view in views.items():
        count, total = len(dropped.get(name, ())), len(view.rows)
        if total and count / total > view.exp.cap:
            report.stop_reasons.append(
                f"{name}: {count}/{total} rows quarantined, over the cap {view.exp.cap}"
            )
    if report.stop_reasons:
        report.stopped = True
        raise BoundaryError(report)


# The late-key file: ``{view: {"columns": [key column, ...], "keys": [[value, ...], ...]}}``.
LateKeys = dict[str, dict[str, list[Any]]]


def _json_key(key: Sequence[Any]) -> str:
    """One spelling per key, so a key read back from the file compares equal to a fresh one."""
    return json.dumps(list(key), default=str)


def _is_key_list(value: object, arity: int) -> bool:
    return isinstance(value, list) and all(isinstance(k, list) and len(k) == arity for k in value)


def load_late_keys(path: Path) -> LateKeys:
    """The late keys persisted by earlier runs (T-031 re-reads their rows); ``{}`` if none yet.

    The caller merges each re-read row into its read by natural key, never appends it: the same
    row twice fails the uniqueness check. The file only shrinks through :func:`mark_written`, so a
    key whose row upstream deleted stays until the caller reports and drops it (T-031 reports the
    keys its re-read did not find).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise ValueError(f"{path}: the late-key file is not JSON: {exc}") from exc
    if not isinstance(data, dict) or not all(
        isinstance(view, str)
        and isinstance(entry, dict)
        and set(entry) == {"columns", "keys"}
        and isinstance(entry["columns"], list)
        and entry["columns"]
        and all(isinstance(c, str) for c in entry["columns"])
        and _is_key_list(entry["keys"], len(entry["columns"]))
        for view, entry in data.items()
    ):
        raise ValueError(
            f"{path}: the late-key file must map each view to "
            '{"columns": [...], "keys": [[...], ...]}'
        )
    return data


def _write_late_keys(path: Path, data: LateKeys) -> None:
    """Replace the file atomically and durably: a crash leaves the old file, never a truncated one.

    With nothing to keep and no file yet, nothing is created.
    """
    out = {
        view: {"columns": entry["columns"], "keys": sorted(entry["keys"], key=_json_key)}
        for view, entry in data.items()
        if entry["keys"]
    }
    if not out and not path.exists():
        return
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w") as handle:
        handle.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())  # on disk before the rename, so a power loss cannot empty it
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Make the rename itself durable; a no-op where directories cannot be opened (Windows)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _persist_late(
    report: BoundaryReport, views: Mapping[str, _View], data: LateKeys, path: Path
) -> None:
    """Add this run's late keys to ``path``; never remove one (:func:`mark_written` does that).

    A view whose key columns changed since its keys were stored cannot match them again: those
    keys are dropped and listed in ``report.stale_late_keys``.
    """
    for view, entry in list(data.items()):
        current = views[view].row_key if view in views else None
        if current is not None and list(current) != entry["columns"]:
            report.stale_late_keys += [
                f"{view} {entry['columns']} = {k} (key is now {list(current)})"
                for k in entry["keys"]
            ]
            del data[view]
    for failure in report.late:
        if failure.key is None:
            continue
        columns = list(views[failure.view].row_key)
        entry = data.setdefault(failure.view, {"columns": columns, "keys": []})
        fresh = json.loads(_json_key(failure.key))
        if _json_key(fresh) not in {_json_key(k) for k in entry["keys"]}:
            entry["keys"].append(fresh)
    _write_late_keys(path, data)


def mark_written(path: Path, view: str, keys: Sequence[Sequence[Any]]) -> None:
    """Drop ``keys`` of ``view`` from the late-key file once their rows are in the store (T-031).

    Called after a successful write, never by :func:`validate`: a row that passed the boundary
    can still fail the SHACL gate or the store, and its key must survive that.
    """
    data = load_late_keys(path)
    entry = data.get(view)
    if entry is None:
        return
    written = {_json_key(k) for k in keys}
    entry["keys"] = [k for k in entry["keys"] if _json_key(k) not in written]
    _write_late_keys(path, data)
