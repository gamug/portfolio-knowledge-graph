# Attractiveness Score + Sector-Relative Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a continuous per-asset attractiveness/ranking score (the positive counterpart to the
existing veto catalog) fed in part by a new sector-relative-momentum signal, and wire that same
signal into a new 7th veto rule — closing part of critique-and-evolution.md gaps #2 and #3.

**Architecture:** Three new immutable/versioned RDF classes (`SectorAggregateSnapshot`,
`AttractivenessSnapshot`, `AttractivenessWeightScheme`+`WeightComponent`) added to the existing
multi-file Turtle/TriG schema, following the file's own established patterns (`ScoreSnapshot`,
`Veto`, `RuleDefinition`) rather than inventing new ones. A new `VETO_MKT_02` rule and a versioned
`AttractivenessWeightScheme` are added to the rule catalog; a worked, hand-checkable example
extends `instances.trig`'s existing 5-ticker dataset. All companion docs and published artifacts
are updated to match.

**Tech Stack:** RDF/OWL (Turtle), SHACL, TriG. Validated with Python `rdflib` + `pyshacl` (no
other build tooling in this repo).

**Spec:** `docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`

## Global Constraints

- IRI namespace for all new terms: `https://thesis.local/kg/portfolio#` (prefix `:`), matching
  every existing file.
- No git repository exists in this project (`git status` fails with "not a git repository") — this
  plan has **no commit steps**; each task's file edits are the durable record, and Task 6's
  validation script is the correctness gate in place of a test suite.
- Every `ScoreSnapshot.normalizedScore` in this ontology is a **risk** reading (0=no risk,
  1=critical risk) — attractiveness must invert risk-oriented inputs, never average them directly
  in the same direction as sentiment/momentum (spec §3).
- `rdfs:domain` on a shared datatype property implies RDFS-entailed class membership; reusing a
  property whose domain is `:ScoreSnapshot` on a new, `AllDisjointClasses`-disjoint class produces
  an inconsistent inferred type. Where `SectorAggregateSnapshot` needs to reuse `metricType`,
  `agentOrigin`, `timestamp`, `normalizedScore`, their `rdfs:domain` must first be widened to a new
  union class (`:ObservationSnapshot`), exactly the way `RuleOperand`/`EvidenceSource` already
  widen ranges elsewhere in `tbox.ttl` — **this is a correctness fix discovered while planning,
  not in the original spec text; flagged here so Task 1 doesn't skip it.**
- Every threshold/weight introduced is an explicit placeholder pending calibration (B5), matching
  every existing threshold in `rules.ttl` — do not present any new number as calibrated.

---

### Task 1: TBox additions (`schema/tbox.ttl`)

**Files:**
- Modify: `schema/tbox.ttl`

**Interfaces:**
- Produces: classes `:SectorAggregateSnapshot`, `:AttractivenessSnapshot`,
  `:AttractivenessWeightScheme`, `:WeightComponent`, `:ObservationSnapshot` (union); properties
  `:sectorSnapshotOfSector`/`:hasSectorSnapshot`, `:attractivenessOfAsset`/`:hasAttractivenessSnapshot`,
  `:computedWithScheme`, `:hasWeightComponent`, `:attractivenessScore`, `:computedAt`, `:schemeId`,
  `:weightMetricName`, `:weightValue`, `:inverted`. Consumed by Tasks 2–4.

- [ ] **Step 1: Insert the four new class definitions**

Insert immediately after the existing `:PriceObservation` class block (the last class before the
`# 1.1 UNION CLASSES` heading):

```turtle
:SectorAggregateSnapshot
    a owl:Class ;
    rdfs:label "Sector Aggregate Snapshot" ;
    rdfs:comment "Immutable, timestamped roll-up of member Assets' ScoreTecnico for one Sector on one date, written by the Sector Agent (08-agent-architecture.md). Added 2026-08-13, closes part of critique #3 (sector layer) -- see docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md." .

:AttractivenessSnapshot
    a owl:Class ;
    rdfs:label "Attractiveness Snapshot" ;
    rdfs:comment "The Orchestrator's computed ranking output for one Asset in one cycle -- the positive counterpart to Veto (v1 modeled exclusion only). Closes part of critique #2/evolution layer B3's ranking half (not the position-sizing half). Added 2026-08-13." .

:AttractivenessWeightScheme
    a owl:Class ;
    rdfs:label "Attractiveness Weight Scheme" ;
    rdfs:comment "A versioned set of per-metric weights the Orchestrator applies to compute AttractivenessSnapshot.attractivenessScore, valid over [validFrom, validTo) -- mirrors RuleDefinition's 'rules live in the graph, not code' pattern (critique #6), applied to weights instead of thresholds. Added 2026-08-13." .

:WeightComponent
    a owl:Class ;
    rdfs:label "Weight Component" ;
    rdfs:comment "One (metric, weight, inverted) triple within an AttractivenessWeightScheme. inverted=true marks risk-oriented metrics (e.g. ScoreFinanciero) that must be flipped (1 - normalizedScore) before weighting -- see attractivenessScore's comment. Added 2026-08-13." .
```

- [ ] **Step 2: Widen the shared observation properties' domain (the collision fix)**

Add a new union class right after the existing `:RuleOperand` union class definition (end of the
`# 1.1 UNION CLASSES` section):

```turtle
:ObservationSnapshot
    a owl:Class ;
    owl:unionOf ( :ScoreSnapshot :SectorAggregateSnapshot ) ;
    rdfs:label "Observation Snapshot" ;
    rdfs:comment "Widens metricType/agentOrigin/timestamp/normalizedScore's domain beyond ScoreSnapshot alone so SectorAggregateSnapshot can reuse the same properties without an RDFS-entailed type clash against AllDisjointClasses. Added 2026-08-13; never used as an individual's rdf:type, same convention as RuleOperand/EvidenceSource." .
```

Then, in `# 3. DATATYPE PROPERTIES`, change these four existing declarations' `rdfs:domain` from
`:ScoreSnapshot` to `:ObservationSnapshot` (leave every other property, including `:rawValue`,
untouched):

