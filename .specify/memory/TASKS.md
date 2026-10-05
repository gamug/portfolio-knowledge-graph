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
loader (T-021) and the ingest gate (T-023); also blocked on Work item 11's
decisions (T-100–T-104).*

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
      (FR-004) with `universe.db` as-of reads (`SQL_UNIVERSE_DB`, read-only via
      `portfolio_common.db`), emitting `:Asset` + `:UniverseMembership`
      (`validFrom`/`validTo`); document the stale-between-snapshots risk and
      that `universe.db` is now a direct upstream. → `PLAN.md` Work item 11,
      step 1.
- [x] **T-101** *(D2; done 2026-10-03: `availableAt` required + `eventTime` optional on `ScoreSnapshot`)* Decide how `available_at` vs. `event_time` is modelled
      (new properties, or encoded in the ingest-graph date) so as-of queries
      cannot leak look-ahead; update `tbox.ttl`/`shapes.ttl` and `07`. → step 2.
- [x] **T-102** *(D3; done 2026-10-03: `raisedOn`/`clearedOn`/`lastSeenOn` + `vetoSeverity`, `VetoShape`)* Model veto stints (`raisedOn`/`clearedOn`/`lastSeenOn`
      or `validFrom`/`validTo`) and write the "active at cutoff C" predicate
      as the T-1-lag SPARQL pattern. → step 3.
- [x] **T-103** *(D4 — decided 2026-10-02: upstream's catalog is final; done 2026-10-03)*
      Implement it: add upstream's six rules (`LEVERAGE_EXTREME`, `NEGATIVE_FCF`,
      `LIQUIDITY_DISTRESS`, `PRICE_CRASH`, `EARNINGS_MISSING`,
      `DATA_QUALITY`) as `RuleDefinition`s (single-leaf `RuleClause`s) so
      `:appliesRule` resolves, supersede `rules.ttl`'s seven tree rules
      (including `VETO_RED_01`), and update FR-003, `06`/`07`, `schema/README.md`
      and the FR-001 counts. → step 3.
- [x] **T-104** *(D5; done 2026-10-03: modelled as an `EvidenceSource` leaf, `DataQualityIssueShape`)* Decide `:DataQualityIssue` (evidence for the
      `DATA_QUALITY` veto) vs. dropping it. → step 3.
- [x] **T-105** *(D6; done 2026-10-03: `agentOrigin` `VALORIZATION`, graph/gate renamed; metric id `ScoreCuantitativo` kept; rename dropped 2026-10-05 (T-109): upstream has no metric id for a score beyond `score_type`, which is `agentOrigin`)* `agentOrigin` `QUANTITATIVE` → `VALORIZATION` in
      `shapes.ttl`/`reference.ttl` (MetricType) and docs; document each score
      type's `event_time` meaning and the extra provenance fields. → step 4.
- [x] **T-106** *(D7; done 2026-10-03: optional `runId`/`runAsOf`/`codeVersion`/`engineVersion` (no domain; SHACL on 5 classes, 6 since T-107), no `Run` class; extras not projected)* Decide how upstream `run_id`/`as_of`/`code_version`/
      `engine_version` map onto `provenanceId` (or a `Run` class), and record a
      disposition for the per-score-type extras `forensic_flags_json`,
      `prompt_hash` (FUNDAMENTAL) and `correction_rule` (`financial_facts`)
      handed over by T-105. → step 4.
- [x] **T-107** *(D10; done 2026-10-03: `AssetCoOccurrence` + `AssetCoOccurrenceShape`)* Give projected `sharedExecutiveWith` a
      method/weight/confidence (or a separate candidate property) so news
      co-occurrence is not asserted as fact; decide `media_cooccurrence`. →
      step 5.
- [x] **T-108** *(D9 decided 2026-10-02; D11 decided and (b) done 2026-10-03; (a) moved to T-120, done 2026-10-05)*
      (a) ~~Who triggers the quarterly/daily cycles~~ — **`portfolio-app`**
      (not yet created) calls the upstream endpoints; raise with upstream that
      `api/` is read-only with no run-trigger endpoint and that their docs name
      `portfolio-reports` as the trigger. (b) **Done 2026-10-03:** only finished numbers
      upstream exposes through a `v_*` view become individuals: benchmark
      books/positions/performance and `v_quant_vs_live` active weight
      (`Portfolio.portfolioKind`, `BenchmarkObservation`, graph
      `urn:graph:derived:quant:{date}`); never returns, μ, Σ, frontier
      points — NR-003. (a)'s trigger/integration questions are now tracked by T-120. → steps 5–6.
