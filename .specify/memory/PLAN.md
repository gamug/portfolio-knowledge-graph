# PLAN.md — `portfolio-knowledge-graph`

The implementation plan for the live backlog identified in
`.specify/memory/SPEC.md`. Where the constitution is principles and
`SPEC.md` is the requirements/architecture contract, this document is the
"how, and in what order" for the work that contract still leaves open.

**This plan is not narrow the way a near-feature-complete repo's would be.**
`SPEC.md` §14's disposition table splits `SPEC.md` §13's nine open items into
two different categories, and most of them land on the larger side: only
three items (7, 8, 9 — no test suite, uncalibrated severity formulas, no
pinned SOURCE/RESULTS contract) are **permanently out of scope**. The other
six are **pending development** — this repo's actual unbuilt roadmap
(`10-integration-roadmap.md` steps 1–9), not a closed list of accepted
limitations. This plan covers all six, at a level of detail matched to how
soon and how independently each can actually start: the three cheap,
no-blocker doc/schema fixes are fully detailed (Work items 1, 2, 9); the
larger roadmap steps are broken into work items with a stated goal, approach,
and acceptance criteria, but — like `portfolio-nlp`'s `PLAN.md` treats an
infrastructure-blocked item — left coarse-grained where the actual
implementation depends on a scope or architecture decision nobody has made
yet (Work item 3 was one until the maintainer chose GraphDB; Work items 5 and 7
were resolved by the 2026-10-02 scope decision).

## Goal

Close every item `SPEC.md` §14 categorizes as pending development:

1. Rewrite `10-integration-roadmap.md`'s stale repo references (§13 item 3).
2. Reconcile `CLAUDE.md` with `origin/master`'s actual merged state (§13
   item 5). **Done.**
3. Stand up a triple store and wire the SHACL ingest gate (§13 item 1,
   roadmap step 1).
4. Build the real step-2 projection: `financial-analysis`'s `v_*` views +
   `portfolio-nlp`'s `article_*` tables → SHACL-validated, dated named
   graphs (§13 items 1 and 2, roadmap step 2 proper — supersedes today's
   `src/etl/` shortcut).
5. ~~Implement the SEMANTIC score's per-`(asset, day)` aggregation~~ —
   **reassigned upstream** (T-007 scan, 2026-10-02): `portfolio-nlp` computes
   it, `portfolio-financial-analysis` materializes it; this repo only
   projects the resulting row (folded into Work item 4).
6. Bring up the OWL RL reasoner and the SPARQL query surface (§13 item 1,
   roadmap steps within 1–3).
7. ~~Decide and build the orchestrator~~ — **decided: delegate** (T-007,
   2026-10-02). The two-speed cycle is `portfolio-financial-analysis`'s
   `cycle` package; this repo builds no orchestrator and projects its
   outputs (Work item 4). Note: no scheduler exists upstream either.
8. Regenerate `schema/protege-view.ttl` (§13 item 4).
11. Reconcile the ontology, SHACL shapes, rule catalog and ETL with the
    upstream contracts found by the T-007 rescan (`SPEC.md` §2.6 D1–D16):
    decisions first, then schema/ETL edits (§13 item 10).
9. Resolve the `ScoreSnapshotShape`/Sentiment `rawValue` divergence (§13
   item 6).
10. Complete `schema/README.md`'s directory map (found during a
    constitution-compliance audit, not originally in `SPEC.md` §13). **Done.**

Growing the ABox from the current MVP shortcut's output to the full
500-name universe on the real (not shortcut) projection is the natural
completion criterion for Work item 4, not a separate item — see that work
item's acceptance criteria.

**Scope principle (T-007, 2026-10-02):** this repo is purely integrative —
all computation lives in `portfolio-data-mining`, `portfolio-nlp` and
`portfolio-financial-analysis` (`SPEC.md` §2.5). Work items here only model,
project, validate and query; any task that would compute a score, rank,
veto, sentiment or filing metric belongs in an upstream repo's plan.

## Non-goals

Only the three items `SPEC.md` §14 places in **permanently out of scope**
are excluded from this plan — everything else in `SPEC.md` §13 is a Goal
above, not a non-goal:

- Item 7 — adding a `pytest` suite for `src/etl/`: accepted at current
  scale; revisit only if Work item 4 grows the ETL's logic enough that
  end-to-end SHACL checking alone stops catching regressions.
- Item 8 — calibrating the G1/G2/G3/G9 severity formulas: a research task
  needing ground-truth labels this plan has no way to produce.
- Item 9 — pinning a formal SOURCE/RESULTS schema contract with
  `portfolio-nlp`: accepted risk at this scale; would only become a work
  item here if a `portfolio-nlp` schema change actually broke Work item 4's
  projection.
- **Productizing this system** (access control, monitoring, a scheduler-
  backed SLA) — permanently out of scope regardless of how much of the Goal
  list above gets built (`SPEC.md` §14).

## Work item 1 — Rewrite the integration roadmap's stale repo references

**Why**: `10-integration-roadmap.md` was written before the external
codebase it describes was split into the current six-repo system. It still
names `news-collector`, `news-crawler`, `edgar_tool.py`, and "a LangGraph
agent layer" as if they were the only pieces outside this repo — they have
since become `portfolio-data-mining` (crawling/discovery), `portfolio-nlp`
(semantic layer), and `portfolio-financial-analysis`
(fundamentals/pricing/cycle/quant), with the LangGraph agent layer specified
in this repo's own `08-agent-architecture.md`.

