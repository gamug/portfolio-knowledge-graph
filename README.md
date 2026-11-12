# Portfolio Knowledge Graph — S&P 500 Thesis Ontology

A master's-thesis design artifact: a formal RDF/OWL/SHACL ontology, plus a set of Markdown
architecture documents, for a knowledge-graph-backed S&P 500 portfolio
construction-and-maintenance system. It is the **integrative layer** of a six-repository system:
this repo owns the ontology, the projection of its siblings' outputs into it, and the query surface;
all computation — news acquisition and EDGAR/pricing services (`portfolio-data-mining`), NLP
(`portfolio-nlp`), and fundamentals/pricing/scoring/vetoes/ranking/portfolio construction
(`portfolio-financial-analysis`) — lives in those repos. The application code here is small:
a transitional ETL (`src/etl/`, entry `cli/build_data_ttl.py`) that turns `portfolio-data-mining`'s point-in-time `universe.db` and
`portfolio-nlp`'s results into a flat `data.ttl` loadable on top of `schema/`; the GraphDB store and its
SHACL ingest gate (`src/kg_store/`); and the start of the real projection from
`portfolio-financial-analysis`'s `v_*` views (`src/projection/`). Scope detail: `.specify/memory/SPEC.md` §2.5–§2.6.

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
| — | [`docs/critique-and-evolution.md`](docs/critique-and-evolution.md) | Critique of v1 + the B1–B10 evolution layers everything else implements pieces of. |
| `06` | [`docs/06-ontology-definition.md`](docs/06-ontology-definition.md) | The ontology design rationale — *what* exists: classes, properties, the `RuleClause` tree that fixes v1's unparenthesized ∧/∨ precedence bug. |
| `07` | [`docs/07-ontology-topology.md`](docs/07-ontology-topology.md) | Physical layout — *how* it's stored: named-graph partitioning, scale estimates, reasoning profile. |
| `08` | [`docs/08-agent-architecture.md`](docs/08-agent-architecture.md) | The compute-layer *design* — two LangGraph state graphs (`SelectionCycleGraph` quarterly, `MonitoringCycleGraph` daily) for v1's two-speed cycle. Reference only: the cycle is implemented upstream in `portfolio-financial-analysis`'s `cycle` package (mapping at the end of the doc). |
| `09` | [`docs/09-nlp-finbert-architecture.md`](docs/09-nlp-finbert-architecture.md) | The Semantic Agent's NLP pipeline (FinBERT tone + NER + event/category classification). |
| `10` | [`docs/10-integration-roadmap.md`](docs/10-integration-roadmap.md) | Dependency-ordered steps (0–9) with the owning repo and status of each. Step 0 (`schema/`) is the only one built here; steps 3–9 are computation built (or planned) in the sibling repos. |
| — | [`docs/reports-agent-query-catalog.md`](docs/reports-agent-query-catalog.md) | The reports-agent query contract: scoped SPARQL for the FIBO glossary and the backtest battery, the brief's 11 evaluation questions (including what is not projected yet), and the executable test that keeps the catalog true. |
| — | [`docs/ttyg/`](docs/ttyg/README.md) | Source of truth for the Talk to Your Graph agent: the curated CONSTRUCT, the English v1.2 additional instructions and how they map to the Workbench form. |
| — | [`docs/ttyg/create-agent.md`](docs/ttyg/create-agent.md) | Recreate the Workbench agent by hand: SPARQL only, the curated CONSTRUCT, temperature `0.1`, the single instruction fence and the `graphdb.llm.*` placeholders. |
| — | [`docs/final-delivery.md`](docs/final-delivery.md) | The end-to-end production sequence for label `final`: preconditions, backup and SHA-256, graph clearing, schema/catalog/ticker-history/backtest/aggregates loads, the acceptance queries and the rehearsal-first rule. |
| — | [`docs/second-user-setup.md`](docs/second-user-setup.md) | A colleague's local GraphDB 11.5.1 Free and `portfolio-app`: repository profile, verified export import, TTYG agent, read-only user, first smoke questions. |
| — | [`docs/backtest-load-runbook.md`](docs/backtest-load-runbook.md) | The final-backtest load procedure: the one-command `cli/load_run.py` flow first, the six date-ordered windows, the `SHA256SUMS` manifest and `config_<label>.md` configuration, the metadata graph, the manual fallback, schema and catalog prerequisites, contract check, label choice, both dry runs, the full read-only `--check-store` pre-flight, writes and production guard, `cli/verify_backtest.py` for m018 and selection graphs, the `cli/load_aggregates.py` step after the run, recording the numbers, single-graph rollback, whole-label removal, the one-time catalog load and its incremental `--delta` extension, and the common failure messages. |
Each doc is a companion to its neighbors, not standalone — a class defined in `06` gets its
storage location assigned in `07` and its writer assigned in `08`.

