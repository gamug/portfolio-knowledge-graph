"""Project and verify upstream's ``aggregates_<label>.json`` (Work item 37).

The file is a small per-label publication beside the run databases and their ``SHA256SUMS``
manifest: one row per trend-filter decision date and one row per reporting segment and reference.
This module reads it through a whitelist, builds the deterministic batch for
``urn:graph:derived:backtest:aggregates:{label}`` and verifies it against the source databases
read-only. It never reads or writes a daily series, a price level or the 210-session average.

The parser accepts only the contract upstream described. An extra or missing key, an unknown
state/reference/segment, a duplicate identity, a malformed date or decimal and a manifest that does
not list the file (or whose hash differs) stop with a message naming the table, row and key. The
``sources.spy_total_return_series_sha256`` value is validated and deliberately not projected.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from kg_store.graphdb import EXPLICIT_GRAPH
from projection.backtest import (
    RUN_LABEL_PATTERN,
    SEGMENT_PATTERN,
    WINDOW_PATTERN,
    GraphBuilder,
)
from projection.source import FinancialSource

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

GRAPH_PREFIX = "urn:graph:derived:backtest:aggregates:"
#: The two arms the trend filter applies to, in the file's order. The MARKOWITZ_* arms never use it.
TOP_N_ARMS = ("TOPN_MV_NOGUARD", "TOPN_MV_GUARD_NO_NLP")
TREND_STATES = ("below", "at_or_above", "not_evaluable")
REFERENCES = ("SPY", "SP500_EW_INTERNAL")
#: The exact top-level keys, source keys and row keys of the contract.
TOP_LEVEL_KEYS = frozenset(
    {
        "label",
        "config_id",
        "trend_filter_applies_to_arms",
        "sources",
        "dictionary",
        "trend_filter",
        "reference_returns",
    }
)
SOURCE_KEYS = frozenset(
    {
        "run_databases",
        "spy_total_return_series_sha256",
        "spy_source",
        "sp500_ew_internal",
    }
)
DICTIONARY_KEYS = {
    "trend_filter": frozenset({"window", "decision_date", "spy_vs_sma210", "cash_fraction"}),
    "reference_returns": frozenset(
        {
            "window",
            "segment",
            "date_from",
            "date_to",
            "n_sessions",
            "reference",
            "total_return",
            "max_drawdown",
        }
    ),
}
TREND_KEYS = DICTIONARY_KEYS["trend_filter"]
REFERENCE_KEYS = DICTIONARY_KEYS["reference_returns"]
TREND_COLUMNS = ("window", "decision_date", "spy_vs_sma210", "cash_fraction")
REFERENCE_COLUMNS = (
    "window",
    "segment",
    "date_from",
    "date_to",
    "n_sessions",
    "reference",
    "total_return",
    "max_drawdown",
)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WINDOW = re.compile(WINDOW_PATTERN)
_SEGMENT = re.compile(SEGMENT_PATTERN)
_LABEL = re.compile(RUN_LABEL_PATTERN)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")
_ZERO = Decimal("0.0")
_TOLERANCE = Decimal("0.000001")


class AggregatesError(ValueError):
    """The file, the manifest or a verification check cannot be accepted."""


class ManifestError(AggregatesError):
    """``SHA256SUMS`` is missing, malformed, or does not match the aggregates file."""


@dataclass(frozen=True)
class TrendFilterRow:
    """One ``trend_filter`` row: the filter state at one decision date."""

    window: str
    decision_date: datetime.date
    state: str
    cash_fraction: Decimal


@dataclass(frozen=True)
class ReferenceReturnRow:
    """One ``reference_returns`` row: one reference over one reporting segment."""

    window: str
    segment: str
    date_from: datetime.date
    date_to: datetime.date
    n_sessions: int
    reference: str
    total_return: Decimal
    max_drawdown: Decimal


@dataclass(frozen=True)
class AggregatesFile:
    """The accepted aggregates file, plus the manifest identity of its own file."""

    label: str
    config_id: str
    arms: tuple[str, str]
    sources: Mapping[str, str]
    dictionary: Mapping[str, Mapping[str, str]]
    trend_filter: tuple[TrendFilterRow, ...]
    reference_returns: tuple[ReferenceReturnRow, ...]
    source_file: str = ""
    source_sha256: str = ""


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line of the source or stored-graph verifier."""

    name: str
    passed: bool
    detail: str


