# TASKS.md — `portfolio-knowledge-graph`

Discrete, checkable task breakdown for `.specify/memory/PLAN.md`. Each task
references the plan work item and the `SPEC.md` section it closes. Check a
box only when its acceptance criterion (in `PLAN.md`) is actually met — not
when the code/doc edit is merely written.

**Closed work items live in `.specify/memory/CHANGELOG.md`**, moved there verbatim
(task IDs unchanged) once every task in them is done, superseded, or moved elsewhere —
see constitution Claude Code conduct #7. This file carries only open work items.

Task IDs are stable, same rule as `SPEC.md`'s `FR-0xx`/`NR-0xx`: don't
renumber; mark a cancelled/superseded task in place instead. IDs are grouped
in decades by work item (`T-00x` → Work item 1, `T-01x` → Work item 2, `T-02x`
→ Work item 3, …) so a later-inserted task within a work item doesn't force a
renumber of the next work item's block.

## Work item 1 — Rewrite the integration roadmap's stale repo references (docs, no blockers)

- [x] **T-001** Read `10-integration-roadmap.md` in full and list every
      reference to `news-collector`, `news-crawler`, `edgar_tool.py`, or "a
      LangGraph agent layer" as an unspecified external thing. → `PLAN.md`
      Work item 1, step 1.
- [x] **T-002** Replace each superseded name with the current repo it maps
      to, and point the agent-layer reference at `08-agent-architecture.md`.
      → step 2.
- [x] **T-003** Update the roadmap's step 0–9 table so each step names the
      repo that now owns or will build it (owners per `SPEC.md` §2.5). The
      done/not-started status rewrite is out of scope and tracked solely under
      T-008. → step 3. *Superseded by T-008 before completion; the roadmap now
      has a "Step → owner → status" table with steps 3–9 marked built/partly
      built upstream per those repos' docs, not verified here.*
- [x] **T-004** Cross-check the tracked docs (`README.md`, `docs/06`, `07`,
      `09`) for the same stale names and update them. → step 4. *Done (README
      in T-008, the others in this change). The local, gitignored `CLAUDE.md`
      was split out because a gitignored file cannot be reviewed or verified
      from a PR: its stale-name line (fixed locally) and its wider rewrite are
      both tracked under T-009.*
- [x] **T-005** Verify: `grep -rn "news-collector\|news-crawler\|edgar_tool"
      *.md README.md CLAUDE.md` returns nothing outside `SPEC.md`'s
      historical §13 references; the schema parse+`pyshacl` check still
      passes. → `PLAN.md` acceptance criteria. *Done 2026-10-02: grep empty
      over root `*.md`, `README.md` and the author's local `CLAUDE.md` (not
      reviewable from a PR); no hits remain under `docs/` or `schema/`
      either (the `docs/08` banner was reworded); the only remaining hits are
      in `.specify/` — `SPEC.md` §13 item 3 (the allowed historical
      reference) and the PLAN/TASKS text that describes this task itself. Parse: `quads: 1608`; `pyshacl`: `conforms:
      True` (flat union of `instances.trig` + `tbox`/`reference`/`rules`
      against `shapes.ttl`, no inference).*
- [~] **T-006** ~~Update the two architecture artifacts per constitution
      "Claude Code / coding-agent conduct" #6 (Portfolio Thesis + Portfolio
      Knowledge Graph) — reconcile the gap list entry for this item, never
      rename either artifact.~~ **Deprecated 2026-10-02 in favor of T-009**,
      which now carries this scope (both artifacts, the gap-list entry, and the
      never-rename rule).

- [x] **T-007** Scan the three upstream repos —
      https://github.com/gamug/portfolio-financial-analysis,
      https://github.com/gamug/portfolio-nlp and
      https://github.com/gamug/portfolio-data-mining — and use them to set
      this repo's proper scope (purely integrative: computation lives
      upstream). **Done 2026-10-02**: ownership map in `SPEC.md` §2.5; pricing
      endpoint confirmed in `portfolio-data-mining`; `.specify/` reconciled
      (SPEC §1/§2/§4/§12/§13/§14, PLAN Goal/WI 4/5/7/11, this file). A
      careful rescan the same day added `SPEC.md` §2.6 (16 upstream drifts,
      D1–D16) and Work item 11. → `PLAN.md` Work item 1, step 5.
