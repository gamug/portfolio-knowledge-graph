"""Load the block E daily reference series (SPY and the external MARKOWITZ_MV book).

The series folder carries ``spy_daily.csv``, the seven
``markowitz_mv/mv_daily_<window>.csv`` files and ``markowitz_mv/mv_weights.csv``. Its own
``SHA256SUMS`` is used when present; otherwise the nearest parent's manifest is used and each
entry is matched by its path relative to that parent (the final delivery root lists
``series_diarias_referencia/...``). The loader verifies every series CSV before reading it, rejects
header drift, duplicate keys, missing windows and malformed decimals/dates, then projects one
append-only graph per ``(label, configuration slug)``:

``urn:graph:derived:backtest:series:{label}:markowitz_mv``
``urn:graph:derived:backtest:series:{label}:spy``

No price level or OHLCV is stored: only the columns the CSVs carry. ``--write`` plans both graphs
through the SHACL gate and appends each in bounded N-Triples chunks; a lost answer on a chunk is
reported as a graph in doubt and is never retried blindly.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from kg_store import gate
from kg_store.graphdb import (
    PRODUCTION_REPOSITORY,
    GraphDB,
    GraphDBError,
    announce_target,
)
from projection.backtest import RUN_LABEL_PATTERN, GraphBuilder

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

GRAPH_PREFIX = "urn:graph:derived:backtest:series:"
MANIFEST_NAME = "SHA256SUMS"
BATCH_SIZE = 20_000
WINDOWS = ("P1", "H1", "P3", "H2", "P2", "H3", "C1")
MARKOWITZ_SLUG = "markowitz_mv"
SPY_SLUG = "spy"
CONFIGURATIONS = {
    MARKOWITZ_SLUG: KG.Configuration_MarkowitzMV,
    SPY_SLUG: KG.Configuration_SPY,
}
SPY_FILE = "spy_daily.csv"
MV_DIR = "markowitz_mv"
WEIGHTS_FILE = f"{MV_DIR}/mv_weights.csv"
MV_DAILY_FILES = {window: f"{MV_DIR}/mv_daily_{window}.csv" for window in WINDOWS}
REQUIRED_FILES = (
    SPY_FILE,
    WEIGHTS_FILE,
    *(MV_DAILY_FILES[window] for window in WINDOWS),
)
SPY_HEADER = ("window", "date", "daily_total_return", "value")
MV_DAILY_HEADER = ("date", "gross_return", "net_return", "turnover", "cost", "cash_weight")
WEIGHTS_HEADER = ("window", "decision_date", "asset_id", "weight")

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")
_LABEL = re.compile(RUN_LABEL_PATTERN)
_WINDOW = re.compile(r"([PH][0-9]+|C[0-9]+)")


class SeriesError(ValueError):
    """The series delivery, its manifest or a verification check cannot be accepted."""


class ManifestError(SeriesError):
    """``SHA256SUMS`` is missing, malformed, or does not match a file."""


@dataclass(frozen=True)
class MvDailyRow:
    """One ``mv_daily_<window>.csv`` row."""

    window: str
    date: datetime.date
    gross_return: Decimal
    net_return: Decimal
    turnover: Decimal
    cost: Decimal
    cash_weight: Decimal


@dataclass(frozen=True)
class SpyDailyRow:
    """One ``spy_daily.csv`` row."""

    window: str
    date: datetime.date
    daily_total_return: Decimal
    value: Decimal


@dataclass(frozen=True)
class WeightRow:
    """One ``mv_weights.csv`` row, keyed by (window, decision date, asset id)."""

    window: str
    decision_date: datetime.date
    asset_id: int
    weight: Decimal


@dataclass(frozen=True)
class SeriesFile:
    """The accepted delivery plus the manifest that verified it."""

    label: str
    mv_daily: Mapping[str, tuple[MvDailyRow, ...]]
    spy_daily: tuple[SpyDailyRow, ...]
    weights: tuple[WeightRow, ...]
    hashes: Mapping[str, str]
    manifest: Path


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line in the loader output."""

    name: str
    passed: bool
    detail: str


