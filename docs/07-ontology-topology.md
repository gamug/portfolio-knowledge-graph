# Ontology Topology — Physical Layout of the RDF Store

Companion to [`06-ontology-definition.md`](./06-ontology-definition.md), which defines *what*
exists (classes, properties, shapes). This document defines *how it's physically laid out* in a
GraphDB or Fuseki quad store — named-graph partitioning, expected scale, indexing, and reasoning
scope. These are load-bearing operational decisions, not implementation detail — get the
partitioning wrong and either queries can't answer "what did we believe on date X" (the whole
point of the bitemporal upgrade, critique gap #8) or the store grinds under an unbounded price
panel that never should have been triples in the first place.

## Named-graph partitioning scheme

RDF triples have no transaction-time dimension of their own; a quad store's **named graph** is the
mechanism that supplies one — every ingested batch is written into its own graph, so "what did we
believe as of ingestion date X" falls out of *which graphs existed* at that point, not from a
special query language feature.

| Named graph pattern | Contents | Mutability |
|---|---|---|
| `urn:graph:tbox` | The ontology itself — classes, properties from `schema/tbox.ttl`, SHACL shapes from `schema/shapes.ttl` | Rarely changes; versioned like code. |
| `urn:graph:reference` | Static reference data: GICS `Sector`/`Industry` SKOS scheme, FIBO alignment annotations, Asset master data (`schema/reference.ttl`) | Rarely changes. |
| `urn:graph:reference:fibo` | The 25-term FIBO 2026Q2 glossary slice (`schema/fibo.ttl`, 54 entries, 277 statements), loaded after `reference.ttl`: FIBO labels and definitions with their original language tags, the named parents, the `cmns-av` notes, and the authors' `rdfs:label`@es / `skos:definition`@es on the 25 reviewed seeds. Produced by `cli/build_fibo_slice.py`; never hand-edited. | Append-only in effect: rebuilt only for a new FIBO release, and the old graph is replaced as a whole by `cli/load_schema.py`. |
| `urn:graph:rules:catalog` | The versioned rule catalog (`schema/rules.ttl`): selection rules and GUARD protection rules | Rarely changes; each `RuleDefinition` is already self-temporal via `validFrom`/`validTo` (`validTo` exclusive; since T-187 one `ruleId` can have two definitions over time, such as `LIQUIDITY_DISTRESS`, so query by `ruleId`, not by IRI). |
| `urn:graph:ingest:{agent}:{date}` | One graph per (agent, day) ingestion batch — that day's `ScoreSnapshot`s and `RiskEvent`s from `SEMANTIC`/`VALORIZATION`/`TECHNICAL` agents (v1's fast cycle, §2B). "That day's" means loaded that day (T-031): a snapshot is loaded once its `availableAt` is on or before the day, and keeps its own `availableAt` and `eventTime` whatever graph holds it, so a point-in-time query filters on `availableAt`, never on the graph's date. The first write after upstream's T-144 fills `available_at` loads every cycle-lane row accumulated until then into that one day's graph | **Append-only.** Never edited after creation — this is what makes it a faithful transaction-time record. So a graph is named only for the day it is written; a replay of past days writes only to a repository other than production (T-031). A replay reads upstream as it is now, so in a replay store a graph's date means "usable by", not "known on": it holds rows computed after that day and may hold rows production lost. Query a replay store by `availableAt`; it is neither a transaction-time record nor a copy of production. |
| `urn:graph:ingest:SECTOR:{date}` | One graph per Sector Agent daily run — `SectorAggregateSnapshot`s and per-asset `SectorRelativeMomentum` `ScoreSnapshot`s (added 2026-08-13, see spec) | **Append-only**, same convention as the other per-agent ingest graphs. |
| `urn:graph:ingest:FUNDAMENTAL:{year}-Q{n}` | One graph per quarter of the Fundamental Agent's slow cycle (not per run: one run can write several quarters) — new `UniverseMembership` records, fundamental `ScoreSnapshot`s, and `DataQualityIssue` evidence from the Ring-1 gates (T-104; dated by `dqRaisedOn`, optionally linked to the gated `SECFiling` and metric) (v1's slow cycle, §2A). A fundamental `ScoreSnapshot` goes to the quarter its `availableAt` falls in (when the filing became usable, as `instances.trig` does), so a run that backfills history writes one graph per quarter it covers; a quarter's graph is written only once that quarter is complete: before the run day's quarter, and covered by a full upstream analysis run (`v_analysis_run`: completed, every ticker, both forms, years reaching the quarter) as of a later quarter and no later than the run day, since upstream computes in batches after the fact and a scoped run or a row's `computed_at` says nothing about the rest of the quarter (T-031; which fields define a full run is SPEC Q7) | Append-only. A snapshot that arrives after its quarter's graph is written (a filing the covering run failed on, or one computed later still) is lost for that quarter and listed as lost (SPEC §13 item 10). |
| `urn:graph:ingest:ORCHESTRATOR:{date}` | The Orchestrator's own decisions — `Veto` individuals and any `RiskEvent`s it directly produced; also `AttractivenessSnapshot` individuals (added 2026-08-13) — the Orchestrator's ranking output, alongside its veto output — and, since T-121, the per-run `AttractivenessWeightScheme` (with its `WeightComponent`s) those snapshots point at by `computedWithScheme`, in the graph of its `cycleDate` | Append-only. A `Veto` stint is closed by a `clearedOn` triple written in the clearing cycle's graph (T-102), never deleted. A per-run weight scheme is never closed (T-121); only the design-history `WeightScheme_v1` lives in `urn:graph:rules:catalog`. |
| `urn:graph:ingest:EDGAR:{date-or-quarter}` | `SECFiling`/`SECFilingSection` individuals from the EDGAR batch pipeline (roadmap step 4), including restated sections | Append-only — see the restatement pattern below. |
| `urn:graph:derived:quant:{date}` | Benchmark `Portfolio` books (never upstream's `live_book` snapshot, T-109), their `PortfolioPosition`s and `BenchmarkObservation`s (T-108; from `v_quant_portfolio`/`v_quant_position`/`v_quant_benchmark_performance`/`v_quant_vs_live`). Never returns, μ or Σ | Append-only; separate from `urn:graph:portfolio:current` (the live book). |
| `urn:graph:derived:entity-resolution:{date}` | `AssetCoOccurrence` candidate edges (T-107; news co-occurrence, method/weight) and other entity-resolution-service output (roadmap step 7); `sharedExecutiveWith` only if verified | Append-only; kept separate from the EDGAR graphs it draws on since it's a different service's output. |
| `urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}` | The eight m018 backtest/GUARD views' individuals — `StrategyBook`, `BookRebalance`, `GuardAlert`, `GuardAction`, `BookWeightDaily`, `BookDailyPerformance`, `PortfolioPeriodSummary`, `BacktestTest` — one graph per backtest run, written by `src/projection/backtest.py` (T-207, T-231; `docs/08`), with each individual carrying `:knowledgeDate` for `knowledgeDate <= D` reads. The window qualifies the name because the three run databases each start their ids at 1; the run label (`rule`, `champ_v1`, …) qualifies it again because the views expose no run identity, so several result families can share one repository. | Append-only; a run is a frozen artifact, so a re-run is a new `backtest_run_id` (and, per Work item 17, a new automation/repository), never an edit. |
| `urn:graph:derived:backtest:selection:{run_label}:{window_id}:{backtest_run_id}` | The selection side of the same run: `SelectionCycle` (`v_cycle_run`), the configured `AttractivenessWeightScheme`/`WeightComponent` (`v_weight_scheme`/`v_weight_component`), the `AttractivenessSnapshot`s and per-asset effective-weight components (`v_cycle_ranking`/`v_cycle_ranking_component`), and the `Veto` stints (`v_veto`), written by `cli/project_selection.py` (Work item 26; `docs/08`). Same label and window vocabulary; a sibling graph because the m018 graph is append-only and may already be written. | Append-only; skipped, never appended to, when the graph already exists. Rule links resolve by `:ruleId` against the definition in force on the run's knowledge date (2026-10-31), not by `:raisedOn`. |
| `urn:graph:derived:ticker-history:{run_label}:{snapshot_date}` | One complete ticker-history snapshot — `TickerHistory` individuals for every `v_ticker_history` row — written by `src/projection/reference.py` (T-352; `docs/08`). The label names the source family and the date is the snapshot date (`--as-of`, default today in UTC). Every individual IRI carries both (`TickerHistory_{label}_{YYYYMMDD}_{cik}_{symbol}_{validFrom}`), so a later refresh is a new graph with new individuals, never a re-declaration of a stored one. | Append-only. A later snapshot is a new date (or a new label) and leaves the previous graph untouched; it is a reference-like complete snapshot, not a delta, and readers use the latest `urn:graph:derived:ticker-history:` graph. |
| `urn:graph:derived:orchestrator:{run_label}:{run_id}` | One `OrchestratorRun` and its `OrchestratorStep`s from `v_orchestrator_run`/`v_orchestrator_step`, written by `src/projection/reference.py` (T-353; `docs/08`). The label separates source families because each database starts its run ids at 1. The step links to its run by `:stepOfOrchestratorRun`; the step's own `run_id` is the string `"{run_kind}:{id}"`. | Append-only; a run is an immutable process record. A later run has a new id and a new graph, never an append to the previous one. |
| `urn:graph:universe:{year}-Q{n}` | The `Universe` individual + its membership boundary for that quarter; since T-220 the real asset catalog (`:SP500Index` + one `:Asset` per company line for a pure rename, or per symbol for concurrent classes / a mixed CIK / a CIK-less stint + one `:UniverseMembership` per stint) written there by `cli/load_universe.py` from `universe.db`, in the quarter of its `--as-of` | Append-only, one-time per repository: the whole catalog is written once, and a second load into the same quarter is refused (check 2) while a later quarter re-declares stored individuals (check 6). Memberships are closed by writing `validTo` on the stored record (never by deleting them); the gate checks that each closure names a stored, open record and a date after it opened (`graphdb-setup.md`, check 7). |
| `urn:graph:universe:{year}-Q{n}:delta:{n}` | The **incremental** asset-catalog delta (Work item 28): only the new `:Asset` individuals, their new `:UniverseMembership` individuals (and new memberships of stored assets), and the `:validTo` closures of stored open memberships that `cli/load_universe.py --delta` finds by diffing `universe.db` against the stored catalog. Drift (changed names, CIK, classification, other dates, source-absent rows) is reported, never written. `{n}` is the next free positive sequence for that quarter | Append-only, never appended to: each later delta gets the next `{n}`. It re-declares no stored typed individual and drops no graph, so the base quarter graph above stays the catalog's one-time boundary. |
| `urn:graph:portfolio:current` | Live `PortfolioPosition` individuals — the actively-held book | The one graph that's genuinely mutated in place, but even here, closing a position sets `validTo` rather than deleting the triple, preserving history in place (checked as above). |

**Implementation addendum — three graph patterns this table originally missed.** Building
`schema/instances.trig` (a real, loadable dataset, not just this table) surfaced three placements
this document hadn't specified: Asset master data belongs in `urn:graph:reference` (same
slowly-changing nature as the taxonomy it's classified against); the rule catalog gets its own
`urn:graph:rules:catalog`; and the Orchestrator's own output (`Veto`s) and entity resolution's
derived output (`sharedExecutiveWith`) each need a graph pattern distinct from the four *agents'*
ingest graphs this table originally enumerated. All four are folded into the table above.

**Contract v18 backtest/GUARD placement (T-206/T-207, T-231).** The eight m018 views are a
*backtest run's* output, not an agent's daily batch: one run owns three books, and each book owns
its rebalances, alerts/actions, daily weights, daily performance, period summaries and tests. The
accepted placement is `urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}` — one
append-only graph per run, written by `src/projection/backtest.py` (`docs/08`), with every
individual carrying `:knowledgeDate` so `knowledgeDate <= D` reads work without relying on the
graph name. The window is part of the name because `rule_P1.db`, `rule_P2.db` and `rule_P3.db` each
start their `backtest_run.id`/`strategy_book.id` at 1; the label is there because the views expose
no run identity at all (no input hash, no parameters), so the operator names the result family and
several can share a window. The label reaches every individual IRI stem as well
(`Book_{label}_{window}_{arm}`, …), so two families never share an individual; the gate's
backtest target pattern accepts only a label matching `[a-z][a-z0-9_]{1,31}` and a window
matching `P[0-9]+`. A label therefore identifies one run per window: a re-run of the same family
and window needs a different label or, per Work item 17, another automation/repository, because
equal stems would otherwise coincide. A run is a frozen artifact: a re-run is a new
`backtest_run_id` (and, per Work item 17, a new automation/repository), never an edit, and the gate
refuses an existing graph. The m015 `OrchestratorRun`/`OrchestratorStep` and m016
`TickerHistory` classes are not m018 output: T-208 places them in
`urn:graph:derived:ticker-history:{label}:{snapshot_date}` (one complete snapshot, labelled and
dated so a later refresh is a new graph) and
`urn:graph:derived:orchestrator:{label}:{run_id}` (one graph per immutable run), both written by
`src/projection/reference.py`. `TickerHistory`'s own interval is inclusive
(`validFrom <= d <= validTo`, `validTo` = the symbol's last valid date, handoff §3.1), unlike
`RuleDefinition`'s exclusive `validTo`.

**Selection-side placement (Work item 26).** The four selection views (`v_veto`, `v_cycle_run`,
`v_cycle_ranking`, `v_cycle_ranking_component`) plus the scheme views they depend on are a *run's*
output too, but they go in the sibling graph above. A `SelectionCycle` carries `:cycleRunId`, which
matches a `BookRebalance`'s literal `:cycleRunId` (`NULL` on `MARKOWITZ_BASE`, so that arm has no
selection link); a ranking snapshot reaches its cycle by `:rankingOfCycle` and its scheme by
`:computedWithScheme`. The graph is validated and written through the ingest gate exactly like the
m018 one, and a `--write` that finds it already present reports and skips it. The selection graph
does not contain a `StrategyBook`, so `runs-available` still reads the m018 graph.

**Context-fetch rule (Work item 30).** On a write the ingest gate does not validate a batch beside
the whole store. It fetches, for each individual the batch points at, only the properties the
shapes read: the target class comes from the relation's `sh:class` first and, when the relation
declares none, from its `rdfs:range` in the TBox (`gate.context_predicates`). This is why
`:appliesRule`/`:primaryRule` (no `sh:class`, deliberately, so the canonical pyshacl command can
validate `instances.trig` without `rules.ttl`) and `:attractivenessOfAsset`/`:vetoOfAsset` (no
property shape) still fetch `:ruleId`/`:category`/`:ruleSeverity` and
`:cikNumber`/`:hasUniverseMembership`; fetching only `rdf:type` made `AssetShape` and
`RuleDefinitionShape` fail on the first real selection write (2026-11-04, `portfolio_test`). The
dry run validates beside the full local rules/asset graphs and cannot see this difference, so the
projection CLIs offer a read-only `--check-store`: it runs the same `gate.plan` a write uses
against the live store with `SELECT` only -- the context validation plus checks 2 (target graph),
6 (stored individuals) and 7 (closing state) -- and reports `would-be-written`,
`already-in-the-store` (skipped) or `refused`, writing nothing.

**Asset master load (T-220).** The real asset master (`portfolio-data-mining`'s point-in-time
`universe.db`, D1) is written by `cli/load_universe.py` (logic in `src/kg_store/universe.py`) into
the quarter graph of its `--as-of`, through the ingest gate, reusing `etl.asset_master`. It does
not go into `urn:graph:reference`, where the table above puts *static* reference data:
`cli/load_schema.py` drops and rewrites every graph owned by `schema/` on each reload, so ABox
individuals written there would disappear on the next schema edit, and the loader could not append
to it (the gate refuses an existing graph for every append-only target). The quarter graph is the
placement this table already assigns to the universe and the gate already accepts; the catalog is
the membership boundary of that quarter. `--since` (default 2019-01-02) keeps a stint with no
`validTo` or `validTo >= since`; `validTo` is inclusive (the last day of membership), so a one-day
stint is kept. A point-in-time read on day D is `validFrom <= D AND (no validTo OR validTo >= D)`;
on its last day a membership is still in. A ticker reused by another company (`CEG`, `DELL`, `Q`) is
one `:Asset` described by the era the backtests and the live index can see; nothing is invented for
the dropped stints. The catalog is resolved by CIK (T-264): a pure ticker succession (`FB`→`META`)
is ONE `:Asset` named by the latest symbol with every stint as a membership, so the backtest's
`holding_key` (the current ticker) links across the rename; concurrent classes, a mixed CIK and a
CIK-less symbol stay per symbol. The five `:Asset`s `reference.ttl` already declares get memberships
but are never re-declared, and a CIK-less asset is accepted only when all its memberships are closed
(`AssetShape`).

**Known overlap with the worked example.** `schema/instances.trig` already holds `:UM_*_2026Q3`
memberships for the five `reference.ttl` assets in `urn:graph:universe:2026-Q3`, against
`:SP500Watchlist_2026Q3` (a fundamental-agent watchlist, not `:SP500Index`). The loader adds a
second set of memberships for those five in its own quarter graph; they are different
`:UniverseMembership` individuals in a different `:Universe`, and neither the batch nor this
change removes or re-declares anything. The overlap is accepted until the worked-example ABox stops
being loaded into the real store (TASKS T-225).

**Incremental catalog deltas (Work item 28).** `cli/load_universe.py --delta` diffs the source
against the stored catalog and writes only what is new into
`urn:graph:universe:{year}-Q{n}:delta:{n}`. The stored catalog it reads is the `:Asset`
individuals and the `:UniverseMembership`s whose `:membershipUniverse` is `:SP500Index` (the
worked-example `:SP500Watchlist_2026Q3` memberships in `urn:graph:universe:2026-Q3` are a
different universe and are not catalog drift). The delta has four categories: new assets (with
their stints), new memberships of stored assets (a re-entry, or a symbol of a renamed company that
still folds into the stored asset by CIK), closures (only the closing `:validTo` triple), and
drift. Drift covers a changed `:companyName`, `:cikNumber` or `:classifiedAs` (the store's only
sector/sub-industry fact), a stored membership with other `membershipAsset`/`validFrom`/`validTo`
values, a stored closed membership whose source stint is open, and a stored membership or
non-reference asset absent from the source. Drift is reported and never applied: the old value is
not rewritten, the old membership is not deleted, and no graph is dropped. The five
`reference.ttl` assets keep their declarations and are not compared; they still get new
memberships. The source is read with the loader's own `--since` and `resolve_assets`, so the full
load and the delta agree on the asset set. The run is idempotent: after a write, the next run's
actionable delta is empty and nothing is written. The runbook
([`backtest-load-runbook.md`](backtest-load-runbook.md)) carries the procedure; the dry run against
the repository whose catalog came from the same `universe.db` must be empty.

**Restatements/amendments** (the concrete case critique gap #8 was raised for): a corrected 10-K
does not edit the old `SECFilingSection` individual — it lands in a *new* dated EDGAR graph
alongside a `:supersededBy` triple pointing from the old section to the new one, asserted in the
new graph (where the correction becomes known), never by editing the original graph. This is more
precise than this section's earlier framing of a graph-level `supersededBy` metadata pointer:
`schema/tbox.ttl` gives `SECFilingSection` its own `supersededBy` object property, so supersession
is tracked at the individual level, and no separate metadata graph is needed at all. Both versions
stay queryable; only the "current best understanding" view filters to the latest non-superseded
section. Worked example (JNJ's Item 1A, original + restated) in `schema/instances.trig`.
Scope, the gate's check 8 and why no source emits a restatement today: see "Restatements and re-runs" below (T-032).

**Restatements and re-runs (T-032, decided 2026-10-12).** Two cases look alike and are handled
differently:

- **A correction known on a later day** (a restated section; a cycle-lane score recomputed after its
  graph was written) is new information and is kept: a new individual in a new dated graph, never an
  edit. What links it to the old one depends on the class. A `SECFilingSection` uses `:supersededBy`,
  which the gate checks (`graphdb-setup.md`, check 8): the old side is a stored or declared section not
  yet superseded, the new side is a section of the same item that the same batch declares, a new
  section replaces one section, no chain loops, and a second correction replaces the latest section,
  not the first; so each item's restatements form one chain with one current section. Every other
  observation (a `ScoreSnapshot` recomputed under a newer engine version, say) takes no link: readers
  keep the latest `timestamp` among rows with `availableAt <= D` (the query in "Re-projection" below).
  Both versions stay in the store and in the reasoner's view; "current" is a filter on the query, not a
  place the old value is moved to. An as-of query for a day before the correction still sees the old
  value. **Scope.** The correction can go into a new graph only where a graph's date can be the day the
  correction became known: the graphs dated by ingestion (SEMANTIC, VALORIZATION, TECHNICAL, SECTOR), and
  EDGAR, whose restatement is dated by its own filing. In every other graph dated by the data
  (`ORCHESTRATOR` by `cycleDate`, `FUNDAMENTAL` by quarter, `derived:quant`, `derived:entity-resolution`,
  `universe`) the graph for that date already exists when a late correction arrives, the gate refuses to
  append to it, and the row is lost for that date and listed as lost (the FUNDAMENTAL row of the table
  above; SPEC §13 item 10). This rule does not change that; a recomputed ranking snapshot or quant book
  for a past cycle date is in the second group. Work item 28's universe delta is not a restatement: it
  never changes a stored asset value or membership date, it only adds new individuals and writes the
  closing `:validTo`, and any other difference is reported as drift. **No source emits a restatement today:** upstream stores
  no amendments (10-K/A and 10-Q/A are not stored; each period's values come from its original filing,
  SPEC §2.6, seventh reply) and `v_sec_filing_section` has no column naming a replacement. The rule and
  the gate's check 8 wait for one; if upstream starts storing amendments, a projector rule derives the
  link, as a new task then.
- **A second run for the same agent and day** is refused by the gate ("already exists and is
  append-only"), and the first stays. A re-run with other settings, or after a fix, is a new
  automation (one realization of the algorithm) built in its own GraphDB repository, so no graph is
  ever replaced.

> **As-of reads (T-101).** The graph date is the ingest batch, not the usable date. `ScoreSnapshot.availableAt` is the look-ahead guard: as-of-D queries over `ScoreSnapshot`s filter `availableAt <= D`, never `eventTime` or `timestamp`. `SectorAggregateSnapshot` and `AttractivenessSnapshot` are same-cycle derived outputs with no separate clock: they are usable from the date of their `timestamp`/`computedAt`.
>
> **Run provenance (T-106, D7).** Upstream rows (`ScoreSnapshot`, `SectorAggregateSnapshot`, `Veto`, `PortfolioPosition`, `DataQualityIssue`, and since T-107/T-108 `AssetCoOccurrence`, `BenchmarkObservation`) may carry the run that wrote them as plain optional properties: `runId`, `runAsOf`, `codeVersion`, `engineVersion` (no `rdfs:domain`, like `provenanceId`; SHACL scopes them per class). There is no `Run` class and the run log (params, dirty-tree reason, `schema_version`) stays upstream, reachable through `runId` and the `v_*_run` views. Per-score-type extras `forensic_flags_json`, `prompt_hash` and `correction_rule` are deliberately not projected (see `schema/README.md`).
>
> - **Stints and valid-time records record the opener.** A `Veto` (stint) and a `PortfolioPosition` (valid-time) are appended to by later cycles (`lastSeenOn`, `clearedOn`/`validTo`, often from another run; the gate accepts both, a `lastSeenOn` only on a stored Veto that is not cleared, T-194). On them the four properties record only the run that **opened** the record (`raisedOn`/`validFrom`); later cycles must not re-emit them (that would give two values, violating `maxCount 1` and the functional property, which OWL2-RL reads as an inconsistency) and the closing run is not recorded. Immutable observations (`ScoreSnapshot`, `SectorAggregateSnapshot`) and `DataQualityIssue` rows are written once, so no such rule is needed.
> - **Three dates, three jobs.** `eventTime` = what the observation is about; `availableAt` = the **only** as-of read filter; `runAsOf` = the date the producing run was evaluated for, informational. For TECHNICAL/VALORIZATION/SECTOR it equals `eventTime` (so omit it); it can differ for FUNDAMENTAL and for `backfill` replays.
> - **Re-projection / several engine versions.** Upstream writes parallel rows per `engine_version` and its views return the newest, so a later projection can add a second snapshot for a key already loaded (graphs are append-only). Projectors should skip a key already present with the same `runId`+`engineVersion`. Readers must collapse duplicates per (asset, `metricType`, `eventTime`) by **latest `timestamp` among rows with `availableAt <= D`** -- never by comparing `engineVersion`, which is an unordered string:
>
>   ```sparql
>   SELECT ?s WHERE {
>     ?a :hasScoreObservation ?s . ?s :metricType ?m ; :eventTime ?e ; :timestamp ?t ; :availableAt ?av .
>     FILTER (?av <= "2026-08-05"^^xsd:date)
>     FILTER NOT EXISTS { ?a :hasScoreObservation ?s2 . ?s2 :metricType ?m ; :eventTime ?e ; :timestamp ?t2 ; :availableAt ?av2 .
>                         FILTER (?av2 <= "2026-08-05"^^xsd:date && ?t2 > ?t) }
>   }
>   ```
> - **Cost.** Four optional triples on up to ~2.2M `ScoreSnapshot`s is up to ~9M extra triples (literals are dictionary-encoded, so the cost is statements, not strings); `runAsOf` is omitted on cycle types, cutting it to ~6.6M. See the scale table.

## Scale estimate

Back-of-envelope for a full 2022–present backfill (~4 years, ~1,008 trading days), 500 `Asset`s:

| Source | Rough volume | Why |
|---|---|---|
| `ScoreSnapshot` (VALORIZATION + TECHNICAL) | ~2.0M individuals | Daily metrics × 500 assets × ~1,000 trading days × 2 agents × ~2 metrics each. |
| `ScoreSnapshot` (SEMANTIC) | ~200K individuals | News-driven, not every company every day — roughly matches the density already observed in `portfolio-data-mining`'s extracted-article corpus (2,289 articles from just 8 tickers in a sample window) scaled to 500 tickers over 4 years. |
| `ScoreSnapshot` (FUNDAMENTAL) | ~25K individuals | Quarterly × 500 assets × ~16 quarters × ~3 metrics. |
| `NewsArticle` | ~100K–150K individuals | Scaling the existing extracted-article corpus density (§ above) to the full S&P 500. |
| `SECFilingSection` | ~30K individuals | 500 companies × ~20 filings (10-K/10-Q/DEF 14A) over 4 years × ~3 sections each. |
| Run provenance (T-106) | ~6–9M triples | Up to four optional properties (`runId`, `codeVersion`, `engineVersion`, `runAsOf`) per upstream-row individual, ~2.2M `ScoreSnapshot`s dominating. A `Run` node would be a few thousand triples plus one link each, but run values are identical across a run's rows and stay upstream, so denormalising was accepted; revisit if the store grows past single-node scale. |
| `RiskEvent`, `Veto` | Low tens of thousands | Only fires when a threshold is actually crossed — a small fraction of `ScoreSnapshot` volume. |
| `SectorAggregateSnapshot` + `SectorRelativeMomentum` + `AttractivenessSnapshot` (added 2026-08-13) | Low tens of millions combined at full backfill scale | ~11 sectors × 500 assets × ~1,000 trading days — comparable order of magnitude to the existing daily `ScoreSnapshot` volume above; does not change this table's headline order-of-magnitude conclusion below, it's absorbed within it. |

**Total: on the order of 15–20 million triples (about 22–29 million with T-106's run provenance)** over the full historical backfill, dominated by
the daily fast-cycle `ScoreSnapshot` volume. That is comfortably within a single-node GraphDB or
Fuseki+TDB2 deployment — no clustering or distributed store is warranted at this scale, which
matters for a thesis-scope, single-researcher environment.

**The load-bearing warning:** raw daily OHLCV bars (500 tickers × ~1,000 trading days × 5–6 fields
= **~3M rows of low-semantic-value, high-volume tick data**) must **not** be stored as RDF triples
at that density — it would roughly double total triple count for data that's almost never queried
by IRI, only by (`asset`, `date range`) scans that a columnar/relational store answers far better.
`PriceObservation` individuals (`06-ontology-definition.md` §1.2) are explicitly **derived summaries
only** — closing price, daily return, ATR — projected into the graph for the bounded window the
veto rules actually need (e.g. a rolling 90-day window), while the full historical OHLCV panel
lives in a separate columnar store (Parquet/SQLite/Postgres) that the Valorization/Technical agents
query directly. This is the single design call in this document most likely to be silently
violated by a future implementer reaching for "just put everything in the graph" — it's called out
here explicitly so it isn't.

## Indexing

- **SPOG-family indexes** (store defaults — GraphDB and Fuseki+TDB2 both maintain multiple
  permutation indexes so any triple-pattern position can be bound efficiently). No custom indexing
  work needed here; this is a "don't disable the defaults" note, not a build task.
- **Full-text index** (GraphDB's Lucene connector, or Jena's text query module in Fuseki) over
  `RiskEvent` free-text fields, `NewsArticle` titles, and `SECFilingSection` text — supports
  evidence search for the audit/explainability layer (evolution layer B9) and doubles as the
  candidate-generation step for entity resolution (fuzzy name matching over `Executive`/`Asset`
  labels, roadmap step 7).

## Reasoning profile

Recommend **OWL 2 RL / RDFS+ only** — not a full OWL DL reasoner:

- **Turn on:** `rdfs:subClassOf` transitivity — this now pays off in two places, not one. The GICS
  `Industry → Sector` roll-up ("give me every `Asset` in the Information Technology sector",
  ~11 sectors/~70 industries) is cheap to materialize, as before. As of the 2026-08-23 taxonomy
  revision (`06-ontology-definition.md` §1.2), the ontology's own 38 domain classes also have
  `subClassOf` structure to reason over — e.g. `?x a :ObservationSnapshot` now correctly returns
  every `ScoreSnapshot`, `SectorAggregateSnapshot`, and `AttractivenessSnapshot` individual without
  the query author enumerating all three types by hand. Before that revision this setting only ever
  did work for GICS, since the 25 domain classes had no `subClassOf` edges among themselves at all —
  worth noting since it means this section's recommendation is now doing more than it used to for
  the same reasoning cost.
- **Leave off:** full OWL DL / property-chain reasoning. In particular, `sharedExecutiveWith`
  (used by the superseded `VETO_RED_01`'s contagion check, dropped from the target catalog by T-103) is deliberately **not** something the reasoner
  computes automatically via property chains — it would be written explicitly as application logic (upstream's news candidates are `AssetCoOccurrence`, not this property, and no upstream source of *verified* edges exists today, so the closed `VETO_RED_01` has nothing feeding it), not inferred transitively across the graph.
  Materializing deep inference chains over tens of millions of `ScoreSnapshot` triples would blow
  up both load time and result-set size for a benefit that, for this rule specifically, needs
  controlled/auditable logic anyway — an inferred edge is harder to explain in an audit trail than
  one an explicit service wrote and can justify.

---

*Diagram for this document (Exhibit 2) is in the companion Artifact: the named-graph topology map
and an example bounded cross-graph query path.*
