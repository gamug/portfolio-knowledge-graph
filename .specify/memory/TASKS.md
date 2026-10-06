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
in decades by work item, each taking the next free decade (`T-00x` → Work item 1, `T-01x` → Work item 2, `T-02x`
→ Work item 3, …; Work item 11 ran into `T-11x`, so Work item 12 took `T-12x` and later
items follow on) so a later-inserted task within a work item doesn't force a
renumber of the next work item's block.

## Work item 4 — Build the real step-2 projection (roadmap step 2)

*Work item 3 (closed, see `CHANGELOG.md`) provides the running store, the schema
loader (T-021) and the ingest gate (T-023); Work item 11's decisions (T-100–T-113)
are closed (see `CHANGELOG.md`).*

- [x] **T-030** *(done 2026-10-05: columns pinned in `src/projection/view_contract.py`, drift check `cli/check_view_contract.py`, score rescale `src/projection/score_scale.py`; decision in `SPEC.md` §2.6)* Confirm the `financial-analysis` `v_*` views' actual column
      shapes (view list in `SPEC.md` §2.5; definitions in that repo's
      `src/kg_schema/views.py`), pin the columns this repo reads, and add a
      check that fails on drift (`SPEC.md` §13 item 10). Include the score scale:
      upstream's `score_snapshot.normalized_score` is on 0–100 (FUNDAMENTAL, VALORIZATION,
      TECHNICAL, SECTOR) while `ScoreSnapshotShape` bounds `normalizedScore` to [0, 1], so a
      projection must rescale (or the shape must change). → `PLAN.md` Work item 4,
      step 1.
- [ ] **T-031** Design and implement the SHACL-validated-on-write path into
      fresh `urn:graph:ingest:{agent}:{date}` graphs. Also: trim `view_contract.py` to the
      columns read; decide the `:rawValue` range for FUNDAMENTAL/VALORIZATION/TECHNICAL, and map upstream SECTOR and
      SEMANTIC into the `[-1, 1]` `rawValue` `ScoreSnapshotShape` requires of them (T-081, T-140;
      `SPEC.md` §2.6; for SECTOR, whether the bound stays is decided with T-155); and guard
      against a change of *meaning* the column-name check cannot see (e.g. upstream moving
      `normalized_score` to [0, 1] would pass the [0, 100] check and become ~0.99 risk), for
      instance a per-lane cohort mean near 50, upstream's documented centre (the row checks are Work item 16, T-162/T-163). → step 2.
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
D13 check recorded in `SPEC.md` §2.6; T-120's upstream answer arrived 2026-10-05 (Work item 15).*