```turtle
:metricType  a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :ObservationSnapshot ; rdfs:range xsd:string .
:agentOrigin a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :ObservationSnapshot ; rdfs:range xsd:string ;
    rdfs:comment "One of FUNDAMENTAL | SEMANTIC | QUANTITATIVE | TECHNICAL | SECTOR. SHACL sh:in enforced." .
:timestamp   a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :ObservationSnapshot ; rdfs:range xsd:dateTime .
```

and

```turtle
:normalizedScore a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :ObservationSnapshot ; rdfs:range xsd:decimal ;
    rdfs:comment "[0.0, 1.0], 0=no risk, 1=critical risk on ScoreSnapshot; sector-aggregate reading on SectorAggregateSnapshot. Range enforced by SHACL." .
```

(Note the `agentOrigin` comment also gains `| SECTOR` — the Sector Agent is a 5th writer.)

- [ ] **Step 3: Add the new object properties**

Insert after the existing `:priceObservationOf` line in `# 2. OBJECT PROPERTIES`:

```turtle
:sectorSnapshotOfSector a owl:ObjectProperty, owl:FunctionalProperty ; rdfs:domain :SectorAggregateSnapshot ; rdfs:range :Sector ;
    owl:inverseOf :hasSectorSnapshot .
:hasSectorSnapshot a owl:ObjectProperty ; rdfs:domain :Sector ; rdfs:range :SectorAggregateSnapshot .

:attractivenessOfAsset a owl:ObjectProperty, owl:FunctionalProperty ; rdfs:domain :AttractivenessSnapshot ; rdfs:range :Asset ;
    owl:inverseOf :hasAttractivenessSnapshot .
:hasAttractivenessSnapshot a owl:ObjectProperty ; rdfs:domain :Asset ; rdfs:range :AttractivenessSnapshot .

:computedWithScheme a owl:ObjectProperty, owl:FunctionalProperty ; rdfs:domain :AttractivenessSnapshot ; rdfs:range :AttractivenessWeightScheme ;
    rdfs:comment "Audit trail -- same role appliesRule/primaryRule play for Veto." .

:hasWeightComponent a owl:ObjectProperty ; rdfs:domain :AttractivenessWeightScheme ; rdfs:range :WeightComponent .
```

- [ ] **Step 4: Add the new datatype properties**

Insert after `:atr14` at the end of `# 3. DATATYPE PROPERTIES`:

```turtle
# --- AttractivenessSnapshot / AttractivenessWeightScheme / WeightComponent (added 2026-08-13) ---
:attractivenessScore a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :AttractivenessSnapshot ; rdfs:range xsd:decimal ;
    rdfs:comment "[0.0, 1.0], 1=most attractive -- the inverse sense of ScoreSnapshot.normalizedScore's risk convention. Formula: docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md SS3." .
:computedAt a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :AttractivenessSnapshot ; rdfs:range xsd:dateTime .
:schemeId a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :AttractivenessWeightScheme ; rdfs:range xsd:string .
:weightMetricName a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :WeightComponent ; rdfs:range xsd:string ;
    rdfs:comment "Matches a ScoreSnapshot.metricType value. Named distinctly from ThresholdComparison's metricName to avoid a shared-property domain clash (see ObservationSnapshot's rationale)." .
:weightValue a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :WeightComponent ; rdfs:range xsd:decimal .
:inverted a owl:DatatypeProperty, owl:FunctionalProperty ; rdfs:domain :WeightComponent ; rdfs:range xsd:boolean ;
    rdfs:comment "true for risk-oriented metrics that must be read as (1 - normalizedScore) before weighting." .
```

- [ ] **Step 5: Update the `ThresholdComparison` dispatch-convention comment**

Find `:ThresholdComparison`'s `rdfs:comment` (the one documenting the raw-vs-normalized dispatch
convention) and append one sentence to the existing comment text: `" Added 2026-08-13:
SectorRelativeMomentum (a ScoreSnapshot metricType, not a new class) is a third entry in this same
dispatch table, compared via rawValue like Sentiment -- see rules.ttl's VETO_MKT_02."`

- [ ] **Step 6: Update the disjointness block**

Change the `# 1.2 DISJOINTNESS` comment's class count from 20 to 24, and add the 4 new classes to
the `owl:members` list:

```turtle
#################################################################
# 1.2 DISJOINTNESS — every individual belongs to exactly one of
# these 24 classes (the 2 union classes above, plus ObservationSnapshot
# added 2026-08-13, are deliberately excluded -- they're meant to
# overlap with their members).
#################################################################

[] a owl:AllDisjointClasses ;
   owl:members ( :Asset :Sector :Industry :Universe :UniverseMembership :ScoreSnapshot
                 :RiskEvent :NewsArticle :SECFiling :SECFilingSection :Executive :Veto
                 :RuleDefinition :RuleClause :ThresholdComparison :CategoricalComparison
                 :GraphPredicate :Portfolio :PortfolioPosition :PriceObservation
                 :SectorAggregateSnapshot :AttractivenessSnapshot :AttractivenessWeightScheme
                 :WeightComponent ) .
```

- [ ] **Step 7: Verify the file still parses standalone**

Run from `schema/`:
```bash
python -c "import rdflib; g = rdflib.Graph(); g.parse('tbox.ttl', format='turtle'); print('triples:', len(g))"
```
Expected: prints a triple count with no exception. (Exact count isn't asserted here — Task 6's
full-dataset validation is the real gate.)

---

### Task 2: SHACL shapes (`schema/shapes.ttl`)

**Files:**
- Modify: `schema/shapes.ttl`

**Interfaces:**
- Consumes: classes/properties from Task 1.
- Produces: `:SectorAggregateSnapshotShape`, `:AttractivenessSnapshotShape`,
  `:AttractivenessWeightSchemeShape`, `:WeightComponentShape`; amended `:ScoreSnapshotShape`.

- [ ] **Step 1: Amend `ScoreSnapshotShape`'s `normalizedScore` constraint**

Replace the existing `normalizedScore` property line inside `:ScoreSnapshotShape`:

```turtle
sh:property [ sh:path :normalizedScore ; sh:datatype xsd:decimal ; sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ; sh:minCount 1 ; sh:maxCount 1 ] ;
```

with a version that drops the blanket `sh:minCount 1` and adds a node-level `sh:or` requiring
either `metricType = "SectorRelativeMomentum"` or a present `normalizedScore`:

