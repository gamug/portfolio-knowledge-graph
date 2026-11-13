# Veto Hierarchy projection — design (Work item 46, T-840)

**Status:** design, 2026-11-13. **No code, no schema edit, no GraphDB write.**

**Source delivery:** `/workspaces/thesis/knoledge graph/2026-11-13_diccionario_y_piloto/`.
`SHA256SUMS` hashes to `63a14af7892575d996726a82747a4dee620989c7bd5164e3b561f2e1d7d76005`;
all 17 listed entries verify with `sha256sum -c`. The pilot is `piloto_H1C_P1/H1C-B5-P1.db`
(read-only, `mode=ro`) plus 271 JSON-lines events, 10 rankings, 10 panels, 12 scale changes,
19 retention lines and `verification.json` (`all_match: true`). The mask is
`mascara_tiingo/tiingo_assets.csv`, SHA-256
`4712c7c224bd76b4661260d77d95ce3c62fe80710c0b7d30a1ce44ac00c39dce`, 33 assets.

This design is based on the frozen dictionary (2026-11-14 contract) and the five specifications.
The final delivery (2026-11-17/18) may add fields; names and types do not change. All counts below
are measured on the pilot unless a line explicitly says "budget" or "projection".

> **Superseding decision.** `docs/labels-design.md` (Work item 43) decided that C1 had no concept,
> IRI or notation. That decision is **superseded** by Reviewer A's plan of 2026-11-12: C1 is loaded
> as an independent continuous run starting at 1.0. See §1.5 for the exact doc/label text to change.

---

## 0. Recommendation

Load the new delivery as a **configuration-keyed family of append-only graphs**, not as a repeat of
the old `final` family:

- one explicit `:configuration` per book, with five closed configuration individuals
  (`SYSTEM_WITH_HIERARCHY`, `SYSTEM_WITHOUT_HIERARCHY`, `MARKOWITZ_BASE`, `MARKOWITZ_MV`, `SPY`);
- graph and IRI names from `(label, configuration, window)`, never from `backtest_run_id`,
  `book_id`, `alert_id` or `action_id`;
- only the manifest-named books and actions, no `ARM_DISABLED`, no twin tests, `MARKOWITZ_BASE`
  once per window;
- new layer-0 rules and `L1_BP_STOP_BLOCKED` in the catalog and shapes; no price or price-derived
  field on any `L1_BP_*` alert;
- a lean event model for the detail file (no JSON blobs, no string lists, no full candidate matrix);
- the existing selection projection for `v_cycle_ranking`, not `rankings.json`; `panels.json`,
  `scales.json` and `retention.jsonl` are cross-checks, not separate loads.
- The old `final` graphs are replaced by the maintainer, not by an append.

The full 7-window budget is **5,991,280 asserted triples** if both System selection graphs keep all
22 cycles per window, or **3,707,726** if only the 10 decision cycles are kept. The current store is
about 5.0M; replacing the old 4,164,492 m018+selection triples leaves about **6.83M** in the first
case and **4.54M** in the second. The selection-cycle choice is question Q1 in §10.

---

## 1. Configuration identity (full)

### 1.1 The engine's arm code no longer identifies a configuration

The dictionary §0 and §1.1 are explicit: `arm_code` does not identify a configuration.

| Run family | Books in the DB | What is loaded |
|---|---|---|
| With the Veto Hierarchy (pilot) | `MARKOWITZ_BASE`, `TOPN_MV_NOGUARD`, `TOPN_MV_GUARD_NO_NLP` | `MARKOWITZ_BASE` = minimum variance (Ledoit-Wolf). `TOPN_MV_GUARD_NO_NLP` = System with the Veto Hierarchy (`TOPN_MV_GUARD` if the chosen System carries news). **`TOPN_MV_NOGUARD` is the twin without GUARD and is NOT loaded.** |
| Without the Veto Hierarchy | `MARKOWITZ_BASE`, `TOPN_MV_NOGUARD` | `TOPN_MV_NOGUARD` = **System without the Veto Hierarchy** (risk rules and trend filter off, no portfolio GUARD; `DATA_QUALITY` and `EARNINGS_MISSING` on, pool 100, retention). `MARKOWITZ_BASE` = minimum variance. |

`MARKOWITZ_BASE_GUARD` no longer exists. `guard_layers` on the System book is NULL in the pilot; it
must not be used to decide whether a book has GUARD. `objective` remains the fixed `min_var`
selection-stage label; it is not the book's weighting objective.

The five configurations are exactly:

| Configuration individual | `skos:notation` | Source |
|---|---|---|
| `:Configuration_SystemWithHierarchy` | `SYSTEM_WITH_HIERARCHY` | engine DB; `TOPN_MV_GUARD_NO_NLP` (or `TOPN_MV_GUARD` if news) |
| `:Configuration_SystemWithoutHierarchy` | `SYSTEM_WITHOUT_HIERARCHY` | engine DB; `TOPN_MV_NOGUARD` of the without-hierarchy DB |
| `:Configuration_MarkowitzBase` | `MARKOWITZ_BASE` | engine DB; once per window from the manifest-named DB |
| `:Configuration_MarkowitzMV` | `MARKOWITZ_MV` | external summary graph from Work item 44; keep separate |
| `:Configuration_SPY` | `SPY` | reference series (block E, later) |

### 1.2 Proposed schema for the configuration

Add a small closed class and one functional object property; the labels and comments go in the
second label table of §8, not in `labels.ttl` yet.

```turtle
:BacktestConfiguration a owl:Class ;
    rdfs:label "Backtest configuration"@en, "Configuración de backtest"@es .

:Configuration_SystemWithHierarchy a :BacktestConfiguration ;
    skos:notation "SYSTEM_WITH_HIERARCHY" .
# ... the other four ...

:configuration a owl:ObjectProperty, owl:FunctionalProperty ;
    rdfs:range :BacktestConfiguration .   # no rdfs:domain: shared by StrategyBook and BacktestRun
```

` :configuration` is required on every `:StrategyBook` and every `:BacktestRun`; it is optional on
`:RunConfiguration` because there is one label-level configuration body, not one per book. The
five individuals are vocabulary, not run data. The labels table (§8) freezes their bilingual
labels. `:armCode` remains on the books/alerts/actions/weights/performance/summaries/tests as raw
engine provenance; no query may infer the configuration from it.

The loader maps the manifest `configuration` string to the individual through a closed dictionary;
an unknown string is an error. The manifest, not the book code, decides which book is the System.

### 1.3 Key and graph names

The global key is `(label, configuration, window)`, from `manifest_final.json`. `backtest_run_id`,
`book_id`, `alert_id`, `action_id` and `rebalance_id` are **local to one engine DB**; the
with- and without-hierarchy DBs both start at 1. They are stored as literal properties for
traceability but never used as graph names or IRI stems.

Current naming:

```text
urn:graph:derived:backtest:{label}:{window}:{run_id}
urn:graph:derived:backtest:selection:{label}:{window}:{run_id}
urn:graph:derived:backtest:meta:{label}
urn:graph:derived:backtest:aggregates:{label}
urn:graph:derived:backtest:external:{label}
```

Proposed naming:

```text
urn:graph:derived:backtest:{label}:{window}:{configuration_slug}
urn:graph:derived:backtest:selection:{label}:{window}:{configuration_slug}
urn:graph:derived:backtest:meta:{label}
urn:graph:derived:backtest:aggregates:{label}:{configuration_slug}
urn:graph:derived:backtest:external:{label}          (MARKOWITZ_MV, unchanged)
urn:graph:derived:backtest:series:{label}:{configuration_slug}  (block E, later)
```

`configuration_slug` is lower-case: `system_with_hierarchy`, `system_without_hierarchy`,
`markowitz_base`, `markowitz_mv`, `spy`. Examples:

```text
urn:graph:derived:backtest:final:P1:system_with_hierarchy
urn:graph:derived:backtest:final:P1:system_without_hierarchy
urn:graph:derived:backtest:final:P1:markowitz_base
urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy
```

The meta graph remains one per label because it holds one `RunConfiguration_final` and one
`BacktestRun` per key; its rows carry `:configuration` and `:windowId`. The aggregates graph is
proposed per configuration because the aggregates are per book; if the delivery keeps one
label-level aggregates file, the loader may instead keep `aggregates:{label}` and link each row to
its book. This is question Q2. If the per-configuration form is chosen, the gate
`_BACKTEST_AGGREGATES_TARGET` must accept the extra configuration slug; if the label-level form is
chosen, it stays unchanged. `MARKOWITZ_MV` stays in `external:{label}`; the new engine graphs do
not touch it.

