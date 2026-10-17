"""``etl.news_to_rdf.stream_news`` reads through ``portfolio_common.news_export
.connect_readonly``, which ATTACHes the SOURCE db (``urls.db``) read-only into
the RESULTS db (``nlp.db``) via ``Database.attach(read_only=True)`` --
``TwoTierDatabase.attach_readonly`` in ``portfolio_common.db.two_store``.

Unlike ``portfolio-financial-analysis``'s own ``urls.db`` read path (a bare
``Database.connect(read_only=True)`` open, never exposed to the bug), this
repo's read path genuinely goes through ``attach()`` -- the exact function
``portfolio-common`` v1.2.2 fixed. Before that fix, running this ETL step
while ``portfolio-data-mining``'s collector held ``urls.db`` open in WAL mode
raised for as long as the writer was running: the production bug tracked in
``portfolio-common``'s CHANGELOG v1.2.2 entry and ``portfolio-nlp``'s
``tests/news_nlp/test_db.py::test_attach_source_allows_a_live_writers_wal``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from io import StringIO
from pathlib import Path

from etl.news_to_rdf import NewsDbPaths, stream_news

_SOURCE_SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    company TEXT,
    pub_date TEXT,
    fetched_at TEXT,
    body_text TEXT,
    fetch_status TEXT
)
"""

_RESULTS_SCHEMA = """
CREATE TABLE article_sentiment (
    article_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    score REAL NOT NULL,
    positive REAL NOT NULL,
    negative REAL NOT NULL,
    neutral REAL NOT NULL,
    model_name TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
CREATE TABLE article_category (
    article_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    score REAL NOT NULL,
    processed_at TEXT NOT NULL
)
"""


def _seed_source_article(
    conn: sqlite3.Connection,
    id: int,
    ticker: str,
    pub_date: str = "2026-01-01T00:00:00Z",
) -> None:
    conn.execute(
        "INSERT INTO articles (id, ticker, company, pub_date, fetched_at, body_text, "
        "fetch_status) VALUES (?, ?, ?, ?, ?, ?, 'ok')",
        (
            id,
            ticker,
            f"Company {ticker}",
            pub_date,
            pub_date,
            f"Body text for article {id}.",
        ),
    )


def _seed_results_row(conn: sqlite3.Connection, id: int) -> None:
    # Low negative/score on purpose: keeps `creation_gate` closed so this test's
    # counts stay simple (no RiskEvent branch to also account for).
    conn.execute(
        "INSERT INTO article_sentiment (article_id, label, score, positive, negative, "
        "neutral, model_name, processed_at) VALUES (?, 'neutral', 0.5, 0.3, 0.1, 0.6, "
        "'test-model', '2026-01-02T00:00:00Z')",
        (id,),
    )
    conn.execute(
        "INSERT INTO article_category (article_id, label, score, processed_at) "
        "VALUES (?, 'other', 0.2, '2026-01-02T00:00:00Z')",
        (id,),
    )


def _build_source_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SOURCE_SCHEMA)
    _seed_source_article(conn, 1, "AAA")
    _seed_source_article(conn, 2, "BBB")
    conn.commit()
    conn.close()


def _build_results_db(path: Path, ids: Iterator[int]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_RESULTS_SCHEMA)
    for article_id in ids:
        _seed_results_row(conn, article_id)
    conn.commit()
    conn.close()


def test_stream_news_reads_through_a_live_writers_wal(tmp_path: Path) -> None:
    """A real writer (standing in for portfolio-data-mining's collector) keeps
    ``urls.db`` open in WAL mode with auto-checkpoint off, so the ``-wal``
    stays non-empty and the ``-shm`` stays present for the whole test -- the
    exact shape a concurrent collector run leaves behind. ``stream_news`` must
    not be blocked by this, and must see the writer's just-committed row
    rather than a stale snapshot (id 3, inserted into SOURCE below after the
    WAL was already non-empty; its RESULTS counterpart is pre-seeded before
    the writer ever opens the file, since only the SOURCE attach goes through
    the preflight this proves)."""
    source_path = tmp_path / "urls.db"
    results_path = tmp_path / "nlp.db"
    _build_source_db(source_path)
    _build_results_db(results_path, ids=iter((1, 2, 3)))

    holder = sqlite3.connect(source_path)
    assert holder.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    holder.execute("PRAGMA wal_autocheckpoint=0")
    _seed_source_article(holder, 3, "CCC")
    holder.commit()
    try:
        assert Path(f"{source_path}-wal").stat().st_size > 0
        assert Path(f"{source_path}-shm").exists()

        out_fh = StringIO()
        warnings: list[str] = []
        counts = stream_news(
            NewsDbPaths(source=source_path, results=results_path),
            known_tickers={"AAA", "BBB", "CCC"},
            out_fh=out_fh,
            warnings=warnings,
        )

        assert counts == {
            "articles": 3,
            "score_snapshots": 3,
            "risk_events": 0,
            "unresolved_ticker_rows": 0,
            "missing_date_rows": 0,
        }
        assert warnings == []
        assert ":News_3" in out_fh.getvalue()
    finally:
        holder.close()
