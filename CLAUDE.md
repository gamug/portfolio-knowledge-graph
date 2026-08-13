# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A master's thesis design/artifact repo for a knowledge-graph-backed S&P 500 portfolio
construction-and-maintenance system. There is no application code here — this is a formal
RDF/OWL/SHACL ontology plus a set of Markdown architecture documents. The source document being
formalized is `Avance arquitectura del sistema.docx` (v1, Spanish, 6 sections); `critique-and-evolution.md`
is a critical review of that v1 design plus a proposed v2 evolution (ten additive layers, B1–B10,
each closing a specific gap identified in the critique). The numbered docs (`06`–`10`) are the
formal specification that resulted, and `schema/` is the first implemented piece of it (roadmap
step 0). Everything downstream (steps 1–9 in `10-integration-roadmap.md`) is future work, not yet
built.

Read `critique-and-evolution.md` first when picking up this repo cold — it's the traceability anchor:
every class/property/graph-placement decision elsewhere cites a "critique #N" or "closes gap #N" back
to it.

## Document chain (read in this order)

1. `critique-and-evolution.md` — critique of v1 (`Avance arquitectura del sistema.docx`) + the
   v2 evolution layers (B1–B10) that everything else implements pieces of.
2. `06-ontology-definition.md` — the ontology design rationale (*what* exists: classes, properties,
   the RuleClause tree design that fixes v1's unparenthesized ∧/∨ precedence bug).
3. `07-ontology-topology.md` — physical layout (*how* it's stored: named-graph partitioning scheme,
   scale estimates, reasoning profile). The named-graph table here is the authority for where any
   new triple type should be written — check it (and its "implementation addendum" for graph
   placements discovered after the fact) before inventing a new `urn:graph:...` pattern.
4. `08-agent-architecture.md` — the compute layer: two LangGraph state graphs (`SelectionCycleGraph`
   quarterly, `MonitoringCycleGraph` daily) implementing v1's two-speed cycle; LangGraph's
   checkpointer *is* the `T-1` contagion-lag mechanism, not a separate feature.
5. `09-nlp-finbert-architecture.md` — the Semantic Agent's NLP pipeline (FinBERT tone + NER +
   event/category classification) feeding `ScoreSnapshot`/`RiskEvent` individuals.
