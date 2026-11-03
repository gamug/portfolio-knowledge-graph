# Ontology Definition — Portfolio Knowledge Graph (v2)

**Implementation:** [`schema/`](../schema/) — the formal OWL/SHACL/TriG implementation of
everything described below, split into `tbox.ttl` (classes/properties, **51 classes total** as of
this revision — 38 mutually-disjoint leaf/domain classes plus a 13-class `rdfs:subClassOf`
taxonomic backbone, see §1.2), `shapes.ttl` (SHACL, 31 shapes), `reference.ttl` (GICS taxonomy +
asset master data + the new `MetricType` controlled vocabulary, §1.9), `rules.ttl` (the ten active
selection rules, the five GUARD protection rules, and the seven original ones as trees), and
`instances.trig` (a worked, multi-graph, multi-asset dataset). Parsed clean
with `rdflib` and SHACL-validated with `pyshacl` (**conforms: True**); the veto rule trees were
independently re-executed in Python against the instance data and reproduced the expected firings
exactly (see `schema/README.md`). This document is the prose walkthrough; `schema/` is the
executable artifact a thesis appendix or a real GraphDB/Fuseki load would use. `schema/README.md`
documents the file-to-named-graph map and the modeling refinements only discovered while
implementing (two new `RuleClause` leaf types, a raw-vs-normalized comparison convention, and a
shared-property domain-collision fix) — summarized in §1.5 and §1.8 below.

**Revision note (2026-08-23).** This pass replaces the previously flat, disjointness-only class
inventory with an explicit taxonomy, and closes a second, smaller gap (untyped `metricType`
strings) the same way GICS sectors were already handled. Neither change renames, removes, or
redefines any existing class, property, or SHACL shape — the prior design's entity/relationship
modeling, temporal handling, and rule-as-data pattern were reviewed and found sound; only the
*taxonomic structure* (or lack of it) among the 25 domain classes needed fixing. See §1.2 and §1.9.

**Store target:** RDF triple/quad store (GraphDB or Apache Jena Fuseki). This is the single
decision that shapes everything in this document — it means the ontology has to be formal OWL
(classes with IRIs, typed properties with domain/range) rather than a property-graph node/edge
sketch, which is a real step up in rigor from `Avance arquitectura del sistema.docx` ("v1" below).

This is the core deliverable of the four (ontology / topology / agents / NLP) — get this wrong and
everything downstream inherits the mistake, so every design choice below is justified against
either a specific v1 section or a specific gap from `critique-and-evolution.md` ("critique #N").

---

## 1.1 Namespace & IRI strategy

Base IRI: `https://thesis.local/kg/portfolio#` — a placeholder, swappable for a real
dereferenceable namespace at deployment time; nothing in the design *depends* on it resolving.
Every class/property below lives under this single namespace (prefix `:`), which keeps the
ontology self-contained and avoids a dependency on any external ontology resolving at parse time.

