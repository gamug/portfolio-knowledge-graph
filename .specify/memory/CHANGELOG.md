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

## Work item 3 — Stand up a triple store and wire the SHACL ingest gate (roadmap step 1)

- [x] **T-020** *(maintainer)* Choose GraphDB or Fuseki and its hosting
      (devcontainer service vs. separate). → `PLAN.md` Work item 3, step 1.
- [x] **T-021** Containerize/configure the chosen store; load
      `tbox.ttl → shapes.ttl → reference.ttl → rules.ttl → instances.trig`
      into a fresh repository/dataset. `cli/load_schema.py` (`src/kg_store/`) does it
      idempotently and verifies per-graph asserted counts against an `rdflib` parse
      (15 graphs, 1608 triples). Scope is `schema/` only; `data.ttl` and projected
      upstream data belong to Work item 4. → step 2.
- [x] **T-022** Lock the reasoning profile (OWL 2 RL/RDFS+ per
      `07-ontology-topology.md`) in the store's config. Config in
      `schema/graphdb-repo-config.ttl`; on loaded data `?x a :ObservationSnapshot`
      returns 35 = 25 `ScoreSnapshot` + 5 `SectorAggregateSnapshot` + 5
      `AttractivenessSnapshot`, so `subClassOf` inference works. → step 3.
- [x] **T-023** Wire a `pyshacl`-based ingest gate in front of write access.
      `kg_store.gate` / `cli/ingest.py`: the six checks in `docs/graphdb-setup.md`
      (§ Ingest gate); a rejected batch writes nothing. Every graph in
      `instances.trig` passes it on its own. → step 4.
- [x] **T-024** Document connection details in `.env.example`/`docs/`. →
      step 5.
- [x] **T-025** Verify: a basic SPARQL query returns real results; a
      deliberately-malformed write is rejected before reaching the store;
      the reasoning profile matches `07`'s documented choice. → `PLAN.md`
      acceptance criteria. Run: `cli/verify_store.py` (`docs/graphdb-setup.md` § Acceptance check).
- [x] **T-026** Rename the database environment variables to the maintainer's new
      scheme. The names are the maintainer's to choose and may change again, so
      read the final ones from the maintainer's `.env` when starting (as of
      2026-10-03: `SQL_URLS_DB`, `SQL_NLP_DB`, `SQL_FINANCIAL_DB`, `SQL_UNIVERSE_DB`,
      replacing `KG_URLS_DB`, `KG_RESULTS_DB`, `KG_FINANCIAL_DB`, `KG_UNIVERSE_DB`).
      Update every reader and every mention: `src/etl/config.py`, `src/etl/README.md`,
      `.env.example`, `constitution.md`, `SPEC.md`, `PLAN.md` and `TASKS.md` (the
      `KG_*` GraphDB variables keep their names). Leave `docs/portfolio-common-v1.2-engine-agnostic.md`
      alone (a dated decision record) and upstream's own variable names. Run the
      ETL's config load, then `rg --hidden 'KG_(URLS|RESULTS|FINANCIAL|UNIVERSE)_DB' --glob '!.git' --glob '!.env' --glob '!.specify/memory/TASKS.md' --glob '!docs/portfolio-common-v1.2-engine-agnostic.md'`
      to confirm no old name remains. Matches in those two excluded files are
      expected (T-026 itself lists the old names; the decision record is left as is). → `PLAN.md` Work item 3, step 5.

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

## Work item 9 — Resolve the `ScoreSnapshotShape`/Sentiment `rawValue` divergence

- [x] **T-080** Decide: add a `rawValue`-only branch to `ScoreSnapshotShape`
      for `metricType = Sentiment`, or add a normalization step to the ETL.
      → `PLAN.md` Work item 9, approach. **Done 2026-10-05 (maintainer
      decision: option 1, the shape branch).**
- [x] **T-081** Implement the chosen fix. → same. **Done 2026-10-05:** `ScoreSnapshotShape`
      exempts `Sentiment` from `normalizedScore` and requires `rawValue` ∈ [-1, 1] on every
      `Sentiment` snapshot (two `sh:or` constraints).
- [x] **T-082** Verify: the FR-001/FR-006 parse+`pyshacl` checks show zero
      violations for Sentiment snapshots in a sample run. → `PLAN.md`
      acceptance criteria. **Done 2026-10-05:** real ETL smoke run
      (`--limit 3000`) had 3000 Sentiment violations on the old shape and
      `SHACL conforms: True` on the new one; eight synthetic cases behave as
      intended; full schema 2400 quads, conforms: True.
- [x] **T-083** Document which option was chosen and why in
      `schema/README.md`'s gap list, alongside its three existing gaps. →
      `PLAN.md` acceptance criteria. **Done 2026-10-05** (in refinement 2 of the list).

## Work item 10 — Complete `schema/README.md`'s directory map

**DONE (2026-09-12)**, closed by the constitution-compliance pass.

- [x] **T-090** Add `protege-view.txt` and
      `taxonomy-quality-review-2026-08-23.md` to `schema/README.md`'s file
      listing. → `PLAN.md` Work item 10, approach.
- [x] **T-091** Verify: both files are now listed; the schema parse+`pyshacl`
      check still passes (docs-only change). → `PLAN.md` acceptance
      criteria.

## Work item 11 — Reconcile the ontology and ETL with the upstream contracts (T-007 rescan)

*Decisions first; Work item 4 is gated on T-100–T-104. D-numbers refer to
`SPEC.md` §2.6.*

- [x] **T-100** *(D1; done 2026-10-05, maintainer decision: adopt `universe.db`)* Replace the ETL's
      live-Wikipedia asset master (FR-004) with `universe.db` (`SQL_UNIVERSE_DB`, read-only via
      `portfolio_common.db`), emitting `:Asset` + `:UniverseMembership`
      (`validFrom`/`validTo`); document the stale-between-snapshots risk and
      that `universe.db` is now a direct upstream. → `PLAN.md` Work item 11,
      step 1. **Done:** `etl/asset_master.py` reads every stint; one `:Asset` per symbol, one
      `:UniverseMembership` per stint in `:SP500Index`; `AssetShape` makes `cikNumber`
      optional only when every membership is closed (checked with five cases); each run prints
      `universe.db`'s latest recorded change and file date; `KG_SP500_SOURCE_URL` removed,
      `SQL_UNIVERSE_DB` added. Full run on the real data: 98.5 s, 852 `:Asset` (+ 5 in
      `reference.ttl`), 877 memberships (503 open, 374 closed), 459,112 articles, 216,596
      `:RiskEvent`s; the only unresolved news ticker is `EQR` (1,104 rows, absent from
      `universe.db`; the live table lacked it too). 2383 quads, conforms: True (the PR review added `validFrom < validTo` to `UniverseMembershipShape`). Open parts are in
      `SPEC.md` §2.6's D1 row (upstream's `EQR` gap, hand-refreshed file, stray `|` in two symbols, two empty stints (`HNG`, `AYE`),
      no CIK on closed stints; nine symbols with several company names).
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
- [x] **T-108** *(D9 decided 2026-10-02; D11 decided and (b) done 2026-10-03; (a) moved to T-120 on 2026-10-05; task closed)*
      (a) ~~Who triggers the quarterly/daily cycles~~ — **`portfolio-app`**
      (not yet created) calls the upstream endpoints; raise with upstream that
      `api/` is read-only with no run-trigger endpoint and that their docs name
      `portfolio-reports` as the trigger. (b) **Done 2026-10-03:** only finished numbers
      upstream exposes through a `v_*` view become individuals: benchmark
      books/positions/performance and `v_quant_vs_live` active weight
      (`Portfolio.portfolioKind`, `BenchmarkObservation`, graph
      `urn:graph:derived:quant:{date}`); never returns, μ, Σ, frontier
      points — NR-003. (a)'s trigger/integration questions are now tracked by T-120. → steps 5–6.