@dataclass
class Verification:
    """The checks run for one aggregates label and their result."""

    label: str
    directory: Path
    checks: list[Check]
    graph: str

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def summary(self) -> str:
        lines = [
            f"aggregates: {self.label}",
            f"source: {self.directory}",
            f"graph: {self.graph}",
        ]
        lines += [
            f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}"
            for check in self.checks
        ]
        passed = sum(check.passed for check in self.checks)
        lines.append(
            f"{len(self.checks)} checks: {passed} passed, {len(self.checks) - passed} failed"
        )
        return "\n".join(lines)


class ReadableStore(Protocol):
    """What the stored-graph check needs of a store: SPARQL ``SELECT`` and nothing else."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


# --- reading and validating the file ------------------------------------------------------------


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object hook that refuses a duplicate key instead of keeping the last value."""
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AggregatesError(f"duplicate JSON key {key!r}: the file contract has unique keys")
        out[key] = value
    return out


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise AggregatesError(f"{where}: expected a JSON object, got {type(value).__name__}")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing " + ", ".join(repr(key) for key in missing))
        if extra:
            parts.append("unknown " + ", ".join(repr(key) for key in extra))
        raise AggregatesError(f"{where}: {'; '.join(parts)}")


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AggregatesError(f"{where}: expected a non-empty string")
    return value


def _label(value: object, where: str) -> str:
    text = _string(value, where)
    if not _LABEL.fullmatch(text):
        raise AggregatesError(
            f"{where}: {text!r} does not match the run-label pattern {RUN_LABEL_PATTERN}"
        )
    return text


def _window(value: object, where: str) -> str:
    text = _string(value, where)
    if not _WINDOW.fullmatch(text):
        raise AggregatesError(
            f"{where}: {text!r} does not match the window pattern {WINDOW_PATTERN}"
        )
    return text


def _segment(value: object, where: str) -> str:
    text = _string(value, where)
    if not _SEGMENT.fullmatch(text):
        raise AggregatesError(
            f"{where}: {text!r} does not match the segment pattern {SEGMENT_PATTERN}"
        )
    return text


def _date(value: object, where: str) -> datetime.date:
    text = _string(value, where)
    if not _DATE.fullmatch(text):
        raise AggregatesError(f"{where}: {text!r} is not a strict YYYY-MM-DD date")
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise AggregatesError(f"{where}: {text!r} is not a calendar date ({exc})") from exc
    if day.isoformat() != text:
        raise AggregatesError(f"{where}: {text!r} is not the ISO form of {day.isoformat()}")
    return day


