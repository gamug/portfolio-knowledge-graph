# Integration Roadmap — Dependency-Ordered Build Steps

Companion to all four preceding documents. This is the "other steps" needed to reach the thesis's
stated scope (structure + maintain an S&P 500 portfolio from news + EDGAR + daily pricing),
sequenced by **dependency**, not by calendar date — each step lists what it needs from the steps
before it, and which repo owns it.

> **Scope update (2026-10-02).** This repo (`portfolio-knowledge-graph`) is purely
> integrative: it owns the ontology, the projection of its siblings' outputs into it, and the
> query surface. Steps 3–9 below are *computation*, and that computation is built (or planned)
> in `portfolio-data-mining`, `portfolio-nlp` and `portfolio-financial-analysis`, not here —
> they stay in the roadmap as dependencies this repo's projection reads from. The ownership
> map, the evidence behind it, and the differences found are in `.specify/memory/SPEC.md` §2.5–§2.6.
> "Built upstream" below is taken from those repos' own docs and was **not** verified by running
> them.

## Step → owner → status

| Step | What | Owner repo | Status |
|---|---|---|---|
| 0 | Ontology TBox + SHACL | this repo (`schema/`) | ✅ Done |
| 1 | Triple store | this repo (`src/kg_store/`, `docs/graphdb-setup.md`) | ✅ Done — GraphDB 11.5.1, `schema/` loaded, ABox writes pass the SHACL gate (PLAN Work item 3) |
| 2 | Ingestion / projection into the graph | this repo (`src/etl/` shortcut; real projection = PLAN Work item 4) | Shortcut built (assets from Wikipedia + news from `portfolio-nlp`); the real `v_*` projection not started |
| 3 | Daily pricing collector | `portfolio-data-mining` (pricing service) + `portfolio-financial-analysis` (`pricing_agent`); this repo projects `v_price_observation` | Built upstream |
| 4 | EDGAR batch pipeline | `portfolio-data-mining` (`sec_edgar` service) + `portfolio-financial-analysis` (`fundamental_agent`); this repo projects scores/filings/sections | Built upstream |
| 5 | NLP / sentiment service | `portfolio-nlp` | Partly built — per-article sentiment/NER/category shipped; per-asset-per-day aggregation not built |
| 6 | Agent layer (selection / monitoring cycles) | `portfolio-financial-analysis` (`cycle select` / `cycle monitor`); triggered by the future `portfolio-app` | Built upstream (logic); no scheduler anywhere |
| 7 | Entity resolution | `portfolio-financial-analysis` (`entity_resolution`) | Built upstream — as news-co-occurrence *candidates* |
| 8 | Sector layer + portfolio construction | `portfolio-financial-analysis` (`cycle`: SECTOR scores, ranking, positions) | Built upstream |
| 9 | Calibration / backtesting | `portfolio-financial-analysis` (`cycle backfill` replay, `quant evaluate`) | Partial — no walk-forward fitting or per-rule ablation harness found |

## What already exists (recap — full detail in each document's own context section)

| Repo/asset | Status |
|---|---|
| `portfolio-data-mining` (news discovery) | Built, tested — S&P 500 news URL discovery. |
| `portfolio-data-mining` (article extraction) | Built, tested — full article text extraction, 2,289/2,289 processed. |
| `portfolio-nlp` | Already publishes sentiment and category results (read by `src/etl/`); step 5 extends it with the FinBERT service from `09-nlp-finbert-architecture.md`. |
| `portfolio-data-mining` (`sec_edgar` service) | Built — SEC filings/financials over HTTP; swept over the full universe by `portfolio-financial-analysis`'s `fundamental_agent` (step 4). |
| `portfolio-data-mining` (pricing service) | Built — Finnhub/yfinance daily OHLCV, corporate actions and an as-of universe over HTTP (`GET /pricing/{ticker}`); consumed by `portfolio-financial-analysis`'s `pricing_agent` (step 3). |
| `portfolio-data-mining` (`universe.db`) | Built — point-in-time S&P 500 membership (valid-from/valid-to), read by every upstream agent; a direct input for this repo's projection. |
| `gdelt_news_full.csv` | Real historical GDELT data — usable as calibration/backtest fuel (step 9). |
| GraphDB repository `portfolio` | Built (step 1) — `schema/` loaded, reasoning profile `rdfsplus-optimized`, `cli/ingest.py` gate in front of writes. The ABox is still only the `instances.trig` worked example; real projection is PLAN Work item 4. |

## The steps

**0. Formalize ontology TBox + SHACL shapes.** ✅ **Implemented.**
`schema/tbox.ttl` + `schema/shapes.ttl` + `schema/reference.ttl` + `schema/rules.ttl` (this
series' §1) — 37 classes (24 mutually disjoint leaf/domain classes under a 13-class taxonomic
backbone added 2026-08-23), 14 SHACL shapes, the full 7-rule veto catalog as unambiguous trees, and a
5-asset worked dataset (`schema/instances.trig`) that's been parsed, SHACL-validated
(`pyshacl`: conforms = True), and independently re-evaluated in Python to confirm the rule trees
fire exactly as intended (that 7-rule catalog is superseded as the target by `portfolio-financial-analysis`'s
six-rule catalog — `.specify/memory/SPEC.md` §2.6 D4; `rules.ttl` now carries those six as the active catalog and keeps the seven as closed design history — T-103, done 2026-10-03). Everything downstream needs real classes to write into — this is why it
was built first, not last, in this whole engagement. Extended 2026-08-13 with an
attractiveness-ranking + sector-relative-momentum feature (4 new classes, a 7th veto rule, a
versioned weight scheme) — see docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md.
See `schema/README.md`.