- [ ] **T-120** *(moved from T-108(a); D9. Answered 2026-10-05: `portfolio-app` triggers by running upstream's orchestrator command as a job, `portfolio-reports` reads, `api/` stays read-only; closes when T-150 records it)* `portfolio-app` and `portfolio-reports` integration. Upstream's `api/` is read-only with no run-trigger endpoint, and its docs name `portfolio-reports` as the trigger, while this repo's SPEC names `portfolio-app` (not yet created). Agree with upstream who triggers `cycle select`/`cycle monitor`, and what `portfolio-app` and `portfolio-reports` each read: `portfolio-reports` reads the run-log `v_*` views (`v_*_run`), `portfolio-app` should read this repo's query surface. Record the outcome in SPEC D9 and `docs/10`. → steps 5–6.
- [ ] **T-121** *(moved from T-109(ii); D13)* Extend the weight-scheme model to what upstream records per run: one `AttractivenessWeightScheme` per `cycle_run` (`schemeId` = `scheme_id`, `validFrom` = `cycle_date`, no `validTo`), a component per `score_type` (`weightMetricName` ← `agentOrigin`: FUNDAMENTAL, VALORIZATION, TECHNICAL, SEMANTIC), and the scalar knobs (`top_n`, `max_name_weight`, `max_sector_weight`, `soft_veto_penalty`) as new properties; decide what to do with `inverted` and `SectorRelativeMomentum`, which upstream does not weight. **Upstream reply (2026-10-05):** `score_weights` holds the *configured* weights for all four types in every run, not the blended ones; the blend renormalizes per asset over its non-null components, so the effective weights are per asset, not per scheme. Model the scheme as configured, and read the effective weights from upstream (T-155), never derive them here. **Decide first:** a per-run scheme with `validFrom` and no `validTo` reads as "still active" for every run (the valid-time convention), so either close the previous run's scheme with `validTo` when the next run is projected, or stop treating a per-run scheme as a valid-time record (a run-date property linked to the run, and relax `validFrom` `minCount 1` in `AttractivenessWeightSchemeShape`). Update `tbox.ttl`, `shapes.ttl`, `rules.ttl`'s `WeightScheme_v1`, docs 06/07 and `schema/README.md` counts. → step 6.

## Work item 13 — A `pytest` suite for the code this repo owns

*The constitution has no testing rules and `SPEC.md` NR-005 says there is no suite, so T-130 comes
first. T-131–T-134 are independent of each other once it lands.*

- [ ] **T-130** Amend `constitution.md` (MINOR bump, Governance steps 1–4) with the test structure
      proposed in `PLAN.md` Work item 13 (`tests/`, flat `test_<module>.py`, `conftest.py`, hermetic,
      `integration` marker skipped by default, `uv run pytest`); add the command to §Executable cmds;
      reverse NR-005, `SPEC.md` §10, §13 item 7 and §14. Its own reviewed change. → Approach 1.
- [ ] **T-131** Add `pytest` to the `dev` group and the `tests/` skeleton (`conftest.py` with the
      `src/` path bootstrap, the `integration` marker). → Approach 2.
- [ ] **T-132** Tests for `src/projection/score_scale.py` (0, 50, 100, `None`, out of range, decimal
      exactness) and `contract_check.py` against a synthetic miniature upstream (removed column, new
      unlisted view and view that did not build are drift; added or reordered columns are notes),
      plus a `kg_schema` already in `sys.modules` not being reused; `to_normalized_score` on a
      `bool` or a non-numeric string raises `ValueError`. → Approach 3.
- [ ] **T-133** Tests for `src/etl/common` (severity/G1–G3, GICS rollup, provenance IDs, Turtle
      literals) and the ticker skip-set logic (`SPEC.md` §10). → Approach 3.
- [ ] **T-134** The FR-001 parse + `pyshacl` conformance gate as a test, so `uv run pytest` covers
      the schema too. → Approach 3.
- [ ] **T-135** Decide where the real-checkout drift check (`cli/check_view_contract.py`) runs: a
      check by the projector against the live DB's views before each read, an `integration` test
      against a pinned upstream commit, or both; and whether to ask upstream for a contract
      endpoint/constant (see `SPEC.md` D15: the HTTP `api/` is not a source today). → Approach 4.

## Work item 14 — `ScoreSnapshotShape` and store-gate follow-ups (PR #48 post-merge review)

- [x] **T-140** *(done 2026-10-06)* Tighten `ScoreSnapshotShape`: `SectorRelativeMomentum` requires
      `rawValue` in `[-1, 1]` (`docs/06` §1.8; mapping upstream SECTOR into it is T-031's); `rawValue` at most once (`owl:FunctionalProperty` in `tbox.ttl`);
      `agentOrigin` ↔ `metricType` one-to-one via `sh:xone`. 2458 quads, conforms; 18 synthetic cases,
      the acceptance probe (one violation), `docs/09`'s example and the ETL smoke run agree. → `PLAN.md`
      Work item 14, step 1.
- [ ] **T-141** Run `cli/verify_store.py` against the live GraphDB repository with the current
      acceptance probe and record the result in `docs/graphdb-setup.md`. → step 2.
- [ ] **T-142** Have `kg_store.gate.validate` expose pyshacl's results graph and make
      `acceptance.check_gate` count `sh:ValidationResult` nodes instead of matching
      `"Constraint Violation in"` in the text report. → step 3.

## Work item 15 — Adopt upstream's `v_*` contract changes (reply of 2026-10-05)

*Upstream's reply to the gaps in `SPEC.md` §2.6 (checked against their `0a528be`). T-150 and T-151
need nothing, nor does T-155's removal of the blend formula; the rest of T-152–T-158 waits on the
upstream change it reads. Feeds Work item 4 (T-031) and Work item 12 (T-121).*

- [ ] **T-150** Record the reply in `SPEC.md` §2.6: rows and dispositions D8 (REPLAY never reaches
      production, so no replay flag is needed; `v_cycle_ranking` gains `status`), D9 (the trigger
      decision; also `docs/10`, which closes T-120), D10 (`computed_at`/`run_id` coming;
      `first_seen`/`last_seen` NULL until their Work item 9; `v_media_cooccurrence_edge` with their
      T-082), D11 (`live_book`, dead kind names and `LIVE_ONLY` confirmed; `opt-v1`/`opt-v2` books
      coexist), D12 (`v_fundamental_metric` coming, market cap as its `market_capitalization`
      metric; moves from "rejected for now"), D13 (configured vs effective weights), D14 (still
      unanswered), D16 (`metrics-v5`, `opt-v2`, filings keyed by period end), and the run-id reuse
      fact. List what was declined (PLAN Work item 15). → `PLAN.md` Work item 15, step 1.
- [ ] **T-151** Decide when `:runId` may be emitted now that upstream can reuse a `cycle_run.id`
      (confirmed for `cycle_run` only; `analysis_run`, `pricing_run` and `quant_run` are unconfirmed
      and part of the same ask). Upstream says a run id is unique only with the run's `cycle_type`
      and `started_at`, so emit `<run table>:<id>` only when all of these read checks pass, and
      omit it otherwise (today: every `shared_executive_edge` row):
      (a) the run row exists in that table;
      (b) for `cycle_run`, its `cycle_type` is one the view expects: `ENTITY_RESOLUTION` for
      `v_shared_executive_edge`; `SELECTION` or `MONITORING` for cycle-written `v_score_snapshot`
      rows (`run_kind = 'cycle'`: TECHNICAL, VALORIZATION, SECTOR), `v_sector_aggregate_snapshot`,
      `v_veto`, `v_cycle_ranking`, `v_weight_scheme`/`v_weight_component` and
      `v_portfolio_position`. Pin this list next to `view_contract.py`, so a new `run_id`-carrying
      view needs an entry;
      (c) the row's own time falls inside the run: its wall-clock column (`computed_at`,
      `detected_at`, `created_at`) between the run's `started_at` and `finished_at`, or, for a row
      with only a cycle date (`v_cycle_ranking`, `v_weight_*`), that date equal to the run's
      `as_of`; for `v_portfolio_position`, which has neither, its `valid_from` equal to the run's
      `as_of`. Check (c) is what catches an id reused by a run of the same type.
      Nothing is derived. Until upstream stops reusing ids, these checks lower the risk but do not
      prove uniqueness; `:runId`'s comment in `tbox.ttl` and `SPEC.md` D7 must say so. → step 3.
- [ ] **T-152** Model `v_fundamental_metric`: one immutable observation per (filing, metric, engine
      version) with its asset, filing, metric group and name, value, `engineVersion`, and its own
      event-time and available-at properties (not `:eventTime`/`:availableAt`: their
      `rdfs:domain :ScoreSnapshot` would type the new class as a `ScoreSnapshot`, which
      `AllDisjointClasses` forbids; same reason `:runId` has no domain, T-106), with the same rule
      that as-of reads filter on available-at. Written to
      `urn:graph:ingest:FUNDAMENTAL:{year}-Q{n}`; read only the version upstream marks current.
      Place the class by property shape (`docs/06` §1.2), add it to `AllDisjointClasses`, add its
      shape, and flag it in `schema/README.md` as a gap found against real data. Add the class to
      the FUNDAMENTAL row of `docs/07`'s named-graph table, the authority for graph placement.
      Lets a veto stint point to the metric values that fired it (D12). → step 3.
- [ ] **T-153** Add `:promptHash` to `ScoreSnapshot` (SHACL: only when `agentOrigin` is FUNDAMENTAL)
      and a multi-valued forensic-flag code (from `forensic_flags_json`, once upstream's T-074 fills
      it and documents the codes). Reverses D7's "extras rejected" for these two; `correction_rule`
      stays rejected. → step 3.
- [ ] **T-154** `AssetCoOccurrence`: fill `coOccurrenceComputedOn` from `computed_at` and decide
      whether to make it required; add the `MEDIA` kind and its shape rule when
      `v_media_cooccurrence_edge` exists (after upstream's T-082); do not read `first_seen`/
      `last_seen` until upstream fills them. → step 3.
- [ ] **T-155** Project `v_cycle_ranking` as `AttractivenessSnapshot`s, keeping only
      `status = 'completed'` and non-REPLAY runs: `attractivenessScore` from `blended_score` (on the
      scale upstream documents). Skip a row whose `blended_score` is NULL (e.g. an asset `rank`
      excluded as `UNSCORED`, D4): `AttractivenessSnapshotShape` requires a score and none is
      invented here; confirm with upstream whether such rows appear. Also read rank, selection,
      target weight and the per-asset effective weights once upstream exposes them. Never recompute
      the blend (`SPEC.md` §2.5 item 1), and remove every description of computing it here:
      `docs/06` §1.8's `attractivenessScore = Σ weight_i * component_i` and its `inverted` rule;
      `rules.ttl`'s `WeightScheme_v1` header ("Formula this scheme feeds"); the
      `attractivenessScore`, `WeightComponent` and `:inverted` comments in `tbox.ttl`; and mark the
      2026-08-13 attractiveness design spec in `docs/superpowers/specs/` as design history.
      `:inverted`'s remaining purpose, if any, is decided with T-121. The `SectorRelativeMomentum`
      `[-1, 1]` bound (T-140) is justified in `shapes.ttl` and `schema/README.md` by that formula's
      `(rawValue + 1) / 2`: re-justify it without the formula, or relax it, deciding together with
      T-031's mapping of upstream SECTOR and the range upstream documents for it. Leave
      `schema/protege-view.ttl` to its regeneration (Work item 8); it is generated. → step 3.
- [ ] **T-156** Quant: read `v_quant_portfolio` and `v_quant_vs_live` on the engine version upstream
      marks current, with `engine_version` recorded on each `BenchmarkObservation`. Match a
      `v_quant_vs_live` row to its book on `(as_of, kind, engine_version)`, not `(as_of, kind)`:
      with `opt-v1` and `opt-v2` books coexisting, the old key no longer identifies one book; update
      `:benchmarkKind`'s comment in `tbox.ttl`, which names the old key. Keep `live_book` out of
      `Portfolio` (already enforced by `PortfolioShape`); stop expecting `equal_weight`/
      `cap_weight`. → step 3.
- [ ] **T-157** When upstream ships: re-pin `src/projection/view_contract.py` (new view, new
      columns, the commit in its docstring and in `SPEC.md` §2.6), raise the `schema_version` floor
      (D16), and run `cli/check_view_contract.py` against that commit. Repeat for
      `v_media_cooccurrence_edge`. → step 4.
- [ ] **T-158** Replace the `ASSET_DAY_AGGREGATE` placeholder with upstream's SEMANTIC
      `score_method` value once they give it (D14). → step 4.
- [ ] **T-159** Verify: FR-001 parse + `pyshacl` pass after T-151–T-156, with `schema/README.md`,
      `docs/06` and `docs/07` counts in sync (NR-001), `docs/07`'s named-graph table listing every
      new class, and no doc left describing the blend as computed here (T-155); every upstream
      change this work item reads is recorded in `SPEC.md` §2.6 with its commit. → `PLAN.md`
      acceptance criteria.

## Work item 16 — Validate upstream rows at the read boundary

*Input-side validation of the `v_*` rows, before any triple is built. `pyshacl` stays the graph gate.
See `PLAN.md` Work item 16.*

- [ ] **T-160** Decide the failure policy (stop the run, or quarantine failing rows and report them)
      and the validation tool, from the list of checks needed (types, NULL rate, range, natural-key
      uniqueness, `available_at` against `event_time`, row count per view). Compare plain checks,
      pandera, deepchecks and Great Expectations on that list, including dependency weight. Record the
      decision in `SPEC.md` §13 item 10. → `PLAN.md` Work item 16, step 1.
- [ ] **T-161** Add the chosen dependency to `pyproject.toml` (or none, if plain checks win) and
      update the constitution's dependency mention if it lists one. → step 2.
- [ ] **T-162** Write the expectations for the views Work item 4 reads, beside
      `src/projection/view_contract.py`, keyed by view name. Include the `v_score_snapshot`
      `normalized_score` range and the lane-level cohort mean near 50 that T-031 needs as a guard
      against a change of meaning, and a reused-`run_id` check on the run-keyed views (T-151). → step 2.
- [ ] **T-163** Run the expectations on the read path: a function that returns the validated rows
      and a report naming the view, column and row key of every failure, applying the T-160 policy.
      Lands with T-031. → step 3.
- [ ] **T-164** Tests with synthetic frames, one passing and one failing case per check kind and per
      policy branch, under Work item 13's structure (needs T-131). → step 4.
- [ ] **T-165** Verify and document: `SPEC.md` §13 item 10 states what is checked at the boundary and
      what is not; `uv run pytest` passes; the FR-001 gate is unchanged. → `PLAN.md` acceptance criteria.

## Status

Closed Work items 1, 2, 3, 5, 7 (superseded/decided by T-007), 9, 10 and 11 are in
`CHANGELOG.md` (Work item 1 closed with T-006 deprecated in favor of T-009).
Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order (Work items 3 and 11 are closed, so Work item 4 is unblocked).
Work item 12 (T-120–T-121): T-120 answered, closes with T-150; T-121 is unblocked.
Work item 13 (T-130–T-135): T-130 first (the constitution has no testing rules yet); the rest follow it.
Work item 14 (T-140–T-142): T-140 done; T-141 needs a live GraphDB; T-142 is unblocked.
Work item 15 (T-150–T-159): T-150, T-151 and T-155's formula removal are unblocked; the rest of
T-152–T-158 waits on upstream's changes.
Work item 16 (T-160–T-165): T-160 first (policy and tool); T-163 lands with T-031; T-164 needs Work item 13's skeleton.
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
