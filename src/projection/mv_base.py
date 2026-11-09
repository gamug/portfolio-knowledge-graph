"""Load the external mean-variance base Markowitz delivery (Work item 44).

The delivery is the folder ``mv_base/``: ``aggregates_mv_base.json`` (eight per-window and
per-segment summary rows), ``config_mv_base.md`` (the frozen configuration and the SHA-256 of
``sim_v3.py``) and ``SHA256SUMS``. The book is computed outside the engine by an independent
simulator validated against the engine's ``MARKOWITZ_BASE`` book. Only per-window and
per-segment summaries are loaded: no daily series, no weights and no alerts.

The loader writes one append-only graph, ``urn:graph:derived:backtest:external:{label}``, with
one ``:StrategyBook`` per window (``MARKOWITZ_MV``) and one ``:PortfolioPeriodSummary`` per
segment. It never writes an engine graph. The two required files are verified against
``SHA256SUMS``; ``provenance/`` is not required and is never read. The JSON whitelist is strict:
an extra or missing key, an unknown window or segment, a duplicate identity, a malformed date or
decimal stops with a message naming the row and key.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from kg_store import gate
from kg_store.graphdb import (
    EXPLICIT_GRAPH,
    PRODUCTION_REPOSITORY,
    GraphDB,
    GraphDBError,
    announce_target,
)
from projection.backtest import RUN_LABEL_PATTERN, GraphBuilder, read_view
from projection.source import FinancialSource

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

GRAPH_PREFIX = "urn:graph:derived:backtest:external:"
FINAL_LABEL = "final"
ARM = "MARKOWITZ_MV"
OBJECTIVE = "max_sharpe"  # pending Reviewer A: named constant, not an engine value
DATA_SOURCE_DEFAULT = "independent simulator validated against the engine"
DEFAULT_ENGINE_DIR = Path("/workspaces/thesis/scratch/final/final_corregida")
REQUIRED_FILES = ("aggregates_mv_base.json", "config_mv_base.md")
MANIFEST_NAME = "SHA256SUMS"

#: The six windows, in calendar order, and the two cuts of P2.
WINDOWS = ("P1", "H1", "P3", "H2", "P2", "H3")
SEGMENTS = ("P1", "H1", "P3", "H2", "P2", "P2a", "P2b", "H3")
SIX_WINDOW_REBALANCES = 61

TOP_LEVEL_KEYS = frozenset({"label", "book_code", "source", "summary", "dictionary"})
ROW_KEYS = frozenset(
    {
        "window",
        "segment",
        "date_from",
        "date_to",
        "n_sessions",
        "cumulative_return",
        "annualized_return",
        "annualized_vol",
        "ex_post_sharpe",
        "max_drawdown",
        "total_turnover",
        "total_cost_bps",
        "n_rebalances",
        "n_guard_actions",
        "cvar95",
    }
)
_FLOAT_METRICS = (
    "cumulative_return",
    "annualized_return",
    "annualized_vol",
    "ex_post_sharpe",
    "max_drawdown",
    "total_turnover",
    "total_cost_bps",
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LABEL = re.compile(RUN_LABEL_PATTERN)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")
_CODE_VERSION = re.compile(r"sim_v3\.py`?\s*:\s*`?([0-9a-f]{64})")
_ONE_DAY = datetime.timedelta(days=1)
_TOLERANCE = Decimal("0.000000001")


class MvBaseError(ValueError):
    """The delivery, its manifest or a verification check cannot be accepted."""


class ManifestError(MvBaseError):
    """``SHA256SUMS`` is missing, malformed, or does not match a required file."""


@dataclass(frozen=True)
class MvSummaryRow:
    """One ``summary`` row: a window or a cut of P2 and its reported metrics."""

    window: str
    segment: str
    date_from: datetime.date
    date_to: datetime.date
    n_sessions: int
    cumulative_return: Decimal
    annualized_return: Decimal
    annualized_vol: Decimal
    ex_post_sharpe: Decimal
    max_drawdown: Decimal
    total_turnover: Decimal
    total_cost_bps: Decimal
    n_rebalances: int
    n_guard_actions: int
    cvar95: Decimal | None


@dataclass(frozen=True)
class MvConfig:
    """The front matter and the ``sim_v3.py`` hash read from ``config_mv_base.md``."""

    label: str
    book_code: str
    status: str
    revision: str
    code_version: str


@dataclass(frozen=True)
class EngineBook:
    """The engine's MARKOWITZ_BASE book and run for one window."""

    book_id: int
    run_id: int