- [x] **T-109** *(D8, D12, D13, D15, D16; read from upstream `8da3868`, 2026-10-02; done 2026-10-05; D13's schema work moved to T-121, the outward note is `missing_views.md`)*
      Resolved by reading `kg_schema` upstream (incl. T-105's deferred question: no upstream metric id exists to rename `ScoreCuantitativo` to, so it stays): **`schema_version` floor is 9** (migrations 1–9; the projector must refuse a DB below it. No projector exists yet, and `src/etl/` does not read upstream's `v_*` views (it reads `urls.db`/`nlp.db`), so the check belongs to the future `v_*` projector, not `src/etl/`). **`v_cycle_ranking`**: SQL returns every `cycle_run`'s rows, docstring ("latest cycle per cycle_type") is wrong, so per-date ranking graphs must filter by `cycle_run_id`/`cycle_date`. **`run_id` is an integer** (`INTEGER` column, `v_*_run.run_id`), replacing T-106's placeholders. **`v_score_snapshot`** exposes neither `forensic_flags_json` nor `prompt_hash`; no view carries `financial_facts`/`correction_rule`/`fundamental_metrics`/market cap (D12 stays outcome-only). **`REPLAY`**: `cycle_type` marks it in `v_cycle_run`/`v_cycle_ranking`, but its scores/vetoes land in shared tables, so project against a production DB only. **T-108's**: columns, `quantMetric` names, `benchmarkObjective` = `v_quant_portfolio.objective` (`min_var`, `tangency`, `target_vol`, `risk_parity`), `quantAsOf` = `as_of` / performance `date`, values are fractions, with `quantUnit` `fraction` / `fraction_annual` (`expected_*`) / `fraction_daily` (`realized_return`, `active_return`, …) / `ratio` (`sharpe`) / `count`, only `quant_position` weights scaled ×100 into `weightPct` (done in `tbox.ttl`/`instances.trig`). **`live_book` decision (maintainer, option B, 2026-10-05):** `v_quant_portfolio` also holds `kind='live_book'` (a snapshot of the live book, `objective='live'`); it is not projected as a `Portfolio`, and its performance numbers attach to the LIVE `Portfolio` (`quantPortfolio` accepts LIVE or BENCHMARK; `QuantSubjectShape`). `equal_weight`/`cap_weight` (excluded by `v_quant_vs_live`; no writer seen in `quant/`) would be BENCHMARK with `benchmarkKind` recorded. `quantUnit` vocabulary: fraction/fraction_annual/fraction_daily/ratio/count; `quantBenchmark` keeps the reference index; `kind='LIVE_ONLY'` rows have NULL `benchmark_weight`.
      Closed 2026-10-05: (i) T-107's follow-up (answered: `v_shared_executive_edge` has `first_seen`/`last_seen` but no computed-at column, and `media_cooccurrence` has no view): `computedOn` stays optional and no `MEDIA` kind is added until a view exists (`MEDIA` = the proposed second kind of co-occurrence edge, non-executive, for `media_cooccurrence`); (ii) D13's weight-scheme mapping checked against `v_weight_scheme`/`v_weight_component` (findings in SPEC D13; the schema changes it implies are T-121); (iii) the outward findings are written up in `missing_views.md` (repository root, untracked on purpose, to share with the upstream maintainer). → step 6.
- [x] **T-110** *(D16)* Reconcile the `portfolio-common` pin (`v1.2.0` here and
      in `portfolio-nlp`; `v1.2.1` in `financial-analysis` and
      `portfolio-data-mining`) — verify compatibility, then re-pin or record
      why not. → step 6. **Done 2026-10-05:** re-pinned to `v1.2.1`; the diff
      v1.2.0→v1.2.1 is additive (`Dialect.upsert` options, `json_extract`/
      `json_each`, `Database.relation_exists`/`schema_version`, `DatabaseError`)
      and `news_export` is untouched; `uv sync` OK, imports of `Row`/
      `connect_readonly`/`fetch_processed_articles` OK. Only `portfolio-nlp`
      stays on `v1.2.0` (upstream's call).
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

## Work item 12 — Integrate `portfolio-app`/`portfolio-reports` and model per-run weight schemes

*Pending parts of Work item 11's T-108 and T-109. Independent of each other; T-121 follows the
D13 check recorded in `SPEC.md` §2.6, T-120 needs an answer from the upstream maintainer
(`missing_views.md`, section 4).*

- [ ] **T-120** *(moved from T-108(a); D9)* `portfolio-app` and `portfolio-reports` integration. Upstream's `api/` is read-only with no run-trigger endpoint, and its docs name `portfolio-reports` as the trigger, while this repo's SPEC names `portfolio-app` (not yet created). Agree with upstream who triggers `cycle select`/`cycle monitor`, and what `portfolio-app` and `portfolio-reports` each read: `portfolio-reports` reads the run-log `v_*` views (`v_*_run`), `portfolio-app` should read this repo's query surface. Record the outcome in SPEC D9 and `docs/10`. Open question raised in `missing_views.md`. → steps 5–6.
- [ ] **T-121** *(moved from T-109(ii); D13)* Extend the weight-scheme model to what upstream records per run: one `AttractivenessWeightScheme` per `cycle_run` (`schemeId` = `scheme_id`, `validFrom` = `cycle_date`, no `validTo`), a component per `score_type` (`weightMetricName` ← `agentOrigin`: FUNDAMENTAL, VALORIZATION, TECHNICAL, SEMANTIC), and the scalar knobs (`top_n`, `max_name_weight`, `max_sector_weight`, `soft_veto_penalty`) as new properties; decide what to do with `inverted` and `SectorRelativeMomentum`, which upstream does not weight. Update `tbox.ttl`, `shapes.ttl`, `rules.ttl`'s `WeightScheme_v1`, docs 06/07 and `schema/README.md` counts. → step 6.

## Status

Closed Work items 1, 2, 3, 5, 7 (superseded/decided by T-007) and 10 are in
`CHANGELOG.md` (Work item 1 closed with T-006 deprecated in favor of T-009).
Work item 9 (T-080–T-083) has no blockers. Work items 4 and 6 (T-030–T-035, T-050–T-053)
follow in dependency order (Work item 3 is closed); Work item 11 (T-100–T-113, decisions
from the T-007 rescan) gates Work item 4 and has no store dependency.
Work item 8 (T-070–T-071) is independent but needs a human at a Protégé
session, not a coding session.
