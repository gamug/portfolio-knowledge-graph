# PLAN.md — `portfolio-knowledge-graph`

The implementation plan for the live backlog identified in
`.specify/memory/SPEC.md`. Where the constitution is principles and
`SPEC.md` is the requirements/architecture contract, this document is the
"how, and in what order" for the work that contract still leaves open.

**This plan is not narrow the way a near-feature-complete repo's would be.**
`SPEC.md` §14's disposition table splits `SPEC.md` §13's nine open items into
two different categories, and most of them land on the larger side: only
three items (7, 8, 9 — no test suite, uncalibrated severity formulas, no
pinned SOURCE/RESULTS contract) are out of scope: items 7 and 8 permanently,
item 9 until T-172 decides. The other
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

Only the three items `SPEC.md` §14 places in **out of scope** (item 9 is
permanent only until T-172 decides) are excluded from this plan — everything else in `SPEC.md` §13 is a Goal
above, not a non-goal:

- Item 7 — adding a `pytest` suite for `src/etl/`: accepted at current
  scale; revisit only if Work item 4 grows the ETL's logic enough that
  end-to-end SHACL checking alone stops catching regressions.
- Item 8 — calibrating the G1/G2/G3/G9 severity formulas: a research task
  needing ground-truth labels this plan has no way to produce.
- Item 9 — pinning a formal SOURCE/RESULTS schema contract with
  `portfolio-nlp`: accepted risk at this scale, and the one non-permanent item here; reopened as a decision by
  T-172 (Work item 4, after T-033), and it becomes work only if that decision
  says so, for instance after a `portfolio-nlp` schema change actually broke
  the projection.
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
   value arriving after the original graph was written) — done 2026-10-12 (T-032):
   a correction known on a later day is a new individual in a new dated graph, linked by
   `:supersededBy` for a `SECFilingSection` (the gate's check 8) and by the latest-`timestamp`
   read for every other observation; only for the graphs whose date can be the day the correction
   became known (dated by ingestion, and EDGAR); in a graph dated by the data (ORCHESTRATOR,
   FUNDAMENTAL, quant, entity resolution, universe) a late correction is still lost for that date
   (SPEC §13 item 10); a second run for the same agent and day is refused by the gate (check 2); a re-run
   is a new automation in its own repository (Work item 17; replacing the graph, T-195, was cancelled 2026-10-13). The rule is in `07` ("Restatements and re-runs").
4. Retire or fold in today's `src/etl/` shortcut once the real projection
   covers at least the SEMANTIC lane it currently handles (see Work item 5)
   — don't run both indefinitely as parallel, divergent code paths.
5. Grow the ABox from the shortcut's ~500-`:Asset`/news-only slice to the
   full universe across all agent lanes (TECHNICAL, FUNDAMENTAL, SECTOR,
   EDGAR, ORCHESTRATOR — the lanes `instances.trig`'s worked example already
   demonstrates one dated graph per lane for) once this projection can
   produce them.
6. Decide whether to define a read contract with `portfolio-nlp` (T-172), once T-033 has
   settled whether `src/etl/` survives. Until then `SPEC.md` §13 item 9 stands as an accepted
   risk: the only NLP read is the tag-pinned `news_export.fetch_processed_articles`.
7. The Contract v18 ontology half (T-206, 2026-11-01) is in: the 11 classes for the m015/m016/m018
   views, 31 SHACL shapes, and the 10 selection + 5 GUARD rules, with the handoff §3.3 nullable
   columns left optional. `UTILITY_CASH_COVERAGE`'s `validFrom` is 2026-10-14, the real T-071 part
   2a merge date (T-216, 2026-11-03; it was 2026-10-31, the last safe date, until then). The eight
   m018 projectors are built (T-207, 2026-11-02):
   `src/projection/backtest.py` writes one append-only graph per run,
   `urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}` (Work item 20 added the
   label), with a dry run by default and
   `--write` behind the ingest gate; the source check reads `v_book.run_status` rather than
   `v_cycle_run`; no store was reloaded then, and the reload landed with T-212 on 2026-11-02. The
   m015/m016 views (`v_ticker_history`,
   `v_orchestrator_run`, `v_orchestrator_step`) landed in Work item 27 (T-208, 2026-11-04).
   FIBO Phase 1 (T-210, 2026-11-03) is in too: six `rdfs:seeAlso` links from
   `schema/fibo_terms.csv` in `tbox.ttl` and (for the four terms it declares)
   `kg_target_schema.ttl`, the two broken `https://www.omg.org/spec/EDMC-FIBO/` links removed, and
   `cli/check_fibo_terms.py` checking every linked IRI against the pinned FIBO 2026Q2
   `prod.ttl.zip`. FIBO is a reference vocabulary, not a dependency: no import, no equivalence and
   no reasoning over its axioms. FIBO Phase 2 (T-211, 2026-11-03) is in too:
   `schema/fibo.ttl` holds the 54-entry/277-statement glossary slice (25 reviewed seeds, 29
   ancestors, the Spanish `@es` layer and the version/sha256/licence header),
   `schema/fibo_terms.csv` carries the 25 rows, the 27 pre-existing leaf classes have `@es` text,
   and the ETL emits the `:SP500Index` link. The slice loads into `urn:graph:reference:fibo` after
   `reference.ttl`; the store was reloaded with T-212 on 2026-11-02 and the live Appendix A queries
   ran with T-213, and the generated `protege-view` files still carry the old IRIs until
   T-070/T-071.

**Prerequisite**: Work item 11 (the §2.6 drift decisions) — met: it closed
2026-10-05 (see `CHANGELOG.md`).

**Acceptance criteria**:

- A projection run against real `financial-analysis`/`portfolio-nlp` data
  produces one or more dated `ingest:{agent}:{date}` graphs in the Work
  item 3 store, each SHACL-conformant at write time (not just sampled after
  the fact).
- The full ~503-constituent universe and its available signals (not a
  5-asset or news-only slice) are represented once this lands.
- The eight m018 backtest/GUARD views project into one append-only graph per run
  (`urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}`) through the ingest gate,
  with a dry run by default (T-207, labelled by T-231).
- `src/etl/`'s role after this lands is explicitly documented (retired,
  folded in, or kept as a separate smoke-test path) — not left ambiguous.

**Blocked on**: nothing (Work item 11 closed 2026-10-05; the store from Work item 3 is in place).

## Work item 5 — ~~Implement the SEMANTIC score's per-`(asset, day)` aggregation~~ (SUPERSEDED — reassigned upstream)

**Status: SUPERSEDED (2026-10-02, T-007).** Not this repo's job: the
aggregation is a computation, and the upstream boundary note
(`portfolio-financial-analysis/docs/semantic-score-boundary.md`) assigns it
to `portfolio-nlp`, with `portfolio-financial-analysis` materializing
`score_snapshot[SEMANTIC]` and this repo stopping its own writes of that
score. Recorded in `SPEC.md` §2.2/§2.5/§13 item 11. The materialization is
disputed by upstream's reply of 2026-10-06, which names this repo as the future
writer (`SPEC.md` §2.6 D14, raised by T-158); the computation staying in
`portfolio-nlp` is not.

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

**Blocked on**: nothing; both done. T-120's answer is recorded by T-150 (Work item 15); T-121 (PR #65) made a per-run scheme an immutable observation dated by `:cycleDate`, not a valid-time record.

## Work item 13 — A `pytest` suite for the code this repo owns

**Why**: NR-005 and `SPEC.md` §13 item 7 / §14 accept "no `pytest` suite" at the scale of `src/etl/`,
and §10 names the exception: *unless Work item 4's larger projection changes that calculus.* It
has. Work item 4 adds `src/projection/` (T-030 shipped `score_scale.py`, `view_contract.py` and
`contract_check.py`, verified only by hand) and will add the write path and the SHACL-on-write gate,
where a silent wrong number reaches the graph. `src/etl/`'s severity/G1–G3 formulas, ticker skip-set
and provenance-ID formatting are also untested (§10).