def _decimal(value: object, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise AggregatesError(f"{where}: expected a JSON number, got {type(value).__name__}")
    try:
        number = Decimal(value) if isinstance(value, int) else value
    except InvalidOperation as exc:
        raise AggregatesError(f"{where}: {value!r} is not a decimal") from exc
    if not number.is_finite():
        raise AggregatesError(f"{where}: {value!r} is not a finite decimal")
    return number


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AggregatesError(f"{where}: expected a JSON integer, got {type(value).__name__}")
    return value


def _list(value: object, where: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise AggregatesError(f"{where}: expected a JSON array, got {type(value).__name__}")
    return value


def _arms(value: object, where: str) -> tuple[str, str]:
    rows = _list(value, where)
    if len(rows) != len(TOP_N_ARMS):
        raise AggregatesError(f"{where}: expected exactly two Top-N arms, got {len(rows)}")
    arms = tuple(_string(row, f"{where}[{index}]") for index, row in enumerate(rows))
    if arms != TOP_N_ARMS:
        raise AggregatesError(
            f"{where}: expected {TOP_N_ARMS!r} in that order, got {arms!r}; the MARKOWITZ_* arms "
            "never use the trend filter"
        )
    return (arms[0], arms[1])


def _dictionary(value: object) -> Mapping[str, Mapping[str, str]]:
    tables = _object(value, "dictionary")
    _keys(tables, frozenset(DICTIONARY_KEYS), "dictionary")
    out: dict[str, Mapping[str, str]] = {}
    for table, expected in DICTIONARY_KEYS.items():
        columns = _object(tables[table], f"dictionary.{table}")
        _keys(columns, expected, f"dictionary.{table}")
        out[table] = {key: _string(columns[key], f"dictionary.{table}.{key}") for key in expected}
    return out


def _sources(value: object) -> Mapping[str, str]:
    sources = _object(value, "sources")
    _keys(sources, SOURCE_KEYS, "sources")
    out = {key: _string(sources[key], f"sources.{key}") for key in SOURCE_KEYS}
    if not _SHA256.fullmatch(out["spy_total_return_series_sha256"]):
        raise AggregatesError(
            "sources.spy_total_return_series_sha256: expected 64 lowercase hex digits"
        )
    return out


def _trend_filter(value: object) -> tuple[TrendFilterRow, ...]:
    rows = _list(value, "trend_filter")
    out: list[TrendFilterRow] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows):
        where = f"trend_filter[{index}]"
        row = _object(raw, where)
        _keys(row, TREND_KEYS, where)
        window = _window(row["window"], f"{where}.window")
        day = _date(row["decision_date"], f"{where}.decision_date")
        state = _string(row["spy_vs_sma210"], f"{where}.spy_vs_sma210")
        if state not in TREND_STATES:
            raise AggregatesError(
                f"{where}.spy_vs_sma210: {state!r} is not one of {TREND_STATES!r}"
            )
        cash = _decimal(row["cash_fraction"], f"{where}.cash_fraction")
        if not (_ZERO <= cash <= Decimal("1.0")):
            raise AggregatesError(f"{where}.cash_fraction: {cash} is not in [0, 1]")
        identity = (window, day.isoformat())
        if identity in seen:
            raise AggregatesError(
                f"{where}: duplicate trend_filter row for window {window} and {day}"
            )
        seen.add(identity)
        out.append(TrendFilterRow(window, day, state, cash))
    return tuple(out)


def _reference_returns(value: object) -> tuple[ReferenceReturnRow, ...]:  # noqa: C901
    rows = _list(value, "reference_returns")
    out: list[ReferenceReturnRow] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(rows):
        where = f"reference_returns[{index}]"
        row = _object(raw, where)
        _keys(row, REFERENCE_KEYS, where)
        window = _window(row["window"], f"{where}.window")
        segment = _segment(row["segment"], f"{where}.segment")
        if segment != window and not (
            segment[:-1] == window and segment[-1].islower() and segment[-1].isalpha()
        ):
            raise AggregatesError(
                f"{where}.segment: {segment!r} is not the window {window!r} or a cut of it"
            )
        date_from = _date(row["date_from"], f"{where}.date_from")
        date_to = _date(row["date_to"], f"{where}.date_to")
        if date_from > date_to:
            raise AggregatesError(
                f"{where}: date_from {date_from} is after date_to {date_to} in segment {segment}"
            )
        sessions = _integer(row["n_sessions"], f"{where}.n_sessions")
        if sessions < 1:
            raise AggregatesError(f"{where}.n_sessions: {sessions} is not a positive count")
        reference = _string(row["reference"], f"{where}.reference")
        if reference not in REFERENCES:
            raise AggregatesError(f"{where}.reference: {reference!r} is not one of {REFERENCES!r}")
        total = _decimal(row["total_return"], f"{where}.total_return")
        drawdown = _decimal(row["max_drawdown"], f"{where}.max_drawdown")
        if drawdown < _ZERO:
            raise AggregatesError(f"{where}.max_drawdown: {drawdown} is negative")
        identity = (window, segment, reference)
        if identity in seen:
            raise AggregatesError(
                f"{where}: duplicate reference_returns row for {window} / {segment} / {reference}"
            )
        seen.add(identity)
        out.append(
            ReferenceReturnRow(
                window,
                segment,
                date_from,
                date_to,
                sessions,
                reference,
                total,
                drawdown,
            )
        )
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for parsed in out:
        groups[(parsed.window, parsed.segment)].add(parsed.reference)
    for (window, segment), reference_names in sorted(groups.items()):
        if reference_names != set(REFERENCES):
            raise AggregatesError(
                f"reference_returns: segment {segment} of window {window} needs exactly "
                f"{REFERENCES!r}, got {tuple(sorted(reference_names))!r}"
            )
    return tuple(out)


def parse_aggregates(path: str | Path, *, label: str | None = None) -> AggregatesFile:
    """Read and validate one aggregates file; ``label`` is the CLI's expected label."""
    path = Path(path)
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            object_pairs_hook=_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise AggregatesError(f"{path}: not valid JSON ({exc})") from exc
    root = _object(document, str(path))
    _keys(root, TOP_LEVEL_KEYS, str(path))
    file_label = _label(root["label"], f"{path}: label")
    if label is not None and file_label != label:
        raise AggregatesError(
            f"{path}: the file's label is {file_label!r}, the command's is {label!r}"
        )
    config_id = _string(root["config_id"], f"{path}: config_id")
    arms = _arms(root["trend_filter_applies_to_arms"], f"{path}: trend_filter_applies_to_arms")
    sources = _sources(root["sources"])
    dictionary = _dictionary(root["dictionary"])
    trend_filter = _trend_filter(root["trend_filter"])
    reference_returns = _reference_returns(root["reference_returns"])
    return AggregatesFile(
        file_label,
        config_id,
        arms,
        sources,
        dictionary,
        trend_filter,
        reference_returns,
    )


# --- the manifest -------------------------------------------------------------------------------


def read_manifest(path: str | Path) -> dict[str, str]:
    """A strict ``sha256sum`` manifest: hash, two spaces, file name; no duplicates.

    Work item 35's ``delivery.read_manifest`` is not reused here: it accepts uppercase hashes and
    the sha256sum binary marker, while this file's contract requires lowercase hashes and exactly
    two spaces. Keep the strict reader local until the two contracts agree (they can be unified
    later).
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = _MANIFEST_LINE.fullmatch(line)
        if match is None:
            raise ManifestError(
                f"{path}:{number}: expected '<64 lowercase hex>  <file name>', got {line!r}"
            )
        digest, name = match.groups()
        if Path(name).name != name or name in {".", ".."}:
            raise ManifestError(f"{path}:{number}: {name!r} is not a bare file name")
        if name in entries:
            raise ManifestError(f"{path}:{number}: {name!r} is listed twice")
        entries[name] = digest
    if not entries:
        raise ManifestError(f"{path}: the manifest is empty")
    return entries


def sha256_file(path: str | Path) -> str:
    """The lowercase SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(directory: str | Path, file_name: str) -> str:
    """Require ``file_name`` in ``directory/SHA256SUMS`` and its actual hash to match."""
    directory = Path(directory)
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise ManifestError(f"{manifest}: no SHA256SUMS in the aggregates directory")
    entries = read_manifest(manifest)
    if file_name not in entries:
        raise ManifestError(f"{manifest}: {file_name!r} is not listed")
    expected = entries[file_name]
    path = directory / file_name
    if not path.is_file():
        raise ManifestError(f"{path}: listed in {manifest.name} but the file does not exist")
    actual = sha256_file(path)
    if actual != expected:
        raise ManifestError(
            f"{path}: SHA-256 mismatch: manifest says {expected}, the file has {actual}"
        )
    return expected


# --- the batch ----------------------------------------------------------------------------------


def graph_name(label: str) -> str:
    """The append-only aggregates graph of one label."""
    if not _LABEL.fullmatch(label):
        raise AggregatesError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    return f"{GRAPH_PREFIX}{label}"


def aggregates_set_iri(label: str) -> rdflib.URIRef:
    return KG[f"AggregatesSet_{label}"]


def trend_filter_iri(label: str, row: TrendFilterRow) -> rdflib.URIRef:
    return KG[f"TrendFilter_{label}_{row.window}_{row.decision_date:%Y%m%d}"]


def reference_return_iri(label: str, row: ReferenceReturnRow) -> rdflib.URIRef:
    return KG[f"RefReturn_{label}_{row.segment}_{row.reference}"]


def _decimal_literal(value: Decimal) -> rdflib.Literal:
    return rdflib.Literal(format(value, "f"), datatype=XSD.decimal)


def _date_literal(value: datetime.date) -> rdflib.Literal:
    return rdflib.Literal(value.isoformat(), datatype=XSD.date)


def project(data: AggregatesFile) -> GraphBuilder:
    """Build the deterministic Turtle batch for one aggregates file."""
    if not data.source_file or not data.source_sha256:
        raise AggregatesError(
            "the manifest identity is missing: parse the file with :func:`with_manifest` "
            "or the CLI before projecting"
        )
    builder = GraphBuilder()
    label = data.label
    root = aggregates_set_iri(label)
    builder.add(root, RDF.type, KG.AggregatesSet)
    builder.add(root, KG.runLabel, rdflib.Literal(label))
    builder.add(root, KG.aggregatesSourceFile, rdflib.Literal(data.source_file))
    builder.add(root, KG.aggregatesSourceSha256, rdflib.Literal(data.source_sha256))
    builder.add(root, KG.aggregatesConfigId, rdflib.Literal(data.config_id))
    builder.add(
        root,
        KG.aggregatesRunDatabasesSource,
        rdflib.Literal(data.sources["run_databases"]),
    )
    builder.add(root, KG.aggregatesSpySource, rdflib.Literal(data.sources["spy_source"]))
    builder.add(
        root,
        KG.aggregatesSp500EwInternalSource,
        rdflib.Literal(data.sources["sp500_ew_internal"]),
    )
    for trend_row in sorted(data.trend_filter, key=lambda item: (item.decision_date, item.window)):
        iri = trend_filter_iri(label, trend_row)
        builder.add(iri, RDF.type, KG.TrendFilterState)
        builder.add(iri, KG.runLabel, rdflib.Literal(label))
        builder.add(iri, KG.trendWindow, rdflib.Literal(trend_row.window))
        builder.add(iri, KG.trendDecisionDate, _date_literal(trend_row.decision_date))
        builder.add(iri, KG.trendState, rdflib.Literal(trend_row.state))
        builder.add(iri, KG.cashFraction, _decimal_literal(trend_row.cash_fraction))
        for arm in data.arms:
            builder.add(iri, KG.appliesToArm, rdflib.Literal(arm))
        builder.add(iri, KG.aggregatesSet, root)
    for reference_row in sorted(
        data.reference_returns,
        key=lambda item: (item.date_from, item.segment, item.reference),
    ):
        iri = reference_return_iri(label, reference_row)
        builder.add(iri, RDF.type, KG.ReferenceReturn)
        builder.add(iri, KG.runLabel, rdflib.Literal(label))
        builder.add(iri, KG.returnWindow, rdflib.Literal(reference_row.window))
        builder.add(iri, KG.returnSegment, rdflib.Literal(reference_row.segment))
        builder.add(iri, KG.referenceDateFrom, _date_literal(reference_row.date_from))
        builder.add(iri, KG.referenceDateTo, _date_literal(reference_row.date_to))
        builder.add(
            iri,
            KG.nSessions,
            rdflib.Literal(reference_row.n_sessions, datatype=XSD.integer),
        )
        builder.add(iri, KG.referenceName, rdflib.Literal(reference_row.reference))
        builder.add(iri, KG.referenceTotalReturn, _decimal_literal(reference_row.total_return))
        builder.add(iri, KG.referenceMaxDrawdown, _decimal_literal(reference_row.max_drawdown))
        builder.add(iri, KG.aggregatesSet, root)
    return builder


def batch(data: AggregatesFile) -> tuple[str, bytes]:
    """The graph name and its deterministic Turtle batch."""
    return graph_name(data.label), project(data).turtle()


# --- the read-only verifier ---------------------------------------------------------------------


def _tsv(values: set[str]) -> str:
    return ", ".join(sorted(values)) if values else "none"


def _triples_text(values: set[tuple[str, str, str]]) -> str:
    return ", ".join(" | ".join(triple) for triple in sorted(values)[:5])


def _decision_dates(source: FinancialSource) -> dict[str, set[str]]:
    """Per Top-N arm, the distinct ``v_book_rebalance.decision_date`` values."""
    rows = source.execute(
        "SELECT DISTINCT arm_code, decision_date FROM v_book_rebalance "
        "WHERE arm_code IN (?, ?) ORDER BY arm_code, decision_date",
        TOP_N_ARMS,
    ).fetchall()
    out: dict[str, set[str]] = defaultdict(set)
    for arm, day in rows:
        out[str(arm)].add(str(day))
    return out


def _summary_segments(source: FinancialSource) -> dict[str, tuple[str, str, str]]:
    """Segment -> (window, date_from, date_to) from one database's period summaries."""
    rows = source.execute(
        "SELECT DISTINCT window_id, segment, date_from, date_to "
        "FROM v_portfolio_period_summary ORDER BY segment"
    ).fetchall()
    out: dict[str, tuple[str, str, str]] = {}
    for window, segment, date_from, date_to in rows:
        key = str(segment)
        value = (str(window), str(date_from), str(date_to))
        if key in out and out[key] != value:
            raise AggregatesError(
                f"v_portfolio_period_summary: segment {key!r} has conflicting dates or windows "
                f"({out[key]} vs {value})"
            )
        out[key] = value
    return out


def _manifest_check(data: AggregatesFile, directory: Path) -> Check:
    try:
        digest = verify_manifest(directory, data.source_file)
    except (ManifestError, OSError) as exc:
        return Check("manifest", False, str(exc))
    return Check("manifest", True, f"{data.source_file} is listed; SHA-256 {digest} matches")


def _trend_checks(data: AggregatesFile, directory: Path) -> list[Check]:
    checks: list[Check] = []
    by_window: dict[str, set[str]] = defaultdict(set)
    for row in data.trend_filter:
        by_window[row.window].add(row.decision_date.isoformat())
    for window in sorted(by_window):
        expected = by_window[window]
        path = directory / f"{data.label}_{window}.db"
        if not path.is_file():
            checks.append(
                Check(
                    f"trend filter {window}",
                    False,
                    f"{path}: the window's database is missing",
                )
            )
            continue
        try:
            source = FinancialSource.open(path)
            try:
                dates = _decision_dates(source)
            finally:
                source.close()
        except (sqlite3.Error, OSError, AggregatesError) as exc:
            checks.append(Check(f"trend filter {window}", False, f"{path}: {exc}"))
            continue
        problems: list[str] = []
        for arm in TOP_N_ARMS:
            if arm not in dates:
                problems.append(f"{arm} has no v_book_rebalance row")
                continue
            missing = expected - dates[arm]
            extra = dates[arm] - expected
            if missing:
                problems.append(f"{arm} is missing {_tsv(missing)}")
            if extra:
                problems.append(f"{arm} has extra {_tsv(extra)}")
        arm_sets = [dates[arm] for arm in TOP_N_ARMS if arm in dates]
        if len(arm_sets) == len(TOP_N_ARMS) and arm_sets[0] != arm_sets[1]:
            problems.append(
                "the two Top-N arms disagree: "
                f"{TOP_N_ARMS[0]} {_tsv(arm_sets[0])} vs "
                f"{TOP_N_ARMS[1]} {_tsv(arm_sets[1])}"
            )
        detail = (
            f"{len(expected)} decision date(s) match both Top-N arms"
            if not problems
            else f"{window}: " + "; ".join(problems)
        )
        checks.append(Check(f"trend filter {window}", not problems, detail))
    return checks


def _reference_checks(data: AggregatesFile, directory: Path) -> list[Check]:  # noqa: C901, PLR0912
    checks: list[Check] = []
    file_groups: dict[str, list[ReferenceReturnRow]] = defaultdict(list)
    for row in data.reference_returns:
        file_groups[row.segment].append(row)
    db_segments: dict[str, tuple[str, str, str]] = {}
    db_by_window: dict[str, set[str]] = {}
    windows = {row.window for row in data.reference_returns} | {
        row.window for row in data.trend_filter
    }
    for window in sorted(windows):
        path = directory / f"{data.label}_{window}.db"
        if not path.is_file():
            checks.append(
                Check(
                    f"reference returns {window}",
                    False,
                    f"{path}: the window's database is missing",
                )
            )
            continue
        try:
            source = FinancialSource.open(path)
            try:
                segments = _summary_segments(source)
            finally:
                source.close()
        except (sqlite3.Error, OSError, AggregatesError) as exc:
            checks.append(Check(f"reference returns {window}", False, f"{path}: {exc}"))
            continue
        db_by_window[window] = set(segments)
        for segment, value in segments.items():
            if segment in db_segments and db_segments[segment] != value:
                checks.append(
                    Check(
                        f"reference returns {segment}",
                        False,
                        f"{path}: segment {segment} has conflicting summary values "
                        f"{db_segments[segment]} vs {value}",
                    )
                )
            db_segments[segment] = value
    for segment in sorted(set(file_groups) | set(db_segments)):
        rows = file_groups.get(segment, [])
        if segment not in db_segments:
            checks.append(
                Check(
                    f"reference returns {segment}",
                    False,
                    f"segment {segment} is in the file but no database summary publishes it",
                )
            )
            continue
        if not rows:
            window, date_from, date_to = db_segments[segment]
            checks.append(
                Check(
                    f"reference returns {segment}",
                    False,
                    f"segment {segment} ({window}, {date_from}..{date_to}) is in the databases "
                    "but has no reference_returns rows",
                )
            )
            continue
        window, date_from, date_to = db_segments[segment]
        problems: list[str] = []
        references = [row.reference for row in rows]
        if sorted(references) != sorted(REFERENCES):
            problems.append(f"has references {tuple(sorted(references))}, expected {REFERENCES}")
        for row in rows:
            if row.window != window:
                problems.append(f"row window {row.window} differs from the summary window {window}")
            if row.date_from.isoformat() != date_from:
                problems.append(f"date_from {row.date_from} differs from {date_from}")
            if row.date_to.isoformat() != date_to:
                problems.append(f"date_to {row.date_to} differs from {date_to}")
            if row.window not in db_by_window:
                problems.append(f"window {row.window} has no database")
        detail = (
            f"{window}, {date_from}..{date_to}, 2 references match the summary"
            if not problems
            else f"segment {segment}: " + "; ".join(problems)
        )
        checks.append(Check(f"reference returns {segment}", not problems, detail))
    return checks


def _cash_checks(data: AggregatesFile) -> Check:
    problems: list[str] = []
    for row in data.trend_filter:
        if row.state == "below":
            if not row.cash_fraction > _ZERO:
                problems.append(f"{row.window} {row.decision_date}: below with cash 0")
        elif row.cash_fraction != _ZERO:
            problems.append(
                f"{row.window} {row.decision_date}: {row.state} with cash {row.cash_fraction}"
            )
    if problems:
        return Check("cash fractions", False, "; ".join(problems))
    return Check(
        "cash fractions",
        True,
        f"{len(data.trend_filter)} row(s): below positive, other states exactly 0.0",
    )


def _compounding_check(data: AggregatesFile) -> Check:
    rows = {(row.segment, row.reference): row for row in data.reference_returns}
    parts: list[str] = []
    problems: list[str] = []
    for reference in REFERENCES:
        whole = rows.get(("P2", reference))
        first = rows.get(("P2a", reference))
        second = rows.get(("P2b", reference))
        if whole is None or first is None or second is None:
            parts.append(f"{reference}: P2/P2a/P2b not all present")
            continue
        compounded = (Decimal(1) + first.total_return) * (Decimal(1) + second.total_return) - 1
        difference = whole.total_return - compounded
        parts.append(
            f"{reference}: P2 {whole.total_return}, compounded {compounded} "
            f"(difference {difference})"
        )
        if abs(difference) > _TOLERANCE:
            problems.append(
                f"{reference}: P2 {whole.total_return} differs from compounded {compounded} "
                f"by {difference}, more than {_TOLERANCE}"
            )
    return Check(
        "P2 compounding",
        not problems,
        "; ".join(problems) if problems else "; ".join(parts),
    )


def verify_sources(data: AggregatesFile, directory: str | Path) -> Verification:
    """Run checks (a)-(e) read-only against the manifest and ``<label>_<window>.db`` files."""
    directory = Path(directory)
    checks = [_manifest_check(data, directory)]
    if checks[0].passed:
        checks += _trend_checks(data, directory)
        checks += _reference_checks(data, directory)
        checks.append(_cash_checks(data))
        checks.append(_compounding_check(data))
    return Verification(data.label, directory, checks, graph_name(data.label))


def verify_stored(store: ReadableStore, data: AggregatesFile, builder: GraphBuilder) -> Check:
    """Check (f): the stored graph's explicit triples equal the file's batch, counts and values."""
    graph = graph_name(data.label)
    expected = {(str(s), str(p), str(o)) for s, p, o in builder.triples}
    try:
        rows = store.select(
            f"SELECT ?s ?p ?o FROM <{EXPLICIT_GRAPH}> WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"  # noqa: S608 -- label checked above
        )
    except Exception as exc:
        return Check("stored graph", False, f"{graph}: {exc}")
    stored = {(str(row.get("s", "")), str(row.get("p", "")), str(row.get("o", ""))) for row in rows}
    missing = expected - stored
    extra = stored - expected
    if not missing and not extra:
        return Check(
            "stored graph",
            True,
            f"{graph}: {len(stored)} triple(s) equal the file's batch",
        )
    detail = [f"{graph}: {len(stored)} stored, {len(expected)} expected"]
    if missing:
        detail.append("missing " + _triples_text(missing))
    if extra:
        detail.append("extra " + _triples_text(extra))
    return Check("stored graph", False, "; ".join(detail))


def with_manifest(data: AggregatesFile, directory: str | Path, file_name: str) -> AggregatesFile:
    """Attach the manifest's hash to a parsed file (the CLI's one ordering)."""
    digest = verify_manifest(directory, file_name)
    return replace(data, source_file=file_name, source_sha256=digest)
