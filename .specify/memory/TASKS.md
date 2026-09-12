# TASKS.md — `portfolio-knowledge-graph`

Discrete, checkable task breakdown for `.specify/memory/PLAN.md`. Each task
references the plan work item and the `SPEC.md` section it closes. Check a
box only when its acceptance criterion (in `PLAN.md`) is actually met — not
when the code/doc edit is merely written.

Task IDs are stable, same rule as `SPEC.md`'s `FR-0xx`/`NR-0xx`: don't
renumber; mark a cancelled/superseded task in place instead. IDs are grouped
in decades by work item (`T-00x` → Work item 1, `T-01x` → Work item 2, `T-02x`
→ Work item 3, …) so a later-inserted task within a work item doesn't force a
renumber of the next work item's block.

## Work item 1 — Rewrite the integration roadmap's stale repo references (docs, no blockers)

- [ ] **T-001** Read `10-integration-roadmap.md` in full and list every
      reference to `news-collector`, `news-crawler`, `edgar_tool.py`, or "a
      LangGraph agent layer" as an unspecified external thing. → `PLAN.md`
      Work item 1, step 1.
- [ ] **T-002** Replace each superseded name with the current repo it maps
      to, and point the agent-layer reference at `08-agent-architecture.md`.
      → step 2.
- [ ] **T-003** Update the roadmap's step 0–9 table so each step names the
      repo that now owns or will build it, without changing done/not-started
      status. → step 3.
- [ ] **T-004** Cross-check `README.md` and `CLAUDE.md` for the same stale
      names and update them in the same pass. → step 4.
- [ ] **T-005** Verify: `grep -rn "news-collector\|news-crawler\|edgar_tool"
      *.md README.md CLAUDE.md` returns nothing outside `SPEC.md`'s
      historical §13 references; the schema parse+`pyshacl` check still
      passes. → `PLAN.md` acceptance criteria.
- [ ] **T-006** Update the two architecture artifacts per constitution
      "Claude Code / coding-agent conduct" #6 (Portfolio Thesis + Portfolio
      Knowledge Graph) — reconcile the gap list entry for this item, never
      rename either artifact.

## Work item 2 — Reconcile `CLAUDE.md` with `origin/master` (docs, no blockers)

- [ ] **T-010** On a checkout confirmed up to date with `origin/master`,
      read `src/etl/news_to_rdf.py`, `pyproject.toml`'s `portfolio-common`
      pin, and `docs/portfolio-common-v1.2-engine-agnostic.md`. → `PLAN.md`
      Work item 2, step 1.
- [ ] **T-011** Update `CLAUDE.md`'s description of `src/etl/`'s database
      access to describe `portfolio_common.news_export` and the actual
      `portfolio-common` version pin. → step 2.
- [ ] **T-012** Add or fold in a pointer to
      `docs/portfolio-common-v1.2-engine-agnostic.md` alongside the existing
      `docs/portfolio-common-v1-migration-plan.md` reference. → step 3.
- [ ] **T-013** Confirm `CLAUDE.md` references both
      `.specify/memory/constitution.md` and `.specify/memory/SPEC.md`; add
      them if missing. → step 4.
- [ ] **T-014** Verify: `CLAUDE.md`'s `src/etl/` description matches the
      actual imports and tag pin (inspection). → `PLAN.md` acceptance
      criteria.
- [ ] **T-015** Update `SPEC.md` §13 item 5 to note this reconciliation done
      for the checkout it was performed on (keep the item number). Also
      update the two architecture artifacts per constitution #6.

## Work item 3 — Stand up a triple store and wire the SHACL ingest gate (roadmap step 1)

- [ ] **T-020** *(maintainer)* Choose GraphDB or Fuseki and its hosting
      (devcontainer service vs. separate). → `PLAN.md` Work item 3, step 1.
- [ ] **T-021** Containerize/configure the chosen store; load
      `tbox.ttl → shapes.ttl → reference.ttl → rules.ttl → instances.trig`
      into a fresh repository/dataset. → step 2.
- [ ] **T-022** Lock the reasoning profile (OWL 2 RL/RDFS+ per
      `07-ontology-topology.md`) in the store's config. → step 3.
- [ ] **T-023** Wire a `pyshacl`-based ingest gate in front of write access.
      → step 4.
- [ ] **T-024** Document connection details in `.env.example`/`docs/`. →
      step 5.
- [ ] **T-025** Verify: a basic SPARQL query returns real results; a
      deliberately-malformed write is rejected before reaching the store;
      the reasoning profile matches `07`'s documented choice. → `PLAN.md`
      acceptance criteria.

## Work item 4 — Build the real step-2 projection (roadmap step 2)

*Blocked on Work item 3 (T-020–T-025).*

- [ ] **T-030** Enumerate and confirm the `financial-analysis` `v_*` views'
      actual column shapes this repo needs to read. → `PLAN.md` Work item 4,
      step 1.
- [ ] **T-031** Design and implement the SHACL-validated-on-write path into
      fresh `urn:graph:ingest:{agent}:{date}` graphs. → step 2.
- [ ] **T-032** Decide and implement `:supersededBy` semantics for a
      restatement. → step 3.