**1. Stand up the triple store.**
GraphDB or Fuseki, with the named-graph topology from `07-ontology-topology.md` (TBox graph,
per-batch ABox graphs, quarterly Universe snapshots). `schema/instances.trig` already demonstrates
the target shape end to end (12 named graphs) against 5 example tickers — standing up a real store
is now a load operation (`schema/README.md`'s load order), not a from-scratch design exercise.
**Owner: this repo.**

**2. Ingestion adapters for already-collected data.**
Before building anything new, get the graph populated with what already exists, for early
validation: a small ETL script reading both tiers of the news databases through `portfolio_common.news_export` — the SOURCE `urls.db` (for `articles.body_text`, which the ETL's severity step scans) and `portfolio-nlp`'s results store (`nlp.db`) — and, for the real projection, `portfolio-financial-analysis`'s `v_*` views and `portfolio-data-mining`'s point-in-time `universe.db` — writing them as `NewsArticle`/evidence
individuals with `provenanceId` set (per `09-nlp-finbert-architecture.md`'s output contract). This
step deliberately comes *before* any new agent or NLP code — it's the fastest way to get a
SHACL-validated, non-trivial graph to test §0/§1's design against real data.

**3. Daily stock-pricing collector — built upstream.**
Owned by `portfolio-data-mining` (the pricing HTTP service: Finnhub with a yfinance fallback, daily
OHLCV and corporate actions) and `portfolio-financial-analysis` (`pricing_agent`, which calls it for
the point-in-time S&P 500 universe and stores `price_window`/`price_daily`/`price_observation`).
Nothing to build here. Per `07-ontology-topology.md`'s warning, the raw panel goes to a columnar store
(Parquet/SQLite), **not** the triple store — only derived `PriceObservation` summaries get
projected into the graph (from `v_price_observation`), and only for the bounded window the veto rules need.

**4. EDGAR batch pipeline — built upstream.**
`portfolio-financial-analysis`'s `fundamental_agent` sweeps the as-of S&P 500 universe over
`portfolio-data-mining`'s `sec_edgar` service (10-K/10-Q, fiscal years ≥ 2022), computes the ratios,
and writes one FUNDAMENTAL `score_snapshot` per filing; `--sections` additionally stores narrative
filing text (MD&A, risk factors) as `sec_filing_section` — the source of this repo's `SECFilingSection`
individuals. DEF 14A director lists are **not** among its outputs (see step 7). This is the batch
operation the Fundamental Agent's quarterly `fundamental_screen` node (`08-agent-architecture.md`)
assumed.

**5. NLP / FinBERT service in `portfolio-nlp` — partly built.**
`portfolio-nlp` already ships per-article sentiment (FinBERT), NER and category classification
(plus opt-in summaries) into its results store, which this repo's `src/etl/` reads. Not built: the
per-`(asset, day)` SEMANTIC aggregation, which `portfolio-nlp` is slated to own and
`portfolio-financial-analysis` to materialize as `score_snapshot[SEMANTIC]`
(`.specify/memory/SPEC.md` §13 item 11). `09-nlp-finbert-architecture.md` remains the design reference;
consuming step 4's filing sections is not part of what `portfolio-nlp` does today.

**6. Agent layer (selection / monitoring cycles) — built upstream, not LangGraph.**
`08-agent-architecture.md` designed two LangGraph graphs inside this repo. The cycle logic instead
exists as `portfolio-financial-analysis`'s `cycle` package (`cycle select`, `cycle monitor`,
`cycle backfill`): a checkpointed runner over relational tables, with veto stints and a T-1 lag, writing
to a relational database rather than the triple store. No repo has a scheduler; the future
`portfolio-app` is to trigger the runs. This repo builds no agents — it projects `cycle`'s outputs (step 2).
`08-agent-architecture.md` is kept as design reference, with a mapping to what exists.

**7. Entity resolution service — built upstream, narrower than designed.**
Closes critique gap #7 only in part. `portfolio-financial-analysis`'s `entity_resolution` derives
`sharedExecutiveWith` *candidate* edges from person-name co-occurrence in news (method-versioned, with
a weight), not from DEF 14A director lists, and its own docs say co-occurrence is not an actual shared
directorship. The `VETO_RED_01` contagion rule this step was meant to unblock has no counterpart in the
upstream rule catalog (`.specify/memory/SPEC.md` §2.6 D4, D10).

**8. Sector/rotation layer + portfolio construction module — built upstream.**
Closes critique gaps #2 and #3 together, since a ranking over survivors (portfolio construction) is
most useful once it can be viewed sector-relative (sector layer). Upstream's `cycle` does both in one
run: SECTOR scores and per-sector aggregates, a weighted blend of the score types, a ranking
(`cycle_ranking`) and capped position weights. The weighted-formula `AttractivenessSnapshot` of this
repo's ontology has no direct upstream equivalent; how it maps is open (T-109).

**9. Calibration/backtesting harness — partly built upstream.**
Closes critique gap #4. Upstream has `cycle backfill` (replaying selection cycles against a scratch
database) and `quant evaluate` (forward return of a frozen benchmark book); a walk-forward
threshold-fitting or per-rule ablation harness was not found. The aim: use the already-collected `gdelt_news_full.csv` and the historical price
panel (step 3) as backtest fuel for walk-forward threshold fitting and per-rule ablation — this is
sequenced last because it needs a working end-to-end system (steps 0–8) to backtest *against*, not
because it's less important.

---

*Diagram for this document (Exhibit 5) is in the companion Artifact: the dependency DAG for steps
0–9, annotated with which existing repo each step extends versus builds new.*
