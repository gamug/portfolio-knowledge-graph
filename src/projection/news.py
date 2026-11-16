"""Load the block D news rows into one append-only graph per calendar year (Work item 46).

The delivery's ``news/news_rows.jsonl`` is one JSON object per line, UTF-8, in the order of the
manifest's ``news_rows_file.columns``. The loader verifies the file against both the manifest hash
and the delivery's ``SHA256SUMS`` before reading a row, checks the key and every typed value, and
projects one ``:NewsItem`` per ``(item_kind, item_id, ticker)``. The IRI is built from that triple
only, never from a run id, so a later ``model_revision`` cannot mint a second individual for the
same news fragment.

Graphs are split by calendar year (``urn:graph:derived:news:{label}:{year}``). A year that would
exceed the ~400,000-triple bound is split into its two month spans
(``...:{year}:01-06``/``07-12``). Writes go through
:func:`kg_store.gate.write_batched`; a lost answer is a graph in doubt and is never retried
blindly. A future revision that re-labels an already loaded fragment writes one value per graph,
so a query must read the revision by graph.

Sentiment and category are NLP-model outputs: the row's three revision fields are stored as
provenance and the labels/comments never present them as verified facts. The text is the exact
fragment the model labelled (at most 2,000 characters), never the full article.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

import rdflib
from rdflib.namespace import RDF, XSD

from etl import config as etl_config
from kg_store import gate
from kg_store.graphdb import (
    PRODUCTION_REPOSITORY,
    GraphDB,
    GraphDBError,
    announce_target,
)
from projection.asset_link import resolve_asset
from projection.backtest import RUN_LABEL_PATTERN, AssetInfo, GraphBuilder, universe_assets
from projection.series import read_manifest as read_sha256sums
from projection.series import sha256_file
from projection.veto_manifest import NewsRowsContract, VetoManifest, read_manifest

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

GRAPH_PREFIX = "urn:graph:derived:news:"
MANIFEST_NAME = "manifest_final.json"
SUMS_NAME = "SHA256SUMS"
BATCH_SIZE = 20_000
#: A graph above this bound is split further; the loader refuses to write a larger one.
MAX_GRAPH_TRIPLES = 400_000
#: The most triples one row can add: rdf:type + 23 column properties + the Asset link + url.
MAX_TRIPLES_PER_ROW = 26
#: The delivery promises a fragment, never the full article.
MAX_TEXT_LENGTH = 2_000
#: June is the last month of the first month span used when a year must be split.
MID_YEAR_MONTH = 6
#: The month-span suffixes of a split year; the test-window names H1/H2/H3 are not reused.
FIRST_HALF = "01-06"
SECOND_HALF = "07-12"
#: The strict block D column order the delivery's header must repeat.
NEWS_COLUMNS: tuple[str, ...] = (
    "model_revision",
    "item_kind",
    "item_id",
    "ticker",
    "asset_id",
    "date",
    "date_source",
    "title",
    "text",
    "text_source",
    "sentiment",
    "sentiment_score",
    "p_positive",
    "p_negative",
    "p_neutral",
    "sentiment_revision",
    "category",
    "category_score",
    "group_label",
    "category_revision",
    "article_id",
    "body_hash",
    "source_domain",
    "url",
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LABEL = re.compile(RUN_LABEL_PATTERN)
_LOCAL_NAME = re.compile(r"[A-Za-z0-9_.-]+")
_YEAR = re.compile(r"([12][0-9]{3})")


class NewsError(ValueError):
    """The news delivery, its manifest or a verification check cannot be accepted."""


class ManifestError(NewsError):
    """``more specific than NewsError``: the manifest or SHA256SUMS does not match."""


@dataclass(frozen=True)
class NewsRow:
    """One accepted ``news_rows.jsonl`` row, plus the Asset it resolves to (if any)."""

    line: int
    model_revision: str
    item_kind: str
    item_id: str
    ticker: str
    asset_id: int | None
    date: datetime.date
    date_source: str
    title: str
    text: str
    text_source: str
    sentiment: str
    sentiment_score: Decimal
    p_positive: Decimal
    p_negative: Decimal
    p_neutral: Decimal
    sentiment_revision: str
    category: str
    category_score: Decimal
    group_label: str
    category_revision: str
    article_id: int
    body_hash: str
    source_domain: str
    url: str | None
    asset: str | None = None


@dataclass(frozen=True)
class NewsFile:
    """The verified and parsed file, plus the manifest that accepted it."""

    label: str
    root: Path
    contract: NewsRowsContract
    rows: tuple[NewsRow, ...]
    sha256: str
    sums_sha256: str


@dataclass(frozen=True)
class Check:
    """One PASS/FAIL line in the loader output."""

    name: str
    passed: bool
    detail: str


class ReadableStore(Protocol):
    """What the stored-graph check needs of a store: SPARQL ``SELECT`` only."""

    def select(self, sparql: str) -> list[dict[str, str]]: ...


# --- manifest and hashes ------------------------------------------------------------------------


def _manifest_path(directory: str | Path) -> Path:
    """The delivery's manifest: ``--dir`` may be the root or the ``news/`` folder below it."""
    directory = Path(directory).resolve()
    if (directory / MANIFEST_NAME).is_file():
        return directory / MANIFEST_NAME
    parent = directory.parent / MANIFEST_NAME
    if parent.is_file():
        return parent
    raise ManifestError(f"{directory}: no {MANIFEST_NAME} here or in its parent directory")