**FIBO alignment (Phase 1, 2026-11-03; T-210).** FIBO is a **reference vocabulary, not a
dependency** (the FIBO integration brief §1). Our terms stay in
`https://thesis.local/kg/portfolio#` (constitution Project structure #8, SPEC NR-004); there is no
`owl:imports`, `owl:equivalentClass` or `rdfs:subClassOf` to FIBO, and FIBO's axioms are never used
for reasoning. A term gets `rdfs:seeAlso` only when FIBO's definition is true of **every** instance
of ours — the same meaning, or a broader FIBO term. Where FIBO's definition would misstate ours
there is no link, and our own definition states the difference.

The six Phase 1 links live in `schema/tbox.ttl` and in `schema/fibo_terms.csv` (the single source
for them and for the glossary slice); they were empty in Phase 1 and are filled in Phase 2. Here
`fibo:` stands for `https://spec.edmcouncil.org/fibo/ontology/`:

| Our term | FIBO term (`fibo:` + path) | Fit | Link | What our own definition must say |
|---|---|---|---|---|
| `:Portfolio` | `FND/OwnershipAndControl/Ownership/Portfolio` | same | yes | |
| `:PortfolioPosition` | `FBC/ProductsAndServices/FinancialProductsAndServices/Position` | same | yes | It carries a weight and a validity interval `[validFrom, validTo)`. |
| `:tickerSymbol` (property) | `SEC/Securities/SecuritiesIdentification/TickerSymbol` | same | yes | FIBO defines a ticker as reassignable; see the `:Asset` note below. |
| `:Sector` | `SEC/Securities/SecuritiesClassification/GlobalIndustryClassificationStandardsClassifier` | same | yes | Our 11 sectors are GICS's 11. |
| `:Industry` | `FND/Arrangements/ClassificationSchemes/IndustrySectorClassifier` | broader | yes | GICS-based industry groups. GICS has 25; `reference.ttl` has 26 because it splits the Energy group into its two GICS industries, so the link is to the generic classifier, not the GICS one. |
| `:SECFiling` | `FND/Arrangements/Reporting/Report` | broader | yes | It lists the forms it covers (10-K, 10-Q, 8-K, DEF 14A). FIBO has no filing class. |
| `:SP500Index` (the `:Universe` individual the ETL emits) | `IND/MarketIndices/BasketIndices/EquityIndex` | same | yes (ETL output) | |
| `:Asset` | none (nearest: `ListedShare`, `PubliclyHeldCompany`) | differs | **no** | See the note below. The broken `.../LegalPersons/LegalPerson` link is removed and not replaced. |
| `:Universe` | none (nearest: `EquityIndex`, defined as a benchmark) | differs | no | The pool the system selects from: the S&P 500 members valid on each date. It is not the yardstick that performance is measured against. |
| `:UniverseMembership` | none (nearest: `FND/DatesAndTimes/FinancialDates/DatedCollectionConstituent`, one date) | differs | no | Membership over an interval `[validFrom, validTo)`. With no `validTo`, it is still current. |
| `:PriceObservation` | none (nearest: `ClosingPrice`, `AdjustedClosingPrice`) | differs | no | See the note below. |
| `:Executive` | none (nearest: `CorporateOfficer`, `BoardMember`) | differs | no | A director or an officer named in a proxy statement (DEF 14A). FIBO's `Executive` manages the organization, which excludes non-executive directors. |
| The 17 explanation-layer classes | none | ours | no | Their own definitions. |

The 17 explanation-layer classes are `ScoreSnapshot`, `SectorAggregateSnapshot`,
`AttractivenessSnapshot`, `AssetCoOccurrence`, `BenchmarkObservation`, `NewsArticle`,
`SECFilingSection`, `DataQualityIssue`, `RiskEvent`, `Veto`, `RuleDefinition`, `RuleClause`,
`ThresholdComparison`, `CategoricalComparison`, `GraphPredicate`, `AttractivenessWeightScheme` and
`WeightComponent`.

**Why `:Asset` has no FIBO link.** `:Asset` is one node per ticker symbol
(`src/etl/asset_master.py`), not one per company. A company with several share classes in the
index has one node per class (GOOGL/GOOG, FOXA/FOX, NWSA/NWS); upstream, 503 assets map to 500
CIKs. A ticker reused by another company is one node (Q, CEG, DELL). FIBO's `LegalPerson` is a
company, so the old link misstated every multi-class company and every reused ticker. There is no
replacement: `ListedShare` is one listing and `PubliclyHeldCompany` is the issuer, neither of which
is our per-ticker node.

**Why `:PriceObservation` has no FIBO link.** It is a derived daily summary (close, return,
volatility, ATR, momentum), not a traded price. Its close is split-adjusted as of download and not
adjusted for dividends (upstream `src/pricing_agent/integrity.py`), so its return is price-only.
FIBO's adjusted close also includes dividends; upstream's `quant` computes dividend-inclusive
returns separately (upstream SPEC FR-009).

**Why FIBO is not imported.** The release has 220 modules and 134,946 statements, with 2,240 named
classes against our 51. 71% of its statements describe its 11,763 named individuals (exchanges,
market codes and the like). The evaluation load of 2026-10-27, with the `rdfsplus-optimized`
ruleset, produced about 178,000 inferred statements and an unscoped "list all classes" query
returned 2,280 classes; the 2,280 figure was not re-measured. P1 removed that load and measured the
cost on 2026-11-02: before dropping the FIBO graph the repository held 137,496
explicit and 180,948 inferred statements across 19 graphs, with 134,946 statements in the FIBO
graph; after dropping only that graph it held 2,550 explicit and 908 inferred. The difference is
134,946 explicit (exactly the graph's size) and **180,040 inferred**, which confirms the order of
magnitude of the 2026-10-27 evaluation. The remaining 2,550 explicit statements are the other 18
graphs, unchanged. The full release is therefore never kept in the `portfolio` repository; the zip
stays the source and a browsing copy would need a separate repository with no reasoning.

**Release and licence.** The pinned release is FIBO 2026Q2, `prod.ttl.zip` (220 Turtle modules,
134,946 statements), sha256
`7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579`; it is not committed. It is
MIT-licensed: copyright EDM Association dba EDM Council, Inc. and Object Management Group, as the
release's `AboutFIBOProd` `dct:license` states, verbatim (one whitespace-only line in the source is
rendered blank):

```text
Copyright (c) 2018-2026 EDM Association dba EDM Council, Inc.
Copyright (c) 2018-2025 Object Management Group, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the 'Software'), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

See https://opensource.org/licenses/MIT.
```

**FIBO Phase 2: the glossary slice (T-211).** The slice is built and committed as
`schema/fibo.ttl`; `schema/fibo_terms.csv` now holds the 25 seeds of brief §4.1 with their reviewed
Spanish columns. The slice has 54 entries (25 seeds plus 29 ancestors the release describes) and
223 English statements: 54 `rdfs:label`, 54 `skos:definition`, 63 `rdfs:subClassOf` (16 of them to
parents outside the release, kept only as the objects of their edges), 37 explanatory notes, 7
abbreviations, 6 synonyms and 2 usage notes. It copies no `rdf:type`, so no FIBO term is an
`owl:Class` in this repository (NR-004 as written); a `?c a owl:Class` query cannot return one. The
Spanish layer adds 50 statements (25 labels plus 25 definitions) and the header adds 4: the
release (`owl:versionInfo "FIBO 2026Q2"`), the zip's sha256, the `dct:license` text copied verbatim
from `AboutFIBOProd`, and a comment saying the `@es` text is the thesis authors' translation.

Rebuild it with:

```bash
uv run python cli/build_fibo_slice.py --zip /path/to/prod.ttl.zip \
    --terms schema/fibo_terms.csv --out schema/fibo.ttl
```

The builder refuses any zip whose sha256 is not
`7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579`, and the same zip and terms
file give a byte-identical file. It keeps only labels, definitions, named parents and the
`cmns-av` notes, copies every literal with its language tag exactly as in the release (FIBO's own
text is untagged or `@en`), and adds `rdfs:label`@es and `skos:definition`@es for a row only when
both Spanish columns are filled. All 25 rows are filled in this revision; the thesis authors
approve them by merging the change. The slice loads into `urn:graph:reference:fibo` after
`reference.ttl` (S1), and is append-only in effect: it is rebuilt only for a new FIBO release.

For a linked row, the Spanish definition in `fibo.ttl` is FIBO's meaning, never ours; our own
Spanish definitions live in `tbox.ttl` (S2), where the six "differs" classes state why FIBO does
not define every instance of ours. The 27 pre-existing leaf classes now carry one `@es` label and
one `@es` definition each; the 11 v18 classes' handoff §6.2 texts are unchanged. Those 54 new
triples take the FR-001 bundle to **4236 quads; conforms: True**; `fibo.ttl` is a separate
277-statement graph. `:SP500Index` gets its `rdfs:seeAlso` in the ETL output, where the universe
individual is emitted (S3), not in `urn:graph:tbox`.

**Lookup queries for the reports agent (brief Appendix A, unchanged).** `A1` explains one of our
terms from `urn:graph:tbox` and, when it has an `rdfs:seeAlso` into FIBO, adds the standard term's
English definition and the authors' `@es` text. `A2` looks up a general finance term by its Spanish
label in `urn:graph:reference:fibo`. The FIBO text is the untagged or `@en` literal; `@es` is
always the authors' translation, never FIBO's words.

```sparql
PREFIX :     <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?labelEs ?defEs ?fibo ?fiboLabelEs ?fiboDefEs ?fiboDef
WHERE {
  GRAPH <urn:graph:tbox> {
    :Portfolio rdfs:label ?labelEs ; skos:definition ?defEs .
    FILTER (lang(?labelEs) = "es" && lang(?defEs) = "es")
  }
  OPTIONAL {
    GRAPH <urn:graph:tbox> { :Portfolio rdfs:seeAlso ?fibo . }
    GRAPH <urn:graph:reference:fibo> {
      ?fibo skos:definition ?fiboDef .
      FILTER (!langMatches(lang(?fiboDef), "es"))
      OPTIONAL { ?fibo rdfs:label      ?fiboLabelEs FILTER (lang(?fiboLabelEs) = "es") }
      OPTIONAL { ?fibo skos:definition ?fiboDefEs   FILTER (lang(?fiboDefEs)   = "es") }
    }
  }
}
```

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) = "volatilidad")
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}
```

The executable forms of these two lookups, together with the backtest battery and the limits of
what the graph can answer, live in
[`reports-agent-query-catalog.md`](reports-agent-query-catalog.md);
`tests/test_query_catalog.py` runs every query there against the schema bundle and the synthetic
two-window backtest.

## 1.2 Class taxonomy

Replaces the earlier flat, disjointness-only inventory. The 38 leaf/domain classes are organized
under 6 broad categories and, in 4 cases, an intervening mid-level category — placement was decided
by **shared property shape**, a structural criterion, not by theme (e.g. `AttractivenessSnapshot`
sits under `Observation Snapshot`, not next to `Veto`, because it shares `ScoreSnapshot`'s
immutable/timestamped/one-per-cycle shape, even though thematically it's also "an orchestrator
decision output"). Depth is kept shallow (max 4 levels) to match a 38-leaf ontology.

```
Portfolio Knowledge Graph
├── Domain Entity
│   ├── Asset
│   ├── Executive
│   ├── Classification Concept
│   │   ├── Sector
│   │   └── Industry
│   └── Collection
│       ├── Universe
│       ├── Portfolio
│       └── StrategyBook              (T-206)
├── Temporal Relation
│   ├── UniverseMembership
│   ├── PortfolioPosition
│   ├── TickerHistory                 (T-206)
│   └── BookRebalance                 (T-206)
├── Observation
│   ├── Observation Snapshot
│   │   ├── ScoreSnapshot
│   │   ├── SectorAggregateSnapshot   (§1.8)
│   │   └── AttractivenessSnapshot    (§1.8)
│   ├── PriceObservation
│   ├── AssetCoOccurrence             (T-107)
│   ├── BenchmarkObservation          (T-108)
│   ├── OrchestratorRun               (T-206)
│   ├── OrchestratorStep              (T-206)
│   ├── GuardAlert                    (T-206)
│   ├── BookWeightDaily               (T-206)
│   ├── BookDailyPerformance          (T-206)
│   ├── PortfolioPeriodSummary        (T-206)
│   └── BacktestTest                  (T-206)
├── Evidence
│   ├── Source Document
│   │   └── SECFiling
│   └── Evidence Source
│       ├── NewsArticle
│       ├── SECFilingSection
│       └── DataQualityIssue
├── Risk And Decision
│   ├── RiskEvent
│   ├── Veto
│   └── GuardAction                   (T-206)
└── Rule System
    ├── RuleDefinition
    ├── RuleClause
    ├── Rule Operand
    │   ├── ThresholdComparison
    │   ├── CategoricalComparison
    │   └── GraphPredicate
    └── Attractiveness Scheme        (§1.8)
        ├── AttractivenessWeightScheme
        └── WeightComponent
