"""Load the fundamentals block C delivery (Work item 45, T-813-T-815).

The delivery is the folder ``bloque_c_fundamentales/``: ``filings.csv`` (one row per SEC
filing), ``metrics.csv`` (one row per computed ratio, with empty values for a ratio that could
not be computed), ``assessments.jsonl`` (one assessment per filing), ``source.json``, a
``README.md`` and the export script under ``provenance/``. All six files are verified against
``SHA256SUMS``; the manifest's own SHA-256 is fixed in :data:`MANIFEST_SHA256`.

The loader writes one append-only graph, ``urn:graph:derived:fundamentals:{label}``, with one
``:SECFiling`` per filing, one ``:FundamentalMetricSet`` per filing carrying the 37 direct metric
properties, one ``:FundamentalAssessment`` per assessment, and the ``:pricesNotPublished`` flag
for every asset of the SHA-256-verified Tiingo mask. ``value_inputs`` has no property and its
rows are discarded for every asset; a ``valuation`` row of a masked asset stops the load.

Null metric values are omitted, never written as null. The assessment carries its own
``:scoreRaw0to100`` and ``:rating``: there is no ``:ScoreSnapshot`` link, no ``:promptHash`` and
no ``:metricIdsJson``. The parser is strict: an unknown column, group, metric, unit, duplicate
key, malformed date/decimal, foreign key that does not exist or a provenance note that differs
from the delivery stops with a message naming the file, line and key.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import re
import resource
import sqlite3
import sys
import time
import types
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from etl import config as etl_config
from kg_store import gate
from kg_store.graphdb import (
    EXPLICIT_GRAPH,
    PRODUCTION_REPOSITORY,
    GraphDB,
    GraphDBError,
    announce_target,
)
from projection.asset_link import resolve_asset
from projection.backtest import (
    RUN_LABEL_PATTERN,
    AssetInfo,
    GraphBuilder,
    universe_assets,
    validation_context,
)

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

GRAPH_PREFIX = "urn:graph:derived:fundamentals:"
FINAL_LABEL = "final"
MANIFEST_NAME = "SHA256SUMS"
DEFAULT_MASK = Path("/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv")
DEFAULT_DELIVERY = Path(
    "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales"
)

#: SHA-256 of the v2 delivery's own ``SHA256SUMS``.
MANIFEST_SHA256 = "fd32daed391f515e5ff76e030acaab2dd018fea8dadf4d206429274bbe6ee677"
#: SHA-256 of ``mascara_tiingo/tiingo_assets.csv``.
MASK_SHA256 = "4712c7c224bd76b4661260d77d95ce3c62fe80710c0b7d30a1ce44ac00c39dce"

REQUIRED_FILES = (
    "README.md",
    "filings.csv",
    "metrics.csv",
    "assessments.jsonl",
    "source.json",
    "provenance/export_bloque_c.py",
)
FILINGS_HEADER = (
    "filing_id",
    "asset_id",
    "ticker",
    "cik",
    "form",
    "fiscal_year",
    "fiscal_period",
    "period_end",
    "filing_date",
    "available_at",
    "accession_number",
)
METRICS_HEADER = (
    "metric_id",
    "filing_id",
    "metric_group",
    "metric_name",
    "value",
    "unit",
    "engine_version",
    "computed_at",
    "available_at",
)
MASK_HEADER = ("asset_id", "ticker", "tiingo_price_rows", "first_date", "last_date")
ASSESSMENT_KEYS = frozenset(
    {
        "snapshot_id",
        "asset_id",
        "ticker",
        "filing_id",
        "score_raw_0_100",
        "rating",
        "narrative",
        "strengths",
        "risks",
        "model",
        "prompt_hash",
        "computed_at",
        "event_time",
        "available_at",
        "generated_by_language_model",
        "provenance_note",
    }
)
SOURCE_KEYS = frozenset({"source_db", "source_db_sha256"})

#: The 38 source metric names -> the source group and unit. ``value_inputs`` has no property.
METRIC_GROUPS: Mapping[str, str] = {
    "return_on_equity": "profitability",
    "net_margin": "profitability",
    "operating_margin": "profitability",
    "gross_margin": "profitability",
    "return_on_assets": "profitability",
    "return_on_invested_capital": "roic",
    "return_on_invested_capital_effective_rate": "roic",
    "effective_tax_rate": "roic",
    "nopat": "roic",
    "interest_coverage": "leverage",
    "ebitda": "leverage",
    "net_debt_to_ebitda": "leverage",
    "debt_to_equity": "leverage",
    "debt_to_assets": "leverage",
    "operating_cash_flow_margin": "cashflow",
    "capex_intensity": "cashflow",
    "free_cash_flow_margin": "cashflow",
    "free_cash_flow_conversion": "cashflow",
    "cash_ratio": "liquidity",
    "current_ratio": "liquidity",
    "quick_ratio": "liquidity",
    "free_cash_flow_yield": "valuation",
    "sbc_adjusted_fcf_yield": "valuation",
    "enterprise_fcf_yield": "valuation",
    "enterprise_value": "valuation",
    "market_capitalization": "valuation",
    "revenue_growth": "growth",
    "net_income_growth": "growth",
    "operating_income_growth": "growth",
    "free_cash_flow_growth": "growth",
    "asset_turnover": "efficiency",
    "receivables_turnover": "efficiency",
    "inventory_turnover": "efficiency",
    "net_income_cagr": "cagr",
    "revenue_cagr": "cagr",
    "operating_cash_flow_cagr": "cagr",
    "utility_cash_coverage_3y": "rule_input",
    "value_inputs": "rule_input",
}
METRIC_UNITS: Mapping[str, str] = {
    **{name: "ratio" for name in METRIC_GROUPS},
    **{
        name: "x"
        for name in (
            "interest_coverage",
            "net_debt_to_ebitda",
            "debt_to_equity",
            "free_cash_flow_conversion",
            "cash_ratio",
            "current_ratio",
            "quick_ratio",
            "asset_turnover",
            "receivables_turnover",
            "inventory_turnover",
        )
    },
    **{
        name: "usd"
        for name in (
            "nopat",
            "ebitda",
            "enterprise_value",
            "market_capitalization",
            "value_inputs",
        )
    },
}
#: The 37 loaded source names -> the TBox property local name (``value_inputs`` is absent).
METRIC_PROPERTIES: Mapping[str, str] = {
    "asset_turnover": "assetTurnover",
    "capex_intensity": "capexIntensity",
    "cash_ratio": "cashRatio",
    "current_ratio": "currentRatio",
    "debt_to_assets": "debtToAssets",
    "debt_to_equity": "debtToEquity",
    "ebitda": "ebitda",
    "effective_tax_rate": "effectiveTaxRate",
    "enterprise_fcf_yield": "enterpriseFcfYield",
    "enterprise_value": "enterpriseValue",
    "free_cash_flow_conversion": "freeCashFlowConversion",
    "free_cash_flow_growth": "freeCashFlowGrowth",
    "free_cash_flow_margin": "freeCashFlowMargin",
    "free_cash_flow_yield": "freeCashFlowYield",
    "gross_margin": "grossMargin",
    "interest_coverage": "interestCoverage",
    "inventory_turnover": "inventoryTurnover",
    "market_capitalization": "marketCapitalization",
    "net_debt_to_ebitda": "netDebtToEbitda",
    "net_income_cagr": "netIncomeCagr",
    "net_income_growth": "netIncomeGrowth",
    "net_margin": "netMargin",
    "nopat": "nopat",
    "operating_cash_flow_cagr": "operatingCashFlowCagr",
    "operating_cash_flow_margin": "operatingCashFlowMargin",
    "operating_income_growth": "operatingIncomeGrowth",
    "operating_margin": "operatingMargin",
    "quick_ratio": "quickRatio",
    "receivables_turnover": "receivablesTurnover",
    "return_on_assets": "returnOnAssets",
    "return_on_equity": "returnOnEquity",
    "return_on_invested_capital": "returnOnInvestedCapital",
    "return_on_invested_capital_effective_rate": "returnOnInvestedCapitalEffectiveRate",
    "revenue_cagr": "revenueCagr",
    "revenue_growth": "revenueGrowth",
    "sbc_adjusted_fcf_yield": "sbcAdjustedFcfYield",
    "utility_cash_coverage_3y": "utilityCashCoverage3y",
}
METRIC_GROUP_NAMES = frozenset(METRIC_GROUPS.values())
VALUE_INPUTS = "value_inputs"
VALUATION_GROUP = "valuation"
ENGINE_VERSION = "metrics-v10"
RULE_MODEL = "unscored-pillar-coverage-v1"
GENERATED_PROVENANCE = "generated by a language model from computed ratios; not a verified fact"
RULE_PROVENANCE = "rule-based text: no fundamental score (coverage rule); not generated by a model"
RATINGS = frozenset({"bullish", "neutral", "bearish"})
MAX_SCORE = Decimal(100)
FORMS = frozenset({"10-K", "10-Q"})
UNITS = frozenset({"ratio", "x", "usd"})
#: Properties that must never appear in this batch: the delivery has no price or daily return.
FORBIDDEN_PROPERTIES = frozenset(
    {
        "closePrice",
        "adjustedClose",
        "dailyReturn",
        "dailyReturnPct",
        "PriceObservation",
        "observationDate",
        "atr14",
    }
)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_DECIMAL = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")
_TICKER = re.compile(r"[A-Z0-9]{1,6}(?:\.[A-Z])?")
_LABEL = re.compile(RUN_LABEL_PATTERN)


class FundamentalsError(ValueError):
    """The delivery, its manifest or a verification check cannot be accepted."""


class ManifestError(FundamentalsError):
    """``SHA256SUMS`` is missing, malformed, or does not match a required file."""


@dataclass(frozen=True)
class Filing:
    """One ``filings.csv`` row."""

    filing_id: int
    asset_id: int
    ticker: str
    cik: str
    form: str
    fiscal_year: int
    fiscal_period: str
    period_end: datetime.date
    filing_date: datetime.date
    available_at: datetime.date
    accession_number: str
    line: int


@dataclass(frozen=True)
class MetricRow:
    """One ``metrics.csv`` row; ``value`` is None when the CSV value is empty."""

    metric_id: int
    filing_id: int
    group: str
    name: str
    value: Decimal | None
    unit: str
    engine_version: str
    computed_at: datetime.datetime
    computed_at_text: str
    available_at: datetime.date
    line: int


@dataclass(frozen=True)
class Assessment:
    """One ``assessments.jsonl`` row."""

    snapshot_id: int
    asset_id: int
    ticker: str
    filing_id: int
    score: Decimal | None
    rating: str | None
    narrative: str
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    model: str
    prompt_hash: str | None
    computed_at: datetime.datetime
    computed_at_text: str
    event_time: datetime.date
    available_at: datetime.date
    generated: bool
    provenance_note: str
    line: int


@dataclass(frozen=True)
class MaskAsset:
    """One row of ``mascara_tiingo/tiingo_assets.csv``."""

    asset_id: int
    ticker: str
    price_rows: int
    first_date: datetime.date
    last_date: datetime.date
    line: int


@dataclass(frozen=True)
class FundamentalsStats:
    """The counts the CLI prints and the tests assert."""

    filings: int
    metric_sets: int
    metric_rows: int
    metric_values: int
    null_values: int
    value_inputs_rows: int
    masked_value_inputs_rows: int
    assessments: int
    scored: int
    rule_rows: int
    strengths: int
    risks: int
    masked_flags: int


@dataclass(frozen=True)
class FundamentalsFile:
    """The accepted delivery plus its manifest, mask and resolved asset identities."""

    label: str
    directory: Path
    filings: tuple[Filing, ...]
    metrics: tuple[MetricRow, ...]
    assessments: tuple[Assessment, ...]
    mask: tuple[MaskAsset, ...]
    hashes: Mapping[str, str]
    manifest_sha256: str
    mask_sha256: str
    source_db: str
    source_db_sha256: str
    assets: Mapping[str, str] = field(default_factory=dict)
    asset_infos: Mapping[str, AssetInfo] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line in the stored-graph verification."""

    name: str
    passed: bool
    detail: str


