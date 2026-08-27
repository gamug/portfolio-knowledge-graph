# Portfolio Knowledge Graph — S&P 500 Thesis Ontology

A master's-thesis design artifact: a formal RDF/OWL/SHACL ontology, plus a set of Markdown
architecture documents, for a knowledge-graph-backed S&P 500 portfolio
construction-and-maintenance system. There is no application code in this repository — this is
the ontology and its supporting specification, built to be loaded into a triple store (GraphDB /
Fuseki) and driven by an external agent codebase (`news-collector/`, `news-crawler/`,
`edgar_tool.py`, a LangGraph agent layer) that is not part of this repo.

The source document being formalized is `Avance arquitectura del sistema.docx` (v1, Spanish,
6 sections). `critique-and-evolution.md` is a critical review of that v1 design plus a proposed
v2 evolution — ten additive layers (B1–B10), each closing a specific gap identified in the
critique. The numbered documents (`06`–`10`) are the formal specification that resulted, and
`schema/` is the first implemented piece of it. Everything past that (the rest of the
integration roadmap) is future work, not yet built.

## Where to start

Read `critique-and-evolution.md` first — it's the traceability anchor. Every class, property,
and graph-placement decision elsewhere cites a "critique #N" or "closes gap #N" back to it. Then
the numbered docs, in order:

| # | Document | Covers |
|---|---|---|
| — | [`critique-and-evolution.md`](critique-and-evolution.md) | Critique of v1 + the B1–B10 evolution layers everything else implements pieces of. |
| `06` | [`06-ontology-definition.md`](06-ontology-definition.md) | The ontology design rationale — *what* exists: classes, properties, the `RuleClause` tree that fixes v1's unparenthesized ∧/∨ precedence bug. |
| `07` | [`07-ontology-topology.md`](07-ontology-topology.md) | Physical layout — *how* it's stored: named-graph partitioning, scale estimates, reasoning profile. |
| `08` | [`08-agent-architecture.md`](08-agent-architecture.md) | The compute layer — two LangGraph state graphs (`SelectionCycleGraph` quarterly, `MonitoringCycleGraph` daily) implementing v1's two-speed cycle. |
| `09` | [`09-nlp-finbert-architecture.md`](09-nlp-finbert-architecture.md) | The Semantic Agent's NLP pipeline (FinBERT tone + NER + event/category classification). |
| `10` | [`10-integration-roadmap.md`](10-integration-roadmap.md) | Dependency-ordered build steps (0–9) tying it all to the external codebase. Step 0 (`schema/`) is the only one done. |

Each doc is a companion to its neighbors, not standalone — a class defined in `06` gets its
storage location assigned in `07` and its writer assigned in `08`.

## Repository layout

```
.
├── Avance arquitectura del sistema.docx   source v1 design doc (Spanish)
├── critique-and-evolution.md              v1 critique + v2 evolution layers
├── 06-ontology-definition.md              ontology design rationale
├── 07-ontology-topology.md                named-graph storage design
├── 08-agent-architecture.md               LangGraph agent architecture
├── 09-nlp-finbert-architecture.md         NLP / FinBERT pipeline design
├── 10-integration-roadmap.md              10-step build roadmap
├── FAQ.md                                 running Q&A log on graph population mechanics
├── schema/                                the implemented ontology (roadmap step 0) — all files real, verified
│   ├── README.md                          authoritative map of this directory — read first
│   ├── tbox.ttl                           OWL classes, properties, cardinality restrictions, class taxonomy (§1.2)
│   ├── shapes.ttl                         SHACL data-quality shapes (14)
│   ├── reference.ttl                      GICS sector/industry taxonomy + asset master data + MetricType vocabulary
│   ├── rules.ttl                          veto rule catalog + AttractivenessWeightScheme, as RuleClause/weight trees
│   ├── instances.trig                     worked-example ABox (TriG, multiple named graphs)
│   └── protege-view.ttl                   generated flat Turtle bundle for Protégé — STALE as of 2026-08-23, not regenerated after the tbox.ttl/reference.ttl/shapes.ttl edits below; regenerate before using in Protégé
└── docs/superpowers/                      planning/spec artifacts from the SDD workflow used
                                            to build the attractiveness-ranking + sector-momentum
                                            feature
```

`CLAUDE.md` (instructions for AI-assisted development sessions on this repo) exists locally but
is gitignored — it's a personal working note, not part of the tracked repository.

## The schema

**2026-08-23 note:** for a while, this repository copy had no `schema/` files at all — every
reference to them across these docs described a design that was never actually included, only
written up in prose. The real files (`tbox.ttl`, `shapes.ttl`, `reference.ttl`, `rules.ttl`,
`instances.trig`, `protege-view.ttl`, `schema/README.md`) have since been added, and this revision's
class taxonomy (§1.2 in `06-ontology-definition.md`) and MetricType vocabulary (§1.9) were merged
directly into `tbox.ttl`/`reference.ttl`/`shapes.ttl` — not left as separate addendum files. Full
`rdflib` parse + `pyshacl` conformance re-verified against the real files after the merge: **parses
clean (1608 quads — `schema/taxonomy-quality-review-2026-08-23.md` has the +1 delta from a
same-day `RuleClause` fix), conforms: True** (`schema/README.md`'s Validation section has the exact
command). `protege-view.ttl` is the one file *not* re-verified — it's a generated bundle
(`schema/README.md`: "never hand-edit") that predates this revision's edits and needs regenerating
from a real Protégé session, not something this pass could safely hand-patch.

`schema/README.md` is the authoritative map of that directory — read it before editing any
`.ttl`/`.trig` file. Current shape:

| File | Format | Named graph | Contents |
|---|---|---|---|
| `tbox.ttl` | Turtle | `urn:graph:tbox` | 37 classes (24 mutually disjoint leaf/domain classes + a 13-class `rdfs:subClassOf` taxonomic backbone), properties, cardinality restrictions |
| `shapes.ttl` | Turtle | `urn:graph:tbox` | 14 SHACL node shapes |
| `reference.ttl` | Turtle | `urn:graph:reference` | GICS sector/industry taxonomy + 5 worked-example asset tickers |
| `rules.ttl` | Turtle | `urn:graph:rules:catalog` | 7-rule veto catalog as unambiguous `RuleClause` trees |
| `instances.trig` | TriG | *(self-describing — 11 `GRAPH` blocks)* | Dated ABox: universe membership, agent snapshots, evidence, vetoes, filings, portfolio, sector-aggregate and attractiveness-ranking output |

Load order: `tbox.ttl` → `shapes.ttl` → `reference.ttl` → `rules.ttl` → `instances.trig`.

OWL (`tbox.ttl`) and SHACL (`shapes.ttl`) are deliberately both present and answer different
questions — OWL is open-world (what can be *inferred*), SHACL is closed-world (what an ingestion
pipeline *rejects*).

### Validating the schema

There's no test suite — validation is a parse-and-conform check. Run from inside `schema/`:

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

`pyshacl` (`pip install pyshacl`) validates `instances.trig`'s data against `shapes.ttl`'s shapes
for SHACL conformance — both checks need to pass after any schema edit.

## Build status

| Roadmap step | Status |
|---|---|
| 0 — Ontology + SHACL shapes (this repo's `schema/`) | ✅ Done |
| 1 — Stand up the triple store | Not started |
| 2 — Ingest already-collected news/EDGAR data (the actual next step) | Not started |
| 3–9 — Pricing collector, EDGAR batch pipeline, FinBERT service, LangGraph agents, entity resolution, portfolio construction, backtesting | Not started |

Full dependency-ordered detail in [`10-integration-roadmap.md`](10-integration-roadmap.md).
[`FAQ.md`](FAQ.md) is a growing log of Q&A on how instance data actually gets populated into the
graph once that build starts — node-vs-observation patterns, the two date mechanisms, and how
named-graph filtering works in practice.

## Companion diagrams

Several documents (and the schema itself) have interactive HTML companion diagrams published as
Claude Artifacts. These are generated deliverables, not checked into this repo — regenerate them
from the current `.md`/`.ttl` source rather than treating a previously published version as
authoritative.

| Document | Artifact |
|---|---|
| `critique-and-evolution.md` | [KG Portfolio Architecture — Critique & Evolution](https://claude.ai/code/artifact/8f9bc0fc-e6f0-4f52-9e5c-5332461c1f67) |
| `06-ontology-definition.md` | [Ontology Definition](https://claude.ai/code/artifact/79386779-bdc1-41a3-a4fc-9383cfad1ef4) |
| `07-ontology-topology.md` | [Ontology Topology](https://claude.ai/code/artifact/89c8ee18-7538-4d41-a71e-60ab1e95d028) |
| `schema/` (interactive node-graph view) | [Ontology Topography](https://claude.ai/code/artifact/c02922ce-2182-4071-be44-35738ae24a06) |
| `08-agent-architecture.md` | [Agent Architecture](https://claude.ai/code/artifact/b4b2db9f-1cba-4900-8455-336e49b1ae1c) |
| `09-nlp-finbert-architecture.md` | [NLP Architecture — FinBERT Pipeline](https://claude.ai/code/artifact/35ef109c-1667-4dfb-8f90-e89e839bad9d) |
| `10-integration-roadmap.md` | [Integration Roadmap](https://claude.ai/code/artifact/3108d78d-0c8b-4c66-956e-28e1f96c2059) |
| `FAQ.md` / population mechanics | [The Population Ledger](https://claude.ai/code/artifact/6b434b58-7a91-4a0e-8c8a-7f11be020034) |

## Conventions worth knowing before editing

- **Class taxonomy** — the 24 domain classes sit under an explicit `rdfs:subClassOf` backbone (6
  broad categories: `DomainEntity`, `TemporalRelation`, `Observation`, `Evidence`,
  `RiskAndDecision`, `RuleSystem`, plus 4 mid-level categories) rather than flat under `owl:Thing`.
  Three former `owl:unionOf` domain-widening helpers (`ObservationSnapshot`, `EvidenceSource`,
  `RuleOperand`) were upgraded to ordinary, queryable superclasses as part of this — same IRIs, no
  other change. See `06-ontology-definition.md` §1.2.
- **Immutable observations, not mutable attributes** — a `ScoreSnapshot` is never updated in
  place; a new measurement is a new individual.
- **Valid-time via `validFrom`/`validTo`** — absence of `validTo` means "still active." Closing a
  record means writing `validTo` on it, never deleting it.
- **N-ary relations are reified as classes** whenever the relationship itself carries data (e.g.
  `UniverseMembership`, not a bare `hasUniverse` property with nowhere to hang dates).
- **The `RuleClause` tree replaces v1's infix rule strings** so `AND`/`OR` precedence can never
  be re-parsed wrong.
- **Raw price data does not belong in the triple store** — only derived `PriceObservation`
  summaries for a bounded window. The full OHLCV panel belongs in a separate columnar store.
- **IRI namespace**: everything hangs off `https://thesis.local/kg/portfolio#` (prefix `:`)
  unless deliberately aligning to an external vocabulary (FIBO, GICS via SKOS).

A fuller version of these conventions lives in the local, gitignored `CLAUDE.md`, aimed at
AI-assisted development sessions on this repo.
