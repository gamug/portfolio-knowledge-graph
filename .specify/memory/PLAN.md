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
yet (Work items 3–7).

## Goal

Close every item `SPEC.md` §14 categorizes as pending development:

1. Rewrite `10-integration-roadmap.md`'s stale repo references (§13 item 3).
2. Reconcile `CLAUDE.md` with `origin/master`'s actual merged state (§13
   item 5).
3. Stand up a triple store and wire the SHACL ingest gate (§13 item 1,
   roadmap step 1).
4. Build the real step-2 projection: `financial-analysis`'s `v_*` views +
   `portfolio-nlp`'s `article_*` tables → SHACL-validated, dated named
   graphs (§13 items 1 and 2, roadmap step 2 proper — supersedes today's
   `src/etl/` shortcut).
5. Implement the SEMANTIC score's per-`(asset, day)` aggregation as part of
   that projection (§13 item 1; the artifact's "owed work" gap).
6. Bring up the OWL RL reasoner and the SPARQL query surface (§13 item 1,
   roadmap steps within 1–3).
7. Decide and build the orchestrator — the two LangGraph agent cycles here,
   or delegate the two-speed cycle to `financial-analysis`'s `cycle` package
   (§13 item 1, roadmap steps ~4–8).
8. Regenerate `schema/protege-view.ttl` (§13 item 4).
9. Resolve the `ScoreSnapshotShape`/Sentiment `rawValue` divergence (§13
   item 6).

Growing the ABox from the current MVP shortcut's output to the full
500-name universe on the real (not shortcut) projection is the natural
completion criterion for Work item 4, not a separate item — see that work
item's acceptance criteria.

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
   not-started (a naming fix, not a status change; Work items 3–7 below are
   what actually change the status).
4. Cross-check `README.md` and `CLAUDE.md` for the same stale names and
   update them in the same pass.

**Acceptance criteria**:

- `grep -rn "news-collector\|news-crawler\|edgar_tool" *.md README.md
  CLAUDE.md` (excluding `SPEC.md`'s own historical §13 references) returns
  nothing.
- `10-integration-roadmap.md`'s step table names only repos that actually
  exist in the six-repo system today.
- The schema parse+`pyshacl` check still passes (docs-only change).

## Work item 2 — Reconcile `CLAUDE.md` with `origin/master`'s actual state

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
run against. Nothing is stood up today; `schema/` is validated only as flat
files on disk (FR-001).

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
   `docs/` the way `KG_URLS_DB`/`KG_RESULTS_DB` are documented today.

**Acceptance criteria**:

- A running store loads the four static files + `instances.trig` and answers
  a basic SPARQL query (`SELECT * WHERE { ?s a :Asset } LIMIT 5` or
  equivalent) over HTTP/the store's client.
- A deliberately-malformed write (missing a required SHACL property) is
  rejected by the ingest gate before it reaches the store, not merely logged
  after the fact.
- The reasoning profile matches `07-ontology-topology.md`'s documented
  choice, not a store's un-configured default.

**Blocked on**: the maintainer's store choice (step 1) — everything after it
can proceed once that's made.

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

1. Enumerate `financial-analysis`'s `v_*` views this repo needs to read
   (`v_score_snapshot`, `v_price_observation`, `v_cycle_ranking`,
   `v_portfolio_position`, `v_quant_*`, `v_sec_filing_section`, per `SPEC.md`
   §4's diagram) and confirm their actual column shapes against that repo's
   own docs — this repo pins no contract on them today (§13 item 9's sibling
   risk on the `financial-analysis` side).
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

**Acceptance criteria**:

- A projection run against real `financial-analysis`/`portfolio-nlp` data
  produces one or more dated `ingest:{agent}:{date}` graphs in the Work
  item 3 store, each SHACL-conformant at write time (not just sampled after
  the fact).
- The full ~503-constituent universe and its available signals (not a
  5-asset or news-only slice) are represented once this lands.
- `src/etl/`'s role after this lands is explicitly documented (retired,
  folded in, or kept as a separate smoke-test path) — not left ambiguous.

**Blocked on**: Work item 3 (needs a store to write into).

## Work item 5 — Implement the SEMANTIC score's per-`(asset, day)` aggregation

**Why**: `financial-analysis` accepts a `score_snapshot[SEMANTIC]` input,
but the aggregation from `portfolio-nlp`'s `article_sentiment`/
`article_category` rows into one `ScoreSnapshot` per `(asset, day)` is owed
to "the integration repo" — this one — and doesn't exist yet as a designed
aggregation (today's `src/etl/` emits one `ScoreSnapshot` per article, not
aggregated per day).

**Approach**:

1. Define the aggregation function (e.g. article-count-weighted mean
   `rawValue` per `(asset, day)`, or a more deliberate scheme) — this is a
   modeling decision that needs sign-off the same way the G1–G3/G9 formulas
   in `etl/common/severity.py` are flagged as provisional, not a default to
   pick silently.
2. Implement it as part of Work item 4's write path (one aggregated
   `ScoreSnapshot` written per `(asset, day)` into the day's ingest graph,
   not one per article).
3. Mirror to `financial-analysis`'s `score_snapshot[SEMANTIC]` column if
   that repo keeps it, per `SPEC.md` §4/§12.

**Acceptance criteria**:

- Exactly one `SEMANTIC`/`Sentiment` `ScoreSnapshot` exists per
  `(asset, day)` with available articles, not one per article.
- The aggregation formula is documented and flagged provisional/sign-off-
  pending the same way `etl/common/severity.py`'s G1–G3/G9 are, until
  calibrated.

**Blocked on**: Work item 4 (this is part of that projection's write path,
not a standalone pipeline).

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

## Work item 7 — Decide and build the orchestrator

**Why**: `08-agent-architecture.md` designs two LangGraph state graphs
(`SelectionCycleGraph` quarterly, `MonitoringCycleGraph` daily) implementing
the two-speed cycle, but no scheduler exists, and it's an open question
whether this repo builds them or `financial-analysis`'s `cycle` package
absorbs the two-speed cycle and this repo stays query-only.

**This is a scope decision, not a default to implement silently** — flag it
for the repo owner before writing agent code either here or in
`financial-analysis`.

**Approach**:

1. *(maintainer decision)* Build the two LangGraph state graphs in this
   repo, or delegate to `financial-analysis`'s `cycle` package and keep this
   repo query-only (SPARQL surface from Work item 6, no orchestration code).
2. Whichever is chosen: implement the checkpointer-as-T-1-contagion-lag
   mechanism `08` designs (the orchestrator on day N reads only day N-1's
   checkpointed vetoes — "what did we believe as of D" is *which dated
   graphs exist*, not a temporal query).
3. Wire a scheduler for the quarterly/daily cadence — none exists today
   regardless of which repo owns the graphs.

**Acceptance criteria**:

- The decision (build here vs. delegate) is recorded in `SPEC.md` §3/§12,
  not left implicit.
- Whichever is built, a `SelectionCycleGraph` run and a `MonitoringCycleGraph`
  run each produce a dated `ingest:ORCHESTRATOR:{date}` graph consistent
  with `instances.trig`'s worked example of that lane.

**Blocked on**: Work items 3, 4, and 6 (needs a store, real data, and a
query surface to orchestrate over) — and the maintainer's build-vs-delegate
decision.

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

**Why**: `ScoreSnapshotShape` requires `normalizedScore` for every
non-`SectorRelativeMomentum` snapshot, but the ETL's Sentiment snapshots
carry only `rawValue` — the scale the veto-rule thresholds are defined on
(`SPEC.md` §5/§7). This produces one SHACL violation per Sentiment snapshot
in the sample/smoke check today.

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

## Sequencing

```
Work item 1 (roadmap doc)  ─┐
Work item 2 (CLAUDE.md)     ├─ independent, cheap, no blockers — land first
Work item 9 (shape fix)    ─┘

Work item 3 (triple store)
        │
        ▼
Work item 4 (real projection) ──► Work item 5 (SEMANTIC aggregation)
        │
        ▼
Work item 6 (reasoner + SPARQL)
        │
        ▼
Work item 7 (orchestrator) ── blocked additionally on a build-vs-delegate decision

Work item 8 (protege-view.ttl) — independent, manual, land whenever convenient
```

Work items 1, 2, and 9 have no dependencies and no blockers — they can land
immediately, in any order, in one PR or several. Work items 3–7 follow the
roadmap's own dependency chain (a store before a projection, a projection
before a reasoner/SPARQL surface, both before an orchestrator) and item 7 is
additionally gated on a maintainer decision. Work item 8 is independent of
everything but needs a human at a Protégé session, not code.

See `TASKS.md` for the discrete, checkable task breakdown.
