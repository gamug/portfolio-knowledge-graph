# Agent Architecture — LangGraph

Companion to `06-ontology-definition.md` (what the agents read/write) and
`07-ontology-topology.md` (where). This document specifies the compute layer — the actual agent
processes that implement v1's "graph = memory, agents = compute" principle (§1), now built on
**LangGraph**, chosen because the codebase already has LangGraph coursework on this machine and
because its state-graph model plus built-in checkpointing map onto the two-speed cycle and the
`T-1` contagion lag natively, not as bolted-on infrastructure.

> **Status (2026-10-02): design reference, not a build target in this repo.** This repo is purely
> integrative, so it builds no agents. The two-speed cycle this document designs is implemented
> upstream by `portfolio-financial-analysis`'s `cycle` package, which differs from the LangGraph design
> below in several ways — see "Mapping to what exists upstream" at the end. Decision and evidence:
> `.specify/memory/SPEC.md` §2.2, §2.5, §2.6 and `PLAN.md` Work item 7. Repo names below were
> updated from the pre-split codebase to the current repos.

## Two graphs, mirroring the two-speed cycle

**`SelectionCycleGraph`** (quarterly, triggered by 10-K/10-Q publication — v1 §2A):

1. `fetch_universe_candidates` — the full S&P 500 list (reuses the universe loader already built in
   `portfolio-data-mining` — `data_mining.portfolio` / the point-in-time `universe.db` — not reimplemented).
2. `fundamental_screen` — fan-out (LangGraph `Send`) over ~500 tickers, each invocation calling a
   *batched* wrapper around `portfolio-data-mining`'s `sec_edgar` agent (built upstream as
   `portfolio-financial-analysis`'s `fundamental_agent` — see `10-integration-roadmap.md` step 4), computing solvency/liquidity metrics, and
   writing `ScoreSnapshot(agentOrigin='FUNDAMENTAL')` individuals straight to the graph.
3. `select_watchlist` — a join node after the fan-out: ranks/filters down to 50–80 names, writes
   new `UniverseMembership` individuals for the new quarter.