- [x] **T-008** Reconcile outside `.specify/` with the T-007 scope decision:
      `08-agent-architecture.md` (LangGraph graphs → reference for upstream
      `cycle`, not a build target), `10-integration-roadmap.md` steps 3–9 and
      the stale "`src/trading/` is empty" row (pricing/EDGAR/entity
      resolution/construction are computed upstream), and the README's
      repo-role wording. Fold into T-003/T-004 where they overlap. →
      `PLAN.md` Work item 7, "What remains here".

- [ ] **T-009** Update the Claude Code artifacts to match the T-007 scope
      decisions (`SPEC.md` §1/§2.5/§2.6) — absorbs the deprecated T-006.
      **NEVER change a published Claude Artifact's name: not its `<title>`
      tag, not the name shown in the artifact gallery, not its URL — update
      content only** (constitution "Claude Code / coding-agent conduct" #6 and
      the rule against renaming a published artifact as a side effect).
      (a) The local, gitignored `CLAUDE.md` — the stale
      `news-collector`/`news-crawler`/`edgar_tool.py` line (split out of
      T-004; already fixed in the author's checkout), purely integrative
      scope, upstream ownership map, `universe.db` as a direct upstream,
      upstream's six-rule catalog replacing the "`RuleClause` tree /
      `VETO_RED_01`" convention (T-103), no orchestrator or scheduler here
      (`portfolio-app` triggers cycles, T-108), the corrected document chain
      (`docs/` paths, `08` as reference only). (b) The two published
      architecture artifacts named in constitution conduct #6 — *Portfolio
      Thesis* (system-wide) and *Portfolio Knowledge Graph*
      (repository-specific) — plus any other published artifact the scope
      change makes stale: regenerate/reconcile their content (including the
      gap-list entry for Work item 1) from the current `.md`/`.ttl` sources.
      `CLAUDE.md` is untracked, so its edit cannot ride a PR: record in the PR
      description that it was done locally. Do it after T-003/T-004/T-008 and
      T-103's decision wording are settled. → `PLAN.md` Work item 1, step 6.
      **Progress 2026-10-02:** (a) done locally (`CLAUDE.md` rewritten);
      (b) *Portfolio Thesis* and *Portfolio Knowledge Graph* republished in
      place with names/URLs unchanged. Still open: the other artifacts the
      scope change makes stale — *Agent Architecture* and *Integration
      Roadmap* (and possibly *Ontology Definition* / *Ontology Topology*, for
      the rule-catalog wording) — then tick.

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

*Blocked on Work item 3 (T-020–T-025) and on Work item 11's decisions
(T-100–T-104).*

- [ ] **T-030** *(after Work item 11's T-100–T-104)* Confirm the `financial-analysis` `v_*` views' actual column
      shapes (view list in `SPEC.md` §2.5; definitions in that repo's
      `src/kg_schema/views.py`), pin the columns this repo reads, and add a
      check that fails on drift (`SPEC.md` §13 item 10). → `PLAN.md` Work item 4,
      step 1.
- [ ] **T-031** Design and implement the SHACL-validated-on-write path into
      fresh `urn:graph:ingest:{agent}:{date}` graphs. → step 2.
- [ ] **T-032** Decide and implement `:supersededBy` semantics for a
      restatement. → step 3.
- [ ] **T-033** Retire or explicitly fold in today's `src/etl/` shortcut
      once the real projection covers the SEMANTIC lane, i.e. once the
      upstream `score_snapshot[SEMANTIC]` row exists to project (Work item
      5's remainder). → step 4.
- [ ] **T-034** Grow the ABox to the full ~503-constituent universe across
      all agent lanes once this projection can produce them. → step 5.
- [ ] **T-035** Verify: a real-data projection run produces SHACL-conformant
      dated graphs at write time; the full universe is represented;
      `src/etl/`'s post-landing role is explicitly documented. → `PLAN.md`
      acceptance criteria.

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

## Work item 11 — Reconcile the ontology and ETL with the upstream contracts (T-007 rescan)

*Decisions first; Work item 4 is gated on T-100–T-104. D-numbers refer to
`SPEC.md` §2.6.*

- [ ] **T-100** *(D1)* Replace the ETL's live-Wikipedia asset master
      (FR-004) with `universe.db` as-of reads (`KG_UNIVERSE_DB`, read-only via
      `portfolio_common.db`), emitting `:Asset` + `:UniverseMembership`
      (`validFrom`/`validTo`); document the stale-between-snapshots risk and
      that `universe.db` is now a direct upstream. → `PLAN.md` Work item 11,
      step 1.
- [ ] **T-101** *(D2)* Decide how `available_at` vs. `event_time` is modelled
      (new properties, or encoded in the ingest-graph date) so as-of queries
      cannot leak look-ahead; update `tbox.ttl`/`shapes.ttl` and `07`. → step 2.
- [ ] **T-102** *(D3)* Model veto stints (`raisedOn`/`clearedOn`/`lastSeenOn`
      or `validFrom`/`validTo`) and write the "active at cutoff C" predicate
      as the T-1-lag SPARQL pattern. → step 3.
- [ ] **T-103** *(D4 — decided 2026-10-02: upstream's catalog is final)*
      Implement it: add upstream's six rules (`LEVERAGE_EXTREME`, `NEGATIVE_FCF`,
      `LIQUIDITY_DISTRESS`, `PRICE_CRASH`, `EARNINGS_MISSING`,
      `DATA_QUALITY`) as `RuleDefinition`s (single-leaf `RuleClause`s) so
      `:appliesRule` resolves, supersede `rules.ttl`'s seven tree rules
      (including `VETO_RED_01`), and update FR-003, `06`/`07`, `schema/README.md`
      and the FR-001 counts. → step 3.
- [ ] **T-104** *(D5)* Decide `:DataQualityIssue` (evidence for the
      `DATA_QUALITY` veto) vs. dropping it. → step 3.
- [ ] **T-105** *(D6)* `agentOrigin` `QUANTITATIVE` → `VALORIZATION` in
      `shapes.ttl`/`reference.ttl` (MetricType) and docs; document each score
      type's `event_time` meaning and the extra provenance fields. → step 4.
- [ ] **T-106** *(D7)* Decide how upstream `run_id`/`as_of`/`code_version`/
      `engine_version` map onto `provenanceId` (or a `Run` class). → step 4.
- [ ] **T-107** *(D10)* Give projected `sharedExecutiveWith` a
      method/weight/confidence (or a separate candidate property) so news
      co-occurrence is not asserted as fact; decide `media_cooccurrence`. →
      step 5.
- [ ] **T-108** *(D9 decided 2026-10-02; D11 open, maintainer sign-off)*
      (a) ~~Who triggers the quarterly/daily cycles~~ — **`portfolio-app`**
      (not yet created) calls the upstream endpoints; raise with upstream that
      `api/` is read-only with no run-trigger endpoint and that their docs name
      `portfolio-reports` as the trigger. (b) Still to decide: which `quant`
      outputs become individuals (benchmark books/positions/performance; never
      returns, μ or Σ — NR-003). → steps 5–6.
- [ ] **T-109** *(D8, D12, D13, D15, D16)* Pin and assert upstream's
      `schema_version` floor; confirm `v_cycle_ranking`'s actual behaviour
      (docstring says latest-only, SQL returns all runs); list contract gaps
      for upstream (no `fundamental_metrics`/market-cap view; REPLAY
      exclusion); check D13's weight-scheme mapping. → step 6.
- [ ] **T-110** *(D16)* Reconcile the `portfolio-common` pin (`v1.2.0` here and
      in `portfolio-nlp`; `v1.2.1` in `financial-analysis` and
      `portfolio-data-mining`) — verify compatibility, then re-pin or record
      why not. → step 6.
- [ ] **T-111** *(D14)* Add a `score_method` discriminator for SEMANTIC and
      correct the wording upstream still attributes to this repo (their
      rollout step 4); no write-back code exists here to remove. → step 6.
- [ ] **T-112** Record each D1–D16 disposition (adopted / translated /
      rejected / raised upstream) in `SPEC.md` §2.6; re-run FR-001 and update
      `schema/README.md` counts if `schema/` changed. → `PLAN.md` acceptance
      criteria.
- [ ] **T-113** *(found while handling review on PR #22)* Reconcile FR-005
      with the code: `src/etl/news_to_rdf.py` reads SOURCE `urls.db`
      `body_text` (via `news_export`) for `compute_severity`'s hard-trigger
      keyword scan, but FR-005, §2.2 and its acceptance grep say the ETL never
      reads `body_text`. Either drop the body-text escalation or amend FR-005,
      §2.2 and §12. → `PLAN.md` Work item 11.

## Status

Closed Work items 2, 5, 7 (superseded/decided by T-007) and 10 are in
`CHANGELOG.md`. Work item 1 has only T-009 open (T-001–T-005,
T-007, T-008 done; T-006 deprecated in favor of T-009); it is local/artifact
work with no code blockers. Work
item 9 (T-080–T-083) has no blockers. Work item 3 (T-020–T-025) is blocked on
a maintainer store choice; Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order after it; Work item 11 (T-100–T-113, decisions
from the T-007 rescan) gates Work item 4 and has no store dependency.
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
