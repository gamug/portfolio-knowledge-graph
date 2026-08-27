# skills/

The methodology skills used to produce the 2026-08-23 taxonomic integrity and quality
pass on this ontology. They are reusable, domain-agnostic persona prompts — not part of the
ontology artifact itself — kept here so the analysis records that cite them resolve to a
checked-in file.

| Skill | Role | Used to produce |
|---|---|---|
| `ontologies/SKILL.md` | Ontology & Knowledge Graph Engineer — path-based taxonomy construction (root → broad → mid → leaf), then prune/acyclicity/quality gates | `new_ontology/taxonomy-v1.md`, and the `rdfs:subClassOf` backbone merged into `schema/tbox.ttl` §1.2 |
| `ontology_quality/SKILL.md` | Ontology Quality Auditor — five evaluation gates (literal, fuzzy-semantic, pairwise-relation, neighborhood-consistency, acyclicity/rooting) | `new_ontology/critical-evaluation.md`, `schema/taxonomy-quality-review-2026-08-23.md` |

Cross-references: `../new_ontology/`, `../schema/taxonomy-quality-review-2026-08-23.md`,
`../06-ontology-definition.md` §1.2.