- [x] **T-109** *(D8, D12, D13, D15, D16; read from upstream `8da3868`, 2026-10-02; done 2026-10-05; D13's schema work moved to T-121; the read-contract gaps are to be raised with the upstream maintainer)*
      Resolved by reading `kg_schema` upstream (incl. T-105's deferred question: no upstream metric id exists to rename `ScoreCuantitativo` to, so it stays): **`schema_version` floor is 9** (migrations 1–9; the projector must refuse a DB below it. No projector exists yet, and `src/etl/` does not read upstream's `v_*` views (it reads `urls.db`/`nlp.db`), so the check belongs to the future `v_*` projector, not `src/etl/`). **`v_cycle_ranking`**: SQL returns every `cycle_run`'s rows, docstring ("latest cycle per cycle_type") is wrong, so per-date ranking graphs must filter by `cycle_run_id`/`cycle_date`. **`run_id` is an integer** (`INTEGER` column, `v_*_run.run_id`), replacing T-106's placeholders. **`v_score_snapshot`** exposes neither `forensic_flags_json` nor `prompt_hash`; no view carries `financial_facts`/`correction_rule`/`fundamental_metrics`/market cap (D12 stays outcome-only). **`REPLAY`**: `cycle_type` marks it in `v_cycle_run`/`v_cycle_ranking`, but its scores/vetoes land in shared tables, so project against a production DB only. **T-108's**: columns, `quantMetric` names, `benchmarkObjective` = `v_quant_portfolio.objective` (`min_var`, `tangency`, `target_vol`, `risk_parity`), `quantAsOf` = `as_of` / performance `date`, values are fractions, with `quantUnit` `fraction` / `fraction_annual` (`expected_*`) / `fraction_daily` (`realized_return`, `active_return`, …) / `ratio` (`sharpe`) / `count`, only `quant_position` weights scaled ×100 into `weightPct` (done in `tbox.ttl`/`instances.trig`). **`live_book` decision (maintainer, option B, 2026-10-05):** `v_quant_portfolio` also holds `kind='live_book'` (a snapshot of the live book, `objective='live'`); it is not projected as a `Portfolio`, and its performance numbers attach to the LIVE `Portfolio` (`quantPortfolio` accepts LIVE or BENCHMARK; `QuantSubjectShape`). `equal_weight`/`cap_weight` (excluded by `v_quant_vs_live`; no writer seen in `quant/`) would be BENCHMARK with `benchmarkKind` recorded. `quantUnit` vocabulary: fraction/fraction_annual/fraction_daily/ratio/count; `quantBenchmark` keeps the reference index; `kind='LIVE_ONLY'` rows have NULL `benchmark_weight`.
      Closed 2026-10-05: (i) T-107's follow-up (answered: `v_shared_executive_edge` has `first_seen`/`last_seen` but no computed-at column, and `media_cooccurrence` has no view): `computedOn` stays optional and no `MEDIA` kind is added until a view exists (`MEDIA` = the proposed second kind of co-occurrence edge, non-executive, for `media_cooccurrence`); (ii) D13's weight-scheme mapping checked against `v_weight_scheme`/`v_weight_component` (findings in SPEC D13; the schema changes it implies are T-121); (iii) the read-contract gaps found are to be raised with the upstream maintainer. → step 6.
- [x] **T-110** *(D16)* Reconcile the `portfolio-common` pin (`v1.2.0` here and
      in `portfolio-nlp`; `v1.2.1` in `financial-analysis` and
      `portfolio-data-mining`) — verify compatibility, then re-pin or record
      why not. → step 6. **Done 2026-10-05:** re-pinned to `v1.2.1`; the diff
      v1.2.0→v1.2.1 is additive (`Dialect.upsert` options, `json_extract`/
      `json_each`, `Database.relation_exists`/`schema_version`, `DatabaseError`)
      and `news_export` is untouched; `uv sync` OK, imports of `Row`/
      `connect_readonly`/`fetch_processed_articles` OK. Only `portfolio-nlp`
      stays on `v1.2.0` (upstream's call).
- [x] **T-111** *(D14)* Add a `score_method` discriminator for SEMANTIC and
      correct the wording upstream still attributes to this repo (their
      rollout step 4); no write-back code exists here to remove. → step 6.
      **Done 2026-10-05:** optional open-vocabulary `:scoreMethod` on
      `ScoreSnapshot` (`tbox.ttl`, `ScoreSnapshotShape`); `src/etl/` emits
      `ARTICLE_SENTIMENT`, the worked asset-day snapshots carry the
      placeholder `ASSET_DAY_AGGREGATE`; D14 and `schema/README.md` updated. The stale
      "KG writes SEMANTIC" text is in upstream's `README.md`,
      `docs/README.md` and `docs/kg_schema.md`: not ours to edit, listed in
      the next upstream note.
- [x] **T-112** Record each D1–D16 disposition (adopted / translated /
      rejected / raised upstream) in `SPEC.md` §2.6; re-run FR-001 and update
      `schema/README.md` counts if `schema/` changed. → `PLAN.md` acceptance
      criteria. **Done 2026-10-05:** disposition table after the §2.6
      register; FR-001 re-run (2366 quads, conforms: True; `schema/README.md`
      already had it from T-111), and the stale 2352 in `SPEC.md` (§2.1, FR-001,
      §4 diagram, §6) and the root `README.md` updated. D1 is recorded as *Proposed*: no
      decision is on record, so T-100 starts by deciding it. Other open parts stay with
      T-120, T-121 and the upstream maintainer's answers.
- [x] **T-113** *(found while handling review on PR #22)* Reconcile FR-005
      with the code: `src/etl/news_to_rdf.py` reads SOURCE `urls.db`
      `body_text` (via `news_export`) for `compute_severity`'s hard-trigger
      keyword scan, but FR-005, §2.2 and its acceptance grep say the ETL never
      reads `body_text`. Either drop the body-text escalation or amend FR-005,
      §2.2 and §12. → `PLAN.md` Work item 11. **Done 2026-10-05 (maintainer
      decision: amend the spec, keep the escalation as provisional G3).**
      FR-005 (statement and acceptance criteria) and §2.2 now forbid reading
      source data for anything the processed stores (`nlp`, `financial`)
      already publish, instead of forbidding SOURCE reads. §12 and §13 item 12
      say the G3 keyword bump is the one SOURCE-derived signal today, and that
      `urls.db` stays required whatever happens to the bump, because the
      shared join reads `articles` from SOURCE. Measured on the full data: the bump raises
      20,363 of 216,596 `:RiskEvent`s one tier. No code change.

## Work item 14 — `ScoreSnapshotShape` and store-gate follow-ups (PR #48 post-merge review)

- [x] **T-140** *(done 2026-10-06; T-155 widens its [-1, 1] bound)* Tighten `ScoreSnapshotShape`:
      `SectorRelativeMomentum` requires `rawValue` in `[-1, 1]` (`docs/06` §1.8; mapping upstream
      SECTOR into it is T-031's); `rawValue` at most once (`owl:FunctionalProperty` in `tbox.ttl`);
      `agentOrigin` ↔ `metricType` one-to-one via `sh:xone`. 2458 quads, conforms; 18 synthetic
      cases, the acceptance probe (one violation), `docs/09`'s example and the ETL smoke run agree.
      → `PLAN.md` Work item 14, step 1.
- [x] **T-141** *(done 2026-10-08: `cli/verify_store.py` against the live `portfolio` repository, exit 0, all three checks pass; recorded in `docs/graphdb-setup.md`. It found that the store's schema graph is out of date and that the store holds a conflicting leftover graph: see T-174)* Run `cli/verify_store.py` against the live GraphDB repository with the current
      acceptance probe and record the result in `docs/graphdb-setup.md`. → step 2.
- [x] **T-142** *(done 2026-10-07 in PR #63: `gate.validate` raises `ShaclRejected`, an `IngestRejected` carrying pyshacl's results graph; `check_gate` requires exactly one `sh:ValidationResult`, a `:timestamp` `MinCountConstraintComponent`, with `tests/test_acceptance_gate.py` covering wording-independence, a second violation, a single violation of another kind, a non-SHACL rejection and an accepted batch)* Have `kg_store.gate.validate` expose pyshacl's results graph and make
      `acceptance.check_gate` count `sh:ValidationResult` nodes instead of matching
      `"Constraint Violation in"` in the text report. → step 3.
- [x] **T-146** *(done 2026-10-10: `ingest` reads what the store holds about the individuals a batch points at (`gate.references`, `gate.fetch_context`) and `validate` checks the batch beside it (only the properties the referenced classes' shapes read, plus an Asset's memberships' `validTo`), so a reference is typed by the store, not by the batch; `:clearedOn` joins `:validTo` as a closing property; the three `xfail`s are gone and every worked-example graph passes with its context; `--check` cannot see references and says so when it rejects; T-180 and T-181 split off; the text below is the original task)* Let the gate take the worked example's own batches (found writing T-136's tests):
      `gate.validate` checked a batch alone, so three `instances.trig` graphs fail it:
      `derived:entity-resolution:2026-08-05` (`sh:class :Asset` on `:coOccurrenceAsset` values typed
      in another graph), `derived:quant:2026-08-05` (`sh:class` on `:quantAsset`/`:quantPortfolio`
      values typed elsewhere) and `ingest:ORCHESTRATOR:2026-08-05` (closing a Veto with `:clearedOn`,
      which the untyped-subject rule allows only for `:validTo`). Decide per case: type the
      references in the batch's data graph for validation (without writing them), or relax the shape;
      allow `:clearedOn` as a closing property. Then drop the three `xfail`s in
      `tests/test_kg_gate.py` (strict, so they fail once it is fixed). Constitution Code & Git #9.
      → `PLAN.md` Work item 14, step 4.
- [x] **T-174** *(done 2026-10-08, after the maintainer's go-ahead: `cli/load_schema.py` reloaded the 19 graphs of `schema/` (2547 triples match the local parse); the leftover `QUANTITATIVE` graph was exported (35 triples, outside the repository) and dropped, `/size` 2582 → 2547; every `VALORIZATION` snapshot has one `:agentOrigin`, none has two anywhere; `verify_store` exit 0; recorded in `docs/graphdb-setup.md`. The leftover's absence is shown by the size (2547 is the total of the 19 graphs), not by a direct graph-list query: that query was blocked by the permission classifier and not retried; the text below is the original task, kept for the record)* Bring the live store's schema in line with `schema/` (found by T-141). Per graph,
      `urn:graph:tbox` holds 1420 triples against 1567 (it lacks the changes since the last load:
      T-121's per-run scheme terms and edits from T-151, T-153, T-155 and T-171, among others), and the
      store holds `urn:graph:ingest:QUANTITATIVE:2026-08-05` (35 triples), which `schema/` no longer
      has. That graph asserts the same five snapshot IRIs as `urn:graph:ingest:VALORIZATION:2026-08-05`
      with the old `:agentOrigin "QUANTITATIVE"`, so each of them has two `:agentOrigin` values in the
      store now (a defect, not just a tidy-up: `"QUANTITATIVE"` is outside `sh:in` and breaks
      `sh:maxCount 1`; dropping it loses no data). Two writes to the
      production repository, each run by the maintainer, or by a session they name, after their
      go-ahead (the gate does not cover a drop):
      (1) `uv run python cli/load_schema.py` (it drops and reloads every graph in `schema/`: `tbox`,
      `reference`, `rules:catalog` **and the worked-example data graphs of `instances.trig`**, so it
      leaves the leftover and prints it as "not in schema/"; reloading the example graphs is safe
      only because nothing else has been written into them, which the store's graph list confirms:
      it holds the example graphs and the leftover, no projected graph);
      (2) drop the leftover: first download that one graph as N-Triples
      (`GET {KG_HOST}/repositories/portfolio/rdf-graphs/service?graph=urn:graph:ingest:QUANTITATIVE:2026-08-05`
      with `Accept: application/n-triples`) to a file outside the repository, then run the update
      `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` on `/statements`.
      Note `/size` immediately before (2) (step (1) changes `tbox` by +147, so a size taken earlier
      is no baseline). After (2), check read-only: the graph is absent from the graph list, `/size`
      is that number minus 35, and each of the five snapshots in the `VALORIZATION` graph has exactly
      one `:agentOrigin`.
      Then re-run `cli/verify_store.py` and add the per-graph sizes to the `docs/graphdb-setup.md`
      record. Done when every graph in `schema/` has its expected size, the leftover is gone, and
      the checks above pass. → `PLAN.md` Work item 14, step 5.
- [x] **T-175** *(done 2026-10-08: `tests/test_store_cli_exit_codes.py`, six tests, all pass with `-m integration`; the three on a scratch repository need `KG_ADMIN_USER`/`KG_ADMIN_PASSWORD` because `portfolio.app` gets HTTP 403 on creating one; the scratch repositories are deleted, `portfolio` untouched at 2547 triples)* `integration` tests for the exit codes of `cli/verify_store.py`, `cli/load_schema.py` and
      `cli/ingest.py` (constitution Code & Git #9 lists them; the T-141 text covered only the run).
      `verify_store.py` writes nothing, so its test can run against the live repository (0 on a
      healthy store; with T-176 in, that is a store that matches `schema/`, as the live one now does). `load_schema.py` and `ingest.py` write, so they need a repository of their own
      (as `project_scores --replay` does), never `portfolio`. Opt in with `-m integration`, skipped
      when the store is unreachable. → `PLAN.md` Work item 14, step 7.

- [x] **T-176** *(done 2026-10-08: two checks in `kg_store.acceptance`, twelve fake-store tests in `tests/test_acceptance_schema_checks.py`; the live store passes, exit 0, five checks; the text below is the original)* Make `cli/verify_store.py` check the schema graphs and the defect T-174 found (read-only;
      found by T-141, split from T-174 so it does not wait for the production writes). Two new
      checks, reusing `load_schema.expected_sizes` and `verify`: (a) a graph that `schema/` owns and
      whose asserted size differs fails (owned = the graphs of `tbox`, `shapes`, `reference` and
      `rules` always; the worked-example graphs of `instances.trig` too, while that file is what
      `schema/` ships: when Work item 4 or T-035 replaces the example with real data, that task
      edits `instances.trig` and this check follows it, since `expected_sizes` reads the file); (b) no individual has more than one `:agentOrigin` (one
      `SELECT` over all graphs), and none has a value outside `ScoreSnapshotShape`'s `sh:in` list (read from `shapes.ttl`, parsed once as the gate does, not copied into the check).
      A graph the store holds that `schema/` does not own is **reported, not failed**, as
      `load_schema.verify` already does: Work item 4 writes dated `urn:graph:ingest:…` graphs there,
      and a healthy store must still exit 0. A total-size or one-term check would hide both
      differences. Tests with a fake store: equal sizes pass; a short graph fails; an extra graph is
      reported and passes; a doubled `:agentOrigin` fails; an `:agentOrigin` outside the list fails;
      the existing three checks are unchanged (constitution Code & Git #9). Before T-174 it would have
      failed (a) on `tbox` and (b) on the five snapshots; the live store no longer shows that (T-174 is done),
      so the fake-store tests carry the proof, and the live store must pass.
      → `PLAN.md` Work item 14, step 6.
- [x] **T-179** *(found by T-177; done 2026-10-10 after the maintainer's go-ahead; record in `docs/graphdb-setup.md`; the text below is the original task)* Reload the live store with
      `cli/load_schema.py` (T-174's procedure: the `urn:graph:tbox` graph grows by 2, to the size T-176's
      check expects from `schema/`: 1567 to 1569 triples there, 2547 to 2549 over the 19 graphs, the figures
      T-174 left in `docs/graphdb-setup.md`), then run `cli/verify_store.py` and record the result in
      `docs/graphdb-setup.md`. Until the reload `verify_store` failed its "schema graphs have their expected
      size" check, by design, and so did the `integration` test
      `test_verify_store_passes_on_the_configured_store` (T-175); both pass since the reload (figures in
      `docs/graphdb-setup.md`). → `PLAN.md` Work item 14, step 8.
- [x] **T-180** *(found in PR #86's review; the gate; done 2026-10-11: `gate.refused_closures` reads the closed subjects' types and closing values from the store (`fetch_closing_state`) and `ingest` refuses a closure of an unknown subject, of a class the property does not close (the explicit `gate.CLOSABLE`; a per-run weight scheme is never closed), of a record already closed, on a date not after it opened (strict `YYYY-MM-DD`, compared as dates), or with two dates; `--check` cannot see it, as for references, and says so on stderr; the text below is the original task)* Make the gate check what a closing triple closes:
      `untyped_writes` lets `:validTo` and `:clearedOn` through on any untyped subject without looking at
      the store, so a closure of a subject that is no stored record (or no stored Veto, for `:clearedOn`),
      or of one already closed, is written. In `ingest`, read the closed subjects' types and existing
      closing value from the store and refuse the batch otherwise. Tests with a fake store. Code, so its
      own PR on a `feat/` branch. → `PLAN.md` Work item 14, step 9.
- [x] **T-181** *(found in PR #86's review; done 2026-10-11: `GraphDB.select_terms` returns rdflib terms with the datatype or language the store holds, `select` is unchanged, `gate.fetch_context` uses it and drops the declared-datatype guess, a test stores a wrong-datatype literal, **a string is read as a plain literal** (whether the store writes `xsd:string` or nothing, because `sh:in`/`sh:hasValue` compare terms and the quant shape failed with the typed form), a statement whose subject or predicate is not an IRI raises, and `verify_store` gained a sixth check (the worked example's quant batch passes beside the stored Portfolios; not yet run live); the text below is the original task)* Keep the term type of a SPARQL result:
      `GraphDB.select` returns the lexical value only, so `gate.fetch_context` rebuilds a stored literal
      with the datatype its property declares and a stored literal of another datatype passes as if it
      had the right one. Return the type and datatype beside the value (a second method, or a richer
      row, so no existing caller changes), use it in `fetch_context`, and add a test with a stored literal
      of the wrong datatype. Code, so its own PR on a `feat/` branch. → `PLAN.md` Work item 14, step 9.
- [x] **T-185** *(found in PR #90's review; the gate)* Check a Veto's `:clearedOn` against its `:lastSeenOn`:
      **Done 2026-10-11 in PR #94**, after the maintainer chose to check at three places (`PLAN.md` Work item 14, step 10): the gate
      refuses a `clearedOn` earlier than the latest `lastSeenOn` of a stored Veto (`gate.CLOSABLE` carries a
      `last_seen` property); `VetoShape` refuses the same in a batch that declares a Veto with both dates
      (`sh:lessThanOrEquals :clearedOn` on `lastSeenOn`, 2550 quads, the twin in `kg_target_schema.ttl` too); T-192
      adds the read-boundary check. The same day passes, an assumption about upstream's `last_seen_on` on the
      clearing cycle (unverified; the question is listed in T-191). **Limit (until T-194):** the gate could not append a `lastSeenOn` to a stored Veto,
      so the closing check compared with the sightings declared with the Veto. **Open follow-ups** (T-194, the `lastSeenOn` append, and T-193, the store reload, are done): T-192 (the read-boundary check) and the question about the clearing cycle's
      `last_seen_on` (listed in T-191). Tests in `tests/test_kg_gate.py` and
      `tests/test_schema_gate.py`. The text below is the original task.
      `lastSeenOn` is multi-valued (one per cycle, current = MAX) and no shape relates it to `clearedOn`, so
      a Veto can be cleared on a date earlier than a cycle that still saw it raised. T-180's closing check
      already reads the Veto's stored state; read `lastSeenOn` there (or add `sh:lessThanOrEquals` to the
      shape, which changes the quad count SPEC states) and refuse a `clearedOn` earlier than its maximum.
      Decide with the maintainer whether a clearing run may predate a later sighting from another run.
      Code, so its own PR on a `feat/` branch. → `PLAN.md` Work item 14, step 10.
- [x] **T-186** *(found in PR #91's review; the maintainer, not code; done 2026-10-12: the six PASS lines are in `docs/graphdb-setup.md`'s T-193 section; the text below is the original task)* Run `uv run python cli/verify_store.py`
      against the live repository, which T-181 made six checks (the sixth runs the worked example's quant batch
      beside the stored Portfolios and Assets, so it needs `instances.trig` and `reference.ttl` loaded), and record
      the six PASS/FAIL lines and the date as a row of `docs/graphdb-setup.md`'s live-run section. The agent's
      sandbox reaches the store only when the server is up on the sandbox's network (the first attempt, 2026-10-12, got `Network is unreachable`; the next succeeded), so this is the only evidence of what GraphDB
      returns for a string literal (`datatype` absent or `xsd:string`). If it fails, fix `GraphDB._term` or the
      check. → `PLAN.md` Work item 14, step 9.
- [x] **T-193** *(from T-185; the maintainer, not code; done 2026-10-12: the store holds 2550 triples and `verify_store` exits 0, recorded in `docs/graphdb-setup.md`; the text below is the original task)* Reload the live store from `schema/` after PR #94 merges:
      `shapes.ttl` loads into `urn:graph:tbox`, which grows by 1 triple (2549 to 2550 over the 19 graphs), so
      `verify_store`'s "schema graphs have their expected size" check fails until then, with
      `urn:graph:tbox: expected 1570, store has 1569` (the expected failure; any other line is a different problem). With the maintainer's
      go-ahead: `uv run python cli/verify_store.py` (that check fails as expected), `uv run python cli/load_schema.py`
      (exit 0, `2550 asserted triples match the local parse`), `uv run python cli/verify_store.py` (exit 0), and a dated
      row in `docs/graphdb-setup.md`, as T-179 did. The agent's sandbox reaches the store only when the maintainer's server is up (down on the first attempt, up on 2026-10-12).
      → `PLAN.md` Work item 14, step 10.
- [x] **T-194** *(from PR #94's third review; the gate; done 2026-10-11 in PR #96: `gate.APPENDABLE` / `APPENDING_PROPERTIES`, a `lastSeenOn` is allowed on an untyped subject and checked against the store: a stored Veto, not cleared, the date not before `raisedOn` nor after the `clearedOn` the same batch gives it, later than the latest stored sighting (an equal date is a replay), one date per batch; tests in `tests/test_kg_gate.py`; the text below is the original task)* Let a later cycle append a `lastSeenOn` to a stored Veto.
      `docs/07` says a stint is appended to by later cycles (`lastSeenOn`, `clearedOn`) and `lastSeenOn` is
      multi-valued for that, but `gate.untyped_writes` allows only relations and `validTo`/`clearedOn` on a
      subject untyped in the batch, so the append is rejected. Allow an `xsd:date` `lastSeenOn` there and check it
      like a closing (`gate.CLOSABLE`-style): the subject is a stored Veto, not cleared, the date not before
      `raisedOn` and not before its latest stored `lastSeenOn`. Tests with a fake store (the closing tests'
      pattern). T-031's vetoes lane needs it for live cycles; stints loaded whole for backtests do not.
      Code, so its own PR on a `feat/` branch. → `PLAN.md` Work item 14, step 10.
- [~] **T-195** *(from T-032, the maintainer's decision of 2026-10-12; the gate; a `feat/` PR; needed a constitution edit first; cancelled 2026-10-13 (the maintainer): a re-run with other settings, or after a fix, is to be a new automation (one realization of the algorithm) built in its own GraphDB repository, so no graph is ever replaced (`PLAN.md` Work item 17, T-196–T-200); the text below is the original task)* ~~Let a re-run for the same
      agent and day replace that day's graph.~~ Superseded by Work item 17; the design below, constitution exception
      included, was never adopted. The gate refuses today a graph that exists
      (`gate.ingest`, check 2), which is right for a correction known on a later day (T-032) but
      wrong for a second run on the day the graph was written: nothing was believed in between, and
      keeping both says nothing a reader can use. Add one way in (a flag on `ingest`, or its own
      function) that validates the new batch with every check, then in one transaction clears the
      graph and writes the batch. Only the graphs dated by ingestion (`ingest:{SEMANTIC|VALORIZATION|TECHNICAL|SECTOR}:{date}`,
      `SPEC.md` §13 item 10): the per-quarter ones (`FUNDAMENTAL`, `EDGAR` by quarter, `universe`) are
      written once their quarter is complete, and `ORCHESTRATOR` is dated by the data's `cycleDate`, so
      none has a "day it was written" to match. Check 6 (no typed individual already stored) then
      reads the store minus the graph being replaced, since the new batch re-declares the old graph's
      individuals; every other check runs as for a new graph. Settle first: (a) the constitution's invariant 1 and
      `docs/07` ("Append-only") say an ingest graph is never edited, so both get the exception,
      stated narrowly: only the graph of the same agent and the day it was written, never one of a
      past day; (b) what points into the graph from elsewhere, settled by the scope above: the
      Vetoes and weight schemes that later graphs clear, sight or point at live in `ORCHESTRATOR`
      graphs, which are out. Keep one guard anyway: refuse the replacement when another graph holds a
      triple about a subject the old graph declares; (c) the replacement keeps the IRIs of the rows that
      did not change. Tests with a fake store. → `PLAN.md` Work item 14.

## Contract v18 re-pin (2026-11-01, T-205)

- Re-pinned the upstream read contract from v12 (33 contract views) to v18 (44): 43 views pinned in
  `src/projection/view_contract.py` plus `v_universe_membership` in `NOT_READ`. The 11 views added
  since v12 are `v_orchestrator_run`/`v_orchestrator_step` (m015), `v_ticker_history` (m016) and the
  eight m018 backtest/GUARD views; `v_quant_return_daily` gains `vendor` as its last column (m017,
  15 columns, pinned but unread under the Tiingo non-redistribution rule). No other existing view
  changed.
- `src/projection/view_expectations/_source.json` records `schema_version_floor` and
  `contract_version` 18; the 11 new views have expectation files with the handoff §3.3 nullable
  columns left nullable.
- The completed v18 database `rule_P1.db` (read-only) matches the handoff's 44 column tuples
  exactly. It is a backtest database: all 22 `v_cycle_run` rows are `REPLAY` and 13
  `v_analysis_run` rows have a NULL `as_of`, so the source check refuses it by design. The
  real-file boundary suite was not run against it, and nothing was filtered or filled in to work
  around that.
- A2 note: the final m018 design has eight views, not the A2 draft's 10–12.
- Follow-up: the new-view expectations were re-checked on P1, P2 and P3; the orchestrator null
  rules were relaxed to the key columns only, the `v_ticker_history` `evidence_url`/`evidence_date`
  non-null rules were removed, and the `drawdown`/`max_drawdown` min-0 ranges were removed because
  the handoff states no sign convention (`cost_return` min 0 kept; all three databases are
  non-negative).

## Contract v18 ontology (2026-11-01, T-206)

- The 11 views added between v12 and v18 now have ontology terms: `TickerHistory`,
  `OrchestratorRun`, `OrchestratorStep`, `StrategyBook`, `BookRebalance`, `GuardAlert`, `GuardAction`,
  `BookWeightDaily`, `BookDailyPerformance`, `PortfolioPeriodSummary` and `BacktestTest`, one per
  view. `tbox.ttl` goes from 40 to 51 classes (38 disjoint leaves, 13 backbone) and `shapes.ttl`
  from 20 to 31 named shapes; `AllDisjointClasses` gains the 11 leaves. Placement is by property
  shape: `TemporalRelation` for `TickerHistory`/`BookRebalance`, `Collection` for `StrategyBook`,
  `RiskAndDecision` for `GuardAction`, `Observation` for the other seven. Each class carries the
  handoff §6.2 `rdfs:label`@es and `skos:definition`@es verbatim (outer « » dropped); no new class
  has a FIBO `rdfs:seeAlso` (handoff §6.1).
- Every view column has a property. The shared ones (`bookId`, `backtestRunId`, `armCode`,
  `windowId`, `knowledgeDate`, `status`, `decisionDate`, `guardTicker`, `guardLayer`, `segment`,
  `handle`, `startedAt`, `finishedAt`, `runKind`) have no `rdfs:domain`, the `:runId` pattern, and
  every m018 individual carries `:knowledgeDate`. The handoff §3.3 nullable columns are optional in
  SHACL and never required; a CASH weight row has no asset link and needs no `:Asset` node.
  `TickerHistory`'s interval is **inclusive** (`validFrom <= d <= validTo`; a one-day symbol is
  valid), unlike `RuleDefinition`'s exclusive `validTo`; the gate's `CLOSABLE` entry carries an
  `inclusive` flag for it. The Orchestrator shapes require only their natural keys
  (`orchestratorRunId`; `stepOfOrchestratorRun` + `ordinal`): handoff §3.1 gives no base-table
  nullability and both views have 0 rows. The
  completed P1/P2/P3 databases override the DDL comments: `guard_layers` is NULL on
  `MARKOWITZ_BASE`/`TOPN_MV_NOGUARD` (optional in the shape) and `exclude_hard_vetoed` is 0 on all
  three arms (only its boolean type is enforced); `drawdown`, `cost_return` and `max_drawdown` get no
  sign or range constraint because the handoff states no sign convention.
- `rules.ttl` gains `UTILITY_CASH_COVERAGE` (HARD, `rule_input.utility_cash_coverage_3y < 0.05`, rank
  10, valid from 2026-10-31 — the last safe date: the rule was already in upstream's catalog in the
  completed backtest runs and raised a real veto in P1 on 2022-03-03, so a later date is impossible;
  not backdated to 2019/2020, and upstream's `v_rule_catalog.created_at` (2026-10-31T19:37:32) is a
  technical persistence timestamp, not the adoption date; superseded 2026-11-03 by T-216, which set
  the real 2026-10-14 date — see its entry at the end of this file) as the tenth selection rule; the `LEVERAGE_EXTREME`/`NEGATIVE_FCF`/
  `LIQUIDITY_DISTRESS` comments record the APP-00 profile exemptions (financial firms; regulated
  utilities; equity REITs) without changing thresholds, severities or clauses. The five GUARD rules
  (`L1_STOP_LOSS`, `L1_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD`) are `:category "GUARD"`
  `RuleDefinition`s in a separate section, one `GraphPredicate` leaf each, `:guardLayer` 1..4 and the
  frozen parameters/academic sources only in `rdfs:comment`; `L2_NEWS` is disabled in the 2022–2025
  backtest. They carry no `:ruleSeverity`/`:penaltyPoints`/`:priorityRank`.
- `RuleDefinitionShape` gets one `sh:or` branch for `:category "GUARD"`, keeps the severity
  requirement for every other active rule and makes `:priorityRank` mandatory for non-GUARD rules
  (range widened to `[1,10]`); `VetoShape` refuses a GUARD rule as `:appliesRule`/`:primaryRule`. A
  GUARD rule is not a veto rule.
- Tests: `tests/test_ontology_v18.py` covers the 51/38/31 counts, the @es text against handoff §6.2,
  the property list, every nullable case (layer-1 alert without value, layer-3 alert without asset,
  CASH weight without asset, MARKOWITZ_BASE rebalance without cycle run, book without guard layers,
  ordinary-day weight without targets, a one-day TickerHistory, an Orchestrator run/step with only
  its keys), synthetic non-conformant cases, the rule table and the GUARD/veto separation;
  `tests/test_kg_gate.py` covers the inclusive one-day TickerHistory closure and keeps the same-day
  membership closure refused; `tests/test_schema_gate.py` updates the 10 selection rules, the
  [1,10] rank and the target-schema mirror.
- Docs: `docs/06` §1.10 and the class tree/table, `docs/07` (PROPOSED
  `urn:graph:derived:backtest:{backtest_run_id}`), `docs/08` (the future projector), `schema/README.md`
  refinement 7, `SPEC.md` §2.1/§2.6, `PLAN.md` Work item 4 step 7, `README.md`, `docs/10` and
  `docs/graphdb-setup.md` counts. Bundle **4178 quads; conforms: True**.
- Not done: no projector (`src/projection/`), no change to the v18 pin, no ingest-gate pattern change
  beyond the schema-driven `CLOSABLE` entry and its `inclusive` flag for `TickerHistory`, no GraphDB
  write/reload and no `protege-view.ttl` regeneration (T-070/T-071).

## Contract v18 backtest/GUARD projector (2026-11-02, T-207)

- `src/projection/backtest.py` reads only the eight m018 views (`v_book`, `v_book_rebalance`,
  `v_guard_alert`, `v_guard_action`, `v_book_weight_daily`, `v_book_daily_performance`,
  `v_portfolio_period_summary`, `v_backtest_test`), runs the eight shipped boundary expectation
  files, and writes one append-only graph per completed run,
  `urn:graph:derived:backtest:{window_id}:{backtest_run_id}`. The window qualifies the name because
  P1/P2/P3 each start their `backtest_run.id`/`strategy_book.id` at 1. `src/projection/project_backtest.py`
  is the policy/`main`; `cli/project_backtest.py` is the thin entry point.
- The separate source check requires `schema_version >= 18` and `v_book.run_status = 'completed'`
  and never reads `v_cycle_run` (a backtest database's cycle runs are `REPLAY` by construction).
  The live `check_source` is unchanged and still refuses `REPLAY`.
- Every individual carries `:knowledgeDate` exactly as its view gives it. Masked/NULL columns are
  omitted, never filled: layer-1 alert value, layer-3/4 asset/ticker, asset-level action weights,
  ordinary-session target weights, CASH asset/name. A CASH row has no `:holdingAsset` and creates
  no `:Asset` node. Asset links are written only for tickers in `SQL_UNIVERSE_DB`; the rest keep
  their `:guardTicker`/`:holdingKey` and are counted per view. `:alertRule` resolves to the GUARD
  `:Rule_{rule_id}`; an unknown rule or a view layer that disagrees with the rule's `:guardLayer`
  stops the run. The five layers are 1, 1, 2, 3, 4, and all three real databases agree.
- Deterministic Turtle and window-qualified IRIs (`Book_{window}_{arm}`,
  `Rebalance_{window}_{arm}_{YYYYMMDD}`, `GuardAlert_{window}_{alert_id}`,
  `GuardAction_{window}_{action_id}`, `BookWeight_{window}_{arm}_{YYYYMMDD}_{holdingKey}`,
  `BookPerf_{window}_{arm}_{YYYYMMDD}`, `PeriodSummary_{window}_{arm}_{segment}`,
  `BacktestTest_{window}_{segment}_{armA}_{armB}_{test}`) are pinned by
  `tests/test_backtest.py` over a synthetic database built from handoff §3.2's literal DDL and view
  SQL, covering every §3.3 nullable case and two windows with colliding ids.
  `tests/test_project_backtest.py`/`tests/test_cli_project_backtest.py` cover the dry run, the
  production `--write` guard (`--to-production`) and the exit status; `tests/test_backtest_real.py`
  is the opt-in `BACKTEST_DB` row-count check.
- `src/kg_store/gate.py` accepts the new graph on its own branch (window `P1|P2|P3`, positive
  integer run id) instead of passing the id through `_date_ok`; `tests/test_kg_gate.py` covers the
  accepted/malformed forms and keeps the existing patterns unchanged.
- Real dry runs: P1 18,062 rows / 194,259 triples, P2 17,129 / 182,182, P3 19,421 / 205,892, each
  `pyshacl`-conformant, ~11–13 s and ~0.6–0.7 GB peak RSS. The asset links omitted are 303/112/52
  alerts, 606/224/104 actions and 14,709/14,301/16,392 weight rows. No GraphDB write or reload.
- Docs: `docs/07` (accepted graph and frozen-run rule), `docs/08` (the writer and how to run it),
  `docs/graphdb-setup.md`, `schema/README.md` refinement 7, `SPEC.md` §2.6, `PLAN.md` Work item 4,
  `TASKS.md` T-207 and the T-208/T-209 follow-ups. No schema file changed; the bundle stays
  **4178 quads; conforms: True**.

## FIBO Phase 1 alignment (2026-11-03, T-210)

- **Decision.** FIBO is a reference vocabulary, not a dependency: our terms stay in
  `https://thesis.local/kg/portfolio#`, there is no `owl:imports`/`owl:equivalentClass`/
  `rdfs:subClassOf` to FIBO, and no reader reasons over FIBO's axioms. A term gets
  `rdfs:seeAlso` only when FIBO's definition is true of every instance of it (same meaning, or a
  broader FIBO term); where FIBO would misstate ours there is no link and our definition states the
  difference.
- **Terms file.** `schema/fibo_terms.csv` (UTF-8, header `fibo_iri,our_term,fit,label_es,
  definition_es`, six data rows) is the single source for the six Phase 1 links. The Spanish
  columns are empty until Phase 2. Full IRIs are written in both IRI columns.
- **Schema.** `schema/tbox.ttl` removes the two broken
  `https://www.omg.org/spec/EDMC-FIBO/` links (`:Asset` → `LegalPerson`, with no replacement
  because `:Asset` is one node per ticker and FIBO has no matching term; `:SECFiling` → `Filing`,
  replaced by `Report`) and adds the six links: `:Portfolio`, `:PortfolioPosition`,
  `:tickerSymbol`, `:Sector`, `:Industry` and `:SECFiling`. `kg_target_schema.ttl` gets the same
  removals and four of the six links (it does not declare `:Sector`/`:Industry`). Net +4 triples in
  `tbox.ttl`: **4182 quads; conforms: True**.
- **Release check.** `cli/check_fibo_terms.py` (logic in `src/projection/fibo_terms.py`) refuses a
  zip whose sha256 is not
  `7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579` and requires every
  `fibo_iri` to have an `rdfs:label` and a `skos:definition`. The real run against
  `prod.ttl.zip` printed six `IRI -> label` lines in 1.6 s at ~111 MB peak.
- **Measured reasons for not importing FIBO.** The 2026Q2 release has 220 modules and 134,946
  statements, 2,240 named classes against our 51, and 71% of its statements describe 11,763 named
  individuals. The 2026-10-27 evaluation load inferred about 178,000 statements and returned 2,280
  classes (not re-measured); P1 (2026-11-02) counted 180,948 inferred before dropping the FIBO
  graph and 908 after (180,040 fewer), with the graph itself holding 134,946 statements and the
  other 18 graphs keeping their 2,550 explicit statements. The release is MIT-licensed (copyright
  EDM Association dba EDM Council, Inc. and Object Management Group) per `AboutFIBOProd`.
- **Tests.** `tests/test_fibo_terms.py`: the six rows and their fit/namespace/version rules; no old
  EDMC-FIBO IRI in the hand-maintained schema files; the `tbox.ttl` and `kg_target_schema.ttl`
  `rdfs:seeAlso` pairs equal the terms file in both directions (four links in the target schema);
  the synthetic-zip checker (wrong sha256, missing IRI, missing label, missing definition) and the
  CLI exit codes.
- **Docs.** `docs/06` §1.1 (decision, link rule, alignment table with the differs rows and the
  `:Asset`/`:PriceObservation` notes, measured sizes and inference cost, release and licence),
  `schema/README.md`, `SPEC.md` §2.1/§2.6, `PLAN.md` Work item 4 step 7, `README.md`,
  `docs/06`'s bundle count. Phase 2 (the 25-term slice, the authors' `@es` text and S1–S5) is
  T-211 and is not started. `protege-view.ttl`/`.txt` are generated and still carry the old IRIs;
  T-070/T-071 must regenerate and verify them with the six new links.

## FIBO Phase 2 glossary slice (2026-11-03, T-211)

- **Terms file.** `schema/fibo_terms.csv` grows to the 25 seeds of brief §4.1: the six Phase 1
  link rows now carry Spanish, the `:SP500Index` row is the seventh link, and the 18 glossary-only
  rows have an empty `our_term` and `fit = glossary`. Every row has a reviewed `label_es` and
  `definition_es`; a row is loaded only when both are filled. The thesis proposal was searched for
  a glossary (none found; its Word glossary part is empty), so its vocabulary governs: `portafolio`
  rather than `cartera`, and `tasa de retorno` rather than the brief's `tasa de rentabilidad`.
- **Builder.** `cli/build_fibo_slice.py` (logic in `src/projection/fibo_slice.py`) refuses any zip
  whose sha256 is not
  `7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579`, expands the 25 seeds through
  the release's named `rdfs:subClassOf` ancestors, keeps only labels, definitions, named parents
  and the `cmns-av` notes, copies literals with their original language tags, and writes a sorted,
  byte-identical file. It drops `rdf:type`, so no FIBO term is an `owl:Class` (NR-004).
- **Slice.** `schema/fibo.ttl` is 277 statements: 54 entries (25 seeds + 29 ancestors), 223 English
  statements (54 labels, 54 definitions, 63 named parents, 37 explanatory notes, 7 abbreviations, 6
  synonyms, 2 usage notes), 50 Spanish statements (25 labels + 25 definitions) and 4 header
  statements (version, sha256, verbatim MIT licence, comment). 16 parents outside the release stay
  only as the objects of their edges.
- **Spanish for our classes.** `schema/tbox.ttl` gains one `rdfs:label`@es and one
  `skos:definition`@es on each of the 27 pre-existing leaf classes, including the six "differs"
  definitions of brief §4.3; `kg_target_schema.ttl` mirrors the 14 it declares. The 11 v18 texts are
  unchanged (digest test). The FR-001 bundle is **4236 quads; conforms: True**.
- **S1/S3.** `schema/fibo.ttl` loads into `urn:graph:reference:fibo` after `reference.ttl`; the
  fresh-load total is 20 graphs and 4513 asserted triples. The ETL emits
  `:SP500Index rdfs:seeAlso <.../IND/MarketIndices/BasketIndices/EquityIndex>` once, in
  `src/etl/asset_master.py`.
- **Tests.** `tests/test_fibo_slice.py`: the §4.2 counts, no `rdf:type`, every FIBO link target is
  an entry, the 38 leaves and the 11 v18 digest, the Appendix A queries offline, the synthetic
  builder and the opt-in `FIBO_ZIP` byte-for-byte rebuild. `tests/test_fibo_terms.py`,
  `tests/test_asset_master.py` and `tests/test_kg_load_schema.py` are updated for 25 rows, the ETL
  link and the new graph.
- **Docs.** `docs/06` §1.1 (Phase 2, rebuild command, the two Appendix A queries unchanged),
  `docs/07`, `docs/graphdb-setup.md`, `schema/README.md`, `SPEC.md`, `PLAN.md`, `TASKS.md`,
  `README.md`.
- **Not done then.** No GraphDB write or reload was made in that change; T-212 and T-213 landed
  on 2026-11-02 (see the next entry), and the generated `protege-view.ttl`/`.txt` still need
  regeneration (T-070/T-071).

## Live-store reload and FIBO graph drop (2026-11-02, T-212/T-213)

Documentation only; no code, schema, shape or test logic changed.

- **P1, the full FIBO graph drop.** P1 of the FIBO integration brief, done by the maintainer by hand
  in the GraphDB Workbench on 2026-11-02 (local evening), repository `portfolio`. The graph
  `<https://spec.edmcouncil.org/fibo/ontology/2026Q2>` was dropped with `DROP GRAPH`, nothing else.
  Before: 137,496 explicit and 180,948 inferred statements over 19 graphs, 134,946 of them in that
  graph. After: 2,550 explicit and 908 inferred over 18 graphs. Difference: 134,946 explicit and
  180,040 inferred; the remaining 2,550 explicit statements equal the sum of the other 18 graphs.
  Recorded in `docs/graphdb-setup.md`; `docs/06` §1.1 already cited the same measurement.
- **T-212, the schema reload.** The maintainer, by hand on 2026-11-02, from `master` at `0267d90`
  (the merge of PR #113): `cli/load_schema.py` exit 0, `verified: 20 graphs, 4513 asserted triples
  match the local parse`; `cli/verify_store.py` exit 0, all six checks pass (the store size stays
  4513). The local `.env` needed `KG_HOST=http://host.docker.internal:7200` instead of
  `127.0.0.1`; no `verify_store` ran before the reload. `urn:graph:reference:fibo` holds the 277
  statements of the slice, which follows only as 4513 − 4236, not from a separate per-graph count.
- **T-213, the live Appendix A run.** The maintainer, in the Workbench on 2026-11-02, ran the two
  queries exactly as in `docs/06` §1.1: A2 returned one row for `Volatility`, A1 one row for
  `Portfolio`, each with our Spanish pair, the FIBO IRI, FIBO's English definition and the authors'
  `@es` text. Both match `tests/test_fibo_slice.py`, confirming the live graph layout.
- **T-187/T-188** no longer wait for the reload: `verify_store` passes. T-187 stays open only for
  the maintainer's local, untracked `CLAUDE.md` ("six rules").
- **Follow-ups.** T-215 (first real backtest `--write` into a scratch repository, needs the full
  universe) and T-216 (ask upstream T-071's real merge date) were open then (T-216 closed
  2026-11-03; see its entry below). The generated `protege-view.ttl`/`.txt` remain stale
  (T-070/T-071); no backtest graph was written. The FR-001 bundle is unchanged at 4236 quads.

## UTILITY_CASH_COVERAGE validFrom correction (2026-11-03, T-216)

- The upstream maintainer supplied T-071's real integration date: part 2a (PR #167, merge commit
  `7ae8ba8`, "Merge pull request #167 from gamug/feat/t071b-vetoes") reached upstream master on
  2026-10-14 20:51:47 -0500 (already 2026-10-15 in UTC). `schema/rules.ttl` now sets
  `:Rule_UTILITY_CASH_COVERAGE`'s `:validFrom` to `2026-10-14`; it was `2026-10-31`, the last safe
  date, until this change. The block comment and `rdfs:comment` explain that valid-time means when
  the definition was in force in production, not that a backtest applies it retroactively: the P1
  backtest replays history with today's catalog, so it raised this rule's veto on 2022-03-03, which
  is why backtest vetoes cannot resolve their rule by `raisedOn` (T-209).
- `tests/test_ontology_v18.py` pins `2026-10-14` and asserts it is not later than the 2026-10-31
  backtest run date, so T-209's convention still resolves the rule. Docs updated: `docs/06` §1.5
  (new T-216 addendum) and §1.10, `schema/README.md` refinement 7, `SPEC.md`, `PLAN.md`, and
  `TASKS.md` (T-206 history, the T-212/T-216 reload note, T-216 closed). The bundle is unchanged at
  **4236 quads; conforms: True**.
- No GraphDB write or reload: the live store (and the scratch store, if any) keeps `2026-10-31` for
  this rule until the next `cli/load_schema.py`, which the maintainer will run later together with
  other schema changes (T-212/T-216).

## Work item 21 — Reports-agent query catalog and its executable test (2026-11-03)

*Closed 2026-11-03. Plan: `PLAN.md` Work item 21. The catalog is a document plus a hermetic test;
no `src/`, `schema/` or gate change.*

- [x] **T-240** *(done 2026-11-03)* Write `docs/reports-agent-query-catalog.md`: the scope rule
      (always `GRAPH`, never the default union), the Appendix A lookups (`A1` for ten of our
      terms at once with the FIBO link in the same `OPTIONAL`; `A2` by Spanish label, the
      volatility, equity-index, closing-price and SEC terms), the terms FIBO does not define (a
      `@es` definition containing "sharpe": `PortfolioPeriodSummary` and `BacktestTest`), the
      active rules by category (10 selection + 5 GUARD, active = no `validTo`), and the backtest
      battery (including `n-equity-per-arm-on-last-day`). Every `sparql` block is preceded by
      `<!-- q:NAME expect:... -->`. → `PLAN.md` Work item 21, step 1.
- [x] **T-241** *(done 2026-11-03)* Add `tests/test_query_catalog.py`: parse every tagged query,
      build one in-memory `rdflib.Dataset` from `schema/tbox.ttl` (`urn:graph:tbox`),
      `schema/fibo.ttl` (`urn:graph:reference:fibo`), `schema/rules.ttl`
      (`urn:graph:rules:catalog`) and `schema/reference.ttl` (`urn:graph:reference`), plus two
      run labels (`rule`, `champ_v1`) across two windows (`P1`, `P2`) projected with
      `projection.backtest.project`;
      run every query and check its exact row count or named rule. The test also pins the A1
      no-FIBO rows (`:Asset`, `:Universe`, `:UniverseMembership`, `:PriceObservation`,
      `:Executive`), the exact eleven questions, the six status labels, the two Sharpe-less
      terms, the 5/1/4/5 active-rule split, and the absence of a drifted weight or a per-asset
      daily return on `BookWeightDaily` and `BookDailyPerformance`. → step 2.
- [x] **T-242** *(done 2026-11-03)* Write the limits section: the brief's 11 evaluation
      questions and the backtest questions mapped to today / after the asset catalog / after
      T-209 / after T-208 / never by design / not projected yet; state the §5 boundary rule and
      the control rule that the answers to questions 9 to 11 must not change with or without the
      FIBO slice. The exact questions and the six labels are pinned by the test, and the table
      has exactly 11 `Q` rows. → step 3.
- [x] **T-243** *(done 2026-11-03)* Verify and reconcile: `uv run pytest -q`,
      `uv run mypy --config-file=.code_quality/mypy.ini`, `uv run pre-commit run --all-files`;
      update `README.md`, `docs/06` §1.1, `SPEC.md`, `PLAN.md`, `TASKS.md` and this file. No
      schema count changed, so `schema/README.md` and the FR-001 bundle are untouched. → step 4.
- [x] **Follow-up (2026-11-03, PR #116 review).** Replace the reconstructed §6 table with the
      brief's 11 questions verbatim; add the `Not projected yet` status, the §5 control rule and
      the `n-equity-per-arm-on-last-day` query; extend `A1` to `:Universe`,
      `:UniverseMembership`, `:PriceObservation` and `:Executive`, and add the equity-index,
      closing-price and SEC A2 labels. The test now pins the exact question text and the six
      labels. No new task ID; this completes the same work item.
- [x] **Follow-up (2026-11-04, merge of PR #117 and PR #118).** Merge `origin/master` and keep
      both sides of the append-only logs; renumber this work item from 19 to 21 because master
      already has Work item 19 (asset loader) and Work item 20 (run labels). The catalog now uses
      `urn:graph:derived:backtest:{label}:{window}:{run_id}`, adds `runs-available`, and every
      per-run backtest query takes the optional `FILTER (?label = "rule")` parameter. The test
      projects two labels in the same window as well as two windows and proves the labels do not
      mix; the §6 legend notes that the asset loader exists as `cli/load_universe.py` but the
      statuses stay until the maintainer runs it and the live check passes.

## Work item 22 — Map the six retired GICS sub-industry names (2026-11-04)

*Closed 2026-11-04. Plan: `PLAN.md` Work item 22. Only the rollup table, its
tests and docs changed; `schema/reference.ttl`, the shapes, the tbox and the
loader were untouched.*

- [x] **T-250** *(done 2026-11-04, read-only)* Audit
      `file:/workspaces/thesis/data/universe_history_gics.db?mode=ro` under the
      loader's `--since 2019-01-02` kept set. Each of the six names occurs on
      exactly one kept stint, one symbol: Alternative Carriers (LUMN,
      1976-07-01..2023-03-19, Communication Services); Drug Retail (WBA,
      1976-07-01..2025-08-27, Consumer Staples); Home Furnishings (MHK,
      2013-12-23..2025-12-21, Consumer Discretionary); Household Appliances
      (WHR, 1976-07-01..2024-03-17, Consumer Discretionary); Housewares &
      Specialties (NWL, 1976-07-01..2023-09-17, Consumer Discretionary);
      Thrifts & Mortgage Finance (PBCT, 1976-07-01..2022-04-03, Financials).
      All six had an unambiguous existing reference group, so no mapping needed
      to stop for a decision. → step 1.
- [x] **T-251** *(done 2026-11-04)* Add the six entries to
      `SUB_INDUSTRY_TO_INDUSTRY` in `src/etl/common/gics_rollup.py`: Alternative
      Carriers -> `Ind_TelecomServices`; Drug Retail ->
      `Ind_ConsumerStaplesRetail`; Home Furnishings, Household Appliances and
      Housewares & Specialties -> `Ind_ConsumerDurables`; Thrifts & Mortgage
      Finance -> `Ind_Banks`. The comment beside them marks them historical,
      notes that only Thrifts & Mortgage Finance was itself discontinued by the
      March 2023 reclassification (into Commercial & Residential Mortgage
      Finance), and leaves `lookup()` returning `None` for every other unmapped
      name. → step 2.
- [x] **T-252** *(done 2026-11-04)* Add one parametrized case per name in
      `tests/test_etl_common.py`, asserting the target group and the period
      sector cross-check (`sector_matches`); the existing unknown-name case
      still fixes `lookup("Not A Sub-Industry") is None`. → step 3.
- [x] **T-253** *(done 2026-11-04)* Add
      `test_a_dry_run_maps_the_historical_sub_industries_without_a_warning` in
      `tests/test_cli_load_universe.py`: a six-row fixture through
      `cli/load_universe.py` exits 0, reports no "no rollup entry" warning and
      names none of the six strings. → step 3.
- [x] **T-254** *(done 2026-11-04, read-only)* Full dry run over
      `universe_history_gics.db`: 657 of 891 stints kept over 653 symbols, 648
      assets written plus the five in `reference.ttl`, 657 memberships (503
      open, 154 closed), **6563 triples** (6557 before), no rollup warning and
      SHACL conforms. LUMN, WBA, MHK, WHR, NWL and PBCT each gained the expected
      `:classifiedAs`; the only remaining warnings are the pre-existing stray
      `|` and empty-stint reports. → step 4.
- [x] **T-255** *(done 2026-11-04)* Document the rollup and the six historical
      names in `src/etl/README.md`, including the mapping table and the
      retained-vs-retired distinction. → step 5.
- [x] **T-256** *(done 2026-11-04)* Update the real dry-run record in
      `docs/graphdb-setup.md` to the 2026-11-04 run over
      `universe_history_gics.db`, 6563 triples and no unmapped warning. → step 5.
- [x] **T-257** *(done 2026-11-04)* Update SPEC FR-008's acceptance count and
      the Work item 19 plan count to 6563 (recording 6557 as the before value;
      6476 was the earlier `universe_history.db` run); no schema count changed. → step 5.
- [x] **T-258** *(done 2026-11-04)* Record Work item 22 in `PLAN.md`, move its
      task block here, and add the closed-work-item pointer to `TASKS.md`. → step 5.
- [x] **T-259** *(done 2026-11-04)* Verify: `uv run pytest -q` = 1052 passed,
      56 deselected in 665.18 s; `uv run mypy --config-file=.code_quality/mypy.ini`
      = success, 77 files; `uv run pre-commit run --files <changed files>` passes
      all hooks (the standalone `uv run ruff check .` still reports the
      pre-existing repo-wide 0.16.x/config mismatch, not these files). → step 5.

## Work item 23 — Inclusive membership end dates and one asset per CIK (2026-11-04)

*Closed 2026-11-04. Plan: `PLAN.md` Work item 23. Two work commits on
`feat/universe-inclusive-validto-cik-fold`: T-260–T-263 are Commit 1 (the inclusive `validTo`);
T-264–T-271 are Commit 2 (the CIK fold); `origin/master` was merged after PR #119, keeping both
sides of the append-only logs. No GraphDB write or schema reload was made.*

- [x] **T-260** *(done 2026-11-04)* Make `:UniverseMembership`'s `validTo` inclusive:
      `read_stints` keeps `valid_to == valid_from` and skips only `valid_to < valid_from`;
      `UniverseMembershipShape` uses `sh:lessThanOrEquals`; the gate's `CLOSABLE` entry treats a
      membership as inclusive (a same-day closure is a one-day stint). Do not change another
      class's `validTo` semantics. → `PLAN.md` Work item 23, Commit 1.
- [x] **T-261** *(done 2026-11-04)* Tests: a one-day stint is kept and SHACL-conforms;
      `validTo < validFrom` still fails; a membership on its last day is in the catalog query; a
      same-day membership closure is accepted and a closure before its opening day is refused.
      → Commit 1.
- [x] **T-262** *(done 2026-11-04)* Update every statement and query that said exclusive for
      memberships: `schema/tbox.ttl`, `schema/shapes.ttl`, `schema/README.md`, `docs/06`, `docs/07`,
      `src/etl/README.md`, `docs/graphdb-setup.md`, SPEC FR-004/FR-008/D1 and
      `docs/reports-agent-query-catalog.md` (+ `tests/test_query_catalog.py`). The predicate is
      `validFrom <= D AND (no validTo OR validTo >= D)`. → Commit 1.
- [x] **T-263** *(done 2026-11-04, read-only)* Real-data verification on
      `/workspaces/thesis/data/universe_history_gics.db`: before 657 stints over 653 symbols, 648
      `:Asset`s plus five in `reference.ttl`, 657 memberships (503 open, 154 closed), 6563 triples,
      63 written assets without `:classifiedAs`; after 658 stints over 654 symbols (236 dropped over
      230; 215 not loaded, 15 with a later stint kept), 649 `:Asset`s plus five, 658 memberships
      (503 open, 155 closed), 6573 triples, 64 written assets without `:classifiedAs` (their latest
      stint has no GICS sub-industry; Work item 22's six values are mapped), SHACL conforms.
      → `PLAN.md` Work item 23, Commit 1.
- [x] **T-264** *(done 2026-11-04)* Added one shared CIK-aware resolver
      (`etl.asset_master.resolve_assets`, with `classify_ciks` and `AssetResolutionError`): a pure
      succession (one CIK, symbols' inclusive stints non-overlapping) becomes one `:Asset` named
      by the latest stint's symbol with every stint as a membership; concurrent share classes stay
      one `:Asset` per symbol; a mixed CIK stays as today; a CIK-less stint stays grouped by
      symbol. The `:TICKER` IRI scheme is unchanged and no property or class was added. → Commit 2.
- [x] **T-265** *(done 2026-11-04)* `build_assets`/`cli/load_universe.py` use the resolver;
      `--since` and ticker reuse (`CEG`, `DELL`, `Q`) keep their behaviour; two kept CIKs claiming
      the same latest ticker stop the run with both CIKs named (`STOPPED`, exit 1); the resolver
      exposes the multi-symbol CIK classification. → Commit 2.
- [x] **T-266** *(done 2026-11-04)* `projection.backtest.universe_assets` uses the same resolver
      (no second grouping), and `projection.score_snapshots.universe_symbols` does too, so a
      former ticker is never offered as an asset;
      `test_the_loader_and_the_backtest_projector_share_the_asset_set` proves the sets are equal.
      → Commit 2.
- [x] **T-267** *(done 2026-11-04)* Hermetic tests in `tests/test_asset_master.py` and
      `tests/test_universe_load.py`: the `FB`→`META` chain is one `:META` with two memberships and
      no `:FB`; concurrent classes stay separate; the mixed `DISCA`/`DISCK`/`WBD` stays per
      symbol; a CIK-less stint stays by symbol; two kept CIKs on one ticker stop; loader and
      projector agree. → Commit 2.
- [x] **T-268** *(done 2026-11-04, read-only)* Real-data verification on
      `universe_history_gics.db` at `--since` 2019-01-02: before 658 stints over 654 symbols, 649
      `:Asset`s plus five, 658 memberships (503 open, 155 closed), 6573 triples, 64 without
      `:classifiedAs`; after 643 `:Asset`s plus five (648 assets from 654 symbols; six successions
      folded), 658 memberships (503 open, 155 closed), 6548 triples, 59 without `:classifiedAs`,
      SHACL conforms. Every multi-symbol CIK is classified: six successions, four concurrent, one
      mixed. → Commit 2.
- [x] **T-269** *(done 2026-11-04, read-only)* Dry runs of `cli/project_backtest.py` for
      `rule_P1`, `rule_P2` and `rule_P3` (`--db rule=<path>`): the graphs are SHACL-valid and not
      written, with 0 unlinked assets; every ticker in `v_book_weight_daily` (CASH excluded),
      `v_guard_alert` and `v_guard_action` links (P1 100, P2 123, P3 115 distinct; 0 missing).
      → Commit 2.
- [x] **T-270** *(done 2026-11-04)* Updated SPEC FR-004/FR-008/D1, `docs/06`, `docs/07`,
      `src/etl/README.md`, `schema/README.md` and `docs/graphdb-setup.md` for the CIK fold and
      every asserted count, keeping `:Asset` per company vs per share class explicit. → Commit 2.
- [x] **T-271** *(done 2026-11-04)* Final gates and reconciliation: `uv run pytest`, `uv run mypy
      --config-file=.code_quality/mypy.ini`, the pinned `uv run pre-commit run --all-files`; Work
      item 23 moved to `CHANGELOG.md`. → Commit 2.

## Work item 24 — Verify a loaded backtest against its source (2026-11-04)

*Closed 2026-11-04. Plan: `PLAN.md` Work item 24. Code, tests and the runbook; no
schema file, no GraphDB write or reload.*

- [x] **T-280** *(done 2026-11-04)* Add `src/projection/verify_backtest.py` and its thin entry point
      `cli/verify_backtest.py`: `--graph` (required), `--db` and `--label`. The store comes from
      `GraphDB.from_env()` and the verifier issues only SPARQL `SELECT` queries. It re-projects the
      source in memory through a new `projection.backtest.project_source` (the same boundary,
      projector and deterministic Turtle the write path uses), prints the repository and graph it
      checked, one `PASS`/`FAIL` line per check, and exits 0 only when every check passes. The
      checks cover the graph name and stored `:runLabel`/`:windowId`/`:backtestRunId`, total
      triples, the eight class counts, distinct `:holdingAsset`/`:guardAsset` tickers and the
      unlinked-row ceiling, GuardAlert groups by rule/layer/state, GuardAction by status, last NAV
      per arm, CASH rows, `:runLabel` through the book and `:knowledgeDate`. `project_source` is
      also now what `backtest.run` calls, so the verifier cannot drift from the writer. →
      `PLAN.md` Work item 24, item 1.
- [x] **T-281** *(done 2026-11-04)* Add `docs/backtest-load-runbook.md`: schema reload and
      `verify_store`, the one-time asset-catalog load, copying the databases, the pinned contract
      check, the label rule, the dry run, `--write` and the `--to-production` guard, the
      per-graph verifier, recording the numbers, dropping exactly one graph, a new label/run, and
      the common failure messages. The catalog section states the real limit read from the code and
      gate: the loader writes the whole catalog, a second same-quarter load is refused because the
      graph exists, a later quarter re-declares the same typed individuals and is refused by check
      6, so a new ticker needs a fresh repository (or a new incremental membership task); dropping
      the universe graph or writing around the gate is never the procedure. → item 2.
- [x] **T-282** *(done 2026-11-04, read-only)* Re-measure the three completed databases:
      `rule_P1.db` 15,615 `v_book_weight_daily` rows and 209,886 triples in
      `urn:graph:derived:backtest:rule:P1:1`; `rule_P2.db` 15,641 and 196,840; `rule_P3.db` 18,025
      and 222,449. Peak RSS 0.66–0.73 GB and 44–48 s per database; all three dry runs exit 0 with
      `SHACL-valid, not written`. Recorded in `docs/graphdb-setup.md` and the runbook. → item 3.
- [x] **T-283** *(done 2026-11-04)* Tests: `tests/test_verify_backtest.py` uses an in-memory
      `rdflib.Dataset` as the store and covers a passing graph, a missing class, an altered
      individual count, a missing link, a wrong label and a wrong graph name, plus the repository/
      graph header and the check names; `tests/test_cli_verify_backtest.py` runs the real entry
      point as a subprocess for its argument contract. The verifier was also exercised against an
      in-memory Dataset holding `rule_P1.db`'s projection: 21 of 21 checks passed over 209,886
      triples (100 linked holding tickers, 46 linked guard tickers, 588 CASH rows), so the checks
      are proven on real source data as well as the fixture. Docs: `PLAN.md` Work item 24, `TASKS.md`
      pointer, this entry, `SPEC.md` FR-009 and §2.1, `README.md`, `schema/README.md`,
      `docs/graphdb-setup.md`, and the runbook. No schema count changed. → item 5.

**Files.** `src/projection/verify_backtest.py`, `cli/verify_backtest.py`,
`src/projection/backtest.py` (`project_source` extraction), `tests/test_verify_backtest.py`,
`tests/test_cli_verify_backtest.py`, `docs/backtest-load-runbook.md`,
`docs/graphdb-setup.md`, `README.md`, `schema/README.md`, `SPEC.md`, `PLAN.md`, `TASKS.md`,
`CHANGELOG.md`.

**Validation.** `uv run pytest -q`: **1071 passed, 56 deselected, 1507 warnings in 864.99 s
(0:14:24)**, exit 0 (19 of the tests are this work item's new files; the run overlapped other
sessions on the same host, so the wall time is higher than T-259's 665 s baseline). `uv run
mypy --config-file=.code_quality/mypy.ini`: success, 81 source files. Pinned `pre-commit` on every
changed file: all hooks passed (`ruff-check`, `ruff-format`, `mypy`, the file/secret checks). The
verifier also ran against an in-memory Dataset holding `rule_P1.db`'s projection: 21 of 21 checks
passed over 209,886 triples. No GraphDB write or reload was made; the verifier has never run
against a live repository, so that first live run remains the operator's step in the runbook.
## Work item 25 — Reports-agent sector and industry queries (2026-11-04)

*Closed 2026-11-04. Plan: `PLAN.md` Work item 25. The catalog and its hermetic
test changed; no `src/`, `schema/` or gate change.*

- [x] **T-300** *(done 2026-11-04)* Add §6 to
      `docs/reports-agent-query-catalog.md`: the cross-graph rule (backtest
      triples inside `GRAPH ?g` filtered to `urn:graph:derived:backtest:`, the
      asset-to-sector part in a `SELECT DISTINCT` sub-select outside it) and
      five tagged queries — `layer1-cuts-by-window-sector`,
      `sector-composition-on-rebalance`, `held-tickers-by-window-industry`,
      `sector-coverage-of-held-assets` and
      `unclassified-assets-by-validto-year`. State that `:finalTargetWeight`
      exists only on decision and execution dates and that the sector weights
      plus CASH sum to 1. → step 1.
- [x] **T-301** *(done 2026-11-04)* Rework `tests/test_query_catalog.py` to the
      real layout: `:Asset` and `:classifiedAs` in
      `urn:graph:universe:2026-Q4`, the taxonomy in `urn:graph:reference`, and
      `AAPL` in both graphs (T-225); enable GraphDB's default union for the
      documented sub-select. Add the sector assertions (P1 cuts = layer-1 ENTER
      alerts, composition = 1 − CASH, Banks/Insurance lists, coverage split,
      unclassified years) and the negative test: the single-graph form returns
      0 rows in the universe graph and 5 in the reference graph against 8 for
      the correct cross-graph form; a naive union counts AAPL twice. → step 2.
- [x] **T-302** *(done 2026-11-04)* Update the limits table: Q5 and Q11 become
      **Today**, Q11 points at `held-tickers-by-window-industry`, and the loader
      note records the `portfolio_test` catalog (648 assets, 579 classified).
      Add §6.7 "Known limits of the asset catalog": the 2019–2021 leavers'
      **56 closed stints** have no source classification ("no classification in
      the source", not an error), MBC (inference, no source), FTRE and PHIN
      (S&P DJI release of 2023-06-28, cited in `universe_patches.py`) have none
      either, and GICS is rolled up by `src/etl/common/gics_rollup.py`. Leave
      `validTo` semantics and asset identity to Work item 23 and refer to it by
      name. → step 3.
- [x] **T-303** *(done 2026-11-04, read-only)* Verify the five queries against
      `portfolio_test`: layer-1 cuts 157 (P1), 56 (P2), 29 (P3), with P1 equal
      to its 157 ENTER alerts; the P1 `MARKOWITZ_BASE` composition (decision
      2021-12-31, execution 2022-01-03) has 9 sector rows summing to
      `0.999999548278…` with CASH `0.000000451721…`, i.e. exactly 1; the
      Banks/Insurance query returns 5 rows; coverage is 100/100/100,
      123/123/123 and 115/115/115; the 2019–2021 unclassified closed stints
      total 56. No GraphDB write or reload. → step 4.
- [x] **T-304** *(done 2026-11-04)* Verify and reconcile: `uv run pytest -q` =
      **1069 passed, 56 deselected in 955.22 s**; `tests/test_query_catalog.py`
      = 50 passed in 4.14 s; `uv run mypy --config-file=.code_quality/mypy.ini`
      = success, 77 files; `uv run pre-commit run --files <changed files>`
      passes all hooks. Update `PLAN.md`, `TASKS.md` and this file; no schema
      count changed. → step 5.
- [x] **T-305** *(done 2026-11-04, PR #120 review)* Fix
      `sector-composition-on-rebalance`: the sector sub-select ran before
      `GRAPH ?g`, so a holding without `:classifiedAs` or without
      `:holdingAsset` disappeared instead of joining `unclassified`. The
      holding and CASH patterns now stay inside `GRAPH ?g` with
      `OPTIONAL { ?row :holdingAsset ?asset }`, followed by the
      `COALESCE` sentinel, the `SELECT DISTINCT` sector sub-select and the
      `unclassified` bucket. A dedicated fixture uses AAA 0.60, QQQ 0.30 (a
      catalog asset without a sector), ZZZ 0.05 (no `:holdingAsset`) and CASH
      0.05, and asserts Financials 0.60, `unclassified` 0.35 and
      0.60 + 0.35 + 0.05 = 1. → step 1.
- [x] **T-306** *(done 2026-11-04, PR #120 review)* Add the tagged
      `sector-of-asset` query for Q5: ticker parameter (`VALUES ?ticker {
      "AAA" }`), company name when present, industry label, sector label and
      the sector individual's Spanish `rdfs:comment`/`skos:definition` when
      present; point Q5's "Where" cell at it. The test covers AAA (classified
      catalog asset), AAPL (one row despite being declared in both graphs) and
      an unclassified ticker (no row, as documented). → step 2.
- [x] **T-307** *(done 2026-11-04, PR #120 review)* Re-run the checks and
      record the new counts: `uv run pytest -q` = **1074 passed, 56 deselected
      in 800.19 s**; `tests/test_query_catalog.py` = 55 passed in 4.02 s;
      `uv run mypy --config-file=.code_quality/mypy.ini` = success, 77 files;
      `uv run pre-commit run --files <changed files>` passes all hooks. No
      GraphDB write or reload, no merge or rebase. → step 3.
- [x] **T-308** *(done 2026-11-04, merge of PR #122)* Re-measure the reloaded
      catalog read-only against `portfolio_test`: `urn:graph:universe:2026-Q4`
      holds **643 `:Asset` individuals, 584 with `:classifiedAs`** (59
      unclassified), plus the five `reference.ttl` assets. Replace the
      pre-Work-item-23 648/579 counts in §6 and the §7 loader note with those
      measured values; `tests/test_query_catalog.py` = 57 passed in 3.16 s;
      `uv run pre-commit run --files <changed files>` passes all hooks. No
      GraphDB write or reload. → step 4.


## Work item 26 — Project the backtest selection side

*From T-209 and the report questions "why did X (not) make the Top-30" / "which vetoes were in
force". See `PLAN.md` Work item 26. Task IDs T-320–T-349.*

- [x] **T-320** *(done 2026-11-04: `SELECTION_VIEWS`, `project_selection` and `run_selection` in
      `src/projection/backtest.py`; `SelectionCycle`, schemes, configured/effective
      `WeightComponent`s, `AttractivenessSnapshot`s and `Veto`s; `load_selection_catalog`/
      `resolve_rule`; `universe_assets` unchanged; unlinked rows counted per view.)* Implement the
      selection projector over `v_cycle_run`, `v_weight_scheme`, `v_weight_component`,
      `v_cycle_ranking`, `v_cycle_ranking_component` and `v_veto`.
- [x] **T-321** *(done 2026-11-04: `urn:graph:derived:backtest:selection:{label}:{P<n>}:{run}` and
      `_BACKTEST_SELECTION_TARGET` in `src/kg_store/gate.py`; the m018 target is unchanged;
      `tests/test_kg_gate.py` and `tests/test_backtest_selection.py` cover the accepted and
      malformed names.)* Add the sibling graph name and the gate's target branch.
- [x] **T-322** *(done 2026-11-04: `:SelectionCycle`, `:cycleType`, `:rankingTicker`, `:vetoTicker`,
      `:vetoRulesJson`, `:rankingOfCycle`, `:hasEffectiveWeight`, `:rankPosition`,
      `:selectedForBook`, `:vetoedAtRanking`, `:targetWeight` and `:componentValue`; the
      `SelectionCycleShape`, `BacktestRankingShape` and `EffectiveWeightComponentShape`; tbox 52
      classes / 39 leaves, shapes 34, FR-001 **4431 quads**, load plan **4708**. `kg_target_schema`
      mirrors the new terms; synthetic positive/negative cases in `tests/test_ontology_v18.py`.)*
      Add the minimum schema, shapes and counts.
- [x] **T-323** *(done 2026-11-04: `src/projection/project_selection.py` and
      `cli/project_selection.py`, `database_argument` shared with the m018 CLI; dry run by default,
      `--write`, `--to-production`, duplicate-graph guard; `tests/test_project_selection.py` and
      `tests/test_cli_project_selection.py`.)* Add the sibling CLI and its command-policy tests.
- [x] **T-324** *(done 2026-11-04: the fixture now has the six upstream views and seven synthetic
      cycles; `tests/test_backtest_selection.py` covers the LIQUIDITY_DISTRESS `_v11` resolution,
      an unknown rule id, the BRK.B UNSCORED placeholder, unlinked FBIN/GAP-style tickers,
      non-completed runs, the m018/selection sibling names and SHACL.)* Add hermetic fixtures and
      tests for every nullable case.
- [x] **T-325** *(done 2026-11-04: `tests/test_selection_real.py`, opt-in under `BACKTEST_DB` and
      `-m integration`; P1/P2/P3 row and individual counts, unlinked counts and the SHACL-valid
      graph.)* Add the opt-in real-database row-count test.
- [x] **T-326** *(done 2026-11-04, read-only dry runs: P1 42,700 rows/individuals, 321,281 triples,
      86.25 s, 1,213,756 KB peak RSS; P2 41,259, 309,726, 81.64 s, 1,153,048 KB; P3 45,440,
      342,929, 90.11 s, 1,282,204 KB; each `pyshacl` conforms; no store write/reload.)* Run the real
      dry runs and record rows, individuals, triples, timing and peak RSS.
- [x] **T-327** *(done 2026-11-04: `docs/06` §1.11, `docs/07`, `docs/08`,
      `docs/graphdb-setup.md`, `schema/README.md`, `README.md`, `SPEC.md`; the query catalog adds
      `selection-ranking-at-rebalance`, `selection-vetoes-in-force` and
      `selection-why-not-top30`, and Q9/B5 are `Today`.)* Update docs and the query catalog.
- [x] **T-328** *(done 2026-11-04: T-209 closed, this section cut to `CHANGELOG.md`, Work item 26
      closed in `PLAN.md`. Verification after merging PR #120/#122: `uv run pytest -q` = 1164
      passed, 57 deselected in 841.85 s; `uv run mypy --config-file=.code_quality/mypy.ini` =
      success, 87 files; the pinned pre-commit hooks pass on every changed file; FR-001 parse =
      4431 quads and `pyshacl` conforms; the opt-in real-database test passes for P1, P2 and P3;
      the dry-run triple counts are unchanged. The veto-in-force reconciliation is recorded in
      `PLAN.md` Work item 26: all disagreements are HARD rules represented only by the `HARD`
      marker, 0 extra.)* Close T-209 and record the rule-resolution convention.

**Follow-up 2026-11-04 (T-351).** The selection projector now uses the shared
`projection.asset_link` rule: exact ticker, else the one loaded `:Asset` with the same CIK from
`v_ticker_history` of the same source database, else unlinked and counted. The old unlinked rows
(ranking 34/0/2 and veto 9/2/3 across P1/P2/P3) are 0. The new dry runs are P1 **321,324** triples
(56.45 s, 1,214,004 KB), P2 **309,728** (53.94 s, 1,155,632 KB) and P3 **342,934** (58.35 s,
1,285,948 KB), all SHACL-valid; the +43/+2/+5 triples are exactly the recovered links. The m018
projector and `universe_assets` are unchanged.

## Work item 27 — Project ticker history and the orchestrator views (2026-11-04)

Design: `PLAN.md` Work item 27. This work item closes T-208.

**Validation.** `uv run pytest -q`: **1225 passed, 58 deselected, 3639 warnings in 818.67 s**.
`uv run mypy --config-file=.code_quality/mypy.ini`: success, 96 source files. `uv run pre-commit
run --all-files`: all hooks passed. Real read-only dry runs over `rule_P1/P2/P3.db`: 21
`v_ticker_history` rows, 198 triples and 21 individuals per database, 17 exact + 4 same-CIK asset
links, 0 unlinked, 4 multi-date evidence cells omitted, 0 orchestrator rows and no graph written;
`pyshacl` conforms in 1.25–1.42 s at ~73 MB peak RSS. `tests/test_reference_real.py` passes with
`REFERENCE_DB=rule_P1.db` and the real universe catalog. The selection dry runs after the same link
rule are P1 321,324 / P2 309,728 / P3 342,934 triples with 0 unlinked ranking/veto rows (before:
34/0/2 and 9/2/3). No GraphDB write or reload was made; the pilot `financial.db` and the task's
`base.db`/`scored_rule.db` paths are not v18 sources in this checkout.

- [x] **T-350** *(design first; commit before any code)* Record the read-only measurements (21
      ticker rows, 8 NULL `valid_to`, 0 orchestrator rows, 17 exact + 4 unique-CIK links, 0
      unlinked) and the graph/IRI/nullability/asset-link design in `PLAN.md` Work item 27.
      → step 1.
- [x] **T-351** Add the shared asset-link rule (exact symbol, else exactly one `:Asset` under the
      same CIK, else unlinked and counted) with hermetic tests, including `FBIN`→`:FBHS` and
      `GAP`→`:GPS`. Applied in this projector and in Work item 26's selection projector (the
      latter's unlinked ranking/veto rows went from 34/0/2 and 9/2/3 to 0). → step 2.
- [x] **T-352** Project `v_ticker_history` into
      `urn:graph:derived:ticker-history:{label}:{snapshot_date}`, with snapshot-qualified IRIs,
      the inclusive `validFrom`/`validTo` interval, optional evidence, and the latest-symbol check.
      → step 2.
- [x] **T-353** Project `v_orchestrator_run`/`v_orchestrator_step` into one
      `urn:graph:derived:orchestrator:{label}:{run_id}` per run, natural keys only, and make the
      empty case say there is nothing to write. → step 2.
- [x] **T-354** Add `cli/project_reference.py` (logic in `src/projection/project_reference.py`)
      following `cli/project_backtest.py`: repeatable `--db LABEL=PATH`, `--as-of`, dry run by
      default, `--write`, `--to-production`, exit codes 0/1/2. → step 3.
- [x] **T-355** Extend `kg_store.gate.check_target` with the ticker-history and orchestrator
      append-only patterns and add accepted/refused cases to `tests/test_kg_gate.py`. → step 3.
- [x] **T-356** Hermetic fixtures and tests for the projector, the link rule, the empty
      orchestrator case, the CLI and the new catalog query. → step 4.
- [x] **T-357** Add an opt-in real-database test (`REFERENCE_DB`, `integration` marker) and run
      the real dry runs; record rows, individuals, triples, exact/CIK/unlinked links, SHACL and
      timings. → step 5.
- [x] **T-358** Update `docs/06`, `docs/07`, `docs/08`, `docs/graphdb-setup.md` and
      `docs/backtest-load-runbook.md`. → step 6.
- [x] **T-359** Add the tagged, tested "which symbol did company X use on date D" query to
      `docs/reports-agent-query-catalog.md`, move the rename question from `After T-208` to
      `Today`, and keep both sides when merging `origin/master` (#120/#122). → step 6.
- [x] **T-360** Mark T-208 and Work item 27 done, move the task block to `CHANGELOG.md`, update
      the asserted counts and run `pytest`, `mypy` and the pinned pre-commit hooks. → step 7.

## Work item 29 — Prove the whole final load in one run

*From the final-load handoff: the selection graphs had no verifier and the load was still a manual
sequence. See `PLAN.md` Work item 29. Task IDs T-390–T-419 (T-390–T-398 used).*

- [x] **T-390** *(done 2026-11-04: `project_selection_source` in `src/projection/backtest.py`,
      shared by `run_selection` and the verifier; `verify` dispatches on the graph prefix so the
      m018 path and its 21 checks are unchanged.)* Add the selection source projection and the
      graph-name dispatch to `src/projection/verify_backtest.py`/`cli/verify_backtest.py`.
- [x] **T-391** *(done 2026-11-04: `selection_graph_identity`; `SelectionCycle` identity check;
      total triples; `SelectionCycle`, `AttractivenessSnapshot`, `AttractivenessWeightScheme`,
      `Veto`, configured `WeightComponent` and effective `WeightComponent` counts.)* Implement the
      selection graph identity, triple and individual checks.
- [x] **T-392** *(done 2026-11-04: UNSCORED/UNPRICED placeholder count, distinct
      `:attractivenessOfAsset`/`:vetoOfAsset` links, `v_cycle_ranking`/`v_veto` unlinked ceiling
      and vetoes grouped by resolved rule IRI.)* Implement the placeholder, asset-link and
      resolved-rule group checks.
- [x] **T-393** *(done 2026-11-04: every TOPN `BookRebalance` `:cycleRunId` in the m018 sibling
      must have a `SelectionCycle`; `MARKOWITZ_BASE` is asserted to have none; a missing m018
      graph fails the check.)* Add the cross-graph check.
- [x] **T-394** *(done 2026-11-04: `src/projection/load_run.py` and `cli/load_run.py`;
      `--label` + repeatable `--db` or `--dir` of `*_P<number>.db`, optional `--contract`,
      `--write`, `--to-production`; both dry runs, m018 writes then selection writes, verifier for
      every graph, final table, duplicate-input refusal and one-graph drop commands.)* Build the
      one-command loader.
- [x] **T-395** *(done 2026-11-04: `tests/test_verify_backtest_selection.py`, in-memory
      `rdflib.Dataset` pass case, missing class, altered count, missing link, missing placeholder
      marker, wrong label, wrong graph name and missing cross-graph cycle; the m018 tests still
      pass unchanged.)* Add the selection verifier tests.
- [x] **T-396** *(done 2026-11-04: `tests/test_load_run.py` covers the ordered stages, a
      verification failure that stops the sequence, the printed drops, a successful write table and
      a write failure after the m018 write; `tests/test_cli_load_run.py` covers the subprocess
      contract, a synthetic dry run, `--dir` discovery and the production guard.)* Add the loader
      sequence and CLI tests.
- [x] **T-397** *(done 2026-11-04, read-only: the real `rule_P1.db` m018 and selection projections
      in an in-memory Dataset pass 21/21 checks over 209,886 triples and 15/15 over 321,324
      triples; `cli/load_run.py` dry runs measured P1 93.2 s / 1.16 GB, P2 90.2 s / 1.10 GB and P3
      101.0 s / 1.22 GB; selection rows 42,700 / 41,259 / 45,440 and triples 321,324 / 309,728 /
      342,934; no store contacted.)* Verify the real P1 projections in memory and re-measure the
      three dry runs.
- [x] **T-398** *(done 2026-11-04: `docs/backtest-load-runbook.md` rewritten around the
      one-command flow with the manual fallback, both graph names in naming/verification/rollback
      and the failure table; `README.md` command table, `docs/graphdb-setup.md`, `SPEC.md`
      FR-009/FR-011, `PLAN.md` Work item 29 and this section updated; this section cut to
      `CHANGELOG.md`.)* Update the docs and close Work item 29.
- [x] **T-399** *(done 2026-11-04, follow-up to the merged Work item 30: `gate.ingest` is now
      `gate.write(db, gate.plan(...))`; `--check-store` and the `--delta` dry run use the same
      plan, which runs the shape/context validation plus checks 2, 6 and 7; they report
      `would-be-written`, `already-in-the-store` (skipped) or `refused`. `tests/test_kg_gate.py`
      covers a skip, an existing individual and a closing-state refusal; `tests/test_store_check.py`
      covers all three reported outcomes.)* Make the pre-flight run every store-dependent gate
      check.

## Work item 30 — Gate context falls back to the relation range

*From the first real selection write (portfolio_test, 2026-11-04). See `PLAN.md` Work item 30.
Task IDs T-420–T-439.*

- [x] **T-420** *(done 2026-11-04: `context_predicates` keeps the `sh:class` rule first and falls
      back to the used relation's `rdfs:range` from the TBox; no `sh:class` and no range still
      fetches only `rdf:type`. Docstring updated.)* Implement the fallback.
- [x] **T-421** *(done 2026-11-04: `tests/test_gate_context_fallback.py` uses an in-memory Dataset
      as the store and the real `fetch_context`; the selection batch conforms, the GUARD mutation
      is refused, and `tickerHistoryAsset`/`holdingAsset`/`guardAsset` keep their AssetShape
      predicates.)* Add the real-fetch regression tests.
- [x] **T-422** *(done 2026-11-04: `--check-store` in the three projection CLIs, shared
      `projection.store_check`, `gate.validate_against_store`; it reads with SELECT only, writes
      nothing and refuses `--write`/`--to-production`.)* Add the read-only store check.
- [x] **T-423** *(done 2026-11-04, read-only against `portfolio_test`: selection P1/P2/P3, m018
      P1/P2/P3 and ticker-history P1/P2/P3 all `would be accepted`; no write/reload.)* Verify
      against the live test repository.
- [x] **T-424** *(done 2026-11-04: `PLAN.md` Work item 30, `SPEC.md` FR-010, `docs/07` context rule,
      `docs/backtest-load-runbook.md` §4a, `CHANGELOG.md`.)* Update the docs.
- [x] **T-425** *(done 2026-11-04: `uv run pytest -q` = 1264 passed, 58 deselected in 775.75 s;
      `mypy` = success, 99 files; pinned pre-commit and FR-001 pass; the real check-store results
      above.)* Run the checks and record them.

## Work item 31 — Pre-flight every graph before `load_run` writes

*From the first real backtest load (`portfolio_test`, 2026-11-04). See `PLAN.md` Work item 31.
Task IDs T-440–T-459 (T-440–T-446 used).*

- [x] **T-440** *(done 2026-11-04: the design is in `PLAN.md` Work item 31 before the code.)*
      Record the pre-flight design and the no-partial-write rule.
- [x] **T-441** *(done 2026-11-04: `RunPlan`, `plan_run`, `plan_selection` and `write_run` in
      `src/projection/backtest.py`; the plan functions call `gate.plan` and write nothing,
      `write_run` applies those plans with `gate.write` and never plans twice.)* Split planning from
      writing.
- [x] **T-442** *(done 2026-11-04: `src/projection/load_run.py` plans every m018 and selection graph
      of every database before any write; a refusal stops with nothing written and lists every
      graph and gate message; `already-in-the-store` is skipped; the final table has a status
      column; `--check-store` runs only the pre-flight and refuses `--write`/`--to-production`.)*
      Add the pre-flight and `--check-store`.
- [x] **T-443** *(done 2026-11-04: `tests/fixtures/dataset_store.py` implements `select_terms` and
      `add`, so `tests/test_load_run.py` runs the real `gate.plan`/`gate.write` path with typed
      assets and `schema/rules.ttl`; it covers the accepted-write-and-verify case, a later refusal
      with no earlier write, an already-stored skip, `--check-store` writing nothing, and a write
      failure after the pre-flight with the written/in-doubt report and drops.)* Add the real-gate
      tests.
- [x] **T-444** *(done 2026-11-04: `docs/backtest-load-runbook.md` gained the pre-flight,
      `--check-store`, status table, write-failure report and free-disk prerequisite; `README.md`
      command table, `SPEC.md` FR-010/FR-011 and `PLAN.md` updated.)* Update the docs.
- [x] **T-445** *(done 2026-11-04, read-only against `portfolio_test`: the three `rule_P*.db` files
      reported all six m018/selection graphs as `already-in-the-store`, exit 0, 273.193 s; the dry
      run over the same files took 280.967 s and reported 209,886/196,840/222,449 m018 and
      321,324/309,728/342,934 selection triples. No GraphDB write or reload.)* Verify read-only.
- [x] **T-446** *(done 2026-11-04: `uv run pytest -q` = 1307 passed, 59 deselected, 5114 warnings
      in 812.16 s (13:32); `mypy` = success, 106 source files; pinned pre-commit hooks pass on the
      changed files; FR-001 remains 4431 quads and conforms.)* Run the checks and record them.

## Work item 32 — Record the portfolio_test live load

*From the first real catalog and backtest writes in `portfolio_test`, 2026-11-04. See `PLAN.md`
Work item 32 and `docs/graphdb-setup.md`, "Live load record, portfolio_test, 2026-11-04".
Task IDs T-460–T-469.*

- [x] **T-460** *(done 2026-11-04: `docs/graphdb-setup.md` records the schema reload, the catalog,
      the m018 and selection graphs and the ticker-history snapshot with the measured numbers.)*
      Record the live load.
- [x] **T-461** *(done 2026-11-04: the same section records Lesson 1 (the gate's context fetch and
      Work item 30's `rdfs:range` fallback/`--check-store`) and Lesson 2 (GraphDB's 5% floor and the
      trim/compact procedure).)* Record the lessons.
- [x] **T-462** *(done 2026-11-04: `docs/backtest-load-runbook.md` §1a adds the `df -h` free-space
      check on the mounted data directory, keeping several GB beyond the 5% line.)* Add the
      free-disk prerequisite.
- [x] **T-463** *(done 2026-11-04: `SPEC.md` FR-008 and FR-009 carry the live `portfolio_test`
      results, and FR-010 records the context refusal that preceded Work item 30.)* Update SPEC.
- [x] **T-464** *(done 2026-11-04: T-215 and T-226 are checked with their evidence; `PLAN.md` Work
      items 4 and 19 point at this work item.)* Close the first-write tasks.
- [x] **T-465** *(done 2026-11-04: `PLAN.md` Work item 32 and the status summary.)* Record the work
      item.
- [x] **T-466** *(done 2026-11-04: this section cut from `TASKS.md`; the status line points here.)*
      Move the closed tasks.
- [x] **T-467** *(done 2026-11-04: the runbook and graphdb-setup references to the first write and
      the verifier now point at the live record.)* Reconcile the cross-references.
- [x] **T-468** *(done 2026-11-04: `uv run pytest -q`, `mypy` and the pinned pre-commit hooks pass;
      no schema file changed.)* Run the checks.
- [x] **T-469** *(done 2026-11-04: T-380 (first real delta `--write`) remains the maintainer's; no
      production write was made.)* Report the residual work.

## Work item 33 — Open the vocabulary for the final backtest (2026-11-04, T-470–T-477)

**Goal**: make the ontology, SHACL shapes, ingest gate and rule catalog accept the final backtest
before any data arrives. Vocabulary only: the projector, verifier and loader kept their behaviour
except `WINDOW_PATTERN`, `SEGMENT_PATTERN`, `ARMS` and the gate's derived-graph targets.

- [x] **T-470** Recorded the design in `PLAN.md` Work item 33 before any code (first commit).
- [x] **T-471** `windowId` is `^[PH][0-9]+$` and `segment` `^[PH][0-9]+[a-z]?$` in every
      `sh:pattern`, the tbox comments, `projection.backtest`, both gate graph patterns,
      `projection.load_run`'s `*_<window>.db` matcher, `kg_target_schema.ttl` and the docs. `P1`–`P3`
      still work; `H1`–`H3` and `P2a`/`P2b` conform.
- [x] **T-472** `MARKOWITZ_BASE_GUARD` joined every arm `sh:in` and `ARMS`; the two non-guard arms
      keep NULL `guardLayers`, both guard arms carry `[1, 3, 4]`.
- [x] **T-473** `:Rule_L1_BP_STOP`/`:Rule_L1_BP_REENTRY` are layer-1 GUARD rules valid from
      2026-11-04, with the handoff comments verbatim. `:alertThreshold` is required for every other
      alert and forbidden (zero triples) for the two Basing Points rules through one node-level
      `sh:xone`, because the threshold is an individual asset's stop price level.
- [x] **T-474** `:ExchangeTradedFund rdfs:subClassOf :Asset`, Spanish label `ETF núcleo`, no FIBO
      mapping (the pinned 2026Q2 slice has no exchange-traded-fund term). `:SPY` is declared in
      `reference.ttl` without CIK, membership or classification; `AssetShape` has an ETF branch and
      ordinary assets keep the CIK/closed-membership rule. The catalog is 643 written assets plus
      six in `reference.ttl` = **649**.
- [x] **T-475** `:BacktestRun` (label + window) and `:RunConfiguration` (one per label) with their
      shapes; the configuration carries the code commit, PR, results document and optional
      `configId`/`configStatus`, with the frozen English body text verbatim, hard line breaks
      included, in `rdfs:comment`. `urn:graph:derived:backtest:meta:{label}` is accepted by the gate
      as append-only and refused on a second write; it cannot collide with the m018/selection names
      and no label is reserved.
- [x] **T-476** Hermetic tests: `H1`/`H2`/`H3`, `P2a`/`P2b`, all five arms, both threshold cases,
      ETF vs ordinary asset, metadata shapes, the configuration-body round trip, and the meta graph
      accepted once/refused twice.
- [x] **T-477** Updated the docs and every asserted count; FR-001 is
      **4634 quads (55 classes, 41 disjoint leaves, 36 named shapes); conforms: True**, and the load
      plan is **4911 asserted triples**.

**Scope notes.** The projector, verifier and loader were not changed beyond the named constants
(`WINDOW_PATTERN`, `SEGMENT_PATTERN`, `ARMS`, and the `projection.load_run` directory matcher, which
is the same window regex). `kg_target_schema.ttl` mirrors the patterns, arm list, alert list and
threshold condition. `protege-view.ttl` is generated and was not regenerated.

**No GraphDB write or reload was made.** Pilot data stays valid: its windows are `P1`–`P3`, its
arms are a subset of the final four, its alerts are the fixed-threshold rules, and it has no
Basing Points alert. The user reloads the schema afterwards with `cli/load_schema.py`, then
`cli/verify_store.py`.

**Verified 2026-11-04**: `uv run pytest -q` = **1362 passed, 59 deselected, 5114 warnings in
1232.29 s (20:32)**; `mypy` = success, **106 source files**; the pinned pre-commit hooks pass on
every changed file; FR-001 remains **4634 quads; conforms: True**.

## Work item 34 — Final-backtest correctness for the projectors and the verifier (2026-11-05, T-500–T-512)

**Goal**: make the m018 and selection projectors and the read-only verifier correct for the final
backtest's Basing Points alerts, core ETF `SPY`, period summaries and six-window/four-arm shape,
without touching the loader (Work item 35) or GraphDB.

- [x] **T-500** Recorded the design in `PLAN.md` Work item 34 before any code (first commit).
- [x] **T-501** `_alerts` omits `:alertThreshold` for every `L1_BP_*` alert and keeps the required
      fixed-parameter threshold on every other GUARD rule. The only other value-bearing columns on a
      layer-1 Basing Points row (`value`, `weight_before`/`weight_after`) are already masked by the
      view, so no further projector masking is needed.
- [x] **T-502** `AssetInfo` carries the loaded RDF type(s); `universe_assets` merges
      `schema/reference.ttl` before the universe rows (the universe wins on CIK/stints, a
      reference-declared type is kept), so `SPY` links by exact symbol. `validation_context` writes the real type (`:ExchangeTradedFund`)
      and the projection/verifier reference context does the same.
- [x] **T-503** Hermetic `SPY` holding/alert/action tests; `gate.plan` (the `--check-store` path)
      accepts a `:holdingAsset`/`:guardAsset` to `:SPY` with the store's reference context, through
      `:holdingAsset`'s `sh:class :Asset` and the superclass expansion of `:ExchangeTradedFund`.
- [x] **T-504** The verifier recomputes every period summary's `:nGuardActions` from the `APPLIED`
      guard actions whose `decision_date` is inside `[dateFrom, dateTo]`, once from the source and
      once from the graph, and requires both to equal the stored value. `:decisionDate` was already
      projected on `:GuardAction` and already required by the shape, so no schema property was
      added. The pilot's day-before-window action is correctly excluded.
- [x] **T-505** The verifier counts the Basing Points alerts, requires the source count, and
      requires zero `:alertThreshold` triples on them.
- [x] **T-506** New hermetic `final_scenario_rows`/`final_backtest_db` fixture: six date-ordered
      windows, four arms, `P2a`/`P2b`, `SPY`, Basing Points alerts and a before-window action. Both
      projectors and the verifier run over every window (`tests/test_final_backtest.py`).
- [x] **T-507** Read-only dry runs over `rule_P1/P2/P3.db` with label `rule`: the m018 and selection
      triple counts are unchanged from the recorded 2026-11-04 runs (no new property was needed),
      and the verifier over in-memory projections passes 23/23 m018 and 15/15 selection checks on
      every database, including the two new m018 checks.
- [x] **T-508** Comments/definition only in `tbox.ttl` (and the `kg_target_schema.ttl` mirror) for
      `:selectedForBook` (candidate-pool membership), `:targetWeight` (pool weight, never portfolio
      weight), `:rankPosition` (counts vetoed names), `:vetoSeverity` (per-row authoritative), the
      related `:topN`/`:finalTargetWeight` clarifications, and the Spanish `:StrategyBook`
      definition (both "selección Top-30" occurrences become "selección del pool Top-N del
      ciclo"). The `test_ontology_v18` expected text and `test_fibo_slice`'s v18 Spanish-text hash
      move with it. No shape, term or count changed.
- [x] **T-509** The first decision date of a window has no weight rows on that date by design; a
      hermetic test proves the verifier does not report that as a gap.
- [x] **T-510** `SPEC.md` FR-009, `docs/06`, `docs/08`, the query catalog, the load runbook,
      `schema/README.md`, `PLAN.md`, `TASKS.md` and this record are consistent with the code.
- [x] **T-511** Checks: `uv run pytest -q`, `mypy`, the pinned pre-commit hooks, FR-001 and the
      read-only pilot verification all pass; the measured evidence is in `PLAN.md` Work item 34.
- [x] **T-512** Added `tests/test_guard_layers.py` and fixture helpers: a Top-N guard arm with
      `guard_layers "[1]"` and one with `"[1, 4]"` (no L3_VOL alert; no L4_DD in the first), and
      two portfolio-level L3_VOL alerts with different thresholds on different dates. The projector
      and verifier pass all three cases; no production code assumed a fixed layer set, so no code
      change was needed.

**Scope notes.** `src/projection/load_run.py`, `cli/load_run.py`, the gate and the schema structure
were not changed (no new property: `:decisionDate` already existed on `GuardAction`). The schema
edit is comments and one Spanish `skos:definition` only, but **the user must reload the schema**
afterwards with `cli/load_schema.py`, then `cli/verify_store.py`, so the store holds the new
literals; `protege-view.ttl` was not regenerated. `SPY` is linked through the already-loaded
`urn:graph:reference`.

**Verified 2026-11-05**: `uv run pytest -q` = **1479 passed, 59 deselected, 8779 warnings in
1124.41 s (18:44)**; `mypy` = success, **118 source files**; the pinned pre-commit hooks pass on
every changed file; FR-001 is the merged **4913 quads; conforms: True**. No GraphDB write or reload
was made by the agent; the user reloads the schema afterwards.

## Work item 35 — Load a six-window delivery with its manifest and configuration (2026-11-05, T-520–T-529)

**Goal**: make `cli/load_run.py` load the final backtest's six date-ordered windows from one
delivery folder, prove its `SHA256SUMS` and `config_<label>.md` before any database read, write the
one `:BacktestRun`/`:RunConfiguration` metadata graph per label, and verify all of it read-only,
without writing anything until every pre-flight passes.

- [x] **T-520** Recorded the design in `PLAN.md` Work item 35 and `TASKS.md` before any code.
- [x] **T-521** `src/projection/delivery.py` discovers `<label>_<window>.db` for
      `P1/H1/P3/H2/P2/H3`, rejects an unknown window or a missing `--windows` entry, verifies
      `SHA256SUMS` in 1 MiB streaming chunks before opening a database, compares hashes
      case-insensitively and stores them lowercase, and orders the windows by `v_book.d_start`/
      `d_end` (`P3` before `P2`).
- [x] **T-522** `config_<label>.md` is read by a minimal front-matter parser: every scalar is a
      string, required `label`/`code_commit`/`pr`/`results_doc`, optional `config_id`/`status`,
      unknown keys are warnings, the label must equal `--label` and the file name, and the body is
      kept byte for byte after the one blank separator line.
- [x] **T-523** `src/projection/run_metadata.py` builds the deterministic
      `:BacktestRun_{label}_{window}`/`:RunConfiguration_{label}` Turtle, plans and writes it
      through the ingest gate, and verifies it read-only: exact triples, one run per window, one
      configuration, every link, each manifest hash/file/date/run id and the configuration body.
- [x] **T-524** `projection.load_run` verifies the delivery before any database read, processes
      the windows chronologically, plans every m018, selection and metadata graph before the first
      write, writes them in that order, then verifies all of them. `--no-manifest --no-config` is
      the pilot legacy mode and builds no metadata graph; a present delivery file is never ignored.
- [x] **T-525** Per-step and per-window timings, the read-only `--min-free-pct` probe with its
      `df -h` fallback, the GraphDB HTTP 500 low-disk translation naming the graph and its
      one-graph `DROP GRAPH`, and the 30-minute `STOP AND ASK upstream` summary are in place.
- [x] **T-526** `tests/test_load_run_delivery.py` covers the six-window folder, manifest
      match/mismatch/missing entry/missing file, unknown and missing windows, config label
      mismatch and verbatim body, chronological order, the metadata graph through the in-memory
      store, the second-write refusal, the low-disk message and the 30-minute flag.
- [x] **T-527** The runbook, `graphdb-setup.md`, `README.md` and `SPEC.md` record the six-window
      procedure, the delivery files, the metadata graph, the disk rule and production-only-`final`.
- [x] **T-528** Real read-only check: the store-free pilot dry run over
      `/workspaces/thesis/scratch/final/runs` processed P1 → P3 → P2 in 376.4 s; the explicit
      `--check-store --no-manifest --no-config` run against `portfolio_test` took 366.2 s and
      reported the six m018/selection graphs as `already-in-the-store`. No GraphDB write was made.
- [x] **T-529** *(done 2026-11-05)* Merged-tree full suite `uv run pytest -q` = **1400 passed,
      59 deselected, 8081 warnings in 1212.64 s (20:12)**; focused load-run suite = **40 passed in
      36.88 s**; merged targeted run = **254 passed in 785.01 s**; `mypy` = success, **110 source
      files**; the pinned pre-commit hooks pass on every changed file.

**Residual work**: the real candidate/final loads remain the maintainer's (the agent never writes
GraphDB). Production receives only the `final` label.

**Verified 2026-11-05 (merged with `origin/master`)**: the full suite, focused load-run suite and
merged targeted run pass as above; the real read-only pilot dry run processed P1 → P3 → P2 in
376.4 s and the `--check-store --no-manifest --no-config` run against `portfolio_test` took 366.2 s,
reporting the six m018/selection graphs `already-in-the-store`. No GraphDB write or reload was made.

## Work item 36 — Make the query catalog independent of the pilot (T-550–T-569)

**Status: closed 2026-11-05.**

**Why**: `docs/reports-agent-query-catalog.md` still describes the pilot as if it were the only
run: three windows named `P1`/`P2`/`P3`, three arms, the label `rule` as a literal filter, and
sector rollups that treat every asset without a GICS class as `unclassified`. The final backtest
has six date-ordered windows (`P1`, `H1`, `P3`, `H2`, `P2`, `H3`; `P3` precedes `P2`), four arms
including `MARKOWITZ_BASE_GUARD`, the same four-arm vocabulary but a different label, a core ETF
(`SPY`), Basing Points GUARD rules, and run metadata dated November 2026. A reports agent that
follows the current text would filter for a label and windows that do not exist, hide `SPY` in an
`unclassified` bucket, and misread the selection side (`selected` is candidate-pool membership, not
the names held; `target_weight` is not a book weight). Work item 33 opened the vocabulary; this
work item makes the catalog and its test ready for the final data without writing any result
number into the documentation.

**Decisions**:

1. **Parameters first.** Every per-run backtest and selection query binds the run label and the
   window (and the arm where the question is per-arm), with a discovery query for each choice:
   run labels present, windows present per label with `MIN(:dateFrom)`/`MAX(:dateTo)` ordered by
   date (never by name), arms present, rebalance dates, and the decision/warm-up cycle dates. `rule` remains
   only an example label; no text says "three windows" or that `P1`–`P3` are the only windows.
2. **Two kinds of cycle.** A decision cycle is a `SelectionCycle` referenced by a `BookRebalance`
   through the shared `:cycleRunId` (same `:runLabel` and `:windowId`); a warm-up cycle is one no
   rebalance references. The book-to-cycle join is `:cycleRunId`, never a date coincidence. Only
   the Top-N arms carry it; both Markowitz arms leave it NULL on purpose and link through
   `:quantPortfolioId`/`:riskModelId` instead. The discovery queries list decision and warm-up
   cycles separately, so an unqualified "cycle dates" answer cannot mix them.
3. **Core ETF.** The three sector rollups (layer-1 cuts by sector, composition at a rebalance,
   coverage of holdings) map an `:ExchangeTradedFund` (`SPY`) to the class's Spanish label
   `ETF núcleo`. They never drop it and never count it as `unclassified`; an ordinary asset with no
   `:classifiedAs` still lands in `unclassified`. The query that lists assets without a sector
   excludes ETFs explicitly. `sector-of-asset` returns the same label for `SPY`.
4. **Held names and the pool.** `:selectedForBook` is membership of the candidate pool
   (`v_weight_scheme.top_n`, 60 in the final run), not the names held. A book's holdings are
   `:BookWeightDaily` rows with `:finalTargetWeight > 0` of the Top-N arms. Composition and
   "what did the book hold" queries use `:finalTargetWeight`, never the ranking's
   `:targetWeight`; that ranking value is the cycle's own pool weight and is not a portfolio
   weight. `:rankPosition` counts vetoed names, so a selected name can have rank greater than the
   pool size. "Not selected" means vetoed or ranked below the last selected name, never a fixed
   "Top-30".
5. **Semantics that look like gaps.** Document each in the catalog, with a text test where a
   query cannot express it: `vetoRulesJson` keeps SOFT rule ids (they penalise the score) and
   collapses HARD vetoes to the marker `"HARD"`, so the HARD rule ids come from the in-force
   `Veto` predicate `raisedOn <= C AND (clearedOn IS NULL OR clearedOn > C)`; the orchestrator views
   are empty by design because backtests do not run through the orchestrator; `n_guard_actions`
   counts by decision date inside the segment, so a guard action decided on the last session
   before a window and effective on its first day is in `v_guard_action` but not in the window's
   summary; the final bases' knowledge date is the run date (November 2026) and vetoes resolve
   their rule by `:ruleId` against the definition valid then; only aggregates are published,
   never a price, return or price-derived value of an individual asset (`evidence_json` is not
   projected, layer-1 alert `value` is masked, and `L1_BP_*` alerts carry no `:alertThreshold`).
6. **Severity and the first decision date.** A veto's displayed severity is the veto's
   `:vetoSeverity`, never the rule's `:ruleSeverity` (`LEVERAGE_EXTREME` is HARD in the catalog but
   emits SOFT for a negative-equity asset with no usable credit metric). The first decision date
   of a window has no weight rows on that date; its weights appear on the execution date, which is
   not a gap.
7. **No result numbers.** The catalog and these docs carry no NAV and no result count of the pilot
   or the final run. Worked examples use only the hermetic fixture and say so; the dated pilot
   records already in `PLAN.md`/`CHANGELOG.md` stay untouched. The trend-filter and
   reference-return queries belong to Work item 37 and are not added here.
8. **The contract stays executable.** Every fenced `sparql` block keeps a tag and an expectation,
   and every `Today` query still runs against the hermetic dataset. The test gains a four-arm,
   date-ordered discovery dataset, decision and warm-up cycles, a Basing Points-alert check, and a
   sector dataset with `SPY`, one classified ordinary asset and one unclassified ordinary asset.

**Tasks**:

- [x] **T-550** Record this design in `PLAN.md` and `TASKS.md` before any code (first commit).
- [x] **T-551** Parameterise the backtest and selection queries by label/window/arm and add the
  discovery queries: run labels, windows by date range, arms (including `MARKOWITZ_BASE_GUARD`),
  rebalance dates, decision cycles and warm-up cycles.
- [x] **T-552** Add the `ETF núcleo` branch to the sector rollups, the `sector-of-asset` query and
  the ETF exclusion in the unclassified-assets query; keep ordinary unclassified assets counted.
- [x] **T-553** Document the veto-JSON, empty-orchestrator, `n_guard_actions`, knowledge-date and
  publication semantics with text tests.
- [x] **T-554** Correct the selection semantics (`selected`, `targetWeight`, `finalTargetWeight`,
  `rankPosition`) and rename the "why not Top-30" query to a pool-neutral name.
- [x] **T-555** Add and test the `:cycleRunId` book-to-cycle join and the decision/warm-up
  discovery, distinguishing both in the catalog text.
- [x] **T-556** State the per-veto severity rule and the first-decision-date weight rule, with a
  test over the fixture graph.
- [x] **T-557** Extend the hermetic fixtures/tests: `SPY` plus a classified and an unclassified
  ordinary asset, four arms, two date-ordered windows, and both cycle kinds.
- [x] **T-558** Update `docs/backtest-load-runbook.md` where it refers to the catalog, plus the
  related README/SPEC references; keep every count and status consistent.
- [x] **T-559** Run `pytest`, `mypy` and the pinned pre-commit hooks on the changed files; report
  counts and timings, and leave GraphDB untouched.

**Acceptance criteria**:

- No per-run query hardcodes `rule`, `P1`–`P3`, "three windows" or "Top-30"; every one binds a
  label and a window (and an arm where per-arm), and the discovery queries answer label, window
  date order, arm list, rebalance dates, decision cycles and warm-up cycles.
- `SPY` appears as `ETF núcleo` in the three sector rollups and in `sector-of-asset`, never as
  `unclassified` or dropped; an ordinary asset without `:classifiedAs` is still `unclassified`;
  the unclassified-assets query excludes ETFs.
- The five semantic notes are present and tested; no catalog or related doc states a NAV or a
  pilot/final result count as a fact, and no query selects `:alertThreshold` or `:evidenceJson`.
- Every tagged query runs against the hermetic dataset; the new fixture includes both cycle kinds
  and all four final arms.
- `uv run pytest`, `mypy` and the pinned pre-commit hooks pass; no GraphDB write or reload.

**Blocked on**: nothing. Work item 37 adds its own trend-filter/reference-return entries later.

**Verified 2026-11-05**: `uv run pytest -q` = **1382 passed, 59 deselected, 6870 warnings in 1515.14 s (25:15)**; `mypy` = success, **106 source files**; the pinned pre-commit hooks (ruff-check, ruff-format, mypy) pass on every changed file. No GraphDB write or reload was made; the schema bundle and FR-001 counts are unchanged because no schema file changed.

## Work item 37 — Project the upstream aggregates file (2026-11-05, T-570–T-599)

**Goal**: project upstream's per-segment `aggregates_<label>.json` into its own append-only graph,
with a whitelist parser, a strict `SHA256SUMS` check, a dry-run/default loader CLI and a read-only
source verifier. No daily series, price level or 210-session average is projected.

- [x] **T-570** Recorded the design in `PLAN.md` Work item 37 before any code (first commit).
- [x] **T-571** `src/projection/aggregates.py` parses only the declared top-level keys, source keys,
  dictionary tables/columns and row keys; it validates the label, windows, segments, states,
  references, dates, decimals, session counts and the exact two Top-N arms, refuses duplicate row
  identities, and validates (but never projects) `sources.spy_total_return_series_sha256`. The
  local manifest reader is strict `sha256sum` format (64 lowercase hex, two spaces, bare file name)
  and reports both hashes on a mismatch. Work item 35's ``delivery.read_manifest`` now exists, but
  it accepts uppercase hashes and the binary marker; the aggregates contract is stricter, so the
  reader stays local until the two contracts agree.
- [x] **T-572** Added `:AggregatesSet`, `:TrendFilterState` and `:ReferenceReturn` as three disjoint
  `:Observation` leaves with Spanish `skos:definition` and English comments. The new properties
  (`:trendWindow`, `:trendDecisionDate`, `:trendState`, `:cashFraction`, `:appliesToArm`,
  `:returnWindow`, `:returnSegment`, `:referenceDateFrom`, `:referenceDateTo`, `:nSessions`,
  `:referenceName`, `:referenceTotalReturn`, `:referenceMaxDrawdown`, `:aggregatesSet` and the six
  `:AggregatesSet` fields) avoid reusing a property whose `rdfs:domain` would entail a disjoint
  class; every row-property comment is the file's dictionary text verbatim. The three shapes close
  the label/window/segment/state/reference lists with `sh:pattern`/`sh:in`. Deterministic IRIs:
  `AggregatesSet_{label}`, `TrendFilter_{label}_{window}_{YYYYMMDD}`,
  `RefReturn_{label}_{segment}_{reference}`.
- [x] **T-573** Added the append-only `urn:graph:derived:backtest:aggregates:{label}` target to
  `kg_store.gate` and `docs/07`; it cannot collide with the m018/selection/meta names and no label
  is reserved. `tests/test_kg_gate.py` covers accepted names, malformed names and a run labelled
  `aggregates`.
- [x] **T-574** Added `cli/load_aggregates.py` and `src/projection/load_aggregates.py`: dry run by
  default (`gate.validate`), read-only `--check-store` (`gate.plan`), `--write`, the production
  `--to-production` guard, manifest-first ordering, timings and the usual exit codes. An existing
  graph is reported as already-in-the-store and its rows are checked against the file.
- [x] **T-575** The read-only verifier checks (a) the manifest entry/hash; (b) each window's trend
  dates against both Top-N arms' distinct `v_book_rebalance.decision_date`, including that the two
  arm sets agree; (c) every `v_portfolio_period_summary` segment has exactly the two reference rows
  with the summary's dates; (d) `below` implies a positive cash fraction and every other state is
  exactly `0.0`; (e) P2 compounds P2a/P2b within `1e-6`; and (f) after a write the stored graph's
  explicit triples equal the file's batch. Failures name the window, date or segment.
- [x] **T-576** Added the aggregates graph family to the catalog's scope table and the two tagged
  queries `trend-filter-on-in-window` and `reference-returns-and-arm`; the latter joins the
  reference rows to the existing `:PortfolioPeriodSummary` arm return. The text states these are
  per-segment aggregates and that no daily series exists in the graph. The hermetic fixture has
  both references, `P2a`/`P2b` and a `not_evaluable` row.
- [x] **T-577** Added `tests/test_aggregates.py` (parser rejects every extra/malformed value and
  duplicate; manifest match/mismatch; deterministic IRIs; shape negatives; gate accepted once and
  refused twice; source verifier including a date-differing window; stored-row equality) and
  `tests/test_cli_load_aggregates.py` (help/arguments, dry-run table, manifest refusal, missing
  file, production guard).
- [x] **T-578** Updated `docs/06`, `docs/07`, `docs/08`, `docs/10`, the backtest runbook (step 1e
  after `load_run`), `docs/graphdb-setup.md`, `schema/README.md`, `README.md`, `SPEC.md` and the
  asserted counts: **58 classes (44 disjoint leaves), 39 named shapes, 4913 quads**, load plan
  **5190 asserted triples**.
- [x] **T-579** Ran `uv run pytest`, `mypy` and the pinned pre-commit hooks; see the verification
  line below.
- [x] **T-580** The real read-only dry run over
  `/workspaces/thesis/scratch/final/candidate_y2` verified the manifest hash, every verifier check
  and SHACL conforms, in 0.574 s CLI time (0.951 s wall including `uv`). The user performs the real
  write.

**Scope notes.** `src/projection/load_run.py` and `src/projection/verify_backtest.py` were not
changed; `cli/load_aggregates.py` runs after `load_run` and only writes the new label's graph.
`schema/protege-view.ttl` is generated and was not regenerated. `sources.
spy_total_return_series_sha256` is validated and never projected. No result NAV or final-run count
is recorded here.

**No GraphDB write or reload was made.** The user reloads the schema afterwards with
`cli/load_schema.py`, then `cli/verify_store.py`, and performs the real write.

**Verified 2026-11-05**: `uv run pytest -q` = **1461 passed, 59 deselected, 8531 warnings in
1217.63 s (20:17)** (the two count tests were fixed before the run); `mypy` = success, **116 source
files**; the pinned pre-commit hooks pass on every changed file; FR-001 is **4913 quads (58
classes, 44 disjoint leaves, 39 named shapes); conforms: True**.

## Work item 38 — Accept the `bootstrap_mdd` test name (2026-11-05, T-600–T-629)

**Goal**: accept upstream's fourth paired test, `bootstrap_mdd`, in the closed `:testName`
vocabulary without changing any other meaning or check.

- [x] **T-600** Recorded the design in `PLAN.md` Work item 38 before any code (first commit).
- [x] **T-601** Added `bootstrap_mdd` to `BacktestTestShape`'s `:testName` `sh:in` list, updated
      both `tbox.ttl` comments and the Spanish `:BacktestTest` definition, and mirrored the list
      and comments in `kg_target_schema.ttl`. The wording is upstream's: a paired circular block
      bootstrap of the maximum-drawdown difference MDD(arm_a) − MDD(arm_b) in the segment (block 5,
      4999 replicates, seed 20261104; the statistic is that difference as a fraction, positive when
      arm_a fell more; the p-value is two-sided), from
      `src/cycle/backtest/stats.py::bootstrap_mdd_diff`.
- [x] **T-602** Grepped `src/`, `tests/`, `docs/` and `src/projection/view_expectations` for the
      three existing names. The expectations JSON has no test-value list, the projector writes any
      source row and the verifier compares source/store counts; only `docs/06` listed the names,
      and it now carries the fourth. Every other closed list and check is unchanged.
- [x] **T-603** Added a fourth `backtest_test` row to the hermetic fixture with
      `test = bootstrap_mdd` and the candidate's published `params_json`; added the SHACL positive
      case, the projector assertion for its individual and `:paramsJson`, the verifier's
      `4 stored, 4 source rows` assertion, and a check that both schema files list the same four
      values. The existing `BOGUS` negative case still fails.
- [x] **T-604** Ran the candidate store-free dry run after the change: all six windows and the
      metadata graph are SHACL-valid and were not written. Per-window m018/selection triples:
      P1 308,139/321,954, H1 441,319/391,365, P3 351,049/343,594, H2 245,220/295,780,
      P2 318,829/310,341, H3 622,477/389,440; metadata 56. Delivery files 118.21 s, total
      1,202.55 s. `final_b5` does not exist, so no final-run dry run was possible. See the table
      below.
- [x] **T-605** Updated `docs/06`, `schema/README.md`, `README.md`, `SPEC.md` and the asserted
      counts: FR-001 is now **4915 quads** (the extra `sh:in` member adds two triples) and the
      load plan is **5192 asserted triples**.
- [x] **T-606** Ran the full checks; see the verification line below.

**Scope notes.** A vocabulary-only change: no class, property, shape, cardinality, datatype, range
or cross-graph check was added or relaxed. `schema/protege-view.ttl` is generated and was not
regenerated. No GraphDB write, `--check-store` or schema reload was made by the agent.

**No GraphDB write or reload was made.** The user reloads the schema afterwards with
`cli/load_schema.py` (`KG_REPOSITORY=portfolio_test`), then `cli/verify_store.py`, and performs the
real candidate/final writes.

**Verified 2026-11-05**: `uv run pytest -q` = **1482 passed, 59 deselected, 8794 warnings in
1541.87 s (25:41)**; `mypy` = success, **118 source files**; the pinned pre-commit hooks pass on
every changed file; FR-001 is **4915 quads (58 classes, 44 disjoint leaves, 39 named shapes);
conforms: True**, and the load plan is **5192 asserted triples**.

## Work item 39 — Store CLI target banners and production guards (T-630–T-659)

*The production schema incident: `KG_REPOSITORY=portfolio` in the shell won over `.env`, and no
command named its target. See `PLAN.md` Work item 39 and SPEC FR-012.*

- [x] **T-630** Record the design in `PLAN.md` Work item 39 before any code: the banner/override
      helper, the two production guards, the schema-only production load and the acceptance
      fallbacks. → `PLAN.md` Work item 39.
- [x] **T-631** Add `announce_target`/`environment_overrides` and call them from every CLI path
      that opens the store; test the target banner, the production marker and the absence of
      credentials. → `PLAN.md` Work item 39, decision 1.
- [x] **T-632** Add `--to-production` to `cli/load_schema.py` and `cli/verify_store.py`, exit 2
      before any request on production without it, and test the guard and the proceed-past path;
      update both module docstrings. → decision 3.
- [x] **T-633** Add `include_examples` to `load_schema.load`/`expected_sizes`, skip
      `instances.trig` in production, keep `portfolio_test` unchanged, and make the six acceptance
      checks consistent (four-graph plan, TBox reasoning fallback, stored-rule vocabulary probe). →
      decisions 4 and 5.
- [x] **T-634** Announce the target before any other output in `load_run`/`load_aggregates` while
      keeping the manifest check before the store is contacted, and test that their banner is
      the first line. → decision 2.
- [x] **T-635** Rename the aggregates runbook step to §1f and add the "Removing a run label"
      section with the listing SELECT, the DROP-as-text review and the backup/only-copy warning. →
      decision 6.
- [x] **T-636** Update `README.md`, `docs/graphdb-setup.md` and SPEC FR-012. → decision 6.
- [x] **T-637** Run `uv run pytest -q`, `mypy` and the pinned pre-commit hooks; record the results
      in `PLAN.md`. → acceptance criteria.

## Work item 41 — Correct the `:objective` comment (2026-11-09, T-690–T-719)

**Goal**: stop the `:objective` field from being read as the Sistema's weighting objective. Keep
the open/read-verbatim semantics, state the fixed per-arm literal upstream writes, and attribute
the pending interpretation.

- [x] **T-690** Recorded the design in `PLAN.md` Work item 41 before any code.
- [x] **T-691** Rewrote the `:objective` comment in `schema/tbox.ttl` and mirrored it in
      `kg_target_schema.ttl`: `v_book.objective` open and read verbatim; upstream's `_insert_books`
      writes a fixed literal per arm (`min_var` for every optimized arm, `equal_weight` for the
      benchmark `SP500_EW_INTERNAL`), independent of the run's `satellite_weighting`; the
      delivery's `config_final.md` describes a minimum-variance optimisation keeping at most 30
      names followed by minimum-CVaR weighting, so `min_var` is NOT the `TOPN_MV_*` weighting
      objective and must not be presented as such; upstream's confirmation is pending.
- [x] **T-692** Grepped `schema/`, `docs/`, `kg_target_schema.ttl`, `docs/06`,
      `docs/reports-agent-query-catalog.md`, `schema/README.md` and `README.md` for `:objective`
      and `min_var`. The only copies are `schema/tbox.ttl` and `kg_target_schema.ttl`; the
      `docs/06` and `instances.trig` hits are the different `:benchmarkObjective` on `Portfolio`.
      `schema/protege-view.ttl` is generated and was not edited.
- [x] **T-693** Added the hermetic test in `tests/test_schema_gate.py`: it parses `schema/tbox.ttl`
      and asserts the key facts and the unchanged `owl:DatatypeProperty`/`owl:FunctionalProperty`,
      `rdfs:domain :StrategyBook` and `rdfs:range xsd:string` declaration. It fails on the old
      comment (`assert '_insert_books' in comment`).
- [x] **T-694** Ran the FR-001 parse and `pyshacl`; the counts are unchanged (4915 quads, 5192
      load-plan triples) and the change is recorded in `schema/README.md` item 13.
- [x] **T-695** Ran the full checks; see the verification line below.

**Scope notes.** Comment only: no class, property, shape, cardinality, datatype, range or IRI was
added, removed or changed, and no other term's comment was touched. `schema/protege-view.ttl` is
generated and was not regenerated.

**No GraphDB write or reload was made.** The user reloads the schema afterwards with
`cli/load_schema.py` (`KG_REPOSITORY=portfolio_test`), then `cli/verify_store.py`; a clean reload
performed after this change is merged also picks it up.

**Verified 2026-11-09**: `uv run pytest -q` = **1483 passed, 59 deselected, 8794 warnings in
1307.23 s (21:47)**; `mypy` = success, **118 source files**; the pinned pre-commit hooks pass on
every changed file; FR-001 is **4915 quads; conforms: True**, and the load plan is **5192 asserted
triples**.