Proposed IRI stems (the key is in every stem; a local integer id is only a suffix):

| Entity | IRI |
|---|---|
| Book | `:Book_{label}_{window}_{configuration_slug}` |
| Rebalance | `:Rebalance_{label}_{window}_{configuration_slug}_{rebalance_id}` |
| Guard alert | `:GuardAlert_{label}_{window}_{configuration_slug}_{alert_id}` |
| Guard action | `:GuardAction_{label}_{window}_{configuration_slug}_{action_id}` |
| Daily weight | `:BookWeight_{label}_{window}_{configuration_slug}_{YYYYMMDD}_{holding}` |
| Daily performance | `:BookPerf_{label}_{window}_{configuration_slug}_{YYYYMMDD}` |
| Period summary | `:PeriodSummary_{label}_{window}_{configuration_slug}_{segment}` |
| Backtest test | `:BacktestTest_{label}_{window}_{configuration_slug}_{segment}_{test}` |
| Selection cycle | `:Cycle_{label}_{window}_{configuration_slug}_{cycle_id}` |
| Ranking snapshot | `:Snap_{label}_{window}_{configuration_slug}_{cycle_id}_{asset_id}` |
| Veto | `:Veto_{label}_{window}_{configuration_slug}_{veto_id}` |
| Backtest run | `:Run_{label}_{window}_{configuration_slug}` |
| Decision event | `:Decision_{label}_{window}_{configuration_slug}_{date}` |
| Stop event | `:Stop_{label}_{window}_{configuration_slug}_{date}_{ticker}` |
| Replacement | `:Replacement_{label}_{window}_{configuration_slug}_{date}_{ticker}` |

The graph gate patterns change from `{label}:{window}:{run_id}` to
`{label}:{window}:{configuration_slug}` in `_BACKTEST_TARGET` and
`_BACKTEST_SELECTION_TARGET`; the configuration slug is
`[a-z][a-z0-9_]{1,31}`. The window pattern becomes `P<n>|H<n>|C1` / `C[0-9]+`. The
`_BACKTEST_META_TARGET` and `_BACKTEST_EXTERNAL_TARGET` remain label-level.

### 1.4 `window_id` and C1

The manifest has `windows: P1,H1,P3,H2,P2,H3,C1`. C1 is an independent continuous run starting at
1.0, not a seventh contiguous calendar window. The current code rejects it in three places:
`WINDOW_PATTERN` / `_window`, the gate `_BACKTEST_TARGET`, and every SHACL `windowId` pattern
(`^[PH][0-9]+$` or `^[PH][0-9]+[a-z]?$`). Change them to `^([PH][0-9]+|C[0-9]+)$` and the segment
pattern to `^([PH][0-9]+|C[0-9]+)[a-z]?$` (if C1 has no cut, the optional suffix harms nothing).

### 1.5 C1 text to update (the old “absent” decision is superseded)

| File | Current text to change |
|---|---|
| `docs/labels-design.md` | line 60 “C1 (continuous run) — Absent… must not become one”; lines 397, 522, 548, 661, 681, 704, 710, 726, 794, 828, 885 (C1 absent / no concept / not in knowledge base) |
| `.specify/memory/PLAN.md` | lines 3334–3343 (six windows, no C1; C1 gets no concept/IRI) |
| `.specify/memory/TASKS.md` | line 1335 (absence of C1) |
| `docs/ttyg/instructions-v1.3.md` | line 17 “all six windows”, line 31 windows list, line 90 “C1 … not in the knowledge base used” |
| `docs/ttyg/evaluation-questions.md` | line 17 honesty list includes C1 |
| `docs/07-ontology-topology.md`, `docs/08-agent-architecture.md`, `docs/06-ontology-definition.md` | window vocabularies list only P/H; add C1 as an independent continuous run |
| `docs/final-delivery.md`, `docs/backtest-load-runbook.md` | six-window folder descriptions; add C1 where the final delivery includes it |
| `schema/labels.ttl` | add `:Window_C1` with `skos:notation "C1"` and the C1 dates when approved; update the `RunLabel_final` comment “six windows” |
| `schema/tbox.ttl` | `:windowId` comment and `:StrategyBook`/`:BookRebalance` definitions mention P/H only |
| `schema/shapes.ttl` | every `windowId`/`segment` pattern (lines 464, 512, 596, 621, 623, 646, 648, 683, 703, 753, 769, 771) |
| `src/projection/backtest.py` | `WINDOW_PATTERN`, `_window`, graph/selection names |
| `src/kg_store/gate.py` | `_BACKTEST_TARGET` / `_BACKTEST_SELECTION_TARGET` window patterns |
| `tests/test_labels.py` | the assertion that `"C1"` is absent; replace it with an assertion that C1 exists and is the only continuous code |

The C1 label table is part of the second label table (§8); do not write `labels.ttl` in this PR.

---

## 2. Which rows load (full)

### 2.1 The five filters

| Rule | Pilot evidence | Projector filter | Test |
|---|---|---|---|
| Only the manifest-named books | 3 books in the pilot; with hierarchy loads `MARKOWITZ_BASE` (1) + `TOPN_MV_GUARD_NO_NLP` (3); the twin (2) is not loaded. Without hierarchy loads `MARKOWITZ_BASE` + `TOPN_MV_NOGUARD`. | Join `v_book` to the manifest `configuration`, `book_code`, `book_id`, `run_id`; reject a mismatch; skip every other book. | A fixture with 3 books loads exactly 2; the twin's rebalances/weights/performance are absent. |
| Only alerts with at least one loaded action | 578 alerts; 251 loaded. `L4_DD` 196 and the twin's 131 `L1_BP_*` alerts have only `ARM_DISABLED` actions. | Build the loaded action set first; filter alerts by `alert_id` in that set. | A twin-only alert and an `L4_DD` alert are absent; a loaded `L0_*` alert is present. |
| NEVER `ARM_DISABLED` | 648 actions; 321 loaded, 327 disabled (196 L4 + 71 stop + 60 reentry). | Drop `status == "ARM_DISABLED"` before alert filtering. | No `:status "ARM_DISABLED"` in the graph; `BLOCKED` and `APPLIED` remain. |
| Only the 4 System-vs-`MARKOWITZ_BASE` tests | 12 tests; 4 with hierarchy vs `MARKOWITZ_BASE`, 8 with the twin. The without-hierarchy DB has 4 System-vs-`MARKOWITZ_BASE`; there is no test between the two System configurations (different runs). | Keep `arm_a == manifest System book_code` and `arm_b == "MARKOWITZ_BASE"`; exactly 4 per System/window. | 12 test rows load 4; the 8 twin tests are absent. |
| `MARKOWITZ_BASE` once per window | The same book is in both DBs. | Load it from the manifest `MARKOWITZ_BASE` entry; dedupe by `(label, MARKOWITZ_BASE, window)`; never load it twice. | One `:Book_..._markowitz_base`, one set of weights/performance/summary; no duplicate. |

### 2.2 The row counts that follow

| View | Pilot rows | Loaded in the with-hierarchy DB | Why |
|---|---:|---:|---|
| `v_book` | 3 | 2 | twin not loaded |
| `v_book_rebalance` | 30 | 20 | 2 books × 10 |
| `v_book_weight_daily` | 16,943 | 12,169 | Markowitz 6,663 + System 5,506; twin 4,774 excluded |
| `v_book_daily_performance` | 588 | 392 | 2 × 196 |
| `v_portfolio_period_summary` | 3 | 2 | P1; P2 adds P2a/P2b per book |
| `v_backtest_test` | 12 | 4 | System vs Markowitz only |
| `v_guard_alert` | 578 | 251 | 12 L0 + 70 L1_BP_STOP + 127 L1_BP_STOP_BLOCKED + 42 L1_BP_REENTRY |
| `v_guard_action` | 648 | 321 | 12 L0 + 140 stop + 127 blocked + 42 reentry; 327 disabled excluded |

