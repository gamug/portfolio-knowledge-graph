# Integration Roadmap — Dependency-Ordered Build Steps

Companion to all four preceding documents. This is the "other steps" needed to reach the thesis's
stated scope (structure + maintain an S&P 500 portfolio from news + EDGAR + daily pricing),
sequenced by **dependency**, not by calendar date — each step lists what it needs from the steps
before it, and which existing repo (if any) it extends versus builds from scratch.

## What already exists (recap — full detail in each document's own context section)

| Repo/asset | Status |
|---|---|
| `news-collector/` | Built, tested — S&P 500 news URL discovery. |
| `news-crawler/` | Built, tested — full article text extraction (2,289/2,289 processed). |
| `news-nlp/` | Empty scaffold — target of step 5. |
| `projects/web_scraping/portfolio-data-mining/src/fundamental/edgar_tool.py` | Built, on-demand single-company EDGAR wrapper — target of step 4's batch extension. |
| `projects/web_scraping/portfolio-data-mining/src/trading/` | **Empty** — no pricing pipeline anywhere — target of step 3. |
| `gdelt_news_full.csv` | Real historical GDELT data — usable as calibration/backtest fuel (step 9). |
| No triple/graph store anywhere | Target of step 1. |

## The steps

**0. Formalize ontology TBox + SHACL shapes.** ✅ **Implemented.**
`schema/tbox.ttl` + `schema/shapes.ttl` + `schema/reference.ttl` + `schema/rules.ttl` (this
series' §1) — 27 classes, 14 SHACL shapes, the full 7-rule veto catalog as unambiguous trees, and a
5-asset worked dataset (`schema/instances.trig`) that's been parsed, SHACL-validated
(`pyshacl`: conforms = True), and independently re-evaluated in Python to confirm the rule trees
fire exactly as intended. Everything downstream needs real classes to write into — this is why it
was built first, not last, in this whole engagement. Extended 2026-08-13 with an
attractiveness-ranking + sector-relative-momentum feature (4 new classes, a 7th veto rule, a
versioned weight scheme) — see docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md.
See `schema/README.md`.

**1. Stand up the triple store.**
GraphDB or Fuseki, with the named-graph topology from `07-ontology-topology.md` (TBox graph,
per-batch ABox graphs, quarterly Universe snapshots). `schema/instances.trig` already demonstrates
the target shape end to end (11 named graphs) against 5 example tickers — standing up a real store
is now a load operation (`schema/README.md`'s load order), not a from-scratch design exercise.

**2. Ingestion adapters for already-collected data.**
Before building anything new, get the graph populated with what already exists, for early
validation: a small ETL script reading `news-collector`+`news-crawler`'s SQLite (`discovered_urls`,
`articles`) and any existing GDELT/EDGAR outputs, writing them as `NewsArticle`/evidence
individuals with `provenanceId` set (per `09-nlp-finbert-architecture.md`'s output contract). This
step deliberately comes *before* any new agent or NLP code — it's the fastest way to get a
SHACL-validated, non-trivial graph to test §0/§1's design against real data.

**3. Daily stock-pricing collector — new.**
The one clear gap with zero existing code (`src/trading/` is empty). Recommend reusing the
`finnhub-python` dependency already present in `portfolio-data-mining/requirements.txt` (or
`yfinance` as a free, no-key alternative) for daily OHLCV, 2022–present, across all S&P 500
tickers. Per `07-ontology-topology.md`'s warning, the raw panel goes to a columnar store
(Parquet/SQLite), **not** the triple store — only derived `PriceObservation` summaries get
projected into the graph, and only for the bounded window the veto rules need.

**4. EDGAR batch pipeline — extends `edgar_tool.py`.**
Turns the existing on-demand, single-company `EdgarAgent` into a scheduled, full-universe sweep:
iterate all S&P 500 tickers, pull 10-K/10-Q/DEF 14A, and extract Item 1A/Item 3/DEF 14A-director
sections as `SECFilingSection` individuals — the structured-evidence counterpart to what
`news-collector`/`news-crawler` already do for news. This is what makes the Fundamental Agent's
quarterly `fundamental_screen` node (`08-agent-architecture.md`) a batch operation instead of 500
sequential on-demand calls.

**5. FinBERT service in `news-nlp/`.**
Builds `09-nlp-finbert-architecture.md` into the currently-empty repo, consuming step 2's ingested
articles and step 4's new filing sections. This is the first step that actually needs steps 0–4 to
already exist — chunking/scoring text that isn't in the graph yet, with nowhere to write results,
would be untestable.

**6. LangGraph agent layer.**
Builds `08-agent-architecture.md`'s two graphs, reading/writing everything steps 0–5 established:
the ontology (0), the store (1), real seed data (2), pricing (3), filings (4), and sentiment (5).
This is deliberately late in the sequence — the agents are orchestration *over* already-working
components, not a scaffold built before there's anything real to orchestrate.

**7. Entity resolution service — new.**
Closes critique gap #7. Needed before `VETO_RED_01`'s contagion check
(`sharedExecutiveWith`, `06-ontology-definition.md` §1.3) can be trusted — without canonical
identity resolution across news text, DEF 14A filings, and price/ticker data, the contagion rule
would silently match on unresolved name strings.

**8. Sector/rotation layer + portfolio construction module — new.**
Closes critique gaps #2 and #3 together, since a ranking/attractiveness score over survivors
(portfolio construction) is most useful once it can be viewed sector-relative (sector layer) —
building them in the same step avoids doing the ranking logic twice.

**9. Calibration/backtesting harness — new.**
Closes critique gap #4. Uses the already-collected `gdelt_news_full.csv` and the historical price
panel (step 3) as backtest fuel for walk-forward threshold fitting and per-rule ablation — this is
sequenced last because it needs a working end-to-end system (steps 0–8) to backtest *against*, not
because it's less important.

---

*Diagram for this document (Exhibit 5) is in the companion Artifact: the dependency DAG for steps
0–9, annotated with which existing repo each step extends versus builds new.*