class ReadableStore(Protocol):
    """What the stored-graph check needs of a store: SPARQL ``SELECT`` only."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


# --- manifest -----------------------------------------------------------------------------------


def read_manifest(path: str | Path) -> dict[str, str]:
    """A strict ``sha256sum`` manifest with safe relative paths."""
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


def _manifest_for(directory: Path) -> tuple[Path, str]:
    """The nearest SHA256SUMS and the prefix of ``directory`` below it."""
    local = directory / MANIFEST_NAME
    if local.is_file():
        return local, ""
    for parent in directory.parents:
        candidate = parent / MANIFEST_NAME
        if candidate.is_file():
            prefix = directory.relative_to(parent).as_posix().rstrip("/") + "/"
            return candidate, prefix
    raise ManifestError(
        f"{directory}: no SHA256SUMS in the series directory or any parent directory"
    )


def verify_manifest(directory: str | Path, required: Sequence[str]) -> tuple[Path, dict[str, str]]:
    """Verify the required CSVs against the nearest manifest, inside or above ``directory``.

    A standalone series folder uses its own ``SHA256SUMS``. In the final delivery the folder has
    no manifest; the parent's manifest lists each series file as
    ``series_diarias_referencia/...``. Only entries below that prefix are verified, so unrelated
    delivery files are not read.
    """
    directory = Path(directory)
    manifest, prefix = _manifest_for(directory)
    entries = read_manifest(manifest)
    selected = {
        name: digest for name, digest in entries.items() if not prefix or name.startswith(prefix)
    }
    out: dict[str, str] = {}
    for name, declared in sorted(selected.items()):
        relative = name[len(prefix) :] if prefix else name
        path = directory / relative
        if not path.is_file():
            raise ManifestError(f"{path}: listed in {manifest.name} but the file does not exist")
        actual = sha256_file(path)
        if actual != declared:
            raise ManifestError(
                f"{path}: SHA-256 mismatch: manifest says {declared}, the file has {actual}"
            )
        out[relative] = actual
    missing = [
        name for name in required if name not in entries and f"{prefix}{name}" not in entries
    ]
    if missing:
        raise ManifestError(f"{manifest}: required file(s) not listed: {', '.join(missing)}")
    for name in required:
        key = f"{prefix}{name}" if prefix else name
        if key not in entries:
            raise ManifestError(f"{manifest}: required file {key!r} is not listed")
        out[name] = entries[key]
    return manifest, out


# --- parsing ------------------------------------------------------------------------------------


def _date(text: str | None, where: str) -> datetime.date:
    if text is None or not _DATE.fullmatch(text):
        raise SeriesError(f"{where}: {text!r} is not a strict YYYY-MM-DD date")
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise SeriesError(f"{where}: {text!r} is not a calendar date ({exc})") from exc
    if day.isoformat() != text:
        raise SeriesError(f"{where}: {text!r} is not the ISO form of {day.isoformat()}")
    return day


def _decimal(text: str | None, where: str) -> Decimal:
    if text is None or not text.strip():
        raise SeriesError(f"{where}: expected a decimal, got an empty value")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise SeriesError(f"{where}: {text!r} is not a decimal") from exc
    if not value.is_finite():
        raise SeriesError(f"{where}: {text!r} is not a finite decimal")
    return value


def _integer(text: str | None, where: str) -> int:
    if text is None:
        raise SeriesError(f"{where}: expected an integer, got nothing")
    try:
        value = int(text)
    except ValueError as exc:
        raise SeriesError(f"{where}: {text!r} is not an integer") from exc
    if value < 1:
        raise SeriesError(f"{where}: {value!r} is not a positive integer")
    return value


def _window(text: str | None, where: str) -> str:
    if text is None or not _WINDOW.fullmatch(text):
        raise SeriesError(f"{where}: {text!r} does not match P<n>, H<n> or C<n>")
    return text


def _rows(path: Path, header: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != tuple(header):
                raise SeriesError(
                    f"{path}: header drift: expected {tuple(header)!r}, "
                    f"got {tuple(reader.fieldnames or ())!r}"
                )
            rows = list(reader)
    except OSError as exc:
        raise SeriesError(f"{path}: {exc}") from exc
    if not rows:
        raise SeriesError(f"{path}: the CSV has no data rows")
    return rows


def parse_spy(path: Path) -> tuple[SpyDailyRow, ...]:
    """Parse ``spy_daily.csv``; every window, including C1, must be present."""
    rows: list[SpyDailyRow] = []
    seen: set[tuple[str, datetime.date]] = set()
    for number, row in enumerate(_rows(path, SPY_HEADER), 2):
        where = f"{path}:{number}"
        window = _window(row["window"], f"{where}.window")
        day = _date(row["date"], f"{where}.date")
        key = (window, day)
        if key in seen:
            raise SeriesError(f"{path}: duplicate (window, date) key {key!r}")
        seen.add(key)
        rows.append(
            SpyDailyRow(
                window,
                day,
                _decimal(row["daily_total_return"], f"{where}.daily_total_return"),
                _decimal(row["value"], f"{where}.value"),
            )
        )
    missing = sorted(set(WINDOWS) - {row.window for row in rows})
    if missing:
        raise SeriesError(f"{path}: missing window(s): {', '.join(missing)}")
    return tuple(rows)


def parse_mv_daily(path: Path, window: str) -> tuple[MvDailyRow, ...]:
    """Parse one ``mv_daily_<window>.csv``; the file carries exactly that window."""
    rows: list[MvDailyRow] = []
    seen: set[datetime.date] = set()
    for number, row in enumerate(_rows(path, MV_DAILY_HEADER), 2):
        where = f"{path}:{number}"
        day = _date(row["date"], f"{where}.date")
        if day in seen:
            raise SeriesError(f"{path}: duplicate (window, date) key {(window, day)!r}")
        seen.add(day)
        rows.append(
            MvDailyRow(
                window,
                day,
                _decimal(row["gross_return"], f"{where}.gross_return"),
                _decimal(row["net_return"], f"{where}.net_return"),
                _decimal(row["turnover"], f"{where}.turnover"),
                _decimal(row["cost"], f"{where}.cost"),
                _decimal(row["cash_weight"], f"{where}.cash_weight"),
            )
        )
    return tuple(rows)


def parse_weights(path: Path) -> tuple[WeightRow, ...]:
    """Parse ``mv_weights.csv``; key is (window, decision date, asset id)."""
    rows: list[WeightRow] = []
    seen: set[tuple[str, datetime.date, int]] = set()
    for number, row in enumerate(_rows(path, WEIGHTS_HEADER), 2):
        where = f"{path}:{number}"
        window = _window(row["window"], f"{where}.window")
        day = _date(row["decision_date"], f"{where}.decision_date")
        asset_id = _integer(row["asset_id"], f"{where}.asset_id")
        key = (window, day, asset_id)
        if key in seen:
            raise SeriesError(f"{path}: duplicate (window, date, asset) key {key!r}")
        seen.add(key)
        rows.append(WeightRow(window, day, asset_id, _decimal(row["weight"], f"{where}.weight")))
    missing = sorted(set(WINDOWS) - {row.window for row in rows})
    if missing:
        raise SeriesError(f"{path}: missing window(s): {', '.join(missing)}")
    return tuple(rows)


def load_file(label: str, directory: Path) -> SeriesFile:
    """Verify the manifest, then parse all CSVs; no file is read before its hash matches."""
    if not _LABEL.fullmatch(label):
        raise SeriesError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    directory = directory.resolve()
    manifest, hashes = verify_manifest(directory, REQUIRED_FILES)
    spy = parse_spy(directory / SPY_FILE)
    mv_daily = {
        window: parse_mv_daily(directory / MV_DAILY_FILES[window], window) for window in WINDOWS
    }
    weights = parse_weights(directory / WEIGHTS_FILE)
    return SeriesFile(label, mv_daily, spy, weights, hashes, manifest)


def file_counts(data: SeriesFile) -> Mapping[str, int]:
    """Rows per source file, for the dry-run report."""
    counts = {SPY_FILE: len(data.spy_daily), WEIGHTS_FILE: len(data.weights)}
    for window, rows in data.mv_daily.items():
        counts[MV_DAILY_FILES[window]] = len(rows)
    return counts


# --- projection ---------------------------------------------------------------------------------


def graph_name(label: str, slug: str) -> str:
    """The append-only graph of one configuration's series."""
    if not _LABEL.fullmatch(label):
        raise SeriesError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    if slug not in CONFIGURATIONS:
        raise SeriesError(f"unknown series configuration slug {slug!r}")
    return f"{GRAPH_PREFIX}{label}:{slug}"


