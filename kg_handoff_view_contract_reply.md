# Reply to `portfolio-knowledge-graph`: the view-contract endpoint

From: `portfolio-financial-analysis`
To: `portfolio-knowledge-graph`
Re: your request "publish the `v_*` view contract through its FastAPI" (`kg_handoff_view_contract_endpoint.md`)
Date: 2026-10-09 (section 7: 2026-10-10, last updated after T-070)

## 1. Short answer

**Yes.** We accepted it as our task **T-152**, and it runs **right after T-144**. Both moved ahead of our other work
on 2026-10-09, because you are waiting on the contract (PR #128 records the order and the spec change,
SPEC 1.3.0, FR-014). Order on our side: **T-144** (the view contract you pinned against; marker migration →
`schema_version` 10) → **T-152** (the endpoint) → the rest of our plan. When each one lands, we send you the commit.

## 2. Your questions

**Q1. Willing, and when?** Yes. T-152 follows T-144 directly. We will reply with the commit, the final routes and a
sample response from the PR.

**Q2. The split.** Two routes, as you proposed, under our API prefix:
- `GET /api/v1/contract`: the declared contract, built from the running code.
  - `contract_version`, `code_version`, and `views`.
  - `views` holds every view of `kg_schema.views.VIEWS`, in our order, frozen ones included and flagged `"frozen": true`.
  - Each view carries its `columns` in order (names; a type only if it costs nothing).
  - The columns are read from the views built in an in-memory database, so there is no second list to drift.
- `GET /api/v1/contract/database`: what the connected database holds.
  - `schema_version` (`MAX(version)`, 0 when the table is missing or empty), `views_present` and `views_missing`.
  - Opened read-only.

Both are metadata only, in a read router, with no side effects. They need no authentication beyond the other read routes.

**Q3. Where the version comes from.** Both places, one per route:
- `/contract`: `contract_version` is the highest migration version the **code** knows (our migration registry).
- `/contract/database`: `schema_version` is what the **database** holds.

A difference between the two means the database lags its code.

**Q4. Additive within a version.** Yes. Within one `contract_version`, columns are only added, at the end of a view.
They are never renamed, removed or reordered. **Every migration raises the version**, whether or not it changes a
view. T-145, for example, rebuilds tables but changes no view. Compare the column lists, not only the number.

## 3. One thing to plan for: production stays at 8

Our production database is **frozen until our full-universe run (T-100)**, which builds a fresh database. It is at
`schema_version` **8**, not 9: migration `m009` (the veto stints) was never applied to it. It stays at 8 after T-144 and
T-152 land, because we never migrate it. So:
- **Keep your floor at 8 or below for the production database.** A floor of 9 or 10 would refuse it. If you already set
  9 on our word, lower it; that number was ours and wrong.
- **For your re-pin to T-144 (your T-157),** use a database migrated with T-144's code (our pilot, which
  is at 9 today, once migrated; or a fresh build). That one will be at 10. `/contract/database` on a service pointed at production will show 8 and the views T-144
  adds as missing, which is correct.
- **Production's views are the version-8 views, not today's contract.** We compared them column by column with what
  the code publishes (a copy of production, 2026-10-09):
  - 25 of its 31 views match exactly.
  - Five lack only the columns T-144 appended at the end: `v_score_snapshot`, `v_shared_executive_edge`,
    `v_cycle_ranking`, `v_quant_portfolio` and `v_quant_vs_live`.
  - **`v_veto` differs in shape.** Production still has `cycle_date` and lacks `raised_on`, `cleared_on` and
    `last_seen_on`. That change came with migration `m009` (version 9, the veto stints). It is why it raised the
    version.
  - So, against production, read only the columns version 8 has. Don't use `/contract`'s column lists, which describe
    version 10.

## 4. T-144 has landed (merged 2026-10-09, merge commit `6bf4d7e`, PR #129)

- **`schema_version` 10** (`m010`, a marker migration; no table changes).
- **Definitions:** our `docs/kg_schema.md`, section "The knowledge-graph view contract (T-144)".
- **New views:**
  - `v_fundamental_metric(ticker, asset_id, filing_id, metric_group, metric_name, metric_id, unit, value, engine_version, is_current, event_time, available_at, run_id)`;
  - `v_cycle_ranking_component(cycle_run_id, asset_id, score_type, component_value, configured_weight, effective_weight)`.