**Approach**:

1. Read `10-integration-roadmap.md` in full; list every reference to a
   superseded name and every step description assuming the old, undivided
   external codebase.
2. Replace each with the actual current repo name from `SPEC.md` §1's
   six-repo diagram, and point the agent-layer reference at
   `08-agent-architecture.md` instead of describing it as external and
   unspecified.
3. Update the roadmap's step 0–9 table so each step names the repo that now
   owns or will build it — without changing which steps are marked done vs.
   not-started (a naming fix, not a status change; Work items 3, 4 and 6 below are
   what actually change the status).
4. Cross-check `README.md` and `CLAUDE.md` for the same stale names and
   update them in the same pass.
5. **Done (2026-10-02, T-007).** Scan `github.com/gamug/portfolio-financial-analysis`,
   `github.com/gamug/portfolio-nlp` and `github.com/gamug/portfolio-data-mining`
   to set this repo's proper scope. This repo is purely integrative: the
   computation lives in those repos; this one models, projects and queries
   their outputs. For each, record inputs and outputs into the knowledge
   graph. Outcome: ownership map in `SPEC.md` §2.5; the `portfolio-data-mining`
   pricing endpoint is confirmed to exist (`apps/pricing_api.py`), so the
   roadmap's "`src/trading/` is empty" row is stale; roadmap steps 3, 4, 7, 8
   (and part of 9) are computed upstream. `.specify/` is corrected; the
   roadmap/`08`/README/CLAUDE.md wording is left to T-003, T-004, T-008.
6. Update the Claude Code artifacts — the local `CLAUDE.md` and the published
   Claude Artifacts — to the scope decisions above, per constitution "Claude
   Code / coding-agent conduct" #4 and #6 (T-009, which absorbs the
   deprecated T-006). Published artifact names are never changed.

**Acceptance criteria**:

- `grep -rn "news-collector\|news-crawler\|edgar_tool" *.md README.md
  CLAUDE.md` (excluding `SPEC.md`'s own historical §13 references) returns
  nothing.
- `10-integration-roadmap.md`'s step table names only repos that actually
  exist in the six-repo system today.
- The schema parse+`pyshacl` check still passes (docs-only change).

## Work item 2 — Reconcile `CLAUDE.md` with `origin/master`'s actual state

**Status: DONE (2026-09-12)**, closed by the same PR that added the required
constitution/SPEC references to `CLAUDE.md` (constitution "Claude Code /
coding-agent conduct" #4) — see `TASKS.md` T-010–T-015.

**Why**: `CLAUDE.md` is intentionally untracked (`.gitignore`'d), so it can
silently drift from what's actually merged on `origin/master`. At the time
`SPEC.md` was drafted, exactly this was found: a working copy's `CLAUDE.md`
described `src/etl/queries.py` as a local, vendored copy of `portfolio-nlp`'s
`fetch_processed_articles` query, pinned to `portfolio-common` v1.0.0 — but
`origin/master` had already merged two further PRs retiring that local copy
in favor of the shared `portfolio_common.news_export` module and re-pinning
to `portfolio-common` v1.2.0.

**Approach**:

1. On a checkout confirmed up to date with `origin/master`
   (`git fetch && git status` shows no "behind" count), read
   `src/etl/news_to_rdf.py`, `pyproject.toml`'s `portfolio-common` pin, and
   `docs/portfolio-common-v1.2-engine-agnostic.md`.
2. Update `CLAUDE.md`'s description of `src/etl/` to describe
   `portfolio_common.news_export` as the read path (not a locally-vendored
   `queries.py`) and the actual `portfolio-common` version pin.
3. Point at `docs/portfolio-common-v1.2-engine-agnostic.md` alongside the
   existing `docs/portfolio-common-v1-migration-plan.md` reference (kept as
   history, not removed).
4. Confirm `CLAUDE.md` still references both
   `.specify/memory/constitution.md` and `.specify/memory/SPEC.md`.

**Acceptance criteria**:

- `CLAUDE.md`'s description of `src/etl/`'s database access matches
  `src/etl/news_to_rdf.py`'s actual imports and `pyproject.toml`'s actual
  tag pin (checked by inspection — `CLAUDE.md` is untracked, no automated
  lint).
- `CLAUDE.md` references both `.specify/memory/constitution.md` and
  `.specify/memory/SPEC.md`.
- `SPEC.md` §13 item 5 updated to note this reconciliation done for the
  checkout it was performed on (leave the item number in place — a *future*
  checkout could still drift again; constitution AI-behavior #2 covers that
  going forward, this item closes the specific instance found).

## Work item 3 — Stand up a triple store and wire the SHACL ingest gate (roadmap step 1)

**Why**: every downstream piece of the target architecture in `SPEC.md` §4
— named graphs, the reasoner, SPARQL, the agent layer — needs somewhere to
run against. (At planning time nothing was stood up and `schema/` was validated
only as flat files on disk, FR-001; this work item has since delivered the store.)

**This is partly an infrastructure decision, not purely a code task** —
similar in kind to `portfolio-nlp`'s `PLAN.md` Work item 2 (a runnable CI
gate blocked on a maintainer's runner choice). Choosing and provisioning
GraphDB vs. Fuseki is the repo owner's call to make before implementation
detail can be planned further.

**Approach** (coarse — refine once the store choice is made):

1. *(maintainer)* Choose GraphDB or Fuseki and how it's hosted (container in
   the devcontainer, a separate service, …).
2. Containerize/configure it; load `tbox.ttl → shapes.ttl → reference.ttl →
   rules.ttl → instances.trig` in that order into a fresh repository/dataset.
3. Lock the reasoning profile per `07-ontology-topology.md` (OWL 2 RL/RDFS+:
   `subClassOf` transitivity on, property chains off) in the store's config.
4. Wire a `pyshacl`-based ingest gate in front of write access — reject,
   don't silently accept, a write that fails `shapes.ttl` conformance.
5. Document the running store's connection details in `.env.example` and
   `docs/` the way `SQL_URLS_DB`/`SQL_NLP_DB` are documented today.

**Acceptance criteria**:

- A running store loads the four static files + `instances.trig` and answers
  a basic SPARQL query (`SELECT * WHERE { ?s a :Asset } LIMIT 5` or
  equivalent) over HTTP/the store's client.
- A deliberately-malformed write (missing a required SHACL property) is
  rejected by the ingest gate before it reaches the store, not merely logged
  after the fact.
- The reasoning profile matches `07-ontology-topology.md`'s documented
  choice, not a store's un-configured default.

**Status**: done (T-020–T-026). The store choice was GraphDB; see
`docs/graphdb-setup.md`.

## Work item 4 — Build the real step-2 projection (roadmap step 2, supersedes the `src/etl/` shortcut)

**Why**: `SPEC.md` §13 items 1 and 2 — the designed projection
(`financial-analysis`'s `v_*` views + `portfolio-nlp`'s `article_*` tables →
SHACL-validated, dated `ingest:{agent}:{date}` named graphs) doesn't exist.
Today's `src/etl/` is a narrower, already-working stand-in that reads only
`portfolio-nlp`'s RESULTS store and writes one flat file — useful for
validating the schema against real data now, but not the target
architecture, and not partitioned for the bitemporal audit trail
`07-ontology-topology.md` designs around.

**Approach**:

1. Enumerate and pin `financial-analysis`'s read contract. The T-007 scan
   found exactly 31 views in `src/kg_schema/views.py` (no wildcards):
   `v_analysis_run`, `v_pricing_run`, `v_quant_run`, `v_cycle_run`,
   `v_universe_coverage`, `v_universe_membership` (**frozen** — use
   `universe.db`), `v_sector`, `v_industry`, `v_score_snapshot`,
   `v_sector_aggregate_snapshot`, `v_price_observation`, `v_corporate_action`,
   `v_quant_return_daily`, `v_risk_free_rate`, `v_benchmark_series`,
   `v_sec_filing`, `v_sec_filing_section`, `v_veto`, `v_rule_catalog`,
   `v_data_quality_issue`, `v_portfolio_position`, `v_shared_executive_edge`,
   `v_cycle_ranking`, `v_weight_scheme`, `v_weight_component`,
   `v_quant_risk_model`, `v_quant_portfolio`, `v_quant_position`,
   `v_quant_frontier_point`, `v_quant_benchmark_performance`,
   `v_quant_vs_live` — plus `universe.db` for membership. T-030 then records,
   per view this repo reads, the exact columns it depends on (done as a
   Python module, `src/projection/view_contract.py`, which `SPEC.md` §2.6
   points to, so the drift check reads the same pin the docs cite), taken from that repo's `views.py`
   projection contract, and adds a check that fails on drift; views this
   repo decides not to read (Work item 11, T-108) are listed as such. This repo
   pins no contract on them today (§13 item 9's sibling risk on the
   `financial-analysis` side).
2. Design the write path: read each source, `INSERT DATA` into a fresh
   `urn:graph:ingest:{agent}:{date}` graph (Work item 3's store), SHACL-
   validated per row/batch against `shapes.ttl` on the way in — not a
   post-hoc sample check like today's `_shacl_check`/`_validate_sample`.
3. Decide `:supersededBy` semantics for a restatement (a corrected upstream
   value arriving after the original graph was written) — `07`'s bitemporal
   design implies this but no code exists yet.
4. Retire or fold in today's `src/etl/` shortcut once the real projection
   covers at least the SEMANTIC lane it currently handles (see Work item 5)
   — don't run both indefinitely as parallel, divergent code paths.
5. Grow the ABox from the shortcut's ~500-`:Asset`/news-only slice to the
   full universe across all agent lanes (TECHNICAL, FUNDAMENTAL, SECTOR,
   EDGAR, ORCHESTRATOR — the lanes `instances.trig`'s worked example already
   demonstrates one dated graph per lane for) once this projection can
   produce them.

**Prerequisite**: Work item 11 (the §2.6 drift decisions) — met: it closed
2026-10-05 (see `CHANGELOG.md`).

**Acceptance criteria**:

- A projection run against real `financial-analysis`/`portfolio-nlp` data
  produces one or more dated `ingest:{agent}:{date}` graphs in the Work
  item 3 store, each SHACL-conformant at write time (not just sampled after
  the fact).
- The full ~503-constituent universe and its available signals (not a
  5-asset or news-only slice) are represented once this lands.
- `src/etl/`'s role after this lands is explicitly documented (retired,
  folded in, or kept as a separate smoke-test path) — not left ambiguous.

**Blocked on**: nothing (Work item 11 closed 2026-10-05; the store from Work item 3 is in place).

## Work item 5 — ~~Implement the SEMANTIC score's per-`(asset, day)` aggregation~~ (SUPERSEDED — reassigned upstream)

**Status: SUPERSEDED (2026-10-02, T-007).** Not this repo's job: the
aggregation is a computation, and the upstream boundary note
(`portfolio-financial-analysis/docs/semantic-score-boundary.md`) assigns it
to `portfolio-nlp`, with `portfolio-financial-analysis` materializing
`score_snapshot[SEMANTIC]` and this repo stopping its own writes of that
score. Recorded in `SPEC.md` §2.2/§2.5/§13 item 11.

**What remains here** (folded into Work item 4): once the upstream cut-over
exists, project the `score_snapshot[SEMANTIC]` row from `v_score_snapshot`
as the SEMANTIC lane, and retire `src/etl/`'s per-article Sentiment
`ScoreSnapshot`s in the same step. Until then the per-article snapshots stay.
Open dependency (not ours to build): the `portfolio-nlp` aggregation stage and
`financial-analysis`'s `KG_NLP_DB` read are "designed, not built" in both
repos as of the scan.

## Work item 6 — Bring up the OWL RL reasoner and the SPARQL surface

**Why**: `SPEC.md` §4's target architecture reads and reasons over the
store Work item 3 stands up and the data Work item 4 projects into it —
neither the reasoner nor a query surface exists today.

**Approach**:

1. Confirm the chosen store's (Work item 3) reasoning support matches
   `07-ontology-topology.md`'s OWL 2 RL/RDFS+ profile natively, or select and
   wire an external reasoner if not.
2. Stand up the three documented SPARQL query patterns (`07`): "active
   universe" (unbound `validTo`), "latest snapshot per asset", "everything
   this agent wrote on this day" (one dated graph).
3. Expose the surface however the agent layer (Work item 7) will consume it
   — a thin query module in this repo, or a direct SPARQL endpoint the
   orchestrator calls.

**Acceptance criteria**:

- Each of the three documented query patterns returns correct results
  against Work item 4's real projected data (not just `instances.trig`'s
  worked example).
- Subclass-transitivity inference (e.g. a sector roll-up) is confirmed
  working without a property-chain inference the design explicitly excludes.

**Blocked on**: Work items 3 and 4.

## Work item 7 — ~~Decide and build the orchestrator~~ (DECIDED: delegate, nothing to build here)

**Status: DECIDED (2026-10-02, T-007).** `08-agent-architecture.md` designed
two LangGraph state graphs; the T-007 scan found the two-speed cycle already
implemented in `portfolio-financial-analysis`'s `cycle` package
(`cycle select` quarterly, `cycle monitor` daily, `cycle_checkpoint` resume,
T-1 contagion-lagged vetoes, `rule_catalog` → `veto` lane). With this repo's
scope fixed as purely integrative, the build-vs-delegate question resolves to
**delegate**: no orchestrator, scheduler or LangGraph code here.

**Correction (T-007 rescan)**: upstream's `cycle` is a relational-checkpoint
topological runner (Strands-era), not LangGraph, and **no scheduler or
cross-module orchestrator exists in any repo** (upstream `SPEC.md` §13 item 3,
§14). Delegating therefore moves the cycle *logic*, not a running cadence —
who triggers quarterly/daily runs was unassigned until the maintainer
(2026-10-02) assigned it to the future `portfolio-app` repo, which will call
the upstream endpoints as needed (T-108).

**What remains here**:

1. Project `cycle`'s outputs (`v_veto`, `v_cycle_ranking`,
   `v_portfolio_position`, `v_cycle_run`) into dated
   `ingest:ORCHESTRATOR:{date}` graphs — part of Work item 4, not a separate
   build.
