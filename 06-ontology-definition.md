# Ontology Definition — Portfolio Knowledge Graph (v2)

**Implementation:** [`schema/`](./schema/) — the formal OWL/SHACL/TriG implementation of
everything described below, split into `tbox.ttl` (classes/properties, 27 classes total), `shapes.ttl`
(SHACL, 14 shapes), `reference.ttl` (GICS taxonomy + asset master data), `rules.ttl` (all 7 veto
rules as trees), and `instances.trig` (a worked, multi-graph, multi-asset dataset). Parsed clean
with `rdflib` and SHACL-validated with `pyshacl` (**conforms: True**); the veto rule trees were
independently re-executed in Python against the instance data and reproduced the expected firings
exactly (see `schema/README.md`). This document is the prose walkthrough; `schema/` is the
executable artifact a thesis appendix or a real GraphDB/Fuseki load would use. `schema/README.md`
documents the file-to-named-graph map and the modeling refinements only discovered while
implementing (two new `RuleClause` leaf types, a raw-vs-normalized comparison convention, and a
shared-property domain-collision fix) — summarized in §1.5 and §1.8 below.

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

**FIBO alignment, as documentation only.** Several classes carry `rdfs:seeAlso` pointers to
Financial Industry Business Ontology (FIBO) concepts — e.g. `:Asset rdfs:seeAlso
fibo:LegalPersons/LegalPerson`, `:SECFiling rdfs:seeAlso fibo:Documents/Filing`. This is
deliberately *not* `owl:equivalentClass` or `owl:imports`: a full FIBO import is heavy (FIBO spans
dozens of modules) and buys nothing at thesis scale, but citing the alignment is worth doing for
academic grounding — it signals the class design isn't arbitrary, without paying FIBO's load cost.

## 1.2 Core class inventory

