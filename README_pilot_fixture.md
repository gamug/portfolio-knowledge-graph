# Pilot database: a test fixture for `portfolio-knowledge-graph`

From `portfolio-financial-analysis`, 2026-10-07. **For internal use by the thesis team only.**

## 1. What this is, and what it is not

- **It is** a small, real database from our first pilot run: 20 S&P 500 companies, 8 GICS sectors. Use it to
  develop and test your projection and SHACL shapes against our `v_*` read contract.
- **It is not** a result. Its values have known defects (section 5), and the final system will produce
  different numbers. **Do not use these values** in a demo, a report, a figure or any chapter, and do not
  publish them.
- **It will be replaced** by the database of our final pilot (`T-143`). That one is built fresh, through the
  orchestrator, and carries the `T-144` view changes. We will send it when it exists.

## 2. Contents

| File | What | SHA-256 |
|---|---|---|
| `financial_pilot.db` | `KG_FINANCIAL_DB` from pilot 1 (SQLite, 51 MB) | `01170d97077bbe6690376e89bedc7d9843c02549a85331f0a5b96ab99b6d5563` |
| `universe.db` | `KG_UNIVERSE_DB`: the 20-member universe the pilot ran on, and **your asset master** (`universe_membership`: symbol, CIK, GICS sector/sub-industry, `valid_from`/`valid_to`) | `ff7324ba8c1d26c1fc95b383a896f46a97facea16e19dbcad04dc95f0e8bbb72` |
| `SHA256SUMS` | The two hashes | — |

Check the files after transfer with `shasum -a 256 -c SHA256SUMS`.

The tickers are APA, APO, BF.B, CPT, ESS, HOOD, HUM, MA, MCD, NEE, PG, PM, PSX, SBAC, STZ, T, UDR, WAT, WFC
and XOM.

## 3. Version stamp

| Item | Value |
|---|---|
| Code commit | `8da3868`, the commit your first view-gap notes were read against. `src/kg_schema/views.py` is unchanged from there to `84914c7`, so the views match the contract you pinned |
| `schema_version` | 9 (your floor) |
| `cycle_type = 'REPLAY'` runs | 0 (passes your projection check) |
| Metrics engine | `metrics-v4` (current code writes `metrics-v5`) |
| Optimizer engine | `opt-v1+1cb239a5` (current code writes `opt-v2`) |
| Built | 2026-10-04 |

## 4. What you can test with it, and what you cannot

**Can test** (your schema's Part 1, on master):

| View | Rows | Notes |
|---|---|---|
| `v_score_snapshot` | 569 | 449 FUNDAMENTAL (`prompt_hash` on all 449; event_time 2020-11-30 → 2026-07-31), 40 each TECHNICAL, VALORIZATION, SECTOR |
| `v_sec_filing` | 449 | 10-K and 10-Q. Accession numbers are unique here |
| `v_cycle_run` / `v_cycle_ranking` | 3 / 60 | SELECTION 2026-07-09 and 2026-10-02, MONITORING 2026-10-02, all `completed` |
| `v_weight_scheme` / `v_weight_component` | 3 / 12 | Configured weights, 4 keys (see section 5) |
| `v_veto`, `v_rule_catalog`, `v_data_quality_issue` | 10, 6, 204 | Veto stints (T-125), rules, Ring-1 issues |
| `v_portfolio_position` | 39 | The live book's stints |
| `v_quant_portfolio`, `v_quant_position`, `v_quant_vs_live`, `v_quant_benchmark_performance` | 5, 100, 80, 300 | One as-of date (2026-07-09); performance 2026-07-10 → 2026-10-02 |
| `v_price_observation`, `v_quant_return_daily`, `v_corporate_action`, `v_benchmark_series`, `v_risk_free_rate` | 23,840, 23,840, 344, 61, 1 | Prices 2022-01-03 → 2026-10-02 |
| `v_sector`, `v_industry`, `v_sector_aggregate_snapshot` | 8, 17, 16 | |

**Cannot test yet:**

1. **Anything from our `T-144`.** It does not exist yet:
   - `v_fundamental_metric` and `v_cycle_ranking_component`;
   - `status` on `v_cycle_ranking`;
   - `is_current`;
   - `forensic_flags_json`/`prompt_hash` in `v_score_snapshot`'s column list;
   - `available_at` filled on cycle lanes, which is NULL here on TECHNICAL, VALORIZATION and SECTOR rows.

   That is your Part 2.
2. **Empty views:** `v_shared_executive_edge` (entity resolution did not run in the pilot, so there is nothing
   for `:AssetCoOccurrence`), `v_sec_filing_section`, `v_universe_membership` (frozen by design) and
   `v_universe_coverage`.
3. **`forensic_flags_json` is NULL in every row**, until our `T-074`.
4. **Multi-version cases:** there is one quant date with one engine version, and one metrics version, so
   `is_current` logic has nothing to choose between.

## 5. Known value defects (shapes are fine; values are not results)

| Area | Defect | Fixed by |
|---|---|---|
| Revenue | APA FY2021–2023, from before our revenue rebuild | `T-140` (merged) |
| Fiscal quarters | WAT's 2023-09-30 quarter (52/53-week label), from before our period-end keying | `T-140` (merged) |
| Weights | Old weight scheme `score_proportional`, caps 0.10/0.30; blend weights 0.4/0.3/0.2/0.1 (SEMANTIC is null everywhere) | Work item 18 (merged); `T-141` (equal weights) |
| Income tax | Displayed sign stored instead of the filed sign in 86 filings → `effective_tax_rate` wrong (often 0), which feeds ROIC and enterprise FCF yield | `T-148` (planned) |
| Line-item choice | PM/STZ equity read "before treasury stock" (PM shows +22.6B; the real figure is −12.6B); net income includes non-controlling interests for 12 tickers; APA income tax takes the deferred part only; short-term debt partial (BF.B, NEE, STZ) | `T-148` (planned) |
| COGS | STZ's COGS sign → negative `inventory_turnover` | `T-148` (planned) |
| FUNDAMENTAL `normalized_score` | Rewritten by every cycle; the value used in a given ranking is in `v_cycle_ranking.components_json` | Documented in `T-144` |

## 6. How to use it

- **Open both files read-only:** `sqlite3 'file:financial_pilot.db?mode=ro'`, or with
  `uri=True, mode=ro`. Read the `v_*` views only, as the contract says.
- **`params_json` mentions container paths** (`/workspaces/...`). They mean nothing outside our dev container
  and can be ignored. The LLM key is stored redacted.
- **`universe.db` is a 20-row sample of a live snapshot** (`source = 'live_snapshot'`, every `valid_to` NULL;
  `valid_from` = the date the company joined the index). It is not the full membership history, which our full
  run (`T-100`) needs.
- **Do not send us bug reports about the values in section 5.** Shape problems (columns, types, NULLs where the
  contract says otherwise) are welcome.

## 7. Data terms

- **SEC data** (filings, XBRL facts) is public.
- **Prices and corporate actions** come from `yfinance` (Yahoo Finance), whose terms are for personal,
  non-commercial use. Keep this database inside the thesis team. Do not redistribute it or put it in a public
  repository.
- **The FUNDAMENTAL narratives** in `v_score_snapshot.narrative` are LLM output (DeepSeek), produced over our
  computed metrics.