- [ ] **T-033** Retire or explicitly fold in today's `src/etl/` shortcut
      once the real projection covers the SEMANTIC lane (coordinate with
      Work item 5). → step 4.
- [ ] **T-034** Grow the ABox to the full ~503-constituent universe across
      all agent lanes once this projection can produce them. → step 5.
- [ ] **T-035** Verify: a real-data projection run produces SHACL-conformant
      dated graphs at write time; the full universe is represented;
      `src/etl/`'s post-landing role is explicitly documented. → `PLAN.md`
      acceptance criteria.

## Work item 5 — Implement the SEMANTIC score's per-`(asset, day)` aggregation

*Blocked on Work item 4 (T-030–T-035) — implemented as part of its write
path.*

- [ ] **T-040** Define and get sign-off on the aggregation formula
      (article-count-weighted mean `rawValue` per `(asset, day)`, or an
      agreed alternative). → `PLAN.md` Work item 5, step 1.
- [ ] **T-041** Implement it in Work item 4's write path — one aggregated
      `ScoreSnapshot` per `(asset, day)`, not per article. → step 2.
- [ ] **T-042** Mirror to `financial-analysis`'s `score_snapshot[SEMANTIC]`
      column if that repo keeps it. → step 3.
- [ ] **T-043** Verify: exactly one `SEMANTIC`/`Sentiment` `ScoreSnapshot`
      per `(asset, day)` with articles; the formula is documented and
      flagged provisional. → `PLAN.md` acceptance criteria.

## Work item 6 — Bring up the OWL RL reasoner and the SPARQL surface

*Blocked on Work items 3 and 4.*

- [ ] **T-050** Confirm the chosen store's native reasoning support against
      the OWL 2 RL/RDFS+ profile, or select/wire an external reasoner. →
      `PLAN.md` Work item 6, step 1.
- [ ] **T-051** Stand up the three documented SPARQL query patterns (active
      universe, latest snapshot per asset, everything an agent wrote on a
      day). → step 2.
- [ ] **T-052** Expose the surface for the orchestrator to consume (a query
      module here, or a direct SPARQL endpoint). → step 3.
- [ ] **T-053** Verify: all three query patterns return correct results
      against real projected data; subclass-transitivity inference works
      without property-chain inference. → `PLAN.md` acceptance criteria.

## Work item 7 — Decide and build the orchestrator

*Blocked on Work items 3, 4, and 6, and on the maintainer's build-vs-delegate
decision.*

- [ ] **T-060** *(maintainer decision)* Build the two LangGraph state graphs
      here, or delegate the two-speed cycle to `financial-analysis`'s
      `cycle` package. → `PLAN.md` Work item 7, step 1.
- [ ] **T-061** Implement the checkpointer-as-T-1-contagion-lag mechanism
      per whichever choice was made. → step 2.
- [ ] **T-062** Wire a scheduler for the quarterly/daily cadence. → step 3.
- [ ] **T-063** Record the build-vs-delegate decision in `SPEC.md` §3/§12.
      → `PLAN.md` acceptance criteria.
- [ ] **T-064** Verify: a `SelectionCycleGraph` run and a
      `MonitoringCycleGraph` run each produce a dated
      `ingest:ORCHESTRATOR:{date}` graph consistent with `instances.trig`'s
      worked example. → `PLAN.md` acceptance criteria.

## Work item 8 — Regenerate `schema/protege-view.ttl` (manual, independent)

- [ ] **T-070** *(whoever needs the Protégé view current)* Open the four
      authoritative sources + `instances.trig` in Protégé, export flattened
      Turtle, re-add the `:sourceNamedGraph` annotation. → `PLAN.md` Work
      item 8.
- [ ] **T-071** Verify via diff review that `protege-view.ttl` reflects
      current schema content, not a stale regenerate-and-forget. → `PLAN.md`
      acceptance criteria.

## Work item 9 — Resolve the `ScoreSnapshotShape`/Sentiment `rawValue` divergence

- [ ] **T-080** Decide: add a `rawValue`-only branch to `ScoreSnapshotShape`
      for `metricType = Sentiment`, or add a normalization step to the ETL.
      → `PLAN.md` Work item 9, approach.
- [ ] **T-081** Implement the chosen fix. → same.
- [ ] **T-082** Verify: the FR-001/FR-006 parse+`pyshacl` checks show zero
      violations for Sentiment snapshots in a sample run. → `PLAN.md`
      acceptance criteria.
- [ ] **T-083** Document which option was chosen and why in
      `schema/README.md`'s gap list, alongside its three existing gaps. →
      `PLAN.md` acceptance criteria.

## Status

Nothing above is started. Work items 1, 2, and 9 (T-001–T-015, T-080–T-083)
have no blockers and can begin immediately. Work item 3 (T-020–T-025) is
blocked on a maintainer store choice; work items 4–7 (T-030–T-064) follow in
strict dependency order after it, with Work item 7 additionally blocked on a
maintainer build-vs-delegate decision. Work item 8 (T-070–T-071) is
independent but needs a human at a Protégé session, not a coding session.