```turtle
sh:property [ sh:path :normalizedScore ; sh:datatype xsd:decimal ; sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ; sh:maxCount 1 ] ;
```

and add this as a new top-level property of `:ScoreSnapshotShape` (alongside its other
`sh:property` lines, before the closing `.`):

```turtle
    sh:or ( [ sh:path :metricType ; sh:hasValue "SectorRelativeMomentum" ]
            [ sh:path :normalizedScore ; sh:minCount 1 ] ) ;
```

- [ ] **Step 2: Add the four new node shapes**

Append after `:AssetShape` (end of file):

```turtle
:SectorAggregateSnapshotShape
    a sh:NodeShape ;
    sh:targetClass :SectorAggregateSnapshot ;
    sh:property [ sh:path :sectorSnapshotOfSector ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :normalizedScore ; sh:datatype xsd:decimal ; sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :metricType ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :agentOrigin ; sh:hasValue "SECTOR" ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :timestamp ; sh:datatype xsd:dateTime ; sh:minCount 1 ; sh:maxCount 1 ] .

:AttractivenessSnapshotShape
    a sh:NodeShape ;
    sh:targetClass :AttractivenessSnapshot ;
    sh:property [ sh:path :attractivenessOfAsset ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :attractivenessScore ; sh:datatype xsd:decimal ; sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :computedAt ; sh:datatype xsd:dateTime ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :computedWithScheme ; sh:minCount 1 ; sh:maxCount 1 ] .

:AttractivenessWeightSchemeShape
    a sh:NodeShape ;
    sh:targetClass :AttractivenessWeightScheme ;
    sh:property [ sh:path :schemeId ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :validFrom ; sh:datatype xsd:date ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :hasWeightComponent ; sh:minCount 1 ] .

:WeightComponentShape
    a sh:NodeShape ;
    sh:targetClass :WeightComponent ;
    sh:property [ sh:path :weightMetricName ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :weightValue ; sh:datatype xsd:decimal ; sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path :inverted ; sh:datatype xsd:boolean ; sh:minCount 1 ; sh:maxCount 1 ] .
```

- [ ] **Step 3: Verify the file still parses standalone**

```bash
python -c "import rdflib; g = rdflib.Graph(); g.parse('shapes.ttl', format='turtle'); print('triples:', len(g))"
```
Expected: prints a triple count with no exception.

---

### Task 3: Rule catalog + weight scheme (`schema/rules.ttl`)

**Files:**
- Modify: `schema/rules.ttl`

**Interfaces:**
- Consumes: classes/properties from Task 1.
- Produces: `:Rule_VETO_MKT_02`, `:WeightScheme_v1` (and its 5 `:WeightComponent` individuals) —
  both consumed by Task 4's worked instance data.

- [ ] **Step 1: Append the new veto rule**

Add after the existing `VETO_COMP_03` block (end of file):

```turtle
# --- Rank 7: VETO_MKT_02 — Market/Sector-Momentum, single signal (added 2026-08-13) ---
# Closes part of critique #3 (sector layer) — see docs/superpowers/specs/2026-08-13-
# attractiveness-sector-momentum-design.md. Appended after the original 6; none of their
# already-validated thresholds change.
:Rule_VETO_MKT_02 a :RuleDefinition ;
    :ruleId "VETO_MKT_02" ; :category "MARKET" ; :priorityRank 7 ;
    :validFrom "2026-08-13"^^xsd:date ;
    :hasClause :Cmp_MKT02_SectorMomentumLow .

:Cmp_MKT02_SectorMomentumLow a :ThresholdComparison ;
    :metricName "SectorRelativeMomentum" ; :operator "<" ; :thresholdValue "-0.50"^^xsd:decimal ;
    rdfs:comment "Compared via rawValue, not normalizedScore — SectorRelativeMomentum is a signed delta, same raw-scale convention as Sentiment (see tbox.ttl's ThresholdComparison comment). Placeholder threshold pending calibration (B5), same status as every other threshold in this file." .
```

- [ ] **Step 2: Append the attractiveness weight scheme**

```turtle
#################################################################
# Attractiveness weight scheme (added 2026-08-13) — the positive
# counterpart to this rule catalog. Versioned graph data, same
# pattern as RuleDefinition above (critique #6's principle applied
# to weights, not just thresholds). Formula this scheme feeds:
# docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-
# design.md §3. Placeholder weights pending calibration (B5).
#################################################################
:WeightScheme_v1 a :AttractivenessWeightScheme ;
    :schemeId "ATTR_WEIGHTS_V1" ; :validFrom "2026-08-13"^^xsd:date ;
    :hasWeightComponent :WC_Fin, :WC_Quant, :WC_Tec, :WC_Sent, :WC_SectorMom .

:WC_Fin       a :WeightComponent ; :weightMetricName "ScoreFinanciero"        ; :weightValue "0.25"^^xsd:decimal ; :inverted true .
:WC_Quant     a :WeightComponent ; :weightMetricName "ScoreCuantitativo"      ; :weightValue "0.20"^^xsd:decimal ; :inverted true .
:WC_Tec       a :WeightComponent ; :weightMetricName "ScoreTecnico"           ; :weightValue "0.20"^^xsd:decimal ; :inverted true .
:WC_Sent      a :WeightComponent ; :weightMetricName "Sentiment"              ; :weightValue "0.20"^^xsd:decimal ; :inverted false .
:WC_SectorMom a :WeightComponent ; :weightMetricName "SectorRelativeMomentum" ; :weightValue "0.15"^^xsd:decimal ; :inverted false .
```

- [ ] **Step 3: Verify the file still parses standalone and the rank-7 rule is queryable**

```bash
python -c "
import rdflib
g = rdflib.Graph(); g.parse('rules.ttl', format='turtle')
ns = rdflib.Namespace('https://thesis.local/kg/portfolio#')
rows = list(g.query('SELECT ?r ?rank WHERE { ?r a <%s>; <%spriorityRank> ?rank }' % (ns.RuleDefinition, ns)))
print(sorted(rows, key=lambda r: int(r[1])))
"
```
Expected: 7 rows, ranks 1–7, with rank 7 bound to `:Rule_VETO_MKT_02`.