@dataclass(frozen=True)
class MvBaseFile:
    """The accepted delivery plus the manifest and engine identities."""

    label: str
    book_code: str
    source: str
    dictionary: Mapping[str, str]
    rows: tuple[MvSummaryRow, ...]
    config: MvConfig
    json_sha256: str = ""
    config_sha256: str = ""
    engine: Mapping[str, EngineBook] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line or one warning in the loader output."""

    name: str
    passed: bool
    detail: str


class ReadableStore(Protocol):
    """What the stored-graph check needs of a store: SPARQL ``SELECT`` only."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


# --- reading and validating the files -----------------------------------------------------------


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MvBaseError(f"duplicate JSON key {key!r}: the file contract has unique keys")
        out[key] = value
    return out


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MvBaseError(f"{where}: expected a JSON object, got {type(value).__name__}")
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
        raise MvBaseError(f"{where}: {'; '.join(parts)}")


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MvBaseError(f"{where}: expected a non-empty string")
    return value


def _label(value: object, where: str) -> str:
    text = _string(value, where)
    if not _LABEL.fullmatch(text):
        raise MvBaseError(
            f"{where}: {text!r} does not match the run-label pattern {RUN_LABEL_PATTERN}"
        )
    return text


def _window(value: object, where: str) -> str:
    text = _string(value, where)
    if text not in WINDOWS:
        raise MvBaseError(f"{where}: {text!r} is not one of the six final windows {WINDOWS!r}")
    return text


def _segment(value: object, window: str, where: str) -> str:
    text = _string(value, where)
    if text not in SEGMENTS:
        raise MvBaseError(f"{where}: {text!r} is not one of {SEGMENTS!r}")
    if text != window and not (window == "P2" and text in {"P2a", "P2b"}):
        raise MvBaseError(f"{where}: segment {text!r} is not window {window!r} or a cut of it")
    return text


def _date(value: object, where: str) -> datetime.date:
    text = _string(value, where)
    if not _DATE.fullmatch(text):
        raise MvBaseError(f"{where}: {text!r} is not a strict YYYY-MM-DD date")
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise MvBaseError(f"{where}: {text!r} is not a calendar date ({exc})") from exc
    if day.isoformat() != text:
        raise MvBaseError(f"{where}: {text!r} is not the ISO form of {day.isoformat()}")
    return day