def _configuration(slug: str) -> rdflib.URIRef:
    return CONFIGURATIONS[slug]


def _date_literal(value: datetime.date) -> rdflib.Literal:
    return rdflib.Literal(value.isoformat(), datatype=XSD.date)


def _decimal_literal(value: Decimal) -> rdflib.Literal:
    return rdflib.Literal(format(value, "f"), datatype=XSD.decimal)


def _int_literal(value: int) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.integer)


def daily_point_iri(label: str, slug: str, window: str, day: datetime.date) -> rdflib.URIRef:
    return KG[f"DailySeriesPoint_{label}_{slug}_{window}_{day.strftime('%Y%m%d')}"]


def weight_point_iri(label: str, window: str, day: datetime.date, asset_id: int) -> rdflib.URIRef:
    return KG[f"SeriesWeightPoint_{label}_{window}_{day.strftime('%Y%m%d')}_{asset_id}"]


def project(data: SeriesFile) -> dict[str, GraphBuilder]:
    """Build both graph batches; the MARKOWITZ_MV graph also carries its weights."""
    markowitz = GraphBuilder()
    spy = GraphBuilder()

    def add_daily(
        builder: GraphBuilder,
        slug: str,
        window: str,
        day: datetime.date,
        values: Mapping[rdflib.URIRef, rdflib.Literal],
    ) -> None:
        point = daily_point_iri(data.label, slug, window, day)
        builder.add(point, RDF.type, KG.DailySeriesPoint)
        builder.add(point, KG.seriesOfConfiguration, _configuration(slug))
        builder.add(point, KG.windowId, rdflib.Literal(window))
        builder.add(point, KG.seriesDate, _date_literal(day))
        for predicate, value in values.items():
            builder.add(point, predicate, value)

    for window in WINDOWS:
        for mv_row in data.mv_daily[window]:
            add_daily(
                markowitz,
                MARKOWITZ_SLUG,
                window,
                mv_row.date,
                {
                    KG.seriesGrossReturn: _decimal_literal(mv_row.gross_return),
                    KG.seriesNetReturn: _decimal_literal(mv_row.net_return),
                    KG.seriesTurnover: _decimal_literal(mv_row.turnover),
                    KG.seriesCost: _decimal_literal(mv_row.cost),
                    KG.seriesCashWeight: _decimal_literal(mv_row.cash_weight),
                },
            )
    for spy_row in data.spy_daily:
        add_daily(
            spy,
            SPY_SLUG,
            spy_row.window,
            spy_row.date,
            {
                KG.dailyTotalReturn: _decimal_literal(spy_row.daily_total_return),
                KG.seriesValue: _decimal_literal(spy_row.value),
            },
        )
    for weight_row in data.weights:
        point = weight_point_iri(
            data.label, weight_row.window, weight_row.decision_date, weight_row.asset_id
        )
        markowitz.add(point, RDF.type, KG.SeriesWeightPoint)
        markowitz.add(point, KG.seriesOfConfiguration, _configuration(MARKOWITZ_SLUG))
        markowitz.add(point, KG.windowId, rdflib.Literal(weight_row.window))
        markowitz.add(point, KG.seriesDate, _date_literal(weight_row.decision_date))
        markowitz.add(point, KG.seriesAssetId, _int_literal(weight_row.asset_id))
        markowitz.add(point, KG.seriesWeight, _decimal_literal(weight_row.weight))
    return {MARKOWITZ_SLUG: markowitz, SPY_SLUG: spy}