| Class | Answers | One-line definition |
|---|---|---|
| `Asset` | v1 §2A/§3A | An S&P 500 constituent tracked by the system. |
| `Sector`, `Industry` | critique #3 | GICS-aligned SKOS concepts; `Industry` rolls up to exactly one `Sector`. **New** — v1 had no sector layer at all despite it being in the thesis's own stated scope. |
| `Universe` | v1 §2A | A named candidate pool (e.g. the quarterly Watchlist). |
| `UniverseMembership` | v1 §2A, formalized | Reifies v1's `(Asset)-[PERTENECE_A_UNIVERSO{fecha_inicio,fecha_fin}]->(Universe)` edge as a first-class individual (§1.4 explains why). |
| `ScoreSnapshot` | v1 §3A | Immutable, timestamped metric from one specialist agent. |
| `RiskEvent` | v1 §3B | A discrete flagged event; SHACL-required to carry evidence (closes critique #5). |
| `NewsArticle`, `SECFilingSection` | v1 §3B | Evidence leaves — cross-referenced to the *existing* `news-collector`/`news-crawler` SQLite pipeline via `provenanceId` (see §1.6 and `09-nlp-finbert-architecture.md`), not a fresh identifier scheme. |
| `SECFiling` | v1 §2B | One EDGAR filing (10-K/10-Q/8-K/DEF 14A) for one `Asset`. |
| `Executive` | v1 §4 | Extracted from DEF 14A; `canonicalId` populated once entity resolution (roadmap step 7) exists. |
| `Veto` | v1 §4 | The orchestrator's per-cycle decision node. |
| `RuleDefinition`, `RuleClause`, `ThresholdComparison` | v1 §4, critique #1 & #6 | The veto catalog as versioned, structurally unambiguous graph data — see §1.5, the direct payoff of choosing RDF. |
| `Portfolio`, `PortfolioPosition` | critique #2 | **New** — v1 specified exclusion (universe + veto) but no inclusion/holding model at all. |
| `PriceObservation` | scope requirement (daily pricing) | **New, derived-summary only** — see the topology document for why raw OHLCV ticks do *not* belong in the triple store. |

## 1.3 Object & datatype properties

The full domain/range table is the `.ttl` file itself (§2–3 of that file); the properties worth
calling out here are the ones that encode a design decision, not just a field:

- **`backedBy`** (`RiskEvent → NewsArticle | SECFilingSection`) has `sh:minCount 1` in the SHACL
  shapes (§1.6) — a `RiskEvent` cannot exist in the store without evidence. This turns critique
  gap #5 ("no null/missing-data policy") from a prose recommendation into an enforced constraint.
- **`appliesRule`** vs **`primaryRule`** — both present on `Veto`, matching v1's own distinction
  ("Mapeo de Activaciones Multiples", §4): the full trigger list plus a computed lowest-`priorityRank`
  primary reason for audit queries.
- **`sharedExecutiveWith`** is declared `owl:SymmetricProperty` but is explicitly commented as
  *derived*, not hand-authored — it is written by the entity-resolution service (roadmap step 7),
  not by any ingestion agent directly. Marking this in the ontology itself prevents a future
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

**Addendum — implementation surfaced a gap in this section.** Encoding all 6 rules from v1's
catalog (`schema/rules.ttl`), not just `VETO_COMP_01`, revealed that `ThresholdComparison` alone
doesn't cover the catalog: `VETO_LEG_01`/`VETO_COMP_02` gate on `RiskEvent.category`/`severity`
(categorical, not numeric) and `VETO_RED_01` gates on a graph-structural predicate
(`HasSharedPrimaryVetoExecutive`), not a scalar comparison at all. `schema/tbox.ttl` adds two more
leaf types — `CategoricalComparison` and `GraphPredicate` — alongside `ThresholdComparison`, each
with its own SHACL shape, unioned under a new `:RuleOperand` class so `operand1`/`operand2`/
`hasClause` can point at any of them. The full 6-rule catalog, plus a 5-asset worked dataset
exercising all three leaf kinds, was independently re-evaluated in Python against the ontology's
own tree structure and reproduced the intended firings exactly — see `schema/README.md`.

## 1.6 SHACL shapes for data-quality enforcement

SHACL (Shapes Constraint Language) is RDF's declarative validator — the world-view equivalent of
a schema/type checker, but expressed as data rather than code. 14 shapes are defined
(`schema/shapes.ttl`; three more than originally scoped here — `ThresholdComparisonShape`,
`CategoricalComparisonShape`, `GraphPredicateShape` — added to cover the two new leaf types from
the addendum above, plus four more added 2026-08-13 for the attractiveness-ranking feature, see
§1.8), each closing a specific gap:

| Shape | Constraint | Closes |
|---|---|---|
| `ScoreSnapshotShape` | `normalizedScore` ∈ `[0.0, 1.0]`; `agentOrigin` ∈ the 4 known agents; `metricType`/`timestamp` required | Prevents a malformed snapshot from silently entering veto evaluation. |
| `RiskEventShape` | `backedBy` `sh:minCount 1`; `severity`/`category` from closed vocabularies | Critique #5 (no null-handling policy) — evidence-free risk events are now a validation failure, not a silent gap. |
| `RuleDefinitionShape` | `validFrom` required; exactly one `hasClause`; `priorityRank` ∈ `[1,7]` | Critique #6 — a rule can't be persisted without being properly temporal and ranked. |
| `RuleClauseShape` | `clauseType` ∈ `{AND, OR}`; both operands required | Structural half of the critique #1 fix — a clause literally cannot be built with a missing operand or an unrecognized operator. |
| `ThresholdComparisonShape` / `CategoricalComparisonShape` / `GraphPredicateShape` | Each leaf kind's required fields (`metricName`/`operator`/`thresholdValue`; `attributeName`/`expectedValue`; `predicateName`) | Completes the structural half of the critique #1 fix across all 7 rules, not just numeric ones. |
| `UniverseMembershipShape` | both endpoints + `validFrom` required | Keeps §1.4's n-ary relation pattern from degrading into a dangling record. |

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
total classes (`AllDisjointClasses` grew from 20 to 24 members) and `shapes.ttl` to 14 shapes
(§1.6):

- **`SectorAggregateSnapshot`** — immutable, timestamped roll-up of member `Asset`s'
  `ScoreTecnico` for one `Sector` on one date, written by the new Sector Agent
  (`08-agent-architecture.md`). Reuses `ScoreSnapshot`'s field shape (`normalizedScore`,
  `metricType`, `timestamp`, `agentOrigin='SECTOR'`) rather than inventing parallel fields — see
  the `ObservationSnapshot` note below for how that reuse was made OWL-safe. The same agent also
  writes a per-asset `SectorRelativeMomentum` — not a new class, but a new `metricType` value on
  the existing `ScoreSnapshot`, computed as that asset's `ScoreTecnico` minus its sector's
  aggregate and stored in `rawValue` (signed, `[-1.0, 1.0]`); it is the first `ScoreSnapshot`
  `metricType` that leaves `normalizedScore` unset, which required relaxing `ScoreSnapshotShape`'s
  `sh:minCount 1` on that field to a conditional (`sh:xone`) exempting this one `metricType`.
