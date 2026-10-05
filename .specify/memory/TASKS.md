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

## Work item 4 — Build the real step-2 projection (roadmap step 2)

*Work item 3 (closed, see `CHANGELOG.md`) provides the running store, the schema
loader (T-021) and the ingest gate (T-023); Work item 11's decisions (T-100–T-113)
are closed (see `CHANGELOG.md`).*

- [ ] **T-030** *(Work item 11 is closed)* Confirm the `financial-analysis` `v_*` views' actual column
      shapes (view list in `SPEC.md` §2.5; definitions in that repo's
      `src/kg_schema/views.py`), pin the columns this repo reads, and add a
      check that fails on drift (`SPEC.md` §13 item 10). Include the score scale:
      upstream's `score_snapshot.normalized_score` is on 0–100 (FUNDAMENTAL, VALORIZATION,
      TECHNICAL, SECTOR) while `ScoreSnapshotShape` bounds `normalizedScore` to [0, 1], so a
      projection must rescale (or the shape must change). → `PLAN.md` Work item 4,
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

## Work item 12 — Integrate `portfolio-app`/`portfolio-reports` and model per-run weight schemes

*Pending parts of Work item 11's T-108 and T-109. Independent of each other; T-121 follows the
D13 check recorded in `SPEC.md` §2.6, T-120 needs an answer from the upstream maintainer.*

- [ ] **T-120** *(moved from T-108(a); D9)* `portfolio-app` and `portfolio-reports` integration. Upstream's `api/` is read-only with no run-trigger endpoint, and its docs name `portfolio-reports` as the trigger, while this repo's SPEC names `portfolio-app` (not yet created). Agree with upstream who triggers `cycle select`/`cycle monitor`, and what `portfolio-app` and `portfolio-reports` each read: `portfolio-reports` reads the run-log `v_*` views (`v_*_run`), `portfolio-app` should read this repo's query surface. Record the outcome in SPEC D9 and `docs/10`. Open question for the upstream maintainer. → steps 5–6.
- [ ] **T-121** *(moved from T-109(ii); D13)* Extend the weight-scheme model to what upstream records per run: one `AttractivenessWeightScheme` per `cycle_run` (`schemeId` = `scheme_id`, `validFrom` = `cycle_date`, no `validTo`), a component per `score_type` (`weightMetricName` ← `agentOrigin`: FUNDAMENTAL, VALORIZATION, TECHNICAL, SEMANTIC), and the scalar knobs (`top_n`, `max_name_weight`, `max_sector_weight`, `soft_veto_penalty`) as new properties; decide what to do with `inverted` and `SectorRelativeMomentum`, which upstream does not weight. **Decide first:** a per-run scheme with `validFrom` and no `validTo` reads as "still active" for every run (the valid-time convention), so either close the previous run's scheme with `validTo` when the next run is projected, or stop treating a per-run scheme as a valid-time record (a run-date property linked to the run, and relax `validFrom` `minCount 1` in `AttractivenessWeightSchemeShape`). Update `tbox.ttl`, `shapes.ttl`, `rules.ttl`'s `WeightScheme_v1`, docs 06/07 and `schema/README.md` counts. → step 6.

## Status

Closed Work items 1, 2, 3, 5, 7 (superseded/decided by T-007), 9, 10 and 11 are in
`CHANGELOG.md` (Work item 1 closed with T-006 deprecated in favor of T-009).
Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order (Work items 3 and 11 are closed, so Work item 4 is unblocked).
Work item 12 (T-120–T-121): T-120 is blocked on an upstream answer, T-121 is unblocked.
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