The without-hierarchy DB has no loaded guard alert or action: its `TOPN_MV_NOGUARD` book is the
System without the hierarchy, and any `ARM_DISABLED` rows are excluded. Its loaded rows are its
book, 10 rebalances, its weights/performance/summary and its 4 System-vs-`MARKOWITZ_BASE` tests.
The pilot's twin book (4,774 weights, 196 performance rows, 10 rebalances) is the **proxy** for
that System in the volume budget.

### 2.3 What is deliberately not a source

- `rankings.json` (10 decisions, 5,040 rows) is the `v_cycle_ranking` table extracted per decision.
  The existing selection projector already loads `v_cycle_ranking` (and its components); do not
  load `rankings.json` as a second source. Use it as a key/count cross-check only.
- `panels.json` (10 decisions, 496–499 ids) is ids only. It is not needed to answer the audit
  questions; do not load it. It may be used to validate that the risk-model panel covers the
  selected names.
- `scales.json` (12 changes) duplicates the `L0_*` alerts; do not load it separately.
- `retention.jsonl` (19 lines: 10 decisions + 9 `retention_decision`) is an extract of the detail
  file. Do not load it separately. In the with-hierarchy DB the System's retention is inside
  `decision.retention`; the 9 twin records are not loaded. In the without-hierarchy DB the only
  detail kind is `retention_decision`; those 9 records are loaded as the System's retention.
- `blocked` and `reentry` JSONL kinds duplicate `L1_BP_STOP_BLOCKED` and `L1_BP_REENTRY` alerts;
  load the DB alerts, not a second event copy.
- `decision.optimizer_target` and `decision.target` are not loaded as new triples. On the 9
  post-formation decisions they equal the `v_book_weight_daily.final_target_weight` rows already
  projected (checked exactly on the pilot); the formation decision (2021-12-31) has no target rows,
  so it alone gets the 20 `:FormationTarget` nodes of §4.
- `decision.candidate_ids` (1,022 ids in 10 decisions) is not loaded one triple per candidate. The
  ordinary pool P is already in the selection graph (`:selectedForBook`, 100 per decision). The
  graph loads only the deltas: 127 blocked alerts, 81 refill links, 22 retained holds.

---

## 3. Rules catalog and shapes (full)

### 3.1 New rules

Add to `schema/rules.ttl`, with `:category "GUARD"`, bilingual labels/comments and a
`:GraphPredicate` or `:hasClause` consistent with the existing GUARD rules:

| `ruleId` | `guardLayer` | `validFrom` | Meaning |
|---|---:|---|---|
| `L0_CARTERA_ACTIVATION` | 0 | `2019-01-02` | Portfolio tail risk crosses the threshold; scale leaves 1. |
| `L0_CARTERA_SCALE_CHANGE` | 0 | `2019-01-02` | A scale already below 1 changes again. |
| `L0_CARTERA_RECOVERY` | 0 | `2019-01-02` | The scale returns to 1. |
| `L1_BP_STOP_BLOCKED` | 1 | `2019-01-02` | A name in the stop memory is blocked at a decision (state `BLOCKED`). |

`L1_BP_STOP` and `L1_BP_REENTRY` stay. `L0_*` and `L1_BP_STOP_BLOCKED` must resolve for the
2022 pilot; `2019-01-02` is the calibration-window convention already used by the GUARD rules.
Reviewer A may prefer a different `validFrom`; it is question Q3.

### 3.2 `GuardAlertShape`

Current shape (`schema/shapes.ttl:507-540`) rejects the new data:

- `:guardLayer` is `minInclusive 1`, `maxInclusive 4`; L0 alerts have 0.
- `:alertRule` is a closed `sh:in` of the seven old rule IRIs; L0 and `L1_BP_STOP_BLOCKED` would
  be rejected.
- `:alertState` `sh:in ("ENTER" "EXIT" "ACTIVE" "COOLDOWN" "SCALE")`; `BLOCKED` is missing.
- The `sh:xone` first branch lists only `L1_BP_STOP` and `L1_BP_REENTRY`; an
  `L1_BP_STOP_BLOCKED` alert falls into the second branch and is forced to carry a decimal
  `:alertThreshold`, which is a price.
- `:alertValue` has no per-rule exclusion; it can carry the close/level of an `L1_BP_*` alert.

Change:

```turtle
sh:property [ sh:path :guardLayer ; sh:datatype xsd:integer ;
              sh:minCount 1 ; sh:maxCount 1 ; sh:minInclusive 0 ; sh:maxInclusive 4 ] ;
sh:property [ sh:path :alertRule ; sh:class :RuleDefinition ; sh:minCount 1 ; sh:maxCount 1 ;
              sh:in ( :Rule_L0_CARTERA_ACTIVATION :Rule_L0_CARTERA_SCALE_CHANGE
                      :Rule_L0_CARTERA_RECOVERY :Rule_L1_STOP_LOSS :Rule_L1_REENTRY
                      :Rule_L1_BP_STOP :Rule_L1_BP_REENTRY :Rule_L1_BP_STOP_BLOCKED
                      :Rule_L2_NEWS :Rule_L3_VOL :Rule_L4_DD ) ] ;
sh:property [ sh:path :alertState ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ;
              sh:in ("ENTER" "EXIT" "ACTIVE" "COOLDOWN" "SCALE" "BLOCKED") ] ;
sh:xone (
  [ sh:property [ sh:path :alertRule ;
                  sh:in ( :Rule_L1_BP_STOP :Rule_L1_BP_REENTRY :Rule_L1_BP_STOP_BLOCKED ) ] ;
    sh:property [ sh:path :alertThreshold ; sh:maxCount 0 ] ;
    sh:property [ sh:path :alertValue ; sh:maxCount 0 ] ]
  [ sh:property [ sh:path :alertRule ;
                  sh:not [ sh:in ( :Rule_L1_BP_STOP :Rule_L1_BP_REENTRY :Rule_L1_BP_STOP_BLOCKED ) ] ] ;
    sh:property [ sh:path :alertThreshold ; sh:datatype xsd:decimal ;
                  sh:minCount 1 ; sh:maxCount 1 ] ]
) .
```

The `L1_BP_*` rule ids are the **only** price-publishing rules. For every one of them, neither
`:alertThreshold` nor `:alertValue` is written. `L0_*` value/threshold are portfolio tail-risk
figures (CVaR95 of 63 sessions and the 80th percentile of 252 sessions), not prices; they load.
`L4_DD` is not loaded by the new delivery; its old value/threshold rules are historical.

### 3.3 `GuardActionShape`

Add `BLOCKED` to `:status`:

```turtle
sh:property [ sh:path :status ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ;
              sh:in ("APPLIED" "ARM_DISABLED" "NOT_HELD" "SUPERSEDED" "BLOCKED") ] .
```

`ARM_DISABLED` remains in the shape for historical graphs, but the new loader never writes it.
`BLOCKED` actions have no weights and no asset/ticker in the pilot (127 rows); the shape's optional
`:guardAsset`/`:guardTicker`/`:weightBefore`/`:weightAfter` allow that.

### 3.4 Window shapes

Change every `:windowId` pattern from `^[PH][0-9]+$` to `^([PH][0-9]+|C[0-9]+)$` and every
`:segment` pattern from `^[PH][0-9]+[a-z]?$` to `^([PH][0-9]+|C[0-9]+)[a-z]?$` (C1 has no
P2a/P2b cut; the optional suffix is harmless). This affects `GuardAlertShape`,
`BookDailyPerformanceShape`, `PortfolioPeriodSummaryShape`, `BacktestTestShape`,
`StrategyBookShape`, `BookRebalanceShape` and any selection shape with a window field.

### 3.5 Projector defence in depth

`src/projection/backtest.py::_alerts` already suppresses `:alertThreshold` for any rule whose id
starts with `L1_BP_`. Change it to:

1. choose the rule id first;
2. for `L1_BP_*`, **force the projected value to `None` and never read the source `value` as a
   price**; do not add `:alertValue` or `:alertThreshold`;
3. for every other rule, keep the existing value/threshold handling;
4. after building the alert, assert that no `L1_BP_*` alert has `:alertValue` or
   `:alertThreshold`; a regression raises `ProjectionError` and fails the run.

The source `value` on `L1_BP_STOP`/`L1_BP_STOP_BLOCKED` is a close or stop level, not None; the
"assert value is None" means **the projected value** is None. A loader that tries to project the
source value must fail.

### 3.6 Negative tests