- **`AttractivenessSnapshot`** — the Orchestrator's computed ranking output for one `Asset` in one
  cycle: the positive counterpart to `Veto` (v1 modeled exclusion only). Closes part of critique
  #2/evolution layer B3's ranking half, not the position-sizing half. Carries `attractivenessScore`
  (functional, `[0.0, 1.0]`, 1 = most attractive), `computedAt`, and an audit-trail pointer
  `computedWithScheme` back to the `AttractivenessWeightScheme` that produced it — the same role
  `appliesRule`/`primaryRule` play for `Veto`. No stored rank field: rank is relative to whatever
  comparison set a query defines, so it is always a query-time `ORDER BY attractivenessScore`,
  never a persisted fact.
- **`AttractivenessWeightScheme`** — a versioned set of per-metric weights the Orchestrator applies
  to compute `attractivenessScore`, valid over `[validFrom, validTo)` — mirrors
  `RuleDefinition`'s "rules live in the graph, not code" pattern (critique #6), applied to weights
  instead of thresholds.
- **`WeightComponent`** — one `(metric, weight, inverted)` triple within an
  `AttractivenessWeightScheme`. `inverted=true` marks risk-oriented metrics (e.g.
  `ScoreFinanciero`) that must be flipped (`1 - normalizedScore`) before weighting.

**Attractiveness score formula** (spec §3):

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
dimensions.

**Domain-collision fix (`ObservationSnapshot`).** `SectorAggregateSnapshot` reuses
`ScoreSnapshot`'s `metricType`/`agentOrigin`/`timestamp`/`normalizedScore` properties, but those
properties' `rdfs:domain` was declared as `:ScoreSnapshot` specifically; reusing them as-is would
RDFS-entail that a `SectorAggregateSnapshot` individual is also a `:ScoreSnapshot`, contradicting
`AllDisjointClasses`. Resolved the same way `RuleOperand`/`EvidenceSource` already resolve the
analogous range problem: a new union class `:ObservationSnapshot = unionOf(:ScoreSnapshot,
:SectorAggregateSnapshot)` widens the four properties' domain instead of duplicating them under
new names. `:ObservationSnapshot` is never used as an individual's `rdf:type`, and is deliberately
excluded from `AllDisjointClasses` (same convention as `RuleOperand`/`EvidenceSource`).

**Explicitly out of scope** (spec §1, not silently dropped): position sizing / `weightPct`
assignment from `attractivenessScore` (B3's sizing module), the full Sector/Industry
dashboard-style roll-up beyond this one aggregate metric (B2's broader signal set), and
rebalancing cadence / correlation / concentration caps. These remain open per
`critique-and-evolution.md`.

---

*Diagrams for this document live in the companion Artifact (n-ary relation + named-graph layering,
worked on the Apple instance above).*