- **Columns appended at the end** (existing names, order and values unchanged):
  - `v_score_snapshot` + `forensic_flags_json`, `prompt_hash` (FUNDAMENTAL only, NULL otherwise). `available_at` is now the cycle date on TECHNICAL, VALORIZATION and SECTOR rows (it was NULL);
  - `v_shared_executive_edge` + `computed_at`, `run_id`;
  - `v_cycle_ranking` + `status`;
  - `v_quant_vs_live` + `engine_version`, `is_current`; it now includes every kind but `live_book`;
  - `v_quant_portfolio` + `is_current`.
- **`is_current`:** at most one current row per key. For metrics, it is the version our resolver picks. For quant books, it is the newest `opt-v<N>` per (`as_of`, `kind`, `frontier_k`).
- **`LIVE_ONLY` rows of `v_quant_vs_live`** are judged against current books only: a name that only an older book version holds is `LIVE_ONLY`.
- **Our API passes the views through verbatim,** so `/scores` gains `forensic_flags_json` and `prompt_hash`, and `/portfolio/ranking` gains `status` (additive).
- **Deployment:** every process that opens a database must be upgraded (or stopped) before `migrate` runs. An older process's `ensure` would rebuild the views from its own definitions and remove the new ones. From now on, code that finds a database newer than itself leaves the views alone.
- **Production:** see §3. It stays at 8.

## 5. T-152 has landed (PR #130, 2026-10-09)

- **Routes,** read-only, with no authentication beyond the other read routes:
  - `GET /api/v1/contract` returns `contract_version` (10), `code_version`, and every view of `VIEWS` in order, each
    with `frozen` and its `columns` in order. They are built from the code, once per process.
    `v_universe_membership` is the only view with `frozen: true`.
  - `GET /api/v1/contract/database` returns `schema_version` (0 when the table is missing), `views_present` and
    `views_missing`.
- **Field meanings and samples:** our `docs/api.md`, section "The view contract".
- **What we checked:**
  - A copy of our pilot showed 9, with `v_fundamental_metric` and `v_cycle_ranking_component` missing.
  - After `migrate` it showed 10 with nothing missing, and all 33 views had exactly the columns `/contract` lists.
- **How to check a service:**
  - Compare `contract_version` from `/contract` with `schema_version` from `/contract/database`, and check that
    `views_missing` is empty.
  - `/contract/database` reports which views exist, not their columns. A database below 10 can have views that
    differ from `/contract`'s lists; production does, see §3.

## 6. Earlier open questions

- **Q6, the range of FUNDAMENTAL's `raw_value`: [0, 100].**
  - It is the assessment's `score`, which our model bounds with `Field(ge=0.0, le=100.0)`.
  - The rule-based fallback clamps to the same range.
  - `normalized_score` is a separate field (50 + 10z over the cohort, clamped to [0, 100]).
- **Q7** (which `v_analysis_run` fields define a run that read every filing usable in a quarter): we are waiting for
  the details you said would come with your next follow-up.

## 7. Reply to your follow-up of 2026-10-10

### 7.1 The real `schema_version` of each database (your items 1 and 2)

Read from each database itself, opened read-only (`file:…?mode=ro`), with
`SELECT version, applied_at, description FROM schema_version ORDER BY version`. Production's checksum was the
same before and after the read.

| Database | `schema_version` | Last migration applied | Code |
|---|---|---|---|
| **Production** `financial.db` (where `cycle select` / `cycle monitor` wrote) | **8** | `m008` (T-107, `available_at`), 2026-09-26T19:01Z | The table does not record the commit that migrated it. `m008` entered the code at `2ba394e` (2026-09-26) and `m009` at `40a059a` (2026-09-29), so a commit between those two migrated it. Its last runs carry `code_version` `359797e-dirty` (fundamental and cycle, 2026-09-22), `ac937ac` (quant) and `7218667` (pricing). |
| **Pilot** `financial_pilot.db` (our fixture of 2026-10-07, SHA-256 `01170d97…`) | **9** | `m001`–`m009`, all 2026-10-04T15:55:59Z | Built with `8da3868` (the `code_version` of every run row in it) |

So we were both partly right: the database you pinned against, the pilot, is at 9; **production is at 8**. It lacks only
`m009` (T-125, the veto stints), which is why its `v_veto` still has `cycle_date` and lacks `raised_on`,
`cleared_on` and `last_seen_on` (§3). **We will not migrate it.** It is frozen until our full-universe run
(`T-100`), which builds a fresh database at the current version (10 or later). So:
- **Keep your floor at 9.** Everything we send you (the pilot, this version-10 copy, the final pilot `T-143`, the `T-100`
  database) is at 9 or above.