- An `L1_BP_STOP` alert with `:alertThreshold` fails SHACL.
- An `L1_BP_STOP_BLOCKED` alert with `:alertThreshold` fails SHACL.
- An `L1_BP_STOP`/`L1_BP_STOP_BLOCKED` alert with `:alertValue` fails SHACL.
- The projector on a row with a non-null `value` for an `L1_BP_*` rule emits no `:alertValue` and
  the post-build assertion passes; a monkeypatched regression that adds one raises.
- An `L0_*` alert with `:alertValue` and `:alertThreshold` passes.
- An alert with `:alertState "BLOCKED"` and a `BLOCKED` action passes; `ARM_DISABLED` is filtered,
  not shape-tested as loaded data.
- A `C1` `:windowId` passes every shape.

### 3.7 The old rules

The old layer-1/3/4 rules are `L1_STOP_LOSS`, `L1_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD`.
The new hierarchy drops layers 3 and 4; `L2_NEWS` is off in the pilot and belongs to the future news
module. Options:

| Option | Effect | Recommendation |
|---|---|---|
| `:validTo` at the adoption boundary | The rule stays in the catalog, resolves for historical data, and is not in force for the new delivery. | **Recommended** for `L3_VOL` and `L4_DD`: keep the definitions, add a bilingual comment “registered System only; not part of the Veto Hierarchy”, and close them with `:validTo` at the new adoption date. `L1_STOP_LOSS`/`L1_REENTRY`/`L2_NEWS` stay historical with the same comment; no new alert uses them. |
| Comment only, no `:validTo` | The rules remain “in force” in the resolver although unused; the agent may describe them as current. | Not recommended. |
| Delete | Breaks the valid-time history and the old graph resolution; the repository never deletes rules. | Rejected. |

The exact `:validTo` date and whether `L3_VOL` remains a definition are question Q4 for Reviewer A.

---

## 4. Detail file and per-decision files (full)

### 4.1 The pilot detail file

`H1C-B5-P1.cartera_v1_3.kg.jsonl`: **271 lines**.

| `kind` | Rows | Unique key | Loaded as |
|---|---:|---|---|
| `decision` | 10 | `date` | `:DecisionEvent` + retention + refill links |
| `stop` | 70 | (`date`, `asset_id`) | `:StopEvent` + options + summary |
| `replacement_bought` | 7 | (`order_date`, `asset_id`) | `:ReplacementPurchase` |
| `replacement_check` | 5 | (`date`, `asset_id`) | `:ReplacementCheck` |
| `replacement_stopped` | 1 | (`date`, `asset_id`) | `:replacementStoppedBy` link |
| `blocked` | 127 | (`date`, `asset_id`) | **not a new event**: `L1_BP_STOP_BLOCKED` `:GuardAlert`/`:GuardAction` |
| `reentry` | 42 | (`date`, `asset_id`) | **not a new event**: `L1_BP_REENTRY` `:GuardAlert`/`:GuardAction` |
| `retention_decision` | 9 | (`date`, `arm`) | with-hierarchy twin: not loaded; without-hierarchy System: `:RetentionDecision` |

The 271 lines are all parsed and validated. They do not all become new individuals: 127 blocked and
42 reentry lines are already the 127+42 loaded alerts; the 9 `retention_decision` lines are the
twin's retention in the with-hierarchy DB (not loaded), and the without-hierarchy detail file has
the same shape for its System.

### 4.2 Decision and retention

**`:DecisionEvent`** — one per `decision` (10). Key `(label, configuration, window, date)`.
Properties: `:decisionOfBook`, `:decisionDate`, `:filterState` (boolean; true = invested/not
evaluable), `:filterDecisionDate`, `:coreWeightInForce`, `:exposureScale`, `:candidatePoolSize`
(100), `:candidateSetSize`, `:blockedCount`, `:retainedCount`, `:selectionCycle`,
`:bookRebalance`, `:knowledgeDate`. 14 fixed triples ×10 = 140.
- **`:FormationTarget`** — only the first decision (2021-12-31) has no `BookWeightDaily` target
  rows; load its 20 target entries as 20 nodes with type, `:targetOfDecision`, `:targetAsset`,
  `:targetWeight`: 20 × 4 = 80 triples. The other 9 decisions use the existing
  `BookWeightDaily.finalTargetWeight` rows (checked equal on the pilot).
- **`:refilledCandidate`** — one link per name that entered the candidate set by refill and is not
  in P: 81 links. Retained names are the `:RetentionHold` links; blocked names are the alerts.

**`:RetentionDecision`** — one per decision with retention on (10 with hierarchy; 9 in the
without-hierarchy proxy). Properties: `:retentionOfDecision`, `:poolSize`, `:heldOutsidePoolCount`,
`:retainedCount`, `:rejectedCount`, `:counterDroppedCount`, `:keptCount`, `:keptWeight`,
`:candidateSetSize`, `:maxDecisions` (3), `:retentionEnabled` (true), `:knowledgeDate`; 13 ×10 =
130 (with) / 117 (without).
- **`:RetentionHold`** — one per retained occurrence: type, `:holdOfDecision`, `:retainedAsset`,
  `:retentionCounter` (1..3), `:rankingSnapshot` (the existing `:Snap_*`), 5 triples ×22 = 110
  (with) / 43 ×5 = 215 (without).
- **`:RetentionRejection`** — one per rejected occurrence: type, `:rejectionOfDecision`,
  `:rejectedAsset`, `:rejectionCause`, `:retentionCounter`, `:rankingSnapshot`, 6 ×6 = 36 (with) /
  7 ×6 = 42 (without).
- **`:counterDroppedAsset`** — one link per name that reached counter 3: 4 (with) + 4 (without).

Pilot retention counts: with hierarchy 22 retained, 6 rejected, 4 counter drops; without-hierarchy
twin proxy 43 retained, 7 rejected, 4 counter drops. The question “retention counter 1..3, who was
kept, rejected with cause” is answered directly.

### 4.3 Stop, destination and cash

**`:StopEvent`** — 70 nodes. Key `(label, configuration, window, date, ticker)`.
Fixed 14 triples: type, `:stopOfBook`, `:stopDate`, `:stoppedAsset`, `:weightBefore`, `:filterState`,
`:filterDecisionDate`, `:exposureScale`, `:rhoW0`, `:rho`, `:chooser`, `:cashLeft`,
`:portfolioCheckPassed`, `:knowledgeDate`.
Optional in the pilot: `:stopCashCause` on 63 cash stops; `:eligibleCount`, `:zoneEvaluated`,
`:zonePass` on all 70; `:aStar` and `:sizeFraction` on the 20 stops with a candidate test; `:chosenCash`
on 63; `:chosenOption` on 7; `:rhoDeltaMin`/`:rhoDeltaMedian`/`:rhoDeltaMax` on 20 (60 triples);
`:weightAfterE3` on 0. Total **1,423**.
- `:DestinationOption` — 33 nodes, one per menu item (7 non-empty menus: 6×5 + 1×3). Each:
  type, `:optionOfStop`, `:optionAsset`, `:optionIsSpy`, `:optionRho`, `:optionR`, `:optionBeta`,
  `:optionRank`, `:optionScore`, `:optionSector`, `:optionSizeFraction`, `:optionWeight`,
  `:menuPosition`; 13 ×33 = **429**. The option is reached from the stop by `:optionOfStop`; no
  inverse duplicate.
- `:StopRejectionSummary` — 20 nodes, one per stop with `eligible_counts`. Type + `:summaryOfStop`
  + one integer property per **nonzero** rejection cause. The pilot has 191 nonzero fields,
  including 20 `zone_evaluated`; the stop already carries `:zoneEvaluated`, so the summary loads
  the other **171** cause values. Total 20×2+171 = **211**. The causes are the 13 dictionary keys
  (`hard_veto`, `soft_penalty`, `news_veto`, `held`, `memory`, `not_ranked`, `no_risk_model`,
  `no_bar`, `missing_return`, `trend_break`, `sector_cap`, `spy_limit`, `zone_high`) plus
  `no_allowed_destination` (13 in the pilot). No JSON blob.
- The stop `menu` choices: 63 cash (47 `FILTER_OFF`, 13 `NO_ALLOWED_DESTINATION`, 3
  `SCALE_BELOW_ONE`), 7 replacements, 0 SPY. The 7 replacement choices are linked to
  `:ReplacementPurchase`; the 63 cash choices carry `:chosenCash true` and `:stopCashCause`.

