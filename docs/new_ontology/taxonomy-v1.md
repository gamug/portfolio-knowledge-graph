> **Merged 2026-08-23** into `../06-ontology-definition.md` §1.2/§1.2.1 (and, for
> `metricType`, the new §1.9). Kept here as the standalone record of the skill-driven derivation.

# Portfolio KG — Taxonomic Backbone (v1)

Built with `skills/ontologies/SKILL.md`'s methodology, applied to the previous agent work
(`06-ontology-definition.md`'s 27-class inventory) as the source data, rather than to fresh
unstructured text. This is an **additive** layer on top of the existing ontology — see
`critical-evaluation.md` for why it's needed and what it does/doesn't change. Nothing here alters
an existing class's own properties, cardinalities, or SHACL shape; it only adds `rdfs:subClassOf`
edges (new) and upgrades three existing union classes in place (same IRIs).

## Phase 1 — Task parsing & root concept

**Domain:** the Portfolio Knowledge Graph ontology (`https://thesis.local/kg/portfolio#`) — an
S&P 500 portfolio construction-and-maintenance system's RDF/OWL TBox.

**Root concept:** `Portfolio Knowledge Graph` (documentation-level root; formally, all classes
below remain `rdfs:subClassOf owl:Thing` as usual — no new root *class* is introduced, since OWL
already provides one and adding a redundant named root would be pure ceremony for a 24-class TBox).

**Source concepts isolated:** the 24 mutually-disjoint domain classes from
`06-ontology-definition.md` §1.2 (listed in Phase 2 below), plus the 3 existing union/domain-
widening classes (`ObservationSnapshot`, `EvidenceSource`, `RuleOperand`) that are upgraded rather
than left as excluded helpers. No spelling/casing variants were found among the 24 — the previous
work's own naming was already internally consistent (see `critical-evaluation.md` finding #5 for
the one *cross-language* naming issue, which is a metric-value concern, not a class-name one).

## Phase 2 — Path-based taxonomy

```
Portfolio Knowledge Graph -> Domain Entity -> Asset
Portfolio Knowledge Graph -> Domain Entity -> Executive
Portfolio Knowledge Graph -> Domain Entity -> Classification Concept -> Sector
Portfolio Knowledge Graph -> Domain Entity -> Classification Concept -> Industry
Portfolio Knowledge Graph -> Domain Entity -> Collection -> Universe
Portfolio Knowledge Graph -> Domain Entity -> Collection -> Portfolio

Portfolio Knowledge Graph -> Temporal Relation -> UniverseMembership
Portfolio Knowledge Graph -> Temporal Relation -> PortfolioPosition

Portfolio Knowledge Graph -> Observation -> Observation Snapshot -> ScoreSnapshot
Portfolio Knowledge Graph -> Observation -> Observation Snapshot -> SectorAggregateSnapshot
Portfolio Knowledge Graph -> Observation -> Observation Snapshot -> AttractivenessSnapshot
Portfolio Knowledge Graph -> Observation -> PriceObservation

Portfolio Knowledge Graph -> Evidence -> Source Document -> SECFiling
Portfolio Knowledge Graph -> Evidence -> Evidence Source -> NewsArticle
Portfolio Knowledge Graph -> Evidence -> Evidence Source -> SECFilingSection

Portfolio Knowledge Graph -> Risk And Decision -> RiskEvent
Portfolio Knowledge Graph -> Risk And Decision -> Veto

Portfolio Knowledge Graph -> Rule System -> RuleDefinition
Portfolio Knowledge Graph -> Rule System -> RuleClause
Portfolio Knowledge Graph -> Rule System -> Rule Operand -> ThresholdComparison
Portfolio Knowledge Graph -> Rule System -> Rule Operand -> CategoricalComparison
Portfolio Knowledge Graph -> Rule System -> Rule Operand -> GraphPredicate
Portfolio Knowledge Graph -> Rule System -> Attractiveness Scheme -> AttractivenessWeightScheme
Portfolio Knowledge Graph -> Rule System -> Attractiveness Scheme -> WeightComponent
```

