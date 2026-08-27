# Taxonomy Quality Review — 2026-08-23

Applies `skills/ontologies/SKILL.md` Phases 3–5 to the class taxonomy added to `tbox.ttl`/
`reference.ttl` this session (§1.2/§1.9 of `06-ontology-definition.md`). Every check below was run
programmatically against the real files with `rdflib` — nothing here is asserted from memory or
from re-reading the prose. Scripts are reproducible; queries and full output are in this session's
transcript. This review found and fixed one real defect (severity: high — see Finding 1) before
writing up a clean pass; it is not a rubber stamp.

## Method

Built the local `rdfs:subClassOf` graph over all 37 `owl:Class` declarations in `tbox.ttl` +
`reference.ttl`, then ran: cycle detection (DFS, white/gray/black coloring), self-loop scan,
root-reachability (does every class have a path to one of the 6 taxonomy roots?), multi-parent
detection, depth measurement (edges from each of the 24 leaves to its root), leaf-count-per-category
density, and a label near-duplicate scan (word-set subset comparison over `rdfs:label`, with
camelCase splitting for classes checked only by IRI).

## Phase 3 gate — pruning rules

| Rule | Result |
|---|---|
| Self-loop removal | **Pass** — 0 self-loops (`s = o` on `rdfs:subClassOf`) found among 37 classes. |
| Inverse-edge resolution | **N/A** — the taxonomy is a hand-asserted DAG, not aggregated from weighted paths; no bidirectional pairs exist to resolve. |
| Relative thresholding / top-p pruning | **N/A** — same reason; nothing here is frequency-weighted. |
| Isolated node cleanup | **Pass** — 0 of 37 classes fail to reach one of the 6 taxonomy roots (checked by recursive parent-chain walk, not assumed). |

## Phase 4 gate — acyclicity & consistency

**Pass.** 0 cycles found by DFS over the local `subClassOf` graph. Cross-checked against the
pre-existing `owl:AllDisjointClasses` axiom (24 members): confirmed `rdfs:subClassOf` (vertical) and
`AllDisjointClasses` (horizontal, sibling-only) remain orthogonal — none of the 13 new taxonomy
classes appear in the disjoint list, and no new triple asserts two disjoint siblings as mutually
subsuming.

**Also checked, not part of the skill's checklist but relevant to consistency:** whether any new
`rdfs:subClassOf` edge, layered on a class still defined via `owl:unionOf`, could make that class
DL-unsatisfiable (a stronger failure mode than a cycle — see Background below). None remain: the
three affected classes (`ObservationSnapshot`, `EvidenceSource`, `RuleOperand`) were converted from
`owl:unionOf` to plain `owl:Class` + `rdfs:subClassOf` assertions specifically to eliminate this risk
before any subclass edges were added to them.

## Phase 5 gate — quality self-reflection

### Semantic Fidelity (fuzzy match)

**Pass, with one disclosed borderline case.** Label near-duplicate scan found 8 parent/child pairs
where a child's label textually contains its direct parent's label plus one differentiating word
(e.g. `Observation` → `Observation Snapshot`, `Evidence` → `Evidence Source`). All 8 are genuine
is-a relationships with different extensions, not synonym duplication — this is the expected,
correct pattern for a taxonomy (specific = general + differentiator), not a fidelity violation. No
case was found of two *different* concepts sharing a name via spelling/casing drift, which is what
this gate actually guards against.

**Finding — disclosure gap, not a structural defect.** `new_ontology/taxonomy-v1.md` (the standalone
design record) claimed "every leaf has exactly one parent path" as a deliberate, unqualified design
choice. That was inaccurate even at the time: `Sector`/`Industry` were already dual-parented
(`skos:Concept`, pre-existing in `tbox.ttl` since before this taxonomy work started) and — see
Finding 1 — `RuleClause` needed to be. **3 of 24 leaves are legitimately multi-parented, not 0.**
Corrected in place in that document with a dated note rather than silently rewritten.

### Structural Integrity

**Pass, after one fix.**

- Fully connected to root: **confirmed** — all 37 classes (24 leaves + 13 taxonomy classes) reach
  one of the 6 broad categories via a finite parent chain; 0 orphans.