**`:StopMemory`** — 51 unique stopped assets. Properties: type, `:memoryOfBook`, `:memoryAsset`,
`:memorySince` (first stop date); `:memoryReleasedOn` for the 35 unique assets that reentered.
204 +35 = **239**. The stop memory level is a **price and is not stored**; the blocked/reentry
alerts and the stop date answer “since when” without it.

### 4.4 Replacement

**`:ReplacementPurchase`** — 7 nodes. Type, `:purchaseOfStop`, `:replacementAsset`, `:orderDate`,
`:executionDate`, `:machineEntrySession`, `:weight`, `:sizeFraction`, `:rank`, `:rankBucket`,
`:filterState`, `:filterDecisionDate`; 12 ×7 = 84. **`:ReplacementCheck`** — 5 nodes: type,
`:checkOfPurchase`, `:checkDate`, `:candidate`, `:kept`; 5 ×5 = 25. `replacement_stopped` is one
`:replacementStoppedBy` link from the purchase to the stop event; **1**. Total **110**.
`stop_distance_pct` is not loaded (see §5).

### 4.5 Answering the required questions

| Question | Graph path |
|---|---|
| Why was stock X sold on date D? | `?stop :stoppedAsset :X ; :stopDate "D" ; :stopOfBook ?book` plus the `L1_BP_STOP` `:GuardAlert` joined by `(date, asset)` (no duplicate link), and `:stopCashCause`/`:chosenOption`. |
| Where did the freed weight go? | `?stop :chosenOption ?option` or `:chosenCash true ; :cashLeft ?c ; :stopCashCause ?cause`; replacement via `?purchase :purchaseOfStop ?stop`. |
| Destination menu with figures | `?option :optionOfStop ?stop` with `:optionRho`, `:optionR`, `:optionBeta`, `:optionRank`, `:optionScore`, `:optionSector`, `:optionSizeFraction`, `:optionWeight`, `:menuPosition`. |
| Exposure-scale path and risk episodes | `:DecisionEvent`/`:StopEvent` `:exposureScale`; `L0_*` alerts with `:alertDate`, `:alertValue`, `:alertThreshold`, `:weightBefore`, `:weightAfter`. Episodes are derived by date order. |
| Which names are blocked and since when? | `?memory :memoryAsset ?asset ; :memorySince ?since`; `L1_BP_STOP_BLOCKED` alerts by date; `:memoryReleasedOn` for reentry. |
| Retention 1..3, kept, rejected cause | `:RetentionHold` `:retentionCounter`; `:RetentionRejection` `:rejectionCause`; `:RetentionDecision` counts. |
| Candidate pool per decision | The selection graph's `:selectedForBook` (100) plus the `:refilledCandidate` links, `:RetentionHold` and the blocked alerts. |
| Filter state | `:DecisionEvent :filterState`, `:filterDecisionDate`, `:coreWeightInForce`; `:StopEvent` copy. |

The full `candidate_ids` (1,022), `optimizer_target`/`target` (except formation) and
`panels.json` are not loaded. This is priced in §6 and repeated in §4.6.

### 4.6 What is not loaded and why

- `stop_distance_pct` in `stop`, `replacement_bought`, `blocked`, `reentry`: price-derived; §5.
- `blocked`/`reentry` as separate events: duplicate the loaded alerts/actions.
- Full candidate IDs, full target/optimizer maps, `rankings.json`, `panels.json`, `scales.json`,
  `retention.jsonl`: duplicate the selection projection, the `BookWeightDaily` targets, the L0
  alerts or the decision retention.
- `eligible_counts` zeros and the `rho` duplicate of `rho_w0`: the summary omits zeros; `:rho` is
  loaded once (the pilot repeats `rho_w0`).
- `portfolio_check.reasons`: empty in all 70 pilot stops; the boolean `:portfolioCheckPassed` is
  loaded, reasons only if non-empty (none in the pilot).
- `weight_after_e3`: absent in the pilot; the property is reserved for the v1.3.3 close.

---

## 5. Price masking (full)

### 5.1 The rule and the existing flag

No absolute price and no daily return of any of the 33 companies in
`mascara_tiingo/tiingo_assets.csv` may enter any table. The 33 assets already carry
`:pricesNotPublished true` in `urn:graph:derived:fundamentals:final`; the backtest graph links to
the same `:Asset` IRIs and does not duplicate the flag. The fundamentals graph also excludes their
market capitalisation and valuation metrics. The new delivery's only price-bearing columns are
`guard_alert.threshold` and `guard_alert.value` for `L1_BP_*`; the dictionary §1.3 corrects the
earlier claim that the threshold was no longer projected.

### 5.2 Verdict per field

| Field | Verdict | Reason |
|---|---|---|
| `guard_alert.value` on `L1_BP_STOP` | **Omit** | It is the close (a price). |
| `guard_alert.threshold` on `L1_BP_STOP` | **Omit** | It is the stop level (a price). |
| `guard_alert.value` on `L1_BP_STOP_BLOCKED` | **Omit** | The close on the decision date (a price). |
| `guard_alert.threshold` on `L1_BP_STOP_BLOCKED` | **Omit** | The level stored in the stop memory (a price). |
| `guard_alert.value`/`threshold` on `L1_BP_REENTRY` | **Omit** | The value is the stop level; the threshold is 0. |
| `guard_alert.value`/`threshold` on `L0_*` | **Load** | Portfolio CVaR95 (63 sessions) and its 80th-percentile threshold, not prices. |
| `guard_alert.value`/`threshold` on `L4_DD` | **Not loaded** | L4 is not part of the new hierarchy; historical data only. |
| `book_daily_performance.nav` | **Load** | Book net asset value (an index), not a company price. |
| `gross_return`, `net_return`, `cost_return`, `drawdown`, `cash_weight`, `turnover`, `n_equity` | **Load** | Book-level returns/weights/counts, not individual asset prices or daily returns. |
| `book_weight_daily.markowitz_target_weight`, `final_target_weight` | **Load** | Fractions of the book. |
| `stop_distance_pct` (stop/replacement/blocked/reentry) | **Omit for every company** | It is (close − level)/close×100, computed from two prices. It is not an absolute price or a daily return, but it is price-derived; for the 33 masked companies it could narrow the stop/close range, and a field that exists only for unmasked companies adds a second rule and a second test. The audit questions do not need it: the stop cause, the chosen option and the menu figures explain the event. If Reviewer A wants it for unmasked names only, it is a separate later property with its own mask test. |
| `beta` (menu/replacement) | **Load** | 252-session regression coefficient against SPY, not a price. |
| `rho`, `rho_w0`, `R` | **Load** | Portfolio risk ratios/CVaR, not prices. |
| `rank`, `score`, `bucket` | **Load** | Dimensionless ranking/score. |
| `sector` (engine id) | **Load** | Categorical engine id; map later if the graph needs the GICS sector. |
| `size_fraction`, `weight`, `a_star`, `cash_left`, `core_weight_in_force`, `scale` | **Load** | Fractions of the book. |
| `eligible_counts`, `zone_evaluated`, `zone_pass`, `eligible` | **Load** | Counts. |
| `close`, `level`, `stop`, `stop_level` | **Reject if present** | The JSONL says they were removed; the loader allowlist fails if one appears. |
| `market_capitalization`, `enterprise_value` | **Not in this delivery** | Fundamentals already masks the 33 assets; no new field. |
| `manager_calls` prompts/answers | **No full prompt** | Store hashes/pointers only; model text is generated, not price data. |

### 5.3 The old 12 triples

The current `portfolio` may hold `:alertThreshold` on 12 `L1_BP_STOP` alerts of Tiingo companies
from the old `final` graph (dictionary §1.3). The new delivery omits **all** `L1_BP_*`
thresholds/values, not only the 33. When the old `final` backtest graphs are replaced, those 12
triples disappear. If the old graph is kept, the maintainer removes the 12 by replacing the affected
graph, not by a loader-side deletion; the loader never deletes.

### 5.4 Hermetic test plan

- A synthetic `L1_BP_STOP`/`L1_BP_STOP_BLOCKED` batch with `:alertThreshold` or `:alertValue` fails
  SHACL.
