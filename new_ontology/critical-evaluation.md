> **Merged 2026-08-23.** This proposal has been applied directly to the previous work — see
> `../06-ontology-definition.md` §1.2/§1.9, `../07-ontology-topology.md`'s Reasoning
> Profile, and the dated update note in `../critique-and-evolution.md` gap #9. Kept here
> as the standalone record of the analysis that produced those edits.

# Critical Evaluation of the Previous Work — Taxonomic/Ontological Structure

**Scope of this review.** `critique-and-evolution.md` already did a rigorous critique of the *v1*
source document (`Avance arquitectura del sistema.docx`) against portfolio-construction
requirements, and the numbered docs (`06`–`10`) already record several "gaps discovered during
implementation." That work is good and is **not** repeated here. This document applies a
different, narrower lens — the one `skills/ontologies/SKILL.md` is built for: is the class
inventory actually organized as a **taxonomy** (a rooted, is-a hierarchy), independent of whether
its entities/properties/constraints are well designed (they mostly are)?

**Verdict up front:** the entity/relationship modeling, temporal design, and SHACL/OWL split are
genuinely strong and should not be rewritten. But **taxonomically, the ontology is flat.** There
is not one `rdfs:subClassOf` edge among the 24 mutually-disjoint domain classes anywhere in the
documented design. That is a real, fixable, additive gap — not a symptom of bad modeling — and
it's the specific thing this review adds on top of the existing critique.

---

## What's right (confirmed, not re-litigated)

- Graph/compute separation, immutable `ScoreSnapshot` observations, n-ary reification for
  temporal relations, named-graph transaction-time, and the `RuleClause` tree fix for the ∧/∨
  precedence bug are all sound design decisions, independently validated (`pyshacl` conforms,
  Python re-execution of the rule trees matches expected firings). No change recommended to any
  of this.
- The OWL-vs-SHACL split (open-world inference vs. closed-world validation) is used correctly and
  consistently.

## New findings — taxonomic structure

**1. Zero `rdfs:subClassOf` edges among the ontology's own 24 disjoint classes.**
`06-ontology-definition.md` §1.2 lists all 27 classes as one flat table, differentiated only by
`owl:AllDisjointClasses` — a *horizontal* partition (these things are mutually exclusive), not a
*vertical* hierarchy (these things are kinds of that thing). The only real subclass hierarchy in
the whole design is GICS `Sector`/`Industry`, and that's a `skos:broader` tree over `skos:Concept`
individuals, not an `owl:Class`/`rdfs:subClassOf` structure at all. For an artifact repeatedly
called "the ontology," there is no taxonomic backbone over its own domain classes.