```

| Class | Category | Answers | One-line definition |
|---|---|---|---|
| `Asset` | Domain Entity | v1 §2A/§3A | An S&P 500 constituent tracked by the system. |
| `Executive` | Domain Entity | v1 §4 | Extracted from DEF 14A; `canonicalId` populated once entity resolution (roadmap step 7) exists. |
| `Sector`, `Industry` | Domain Entity → Classification Concept | critique #3 | GICS-aligned SKOS concepts; `Industry` rolls up to exactly one `Sector`. **New in v2** — v1 had no sector layer at all despite it being in the thesis's own stated scope. |
| `Universe`, `Portfolio` | Domain Entity → Collection | v1 §2A, critique #2 | Named pools — a candidate watchlist and a holding book (the live book, or since T-108 an upstream benchmark book, told apart by `portfolioKind`), respectively. `Portfolio` is **new in v2** (v1 specified exclusion only, no inclusion/holding model). |
| `UniverseMembership`, `PortfolioPosition` | Temporal Relation | v1 §2A formalized, critique #2 | Reified n-ary relations carrying `validFrom`/`validTo` — see §1.4. |
| `ScoreSnapshot`, `SectorAggregateSnapshot`, `AttractivenessSnapshot` | Observation → Observation Snapshot | v1 §3A; §1.8 | Immutable, timestamped metrics sharing one property shape (`metricType`/`agentOrigin`/`timestamp`/`normalizedScore`). |
| `PriceObservation` | Observation | scope requirement (daily pricing) | **New in v2, derived-summary only** — see the topology document for why raw OHLCV ticks do *not* belong in the triple store. |
| `AssetCoOccurrence` | Observation | T-107 (upstream D10) | A method-versioned, weighted *candidate* link between two assets from news co-occurrence (`coOccurrenceKind`/`Method`/`Weight`/`ComputedOn`, exactly two `coOccurrenceAsset`). Not a verified directorship; `sharedExecutiveWith` stays reserved for verified edges. |
| `BenchmarkObservation` | Observation | T-108 (upstream D11) | One finished number upstream's `quant` computed about a benchmark `Portfolio` (or, for the performance numbers upstream measured on its `live_book` snapshot, about the LIVE `Portfolio`; the snapshot's holdings are not re-projected, T-109): a performance metric (`v_quant_benchmark_performance`) or a per-asset active weight against the live book (`v_quant_vs_live`, with `quantAsset`). Projected as handed over, never computed here; returns, μ and Σ are not projected. `Portfolio` also gains required `portfolioKind` (`LIVE`/`BENCHMARK`, set by source view) and optional `benchmarkObjective` (upstream's `objective`) and `benchmarkKind` (its `kind`, never `live_book`); `quantBenchmark` names the reference index of a performance number; benchmark weights are ordinary `PortfolioPosition`s. |
| `SECFiling` | Evidence → Source Document | v1 §2B | One document filed with the SEC through EDGAR (10-K/10-Q/8-K/DEF 14A) for one `Asset`. |
| `NewsArticle`, `SECFilingSection` | Evidence → Evidence Source | v1 §3B | Evidence leaves cited by `backedBy` (a restated section is replaced by a new one through `:supersededBy`, `07` "Restatements and re-runs"); cross-referenced to `portfolio-data-mining`'s news pipeline (`news_collector`/`extractor`, `urls.db`) via `provenanceId` (see §1.6 and `09-nlp-finbert-architecture.md`). |
| `DataQualityIssue` | Evidence → Evidence Source | T-104 (upstream D5) | One Ring-1 `DQ_*` gate firing (upstream `data_quality_issue` row): `dqGateCode`, `dqSeverity`, `quarantined`, `dqRaisedOn`, optional `dqIssueOfFiling`/`dqMetricName`/`gatedValue`/`provenanceId`. HARD ones back the `DATA_QUALITY` veto via a `RiskEvent`. |
| `RiskEvent`, `Veto` | Risk And Decision | v1 §3B/§4 | A flagged event, SHACL-required to carry evidence (closes critique #5); and the orchestrator's per-cycle exclusion decision. |
| `RuleDefinition`, `RuleClause` | Rule System | v1 §4, critique #1 & #6 | The rule catalog's tree structure (selection and GUARD rules), versioned as graph data — see §1.5. |
| `ThresholdComparison`, `CategoricalComparison`, `GraphPredicate` | Rule System → Rule Operand | v1 §4, critique #1 | The three leaf-operand kinds a `RuleClause` can compare — see §1.5. |
| `AttractivenessWeightScheme`, `WeightComponent` | Rule System → Attractiveness Scheme | critique #2/#3, §1.8 | Per-metric weights feeding the attractiveness score: per run for upstream schemes (one `cycle_run`, dated by `cycleDate`, never closed; T-121), versioned (`validFrom`/`validTo`) for the design-history `WeightScheme_v1`. |
| `TickerHistory` | Temporal Relation | T-206 (`v_ticker_history`, m016) | A point-in-time symbol for one CIK line over the INCLUSIVE interval `[validFrom, validTo]`; `validTo` absent = current symbol. Optional link to the canonical `Asset`. |
| `OrchestratorRun` | Observation | T-206 (`v_orchestrator_run`, m015) | One Orchestrator run (pipeline or single command): handle, `as_of`, kind, status, surface, settings. Immutable process record, not a metric snapshot. |
| `OrchestratorStep` | Observation | T-206 (`v_orchestrator_step`, m015) | One step of an `OrchestratorRun`, keyed by `(orchestrator_run_id, ordinal)`, with status, times, exit code and its own run-log id. |
| `StrategyBook` | Domain Entity → Collection | T-206 (`v_book`, m018) | One experimental arm of a backtest run (`MARKOWITZ_BASE`, `TOPN_MV_NOGUARD`, `TOPN_MV_GUARD_NO_NLP`, `TOPN_MV_GUARD`); a named pool of holdings. |
| `BookRebalance` | Temporal Relation | T-206 (`v_book_rebalance`, m018) | A scheduled 21-session rebalance: book × decision/execution dates × upstream quant-portfolio/cycle-run/risk-model ids (literals). |
| `GuardAlert` | Observation | T-206 (`v_guard_alert`, m018) | A GUARD layer's daily alert, linked to its GUARD rule; value optional on layer 1, asset optional on layers 3–4. |
| `GuardAction` | Risk And Decision | T-206 (`v_guard_action`, m018) | The effect of a `GuardAlert` on one book for the next session (`APPLIED`, `ARM_DISABLED`, `NOT_HELD`, `SUPERSEDED`); weights optional on layer 1. |
| `BookWeightDaily` | Observation | T-206 (`v_book_weight_daily`, m018) | One holding's weight in a book on a date; a `CASH` row has no asset link, and the target weights exist only on decision/execution dates. |
| `BookDailyPerformance` | Observation | T-206 (`v_book_daily_performance`, m018) | A book's portfolio-level daily series (gross/net return, turnover, cost, NAV, drawdown, cash weight, equity count, benchmark return). |
| `PortfolioPeriodSummary` | Observation | T-206 (`v_portfolio_period_summary`, m018) | Consolidated statistics of one book over one segment (`P1`, `P2`, `P2a`, `P2b`, `P3`). |
| `BacktestTest` | Observation | T-206 (`v_backtest_test`, m018) | A paired hypothesis test between two arms in one segment (`memmel_jk`, `ledoit_wolf`, `hac_mean_diff`): statistic, p-value, observations. |

### 1.2.1 Taxonomic backbone, formally

`ObservationSnapshot`, `EvidenceSource`, and `RuleOperand` existed already, but as `owl:unionOf`
domain-widening helpers — explicitly excluded from `AllDisjointClasses` and never used as an
individual's `rdf:type` (the pre-revision design's own documented convention). They're upgraded
below to ordinary superclasses under the **same IRIs**: RDFS domain entailment for their reused
properties is preserved identically (every individual typed e.g. `:ScoreSnapshot` is still entailed
a valid subject for `metricType`/`agentOrigin`/`timestamp`/`normalizedScore`), and individuals can
now additionally be queried by the shared type directly (`?x a :ObservationSnapshot`), which the
excluded-union design could never support. Everything else here is new.

```turtle
@prefix :     <https://thesis.local/kg/portfolio#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .

### Broad categories
:DomainEntity     a owl:Class ; rdfs:label "Domain Entity"@en .
:TemporalRelation  a owl:Class ; rdfs:label "Temporal Relation"@en .
:Observation        a owl:Class ; rdfs:label "Observation"@en .
:Evidence            a owl:Class ; rdfs:label "Evidence"@en .
:RiskAndDecision      a owl:Class ; rdfs:label "Risk and Decision"@en .
:RuleSystem            a owl:Class ; rdfs:label "Rule System"@en .

### Mid-level categories
:ClassificationConcept a owl:Class ; rdfs:subClassOf :DomainEntity ;
    rdfs:label "Classification Concept"@en ;
    rdfs:comment "GICS reference concepts. Their internal Sector/Industry hierarchy is a parallel skos:broader tree over skos:Concept individuals in reference.ttl, not further rdfs:subClassOf structure — deliberately kept separate, since SKOS and OWL subsumption are different mechanisms answering different questions." .
:Collection a owl:Class ; rdfs:subClassOf :DomainEntity ; rdfs:label "Collection"@en .
:SourceDocument a owl:Class ; rdfs:subClassOf :Evidence ; rdfs:label "Source Document"@en .
:AttractivenessScheme a owl:Class ; rdfs:subClassOf :RuleSystem ; rdfs:label "Attractiveness Scheme"@en .

### Upgraded former union classes (same IRIs, see note above)
:ObservationSnapshot a owl:Class ; rdfs:subClassOf :Observation ;
    rdfs:label "Observation Snapshot"@en .
:EvidenceSource a owl:Class ; rdfs:subClassOf :Evidence ;
    rdfs:label "Evidence Source"@en .
:RuleOperand a owl:Class ; rdfs:subClassOf :RuleSystem ;
    rdfs:label "Rule Operand"@en .

### The 25 leaf/domain classes — additive subClassOf edges only. No class's own declaration,
### properties, or membership in AllDisjointClasses changes; subClassOf (vertical) and
### AllDisjointClasses (horizontal, sibling-only) are orthogonal OWL constructs.
:Asset     rdfs:subClassOf :DomainEntity .
:Executive rdfs:subClassOf :DomainEntity .
:Sector    rdfs:subClassOf :ClassificationConcept .
:Industry  rdfs:subClassOf :ClassificationConcept .
:Universe  rdfs:subClassOf :Collection .
:Portfolio rdfs:subClassOf :Collection .

:UniverseMembership rdfs:subClassOf :TemporalRelation .
:PortfolioPosition  rdfs:subClassOf :TemporalRelation .

:ScoreSnapshot           rdfs:subClassOf :ObservationSnapshot .
:SectorAggregateSnapshot rdfs:subClassOf :ObservationSnapshot .
:AttractivenessSnapshot  rdfs:subClassOf :ObservationSnapshot .
:PriceObservation        rdfs:subClassOf :Observation .

:SECFiling        rdfs:subClassOf :SourceDocument .
:NewsArticle       rdfs:subClassOf :EvidenceSource .
:SECFilingSection  rdfs:subClassOf :EvidenceSource .
:DataQualityIssue  rdfs:subClassOf :EvidenceSource .

:RiskEvent rdfs:subClassOf :RiskAndDecision .
:Veto      rdfs:subClassOf :RiskAndDecision .