## Repository layout

```
.
├── Avance arquitectura del sistema.docx   source v1 design doc (Spanish)
├── schema/                                the implemented ontology (roadmap step 0) — all files real, verified
│   ├── README.md                          authoritative map of this directory — read first
│   ├── tbox.ttl                           OWL classes, properties, cardinality restrictions, class taxonomy (§1.2)
│   ├── shapes.ttl                         SHACL data-quality shapes (34)
│   ├── reference.ttl                      GICS sector/industry taxonomy + asset master data + MetricType vocabulary
│   ├── rules.ttl                          veto rule catalog + AttractivenessWeightScheme, as RuleClause/weight trees
│   ├── instances.trig                     worked-example ABox (TriG, multiple named graphs)
│   └── protege-view.ttl                   generated flat Turtle bundle for Protégé — STALE as of 2026-08-23, not regenerated after the tbox.ttl/reference.ttl/shapes.ttl edits below; regenerate before using in Protégé
├── src/etl/, cli/build_data_ttl.py         transitional ETL: universe.db + portfolio-nlp results → flat data.ttl (roadmap step 2 shortcut)
├── src/kg_store/, cli/load_schema.py, cli/ingest.py, cli/verify_store.py, cli/load_universe.py   GraphDB store, schema loader, SHACL ingest gate and the asset-master loader with its incremental --delta (roadmap step 1, T-220, Work item 28)
├── src/projection/, cli/check_view_contract.py (a checkout or the service's URL)   real step-2 projection (Work item 4): v_* read contract, drift check, score conversion, boundary expectations (view_expectations/*.json) and their runner (boundary.py), `v_score_snapshot` -> `:ScoreSnapshot` (score_snapshots.py, project_scores.py; entry point cli/project_scores.py), the eight m018 backtest/GUARD views -> `urn:graph:derived:backtest:{label}:{window}:{run}` (backtest.py, project_backtest.py; entry point cli/project_backtest.py), the six selection views -> the sibling `urn:graph:derived:backtest:selection:{label}:{window}:{run}` (project_selection.py; entry point cli/project_selection.py; Work item 26), the read-only verifier for either graph (verify_backtest.py; entry point cli/verify_backtest.py), the delivery manifest/configuration readers (delivery.py), the run-metadata graph and its read-only verifier (run_metadata.py), the read-only disk guard (disk_space.py), the one-command delivery dry-run/pre-flight/write/verify sequence (load_run.py; entry point cli/load_run.py; Work items 29, 31 and 35), and the per-label aggregates file with its manifest check and read-only verifier (aggregates.py/load_aggregates.py; entry point cli/load_aggregates.py; Work item 37), and the external mean-variance base Markowitz delivery (mv_base.py; entry point cli/load_mv_base.py; Work item 44)
└── docs/                                  all Markdown design documents
    ├── critique-and-evolution.md          v1 critique + v2 evolution layers
    ├── 06-ontology-definition.md          ontology design rationale
    ├── 07-ontology-topology.md            named-graph storage design
    ├── 08-agent-architecture.md           LangGraph agent design (reference; built upstream as `cycle`)
    ├── 09-nlp-finbert-architecture.md     NLP / FinBERT pipeline design
    ├── 10-integration-roadmap.md          10-step roadmap, with owner repo per step
    ├── reports-agent-query-catalog.md     the reports-agent query contract + executable test
    ├── ttyg/                              Talk to Your Graph agent sources: curated CONSTRUCT + v1.2 instructions
    │   └── create-agent.md               recreate the Workbench agent by hand
    ├── final-delivery.md                  end-to-end production sequence for label final
    ├── second-user-setup.md               local GraphDB + portfolio-app setup for a second user
    ├── FAQ.md                             running Q&A log on graph population mechanics
    ├── portfolio-common-v1-migration-plan.md      decision record: adopting portfolio-common v1
    ├── portfolio-common-v1.2-engine-agnostic.md   how the engine-agnostic state was reached
    ├── new_ontology/                      taxonomy proposal + critical evaluation
    └── superpowers/                       planning/spec artifacts from the SDD workflow used
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
clean (1608 quads at the 2026-08-23 revision — `schema/taxonomy-quality-review-2026-08-23.md` has the +1 delta from a
same-day `RuleClause` fix; 1771 after T-102/T-103, 1881 after T-104, 1951 after T-101, 1953 after T-105, 2064 after T-106, 2150 after T-107, 2298 after T-108, 2352 after T-109, 2366 after T-111, 2378 after T-100, 2383 after its review, 2400 after T-081, 2458 after T-140, 2648 after T-187/T-188, 4178 after T-206, 4182 after T-210, 4236 after T-211, 4237 after T-220, 4202 after T-233/T-234, 4203 after merging T-220 with T-233/T-234, 4204 after T-227, 4431 after Work item 26, 4634 after Work item 33, 4913 after Work item 37, 4915 after Work item 38, 4940 after Work item 44, 5900 after Work item 43, 5954 after Work item 43 rules, 6072 after Work item 43 terms, 6854 after Work item 45), conforms: True** (`schema/README.md`'s Validation section has the exact
command). `protege-view.ttl` is the one file *not* re-verified — it's a generated bundle
(`schema/README.md`: "never hand-edit") that predates this revision's edits, the T-206 Contract
v18 classes, T-210's FIBO links and T-211's Spanish layer, and needs regenerating from a real
Protégé session, not something this pass could safely hand-patch.

`schema/README.md` is the authoritative map of that directory — read it before editing any
`.ttl`/`.trig` file. Current shape:

| File | Format | Named graph | Contents |
|---|---|---|---|
| `tbox.ttl` | Turtle | `urn:graph:tbox` | 60 classes (46 mutually disjoint leaf/domain classes + a 13-class `rdfs:subClassOf` taxonomic backbone + `:ExchangeTradedFund` under `:Asset`), properties, cardinality restrictions |
| `shapes.ttl` | Turtle | `urn:graph:tbox` | 44 named SHACL node shapes plus two blank-node conditional shapes |
| `reference.ttl` | Turtle | `urn:graph:reference` | GICS sector/industry taxonomy + 6 worked-example assets (5 S&P 500 constituents + the core ETF SPY) |
| `fibo.ttl` | Turtle | `urn:graph:reference:fibo` | 25-term FIBO 2026Q2 glossary slice (54 entries, 277 statements) + the authors' Spanish `@es` layer |
| `rules.ttl` | Turtle | `urn:graph:rules:catalog` | 10 active selection rules + 7 GUARD protection rules (single-leaf `RuleDefinition`s) + 8 superseded definitions kept as history + `AttractivenessWeightScheme` |
| `labels.ttl` | Turtle | `urn:graph:labels` | The bilingual SKOS presentation vocabulary (90 concepts, 892 triples): windows, run label, strategies, GUARD, veto classes, markers, score components, rank, configuration and process terms |
| `instances.trig` | TriG | *(self-describing — 14 `GRAPH` blocks)* | Dated ABox: universe membership, agent snapshots, evidence, vetoes, filings, portfolio, sector-aggregate and attractiveness-ranking output |

Load order: `tbox.ttl` → `shapes.ttl` → `reference.ttl` → `fibo.ttl` → `rules.ttl` → `labels.ttl` → `instances.trig`.
The production repository stops before `instances.trig`: its worked-example ABox is sample data and
never reaches production, while `portfolio_test` and other non-production repositories keep loading it.

OWL (`tbox.ttl`) and SHACL (`shapes.ttl`) are deliberately both present and answer different
questions — OWL is open-world (what can be *inferred*), SHACL is closed-world (what an ingestion
pipeline *rejects*).

### Validating the schema

Schema validation is a parse-and-conform check (code in `src/` has a growing hermetic `pytest` suite:
`uv run pytest`, PLAN Work item 13). Run from inside `schema/`:

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

Opening the repo in the provided **Dev Container** (`.devcontainer/`) pins the Python/`uv`
toolchain and also bind-mounts a shared `thesis` data directory at `/workspaces/thesis`. Two pieces
of configuration:

- `.env` (repo root, git-ignored; `cp .env.example .env`) is passed to the container with
  `docker run --env-file` (`runArgs` in `devcontainer.json`), so its variables are set in the dev shell
  without `export`. The file must exist before the container is created, and its values must be plain
  `KEY=value` (no quotes, no `export`). Paths in it use the in-container layout
  (`/workspaces/thesis/...`). After editing it, run **Dev Containers: Rebuild Container**.
- **`THESIS_HOST_DIR`** — host path of the shared `thesis` data directory, bind-mounted at
  `/workspaces/thesis`. The `mounts` entry is resolved on the host before the container exists
  (`${localEnv:THESIS_HOST_DIR}`), so it must be set in your **host environment** (shell profile or OS
  environment variables, read before VS Code launches) — `.env` cannot provide it. E.g.
  `export THESIS_HOST_DIR=/Users/you/thesis` or, on Windows, `setx THESIS_HOST_DIR D:\thesis`. This
  variable name is shared across the sibling `portfolio-*` repos that mount the same directory.

## Build status

| Roadmap step | Status |
|---|---|
| 0 — Ontology + SHACL shapes (this repo's `schema/`) | ✅ Done |
| 1 — Stand up the triple store | ✅ Done — GraphDB repository `portfolio` with the reasoning profile of `07`, `schema/` loaded (`cli/load_schema.py --to-production`), ABox writes pass a SHACL gate (`cli/ingest.py`); see `docs/graphdb-setup.md`. The production repository holds the schema files only: the `instances.trig` worked example is loaded in `portfolio_test` and other non-production repositories, never in production |
| 2 — Ingest already-collected data into the graph | Shortcut built — `src/etl/` projects the universe (`universe.db`: assets and membership history) and news (`portfolio-nlp` results) to a flat `data.ttl`; the real projection (`financial-analysis` `v_*` views, dated named graphs) is partly built: T-030 pinned the read contract and the score conversion (`src/projection/`), T-031 projects `v_score_snapshot`, T-207 projects the eight m018 backtest/GUARD views into `urn:graph:derived:backtest:{label}:{window}:{run}`, Work item 26 projects the selection side into `urn:graph:derived:backtest:selection:{label}:{window}:{run}`, T-280's `cli/verify_backtest.py` proves a loaded graph matches its source read-only (Work item 29 extends it to the selection graph and adds the cross-graph check), and `cli/load_run.py` verifies the delivery manifest/configuration, runs both dry runs, the read-only pre-flight of every graph, both writes, the run-metadata graph and every verification in one command (see `docs/backtest-load-runbook.md`) |
| 3–9 — Pricing collector, EDGAR batch pipeline, NLP service, agent cycles, entity resolution, sector/portfolio construction, backtesting | Not this repo's to build — owned by `portfolio-data-mining`, `portfolio-nlp`, `portfolio-financial-analysis` (built or partly built there, per their docs; per-step owner table in the roadmap). This repo's part is projecting their outputs (step 2) |

Full dependency-ordered detail in [`docs/10-integration-roadmap.md`](docs/10-integration-roadmap.md).
[`docs/FAQ.md`](docs/FAQ.md) is a growing log of Q&A on how instance data actually gets populated into the
graph once that build starts — node-vs-observation patterns, the two date mechanisms, and how
named-graph filtering works in practice.

Load a final backtest in one command, or verify one graph read-only. Every CLI that opens the store
prints its target as the first output line (`target: GraphDB <host> repository <name> [PRODUCTION]`
or `[not production]`) and warns when a process-environment `KG_HOST`/`KG_REPOSITORY` overrides
`.env`; credentials are never printed. The verifier then prints the repository and graph and one
`PASS`/`FAIL` line per check; exit 0 only if all pass.

| Command | Purpose |
|---|---|
| `cli/load_run.py --label final --dir data/backtests` | Verify `SHA256SUMS` and `config_final.md`, dry-run both projectors over the six date-ordered windows, build/validate the metadata graph and print the graph/triples/status table. |
| `cli/load_run.py --label final --dir data/backtests --check-store` | Run the read-only pre-flight (`gate.plan`) for every m018, selection and metadata graph, report would-be-written/already-in-the-store/refused and write nothing. |
| `cli/load_run.py --label final --dir data/backtests --write` | Pre-flight every graph first; only if all are accepted, write the m018 graphs, then the selection siblings, then the metadata graph, verify every graph and print the checks-passed table. |
| `cli/load_run.py --label rule --dir <pilot> --no-manifest --no-config --check-store` | The pilot's explicit legacy pre-flight: no manifest/configuration and no metadata graph. |
| `cli/load_run.py … --contract /path/to/portfolio-financial-analysis` | Run the pinned view-contract check before reading any database. |
| `cli/load_aggregates.py --label final --dir data/backtests` | Verify `aggregates_<label>.json` against `SHA256SUMS`, parse it, verify the source databases read-only, build and SHACL-validate the batch; no store is contacted. |
| `cli/load_aggregates.py --label final --dir data/backtests --check-store` | Run the read-only gate plan for `urn:graph:derived:backtest:aggregates:{label}` and, if it exists, compare its stored rows with the file. |
| `cli/load_aggregates.py --label final --dir data/backtests --write` | Plan and append the one aggregates graph, then verify the stored rows against the file. |
| `cli/load_mv_base.py --label final --dir "/path/to/mv_base"` | Verify `aggregates_mv_base.json` and `config_mv_base.md` against `SHA256SUMS`, parse/build the external `MARKOWITZ_MV` summaries, read the engine ids/dates read-only from `--engine-dir` (default `.../final_corregida`) and SHACL-validate them; no store is contacted and `provenance/` is not required. |
| `cli/load_mv_base.py --label final --dir "/path/to/mv_base" --check-store` | Run the read-only gate plan for `urn:graph:derived:backtest:external:final` and, if it exists, compare its stored triples with the batch. |
| `cli/load_mv_base.py --label final --dir "/path/to/mv_base" --write --to-production` | Plan and append the one external graph (production needs the explicit opt-in), then verify it. |
| `cli/verify_backtest.py --graph urn:graph:derived:backtest:rule:P1:1 --db rule_P1.db --label rule` | Verify one m018 graph read-only. |
| `cli/verify_backtest.py --graph urn:graph:derived:backtest:selection:rule:P1:1 --db rule_P1.db --label rule` | Verify one selection graph read-only, including its m018 cross-graph check. |

```bash
uv run python cli/load_run.py --label final --dir data/backtests --write
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:selection:rule:P1:1 \
  --db /path/to/rule_P1.db --label rule