class ReadableStore(Protocol):
    """What the stored-graph check needs of a store: SPARQL ``SELECT`` only."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


# --- reading and validating the delivery --------------------------------------------------------


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise FundamentalsError(
                f"duplicate JSON key {key!r}: the file contract has unique keys"
            )
        out[key] = value
    return out


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise FundamentalsError(f"{where}: expected a JSON object, got {type(value).__name__}")
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
        raise FundamentalsError(f"{where}: {'; '.join(parts)}")


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FundamentalsError(f"{where}: expected a non-empty string")
    return value


def _integer(value: object, where: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FundamentalsError(f"{where}: expected an integer, got {type(value).__name__}")
    if value < minimum:
        raise FundamentalsError(f"{where}: {value} is below {minimum}")
    return value


def _date_text(text: str, where: str) -> datetime.date:
    if not _DATE.fullmatch(text):
        raise FundamentalsError(f"{where}: {text!r} is not a strict YYYY-MM-DD date")
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise FundamentalsError(f"{where}: {text!r} is not a calendar date ({exc})") from exc
    if day.isoformat() != text:
        raise FundamentalsError(f"{where}: {text!r} is not the ISO form of {day.isoformat()}")
    return day


def _datetime_text(text: str, where: str) -> datetime.datetime:
    if not _DATE_TIME.fullmatch(text):
        raise FundamentalsError(f"{where}: {text!r} is not a dateTime with a timezone")
    try:
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FundamentalsError(f"{where}: {text!r} is not a dateTime ({exc})") from exc
    if moment.tzinfo is None:
        raise FundamentalsError(f"{where}: {text!r} has no timezone")
    return moment


def _decimal_text(text: str, where: str) -> Decimal:
    if not _DECIMAL.fullmatch(text):
        raise FundamentalsError(f"{where}: {text!r} is not a decimal")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise FundamentalsError(f"{where}: {text!r} is not a decimal") from exc
    if not number.is_finite():
        raise FundamentalsError(f"{where}: {text!r} is not a finite decimal")
    return number


def _decimal_value(value: object, where: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise FundamentalsError(f"{where}: expected a JSON number, got {type(value).__name__}")
    number = Decimal(value) if isinstance(value, int) else value
    if not number.is_finite():
        raise FundamentalsError(f"{where}: {value!r} is not a finite decimal")
    return number


def read_manifest(path: str | Path) -> dict[str, str]:
    """A strict ``sha256sum`` manifest; paths are allowed for the provenance entry."""
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


def verify_manifest(
    directory: str | Path,
    file_names: Sequence[str] = REQUIRED_FILES,
    *,
    expected_manifest_sha256: str | None = None,
) -> tuple[dict[str, str], str]:
    """Verify the manifest's own hash and every required file's hash; return both."""
    directory = Path(directory)
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        raise ManifestError(f"{manifest}: no SHA256SUMS in the delivery directory")
    actual_manifest = sha256_file(manifest)
    expected_manifest = expected_manifest_sha256 or MANIFEST_SHA256
    if actual_manifest != expected_manifest:
        raise ManifestError(
            f"{manifest}: SHA-256 mismatch: expected {expected_manifest}, the file has "
            f"{actual_manifest}"
        )
    entries = read_manifest(manifest)
    hashes: dict[str, str] = {}
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
        hashes[name] = expected
    return hashes, actual_manifest


def _csv_rows(path: Path, header: tuple[str, ...]) -> Sequence[tuple[int, list[str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                actual = tuple(next(reader))
            except StopIteration as exc:
                raise FundamentalsError(f"{path}: the file is empty") from exc
            if actual != header:
                missing = [name for name in header if name not in actual]
                extra = [name for name in actual if name not in header]
                parts = []
                if missing:
                    parts.append("missing " + ", ".join(missing))
                if extra:
                    parts.append("unknown " + ", ".join(extra))
                raise FundamentalsError(
                    f"{path}: the header is not the delivery contract ({'; '.join(parts) or actual})"
                )
            rows: list[tuple[int, list[str]]] = []
            for raw in reader:
                if len(raw) != len(header):
                    raise FundamentalsError(
                        f"{path}:{reader.line_num}: expected {len(header)} columns, got {len(raw)}"
                    )
                rows.append((reader.line_num, raw))
            return rows
    except OSError as exc:
        raise FundamentalsError(f"{path}: {exc}") from exc


def parse_filings(path: str | Path) -> dict[int, Filing]:  # noqa: C901, PLR0912
    """Read ``filings.csv`` and enforce its keys, dates and identity consistency."""
    path = Path(path)
    filings: dict[int, Filing] = {}
    accessions: dict[str, int] = {}
    ticker_asset: dict[str, int] = {}
    asset_ticker: dict[int, str] = {}
    for line, raw in _csv_rows(path, FILINGS_HEADER):
        where = f"{path}:{line}"
        (
            filing_id_text,
            asset_id_text,
            ticker,
            cik,
            form,
            fiscal_year_text,
            fiscal_period,
            period_end_text,
            filing_date_text,
            available_at_text,
            accession_number,
        ) = raw
        try:
            filing_id = int(filing_id_text)
            asset_id = int(asset_id_text)
            fiscal_year = int(fiscal_year_text)
        except ValueError as exc:
            raise FundamentalsError(f"{where}: a numeric key is not an integer ({exc})") from exc
        _integer(filing_id, f"{where}: filing_id")
        _integer(asset_id, f"{where}: asset_id")
        _integer(fiscal_year, f"{where}: fiscal_year", minimum=0)
        if not _TICKER.fullmatch(ticker):
            raise FundamentalsError(f"{where}: ticker {ticker!r} is not a plain ticker")
        if not re.fullmatch(r"\d{10}", cik):
            raise FundamentalsError(f"{where}: cik {cik!r} is not ten digits")
        if form not in FORMS:
            raise FundamentalsError(f"{where}: form {form!r} is not 10-K or 10-Q")
        if not fiscal_period.strip():
            raise FundamentalsError(f"{where}: fiscal_period is empty")
        if not accession_number.strip():
            raise FundamentalsError(f"{where}: accession_number is empty")
        period_end = _date_text(period_end_text, f"{where}: period_end")
        filing_date = _date_text(filing_date_text, f"{where}: filing_date")
        available_at = _date_text(available_at_text, f"{where}: available_at")
        if available_at < filing_date:
            raise FundamentalsError(
                f"{where}: available_at {available_at} is before filing_date {filing_date}"
            )
        if filing_id in filings:
            raise FundamentalsError(f"{where}: duplicate filing_id {filing_id}")
        if accession_number in accessions:
            raise FundamentalsError(
                f"{where}: duplicate accession_number {accession_number!r} "
                f"(filing_id {accessions[accession_number]})"
            )
        previous_asset = ticker_asset.setdefault(ticker, asset_id)
        if previous_asset != asset_id:
            raise FundamentalsError(
                f"{where}: ticker {ticker!r} has asset_id {previous_asset} elsewhere and "
                f"{asset_id} here"
            )
        previous_ticker = asset_ticker.setdefault(asset_id, ticker)
        if previous_ticker != ticker:
            raise FundamentalsError(
                f"{where}: asset_id {asset_id} has ticker {previous_ticker!r} elsewhere and "
                f"{ticker!r} here"
            )
        accessions[accession_number] = filing_id
        filings[filing_id] = Filing(
            filing_id,
            asset_id,
            ticker,
            cik,
            form,
            fiscal_year,
            fiscal_period,
            period_end,
            filing_date,
            available_at,
            accession_number,
            line,
        )
    if not filings:
        raise FundamentalsError(f"{path}: no filings")
    return filings


def parse_metrics(  # noqa: C901, PLR0912
    path: str | Path, filings: Mapping[int, Filing]
) -> tuple[MetricRow, ...]:
    """Read ``metrics.csv``; empty values are null, every other value must be a decimal."""
    path = Path(path)
    rows: list[MetricRow] = []
    metric_ids: set[int] = set()
    identities: set[tuple[int, str]] = set()
    for line, raw in _csv_rows(path, METRICS_HEADER):
        where = f"{path}:{line}"
        (
            metric_id_text,
            filing_id_text,
            group,
            name,
            value_text,
            unit,
            engine_version,
            computed_at_text,
            available_at_text,
        ) = raw
        try:
            metric_id = int(metric_id_text)
            filing_id = int(filing_id_text)
        except ValueError as exc:
            raise FundamentalsError(f"{where}: a numeric key is not an integer ({exc})") from exc
        _integer(metric_id, f"{where}: metric_id")
        _integer(filing_id, f"{where}: filing_id")
        filing = filings.get(filing_id)
        if filing is None:
            raise FundamentalsError(f"{where}: filing_id {filing_id} is not in filings.csv")
        if group not in METRIC_GROUP_NAMES:
            raise FundamentalsError(f"{where}: unknown metric_group {group!r}")
        if name not in METRIC_GROUPS:
            raise FundamentalsError(f"{where}: unknown metric_name {name!r}")
        if METRIC_GROUPS[name] != group:
            raise FundamentalsError(
                f"{where}: metric_name {name!r} belongs to {METRIC_GROUPS[name]!r}, not {group!r}"
            )
        if unit not in UNITS:
            raise FundamentalsError(f"{where}: unknown unit {unit!r}")
        if METRIC_UNITS[name] != unit:
            raise FundamentalsError(
                f"{where}: metric_name {name!r} has unit {METRIC_UNITS[name]!r}, not {unit!r}"
            )
        if engine_version != ENGINE_VERSION:
            raise FundamentalsError(
                f"{where}: engine_version {engine_version!r} is not {ENGINE_VERSION!r}"
            )
        computed_at = _datetime_text(computed_at_text, f"{where}: computed_at")
        available_at = _date_text(available_at_text, f"{where}: available_at")
        if available_at != filing.available_at:
            raise FundamentalsError(
                f"{where}: available_at {available_at} differs from filing {filing_id}'s "
                f"{filing.available_at}"
            )
        value = (
            None if not value_text.strip() else _decimal_text(value_text.strip(), f"{where}: value")
        )
        if metric_id in metric_ids:
            raise FundamentalsError(f"{where}: duplicate metric_id {metric_id}")
        identity = (filing_id, name)
        if identity in identities:
            raise FundamentalsError(
                f"{where}: duplicate (filing_id, metric_name) = ({filing_id}, {name!r})"
            )
        metric_ids.add(metric_id)
        identities.add(identity)
        rows.append(
            MetricRow(
                metric_id,
                filing_id,
                group,
                name,
                value,
                unit,
                engine_version,
                computed_at,
                computed_at_text,
                available_at,
                line,
            )
        )
    if not rows:
        raise FundamentalsError(f"{path}: no metric rows")
    return tuple(rows)


def _string_list(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise FundamentalsError(f"{where}: expected a JSON array, got {type(value).__name__}")
    items = tuple(_string(item, f"{where}[{index}]") for index, item in enumerate(value))
    if len(set(items)) != len(items):
        raise FundamentalsError(f"{where}: duplicate text; each strength/risk is written once")
    return items


def parse_assessments(  # noqa: C901, PLR0912, PLR0915
    path: str | Path, filings: Mapping[int, Filing]
) -> tuple[Assessment, ...]:
    """Read ``assessments.jsonl`` and verify the delivery's provenance strings character for
    character before any of them reaches the graph."""
    path = Path(path)
    rows: list[Assessment] = []
    snapshot_ids: set[int] = set()
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise FundamentalsError(f"{path}: {exc}") from exc
    with handle:
        for line, raw in enumerate(handle, 1):
            where = f"{path}:{line}"
            if not raw.strip():
                raise FundamentalsError(f"{where}: empty JSON line")
            try:
                document = json.loads(raw, parse_float=Decimal, object_pairs_hook=_duplicates)
            except json.JSONDecodeError as exc:
                raise FundamentalsError(f"{where}: not valid JSON ({exc})") from exc
            row = _object(document, where)
            _keys(row, ASSESSMENT_KEYS, where)
            snapshot_id = _integer(row["snapshot_id"], f"{where}: snapshot_id")
            asset_id = _integer(row["asset_id"], f"{where}: asset_id")
            filing_id = _integer(row["filing_id"], f"{where}: filing_id")
            filing = filings.get(filing_id)
            if filing is None:
                raise FundamentalsError(f"{where}: filing_id {filing_id} is not in filings.csv")
            ticker = _string(row["ticker"], f"{where}: ticker")
            if ticker != filing.ticker or asset_id != filing.asset_id:
                raise FundamentalsError(
                    f"{where}: (asset_id, ticker) = ({asset_id}, {ticker!r}) differs from "
                    f"filing {filing_id}'s ({filing.asset_id}, {filing.ticker!r})"
                )
            if snapshot_id in snapshot_ids:
                raise FundamentalsError(f"{where}: duplicate snapshot_id {snapshot_id}")
            snapshot_ids.add(snapshot_id)
            generated = row["generated_by_language_model"]
            if not isinstance(generated, bool):
                raise FundamentalsError(
                    f"{where}: generated_by_language_model must be a JSON boolean"
                )
            model = _string(row["model"], f"{where}: model")
            score = _decimal_value(row["score_raw_0_100"], f"{where}: score_raw_0_100")
            rating_raw = row["rating"]
            if rating_raw is not None and rating_raw not in RATINGS:
                raise FundamentalsError(f"{where}: rating {rating_raw!r} is not a rating")
            rating = rating_raw if isinstance(rating_raw, str) else None
            if generated:
                if score is None or rating is None:
                    raise FundamentalsError(
                        f"{where}: a generated assessment needs a score and a rating"
                    )
                if score < 0 or score > MAX_SCORE:
                    raise FundamentalsError(f"{where}: score {score} is not in [0, 100]")
                if model == RULE_MODEL:
                    raise FundamentalsError(
                        f"{where}: generated_by_language_model true with the rule model"
                    )
                expected_provenance = GENERATED_PROVENANCE
            else:
                if score is not None or rating is not None:
                    raise FundamentalsError(
                        f"{where}: a rule-based assessment must not carry a score or rating"
                    )
                if model != RULE_MODEL:
                    raise FundamentalsError(
                        f"{where}: a rule-based assessment needs model {RULE_MODEL!r}, "
                        f"got {model!r}"
                    )
                expected_provenance = RULE_PROVENANCE
            provenance = _string(row["provenance_note"], f"{where}: provenance_note")
            if provenance != expected_provenance:
                raise FundamentalsError(
                    f"{where}: provenance_note differs from the delivery text: {provenance!r}; "
                    f"expected {expected_provenance!r}"
                )
            prompt_hash = row["prompt_hash"]
            if prompt_hash is not None and (
                not isinstance(prompt_hash, str) or not _SHA256.fullmatch(prompt_hash)
            ):
                raise FundamentalsError(f"{where}: prompt_hash must be a 64-hex string or null")
            narrative = _string(row["narrative"], f"{where}: narrative")
            strengths = _string_list(row["strengths"], f"{where}.strengths")
            risks = _string_list(row["risks"], f"{where}.risks")
            computed_at = _datetime_text(
                _string(row["computed_at"], f"{where}: computed_at"), f"{where}: computed_at"
            )
            event_time = _date_text(
                _string(row["event_time"], f"{where}: event_time"), f"{where}: event_time"
            )
            available_at = _date_text(
                _string(row["available_at"], f"{where}: available_at"), f"{where}: available_at"
            )
            if event_time != filing.period_end:
                raise FundamentalsError(
                    f"{where}: event_time {event_time} differs from filing {filing_id}'s "
                    f"period_end {filing.period_end}"
                )
            if available_at != filing.available_at:
                raise FundamentalsError(
                    f"{where}: available_at {available_at} differs from filing {filing_id}'s "
                    f"{filing.available_at}"
                )
            rows.append(
                Assessment(
                    snapshot_id,
                    asset_id,
                    ticker,
                    filing_id,
                    score,
                    rating,
                    narrative,
                    strengths,
                    risks,
                    model,
                    prompt_hash,
                    computed_at,
                    _string(row["computed_at"], f"{where}: computed_at"),
                    event_time,
                    available_at,
                    generated,
                    provenance,
                    line,
                )
            )
    if not rows:
        raise FundamentalsError(f"{path}: no assessments")
    return tuple(rows)


def parse_mask(path: str | Path, *, expected_sha256: str | None = None) -> tuple[MaskAsset, ...]:
    """Verify the mask's SHA-256 and read its 33 ``asset_id``/``ticker`` rows."""
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"{path}: the Tiingo mask file is missing")
    actual = sha256_file(path)
    expected = expected_sha256 or MASK_SHA256
    if actual != expected:
        raise ManifestError(f"{path}: SHA-256 mismatch: expected {expected}, the file has {actual}")
    rows: list[MaskAsset] = []
    asset_ids: set[int] = set()
    tickers: set[str] = set()
    for line, raw in _csv_rows(path, MASK_HEADER):
        where = f"{path}:{line}"
        asset_id_text, ticker, price_rows_text, first_date_text, last_date_text = raw
        try:
            asset_id = int(asset_id_text)
            price_rows = int(price_rows_text)
        except ValueError as exc:
            raise FundamentalsError(f"{where}: a numeric field is not an integer ({exc})") from exc
        _integer(asset_id, f"{where}: asset_id")
        _integer(price_rows, f"{where}: tiingo_price_rows")
        if not _TICKER.fullmatch(ticker):
            raise FundamentalsError(f"{where}: ticker {ticker!r} is not a plain ticker")
        first_date = _date_text(first_date_text, f"{where}: first_date")
        last_date = _date_text(last_date_text, f"{where}: last_date")
        if first_date > last_date:
            raise FundamentalsError(
                f"{where}: first_date {first_date} is after last_date {last_date}"
            )
        if asset_id in asset_ids:
            raise FundamentalsError(f"{where}: duplicate asset_id {asset_id}")
        if ticker in tickers:
            raise FundamentalsError(f"{where}: duplicate ticker {ticker!r}")
        asset_ids.add(asset_id)
        tickers.add(ticker)
        rows.append(MaskAsset(asset_id, ticker, price_rows, first_date, last_date, line))
    if not rows:
        raise FundamentalsError(f"{path}: the mask has no assets")
    return tuple(rows)