---

### Task 4: Worked instance data (`schema/instances.trig`)

**Files:**
- Modify: `schema/instances.trig`

**Interfaces:**
- Consumes: `:Rule_VETO_MKT_02`, `:WeightScheme_v1` from Task 3; `:sectorSnapshotOfSector`,
  `:hasSectorSnapshot`, `:attractivenessOfAsset`, `:hasAttractivenessSnapshot`,
  `:computedWithScheme` from Task 1. Reads existing `Snap_*_Tec_20260805`,
  `Snap_*_Fin_2026Q3`, `Snap_*_Quant_20260805`, `Snap_*_Sent_20260805` values already in this file.

- [ ] **Step 1: Insert the new `SECTOR` ingest graph**

Insert a new `GRAPH` block after the existing `GRAPH <urn:graph:ingest:SEMANTIC:2026-08-05> { ... }`
block and before `GRAPH <urn:graph:ingest:EDGAR:2026-Q3> { ... }`:

```turtle
GRAPH <urn:graph:ingest:SECTOR:2026-08-05> {
    # Sector aggregates — degenerate to the single worked-example member's own ScoreTecnico for
    # 4 of 5 sectors (this file only populates one Asset per sector; a real deployment aggregates
    # across the full ~500-asset universe — see docs/superpowers/specs/2026-08-13-attractiveness-
    # sector-momentum-design.md §6). Sec_Energy is deliberately given an illustrative aggregate
    # DIFFERENT from XOM's own score, to demonstrate a non-zero SectorRelativeMomentum and
    # VETO_MKT_02 firing below.
    :SectSnap_InfoTech_20260805 a :SectorAggregateSnapshot ; :sectorSnapshotOfSector :Sec_InformationTechnology ;
        :metricType "ScoreTecnico" ; :normalizedScore "0.50"^^xsd:decimal ; :agentOrigin "SECTOR" ;
        :timestamp "2026-08-05T07:15:00"^^xsd:dateTime .
    :SectSnap_Financials_20260805 a :SectorAggregateSnapshot ; :sectorSnapshotOfSector :Sec_Financials ;
        :metricType "ScoreTecnico" ; :normalizedScore "0.40"^^xsd:decimal ; :agentOrigin "SECTOR" ;
        :timestamp "2026-08-05T07:15:00"^^xsd:dateTime .
    :SectSnap_Energy_20260805 a :SectorAggregateSnapshot ; :sectorSnapshotOfSector :Sec_Energy ;
        :metricType "ScoreTecnico" ; :normalizedScore "0.90"^^xsd:decimal ; :agentOrigin "SECTOR" ;
        :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "Illustrative: Energy sector broadly strong on technicals (0.90) while XOM itself is weak (0.35, Snap_XOM_Tec_20260805) — feeds XOM's -0.55 SectorRelativeMomentum below, which fires VETO_MKT_02." .
    :SectSnap_HealthCare_20260805 a :SectorAggregateSnapshot ; :sectorSnapshotOfSector :Sec_HealthCare ;
        :metricType "ScoreTecnico" ; :normalizedScore "0.30"^^xsd:decimal ; :agentOrigin "SECTOR" ;
        :timestamp "2026-08-05T07:15:00"^^xsd:dateTime .
    :SectSnap_ConsumerStaples_20260805 a :SectorAggregateSnapshot ; :sectorSnapshotOfSector :Sec_ConsumerStaples ;
        :metricType "ScoreTecnico" ; :normalizedScore "0.28"^^xsd:decimal ; :agentOrigin "SECTOR" ;
        :timestamp "2026-08-05T07:15:00"^^xsd:dateTime .

    :Sec_InformationTechnology :hasSectorSnapshot :SectSnap_InfoTech_20260805 .
    :Sec_Financials            :hasSectorSnapshot :SectSnap_Financials_20260805 .
    :Sec_Energy                :hasSectorSnapshot :SectSnap_Energy_20260805 .
    :Sec_HealthCare            :hasSectorSnapshot :SectSnap_HealthCare_20260805 .
    :Sec_ConsumerStaples       :hasSectorSnapshot :SectSnap_ConsumerStaples_20260805 .

    # Per-asset SectorRelativeMomentum = own ScoreTecnico.normalizedScore - sector aggregate
    # (spec §3). rawValue only — normalizedScore intentionally absent (no natural [0,1] reading
    # of a signed delta); validates the amended ScoreSnapshotShape's sh:or clause (Task 2).
    :Snap_AAPL_SectMom_20260805 a :ScoreSnapshot ; :agentOrigin "SECTOR" ; :metricType "SectorRelativeMomentum" ;
        :rawValue "0.00"^^xsd:decimal ; :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "0.50 (AAPL ScoreTecnico) - 0.50 (Sec_InformationTechnology aggregate) = 0.00." .
    :Snap_JPM_SectMom_20260805 a :ScoreSnapshot ; :agentOrigin "SECTOR" ; :metricType "SectorRelativeMomentum" ;
        :rawValue "0.00"^^xsd:decimal ; :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "0.40 (JPM) - 0.40 (Sec_Financials aggregate) = 0.00." .
    :Snap_XOM_SectMom_20260805 a :ScoreSnapshot ; :agentOrigin "SECTOR" ; :metricType "SectorRelativeMomentum" ;
        :rawValue "-0.55"^^xsd:decimal ; :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "0.35 (XOM ScoreTecnico, Snap_XOM_Tec_20260805) - 0.90 (Sec_Energy aggregate) = -0.55 — below VETO_MKT_02's -0.50 threshold." .
    :Snap_JNJ_SectMom_20260805 a :ScoreSnapshot ; :agentOrigin "SECTOR" ; :metricType "SectorRelativeMomentum" ;
        :rawValue "0.00"^^xsd:decimal ; :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "0.30 (JNJ) - 0.30 (Sec_HealthCare aggregate) = 0.00." .
    :Snap_PG_SectMom_20260805 a :ScoreSnapshot ; :agentOrigin "SECTOR" ; :metricType "SectorRelativeMomentum" ;
        :rawValue "0.00"^^xsd:decimal ; :timestamp "2026-08-05T07:15:00"^^xsd:dateTime ;
        rdfs:comment "0.28 (PG) - 0.28 (Sec_ConsumerStaples aggregate) = 0.00." .

    :AAPL :hasScoreObservation :Snap_AAPL_SectMom_20260805 .
    :JPM  :hasScoreObservation :Snap_JPM_SectMom_20260805 .
    :XOM  :hasScoreObservation :Snap_XOM_SectMom_20260805 .
    :JNJ  :hasScoreObservation :Snap_JNJ_SectMom_20260805 .
    :PG   :hasScoreObservation :Snap_PG_SectMom_20260805 .
}
```

