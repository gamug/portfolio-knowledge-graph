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
      columns read; decide the `:rawValue` range for FUNDAMENTAL/VALORIZATION/TECHNICAL, and map
      upstream SEMANTIC into the `[-1, 1]` `rawValue` `ScoreSnapshotShape` requires of it (T-081;
      `SPEC.md` §2.6). SECTOR's `raw_value` is read verbatim into the [-100, 100] bound T-155 sets,
      and its 0-100 `normalized_score` is rescaled like the other lanes (add SECTOR to
      `RESCALED_SCORE_TYPES` in `src/projection/score_scale.py`, and rewrite its module docstring,
      which still says SECTOR carries no `normalizedScore` and a [-1, 1] `rawValue`). Skip a
      cycle-lane row with a NULL `available_at` (every such row before upstream's T-144) and count it
      in Work item 16's boundary report (T-163), so no row is dropped silently; never fill it in. Parse
      `computed_at` with `+00:00` or `Z`. And guard
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
- [ ] **T-121** *(moved from T-109(ii); D13)* Extend the weight-scheme model to what upstream records per run: one `AttractivenessWeightScheme` per `cycle_run` (`schemeId` = `cycle_run:<id>`, `validFrom` = `cycle_date`, no `validTo`), a component per `score_type` (`weightMetricName` = that lane's `metricType` name, the fixed mapping `ScoreSnapshotShape` already pairs with `agentOrigin`: FUNDAMENTAL → `ScoreFinanciero`, VALORIZATION → `ScoreCuantitativo`, TECHNICAL → `ScoreTecnico`, SEMANTIC → `Sentiment`), upstream's `scheme_id` on a new book-weighting-rule property, and the scalar knobs (`top_n`, `max_name_weight`, `max_sector_weight`, `soft_veto_penalty`) as new properties, read verbatim (the two weight caps are assumed a fraction of the book until upstream states their unit, as asked with T-155's `target_weight`); `:inverted` becomes optional (below), and `SectorRelativeMomentum`, which upstream does not weight, gets no component. The scheme's identity is a `cycle_run` id, so it relies on upstream's T-145 (ids never reused) and T-100: until both their T-145 and their T-100 rebuild have landed (T-145 stops new reuse; the rebuild drops ids already reused, as T-151 says), project a scheme only for a run that passes T-151's checks (a scheme whose run fails them is not projected, nor are the snapshots computed with it). **Upstream reply (2026-10-05):** `score_weights` holds the *configured* weights for all four types in every run, not the blended ones; the blend renormalizes per asset over its non-null components, so the effective weights are per asset, not per scheme. Model the scheme as configured, and read the effective weights from upstream (T-155), never derive them here. **Second reply (2026-10-06):** why the identity is the run: `scheme_id` is the rule that turns the ranking into book weights (`score_proportional`, `score_tilt`), not the blend, and a blend is identified by its `cycle_run`. New runs (their T-141) record three components at 1/3 (no SEMANTIC), older runs four (0.4/0.3/0.2/0.1); both are per-run schemes. `:inverted` has no upstream counterpart (D13 item 4): make it optional, emit it for no upstream scheme, and keep it on `WeightScheme_v1` (design history). **Decide first:** a per-run scheme with `validFrom` and no `validTo` reads as "still active" for every run (the valid-time convention), so either close the previous run's scheme with `validTo` when the next run is projected, or stop treating a per-run scheme as a valid-time record (a run-date property linked to the run, and relax `validFrom` `minCount 1` in `AttractivenessWeightSchemeShape`). Update `tbox.ttl`, `shapes.ttl`, `rules.ttl`'s `WeightScheme_v1`, docs 06/07 and `schema/README.md` counts. → step 6.

## Work item 13 — A `pytest` suite for the code this repo owns

*Constitution 1.5.0 sets the rules these tasks follow (Project structure #10, Code & Git #9); `SPEC.md`
NR-005 still says there is no suite until T-134. T-132–T-134 and T-136 are independent of each other
once T-131 lands.*

- [ ] **T-130** Amend `constitution.md` (MINOR bump, Governance steps 1–4) with the test structure
      proposed in `PLAN.md` Work item 13 (`tests/`, flat `test_<module>.py`, `conftest.py`, hermetic,
      `integration` marker skipped by default, `uv run pytest`); add the command to §Executable cmds;
      reverse NR-005, `SPEC.md` §10, §13 item 7 and §14. Its own reviewed change. → Approach 1.
      *(Constitution 1.5.0 done: Project structure #10, Code & Git #9, `uv run pytest`. Still open:
      the `SPEC.md` reversals, which wait until the suite exists, so close this task with T-134.)*
- [ ] **T-131** Add `pytest` to the `dev` group and the `tests/` skeleton per constitution #10:
      `[tool.pytest.ini_options]` with `pythonpath = ["src"]`, `testpaths = ["tests"]`, the
      `integration` marker and `addopts = "-m 'not integration'"`; `tests` added to
      `.code_quality/mypy.ini`'s `files`; a `conftest.py` for shared fixtures only (no `sys.path`
      edits). → Approach 2.
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
- [ ] **T-136** Tests for `src/kg_store/` and the `cli/` exit codes, hermetic (a fake `GraphDB`, no
      running store): `load_schema.expected_sizes`/`load`/`verify` (load order, named graphs, size
      mismatch); the ingest gate's `check_target`, `parse_batch`, `unknown_types`,
      `untyped_writes` and `validate` (a conforming batch passes, a non-conforming one raises);
      `acceptance.check_gate`'s violation count (whatever T-142 makes it count);
      `load_schema.main(argv)` called directly; `cli/check_view_contract.py` run as a subprocess
      (constitution #10) against a synthetic upstream in `tmp_path`, exiting 1 on drift and 0
      otherwise. `cli/load_schema.py`, `verify_store.py` and `ingest.py` need a live store: their
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
- [ ] **T-142** Have `kg_store.gate.validate` expose pyshacl's results graph and make
      `acceptance.check_gate` count `sh:ValidationResult` nodes instead of matching
      `"Constraint Violation in"` in the text report. → step 3.

## Work item 15 — Adopt upstream's `v_*` contract changes (replies of 2026-10-05 and 2026-10-06)

*Upstream's reply to the gaps in `SPEC.md` §2.6 (checked against their `0a528be`), and their second
reply (`597832a`), which accepts our asks as their T-144 and T-145 and corrects six assumptions
(`PLAN.md` Work item 15, step 3 lists the decisions). T-150, T-151's rule, T-155's removal of the
blend formula and the shape corrections in T-153 and T-155 need nothing; the rest of T-152–T-158
waits on the upstream change it reads. Feeds Work item 4 (T-031) and Work item 12 (T-121).*

- [x] **T-150** Record the reply in `SPEC.md` §2.6: rows and dispositions D8 (REPLAY never reaches
      production, so no replay flag is needed; `v_cycle_ranking` gains `status`; "production DB
      only", in the row and its disposition, becomes "a database at the floor with no REPLAY run",
      T-157's check), D9 (the trigger
      decision; also `docs/10`, which closes T-120), D10 (`computed_at`/`run_id` coming;
      `first_seen`/`last_seen` NULL until their Work item 9; `v_media_cooccurrence_edge` with their
      T-082), D11 (`live_book`, dead kind names and `LIVE_ONLY` confirmed; `opt-v1`/`opt-v2` books
      coexist), D12 (`v_fundamental_metric` coming, market cap as its `market_capitalization`
      metric; moves from "rejected for now"), D13 (configured vs effective weights), D14 (still
      unanswered), D16 (`metrics-v5`, `opt-v2`, filings keyed by period end), and the run-id reuse
      fact. List what was declined (PLAN Work item 15). Also record the second reply: the six
      corrections (D6 SECTOR range, D13 `blended_score` and `scheme_id`, D2 `available_at` on cycle
      lanes, D12 `metric_id`/`unit`, D11/D12 `is_current` as at most one), the forensic-flag
      format, `+00:00` timestamps, id reuse on all four run tables and `sec_filings` (D7),
      production at `schema_version` 8 (D16), cohort-relative `normalized_score`, their weights
      change (D13: 1/3 each for new runs, SEMANTIC out of the blend), and the upstream task each ask
      maps to (their T-144, T-145, T-074 and T-141, their Work item 2, and after their T-100).
      → `PLAN.md` Work item 15, step 1.
- [ ] **T-151** Decide when `:runId` may be emitted now that upstream can reuse a `cycle_run.id`
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
      same read. → step 3.
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
- [ ] **T-153** Add `:promptHash` to `ScoreSnapshot` (SHACL: only when `agentOrigin` is FUNDAMENTAL)
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
- [ ] **T-155** Project `v_cycle_ranking` as `AttractivenessSnapshot`s, keeping only
      `status = 'completed'` and non-REPLAY runs: `attractivenessScore` = `blended_score / 100`
      (second reply: 0-100 points, higher = more attractive, minus 15 per active SOFT veto, so it
      can be negative). Unblocked now: drop `AttractivenessSnapshotShape`'s lower bound and keep
      `maxInclusive 1.0`, and update `:attractivenessScore`'s comment; no pre-penalty score is
      derived here. A `blended_score` is never NULL: an asset with no component gets 0.0, so skip a
      row whose asset has no `v_cycle_ranking_component` row (a placeholder, not a score; confirm
      with upstream how such an asset appears otherwise; the skipped rows are counted in Work item
      16's boundary report, T-163). One snapshot per `(cycle_run_id, asset_id)`: like the scheme
      (T-121), its identity relies on upstream's T-145 and T-100, so until both have landed only a
      run passing T-151's checks is projected. Also read rank, selection, target weight (verbatim;
      assumed a fraction of the book until upstream states its unit, which the answer to the second
      reply asks) and the per-asset effective weights from `v_cycle_ranking_component`
      (`effective_weight` per `score_type`, named as in T-121, summing to 1 per run and asset; no
      row for an absent component), and not its `component_value`, which repeats a `ScoreSnapshot`,
      nor its `configured_weight`, which repeats `v_weight_component` (T-121). Never recompute the
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
      `SPEC.md` §2.6, and the module docstring of `src/projection/score_scale.py` (with T-031's code
      change). Leave `schema/protege-view.ttl` to its regeneration (Work item 8); it is generated.
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
      **First, raise the ownership disagreement:** upstream's second reply says the future SEMANTIC
      writer is this repo (per their `docs/semantic-score-boundary.md`), against `SPEC.md` §13 item
      11 (`portfolio-nlp` computes, `financial-analysis` materializes, this repo stops writing).
      Ask them to confirm which reading their T-141 doc fix will state, and record the answer in D14
      before the method value is adopted. → step 4.
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
      uniqueness, `available_at` against `event_time`, row count per view, and the source check of
      T-157). A check with no offending row (row count, NULL rate, cohort mean) is reported against
      its view or group and stops the run under either policy, so its thresholds encode upstream's
      documented state: a column NULL for every row by design (SEMANTIC today;
      `first_seen`/`last_seen` on `v_shared_executive_edge` until their Work item 9) is expected,
      not a failure. Rows skipped by design (T-031, T-151, T-155) are counted, not failed. Compare
      plain checks, pandera, deepchecks and Great Expectations on that list, including dependency
      weight. Record the decision in `SPEC.md` §13 item 10. → `PLAN.md` Work item 16, step 1.
- [ ] **T-161** If T-160 picked a library: propose the constitution amendment first (Technological
      stock #6, Governance steps 1–4, MINOR bump), as its own reviewed change, then add the dependency
      to `pyproject.toml`. If plain checks won, there is no dependency and no amendment. → step 2.
- [ ] **T-162** Write the expectations for the views Work item 4 reads, beside
      `src/projection/view_contract.py`, keyed by view name. Include the `v_score_snapshot`
      `normalized_score` range and the cohort mean near 50 per rescaled lane (FUNDAMENTAL,
      VALORIZATION, TECHNICAL and SECTOR, whose `normalized_score` T-031 now rescales; upstream
      documents 50 + 10·z, clamped, for `normalized_score` in general; for SECTOR this is assumed
      until upstream confirms it, so its guard ships only after that; SEMANTIC is not on 0-100), the
      guard against a change of meaning that stays in range (it cannot detect a reversed polarity);
      this task owns that guard. From upstream's second reply also: SECTOR `raw_value` in
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
- [ ] **T-163** Run the expectations on the read path: a function that returns the validated rows
      and a report naming the view and column of every failure, with the row key for a row-level
      check and the group for an aggregate one, applying the T-160 policy. It runs T-162's source
      check first and stops on its failure. The report also counts, per view and reason, the rows
      skipped by design: T-031's cycle-lane rows with a NULL `available_at`, T-155's no-component
      ranking rows, and T-151's run-keyed rows whose run fails the checks. Lands with T-031.
      → step 3.
- [ ] **T-164** Tests with synthetic frames: one passing and one failing case per check kind, and the
      behaviour of the policy T-160 selected (including an aggregate failure), under Work item 13's
      structure (needs T-131). → step 4.
- [ ] **T-165** Verify and document: `SPEC.md` §13 item 10 (today the pin and the drift check) gains
      what is checked at the boundary and what is not, including that polarity is not detectable;
      `uv run pytest` passes; the FR-001 gate is unchanged. → `PLAN.md` acceptance criteria.

## Status

Closed Work items 1, 2, 3, 5, 7 (superseded/decided by T-007), 9, 10 and 11 are in
`CHANGELOG.md` (Work item 1 closed with T-006 deprecated in favor of T-009).
Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order (Work items 3 and 11 are closed, so Work item 4 is unblocked).
Work item 12 (T-120–T-121): T-120 closed by T-150; T-121 is unblocked.
Work item 13 (T-130–T-136): constitution rules in place (1.5.0); T-131 next, then T-132–T-134 and T-136; T-130 closes with T-134.
Work item 14 (T-140–T-142): T-140 done; T-141 needs a live GraphDB; T-142 is unblocked.
Work item 15 (T-150–T-159): T-150 done; T-151's rule, T-155's formula removal and the shape corrections
in T-153/T-155 are unblocked; the rest of T-152–T-158 waits on upstream's T-144 (views), T-145 (ids),
T-074 (flags) and, after their T-100, their T-082 and their Work item 4.
Work item 16 (T-160–T-165): T-160 first (policy and tool); T-163 lands with T-031; T-164 needs Work item 13's skeleton.
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