def parse_source(path: str | Path) -> tuple[str, str]:
    """Read ``source.json``: the source database name and its SHA-256."""
    path = Path(path)
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            object_pairs_hook=_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise FundamentalsError(f"{path}: not valid JSON ({exc})") from exc
    row = _object(document, str(path))
    _keys(row, SOURCE_KEYS, str(path))
    source_db = _string(row["source_db"], f"{path}: source_db")
    source_sha = _string(row["source_db_sha256"], f"{path}: source_db_sha256")
    if not _SHA256.fullmatch(source_sha):
        raise FundamentalsError(f"{path}: source_db_sha256 is not 64 lowercase hex")
    return source_db, source_sha


def _is_masked(filing: Filing, mask: Sequence[MaskAsset]) -> bool:
    """Whether the mask file lists this filing's engine asset id (the stable key)."""
    return any(row.asset_id == filing.asset_id for row in mask)


def masked_rows(
    metrics: Sequence[MetricRow], filings: Mapping[int, Filing], mask: Sequence[MaskAsset]
) -> list[str]:
    """The ``valuation`` rows of masked assets; the load stops if there is any."""
    problems: list[str] = []
    for row in metrics:
        filing = filings[row.filing_id]
        if row.group == VALUATION_GROUP and _is_masked(filing, mask):
            problems.append(
                f"metrics.csv line {row.line}: metric_id {row.metric_id}, filing_id "
                f"{row.filing_id}, ticker {filing.ticker}, metric_name {row.name}"
            )
    return problems