```

The final table is `graph / triples / status / checks`. `--write` plans every graph against the
store before writing any of them: a refused graph stops the command with nothing written, while an
already-stored graph is reported and skipped. A verification failure, or a write failure after the
pre-flight, prints the exact one-graph `DROP GRAPH <iri>` commands for the graphs it wrote. The full load procedure,
including the schema/catalog prerequisites and a single-graph rollback, is
[`docs/backtest-load-runbook.md`](docs/backtest-load-runbook.md).

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

- **Class taxonomy** — the 38 domain classes sit under an explicit `rdfs:subClassOf` backbone (6
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
  be re-parsed wrong. (Being revised: `portfolio-financial-analysis`'s six-rule catalog, all single
  flat comparisons, was confirmed as the final one; `rules.ttl` migrates to it — see
  `.specify/memory/SPEC.md` §2.6 D4.)
- **Raw price data does not belong in the triple store** — only derived `PriceObservation`
  summaries for a bounded window. The full OHLCV panel belongs in a separate columnar store.
- **IRI namespace**: everything hangs off `https://thesis.local/kg/portfolio#` (prefix `:`)
  unless deliberately aligning to an external vocabulary (FIBO, GICS via SKOS).

A fuller version of these conventions lives in the local, gitignored `CLAUDE.md`, aimed at
AI-assisted development sessions on this repo.