- [ ] **Step 2: Extend the existing `ORCHESTRATOR:2026-08-05` graph**

Inside the existing `GRAPH <urn:graph:ingest:ORCHESTRATOR:2026-08-05> { ... }` block, insert the
following immediately before its closing `}` (after the existing `:JPM :triggeredVeto
:Veto_JPM_20260805 .` line):

```turtle

    :Veto_XOM_MKT_20260805 a :Veto ; :appliesRule :Rule_VETO_MKT_02 ; :primaryRule :Rule_VETO_MKT_02 ;
        :decidedAt "2026-08-05T09:15:00"^^xsd:dateTime ;
        rdfs:comment "Single-signal rule (rank 7, added 2026-08-13) — evidence is Snap_XOM_SectMom_20260805's rawValue -0.55 < -0.50. A second, independent veto for XOM alongside 2026-08-04's VETO_FIN_01 — different dates, both legitimately on record." .
    :XOM :triggeredVeto :Veto_XOM_MKT_20260805 .

    # Attractiveness ranking (added 2026-08-13) — computed for every monitored asset regardless
    # of veto status; portfolio construction (roadmap step 8, not yet built) is what would act on
    # both signals together. Formula and full arithmetic: docs/superpowers/specs/2026-08-13-
    # attractiveness-sector-momentum-design.md §3 and §6.
    :Attr_AAPL_20260805 a :AttractivenessSnapshot ; :attractivenessOfAsset :AAPL ;
        :attractivenessScore "0.405"^^xsd:decimal ; :computedAt "2026-08-05T09:16:00"^^xsd:dateTime ;
        :computedWithScheme :WeightScheme_v1 .
    :Attr_JPM_20260805 a :AttractivenessSnapshot ; :attractivenessOfAsset :JPM ;
        :attractivenessScore "0.505"^^xsd:decimal ; :computedAt "2026-08-05T09:16:00"^^xsd:dateTime ;
        :computedWithScheme :WeightScheme_v1 .
    :Attr_XOM_20260805 a :AttractivenessSnapshot ; :attractivenessOfAsset :XOM ;
        :attractivenessScore "0.389"^^xsd:decimal ; :computedAt "2026-08-05T09:16:00"^^xsd:dateTime ;
        :computedWithScheme :WeightScheme_v1 .
    :Attr_JNJ_20260805 a :AttractivenessSnapshot ; :attractivenessOfAsset :JNJ ;
        :attractivenessScore "0.648"^^xsd:decimal ; :computedAt "2026-08-05T09:16:00"^^xsd:dateTime ;
        :computedWithScheme :WeightScheme_v1 .
    :Attr_PG_20260805 a :AttractivenessSnapshot ; :attractivenessOfAsset :PG ;
        :attractivenessScore "0.679"^^xsd:decimal ; :computedAt "2026-08-05T09:16:00"^^xsd:dateTime ;
        :computedWithScheme :WeightScheme_v1 .
    :AAPL :hasAttractivenessSnapshot :Attr_AAPL_20260805 .
    :JPM  :hasAttractivenessSnapshot :Attr_JPM_20260805 .
    :XOM  :hasAttractivenessSnapshot :Attr_XOM_20260805 .
    :JNJ  :hasAttractivenessSnapshot :Attr_JNJ_20260805 .
    :PG   :hasAttractivenessSnapshot :Attr_PG_20260805 .
    # Ranked (most to least attractive): PG (0.679) > JNJ (0.648) > JPM (0.505) > AAPL (0.405) >
    # XOM (0.389) — the two names NOT vetoed on 8/5 (PG, JNJ) rank highest, illustrating that
    # ranking and veto are computed independently even though they correlate here.
```

- [ ] **Step 3: Update the file's header comment**

In the `# Demonstrates...` bullet list near the top of the file, add two bullets after the existing
`VETO_RED_01` bullet:

```
#   - VETO_MKT_02 (single-signal, rank 7, added 2026-08-13) firing for XOM on 2026-08-05, via a
#     new SectorRelativeMomentum signal showing XOM badly lagging its (illustratively strong)
#     Energy sector.
#   - AttractivenessSnapshot ranking all 5 tickers on 2026-08-05 — the positive counterpart to
#     veto, computed independently of veto status.
```

- [ ] **Step 4: Verify the file still parses standalone**

```bash
python -c "import rdflib; g = rdflib.Dataset(); g.parse('instances.trig', format='trig'); print('quads:', len(list(g.quads())))"
```
Expected: prints a quad count with no exception.

---

### Task 5: Full-dataset validation and hand-check

**Files:**
- Read-only: all of `schema/*.ttl`, `schema/*.trig`.
- Create (scratch, not committed to the repo): a temporary validation script in the scratchpad
  directory.

**Interfaces:**
- Consumes: the complete edited schema from Tasks 1–4.
- Produces: pass/fail confirmation gating Task 6 onward.

- [ ] **Step 1: Write the validation script**

Write to `<scratchpad>/validate_attractiveness.py`:

```python
import rdflib
from pyshacl import validate

NS = rdflib.Namespace("https://thesis.local/kg/portfolio#")

# Full dataset parse (mirrors schema/README.md's documented command)
ds = rdflib.Dataset()
for f, fmt in [('tbox.ttl', 'turtle'), ('shapes.ttl', 'turtle'), ('reference.ttl', 'turtle'), ('rules.ttl', 'turtle')]:
    ds.parse(f, format=fmt)
ds.parse('instances.trig', format='trig')
print('quads:', len(list(ds.quads())))

# Flatten to a single data graph for pyshacl (shapes travel with tbox per schema/README.md)
data = rdflib.Graph()
for s, p, o, g in ds.quads():
    data.add((s, p, o))

conforms, results_graph, results_text = validate(data, data_graph_format=None, inference='rdfs', abort_on_first=False)
print('SHACL conforms:', conforms)
if not conforms:
    print(results_text)
assert conforms, "SHACL validation must pass"

# Hand-check 1: VETO_MKT_02 fires for XOM, not for the other 4
xom_mom = float(data.value(NS.Snap_XOM_SectMom_20260805, NS.rawValue))
assert xom_mom < -0.50, f"expected XOM SectorRelativeMomentum < -0.50, got {xom_mom}"
for a in ['AAPL', 'JPM', 'JNJ', 'PG']:
    v = float(data.value(NS[f'Snap_{a}_SectMom_20260805'], NS.rawValue))
    assert v >= -0.50, f"expected {a} SectorRelativeMomentum >= -0.50, got {v}"
assert (NS.XOM, NS.triggeredVeto, NS.Veto_XOM_MKT_20260805) in data

# Hand-check 2: attractivenessScore arithmetic matches the documented formula
weights = {'ScoreFinanciero': (0.25, True), 'ScoreCuantitativo': (0.20, True),
           'ScoreTecnico': (0.20, True), 'Sentiment': (0.20, False), 'SectorRelativeMomentum': (0.15, False)}

def latest_snapshot_value(asset, metric):
    for snap in data.subjects(NS.metricType, rdflib.Literal(metric)):
        if (asset, NS.hasScoreObservation, snap) in data:
            norm = data.value(snap, NS.normalizedScore)
            raw = data.value(snap, NS.rawValue)
            return float(norm) if norm is not None else None, float(raw) if raw is not None else None
    raise LookupError((asset, metric))

expected = {'AAPL': 0.405, 'JPM': 0.505, 'XOM': 0.389, 'JNJ': 0.648, 'PG': 0.679}
for ticker, exp in expected.items():
    asset = NS[ticker]
    score = 0.0
    for metric, (w, inv) in weights.items():
        norm, raw = latest_snapshot_value(asset, metric)
        component = (1 - norm) if inv else (raw + 1) / 2
        score += w * component
    assert abs(score - exp) < 0.005, f"{ticker}: computed {score:.3f}, expected {exp}"
    stored = float(data.value(NS[f'Attr_{ticker}_20260805'], NS.attractivenessScore))
    assert abs(stored - exp) < 0.001, f"{ticker}: stored {stored}, expected {exp}"

print("All hand-checks passed.")
```

- [ ] **Step 2: Run it from `schema/`**

```bash
cd schema
python <scratchpad>/validate_attractiveness.py
```
Expected: `quads: <some number>`, `SHACL conforms: True`, `All hand-checks passed.` — no
`AssertionError`.

- [ ] **Step 3: If anything fails, fix the offending file from Tasks 1–4 and re-run Step 2**

Do not proceed to Task 6 until this passes clean.

---

### Task 6: Regenerate `schema/protege-view.ttl`

**Files:**
- Modify: `schema/protege-view.ttl` (generated — do not hand-edit outside this regeneration)

**Interfaces:**
- Consumes: the validated dataset from Task 5.

- [ ] **Step 1: Read the existing file's generation convention**

Confirm (already read during planning) that every individual sourced from a named graph in
`instances.trig` carries a `:sourceNamedGraph <graph-iri>` annotation, and that `tbox.ttl` /
`reference.ttl` / `rules.ttl` individuals do not (they're not from `instances.trig`'s named
graphs). New individuals from Task 3 (`:Rule_VETO_MKT_02`, `:WeightScheme_v1`, `:WC_*`) get no
`:sourceNamedGraph` tag (same as existing `rules.ttl` individuals); new individuals from Task 4
(everything in `urn:graph:ingest:SECTOR:2026-08-05` and the `ORCHESTRATOR:2026-08-05` additions)
each get `:sourceNamedGraph <urn:graph:ingest:SECTOR:2026-08-05>` or
`<urn:graph:ingest:ORCHESTRATOR:2026-08-05>` respectively, matching the existing pattern for that
graph's other individuals already in the file.

- [ ] **Step 2: Regenerate**

Write to `<scratchpad>/regen_protege_view.py`:

```python
import rdflib

NS = rdflib.Namespace("https://thesis.local/kg/portfolio#")
flat = rdflib.Graph()
flat.bind('', NS)
flat.bind('owl', rdflib.OWL)
flat.bind('rdfs', rdflib.RDFS)
flat.bind('skos', rdflib.Namespace("http://www.w3.org/2004/02/skos/core#"))
flat.bind('xsd', rdflib.XSD)

for f, fmt in [('tbox.ttl', 'turtle'), ('reference.ttl', 'turtle'), ('rules.ttl', 'turtle')]:
    g = rdflib.Graph(); g.parse(f, format=fmt)
    for t in g:
        flat.add(t)

ds = rdflib.Dataset()
ds.parse('instances.trig', format='trig')
for ctx in ds.contexts():
    if str(ctx.identifier).startswith('urn:'):
        for s, p, o in ctx:
            flat.add((s, p, o))
            flat.add((s, NS.sourceNamedGraph, rdflib.URIRef(ctx.identifier)))

flat.serialize(destination='protege-view.ttl', format='turtle')
print('protege-view.ttl regenerated,', len(flat), 'triples')
```

Run from `schema/`: `python <scratchpad>/regen_protege_view.py`

- [ ] **Step 3: Restore the file's header comment**

The `serialize()` call overwrites the hand-written header comment block (lines 1–31 documenting
what this file is and the DO-NOT-edit warning). Re-add that exact header block (read from the
version of the file that existed before this task) above the `@prefix` lines the script wrote —
`rdflib`'s serializer does not preserve comments, so this restoration step is required every time
this file is regenerated, not just this once; note that in the header itself if it doesn't already
say so.

- [ ] **Step 4: Verify**

```bash
python -c "import rdflib; g = rdflib.Graph(); g.parse('protege-view.ttl', format='turtle'); print(len(g))"
```
Expected: parses cleanly; triple count is higher than before this task (new individuals from
Tasks 1–4 are now present).

---

### Task 7: `schema/README.md`