def _resolve_mask_tickers(
    filings: Sequence[Filing],
    mask: Sequence[MaskAsset],
    universe_db: str | Path | None,
    reference_path: str | Path | None,
) -> tuple[dict[str, str], Mapping[str, AssetInfo]]:
    if universe_db is None:
        universe_db = etl_config.universe_db_path()
    try:
        available = universe_assets(universe_db, reference_path)
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise FundamentalsError(
            f"{universe_db}: cannot read the universe/reference assets for the mask ({exc})"
        ) from exc
    ciks_by_ticker: defaultdict[str, set[str]] = defaultdict(set)
    for filing in filings:
        ciks_by_ticker[filing.ticker].add(filing.cik)
    # A ticker reused by two companies has no single CIK; the exact symbol still wins, as in
    # the backtest projector's resolver, and the CIK fallback is only for an unambiguous symbol.
    ciks = {
        ticker: next(iter(values)) for ticker, values in ciks_by_ticker.items() if len(values) == 1
    }
    wanted = sorted({filing.ticker for filing in filings} | {row.ticker for row in mask})
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for ticker in wanted:
        link = resolve_asset(ticker, ciks.get(ticker), available)
        if link.iri is None:
            unresolved.append(ticker)
        else:
            resolved[ticker] = link.iri
    if unresolved:
        raise FundamentalsError(
            "tickers that do not resolve to a loaded :Asset through the universe/reference "
            "resolution: " + ", ".join(unresolved)
        )
    mask_iris = [resolved[row.ticker] for row in mask]
    duplicates = sorted({name for name in mask_iris if mask_iris.count(name) > 1})
    if duplicates:
        raise FundamentalsError(
            "masked tickers that resolve to the same :Asset: " + ", ".join(duplicates)
        )
    infos = {name: available[name] for name in sorted(set(resolved.values()))}
    return resolved, infos