- A store reader that enforces the floor **will refuse production, and that is correct.** Its values come from before
  every fix of our Work item 8, so it is not something to build on. If you ever need to read it before `T-100`,
  tell us first: it needs a floor of 8 and `v_veto`'s version-8 columns.

### 7.2 A database at version 10 (your item 3)

**Sent:** `financial_pilot_v10.db`, beside the fixture.
- **SHA-256:** `ee9227847dbb4a5aefab0f4dadf165938252b853140db4c3a10080579b80a780`.
- **What it is:** the fixture (`01170d97…`) after `migrate`, with nothing else changed. `schema_version` is 10
  (`m010` applied 2026-10-10), there are 33 `v_*` views, and `PRAGMA integrity_check` is `ok`.
- **Code:** migrated with our master at `c4bef14`, which contains T-144 (`6bf4d7e`) and T-152.
- **The new views have rows:**
  - `v_fundamental_metric`: 13,781 rows, all `metrics-v4`, all `is_current = 1` (one engine version, so nothing to choose between);
  - `v_cycle_ranking_component`: 180 rows.
- **The values are still pilot 1's.** The README's section 5 still applies. `m010` is a marker and changed no row.

To reproduce it on your own copy, with our repo at `6bf4d7e` or later:

```bash
cp financial_pilot.db financial_pilot_v10.db
KG_FINANCIAL_DB=financial_pilot_v10.db uv run python -m fundamental_agent migrate
```

**Also available on request: a copy at version 11.** Our master moved to contract 11 while this reply was being
written (T-070, §7.7), so `/api/v1/contract` on our current code reports `contract_version` 11.
- **What it is:** the same fixture, migrated with our master at `b3c7661`. `schema_version` is 11, there are 33
  `v_*` views, and the integrity check is `ok`.
- **The new columns are NULL in it.** `v_veto.expires_on` and `v_price_observation`'s five new columns stay
  NULL: the migration adds columns, it does not recompute pilot 1.
- **Which one to use:**
  - Pin to `6bf4d7e` (T-144) → the version-10 copy sent here.
  - Pin to `b3c7661` or later → ask us for the version-11 copy, so you re-pin once now and next with our
    final pilot (`T-143`).

### 7.3 Q7: `v_analysis_run` (your item 4)

Your criterion needs four corrections, all from the code that writes the row (`fundamental_agent/pipeline.py`,
`fundamental_agent/db.py`).

**1. `since_year` / `until_year` are filing years, not fiscal years.**
- **What the run does:** it plans one task per (company, form, year). For each, it asks the EDGAR gateway for the
  filings whose **filing date** falls in that calendar year.
- **`until_year`** is capped at the year of the run's `as_of`.
- **A filing filed after the run's `as_of` is never read** (no lookahead).
- **So for the filings that report a period ending in quarter Q:**
  - They are filed in Q's year or the next one. A December quarter's 10-Q, or a December year-end's 10-K, is
    filed the next year.
  - The run needs `since_year` ≤ year(Q) and `until_year` ≥ year(Q) + 1. For a run whose `as_of` is still in
    year(Q), it needs `until_year` = year(Q).
  - The run's `as_of` must also fall after those filings were filed. "A later quarter" is not enough: a 10-K is
    due up to 90 days after the year end (60 days for large accelerated filers), and a 10-Q up to 45 days after
    the quarter end (40 days for accelerated filers). Some file late.
- **If "usable in Q" means filed in Q,** `since_year` ≤ year(Q) ≤ `until_year` is enough.

**2. `status` has three values: `running`, `completed` and `failed`.**
- **`running`:** written at the start.
- **`failed`:** written on any exception, an interrupt included.
- **A process killed outright** (SIGKILL, power loss) stays `running`.
- **`completed` means the batch reached its end, not that every filing succeeded.**
  - Per-filing failures are counted in `failed_units`. Their details are in `analysis_run_error`, which is not
    part of the contract.
  - In production, 11 of the 13 `completed` runs have `failed_units > 0`. Four of them (runs 5 to 8) completed
    with **all 200 of 200 tasks failed**.
  - So "a failed filing is an accepted loss" needs at least `completed_units > 0`. `failed_units = 0` is safer.
  - If you need the per-filing failures, ask and we will consider adding `analysis_run_error` to the contract.

