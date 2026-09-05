"""``urls.db``/``nlp.db`` -> ``:NewsArticle`` / ``:ScoreSnapshot`` / ``:RiskEvent`` Turtle.

Reads ``articles`` joined to ``article_sentiment`` and ``article_category`` for
rows with ``fetch_status = 'ok'`` via :mod:`portfolio_common.news_export` --
the read-only two-tier connect and join query shared with ``portfolio-nlp``
(which writes that schema; see its ``src/news_nlp/queries.py``'s own
``fetch_processed_articles``, a thin delegate to the same shared
implementation). This repo used to carry a local copy of that query
(``etl/queries.py``, retired) while ``portfolio-nlp`` had no tagged release
to depend on and ``portfolio-common`` shipped no shared alternative -- see
``docs/portfolio-common-v1-migration-plan.md`` for that decision record and
``portfolio-nlp/docs/portfolio-common-v1.1-news-export.md`` for how it was
resolved. Writes:

* ``:NewsArticle``   -- ``provenanceId``, ``publishedDate``
* ``:ScoreSnapshot`` -- ``agentOrigin = "SEMANTIC"``, ``metricType = "Sentiment"``, ``rawValue``
* ``:RiskEvent``     -- ``category``, ``severity``, ``detectedAt``, ``backedBy`` (gated)

Explicitly NOT read/written this phase:

* ``discovered_urls``   -- no confirmed join key back to ``articles``; an
  evidence-free stub is worse than no stub.
* ``article_entities``  -- ``:Executive`` per ``tbox.ttl`` is scoped to DEF14A
  officer/director extraction; the NER output only distinguishes ORG/PER/LOC.
* ``article_summary`` / ``sector_summary`` -- the "summary" feature is out of
  scope; no ontology class corresponds to either table.
* ``discovery_progress`` -- pipeline bookkeeping, not domain data.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, TextIO

from portfolio_common.news_export import connect_readonly, fetch_processed_articles

from etl.common.provenance import article_provenance_id
from etl.common.severity import (
    compute_severity,
    creation_gate,
    sentiment_raw_value,
    winning_category_and_score,
)
from etl.common.turtle_util import date_lit, datetime_lit, decimal_lit, str_lit

_ISO_DATE_LEN = 10
_MAX_UNRESOLVED_TICKERS_LOGGED = 20


class NewsDbPaths(NamedTuple):
    """The two-tier database pair :func:`stream_news` reads: SOURCE (has
    ``body_text``, e.g. ``urls.db``) and RESULTS (has ``article_sentiment``/
    ``article_category``, e.g. ``nlp.db``). See ``portfolio-common/docs/
    news-nlp-db-topology.md``."""

    source: str | Path
    results: str | Path


@dataclass(frozen=True, slots=True)
class _Article:
    """One joined ``articles`` + ``article_sentiment`` + ``article_category`` row."""

    id: int
    ticker: str | None
    pub_date: str | None
    fetched_at: str | None
    body_text: str | None
    positive: float
    negative: float
    sent_processed_at: str
    cat_label: str
    cat_score: float
    cat_processed_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> _Article:
        return cls(
            id=row["id"],
            ticker=row["ticker"],
            pub_date=row["pub_date"],
            fetched_at=row["fetched_at"],
            body_text=row["body_text"],
            positive=row["positive"],
            negative=row["negative"],
            sent_processed_at=row["sent_processed_at"],
            cat_label=row["cat_label"],
            cat_score=row["cat_score"],
            cat_processed_at=row["cat_processed_at"],
        )

    @property
    def news_iri(self) -> str:
        return f":News_{self.id}"

    def published_date(self) -> str | None:
        """G9: prefer ``pub_date``; fall back to the date part of ``fetched_at``."""
        source = self.pub_date or self.fetched_at
        if source and len(source) >= _ISO_DATE_LEN:
            return source[:_ISO_DATE_LEN]
        return None


@dataclass(slots=True)
class _Counts:
    """Running tallies for one :func:`stream_news` pass."""

    articles: int = 0
    score_snapshots: int = 0
    risk_events: int = 0
    unresolved_ticker_rows: int = 0
    missing_date_rows: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "articles": self.articles,
            "score_snapshots": self.score_snapshots,
            "risk_events": self.risk_events,
            "unresolved_ticker_rows": self.unresolved_ticker_rows,
            "missing_date_rows": self.missing_date_rows,
        }


def _write_news_article(out_fh: TextIO, art: _Article, pub_date: str) -> None:
    out_fh.write(f"{art.news_iri}\n    a :NewsArticle ;\n")
    out_fh.write(f"    :provenanceId {str_lit(article_provenance_id(art.id))} ;\n")
    out_fh.write(f"    :publishedDate {date_lit(pub_date)} .\n\n")


def _write_score_snapshot(
    out_fh: TextIO, art: _Article, raw_value: float, asset_iri: str | None
) -> None:
    out_fh.write(f":SentSnap_{art.id}\n    a :ScoreSnapshot ;\n")
    out_fh.write('    :agentOrigin "SEMANTIC" ;\n')
    out_fh.write('    :metricType "Sentiment" ;\n')
    out_fh.write(f"    :rawValue {decimal_lit(raw_value)} ;\n")
    out_fh.write(f"    :timestamp {datetime_lit(art.sent_processed_at)} ")
    if asset_iri:
        out_fh.write(f";\n    :scoreSnapshotOfAsset {asset_iri} .\n\n")
    else:
        out_fh.write(".\n\n")


def _write_risk_event(out_fh: TextIO, art: _Article, bucket: str, tier: str) -> None:
    out_fh.write(f":RiskEvt_{art.id}\n    a :RiskEvent ;\n")
    out_fh.write(f"    :category {str_lit(bucket)} ;\n")
    out_fh.write(f"    :severity {str_lit(tier)} ;\n")
    out_fh.write(f"    :detectedAt {datetime_lit(art.cat_processed_at)} ;\n")
    out_fh.write(f"    :backedBy {art.news_iri} .\n\n")


def _process_row(
    art: _Article, known_tickers: set[str], out_fh: TextIO, counts: _Counts
) -> str | None:
    """Emit the blocks for one article. Returns an unresolved ticker, if any."""
    pub_date = art.published_date()
    if not pub_date:
        counts.missing_date_rows += 1
        return None  # can't safely emit publishedDate; skip rather than fabricate one

    _write_news_article(out_fh, art, pub_date)
    counts.articles += 1

    unresolved: str | None = None
    asset_iri: str | None = None
    if art.ticker in known_tickers:
        asset_iri = f":{art.ticker}"
    elif art.ticker:
        counts.unresolved_ticker_rows += 1
        unresolved = art.ticker

    raw_value = sentiment_raw_value(art.positive, art.negative)
    _write_score_snapshot(out_fh, art, raw_value, asset_iri)
    counts.score_snapshots += 1

    bucket, top_score = winning_category_and_score(art.cat_label, art.cat_score)
    if bucket is not None and creation_gate(art.negative, top_score):
        tier = compute_severity(art.negative, top_score, bucket, art.body_text or "")
        _write_risk_event(out_fh, art, bucket, tier)
        counts.risk_events += 1

    return unresolved


def stream_news(
    db_paths: NewsDbPaths,
    known_tickers: set[str],
    out_fh: TextIO,
    warnings: list[str],
    limit: int | None = None,
) -> dict[str, int]:
    """Stream news rows from the SOURCE/RESULTS database pair and write Turtle
    blocks to ``out_fh``.

    ``limit``, when given, caps the number of source rows read (used for the
    validation-sample build in :mod:`etl.build_data_ttl`, not the real run).
    """
    out_fh.write("#################################################################\n")
    out_fh.write("# Section B: News evidence, sentiment snapshots, risk events\n")
    out_fh.write("# Source: urls.db/nlp.db articles / article_sentiment / article_category\n")
    out_fh.write("# (portfolio_common.news_export.fetch_processed_articles).\n")
    out_fh.write("# Excludes article_summary/sector_summary and discovered_urls/\n")
    out_fh.write("# article_entities/discovery_progress -- see module docstring.\n")
    out_fh.write("#################################################################\n\n")

    counts = _Counts()
    unresolved_tickers: set[str] = set()
    db, articles_rel = connect_readonly(db_paths.source, db_paths.results)
    try:
        for row in fetch_processed_articles(db, articles_rel, limit=limit):
            unresolved = _process_row(_Article.from_row(row), known_tickers, out_fh, counts)
            if unresolved is not None:
                unresolved_tickers.add(unresolved)
    finally:
        db.close()

    _record_warnings(warnings, counts, unresolved_tickers)
    return counts.as_dict()


def _record_warnings(warnings: list[str], counts: _Counts, unresolved_tickers: set[str]) -> None:
    if counts.unresolved_ticker_rows:
        sample = ", ".join(sorted(unresolved_tickers)[:_MAX_UNRESOLVED_TICKERS_LOGGED])
        warnings.append(
            f"news_to_rdf: {counts.unresolved_ticker_rows} article row(s) had a ticker not in the "
            f"current S&P 500 list ({len(unresolved_tickers)} distinct, e.g. {sample}) -- "
            f"NewsArticle/ScoreSnapshot were still written, but scoreSnapshotOfAsset was left unset. "
            f"Likely a historical ticker/constituent change since the article was published."
        )
    if counts.missing_date_rows:
        warnings.append(
            f"news_to_rdf: {counts.missing_date_rows} 'ok' article row(s) had neither pub_date nor "
            f"fetched_at usable as a date and were skipped entirely."
        )