:RuleDefinition          rdfs:subClassOf :RuleSystem .
:RuleClause              rdfs:subClassOf :RuleSystem .
:ThresholdComparison     rdfs:subClassOf :RuleOperand .
:CategoricalComparison   rdfs:subClassOf :RuleOperand .
:GraphPredicate          rdfs:subClassOf :RuleOperand .
:AttractivenessWeightScheme rdfs:subClassOf :AttractivenessScheme .
:WeightComponent             rdfs:subClassOf :AttractivenessScheme .
```

**Reasoning payoff.** `07-ontology-topology.md`'s Reasoning Profile already turns on
`rdfs:subClassOf` transitivity, previously to serve the GICS taxonomy only. This backbone means
that same setting now also makes `?x a :ObservationSnapshot`, `?x a :Evidence`, `?x a :RuleOperand`,
etc. valid, reasoner-answered queries over the ontology's own domain classes — impossible before
this revision, since there was no `subClassOf` structure among the 25 domain classes for the
reasoner to traverse.

## 1.3 Object & datatype properties

The full domain/range table is the `.ttl` file itself (§2–3 of that file); the properties worth
calling out here are the ones that encode a design decision, not just a field:

- **`backedBy`** (`RiskEvent → NewsArticle | SECFilingSection | DataQualityIssue`) has `sh:minCount 1` in the SHACL
  shapes (§1.6) — a `RiskEvent` cannot exist in the store without evidence. This turns critique
  gap #5 ("no null/missing-data policy") from a prose recommendation into an enforced constraint.
- **`appliesRule`** vs **`primaryRule`** — both present on `Veto`, matching v1's own distinction
  ("Mapeo de Activaciones Multiples", §4): the full trigger list plus a computed lowest-`priorityRank`
  primary reason for audit queries. Since T-187 one `ruleId` can have two `RuleDefinition` IRIs over time
  (`LIQUIDITY_DISTRESS`: stints raised before 2026-10-10 point at the old one, later ones at `_v11`), so a query by
  rule matches on `:ruleId` (`appliesRule/ruleId`), never on the rule's IRI.
- **`Veto` is a stint** (T-102, 2026-10-03): `raisedOn` (required), `clearedOn`, `lastSeenOn` are cycle
  dates mirroring upstream's `veto` rows; `vetoSeverity` (HARD | SOFT) is the per-stint severity. `lastSeenOn` and `expiresOn` (T-188) are both multi-valued, one value per cycle that saw the stint or per move upstream made, current = `MAX`. Four severity-like properties now coexist, deliberately: `severity` (`RiskEvent`, CRITICAL…LOW), `ruleSeverity` (`RuleDefinition`, the catalog default), `vetoSeverity` (`Veto`, per stint) and `dqSeverity` (`DataQualityIssue`, upstream's gate severity, unenumerated).
  Active at cutoff C iff `raisedOn <= C` and (no `clearedOn` or `clearedOn > C`); the T-1 lag is that
  predicate at read time (SPARQL in `schema/README.md`). Stints are closed by writing `clearedOn`.
- **`sharedExecutiveWith`** is declared `owl:SymmetricProperty` but is explicitly commented as
  *derived*, not hand-authored — it is written by the entity-resolution service (roadmap step 7),
  not by any ingestion agent directly. Since T-107 it is reserved for **verified** shared directorships;
  upstream's news co-occurrence candidates are `AssetCoOccurrence` individuals, never this property. Marking this in the ontology itself prevents a future
  implementer from accidentally treating it as raw input data.
- **Functional properties** (`owl:FunctionalProperty`) are used wherever v1's model implies
  exactly one value at a time — e.g. `classifiedAs` (one primary GICS industry), `primaryRule`
  (one primary reason) — versus **non-functional** where v1 implies a list, e.g. `appliesRule`
  (the full `reglas_gatillo: LIST<STRING>` from v1 §4) and `backedBy` (a `RiskEvent` can cite
  several evidence items).

## 1.4 Temporal modeling in RDF

This is the hardest part of the ontology and the one most likely to be gotten wrong silently, so
it gets its own careful treatment.

### Valid-time: n-ary relations, not raw qualified edges

v1's `(Asset)-[:PERTENECE_A_UNIVERSO{fecha_inicio,fecha_fin}]->(Universe)` pattern (§2A) is
already, implicitly, an **n-ary relation** — an edge that carries its own properties rather than
being a plain binary fact. Property graphs support that natively (edge properties); RDF triples do
not (a triple is strictly binary: subject–predicate–object, no properties *on* the edge itself).

The fix is the W3C-documented **n-ary relation pattern**: promote the relationship itself to a
first-class class with its own IRI. `UniverseMembership` and `PortfolioPosition` both follow this:

```turtle
:UM_Apple_2026Q3 a :UniverseMembership ;
    :membershipAsset :Apple ;
    :membershipUniverse :SP500Watchlist_2026Q3 ;
    :validFrom "2026-07-01"^^xsd:date .
    # validTo absent -> still active, mirrors v1's fecha_fin = NULL exactly
```

This is a direct, faithful translation of v1's own pattern — not a redesign — into RDF's
constraints. The `validFrom`/`validTo` properties are declared once and reused across every n-ary
relation class (`UniverseMembership`, `PortfolioPosition`, `RuleDefinition`), so a single SHACL
shape idiom (§1.6) covers temporal-field validation everywhere it's needed.

### Transaction-time: named graphs (closes critique #8)

v1 only had valid-time (*when a fact was true*), not transaction-time (*when the system learned
it*) — critique gap #8 flagged this as missing, relevant whenever a filing is later
restated/amended. RDF's native mechanism for this is **named graphs**: every ingested batch lands
in its own graph (`urn:graph:ingest:{agent_origin}:{date}`), so "what we believed as of ingestion
date X" falls out of *which graphs existed* at that point, with zero TBox changes. This is a
store-topology decision, not an ontology-class decision, so it's specified in full in
`07-ontology-topology.md` §1 — flagged here only so the two documents aren't read as unrelated to
each other.

## 1.5 Veto rule catalog as data, structurally unambiguous

This is the most direct payoff of the RDF/OWL choice, and it fixes critique gap #1 (the likely
correctness bug) and gap #6 (rules not versioned as graph data) in one design.

**The problem being fixed.** v1's catalog stored each rule as a string, e.g. for `VETO_COMP_01`:

> `ScoreFinanciero>Ufin_mod ∧ Sentiment<Usent_mercado ∨ ScoreTécnico>Utec_mod`

Standard operator precedence binds `∧` tighter than `∨`, giving `(Fin>U ∧ Sent<U) ∨ (Tec>U)` — a
high technical score *alone* can trigger a "Financial/Market" veto with zero financial signal
involved, almost certainly not the intended *confluent* semantics the rule's own name implies.

**The fix.** Instead of a string to be re-parsed (and mis-parsed) at evaluation time, each rule is
a tree of `RuleClause` individuals with explicit `operand1`/`operand2` edges. The tree *is* the
parse — there is no precedence to get wrong because there is no infix notation left to parse:

```turtle
:Rule_VETO_COMP_01 a :RuleDefinition ;
    :ruleId "VETO_COMP_01" ; :priorityRank 4 ; :validFrom "2026-01-01"^^xsd:date ;
    :hasClause :Clause_VC01_Root .

:Clause_VC01_Root a :RuleClause ;                 # AND( FinHigh, OR(SentLow, TecHigh) )
    :clauseType "AND" ; :operand1 :Cmp_FinHigh ; :operand2 :Clause_VC01_Inner .

:Clause_VC01_Inner a :RuleClause ;
    :clauseType "OR" ; :operand1 :Cmp_SentLow ; :operand2 :Cmp_TecHigh .