def _decimal(value: object, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise MvBaseError(f"{where}: expected a JSON number, got {type(value).__name__}")
    try:
        number = Decimal(value) if isinstance(value, int) else value
    except InvalidOperation as exc:
        raise MvBaseError(f"{where}: {value!r} is not a decimal") from exc
    if not number.is_finite():
        raise MvBaseError(f"{where}: {value!r} is not a finite decimal")
    return number


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MvBaseError(f"{where}: expected a JSON integer, got {type(value).__name__}")
    return value


def _list(value: object, where: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise MvBaseError(f"{where}: expected a JSON array, got {type(value).__name__}")
    return value


def _dictionary(value: object) -> Mapping[str, str]:
    table = _object(value, "dictionary")
    _keys(table, ROW_KEYS, "dictionary")
    return {key: _string(table[key], f"dictionary.{key}") for key in ROW_KEYS}


def _row(value: object, where: str) -> MvSummaryRow:
    row = _object(value, where)
    _keys(row, ROW_KEYS, where)
    window = _window(row["window"], f"{where}.window")
    segment = _segment(row["segment"], window, f"{where}.segment")
    date_from = _date(row["date_from"], f"{where}.date_from")
    date_to = _date(row["date_to"], f"{where}.date_to")
    if date_from > date_to:
        raise MvBaseError(f"{where}: date_from {date_from} is after date_to {date_to}")
    sessions = _integer(row["n_sessions"], f"{where}.n_sessions")
    if sessions < 1:
        raise MvBaseError(f"{where}.n_sessions: {sessions} is not a positive count")
    calendar_days = (date_to - date_from).days + 1
    if sessions > calendar_days:
        raise MvBaseError(
            f"{where}.n_sessions: {sessions} sessions exceed the {calendar_days} calendar days "
            f"of {date_from}..{date_to}"
        )
    values = {name: _decimal(row[name], f"{where}.{name}") for name in _FLOAT_METRICS}
    rebalances = _integer(row["n_rebalances"], f"{where}.n_rebalances")
    if rebalances < 0:
        raise MvBaseError(f"{where}.n_rebalances: {rebalances} is negative")
    guard_actions = _integer(row["n_guard_actions"], f"{where}.n_guard_actions")
    if guard_actions != 0:
        raise MvBaseError(
            f"{where}.n_guard_actions: {guard_actions}; the external MARKOWITZ_MV book has no "
            "GUARD, so 0 (not applicable) is the only accepted value"
        )
    cvar = row["cvar95"]
    cvar_value = None if cvar is None else _decimal(cvar, f"{where}.cvar95")
    return MvSummaryRow(
        window,
        segment,
        date_from,
        date_to,
        sessions,
        values["cumulative_return"],
        values["annualized_return"],
        values["annualized_vol"],
        values["ex_post_sharpe"],
        values["max_drawdown"],
        values["total_turnover"],
        values["total_cost_bps"],
        rebalances,
        guard_actions,
        cvar_value,
    )


def _rows(value: object) -> tuple[MvSummaryRow, ...]:
    rows = _list(value, "summary")
    out: list[MvSummaryRow] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows):
        where = f"summary[{index}]"
        parsed = _row(raw, where)
        identity = (parsed.window, parsed.segment)
        if identity in seen:
            raise MvBaseError(
                f"{where}: duplicate summary row for window {parsed.window} and segment "
                f"{parsed.segment}"
            )
        seen.add(identity)
        out.append(parsed)
    if {row.segment for row in out} != set(SEGMENTS):
        raise MvBaseError(
            "summary: expected exactly the segments "
            + ", ".join(SEGMENTS)
            + "; got "
            + ", ".join(sorted(row.segment for row in out))
        )
    by_segment = {row.segment: row for row in out}
    p2, p2a, p2b = by_segment["P2"], by_segment["P2a"], by_segment["P2b"]
    if p2a.date_from != p2.date_from or p2b.date_to != p2.date_to:
        raise MvBaseError("summary: P2a/P2b do not span the P2 dates")
    if p2a.date_to + _ONE_DAY != p2b.date_from:
        raise MvBaseError("summary: P2a and P2b are not contiguous cuts of P2")
    if p2a.n_sessions + p2b.n_sessions != p2.n_sessions:
        raise MvBaseError("summary: P2a and P2b n_sessions do not add up to P2")
    window_rebalances = sum(row.n_rebalances for row in out if row.segment == row.window)
    if window_rebalances != SIX_WINDOW_REBALANCES:
        raise MvBaseError(
            "summary: the six windows have "
            f"{window_rebalances} rebalances, expected {SIX_WINDOW_REBALANCES}"
        )
    return tuple(out)


def parse_aggregates(path: str | Path, *, label: str | None = None) -> MvBaseFile:
    """Parse ``aggregates_mv_base.json`` without reading the config or the manifest."""
    path = Path(path)
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            object_pairs_hook=_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise MvBaseError(f"{path}: not valid JSON ({exc})") from exc
    root = _object(document, str(path))
    _keys(root, TOP_LEVEL_KEYS, str(path))
    file_label = _label(root["label"], f"{path}: label")
    if label is not None and file_label != label:
        raise MvBaseError(f"{path}: the file's label is {file_label!r}, the command's is {label!r}")
    book_code = _string(root["book_code"], f"{path}: book_code")
    if book_code != ARM:
        raise MvBaseError(f"{path}: book_code {book_code!r} is not {ARM!r}")
    source = _string(root["source"], f"{path}: source")
    dictionary = _dictionary(root["dictionary"])
    rows = _rows(root["summary"])
    return MvBaseFile(file_label, book_code, source, dictionary, rows, _config_placeholder())


def _config_placeholder() -> MvConfig:
    """The parse step without a config; the CLI replaces it with the real one."""
    return MvConfig("", "", "", "", "")


def with_config(data: MvBaseFile, config: MvConfig) -> MvBaseFile:
    """Attach the parsed configuration to an already validated JSON document."""
    if data.label != config.label:
        raise MvBaseError(
            f"the JSON label {data.label!r} differs from the config label {config.label!r}"
        )
    if data.book_code != config.book_code:
        raise MvBaseError(
            f"the JSON book_code {data.book_code!r} differs from the config book_code "
            f"{config.book_code!r}"
        )
    return replace(data, config=config)


# --- the manifest -------------------------------------------------------------------------------


def read_manifest(path: str | Path) -> dict[str, str]:
    """A strict ``sha256sum`` manifest; paths are allowed for the provenance entries."""
    path = Path(path)
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _MANIFEST_LINE.fullmatch(line)
        if match is None:
            raise ManifestError(
                f"{path}:{number}: expected '<64 lowercase hex>  <file name>', got {line!r}"
            )
        digest, name = match.groups()
        if name.startswith(("/", "../")) or "/../" in name:
            raise ManifestError(f"{path}:{number}: {name!r} is not a safe relative path")
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


def read_engine_books(  # noqa: C901, PLR0912 - one branch per engine/file failure
    engine_dir: str | Path, label: str, data: MvBaseFile
) -> tuple[dict[str, EngineBook], list[str]]:
    """Read the engine's MARKOWITZ_BASE ids and segment dates, read-only, per window."""
    engine_dir = Path(engine_dir)
    out: dict[str, EngineBook] = {}
    warnings: list[str] = []
    for window in WINDOWS:
        path = engine_dir / f"{label}_{window}.db"
        if not path.is_file():
            raise MvBaseError(
                f"{path}: the engine database is missing; --engine-dir must point to the "
                f"folder with {label}_<window>.db"
            )
        try:
            source = FinancialSource.open(path)
            try:
                books = read_view(source, "v_book")
                summaries = read_view(source, "v_portfolio_period_summary")
            finally:
                source.close()
        except (OSError, sqlite3.Error) as exc:
            raise MvBaseError(f"{path}: cannot read the engine database ({exc})") from exc
        window_books = [row for row in books if str(row.get("window_id")) == window]
        if not window_books:
            raise MvBaseError(f"{path}: v_book has no row for window {window}")
        try:
            book_ids = {int(row["book_id"]) for row in window_books}
            run_ids = {int(row["backtest_run_id"]) for row in window_books}
        except (KeyError, TypeError, ValueError) as exc:
            raise MvBaseError(f"{path}: v_book has a non-integer book/run id ({exc})") from exc
        if not run_ids:
            raise MvBaseError(f"{path}: v_book has no backtest_run_id for window {window}")
        if len(run_ids) != 1:
            raise MvBaseError(
                f"{path}: v_book has {len(run_ids)} run ids for window {window}; "
                "one database must describe one engine run"
            )
        engine_book = EngineBook(max(book_ids) + 1, next(iter(run_ids)))
        out[window] = engine_book
        by_segment = {
            str(row.get("segment")): row
            for row in summaries
            if str(row.get("arm_code")) == "MARKOWITZ_BASE" and str(row.get("window_id")) == window
        }
        for row in data.rows:
            if row.window != window:
                continue
            engine_row = by_segment.get(row.segment)
            if engine_row is None:
                raise MvBaseError(
                    f"{path}: v_portfolio_period_summary has no MARKOWITZ_BASE row for "
                    f"window {window}, segment {row.segment}"
                )
            for field_name in ("date_from", "date_to"):
                expected = getattr(row, field_name).isoformat()
                actual = str(engine_row.get(field_name))
                if actual != expected:
                    raise MvBaseError(
                        f"{path}: MARKOWITZ_BASE {window}/{row.segment} {field_name} is "
                        f"{actual}, the delivery says {expected}"
                    )
            try:
                engine_rebalances = int(engine_row["n_rebalances"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MvBaseError(
                    f"{path}: MARKOWITZ_BASE {window}/{row.segment} has a non-integer "
                    f"n_rebalances ({exc})"
                ) from exc
            if engine_rebalances != row.n_rebalances:
                warnings.append(
                    f"{path}: MARKOWITZ_BASE {window}/{row.segment} n_rebalances is "
                    f"{engine_rebalances}, the delivery says {row.n_rebalances} (warning only)"
                )
    return out, warnings


def verify_manifest(directory: str | Path, file_names: Sequence[str]) -> dict[str, str]:
    """Require each name in ``directory/SHA256SUMS`` and its actual hash to match."""
    directory = Path(directory)
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        raise ManifestError(f"{manifest}: no SHA256SUMS in the delivery directory")
    entries = read_manifest(manifest)
    out: dict[str, str] = {}
    for name in file_names:
        if name not in entries:
            raise ManifestError(f"{manifest}: {name!r} is not listed")
        expected = entries[name]
        path = directory / name
        if not path.is_file():
            raise ManifestError(f"{path}: listed in {manifest.name} but the file does not exist")
        actual = sha256_file(path)
        if actual != expected:
            raise ManifestError(
                f"{path}: SHA-256 mismatch: manifest says {expected}, the file has {actual}"
            )
        out[name] = expected
    return out


# --- the config ---------------------------------------------------------------------------------


def _front_matter(  # noqa: C901 - one branch per front-matter failure
    path: Path, text: str
) -> tuple[dict[str, str], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise MvBaseError(f"{path}: the file does not start with a '---' front matter")
    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        raise MvBaseError(f"{path}: the front matter has no closing '---'")
    values: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], 2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise MvBaseError(f"{path}:{number}: expected 'key: value': {line.rstrip()!r}")
        key, value = key.strip(), value.strip()
        if not key:
            raise MvBaseError(f"{path}:{number}: empty front-matter key")
        if key in values:
            raise MvBaseError(f"{path}:{number}: {key} is given twice")
        values[key] = value
    body = "".join(lines[closing + 1 :])
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    if not body.strip():
        raise MvBaseError(f"{path}: the configuration body is empty")
    return values, body


def parse_config(path: str | Path, label: str) -> MvConfig:
    """Read ``config_mv_base.md`` and extract the ``sim_v3.py`` hash from its body."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MvBaseError(f"{path}: {exc}") from exc
    values, body = _front_matter(path, text)
    required = ("label", "book_code", "status", "revision")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise MvBaseError(f"{path}: missing required key(s): {', '.join(missing)}")
    if values["label"] != label:
        raise MvBaseError(
            f"{path}: front-matter label {values['label']!r} differs from --label {label!r}"
        )
    if values["book_code"] != ARM:
        raise MvBaseError(f"{path}: book_code {values['book_code']!r} is not {ARM!r}")
    if values["status"] != "final":
        raise MvBaseError(f"{path}: status {values['status']!r} is not 'final'")
    match = _CODE_VERSION.search(body)
    if match is None:
        raise MvBaseError(f"{path}: no SHA-256 for sim_v3.py in the configuration body")
    return MvConfig(
        label=label,
        book_code=ARM,
        status=values["status"],
        revision=values["revision"],
        code_version=match.group(1),
    )


# --- the batch ----------------------------------------------------------------------------------


def graph_name(label: str) -> str:
    """The append-only external delivery graph of one run label."""
    if not _LABEL.fullmatch(label):
        raise MvBaseError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    return f"{GRAPH_PREFIX}{label}"


def book_iri(label: str, window: str) -> rdflib.URIRef:
    return KG[f"Book_{label}_{window}_{ARM}"]


def summary_iri(label: str, window: str, segment: str) -> rdflib.URIRef:
    return KG[f"PeriodSummary_{label}_{window}_{ARM}_{segment}"]


def _date_literal(value: datetime.date) -> rdflib.Literal:
    return rdflib.Literal(value.isoformat(), datatype=XSD.date)


def _decimal_literal(value: Decimal) -> rdflib.Literal:
    return rdflib.Literal(format(value, "f"), datatype=XSD.decimal)


def project(data: MvBaseFile) -> GraphBuilder:  # noqa: PLR0915 - one field per summary property
    """Build the deterministic Turtle batch for one external delivery."""
    if not data.json_sha256 or not data.config_sha256:
        raise MvBaseError(
            "the manifest identity is missing: load the file through the CLI or verify both "
            "required files first"
        )
    if not data.config.code_version:
        raise MvBaseError("the config's sim_v3.py SHA-256 is missing")
    builder = GraphBuilder()
    label = data.label
    windows = sorted(
        (row for row in data.rows if row.segment == row.window),
        key=lambda row: (row.date_from, row.window),
    )
    if len(windows) != len(WINDOWS):
        raise MvBaseError(f"expected {len(WINDOWS)} windows, got {len(windows)}")
    books: dict[str, rdflib.URIRef] = {}
    for row in windows:
        engine = data.engine.get(row.window)
        if engine is None:
            raise MvBaseError(
                f"window {row.window!r} has no engine book/run: read the engine databases before "
                "projecting"
            )
        iri = book_iri(label, row.window)
        books[row.window] = iri
        builder.add(iri, RDF.type, KG.StrategyBook)
        builder.add(iri, KG.bookId, rdflib.Literal(engine.book_id, datatype=XSD.integer))
        builder.add(iri, KG.backtestRunId, rdflib.Literal(engine.run_id, datatype=XSD.integer))
        builder.add(iri, KG.runLabel, rdflib.Literal(label))
        builder.add(iri, KG.windowId, rdflib.Literal(row.window))
        builder.add(iri, KG.backtestStartDate, _date_literal(row.date_from))
        builder.add(iri, KG.backtestEndDate, _date_literal(row.date_to))
        builder.add(iri, KG.runStatus, rdflib.Literal("completed"))
        builder.add(iri, KG.armCode, rdflib.Literal(ARM))
        builder.add(iri, KG.objective, rdflib.Literal(OBJECTIVE))
        builder.add(iri, KG.excludeHardVetoed, rdflib.Literal(False))
        builder.add(iri, KG.dataSource, rdflib.Literal(data.source))
        builder.add(iri, KG.codeVersion, rdflib.Literal(data.config.code_version))
        builder.add(iri, KG.knowledgeDate, _date_literal(row.date_to))
    for row in sorted(data.rows, key=lambda row: (row.date_from, row.segment)):
        iri = summary_iri(label, row.window, row.segment)
        book = books[row.window]
        engine = data.engine[row.window]
        builder.add(iri, RDF.type, KG.PortfolioPeriodSummary)
        builder.add(iri, KG.summaryOfBook, book)
        builder.add(iri, KG.bookId, rdflib.Literal(engine.book_id, datatype=XSD.integer))
        builder.add(iri, KG.backtestRunId, rdflib.Literal(engine.run_id, datatype=XSD.integer))
        builder.add(iri, KG.armCode, rdflib.Literal(ARM))
        builder.add(iri, KG.windowId, rdflib.Literal(row.window))
        builder.add(iri, KG.segment, rdflib.Literal(row.segment))
        builder.add(iri, KG.dateFrom, _date_literal(row.date_from))
        builder.add(iri, KG.dateTo, _date_literal(row.date_to))
        builder.add(iri, KG.cumulativeReturn, _decimal_literal(row.cumulative_return))
        builder.add(iri, KG.annualizedReturn, _decimal_literal(row.annualized_return))
        builder.add(iri, KG.annualizedVol, _decimal_literal(row.annualized_vol))
        builder.add(iri, KG.exPostSharpe, _decimal_literal(row.ex_post_sharpe))
        builder.add(iri, KG.maxDrawdown, _decimal_literal(row.max_drawdown))
        builder.add(iri, KG.totalTurnover, _decimal_literal(row.total_turnover))
        builder.add(iri, KG.totalCostBps, _decimal_literal(row.total_cost_bps))
        builder.add(iri, KG.nRebalances, rdflib.Literal(row.n_rebalances, datatype=XSD.integer))
        builder.add(
            iri,
            KG.nGuardActions,
            rdflib.Literal(row.n_guard_actions, datatype=XSD.integer),
        )
        builder.add(iri, KG.knowledgeDate, _date_literal(row.date_to))
    return builder


def batch(data: MvBaseFile) -> tuple[str, bytes]:
    """The graph name and its deterministic Turtle batch."""
    return graph_name(data.label), project(data).turtle()


# --- verification -------------------------------------------------------------------------------


def records_changed(directory: str | Path) -> list[str]:
    """Warnings from the optional validation CSVs; never a hard failure."""
    directory = Path(directory)
    warnings: list[str] = []
    for name in ("validation_engine_book.csv", "validation_mv_run.csv"):
        path = directory / name
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error) as exc:
            warnings.append(f"{path}: cannot be read ({exc}); skipped")
            continue
        worst = Decimal(0)
        for row in rows:
            raw = row.get("abs_diff")
            if raw is None:
                warnings.append(f"{path}: no abs_diff column; skipped")
                break
            try:
                worst = max(worst, abs(Decimal(raw)))
            except InvalidOperation:
                warnings.append(f"{path}: non-decimal abs_diff {raw!r}; skipped")
                break
        else:
            if worst > _TOLERANCE:
                warnings.append(f"{path}: max abs_diff {worst} > {_TOLERANCE} (warning only)")
    return warnings


def verify_stored(store: ReadableStore, data: MvBaseFile, builder: GraphBuilder) -> Check:
    """Check that the stored external graph equals the file's batch."""
    graph = graph_name(data.label)
    expected = {(str(s), str(p), str(o)) for s, p, o in builder.triples}
    try:
        rows = store.select(
            f"SELECT ?s ?p ?o FROM <{EXPLICIT_GRAPH}> WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"  # noqa: S608 - graph_name validates the label
        )
    except Exception as exc:
        return Check("stored graph", False, f"{graph}: {exc}")
    stored = {(str(row.get("s", "")), str(row.get("p", "")), str(row.get("o", ""))) for row in rows}
    missing = expected - stored
    extra = stored - expected
    if not missing and not extra:
        return Check("stored graph", True, f"{graph}: {len(stored)} triple(s) equal the batch")
    detail = [f"{graph}: {len(stored)} stored, {len(expected)} expected"]
    if missing:
        detail.append("missing " + ", ".join(" | ".join(t) for t in sorted(missing)[:5]))
    if extra:
        detail.append("extra " + ", ".join(" | ".join(t) for t in sorted(extra)[:5]))
    return Check("stored graph", False, "; ".join(detail))


# --- CLI ----------------------------------------------------------------------------------------


def _label_arg(text: str) -> str:
    if not _LABEL.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in final)"
        )
    return text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--label", required=True, type=_label_arg, help="the run label (final)")
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="the mv_base folder with aggregates_mv_base.json, config_mv_base.md and SHA256SUMS",
    )
    parser.add_argument(
        "--engine-dir",
        type=Path,
        default=DEFAULT_ENGINE_DIR,
        metavar="DIR",
        help="the final_corregida folder with final_<window>.db (read-only; default %(default)s)",
    )
    parser.add_argument("--write", action="store_true", help="append the external graph")
    parser.add_argument(
        "--check-store",
        action="store_true",
        help="run the gate plan with SELECT only; write nothing",
    )
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.check_store and args.to_production:
        parser.error("--check-store never writes; drop --to-production")
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    return args