def parse_delivery(
    directory: str | Path,
    label: str,
    *,
    mask_path: str | Path = DEFAULT_MASK,
    expected_manifest_sha256: str | None = None,
    expected_mask_sha256: str | None = None,
) -> FundamentalsFile:
    """Verify the manifest and parse the four data files (without the universe lookup)."""
    directory = Path(directory)
    hashes, manifest_sha = verify_manifest(
        directory, REQUIRED_FILES, expected_manifest_sha256=expected_manifest_sha256
    )
    source_db, source_sha = parse_source(directory / "source.json")
    filings = parse_filings(directory / "filings.csv")
    metrics = parse_metrics(directory / "metrics.csv", filings)
    assessments = parse_assessments(directory / "assessments.jsonl", filings)
    mask = parse_mask(mask_path, expected_sha256=expected_mask_sha256)
    problems = masked_rows(metrics, filings, mask)
    if problems:
        raise FundamentalsError(
            "a valuation row of a masked asset must not be loaded: " + "; ".join(problems)
        )
    return FundamentalsFile(
        label=label,
        directory=directory,
        filings=tuple(filings.values()),
        metrics=metrics,
        assessments=assessments,
        mask=mask,
        hashes=hashes,
        manifest_sha256=manifest_sha,
        mask_sha256=sha256_file(mask_path),
        source_db=source_db,
        source_db_sha256=source_sha,
    )


