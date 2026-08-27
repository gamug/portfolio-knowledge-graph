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
| `urn:graph:ingest:{agent}:{date}` | One graph per (agent, day) ingestion batch — that day's `ScoreSnapshot`s and `RiskEvent`s from `SEMANTIC`/`QUANTITATIVE`/`TECHNICAL` agents (v1's fast cycle, §2B) | **Append-only.** Never edited after creation — this is what makes it a faithful transaction-time record. |
| `urn:graph:ingest:SECTOR:{date}` | One graph per Sector Agent daily run — `SectorAggregateSnapshot`s and per-asset `SectorRelativeMomentum` `ScoreSnapshot`s (added 2026-08-13, see spec) | **Append-only**, same convention as the other per-agent ingest graphs. |
| `urn:graph:ingest:FUNDAMENTAL:{year}-Q{n}` | One graph per quarterly Fundamental Agent run — new `UniverseMembership` records, fundamental `ScoreSnapshot`s (v1's slow cycle, §2A) | Append-only. |
| `urn:graph:ingest:ORCHESTRATOR:{date}` | The Orchestrator's own decisions — `Veto` individuals and any `RiskEvent`s it directly produced; also `AttractivenessSnapshot` individuals (added 2026-08-13) — the Orchestrator's ranking output, alongside its veto output | Append-only. |
| `urn:graph:ingest:EDGAR:{date-or-quarter}` | `SECFiling`/`SECFilingSection` individuals from the EDGAR batch pipeline (roadmap step 4), including restated sections | Append-only — see the restatement pattern below. |
| `urn:graph:derived:entity-resolution:{date}` | `sharedExecutiveWith` and other entity-resolution-service output (roadmap step 7) | Append-only; kept separate from the EDGAR graphs it draws on since it's a different service's output. |
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

## Scale estimate

Back-of-envelope for a full 2022–present backfill (~4 years, ~1,008 trading days), 500 `Asset`s:

| Source | Rough volume | Why |
|---|---|---|
| `ScoreSnapshot` (QUANTITATIVE + TECHNICAL) | ~2.0M individuals | Daily metrics × 500 assets × ~1,000 trading days × 2 agents × ~2 metrics each. |
| `ScoreSnapshot` (SEMANTIC) | ~200K individuals | News-driven, not every company every day — roughly matches the density already observed in the existing `news-crawler` corpus (2,289 articles from just 8 tickers in a sample window) scaled to 500 tickers over 4 years. |
| `ScoreSnapshot` (FUNDAMENTAL) | ~25K individuals | Quarterly × 500 assets × ~16 quarters × ~3 metrics. |
| `NewsArticle` | ~100K–150K individuals | Scaling the existing `news-crawler` corpus density (§ above) to the full S&P 500. |
| `SECFilingSection` | ~30K individuals | 500 companies × ~20 filings (10-K/10-Q/DEF 14A) over 4 years × ~3 sections each. |
| `RiskEvent`, `Veto` | Low tens of thousands | Only fires when a threshold is actually crossed — a small fraction of `ScoreSnapshot` volume. |
| `SectorAggregateSnapshot` + `SectorRelativeMomentum` + `AttractivenessSnapshot` (added 2026-08-13) | Low tens of millions combined at full backfill scale | ~11 sectors × 500 assets × ~1,000 trading days — comparable order of magnitude to the existing daily `ScoreSnapshot` volume above; does not change this table's headline order-of-magnitude conclusion below, it's absorbed within it. |

**Total: on the order of 15–20 million triples** over the full historical backfill, dominated by
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
lives in a separate columnar store (Parquet/SQLite/Postgres) that the Quantitative/Technical agents
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
  revision (`06-ontology-definition.md` §1.2), the ontology's own 24 domain classes also have
  `subClassOf` structure to reason over — e.g. `?x a :ObservationSnapshot` now correctly returns
  every `ScoreSnapshot`, `SectorAggregateSnapshot`, and `AttractivenessSnapshot` individual without
  the query author enumerating all three types by hand. Before that revision this setting only ever
  did work for GICS, since the 24 domain classes had no `subClassOf` edges among themselves at all —
  worth noting since it means this section's recommendation is now doing more than it used to for
  the same reasoning cost.
- **Leave off:** full OWL DL / property-chain reasoning. In particular, `sharedExecutiveWith`
  (used by `VETO_RED_01`'s contagion check) is deliberately **not** something the reasoner
  computes automatically via property chains — it's written explicitly by the entity-resolution
  service (roadmap step 7) as application logic, not inferred transitively across the graph.
  Materializing deep inference chains over tens of millions of `ScoreSnapshot` triples would blow
  up both load time and result-set size for a benefit that, for this rule specifically, needs
  controlled/auditable logic anyway — an inferred edge is harder to explain in an audit trail than
  one an explicit service wrote and can justify.

---

*Diagram for this document (Exhibit 2) is in the companion Artifact: the named-graph topology map
and an example bounded cross-graph query path.*