**The test structure is set by constitution 1.5.0** (Project structure #10, Code & Git #9), modelled
on the sibling `portfolio-financial-analysis`: top-level `tests/` with flat `test_<module>.py` files,
a `conftest.py` and `tests/fixtures/`; hermetic (no network, no GraphDB, no real
`universe.db`/`urls.db`/`nlp.db`); `pytest` in the `dev` group, configured in
`[tool.pytest.ini_options]`, run as `uv run pytest`; tests that need an upstream checkout or a live
store are marked `integration` and deselected by default; `tests` type-checked by mypy. T-131+
follow it.

**Approach**:

1. Amend `constitution.md` (MINOR, per its Governance) with the testing rules above (done, 1.5.0),
   then reverse NR-005, §10, §13 item 7 and §14 in `SPEC.md` once the suite exists (done with T-134,
   PR #62; §10 and §13 item 7 were first updated by T-133, PR #61).
2. Add `pytest` to the dev group and the `tests/` skeleton.
3. Write the pending tests: `projection/score_scale` (0, 50, 100, `None`, out of range, decimal
   exactness, `"FUNDAMENTAL"` rejected per T-171); `projection/contract_check` against a synthetic miniature upstream (a pin, then the
   same views with a column removed (drift), added and reordered (notes), plus an unlisted new view); `src/etl/common`
   (severity/G1–G3, GICS rollup, provenance IDs, Turtle literals); the FR-001 parse + `pyshacl` gate
   as a test; `src/kg_store/` (loader, ingest gate, `acceptance.check_gate`) against a fake store
   and `cli/check_view_contract.py`'s exit code via subprocess (T-136). The rest of `src/etl/` is transitional (T-033) and is backfilled
   only if it survives.
4. Decide, and document, where the real-checkout drift check runs (T-135, decided 2026-10-08): an
   `integration` test against a pinned upstream checkout, not a check by the projector. Ask
   upstream for a contract endpoint in its FastAPI, metadata only (T-173), and consume it when it
   ships: done 2026-10-11, `cli/check_view_contract.py` reads it (and checks the two versions).

**Acceptance**: `uv run pytest` passes hermetically on a clean checkout; the constitution
documents the structure; NR-005/§10/§13/§14 no longer claim there is no suite.

**Blocked on**: nothing for T-130–T-134 and T-136; T-135 is done (an `integration` test, `PFA_CHECKOUT`) and T-173 is done (the endpoint exists, `cli/check_view_contract.py` reads it), neither blocking.

## Work item 14 — `ScoreSnapshotShape` and store-gate follow-ups (PR #48 post-merge review)

**Status**: closed 2026-10-13 (every task done, T-195 cancelled; its tasks are in `CHANGELOG.md`).

**Why**: the post-merge review of PR #48 (Work item 9) found three gaps in the shape it rewrote and two
follow-ups its third review raised as optional but nobody filed: a `SectorRelativeMomentum` snapshot
with no value at all conformed; `rawValue` (an `owl:FunctionalProperty`) could appear twice; nothing
tied `agentOrigin` to `metricType`; `cli/verify_store.py` has never run against a live GraphDB with the
new acceptance probe; and `acceptance.check_gate` counts violations by matching pyshacl's text report.

**Approach**:

1. Tighten `ScoreSnapshotShape` (T-140): `rawValue` in `[-1, 1]` required for `SectorRelativeMomentum` (the
   range `docs/06` §1.8 defines; mapping upstream SECTOR into it is T-031's), `sh:maxCount 1` on `rawValue`, an `sh:xone` pairing each `agentOrigin` with its one
   `metricType`. Update `docs/06`, `schema/README.md` and every quad count (NR-001).
2. Run `cli/verify_store.py` once against the live repository (T-141, done 2026-10-08: passes; it found the
   store's schema graph older than `schema/` and a conflicting leftover graph, fixed by step 5; the guard is step 6).
3. Make `gate.validate` expose the results graph, and count `sh:ValidationResult` nodes in
   `check_gate` instead of matching text (T-142).
4. Let the gate take the worked example's own batches (T-146, found by T-136's tests; done 2026-10-10): three
   `instances.trig` graphs failed `gate.validate` taken alone (references typed in another graph;
   `:clearedOn`). `ingest` now reads what the store holds about the individuals a batch points at and
   `validate` checks the batch beside it; `:clearedOn` closes a Veto stint like `:validTo` closes a record.
   The context is only the properties the referenced classes' shapes read (plus an Asset's memberships'
   `validTo`), not the individual's whole history. `--check` has no store, so it cannot resolve such
   references and says so when it rejects.
5. Bring the live store in line with `schema/` (T-174, found by T-141, done 2026-10-08): reload `schema/` with
   `cli/load_schema.py`, then export and drop the leftover `urn:graph:ingest:QUANTITATIVE:2026-08-05`
   (the loader does not touch it; it duplicated five snapshots of the `VALORIZATION` graph with the
   old `:agentOrigin`, so the store was inconsistent until it went). Both were writes to production,
   made after the maintainer's go-ahead; the record is in `docs/graphdb-setup.md`. T-177 later put the store two triples behind
   `schema/` again; step 8 (T-179) reloaded it.
6. Make `verify_store` fail on a `schema/` graph of the wrong size and on an individual with more than one
   `:agentOrigin` (or a value outside the allowed list); graphs `schema/` does not own are reported, not
   failed, so projections can write there (T-176, read-only, with tests, no go-ahead needed; done 2026-10-08).
7. `integration` tests for the exit codes of `verify_store.py`, `load_schema.py` and `ingest.py` (T-175);
   the two that write use a repository of their own, never `portfolio`. Done 2026-10-08; `portfolio.app` cannot create a
   repository (HTTP 403), so those tests need `KG_ADMIN_USER`/`KG_ADMIN_PASSWORD`.
8. Reload the live store after T-177 changed `shapes.ttl` (T-179): done 2026-10-10 after the maintainer's go-ahead;
   the store then held 2549 triples (2550 since T-193) and `verify_store` passed (`docs/graphdb-setup.md`).
9. Two limits of the gate found in PR #86's review: a closing triple is not checked against the store (T-180), and
   `select` dropped a literal's datatype, so the context took the declared one (T-181, done: `GraphDB.select_terms` keeps it).
10. A Veto's `clearedOn` against its `lastSeenOn` (T-185, found in PR #90's review; the maintainer's decision of
   2026-10-11, PR #94). Cycles are at least 15 days apart and a cycle that clears a stint did not see it raised, so a
   sighting later than the clearing is a contradiction and a closed stint is never edited. It is checked at three
   places: the gate, when a stored Veto is cleared (done, T-185); `VetoShape`, when a batch declares a Veto with both
   dates, which is how backtests load past stints (done, T-185); and the read boundary, quarantining the `v_veto`
   row (T-192, Work item 16, after T-031's vetoes lane). The same day passes, an assumption about upstream's
   `last_seen_on` on the clearing cycle, to be asked of upstream (listed in T-191). The gate appends a later cycle's `lastSeenOn`
   to a stored Veto that is not cleared, on a date not before it was raised and later than its latest sighting (done, T-194, PR #96). The store reload after the `shapes.ttl` change (T-193) was the maintainer's, as T-179 was: done 2026-10-12, the store holds 2550 triples and
   `verify_store` passes (`docs/graphdb-setup.md`).
11. ~~A same-day re-run replaces its graph (T-195, from T-032, the maintainer's decision of 2026-10-12, PR #102).~~
   Cancelled 2026-10-13 by the maintainer: a re-run with other settings, or after a fix, is to be a new automation (one realization of the algorithm) built in its own GraphDB repository, so no graph is ever replaced (Work item 17, T-196–T-200). The design this replaced (check 6 reading the store minus the replaced graph, a constitution exception for invariant 1) is in `CHANGELOG.md`, T-195.

**Acceptance**: FR-001 parse + `pyshacl` pass with the new count; the store acceptance probe still
yields exactly one violation (`:timestamp`); T-141's run is recorded in `docs/graphdb-setup.md` (done); T-142's
`check_gate` does not depend on pyshacl's report wording; T-146 dropped the three strict `xfail`s in
`tests/test_kg_gate.py` (done); T-174 leaves every graph of the store at its expected size with no leftover;
T-176's `verify_store` fails on a stale or doubled store (it would have failed on the store before T-174; the fake-store tests show it) and exits 0 on a healthy one (done: the live store passes); T-175's tests pass or skip; T-179 leaves the live store at `schema/`'s 2549 triples with `verify_store` exiting 0 (done). T-146 leaves the gate accepting every worked-example graph beside what the store holds about the individuals it points at, with the three `xfail`s gone and `--check` saying why it cannot resolve them (done); T-180 (done) makes it refuse a closing triple whose subject is not a stored record (or Veto) or is already closed, and T-181 (done) keeps a stored literal's datatype in the context, so a literal of the wrong datatype fails its shape. T-185 (done) refuses a clearing earlier than a sighting at the gate and in `VetoShape`; the store is back at `schema/`'s count after T-193 (done: 2550 triples), so `verify_store` exits 0 again. T-194 (done, PR #96) appends a later cycle's `lastSeenOn` to a stored open Veto. T-195 was cancelled (2026-10-13).

**Blocked on**: nothing (closed). T-186 (the live `verify_store` run for T-181's new check) and T-193 (the store reload after T-185's shape) are done, 2026-10-12. T-194 (append a `lastSeenOn` to a stored Veto, PR #96) is done.

## Work item 15 — Adopt upstream's `v_*` contract changes (replies of 2026-10-05, 2026-10-06 and 2026-10-09)

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
  projecting only production is sufficient (step 4 also admits a pilot with no REPLAY run);
  `prompt_hash` exists on FUNDAMENTAL rows only.
- **Run trigger (D9, T-120):** `portfolio-app` triggers and `portfolio-reports` reads. The trigger is
  the cross-module orchestrator command (their open Work item 2), run as a job by `portfolio-app`,
  not an `api/` endpoint; their `api/` stays read-only (FR-014 unchanged).
- **Not answered:** the SEMANTIC `score_method` value that replaces our `ASSET_DAY_AGGREGATE`
  placeholder, and their docs that name this repo as the SEMANTIC writer (intended, per their
  second reply; disputed, D14, T-158).

This repo reads and does not compute (§2.5). Where the reply leaves a number for us to derive
(per-asset effective weights, the current engine version, a unique run key), this work item asks
upstream to expose it instead of deriving it here.

**Second reply (2026-10-06, their `master` at `597832a`, checked against production, the pilot and
its replay copy).** They accept the asks of step 2 as two tasks of theirs: **T-144** (one additive
view change) and **T-145** (ids that are never reused). They also correct six assumptions of ours.
In four cases, rows they write today would fail our shapes, and they will not change their values
to fit:

- **SECTOR `raw_value` is in TECHNICAL points:** the asset's TECHNICAL raw score minus its sector's
  mean (`v_sector_aggregate_snapshot.mean_raw`), so in [-100, 100]. They observed -54 to +46, and
  34 of 40 production rows fall outside the [-1, 1] that `ScoreSnapshotShape` requires of
  `SectorRelativeMomentum` (T-140). SECTOR rows also carry a 0-100 `normalized_score`.
- **`blended_score` can be negative:** the weighted mean of the normalized components (0-100, higher
  = more attractive) minus, per active SOFT stint, its rule's `penalty_points` (or `soft_veto_penalty`, 15 by default, if the rule declares none, a HARD rule's SOFT stint included: assumed, T-189). An asset with
  no component gets 0.0, not NULL. A ÷100 breaks `attractivenessScore`'s [0, 1].
- **Only FUNDAMENTAL rows have `available_at`;** it is NULL on every TECHNICAL, VALORIZATION and
  SECTOR row, which `ScoreSnapshotShape` rejects. Their T-144 fills it *in the view* with the cycle date
  (the score's `event_time`, the day their own `rank` reads it), so it is read here, not derived.
- **`metric_name` has no group prefix** (`debt_to_equity` in group `leverage`); the dotted id exists
  only in `v_rule_catalog.param_metric`. Their T-144 adds `metric_id` (`metric_group || '.' ||
  metric_name`) and `unit` (`ratio` = fraction, `x` = multiple, `usd`) to `v_fundamental_metric`.
- **`is_current` marks at most one row per key, not exactly one:** current is the newest version per
  metric group, by their explicit version order, so a filing not recomputed under it has no
  current row (their cycle does not read it either). Quant: the newest `opt-v*` per
  `(as_of, kind)`. `engine_version` strings carry a suffix (`opt-v1+9d34ff69`) and stay opaque.
- **`v_weight_scheme.scheme_id` is the position-weighting rule** (`score_proportional`,
  `score_tilt`), not the blend. A blend is identified by its `cycle_run`; its configured weights
  are `v_weight_component`.

Also from that reply:

- `forensic_flags_json` (their T-074) is an object of four booleans: `data_error_suspected`,
  `negative_equity_buyback`, `value_destroyer_sub_wacc`, `severe_sbc_dilution`. "Evaluated, none
  fired" is all four `false`, not `[]`; the codes are the keys set to `true`. NULL on every row today
  and on every non-FUNDAMENTAL row.
- `computed_at` is ISO 8601 UTC written with `+00:00`, not `Z`.
- Ids can be reused on all four run tables **and `sec_filings`**, only after a deletion: a manual
  one emptied production's `cycle_run`, and their T-120 repair deletes stale filing rows. Their
  T-145 makes them `AUTOINCREMENT` and adds a run-type check to their pilot verifier. Their T-100
  rebuilds the database, which drops the orphaned edge `run_id`s; the accession number is a stable
  filing key.
- `schema_version` advances only through migrations, so each contract change adds a marker
  migration. Production is at 8, below our floor (9 until T-157, 12 since 2026-10-12; D16); the pilot copy we read
  is at 12; their T-100 starts a fresh database.
- `normalized_score` is cohort-relative (50 + 10·z, clamped to [0, 100]), so `1 - x/100` is a
  relative risk reading, not an absolute level.
- Our `:inverted` comment calls `ScoreFinanciero` inverted, while the example we sent them set it
  `false`.
- **Their weights change (their T-141):** new runs blend FUNDAMENTAL, VALORIZATION and TECHNICAL at
  1/3 each, and SEMANTIC leaves the blend until their Work item 4; older runs keep the four keys
  (0.4/0.3/0.2/0.1). The per-asset renormalization is unchanged.
- **Placed and deferred:** the `v_media_cooccurrence_edge` view and `first_seen`/`last_seen` (with
  their T-082) and the SEMANTIC method value (with their Work item 4) wait until after their T-100.
  The SEMANTIC-writer doc fix goes with their T-141, but their reply says the future writer is
  this repo, which contradicts `SPEC.md` §13 item 11 (raised by T-158 before their T-141, recorded
  in D14); the trigger split in their SPEC goes with their Work item 2. Their order, all in their
  numbering: their Work item 8 (their T-141 and T-074), then their Work item 19 (their T-083,
  T-142, T-144 and T-145), their Work item 2, their final pilot (their T-143), their T-100. They
  send the commit, `schema_version` and doc section when their T-144 and T-145 land.

Every correction is resolved here by reading their value as documented, never by fitting it: the
shapes widen to their documented ranges, and a ÷100 stays the only conversion (a unit change;
`normalized_score` keeps its existing `1 - x/100` risk reading, T-030). The reply to send back
(step 2) states each decision and carries the updated target schema.

**Third reply (2026-10-06, same `597832a`, checked against production, the pilot and its replay
copy, answering our second follow-up's five questions).** All six corrections of the
second reply checked out. One assumption of ours needs correcting, and it changes a declined item:

- **`v_cycle_ranking_component.component_value` does not repeat a `ScoreSnapshot` value, for
  FUNDAMENTAL.** A FUNDAMENTAL row is written once per filing, but every cycle re-normalizes that
  filing's latest raw score against *that cycle's* cohort and overwrites the same row's
  `normalized_score` in place (`src/cycle/orchestrator.py`'s normalize step). So the stored value
  is always the last cycle's, while a ranking row's `component_value` is the value *that run*
  actually used — they differ on 33 of 40 production rows, 1 of 60 pilot rows and 2,267 of 2,799
  (81%) replay rows. TECHNICAL, VALORIZATION and SECTOR rows are unaffected: each belongs to one
  cycle date, never rewritten. Their T-144 keeps `component_value` (and `configured_weight`) in
  the view regardless. This reverses the "Declined from the reply" item below for
  `component_value`; `configured_weight` stays declined, since nothing in this correction touches
  its reasoning (it still repeats `v_weight_component`).
- **This also means a FUNDAMENTAL `ScoreSnapshot`'s `normalizedScore` is not immutable at the
  source** — projected twice, the same individual's value could read differently, which breaks
  this ontology's audit-trail principle (constitution; `docs/06`'s conventions). Upstream leaves
  the fix to us and names two options: drop it, or treat it as "as of the last cycle". **Decided:
  drop `normalizedScore` from FUNDAMENTAL `ScoreSnapshot`s (T-171)** — the per-cycle,
  cohort-relative value now lives correctly scoped to one `cycle_run`, as `component_value` on
  `AttractivenessSnapshot`'s effective-weight `WeightComponent` (T-155), which this correction
  already gives us. FUNDAMENTAL's raw score, `event_time`, `available_at` and every other column
  are stable at the source, so `rawValue` is what the snapshot carries instead — mandatory, like
  it already is for `SectorRelativeMomentum`/`Sentiment`, so dropping `normalizedScore`'s
  requirement (optional, not forbidden, so neither the FUNDAMENTAL individuals already in
  `instances.trig` nor the closed design-history rules that compare on `ScoreFinanciero`'s
  `normalizedScore` stop conforming) doesn't leave the snapshot free to carry neither value. Its
  bounds are a new open question (Q6, below; asked on 2026-10-07; answered 2026-10-09: [0, 100], T-177).
- **The five questions, answered** (folding into `SPEC.md` §2.6's D6/D13/D16, T-170): **Q1**, a
  no-component asset has no dedicated marker — it is always `vetoed = 1` with `"UNSCORED"` in
  `veto_rules_json` (D4), detected exactly as planned, by its missing component rows. **Q2**,
  `rank` excludes nobody (exclusion happens downstream in `positions`), and their T-144 will
  produce one component row per non-null component of every ranking row, whatever
  `vetoed`/`selected` say, with a test asserting it; `vetoedAtRanking` is true only for a HARD
  veto or `UNSCORED` — a SOFT veto alone never sets it, so our worked example's SOFT-only vetoed
  row needs a HARD veto added to stay consistent. **Q3**, SECTOR's `normalized_score` uses the
  same 50 + 10·z function as the other lanes, but the cohort mean sits close to 50, not exactly on
  it (winsorization and the clamp shift it), so T-162's guard needs a tolerance, and that guard
  must run over `v_cycle_ranking_component.component_value` per `(cycle_run_id, score_type)`, not
  over `ScoreSnapshot` rows, which (for FUNDAMENTAL) mix cohorts across cycles. **Q4**,
  `accession_number` is never NULL (0 of 5,076 production rows, 0 of 449 pilot rows) but is not
  unique in production — 30 numbers shared by 60 legacy rows predating their T-091 — though that is
  harmless since production is already excluded by T-157's schema floor; it is unique in the pilot
  and will be in their T-100 rebuild, and their T-145 adds a verifier check for it. **Q5**,
  `target_weight`/`max_name_weight`/`max_sector_weight` are all fractions of the book ([0, 1] as
  our shapes already assume); `max_name_weight` stays optional (`NULL` on a MONITORING run by
  default); the recorded value is the *effective* cap on a SELECTION run, the *configured* value
  on a MONITORING run.
- **What they add to T-144/T-145:** keep `component_value` and `configured_weight` in
  `v_cycle_ranking_component`; a test asserting Q2's one-row-per-non-null-component rule;
  `docs/kg_schema.md` states FUNDAMENTAL's rewrite behaviour, the Q1 rule, Q3's normalization and
  Q5's units; T-145 adds the accession-number uniqueness check.
- **Pilot REPLAY:** `financial_pilot.db` holds 0 REPLAY runs; their backfill ran on a separate,
  unshared copy. Their next pilot (T-143) is a fresh database.

**Fourth reply (2026-10-07, T-031, their `master` at `49d7438`).** Recorded here with the other
replies, under T-031 (which asked it), not as part of this work item's steps below; `SPEC.md` §2.6
holds the matching block. We asked how to read their schema version, and asked Q6. They confirmed
the read rule and did not answer Q6:

- **The floor is `SELECT MAX(version) FROM schema_version`**, the rule their own code uses.
  `PRAGMA user_version` is not theirs and stays 0. An empty or missing table means `migrate` was
  never run and reads as 0, below our floor (PR #73). Only `version` carries the contract; a
  change to how it is stored would be announced first.
- **Each contract change adds a row**, and only `migrate` adds one: their T-144 ships a marker
  migration, their T-145 a table-rebuild migration.
- **The views and the floor move in separate steps:** views are rebuilt on every run, the floor
  only when `migrate` runs, so a database can show new views under the old floor. Read the floor
  as "at least this contract"; their view changes are additive, and their T-144 stops older code
  from rebuilding (downgrading) the views. Fresh databases (their T-143, T-100) run `migrate`
  first.
- **Cycle rows with a NULL `available_at`:** skipping and counting them until their T-144 is the
  right behaviour on our side.
- **Q6 (the range of `raw_value`) was still open here; answered in the fifth reply (2026-10-09): [0, 100], bounded by T-177.** Q7 was not asked yet.
- **Fifth reply (2026-10-09, `SPEC.md` §2.6):** upstream accepted the contract endpoint (their T-152, T-173 here), landed their T-144 (`schema_version` 10, T-157 here) and answered Q6 (T-177); their statement about production's version was disputed (settled in the sixth reply: production is at 8). Two new tasks follow from the review of the record, besides T-173 and T-157: T-177 (the shape bound) and T-178 (the pin's loader learns `contract_version`, before T-157's re-pin writes it).
- **Sixth reply (2026-10-10, `SPEC.md` §2.6):** upstream's T-152 landed (the two routes); production's `schema_version` is 8 and the pilot's 9, so the floor stayed 9 and refused production (until T-157, 2026-10-12: now 12); Q7 answered; a version-10 database sent, a version-11 copy on request (the live service reports `contract_version` 12); content changes (weights, quant variant books, rule catalog, `expires_on`, price columns) were decided on 2026-10-11 (T-183): the rules and `penalty_points` (T-187), `expiresOn` (T-188), the penalty identity (T-189) and the three-component scheme (T-190) are taken, variant books are not projected, the price columns wait for a consumer; Q7's answer corrected T-031's reading of the year bounds (T-182, done 2026-10-11); T-157 waits for a database to re-pin against, at version 12 or their final pilot, to be asked.

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

   Sent 2026-10-06; accepted as their T-144 and T-145 (second reply). The answer to that reply
   restates the decisions below, sends the updated target schema, and asks five open questions,
   **all answered by the third reply** (above, T-170): how a no-component asset appears in
   `v_cycle_ranking` beyond its 0.0 score (Q1); whether `v_cycle_ranking_component` rows exist for
   vetoed or excluded assets (Q2); whether SECTOR's `normalized_score` is also 50 + 10·z (Q3,
   T-162); whether every `v_sec_filing` row has an accession number (Q4, T-151); and the unit of
   `target_weight`, `max_name_weight` and `max_sector_weight` (Q5, T-121, T-155). A sixth question
   is now open: FUNDAMENTAL `rawValue`'s bounds, needed before T-171's shape change can tighten
   past "optional" (asked with the next follow-up; answered in the fifth reply).
3. Decide the run-id rule (T-151), then model the new data (T-152–T-156), each as its own schema
   change with the FR-001 parse + `pyshacl` check and the `schema/README.md` counts (NR-001).
   T-155 also removes the attractiveness formula from the schema and docs: the score is read from
   upstream's ranking, never computed here. The second reply settles these decisions:
   - `SectorRelativeMomentum`'s `rawValue` is upstream's SECTOR `raw_value` verbatim, in TECHNICAL
     points, bounded to [-100, 100] (T-155, with T-031); positive = stronger than its sector.
     Its 0-100 `normalized_score` is rescaled like the three other lanes, giving SECTOR an
     optional `normalizedScore`; the third reply confirms it is the same 50 + 10·z function
     (Q3), with a tolerance, not equality, around the cohort mean (T-162).
   - `attractivenessScore` = `blended_score / 100`, higher = more attractive, at most 1 and with no
     lower bound (soft-veto penalties). No pre-penalty score is derived here (T-155).
   - A ranking row whose asset has no `v_cycle_ranking_component` row is skipped: its 0.0 is a
     placeholder, not a score (T-155). **Confirmed, third reply (Q1):** it is always `vetoed = 1`
     with `"UNSCORED"` in `veto_rules_json` (D4), with no dedicated marker beyond the missing
     component rows. **Q2:** `rank` excludes nobody, and their T-144 will produce one component
     row per non-null component of every ranking row regardless of `vetoed`/`selected`, with a
     test; `vetoedAtRanking` is true only for a HARD veto or `UNSCORED`, never for SOFT alone, so
     a worked example with only SOFT penalties needs a HARD veto added to be valid. **Also
     reversed (third reply, T-171):** read `v_cycle_ranking_component.component_value` verbatim
     onto each effective-weight `WeightComponent` as `:componentValue` — it does not repeat
     FUNDAMENTAL's `ScoreSnapshot` value, because that value is rewritten in place every cycle
     (see the third-reply paragraph above); `configured_weight` stays declined.
   - `availableAt` stays required; until their T-144 lands, cycle-lane rows have none and are not
     projected (never filled in here). Its `tbox.ttl` comment gains the cycle-lane definition, and
     `normalizedScore`'s says it is cohort-relative (T-153).
   - FUNDAMENTAL `ScoreSnapshot`'s `normalizedScore` is dropped (optional, not forbidden) rather
     than kept as a mutable-in-place exception to the immutable-observation principle (T-171); its
     `rawValue` is carried instead (mandatory, `minCount 1`, so dropping one required field doesn't
     leave the snapshot free to carry neither); bounded to `[0, 100]` by T-177 (Q6 answered).
   - Forensic flags: one `:forensicFlag` per key set to `true`, from the four documented keys, and
     a `:forensicFlagsEvaluated` boolean so "evaluated, none fired" differs from "not evaluated"
     (T-153).
   - `v_fundamental_metric`: `metric_name` verbatim, `metric_id` as the join to
     `ThresholdComparison.metricName`, `unit` verbatim; read only `is_current` rows, so a filing
     with no current row has no observation (T-152).
   - `:SECFiling` IRIs and joins are keyed by accession number, not upstream's `id` (T-151).
   - `schemeId` is the `cycle_run` the blend belongs to, and `scheme_id` becomes a separate
     book-weighting-rule property; `:inverted` is not emitted for upstream schemes (T-121).
     Schemes and ranking snapshots are keyed by a `cycle_run` id, so they rely on their T-145
     and T-100 (T-145 stops new reuse; the rebuild drops ids already reused). Until both have
     landed, only runs passing T-151's checks are projected (T-121, T-155), as T-151 itself says.
4. When upstream ships, re-pin `view_contract.py` and the `schema_version` floor (T-157; done
   2026-10-12 against the version-12 pilot: 32 views, floor 12, `contract_version` 12; re-pinned
   again by T-205 on 2026-11-01 to Contract v18 at `7658f78`: 44 contract views, floor 18,
   `contract_version` 18; the T-183 rule content and the drift check against upstream's commit
   remain) and replace the SEMANTIC placeholder (T-158). Project only from a database that meets the floor and holds
   no REPLAY run: a backfill writes REPLAY scores, vetoes and rankings into the shared tables,
   where they cannot be told apart from live rows (D8), and the `cycle_type <> 'REPLAY'` filter
   covers `v_cycle_ranking` only. Production (at 8 today) fails the floor. The pilot (at 9)
   qualifies once a read check finds no `cycle_run` with `cycle_type = 'REPLAY'` in it (rule in
   T-157, check in Work item 16's T-162, run by T-163);
   their T-100 rebuild qualifies on the same check; a replay copy never does.

**Declined from the reply**: `inputs_json` on `v_fundamental_metric` (the metric value and its
filing are enough); a stored daily market cap (the per-filing `market_capitalization` metric is
enough for size context); a replay flag (not needed while no replay copy is projected); a run
trigger endpoint in their `api/`; a pre-penalty attractiveness score (deriving it from the
effective weights would be a computation). From the second reply: `v_weight_component`'s
`configured_weight` on `v_cycle_ranking_component` (it repeats `v_weight_component`).
**Reversed by the third reply:** `component_value` is *not* declined — for FUNDAMENTAL it does
not repeat a `ScoreSnapshot` value (see above, T-171), so it is read (T-155).

**Acceptance**: no D8–D14 or D17 row of `SPEC.md` §2.6 still waits on upstream for this work item: every
question has its answer recorded and every accepted upstream change it reads has shipped, with its
commit (D14 included, so this needs upstream's SEMANTIC method value and the ownership answer, T-158);
every schema change passes the FR-001 parse + `pyshacl` check with updated counts; the projection
reads the new columns from a re-pinned `view_contract.py` and computes none of the values listed in
step 2; no doc or schema comment describes the attractiveness blend as computed here; T-120 is closed;
no shape rejects a value upstream documents as valid (the SECTOR `raw_value` range, a negative
`blended_score`), checked with synthetic rows at those bounds, and a filing with no current metric
row fails no shape; T-187 to T-190 (version 11's content, decided in T-183; T-187's code is PR #104 and T-188's is PR #105, their store reload landed with T-212 on 2026-11-02; T-201 picks the rule by `raisedOn`, T-203 lets the gate take a moved `expiresOn`, T-202 waits on upstream's T-071) are built or explicitly
deferred: the three-component scheme test (T-190, done 2026-10-12; the new rules with `penaltyPoints` are PR #104, `Veto` `expiresOn` is PR #105 and the penalty identity in the docs is T-189, PR #106, done 2026-10-14; the five price columns wait for a consumer, T-183 (3)); T-191 has recorded upstream's answers to the T-184 letter (the seventh reply, 2026-10-11: asks (1) to (5) answered; asks (6), (7) and (8), not in the letter, are open), so T-187 and T-188 are unblocked.

**Blocked on**: nothing for T-150, T-170, T-151's rule, T-155's formula removal, T-171's
`normalizedScore` drop, the shape corrections of step 3 (SECTOR range, `attractivenessScore`
bound, and the `tbox.ttl` comments) and T-158's ownership question (to be asked before their
T-141 ships its doc fix); upstream's T-144
(landed; T-157's re-pin is done in PR #97) for T-152–T-156's projection; their T-145 and T-100 for relaxing T-151's
checks; their T-074 for T-153's flag values; their T-082, after their T-100, for T-154's `MEDIA`
kind and edge dates; their Work item 4, after their T-100, for T-158's method value; T-187 and T-188 are no longer blocked (upstream's answer to the letter T-184 is the seventh reply, recorded by T-191, 2026-10-11), and T-190 needs nothing. Closing this
work item waits on what the acceptance names: T-158 (the ownership answer and the method value) and
the upstream changes this work item reads having shipped (their T-144, T-074 and T-082). Their T-145
and T-100 only relax T-151's checks and do not hold it open.

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
   the checks needed (types, NULL rate, range, natural-key uniqueness, `available_at` against
   `event_time`, row count per view, and the source check: `schema_version` floor and no REPLAY
   run, Work item 15), then compare plain checks, pandera, deepchecks and Great
   Expectations against that list (dependency weight, fit with the pinned-contract style). Record the
   decision in `SPEC.md` §13 item 10 before any dependency is added. Rows skipped by design are not
   failures under either policy, but the report counts them per view and reason (T-031's NULL
   `available_at`, T-155's no-component rows, T-151's run-keyed rows), so no row is dropped
   silently.
2. Add the dependency (through a constitution amendment first, if it is a library) and write the
   expectations as JSON files beside `view_contract.py` (done, T-162), for the views Work item 4
   reads (T-161, T-162). The run-identity checks are not among them: T-151 owns those, because they
   compare a row with its run table and a failure there omits `:runId` instead of failing the row,
   except for the run-keyed views T-151 lists (`v_weight_*`, `v_cycle_ranking`,
   `v_cycle_ranking_component`), whose rows are skipped and counted in the report. The expectations
   do include one source check, which stops the run: the database meets the `schema_version` floor
   and holds no REPLAY run (T-157, Work item 15).
3. Run them on the read path, source check first, so T-031's first real projection already goes
   through them (T-163).
4. Test the selected policy (the cap, a stop on exceeding it, the group cascade, a late row's key
   persisted and re-read) and every check kind with synthetic rows under Work item 13's structure
   (T-164).

**Decided (T-160, 2026-10-07): plain checks, no library.** Rows reach this repo as
`portfolio_common.db` row objects, not frames, and a frame library (pandera, Great Expectations,
deepchecks) would bring a dataframe stack (`uv.lock` has neither pandas nor numpy) for a few
thousand rows per cycle; the checks that matter most (the source check, the per-cohort mean,
by-design NULLs, skipped-row counts, the report naming view, column and row key or group) are custom
code under any of them, and deepchecks targets ML data and model drift. T-161 therefore closes with
no dependency and no constitution amendment (Technological stock #2 already names the whole stack).
The expectations are data: one JSON file per view under `src/projection/view_expectations/` (plus
`_source.json` for the source check), read by a strict loader, `src/projection/expectations.py`
(T-162). The loader checks column names against `VIEW_COLUMNS`, so the column lists are not
repeated; a column or view upstream has not shipped yet is marked `pending`, and the marker is
rejected once the pin gains it. A cap above 0 needs a `cap_reason`. The files only hold parameters:
the check kinds, the cascade and the report are code (T-163).

*Check kinds* (T-164 tests one passing and one failing case per kind; a new kind is added to this
list, to `boundary.CHECK_KINDS` (`Failure` refuses any other) and to its test):

- **source** (aggregate, runs first): the database meets the `schema_version` floor and holds no
  `cycle_run` with `cycle_type = 'REPLAY'` (T-157);
- **type**, **NULL rate**, **range**, **natural-key uniqueness**, **row count** per view;
- **format**: `computed_at` in `+00:00` or `Z` form; `forensic_flags_json` NULL or an object of the
  four documented keys (T-153);
- **ordered pair**, the D2 look-ahead guard, per lane: FUNDAMENTAL `available_at > event_time` (strict:
  the first trading day after the filing, which follows the period end); cycle lanes (TECHNICAL,
  VALORIZATION, SECTOR) `available_at = event_time`, the cycle date, once upstream's T-144 fills it
  (until then a NULL is skipped by design and counted, T-031). Read whether the columns are dates or
  timestamps from a real view before pinning;
- **group mean**: the cohort mean near 50, with a tolerance (T-162), over two groupings.
  VALORIZATION, TECHNICAL and SECTOR run over `v_score_snapshot.normalized_score` by `(run_kind,
  run_id, score_type)`: run ids repeat across the four run tables (D7), so `run_id` alone could
  merge two runs. FUNDAMENTAL runs over `v_cycle_ranking_component.component_value` by
  `(cycle_run_id, score_type)`, since its stored `normalized_score` mixes cohorts (D17); that view
  is `pending` until upstream's T-144, so this guard is inactive until then.

*Policy.* A source or aggregate failure stops the run. A row-level failure quarantines the row **and
its group**, reported as one unit, so no partial individual is built (SHACL would not catch one:
`hasWeightComponent` needs only one component):

- a `v_cycle_ranking` row goes with all its `v_cycle_ranking_component` rows (the effective weights
  sum to 1 per run and asset, T-155), and a failing component takes its ranking row;
- a `v_weight_scheme` row goes with all its `v_weight_component` rows and every ranking row of that
  run, which points to the scheme (T-121); a failing component takes the scheme with it.

This matches T-151's treatment of these run-keyed views. A cascaded row counts against its own view's
cap (a ranking row taken by its scheme counts toward `v_cycle_ranking`'s), and the report names the row
that caused the cascade.

**What a quarantine costs depends on how the target graph is dated** (`docs/07`'s named-graph table;
the ingest gate refuses to append to an existing append-only graph, `kg_store.gate`, and to
re-declare an individual already in the store):

- **Graphs dated by ingestion** (`urn:graph:ingest:{agent}:{date}` for SEMANTIC, VALORIZATION,
  TECHNICAL, SECTOR: transaction time, "what did we believe as of ingestion date X"): a quarantined
  row is **late, not lost**, provided a later run reads it again. The individual never reached the
  store, so once upstream fixes it, a later run writes it into that run's new graph, which is the
  honest record of when it arrived. **Re-read mechanism:** T-163's report persists the keys of its late
  rows, and the next run (T-031) re-reads those keys along with its own rows, dropping a key from the
  list once its row is settled (written, already in the store, or left out by design, each reported).
  T-031 implements it for `v_score_snapshot` (PR #72); for a view without a projection yet, a late
  row is reported as lost.
- **Graphs dated by the data**, and **every graph not listed above**:
  `urn:graph:ingest:ORCHESTRATOR:{date}` (keyed by the scheme's `cycleDate`, T-121),
  `urn:graph:ingest:FUNDAMENTAL:{year}-Q{n}`,
  `urn:graph:universe:{year}-Q{n}`, `urn:graph:ingest:EDGAR:{date-or-quarter}` (`v_sec_filing`),
  `urn:graph:derived:quant:{date}` (`v_quant_*`, the book's `as_of`) and
  `urn:graph:derived:entity-resolution:{date}` (`v_shared_executive_edge`). A quarantined row is
  **lost for that date**, since its graph cannot be appended to once written and a later graph would
  misdate it. The only recovery is a re-run before the graph is written. The report lists it as lost.
  A projection never asks the gate to append to such a graph: it lists the row as lost instead
  (a `graph_written` outcome, T-031), and writes a FUNDAMENTAL quarter only once it is complete:
  closed by the run day and covered by a full upstream analysis run (`v_analysis_run`) as of a
  later quarter, no later than the run day. A loss stays in the view, so a run with a late-key
  file keeps lost keys beside it and lists only new losses.
  A graph added to `docs/07` later is data-dated unless this list says otherwise.

The run stops when a view's quarantined share exceeds its cap. Caps are set per view in T-162's
expectations and **default to 0** (any row-level failure stops the run): the boundary should not decide
what to drop unless T-162 records why a view may lose (or delay) rows, and for a data-dated graph a
non-zero cap is a permanent gap.

**Acceptance**: every view the projection reads has expectations; a violating row never reaches the
triple builder under the chosen policy; the failure message names the view and column, plus the row key
for a row-level check, or the group for an aggregate one; `uv run pytest` covers a passing and a failing
row set per check kind and the selected policy's behaviour; `SPEC.md` §13 item 10 records what is checked
at the boundary and what is not.

**Blocked on**: nothing for T-162 (T-160 done, T-161 closed: no library, no amendment). T-163's function is done (`src/projection/boundary.py`, PR #68), the task stays open: T-031's first slice (PR #72) calls it on the real read for `v_score_snapshot`; counting T-151's and T-155's skips lands with the rest of T-031; T-164 is done (PR #69: every kind in `boundary.CHECK_KINDS` has a passing and a failing case, and a late key's round trip across two runs is tested over synthetic rows); T-031's first slice tests that round trip on the real read (`tests/test_score_snapshots.py`).

## Work item 17 — One GraphDB repository per automation (from T-195's cancellation)

**Why**: the maintainer cancelled T-195 on 2026-10-13: a re-run with other settings, or after a fix,
is a new *automation* (one realization of the algorithm) built in its own GraphDB repository, so no
ingest graph is ever replaced and the gate's refusal of a graph that exists (check 2) stays right.
Nothing in this repo is parameterised by repository yet: `portfolio` is the one repository, and
`PRODUCTION_REPOSITORY` (`src/kg_store/graphdb.py`, used by `project_scores --replay` in
`src/projection/project_scores.py` to refuse the repository) treats it as production. The maintainer
decided on 2026-10-13 that `portfolio` is development-only and production never sees it, so those
guards lose their meaning; `docs/graphdb-setup.md` still describes `portfolio` as the store until T-196.

1. Decide the automation identity (a generated id per lower-case human name, both stored; duplicate
   names refused) and what the repository name derives from it.
2. Parameterise the store tools (`cli/load_schema.py`, `cli/ingest.py`, `cli/verify_store.py`,
   `src/kg_store/`) by repository, and replace the `PRODUCTION_REPOSITORY` guards with what is still
   worth protecting once `portfolio` is development-only.
3. Create a repository per automation (schema loaded, gate on), and clone one.
4. Delete one (a hard delete). The gate does not cover a drop: export first, refuse `portfolio`, and
   run it only after the maintainer's go-ahead.
5. Any HTTP service this repo exposes for it needs a constitution amendment first (the constitution
   says this repo is not a service).

**Acceptance** (SPEC FR-007): a second run for the same agent and day is still refused under the same
automation (the reason T-195 was cancelled) and, under another automation, writes to its own repository
with the gate unchanged; the first automation's graphs are untouched; the replacement for the
`PRODUCTION_REPOSITORY` guards refuses `portfolio` for delete and replay; delete exports first and runs
only after the maintainer's go-ahead; clone copies as the chosen mode says (settings only, or with
data); `verify_store` passes for each new repository; `uv run pytest` passes.

**Blocked on**: step 1 (T-196) is the maintainer's decision and records the open questions: which
settings vary between automations, whether source data is copied or shared, one upstream file per
automation or an `automation_id` column, and what clone copies. Steps 2–4 wait on it; step 5 is a decision that may end in "no".

## Work item 18 — Upstream: `portfolio-common` re-pin `v1.2.1` → `v1.2.2` fixes a real read-blocking bug here (T-204)

**Why**: unlike `portfolio-financial-analysis` (whose own `urls.db` read path is a bare
`Database.connect(read_only=True)`, never exposed to the bug), this repo's `src/etl/news_to_rdf.py`
reads `urls.db` through `portfolio_common.news_export.connect_readonly`, which ATTACHes it read-only
via `TwoTierDatabase.attach_readonly` → `Database.attach(read_only=True)` — the exact function whose
stale-WAL preflight was too broad before `portfolio-common` v1.2.2 (it rejected *any* non-empty `-wal`
sidecar, not only a genuinely orphaned one). Run this repo's ETL step while `portfolio-data-mining`'s
collector holds `urls.db` open in WAL mode (its ordinary running state) and the old preflight raised
for as long as the collector kept running — the same production bug that blocked `portfolio-nlp`'s
`attach_source()`, tracked in `portfolio-common`'s CHANGELOG `v1.2.2` entry
([PR #16](https://github.com/gamug/portfolio-common/pull/16)).

**Demonstrated empirically, not just reasoned about**: `tests/test_news_to_rdf.py::test_stream_news_reads_through_a_live_writers_wal`
holds a real writer open on a WAL-mode SOURCE db and calls `stream_news` through it — confirmed to
fail with the preflight's `RuntimeError` against the old `v1.2.1` pin, and to pass against `v1.2.2`,
seeing the writer's just-committed row rather than a stale snapshot.

**Acceptance criteria** (all verified met, T-204):

- ✅ `pyproject.toml`'s `portfolio-common` source pins `tag = "v1.2.2"`; `uv.lock` diff scoped to
  exactly the `portfolio-common` version/source lines.
- ✅ `tests/test_news_to_rdf.py` (new) proves the fix: fails pre-bump, passes post-bump.
- ✅ `uv run pytest -m "not integration"`: 735 ran (734 baseline-collected + the new test), **722
  passed, 13 failed**. The 13 failures, all in `test_score_snapshots.py`
  (`PermissionError: WinError 32`, a Windows tmp-file-cleanup race), are confirmed identical against
  the old `v1.2.1` pin via `git stash`/`git stash pop` — pre-existing, unrelated to this bump; the
  new test is the only change to the pass count (baseline passing 721 + the new test's 1 = 722).
- ✅ `uv run ruff check .`: 26 pre-existing errors, confirmed identical via `git stash`; `tests/test_news_to_rdf.py`
  and `pyproject.toml` are themselves clean.
- ✅ `uv run mypy --config-file=.code_quality/mypy.ini`: no issues in 56 source files.
- ✅ `SPEC.md`'s storage bullet and upstream-library bullet, and `constitution.md`'s storage clause,
  updated from "currently `v1.2.1`"/`tag v1.2.1` to `v1.2.2` — "Claude Code / coding-agent
  conduct" item 6 reconciliation for this item.
- ✅ Both architecture artifacts updated: the Portfolio Knowledge Graph artifact's "Other useful
  details" bullet and footer changelog now say `v1.2.2` and explain this is a real fix, not a
  consistency bump; the Portfolio Thesis system-wide overview's hero pill, build-state table
  (`portfolio-common` row and this repo's row) and footer changelog updated the same way — this was
  every consumer repo's last unchecked pin, so the Thesis table no longer says any repo's pin is
  unverified. (Round 2 of this PR's review: the Knowledge Graph artifact's hero pill and two body
  mentions of "734 hermetic tests" were stale after this PR's own new test — fixed to 735 in the
  hero pill, the "What exists today" bullet and the "Validation has two layers" bullet.)

## Work item 19 — Load the asset master into the store through the ingest gate (T-220–T-229)

**Why**: the store holds only `reference.ttl`'s five worked-example `:Asset`s. A real `--write` of
a backtest run whose `:holdingAsset`/`:guardAsset` links name other S&P 500 tickers is refused by
the gate because the store does not hold those individuals; the dry run looks fine because the
projector validates beside a context built from `universe.db`. The asset master already exists as
an ETL output (`etl.asset_master`, FR-004), but `data.ttl` is one flat file with no named graphs,
so it does not put the individuals into the store either.

**Design (T-220)**: `cli/load_universe.py` (logic in `src/kg_store/universe.py`) reuses
`etl.asset_master.read_stints`/`build_assets` rather than rewriting them. It reads
`SQL_UNIVERSE_DB`, keeps the stints with no `valid_to` or `valid_to >= --since` (default
`2019-01-02`, so a reused ticker such as `CEG`, `DELL` or `Q` is one `:Asset` described by the era
the backtests can see) and writes the `:SP500Index` `:Universe` (with the ETL's FIBO
`rdfs:seeAlso`), one `:Asset` per symbol and one `:UniverseMembership` per kept stint into
`urn:graph:universe:{year}-Q{n}` for `--as-of` (default today). That quarter graph is the placement
`docs/07` already assigns; `urn:graph:reference` is dropped and rewritten by `cli/load_schema.py`,
so ABox individuals written there would vanish on the next reload. The default is a dry run that
reads, builds and SHACL-validates through `gate.validate` without contacting the store; `--write`
appends through `gate.ingest`, and `KG_REPOSITORY=portfolio` also needs `--to-production`, as
`cli/project_backtest.py` has it. `reference.ttl`'s five `:Asset`s get memberships but are never
re-declared (gate check 6). The gate is not changed; `UniverseMembershipShape` gains the
`sh:class :Asset` triple on `:membershipAsset` that lets `gate.context_predicates` follow a stored
Asset a membership batch points at (T-221). T-227 added the `sh:class :Universe` half on
`:membershipUniverse` once the backtest projector's `validation_context` typed `:SP500Index a
:Universe`; the five dry-run tests that failed on the first attempt now pass.

**Acceptance criteria**:

- ✅ A dry run over the full `universe_history_gics.db` reports what `--since` kept and dropped
  (657 of 891 stints over 653 symbols kept; 234 stints of 229 symbols dropped), the `:Asset` and
  `:UniverseMembership` counts, 6563 triples (6557 before Work item 22 mapped six historical
  sub-industries; 6476 was the earlier count over `universe_history.db`) and a passing
  `gate.validate`; no asset is left without a CIK and with an open membership.
- ✅ Every ticker in `v_book_weight_daily` (CASH excluded), `v_guard_alert` and `v_guard_action` of
  `rule_P1/P2/P3.db` is in the loaded symbol set (P1 100, P2 123, P3 115; 0 missing).
- ✅ Hermetic tests: a ticker's two eras, a CIK-less closed asset, `BRK.B`, the quarter name,
  deterministic output, gate acceptance, the production guard and a fake-store write; the
  `sh:class` change has a gate test for an Asset the store holds (accepted) and one it does not
  (refused).
- ✅ FR-001 parse + `pyshacl` on the 4237-quad bundle at that revision (4204 after T-227 and T-233/T-234); every pinned count updated in the same
  change.
- ⬜ First real `--write` to a scratch repository (T-226), never production by default; it needs the
  maintainer's go-ahead, a schema reload there (the store is 4513 until the merged 4204-quad
  bundle is loaded) and the full universe in `SQL_UNIVERSE_DB`.

**Open**: T-225 (the worked example's `2026-Q3` memberships overlap the loader's catalog for the
five reference assets; clean it when the worked example stops being loaded into the real store) and
T-226 (the live write). Everything else landed with T-220–T-227.
## Work item 20 — Label backtest runs and open the window vocabulary (T-230–T-237)

**Why**: the m018 views carry no identifier for the run itself — no input hash, no parameters — so
every backtest run of one window projected to the same graph name and the same individual IRIs.
`urn:graph:derived:backtest:P1:1` and `:Book_P1_MARKOWITZ_BASE` were identical for any two runs of
P1 (each run database restarts ids at 1), and the gate's "a new individual only" check refused the
second family. Several result families (`rule`, `champ_v1`, …) must be able to live in one
repository. The window and segment vocabularies were also closed `sh:in` lists (`P1|P2|P3`,
`P1|P2|P2a|P2b|P3`), so a new window needed a schema edit.

**Approach**:

1. `--db LABEL=PATH` (repeatable) replaces `--db PATH`; a missing or malformed label exits 2; the
   existing duplicate-graph guard stays, now over labelled names.
2. The graph is `urn:graph:derived:backtest:{label}:{window}:{run_id}`; the gate's backtest pattern
   accepts the label and `P[0-9]+` and retires the unlabelled names.
3. Every IRI stem carries the label after its prefix (`Book_{label}_{window}_{arm}`, …), so labels,
   windows and arms never collide; a test projects two labels on the same window.
4. `:runLabel` (xsd:string, `[a-z][a-z0-9_]{1,31}`) is required on `StrategyBook` and
   `BacktestTest`, the two m018 classes with no book link; `tbox.ttl`, `shapes.ttl` and
   `kg_target_schema.ttl` carry it.
5. `windowId`/`segment` become `^P[0-9]+$`/`^P[0-9]+[a-z]?$` in `shapes.ttl`, the projector and
   the gate pattern; the arm list stays closed; `docs/06` §1.10 states the trade-off.
6. Docs and every asserted count follow in the same change.

**Acceptance criteria**:

- `rule_P1.db` with label `rule`, empty universe: 18,062 rows and 18,062 individuals, the same as
  T-207, and 193,938 triples (`193,929` plus one `:runLabel` on each of the 3 books and 6 tests),
  graph `urn:graph:derived:backtest:rule:P1:1`.
- Two labels on the same window produce two graphs and disjoint IRIs; the gate refuses
  `urn:graph:derived:backtest:P1:1` and accepts `...:champ_v1:P2:1`.
- `:runLabel` is required by SHACL on `StrategyBook`/`BacktestTest`; a missing, upper-case or
  too-short label is refused.
- `P4` and `P2c` conform; `Q1` and `P2A` do not; the arm list is still a closed `sh:in`.
- FR-001 parse + `pyshacl` pass at **4204 quads**; `kg_target_schema.ttl` carries the same facts.
- `uv run pytest`, `mypy` and `pre-commit` pass.

**Blocked on**: nothing. The live-store reload and the drop of stale unlabelled backtest graphs
from scratch repositories are the maintainer's (T-237).

## Work item 21 — Reports-agent query catalog and its executable test (T-240–T-243)

**Status: closed 2026-11-03.**

**Why**: `portfolio-reports` receives questions about what a term means, how a backtest arm
performed and why an asset was cut or excluded. The graph answers them, but the queries were
spread between `docs/06`'s Appendix A and the store notes, and a query could silently drift from
the schema or from the backtest graph naming. The FIBO slice adds a second way to answer "what is
X", so the boundary between a definition and a reason has to be written down: **FIBO explains what
terms mean, never why an asset was in or out of a portfolio** (brief §5).

**What was built**:

1. `docs/reports-agent-query-catalog.md`: the scope rule (always `GRAPH`, never the default
   union), A1 for ten of our terms at once with the FIBO link in the same `OPTIONAL`, A2 by
   Spanish label (volatility, the equity index, the two closing prices, the SEC), the terms FIBO
   does not define (Sharpe), the active rules by category, the backtest battery (performance,
   GUARD alerts, latest NAV known on D, layer-1 cuts, one end-to-end cut explanation, book
   knowledge dates, the full `BookWeightDaily`/`BookDailyPerformance` property list, the weight
   scale, `n-equity-per-arm-on-last-day`, and `runs-available`) and the limits table with the
   brief's 11 evaluation questions verbatim and the backtest questions, mapped to today / after
   the asset catalog / after T-209 / after T-208 / never by design / not projected yet.
2. `tests/test_query_catalog.py`: parses every tagged query, builds one in-memory
   `rdflib.Dataset` from `tbox.ttl`, `fibo.ttl`, `rules.ttl` and `reference.ttl` plus two run
   labels (`rule`, `champ_v1`) across two windows (`P1`, `P2`) projected with
   `projection.backtest.project`, runs every query and checks its exact row count or named rule,
   and pins the A1 no-FIBO rows, the two Sharpe-less terms, the 10+5 active-rule split, the exact
   eleven questions and six status labels, and the absence of per-asset daily returns and drifted
   weights.

**Follow-up (2026-11-03, PR #116 review).** The first commit reconstructed §6 from the task
summary because the brief was not in the container; the review supplied the real questions. This
follow-up replaces the table verbatim, adds the `Not projected yet` status (executives of a
company, the live portfolio), the §5 control rule (questions 9 to 11 must not change with or
without the FIBO slice), the `n-equity-per-arm-on-last-day` query, and the extra A2 labels; it
extends `A1` to `:Universe`, `:UniverseMembership`, `:PriceObservation` and `:Executive`, and
pins the exact question text in the test.

**Follow-up (2026-11-04, merge of PR #117 and PR #118).** The branch merged `origin/master`, which
renumbered this work item from 19 to 21 (master already has Work item 19, the asset loader, and
Work item 20, the run labels). The catalog now uses
`urn:graph:derived:backtest:{label}:{window}:{run_id}`; every per-run backtest query takes the
optional `FILTER (?label = "rule")` parameter, read from `:runLabel` on the run's
`:StrategyBook`, and `runs-available` lists the labels/windows/books. The test projects two labels
in the same window and proves they do not mix. The §6 legend notes that the asset loader exists
as `cli/load_universe.py`, but the statuses do not change until the maintainer runs it and the live
check passes.

**Acceptance**: every `sparql` block in the catalog is tagged and tested; the test is hermetic
(`uv run pytest -q`); no `src/`, `schema/` or gate change from this branch; `uv run mypy
--config-file=.code_quality/mypy.ini` and `uv run pre-commit run --all-files` pass. Verified
2026-11-03, re-verified 2026-11-04 after the merge.

**Blocked on**: nothing.

## Work item 22 — Map the six retired GICS sub-industry names (T-250–T-259)

**Status: closed 2026-11-04.**

**Why**: a read-only dry run of `cli/load_universe.py` over
`/workspaces/thesis/data/universe_history_gics.db` warned that six GICS Sub-Industry strings had no
rollup entry, so those `:Asset`s were written without `:classifiedAs`. They are historical strings
in that file (each occurs only on a closed stint, so no current constituent carries it), but the
real GICS hierarchy of their period still assigns each to an existing reference industry group.
`lookup()` must keep returning `None` for every other unmapped name.

**Approach**:

1. Audit the six strings in the GICS database read-only (`file:...?mode=ro`) under the loader's
   `--since 2019-01-02` kept set; record the carrying symbol(s) and dates.
2. Add the six mappings to `SUB_INDUSTRY_TO_INDUSTRY` in `src/etl/common/gics_rollup.py`, beside a
   comment marking them historical and naming the one (`Thrifts & Mortgage Finance`) the March 2023
   reclassification discontinued. Use only existing `:Ind_*` individuals; no schema/loader edit.
3. Add one mapping test per name (target group plus the period sector cross-check) and a CLI dry-run
   test over a tiny six-row fixture that no longer reports them as unmapped.
4. Verify read-only against the full database: no rollup warning, the six assets now carry
   `:classifiedAs`, and the batch grows from 6557 to 6563 triples.
5. Update the ETL README, `docs/graphdb-setup.md`, SPEC FR-008 and every asserted count.

**Mappings**: Alternative Carriers -> `Ind_TelecomServices`; Drug Retail ->
`Ind_ConsumerStaplesRetail` (Food & Staples Retailing before its 2023 rename); Home Furnishings,
Household Appliances and Housewares & Specialties -> `Ind_ConsumerDurables`; Thrifts & Mortgage
Finance -> `Ind_Banks`.

**Acceptance criteria**:

- Each of the six names resolves to an existing `reference.ttl` group and `sector_matches` agrees
  with the row's own GICS Sector; any other unmapped name still returns `None`.
- The full read-only dry run reports no "no rollup entry" warning, 648 assets written, 657
  memberships, **6563 triples** (6557 before the change) and SHACL conforms; LUMN, WBA, MHK, WHR,
  NWL and PBCT each gain their expected `:classifiedAs`.
- `uv run pytest`, `mypy` and the pinned pre-commit hooks pass; docs and counts are consistent.

## Work item 23 — Inclusive membership end dates and one asset per CIK (T-260–T-279)

**Status: closed 2026-11-04** (two work commits on
`feat/universe-inclusive-validto-cik-fold`, plus the merge of `origin/master` after PR #119). The
reserved decade T-260–T-279 uses T-260–T-271.

**Why**: two upstream facts, confirmed read-only, were modelled wrong. First,
`portfolio-data-mining`'s `universe_membership.valid_to` is **inclusive**: it is the last day of
membership (NULL = still a member), and upstream fixed its own `valid_to > D` predicate on
2026-10-14. One-day stints (`valid_from = valid_to`, `PHIN` on 2023-07-05) are real. This repo's
loader, `UniverseMembershipShape` and docs still described and enforced an exclusive end, so they
dropped real stints and answered "left the index" one day early. Second, the backtest's
`holding_key` is `assets.ticker`, i.e. one asset per CIK carrying the **current** symbol (META for
the whole of P1, even before 2022-06-09). This catalog wrote one `:Asset` per symbol, so a renamed
company was split (`:FB` until 2022-06-08, `:META` from 2022-06-09) and the earlier stint could
not link to the backtest's single holding. Confirmed same-CIK renames: `WLTW`→`WTW`, `FB`→`META`,
`RE`→`EG`, `FLT`→`CPAY`, `SATS`→`ECHO`, `CDAY`→`DAY`. Concurrent share classes under one CIK also
exist (`GOOG`/`GOOGL`, `UA`/`UAA`, `DISCA`/`DISCK`/`WBD`).

**What Commit 1 built** (T-260–T-263):

1. `read_stints` keeps a one-day stint and skips only `valid_to < valid_from`;
   `UniverseMembershipShape` uses `sh:lessThanOrEquals`; the gate's `CLOSABLE` entry treats a
   membership as inclusive too. `RuleDefinition`, `PortfolioPosition` and
   `AttractivenessWeightScheme` stay exclusive; `TickerHistory` was already inclusive.
2. The point-in-time predicate is `validFrom <= D AND (no validTo OR validTo >= D)` everywhere
   the membership is described: `tbox.ttl`, `schema/README.md`, `docs/06`, `docs/07`,
   `src/etl/README.md`, `docs/graphdb-setup.md`, SPEC FR-004/FR-008/D1, `PLAN`/`TASKS`, and the
   reports-agent catalog, which gains a `universe-members-on-date` query that returns the member
   on its last day.
3. Tests: the one-day `PHIN` stint is kept and conforms; `validTo < validFrom` still fails; a
   membership on its last day is in in the catalog query; a same-day membership closure is
   accepted by the gate while a closure before its opening day is not.

**What Commit 2 built** (T-264–T-271): one `:Asset` per company (CIK) for a pure rename
succession, keeping the `:TICKER` IRI scheme. A CIK whose symbols have non-overlapping inclusive
stints gets one `:Asset` named by the symbol of its latest stint, all stints as memberships with
their dates unchanged, and sector/industry from the latest stint. Concurrent share classes stay
one `:Asset` per symbol; a mixed pattern (overlap plus a later non-overlapping symbol, e.g.
`DISCA`/`DISCK`/`WBD`) is not guessed and stays as today. A CIK-less stint stays grouped by
symbol. Ticker reuse (`CEG`, `DELL`, `Q`: different companies, same symbol) and `--since` keep
their behaviour; two kept CIKs that would claim the same latest ticker stop the run. Former
tickers are NOT stored in this change. `etl.asset_master` owns one shared resolver used by both
`cli/load_universe.py` and `projection.backtest.universe_assets`, so the loader and the projector
cannot disagree on the asset set.

**Measured on the real database (read-only).** Commit 1, over
`/workspaces/thesis/data/universe_history_gics.db` at `--since` 2019-01-02: 658 of 894 stints kept
over 654 symbols (236 dropped over 230; 215 not loaded, 15 with a later stint kept), 649 `:Asset`s
written plus five in `reference.ttl`, 658 memberships (503 open, 155 closed), 6573 triples, 64
written assets without `:classifiedAs` (their latest stint has no GICS sub-industry; Work item 22's
six historical values are already mapped), SHACL conforms. Before Commit 1 the same file gave 657
stints over 653 symbols, 648 `:Asset`s plus five, 657 memberships (503 open, 154 closed), 6563
triples, 63 without `:classifiedAs`.

Commit 2, same file and `--since`, AFTER: 658 stints over 654 symbols (unchanged), 643 `:Asset`s
written plus five in `reference.ttl` — 648 assets from 654 symbols, because six pure successions
folded — 658 memberships (503 open, 155 closed), 6548 triples, 59 written assets without
`:classifiedAs`, SHACL conforms. The 11 CIKs with more than one symbol are six successions
(`EG/RE`, `WTW/WLTW`, `CPAY/FLT`, `META/FB`, `ECHO/SATS`, `DAY/CDAY`), four concurrent classes
(`UA/UAA`, `NWS/NWSA`, `GOOG/GOOGL`, `FOX/FOXA`) and one mixed (`DISCA`/`DISCK`/`WBD`), which
stays per symbol. The three real backtest dry runs link every ticker: P1 100, P2 123, P3 115
distinct, 0 unlinked.

**Acceptance**: the point-in-time predicate is inclusive in every document and query; one-day
stints are loaded and conform; a pure rename chain is one `:Asset` with all its memberships and no
former ticker; concurrent and mixed CIKs are unchanged; CIK-less stints and ticker reuse keep
their behaviour; the loader and `projection.backtest.universe_assets` return the same asset set;
every backtest ticker still links (P1 100, P2 123, P3 115 distinct, 0 missing); `uv run pytest`,
`mypy` and the pinned `pre-commit` hooks pass. No GraphDB write or reload in this work item.

**Blocked on**: nothing.

## Work item 24 — Verify a loaded backtest against its source (T-280–T-299)

**Status: closed 2026-11-04.**

**Why**: when the final backtest arrives (same strategy and schema, possibly different data),
loading it through `cli/project_backtest.py` and checking it by eye is not enough. The operator
must be able to prove that the named graph in the selected repository holds exactly what the
deterministic projector builds from that source database, and to do it without writing to the
store. The verifier is the read-only half of the load; the runbook is the copy-pasteable
procedure around both halves.

**What was built**:

1. `cli/verify_backtest.py` (logic in `src/projection/verify_backtest.py`) takes an explicit
   `--graph`, `--db` and `--label`, reads the repository from the same environment as the other
   store CLIs, re-projects the source in memory through `projection.backtest.project_source`
   (the projector, not a second implementation), and prints one `PASS`/`FAIL` line per check
   plus the repository and graph it checked. It issues only SPARQL `SELECT` queries, so it cannot
   write to any repository; exit 0 only when every check passes.
2. Checks: the graph exists and its name plus its stored `:runLabel`/`:windowId`/
   `:backtestRunId` agree with the label, window and run id; total triples equal the
   re-projection; the eight classes (`StrategyBook`, `BookRebalance`, `GuardAlert`, `GuardAction`,
   `BookWeightDaily`, `BookDailyPerformance`, `PortfolioPeriodSummary`, `BacktestTest`) have one
   individual per source row; distinct `:holdingAsset`/`:guardAsset` tickers equal the source's
   linked set, and the unlinked row count is not above the projector's; GuardAlert groups by
   rule/layer/state, GuardAction by status, last NAV per arm and CASH rows equal the source; and
   every individual carries `:runLabel` directly or through its book (where the model has that
   link) and `:knowledgeDate` where the model has it.
3. `docs/backtest-load-runbook.md`: prerequisites, contract check, label choice, dry run, write
   and production guard, verification, recording the numbers, single-graph rollback, a new
   label/run, the asset catalog's real one-time limit, and the common failure messages.
4. Reference dry runs (2026-11-04, read-only): `rule_P1.db` 15,615 `v_book_weight_daily` rows and
   **209,886 triples**; `rule_P2.db` 15,641 and **196,840**; `rule_P3.db` 18,025 and **222,449**;
   peak RSS 0.66–0.73 GB and 44–48 s per database. These are in `docs/graphdb-setup.md` and the
   runbook.
5. Hermetic tests use an in-memory `rdflib.Dataset` as the store and cover a passing graph, a
   missing class, an altered individual count, a missing link, a wrong label and a wrong graph
   name; the CLI is also run as a subprocess for its argument contract.

**Acceptance criteria** (all verified):

- ✅ `uv run python cli/verify_backtest.py --graph … --db … --label …` prints the repository and
  graph, one PASS/FAIL line per check, and exits 0 only when all pass; a live run is read-only by
  construction (only `SELECT` queries).
- ✅ The verifier and runbook use the real projector and the real graph/IRI naming, and the
  dry-run numbers above are measured, not copied.
- ✅ `tests/test_verify_backtest.py` passes all six required cases plus the check-name and
  repository-printing cases; `tests/test_cli_verify_backtest.py` covers the argument contract.
- ✅ The runbook states the asset catalog's actual limit (one catalog per repository; a later
  quarter or a new ticker is refused by gate check 6) and the safe procedure.
- ✅ `uv run pytest`, `mypy` and the pinned pre-commit hooks pass; docs and counts are consistent;
  no schema count changed.
- **Residual risk:** no live GraphDB read or write was made in this change. The verifier passed
  21/21 checks over an in-memory Dataset holding `rule_P1.db`'s 209,886-triple projection, but its
  store-side SPARQL has not yet run against GraphDB. The first live run is the operator's step in
  `docs/backtest-load-runbook.md`.
## Work item 25 — Reports-agent sector and industry queries (T-300–T-308)

**Status: closed 2026-11-04.**

**Why**: a sector question written with the asset classification and the GICS taxonomy in one
`GRAPH` block silently returns almost nothing. In the real store `:Asset :classifiedAs :Ind_*`
lives in the asset-catalog graph `urn:graph:universe:{year}-Q{n}`, while `:Industry`, `:Sector`,
`:memberOfSector` and their `skos:prefLabel`s live in `urn:graph:reference`; only the five
worked-example assets in `reference.ttl` satisfy a single-graph pattern. Those five also appear in
the universe graph for their memberships (T-225), so a naive union join can count them twice.

**What was built**:

1. `docs/reports-agent-query-catalog.md` gains §6, the cross-graph rule and six executable queries:
   layer-1 GUARD cuts by window and sector (with an `unclassified` bucket so the P1 total equals the
   layer-1 ENTER alert count), sector composition of a book on a rebalance date (the sector weights
   plus the `unclassified` bucket plus CASH sum to 1), distinct held tickers by window and industry
   (Banks and Insurance, count and `GROUP_CONCAT` list), sector coverage of held assets (held,
   asset-linked, sector-classified), unclassified assets by year of `:validTo`, and `sector-of-asset`
   for Q5 (ticker, company, industry, sector and the optional Spanish sector note). The
   asset-to-sector part is a `SELECT DISTINCT` sub-select outside `GRAPH ?g`; the backtest part stays
   inside the `urn:graph:derived:backtest:` filter with the run label.
2. `tests/test_query_catalog.py` now builds the synthetic store in the real layout: `:Asset` and
   `:classifiedAs` in `urn:graph:universe:2026-Q4`, the taxonomy in `urn:graph:reference`, and
   `AAPL` in both graphs (T-225). The dataset enables GraphDB's default union for the documented
   sub-select. A negative test proves the single-graph form returns fewer rows (0 in the universe
   graph, 5 in the reference graph) than the correct cross-graph form (8), and that a naive union
   counts the overlapping `AAPL` twice.
3. The limits table marks the sector questions Q5 and Q11 **Today**; §6.7 records the known limits of
   the asset catalog (the 2019–2021 leavers' 56 closed stints have no source classification, the
   spin-offs MBC/FTRE/PHIN have none either, and GICS is rolled up by
   `src/etl/common/gics_rollup.py`).

**Acceptance criteria**:

- Every new query is tagged and executes against the synthetic real-layout store; the sector tests
  pin the cut total, the composition sum, the Banks/Insurance ticker lists, the coverage split and
  the unclassified years.
- Read-only verification against `portfolio_test` on 2026-11-04: layer-1 cuts 157 (P1), 56 (P2) and
  29 (P3), the P1 total equal to its 157 ENTER alerts; the P1 `MARKOWITZ_BASE` composition (decision
  2021-12-31, execution 2022-01-03) is 9 sector rows summing to `0.999999548…` with CASH
  `0.000000451…`; Banks/Insurance returns 5 rows; coverage is 100/100/100, 123/123/123 and
  115/115/115; the 2019–2021 unclassified closed stints total 56.
- `uv run pytest`, `mypy` and the pinned pre-commit hooks pass; docs and counts are consistent.

**Follow-up (2026-11-04, PR #120 review).** The composition query's optional sector sub-select
was evaluated before the backtest block, so a held ticker with no `:classifiedAs` or no
`:holdingAsset` disappeared instead of joining the `unclassified` bucket. T-305 moves the holding
and CASH patterns into `GRAPH ?g` with `OPTIONAL { ?row :holdingAsset ?asset }`, then uses the
sentinel/`COALESCE` pattern; a dedicated fixture now holds AAA (Financials) 0.60, QQQ (catalog asset
without a sector) 0.30, ZZZ (no `:holdingAsset`) 0.05 and CASH 0.05, and asserts Financials 0.60,
`unclassified` 0.35 and 0.60 + 0.35 + 0.05 = 1. T-306 adds `sector-of-asset` for Q5 (ticker
parameter; company, industry, sector and the optional Spanish sector note), proves one row for
`AAPL` even though it is in both graphs, and documents that an unclassified ticker returns no row.
T-307 re-runs the checks and records the counts.

**Coordination**: Work item 23 (inclusive `validTo`, one `:Asset` per CIK for renames) owns the
`validTo` semantics and asset-identity statements and will edit the same catalog for membership
queries. When it lands, merge `origin/master` and keep both sides; this work item deliberately does
not restate or change those decisions.

**Blocked on**: nothing.

## Work item 27 — Project ticker history and the orchestrator views (T-350–T-369)

**Status: closed 2026-11-04 (closes T-208).**

**Why**: Contract v18 added three views that still have no projector: `v_ticker_history` (m016) and
`v_orchestrator_run`/`v_orchestrator_step` (m015). The eight m018 backtest/GUARD views are already
projected by Work item 4/20. Without the ticker-history projector the graph cannot answer which
symbol a company used on a date (the `FB`→`META` rename, or `FBHS`→`FBIN` and `GPS`→`GAP` in the
catalog), and the selection projector leaves the current tickers `FBIN`/`GAP` unlinked when the
loaded catalog still names the company by its older symbol. Without the orchestrator projector the
graph cannot carry a run/step process record. This work item settles both placements and closes
T-208.

### Measurements (read-only, 2026-11-04)

The completed v18 databases available in this checkout are
`/workspaces/thesis/scratch/final/runs/rule_P1.db`, `rule_P2.db` and `rule_P3.db`. The pilot
`/workspaces/thesis/pilot_a3/financial.db` carries the same three views for a read-only row/null
measurement, but it has no `schema_version` row (it reads 0 and is below the v18 floor), so it is
not a valid projection source. The paths named in the task brief (`scratch/final/base.db`,
`scored_rule.db`, `scratch/bt/integ`) are not present here; the three completed backtest databases
give identical answers below, so the design is measured on them.

| View | P1 / P2 / P3 / pilot rows | NULL columns measured |
|---|---|---|
| `v_ticker_history` | 21 / 21 / 21 / 21 | `valid_to` 8; every other column 0 (`cik`, `symbol`, `valid_from`, `canonical_symbol`, `asset_id`, `evidence_url`, `evidence_date`, `rules`) |
| `v_orchestrator_run` | 0 / 0 / 0 / 0 | none (no rows) |
| `v_orchestrator_step` | 0 / 0 / 0 / 0 | none (no rows) |

`v_ticker_history` has 21 rows over 10 CIKs. Every CIK's `canonical_symbol` equals the symbol of
its latest `valid_from` row: **0 mismatches**. The six pure rename chains the asset loader folds are
`FB`→`META`, `WLTW`→`WTW`, `RE`→`EG`, `FLT`→`CPAY`, `CDAY`→`DAY` and `SATS`→`ECHO`; their
canonical symbols `META`, `WTW`, `EG`, `CPAY`, `DAY`, `ECHO` are exactly the loaded `:Asset` IRIs.
The other rows are `DISCK`/`DISCA`→`WBD`, `PSKY`→`SKYD`, `FBHS`→`FBIN` and `GPS`→`GAP`.

Four `v_ticker_history` rows carry a **multi-date** `evidence_date` (`DISCA`, `DISCK` and `WBD`
share `"2022-04-07 ; 2022-04-10"`; `PSKY` carries `"2025-08-07 ; 2026-10-06"`); the
`:evidenceDate` shape is one `xsd:date`, so the projector omits that property on those rows and
counts the omission. Their `evidence_url` also joins two URLs with `" ; "`; it is kept verbatim as
`xsd:anyURI` evidence text.

### The `FBIN`/`FBHS`/`GAP`/`GPS` case

| Symbol | In the loaded catalog (`universe_history_gics.db`) | CIK | `v_ticker_history` | Canonical |
|---|---|---|---|---|
| `FBIN` | **no** `:FBIN` | `0001519751` | `FBHS` 2016-06-22 … 2022-12-14; `FBIN` 2022-12-15 … open | `FBIN` |
| `FBHS` | **yes**, `:FBHS` (2016-06-22 … 2022-12-18) | `0001519751` | as above | `FBIN` |
| `GAP` | **no** `:GAP` | `0000039911` | `GPS` 1976-07-01 … 2024-08-21; `GAP` 2024-08-22 … open | `GAP` |
| `GPS` | **yes**, `:GPS` (1976-07-01 … 2022-02-02) | `0000039911` | as above | `GAP` |

The catalog's latest kept stint ends before the rename, so it names the company by the older
symbol. `v_ticker_history` says the same CIK continued under `FBIN`/`GAP`; the current ticker is
not a different company. The selection projector's reported unlinked rows (ranking 34/0/2, veto
9/2/3) are exactly this case: it looks up the current ticker, the catalog holds the older one.

### Design

1. **Classes reused, no schema change.** `TickerHistory`, `OrchestratorRun` and
   `OrchestratorStep` already exist in `schema/tbox.ttl` with shapes in `schema/shapes.ttl`. This
   work item adds no class, property, shape or rule, so the FR-001 bundle count is unchanged.

2. **Ticker-history graph: a labelled, dated snapshot.**
   `urn:graph:derived:ticker-history:{label}:{snapshot_date}` (label matches the existing run-label
   `[a-z][a-z0-9_]{1,31}`; `snapshot_date` is `--as-of`, default today in UTC). The snapshot is
   reference-like and append-only. Later refreshes write a **new** graph; the old one stays for
   audit. Because the gate also refuses a typed individual that already exists in any graph
   (check 6), every `TickerHistory` IRI is snapshot-qualified:
   `TickerHistory_{label}_{YYYYMMDD}_{cik}_{symbol}_{validFrom}`. A stable IRI would make the
   second snapshot impossible even though its graph name is new. The natural key remains
   `(cik, symbol, valid_from)`; the snapshot identity is part of the node only so a complete
   refresh can be written without rewriting the previous one. Readers pick the latest
   `urn:graph:derived:ticker-history:` snapshot (the query in the catalog does this).

3. **Orchestrator graphs: one graph per run.**
   `urn:graph:derived:orchestrator:{label}:{run_id}`, with
   `OrchestratorRun_{label}_{run_id}` and `OrchestratorStep_{label}_{run_id}_{ordinal}`. A run is
   an immutable process record; a later run has a new id and a new graph, never an append to the
   previous one. The label separates source families (the same `run_id` can exist in two
   databases). A step points at its run by `:stepOfOrchestratorRun`; the step's own `run_id`
   (an integer in the view) is written as the string `"{run_kind}:{run_id}"` (or `"{run_id}"` when
   `run_kind` is NULL), matching the ontology's documented `:runId` shape.

4. **Nullability and masking.** Every required shape property is written; every optional view
   column is omitted when NULL, never filled. `:evidenceDate` is written only when the cell is one
   ISO date; a multi-date cell is omitted and counted. `:evidenceUrl` is copied verbatim as
   `xsd:anyURI` because it is evidence text, not a parsed link. Orchestrator natural keys are the
   only required properties (`orchestratorRunId`; `stepOfOrchestratorRun` + `ordinal`); handle,
   kind, as-of, status, timestamps, settings, surface, step name, argv, exit code, reason and
   output tail are optional. Both orchestrator views are empty today: a dry run with 0 rows
   builds no graph and prints `v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to
   write` rather than a silent success.

5. **Asset link rule (also the rule Work item 26 should reuse).** Link
   `:tickerHistoryAsset` in this order:
   1. **exact symbol**: `canonical_symbol` is a loaded `:Asset` IRI → link to it;
   2. **unique same-CIK fallback**: otherwise, if exactly one loaded `:Asset` has the row's `cik`,
      link to that asset. This is the `FBIN`→`:FBHS` and `GAP`→`:GPS` case: same CIK, older symbol
      in the catalog, no invention;
   3. **otherwise unlinked**: no match or more than one asset under the same CIK (concurrent
      classes, a mixed CIK) → leave `:tickerHistoryAsset` unset and count it under the view.
   The projector never creates an `:Asset`, never links a different CIK, and never guesses among
   several same-CIK assets. On the 21 real rows this gives 17 exact links + 4 unique-CIK links
   (`FBIN`→`:FBHS` twice, `GAP`→`:GPS` twice) = 21 linked, 0 unlinked. Exact-only would leave 4
   unlinked. The projector also refuses a latest row whose `canonical_symbol` is not one of its
   CIK line's latest `valid_from` symbols, because then the history and the catalog disagree about
   the company line. Older rows may keep another canonical symbol on purpose: in the mixed CIK
   `DISCA`/`DISCK`/`WBD` the concurrent `DISCK` row says `DISCK` while the later `WBD` row says
   `WBD`; the invariant is checked on the latest row(s), not on every historical row.

6. **CLI.** `cli/project_reference.py` follows `cli/project_backtest.py`: repeatable
   `--db LABEL=PATH`, dry run by default, `--as-of YYYY-MM-DD` for the ticker snapshot, `--write`
   and the `--to-production` guard, exit 0/1/2. A dry run reads the three views, runs the boundary,
   builds each graph and SHACL-validates it; nothing contacts the store. A write appends each new
   graph through the gate and reports an existing graph instead of appending to it.

7. **Gate and documentation.** `kg_store.gate.check_target` gains the two append-only patterns
   `urn:graph:derived:ticker-history:{label}:{YYYY-MM-DD}` and
   `urn:graph:derived:orchestrator:{label}:{positive run id}`; `docs/07` gets both table rows and
   loses the "placement left to PR-C2" note; `docs/08`, `docs/06`, `docs/graphdb-setup.md` and
   `docs/backtest-load-runbook.md` describe the projector, the snapshot/IRI rule, the asset-link
   rule and the empty-orchestrator case.

### Acceptance criteria

- ✅ The ticker-history and orchestrator views have a projector and CLI with the same dry-run /
  write / production-guard / exit-code policy as the backtest projector.
- ✅ The real dry run reads 21 ticker-history rows, builds one 198-triple snapshot graph, reports
  17 exact + 4 unique-CIK links and 0 unlinked, and prints SHACL conformance, individuals,
  triples and timings (1.25–1.42 s, ~73 MB peak RSS per database); 4 multi-date evidence cells
  are omitted and counted; the orchestrator views report 0 rows and nothing to write.
- ✅ The gate accepts the two new graph names and refuses malformed labels/dates/run ids; hermetic
  tests cover the projection, the link rule, the empty case, the CLI and the query.
- ✅ The reports-agent catalog answers the rename question with a tagged, tested query and moves
  it from `After T-208` to `Today`; the `FBIN`/`GAP` rule is documented for Work item 26.
- ✅ No schema file changes; `uv run pytest`, `mypy` and the pinned pre-commit hooks pass; no
  GraphDB write is made.

**Validation (2026-11-04):** `uv run pytest -q` = **1162 passed, 57 deselected, 3049 warnings in
651.49 s**; `uv run mypy --config-file=.code_quality/mypy.ini` = success, 90 source files;
`uv run pre-commit run --all-files` = all hooks passed. `tests/test_reference_real.py` passes with
`REFERENCE_DB=rule_P1.db` and `SQL_UNIVERSE_DB=universe_history_gics.db`. No GraphDB write or
reload; the pilot `financial.db` has no `schema_version` (reads 0, below the v18 floor), and the
task's `base.db`/`scored_rule.db`/`scratch/bt/integ` paths are absent from this checkout.

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
Work item 13 (pytest suite) — independent; rules in constitution 1.5.0, T-130–T-134 and T-136 done (PR #64);
  T-135 done (its `integration` test)
Work item 14 (PR #48 follow-ups) — closed 2026-10-13 (T-195 cancelled); tasks in `CHANGELOG.md`; T-192 continues in Work item 16
Work item 15 (upstream's v_* changes) — T-150, T-170 and T-171 (PR #56) done, with T-155's schema half (PR #58), T-153's comments (PR #59)
  and T-151's rule (PR #60); T-173 (the contract endpoint check) done 2026-10-11, its version guard reading T-178's `contract_version` key; T-177 (the `rawValue` bound) done (PR #82); T-178 (the pin's loader key)
  done 2026-10-10 (PR #85); the step-3 shape corrections can start now;
  the rest as upstream's T-144/T-145 ship; feeds Work item 4 (T-031) and 12 (T-121)
Work item 16 (boundary validation of upstream rows; T-192 adds the veto stint check after T-031's vetoes lane) — T-160 done (plain checks), T-161 closed, T-162 done; T-163 open (its function is done, the wiring into the read path started with Work item 4's T-031, PR #72)
Work item 17 (one GraphDB repository per automation) — T-196–T-200 open; replaces T-195; starts with T-196 (the maintainer's decision)
Work item 19 (asset master through the ingest gate) — T-220–T-224 done; T-225 (worked-example
  overlap) and T-226 (first real --write) open
Work item 20 (backtest run labels, open window vocabulary) — T-230–T-236 done; T-237 (live reload and dropping
  stale unlabelled graphs from scratch repositories) is the maintainer's
Work item 21 (reports-agent query catalog) — closed 2026-11-03 (T-240–T-243); adapted to the labelled
  backtest graphs and the asset catalog loader on 2026-11-04; see `CHANGELOG.md`
Work item 22 (retired GICS names) — closed 2026-11-04 (T-250–T-259); see `CHANGELOG.md`
Work item 23 (inclusive membership end, one `:Asset` per CIK) — closed 2026-11-04 (T-260–T-271);
  the inclusive `validTo`, the shared loader/projector resolver and the real-data counts are in
  `CHANGELOG.md`
Work item 24 (backtest verifier and load runbook) — closed 2026-11-04 (T-280–T-283); see
Work item 25 (reports-agent sector and industry queries) — closed 2026-11-04 (T-300–T-307); see
  `CHANGELOG.md`
Work item 27 (ticker history and orchestrator projectors) — closed 2026-11-04 (T-350–T-360,
  T-208); see `CHANGELOG.md`
```

Work items 1, 2, and 9 have no dependencies and no blockers — they can land
immediately, in any order, in one PR or several. Work items 3, 4 and 6 follow
the roadmap's own dependency chain (a store before a projection, a projection
before a reasoner/SPARQL surface); 5 and 7 are no longer build items here. Work item 8 is independent of
everything but needs a human at a Protégé session, not code.

See `TASKS.md` for the discrete, checkable task breakdown.