def load_file(  # noqa: PLR0913
    label: str,
    directory: str | Path,
    *,
    mask_path: str | Path = DEFAULT_MASK,
    universe_db: str | Path | None = None,
    reference_path: str | Path | None = None,
    expected_manifest_sha256: str | None = None,
    expected_mask_sha256: str | None = None,
) -> FundamentalsFile:
    """Verify the manifest and the mask, parse the delivery and resolve every asset."""
    _check_label(label)
    data = parse_delivery(
        directory,
        label,
        mask_path=mask_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_mask_sha256=expected_mask_sha256,
    )
    assets, infos = _resolve_mask_tickers(data.filings, data.mask, universe_db, reference_path)
    return replace(data, assets=assets, asset_infos=infos)


# --- the batch ----------------------------------------------------------------------------------


def _check_label(label: str) -> str:
    if not _LABEL.fullmatch(label):
        raise FundamentalsError(
            f"run label {label!r} does not match the pattern {RUN_LABEL_PATTERN} (as in final)"
        )
    return label


def graph_name(label: str) -> str:
    """The append-only fundamentals graph of one run label."""
    return f"{GRAPH_PREFIX}{_check_label(label)}"


def filing_iri(label: str, filing_id: int) -> rdflib.URIRef:
    return KG[f"Filing_{label}_{filing_id}"]


