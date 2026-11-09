# Bilingual labels for the final graph — design

**Work item 43, Phase 1 (investigation and design only).** Baseline: `origin/master`
`e053fbb` (2026-11-09). This document changes no schema, source, CLI or test file.
The only Phase 1 change is this document plus append-only `PLAN.md`/`TASKS.md`
entries. Nothing here writes to GraphDB or reloads run data.

**Request.** Reviewer A, `PARA_K_parte_B_nombres.md` (B1–B4):
apply `rdfs:label`, `rdfs:comment` and `skos:altLabel` in `@es` and `@en` to
windows, strategy books, GUARD rules and states, vetoes (three classes),
ineligibility markers, score components and `rank`/`rank_e` columns, configuration
parameters and process/evaluation terms, without reloading run data and without
changing any IRI or engine code. The glossary is `glosario_grafo_v0_5.md`; the
strategy names are `nomenclatura_estrategias_v3.md`.

**Confirmed by Reviewer A (settled, not open).**

1. `TOPN_MV_GUARD_NO_NLP` is the System (FINAL); `TOPN_MV_NOGUARD` is FINAL NOGUARD;
   `MARKOWITZ_BASE` is the Markowitz minimum-variance book with Ledoit-Wolf
   covariance; `MARKOWITZ_BASE_GUARD` is the same book with GUARD. The `TOPN_MV_`
   prefix is historical: the final weights are minimum-CVaR; the minimum-variance
   stage is the selection.
2. The run label is `final`, the delivery `final_corregida` (`code_commit`
   `5958c6b`). It is not the older `final_b5` name. `rule` and `candidate_y2` are
   not loaded and must not be labelled.
3. `L4_DD` multiplies **all the reference weights, including the SPY core**; the
   reference GUARD receives is the target of the twin arm without GUARD.
4. A new concept vocabulary that does not touch any run IRI is approved.
5. Reviewer A reviews the English comments before they are frozen.

---

## 1. What each glossary item is in the graph today

The graph currently has three kinds of thing:

- **schema terms** with stable IRIs (classes, properties, `:Rule_*` individuals,
  `MetricTypeScheme` concepts) that can carry `rdfs:label`/`rdfs:comment` directly;
- **run-level individuals** with IRIs generated per label/window/run
  (`:Book_*`, `:GuardAlert_*`, …), which can technically carry labels but are run
  data;
- **literals** (`:windowId`, `:armCode`, `:runLabel`, `:alertState`, `:status`,
  `:vetoSeverity`, `:ruleSeverity`, `:guardLayer`, `:objective`, `:testName`,
  `:referenceName`, `:trendState`, …), which cannot be the subject of a label.

The design uses direct labels for the first group, concept labels joined on the
literal for the third group, and **no triples on the second group** (the approved
concept vocabulary does not touch a run IRI).

### 1.1 Windows and run labels

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| Window 1 (P1) … Window 6 (H3) | **No window class and no window individual.** The code is a string literal `:windowId` on `:StrategyBook`, `:GuardAlert`, `:BookDailyPerformance`, `:PortfolioPeriodSummary`, `:BacktestTest`, `:SelectionCycle` and `:BacktestRun`. `:trendWindow` and `:returnWindow` repeat the same code on aggregates rows. Dates exist only on rows (`:backtestStartDate`/`:backtestEndDate`, `:dateFrom`/`:dateTo`, `:referenceDateFrom`/`:referenceDateTo`), never on a window entity. | **No.** A literal cannot be a subject. | `schema/tbox.ttl:939-940` (`:windowId`), `schema/tbox.ttl:999-1000` (`:trendWindow`), `schema/tbox.ttl:1009-1010` (`:returnWindow`), `schema/tbox.ttl:1013-1015` (`:referenceDateFrom`/`:referenceDateTo`), `schema/tbox.ttl:1069-1071` (`:backtestStartDate`/`:backtestEndDate`), `schema/tbox.ttl:1139-1140` (`:dateFrom`/`:dateTo`); shapes enforce the pattern at `schema/shapes.ttl:460, 505, 589, 614, 639, 676, 695, 745-746, 761-762` |
| C1 (continuous run) | **Absent.** No window code, no individual, no literal in the final load. | **No, and it must not become one.** Do not create a concept or an IRI for C1. | No `C1` in `schema/`; the glossary §2/§9 says it is not loaded |
| `final` | `:runLabel` is a string literal on the run-level classes (`:StrategyBook`, `:BacktestTest`, `:BacktestRun`, `:AggregatesSet`, `:TrendFilterState`, `:ReferenceReturn`). There is no run-label individual. | **No.** A literal cannot be a subject. | `schema/tbox.ttl:953-954`; shapes at `schema/shapes.ttl:458-459, 637-638, 674-675, 693-694, 707-708, 729-730, 743-744, 759-760` |
| `rule`, `candidate_y2` | Not loaded in the final store, so not present as a `:runLabel` value. | **No, and they must not receive a label.** | Request A2; `docs/ttyg/instructions-v1.2.md` line 20 still carries a defensive `rule` line that v1.3 removes |

### 1.2 Strategy books and arms

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| Strategy book / arm | `:StrategyBook` is a class; one individual per `(label, window, arm)` in the run graph, named `Book_{label}_{window}_{arm}` by the projector. The arm code is the literal `:armCode`. There is no separate arm class or concept. | **Yes on the individual, but the design does not do it.** A book IRI is run data; the approved vocabulary does not touch it. The user-facing name is attached to the arm concept and joined on `:armCode`. | Class `schema/tbox.ttl:273-278`; shape `schema/shapes.ttl:451-478`; `:armCode` `schema/tbox.ttl:937-938`; closed arm list `schema/shapes.ttl:464-465` (also 487-488, 543-544, 565-566, 587-588, 612-613, 642-645) |
| `MARKOWITZ_BASE`, `TOPN_MV_NOGUARD`, `TOPN_MV_GUARD_NO_NLP`, `MARKOWITZ_BASE_GUARD` | Four literal `:armCode` values in the final load (the shape also accepts `TOPN_MV_GUARD`, not loaded by `final`). | **No.** Literal. | `schema/shapes.ttl:464-465`; `docs/07-ontology-topology.md:77, 87` and `docs/08-agent-architecture.md:254-255` record the final four |

### 1.3 GUARD: rules, layers, states and actions

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| GUARD supervision | No term. It is the concept behind `:category "GUARD"` on `:RuleDefinition` and `:guardLayer` on alerts. | **No.** A concept label is needed. | `schema/tbox.ttl:752` (`:category`), `schema/tbox.ttl:949-950` (`:guardLayer`) |
| Layer 1 … Layer 4 | Integer literal `:guardLayer` on `:GuardAlert` and on GUARD `:RuleDefinition`s; no layer individual/class. | **No.** Literal. | `schema/tbox.ttl:949-950`; shapes `schema/shapes.ttl:509-510` (alert) and `schema/shapes.ttl:217` (rule) |
| `L1_STOP_LOSS`, `L1_REENTRY`, `L1_BP_STOP`, `L1_BP_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD` | Seven `:RuleDefinition` individuals in `rules.ttl`, each with `:ruleId`, `:category "GUARD"`, `:guardLayer`, one `GraphPredicate` leaf. They have **no `rdfs:label` today**. | **Yes.** Individuals; direct bilingual labels/comments in `schema/rules.ttl`. | `schema/rules.ttl:221-275` (all seven); `:ruleId` `schema/tbox.ttl:800-801`; GUARD branch `schema/shapes.ttl:202-217` |
| `ENTER`, `EXIT`, `ACTIVE`, `COOLDOWN`, `SCALE` | String literal `:alertState` on `:GuardAlert`. No state individual. | **No.** Literal. | `schema/tbox.ttl:1097-1098`; closed list `schema/shapes.ttl:527-528` |
| `APPLIED`, `ARM_DISABLED`, `NOT_HELD`, `SUPERSEDED` | String literal `:status` on `:GuardAction`. `:status` is shared with `:OrchestratorRun`/`:OrchestratorStep` and `:BookRebalance`; only the `GuardAction` shape closes it. | **No.** Literal; the concept must be restricted to the action status scheme. | `schema/tbox.ttl:943-944`; `schema/shapes.ttl:549-550` |
| GUARD alert / action / rule state | Classes `:GuardAlert`, `:GuardAction`, `:RuleDefinition`; alerts and actions are run individuals. | **Yes for the classes; no for the run individuals.** Classes get labels/comments in `tbox.ttl`. | `schema/tbox.ttl:287-299`, `schema/tbox.ttl:153-158` |

Proposed direct labels for the seven GUARD rules (comments are the glossary §3
text; `L4_DD` uses the confirmed scope wording):

| Code | `rdfs:label`@en | `rdfs:label`@es |
|---|---|---|
| `L1_BP_STOP` | Exit by Basing Points rule | Salida por regla Basing Points |
| `L1_BP_REENTRY` | Re-entry after Basing Points exit | Reentrada tras salida Basing Points |
| `L1_STOP_LOSS` | 21-session loss-limit exit (Markowitz with GUARD) | Salida por límite de pérdida de 21 sesiones (Markowitz con GUARD) |
| `L1_REENTRY` | Re-entry after loss-limit exit | Reentrada tras salida por límite de pérdida |
| `L2_NEWS` | News trim (disabled in the final configuration) | Recorte por noticias (deshabilitada en la configuración final) |
| `L3_VOL` | Volatility scaling (configured, no activations) | Escalamiento por volatilidad (configurado; sin activaciones en las corridas evaluadas) |
| `L4_DD` | Drawdown scaling | Escalamiento por caída |

