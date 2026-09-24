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

## Work item 10 — Complete `schema/README.md`'s directory map

**DONE (2026-09-12)**, closed by the constitution-compliance pass.

- [x] **T-090** Add `protege-view.txt` and
      `taxonomy-quality-review-2026-08-23.md` to `schema/README.md`'s file
      listing. → `PLAN.md` Work item 10, approach.
- [x] **T-091** Verify: both files are now listed; the schema parse+`pyshacl`
      check still passes (docs-only change). → `PLAN.md` acceptance
      criteria.