def load_file(
    label: str, directory: Path, engine_dir: str | Path = DEFAULT_ENGINE_DIR
) -> MvBaseFile:
    """Verify both required files, parse them, and read the engine identities read-only."""
    hashes = verify_manifest(directory, REQUIRED_FILES)
    data = parse_aggregates(directory / REQUIRED_FILES[0], label=label)
    config = parse_config(directory / REQUIRED_FILES[1], label=label)
    data = with_config(data, config)
    engine, warnings = read_engine_books(engine_dir, label, data)
    return replace(
        data,
        json_sha256=hashes[REQUIRED_FILES[0]],
        config_sha256=hashes[REQUIRED_FILES[1]],
        engine=engine,
        warnings=tuple(warnings),
    )


def open_store(args: argparse.Namespace) -> GraphDB | None:
    if not args.write:
        return None
    store = GraphDB.from_env()
    if store.repository == PRODUCTION_REPOSITORY and not args.to_production:
        print(
            "--write to the production repository needs --to-production: the final label is the "
            "maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def _show_build(data: MvBaseFile, builder: GraphBuilder) -> None:
    graph = graph_name(data.label)
    print(f"label: {data.label}")
    print(f"book: {data.book_code}")
    print(f"graph: {graph}")
    print(f"rows: {len(data.rows)} ({len(WINDOWS)} windows, {len(SEGMENTS) - len(WINDOWS)} cuts)")
    print(f"triples: {len(builder)}")


def _validate(builder: GraphBuilder) -> int:
    try:
        parsed = gate.parse_batch(builder.turtle())
        gate.validate(parsed)
    except gate.IngestRejected as exc:
        print(f"SHACL: FAIL\n{exc}")
        return 1
    print("SHACL: conforms (gate.validate)")
    return 0


def _plan(store: GraphDB, data: MvBaseFile, builder: GraphBuilder) -> gate.IngestPlan:
    graph = graph_name(data.label)
    return gate.plan(store, builder.turtle(), graph)


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901, PLR0911, PLR0915
    args = parse_args(argv)
    started = time.perf_counter()
    directory = args.dir.resolve()
    try:
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        data = load_file(args.label, directory, args.engine_dir)
        print(f"manifest: {REQUIRED_FILES[0]} is listed; SHA-256 {data.json_sha256} matches")
        print(f"manifest: {REQUIRED_FILES[1]} is listed; SHA-256 {data.config_sha256} matches")
        print(f"config: {data.config.label} / {data.config.book_code} / {data.config.status}")
        print(f"code version: sim_v3.py {data.config.code_version}")
        for window in WINDOWS:
            engine = data.engine[window]
            print(
                f"engine {window}: bookId {engine.book_id} (max + 1), backtestRunId {engine.run_id}"
            )
        for warning in data.warnings:
            print(f"WARN  {warning}")
        for warning in records_changed(directory):
            print(f"WARN  {warning}")
        builder = project(data)
        _show_build(data, builder)
        print(f"timing: manifest+parse {time.perf_counter() - started:.3f} s")
        if not args.write and not args.check_store:
            mark = time.perf_counter()
            code = _validate(builder)
            print(f"timing: SHACL {time.perf_counter() - mark:.3f} s")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        store = open_store(args)
        assert store is not None
        mark = time.perf_counter()
        try:
            plan = _plan(store, data, builder)
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        print(f"pre-flight: {plan.status.value}: {graph_name(data.label)}")
        print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
        if args.check_store:
            if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
                print(verify_stored(store, data, builder).detail)
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return 0
        if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
            print(f"already-in-the-store (skipped): {graph_name(data.label)}")
            print(verify_stored(store, data, builder).detail)
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return 0
        mark = time.perf_counter()
        try:
            written = gate.write(store, plan)
        except gate.WriteInDoubt as exc:
            print(
                f"store error, the graph is in doubt: {exc}\n{graph_name(data.label)} was sent "
                "but the store's answer was lost, so it may be written; do not retry blindly",
                file=sys.stderr,
            )
            return 1
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        print(f"written: {graph_name(data.label)}: {written} triples")
        print(f"timing: gate write {time.perf_counter() - mark:.3f} s")
        check = verify_stored(store, data, builder)
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if check.passed else 1  # noqa: TRY300 - success path of the write branch
    except (MvBaseError, ManifestError, GraphDBError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