:Cmp_FinHigh a :ThresholdComparison ; :metricName "ScoreFinanciero" ; :operator ">" ; :thresholdValue 0.65 .
:Cmp_SentLow a :ThresholdComparison ; :metricName "Sentiment"       ; :operator "<" ; :thresholdValue -0.60 .
:Cmp_TecHigh a :ThresholdComparison ; :metricName "ScoreTecnico"    ; :operator ">" ; :thresholdValue 0.70 .
```

This also directly implements critique evolution layer **B4** (rules as versioned data): a
`RuleDefinition` has `validFrom`, so the Orchestrator agent (`08-agent-architecture.md`) reads its
active ruleset from the graph at evaluation time instead of from hardcoded Python — a past
decision can always be reproduced against the exact rule tree that was active when it was made,
which is the auditability guarantee v1 §3B was already aiming for elsewhere in the design.

**Addendum (T-103, 2026-10-03) — the active catalog is upstream's.** The seven tree rules this
section designs are superseded as the target by `portfolio-financial-analysis`'s six flat rules (nine since T-187, below)
(`LEVERAGE_EXTREME`, `NEGATIVE_FCF`, `LIQUIDITY_DISTRESS`, `PRICE_CRASH`, `EARNINGS_MISSING`,
`DATA_QUALITY`; `SPEC.md` §2.6 D4). They are `RuleDefinition`s whose `hasClause` is a single leaf —
the tree representation is unchanged, it just degenerates. The seven originals stay in
`rules.ttl` closed with `validTo 2026-10-02`. `:ruleSeverity` (HARD/SOFT) was added to
`RuleDefinition`; upstream's metric ids are `ThresholdComparison.metricName` values compared on the
raw value.

**Addendum (T-187, 2026-10-13) — nine rules.** Upstream's catalog now has nine (`VOLATILITY_SHOCK`, `CRASH_Z_SCORE` and
`BREAK_TREND_200` are new; `LIQUIDITY_DISTRESS` is redefined as a tree, the old definition kept closed with
`validTo 2026-10-10`; `SPEC.md` §2.6, seventh reply). `RuleDefinition` takes an optional `:penaltyPoints` (SOFT rules
only; a SOFT stint whose rule has none, a HARD rule's included, costs the run's `soft_veto_penalty`, the HARD-rule case assumed: T-191 ask (8)), the three new rules are `GraphPredicate` leaves evaluated upstream, and `LIQUIDITY_DISTRESS`'s sector exemption is
in its comment. Detail: `schema/README.md`.

**Addendum (T-206, 2026-11-01) — ten selection rules and five GUARD rules.** Contract v18's catalog
adds `UTILITY_CASH_COVERAGE` (HARD, `rule_input.utility_cash_coverage_3y < 0.05`, rank 10; applies
only to regulated utilities by the APP-00 profile) to the nine selection rules. The `LEVERAGE_EXTREME`,
`NEGATIVE_FCF` and `LIQUIDITY_DISTRESS` comments now record the APP-00 profile exemptions (financial
firms; regulated utilities; equity REITs); no threshold, severity or clause changed. The five GUARD
daily-protection rules (`L1_STOP_LOSS`, `L1_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD`) are
`RuleDefinition` individuals in a separate section, one `GraphPredicate` leaf each and `:guardLayer`
1..4; the frozen parameters and academic sources live only in `rdfs:comment`. **A GUARD rule is not a
veto rule:** it carries no `:ruleSeverity`, `:penaltyPoints` or `:priorityRank`, and `VetoShape`
refuses it as `:appliesRule`/`:primaryRule`. `RuleDefinitionShape` gets one `sh:or` branch for
`:category "GUARD"`, keeps the severity requirement for every other active rule and makes
`:priorityRank` mandatory for non-GUARD rules. `L2_NEWS` is disabled in the 2022–2025 backtest.
Detail: `schema/README.md` refinement 7 and §1.10.

**Addendum — implementation surfaced a gap in this section.** Encoding all 6 rules from v1's
catalog (`schema/rules.ttl`), not just `VETO_COMP_01`, revealed that `ThresholdComparison` alone
doesn't cover the catalog: `VETO_LEG_01`/`VETO_COMP_02` gate on `RiskEvent.category`/`severity`
(categorical, not numeric) and `VETO_RED_01` gates on a graph-structural predicate
(`HasSharedPrimaryVetoExecutive`), not a scalar comparison at all. `schema/tbox.ttl` adds two more
leaf types — `CategoricalComparison` and `GraphPredicate` — alongside `ThresholdComparison`, each
with its own SHACL shape, grouped under `:RuleOperand` (§1.2.1 — originally an `owl:unionOf` helper
excluded from typing, upgraded to an ordinary superclass in this revision) so
`operand1`/`operand2`/`hasClause` can point at any of them. The full 6-rule catalog, plus a 5-asset worked dataset
exercising all three leaf kinds, was independently re-evaluated in Python against the ontology's
own tree structure and reproduced the intended firings exactly — see `schema/README.md`.

## 1.6 SHACL shapes for data-quality enforcement

SHACL (Shapes Constraint Language) is RDF's declarative validator — the world-view equivalent of
a schema/type checker, but expressed as data rather than code. 31 shapes are defined
(`schema/shapes.ttl`; 10 before 2026-08-13, including `ThresholdComparisonShape`,
`CategoricalComparisonShape`, and `GraphPredicateShape` added during implementation to cover the
two new leaf types from the addendum above, plus four more added 2026-08-13 for the
attractiveness-ranking feature, see §1.8, plus `VetoShape` added 2026-10-03 for T-102 and `DataQualityIssueShape` for T-104; the 11 Contract v18 shapes were added by T-206, §1.10), each closing a specific gap:

| Shape | Constraint | Closes |
|---|---|---|
| `ScoreSnapshotShape` | `normalizedScore` ∈ `[0.0, 1.0]`, required unless `metricType` is `SectorRelativeMomentum`, `Sentiment`, or `ScoreFinanciero` (T-171: upstream rewrites a FUNDAMENTAL row's `normalized_score` in place every cycle, which a `ScoreSnapshot` individual can't carry without breaking the audit-trail principle); every `Sentiment` snapshot requires a `rawValue` ∈ `[-1.0, 1.0]` (T-081), every `SectorRelativeMomentum` snapshot a `rawValue` required (T-140) and ∈ `[-100.0, 100.0]` (T-155: TECHNICAL points, read verbatim), and every `ScoreFinanciero` snapshot a `rawValue` ∈ `[0.0, 100.0]` (T-171 requires it, T-177 bounds it; the reason is in §1.8); `rawValue` at most once (T-140; it is `owl:FunctionalProperty`); `agentOrigin` and `metricType` paired one-to-one: FUNDAMENTAL/`ScoreFinanciero`, VALORIZATION/`ScoreCuantitativo`, TECHNICAL/`ScoreTecnico`, SECTOR/`SectorRelativeMomentum`, SEMANTIC/`Sentiment` (T-140); `agentOrigin` ∈ the 5 known agents (`FUNDAMENTAL`, `SEMANTIC`, `VALORIZATION`, `TECHNICAL`, `SECTOR`); `metricType`/`timestamp`/`availableAt` required (T-101); `eventTime` optional and ≤ `availableAt`; optional `runId`/`runAsOf`/`codeVersion`/`engineVersion` (T-106; the same four are optional on `SectorAggregateSnapshotShape`, `VetoShape`, `PortfolioPositionShape` and `DataQualityIssueShape`); optional `scoreMethod`, at most one, open vocabulary (T-111; set on every SEMANTIC snapshot) | Prevents a malformed snapshot from silently entering veto evaluation. |
| `RiskEventShape` | `backedBy` `sh:minCount 1`; `severity`/`category` from closed vocabularies | Critique #5 (no null-handling policy) — evidence-free risk events are now a validation failure, not a silent gap. |
| `RuleDefinitionShape` | `validFrom` required; exactly one `hasClause`; `priorityRank` ∈ `[1,9]`; `penaltyPoints` at least 0, and none on a HARD rule; `ruleSeverity` ∈ `{HARD, SOFT}`, required unless the rule is closed with `validTo` (T-103) | Critique #6 — a rule can't be persisted without being properly temporal and ranked. |
| `RuleClauseShape` | `clauseType` ∈ `{AND, OR}`; both operands required | Structural half of the critique #1 fix — a clause literally cannot be built with a missing operand or an unrecognized operator. |
| `ThresholdComparisonShape` / `CategoricalComparisonShape` / `GraphPredicateShape` | Each leaf kind's required fields (`metricName`/`operator`/`thresholdValue`; `attributeName`/`expectedValue`; `predicateName`) | Completes the structural half of the critique #1 fix across all rule leaf kinds, not just numeric ones (the 7 original rules; upstream's six single-leaf rules reuse the same shapes, T-103). |
| `UniverseMembershipShape` | both endpoints + `validFrom` required; `validTo` optional, at most one, strictly after `validFrom` (exclusive end, T-100) | Keeps §1.4's n-ary relation pattern from degrading into a dangling record. |
| `AssetShape` | `tickerSymbol` required; `cikNumber` at most one, and required unless the asset has at least one `UniverseMembership` and every one has a `validTo` (T-100) | Upstream's `universe.db` has no CIK for a company that has left the index; inventing one would put false data in the graph, while a current member without a CIK still fails. |
| `DataQualityIssueShape` | gate code, severity, `quarantined`, `dqRaisedOn` and asset required; filing, metric name, `gatedValue`, `provenanceId` optional | Evidence for the `DATA_QUALITY` veto (T-104): an upstream `data_quality_issue` row, an `EvidenceSource` leaf. |
| `AssetCoOccurrenceShape` | exactly two assets; kind (`SHARED_EXECUTIVE_CANDIDATE`), method and weight required; `coOccurrenceComputedOn` and T-106 run provenance optional | Keeps news candidates carrying their method/weight (T-107) |
| `PortfolioShape` | name and `portfolioKind` ∈ {LIVE, BENCHMARK} required; `benchmarkObjective` and `benchmarkKind` optional (`benchmarkKind` may never be `live_book`, enforced by SHACL, T-109) | Lets benchmark books share `Portfolio` with the live book (T-108). |
| `BenchmarkObservationShape` (+ `QuantSubjectShape`) | portfolio, metric (free text) and value required; `quantPortfolio` must be a BENCHMARK or the LIVE book; `quantAsset`, `quantUnit`, `quantAsOf`, `quantBenchmark` and T-106 run provenance optional; a LIVE subject may only carry the four performance metrics | Carries upstream's finished quant numbers without interpreting them (T-108); upstream's columns, units and the `live_book` handling were pinned in T-109. |
| `VetoShape` | `raisedOn` required; `clearedOn`/`lastSeenOn` optional, never before `raisedOn`; no `lastSeenOn` after `clearedOn` (T-185, same day passes); `vetoSeverity` ∈ {HARD, SOFT}; optional, multi-valued `expiresOn` (T-188, like `lastSeenOn`: upstream moves it, current = MAX), each value not before `raisedOn` (the same day passes); it never closes a stint, only `clearedOn` does; since T-206 a GUARD-category rule is refused as `appliesRule`/`primaryRule` | Veto stints (T-102): a stint is closed by `clearedOn`, never deleted. |
| The 11 Contract v18 shapes (`TickerHistoryShape`, `OrchestratorRunShape`, `OrchestratorStepShape`, `StrategyBookShape`, `BookRebalanceShape`, `GuardAlertShape`, `GuardActionShape`, `BookWeightDailyShape`, `BookDailyPerformanceShape`, `PortfolioPeriodSummaryShape`, `BacktestTestShape`) | Required only what the view guarantees non-null; the handoff §3.3 nullable columns stay optional (cycle_run_id on MARKOWITZ_BASE, layer-1 alert value, layer-3/4 asset/ticker, action weights, CASH asset/name/targets, book guard_layers, ticker valid_to/evidence). `sh:in` for window_id, segment, arm_code, GUARD rule ids, alert state, action status and test name; no sign/range on drawdown, cost_return or max_drawdown. Sourcery review: `bookId` required on BookRebalance/GuardAction; `pValue` ∈ [0,1] and `nObs` ≥ 1 on BacktestTest; `sh:equals` for the six row-date/`knowledgeDate` pairs; a CASH row must have no `holdingAsset` | Carries the m015/m016/m018 views into the ontology (T-206, §1.10); a CASH row never needs an Asset node. |

Validated end-to-end with `pyshacl` against the full worked dataset below: **conforms = True**.

## 1.7 Worked example

`schema/instances.trig` instantiates **5** real tickers end to end (AAPL, JPM, XOM, JNJ, PG —
spanning 5 different GICS sectors), in TriG's explicit named-graph syntax rather than a single
flat file, operationalizing `07-ontology-topology.md`'s partitioning scheme directly: universe
membership, agent `ScoreSnapshot`s across all 4 agent types, a full evidence chain
(`NewsArticle` → `RiskEvent` → `Veto`), an EDGAR filing restatement demonstrating
`supersededBy` (critique #8's bitemporal pattern, concretely), and 3 `PortfolioPosition`s. It
exercises four of the seven rules by design — `VETO_FIN_01` (single-signal), `VETO_COMP_01`
(confluent, numeric), `VETO_RED_01` (contagion, via a shared `Executive` and a T-1 prior-cycle
veto), and, added 2026-08-13, `VETO_MKT_02` (single-signal, on the new `SectorRelativeMomentum`
metric — see §1.8) — chosen to cover the single-leaf, numeric-tree, graph-predicate, and
sector-relative cases distinctly. An independent Python script walks the ontology's own
`RuleClause` trees against this data and reproduces exactly the firings the dataset was designed
to produce (`AAPL→VETO_COMP_01`, `JPM→VETO_RED_01`, `XOM→VETO_FIN_01` and, on a later date,
`VETO_MKT_02`; `JNJ`/`PG`→none) — see `schema/README.md`.

## 1.8 Attractiveness Ranking and Sector-Relative Momentum (added 2026-08-13)

`schema/rules.ttl` and §1.5–1.7 above give the ontology a full *exclusion* model — vetoes are
purely negative, a surviving candidate is never ranked against its peers. This addition closes
that gap in part (critique #2, evolution layer B3's ranking half) and, along the way, gives the
ontology its first sector-level signal (critique #3, layer B2's momentum half). Full detail,
including the arithmetic worked example, lives in
`docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`; this section
summarizes what changed in the TBox. Four new classes were added, bringing the ontology to 27
total classes (`AllDisjointClasses` grew from 20 to 24 members, then to 25 with `DataQualityIssue` (T-104), then 26 with `AssetCoOccurrence` (T-107), then 27 with `BenchmarkObservation` (T-108) — the
taxonomic backbone added 2026-08-23, §1.2, brings the *overall* class count to 37, but adds no new
disjoint leaf types) and `shapes.ttl` to 14 shapes (§1.6):

- **`SectorAggregateSnapshot`** — immutable, timestamped roll-up of member `Asset`s'
  `ScoreTecnico` for one `Sector` on one date, written by the new Sector Agent
  (`08-agent-architecture.md`). Reuses `ScoreSnapshot`'s field shape (`normalizedScore`,
  `metricType`, `timestamp`, `agentOrigin='SECTOR'`) rather than inventing parallel fields — see
  the `ObservationSnapshot` note below for how that reuse was made OWL-safe. The same agent also
  writes a per-asset `SectorRelativeMomentum` — not a new class, but a new `metricType` value on
  the existing `ScoreSnapshot`, computed as that asset's `ScoreTecnico` minus its sector's
  aggregate and stored in `rawValue` (signed; `[-1.0, 1.0]` until T-155 widened it to `[-100.0, 100.0]`, upstream's TECHNICAL points); it is the first `ScoreSnapshot`
  `metricType` that leaves `normalizedScore` unset, which required relaxing `ScoreSnapshotShape`'s
  `sh:minCount 1` on that field to a conditional exempting this one `metricType`; T-081 added the same exemption for `Sentiment`, and requires every `Sentiment` snapshot to carry a `rawValue` in `[-1.0, 1.0]`; T-140 requires a `rawValue` of every `SectorRelativeMomentum` snapshot (first in `[-1.0, 1.0]`, for the attractiveness formula's `(rawValue + 1) / 2`; T-155 widened it to `[-100.0, 100.0]` once that formula was no longer computed here), allows `rawValue` at most once, and pairs each `agentOrigin` with its one `metricType`; T-171 (D17) adds `ScoreFinanciero` (FUNDAMENTAL) as a third exemption, for an unrelated reason — upstream rewrites its `normalized_score` in place every cycle, which a `ScoreSnapshot` individual can't carry without becoming a mutable observation — and requires every `ScoreFinanciero` snapshot to carry a `rawValue` too; T-177 bounds it to `[0.0, 100.0]` (upstream's answer to Q6: the assessment's score, which their model bounds at 0 and 100).
- **`AttractivenessSnapshot`** — the Orchestrator's immutable attractiveness ranking result for one
  `Asset` in one selection cycle: its combined attractiveness score. It is **not** the opposite of
  `Veto`: an asset can have both, and a SOFT veto subtracts its rule's `penaltyPoints` from the
  blended score. Closes part of critique #2/evolution layer B3's ranking half, not the
  position-sizing half. Carries `attractivenessScore`
  (functional, at most `1.0`, 1 = most attractive; no lower bound since T-155, because upstream's `blended_score / 100` goes negative when the SOFT-veto penalties exceed the blend; from upstream's version 11 the penalty is the sum of the active SOFT stints' rules' `penaltyPoints`, 15 each unless the stint's rule declares its own, a HARD rule's SOFT stint included: assumed, T-189), `computedAt`, and an audit-trail pointer
  `computedWithScheme` back to the `AttractivenessWeightScheme` that produced it — the same role
  `appliesRule`/`primaryRule` play for `Veto`. No stored rank or selection-status field: `v_cycle_ranking`
  also carries `rank`, `selected` and `status`, but the class does not model them; rank is relative to
  whatever comparison set a query defines, so it is always a query-time `ORDER BY attractivenessScore`,
  never a persisted fact.
- **`AttractivenessWeightScheme`** — the blend behind `attractivenessScore` as upstream's cycle
  runner recorded it for **one `cycle_run`** (read, never applied here, T-155; per-run since T-121):
  `schemeId` `cycle_run:<id>`, `cycleDate` = upstream's `v_weight_scheme.cycle_date`, upstream's book-weighting rule
  (`bookWeightingRule`: `score_proportional`, `score_tilt`) and its scalar knobs (`topN`, `maxNameWeight`,
  `maxSectorWeight`, `softVetoPenalty`), all read verbatim. A per-run scheme is an immutable
  observation, **not a valid-time record**: it is never closed or updated, a later run is a new scheme,
  and its absent `validTo` never means "still active". The shape requires exactly one of the two kinds (`sh:xone`): a `validFrom`, or a `cycleDate` with no `validTo`. It is written to `urn:graph:ingest:ORCHESTRATOR:{date}` with the snapshots that point at it (`docs/07`).
  The design-history `WeightScheme_v1` keeps the valid-time form, `[validFrom, validTo)`, mirroring
  `RuleDefinition`'s "rules live in the graph, not code" pattern (critique #6).
- **`WeightComponent`** — one `(metric, weight)` pair within an `AttractivenessWeightScheme`: for an
  upstream scheme, one per `score_type` (FUNDAMENTAL, VALORIZATION, TECHNICAL, plus SEMANTIC in older
  runs), the *configured* weight; effective weights are per asset and read from upstream (T-155). A new run
  weighs three score types (FUNDAMENTAL, VALORIZATION and TECHNICAL, our `ScoreFinanciero`, `ScoreCuantitativo` and
  `ScoreTecnico`) and an earlier one four (the SEMANTIC `Sentiment` as well; upstream's sixth reply, T-183 (6)); the shape asks for at least one
  component and one of the five names, not for a count (T-190), and the projection writes whatever the run has.
  `SectorRelativeMomentum` has no upstream weight and gets no component. `inverted` is optional design
  history (not computed here since T-155): emitted for no upstream scheme, kept on `WeightScheme_v1`.

**Attractiveness score formula — design history, not computed here (T-155).** The blend is
upstream's: `portfolio-financial-analysis`'s cycle runner produces `blended_score` and its
per-asset effective weights, and this repo reads them (`SPEC.md` §2.5 item 1; T-121, T-155). The
2026-08-13 design (spec §3) is kept below for the record only:

```
attractivenessScore = Σ weight_i * component_i   (weights sum to 1.0)
component_i = (1 - normalizedScore_i)     if inverted
component_i = (rawValue_i + 1) / 2         if not inverted
```

Every existing `normalizedScore` in this ontology is a *risk* reading (0 = no risk, 1 = critical
risk); attractiveness is the inverse sense, so `WeightComponent.inverted` marks which inputs need
that inversion rather than hardcoding it per metric. `Sentiment` and `SectorRelativeMomentum` are
`inverted=false` and read from `rawValue`, rescaled from `[-1,1]` to `[0,1]` — the same
raw-vs-normalized dispatch convention documented on `ThresholdComparison` in §1.2, now with
`SectorRelativeMomentum` as a third entry in that dispatch table alongside `Sentiment`. The
initial `AttractivenessWeightScheme` is an equal-ish weighting across five inputs
(`ScoreFinanciero` 0.25, `ScoreCuantitativo` 0.2, `ScoreTecnico` 0.2 — all inverted; `Sentiment`
0.2, `SectorRelativeMomentum` 0.15 — neither inverted), an explicit placeholder pending
calibration, same status as every veto threshold today.

The same `SectorRelativeMomentum` signal also feeds a new 7th veto rule, `VETO_MKT_02` (rank 7,
single-signal, threshold `-0.50` on `rawValue` — `rules.ttl`): an asset can now be excluded for
badly underperforming its sector peers, independent of and in addition to the six original
dimensions. That threshold is on the original `[-1, 1]` scale; since T-155 the shape
allows `[-100, 100]` (upstream's TECHNICAL points), and the rule, closed with `validTo`, is design
history: don't reuse or extend it as written.

**Domain-collision fix (`ObservationSnapshot`).** `SectorAggregateSnapshot` reuses
`ScoreSnapshot`'s `metricType`/`agentOrigin`/`timestamp`/`normalizedScore` properties, but those
properties' `rdfs:domain` was declared as `:ScoreSnapshot` specifically; reusing them as-is would
RDFS-entail that a `SectorAggregateSnapshot` individual is also a `:ScoreSnapshot`, contradicting
`AllDisjointClasses`. The original implementation resolved this the same way `RuleOperand`/
`EvidenceSource` resolved the analogous range problem: a union class
`:ObservationSnapshot = owl:unionOf(:ScoreSnapshot, :SectorAggregateSnapshot)`, excluded from
`AllDisjointClasses` and never used as an individual's `rdf:type`.

**Revised (2026-08-23, §1.2.1):** `:ObservationSnapshot` is now an ordinary `rdfs:subClassOf`
superclass of `:ScoreSnapshot`, `:SectorAggregateSnapshot`, and `:AttractivenessSnapshot` — all
three share the same immutable/timestamped observation shape — and the four reused properties
declare `rdfs:domain :ObservationSnapshot` directly instead of unioning it in. RDFS domain
entailment behaves identically for existing individuals either way, but individuals can now also be
queried by the shared type (`?x a :ObservationSnapshot`), which the excluded-union design couldn't
support. `RuleOperand` and `EvidenceSource` are upgraded the same way, same IRIs, in §1.2.1.

**Explicitly out of scope** (spec §1, not silently dropped): position sizing / `weightPct`
assignment from `attractivenessScore` (B3's sizing module), the full Sector/Industry
dashboard-style roll-up beyond this one aggregate metric (B2's broader signal set), and
rebalancing cadence / correlation / concentration caps. These remain open per
`critique-and-evolution.md`.

## 1.9 Metric-type controlled vocabulary (added 2026-08-23, merged into `schema/reference.ttl`)

`metricType` values were, until this revision, unconstrained strings: `ScoreSnapshotShape`
validated only that the field was present, not that its value came from a known set. GICS sectors
were in the identical situation before `reference.ttl` gave them a `skos:ConceptScheme`; this
closes the same gap for `metricType` (and the same-shaped `ThresholdComparison.metricName` /
`WeightComponent.weightMetricName`), using the same mechanism. (T-187 added `leverage.interest_coverage` and
`cashflow.operating_cash_flow_margin` to `metricName`'s list, for the redefined `LIQUIDITY_DISTRESS`.)

**Exactly 5 values, verified against the real data, not assumed:** `grep`-ing `metricType`/
`metricName`/`weightMetricName` literals across `rules.ttl` and `instances.trig` turns up exactly
`ScoreFinanciero`, `ScoreCuantitativo`, `ScoreTecnico`, `Sentiment`, `SectorRelativeMomentum` — no
sixth value anywhere. `09-nlp-finbert-architecture.md`'s "Output contract" worked example shows a
metricType of `"NEWS_SENTIMENT_FINBERT"` that is **never actually used** — every real Sentiment
`ScoreSnapshot` in `rules.ttl`'s veto thresholds and `WC_Sent` uses plain `"Sentiment"` instead.
That's a live inconsistency in `09`'s illustrative example, not a second real value; it's flagged
there and here rather than silently folded into a 6-member vocabulary that would misrepresent what
the schema actually does.

**Naming is deliberately left as-is, not translated.** The Spanish-origin values
(`ScoreFinanciero`, `ScoreCuantitativo`, `ScoreTecnico`) trace directly back to
`Avance arquitectura del sistema.docx`'s own variable names, cited verbatim in
`critique-and-evolution.md`'s veto-catalog table for audit traceability. Renaming them to English
at this layer would sever that traceability for a purely cosmetic gain; formalizing them as a
documented, closed vocabulary — rather than either leaving them as free strings or silently
translating them — resolves the real problem (an unconstrained, undocumented value set) without
that cost.

```turtle
@prefix :    <https://thesis.local/kg/portfolio#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