**Files:**
- Modify: `schema/README.md`

- [ ] **Step 1: Add a 4th "refinement found during implementation" entry**

Append to the numbered list in `## Three refinements found during implementation...` (retitle the
heading to `## Refinements found during implementation` since it's no longer exactly three):

```markdown
4. **Shared-property domain collision when reusing `ScoreSnapshot`'s fields for a sibling class.**
   Adding `SectorAggregateSnapshot` (2026-08-13, attractiveness-score feature) needed to reuse
   `metricType`/`agentOrigin`/`timestamp`/`normalizedScore`, but those properties' `rdfs:domain`
   was declared as `:ScoreSnapshot` specifically — reusing them as-is would RDFS-entail that a
   `SectorAggregateSnapshot` individual is also a `:ScoreSnapshot`, contradicting
   `AllDisjointClasses`. Resolved the same way `RuleOperand`/`EvidenceSource` already resolve the
   analogous range problem: a new union class (`:ObservationSnapshot`) widens the four properties'
   domain instead of duplicating them under new names.
```

- [ ] **Step 2: Update the file-to-named-graph table**

Add a row after the `instances.trig` row: no new file, but note `urn:graph:ingest:SECTOR:{date}`
now exists as a graph pattern populated from within `instances.trig`. Amend the `instances.trig`
row's "Contents" cell to end with: `; sector-aggregate and attractiveness-ranking output (added
2026-08-13)`.

- [ ] **Step 3: Update the validation section**

After the existing `rdflib` snippet, add: `` `pyshacl` conformance and hand-verified
attractiveness-score/VETO_MKT_02 arithmetic are checked by the script in Task 5 of
`docs/superpowers/plans/2026-08-13-attractiveness-sector-momentum.md` — re-run it the same way
after any future schema edit that touches `ScoreSnapshot`, `SectorAggregateSnapshot`, or
`AttractivenessSnapshot`. ``

---

### Task 8: `06-ontology-definition.md`

**Files:**
- Modify: `06-ontology-definition.md`

- [ ] **Step 1: Read the file's existing class-count references**

Find every place the file states a total class count (e.g. "22 classes" / "20-class
disjointness") and update each to the new totals from Task 1 Step 6 (26 total classes / 24-member
disjointness — confirm exact numbers against Task 5's validated `tbox.ttl` rather than assuming).

- [ ] **Step 2: Add a new subsection documenting the added classes**

Add a subsection (numbered to follow the existing document's own numbering convention — check the
file's current §-numbering before choosing the number) titled "Attractiveness Ranking and
Sector-Relative Momentum (added 2026-08-13)" covering: the four new classes and their purpose
(one paragraph each, reusing the `rdfs:comment` text from Task 1), the attractiveness-score
formula from spec §3, and an explicit note that position sizing remains out of scope (spec §1).
Cross-reference `docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md` for
full detail rather than duplicating it.

- [ ] **Step 3: Verify**

```bash
grep -n "26\|24-class\|SectorAggregateSnapshot\|AttractivenessSnapshot" 06-ontology-definition.md
```
Expected: the new subsection and updated counts appear; no stale "22 classes"/"20-class" text
remains (re-grep for the old numbers to confirm zero matches outside historical/dated context).

---

### Task 9: `07-ontology-topology.md`

**Files:**
- Modify: `07-ontology-topology.md`

- [ ] **Step 1: Add a new row to the named-graph partitioning table**

```markdown
| `urn:graph:ingest:SECTOR:{date}` | One graph per Sector Agent daily run — `SectorAggregateSnapshot`s and per-asset `SectorRelativeMomentum` `ScoreSnapshot`s (added 2026-08-13, see spec) | **Append-only**, same convention as the other per-agent ingest graphs. |
```

- [ ] **Step 2: Note the `ORCHESTRATOR` graph's expanded contents**

In the existing `urn:graph:ingest:ORCHESTRATOR:{date}` row's "Contents" cell, append: `; also
`AttractivenessSnapshot` individuals (added 2026-08-13) — the Orchestrator's ranking output,
alongside its veto output`.

- [ ] **Step 3: Update the scale-estimate table**

Add a row (or amend the closest existing row) noting the new sources' rough volume:
`SectorAggregateSnapshot` + `SectorRelativeMomentum` + `AttractivenessSnapshot`: ~11 sectors × 500
assets × ~1,000 trading days ≈ low tens of millions combined at full backfill scale — comparable
order of magnitude to the existing daily `ScoreSnapshot` volume already dominating the "15–20M
triples" total; note explicitly that this addition does not change that document's headline
order-of-magnitude conclusion, it's absorbed within it.

- [ ] **Step 4: Verify**

```bash
grep -n "urn:graph:ingest:SECTOR\|AttractivenessSnapshot" 07-ontology-topology.md
```
Expected: both new references present.

---

### Task 10: `08-agent-architecture.md`

**Files:**
- Modify: `08-agent-architecture.md`

- [ ] **Step 1: Update the `MonitoringCycleGraph` node list**

After the existing fan-out's three parallel agent nodes (`quantitative_agent`,
`technical_agent`, `semantic_agent`) and before the `orchestrator` node description, insert:

```markdown
3. `sector_agent` — join node run after the fan-out (needs every asset's `ScoreTecnico` already
   written to compute a per-sector aggregate): reads all `ScoreSnapshot(metricType='ScoreTecnico')`
   individuals for the cycle, groups by `Sector` (via each `Asset`'s `classifiedAs` → `Industry` →
   `memberOfSector` chain), writes one `SectorAggregateSnapshot` per sector plus a per-asset
   `ScoreSnapshot(metricType='SectorRelativeMomentum', agentOrigin='SECTOR')` (added 2026-08-13,
   closes part of critique #3 — see `docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`).
```

Renumber the existing `orchestrator` step to `4.` and add a new sibling step `5.`:

```markdown
5. `compute_attractiveness` — join node, sibling to `orchestrator` (both run after `sector_agent`,
   neither depends on the other): reads the active `AttractivenessWeightScheme` via SPARQL, reads
   each asset's latest snapshots (same snapshot set `orchestrator` reads), computes
   `attractivenessScore` per the weighted-formula convention (§3 of the spec above), writes one
   `AttractivenessSnapshot` per asset — independent of veto status, since ranking and exclusion are
   separate concerns with separate audit trails (added 2026-08-13).
```

- [ ] **Step 2: Update the fan-out/join diagram description**

Wherever the doc describes the fan-out/join shape in prose (near "Fan-out (`Send`) over that set,
three parallel agent nodes per ticker"), update to describe the new
`fan-out → sector_agent → {orchestrator, compute_attractiveness}` shape from spec §7.

- [ ] **Step 3: Update the state schema**

In the `MonitoringCycleState` TypedDict code block, add:

```python
    sector_snapshot_iris: dict[str, str]        # sector -> SectorAggregateSnapshot IRI written this cycle
    attractiveness_iris: dict[str, str]          # ticker -> AttractivenessSnapshot IRI written this cycle
```

- [ ] **Step 4: Update the tool-inventory table**

Add a row: `| Sector | SPARQL `SELECT` (per-asset ScoreTecnico) + SPARQL `INSERT` (SectorAggregateSnapshot, SectorRelativeMomentum) | **New** — no sector roll-up exists anywhere yet. |` and a row for the attractiveness computation similarly under "Orchestrator" or as its own row.

- [ ] **Step 5: Verify**

```bash
grep -n "sector_agent\|compute_attractiveness" 08-agent-architecture.md
```
Expected: both node names appear in the node list, prose diagram description, and (for
`compute_attractiveness`) the tool-inventory table.

---

### Task 11: `critique-and-evolution.md`

**Files:**
- Modify: `critique-and-evolution.md`

- [ ] **Step 1: Annotate gaps #2 and #3 as partially closed**

In the `### A.2 Gaps and issues` section, find gap **#2 (no portfolio-construction layer)** and
gap **#3 (no sector/industry layer)**. Append to each (do not remove the original critique text —
this is a status update, not a rewrite):