- No cycles: **confirmed**, DFS-verified, see Phase 4 above.
- No isolated clusters: **confirmed** — every leaf's category assignment was cross-checked against
  `06-ontology-definition.md` §1.2's table; all 24 map to the documented category with no drift,
  after Finding 1 was fixed.

**Finding 1 (severity: high, found and fixed).** Three artifacts describing the same fact —
`RuleClause`'s taxonomic parentage — disagreed with each other:

| Artifact | Said |
|---|---|
| `06-ontology-definition.md` §1.2.1 (the design spec, written first) | `RuleClause rdfs:subClassOf :RuleSystem` **and** (§1.1) implicitly via `RuleOperand`'s membership — i.e., dual-parent |
| `saved_resource.html` (diagram, built from the spec) | Dual-parent — matches the spec |
| `tbox.ttl` (the actual formal ontology, edited separately when the real files arrived) | **Single**-parent — only `RuleOperand`, missing the `RuleSystem` edge |

The real ontology file was the odd one out, and it's the one that matters most — a diagram or a
markdown table describing a hierarchy the `.ttl` doesn't actually contain is a documentation bug at
best and a trust-destroying inconsistency at worst, exactly the failure mode a structural-integrity
gate exists to catch. **Root cause:** the taxonomy was drafted once against `06-ontology-definition.md`
(before the real `schema/` files existed), then re-implemented from scratch directly in `tbox.ttl`
once they arrived — and the re-implementation silently dropped one edge instead of being diffed
against the original spec. **Fix:** added the missing `:RuleClause rdfs:subClassOf :RuleSystem .`
triple to `tbox.ttl` (comment explains why it's a deliberate exception, not an oversight, going
forward). Re-verified: `rdflib` parses clean (1608 quads, +1 from the baseline 1607), `pyshacl`
conforms `True`. All three artifacts now agree.

### Alignment to Task

**Pass, with precision corrections applied.**

- **Depth:** the path notation (`Root -> Broad -> Mid -> Leaf`) has 4 segments, but "Root" isn't a
  real `owl:Class` — measured directly against `tbox.ttl`'s edges, actual maximum depth is **2**
  (leaf → mid → broad, or leaf → broad directly). Both numbers are true; only one was being stated,
  which read as more structural depth than exists. Corrected in `new_ontology/taxonomy-v1.md`.
- **Density:** 24 leaves over 6 broad categories = exactly 4.0 leaves/category on average (6, 3, 4,
  2, 7, 2 — measured, not estimated), matching the "~4 leaves/category" claim precisely. Not
  over-decomposed (no singleton categories except where a real semantic distinction justified one —
  `ClassificationConcept` and `Collection` each hold exactly 2, both legitimate).
- **Scope match:** a thesis-scope, single-namespace, 24-class formal ontology warrants a shallow,
  hand-verifiable taxonomy over a deep, machine-generated one — the actual shape (depth 2, 6+4
  categories) fits that scope; a deeper tree would have been the over-engineering this task's own
  written guidance warns against.

## Bonus finding — outside this taxonomy's scope, flagged not fixed

`07-ontology-topology.md`'s Reasoning Profile section states the GICS taxonomy has "~11 sectors,
~70 industries." The real `reference.ttl` has 11 sectors and **26** industry-group individuals — not
close to 70. This is very likely a pre-existing tier-name conflation (real-world GICS has ~24–25
*Industry Groups* at the level this file actually populates, and ~74 *Industries* one tier deeper —
a different, unpopulated tier). Predates this taxonomy work and isn't part of what "the created
ontology" refers to in this review's scope, so left as a flag for whoever next edits that document
rather than corrected here.

## Verdict

All four gates pass as of this review. One high-severity cross-artifact inconsistency was found and
fixed at its root cause (the real `.ttl`, not the documentation describing it), with full
`rdflib`/`pyshacl` re-verification after the fix (1608 quads, conforms: True). One disclosure gap in
a superseded design document was corrected rather than left standing. One precision overstatement
(depth) was corrected. Nothing in this pass required touching the pre-existing 24 classes' own
properties, cardinalities, or SHACL shapes — consistent with this taxonomy work's stated additive
scope throughout.
