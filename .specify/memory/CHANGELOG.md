# CHANGELOG.md — `portfolio-knowledge-graph`

Legacy record of **closed** work items, moved here verbatim from
`.specify/memory/TASKS.md` so that file carries only open work. A work item is
closed once every task in it is checked, or explicitly superseded/moved elsewhere.
Task IDs are stable and never reused; `PLAN.md` keeps each work item's plan and
acceptance criteria. Ordered by work item number.

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
      Superseded — not this repo's.
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