def metric_set_iri(label: str, filing_id: int) -> rdflib.URIRef:
    return KG[f"FundamentalMetricSet_{label}_{filing_id}"]


def assessment_iri(label: str, snapshot_id: int) -> rdflib.URIRef:
    return KG[f"FundamentalAssessment_{label}_{snapshot_id}"]


def _date_literal(value: datetime.date) -> rdflib.Literal:
    return rdflib.Literal(value.isoformat(), datatype=XSD.date)


def _decimal_literal(value: Decimal) -> rdflib.Literal:
    return rdflib.Literal(format(value, "f"), datatype=XSD.decimal)


def statistics(data: FundamentalsFile) -> FundamentalsStats:
    """The counts the run record and the tests assert."""
    filings = {filing.filing_id: filing for filing in data.filings}
    value_inputs = [row for row in data.metrics if row.name == VALUE_INPUTS]
    loaded = [row for row in data.metrics if row.name != VALUE_INPUTS]
    masked_value_inputs = [
        row for row in value_inputs if _is_masked(filings[row.filing_id], data.mask)
    ]
    return FundamentalsStats(
        filings=len(data.filings),
        metric_sets=len(data.filings),
        metric_rows=len(data.metrics),
        metric_values=sum(1 for row in loaded if row.value is not None),
        null_values=sum(1 for row in loaded if row.value is None),
        value_inputs_rows=len(value_inputs),
        masked_value_inputs_rows=len(masked_value_inputs),
        assessments=len(data.assessments),
        scored=sum(1 for row in data.assessments if row.generated),
        rule_rows=sum(1 for row in data.assessments if not row.generated),
        strengths=sum(len(row.strengths) for row in data.assessments),
        risks=sum(len(row.risks) for row in data.assessments),
        masked_flags=len(data.mask),
    )


def project(data: FundamentalsFile) -> GraphBuilder:  # noqa: C901
    """Build the deterministic Turtle batch for one fundamentals delivery."""
    if not data.assets or not data.asset_infos:
        raise FundamentalsError(
            "the resolved assets are missing: load the delivery through the CLI or call "
            "resolve_mask_tickers first"
        )
    metrics_by_filing: defaultdict[int, list[MetricRow]] = defaultdict(list)
    for row in data.metrics:
        metrics_by_filing[row.filing_id].append(row)
    builder = GraphBuilder()
    for filing in sorted(data.filings, key=lambda row: row.filing_id):
        asset = KG[data.assets[filing.ticker]]
        filing_node = filing_iri(data.label, filing.filing_id)
        builder.add(filing_node, RDF.type, KG.SECFiling)
        builder.add(filing_node, KG.filingOfAsset, asset)
        builder.add(filing_node, KG.formType, rdflib.Literal(filing.form))
        builder.add(filing_node, KG.filingDate, _date_literal(filing.filing_date))
        builder.add(filing_node, KG.periodEnd, _date_literal(filing.period_end))
        builder.add(
            filing_node, KG.fiscalYear, rdflib.Literal(filing.fiscal_year, datatype=XSD.integer)
        )
        builder.add(filing_node, KG.fiscalPeriod, rdflib.Literal(filing.fiscal_period))
        builder.add(filing_node, KG.availableAt, _date_literal(filing.available_at))
        builder.add(filing_node, KG.accessionNumber, rdflib.Literal(filing.accession_number))
        builder.add(
            filing_node, KG.filingId, rdflib.Literal(filing.filing_id, datatype=XSD.integer)
        )
        rows = metrics_by_filing.get(filing.filing_id, [])
        if not rows:
            raise FundamentalsError(
                f"filings.csv filing_id {filing.filing_id} has no metrics.csv row; "
                "every filing gets one metric set"
            )
        latest = max(rows, key=lambda row: (row.computed_at, row.computed_at_text))
        set_node = metric_set_iri(data.label, filing.filing_id)
        builder.add(set_node, RDF.type, KG.FundamentalMetricSet)
        builder.add(set_node, KG.metricSetOfFiling, filing_node)
        builder.add(set_node, KG.availableAt, _date_literal(filing.available_at))
        builder.add(
            set_node, KG.computedAt, rdflib.Literal(latest.computed_at_text, datatype=XSD.dateTime)
        )
        builder.add(set_node, KG.engineVersion, rdflib.Literal(ENGINE_VERSION))
        for row in sorted(rows, key=lambda item: item.metric_id):
            if row.name == VALUE_INPUTS or row.value is None:
                continue
            builder.add(set_node, KG[METRIC_PROPERTIES[row.name]], _decimal_literal(row.value))
    for assessment in sorted(data.assessments, key=lambda row: row.snapshot_id):
        node = assessment_iri(data.label, assessment.snapshot_id)
        builder.add(node, RDF.type, KG.FundamentalAssessment)
        builder.add(
            node,
            KG.assessmentOfFiling,
            filing_iri(data.label, assessment.filing_id),
        )
        builder.add(node, KG.assessmentOfAsset, KG[data.assets[assessment.ticker]])
        builder.add(
            node, KG.snapshotId, rdflib.Literal(assessment.snapshot_id, datatype=XSD.integer)
        )
        if assessment.score is not None:
            builder.add(node, KG.scoreRaw0to100, _decimal_literal(assessment.score))
        if assessment.rating is not None:
            builder.add(node, KG.rating, rdflib.Literal(assessment.rating))
        builder.add(node, KG.narrative, rdflib.Literal(assessment.narrative))
        for strength in assessment.strengths:
            builder.add(node, KG.strength, rdflib.Literal(strength))
        for risk in assessment.risks:
            builder.add(node, KG.risk, rdflib.Literal(risk))
        builder.add(node, KG.model, rdflib.Literal(assessment.model))
        builder.add(
            node, KG.computedAt, rdflib.Literal(assessment.computed_at_text, datatype=XSD.dateTime)
        )
        builder.add(node, KG.eventTime, _date_literal(assessment.event_time))
        builder.add(node, KG.availableAt, _date_literal(assessment.available_at))
        builder.add(
            node,
            KG.generatedByLanguageModel,
            rdflib.Literal(assessment.generated, datatype=XSD.boolean),
        )
        builder.add(node, KG.provenanceNote, rdflib.Literal(assessment.provenance_note))
    for mask_row in sorted(data.mask, key=lambda item: item.ticker):
        builder.add(KG[data.assets[mask_row.ticker]], KG.pricesNotPublished, rdflib.Literal(True))
    return builder