6. `10-integration-roadmap.md` — dependency-ordered build steps (0–9) tying it all to the existing
   (external, not in this repo) codebase: `news-collector/`, `news-crawler/`, `edgar_tool.py`, etc.
   Step 0 (this repo's `schema/`) is the only step marked done.

Each doc is a *companion* to its neighbors, not standalone — cross-references between them are load
bearing (e.g. a class defined in `06` gets its storage location assigned in `07` and its writer
assigned in `08`).

## The `schema/` implementation

`schema/README.md` is the authoritative map of this directory — read it before editing any `.ttl`/
`.trig` file. Key facts it establishes:

- **File → named graph → format** table: `tbox.ttl`+`shapes.ttl` → `urn:graph:tbox` (Turtle);
  `reference.ttl` → `urn:graph:reference`; `rules.ttl` → `urn:graph:rules:catalog`; `instances.trig`
  is **TriG** (self-describing, multiple `GRAPH <urn:graph:...> { }` blocks) — every other file loads
  wholesale into the single graph named in the table.
- **Load order**: `tbox.ttl` → `shapes.ttl` → `reference.ttl` → `rules.ttl` → `instances.trig`.
- **OWL (`tbox.ttl`) vs. SHACL (`shapes.ttl`) are deliberately both present** and answer different
  questions: OWL is open-world (what can be *inferred*), SHACL is closed-world (what an ingestion
  pipeline *rejects*). Don't collapse one into the other.
- `schema/protege-view.ttl` is a **generated** file (flattened plain-Turtle bundle for Protégé, which
  can't open `.trig`) — never hand-edit it; it's derived from the four authoritative sources plus a
  `:sourceNamedGraph` annotation that exists only in this file.
- Three design gaps were discovered only while populating real instance data (not anticipated in the
  `06`/`07` design docs) and are flagged inline at the point they surfaced, then summarized in
  `schema/README.md`: `CategoricalComparison`/`GraphPredicate` leaf types (rule catalog needed
  non-numeric leaves), the raw-vs-normalized comparison convention (`Score*` metrics compare on
  `normalizedScore`, `Sentiment` compares on `rawValue`), and two additional named-graph placements
  (`urn:graph:ingest:ORCHESTRATOR:{date}`, `urn:graph:derived:entity-resolution:{date}`). When adding
  new rule types or instance data, check whether it surfaces another such gap and flag/document it
  the same way rather than silently special-casing it in one file.

### Validating the schema

There's no test suite — validation is the `rdflib`/`pyshacl` parse-and-conform check documented in
`schema/README.md`:

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

Run from inside `schema/`. `pyshacl` (`pip install pyshacl`) validates `instances.trig`'s data
against `shapes.ttl`'s shapes for SHACL conformance. Both need to pass after any schema edit —
`tbox.ttl`'s `AllDisjointClasses` block (20 members) and cardinality restrictions, and every
`sh:NodeShape` in `shapes.ttl`, are asserted as exact counts/values in the design docs and will
silently drift out of sync with them if a class or property is added without updating both.

## Conventions specific to this ontology

- **Immutable observations, not mutable attributes**: `ScoreSnapshot` individuals are never updated
  in place — a new measurement is a new individual. This is the audit-trail principle inherited
  directly from v1 §3A; don't model any new metric as a node property that gets overwritten.
- **Valid-time via `validFrom`/`validTo`, absence of `validTo` means "still active"** — this pattern
  (`UniverseMembership`, `PortfolioPosition`, `RuleDefinition`) is closed by writing `validTo` on the
  old record, never by deleting it.
- **N-ary relations are reified as classes**, not modeled as direct properties, whenever the
  relationship itself carries data (e.g. `UniverseMembership` reifies `Asset`-in-`Universe`-with-dates
  rather than a bare `hasUniverse` property with no room for `validFrom`/`validTo`).
- **The `RuleClause` tree replaces v1's infix rule strings** specifically to make the unparenthesized
  `∧`/`∨` precedence ambiguity (critique #1) structurally impossible — every confluent veto rule in
  `rules.ttl` is `AND(primary_signal, OR(secondary_signals))` as an explicit tree, not a string to
  re-parse. Any new rule must be added the same way (see `rules.ttl`'s worked examples for all three
  leaf-operand kinds: `ThresholdComparison`, `CategoricalComparison`, `GraphPredicate`).
- **Raw price data does not belong in the triple store** (`07-ontology-topology.md`'s explicit
  warning) — only derived `PriceObservation` summaries (close, return, ATR) for a bounded window.
  The full OHLCV panel is meant to live in a separate columnar store. Don't add a full tick-level
  class to `tbox.ttl`.
- **IRI namespace**: everything hangs off `https://thesis.local/kg/portfolio#` (prefix `:`) across
  all `schema/*.ttl`/`.trig` files — keep new terms in that namespace unless deliberately aligning to
  an external vocabulary (the ontology already cites FIBO via `rdfs:seeAlso` on `Asset`/`SECFiling`,
  and GICS sectors/industries are modeled as `skos:Concept`s in `reference.ttl`).

## Associated Artifacts

Several of the numbered documents and the schema itself have companion interactive HTML diagrams
published as Claude Artifacts (ontology definition, topology map, agent-graph diagram, NLP pipeline
diagram, integration roadmap DAG, and an interactive node-graph ontology visualization). These are
generated deliverables, not checked into this repo — regenerate them from the current state of the
source `.md`/`.ttl` files rather than treating any previously published version as authoritative.