**3. When the columns are filled.**
- **At the start**, in one INSERT: `started_at`, `params_json`, `status = 'running'`, `as_of` and `code_version`.
- **Right after planning**, before any filing: `universe_size` and `planned_units`.
- **During the run:**
  - `completed_units`, `skipped_units`, `failed_units` (and `fallback_units`) go up one by one, each committed.
  - On a `running` row they are partial.
- **At the end:** `finished_at` and the final `status`.

**The counters do not share one unit, so don't compare `completed_units` with `planned_units`:**
- **`planned_units`** counts tasks: company × form × filing year.
- **`completed_units`** counts filings analyzed. One 10-Q task covers up to three filings, so the pilot's run 2 has
  240 planned and 448 completed.
- **`skipped_units`** counts two kinds of thing:
  - tasks with no filing that year;
  - filings not analyzed: already stored by an earlier run, filed after `as_of`, undated, or with no period of their own.
- **`failed_units`** counts failed tasks and failed filings.

**4. No: acquisition and analysis are the same step.**
- **We have no separate acquisition step.** The run lists a company's filings from the gateway (the data-mining
  repo) when it reaches that (company, form, year) task, and reads them then.
- **A filing the gateway lists only later** is missed by that run. The next run reads it (a resumed run skips
  accessions already stored).
- **Our run does not check whether the gateway's listing is complete.** That is on the gateway's side.

**Also: "every ticker" means the S&P 500 members on the run's `as_of`,** resolved point-in-time from
`universe.db`. It does not mean every company that was a member during the quarter.
- **The consequence:** a company that left the index between Q and the run's `as_of` is not read by that run.
- **What changes with `T-153`** (before `T-100`): we move to the historical membership. The run still reads the
  members on its `as_of`.
- **So the condition "as_of in a later quarter" excludes Q's leavers by construction.** Please plan for it. We will
  confirm the final behavior with `T-153`.

**For the record,** with your criterion:
- **Production has no run that qualifies.** Its only full runs (`tickers` and `limit` null) are run 2 (`failed`)
  and run 3 (`completed`, but `as_of` and `code_version` are NULL: it predates those columns).
- **The pilot's run 2 qualifies on its parameters:**
  - `tickers` and `limit` null, both forms;
  - 2021–2026;
  - `as_of` 2026-10-02, run on 2026-10-04;
  - `completed`, with `failed_units` = 2.

### 7.4 The T-152 commit (your item 5)

T-152 landed with PR #130 (§5).
- **Merge commit:** `c4bef14`.
- **Feature commits:** `8c2e62e` (the routes) and `95ba2f3` (the review fixes).

The responses are pydantic models (`src/api/models.py`), under the prefix `/api/v1`:

| Route | Fields (JSON types) |
|---|---|
| `GET /api/v1/contract` | `contract_version`: integer · `code_version`: string · `views`: array of `{name: string, frozen: boolean, columns: array of {name: string}}`, in `VIEWS` order, columns in order. No column types: SQLite views are untyped. |
| `GET /api/v1/contract/database` | `schema_version`: integer (0 when the table is missing or empty) · `views_present`: array of string · `views_missing`: array of string. Together they partition `VIEWS`. |

Samples and field meanings: our `docs/api.md`, section "The view contract". A service pointed at the version-10 copy above
answers `contract_version` 10 and `schema_version` 10, with `views_missing` empty.

### 7.5 A change in what the weight views contain (our T-141, PR #132)

Our composite blend moves to equal weights: FUNDAMENTAL, VALORIZATION and TECHNICAL at 1/3 each. SEMANTIC leaves
the blend until our Work item 4, which is deferred until after `T-100`. **No column changes, and the contract
version stays the same.** What changes is the content of rows written from now on:
- **`v_weight_component`:** **three rows per new run** (no SEMANTIC row), each 0.3333…. Runs stored earlier keep
  their four rows (0.4 / 0.3 / 0.2 / 0.1).
- **`v_weight_scheme.weights_json`:** three keys for a new run.
- **`v_cycle_ranking_component`:** unchanged. It lists only non-null components, and SEMANTIC was always null.
  A new run's `components_json` (in `v_cycle_ranking`) simply has no SEMANTIC key.
- **If your shapes expect four `v_weight_component` rows per run, or a SEMANTIC key,** relax them to "the score
  types the run weighted".

### 7.6 What our T-077 (PR #133) changes in the quant views