This is not just a documentation nicety. `07-ontology-topology.md`'s Reasoning Profile explicitly
turns **on** `rdfs:subClassOf` transitivity as a named feature ("so `Industry → Sector` roll-up
queries work") — but the only place that reasoning switch pays off is the SKOS-adjacent GICS
taxonomy (~11 sectors, ~70 industries). The 24 first-party TBox classes get zero benefit from a
reasoning feature the design explicitly turns on. That's an inconsistency between what the
topology doc says the store is configured to do and what the TBox actually gives it to do.

**2. The three union-class workarounds are a property-domain patch fighting the disjointness
design, not a taxonomic commitment.** `06-ontology-definition.md` §1.8 documents this pattern
directly: `ObservationSnapshot = owl:unionOf(:ScoreSnapshot :SectorAggregateSnapshot)`,
deliberately **excluded** from `AllDisjointClasses`, and **never used as an individual's
`rdf:type`** — purely a mechanism to widen `rdfs:domain` for four reused properties
(`metricType`/`agentOrigin`/`timestamp`/`normalizedScore`) without re-declaring them twice. The
same pattern is reused for `RuleOperand` (unions `ThresholdComparison`/`CategoricalComparison`/
`GraphPredicate`) and `EvidenceSource` (unions `NewsArticle`/`SECFilingSection`).

This works, but it's strictly weaker than the alternative that was available: making these ordinary
`rdfs:subClassOf` parents instead of `owl:unionOf` helpers gets the same domain-widening (RDFS
domain entailment propagates through `subClassOf` exactly as it did through `unionOf`, since every
individual typed e.g. `:ScoreSnapshot` becomes entailed `:Observation` either way) **plus** a
queryable, reasoner-visible category (`?x a :Observation` becomes a valid, answerable query — it
isn't today) **at no cost to the existing disjointness axiom**, since sibling disjointness and
parent-child `subClassOf` are orthogonal in OWL. The design paid RDF's binary-triple tax twice: once
legitimately, for n-ary relations (`UniverseMembership`, `PortfolioPosition` — correctly reified,
no complaint there), and once unnecessarily, for shared-property domains, where a plain subclass
edge was available and cheaper. This is the single most actionable finding in this review — see
`taxonomy-v1.md` for the concrete fix, which upgrades these same three class IRIs in place.

**3. Implicit groupings were never promoted, despite already sharing property shapes.**
`CLAUDE.md`'s own conventions section calls out that `validFrom`/`validTo` is "closed by writing
`validTo` on the old record" as a pattern reused across `UniverseMembership`, `PortfolioPosition`,
and `RuleDefinition` — i.e., the project already recognizes these three as instances of one
recurring shape. The ontology never reifies that recognition as a shared superclass (or even a
shared SHACL property group). Same story for the observation shape
(`ScoreSnapshot`/`SectorAggregateSnapshot`/`AttractivenessSnapshot` — flagged directly above) and
for the evidence shape (`NewsArticle`/`SECFilingSection`, both reachable via `backedBy`). The skill
being applied here (`skills/ontologies/SKILL.md`, Phase 1.3) calls this out directly as the thing
to fix: "merge redundant variations... into single canonical nodes." The previous work stopped one
step short of doing that for its own class layer, despite doing exactly this discipline correctly
for GICS sector/industry naming.

**4. No documented root concept.** The skill's Phase 1 requires formulating a canonical root before
extracting nodes. Nothing in `06`–`10` states one — classes float directly under implicit
`owl:Thing`, ungrouped. Practically, this means a future contributor adding class #28 has no
taxonomy to consult for "where does this kind of thing go" — they'd have to re-read all 27 rows of
the table and guess by analogy. A shallow, 2–3 level broad-category layer (proposed in
`taxonomy-v1.md`) turns that into a lookup.

**5. Minor — mixed-language labeling, unaddressed.** Spanish-origin identifiers survive into the
formal layer unremarked: rule mechanism names in `critique-and-evolution.md`'s table
(`ScoreFinanciero`, `ScoreTécnico`) and the original `PERTENECE_A_UNIVERSO` edge label coexist with
English class/property names everywhere else (`Asset`, `ScoreSnapshot`, `membershipAsset`). Given
`rules.ttl`'s `metricName` values are still the Spanish strings (`ScoreFinanciero`, per `06`'s own
worked example in §1.5), this is a live naming-consistency issue in the data, not just historical
color — worth a stated translation/glossary decision (keep Spanish `metricName` values as a
controlled vocabulary and document it, or translate) rather than leaving it implicit. Low severity,
flagged for completeness since the skill's Phase 1.3 explicitly calls out
spelling/casing/synonym standardization.

**6. A second, smaller taxonomy gap: `metricType` values are untyped strings.** The `metricType`
values observed across the docs (`ScoreFinanciero`, `ScoreCuantitativo`, `ScoreTecnico`,
`Sentiment`, `SectorRelativeMomentum`, `NEWS_SENTIMENT_FINBERT`) are free strings validated (per
`ScoreSnapshotShape`, implied) only by membership in a closed set — the same situation GICS
sectors were in before being modeled as SKOS. The project already has the exact pattern needed
(`reference.ttl`'s GICS `skos:ConceptScheme`) sitting unused for this second, smaller taxonomy.
Flagged as a nice-to-have, not a blocker — sketched briefly in `taxonomy-v1.md`'s appendix.

## Quality-gate self-check (skill Phase 5, applied to the *previous* work)

- **Semantic fidelity:** no synonym-duplication problems found — the 24-class inventory has no two
  classes naming the same concept twice. Good.
- **Structural integrity:** the ABox/property layer is fully connected and cycle-free (confirmed by
  `pyshacl` conformance and the independent Python re-execution). The **class layer**, however, is
  not a connected structure at all in the taxonomic sense — it's 24 disconnected roots directly
  under `owl:Thing`. This is the finding this review is centered on.
- **Alignment to task:** for a thesis ontology whose primary claims are about entity/relationship
  modeling, temporal correctness, and rule determinism, the taxonomic gap didn't block any of the
  stated goals — which is presumably why it wasn't caught earlier. It becomes relevant now because
  the current task is specifically to produce a well-structured taxonomy on top of this work.

## What NOT to change

Per the previous work's own stated philosophy ("the v1 core... is sound and should not be
rewritten. The evolution... is additive"), the same discipline applies here one layer up: no
existing class, property, shape, or individual is renamed, removed, or redefined by this review.
`taxonomy-v1.md` adds `rdfs:subClassOf` edges and a small number of new intermediate classes; it
upgrades three existing union classes in place (same IRIs, broader membership, no longer excluded
from typing) and touches nothing else. It is designed to be pasted into `schema/tbox.ttl` without
requiring a re-run of the `pyshacl`/`rdflib` validation story documented in `schema/README.md` —
new `subClassOf` triples don't interact with `sh:NodeShape` targets, which target the leaf classes
directly.
