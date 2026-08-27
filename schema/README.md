# Portfolio Knowledge Graph — Schema Implementation

Implements `06-ontology-definition.md` and `07-ontology-topology.md` as loadable OWL/SHACL/TriG.
Supersedes the earlier single-file `schema/portfolio-kg.ttl` sketch, split here per the topology
document's named-graph design — and extended with four refinements that only became visible while
actually building it (each flagged inline in the file that surfaced it, and summarized below).

## File-to-named-graph map

| File | Format | Loads into | Contents |
|---|---|---|---|
| `tbox.ttl` | Turtle | `urn:graph:tbox` | Classes, properties, OWL cardinality restrictions. |
| `shapes.ttl` | Turtle | `urn:graph:tbox` | SHACL data-quality shapes (kept as a separate file/concern from `tbox.ttl` — OWL semantics vs. SHACL validation, see below). |
| `reference.ttl` | Turtle | `urn:graph:reference` | GICS sector/industry taxonomy + asset master data (5 worked-example tickers). |
| `rules.ttl` | Turtle | `urn:graph:rules:catalog` | The 7-rule veto catalog: v1's original 6 rules plus `VETO_MKT_02` (added 2026-08-13), as unambiguous `RuleClause` trees. |
| `instances.trig` | **TriG** | *(self-describing — see below)* | Dated ABox: universe membership, agent snapshots, evidence, vetoes, filings, portfolio; sector-aggregate and attractiveness-ranking output (added 2026-08-13). |

`instances.trig` is TriG, not Turtle — it contains explicit `GRAPH <urn:graph:...> { ... }` blocks,
so it's the one file that's self-describing about which named graph each triple belongs to. Every
other file loads wholesale into the single graph named in the table. No new file was added for the
attractiveness-ranking feature: its `urn:graph:ingest:SECTOR:{date}` graph pattern is populated
from within `instances.trig` like every other per-agent ingest graph.

**Load order for a fresh GraphDB/Fuseki repository:** `tbox.ttl` → `shapes.ttl` → `reference.ttl`
→ `rules.ttl` → `instances.trig`. Nothing strictly requires this order at load time (a quad store
doesn't validate on ingest unless SHACL validation is explicitly turned on), but it matches
dependency order and is the sequence `10-integration-roadmap.md` step 1 assumes.

## Why both OWL restrictions (`tbox.ttl` §4) and SHACL shapes (`shapes.ttl`)

They answer different questions and neither substitutes for the other:

- **OWL** (`tbox.ttl`) is open-world: a cardinality restriction lets a reasoner *infer* things
  (e.g. "this RuleClause's second operand, if unstated, still logically exists somewhere") but
  never *rejects* incoming data for missing a required property.
- **SHACL** (`shapes.ttl`) is closed-world validation: it's what a real ingestion pipeline runs
  against incoming data before accepting it — missing `operand2` on a `RuleClause` is a validation
  failure, not an inference opportunity.

A thesis-grade ontology benefits from stating both: OWL for what the classes *mean*, SHACL for
what the store *enforces*.

## Refinements found during implementation (not anticipated in the design docs)

1. **Two new leaf types.** `06-ontology-definition.md` §1.5 only worked through `VETO_COMP_01`,
   whose leaves are all numeric. Encoding the full 6-rule catalog (`rules.ttl`) surfaced that
   `VETO_LEG_01`/`VETO_COMP_02` gate on `RiskEvent.category`/`severity` (categorical, not numeric)
   and `VETO_RED_01` gates on a graph-structural predicate (not a scalar comparison at all) — hence
   `CategoricalComparison` and `GraphPredicate` in `tbox.ttl`, each with their own SHACL shape.
2. **Raw-vs-normalized comparison convention.** Populating real numbers in `instances.trig` forced
   an explicit answer to a question the ontology alone doesn't resolve: `Score*` metrics compare
   via `normalizedScore` ([0,1]), but `Sentiment` compares via `rawValue` ([-1,1]) — v1's own
   thresholds (`-0.50`, `-0.60`) are only meaningful on the raw scale. Documented on
   `ThresholdComparison` in `tbox.ttl`.
3. **Two more named-graph placements.** `07-ontology-topology.md` assigned graphs to every
   *agent's* daily output but not to the Orchestrator's own decisions or to entity resolution's
   derived facts. Resolved: `urn:graph:ingest:ORCHESTRATOR:{date}` and
   `urn:graph:derived:entity-resolution:{date}` (both documented in `instances.trig`'s header).
4. **Shared-property domain collision when reusing `ScoreSnapshot`'s fields for a sibling class.**
   Adding `SectorAggregateSnapshot` (2026-08-13, attractiveness-score feature) needed to reuse
   `metricType`/`agentOrigin`/`timestamp`/`normalizedScore`, but those properties' `rdfs:domain`
   was declared as `:ScoreSnapshot` specifically — reusing them as-is would RDFS-entail that a
   `SectorAggregateSnapshot` individual is also a `:ScoreSnapshot`, contradicting
   `AllDisjointClasses`. Resolved the same way `RuleOperand`/`EvidenceSource` already resolve the
   analogous range problem: a new union class (`:ObservationSnapshot`) widens the four properties'
   domain instead of duplicating them under new names.

## Validation

Parsed and checked with `rdflib` (Turtle + TriG) and validated end-to-end with `pyshacl` —
see the conformance report captured at the bottom of this implementation pass. Re-run:

```bash
python -c "
import rdflib
g = rdflib.Dataset()
for f, fmt in [('tbox.ttl','turtle'), ('shapes.ttl','turtle'), ('reference.ttl','turtle'), ('rules.ttl','turtle')]:
    g.parse(f, format=fmt)
g.parse('instances.trig', format='trig')
print('quads:', len(list(g.quads())))
"
```

`pyshacl` conformance and hand-verified attractiveness-score/VETO_MKT_02 arithmetic are checked by
the script in Task 5 of `docs/superpowers/plans/2026-08-13-attractiveness-sector-momentum.md` —
re-run it the same way after any future schema edit that touches `ScoreSnapshot`,
`SectorAggregateSnapshot`, or `AttractivenessSnapshot`.