def read_news_manifest(directory: str | Path) -> VetoManifest:
    """Read the final manifest and return it with its ``news_rows_file`` contract.

    The manifest parser is B's (``veto_manifest.read_manifest``); this helper only enforces the
    block D column order and fails clearly when the block is absent.
    """
    path = _manifest_path(directory)
    manifest = read_manifest(path)
    contract = manifest.news_rows
    if contract is None:
        raise ManifestError(f"{path}: the manifest has no news_rows_file block")
    if contract.columns != NEWS_COLUMNS:
        raise ManifestError(
            f"{path}: news_rows_file.columns does not match the block D contract; "
            f"got {contract.columns!r}"
        )
    return manifest


def verify_hashes(manifest: VetoManifest, contract: NewsRowsContract) -> tuple[str, str]:
    """The file's SHA-256 must match the manifest *and* the delivery's own ``SHA256SUMS``."""
    path = contract.path
    if not path.is_file():
        raise ManifestError(f"{path}: the manifest lists a file that does not exist")
    actual = sha256_file(path)
    if actual != contract.sha256:
        raise ManifestError(
            f"{path}: SHA-256 mismatch: manifest says {contract.sha256}, file has {actual}"
        )
    sums_path = manifest.root / SUMS_NAME
    if not sums_path.is_file():
        raise ManifestError(f"{sums_path}: the delivery has no {SUMS_NAME}")
    entries = read_sha256sums(sums_path)
    key = path.relative_to(manifest.root).as_posix()
    if key not in entries:
        raise ManifestError(f"{sums_path}: {key!r} is not listed")
    if entries[key] != contract.sha256:
        raise ManifestError(
            f"{sums_path}: {key!r} has {entries[key]}, the manifest says {contract.sha256}"
        )
    return actual, entries[key]


# --- parsing ------------------------------------------------------------------------------------


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise NewsError(f"{where}: expected a non-empty string")
    return value


def _date(value: object, where: str) -> datetime.date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise NewsError(f"{where}: {value!r} is not a strict YYYY-MM-DD date")
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise NewsError(f"{where}: {value!r} is not a calendar date ({exc})") from exc
    if day.isoformat() != value:
        raise NewsError(f"{where}: {value!r} is not the ISO form of {day.isoformat()}")
    return day