:MetricTypeScheme a skos:ConceptScheme ; skos:prefLabel "Portfolio KG Metric Types"@en .

:ScoreFinanciero        a skos:Concept ; skos:inScheme :MetricTypeScheme ; skos:prefLabel "ScoreFinanciero"@es ; skos:altLabel "Financial Score"@en ; rdfs:comment "FUNDAMENTAL agent, v1 §2A." .
:ScoreCuantitativo      a skos:Concept ; skos:inScheme :MetricTypeScheme ; skos:prefLabel "ScoreCuantitativo"@es ; skos:altLabel "Quantitative Score"@en, "Valorization Score"@en ; rdfs:comment "VALORIZATION agent (T-105, D6; agentOrigin was QUANTITATIVE in v1). The metric id keeps its v1 Spanish name, DECIDED (T-109 review): upstream has no separate metric id for a score, only score_type = VALORIZATION, which is :agentOrigin (already renamed in T-105). metricType is this ontology's own vocabulary, so there is nothing upstream to rename it to (score_snapshot.model exists but is a method label, default 'deterministic', not an id), and a rename would touch three sh:in lists, rules.ttl, the blend weights and the instances for no integration gain." .
:ScoreTecnico           a skos:Concept ; skos:inScheme :MetricTypeScheme ; skos:prefLabel "ScoreTecnico"@es ; skos:altLabel "Technical Score"@en .
:Sentiment              a skos:Concept ; skos:inScheme :MetricTypeScheme ; skos:prefLabel "Sentiment"@en ; rdfs:comment "rawValue-compared, not normalizedScore — see §1.5's dispatch convention." .
:SectorRelativeMomentum a skos:Concept ; skos:inScheme :MetricTypeScheme ; skos:prefLabel "SectorRelativeMomentum"@en ; rdfs:comment "Added 2026-08-13 with the Sector Agent; the metricType that leaves normalizedScore unset (§1.8)." .
```

`ScoreSnapshotShape.metricType`, `ThresholdComparisonShape.metricName`, and
`WeightComponentShape.weightMetricName` all tighten from an open string to `sh:in` over this
scheme's 5 `skos:prefLabel` values (`SectorAggregateSnapshotShape.metricType` tightens further, to
`sh:hasValue "ScoreTecnico"`, its one real value) — a constraint tightening on 3 existing shapes,
not a new shape (`shapes.ttl` stays at 14). Re-validated end-to-end against the real
`schema/*.ttl`/`.trig` files 2026-08-23: `rdflib` parses clean (1608 quads — see the taxonomy
quality review below for the +1 from the `RuleClause` fix), `pyshacl` conforms —
and this `sh:in` tightening is a real check, not a no-op: it would have failed had any actual data
value fallen outside the 5-member set. Adding a new metric type going forward means adding one
`skos:Concept` here and one value to each `sh:in` list, exactly the workflow already established
for adding a GICS industry.

## 1.10 Contract v18 backtest and GUARD classes (T-206, 2026-11-01)

The 11 views added between v12 and v18 (`SPEC.md` §2.6, T-205) now have ontology terms. One class
per view: `TickerHistory` (`v_ticker_history`, m016), `OrchestratorRun`/`OrchestratorStep`
(`v_orchestrator_run`/`v_orchestrator_step`, m015) and the eight m018 backtest/GUARD classes
`StrategyBook` (`v_book`), `BookRebalance`, `GuardAlert`, `GuardAction`, `BookWeightDaily`,
`BookDailyPerformance`, `PortfolioPeriodSummary` and `BacktestTest`. `tbox.ttl` is now 51 classes
(38 disjoint leaves) and `shapes.ttl` 31 named shapes; `AllDisjointClasses` gains the 11 leaves.

**Placement is by property shape, not theme** (the rule in §1.2 and the constitution's Project
structure #2). `TickerHistory` and `BookRebalance` are dated n-ary relations carrying data, so
`TemporalRelation`, like `UniverseMembership`/`PortfolioPosition`. `StrategyBook` is a named pool of
holdings, so `Collection`, like `Portfolio`. `GuardAction` is the decision/effect taken on a book, so
`RiskAndDecision`, beside `RiskEvent`/`Veto`. The other seven are immutable dated records with scalar
fields and no valid-time interval, so plain `Observation` (not `ObservationSnapshot`: they are not
metric snapshots with `metricType`/`agentOrigin`/`timestamp`). `OrchestratorRun`/`OrchestratorStep`
are process provenance, which is why they are `Observation` and not a `Run` class: T-106 already
decided the run log stays upstream.

**Spanish labels and definitions.** Each of the 11 classes carries one `rdfs:label`@es and one
`skos:definition`@es, the handoff §6.2 text verbatim (outer « » delimiters dropped), plus the English
label/comment the other classes carry. There is **no FIBO `rdfs:seeAlso`** on any of them: handoff
§6.1 says FIBO has no class for backtest runs, strategy arms, GUARD rules, Sharpe, drawdown,
turnover, costs or paired statistical tests. The FIBO alignment for the pre-existing classes is
Phase 1 of the FIBO brief (T-210, §1.1); these 11 classes still have no FIBO link because FIBO has
no class for them.

**Properties.** Every column of the 11 views has a property. The columns shared across classes
(`bookId`, `backtestRunId`, `armCode`, `windowId`, `knowledgeDate`, `status`, `decisionDate`,
`guardTicker`, `guardLayer`, `segment`, `handle`, `startedAt`, `finishedAt`, `runKind`) are declared
**without `rdfs:domain`**, the `:runId` pattern (T-106): a domain would RDFS-entail one new class on
another class's individual and contradict `AllDisjointClasses`. Every m018 individual carries
`:knowledgeDate` (`xsd:date`), so a uniform `knowledgeDate <= D` query works (handoff checklist 3).
A book or a test links to its backtest run by the literal `:backtestRunId`; there is no
`BacktestRun` class and no invented node. A rebalance's `quant_portfolio_id`, `cycle_run_id` and
`risk_model_id` are literals too, because they are upstream ids, not nodes in this graph. Object
links exist only between the new classes: `stepOfOrchestratorRun`, `tickerHistoryAsset`,
`rebalanceOfBook`, `actionOfBook`, `actionAlert`, `alertRule`, `guardAsset`, `weightOfBook`,
`performanceOfBook`, `summaryOfBook`, `holdingAsset`. Functional only where the data guarantees one
value (a step has one run, an action one alert and one book, a weight/performance/summary row one
book).

**Nullable columns.** `sh:minCount 1` is used only where the m015/m016/m018 DDL or handoff §3.3
guarantees a value. The following are optional and must never be required: `cycle_run_id` on
`MARKOWITZ_BASE` rebalances; `asset_id`/`ticker` on layer 3–4 alerts and actions; `value` on layer 1
alerts; `weight_before`/`weight_after` on asset actions and `NOT_HELD`; `asset_id`/`holding_name`
and both target weights on `BookWeightDaily` (CASH has no asset; ordinary sessions mask the targets);
`v_book.guard_layers`; `valid_to` (NULL = current symbol), `evidence_url` and `evidence_date` on
`TickerHistory`. The Orchestrator shapes require only their natural keys — `orchestratorRunId` on a
run, `stepOfOrchestratorRun` + `ordinal` on a step — because handoff §3.1 gives no base-table
nullability and both views have 0 rows. A CASH row is a `BookWeightDaily` with `holdingKey "CASH"`
and no `:holdingAsset`; it never needs an `:Asset` node.

**TickerHistory's interval is inclusive.** `v_ticker_history.valid_to` is the symbol's **last valid
date** (handoff §3.1), and the point-in-time lookup is `date BETWEEN valid_from AND
COALESCE(valid_to, '9999-12-31')`, so the model is `validFrom <= d <= validTo` and a one-day symbol
has `validFrom == validTo`. `TickerHistoryShape` uses `sh:lessThanOrEquals`; the shared `:validTo`
property stays exclusive on `RuleDefinition` (T-187), `UniverseMembership`, `PortfolioPosition` and
`AttractivenessWeightScheme`.

**Data over the handoff's DDL comments.** Measured on the completed `rule_P1/P2/P3.db` (identical in
all three): `MARKOWITZ_BASE` and `TOPN_MV_NOGUARD` have `guard_layers` NULL, while the DDL comment
says `'[]'`; `exclude_hard_vetoed` is 0 on all three arms, while the DDL says 1 for `TOPN_MV_*`. The
upstream maintainer confirmed the real values: `guard_layers` is NULL (not `'[]'`) for
`MARKOWITZ_BASE` and `TOPN_MV_NOGUARD`, and `'[1, 3, 4]'` for `TOPN_MV_GUARD_NO_NLP` (the driver
writes `None` when the arm has no guard, else a sorted JSON list); `exclude_hard_vetoed` is 0 on all
three arms because the `TOPN_MV_*` arms optimize over the 30 candidates cycle already filtered of
HARD vetoes, so the column is persisted as 0 (upstream's DDL comment reads `0 (the arms) | 1`). The
shapes stay as they are: `guard_layers` is optional and `exclude_hard_vetoed` is only an
`xsd:boolean`, with no per-arm value. `drawdown`, `cost_return` and `max_drawdown` are non-negative
magnitudes in the data, but the handoff states no sign convention, so no sign or range constraint is
placed on them.

**Rule catalog.** `UTILITY_CASH_COVERAGE` (HARD, `rule_input.utility_cash_coverage_3y < 0.05`, rank
10, valid from **2026-10-31**) joins the nine selection rules; the date is the last safe one: the
rule was already in upstream's catalog in the completed backtest runs (`rule_P1/P2/P3.db`, runs of
2026-10-31) and raised a real veto in P1 on 2022-03-03, so a later date is impossible. It is not
backdated to 2019/2020: valid-time here means when a definition was in force in production (T-187,
T-201), not that a backtest applies a rule retroactively. Upstream's `v_rule_catalog.created_at`
(2026-10-31T19:37:32) is a technical persistence timestamp, not the adoption date; the true T-071
merge date is still to confirm with upstream. The `LEVERAGE_EXTREME`, `NEGATIVE_FCF` and
`LIQUIDITY_DISTRESS` comments record the APP-00 profile exemptions (financial firms; regulated
utilities; equity REITs) without changing any threshold, severity or clause. The five GUARD rules
(`L1_STOP_LOSS`, `L1_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD`) are `RuleDefinition` individuals in a
separate, labelled section of `rules.ttl`: one `GraphPredicate` leaf each, `:category "GUARD"`,
`:guardLayer` 1..4, the frozen parameters and academic sources only in `rdfs:comment`. Their
`validFrom` 2019-01-02 is the calibration-window start (2019-01-02..2021-12-31, 757 NYSE sessions,
`params.frozen.toml`), confirmed by the upstream maintainer, and covers every alert and action of
P1, P2 and P3. `L2_NEWS` is
disabled in the 2022–2025 backtest (the FinBERT training pool spans 2022–2026). **A GUARD rule is
not a veto rule:** it carries no `:ruleSeverity`, `:penaltyPoints` or `:priorityRank`, and
`VetoShape` refuses it as the object of `:appliesRule`/`:primaryRule`. `RuleDefinitionShape` adds one
`sh:or` branch for `:category "GUARD"`, keeps the severity requirement for every other active rule,
makes `:priorityRank` mandatory for non-GUARD rules, and widens the rank range to `[1,10]` for
`UTILITY_CASH_COVERAGE`. The bundle is **4236 quads; conforms: True** (the FR-001 gate).

---

*Diagrams for this document live in the companion Artifact (n-ary relation + named-graph layering,
worked on the Apple instance above).*
