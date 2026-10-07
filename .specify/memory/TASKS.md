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
      columns read; decide the `:rawValue` range for FUNDAMENTAL (T-171 drops its
      `normalizedScore` instead; the range needs Q6, asked with T-150's next follow-up) and for
      VALORIZATION/TECHNICAL, and map
      upstream SEMANTIC into the `[-1, 1]` `rawValue` `ScoreSnapshotShape` requires of it (T-081;
      `SPEC.md` §2.6). SECTOR's `raw_value` is read verbatim into the [-100, 100] bound T-155 sets,
      and its 0-100 `normalized_score` is rescaled like the other lanes (add SECTOR to
      `RESCALED_SCORE_TYPES` in `src/projection/score_scale.py`, whose module docstring already
      describes that step (PR #60); do not
      re-add FUNDAMENTAL, which T-171 removed: project its `raw_value` only, never its
      `normalized_score`). Skip a
      cycle-lane row with a NULL `available_at` (every such row before upstream's T-144) and count it
      in Work item 16's boundary report (T-163), so no row is dropped silently; never fill it in. Parse
      `computed_at` with `+00:00` or `Z`. Re-read the keys of the late rows T-163's previous report
      persisted (quarantined rows bound for an ingestion-dated graph, `PLAN.md` Work item 16), and drop
      each key once its row is written. And guard
      against a change of *meaning* the column-name check cannot see (e.g. upstream moving
      `normalized_score` to [0, 1] would pass the [0, 100] check and become ~0.99 risk), for
      instance a per-lane cohort mean near 50, upstream's documented centre (Work item 16's
      T-162 owns that check and T-163 runs it; T-031 calls it). → step 2.
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

- [x] **T-120** *(moved from T-108(a); D9. Answered 2026-10-05: `portfolio-app` triggers by running upstream's orchestrator command as a job, `portfolio-reports` reads, `api/` stays read-only; recorded in `SPEC.md` D9 and `docs/10` by T-150)* `portfolio-app` and `portfolio-reports` integration. Upstream's `api/` is read-only with no run-trigger endpoint, and its docs name `portfolio-reports` as the trigger, while this repo's SPEC names `portfolio-app` (not yet created). Agree with upstream who triggers `cycle select`/`cycle monitor`, and what `portfolio-app` and `portfolio-reports` each read: `portfolio-reports` reads the run-log `v_*` views (`v_*_run`), `portfolio-app` should read this repo's query surface. Record the outcome in SPEC D9 and `docs/10`. → steps 5–6.
- [x] **T-121** *(done 2026-10-07 in PR #65: option 2, a per-run scheme is an immutable observation dated by a new `:cycleDate` (`v_weight_scheme.cycle_date`), exactly one of `validFrom` or `cycleDate`-without-`validTo` (`sh:xone`), placed in `urn:graph:ingest:ORCHESTRATOR:{date}`; `:bookWeightingRule`, `:topN`, `:maxNameWeight`, `:maxSectorWeight`, `:softVetoPenalty` added, `:inverted` optional; 2547 quads; the text below is the original task, kept for the record)* Extend the weight-scheme model to what upstream records per run: one `AttractivenessWeightScheme` per `cycle_run` (`schemeId` = `cycle_run:<id>`, `validFrom` = `cycle_date`, no `validTo`), a component per `score_type` (`weightMetricName` = that lane's `metricType` name, the fixed mapping `ScoreSnapshotShape` already pairs with `agentOrigin`: FUNDAMENTAL → `ScoreFinanciero`, VALORIZATION → `ScoreCuantitativo`, TECHNICAL → `ScoreTecnico`, SEMANTIC → `Sentiment`), upstream's `scheme_id` on a new book-weighting-rule property, and the scalar knobs (`top_n`, `max_name_weight`, `max_sector_weight`, `soft_veto_penalty`) as new properties, read verbatim (**confirmed, third reply 2026-10-06, Q5:** all three are fractions of the book, 0.05 = 5%, bound [0, 1] as the shapes already assume; `max_name_weight` stays optional — it is `NULL` on a MONITORING run by default, deriving from N at book time; the recorded value is the *effective* cap on a SELECTION run since upstream's Work item 18, the *configured* value on a MONITORING run); `:inverted` becomes optional (below), and `SectorRelativeMomentum`, which upstream does not weight, gets no component. The scheme's identity is a `cycle_run` id, so it relies on upstream's T-145 (ids never reused) and T-100: until both their T-145 and their T-100 rebuild have landed (T-145 stops new reuse; the rebuild drops ids already reused, as T-151 says), project a scheme only for a run that passes T-151's checks (a scheme whose run fails them is not projected, nor are the snapshots computed with it). **Upstream reply (2026-10-05):** `score_weights` holds the *configured* weights for all four types in every run, not the blended ones; the blend renormalizes per asset over its non-null components, so the effective weights are per asset, not per scheme. Model the scheme as configured, and read the effective weights from upstream (T-155), never derive them here. **Second reply (2026-10-06):** why the identity is the run: `scheme_id` is the rule that turns the ranking into book weights (`score_proportional`, `score_tilt`), not the blend, and a blend is identified by its `cycle_run`. New runs (their T-141) record three components at 1/3 (no SEMANTIC), older runs four (0.4/0.3/0.2/0.1); both are per-run schemes. `:inverted` has no upstream counterpart (D13 item 4): make it optional, emit it for no upstream scheme, and keep it on `WeightScheme_v1` (design history). **Decide first:** a per-run scheme with `validFrom` and no `validTo` reads as "still active" for every run (the valid-time convention), so either close the previous run's scheme with `validTo` when the next run is projected, or stop treating a per-run scheme as a valid-time record (a run-date property linked to the run, and relax `validFrom` `minCount 1` in `AttractivenessWeightSchemeShape`). Update `tbox.ttl`, `shapes.ttl`, `rules.ttl`'s `WeightScheme_v1`, docs 06/07 and `schema/README.md` counts. → step 6.

## Work item 13 — A `pytest` suite for the code this repo owns

*Constitution 1.5.0 sets the rules these tasks follow (Project structure #10, Code & Git #9); `SPEC.md`
NR-005, §10, §13 item 7 and §14 now describe the suite (T-130, T-134). T-132–T-134 and T-136 are
independent of each other once T-131 lands.*

- [x] **T-130** Amend `constitution.md` (MINOR bump, Governance steps 1–4) with the test structure
      proposed in `PLAN.md` Work item 13 (`tests/`, flat `test_<module>.py`, `conftest.py`, hermetic,
      `integration` marker skipped by default, `uv run pytest`); add the command to §Executable cmds;
      reverse NR-005, `SPEC.md` §10, §13 item 7 and §14. Its own reviewed change. → Approach 1.
      *(Constitution 1.5.0 done: Project structure #10, Code & Git #9, `uv run pytest`. Still open:
      the `SPEC.md` reversals (NR-005, §10, §13 item 7, §14), done with T-134 in PR #62, with
      constitution 1.5.1 dropping the stale "once T-131 lands" wording.)*
- [x] **T-131** *(done 2026-10-06 in PR #56, pulled forward because constitution Code & Git #9
      required a test for T-171's `score_scale.py` fix in the same PR; `tests/fixtures/` is created
      by the first test that needs one)* Add `pytest` to the `dev` group and the `tests/` skeleton per constitution #10:
      `[tool.pytest.ini_options]` with `pythonpath = ["src"]`, `testpaths = ["tests"]`, the
      `integration` marker and `addopts = "-m 'not integration'"`; `tests` added to
      `.code_quality/mypy.ini`'s `files`; a `conftest.py` for shared fixtures only (no `sys.path`
      edits). → Approach 2.
- [x] **T-132** *(done 2026-10-07: `tests/test_score_scale.py` in PR #56, every case listed below
      for it, verified to fail on the pre-T-171 module; `tests/test_contract_check.py` in PR #57, each
      drift/note case checked to fail when its branch of `check` is broken)* Tests for `src/projection/score_scale.py` (0, 50, 100, `None`, out of range, decimal
      exactness, and `"FUNDAMENTAL"` raising `ValueError`, so T-171's removal can't silently
      regress) and `contract_check.py` against a synthetic miniature upstream (removed column, new
      unlisted view and view that did not build are drift; added or reordered columns are notes),
      plus a `kg_schema` already in `sys.modules` not being reused; `to_normalized_score` on a
      `bool` or a non-numeric string raises `ValueError`. → Approach 3.
- [x] **T-133** Tests for `src/etl/common` (severity/G1–G3, GICS rollup, provenance IDs, Turtle
      literals) and the ticker skip-set logic (`SPEC.md` §10). → Approach 3.
      *(done in PR #61: `tests/test_etl_common.py` and `tests/test_asset_master.py`; the skip-set is
      `reference_asset_tickers()` plus `build_assets(already_defined=...)`; the rollup test also
      checks every target against `reference.ttl`)*
- [x] **T-134** *(done in PR #62: `tests/test_schema_gate.py` parses the bundle in load order, runs `pyshacl`, shows the ticker rule alone rejects a broken `:Asset`, and pins every quad count and the named-graph count `SPEC.md` states to the real ones, which had drifted from 2458 to 2473 quads and 15 to 16 graphs)* The FR-001 parse + `pyshacl` conformance gate as a test, so `uv run pytest` covers
      the schema too. → Approach 3.
- [ ] **T-135** Decide where the real-checkout drift check (`cli/check_view_contract.py`) runs: a
      check by the projector against the live DB's views before each read, an `integration` test
      against a pinned upstream commit, or both; and whether to ask upstream for a contract
      endpoint/constant (see `SPEC.md` D15: the HTTP `api/` is not a source today). → Approach 4.
- [x] **T-136** *(done 2026-10-07 in PR #64: `tests/test_kg_gate.py`, `test_kg_load_schema.py`, `test_cli_check_view_contract.py`; `derived:quant:{date}` added to `APPEND_ONLY_PATTERNS`; three worked-example graphs the gate cannot take as a batch are strict xfails, T-146; `check_gate` and its test also share one `violations()` helper, the PR #63 nit)* Tests for `src/kg_store/` and the `cli/` exit codes, hermetic (a fake `GraphDB`, no
      running store). **Includes a fix found in PR #62's review:** `gate.check_target` rejects
      `urn:graph:derived:quant:{date}`, which `docs/07` defines (T-108) and `instances.trig` uses, so
      add it to `APPEND_ONLY_PATTERNS` with a test that every `instances.trig` graph is accepted
      (constitution Code & Git #9). Then: `load_schema.expected_sizes`/`load`/`verify` (load order, named graphs, size
      mismatch); the ingest gate's `check_target`, `parse_batch`, `unknown_types`,
      `untyped_writes` and `validate` (a conforming batch passes, a non-conforming one raises);
      `acceptance.check_gate`'s violation count (one `sh:ValidationResult`, T-142);
      `load_schema.main(argv)` called directly; `cli/check_view_contract.py` run as a subprocess
      (constitution #10) against a synthetic upstream in `tmp_path`, exiting 1 on drift and 0
      otherwise, plus the error case (a view `ensure` cannot create raises, so the exit is 1 with
      a traceback and no `DRIFT` lines: the exit code alone does not tell it from drift, PR #57
      review). `cli/load_schema.py`, `verify_store.py` and `ingest.py` need a live store: their
      exit codes are `integration` tests with T-141. `cli/build_data_ttl.py` is transitional
      (T-033). → Approach 3.

## Work item 14 — `ScoreSnapshotShape` and store-gate follow-ups (PR #48 post-merge review)

- [x] **T-140** *(done 2026-10-06; T-155 widens its [-1, 1] bound)* Tighten `ScoreSnapshotShape`:
      `SectorRelativeMomentum` requires `rawValue` in `[-1, 1]` (`docs/06` §1.8; mapping upstream
      SECTOR into it is T-031's); `rawValue` at most once (`owl:FunctionalProperty` in `tbox.ttl`);
      `agentOrigin` ↔ `metricType` one-to-one via `sh:xone`. 2458 quads, conforms; 18 synthetic
      cases, the acceptance probe (one violation), `docs/09`'s example and the ETL smoke run agree.
      → `PLAN.md` Work item 14, step 1.
- [ ] **T-141** Run `cli/verify_store.py` against the live GraphDB repository with the current
      acceptance probe and record the result in `docs/graphdb-setup.md`. → step 2.
- [x] **T-142** *(done 2026-10-07 in PR #63: `gate.validate` raises `ShaclRejected`, an `IngestRejected` carrying pyshacl's results graph; `check_gate` requires exactly one `sh:ValidationResult`, a `:timestamp` `MinCountConstraintComponent`, with `tests/test_acceptance_gate.py` covering wording-independence, a second violation, a single violation of another kind, a non-SHACL rejection and an accepted batch)* Have `kg_store.gate.validate` expose pyshacl's results graph and make
      `acceptance.check_gate` count `sh:ValidationResult` nodes instead of matching
      `"Constraint Violation in"` in the text report. → step 3.
- [ ] **T-146** Let the gate take the worked example's own batches (found writing T-136's tests):
      `gate.validate` checks a batch alone, so three `instances.trig` graphs fail it:
      `derived:entity-resolution:2026-08-05` (`sh:class :Asset` on `:coOccurrenceAsset` values typed
      in another graph), `derived:quant:2026-08-05` (`sh:class` on `:quantAsset`/`:quantPortfolio`
      values typed elsewhere) and `ingest:ORCHESTRATOR:2026-08-05` (closing a Veto with `:clearedOn`,
      which the untyped-subject rule allows only for `:validTo`). Decide per case: type the
      references in the batch's data graph for validation (without writing them), or relax the shape;
      allow `:clearedOn` as a closing property. Then drop the three `xfail`s in
      `tests/test_kg_gate.py` (strict, so they fail once it is fixed). Constitution Code & Git #9.
      → `PLAN.md` Work item 14, step 4.

## Work item 15 — Adopt upstream's `v_*` contract changes (replies of 2026-10-05, 2026-10-06 x2)

*Upstream's reply to the gaps in `SPEC.md` §2.6 (checked against their `0a528be`), their second
reply (`597832a`), which accepts our asks as their T-144 and T-145 and corrects six assumptions,
and their third reply (also `597832a`, answering our five follow-up questions and correcting the
`component_value` assumption) (`PLAN.md` Work item 15, step 3 lists the decisions). T-150, T-151's
rule, T-155's removal of the blend formula, the shape corrections in T-153 and T-155, T-170, T-171
and T-158's ownership question need nothing; the rest of T-152–T-158 waits on the upstream change
it reads. Feeds Work item 4 (T-031) and Work item 12 (T-121).*

- [x] **T-150** Record the reply in `SPEC.md` §2.6: rows and dispositions D8 (REPLAY never reaches
      production, so no replay flag is needed; `v_cycle_ranking` gains `status`; "production DB
      only", in the row and its disposition, becomes "a database at the floor with no REPLAY run",
      T-157's check), D9 (the trigger
      decision; also `docs/10`, which closes T-120), D10 (`computed_at`/`run_id` coming;
      `first_seen`/`last_seen` NULL until their Work item 9; `v_media_cooccurrence_edge` with their
      T-082), D11 (`live_book`, dead kind names and `LIVE_ONLY` confirmed; `opt-v1`/`opt-v2` books
      coexist), D12 (`v_fundamental_metric` coming, market cap as its `market_capitalization`
      metric; moves from "rejected for now"), D13 (configured vs effective weights), D14 (still
      unanswered), D16 (`metrics-v5`, `opt-v2`, a filing's period identified by its period end), and the run-id reuse
      fact. List what was declined (PLAN Work item 15). Also record the second reply: the six
      corrections (D6 SECTOR range, D13 `blended_score` and `scheme_id`, D2 `available_at` on cycle
      lanes, D12 `metric_id`/`unit`, D11/D12 `is_current` as at most one), the forensic-flag
      format, `+00:00` timestamps, id reuse on all four run tables and `sec_filings` (D7),
      production at `schema_version` 8 (D16), cohort-relative `normalized_score`, their weights
      change (D13: 1/3 each for new runs, SEMANTIC out of the blend), and the upstream task each ask
      maps to (their T-144, T-145, T-074 and T-141, their Work item 2, and after their T-100).
      → `PLAN.md` Work item 15, step 1.
- [ ] **T-151** *(rule recorded 2026-10-07 in PR #60: `:runId`'s comment and `SPEC.md` D7; open: the checks and their pinned `cycle_type` list, which land with T-031 and T-163, and dropping (c) once upstream's T-145 and T-100 land)* Decide when `:runId` may be emitted now that upstream can reuse a `cycle_run.id`
      (first confirmed for `cycle_run`; the second reply extends it to `analysis_run`,
      `pricing_run`, `quant_run` and `sec_filings`, below). Upstream says a run id is unique only
      with the run's `cycle_type` and `started_at`, so emit `<run table>:<id>` only when all of
      these read checks pass, and omit it otherwise (today: every `shared_executive_edge` row).
      **Exception, rows whose identity is the run:** a `v_weight_scheme`, `v_weight_component`,
      `v_cycle_ranking` or `v_cycle_ranking_component` row whose run fails the checks is skipped,
      not kept without `:runId` (its scheme or snapshot IRI is the run id, T-121, T-155), and
      counted in Work item 16's boundary report (T-163). Every other row only loses `:runId`. The
      checks:
      (a) the run row exists in that table;
      (b) for `cycle_run`, its `cycle_type` is one the view expects: `ENTITY_RESOLUTION` for
      `v_shared_executive_edge`; `SELECTION` or `MONITORING` for cycle-written `v_score_snapshot`
      rows (`run_kind = 'cycle'`: TECHNICAL, VALORIZATION, SECTOR), `v_sector_aggregate_snapshot`,
      `v_veto`, `v_cycle_ranking`, `v_cycle_ranking_component`, `v_weight_scheme`/
      `v_weight_component` and `v_portfolio_position`. Pin this list next to `view_contract.py`,
      so a new `run_id`-carrying view needs an entry;
      (c) the row's own time falls inside the run: its wall-clock column (`computed_at`,
      `detected_at`, `created_at`) between the run's `started_at` and `finished_at`, or, for a row
      with only a cycle date (`v_cycle_ranking`, `v_weight_*`; a `v_cycle_ranking_component` row
      takes its ranking row's), that date equal to the run's
      `as_of`; for `v_portfolio_position`, which has neither, its `valid_from` equal to the run's
      `as_of`. Check (c) is what catches an id reused by a run of the same type.
      Nothing is derived. Until upstream stops reusing ids, these checks lower the risk but do not
      prove uniqueness; `:runId`'s comment in `tbox.ttl` and `SPEC.md` D7 must say so.
      **Second reply:** ids can be reused on all four run tables and on `sec_filings`, only after a
      deletion (a manual one on `cycle_run`, their T-120 repair on `sec_filings`). Their T-145 makes
      them non-reusable and their T-100 rebuild drops the orphaned edge ids; after both, keep
      checks (a) and (b) (plain reads) and drop (c). Key `:SECFiling` IRIs by accession number,
      never `sec_filings.id`, and resolve a row's `filing_id` to it through `v_sec_filing` in the
      same read. **Confirmed, third reply (2026-10-06), Q4:** `accession_number` is never NULL or
      empty (0 of 5,076 production rows, 0 of 449 pilot rows), so the key is always available.
      It is *not* unique in production: 30 accession numbers are shared by 60 legacy rows from
      before upstream's T-091 (a 10-Q's quarters stored as separate rows under one accession,
      repaired by their T-120) — harmless here, since production (`schema_version` 8) is already
      excluded by T-157's floor. It is unique in the pilot and will be in their T-100 rebuild; no
      constraint enforces it today, but their T-145 adds a uniqueness check to their pilot
      verifier. → step 3.
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
      Lets a veto stint point to the metric values that fired it (D12). **Second reply:**
      `metric_name` has no group prefix; read it verbatim, and read their T-144's `metric_id`
      (`leverage.debt_to_equity`) into its own property, the join to `ThresholdComparison.metricName`
      and `v_rule_catalog.param_metric`. Read `unit` (`ratio` = fraction, `x` = multiple, `usd`)
      verbatim; `value` is never converted. `is_current` marks at most one row per key: a filing with
      no current row gets no observation. → step 3.
- [ ] **T-153** *(comment half done 2026-10-07 in PR #59: `:availableAt` and `:normalizedScore`; open: `:promptHash` and the forensic flags, which wait on upstream's T-144/T-074)* Add `:promptHash` to `ScoreSnapshot` (SHACL: only when `agentOrigin` is FUNDAMENTAL)
      and a multi-valued forensic-flag code (from `forensic_flags_json`, once upstream's T-074 fills
      it and documents the codes). Reverses D7's "extras rejected" for these two; `correction_rule`
      stays rejected. **Second reply:** `forensic_flags_json` is an object of four booleans
      (`data_error_suspected`, `negative_equity_buyback`, `value_destroyer_sub_wacc`,
      `severe_sbc_dilution`); emit one `:forensicFlag` per key set to `true` (`sh:in` those four,
      FUNDAMENTAL only) and a `:forensicFlagsEvaluated` boolean (column non-NULL), so "evaluated,
      none fired" (all `false`) differs from "not evaluated" (NULL). Unblocked now: `:availableAt`'s
      comment in `tbox.ttl` gains the cycle lanes (the cycle date, as upstream's view defines it
      from their T-144; never filled in here, so such rows are not projected before then), and
      `:normalizedScore`'s says it is cohort-relative (upstream's 50 + 10·z, clamped, so
      `1 - x/100` is a relative risk reading). → step 3.
- [ ] **T-154** `AssetCoOccurrence`: fill `coOccurrenceComputedOn` from `computed_at` and decide
      whether to make it required; add the `MEDIA` kind and its shape rule when
      `v_media_cooccurrence_edge` exists (after upstream's T-082); do not read `first_seen`/
      `last_seen` until upstream fills them. `computed_at` is written `+00:00`: parse that form and
      `Z`. The `MEDIA` view and the edge dates come after their T-100. → step 3.
- [ ] **T-155** *(schema half done 2026-10-07 in PR #58: the two shape bounds, every comment and doc listed under "Unblocked now"; open: the projection, which waits on T-031, T-121, T-157)* Project `v_cycle_ranking` as `AttractivenessSnapshot`s, keeping only
      `status = 'completed'` and non-REPLAY runs: `attractivenessScore` = `blended_score / 100`
      (second reply: 0-100 points, higher = more attractive, minus 15 per active SOFT veto, so it
      can be negative). Unblocked now: drop `AttractivenessSnapshotShape`'s lower bound and keep
      `maxInclusive 1.0`, and update `:attractivenessScore`'s comment; no pre-penalty score is
      derived here. A `blended_score` is never NULL: an asset with no component gets 0.0, so skip a
      row whose asset has no `v_cycle_ranking_component` row (a placeholder, not a score; the
      skipped rows are counted in Work item 16's boundary report, T-163). **Confirmed, third reply
      (2026-10-06), Q1:** such a row is always `vetoed = 1` with `"UNSCORED"` in `veto_rules_json`
      (D4) — it has no FUNDAMENTAL score, but can still have TECHNICAL/VALORIZATION components;
      there is no dedicated marker beyond the missing component rows, which is the test to keep.
      **Q2:** `rank` excludes nobody — every universe member gets a ranking row, and exclusion from
      `positions` happens downstream of this view. Their T-144 will produce exactly one component
      row per non-null component of every ranking row, whatever `vetoed`/`selected` say, with a
      test asserting it; the only ranking rows without any component row stay the no-component ones
      above. `vetoedAtRanking` is true only for a HARD veto (with the T-1 lag) or the `UNSCORED`
      case — a SOFT veto only lowers `blended_score`, it never sets `vetoed` on its own; a row with
      SOFT penalties and `vetoedAtRanking true` is only valid if it also carries a HARD veto. One
      snapshot per `(cycle_run_id, asset_id)`: like the scheme
      (T-121), its identity relies on upstream's T-145 and T-100, so until both have landed only a
      run passing T-151's checks is projected. Also read rank, selection, target weight (verbatim;
      **confirmed, third reply, Q5:** a fraction of the book, [0, 1], `NULL` for an unselected row
      and on a MONITORING run) and the per-asset effective weights from `v_cycle_ranking_component`
      (`effective_weight` per `score_type`, named as in T-121, summing to 1 per run and asset; no
      row for an absent component). **Reversed, third reply:** `component_value` does *not* repeat
      a `ScoreSnapshot` value for FUNDAMENTAL — upstream measured 33/40 production, 1/60 pilot and
      2,267/2,799 replay ranking rows where the two differ, because FUNDAMENTAL's stored
      `normalized_score` is overwritten by whichever cycle last re-normalized that filing (T-171
      covers the fallout for `ScoreSnapshot`), while `component_value` is the value *that run*
      actually used. Read it verbatim onto each effective-weight `WeightComponent` as
      `:componentValue` (decimal, 0–100, the same cohort-relative scale as `normalized_score`); run
      a cohort-mean check over it per `(cycle_run_id, score_type)`, not over FUNDAMENTAL
      `ScoreSnapshot` rows, which mix cohorts across cycles (Work item 16's T-162, which this scope
      change feeds). `configured_weight` stays declined — upstream keeps it in `v_cycle_ranking_component`
      for their own tests, but it still repeats `v_weight_component` for us, so there is nothing to
      read. Never recompute the
      blend (`SPEC.md` §2.5 item 1), and remove every description of computing it here: `docs/06`
      §1.8's `attractivenessScore = Σ weight_i * component_i` and its `inverted` rule; `rules.ttl`'s
      `WeightScheme_v1` header ("Formula this scheme feeds"); the `attractivenessScore`,
      `WeightComponent` and `:inverted` comments in `tbox.ttl`; and mark the 2026-08-13
      attractiveness design spec in `docs/superpowers/specs/` as design history. `:inverted`'s
      remaining purpose, if any, is decided with T-121. Unblocked now: the `SectorRelativeMomentum`
      `[-1, 1]` bound (T-140), justified only by that formula's `(rawValue + 1) / 2`, becomes
      [-100, 100]: upstream's SECTOR `raw_value` is the asset's TECHNICAL raw score minus its
      sector's mean, in TECHNICAL points (observed -54 to +46), read verbatim, positive = stronger
      than its sector; its 0-100 `normalized_score` becomes an optional `normalizedScore` (T-031
      rescales it). Update every statement of the old bound or of "no `normalizedScore` for SECTOR":
      `shapes.ttl`, `reference.ttl`'s SRM comment, `docs/06` §1.8, `schema/README.md` refinements 2
      and 6 (6 still lists SECTOR as "open, not fixed"), the T-030 rescale paragraph closing
      `SPEC.md` §2.6, and the module docstring of `src/projection/score_scale.py` (done in PR #60;
      the code change itself is T-031's). Leave `schema/protege-view.ttl` to its regeneration (Work item 8); it is generated.
      → step 3.
- [ ] **T-156** Quant: read `v_quant_portfolio` and `v_quant_vs_live` on the engine version upstream
      marks current, with `engine_version` recorded on each `BenchmarkObservation`. Match a
      `v_quant_vs_live` row to its book on `(as_of, kind, engine_version)`, not `(as_of, kind)`:
      with `opt-v1` and `opt-v2` books coexisting, the old key no longer identifies one book; update
      `:benchmarkKind`'s comment in `tbox.ttl`, which names the old key. Keep `live_book` out of
      `Portfolio` (already enforced by `PortfolioShape`); stop expecting `equal_weight`/
      `cap_weight`. `is_current` marks at most one book per `(as_of, kind)`, the newest `opt-v*`;
      `engine_version` stays opaque (`opt-v1+9d34ff69`). → step 3.
- [ ] **T-157** When upstream ships: re-pin `src/projection/view_contract.py` (new view, new
      columns, the commit in its docstring and in `SPEC.md` §2.6), raise the `schema_version` floor
      (D16), and run `cli/check_view_contract.py` against that commit. Repeat for
      `v_media_cooccurrence_edge`. Pin their T-144's `v_cycle_ranking_component` too. Every contract
      change carries a marker migration, so each raises the floor; repeat for their T-145.
      Project only from a database that meets the floor and holds no REPLAY run (no `cycle_run`
      row with `cycle_type = 'REPLAY'`; a backfill's REPLAY scores and vetoes land in the shared
      tables, D8). This task sets the rule; the check is one of T-162's expectations, run by T-163
      at the start of each projection. Production (at 8) fails the floor; the pilot (at 9) and
      their T-100 rebuild qualify if the check passes.
      → step 4.
- [ ] **T-158** Replace the `ASSET_DAY_AGGREGATE` placeholder with upstream's SEMANTIC
      `score_method` value once they give it (D14; with their Work item 4, after their T-100).
      **First, raise the ownership disagreement (unblocked now; ask before their T-141 ships its
      doc fix):** upstream's second reply says the future SEMANTIC
      writer is this repo (per their `docs/semantic-score-boundary.md`), against `SPEC.md` §13 item
      11 (`portfolio-nlp` computes, `financial-analysis` materializes, this repo stops writing).
      Ask them to confirm which reading their T-141 doc fix will state, and record the answer in D14
      before the method value is adopted. → step 4.
- [ ] **T-159** Verify: FR-001 parse + `pyshacl` pass after T-151–T-156, T-171, with
      `schema/README.md`, `docs/06` and `docs/07` counts in sync (NR-001), `docs/07`'s named-graph
      table listing every new class, and no doc left describing the blend as computed here (T-155);
      every upstream change this work item reads is recorded in `SPEC.md` §2.6 with its commit. →
      `PLAN.md` acceptance criteria.
- [x] **T-170** *(third reply, 2026-10-06, checked against their `597832a`, production, the pilot
      and its replay copy; our ask was `kg_handoff_second_followup.md`, PR #54, T-150's own
      follow-up)* Record the reply in `SPEC.md` §2.6: new row D17 (FUNDAMENTAL's `normalized_score`
      is rewritten in place every cycle, not immutable at the source); the `component_value`
      correction and Q1/Q2/Q5 folded into D13's disposition; Q3 (SECTOR confirmed) into D6's; Q4
      (accession numbers) into D16's; and their T-144/T-145 scope additions (keep `component_value`
      and `configured_weight`; a Q2 test; `docs/kg_schema.md`; an accession-number uniqueness
      check). → `PLAN.md` Work item 15, step 1.
- [x] **T-171** *(D17, raised by the third reply; done in PR #56: the `sh:or` change, comments, docs, `score_scale.py` and its tests; FUNDAMENTAL `rawValue`'s bounds stay open as Q6, asked with T-150's next follow-up)* Decide how `ScoreSnapshot` keeps its
      immutable-observation principle (constitution; `docs/06` conventions) now that upstream
      rewrites a FUNDAMENTAL row's `normalized_score` in place on every cycle that re-normalizes
      its filing against that cycle's cohort (measured: 33/40 production, 1/60 pilot, 2,267/2,799
      replay ranking rows whose component differs from the stored snapshot value). **Decided:**
      drop `normalizedScore` from FUNDAMENTAL `ScoreSnapshot`s going forward rather than add an
      exception to the audit-trail principle. Widen `ScoreSnapshotShape`'s `sh:or` (T-080/T-081)
      so `ScoreFinanciero` joins `SectorRelativeMomentum`/`Sentiment` as a metric that does not
      require `normalizedScore` — optional, not forbidden, so the FUNDAMENTAL individuals already
      in `instances.trig` and the closed design-history rules that compare on it
      (`VETO_FIN_01`, `VETO_COMP_01`/`02`, `VETO_RED_01`) still conform. The per-cycle,
      cohort-relative FUNDAMENTAL value is not lost: it now lives correctly scoped to one
      `cycle_run` as `:componentValue` on `AttractivenessSnapshot`'s effective-weight
      `WeightComponent` (T-155), rather than as a property of a filing-keyed individual that no
      single cycle owns. FUNDAMENTAL's `rawValue` — stable at the source, per the third reply — is
      the value to carry on the snapshot instead, and a paired `sh:or` makes it mandatory
      (`minCount 1`, no bounds yet) the same way the shape already pairs `SectorRelativeMomentum`'s
      and `Sentiment`'s exemptions with a mandatory `rawValue` — otherwise a FUNDAMENTAL snapshot
      could conform while carrying neither value (PR #56 review). Its bounds are unknown, so ask
      upstream (new question, Q6, with T-150's next follow-up) before adding a
      `minInclusive`/`maxInclusive` pair, matching how SECTOR's `rawValue` range wasn't bounded
      until confirmed (T-140/T-155). Update `:normalizedScore`'s and `:rawValue`'s `tbox.ttl`
      comments and `schema/README.md` (flagged as a design gap found against real data, per
      CLAUDE.md's convention for the three earlier ones). Also `docs/06-ontology-definition.md`'s
      `ScoreSnapshotShape` table row and §1.8's exemption-history paragraph (PR #56 review):
      T-081 and T-140, the two prior amendments to this shape, each updated both inline when they
      landed, so this one does too rather than waiting on T-159's later sync pass. And the code
      and contract that implemented the old reading (PR #56 review): FUNDAMENTAL comes out of
      `RESCALED_SCORE_TYPES` in `src/projection/score_scale.py`, so `to_normalized_score` rejects
      the lane instead of converting a value upstream mutates (SHACL cannot enforce this: the shape
      keeps FUNDAMENTAL `normalizedScore` optional for legacy data, so the projector is the only
      place it holds); `SPEC.md` §2.6's T-030 rescale paragraph and `schema/README.md` refinement 6
      stop listing FUNDAMENTAL as rescaled. → step 3.

## Work item 16 — Validate upstream rows at the read boundary

*Input-side validation of the `v_*` rows, before any triple is built. `pyshacl` stays the graph gate.
See `PLAN.md` Work item 16.*

- [x] **T-160** *(done 2026-10-07: plain checks, no library; row-level failures quarantine the row and its group (ranking + components, scheme + components + that run's rankings), late in an ingestion-dated graph (re-read by the next run) and lost in any other, each row counted against its own view's per-view cap (default 0); source and aggregate failures stop the run; nine check kinds, a per-lane D2 look-ahead check; recorded in `SPEC.md` §13 item 10; the text below is the original task, kept for the record)* Decide the failure policy (stop the run, or quarantine failing rows and report them)
      and the validation tool, from the list of checks needed (types, NULL rate, range, natural-key
      uniqueness, `available_at` against `event_time`, row count per view, and the source check of
      T-157). A check with no offending row (row count, NULL rate, cohort mean) is reported against
      its view or group and stops the run under either policy, so its thresholds encode upstream's
      documented state: a column NULL for every row by design (SEMANTIC today;
      `first_seen`/`last_seen` on `v_shared_executive_edge` until their Work item 9) is expected,
      not a failure. Rows skipped by design (T-031, T-151, T-155) are counted, not failed. Compare
      plain checks, pandera, deepchecks and Great Expectations on that list, including dependency
      weight. Record the decision in `SPEC.md` §13 item 10. → `PLAN.md` Work item 16, step 1.
- [x] **T-161** *(closed with T-160: plain checks won, so no dependency and no amendment)* If T-160 picked a library: propose the constitution amendment first (Technological
      stock #6, Governance steps 1–4, MINOR bump), as its own reviewed change, then add the dependency
      to `pyproject.toml`. If plain checks won, there is no dependency and no amendment. → step 2.
- [x] **T-162** *(done: one JSON file per view under `src/projection/view_expectations/`, plus `_source.json`, and the strict loader `src/projection/expectations.py`; `tests/test_expectations.py`. Every cap is 0. The tolerance (5), the row-count minimums and the key and range columns not stated upstream are first picks, to be checked against a real database when T-163 lands. `forensic_flags_json` and `v_cycle_ranking_component` are marked `pending` until upstream's re-pin. SEMANTIC's all-NULL columns are not encoded yet: T-158 does that. FUNDAMENTAL's cohort-mean guard sits on the pending `v_cycle_ranking_component`, so it is inactive until upstream's T-144 ships that view. The `v_score_snapshot` mean groups by `run_kind` too, since run ids repeat across the four run tables, D7.)* Write the expectations for the views Work item 4 reads, as JSON files beside
      `src/projection/view_contract.py`, one per view. Include each view's quarantine cap (default 0;
      record why for any view allowed to lose rows) and the check kinds T-160 lists (`PLAN.md` Work
      item 16), the format and per-lane look-ahead checks included. Include the `v_score_snapshot`
      `normalized_score` range and the cohort mean near 50, with a tolerance, not equality
      (upstream's winsorization and clamp shift it slightly, third reply, Q3) for VALORIZATION,
      TECHNICAL and SECTOR, whose `normalized_score` T-031 rescales (upstream documents
      50 + 10·z, clamped). **Confirmed, third reply, Q3:** SECTOR uses the same function over the
      cycle's SECTOR raw values (a cross-sectional z with 2% winsorization), so its guard is
      unblocked, no longer waiting on confirmation. **FUNDAMENTAL is excluded from this
      `ScoreSnapshot`-row check** (third reply, with T-171): its stored `normalized_score` is
      rewritten by whichever cycle last touched the filing, so a `ScoreSnapshot` row mixes
      cohorts and would fail the mean check for reasons that have nothing to do with bad data. Its
      cohort-mean guard runs instead over `v_cycle_ranking_component.component_value`, grouped by
      `(cycle_run_id, score_type)` — one cohort per group, correctly scoped (SEMANTIC is not on
      0-100, so it carries neither check). The guard against a change of meaning that stays in
      range (it cannot detect a reversed polarity); this task owns that guard. From upstream's
      second reply also: SECTOR `raw_value` in
      [-100, 100]; `blended_score` at most 100, no lower bound; `available_at` NULL on cycle lanes
      until their T-144, then never NULL; `computed_at` in `+00:00` or `Z` form;
      `forensic_flags_json` NULL or an object of the four documented keys. T-031 only calls these
      checks. The run-identity checks are not here: T-151 owns them (a reused `run_id` is allowed; a
      failure omits `:runId` and keeps the row, except for the run-keyed views T-151 lists, whose
      rows are skipped and counted in the report). Also here, as an aggregate check that stops the
      run: the source database meets the `schema_version` floor and holds no `cycle_run` with
      `cycle_type = 'REPLAY'` (T-157's rule; a backfill's REPLAY rows land in the shared tables,
      D8); T-163 runs it first. Update an all-NULL-by-design expectation when upstream fills the
      column (T-154 for the edge dates, T-158 for SEMANTIC). → step 2.
- [ ] **T-163** *(function done in PR #68: `src/projection/boundary.py` (`check_source`, `validate`, `BoundaryReport`) and `tests/test_boundary.py`; rows of a cycle lane with a NULL `available_at` are counted, and `BoundaryReport.skip` lets the caller count the rest. Open: calling it on the real read and re-reading the persisted late keys (T-031), and counting T-155's no-component ranking rows and T-151's run-keyed rows through `skip` (with T-031 and T-151). Until a caller passes `late_keys_path`, every quarantined row is reported lost. `validate` only adds keys to that file (written atomically, with each view's key columns; keys under old columns are dropped and reported); T-031 drops a key with `mark_written` once its row is written, merges each re-read row into its read by natural key (appending it would duplicate the key and stop the run), and reports the keys its re-read did not find. First picks, to check against a real view: the cascade links of `v_cycle_ranking_component` assume `cycle_run_id` and `asset_id`; an ordered pair parses ISO values, a bare date as midnight UTC. The missing-column check covers only the columns an expectation names, so T-031 can trim the pin.)* Run the expectations on the read path: a function that returns the validated rows
      and a report naming the view and column of every failure, with the row key for a row-level
      check and the group for an aggregate one, applying the T-160 policy. It runs T-162's source
      check first and stops on its failure. It skips a `pending` view or column (one upstream has
      not shipped, so it cannot be read) and lists each one in the report, so an inactive guard is
      visible. The report also counts, per view and reason, the rows skipped by design: T-031's
      cycle-lane rows with a NULL `available_at`, T-155's no-component ranking rows, and T-151's
      run-keyed rows whose run fails the checks. It lists each quarantined row as late
      (ingestion-dated graph) or lost (any other graph), per `PLAN.md` Work item 16, and persists
      the late rows' keys for the next run to re-read. Lands with T-031.
      → step 3.
- [x] **T-164** Tests with synthetic rows: one passing and one failing case per check kind, and the
      behaviour of the policy T-160 selected: an aggregate failure, a quarantine under the cap, a stop
      above it (the default cap of 0 included), and the group cascade (a failing component takes its
      ranking row; a failing scheme takes its components and that run's rankings; each cascaded row
      counted against its own view's cap; a late row's key persisted by one run and re-read, then
      dropped once written, by the next), under Work item 13's
      structure (T-131, landed in PR #56). → step 4.
      Done: `tests/test_boundary.py` holds a parametrized passing and failing case for each of the nine
      check kinds (T-163's tests already cover the policy, cascade and late keys), plus the forensic-flags
      format. The task stays checked only for the runner as it stands; T-031 adds the wiring tests.
- [ ] **T-165** Verify and document: `SPEC.md` §13 item 10 (today the pin and the drift check) gains
      what is checked at the boundary and what is not, including that polarity is not detectable;
      `uv run pytest` passes; the FR-001 gate is unchanged. → `PLAN.md` acceptance criteria.

## Status

Closed Work items 1, 2, 3, 5, 7 (superseded/decided by T-007), 9, 10 and 11 are in
`CHANGELOG.md` (Work item 1 closed with T-006 deprecated in favor of T-009).
Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order (Work items 3 and 11 are closed, so Work item 4 is unblocked).
Work item 12 (T-120–T-121): T-120 closed by T-150; T-121 done (PR #65).
Work item 13 (T-130–T-136): constitution rules in place (1.5.0); T-130–T-134 and T-136 done (PR #64); T-135 is an open decision.
Work item 14 (T-140–T-142 and T-146): T-140 and T-142 done; T-141 needs a live GraphDB; T-146 found by T-136's tests.
Work item 15 (T-150–T-159, T-170–T-171): T-150, T-170 and T-171 (PR #56) done; T-155's schema half done (PR #58); T-153's comment half (PR #59);
T-151's rule recorded (PR #60), its checks waiting on T-031/T-163; T-158's
ownership question (before their T-141) is unblocked; the rest of T-152–T-158 waits on upstream's
T-144 (views), T-145 (ids), T-074 (flags) and, after their T-100, their T-082 and their Work item 4.
Work item 16 (T-160–T-165): T-160 done (plain checks, quarantine-with-cap), T-161 closed with it (no dependency) and T-162 done (JSON files per view, strict loader);
T-163 lands with T-031; T-164's prerequisite, Work item 13's skeleton (T-131), has landed (PR #56).
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