- The projector on a row with a non-null `value` for an `L1_BP_*` rule emits no `:alertValue`; the
  post-build assertion passes; a regression that tries to add it raises.
- A stop/menu/purchase record containing `stop_distance_pct` is accepted by the parser but **no
  `:stopDistancePct` triple** is written; the property is absent from the output.
- A synthetic masked asset (`:pricesNotPublished true` in the fundamentals context) with a stop
  menu has no `:alertValue`, `:alertThreshold`, `:stopDistancePct`, `:closePrice` or daily-return
  property.
- A batch-level scan asserts none of `:alertValue`, `:alertThreshold`, `:stopDistancePct`,
  `:closePrice`, `:dailyReturn`, `:PriceObservation` appears on an `L1_BP_*` alert or any masked
  asset.
- The loader rejects a JSONL object with any of `close`, `level`, `stop`, `stop_level`.

---

## 6. Volume (full)

### 6.1 Exact pilot row counts

| Item | Pilot |
|---|---:|
| Books / loaded in with-hierarchy | 3 / 2 |
| Rebalances (3 books / loaded 2) | 30 / 20 |
| Weight rows (3 books / loaded 2) | 16,943 / 12,169 |
| Performance rows (3 books / loaded 2) | 588 / 392 |
| Segment summaries (P1, 3 books / loaded 2) | 3 / 2 |
| Tests (12 / loaded System-vs-Markowitz) | 12 / 4 |
| Alerts (578 / loaded) | 578 / 251 |
| Actions (648 / loaded) | 648 / 321 |
| Detail events | 271 |
| Menus / options | 7 / 33 |
| Selection cycles (all / decision) | 22 / 10 |
| `v_cycle_ranking` rows (all / decision) | 10,484 / 5,040 |
| `v_veto` rows (all / decision) | 1,442 / 1,010 |

### 6.2 Current m018 model, measured on the pilot

The current projector, run read-only on the pilot rows for all 3 books with the 8
System-vs-Markowitz tests and the loaded alerts/actions, produces **207,109 triples**. The four new
rule entries were supplied in memory to let the projector resolve them; no code was changed. The new
design adds `:configuration` (3 books), `:systemVariant`/`:poolSize`/`:retentionEnabled` on the two
System books (6), and removes the 197 `L1_BP_*` `:alertValue` triples (70 stop + 127 blocked):
**206,921** for the m018 side of a window.

### 6.3 New event model, exact from the pilot

| Class / link | Nodes | Triples |
|---|---:|---:|
| `:DecisionEvent` | 10 | 140 |
| `:refilledCandidate` links | 81 | 81 |
| `:FormationTarget` | 20 | 80 |
| `:RetentionDecision` (with) | 10 | 130 |
| `:RetentionHold` (with) | 22 | 110 |
| `:RetentionRejection` (with) | 6 | 36 |
| `:counterDroppedAsset` links (with) | 4 | 4 |
| `:StopEvent` | 70 | 1,423 |
| `:DestinationOption` | 33 | 429 |
| `:StopRejectionSummary` | 20 | 211 |
| `:ReplacementPurchase` | 7 | 84 |
| `:ReplacementCheck` | 5 | 25 |
| `:replacementStoppedBy` link | 1 | 1 |
| `:StopMemory` | 51 | 239 |
| **With-hierarchy event total** | | **2,993** |
| Without-hierarchy retention (proxy: 9 records, 43 retained, 7 rejected, 4 drops) | 59 | **378** |
| **Both System configurations** | | **3,371** |

`210,292` triples per window (206,921 + 3,371). P2 adds two segment summaries per book
(6 × 20 = 120), so the 7-window m018+events budget is `210,292 × 7 + 120 = 1,472,164`.

### 6.4 Selection side

The existing selection projector on the pilot produces **322,794 triples** for 22 cycles, 10,484
rankings, 30,664 ranking components and 1,442 vetoes. Filtered to the 10 decision cycles it is
**159,683** triples (5,040 rankings, 14,819 components, 1,010 vetoes). The without-hierarchy DB has
its own selection set; the pilot's count is the proxy.

### 6.5 Total and store impact

| Scope | Per window | 7 windows |
|---|---:|---:|
| m018 + new events (3 configs) | 210,292 | 1,472,164 |
| selection, 2 System configs, all 22 cycles | 645,588 | 4,519,116 |
| **Total, all cycles** | **855,880** | **5,991,280** |
| selection, 2 System configs, 10 decision cycles | 319,366 | 2,235,562 |
| **Total, decision-only** | **529,658** | **3,707,726** |

The old `final` m018+selection graphs measure **4,164,492** triples in the last delivery's dry-run
table (`docs/final-delivery.md` step 10). The current store is about 5.0M after the fundamentals
load. If the old final graphs are replaced:

- all cycles: `5.0M − 4.164M + 5.991M ≈ 6.83M` asserted, a net **+1.83M**;
- decision-only: `5.0M − 4.164M + 3.708M ≈ 4.54M` asserted, a net **−0.46M**.

The selection side is the swing: two System selection graphs are **4.52M** all-cycles, more than
the old one-selection 2.05M. The old `final` graph's m018+selection is replaced, but the new graph
is not automatically smaller. This is question Q1.

### 6.6 `rdfsplus-optimized` inference

The new event classes are proposed as `:Observation` subclasses. The pilot event model has 313 new
individuals per window (254 with hierarchy + 59 without), so inference adds about **2,191**
`:Observation` types across 7 windows if every new event class is an `:Observation` subclass; the
exact count is measured on the rehearsal. The existing `GuardAlert`/`GuardAction`/`BookWeightDaily`
etc. already receive their inferred types today; no subproperty hierarchy is added, and no
per-value inference is introduced. The asserted budget above excludes those ~2.2k inferred
triples. Measure the actual closure on the rehearsal; do not assume a percentage.

`MARKOWITZ_MV` stays the existing external graph (about 200 triples) and is not included; the SPY
and MARKOWITZ_MV daily series are block E, later. Their graph is
`urn:graph:derived:backtest:series:{label}:{configuration_slug}`, keyed by `(label, configuration,
window, date)`; it does not collide with this design.

---

## 7. Forward-looking (short)

**News actions.** Design now, no real run yet. Add `:NewsAction` per `PoolActionRecord`, key
`(decision_date, asset_id, action)`; `:newsActionOfBook`, `:newsActionDate`, `:newsActionAsset`,
`:newsActionKind` (`veto`/`promotion`), `:replacesAsset`, `:replacedByAsset`; `:NewsEvidence` per
company with `:newsState`, `:newsN`, `:newsA`, `:newsB`, tier counts, `:meanProbabilityMargin`; the
exact test as two integer properties `:pValueNumerator`/`:pValueDenominator` (and the same for the
critical/size fractions), parsed from `"num/den"` as rationals, not floats. `:testRows` is one link
per `(item_id, ticker)` to a `:NewsItem` carrying `:itemId`, `:bodyHash`, `:url`, `:summary`, and
the ticker's asset; do not store the body. `:DateRecord` per decision carries coverage, admission
counts, base rates, expected-by-chance fractions, states and the action list. No individuals exist
in the pilot; the first real news run is a later task.

**Manager calls and narrator.** `:ManagerCall` per `manager_calls.jsonl` line, key `call_index`
local to the run, linked to the stop by `(date, stopped_asset_id)`. Carry `:agentArm`,
`:modelRequested`, `:modelResolved`, `:modelRevision`, `:reasoningEffort`, `:promptTemplateSha256`,
`:promptSha256`, `:skillPath`, `:skillFileSha256`, `:skillASha256`, `:skillPolicySha256`,
`:skillTextSha256`, `:shuffleSeed`, `:validatorPassed`, `:validatorCause`, `:answerChoice`,
`:chosenAsset`, `:fallbackUsedRule`, `:fallbackCause`, `:generatedByLanguageModel`. Do not store
full prompts or raw answers; store their SHA-256 and the file/pointer. `:NarratorText` needs the
new key `(kind, date, asset_id)` that A is adding, plus `:text`, `:source` (`model`/`template`),
`:modelRequested`/`:modelResolved`, `:promptTemplateSha256`/`:promptSha256`, `:validatorPassed`,
`:generatedByLanguageModel`. Every model text carries the sentence “generated by a language model;
not a verified fact” in its `:provenanceNote`; template text is marked false. No real calls exist
in the pilot; implement in a later task.

