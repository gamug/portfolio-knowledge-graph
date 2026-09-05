"""Local copy of ``portfolio-nlp``'s ``fetch_processed_articles`` export join,
built directly on ``portfolio_common.db.Database``.

``portfolio-common`` v1.0.0 extracted the ``news_nlp`` results-DB layer
(including the connection machinery and this query) out of the shared library
entirely, into a package now owned and vendored by ``portfolio-nlp`` itself
(``portfolio-nlp/src/news_nlp/``) rather than shipped as
``portfolio_common.news_nlp``. This repo isn't adding a direct git dependency
on ``portfolio-nlp`` yet -- it has no tagged release to pin to (see
``docs/portfolio-common-v1-migration-plan.md`` for the decision record) -- so
this module duplicates the one query this ETL actually needs, built on the
DB-engine-only pieces ``portfolio-common`` still ships
(:class:`portfolio_common.db.Database`, :class:`portfolio_common.db.Allowlist`).

Keep this in sync with ``portfolio-nlp``'s ``src/news_nlp/queries.py``'s
``fetch_processed_articles`` if that query's shape ever changes -- the column
list and eligibility filter (``fetch_status = 'ok'``, both a sentiment and a
category result present) must match exactly, since ``news_to_rdf.py``'s
``_Article.from_row`` assumes this row shape.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from portfolio_common.db import Allowlist, Database

# Only ever "main" (SOURCE and RESULTS resolve to the same file) or "source"
# (a read-only SOURCE DB is ATTACHed) -- the two branches of
# connect_pipeline() below are the only place either literal is produced.
_ARTICLES_SCHEMA = Allowlist("main", "source")


def connect_pipeline(
    source_db: str | os.PathLike[str], results_db: str | os.PathLike[str]
) -> tuple[Database, str]:
    """Open the RESULTS store read/write and, unless SOURCE resolves to the
    same path, ATTACH the SOURCE store read-only as schema ``source``.

    Returns ``(db, articles_rel)`` -- ``articles_rel`` is the schema
    :func:`fetch_processed_articles` should qualify ``articles`` with
    (``"source"`` when attached, else ``"main"``). Unlike ``portfolio-nlp``'s
    ``news_nlp.db.connect_pipeline`` (which tracks this as connection state,
    needed there for the write-side ``_ensure_article_row``), this ETL only
    reads, so there's nothing to track across calls -- the caller just
    threads the returned schema name through to
    :func:`fetch_processed_articles`.
    """
    results_path = Path(results_db)
    source_path = Path(source_db)
    db = Database.connect(f"file:{results_path.as_posix()}", uri=True)
    if source_path.resolve() == results_path.resolve():
        return db, "main"
    db.attach(source_path, "source", read_only=True)
    return db, "source"


def fetch_processed_articles(
    db: Database, articles_rel: str, limit: int | None = None
) -> list[sqlite3.Row]:
    """Every successfully-fetched article that has both a sentiment and a
    category result, as one flat row per article: ``id, ticker, pub_date,
    fetched_at, body_text, positive, negative, sent_processed_at, cat_label,
    cat_score, cat_processed_at``.

    Mirrors ``portfolio-nlp``'s ``news_nlp.queries.fetch_processed_articles``
    exactly (same join, same column list, same eligibility filter) -- see
    this module's docstring for why this repo carries its own copy instead of
    depending on that package directly.
    """
    schema = _ARTICLES_SCHEMA.check(articles_rel)
    # S608: `schema` is Allowlist-checked above; `limit` is bound as a
    # parameter, never interpolated.
    sql = f"""
        SELECT a.id AS id, a.ticker AS ticker, a.pub_date AS pub_date,
               a.fetched_at AS fetched_at, a.body_text AS body_text,
               s.positive AS positive, s.negative AS negative,
               s.processed_at AS sent_processed_at,
               c.label AS cat_label, c.score AS cat_score,
               c.processed_at AS cat_processed_at
        FROM {schema}.articles a
        JOIN article_sentiment s ON s.article_id = a.id
        JOIN article_category c ON c.article_id = a.id
        WHERE a.fetch_status = 'ok'
        ORDER BY a.id
    """  # noqa: S608
    params: list = []
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return db.execute(sql, params).fetchall()