def expected_window_counts(data: SeriesFile) -> Mapping[str, Mapping[str, int]]:
    """Expected distinct point counts per graph and window."""
    markowitz = {window: len(data.mv_daily[window]) for window in WINDOWS}
    for weight_row in data.weights:
        markowitz[weight_row.window] += 1
    spy = {window: 0 for window in WINDOWS}
    for spy_row in data.spy_daily:
        spy[spy_row.window] += 1
    return {MARKOWITZ_SLUG: markowitz, SPY_SLUG: spy}


# --- store checks -------------------------------------------------------------------------------


def _window_counts(store: ReadableStore, graph: str) -> Mapping[str, int]:
    rows = store.select(
        _PREFIX + "SELECT ?window (COUNT(DISTINCT ?point) AS ?n) "
        f"WHERE {{ GRAPH <{graph}> {{ ?point :windowId ?window }} }} GROUP BY ?window"
    )
    return {str(row["window"]): int(row["n"]) for row in rows}


def _graph_exists(store: ReadableStore, graph: str) -> bool:
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))


def verify_stored(
    store: ReadableStore,
    data: SeriesFile,
    builders: Mapping[str, GraphBuilder],
    *,
    only: Sequence[str] | None = None,
) -> list[Check]:
    """Compare stored per-window point counts with the projected batches."""
    checks: list[Check] = []
    expected = expected_window_counts(data)
    slugs = tuple(only) if only is not None else (MARKOWITZ_SLUG, SPY_SLUG)
    for slug in slugs:
        graph = graph_name(data.label, slug)
        actual = _window_counts(store, graph)
        problems = []
        for window in WINDOWS:
            want = expected[slug][window]
            got = actual.get(window, 0)
            if got != want:
                problems.append(f"{window}: stored {got}, expected {want}")
        extra = sorted(set(actual) - set(WINDOWS))
        if extra:
            problems.append(f"extra window(s): {', '.join(extra)}")
        checks.append(
            Check(
                f"stored {graph}",
                not problems,
                f"{len(builders[slug])} projected triple(s)"
                if not problems
                else "; ".join(problems),
            )
        )
    return checks