**Daily series.** `MARKOWITZ_MV` and `SPY` daily series are block E. Proposed graph
`urn:graph:derived:backtest:series:{label}:{configuration_slug}` with one `:DailySeriesPoint` per
`(window, date)` and `:seriesOfConfiguration`, `:seriesDate`, `:seriesValue`; the key and naming
above reserve the configuration slug (`markowitz_mv`, `spy`) and the `series` segment, so block E
does not need a rename.

---

## 8. Concept map (short)

The 31 glossary concepts and their home. “Label concept” means a `skos:Concept` in the second label
table, not in `labels.ttl` yet.

| Concept (ES / EN) | Home in the graph |
|---|---|
| Jerarquía de Veto / Veto Hierarchy | `:Configuration_SystemWithHierarchy` + label concept; its comment names the three levels. |
| GUARD de reglas / Rules GUARD | `:RuleDefinition` + `:Veto`; hard/soft rule layer; label concept. |
| GUARD de noticias / News GUARD | Future `:NewsAction`/`:DateRecord`; **no data in the pilot**; label concept. |
| GUARD de cartera / Portfolio GUARD | `L0_*` alerts, `:DecisionEvent`, `:StopEvent`; label concept. |
| Sistema sin jerarquía / System without the Veto Hierarchy | `:Configuration_SystemWithoutHierarchy`. |
| Umbral de riesgo de cola / Tail-risk threshold | `:alertThreshold` on `L0_*`; label concept. |
| Riesgo de cola de la cartera / Portfolio tail risk | `:alertValue` on `L0_*`; label concept. |
| Razón de riesgo (ρ) / Risk ratio (rho) | `:rhoW0`, `:rho` on `:StopEvent`; `:optionRho`; label concept. |
| Zona de riesgo / Risk zone | Derived from `:rhoW0`/`:rho` (LOW ≤0.90, MIDDLE ≤1, HIGH >1); no stored literal; label concept. |
| Escala de exposición / Exposure scale | `:exposureScale` on `:DecisionEvent`/`:StopEvent`; `L0_*` `:weightBefore`/`:weightAfter`; label concept. |
| Episodio de riesgo / Risk episode | Derived from `:exposureScale` dates and the `L0_*` alerts; no separate individual; label concept. |
| Destino del peso liberado / Destination of the freed weight | `:chosenOption`/`:chosenCash`/`:cashLeft` on `:StopEvent`; label concept. |
| Reemplazo / Replacement | `:ReplacementPurchase`; label concept. |
| Menú de destinos / Destination menu | `:DestinationOption` + `:optionOfStop`; label concept. |
| Causa de efectivo / Cash cause | `:stopCashCause` on `:StopEvent`; label concept. |
| Memoria de la parada / Stop memory | `:StopMemory` (`:memoryAsset`, `:memorySince`, `:memoryReleasedOn`); label concept. |
| Reentrada bloqueada / Blocked re-entry | `L1_BP_STOP_BLOCKED` `:GuardAlert`/`:GuardAction` with `BLOCKED`; label concept. |
| Sistema básico / Basic system | `:StrategyBook :systemVariant "basic"`, `:poolSize 60`, `:retentionEnabled false`; label concept. |
| Sistema completo / Complete system | Same, `"complete"`, `:poolSize 100`, `:retentionEnabled true`; label concept. |
| Retención / Retention | `:RetentionDecision` + `:RetentionHold`; label concept. |
| Contador de retención / Retention counter | `:retentionCounter` on hold/rejection; label concept. |
| Veto por noticias / News veto | Future `:NewsAction :newsActionKind "veto"`; **no data in the pilot**; label concept. |
| Promoción por noticias / News promotion | Future `:NewsAction :newsActionKind "promotion"`; **no data in the pilot**; label concept. |
| Tasa base de noticias / News base rate | Future `:DateRecord`/`:NewsEvidence` with numerator/denominator; **no data in the pilot**; label concept. |
| Cobertura temporal de noticias / News temporal coverage | Future `:DateRecord :hasTemporalCoverage`/`:coverageFirst`/`:coverageLast`; **no data in the pilot**; label concept. |
| Agente gestor / Manager agent | Future `:ManagerCall` + `:NarratorText`; **no data in the pilot**; label concept. |
| Elector / Chooser | `:chooser` on `:StopEvent` (`rule`/`agent`); future `:ManagerCall :answerChoice`; label concept. |
| Narrador / Narrator | Future `:NarratorText`; **no data in the pilot**; label concept. |
| Política de inversión del gestor / Manager investment policy | Future `:ManagerPolicy` with skill/policy hashes; **no data in the pilot**; label concept. |
| Elección de respaldo / Fallback choice | Future `:ManagerCall :fallbackUsedRule`/`:fallbackCause`; label concept. |
| Validador / Validator | Future `:ManagerCall :validatorPassed`/`:validatorCause`; label concept. |

**Concepts without a home in the pilot:** all news concepts (0 real rows), manager/narrator
concepts (0 real calls/texts), and `Manager investment policy` (no file in the pilot). They are
proposed in §7 and implemented later.

**New schema elements not in the glossary:** `:BacktestConfiguration` and its five individuals;
`:configuration`; `:systemVariant`, `:poolSize`, `:retentionEnabled`; `:DecisionEvent`,
`:FormationTarget`, `:RetentionDecision`, `:RetentionHold`, `:RetentionRejection`,
`:counterDroppedAsset`, `:StopEvent`, `:DestinationOption`, `:StopRejectionSummary`,
`:StopMemory`, `:ReplacementPurchase`, `:ReplacementCheck`; the properties `:decisionOfBook`,
`:stopOfBook`, `:stopDate`, `:chosenOption`, `:chosenCash`, `:stopCashCause`, `:rhoW0`, `:rho`,
`:optionRho`, `:optionR`, `:optionBeta`, `:optionRank`, `:optionScore`, `:optionSector`,
`:optionSizeFraction`, `:optionWeight`, `:menuPosition`, `:rejectionCause`,
`:retentionCounter`, `:candidatePoolSize`, `:candidateSetSize`, `:blockedCount`,
`:retainedCount`, `:refilledCandidate`, `:formationTarget`, `:memorySince`,
`:memoryReleasedOn`, `:replacementStoppedBy`; the rules `L0_CARTERA_*`, `L1_BP_STOP_BLOCKED`;
the states `BLOCKED`; and the future news/manager/narrator classes of §7.

The second label table (Reviewer A approves in one pass after 2026-11-14) must include the 31
concept labels plus these new schema elements, with A's English name unless it clashes with the
existing style. Do not write `labels.ttl` in this PR.

---

## 9. Loader plan (full)

### 9.1 Manifest parser

`manifest_final.json` is strict:

- exact top-level keys (the draft keys plus any A adds as a column diff), reject unknown keys;
- `manifest_version`, `label` (`final`), `created_at`, `key` exactly `["label","configuration","window"]`,
  `windows` exactly the seven values (or a subset, in any order? require the seven), `price_mask`
  (file + SHA-256 + rule), `prereg` hashes, `configurations` exactly five;
- each configuration: `configuration`, `name_es`, `name_en`, `source_kind`, `runs`; a run has
  `window`, `db_file`, `db_sha256`, `run_id`, `book_code`, `book_id`, and the relevant file keys
  (`jsonl_file`, `rankings_file`, `panels_file`, `scales_file`, `manager_calls_file`,
  `narrator_file`, `news_actions_file`, `code_version`, `files_sha256`); `MARKOWITZ_MV` has
  `daily_file`/`weights_file`/`aggregates_file`; `SPY` has `daily_file`/`window_filter`.
- `PENDIENTE` is accepted only in the draft (`status: BORRADOR`); the final manifest with a
  `PENDIENTE` value is an error.
- The manifest's file paths are relative to the delivery root; absolute paths, `..` or a missing
  file are errors. The global key is the triple `(label, configuration, window)`; duplicate keys
  are errors.
- The manifest's `price_mask` SHA-256 must match the real mask file; otherwise stop before parsing.

### 9.2 SHA-256 before parsing

Verify `SHA256SUMS` (all listed entries, including any provenance) and then every file the manifest
names, using streaming hashes; compare to the manifest `*_sha256`/`files_sha256`. Open the engine DB
`mode=ro` only after its hash matches. Never open a DB before the hash. Print the manifest hash, the
mask hash and the source DB hashes for the run record.