2. Reconcile `08-agent-architecture.md` (and the roadmap's step 6) with the
   decision: the LangGraph design becomes reference for what the upstream
   `cycle` implements, not a build target (T-008).

**Acceptance criteria**: the decision is in `SPEC.md` §2.2/§2.5/§12 (done).

## Work item 8 — Regenerate `schema/protege-view.ttl`

**Why**: `schema/protege-view.ttl` is a generated, flattened bundle for
Protégé (which can't open `.trig`); it predates the 2026-08-23 class
taxonomy/`MetricType` revision and later edits, so it's stale.

**This is a manual, interactive task** (open the four authoritative sources
plus `instances.trig` in an actual Protégé session, export flattened Turtle,
re-add the `:sourceNamedGraph` annotation), not something to script
end-to-end — flag it for whoever next needs the Protégé view current.

**Acceptance criteria**: `schema/protege-view.ttl` reflects the current
`tbox.ttl`/`shapes.ttl`/`reference.ttl`/`rules.ttl`/`instances.trig` content,
confirmed by a diff review, not just a regenerate-and-forget.

## Work item 9 — Resolve the `ScoreSnapshotShape`/Sentiment `rawValue` divergence

**Why**: `ScoreSnapshotShape` required `normalizedScore` for every
non-`SectorRelativeMomentum` snapshot, but the ETL's Sentiment snapshots
carry only `rawValue` — the scale the veto-rule thresholds are defined on
(`SPEC.md` §5/§7). This produced one SHACL violation per Sentiment snapshot
in the sample/smoke check.

**Approach** (pick one, this is a schema decision — record which in
`schema/README.md`'s gap list the same way the other three implementation-
time gaps are documented):

1. Add a `rawValue`-only branch to `ScoreSnapshotShape` for `metricType =
   Sentiment` (a `sh:or` alternative, or a separate shape scoped by
   `sh:targetObjectsOf`/`sh:in` on `metricType`), **or**
2. Add a normalization step to the ETL so Sentiment snapshots carry
   `normalizedScore` too, converging on one comparison convention instead of
   two.

**Acceptance criteria**:

- The chosen fix is applied; the FR-001/FR-006 parse+`pyshacl` checks show
  zero violations for Sentiment snapshots in a sample run.
- `schema/README.md`'s gap list documents which of the two options was
  chosen and why, alongside its three existing worked-during-population
  gaps.

**Status**: done 2026-10-05 (T-080–T-083). Maintainer chose option 1 (shape branch); see
`schema/README.md`, refinement 2.

## Work item 10 — Complete `schema/README.md`'s directory map

**Status: DONE (2026-09-12).**

**Why**: a constitution-compliance audit found `schema/README.md` — which
both it and `CLAUDE.md` call "the authoritative map of this directory" (`.
specify/memory/constitution.md`'s Project structure #1) — never mentioned
two files that actually live in `schema/`: `protege-view.txt` (an earlier,
superseded generated bundle) and `taxonomy-quality-review-2026-08-23.md`
(the write-up of the `rdfs:subClassOf` taxonomy audit `schema/README.md`'s
own "Validation" section already references by name). A reader relying on
the README as the complete map would not know either file existed.

**Approach**: add both to the file listing near the top of
`schema/README.md`, alongside the existing note that `protege-view.ttl` is
generated and never hand-edited — no `schema/*.ttl`/`.trig` content changes.

**Acceptance criteria**:

- `schema/README.md` lists `protege-view.txt` and
  `taxonomy-quality-review-2026-08-23.md` alongside every other file in
  `schema/`.
- The schema parse+`pyshacl` check still passes (docs-only change).

## Work item 11 — Reconcile the ontology and ETL with the upstream contracts (T-007 rescan)

**Why**: the second T-007 pass (`SPEC.md` §2.6, D1–D16) found that
`portfolio-financial-analysis` moved well past the design this repo's ontology
was written against. Most gaps are *semantic*, not naming: a point-in-time
universe the ETL ignores, an `available_at` look-ahead guard the ontology
cannot express, veto stints vs. veto events, a rule catalog with different
ids and logic, a renamed score type that fails today's SHACL shape, candidate
(not asserted) executive edges. Writing the Work item 4 projection first would
encode them wrongly.

**Approach** (decide, record in `SPEC.md`/`schema/README.md`, then edit; one
decision may be "keep ours, translate on projection"):

1. Universe (D1): replace the ETL's live-Wikipedia asset master by
   `universe.db` → `:UniverseMembership` (T-100, done 2026-10-05).
2. Temporal model (D2): `availableAt`/`eventTime` properties vs. ingest-graph
   dates (T-101).
3. Veto lifecycle and rule catalog (D3, D4, D5): stint properties, the T-1
   predicate as SPARQL, upstream's six rules as `RuleDefinition`s, a
   `DataQualityIssue` decision (T-102–T-104).
4. Vocabulary (D6, D7): `QUANTITATIVE` → `VALORIZATION` in shapes/reference,
   run-provenance modelling incl. the `forensic_flags_json`/`prompt_hash`/`correction_rule` extras (T-105, T-106; both done).
5. Edges and quant scope (D10, D11): candidate-edge semantics (T-107 done); which quant
   outputs become individuals (T-108 done).
6. Read-contract gaps and moving parts (D8, D12, D13, D15, D16): list for
   upstream, assert `schema_version`, reconcile the `portfolio-common` pin
   (T-109, T-110, both done 2026-10-05; the D13 schema work moved to T-121, in Work item 12, and the read-contract gaps are to go to the upstream maintainer); SEMANTIC `score_method` discriminator and wording (D14,
   T-111, done 2026-10-05: `:scoreMethod`).

**Acceptance criteria**:

- Each of D1–D16 has a recorded disposition (adopted / translated /
  rejected / raised upstream) in `SPEC.md` §2.6. **Met for D1–D16 (T-112 and T-100, 2026-10-05).**
- Where a decision changes `schema/`, the FR-001 parse + `pyshacl` check
  passes and `schema/README.md`'s counts are updated (NR-001).
- No Work item 4 task starts before this one's items 1–4 are decided.

**Status**: closed 2026-10-05 (T-100–T-113 done; its tasks are in `CHANGELOG.md`; the parts that could not close moved to Work item 12). Maintainer decisions
(2026-10-02): D4 — upstream's rule catalog is final; D9 — `portfolio-app`
triggers the cycles. D11 — only finished, view-exposed quant numbers become individuals (T-108 done). D1 (2026-10-05) — `universe.db` is the asset master and the universe's source (T-100).

## Work item 12 — Integrate `portfolio-app`/`portfolio-reports` and model per-run weight schemes

**Why**: the two parts of Work item 11 that could not close there. (a) T-120: upstream's `api/` has
no run trigger and its docs name `portfolio-reports` as the trigger, while D9 names `portfolio-app`;
the split needs agreeing with upstream. (b) T-121: the D13 check found that upstream's weight
schemes (one per `cycle_run`, keyed by `score_type`, plus scalar knobs) do not map onto
`AttractivenessWeightScheme`/`WeightComponent` as modelled.

**Acceptance**: T-120's outcome is recorded in `SPEC.md` D9 and `docs/10`; T-121 changes pass the
FR-001 parse + `pyshacl` check and update `schema/README.md`'s counts (NR-001).

**Blocked on**: nothing. T-120's answer arrived 2026-10-05 and is recorded by T-150 (Work item 15); T-121 must first take in that reply's weight facts (see T-121).

## Work item 13 — A `pytest` suite for the code this repo owns

**Why**: NR-005 and `SPEC.md` §13 item 7 / §14 accept "no `pytest` suite" at the scale of `src/etl/`,
and §10 names the exception: *unless Work item 4's larger projection changes that calculus.* It
has. Work item 4 adds `src/projection/` (T-030 shipped `score_scale.py`, `view_contract.py` and
`contract_check.py`, verified only by hand) and will add the write path and the SHACL-on-write gate,
where a silent wrong number reaches the graph. `src/etl/`'s severity/G1–G3 formulas, ticker skip-set
and provenance-ID formatting are also untested (§10).

**The constitution gives no test-structuring rules today** (it has no testing section; §Executable
cmds lists none), so the first task amends it rather than invent a layout in a PR.
Proposed structure, mirroring the sibling repos (`portfolio-financial-analysis`, `portfolio-nlp`):
top-level `tests/` with flat `test_<module>.py` files and a `conftest.py`; hermetic (no network, no
GraphDB, no real `universe.db`/`urls.db`/`nlp.db`); fixtures built in memory; `pytest` in the `dev`
dependency group, run as `uv run pytest`; tests that need an upstream checkout or a live store are
marked (`integration`) and skipped by default. Whatever the review settles on is what T-131+ follow.

**Approach**:

1. Amend `constitution.md` (MINOR, per its Governance) with the testing rules above, then reverse
   NR-005, §10, §13 item 7 and §14 in `SPEC.md`; add the `uv run pytest` command to §Executable cmds.
2. Add `pytest` to the dev group and the `tests/` skeleton.
3. Write the pending tests: `projection/score_scale` (0, 50, 100, `None`, out of range, decimal
   exactness); `projection/contract_check` against a synthetic miniature upstream (a pin, then the
   same views with a column removed (drift), added and reordered (notes), plus an unlisted new view); `src/etl/common`
   (severity/G1–G3, GICS rollup, provenance IDs, Turtle literals); the FR-001 parse + `pyshacl` gate
   as a test.
4. Decide, and document, where the real-checkout drift check runs (see T-135).

**Acceptance**: `uv run pytest` passes hermetically on a clean checkout; the constitution
documents the structure; NR-005/§10/§13/§14 no longer claim there is no suite.

**Blocked on**: nothing for T-130–T-134; T-135 depends on how upstream exposes its contract (open).

## Work item 14 — `ScoreSnapshotShape` and store-gate follow-ups (PR #48 post-merge review)

**Why**: the post-merge review of PR #48 (Work item 9) found three gaps in the shape it rewrote and two
follow-ups its third review raised as optional but nobody filed: a `SectorRelativeMomentum` snapshot
with no value at all conformed; `rawValue` (an `owl:FunctionalProperty`) could appear twice; nothing
tied `agentOrigin` to `metricType`; `cli/verify_store.py` has never run against a live GraphDB with the
new acceptance probe; and `acceptance.check_gate` counts violations by matching pyshacl's text report.

**Approach**:

1. Tighten `ScoreSnapshotShape` (T-140): `rawValue` in `[-1, 1]` required for `SectorRelativeMomentum` (the
   range `docs/06` §1.8 defines; mapping upstream SECTOR into it is T-031's), `sh:maxCount 1` on `rawValue`, an `sh:xone` pairing each `agentOrigin` with its one
   `metricType`. Update `docs/06`, `schema/README.md` and every quad count (NR-001).
2. Run `cli/verify_store.py` once against the live repository (T-141).
3. Make `gate.validate` expose the results graph, and count `sh:ValidationResult` nodes in
   `check_gate` instead of matching text (T-142).

**Acceptance**: FR-001 parse + `pyshacl` pass with the new count; the store acceptance probe still
yields exactly one violation (`:timestamp`); T-141's run is recorded in `docs/graphdb-setup.md`; T-142's
`check_gate` does not depend on pyshacl's report wording.

**Blocked on**: T-141 needs a running GraphDB; nothing else.

## Work item 15 — Adopt upstream's `v_*` contract changes (reply of 2026-10-05)

**Why**: the `portfolio-financial-analysis` maintainers answered the gaps §2.6 lists as "raised
upstream" (D8–D14), checking their `master` at `0a528be` and their production and pilot databases.
They propose one additive view change and two later views; until they approve them, these are
proposals. Their reply also brings facts the drift register does not have yet:

- **`cycle_run.id` can be reused** after a deletion (`INTEGER PRIMARY KEY` without
  `AUTOINCREMENT`). Every production `shared_executive_edge` row carries `run_id = 1`, and
  `cycle_run` 1 is now a SELECTION run of 2026-09-22; the ENTITY_RESOLUTION run that wrote the
  edges is gone. So `cycle_run:<id>` (`:runId`, T-106) is not unique on its own.
- **`score_weights` holds the configured weights, not the blended ones.** Every run records
  FUNDAMENTAL 0.4, VALORIZATION 0.3, TECHNICAL 0.2, SEMANTIC 0.1. The blend renormalizes per asset
  over the components that asset has, and SEMANTIC is null for every asset today. T-121 assumes
  the opposite.
- **Two optimizer versions can coexist** (`opt-v1`, `opt-v2`, their T-137), and `v_quant_vs_live`
  does not expose `engine_version`, so its rows can mix both.
- **`first_seen`/`last_seen` on `v_shared_executive_edge` are NULL for every edge** by design, until
  their entity-resolution rework (their Work item 9, T-080–T-084).
- **Answered as we read them:** `live_book` is the live book's performance, not a benchmark;
  `equal_weight`/`cap_weight` are dead names; `LIVE_ONLY` rows have a NULL `benchmark_weight`;
  REPLAY runs never reach the production database (`cycle backfill` refuses it, their T-115), so
  projecting only production is sufficient; `prompt_hash` exists on FUNDAMENTAL rows only.
- **Run trigger (D9, T-120):** `portfolio-app` triggers and `portfolio-reports` reads. The trigger is
  the cross-module orchestrator command (their open Work item 2), run as a job by `portfolio-app`,
  not an `api/` endpoint; their `api/` stays read-only (FR-014 unchanged).
- **Not answered:** the SEMANTIC `score_method` value that replaces our `ASSET_DAY_AGGREGATE`
  placeholder, and their docs that still name this repo as the SEMANTIC writer (D14).

This repo reads and does not compute (§2.5). Where the reply leaves a number for us to derive
(per-asset effective weights, the current engine version, a unique run key), this work item asks
upstream to expose it instead of deriving it here.

**Approach**:

1. Record the reply in `SPEC.md` §2.6 (rows and dispositions D8–D14, D16, plus the run-id fact),
   which also closes T-120 (T-150).
2. Ask upstream for the changes this repo needs to read, not compute (to be sent to their maintainers
   with this work item; each is theirs to accept and track):
   - the additive view change they proposed: `v_fundamental_metric`; `forensic_flags_json` and
     `prompt_hash` on `v_score_snapshot`; `computed_at` and `run_id` on `v_shared_executive_edge`;
     `status` on `v_cycle_ranking` and a corrected docstring; `engine_version` on
     `v_quant_vs_live`, and the dead kind names removed;
   - in the same change, a marker of the current engine version in every view that keeps several
     (`v_fundamental_metric`, `v_quant_portfolio`, `v_quant_vs_live`), so this repo does not
     decide which version counts;
   - per-asset effective weights in `v_cycle_ranking` (the renormalized weight of each component),
     so this repo does not renormalize;
   - run ids that are never reused, and the orphaned `run_id` on the existing edges fixed;
   - the scale and units of what we project: `blended_score`, `components_json` keys, `raw_value`
     per `score_type`, the `v_fundamental_metric` metric names, the forensic-flag codes;
   - `v_media_cooccurrence_edge` with their T-082, and `first_seen`/`last_seen` filled by their
     Work item 9;
   - the SEMANTIC method value and their doc fix (still open from D14);
   - the trigger decision recorded in their SPEC (`portfolio-app` triggers, `portfolio-reports`
     reads);
   - a `schema_version` bump and the commit for each change, so the pin can follow.
3. Decide the run-id rule (T-151), then model the new data (T-152–T-156), each as its own schema
   change with the FR-001 parse + `pyshacl` check and the `schema/README.md` counts (NR-001).
   T-155 also removes the attractiveness formula from the schema and docs: the score is read from
   upstream's ranking, never computed here.
4. When upstream ships, re-pin `view_contract.py` and the `schema_version` floor (T-157) and replace
   the SEMANTIC placeholder (T-158).

**Declined from the reply**: `inputs_json` on `v_fundamental_metric` (the metric value and its
filing are enough); a stored daily market cap (the per-filing `market_capitalization` metric is
enough for size context); a replay flag (not needed while only production is projected); a run
trigger endpoint in their `api/`.

**Acceptance**: `SPEC.md` §2.6 has no D8–D14 item left as "raised upstream" without its answer
(D14 included, so this needs upstream's SEMANTIC method value, T-158);
every schema change passes the FR-001 parse + `pyshacl` check with updated counts; the projection
reads the new columns from a re-pinned `view_contract.py` and computes none of the values listed in
step 2; no doc or schema comment describes the attractiveness blend as computed here; T-120 is closed.

**Blocked on**: T-150, T-151 and T-155's removal of the blend formula on nothing; the rest of
T-152–T-158 on the upstream change each one reads
(T-153's forensic flags also wait on their T-074, T-154's MEDIA kind on their T-082). Closing this
work item also waits on upstream's D14 answer (T-158), which their reply did not give.

## Work item 16 — Validate upstream rows at the read boundary, before any triple is built

**Why**: T-030 pins upstream's `v_*` column *names*; nothing checks the *rows*. The graph gate
(`pyshacl`, FR-001) sees only the finished graph, so a value that is wrong but still legal passes it.
`ScoreSnapshotShape` already rejects a `normalizedScore` above 1, so an unconverted 0-100 score does
not get through; what does is a change of *meaning* that stays inside the accepted range, for example
upstream moving `normalized_score` to [0, 1], which passes the [0, 100] check and becomes a ~0.99 risk.
Its violations also name a triple, not the upstream row that caused it. Upstream's own reply (Work
item 15) shows the kinds of bad data to expect: a reusable run id, edge dates NULL for every row,
SEMANTIC null for every asset. A boundary check catches bad data before it becomes triples and says
which view (and, where the check has one, which row) is at fault; the reused run id is handled by
T-151 instead, and the two by-design NULLs are expected, not failures (step 1).

This is input-side validation of tabular data. It does not replace `pyshacl`, which stays the
closed-world gate on the graph (constitution, OWL and SHACL both present). A new validation *library*
is a different matter: Technological stock #6 makes adopting one a constitution-level change, so if
T-160 picks a library, T-161 is a separately proposed and reviewed amendment, done before the
dependency is added. Plain checks need none.

Limits: it cannot say whether upstream's numbers are *right* (that stays upstream's job, §2.5), and
it cannot detect a reversed polarity, which leaves values in range with the cohort mean still near 50.
Polarity rests on `score_scale.py`'s documented convention; T-030's drift check does not see it either,
since a polarity change leaves the column set untouched.

**Approach**:

1. Decide the failure policy and the tool (T-160). Policy first: stop the run on any failure, or
   quarantine the failing rows and report them. Either way, a check that has no offending row (row
   count, NULL rate, cohort mean) is reported against its view or group and stops the run, since there
   is nothing to quarantine. So the NULL-rate and row-count thresholds encode upstream's documented
   state: a column NULL for every row *by design* (SEMANTIC today; `first_seen`/`last_seen` on
   `v_shared_executive_edge` until their Work item 9) is expected, not a failure, and its expectation
   changes when upstream fills it (T-154 for the edge dates, T-158 for SEMANTIC). Tool second: list
   the checks needed (types, NULL rate, range, natural-key uniqueness, `available_at` against `event_time`, row count per view), then compare
   plain checks, pandera, deepchecks and Great Expectations against that list (dependency weight,
   fit with the pinned-contract style). Record the decision in `SPEC.md` §13 item 10 before any dependency
   is added.
2. Add the dependency (through a constitution amendment first, if it is a library) and write the
   expectations beside `view_contract.py`, for the views Work item 4 reads (T-161, T-162). The
   run-identity checks are not among them: T-151 owns those, because they compare a row with its run
   table and a failure there omits `:runId` instead of failing the row.
3. Run them on the read path, so T-031's first real projection already goes through them (T-163).
4. Test the selected policy and every check kind with synthetic frames under Work item 13's structure
   (T-164).

**Acceptance**: every view the projection reads has expectations; a violating row never reaches the
triple builder under the chosen policy; the failure message names the view and column, plus the row key
for a row-level check, or the group for an aggregate one; `uv run pytest` covers a passing and a failing
frame per check kind and the selected policy's behaviour; `SPEC.md` §13 item 10 records what is checked
at the boundary and what is not.

**Blocked on**: T-160 on nothing; T-161 onward on T-160 (and, for a library, on its constitution
amendment). T-163 lands with T-031; T-164 needs Work item 13's skeleton (T-131).

## Sequencing

```
Work item 1 (roadmap doc)   ─┐
Work item 2 (CLAUDE.md)      ├─ independent, cheap, no blockers — land first
Work item 9 (shape fix)      │  (2, 9 and 10 done)
Work item 10 (README map)   ─┘

Work item 3 (triple store)
        │
        ▼
Work item 4 (real projection; absorbs the SEMANTIC and ORCHESTRATOR lanes)
        │
        ▼
Work item 6 (reasoner + SPARQL)

Work item 11 (reconcile with upstream contracts) — closed 2026-10-05; it gated Work item 4
Work item 12 (app/reports integration, per-run weight schemes) — pending parts of 11, independent

Work item 5 (SEMANTIC aggregation) — superseded, reassigned upstream
Work item 7 (orchestrator)         — decided: delegate to financial-analysis `cycle`

Work item 8 (protege-view.ttl) — independent, manual, land whenever convenient
Work item 13 (pytest suite) — independent; T-130 (constitution amendment) first, ideally before Work item 4's code grows
Work item 14 (PR #48 follow-ups) — independent; T-140 done, T-141 needs a live GraphDB
Work item 15 (upstream's v_* changes) — T-150/T-151 now; the rest as upstream ships; feeds Work item 4 (T-031) and 12 (T-121)
Work item 16 (boundary validation of upstream rows) — T-160 first; T-163 lands with Work item 4's T-031
```

Work items 1, 2, and 9 have no dependencies and no blockers — they can land
immediately, in any order, in one PR or several. Work items 3, 4 and 6 follow
the roadmap's own dependency chain (a store before a projection, a projection
before a reasoner/SPARQL surface); 5 and 7 are no longer build items here. Work item 8 is independent of
everything but needs a human at a Protégé session, not code.

See `TASKS.md` for the discrete, checkable task breakdown.