Proposed labels for the alert states and action statuses (comments are the
glossary §3 text; `ENTER`/`EXIT` must say they are rule activation/deactivation,
not buy/sell orders):

| Code | Kind | `rdfs:label`@en | `rdfs:label`@es |
|---|---|---|---|
| `ENTER` | alert state | Rule activated | Regla activada |
| `EXIT` | alert state | Rule deactivated | Regla desactivada |
| `ACTIVE` | alert state | Rule in effect | Regla vigente |
| `COOLDOWN` | alert state | Rule in cool-down | Regla en enfriamiento |
| `SCALE` | alert state | Exposure scaled | Exposición escalada |
| `APPLIED` | action status | Action applied | Acción aplicada |
| `ARM_DISABLED` | action status | Arm without GUARD (shadow alert) | Brazo sin GUARD (alerta en sombra) |
| `NOT_HELD` | action status | Asset not held | Activo no mantenido |
| `SUPERSEDED` | action status | Alert superseded | Alerta reemplazada |

Layer labels: `1` = "Per-stock stop (layer 1)" / "Parada por acción (capa 1)";
`2` = "News trim (disabled in the final configuration)" / "Recorte por noticias
(deshabilitada en la configuración final)"; `3` = "Volatility scaling (configured,
no activations)" / "Escalamiento por volatilidad (configurado; sin activaciones en
las corridas evaluadas)"; `4` = "Drawdown scaling" / "Escalamiento por caída".

### 1.4 Vetoes: the three classes

The ontology has **one** `:Veto` class. It does not have `HardVeto`, `SoftVeto`
or `Indicator` classes. The three glossary classes are presentation categories:

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| Hard veto | Rule-level `:ruleSeverity "HARD"` on the selection rules; stint-level `:vetoSeverity "HARD"` on a `:Veto`; `:ruleSeverity`/`:vetoSeverity` are literals. | **No class to label.** A presentation concept joins on `"HARD"`. | `schema/tbox.ttl:802-803` (`:ruleSeverity`), `schema/tbox.ttl:796-797` (`:vetoSeverity`); `schema/shapes.ttl:100` |
| Soft penalty | Rule-level `:ruleSeverity "SOFT"` plus `:penaltyPoints`; `:softVetoPenalty` on a per-run scheme. Literals/number. | **No class to label.** A presentation concept joins on `"SOFT"`; the penalty is the rule's `:penaltyPoints` or the run's `:softVetoPenalty`. | `schema/tbox.ttl:806-807`, `schema/tbox.ttl:891-892`; `schema/rules.ttl:119-133` |
| Informative indicator | `BREAK_TREND_200` is a `:RuleDefinition` with `:ruleSeverity "SOFT"` and `:penaltyPoints 0`; it is **not** a separate class. | **No class to label.** Label the rule directly; explain in the concept that a zero-point SOFT rule is a flag, not a veto. | `schema/rules.ttl:165-171`; `schema/tbox.ttl:806-807` |
| The active selection rules | Individuals `:Rule_LEVERAGE_EXTREME`, `:Rule_NEGATIVE_FCF`, `:Rule_LIQUIDITY_DISTRESS` (+ `_v11`), `:Rule_PRICE_CRASH`, `:Rule_EARNINGS_MISSING`, `:Rule_DATA_QUALITY`, `:Rule_VOLATILITY_SHOCK`, `:Rule_CRASH_Z_SCORE`, `:Rule_BREAK_TREND_200`, `:Rule_UTILITY_CASH_COVERAGE`. | **Yes.** Direct bilingual labels/comments in `schema/rules.ttl`. | `schema/rules.ttl:75-191` |
| `LIQUIDITY_DISTRESS` history | Two definitions with the same `:ruleId`: the closed pre-2026-10-10 one and the current `_v11` one. | **Yes**; label both, mark the closed one superseded in its comment. | `schema/rules.ttl:91-117` |

Proposed direct labels for the active selection rules (comments are the glossary
§4 text; the closed `LIQUIDITY_DISTRESS` gets the same label plus a
"superseded 2026-10-10" note):

| Presentation class | Code | `rdfs:label`@en | `rdfs:label`@es |
|---|---|---|---|
| Hard veto | `LEVERAGE_EXTREME` | Extreme leverage | Apalancamiento extremo |
| Hard veto | `NEGATIVE_FCF` | Negative free cash flow | Flujo de caja libre negativo |
| Hard veto | `UTILITY_CASH_COVERAGE` | Weak operating cash flow to debt (regulated utilities) | Flujo operativo débil frente a la deuda (utilities reguladas) |
| Hard veto | `DATA_QUALITY` | Data-quality failure | Falla de calidad de datos |
| Hard veto | `VOLATILITY_SHOCK` | Volatility shock | Choque de volatilidad |
| Hard veto | `CRASH_Z_SCORE` | Abnormal price drop | Caída anormal de precio |
| Soft penalty | `PRICE_CRASH` | Deep 90-day drawdown | Caída profunda de 90 días |
| Soft penalty | `LIQUIDITY_DISTRESS` | Liquidity distress | Estrés de liquidez |
| Soft penalty | `EARNINGS_MISSING` | Stale fundamentals | Fundamentales desactualizados |
| Informative indicator | `BREAK_TREND_200` | Below 200-day trend (flag only) | Bajo la tendencia de 200 días (solo indicador) |

The three class concepts are labelled "Excluded by a hard veto" / "Excluida por
veto duro", "Soft penalty" / "Penalización suave" and "Informative indicator" /
"Indicador informativo"; their comments state that only the first excludes, the
second subtracts points and the third neither excludes nor subtracts.

### 1.5 Ineligibility markers, score components, rank and weight

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| `HARD` marker | Literal `:vetoSeverity "HARD"` / `:ruleSeverity "HARD"`; also a token inside the opaque `:vetoRulesJson` JSON string. | **No.** A marker concept joins on `"HARD"`; the JSON is never parsed here. | `schema/tbox.ttl:796-797, 802-803, 903-904` |
| `UNSCORED`, `UNPRICED` | Only tokens inside `:vetoRulesJson` (e.g. `["UNSCORED"]`); no separate literal or property. | **No direct join.** Concepts can explain the codes; a query can only use `FILTER(CONTAINS(STR(?json), "UNSCORED"))`, which is a heuristic, not a structured join. | `schema/tbox.ttl:903-904`; `schema/README.md:426` describes the placeholder rows |
| `NO_RISK_MODEL` | **Not represented** in the schema or the projected data. It is a data-gap cause described in the glossary, not a literal in the graph. | **No.** Concept only, marked as not represented; the agent must not infer it from a missing row. | Grep of `schema/` finds no `NO_RISK_MODEL`; it appears only in `docs/reports-agent-query-catalog.md:1053` as a marker category |
| `blended_score` / combined score | Property `:attractivenessScore` on `:AttractivenessSnapshot` (0..1; can be negative after soft penalties). The literal name `blended_score` is upstream's column, not a graph literal. | **Yes** on the property. | `schema/tbox.ttl:872-873`; class comment `schema/tbox.ttl:218-223` |
| `rank` | Property `:rankPosition` (integer) on `:AttractivenessSnapshot`; counts vetoed names. | **Yes** on the property. | `schema/tbox.ttl:895-896` |
| `rank_e` | **Absent.** No property, no literal, no column in the projected selection side. | **No data at all.** A concept can explain it, but the agent must say it is not loaded and must not estimate it. | Grep of `schema/`, `src/`, `docs/` finds no `rank_e`/`rankE`/`eligibleRank` |
| `FUNDAMENTAL`, `TECHNICAL`, `VALORIZATION`, `SECTOR` | Literal `:agentOrigin` on `:ScoreSnapshot`; closed list. The corresponding metric types are SKOS concepts in `:MetricTypeScheme` (`ScoreFinanciero`, `ScoreTecnico`, `ScoreCuantitativo`, `SectorRelativeMomentum`; `Sentiment` for SEMANTIC). | **Literals: no** (concept joins on the code). **MetricType concepts: yes** (add `rdfs:label`/`rdfs:comment` in `reference.ttl`). | `schema/tbox.ttl:725-727`; `schema/shapes.ttl:21-23`; `schema/reference.ttl:126-133` |
| Soft penalty | `:penaltyPoints` on a rule and `:softVetoPenalty` on a scheme; no single property called "soft penalty". | **Partly:** label the two properties; a concept explains the combined idea. | `schema/tbox.ttl:806-807, 891-892` |
| Score is not weight | No term. The distinction is carried by `:attractivenessScore`/`:componentValue` (score) versus `:finalTargetWeight`/`:targetWeight` (weights). | **No single term.** Process concept plus labels on the properties. | `schema/tbox.ttl:872-873, 901-906, 1119-1120` |

Proposed labels for the marker, score and rank group:

| Code | `rdfs:label`@en | `rdfs:label`@es | Anchor |
|---|---|---|---|
| `HARD` | Excluded by a hard veto | Excluida por veto duro | `:vetoSeverity` / `:ruleSeverity`; JSON token |
| `UNSCORED` | No score available | Sin puntaje | `:vetoRulesJson` only |
| `UNPRICED` | No price history | Sin historia de precios | `:vetoRulesJson` only |
| `NO_RISK_MODEL` | Not covered by the risk model | Sin cobertura del modelo de riesgo | Not represented |
| `blended_score` | Combined score | Puntaje combinado | `:attractivenessScore` |
| `rank` | Raw ranking position (includes excluded names) | Posición en el ranking bruto (incluye excluidas) | `:rankPosition` |
| `rank_e` | Rank among eligible companies | Posición entre empresas elegibles | Not loaded |
| `FUNDAMENTAL` | Fundamental score | Puntaje fundamental | `:agentOrigin`; `ScoreFinanciero` |
| `TECHNICAL` | Technical score | Puntaje técnico | `:agentOrigin`; `ScoreTecnico` |
| `VALORIZATION` | Valuation score | Puntaje de valoración | `:agentOrigin`; `ScoreCuantitativo` |
| `SECTOR` | Sector-relative technical score | Puntaje técnico relativo al sector | `:agentOrigin`; `SectorRelativeMomentum` |
| soft penalty | Soft penalty | Penalización suave | `:penaltyPoints` / `:softVetoPenalty` |

### 1.6 Configuration parameters

