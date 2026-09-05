# Coordination note: `portfolio-common` v1.2.0 — engine-agnostic seam

## Context

`portfolio-common` v1.2.0 makes the database engine a single-repo concern:
it adds a `Dialect` seam, `Database.connect_url`, schema-introspection
helpers, `portfolio_common.db.two_store`, and a neutral `Row` type (an alias
for `sqlite3.Row` today, `RowLike` being the access contract a future engine
must meet). See `portfolio-nlp`'s `docs/engine-agnostic-rollout.md` for the
full cross-repo plan.

## What changed here

This repo was already almost uncoupled — it holds no SQL of its own; the
`articles ⋈ article_sentiment ⋈ article_category` join and the read-only
two-tier connect both live in `portfolio_common.news_export`. The only
engine reference was in `src/etl/news_to_rdf.py`:

- dropped `import sqlite3`;
- `_Article.from_row(cls, row: sqlite3.Row)` → `row: Row`
  (`from portfolio_common.db import Row`). Row access is `row["name"]`
  mapping-style throughout — already within the `RowLike` contract.
- `pyproject.toml`: `[tool.uv.sources]` `portfolio-common` re-pinned from the
  interim `feat/news-export-shared-read-contract` branch commit straight to
  `tag = "v1.2.0"` (this repo had never moved off that interim `rev`).

`src/etl/config.py`'s `KG_URLS_DB` / `KG_RESULTS_DB` stay filesystem paths —
they feed `portfolio_common.db.Database.connect_url` (via
`news_export.connect_readonly`), which accepts a path or a `scheme://` URL,
so no change is needed here for a future engine.

## Verification

- `uv sync` against `v1.2.0`
- `uv run ruff check --config .code_quality/ruff.toml .` — clean
- `uv run mypy --config-file=.code_quality/mypy.ini` — clean
- `import etl.news_to_rdf` smoke — clean

## Companion PRs

- `portfolio-common#9` — the seam (merged, tagged `v1.2.0`).
- `portfolio-nlp#24` — adopts the seam in `src/news_nlp/` (merged).
- `portfolio-financial-analysis`, `portfolio-data-mining` — same treatment,
  tracked in `portfolio-nlp`'s `docs/engine-agnostic-rollout.md`.

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
