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
| `urn:graph:rules:catalog` | The versioned veto rule catalog (`schema/rules.ttl`) | Rarely changes; each `RuleDefinition` is already self-temporal via `validFrom`/`validTo`. |
| `urn:graph:ingest:{agent}:{date}` | One graph per (agent, day) ingestion batch — that day's `ScoreSnapshot`s and `RiskEvent`s from `SEMANTIC`/`VALORIZATION`/`TECHNICAL` agents (v1's fast cycle, §2B) | **Append-only.** Never edited after creation — this is what makes it a faithful transaction-time record. |
| `urn:graph:ingest:SECTOR:{date}` | One graph per Sector Agent daily run — `SectorAggregateSnapshot`s and per-asset `SectorRelativeMomentum` `ScoreSnapshot`s (added 2026-08-13, see spec) | **Append-only**, same convention as the other per-agent ingest graphs. |
| `urn:graph:ingest:FUNDAMENTAL:{year}-Q{n}` | One graph per quarterly Fundamental Agent run — new `UniverseMembership` records, fundamental `ScoreSnapshot`s, and `DataQualityIssue` evidence from the Ring-1 gates (T-104; dated by `dqRaisedOn`, optionally linked to the gated `SECFiling` and metric) (v1's slow cycle, §2A) | Append-only. |
| `urn:graph:ingest:ORCHESTRATOR:{date}` | The Orchestrator's own decisions — `Veto` individuals and any `RiskEvent`s it directly produced; also `AttractivenessSnapshot` individuals (added 2026-08-13) — the Orchestrator's ranking output, alongside its veto output | Append-only. A `Veto` stint is closed by a `clearedOn` triple written in the clearing cycle's graph (T-102), never deleted. |
| `urn:graph:ingest:EDGAR:{date-or-quarter}` | `SECFiling`/`SECFilingSection` individuals from the EDGAR batch pipeline (roadmap step 4), including restated sections | Append-only — see the restatement pattern below. |
| `urn:graph:derived:quant:{date}` | Benchmark `Portfolio` books (never upstream's `live_book` snapshot, T-109), their `PortfolioPosition`s and `BenchmarkObservation`s (T-108; from `v_quant_portfolio`/`v_quant_position`/`v_quant_benchmark_performance`/`v_quant_vs_live`). Never returns, μ or Σ | Append-only; separate from `urn:graph:portfolio:current` (the live book). |
| `urn:graph:derived:entity-resolution:{date}` | `AssetCoOccurrence` candidate edges (T-107; news co-occurrence, method/weight) and other entity-resolution-service output (roadmap step 7); `sharedExecutiveWith` only if verified | Append-only; kept separate from the EDGAR graphs it draws on since it's a different service's output. |
| `urn:graph:universe:{year}-Q{n}` | The `Universe` individual + its membership boundary for that quarter | Append-only, closed by writing `validTo` on the *previous* quarter's memberships (never by deleting them). |
| `urn:graph:portfolio:current` | Live `PortfolioPosition` individuals — the actively-held book | The one graph that's genuinely mutated in place, but even here, closing a position sets `validTo` rather than deleting the triple, preserving history in place. |

**Implementation addendum — three graph patterns this table originally missed.** Building
`schema/instances.trig` (a real, loadable dataset, not just this table) surfaced three placements
this document hadn't specified: Asset master data belongs in `urn:graph:reference` (same
slowly-changing nature as the taxonomy it's classified against); the rule catalog gets its own
`urn:graph:rules:catalog`; and the Orchestrator's own output (`Veto`s) and entity resolution's
derived output (`sharedExecutiveWith`) each need a graph pattern distinct from the four *agents'*
ingest graphs this table originally enumerated. All four are folded into the table above.

**Restatements/amendments** (the concrete case critique gap #8 was raised for): a corrected 10-K
does not edit the old `SECFilingSection` individual — it lands in a *new* dated EDGAR graph
alongside a `:supersededBy` triple pointing from the old section to the new one, asserted in the
new graph (where the correction becomes known), never by editing the original graph. This is more
precise than this section's earlier framing of a graph-level `supersededBy` metadata pointer:
`schema/tbox.ttl` gives `SECFilingSection` its own `supersededBy` object property, so supersession
is tracked at the individual level, and no separate metadata graph is needed at all. Both versions
stay queryable; only the "current best understanding" view filters to the latest non-superseded
section. Worked example (JNJ's Item 1A, original + restated) in `schema/instances.trig`.

> **As-of reads (T-101).** The graph date is the ingest batch, not the usable date. `ScoreSnapshot.availableAt` is the look-ahead guard: as-of-D queries over `ScoreSnapshot`s filter `availableAt <= D`, never `eventTime` or `timestamp`. `SectorAggregateSnapshot` and `AttractivenessSnapshot` are same-cycle derived outputs with no separate clock: they are usable from the date of their `timestamp`/`computedAt`.
>
> **Run provenance (T-106, D7).** Upstream rows (`ScoreSnapshot`, `SectorAggregateSnapshot`, `Veto`, `PortfolioPosition`, `DataQualityIssue`, and since T-107/T-108 `AssetCoOccurrence`, `BenchmarkObservation`) may carry the run that wrote them as plain optional properties: `runId`, `runAsOf`, `codeVersion`, `engineVersion` (no `rdfs:domain`, like `provenanceId`; SHACL scopes them per class). There is no `Run` class and the run log (params, dirty-tree reason, `schema_version`) stays upstream, reachable through `runId` and the `v_*_run` views. Per-score-type extras `forensic_flags_json`, `prompt_hash` and `correction_rule` are deliberately not projected (see `schema/README.md`).
>
> - **Stints and valid-time records record the opener.** A `Veto` (stint) and a `PortfolioPosition` (valid-time) are appended to by later cycles (`lastSeenOn`, `clearedOn`/`validTo`, often from another run). On them the four properties record only the run that **opened** the record (`raisedOn`/`validFrom`); later cycles must not re-emit them (that would give two values, violating `maxCount 1` and the functional property, which OWL2-RL reads as an inconsistency) and the closing run is not recorded. Immutable observations (`ScoreSnapshot`, `SectorAggregateSnapshot`) and `DataQualityIssue` rows are written once, so no such rule is needed.
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
  revision (`06-ontology-definition.md` §1.2), the ontology's own 27 domain classes also have
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