Most `params_json` keys are **not projected**. Only a few have a graph property;
the rest appear in prose (`:RunConfiguration`'s frozen English comment) or not at
all. This is the most important limitation for B1: a label can explain a
parameter, but it cannot make a value queryable.

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| `core_weight` (50 %) | No property. The nominal 50 % is in the `:RunConfiguration` comment; realized weights are `:BookWeightDaily` rows. | **No property.** Concept explains the nominal value; no query join. | `schema/tbox.ttl:341-352` (comment), `schema/tbox.ttl:1119-1120` (`:finalTargetWeight`) |
| `pool_m` (60) | `:topN` on `:AttractivenessWeightScheme` is the candidate-pool size (60), **not** the held cap. | **Yes** on `:topN`; concept also exists for the parameter name. | `schema/tbox.ttl:885-886`; `schema/shapes.ttl:361` |
| `top_n` (30) | No property; `:topN`'s comment says the held cap (30) is a `params_json` value no view exposes. | **No.** Concept only; agent must not read `:topN` as 30. | `schema/tbox.ttl:885-886` |
| `satellite_weighting` = `mincvar` | No property. It is **not** `:objective`; the WI 41 comment explicitly says `min_var` is not the weighting objective. | **No.** Concept; the agent must use `satellite_weighting` from the run configuration/instructions, not `:objective`. | `schema/tbox.ttl:1063-1064`; `PLAN.md` Work item 41 |
| `cvar_scenarios` = `simple` | Not projected. | **No.** Concept; explain only if asked. | No `cvar_scenarios` in `schema/` or `src/projection/` |
| `cov_estimator` = `ledoit_wolf_cc` | Not a property; the `:RunConfiguration` comment names Ledoit-Wolf constant-correlation covariance and 756 sessions. | **No.** Concept; no query join. | `schema/tbox.ttl:341-352` |
| `lookback` / `min_history` (756 / 740) | Not projected as numbers; 756 appears in the `:RunConfiguration` comment. | **No.** Concept; no query join. | `schema/tbox.ttl:341-352` |
| `returns_members` = `range` | Not projected. | **No.** Concept; explain the panel definition. | No `returns_members` in `schema/` or `src/projection/` |
| `trend_filter`, `filter_exit` | `:TrendFilterState` rows carry `:trendState` and `:cashFraction`; the configured `filter_exit` value (0.5) is not a property. | **Partly:** label `:TrendFilterState`, `:trendState`, `:cashFraction`; concept for the parameter names. | `schema/tbox.ttl:361-366, 1003-1008`; `schema/shapes.ttl:740-754` |
| `stop_rule` = `bp4` | `:Rule_L1_BP_STOP` is a GUARD rule; the code `bp4` is not a literal. | **No direct join.** Concept maps `bp4` to the Basing Points rule. | `schema/rules.ttl:237-243` |
| `cost_bps` (10) | `:costReturn` and `:totalCostBps` are per-session/per-period costs; the 10 bps rate is in the `:RunConfiguration` comment and the `BookDailyPerformance` definition. | **Partly:** label the cost properties; concept for `cost_bps`. | `schema/tbox.ttl:1127, 1148, 341-352`; `schema/tbox.ttl:308-313` |
| `vol_target` = `fixed` | `:Rule_L3_VOL` records the configured layer; no target value property. | **No direct join.** Concept maps `fixed` to layer 3; comment says configured, no activations. | `schema/rules.ttl:261-267` |
| `exclude_hard_vetoed` | Property `:excludeHardVetoed` (boolean) on `:StrategyBook`. It is 0 on all four final arms; the System excludes hard vetoes earlier, in the candidate selection. | **Yes** on the property; concept explains the trap. | `schema/tbox.ttl:1065-1066`; `schema/shapes.ttl:467-471` |
| `tilt`, `blend`, `rp`, `news_model`, `news_db`, `shadow_from` | Not projected. | **No.** Concepts marked internal; hide in ordinary answers. | No hits in `schema/`; glossary §7 lists them as internal |
| `strategy_book.objective` = `min_var` | Property `:objective` (string literal). WI 41 corrected its comment: a fixed per-arm literal, not the weighting objective of the `TOPN_MV_*` books. | **Yes** on the property; a concept for the `min_var` value explains it. | `schema/tbox.ttl:1063-1064`; `PLAN.md` Work item 41 |

The EN/ES labels of the configuration group are the glossary §7 "Etiqueta EN /
ES" column verbatim, except `objective`, whose label is **Registered
optimization class** / **Clasificación de optimización registrada**, and the
`pool_m`/`top_n` pair, which must never be swapped.

### 1.7 Process and evaluation terms

| Glossary item | Graph representation today | Can it carry a label directly? | Evidence |
|---|---|---|---|
| Point-in-time universe | `:Universe` and `:UniverseMembership` classes; memberships carry `:validFrom`/`:validTo` (inclusive). | **Yes** on the classes; process concept for the term. | `schema/tbox.ttl:68-80` |
| Eligible universe | No single class; derived from score availability, `:vetoedAtRanking`, `:vetoRulesJson`, and the absence of a hard veto. | **No single term.** Concept; comment explains the derivation. | `schema/tbox.ttl:897-904`; `schema/tbox.ttl:796-797` |
| Candidate pool | `:selectedForBook` (boolean) means membership of the 60-name pool, not the held names; `:topN` is the pool size. | **Yes** on both properties. | `schema/tbox.ttl:885-886, 897-898` |
| Maximum satellite holdings (30) | No property. `:topN` is 60; the held cap is in `params_json` and not exposed. | **No.** Concept only; never read 30 from `:topN`. | `schema/tbox.ttl:885-886` |
| Selection | `:SelectionCycle` class and selection-side ranking individuals. | **Yes** on the class. | `schema/tbox.ttl:375-380` |
| Weighting | `:bookWeightingRule` (upstream `scheme_id`, open vocabulary) and `:objective` (registered class, not the satellite weighting). | **Yes** on `:bookWeightingRule` and `:objective`; concepts distinguish the four ideas. | `schema/tbox.ttl:883-884, 1063-1064` |
| Core / satellite / cash | `:ExchangeTradedFund`/`:SPY` for the core; `:BookWeightDaily` with `holdingKey "CASH"` and `:cashWeight`/`:cashFraction` for cash; the satellite is the non-core equity holdings. | **Partly:** labels on classes/properties; a process concept explains the trio. | `schema/tbox.ttl:42-48, 301-306, 1133, 1005-1006`; `schema/reference.ttl:100` |
| Nominal / realized composition | `:markowitzTargetWeight` (pre-GUARD target) versus `:finalTargetWeight` (final); `:targetWeight` is the ranking's pool weight, not a portfolio weight. | **Yes** on the properties; process concept for the distinction. | `schema/tbox.ttl:901-902, 1117-1120` |
| Scheduled rebalance | `:BookRebalance` class; every 21 NYSE sessions. | **Yes** on the class. | `schema/tbox.ttl:280-285` |
| Trading day | No term; a session with `:turnover > 0` on `:BookDailyPerformance`. | **No single term.** Process concept. | `schema/tbox.ttl:1125-1135` |
| Gross / net return | `:grossReturn`, `:netReturn`, `:costReturn` properties. | **Yes** on the properties. | `schema/tbox.ttl:1125-1129` |
| Sharpe | `:exPostSharpe` on `:PortfolioPeriodSummary`; benchmark observations can carry `:quantMetric "sharpe"`. | **Yes** on the properties; process concept states annualized or not. | `schema/tbox.ttl:1144, 851-856` |
| CVaR 95 % | **Not in the graph.** No CVaR value, no `satellite_weighting` property. | **No data.** Concept only; the agent must not report a CVaR figure. | No `CVaR`/`cvar` in `schema/`; glossary §6 |
| Maximum drawdown (MDD) | `:maxDrawdown` on `:PortfolioPeriodSummary`, `:drawdown` on `:BookDailyPerformance`, `:referenceMaxDrawdown` on `:ReferenceReturn`, and `:statistic` for `bootstrap_mdd`. | **Yes** on the properties. | `schema/tbox.ttl:1131, 1145, 1023, 1159` |
| Turnover | `:turnover` (daily) and `:totalTurnover` (period); full sum of absolute equity-weight changes, cash excluded. | **Yes** on the properties. | `schema/tbox.ttl:1126, 1147` |
| Transaction costs | `:costReturn` and `:totalCostBps`; 10 bps of turnover. | **Yes** on the properties; concept for the rate. | `schema/tbox.ttl:1127, 1148` |
| Benchmark | `:ReferenceReturn`/`:referenceName` for SPY and SP500_EW_INTERNAL; `:BenchmarkObservation`, `:portfolioKind "BENCHMARK"`, `:benchmarkObjective` for quant benchmark books. | **Yes** on the classes/properties. | `schema/tbox.ttl:139-144, 368-373, 842-847, 1019-1024` |
| DSR / PBO | **Not in the graph.** No DSR or PBO value/test name. | **No data.** Concepts only; the agent must not treat them as acceptance tests. | No `DSR`/`PBO` in `schema/`; test names are `memmel_jk`, `ledoit_wolf`, `hac_mean_diff`, `bootstrap_mdd` (`schema/shapes.ttl:646-647`) |
| Data availability and quality | `:DataQualityIssue`/`:dqSeverity`/`:quarantined` exist for DQ failures; there is no controlled vocabulary for available/unavailable/insufficient/stale/provisional. | **No single term.** Process concepts; explain the graph's actual fields. | `schema/tbox.ttl:118-123, 775-778` |
| Data nature (observed / calculated / derived) | No property. `:PriceObservation` is derived; `:BenchmarkObservation` is computed upstream; `:ScoreSnapshot` is an immutable observation. | **No single term.** Process concepts; labels on the classes. | `schema/tbox.ttl:82-87, 139-144, 204-209` |

The EN/ES labels of the process group are the glossary §6 "Etiqueta EN / ES"
column verbatim, plus the meta terms in §2.2 (in-sample, out-of-sample, counting
rule, formation-day alert, warm-up veto, not in the knowledge base, conceptual
answer, operations are not orders, score is not weight).

---

## 2. Proposed mechanism for literals: a SKOS presentation vocabulary

### 2.1 Shape of the solution

A new `schema/labels.ttl` defines a presentation vocabulary in
`urn:graph:labels`. It contains **no run individual**: only `skos:Concept`
resources whose IRIs are new presentation terms, plus a few annotation
properties and concept schemes.

Every concept carries:

- `skos:inScheme` — exactly one scheme;
- `skos:notation` — the literal code, so a query can join on it;
- `rdfs:label` — exactly one `@en` and one `@es`;
- `rdfs:comment` — exactly one `@en` and one `@es`;
- `skos:altLabel` — optional synonyms, only `@en`/`@es`;
- `:labelScheme :PresentationScheme` — a marker used only by the SHACL shape
  (so the shape does not target GICS sectors or `MetricTypeScheme` concepts).

Window concepts additionally carry `:windowStart`/`:windowEnd` (xsd:date) and
the two separate fields `:historicalCondition` and
`:finalConfigurationCondition` (both language-tagged, `@en`/`@es`).

The concept IRIs stay in the project namespace
(`https://thesis.local/kg/portfolio#`, prefix `:`), as the constitution requires.
They are descriptive (`:Strategy_MinVarianceLedoitWolf`, not
`:Arm_MARKOWITZ_BASE`). The code lives in `skos:notation`, not in the label.

### 2.2 Schemes and code fields

| Scheme | Concepts | `skos:notation` matches | Query anchor |
|---|---|---|---|
| `:WindowScheme` | `:Window_1` … `:Window_6` | `"P1"`, `"H1"`, `"P3"`, `"H2"`, `"P2"`, `"H3"` | `:windowId`, `:trendWindow`, `:returnWindow` |
| `:RunLabelScheme` | `:RunLabel_final` | `"final"` | `:runLabel` |
| `:StrategyScheme` | `:Strategy_System`, `:Strategy_SystemNoGuard`, `:Strategy_MinVarianceLedoitWolf`, `:Strategy_MinVarianceLedoitWolfGuard` | the four final `:armCode` values | `:armCode` |
| `:GuardScheme` | `:GuardSupervision`, `:GuardLayer_1` … `:GuardLayer_4`, `:AlertState_ENTER` … `:AlertState_SCALE`, `:ActionStatus_APPLIED` … `:ActionStatus_SUPERSEDED` | `"GUARD"`, `1`…`4` (xsd:integer), `"ENTER"`…, `"APPLIED"`… | `:guardLayer`, `:alertState`, `:status` on `:GuardAction` |
| `:VetoClassScheme` | `:VetoClass_Hard`, `:VetoClass_Soft`, `:VetoClass_Indicator` | `"HARD"`, `"SOFT"`, `"INDICATOR"` | `:ruleSeverity`, `:vetoSeverity`; indicator via `:ruleId "BREAK_TREND_200"` |
| `:MarkerScheme` | `:Marker_HARD`, `:Marker_UNSCORED`, `:Marker_UNPRICED`, `:Marker_NO_RISK_MODEL` | `"HARD"`, `"UNSCORED"`, `"UNPRICED"`, `"NO_RISK_MODEL"` | `:vetoSeverity` for HARD; `CONTAINS` on `:vetoRulesJson` for UNSCORED/UNPRICED; no anchor for NO_RISK_MODEL |
| `:ScoreComponentScheme` | `:ScoreComponent_Fundamental`, `:ScoreComponent_Technical`, `:ScoreComponent_Valorization`, `:ScoreComponent_Sector` | `"FUNDAMENTAL"`, `"TECHNICAL"`, `"VALORIZATION"`, `"SECTOR"` | `:agentOrigin` |
| `:RankScheme` | `:RankColumn_Raw`, `:RankColumn_Eligible` | `"rank"`, `"rank_e"` | `:rankPosition` for `rank`; no anchor for `rank_e` |
| `:ConfigScheme` | `:Config_core_weight`, `:Config_pool_m`, `:Config_top_n`, `:Config_satellite_weighting`, `:Config_cvar_scenarios`, `:Config_cov_estimator`, `:Config_lookback`, `:Config_min_history`, `:Config_returns_members`, `:Config_trend_filter`, `:Config_filter_exit`, `:Config_stop_rule`, `:Config_cost_bps`, `:Config_vol_target`, `:Config_exclude_hard_vetoed`, `:Config_tilt`, `:Config_blend`, `:Config_rp`, `:Config_news_model`, `:Config_news_db`, `:Config_shadow_from`, `:Config_objective_min_var` | the `params_json` key (or the literal value `min_var` for `:Config_objective_min_var`) | only `:topN`, `:excludeHardVetoed`, `:objective` have a property anchor; the rest are explanatory |
| `:ProcessScheme` | the §6 terms and the run/evaluation meta terms (see §2.3) | stable uppercase codes (`PIT_UNIVERSE`, `ELIGIBLE_UNIVERSE`, `CANDIDATE_POOL`, `MAX_SATELLITE`, `SELECTION`, `WEIGHTING`, `CORE_SATELLITE_CASH`, `NOMINAL_REALIZED`, `SCHEDULED_REBALANCE`, `TRADING_DAY`, `GROSS_NET`, `SHARPE`, `CVAR_95`, `MDD`, `TURNOVER`, `TRANSACTION_COSTS`, `BENCHMARK`, `DSR`, `PBO`, `DATA_STATE`, `DATA_NATURE`, `IN_SAMPLE`, `OUT_OF_SAMPLE`, `COUNTING_RULE`, `FORMATION_DAY_ALERT`, `WARMUP_VETO`, `NOT_IN_KNOWLEDGE_BASE`, `CONCEPTUAL_ANSWER`, `OPERATIONS_NOT_ORDERS`, `SCORE_NOT_WEIGHT`) | explanatory; no data join except where a property/class is labelled directly |

Scheme membership disambiguates `"HARD"` (veto class vs marker) and `"1"`
(guard layer vs nothing else). A query MUST name the scheme; a bare
`?concept skos:notation "HARD"` is ambiguous by design.

### 2.3 How the query agent finds a label from a code

Window from a run row:

```sparql
SELECT ?label ?conditionFinal WHERE {
  VALUES ?row { <…Book_final_P1_TOPN_MV_GUARD_NO_NLP> }
  ?row :windowId ?code .
  ?c skos:inScheme :WindowScheme ; skos:notation ?code ;
     rdfs:label ?label ; :finalConfigurationCondition ?conditionFinal .
  FILTER (LANG(?label) = "en" && LANG(?conditionFinal) = "en")
}
```

Arm from a book:

```sparql
SELECT ?label WHERE {
  VALUES ?book { <…Book_final_P1_TOPN_MV_GUARD_NO_NLP> }
  ?book :armCode ?code .
  ?c skos:inScheme :StrategyScheme ; skos:notation ?code ;
     rdfs:label ?label .
  FILTER (LANG(?label) = "en")
}
```

Alert state / action status:

```sparql
?alert :alertState ?code .
?c skos:inScheme :GuardScheme ; skos:notation ?code ; rdfs:label ?label .
FILTER (LANG(?label) = "es")

?action :status ?code .
?c skos:inScheme :GuardScheme ; skos:notation ?code ; rdfs:label ?label .
```

Rule: direct label on the rule individual:

```sparql
?rule a :RuleDefinition ; :ruleId ?id ; rdfs:label ?label ; rdfs:comment ?comment .
FILTER (LANG(?label) = "en")
```

`objective` value:

```sparql
?book :objective ?code .
?c skos:inScheme :ConfigScheme ; skos:notation ?code ; rdfs:label ?label .
```

Markers in `:vetoRulesJson`: there is no structured join. The only safe query is
a `CONTAINS` test, and the agent must present it as a marker, not as a veto
individual:

```sparql
?row :vetoRulesJson ?json .
FILTER (CONTAINS(STR(?json), "UNSCORED"))
```

`rank_e` and `NO_RISK_MODEL` have **no data anchor**: the concept exists only to
explain the term. A query for a `rank_e` column returns nothing; the agent must
say it is not loaded.

### 2.4 What this adds to the loading and validation surfaces

| Surface | Today | After this design | Action |
|---|---|---|---|
| `LOAD_PLAN` | 6 files, 20 graphs, 5,192 asserted triples | 7 files, 21 graphs, `5,192 + D` triples | Add `("labels.ttl", "urn:graph:labels")` before `instances.trig` |
| Production (`include_examples=False`) | 5 files, 4 graphs, 4,671 triples | 6 files, 5 graphs, `4,671 + D` triples | Labels are schema, not ABox; they load in production with the WI 39 guard unchanged |
| `expected_sizes` | 20 entries / 4 production | 21 entries / 5 production | No code change beyond the load plan; `verify_store` and the schema-graphs acceptance check follow automatically |
| FR-001 bundle | 4,915 quads, 58 tbox classes, 39 named shapes | `4,915 + D` quads, 58 tbox classes (unchanged), 40 named shapes | Add `labels.ttl` to the FR-001 file list; add one `LabelConceptShape` |
| `tests/test_kg_load_schema.py` | asserts 20/5,192 and 4/4,671 | assert 21/`5,192+D` and 5/`4,671+D` | Update the two tests |
| `tests/test_acceptance_schema_checks.py` | expects "4 schema graphs" in the production message | "5 schema graphs" | Update the expectation |
| `verify_store` | six checks; the schema-graphs check uses `expected_sizes` | same six checks; the first reports 21 or 5 graphs | No new check; no change to the six |
| `kg_target_schema.ttl` | mirrors tbox terms | not changed by this design | Decide in T-756; it is not in FR-001 or the load plan, so it has no asserted count |
| `schema/protege-view.ttl` | generated | untouched | Regenerate only in the existing Protégé task, never by hand |

`D` is the net new triple count of `labels.ttl` plus the direct labels/comments
added to `tbox.ttl`, `rules.ttl`, `reference.ttl` and `shapes.ttl`. It is measured
with `rdflib` in the PR that adds each group; it is not guessed here.

**SHACL shape.** One new named shape, `:LabelConceptShape`, in `shapes.ttl`
(39 → 40). It targets `sh:targetSubjectsOf :labelScheme` (not all SKOS concepts),
requires `:labelScheme :PresentationScheme`, exactly one `skos:notation`, exactly
one `skos:inScheme`, exactly one `rdfs:label` per language, exactly one
`rdfs:comment` per language, and only `@en`/`@es` `skos:altLabel`s. Window-specific
fields (`:windowStart`, `:windowEnd`, `:historicalCondition`,
`:finalConfigurationCondition`) are enforced by `tests/test_labels.py`, not by a
second shape, to keep the shape count at 40.

**No new acceptance check.** The existing schema-graphs check covers the new graph
through `expected_sizes`; a seventh check would force a docs/count change for no
additional safety. A hermetic `tests/test_labels.py` covers the vocabulary
contract (notation uniqueness per scheme, one label/comment per language,
absence of C1/`rule`/`candidate_y2`, window fields).

### 2.5 What stays untouched

- Every run graph: `urn:graph:derived:backtest:{label}:{window}:{run_id}`,
  `urn:graph:derived:backtest:selection:…`, `…:meta:{label}`, `…:aggregates:{label}`,
  `urn:graph:derived:quant:{date}`, all `urn:graph:ingest:…` and
  `urn:graph:universe:…` graphs, and `urn:graph:portfolio:current`.
- `schema/instances.trig` and every worked-example individual.
- Every run IRI (`Book_*`, `GuardAlert_*`, `GuardAction_*`, `BacktestRanking_*`,
  `Veto_*`, `SelectionCycle_*`, …). The vocabulary adds no triple whose subject is
  a run IRI.
- `src/`, `cli/`, the projection/engine code and every IRI/code of the engine.
- The final run's rows, counts, dates, weights and results. No run data is
  reloaded; only `cli/load_schema.py` is re-run to write the schema graphs,
  including the new labels graph.

---

## 3. Where the vocabulary lives

**Recommendation: `schema/labels.ttl`, in the authoritative schema bundle,
loaded by `cli/load_schema.py` into `urn:graph:labels`.**

Why not a file outside `schema/`:

1. `cli/load_schema.py` is the sanctioned schema write path
   (`AGENTS.md` §4). A file outside `schema/` would need a second loader and a
   second write path, or a manual GraphDB upload that bypasses the gate.
2. The WI 39 production guard (`load_schema`/`verify_store --to-production`,
   `include_examples`) already models "schema files load everywhere; instances
   only outside production". A labels file is schema, not ABox; adding it to
   `LOAD_PLAN` gets the guard for free.
3. `load_schema` drops and rewrites the graphs it owns. The labels graph is
   therefore always rebuilt from the reviewed file, never patched by hand.
4. `schema/README.md` already maps every schema file to a named graph; one more
   row is the smallest documentation change.

Why not put the concepts in `reference.ttl`: it would mix a presentation layer
with the GICS/MetricType reference data and make the "labels are a separate
reviewable artifact" story weaker. `reference.ttl` still receives the bilingual
labels of the `MetricTypeScheme` concepts because those concepts already live
there; that is a direct label edit, not the new vocabulary.

**Effect on every asserted count (NR-001).** Let `D` be the net new triples. The
following live assertions change:

- `.specify/memory/SPEC.md` FR-001: `4915 quads` → `4915 + D`.
- `SPEC.md` §2.1 (in-scope bundle), §2.3 (FR-001/FR-012), §2.6 and the related
  work-item paragraphs that repeat the current count; the FR-012
  production-load sentence (`four schema graphs`, `20 graphs`) → `five schema
  graphs`, `21 graphs`.
- `README.md` schema section: the current count and the file-to-graph table
  (add `labels.ttl` / `urn:graph:labels`).
- `schema/README.md`: file-to-graph table, load order, validation counts, class
  and shape counts (58 tbox classes unchanged; 39 → 40 named shapes), and the
  current `4915`/`5192` statements.
- `docs/06-ontology-definition.md`: current count statements and the shape list.
- `docs/07-ontology-topology.md`: named-graph list adds `urn:graph:labels`.
- `docs/graphdb-setup.md`: production/test load sizes (`4671`, `5192`, `20`).
- `docs/backtest-load-runbook.md`: the `20 graphs` references.
- `docs/reports-agent-query-catalog.md`: if it states the schema graph set, add
  the labels graph; otherwise no count change.
- `tests/test_schema_gate.py`: `TURTLE_FILES` and the expected quad count.
- `tests/test_kg_load_schema.py`: 20/5,192 and 4/4,671.
- `tests/test_acceptance_schema_checks.py`: "4 schema graphs" → "5".
- `tests/test_ontology_v18.py`: named shapes 39 → 40.

Historical `PLAN.md`/`CHANGELOG.md` statements about past revisions are history
and stay as they are; the new work item records the new count. The generated
`protege-view.ttl` is not hand-edited.

---

## 4. Strategy-book labels (confirmed mapping)

The four labels below are the **only** strategy concepts in the final vocabulary.
The mean-variance tangency portfolio ("Markowitz base") is **not in the graph**:
it gets no concept and no label. `B0`, `MCF`, `MARKOWITZ_SAMPLE`,
`MARKOWITZ_SAMPLE_GUARD`, `BMK_EXPO`, `BMK_BETA`, `BMK_VOL`, `SPY` and
`SP500_EW` are not final books either; they are not given run-data labels in this
scope. `SPY` and `SP500_EW_INTERNAL` remain a reference asset and a reference
series (`:SPY` is declared as an `:ExchangeTradedFund`, whose class carries the
"ETF núcleo" label at `schema/tbox.ttl:46`), not strategy books. `TOPN_MV_GUARD`
is accepted by the shape but not loaded by `final`; it gets no concept until a run
uses it.

| `skos:notation` | Concept IRI | `rdfs:label`@en | `rdfs:label`@es | `rdfs:comment` (one line, ES source) |
|---|---|---|---|---|
| `TOPN_MV_GUARD_NO_NLP` | `:Strategy_System` | Core-satellite multifactor with CVaR weighting and GUARD supervision | Núcleo-satélite multifactorial con ponderación por CVaR y supervisión GUARD | Mandato nominal de 50 % en SPY y 50 % en hasta 30 acciones del grupo de 60 candidatas elegibles (puntajes técnico, de valoración y fundamental con vetos), ponderadas por mínimo CVaR con tope por nombre de 1.5 dividido entre el número de acciones, filtro de tendencia y supervisión GUARD; la composición realizada difiere del mandato nominal. |
| `TOPN_MV_NOGUARD` | `:Strategy_SystemNoGuard` | Core-satellite multifactor with CVaR weighting, without GUARD | Núcleo-satélite multifactorial con ponderación por CVaR, sin GUARD | Igual que el Sistema, sin la supervisión GUARD. |
| `MARKOWITZ_BASE` | `:Strategy_MinVarianceLedoitWolf` | Markowitz minimum variance (Ledoit-Wolf covariance) | Markowitz de mínima varianza (covarianza Ledoit-Wolf) | Cartera de mínima varianza sobre los miembros elegibles del S&P 500, solo largos, máximo 5 % por acción y 30 % por sector, con covarianza con contracción de Ledoit-Wolf; no estima retornos esperados; sin SPY, filtro ni selección. |
| `MARKOWITZ_BASE_GUARD` | `:Strategy_MinVarianceLedoitWolfGuard` | Markowitz minimum variance (Ledoit-Wolf covariance) with GUARD supervision | Markowitz de mínima varianza (covarianza Ledoit-Wolf) con supervisión GUARD | La cartera de mínima varianza (Ledoit-Wolf) con la supervisión GUARD (parada de 21 sesiones por acción y escalamiento por caída). |

AltLabels (for search, never for display as the name):

- System: `"Sistema"@es`, `"The System"@en`, `"NS-CVaR-GUARD"@en`/`@es`.
- System no GUARD: `"FINAL NOGUARD"@en`, `"NS-CVaR"@en`/`@es`.
- Min-variance Ledoit-Wolf: `"Mínima varianza (MV-LW)"@es`, `"Minimum variance (MV-LW)"@en`.
- Min-variance Ledoit-Wolf + GUARD: `"Mínima varianza (MV-LW) + GUARD"@es`, `"Minimum variance (MV-LW) + GUARD"@en`.

The internal code is `skos:notation`, not an altLabel and not part of the label.
If the agent ever shows a code, it is in parentheses and visually secondary. The
string `"Markowitz base"` must not appear in any label or comment; the only
permitted use of "base" is `MARKOWITZ_BASE` as a technical code in a provenance
field, never as a user-facing name.

---

## 5. Window labels

The run-label concept is separate from the windows: `:RunLabel_final`,
`skos:notation "final"`, `rdfs:label` "Final configuration run" / "Corrida de la
configuración final". Its comment states the delivery `final_corregida`
(`code_commit` `5958c6b`), the six windows, the in-sample status and that it is
the default label for final results. It must not mention `final_b5`; `rule` and
`candidate_y2` get no concept.

Six window concepts, calendar number 1–6. The code is `skos:notation`; the label
carries the number and dates; the historical and final-configuration conditions
are two separate fields. C1 gets no concept, no IRI and no notation.

| # | `skos:notation` / IRI | `rdfs:label`@en | `rdfs:label`@es | `:historicalCondition` (EN) | `:finalConfigurationCondition` (EN) |
|---|---|---|---|---|---|
| 1 | `P1` / `:Window_1` | Window 1 · Jan–Oct 2022, bear market with inflation | Ventana 1 · ene–oct 2022, mercado bajista con inflación | Design window; bear market with inflation (`docs/backtest.md`). | In-sample results. |
| 2 | `H1` / `:Window_2` | Window 2 · Oct 2022–Oct 2023 | Ventana 2 · oct 2022–oct 2023 | Originally reserved in the champion preregistration. | In-sample results. |
| 3 | `P3` / `:Window_3` | Window 3 · Oct 2023–Aug 2024, bull market | Ventana 3 · oct 2023–ago 2024, mercado alcista | Design window; bull market (`docs/backtest.md`). | In-sample results. |
| 4 | `H2` / `:Window_4` | Window 4 · Aug 2024–Feb 2025 | Ventana 4 · ago 2024–feb 2025 | Originally reserved. | In-sample results. |
| 5 | `P2` / `:Window_5` | Window 5 · Feb–Sep 2025 (P2) | Ventana 5 · feb–sep 2025 (P2) | Design window; the scenario is not labelled in `docs/backtest.md`. | In-sample results. |
| 6 | `H3` / `:Window_6` | Window 6 · Sep 2025–Oct 2026 | Ventana 6 · sep 2025–oct 2026 | Originally reserved. | In-sample results. |

Spanish versions of the two condition fields are the faithful translations:
"Ventana de diseño; mercado bajista con inflación (`docs/backtest.md`).",
"Reservada originalmente en el preregistro del campeón.", etc.; final condition
"Resultados dentro de muestra." in every window.

AltLabels per window, only where backed:

- Number: `"Window n"@en`, `"Ventana n"@es`.
- Dates: `"2022-01-03 to 2022-10-12"@en`, `"2022-01-03 a 2022-10-12"@es`, etc.
- Code: `"P1"@en`/`@es` (the same for H1, P3, H2, P2, H3).
- Scenario: only Window 1 (`"bear market with inflation"@en`,
  `"mercado bajista con inflación"@es`) and Window 3 (`"bull market"@en`,
  `"mercado alcista"@es`). Window 5 stays neutral: no high-volatility scenario
  until a numeric definition exists. H windows have no scenario altLabel.

`skos:notation "C1"` must be absent; a test asserts it. The agent's v1.3
instructions say C1 is not in the knowledge base used, not that it does not exist
in the project.

---

## 6. Drafting rules and their enforcement

1. **No internal code as a name.** The `rdfs:label` is the full human name. The
   code is `skos:notation` or, if displayed at all, a parenthetical in gray.
2. **Full strategy names.** Use `nomenclatura_estrategias_v3.md` exactly. First
   mention in an answer includes the one-line description.
3. **No Tiingo licence note.** No label, comment, altLabel or example mentions
   Tiingo or a licence restriction.
4. **No Grossman-Zhou mention.** The `L4_DD` comment must not cite Grossman &
   Zhou. The existing `schema/rules.ttl:273` and `schema/tbox.ttl:349` comments
   contain that citation; the labels PR rewrites the touched `L4_DD` comment and
   proposes the same cleanup for the `:RunConfiguration` class comment. The
   existing `schema/tbox.ttl:1094` comment also contains a Tiingo note; if the
   "no mention in any comment" rule is global, it is a comment-only cleanup under
   T-756, not a label change.
5. **`L4_DD` scope.** The comment says, verbatim in English, that the layer-4
   factor multiplies **all the reference weights, including the SPY core**, and
   that the reference GUARD receives is the target of the twin arm without GUARD.
   Spanish: "todos los pesos de referencia, incluido el núcleo SPY". No formula
   change; the parameters stay as in `schema/rules.ttl:269-275`.
6. **`objective`.** The property label is **Registered optimization class** /
   **Clasificación de optimización registrada**. Its English comment is the
   merged Work item 41 text, unchanged in substance: a fixed per-arm literal
   (`min_var`), independent of `satellite_weighting`, not the weighting objective
   of the `TOPN_MV_*` books; confirmation of the full upstream meaning pending.
   The Spanish comment is a translation of that text. The `min_var` value concept
   repeats the warning; it is not the satellite weighting.
7. **Language tags.** Every new label/comment has exactly `@en` and `@es`.
   Existing untagged English labels/comments on touched terms are retagged `@en`
   rather than duplicated. A term with an existing technical English comment not
   present in the glossary keeps that text as `skos:note`@en; `rdfs:comment`
   stays one per language.
8. **No new ontology semantics.** The three veto classes, the not-loaded markers
   and `rank_e` are presentation concepts, not new `owl:Class` declarations. No
   `:vetoClass` property, no `:rankE` property, no change to `RuleDefinition` or
   `Veto`.
9. **No run IRI.** The vocabulary never adds a triple about `Book_*`,
   `GuardAlert_*`, `GuardAction_*`, `Veto_*`, `SelectionCycle_*` or any other run
   individual. The labels are reached by `skos:notation` joins.
10. **Freeze.** No English comment enters `schema/` until Reviewer A approves the
    row in `docs/labels-en-review.md`.

---

## 7. English comments: review before freezing

**Proposed review artifact: `docs/labels-en-review.md`** (created in Phase 2, not
now). It is a table with one row per labelled element:

| Column | Content |
|---|---|
| `id` | Stable row id, e.g. `WIN-01`, `ARM-03`, `GUARD-L4`, `VETO-LEV` |
| `iri` | The concept or schema term IRI |
| `group` | window / run / strategy / guard / veto / marker / score / rank / config / process |
| `notation` | `skos:notation` or the literal code |
| `es_comment` | The glossary Spanish comment, verbatim |
| `en_comment_draft` | The proposed English translation |
| `reviewer_decision` | empty, `approved`, or `change requested: …` |
| `notes` | formula/parameter checks, forbidden-term checks |

Drafting method:

1. Start from the glossary Spanish comment; translate sentence by sentence.
2. Keep every number, formula, threshold, date and proper name exactly.
3. Add no claim that is not in the Spanish. If the Spanish is ambiguous, the row
   is marked and Reviewer A decides; the schema does not guess.
4. Apply the drafting rules in §6, especially the `L4_DD` wording and the
   `objective` WI 41 text.
5. Run a forbidden-term check on the whole table: `Tiingo`, `Grossman`, `Zhou`,
   `Markowitz base`, `final_b5`, `rule`/`candidate_y2` as labels.
6. Reviewer A signs off row by row. Only approved rows are copied into
   `labels.ttl`, `rules.ttl`, `tbox.ttl` or `reference.ttl`; the review file keeps
   the decision record.

The Phase 2 PR that adds the comments links each schema change to its review row
id, so a reviewer can diff the frozen text against the approved text.

---

## 8. Risks and ordered PR breakdown

### 8.1 Risks

- **NR-001 count churn.** `D` must be measured and every live assertion updated;
  a missed `4915`, `5192`, `4671`, `20 graphs`, `39 shapes` or `4 schema graphs`
  is a defect.
- **Duplicate labels/comments.** Adding bilingual labels next to existing
  untagged ones can return two values. The design retags touched terms and
  filters by language; a full repo-wide cleanup is out of scope.
- **Notation ambiguity.** `"HARD"` exists in two schemes and `1` is a guard
  layer; queries must name the scheme. The test checks notation uniqueness **per
  scheme**.
- **Implied data.** `rank_e`, `NO_RISK_MODEL`, `CVaR`, DSR/PBO and the
  not-loaded strategies get concepts; the comments must say "not loaded" so the
  agent does not invent values.
- **C1 leak.** A future contributor may add a C1 concept "for completeness".
  The test asserts absence.
- **Production guard.** If `labels.ttl` is not in the production plan, the
  production agent has no labels. The load-plan test must assert the 5-graph
  production shape.
- **Schema reload.** `load_schema` drops/rewrites the schema graphs; a labels
  change requires a schema reload, not a run-data reload. This is allowed but
  must be stated in the PR and runbook.
- **Existing forbidden mentions.** `schema/tbox.ttl:349` (Grossman & Zhou),
  `schema/tbox.ttl:1094` (Tiingo) and `schema/rules.ttl:273` (Grossman & Zhou)
  predate this work. The new comments avoid them; a global cleanup is a
  comment-only follow-up.
- **English drift.** The Spanish is frozen; the English is a translation.
  Reviewer A's row-level sign-off is the control.

### 8.2 Ordered, small PRs (T-750–T-779)

| PR | Tasks | Content | Acceptance |
|---|---|---|---|
| 1 | **T-750** | This design document and append-only PLAN/TASKS entries. | Design reviewed; no schema/src/cli/test change. |
| 2 | **T-751** | `schema/labels.ttl`: schemes, concepts, notations, labels/comments/altLabels, window fields; `tests/test_labels.py` (notation uniqueness per scheme; one label/comment per language; window fields; absence of C1/`rule`/`candidate_y2`). | File parses; tests fail without the vocabulary; no run IRI in the file. |
| 3 | **T-752** | `LabelConceptShape` in `shapes.ttl`, `LOAD_PLAN`, FR-001 file list, `expected_sizes`, counts and docs; update `test_kg_load_schema`, `test_acceptance_schema_checks`, `test_ontology_v18`, `test_schema_gate`. | 21/`5192+D` test plan, 5/`4671+D` production plan, FR-001 `4915+D`, 40 shapes, pyshacl conforms. |
| 4 | **T-753** | Direct labels/comments for GUARD rules and the active veto rules in `rules.ttl`; label the three veto-class concepts and the markers; remove forbidden mentions from the touched L4_DD comment. | Rule labels present; no Grossman-Zhou/Tiingo in new comments; tests. |
| 5 | **T-754** | Direct labels/comments for `StrategyBook`, `GuardAlert`, `GuardAction`, `Veto`, score/rank/config/process classes and properties; `MetricTypeScheme` concepts; `objective` label and WI 41-consistent comment. | Labels present; `objective` test still passes; no "Markowitz base"; no run IRI touched. |
| 6 | **T-755** | `docs/labels-en-review.md` with every row; Reviewer A sign-off. | All rows approved or changed; no schema change yet. |
| 7 | **T-756** | Freeze the approved English into the schema; final label audit; `kg_target_schema.ttl` decision; comment-only cleanup of the remaining Tiingo/Grossman mentions if approved. | Frozen text matches review rows; counts `D` final; full label audit. |
| 8 | **T-757** | `docs/ttyg/instructions-v1.3.md` + `ontology_construct_curated_v3.rq`; update `docs/ttyg/README.md` and its test. | v1.3 rules in §9; CONSTRUCT returns label concepts and rules; test passes. |
| 9 | **T-758** | `docs/ttyg/evaluation-questions.md` (empty sheet, 14 questions, columns, audit checklist). | Sheet has all 14 ES/EN questions and no answers. |
| 10 | **T-759** | Human runs the sheet against the loaded graph; results recorded outside the repo or in the agreed record. | Four criteria filled per question; findings filed. |
| — | **T-760–T-779** | Reserve for review fixes, a second label pass, or renumbering. | — |

Dependencies: T-751 → T-752 → T-753/T-754 → T-755 → T-756 → T-757 →
T-758 → T-759. T-755 can start as soon as T-751/T-753/T-754 texts exist.

---

## 9. Agent instructions v1.3 (B2): exact changes to the v1.2 block

The source is `docs/ttyg/instructions-v1.2.md` (line numbers refer to the
pasteable `text` block, lines 10–47). Do not edit v1.2 now; v1.3 is a new file.

| v1.2 line | Current rule | v1.3 change |
|---|---|---|
| 11 | "If the graph does not have the data, say …" | Add: "not in the knowledge base used, not that it does not exist in the project." List C1, the mean-variance Markowitz tangency portfolio, Addendum 2, the later exploration, the news layer and GUARD v2. Do not estimate any of them. |
| 15 | Every answer states the run label and counting rule. | Restrict to answers with **empirical results**. A conceptual explanation (e.g. "what is CVaR?") needs no window, run or counting rule. Every empirical answer still states run label, window, arm and counting rule. |
| 16 | Default label `final`; default counting rule is rows inside the window. | Keep. Add: formation-day alerts and warm-up vetoes are reported separately as initialization/warm-up events; when a window total is given, say whether it includes them. |
| 17 | All six windows were seen; final results are in-sample. | Keep and make it explicit in every result answer: no final-configuration result is out of sample. |
| 20 | Layout; `rule` is an old pilot, do not use it. | Remove the `rule` line. State that `final` is the only loaded label; `rule` and `candidate_y2` are not loaded and must not be used or labelled. Add the `urn:graph:labels` lookup. |
| 21 | Discover labels/windows/arms first. | Point to `urn:graph:labels`: `skos:notation` + `rdfs:label`/`rdfs:comment`, filter by language; scheme names disambiguate codes. |
| 24 | Works/arms/windows list and dates; ambiguous window stated. | Add calendar numbers 1–6; window 5 is neutral ("Feb–Sep 2025 (P2)"); H windows carry two separate conditions (historical vs final in-sample); C1 not loaded; "bear market" does not automatically resolve to a window; use number, dates, code or scenario altLabels. |
| 25 | "Arms: MARKOWITZ_BASE, …" | Replace with full strategy names and the confirmed mapping. Codes only in parentheses. Never say "Markowitz base" except for the mean-variance tangency portfolio, which is not in the graph. |
| 26 | Statistical tests list. | Keep; use full arm names when naming a pair. |
| 31 | List all actions; `ARM_DISABLED` are counterfactuals. | Keep; add that GUARD states/alerts are not orders and a weight change does not prove a trade. |
| 32 | Read `:alertState`; do not assume ENTER/EXIT. | Replace with explicit semantics: `ENTER` = rule activated, `EXIT` = rule deactivated; neither is a buy or sell. `ACTIVE`/`COOLDOWN` may not appear. Only claim a buy/sell when transaction data exists; otherwise describe the exposure/weight change. |
| 34 | L4 alerts daily; layer 3 no alerts. | Keep; add that L4 scales **all the reference weights, including the SPY core**, and that counts are actions/state changes, not alerts. |
| 35 | Weights; `:targetWeight` is not a portfolio weight. | Add: the score is not the weight; the satellite weighting comes from `satellite_weighting`, not from `objective`. |
| 37 | `:selectedForBook` is the 60-name pool; `:rankPosition` includes vetoed names. | Add: `rank` includes excluded names; `rank_e` is the rank among eligible names and is **not loaded**; never estimate or substitute it. |
| 38 | `:vetoRulesJson` only carries "HARD"; use the in-force Veto. | Add: `UNSCORED`/`UNPRICED` are markers, not financial vetoes; `NO_RISK_MODEL` is a coverage gap, not a catalog veto; severity is the stint's `:vetoSeverity`. |
| 39 | Decision cycles and warm-up. | Add: formation-day alerts and warm-up vetoes are reported separately; when a window total is given, say it includes them. |
| 42 | Do not present `:objective "min_var"` as the Sistema weighting objective. | Expand to four distinct concepts: registered optimization class (`objective`), satellite weighting (`satellite_weighting` = minimum CVaR in the System), risk model/covariance estimator, and candidate selection. Use the label "Registered optimization class". |
| 44–46 | "What is not in the graph". | Expand the list (C1, mean-variance Markowitz tangency, Addendum 2, later exploration, news layer, GUARD v2, `rank_e`, CVaR values, DSR/PBO) and repeat the "not in the knowledge base used" wording. |
| new | Full names and first mention. | Add: every strategy is named with its complete v3 name and a one-line description the first time it appears; never use an internal code as the name; a code may appear only in parentheses and secondary. |
| new | Operations. | Add: GUARD states/alerts and weight changes are not orders; the graph stores aggregate turnover and cost per session and target/derived weights, not per-asset orders; `EXIT` means the rule was deactivated. |
| new | Conceptual answers. | Add: a conceptual answer (definition, formula, "what is CVaR?") needs no window, run or counting rule; an empirical answer does. |

The v1.3 block should also point at `urn:graph:labels` in the layout section and
state that the labels graph is schema metadata, not run data. The CONSTRUCT v3
adds the label concepts, rule labels and MetricType labels to the agent schema
context (the v2 CONSTRUCT at `docs/ttyg/ontology_construct_curated_v2.rq:8-11`
only projects tbox classes/properties today).

---

## 10. Evaluation sheet (B3)

**Proposed file: `docs/ttyg/evaluation-questions.md`** (Phase 2; the repo holds
the empty sheet, not answers). A human runs it against the loaded graph.

Columns:

| Column | Content |
|---|---|
| `#` | 1–14 |
| `question_es` | The Spanish question from glossary §10 |
| `question_en` | The English question from glossary §10 |
| `must_show` | What the question demonstrates (identification, context, honesty) |
| `answer` | Empty; the human records the agent's answer |
| `queries_used` | Empty; the SPARQL queries the agent ran |
| `identification` | Empty; correct strategy/window/asset/rule? |
| `accuracy` | Empty; matches the graph? |
| `context` | Empty; run/configuration/period/version stated when reporting results? |
| `honesty` | Empty; says when data is unavailable? |
| `notes` | Empty; follow-up or ambiguity |

The 14 questions (ES / EN):

1. ¿Qué ocurrió en la ventana 1? / What happened in window 1?
2. ¿Y en el mercado bajista de 2022? / And in the 2022 bear market?
3. ¿Qué diferencia hay entre `rank` y la posición entre elegibles? / What is the difference between `rank` and the rank among eligible names?
4. ¿Por qué fue excluida una empresa? / Why was a company excluded?
5. ¿El Sistema pondera por mínima varianza o por mínimo CVaR? / Does the System weight by minimum variance or minimum CVaR?
6. ¿Cuántas acciones seleccionó el Sistema? / How many stocks did the System select?
7. ¿Mantuvo una composición 50/50? / Did it keep a 50/50 composition?
8. ¿GUARD vendió una acción cuando aparece `EXIT`? / Did GUARD sell a stock when `EXIT` appears?
9. ¿El Sistema excluye empresas con veto duro? / Does the System exclude hard-vetoed companies?
10. ¿Qué resultados de la configuración final son fuera de muestra? / Which results of the final configuration are out of sample?
11. ¿Qué pasó en la corrida continua? / What happened in the continuous run?
12. ¿Cuál es el Markowitz base? / What is the base Markowitz?
13. ¿Qué es el CVaR? / What is CVaR?
14. ¿Cuál fue el CVaR del Sistema? / What was the System's CVaR?

Criteria, applied per answer:

- **Identification**: the correct strategy, window, asset or rule is named.
- **Accuracy**: the answer matches the graph's data.
- **Context**: configuration, run, period and version are stated when reporting
  empirical results; conceptual answers are exempt.
- **Honesty**: unavailable data is recognised as unavailable, including C1,
  `rank_e`, CVaR values, the tangency portfolio, Addendum 2, the later
  exploration, the news layer and GUARD v2.

The sheet also carries the §10 audit checklist: classes/properties without
`rdfs:label` or `rdfs:comment`; labels without a language or with the wrong
language; `skos:altLabel` per language; relations, domains and ranges; provenance
per run and period; obsolete elements (such as `rule`) outside default queries.

---

## 11. Open questions not answerable from the repository

1. **`rank_e` name and availability.** No `rank_e`/`rankE`/`eligibleRank` exists
   in `schema/`, `src/` or `docs/`. Confirm the upstream column/view name and
   whether the `final_corregida` selection side exposes it. If not, the concept
   stays explanatory and the agent must say it is not loaded.
2. **Configuration parameters.** `core_weight`, `top_n`, `satellite_weighting`,
   `cvar_scenarios`, `cov_estimator`, `lookback`, `min_history`,
   `returns_members`, `trend_filter`, `filter_exit`, `stop_rule`, `cost_bps`,
   `vol_target`, `tilt`, `blend`, `rp`, `news_model`, `news_db`, `shadow_from`
   are not projected properties. Confirm that labels-only is enough for B1/B3,
   or file a separate projection work item (which would need a run-data reload).
3. **`NO_RISK_MODEL` representation.** Confirm it appears (or not) in
   `veto_rules_json`, and whether a future derived marker property is wanted.
   The graph has no literal for it today.
4. **`UNSCORED`/`UNPRICED` structured join.** They live only inside
   `:vetoRulesJson`. Is a `CONTAINS` lookup acceptable for the agent, or should a
   later projector add a parsed marker property? The latter changes engine code
   and needs a reload, so it is out of Phase 1.
5. **`BREAK_TREND_200` class.** It is `SOFT` with `:penaltyPoints 0`, not a
   separate class. Confirm the "indicator" class is presentation-only and must
   not become an `owl:Class` or a new `:vetoClass` property.
6. **Not-loaded strategies.** `B0`, `MCF`, `MARKOWITZ_SAMPLE`,
   `MARKOWITZ_SAMPLE_GUARD`, `BMK_EXPO`, `BMK_BETA`, `BMK_VOL`, `SPY`,
   `SP500_EW` and the mean-variance tangency portfolio are not final books.
   Confirm they get no concept/label (recommended) rather than a concept marked
   "not loaded".
7. **`TOPN_MV_GUARD`.** The shape accepts it but `final` does not load it and
   nomenclature v3 does not name it. Confirm it gets no concept until a run uses
   it.
8. **Direct labels on `StrategyBook` individuals.** The design labels the arm
   concept, not the 24 `Book_*` run individuals. Confirm that is acceptable; the
   alternative is an additive labels-graph statement per book, which does not
   require a data reload but does touch run IRIs.
9. **`final` comment details.** Confirm the comment may name the delivery
   `final_corregida` and `code_commit 5958c6b`, and that `final_b5` must not
   appear anywhere.
10. **Forbidden mentions scope.** Are the existing Tiingo/Grossman-Zhou mentions
    in untouched comments (`schema/tbox.ttl:349, 1094`) in scope for cleanup, or
    only the new/edited comments? The design avoids them in all new text.
11. **`skos:prefLabel`.** The request names `rdfs:label`; GICS and MetricType use
    `skos:prefLabel`. Should the new concepts carry both (`rdfs:label` and
    `skos:prefLabel`) for SKOS consumers, or only the requested `rdfs:label`?
12. **FR-001 membership.** Should `labels.ttl` be part of FR-001 (recommended, so
    it is pyshacl-validated and counted) or only part of the load plan? The
    recommendation changes the `4915` assertion to `4915 + D`.
13. **`kg_target_schema.ttl`.** It mirrors tbox terms but is not in FR-001 or the
    load plan. Should the label vocabulary be mirrored there for consistency, or
    left out because it is a target ontology, not presentation?
14. **Window 5 scenario.** The glossary keeps it neutral until a numeric
    definition exists. Confirm no scenario altLabel is added even though P2
    contains the April 2025 shock.
15. **H1 historical wording.** The glossary says "reserved originally in the
    champion preregistration"; H2/H3 say "originally reserved". Confirm the H1
    specificity is intended and not a copy of a champion-specific definition.
16. **Other loaded labels.** The reports catalog mentions a `candidate` rehearsal
    label; the request says `candidate_y2` is not loaded. Confirm the final store
    contains only `final` and no `candidate`/`rule` label before the v1.3
    instructions drop the defensive `rule` line.
17. **B4 (Part A inventory).** The A4 SPARQL inventory (classes, properties,
    relation types and frequencies; labels/comments per language; provenance;
    obsolete elements) is not re-run in this Phase 1 design. It belongs with the
    label audit in T-756. This design uses the static schema and the existing
    docs; the inventory results are still outstanding.

---

## 12. Residual risk

- The design is only as good as the English review; a translation that adds a
  number or a causal claim would contaminate the presentation layer.
- `D` and every asserted count must be updated in the same PR; NR-001 makes a
  stale count a defect, not a documentation nicety.
- The concept vocabulary is a new schema graph. If the production load is not
  re-run after the merge, the production agent keeps the old labels; the
  runbook must include the schema reload step.
- `load_schema` drops and rewrites all schema graphs. A labels-only change still
  rewrites `tbox`, `reference`, `fibo` and `rules`; no run graph is touched, but
  the operation is a schema reload and needs the usual `portfolio_test` rehearsal.
- Existing untagged labels and comments remain outside the touched set; a query
  that does not filter by language can still return duplicates until a later
  cleanup.
- The not-loaded concepts (`rank_e`, `NO_RISK_MODEL`, CVaR, DSR/PBO) can be
  mistaken for data if the comments are not explicit; the evaluation sheet's
  honesty criterion is the control.
- C1 has no concept by design. If a future contributor adds one "for symmetry",
  the test must fail and the reviewer must reject it.
- The three veto classes are presentation categories, not ontology classes; a
  future ontology change that adds `HardVeto`/`SoftVeto` would need its own work
  item and would make this vocabulary redundant.
- The final store's run label is `final`; any document or agent line that still
  says `final_b5`, `rule` or `candidate_y2` is a live inconsistency to fix in the
  same effort.