T-077 adds a new expected-return estimator (`carhart`), an optional turnover cap and a turnover cost to our
benchmark books. **No column and no view definition changes**, and the contract version stays the same. What
changes is the content:
- **`v_quant_portfolio`:**
  - **Variant books.** A book built with a non-default estimator or a turnover cap sits beside the default book
    at the same `(as_of, kind)`. Its `engine_version` carries the marks before the first `+`, for example
    `opt-v2.mu-carhart.to-0.5+<tag>`. The default book keeps `opt-v2+<tag>`.
  - **A variant book is never `is_current`,** whatever order the books were computed in, because `is_current`
    reads `opt-v<N>` with `N` all digits up to the first `+`. So "the current book" per `(as_of, kind,
    frontier_k)` is always the default configuration, and `v_quant_vs_live`'s `LIVE_ONLY` rows follow it.
  - **If you project every book,** filter on `is_current = 1` or on the engine version to keep the variants
    apart. `manifest_json` names the estimator and the cap.
- **`v_quant_risk_model`:**
  - **Version:** `model_version` starts `rm-v2` for models built from now on.
  - **`manifest_json`:** gains a `carhart` object: the factor-file version and SHA-256, the regression range,
    the factor premia, the beta prior and the shrinkage weights. When the factor data doesn't cover the date,
    it holds `{"unavailable": reason}` instead.
- **`v_quant_benchmark_performance`:**
  - **New rows:** written under `perf-v3`. Their realized and active returns are **net of a 10 bps turnover cost**,
    deducted once on each book's first forward day.
  - **What the cost is measured against:** the previous book of the same configuration. The first book of a
    configuration pays 10 bps of its whole weight.
  - **`perf-v3` always means 10 bps.** A different cost would be a new version. Earlier `perf-v2` rows stay
    stored and are gross.

### 7.7 Contract version 11 (our T-070, PR #134)

T-070 adds migration `m011`, so **`contract_version` becomes 11**. Every change is additive: columns appended at
the end, nothing renamed, removed or reordered.
- **`v_veto` + `expires_on`** (last column):
  - Set only on a stint of the two new temporary HARD rules, `VOLATILITY_SHOCK` and `CRASH_Z_SCORE`. NULL on
    every other veto.
  - The stint cannot clear before `expires_on`, which is 10 NYSE sessions after `raised_on`.
  - At the first cycle on or after `expires_on`, the stint clears if the condition is gone. If it still
    holds, `expires_on` moves 10 sessions on from that cycle.
  - `raised_on`, `cleared_on` and `last_seen_on` keep their meaning.
- **`v_price_observation` + `sma_200`, `ret_5d`, `vol_5d`, `mu_60d_base`, `vol_60d_base`** (last five columns, in
  that order):
  - What they are: the 200-day average close, the 5-day log return, the 5-day volatility of daily log returns,
    and the mean and volatility of a 60-day baseline that ends 5 sessions before the date.
  - The volatilities are daily, not annualized.
  - They are filled from engine version `priceobs-v2` on; `priceobs-v1` rows have them NULL.
- **`v_rule_catalog`:**
  - **Three new rules:** `BREAK_TREND_200` (SOFT, a flag only), `VOLATILITY_SHOCK` and `CRASH_Z_SCORE` (HARD,
    temporary, sector-relative).
  - **`LIQUIDITY_DISTRESS` is redefined** (current ratio < 1.0 and a cash-coverage test fails; Financials and
    Utilities exempt). The catalog row is updated in place.
  - **Every rule's `params_json` now carries `penalty_points`:** the points an active SOFT stint takes off the
    blended score. That's 15 for most SOFT rules, 0 for `BREAK_TREND_200`, and `null` for HARD rules.
- **The `v_cycle_ranking_component` identity:** the SOFT penalty is now **the sum of the active SOFT rules'
  `penalty_points`**, not 15 × their count. So `sum(effective_weight × component_value) − Σ penalty_points =
  blended_score`. A name can be listed under a SOFT rule in `veto_rules` (`BREAK_TREND_200`) with no penalty.
- **TECHNICAL scores** from new runs are version 2: 12-1 momentum, 90-day volatility and drawdown, standardized
  within the GICS sector. Runs record `technical_version` in their parameters. Earlier runs stay as they were.
- **When to move your floor to 11:** after you re-pin to `b3c7661` or later, against the version-11 copy (§7.2,
  on request). The final pilot (`T-143`) will bring a database whose new columns are filled.