For #2: `> **Update (2026-08-13):** the ranking half of this gap is now closed — see
`AttractivenessSnapshot` in `06-ontology-definition.md`'s attractiveness-ranking subsection and
`docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`. Position sizing,
rebalancing cadence, and diversification/correlation constraints remain open.`

For #3: `> **Update (2026-08-13):** a sector-relative-momentum signal (one metric, feeding both a
new veto rule and the attractiveness score) is now implemented — see `SectorAggregateSnapshot`.
The full sector-rotation dashboard (relative-strength-vs-benchmark roll-ups, a dedicated Sector
Agent's broader signal set) described in layer B2 remains open beyond this one signal.`

- [ ] **Step 2: Update the B3/B2 rows in the evolution-layers table**

In `### Part B`'s layer table, append to B2's "Adds" cell: `(sector-relative-momentum signal
implemented 2026-08-13; broader roll-up dashboard still open)`, and to B3's "Adds" cell:
`(attractiveness/ranking score implemented 2026-08-13; sizing module still open)`.

- [ ] **Step 3: Verify**

```bash
grep -n "2026-08-13" critique-and-evolution.md
```
Expected: 4 matches (two gap annotations, two table-cell annotations).

---

### Task 12: `10-integration-roadmap.md`

**Files:**
- Modify: `10-integration-roadmap.md`

- [ ] **Step 1: Update step 0's status line**

Amend the "**0. Formalize ontology TBox + SHACL shapes.** ✅ **Implemented.**" paragraph's class
count (from Task 8's confirmed number) and add one sentence: `Extended 2026-08-13 with an
attractiveness-ranking + sector-relative-momentum feature (4 new classes, a 7th veto rule, a
versioned weight scheme) — see docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md.`

- [ ] **Step 2: Verify**

```bash
grep -n "2026-08-13" 10-integration-roadmap.md
```
Expected: 1 match.

---

### Task 13: Redeploy affected published Artifacts

**Files:**
- None in-repo — this task updates externally hosted HTML artifacts to match the doc changes
  from Tasks 8–12, per this project's established convention (each prior schema change redeployed
  its cited artifacts to the same URLs).

- [ ] **Step 1: List existing artifacts**

Call the `Artifact` tool with `action: "list"` to find the current URLs for: the ontology
definition artifact (06), the ontology topology artifact (07), the agent architecture artifact
(08), the integration roadmap artifact (10), and the interactive ontology visualization dashboard.
(09's NLP artifact is unaffected by this feature — skip it.)

- [ ] **Step 2: Update each artifact's HTML source and redeploy to the same URL**

For each of the 4 docs + the visualization dashboard: locate the local HTML source file used to
generate that artifact (if one exists in a prior session's scratchpad, otherwise reconstruct the
relevant section), apply the same content changes made to the corresponding `.md` file in Tasks
8–12 (new subsection / table row / status line), and redeploy via `Artifact` with the **same
`url`** parameter so the existing link stays live. For the visualization dashboard specifically:
add the 4 new classes as nodes (zone: likely a new "ranking" zone alongside the existing
reference/core/observations/evidence/people/decision/rule-tree/portfolio zones from the prior
session, or folded into "decision" alongside `Veto`) with their edges to `Asset`/`Sector`.

- [ ] **Step 3: Confirm each redeploy**

After each `Artifact` call, confirm the tool response shows success and the URL matches the one
found in Step 1 (not a newly minted URL) — a different URL means it published as a separate
artifact instead of updating in place, which is the failure mode to avoid per this project's own
artifact-update convention.

---

## Self-Review Notes (for the plan author, not a task)

- **Spec coverage:** §2 (classes/properties) → Task 1; §3 (formula) → Tasks 1+4+5; §4 (SHACL) →
  Task 2; §5 (VETO_MKT_02) → Task 3; §6 (worked example) → Task 4; §7 (agent architecture) → Task
  10; §8 (named graphs) → Task 4 (data) + Task 9 (docs); §9 (validation) → Task 5; §10 (doc/artifact
  updates) → Tasks 7–13; §11 (open questions) → addressed inline in Task 1 (the domain-collision
  fix) and Task 3 (weight values left as an easy one-line change, not re-designed).
- **Domain-collision fix** was not in the original spec text — added to Global Constraints and
  Task 1 explicitly so it isn't lost, per this project's own convention of flagging
  discovered-during-implementation issues inline rather than silently.