4. `close_ended_memberships` — sets `validTo` on the prior quarter's memberships for assets that
   fell off the watchlist (never deletes — matches v1 §2A's own stated behavior).

**`MonitoringCycleGraph`** (daily / continuous — v1 §2B):

1. `load_active_universe` — SPARQL query for the current candidate universe (`UniverseMembership`
   with unbound `validTo`) plus any open `PortfolioPosition` assets, per v1's own scoping rule.
2. Fan-out (`Send`) over that set, three parallel agent nodes per ticker — since 2026-08-13 this
   fan-out no longer joins straight back into a single `orchestrator` node; the shape is now
   `fan-out(quantitative_agent, technical_agent, semantic_agent) → sector_agent →
   {orchestrator, compute_attractiveness}` (spec §7), i.e. one join (`sector_agent`) feeding two
   independent sibling joins:
   - `quantitative_agent` — reads the price panel (external columnar store, **not** the graph —
     see `07-ontology-topology.md`'s price-panel warning) and writes `ScoreSnapshot('QUANTITATIVE')`.
   - `technical_agent` — computes momentum/ATR and writes `ScoreSnapshot('TECHNICAL')` plus a
     derived `PriceObservation`.
   - `semantic_agent` — pulls new rows from `portfolio-data-mining`'s `articles` table (via
     `portfolio-nlp`) and new EDGAR sections, calls the FinBERT service (`09-nlp-finbert-architecture.md`), writes
     `ScoreSnapshot('SEMANTIC')` and any `RiskEvent`s.
3. `sector_agent` — join node run after the fan-out (needs every asset's `ScoreTecnico` already
   written to compute a per-sector aggregate): reads all `ScoreSnapshot(metricType='ScoreTecnico')`
   individuals for the cycle, groups by `Sector` (via each `Asset`'s `classifiedAs` → `Industry` →
   `memberOfSector` chain), writes one `SectorAggregateSnapshot` per sector plus a per-asset
   `ScoreSnapshot(metricType='SectorRelativeMomentum', agentOrigin='SECTOR')` (added 2026-08-13,
   closes part of critique #3 — see `docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`).
4. `orchestrator` — join node after `sector_agent`: reads the live `RuleDefinition`/`RuleClause` tree
   for every active rule (`06-ontology-definition.md` §1.5) via SPARQL, evaluates each asset's
   latest snapshots against every rule using a plain-Python tree walker that mirrors the ontology's
   own `RuleClause`/`operand1`/`operand2`/`ThresholdComparison` structure exactly — the same tree,
   evaluated once, not re-parsed from a string — and writes `Veto` individuals for triggered
   assets. Since 2026-08-13 this also evaluates the 7th rule, `VETO_MKT_02`, against the
   `SectorRelativeMomentum` snapshots `sector_agent` just wrote.
5. `compute_attractiveness` — join node, sibling to `orchestrator` (both run after `sector_agent`,
   neither depends on the other): reads the active `AttractivenessWeightScheme` via SPARQL, reads
   each asset's latest snapshots (same snapshot set `orchestrator` reads), computes
   `attractivenessScore` per the weighted-formula convention (§3 of the spec above), writes one
   `AttractivenessSnapshot` per asset — independent of veto status, since ranking and exclusion are
   separate concerns with separate audit trails (added 2026-08-13).

## State schema — thin, by design

LangGraph state carries **references, not data** — the durable record lives in the graph, per v1
§1's own principle, now applied to the orchestration layer too:

```python
class MonitoringCycleState(TypedDict):
    cycle_date: str
    candidate_assets: list[str]                # tickers
    pending_snapshot_iris: dict[str, list[str]] # ticker -> IRIs written this cycle, not values
    prior_cycle_vetoes: dict[str, list[str]]    # ticker -> rule IRIs that fired last cycle (T-1)
    current_vetoes: dict[str, list[str]]
    sector_snapshot_iris: dict[str, str]        # sector -> SectorAggregateSnapshot IRI written this cycle
    attractiveness_iris: dict[str, str]          # ticker -> AttractivenessSnapshot IRI written this cycle
```

No metric value, article text, or evidence ever sits in LangGraph state — every agent node writes
straight to the triple store and state only threads the IRI back for the orchestrator to dereference.

## Tool inventory, reusing existing code

| Agent | Tools | Reuse vs. new |
|---|---|---|
| Fundamental | `portfolio-data-mining`'s `sec_edgar` agent (`get_financials`, `search_filings`, ...), batched | Built upstream as `portfolio-financial-analysis`'s `fundamental_agent` (roadmap step 4). |
| Semantic | `portfolio-data-mining`'s `articles` via `portfolio-nlp`'s results + FinBERT service | `portfolio-nlp` ships per-article sentiment/NER/category (`09-nlp-finbert-architecture.md`); the per-asset-per-day score is not built. |
| Quantitative / Technical | Pricing-data reader + indicator functions (ATR, Sharpe, volatility) | Built upstream — `portfolio-data-mining`'s pricing service feeds `pricing_agent`; `cycle` computes TECHNICAL and VALORIZATION (roadmap step 3). Deterministic calculations, not LLM calls — consistent with v1 §1's compute/memory split. |
| Sector | SPARQL `SELECT` (per-asset `ScoreTecnico`) + SPARQL `INSERT` (`SectorAggregateSnapshot`, `SectorRelativeMomentum`) | **New** (added 2026-08-13) — no sector roll-up exists anywhere yet. |
| Orchestrator | SPARQL `SELECT` (rule trees + latest snapshots) + Python boolean-tree evaluator + SPARQL `INSERT` (Veto) | Tree evaluator is the direct executable counterpart of `06-ontology-definition.md` §1.5's `RuleClause` structure — same tree, no separate rule language to maintain. |
| Orchestrator (`compute_attractiveness`) | SPARQL `SELECT` (`AttractivenessWeightScheme` + latest snapshots) + Python weighted-sum evaluator + SPARQL `INSERT` (`AttractivenessSnapshot`) | **New** (added 2026-08-13) — the weighted-sum evaluator is the direct executable counterpart of `06-ontology-definition.md` §1.8's formula, same "graph, not code" pattern as the veto tree evaluator. |

## Concurrency and checkpointing

**Fan-out**: LangGraph's `Send` API dispatches one sub-invocation per ticker, but the actual I/O
inside each invocation (EDGAR calls, price-API calls, SPARQL writes) is wrapped in an
`asyncio.Semaphore`, matching the pattern already established in `portfolio-data-mining`'s `news_collector`
`DiscoveryOrchestrator` (global + per-domain semaphores) rather than relying on LangGraph's own
dispatch to rate-limit calls to external, rate-limited APIs.

**Checkpointing *is* the T-1 mechanism, not a separate feature.** LangGraph's built-in checkpointer
(`SqliteSaver`/`PostgresSaver`) persists state after every node execution, keyed by a thread id
(one thread per cycle type). The orchestrator's `prior_cycle_vetoes` read at cycle N is literally
the checkpointed `current_vetoes` output of cycle N−1 — so `VETO_RED_01`'s `T-1` lag (v1 §4,
"Estrategia de Rezago de Ciclo") and ordinary resumability are the same feature. Cold start (v1
§5, `T=0`) needs no special-casing: when no checkpoint exists yet, the checkpointer returns empty
state, which is exactly v1's documented `∅` initialization.

## Mapping to what exists upstream

`portfolio-financial-analysis`'s `cycle` runs `universe → fundamental → technical → valorization →
semantic_read → normalize → sector → veto → rank → [positions]` (`positions` only for `select`), as a
topological runner whose resume state is the relational `cycle_checkpoint` table. Read from its docs and
code; not run here. Differences from the design above:

| This document | Upstream `cycle` |
|---|---|
| LangGraph state graphs, `Send` fan-out, `SqliteSaver`/`PostgresSaver` checkpointer | Checkpointed runner over relational tables; `cycle_run`/`cycle_checkpoint` are the resume source of truth (a Strands graph "can drive it later") |
| Writes individuals straight to the triple store | Writes relational rows (`score_snapshot`, `veto`, `cycle_ranking`, `portfolio_position`); this repo projects them |
| Quarterly selection triggered by 10-K/10-Q publication; daily monitoring | `cycle select` / `cycle monitor` are commands run with `--analysis-date`; **no scheduler exists** (`portfolio-app` is to trigger them) |
| `fundamental_screen` fan-out inside the selection graph | `fundamental_agent run` is a separate batch; `cycle` only reads its scores |
| Score type `QUANTITATIVE` | Renamed `VALORIZATION` |
| `semantic_agent` computes SEMANTIC | `semantic_read` is a no-op; the SEMANTIC row is pending the `portfolio-nlp` aggregation |
| `orchestrator` walks a `RuleClause` tree; seven rules incl. `VETO_RED_01` contagion and `VETO_MKT_02` | Six flat threshold rules (`LEVERAGE_EXTREME`, `NEGATIVE_FCF`, `LIQUIDITY_DISTRESS`, `PRICE_CRASH`, `EARNINGS_MISSING`, `DATA_QUALITY`); no contagion rule — upstream's catalog is the maintainer-confirmed final one |
| T-1 lag = the checkpointer's previous-cycle state | T-1 lag = a read-time predicate: a veto stint is active at cutoff C iff `raised_on <= C AND (cleared_on IS NULL OR cleared_on > C)`; vetoes are stints with a raised and a cleared date, closed never deleted |
| `compute_attractiveness` → `AttractivenessSnapshot` | `rank` blends the score types by per-run weights into `cycle_ranking` and capped `portfolio_position` stints; no attractiveness individual |
| Universe from a Wikipedia fetch / SPARQL on `UniverseMembership` | Point-in-time `universe.db` as of `--analysis-date` |

The T-1 mechanism, the stint model and the rule catalog are decisions still to be reflected in
`schema/` (`.specify/memory/PLAN.md` Work item 11, T-102/T-103).

---

*Diagram for this document (Exhibit 3) is in the companion Artifact: both LangGraph graphs, their
fan-out/join shape, and the checkpoint hand-off implementing T-1.*
