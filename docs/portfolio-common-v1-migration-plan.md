# Migration plan: portfolio-common v1.0.0 (DB engine + business_folders split)

## What changed upstream

`portfolio-common` v1.0.0 is a clean-break rewrite: the shared library used to
mix two concerns — a generic SQLite connection engine, and business/domain
code owned by specific downstream repos. This repo doesn't own any of that
business code (it's a pure consumer of one function), but the breaking change
still affects it directly:

- `portfolio-common` is now **DB-engine-only**:
  `portfolio_common.db.Database`, `portfolio_common.db.in_clause`,
  `portfolio_common.db.Allowlist`. It no longer ships `news_nlp` at all.
- Everything under the old `portfolio_common.news_nlp` package — including
  `connect_pipeline` and `fetch_processed_articles`, which this repo's
  `src/etl/news_to_rdf.py` imports directly — has moved to
  `business_folders/news_nlp/news_nlp/` in the `portfolio-common` repo,
  staged for **`portfolio-nlp`** to adopt into its own `src/news_nlp/`. This
  repo owns none of that code and gets nothing from `portfolio-common`
  v1.0.0 to replace it with.

## The decision this repo needs to make

Unlike the other three sibling repos, this one has no `business_folders/`
staging content of its own to pull in — it needs a new place to get
`connect_pipeline`/`fetch_processed_articles` from once `portfolio-common`
stops shipping `news_nlp`. Two options (pick one before executing this
plan — this is flagged as a decision point in `portfolio-nlp`'s own
migration-plan doc too, coordinate before executing either in isolation):

1. **Add a git dependency on `portfolio-nlp` itself**, once `portfolio-nlp`
   has vendored `news_nlp` into its own `src/news_nlp/` (per its migration
   plan). Import becomes `from news_nlp import connect_pipeline,
   fetch_processed_articles`. This makes `portfolio-knowledge-graph` depend
   on `portfolio-nlp`'s package the same way it currently depends on
   `portfolio-common`'s — a direct repo-to-repo dependency instead of a
   shared-library one. Cleanest long-term (one owner, one place these two
   functions live), but couples this repo's dependency graph to
   `portfolio-nlp`'s release cadence instead of `portfolio-common`'s.
2. **Duplicate the two functions locally** (or a minimal read-only query
   against the RESULTS DB shaped like `fetch_processed_articles`), built
   directly on `portfolio_common.db.Database` (which this repo keeps as a
   dependency regardless, for the engine). Avoids the new repo-to-repo
   dependency, at the cost of a second copy of that query to keep in sync
   with `portfolio-nlp`'s schema if it changes.

Recommendation: option 1, since `fetch_processed_articles`'s join logic
(cross-database SOURCE/RESULTS read, `_articles_rel` schema-qualification) is
exactly the kind of thing that should have one owner — but this is the
user's call, not a default to execute silently.

## What to pull in

Nothing from `business_folders/` — see decision above. Once the dependency
choice is made:

- **Option 1**: add `portfolio-nlp` to `[tool.uv.sources]`/`dependencies`
  (as a git dependency, mirroring how `portfolio-common` is pinned today),
  pointing at whatever tag `portfolio-nlp` cuts after it vendors `news_nlp`.
- **Option 2**: no new dependency; write the local query against
  `portfolio_common.db.Database` directly, following the `queries.py`
  convention below.

## Import updates

Current call site (confirmed by search when this plan was written — re-grep
before executing):

- `src/etl/news_to_rdf.py:30` — `from portfolio_common.news_nlp import
  connect_pipeline, fetch_processed_articles` → repoint per the decision
  above (`from news_nlp import ...` for option 1, or a local module for
  option 2)
- `src/etl/config.py` — also matched `portfolio_common` in search; check for
  any `news_nlp`-related config (DB path env vars) that needs to keep
  matching whatever `SOURCE_DATABASE_URL`/`DATABASE_URL` convention
  `news_nlp.env` used

## `queries.py` convention

If you take option 2 (local duplication), still follow the project-wide
convention: the query lives in one clearly documented module (e.g.
`src/etl/queries.py`), with a docstring noting its purpose and that it
mirrors `portfolio-nlp`'s `fetch_processed_articles` — not embedded inline in
`news_to_rdf.py`'s orchestration code.

## Version pin

Once the dependency decision is executed and this repo's ETL run succeeds
against a scratch RESULTS DB, bump `pyproject.toml`'s `[tool.uv.sources]`
pin:

```toml
portfolio-common = { git = "https://github.com/gamug/portfolio-common", tag = "v1.0.0" }
```

## Verification

- `uv sync`, `uv run pytest` (if this repo has a test suite covering
  `news_to_rdf.py` — confirm), and a manual run of
  `python -m etl.news_to_rdf` (or whatever this repo's actual entrypoint is)
  against a scratch RESULTS DB, confirming the RDF export still produces the
  same shape of output as before this migration.

---
🤖 Generated with [Claude Code](https://claude.com/claude-code) as part of the
portfolio-common v1.0.0 DB-engine/business_folders split.
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