# --- CLI ----------------------------------------------------------------------------------------

_PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"


def _label_arg(text: str) -> str:
    if not _LABEL.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in final)"
        )
    return text


def _batch_size(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be a positive integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("batch size must be a positive integer")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--label", required=True, type=_label_arg, help="the run label (final)")
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="the series folder with SHA256SUMS, spy_daily.csv and markowitz_mv/",
    )
    parser.add_argument("--write", action="store_true", help="append the two series graphs")
    parser.add_argument(
        "--check-store",
        action="store_true",
        help="read the live store, run the same gate plans, write nothing",
    )
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=BATCH_SIZE,
        metavar="N",
        help=f"N-Triples per write request (default {BATCH_SIZE})",
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.check_store and args.to_production:
        parser.error("--check-store never writes; drop --to-production")
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    return args


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a --write appends to; production needs the explicit opt-in."""
    if not (args.write or args.check_store):
        return None
    store = GraphDB.from_env()
    if args.write and store.repository == PRODUCTION_REPOSITORY and not args.to_production:
        print(
            "--write to the production repository needs --to-production: the final label is the "
            "maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def _show_build(data: SeriesFile, builders: Mapping[str, GraphBuilder]) -> None:
    print(f"label: {data.label}")
    for name, count in sorted(file_counts(data).items()):
        print(f"rows: {name}: {count}")
    for slug in (MARKOWITZ_SLUG, SPY_SLUG):
        print(f"graph: {graph_name(data.label, slug)}")
        print(f"triples: {slug}: {len(builders[slug])}")


def _validate(builders: Mapping[str, GraphBuilder]) -> int:
    for slug in (MARKOWITZ_SLUG, SPY_SLUG):
        try:
            parsed = gate.parse_batch(builders[slug].turtle())
            gate.validate(parsed)
        except gate.IngestRejected as exc:
            print(f"SHACL: FAIL {slug}\n{exc}")
            return 1
        print(f"SHACL: conforms ({slug}, gate.validate)")
    return 0


def _plan(
    store: GraphDB, data: SeriesFile, builders: Mapping[str, GraphBuilder]
) -> dict[str, gate.IngestPlan]:
    plans: dict[str, gate.IngestPlan] = {}
    for slug in (MARKOWITZ_SLUG, SPY_SLUG):
        plans[slug] = gate.plan(store, builders[slug].turtle(), graph_name(data.label, slug))
    return plans


def _show_plan(plans: Mapping[str, gate.IngestPlan]) -> None:
    for slug, plan in plans.items():
        print(f"pre-flight: {slug}: {plan.status.value}: {plan.graph}")


def _show_checks(checks: Sequence[Check]) -> bool:
    ok = True
    for check in checks:
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
        ok = ok and check.passed
    return ok


def _write_graph(store: GraphDB, plan: gate.IngestPlan, batch_size: int) -> int:
    try:
        return gate.write_batched(store, plan, batch_size=batch_size)
    except gate.WriteInDoubt as exc:
        print(
            f"store error, the graph is in doubt: {exc}\n{plan.graph} may be partially or fully "
            "written; do not retry blindly",
            file=sys.stderr,
        )
        raise
    except gate.IngestRejected as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        raise


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901 -- one return per mode
    args = parse_args(argv)
    started = time.perf_counter()
    directory = args.dir.resolve()
    try:
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        data = load_file(args.label, directory)
        print(f"manifest: using {data.manifest}")
        for name in sorted(data.hashes):
            print(f"manifest: {name} is listed; SHA-256 {data.hashes[name]} matches")
        builders = project(data)
        _show_build(data, builders)
        print(f"timing: manifest+parse {time.perf_counter() - started:.3f} s")
        if not args.write and not args.check_store:
            mark = time.perf_counter()
            code = _validate(builders)
            print(f"timing: SHACL {time.perf_counter() - mark:.3f} s")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        store = open_store(args)
        assert store is not None
        mark = time.perf_counter()
        try:
            plans = _plan(store, data, builders)
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        _show_plan(plans)
        print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
        if args.check_store:
            existing = [
                slug
                for slug, plan in plans.items()
                if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE
            ]
            code = 0
            if existing:
                checks = verify_stored(store, data, builders, only=existing)
                code = 0 if _show_checks(checks) else 1
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        mark = time.perf_counter()
        written = 0
        for slug in (MARKOWITZ_SLUG, SPY_SLUG):
            plan = plans[slug]
            if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
                print(f"already-in-the-store (skipped): {plan.graph}")
                continue
            try:
                count = _write_graph(store, plan, args.batch_size)
            except (gate.WriteInDoubt, gate.IngestRejected):
                return 1
            written += count
            print(f"written: {plan.graph}: {count} triples")
        print(f"timing: gate write {time.perf_counter() - mark:.3f} s")
        checks = verify_stored(store, data, builders)
        ok = _show_checks(checks)
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if ok else 1  # noqa: TRY300 -- the success return pairs with the failure handlers
    except (SeriesError, ManifestError, GraphDBError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