def batch(data: FundamentalsFile) -> tuple[str, bytes]:
    """The graph name and its deterministic Turtle batch."""
    return graph_name(data.label), project(data).turtle()


def validation_graph(data: FundamentalsFile) -> rdflib.Graph:
    """The assets a dry run needs beside the batch; none of it is written."""
    return validation_context(data.asset_infos, types.SimpleNamespace(graph=rdflib.Graph()))


def verify_stored(store: ReadableStore, data: FundamentalsFile, builder: GraphBuilder) -> Check:
    """Check that the stored graph equals the file's batch."""
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
    try:
        return _check_label(text)
    except FundamentalsError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--label", default=FINAL_LABEL, type=_label_arg, help="the run label (default: final)"
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="the bloque_c_fundamentales folder with the six SHA256SUMS files",
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=DEFAULT_MASK,
        metavar="FILE",
        help="the Tiingo mask CSV (SHA-256 verified; default %(default)s)",
    )
    parser.add_argument(
        "--universe-db",
        type=Path,
        default=None,
        metavar="FILE",
        help="the universe database for the asset resolution (default: SQL_UNIVERSE_DB)",
    )
    parser.add_argument("--write", action="store_true", help="append the fundamentals graph")
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


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """Open the store only for the two store paths; guard the production write."""
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


def _validate(payload: bytes, context: rdflib.Graph | None) -> int:
    try:
        parsed = gate.parse_batch(payload)
        gate.validate(parsed, context=context)
    except gate.IngestRejected as exc:
        print(f"SHACL: FAIL\n{exc}")
        return 1
    print("SHACL: conforms (gate.validate)")
    return 0


def _peak_memory_mb() -> float | None:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB, macOS bytes.
    return usage / 1024 if sys.platform != "darwin" else usage / (1024 * 1024)


def _show_build(data: FundamentalsFile, builder: GraphBuilder, stats: FundamentalsStats) -> None:
    print(f"label: {data.label}")
    print(f"graph: {graph_name(data.label)}")
    print(
        f"filings: {stats.filings}; metric sets: {stats.metric_sets}; "
        f"assessments: {stats.assessments}"
    )
    print(
        f"metric rows: {stats.metric_rows} ({stats.metric_values} values, "
        f"{stats.null_values} null, {stats.value_inputs_rows} value_inputs discarded, "
        f"{stats.masked_value_inputs_rows} of them masked)"
    )
    print(
        f"assessments: {stats.scored} scored, {stats.rule_rows} rule rows; "
        f"{stats.strengths} strengths, {stats.risks} risks"
    )
    print(f"masked flags: {stats.masked_flags}")
    print(f"triples: {len(builder)}")


def _drop_line(graph: str) -> None:
    print(f"maintainer rollback (never run by the loader): DROP GRAPH <{graph}>")


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901, PLR0911, PLR0915
    args = parse_args(argv)
    started = time.perf_counter()
    directory = args.dir.resolve()
    try:
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        data = load_file(
            args.label,
            directory,
            mask_path=args.mask,
            universe_db=args.universe_db,
        )
        print(f"manifest: {MANIFEST_NAME} SHA-256 {data.manifest_sha256} matches the delivery")
        for name in REQUIRED_FILES:
            print(f"manifest: {name} is listed; SHA-256 {data.hashes[name]} matches")
        print(
            f"source: {data.source_db} SHA-256 {data.source_db_sha256}; "
            f"mask SHA-256 {data.mask_sha256} matches"
        )
        stats = statistics(data)
        builder = project(data)
        _show_build(data, builder, stats)
        payload = builder.turtle()
        print(f"timing: manifest+parse+project {time.perf_counter() - started:.3f} s")
        if not args.write and not args.check_store:
            mark = time.perf_counter()
            context = validation_graph(data)
            code = _validate(payload, context)
            print(f"timing: SHACL {time.perf_counter() - mark:.3f} s")
            peak = _peak_memory_mb()
            if peak is not None:
                print(f"peak memory: {peak:.1f} MB")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        store = open_store(args)
        assert store is not None
        graph = graph_name(data.label)
        mark = time.perf_counter()
        try:
            plan = gate.plan(store, payload, graph)
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        print(f"pre-flight: {plan.status.value}: {graph}")
        print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
        if args.check_store:
            if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
                check = verify_stored(store, data, builder)
                print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return 0
        if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
            print(f"already-in-the-store (skipped): {graph}")
            check = verify_stored(store, data, builder)
            print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return 0 if check.passed else 1
        mark = time.perf_counter()
        try:
            written = gate.write(store, plan)
        except gate.WriteInDoubt as exc:
            print(
                f"store error, the graph is in doubt: {exc}\n{graph} was sent but the store's "
                "answer was lost, so it may be written; do not retry blindly",
                file=sys.stderr,
            )
            _drop_line(graph)
            return 1
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        print(f"written: {graph}: {written} triples")
        print(f"timing: gate write {time.perf_counter() - mark:.3f} s")
        check = verify_stored(store, data, builder)
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
        if not check.passed:
            _drop_line(graph)
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if check.passed else 1  # noqa: TRY300 - success path of the write branch
    except (FundamentalsError, ManifestError, GraphDBError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