24 leaves, matching all 24 disjoint classes in `06-ontology-definition.md` §1.2 exactly (none
added, none dropped, none duplicated). 6 broad categories, 4 mid-level categories — kept shallow
(max 4 segments in this path notation: Root/Broad/Mid/Leaf) to match a 24-class ontology; a deeper
tree would be over-engineering relative to the source's own scale. **Precision note (2026-08-23
review pass):** "Root" here is documentation-only, not a real `owl:Class` — measured directly
against `tbox.ttl`'s actual `rdfs:subClassOf` edges, the real maximum depth is **2 edges**
(leaf → mid → broad, or leaf → broad directly), not 4. The two numbers describe different things
(path-notation segments vs. graph edges) and both are correct, but stating only "4" without that
distinction risked overstating the structure's depth.

**Correction (2026-08-23 review pass):** this claim held for the 24 leaves as originally drafted
here, but two things surfaced once the real `tbox.ttl` existed to check against: `Sector`/`Industry`
were already dual-parented (`skos:Concept`, pre-existing, unrelated to this taxonomy) before this
document was written, and `RuleClause` turned out to need a genuine second parent too (`RuleOperand`,
since a clause can nest inside another clause — added to `tbox.ttl` during the review, see
`schema/README.md`). 3 of 24 leaves are legitimately multi-parented, not 0. The design principle
below (placement by structural criterion, kept as a tree wherever that's sufficient) still holds —
it just isn't *always* sufficient, and this document originally overstated that it was.

**Design choice — single inheritance, deliberately, with two pre-existing and one discovered
exception (see correction above).** Every other leaf has exactly one parent path, even
where a thematic case exists for two (e.g. `AttractivenessSnapshot` is both "an Observation-shaped
thing" and "an Orchestrator decision output" alongside `Veto`). Single inheritance was chosen to
keep the hierarchy a clean tree rather than a general DAG, mirroring the previous work's own
preference for auditable, unambiguous structure over cleverness (the same instinct that produced
the `RuleClause` tree fix for the ∧/∨ precedence bug). `AttractivenessSnapshot` is placed under
`Observation Snapshot` because it shares that class's exact property shape (timestamped,
`computedAt`, immutable, one-per-cycle) — that's a structural criterion, not a thematic one, and
structural criteria are what should decide is-a placement.

## Phase 3 — Graph aggregation & pruning

Applied mechanically, per the skill's rules, even though a hand-built 24-leaf tree rarely triggers
any of them:

1. **Self-loop removal:** none present (every edge is strictly parent→child).
2. **Inverse-edge resolution:** no bidirectional pairs exist — this is a tree, not a general graph.
3. **Relative thresholding / top-p pruning:** not applicable — every edge here is asserted, not
   frequency-weighted from aggregated text extraction, so there is no low-weight tail to prune.
4. **Isolated node cleanup:** none — all 24 leaves and 11 new intermediate classes connect back to
   the root through exactly one path (verified by construction in Phase 2).

## Phase 4 — Acyclicity & consistency

Strict tree ⇒ trivially a DAG. Cross-checked against the existing `owl:AllDisjointClasses` axiom
over the 24 classes: `rdfs:subClassOf` (vertical) and `owl:AllDisjointClasses` (horizontal, between
siblings) are orthogonal OWL constructs — adding these edges does not create, and cannot create, a
disjointness violation, since no leaf is placed under more than one parent and no two classes
sharing a parent were already asserted disjoint *from that parent* (only from each other, which
`AllDisjointClasses` already covers and this addition doesn't touch).

## Phase 5 — Quality gate

- **Semantic fidelity:** no synonym collisions — each of the 24 source classes maps to exactly one
  leaf; no concept is represented twice under different labels.
- **Structural integrity:** fully connected to the root, acyclic, zero isolated clusters (all
  checked above).
- **Alignment to task:** depth (max 4) and density (6 broad categories over 24 leaves, 4 mid-level
  categories, ~4 leaves/broad-category average) match a thesis-scope, single-namespace ontology — not over-decomposed into
  categories with one member each (the only two-item categories, `Classification Concept` and
  `Collection`, were kept because they mark a real semantic distinction — SKOS-backed reference
  data vs. named pools — not padding).

---

## Output format 1 — standardized path list

See Phase 2 above (already in the required flat, bulleted, Root→Leaf form).

## Output format 2 — RDF/Turtle (`rdfs:subClassOf`)

Drop-in addition to `schema/tbox.ttl`. Uses the ontology's existing namespace and prefixes;
introduces 11 new classes and re-parents the 24 existing ones. The three existing union classes
(`ObservationSnapshot`, `EvidenceSource`, `RuleOperand`) are **upgraded in place** — same IRI,
same intent, changed from an excluded `owl:unionOf` helper to an ordinary, instantiable
superclass — rather than duplicated under new names.

```turtle
@prefix :     <https://thesis.local/kg/portfolio#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .

### Broad categories (new)
:DomainEntity    a owl:Class ; rdfs:label "Domain Entity"@en .
:TemporalRelation a owl:Class ; rdfs:label "Temporal Relation"@en .
:Observation      a owl:Class ; rdfs:label "Observation"@en .
:Evidence          a owl:Class ; rdfs:label "Evidence"@en .
:RiskAndDecision    a owl:Class ; rdfs:label "Risk and Decision"@en .
:RuleSystem          a owl:Class ; rdfs:label "Rule System"@en .

### Mid-level categories
:ClassificationConcept a owl:Class ; rdfs:subClassOf :DomainEntity ;
    rdfs:label "Classification Concept"@en ;
    rdfs:comment "GICS-aligned reference concepts. Their internal Sector/Industry hierarchy is a parallel skos:broader tree over skos:Concept individuals, not further rdfs:subClassOf structure — kept separate deliberately; see reference.ttl." .

:Collection a owl:Class ; rdfs:subClassOf :DomainEntity ; rdfs:label "Collection"@en .

:SourceDocument a owl:Class ; rdfs:subClassOf :Evidence ; rdfs:label "Source Document"@en .

:AttractivenessScheme a owl:Class ; rdfs:subClassOf :RuleSystem ;
    rdfs:label "Attractiveness Scheme"@en .

### Upgraded union classes (same IRIs as the existing owl:unionOf helpers; membership widened
### where noted; no longer excluded from typing — individuals MAY now be queried by these types)

:ObservationSnapshot a owl:Class ; rdfs:subClassOf :Observation ;
    rdfs:label "Observation Snapshot"@en ;
    rdfs:comment "Upgraded from owl:unionOf(:ScoreSnapshot :SectorAggregateSnapshot), previously excluded from AllDisjointClasses and never used as an individual's rdf:type (06-ontology-definition.md §1.8). Now an ordinary superclass, broadened to include :AttractivenessSnapshot as a third member — all three share the immutable/timestamped/agent-or-orchestrator-authored observation shape. rdfs:domain entailment for metricType/agentOrigin/timestamp/normalizedScore is preserved identically under subClassOf." .

:EvidenceSource a owl:Class ; rdfs:subClassOf :Evidence ;
    rdfs:label "Evidence Source"@en ;
    rdfs:comment "Upgraded from owl:unionOf(:NewsArticle :SECFilingSection) the same way; this is the backedBy range." .

:RuleOperand a owl:Class ; rdfs:subClassOf :RuleSystem ;
    rdfs:label "Rule Operand"@en ;
    rdfs:comment "Upgraded from owl:unionOf(:ThresholdComparison :CategoricalComparison :GraphPredicate) the same way; this is the operand1/operand2 range." .

### Existing 24 classes — additive subClassOf edges only. No change to any class's own
### declaration, properties, or the existing AllDisjointClasses axiom.

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

## Appendix — a second, smaller taxonomy (not built here, flagged only)

`metricType` values observed across the docs (`ScoreFinanciero`, `ScoreCuantitativo`,
`ScoreTecnico`, `Sentiment`, `SectorRelativeMomentum`, `NEWS_SENTIMENT_FINBERT`) are free strings,
not modeled as a controlled vocabulary — the same situation GICS sectors were in before
`reference.ttl` gave them a `skos:ConceptScheme`. If this becomes worth formalizing, the existing
GICS pattern is the template: a `:MetricType` `skos:ConceptScheme` with one `skos:Concept` per
value, and `ScoreSnapshotShape` tightened from an open string to `sh:in` over that scheme's
members. Not built here since it's a property-value taxonomy, not a class taxonomy, and is a
smaller, separable piece of follow-up work.
