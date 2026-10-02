# CHANGELOG.md — `portfolio-knowledge-graph`

Legacy record of **closed** work items, moved here verbatim from
`.specify/memory/TASKS.md` so that file carries only open work. A work item is
closed once every task in it is checked, or explicitly superseded/moved elsewhere.
Task IDs are stable and never reused; `PLAN.md` keeps each work item's plan and
acceptance criteria. Ordered by work item number.

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

- [x] **T-009** Update the Claude Code artifacts to match the T-007 scope
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
      **Done 2026-10-02:** (a) the local `CLAUDE.md` rewritten (untracked, so
      not in a PR); (b) republished in place, names and URLs unchanged:
      *Portfolio Thesis*, *Portfolio Knowledge Graph*, *Agent Architecture*,
      *Integration Roadmap*, *Ontology Definition*, *Ontology Topology*.

## Work item 2 — Reconcile `CLAUDE.md` with `origin/master` (docs, no blockers)

**DONE (2026-09-12)**, closed by the constitution-compliance pass.

- [x] **T-010** On a checkout confirmed up to date with `origin/master`,
      read `src/etl/news_to_rdf.py`, `pyproject.toml`'s `portfolio-common`
      pin, and `docs/portfolio-common-v1.2-engine-agnostic.md`. → `PLAN.md`
      Work item 2, step 1.
- [x] **T-011** Update `CLAUDE.md`'s description of `src/etl/`'s database
      access to describe `portfolio_common.news_export` and the actual
      `portfolio-common` version pin. → step 2.
- [x] **T-012** Add or fold in a pointer to
      `docs/portfolio-common-v1.2-engine-agnostic.md` alongside the existing
      `docs/portfolio-common-v1-migration-plan.md` reference. → step 3.
- [x] **T-013** Confirm `CLAUDE.md` references both
      `.specify/memory/constitution.md` and `.specify/memory/SPEC.md`; add
      them if missing. → step 4.
- [x] **T-014** Verify: `CLAUDE.md`'s `src/etl/` description matches the
      actual imports and tag pin (inspection). → `PLAN.md` acceptance
      criteria.
- [x] **T-015** Update `SPEC.md` §13 item 5 to note this reconciliation done
      for the checkout it was performed on (keep the item number). The two
      architecture artifacts (constitution #6) needed no update — this pass
      touched no fact either artifact currently states (verified by reading
      both; still content-consistent with the repo's actual state).

## Work item 5 — ~~Implement the SEMANTIC score's per-`(asset, day)` aggregation~~ (SUPERSEDED, reassigned upstream)

**CLOSED (2026-10-02)**, superseded by the T-007 scope decision.

*Superseded 2026-10-02 (T-007): the aggregation is computed by
`portfolio-nlp` and materialized by `portfolio-financial-analysis`; this repo
only projects the resulting row (Work item 4). IDs kept, not reused.*

- [~] **T-040** ~~Define and get sign-off on the aggregation formula.~~
      Superseded — upstream's (`portfolio-nlp`) decision.
- [~] **T-041** ~~Implement it in Work item 4's write path.~~ Superseded —
      replaced by projecting the upstream SEMANTIC row (covered by T-031/T-033).
- [~] **T-042** ~~Mirror to `financial-analysis`'s `score_snapshot[SEMANTIC]`.~~
      Superseded — the dependency now runs the other way (this repo stops
      writing it).
- [~] **T-043** ~~Verify one aggregated snapshot per `(asset, day)`.~~
      Superseded — verify instead, within T-035, that the projected SEMANTIC
      lane equals the upstream rows.

## Work item 7 — ~~Decide and build the orchestrator~~ (DECIDED: delegate)

**CLOSED (2026-10-02)**, decided by the T-007 scope decision.

*Decided 2026-10-02 (T-007): the two-speed cycle is `portfolio-financial-
analysis`'s `cycle` package; this repo builds no orchestrator. IDs kept, not
reused.*

- [x] **T-060** *(maintainer decision)* Build the two LangGraph state graphs
      here, or delegate to `financial-analysis`'s `cycle` package. →
      **Delegate.**
- [~] **T-061** ~~Implement the checkpointer-as-T-1-contagion-lag mechanism.~~
      Superseded — implemented upstream (`cycle_checkpoint`, T-1 lagged vetoes).
- [~] **T-062** ~~Wire a scheduler for the quarterly/daily cadence.~~
      Superseded — not this repo's; **but no scheduler exists upstream either**
      (T-007 rescan, `SPEC.md` §2.6 D9) — the maintainer assigned the cadence to the future `portfolio-app` (T-108).
- [x] **T-063** Record the decision in `SPEC.md` — done (§2.2/§2.5/§12).
- [~] **T-064** ~~Verify a `SelectionCycleGraph`/`MonitoringCycleGraph` run
      produces an `ORCHESTRATOR` graph.~~ Superseded — verify instead, within
      T-035, that `cycle`'s `v_veto`/`v_cycle_ranking`/`v_portfolio_position`
      rows project into dated `ingest:ORCHESTRATOR:{date}` graphs.

## Work item 10 — Complete `schema/README.md`'s directory map

**DONE (2026-09-12)**, closed by the constitution-compliance pass.

- [x] **T-090** Add `protege-view.txt` and
      `taxonomy-quality-review-2026-08-23.md` to `schema/README.md`'s file
      listing. → `PLAN.md` Work item 10, approach.
- [x] **T-091** Verify: both files are now listed; the schema parse+`pyshacl`
      check still passes (docs-only change). → `PLAN.md` acceptance
      criteria.
