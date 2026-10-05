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
      `SQL_UNIVERSE_DB` added. Full run on the real data: 98.5 s, 853 `:Asset` (+ 5 in
      `reference.ttl`), 879 memberships (503 open, 376 closed), 459,112 articles, 216,596
      `:RiskEvent`s; the only unresolved news ticker is `EQR` (1,104 rows, absent from
      `universe.db`; the live table lacked it too). 2378 quads, conforms: True. Open parts are in
      `SPEC.md` §2.6's D1 row (upstream's `EQR` gap, hand-refreshed file, stray `|` in two symbols,
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