### 9.3 Order of load

1. schema: tbox, shapes, reference, rules, labels (the new rules and shapes must be loaded before
   the data; the loader itself does not load schema in production, `cli/load_schema.py` does).
2. meta: `urn:graph:derived:backtest:meta:{label}` — one `RunConfiguration_final` and one
   `BacktestRun` per `(label, configuration, window)`, with `:configuration`.
3. m018 per config/window in calendar order, then selection per System config/window, then
   aggregates per config, then the existing `external:{label}` (MARKOWITZ_MV) if it is not already
   in the store. The loader never touches the external graph unless the manifest says its hash
   changed; the existing external graph is a separate loader.
4. Block units: **one graph per key**. The append-only gate refuses an existing graph; a later
   correction is a new label or a new configuration window, never an append.
5. Clean reload: the maintainer drops the **old** `urn:graph:derived:backtest:final:*` graphs
   (m018, selection, meta, aggregates) by exact IRI after reviewing the listing and backup; the
   loader never drops. The new graphs have different names (configuration instead of run id), so
   the old and new families do not collide; the old family must be removed explicitly. The
   fundamentals graph and the external MARKOWITZ_MV graph stay.

### 9.4 Dry run, SHACL and store paths

- Dry run: no store; parse, filter, project, print per-key row/triple counts, and SHACL-validate
  each key's batch with a local asset/context graph. The local context includes `:Asset` types,
  tickers/CIKs and the five configuration individuals; it is not written.
- `--check-store`: open the store without `--write`, run `gate.plan` per key with `SELECT` only,
  report `would-be-written`/`already-in-the-store`/`refused`; write nothing.
- `--write`: plan every key first; write only after all keys are accepted, one graph at a time;
  production needs `--to-production`; `WriteInDoubt` is reported and the exact one-graph
  `DROP GRAPH` is printed for the maintainer. Verify each stored graph triple-for-triple.
- SHACL batching: the WI 45 measurement is ~10 min and 4.5 GB for an 835k-triple batch. The largest
  graph here is the selection graph at ~323k triples; the m018 per config is ~150k. Validate **per
  graph**, not the whole 6M delivery; if a selection graph grows above ~500k, split it by
  `SelectionCycle`/subject and run the same shapes. Do not attempt one whole-delivery SHACL.
- Memory: per-key projection and validation are bounded; the dry run does not hold all keys at
  once; the run record prints wall time and peak memory.

### 9.5 Tests

- Manifest: unknown key, duplicate key, missing hash, `PENDIENTE` in a final manifest, wrong mask
  hash, missing file, path escape.
- Filters: twin book excluded, twin alerts/tests excluded, `ARM_DISABLED` excluded, Markowitz once,
  L0 loaded, BLOCKED loaded.
- Price: all negative tests of §5.4; `C1` accepted in every shape and gate.
- Configuration: five individuals, `:configuration` required, unknown configuration rejected, no
  inference from `:armCode`.
- Detail: decision/retention/stop/menu/replacement/stop-memory counts and links; no full candidate
  matrix, no target duplication, no blocked/reentry duplicate.
- Selection: `rankings.json` not loaded; DB `v_cycle_ranking` counts cross-check the file; panels/
  scales/retention not loaded as separate sources.
- Marks: no `ARM_DISABLED`; no L1_BP price; no `stop_distance_pct`; no `close`/`level`/`stop`/
  `stop_level`.
- Hermetic fixture cut from the pilot with one masked asset; no GraphDB; dry run and `--check-store`
  with the in-memory store; mypy/pre-commit; no full suite.

---

## 10. Questions for Reviewer A and staging (short)

### Questions

1. **Selection cycles.** Keep all 22 cycles per System (store ≈6.83M, warm-up vetoes preserved) or
   only the 10 decision cycles (store ≈4.54M, warm-up vetoes not loaded)? The old final graphs are
   replaced; this is the main volume decision.
2. **Aggregates graph.** Per configuration (`aggregates:{label}:{config}`) or one label-level graph
   with `:configuration` links? The manifest structure will decide; the design prefers per config.
3. **New rule dates.** Use `:validFrom "2019-01-02"` for `L0_*`/`L1_BP_STOP_BLOCKED` (the GUARD
   calibration convention) or a later date?
4. **Old rules.** Confirm the recommendation in §3.7: keep `L1_STOP_LOSS`, `L1_REENTRY`,
   `L2_NEWS`, `L3_VOL`, `L4_DD` with a “registered System only” comment and `:validTo` at the
   adoption boundary; L3/L4 are not part of the hierarchy. Which exact `:validTo`?
5. **`stop_distance_pct`.** Confirm omitting it for every company, including unmasked names, and
   that `:nav` remains allowed. If it is wanted for unmasked names, a later separate property and
   mask test are needed.
6. **C1 labels/instructions.** Confirm adding `:Window_C1`, updating the TTYG v1.3 “six windows” and
   “C1 not in the knowledge base” text, and the label test that currently asserts C1 is absent.
7. **Basic/complete and news variant.** The manifest's `selected_variant` is PENDIENTE. Confirm the
   graph properties `:systemVariant`, `:poolSize`, `:retentionEnabled`, and how to label the System
   when the news rule is on (`TOPN_MV_GUARD` vs `_NO_NLP`).
8. **Book caps.** `:bookWeightingRule`/`:maxNameWeight`/`:maxSectorWeight`/`:softVetoPenalty` are
   attractiveness-scheme parameters. Should the graph add explicit `:effectiveNameCap`/
   `:effectiveSectorCap` on the book, or keep the formula only in the `RunConfiguration_final`
   comment? The design prefers the comment (no misleading nearest property).
9. **Manifest final.** Confirm the final `manifest_final.json` keys and the control counts; the
   delivery's `SHA256SUMS` final hash.
10. **Label table.** Approve the 31 concepts and the new schema elements in one pass after
    2026-11-14; no `labels.ttl` before that.

### Staging

Given the 2026-11-17/18 delivery and 18–19 reload:

- **PR A (schema + rules + shapes + configuration class):** T-841–T-846. No data. Add
  `:BacktestConfiguration`, the five individuals, `:configuration`, new rules, BLOCKED, C1
  patterns, price exclusions, new event shapes; tests for shapes/rules. Reviewable without the
  final data.
- **PR B (manifest + filters + graph naming + m018):** T-847–T-852. Strict manifest, hashes,
  filter rules, config-keyed graph/IRI names, meta, m018, tests with the pilot DB. No detail events.
- **PR C (detail events + selection cross-check):** T-853–T-859. Decision/retention/stop/menu/
  replacement/stop-memory, price tests, selection-not-`rankings.json`, volume dry run on the pilot.
- **PR D (labels + TTYG + docs):** T-860–T-864. Second label table, `:Window_C1`, instructions
  update, concept map, runbook.
- **PR E (loader CLI + production runbook + final dry run):** T-865–T-869. Manifest/hash/check-store/
  write/verify, batching, rehearsal, final dry run, production record (maintainer writes).

Do not start PR B–E before the design is approved and the final manifest/control counts arrive; the
data dictionary is frozen, but the final paths, hashes, `selected_variant` and control counts are
not.

---

## Appendix A — pilot control counts

| Item | Value |
|---|---:|
| Books / loaded | 3 / 2 |
| L0 alerts | 12 |
| L1_BP_STOP alerts (System / twin) | 70 / 71 |
| L1_BP_STOP_BLOCKED alerts | 127 |
| L1_BP_REENTRY alerts (System / twin) | 42 / 60 |
| L4_DD alerts (disabled) | 196 |
| System actions APPLIED / BLOCKED | 194 / 127 |
| Stops by destination (replacement / SPY / cash) | 7 / 0 / 63 |
| Cash causes (FILTER_OFF / NO_ALLOWED_DESTINATION / SCALE_BELOW_ONE) | 47 / 13 / 3 |
| Decisions | 10 |
| Retention (with hierarchy: retained / rejected / counter drops) | 22 / 6 / 4 |
| Retention (without-hierarchy twin proxy: retained / rejected / counter drops) | 43 / 7 / 4 |
| System net cumulative return P1 | −0.155740 |
| MARKOWITZ_BASE cumulative return P1 | −0.105536 |
| Pilot `verification.json` | `all_match: true` |