def _decimal(value: object, where: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise NewsError(f"{where}: expected a decimal, got {value!r}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise NewsError(f"{where}: {value!r} is not a decimal") from exc
    if not number.is_finite():
        raise NewsError(f"{where}: {value!r} is not a finite decimal")
    return number


def _probability(value: object, where: str) -> Decimal:
    number = _decimal(value, where)
    if not (0 <= number <= 1):
        raise NewsError(f"{where}: probability {number} is outside [0, 1]")
    return number


def _integer(value: object, where: str, *, positive: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NewsError(f"{where}: expected an integer, got {value!r}")
    if positive and value < 1:
        raise NewsError(f"{where}: {value} is not a positive integer")
    return value


def _local(value: str, where: str) -> str:
    if not _LOCAL_NAME.fullmatch(value):
        raise NewsError(f"{where}: {value!r} is not safe in a NewsItem IRI")
    return value


def _row(raw: object, line: int, contract: NewsRowsContract) -> NewsRow:
    where = f"{contract.path}:{line}"
    if not isinstance(raw, dict):
        raise NewsError(f"{where}: expected one JSON object")
    if tuple(raw.keys()) != contract.columns:
        raise NewsError(
            f"{where}: header drift: expected {contract.columns!r}, got {tuple(raw.keys())!r}"
        )
    model_revision = _text(raw["model_revision"], f"{where}.model_revision")
    item_kind = _text(raw["item_kind"], f"{where}.item_kind")
    if item_kind not in ("body", "sub_news"):
        raise NewsError(f"{where}.item_kind: {item_kind!r} is not body or sub_news")
    item_id = _local(_text(raw["item_id"], f"{where}.item_id"), f"{where}.item_id")
    ticker = _local(_text(raw["ticker"], f"{where}.ticker"), f"{where}.ticker")
    asset_id_value = raw["asset_id"]
    asset_id = (
        None
        if asset_id_value is None
        else _integer(asset_id_value, f"{where}.asset_id", positive=True)
    )
    day = _date(raw["date"], f"{where}.date")
    date_source = _text(raw["date_source"], f"{where}.date_source")
    if date_source not in ("published", "crawled", "crawled_future_pub"):
        raise NewsError(f"{where}.date_source: {date_source!r} is not a known date source")
    title = _text(raw["title"], f"{where}.title")
    text = _text(raw["text"], f"{where}.text")
    if len(text) > MAX_TEXT_LENGTH:
        raise NewsError(
            f"{where}.text: {len(text)} characters; the delivery contract is a fragment of at "
            "most 2,000 characters, never the full article"
        )
    text_source = _text(raw["text_source"], f"{where}.text_source")
    if text_source not in ("original", "summary"):
        raise NewsError(f"{where}.text_source: {text_source!r} is not original or summary")
    sentiment = _text(raw["sentiment"], f"{where}.sentiment")
    if sentiment not in ("positive", "negative", "neutral"):
        raise NewsError(f"{where}.sentiment: {sentiment!r} is not a known sentiment label")
    sentiment_score = _probability(raw["sentiment_score"], f"{where}.sentiment_score")
    p_positive = _probability(raw["p_positive"], f"{where}.p_positive")
    p_negative = _probability(raw["p_negative"], f"{where}.p_negative")
    p_neutral = _probability(raw["p_neutral"], f"{where}.p_neutral")
    sentiment_revision = _text(raw["sentiment_revision"], f"{where}.sentiment_revision")
    category = _text(raw["category"], f"{where}.category")
    category_score = _probability(raw["category_score"], f"{where}.category_score")
    group_label = _text(raw["group_label"], f"{where}.group_label")
    category_revision = _text(raw["category_revision"], f"{where}.category_revision")
    article_id = _integer(raw["article_id"], f"{where}.article_id", positive=True)
    body_hash = _text(raw["body_hash"], f"{where}.body_hash")
    source_domain = _text(raw["source_domain"], f"{where}.source_domain")
    url_value = raw["url"]
    url = None if url_value is None else _text(url_value, f"{where}.url")
    return NewsRow(
        line=line,
        model_revision=model_revision,
        item_kind=item_kind,
        item_id=item_id,
        ticker=ticker,
        asset_id=asset_id,
        date=day,
        date_source=date_source,
        title=title,
        text=text,
        text_source=text_source,
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        p_positive=p_positive,
        p_negative=p_negative,
        p_neutral=p_neutral,
        sentiment_revision=sentiment_revision,
        category=category,
        category_score=category_score,
        group_label=group_label,
        category_revision=category_revision,
        article_id=article_id,
        body_hash=body_hash,
        source_domain=source_domain,
        url=url,
    )


def parse_rows(contract: NewsRowsContract) -> tuple[NewsRow, ...]:
    """Parse every row; the key is unique, and no IRI may appear under two revisions."""
    rows: list[NewsRow] = []
    keys: set[tuple[str, str, str, str]] = set()
    revision_by_iri: dict[tuple[str, str, str], str] = {}
    try:
        with contract.path.open("r", encoding="utf-8") as handle:
            for line, text in enumerate(handle, 1):
                if not text.strip():
                    raise NewsError(f"{contract.path}:{line}: empty line")
                try:
                    raw = json.loads(text, parse_float=Decimal)
                except json.JSONDecodeError as exc:
                    raise NewsError(f"{contract.path}:{line}: invalid JSON: {exc}") from exc
                row = _row(raw, line, contract)
                key = (row.model_revision, row.item_kind, row.item_id, row.ticker)
                if key in keys:
                    raise NewsError(f"{contract.path}:{line}: duplicate key {key!r}")
                keys.add(key)
                iri_key = (row.item_kind, row.item_id, row.ticker)
                prior = revision_by_iri.setdefault(iri_key, row.model_revision)
                if prior != row.model_revision:
                    raise NewsError(
                        f"{contract.path}:{line}: {iri_key!r} appears under two revisions "
                        f"({prior!r} and {row.model_revision!r}); the NewsItem IRI would collide"
                    )
                if row.model_revision != contract.model_revision:
                    raise NewsError(
                        f"{contract.path}:{line}: model_revision {row.model_revision!r} differs "
                        f"from the manifest's {contract.model_revision!r}"
                    )
                rows.append(row)
    except OSError as exc:
        raise NewsError(f"{contract.path}: {exc}") from exc
    if len(rows) != contract.rows:
        raise NewsError(f"{contract.path}: {len(rows)} row(s), the manifest says {contract.rows}")
    return tuple(rows)


def load_file(label: str, directory: str | Path) -> NewsFile:
    """Verify the manifest and SHA256SUMS, then parse the file; no store is contacted."""
    if not _LABEL.fullmatch(label):
        raise NewsError(f"run label {label!r} does not match {RUN_LABEL_PATTERN} (as in final)")
    manifest = read_news_manifest(directory)
    contract = manifest.news_rows
    assert contract is not None  # read_news_manifest refuses an absent block
    actual, sums = verify_hashes(manifest, contract)
    rows = parse_rows(contract)
    return NewsFile(label, manifest.root, contract, rows, actual, sums)


# --- asset resolution ---------------------------------------------------------------------------


def link_assets(rows: Sequence[NewsRow], assets: Mapping[str, AssetInfo]) -> tuple[NewsRow, ...]:
    """Link every row whose ticker resolves, with the engine asset id as the rename fallback.

    The exact ticker is the normal rule. A ticker that no longer names the catalog's current
    symbol falls back to the Asset that another row of the same engine ``asset_id`` resolves to,
    and only when that set has exactly one member. Letter 26 gives the 261 PSKY rows engine
    ``asset_id`` 477, so they link to ``:SKYD`` through this fallback. A null ``asset_id`` has no
    fallback: the row is loaded without a link and counted (the 9 EQR rows).
    """
    tickers_by_id: defaultdict[int, set[str]] = defaultdict(set)
    for row in rows:
        if row.asset_id is not None:
            tickers_by_id[row.asset_id].add(row.ticker)

    def exact(ticker: str) -> str | None:
        return resolve_asset(ticker, None, assets).iri

    linked: list[NewsRow] = []
    for row in rows:
        asset = exact(row.ticker)
        if asset is None and row.asset_id is not None:
            candidates = {
                resolved
                for ticker in tickers_by_id[row.asset_id]
                if (resolved := exact(ticker)) is not None
            }
            if len(candidates) == 1:
                asset = candidates.pop()
        linked.append(replace(row, asset=asset))
    return tuple(linked)


def unresolved_summary(rows: Sequence[NewsRow]) -> tuple[int, int, Counter[str]]:
    """The unresolved rows, how many of them had a null ``asset_id``, and their tickers."""
    unresolved = [row for row in rows if row.asset is None]
    null_ids = sum(1 for row in unresolved if row.asset_id is None)
    return len(unresolved), null_ids, Counter(row.ticker for row in unresolved)


def asset_context(rows: Sequence[NewsRow], assets: Mapping[str, AssetInfo]) -> rdflib.Graph:
    """Validation-only types for the linked Assets a dry run cannot fetch from a store."""
    context = rdflib.Graph()
    context.add((KG.SP500Index, RDF.type, KG.Universe))
    for symbol in sorted({row.asset for row in rows if row.asset is not None}):
        info = assets[symbol]
        asset = KG[symbol]
        for kind in info.types:
            context.add((asset, RDF.type, KG[kind]))
        context.add((asset, KG.tickerSymbol, rdflib.Literal(symbol)))
        if info.cik is not None:
            context.add((asset, KG.cikNumber, rdflib.Literal(info.cik)))
        for index, (valid_from, valid_to) in enumerate(info.stints):
            membership = KG[f"Membership_{symbol}_{index}"]
            context.add((membership, RDF.type, KG.UniverseMembership))
            context.add((membership, KG.membershipAsset, asset))
            context.add((membership, KG.membershipUniverse, KG.SP500Index))
            context.add((membership, KG.validFrom, rdflib.Literal(valid_from, datatype=XSD.date)))
            if valid_to is not None:
                context.add((membership, KG.validTo, rdflib.Literal(valid_to, datatype=XSD.date)))
            context.add((asset, KG.hasUniverseMembership, membership))
    return context


# --- projection ---------------------------------------------------------------------------------


def news_item_iri(row: NewsRow) -> rdflib.URIRef:
    """The permanent IRI: ``(item_kind, item_id, ticker)`` only, never a run or model revision."""
    return KG[f"NewsItem_{row.item_kind}_{row.item_id}_{row.ticker}"]


def graph_name(label: str, year: int | str, half: str | None = None) -> str:
    """One year graph, or one half of a split year."""
    if not _LABEL.fullmatch(label):
        raise NewsError(f"run label {label!r} does not match {RUN_LABEL_PATTERN}")
    text = str(year)
    if not _YEAR.fullmatch(text):
        raise NewsError(f"news graph year {text!r} is not a four-digit year")
    if half is not None and half not in (FIRST_HALF, SECOND_HALF):
        raise NewsError(f"news graph half {half!r} is not {FIRST_HALF} or {SECOND_HALF}")
    return f"{GRAPH_PREFIX}{label}:{text}" + (f":{half}" if half else "")


def rows_by_graph(label: str, rows: Sequence[NewsRow]) -> dict[str, tuple[NewsRow, ...]]:
    """Split by calendar year; a year over the bound is split into its two halves."""
    by_year: defaultdict[int, list[NewsRow]] = defaultdict(list)
    for row in rows:
        by_year[row.date.year].append(row)
    out: dict[str, tuple[NewsRow, ...]] = {}
    for year in sorted(by_year):
        year_rows = by_year[year]
        if len(year_rows) * MAX_TRIPLES_PER_ROW <= MAX_GRAPH_TRIPLES:
            out[graph_name(label, year)] = tuple(year_rows)
            continue
        first = tuple(row for row in year_rows if row.date.month <= MID_YEAR_MONTH)
        second = tuple(row for row in year_rows if row.date.month > MID_YEAR_MONTH)
        if not first or not second:
            raise NewsError(
                f"{year}: {len(year_rows)} rows exceed the {MAX_GRAPH_TRIPLES}-triple bound but "
                "the year has only one half"
            )
        out[graph_name(label, year, FIRST_HALF)] = first
        out[graph_name(label, year, SECOND_HALF)] = second
    return out


def _date_literal(value: datetime.date) -> rdflib.Literal:
    return rdflib.Literal(value.isoformat(), datatype=XSD.date)


def _decimal_literal(value: Decimal) -> rdflib.Literal:
    return rdflib.Literal(format(value, "f"), datatype=XSD.decimal)


def _int_literal(value: int) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.integer)


def _add_row(builder: GraphBuilder, row: NewsRow) -> None:
    item = news_item_iri(row)
    builder.add(item, RDF.type, KG.NewsItem)
    builder.add(item, KG.modelRevision, rdflib.Literal(row.model_revision))
    builder.add(item, KG.itemKind, rdflib.Literal(row.item_kind))
    builder.add(item, KG.itemId, rdflib.Literal(row.item_id))
    builder.add(item, KG.newsTicker, rdflib.Literal(row.ticker))
    if row.asset_id is not None:
        builder.add(item, KG.newsAssetId, _int_literal(row.asset_id))
    builder.add(item, KG.newsDate, _date_literal(row.date))
    builder.add(item, KG.dateSource, rdflib.Literal(row.date_source))
    builder.add(item, KG.newsTitle, rdflib.Literal(row.title))
    builder.add(item, KG.newsText, rdflib.Literal(row.text))
    builder.add(item, KG.textSource, rdflib.Literal(row.text_source))
    builder.add(item, KG.newsSentiment, rdflib.Literal(row.sentiment))
    builder.add(item, KG.sentimentScore, _decimal_literal(row.sentiment_score))
    builder.add(item, KG.pPositive, _decimal_literal(row.p_positive))
    builder.add(item, KG.pNegative, _decimal_literal(row.p_negative))
    builder.add(item, KG.pNeutral, _decimal_literal(row.p_neutral))
    builder.add(item, KG.sentimentRevision, rdflib.Literal(row.sentiment_revision))
    builder.add(item, KG.newsCategory, rdflib.Literal(row.category))
    builder.add(item, KG.categoryScore, _decimal_literal(row.category_score))
    builder.add(item, KG.groupLabel, rdflib.Literal(row.group_label))
    builder.add(item, KG.categoryRevision, rdflib.Literal(row.category_revision))
    builder.add(item, KG.articleId, _int_literal(row.article_id))
    builder.add(item, KG.bodyHash, rdflib.Literal(row.body_hash))
    builder.add(item, KG.sourceDomain, rdflib.Literal(row.source_domain))
    if row.url is not None:
        builder.add(item, KG.url, rdflib.Literal(row.url, datatype=XSD.anyURI))
    if row.asset is not None:
        builder.add(item, KG.newsItemOfAsset, KG[row.asset])


def project(data: NewsFile) -> dict[str, GraphBuilder]:
    """Build one bounded graph builder per year (or half-year); refuse an over-size graph."""
    builders: dict[str, GraphBuilder] = {}
    for graph, rows in rows_by_graph(data.label, data.rows).items():
        builder = GraphBuilder()
        for row in rows:
            _add_row(builder, row)
        if len(builder) > MAX_GRAPH_TRIPLES:
            raise NewsError(
                f"{graph}: {len(builder)} triples exceed the {MAX_GRAPH_TRIPLES}-triple bound; "
                "split it further before writing"
            )
        builders[graph] = builder
    return builders


# --- store checks -------------------------------------------------------------------------------

_PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"


def _graph_exists(store: ReadableStore, graph: str) -> bool:
    return bool(store.select(f"SELECT * WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} LIMIT 1"))


def _stored_items(store: ReadableStore, graph: str) -> int:
    rows = store.select(
        _PREFIX + f"SELECT (COUNT(DISTINCT ?item) AS ?n) WHERE {{ GRAPH <{graph}> "
        "{ ?item a :NewsItem } }"
    )
    try:
        return int(rows[0]["n"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise NewsError(f"{graph}: unreadable stored NewsItem count") from exc


def _stored_tickers(store: ReadableStore, graph: str) -> set[str]:
    rows = store.select(
        _PREFIX + f"SELECT DISTINCT ?ticker WHERE {{ GRAPH <{graph}> "
        "{ ?item a :NewsItem ; :newsTicker ?ticker } }"
    )
    return {str(row["ticker"]) for row in rows}


def verify_stored(
    store: ReadableStore,
    label: str,
    rows: Sequence[NewsRow],
    builders: Mapping[str, GraphBuilder],
) -> list[Check]:
    """Compare every graph's stored ``:NewsItem`` count with the projected rows."""
    checks: list[Check] = []
    expected = rows_by_graph(label, rows)
    for graph in sorted(builders):
        want = len(expected[graph])
        if not _graph_exists(store, graph):
            checks.append(Check(f"stored {graph}", False, "the graph is absent"))
            continue
        got = _stored_items(store, graph)
        checks.append(
            Check(
                f"stored {graph}",
                got == want,
                f"{got} NewsItem(s), expected {want}",
            )
        )
    return checks


def verify_manifest_store(store: ReadableStore, manifest: VetoManifest, label: str) -> None:
    """Store-side check used by ``verify_store --manifest``; absent graphs are not failures."""
    contract = manifest.news_rows
    if contract is None:
        raise ManifestError("the manifest has no news_rows_file block")
    if contract.columns != NEWS_COLUMNS:
        raise ManifestError("news_rows_file.columns does not match the block D contract")
    verify_hashes(manifest, contract)
    rows = parse_rows(contract)
    groups = rows_by_graph(label, rows)
    missing = [graph for graph in groups if not _graph_exists(store, graph)]
    if missing:
        print(
            "news: not store-verifiable: "
            + ", ".join(missing)
            + (" graph(s) absent" if len(missing) > 1 else " graph absent")
        )
        return
    total = 0
    tickers: set[str] = set()
    for graph, group in groups.items():
        stored = _stored_items(store, graph)
        if stored != len(group):
            raise NewsError(f"{graph}: stored {stored} NewsItem(s), expected {len(group)}")
        total += stored
        tickers.update(_stored_tickers(store, graph))
        print(f"PASS  news rows {graph}: {stored}")
    if total != contract.rows:
        raise NewsError(f"news: stored rows sum to {total}, the manifest says {contract.rows}")
    expected_tickers = {row.ticker for row in rows}
    if tickers != expected_tickers:
        missing_tickers = sorted(expected_tickers - tickers)
        extra = sorted(tickers - expected_tickers)
        raise NewsError(
            f"news: stored tickers differ (missing {missing_tickers[:10]}, extra {extra[:10]})"
        )
    print(f"PASS  news: {total} rows, {len(tickers)} distinct tickers")


# --- CLI ----------------------------------------------------------------------------------------


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
        help="the delivery root with manifest_final.json and SHA256SUMS (or its news/ folder)",
    )
    parser.add_argument(
        "--universe-db",
        type=Path,
        help="the universe catalog for the ticker -> Asset resolution (default: SQL_UNIVERSE_DB)",
    )
    parser.add_argument("--write", action="store_true", help="append the news graphs")
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


def _show_build(data: NewsFile, builders: Mapping[str, GraphBuilder]) -> None:
    print(f"label: {data.label}")
    print(f"manifest: {data.root / MANIFEST_NAME}")
    print(f"file: {data.contract.path}")
    print(f"rows: {len(data.rows)}")
    unresolved, null_ids, tickers = unresolved_summary(data.rows)
    print(f"unresolved assets: {unresolved} row(s); asset_id null: {null_ids}")
    if tickers:
        preview = ", ".join(f"{ticker}={count}" for ticker, count in tickers.most_common(10))
        print(f"unresolved tickers: {preview}")
    for graph in sorted(builders):
        print(f"graph: {graph}")
        print(f"triples: {graph}: {len(builders[graph])}")


def _validate(
    builders: Mapping[str, GraphBuilder], rows: Sequence[NewsRow], assets: Mapping[str, AssetInfo]
) -> int:
    context = asset_context(rows, assets)
    for graph in sorted(builders):
        try:
            parsed = gate.parse_batch(builders[graph].turtle())
            gate.validate(parsed, context=context)
        except gate.IngestRejected as exc:
            print(f"SHACL: FAIL {graph}\n{exc}")
            return 1
        print(f"SHACL: conforms ({graph}, gate.validate)")
    return 0


def _plan(store: GraphDB, builders: Mapping[str, GraphBuilder]) -> dict[str, gate.IngestPlan]:
    return {graph: gate.plan(store, builders[graph].turtle(), graph) for graph in sorted(builders)}


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


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901, PLR0915 -- one return per mode
    args = parse_args(argv)
    started = time.perf_counter()
    try:
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        data = load_file(args.label, args.dir)
        print(f"manifest: using {_manifest_path(args.dir)}")
        print(f"manifest: {data.contract.path.name} is listed; SHA-256 {data.sha256} matches")
        print(f"manifest: {data.contract.rows} row(s) declared")
        universe_db = args.universe_db or etl_config.universe_db_path()
        assets = universe_assets(universe_db)
        data = replace(data, rows=link_assets(data.rows, assets))
        builders = project(data)
        _show_build(data, builders)
        print(f"timing: manifest+parse+resolve {time.perf_counter() - started:.3f} s")
        if not args.write and not args.check_store:
            mark = time.perf_counter()
            code = _validate(builders, data.rows, assets)
            print(f"timing: SHACL {time.perf_counter() - mark:.3f} s")
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        store = open_store(args)
        assert store is not None
        mark = time.perf_counter()
        try:
            plans = _plan(store, builders)
        except gate.IngestRejected as exc:
            print(f"STOPPED\n{exc}", file=sys.stderr)
            return 1
        for graph in sorted(plans):
            print(f"pre-flight: {graph}: {plans[graph].status.value}")
        print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
        if args.check_store:
            existing = [
                graph
                for graph, plan in plans.items()
                if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE
            ]
            code = 0
            if existing:
                checks = verify_stored(
                    store, data.label, data.rows, {g: builders[g] for g in existing}
                )
                code = 0 if _show_checks(checks) else 1
            print(f"timing: total {time.perf_counter() - started:.3f} s")
            return code
        mark = time.perf_counter()
        written = 0
        for graph in sorted(plans):
            plan = plans[graph]
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
        checks = verify_stored(store, data.label, data.rows, builders)
        ok = _show_checks(checks)
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if ok else 1  # noqa: TRY300 -- the success return pairs with the failure handlers
    except (NewsError, GraphDBError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _show_checks(checks: Sequence[Check]) -> bool:
    ok = True
    for check in checks:
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
        ok = ok and check.passed
    return ok


if __name__ == "__main__":
    sys.exit(main())
