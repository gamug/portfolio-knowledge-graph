# `etl/` — knowledge-graph data population

Roadmap **step 2** of `10-integration-roadmap.md` — "ingestion adapters for
already-collected data" (step 0, `schema/`, is the only prior step marked done;
step 1 stands up the triple store the output loads into). This package turns two
external sources into a flat Turtle `data.ttl` that loads on top of this repo's
`schema/`:

| Source | Produces |
|---|---|
| Wikipedia "List of S&P 500 companies" table | `:Asset` + `:classifiedAs` (full ~503-constituent universe) |
| `urls.db` — the `news-collector` / `news-crawler` SQLite DB | `:NewsArticle`, `:ScoreSnapshot` (Sentiment), `:RiskEvent` (gated) |

It is an **MVP single-shot load**, not the named-graph-partitioned target
architecture of `07-ontology-topology.md`. There is no bitemporal / audit-trail
tracking on data loaded this way.

## Layout

```
etl/
  config.py          # resolves DB path / schema dir / output path / source URL from .env
  asset_master.py    # Wikipedia table  -> :Asset / :classifiedAs
  news_to_rdf.py     # urls.db          -> :NewsArticle / :ScoreSnapshot / :RiskEvent
  build_data_ttl.py  # entry point; orchestrates the two + a sample SHACL check
  common/
    gics_rollup.py   # GICS Sub-Industry -> reference.ttl :Ind_* rollup (Gap G5)
    provenance.py    # provenanceId formatting
    severity.py      # provisional G1/G2/G3 sentiment/category/severity formulas
    turtle_util.py   # dependency-free Turtle-literal helpers
```

## Configuration

`config.py` loads a repo-root `.env` (via `python-dotenv`). Copy `.env.example`
to `.env` and set at least `KG_URLS_DB`:

| Key | Default | Meaning |
|---|---|---|
| `KG_URLS_DB` | `<repo>/data/urls.db` | external `news-collector` SQLite DB. In this dev container it is bind-mounted at `/workspaces/thesis/data/urls.db` (see `.devcontainer/devcontainer.json`). |
| `KG_SCHEMA_DIR` | `<repo>/schema` | dir holding `tbox.ttl` / `shapes.ttl` / `reference.ttl` / `rules.ttl` |
| `KG_DATA_TTL` | `<repo>/data.ttl` | output path (git-ignored) |
| `KG_SP500_SOURCE_URL` | Wikipedia S&P 500 list | constituent table to parse |
| `KG_SAMPLE_NEWS_ROWS` | `500` | rows in the post-build SHACL validation sample |

## Running

```bash
python -m etl.build_data_ttl --limit 500   # smoke test: caps news rows, skips header + SHACL sample
python -m etl.build_data_ttl               # full run -> data.ttl (millions of triples; git-ignored)
```

Load order into a fresh triple store, `data.ttl` **last**:

```
schema/tbox.ttl -> shapes.ttl -> reference.ttl -> rules.ttl -> data.ttl
```

`build_data_ttl.py` does **not** run `pyshacl` over the full dataset — at 400K+
articles that is not a practical validation step. Instead it builds a
`KG_SAMPLE_NEWS_ROWS`-row sample and validates that against the real
`tbox.ttl` + `shapes.ttl` + `reference.ttl`.

## Scope — excluded this phase

- SEC EDGAR filings/sections (`:SECFiling`, `:SECFilingSection`)
- Pricing/trading data (`:PriceObservation`)
- `:Executive` — DEF14A-sourced only per `tbox.ttl`; not derivable from news NER
- `article_summary` / `sector_summary` — the "summary" feature
- `discovered_urls`, `article_entities`, `discovery_progress`
- Computed / orchestrator-layer classes (`:Veto`, `:AttractivenessSnapshot`,
  `:Universe`, `:UniverseMembership`, `:Portfolio`, `:PortfolioPosition`) —
  these *consume* this ETL's output, they are not populated by it.

## Provisional formulas requiring sign-off

Everything in `common/severity.py` is a documented assumption, not calibrated
against ground truth:

| Gap | Assumption |
|---|---|
| G1 | `rawValue = clamp(positive - negative, -1, 1)` |
| G2 | 9-dimension `article_category` → 4-value `RiskEvent.category` bucket table (`'other'` → no RiskEvent) |
| G3 | `creation_gate` bars (`negative ≥ 0.50` **or** `cat_score ≥ 0.70`); severity ladder + hard-trigger keyword bump. A category-confidence-only RiskEvent with `negative` below every tier is mapped to `LOW`. |
| G9 | `publishedDate = pub_date`, falling back to `fetched_at` when `pub_date` is null; rows with neither are skipped |

## Coupling notes

- **`reference.ttl` stays authoritative for its own `:Asset`s.** Any ticker
  already declared as an `:Asset` individual in `schema/reference.ttl` (the 5
  worked-example tickers today) is *not* re-emitted in `data.ttl` — otherwise a
  divergent `cikNumber` (e.g. `:XOM`'s post-reincorporation CIK on Wikipedia)
  would collide with `reference.ttl`'s value under the functional-property /
  `sh:maxCount 1` contract once both files load. Those tickers are still
  resolvable as `scoreSnapshotOfAsset` targets. The skip set is read from
  `reference.ttl` at build time (`reference_asset_tickers()`), not hard-coded.

## Known divergence (schema decision, not an ETL bug)

`schema/shapes.ttl`'s `ScoreSnapshotShape` requires `normalizedScore` for every
non-`SectorRelativeMomentum` snapshot, but the Sentiment snapshots emitted here
carry only `rawValue` (the scale v1's `-0.50` / `-0.60` thresholds are defined
on — see `tbox.ttl`'s `ThresholdComparison` comment). The post-build SHACL
check reports one violation per Sentiment snapshot until either a `rawValue`-only
branch is added to the shape or a normalisation step is agreed.
