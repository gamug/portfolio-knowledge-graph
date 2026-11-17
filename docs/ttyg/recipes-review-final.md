# Recipes review for the final graph (TTYG v1.5)

**Scope.** This table reviews `docs/ttyg/investor-recipes.md` (C1–C20, R1–R9) against the final
`portfolio` graph loaded from `/workspaces/thesis/knoledge graph/2026-11-17_final_v2` (label
`final`). It does not change any case wording, any recipe, the four evaluation dimensions or the
acceptance criterion. Proposed edits are listed separately for Reviewer A.

## C1–C20

| Case | Question still holds | Configuration / window still holds | Expected answer type still holds | Graph(s) that answer it | Proposed edit |
|---|---|---|---|---|---|
| C1 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: stops + point-in-time fundamentals | `backtest:final:P1:system_with_hierarchy`, `fundamentals:final`, `universe:2026-Q4` | status “needs the reload” is obsolete; propose “available now” after phase 2 |
| C2 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: replacement + sector/fundamental comparison | book, `fundamentals:final`, `universe:2026-Q4`, `reference` | status “needs the reload” is obsolete; propose “available now” |
| C3 | yes | yes: `SYSTEM_WITH_HIERARCHY` + `MARKOWITZ_BASE`, P1 | yes: quality profile comparison | both book graphs, `fundamentals:final` | “partial / five configurations need reload” is obsolete; propose “available now” |
| C4 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: veto vs assessment agreement | `selection:final:P1:system_with_hierarchy`, `rules:catalog`, `fundamentals:final`, `universe:2026-Q4` | none |
| C5 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: sector concentration of vetoes | selection, `rules:catalog`, `universe:2026-Q4`, `reference`, `fundamentals:final` | none |
| C6 | yes | yes: `SYSTEM_WITH_HIERARCHY`, C1 | yes: bank exposure/stops in the continuous window | `backtest:final:C1:system_with_hierarchy`, `universe:2026-Q4`, `reference`, `rules:catalog`, `fundamentals:final` | status “needs the reload (C1)” is obsolete; propose “available now” |
| C7 | yes | yes: both System configurations, P1 | yes: layer-0 episodes + NAV | both book graphs, `rules:catalog` | status “needs the reload” is obsolete; propose “available now” |
| C8 | yes | yes: both System configurations, P1 | yes: summaries + paired tests | both book graphs, `rules:catalog` | status “needs the reload” is obsolete; propose “available now” |
| C9 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes for measured concentration/drawdowns; the causal wording remains not answerable | book, `universe:2026-Q4`, `reference`, `fundamentals:final` | none; keep the causal caveat |
| C10 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: stop destination + cash cause | book | status “needs the reload” is obsolete; propose “available now” |
| C11 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: one decision end to end | book, `rules:catalog`, `universe:2026-Q4`, `fundamentals:final` | status “needs the reload” is obsolete; propose “available now” |
| C12 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: full company card | `universe:2026-Q4`, `reference`, `fundamentals:final`, book + selection | “partial” is obsolete; propose “available now” |
| C13 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: point-in-time knowledge | `universe:2026-Q4`, `fundamentals:final` | none |
| C14 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: retention decisions/holds/rejections | book, `universe:2026-Q4`, `fundamentals:final` | status “needs the reload” is obsolete; propose “available now” |
| C15 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: StopMemory episodes | book, `universe:2026-Q4`, `fundamentals:final` | status “needs the reload” is obsolete; propose “available now” |
| C16 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: rule vs manager destination | book | status “needs the reload” is obsolete; propose “available now” |
| C17 | yes | yes: `SYSTEM_WITH_HIERARCHY` + `MARKOWITZ_BASE`, P1 | yes: composition comparison | both book graphs, `universe:2026-Q4`, `reference`, `fundamentals:final` | “partial / five configurations need reload” is obsolete; propose “available now” |
| C18 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: weak fundamental signals | book, `fundamentals:final`, `universe:2026-Q4` | none |
| C19 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: assessment history and exit | `universe:2026-Q4`, `fundamentals:final`, book | none |
| C20 | yes | yes: `SYSTEM_WITH_HIERARCHY`, P1 | yes: filings vs no filings, Tiingo mask | book, `fundamentals:final`, `universe:2026-Q4` | none |

No C case reads the news, aggregates, series or agent graphs; their questions are fundamentals,
backtest, selection or book questions. None needs a graph change.

## R1–R9

| Case | Refusal still holds | Expected answer type still holds | Graph or reason | Proposed edit |
|---|---|---|---|---|
| R1 | yes | yes: no individual price/return | no price series for individual assets; offer stop/portfolio effect | none |
| R2 | yes | yes: no later-price verdict | same limit; offer C8 | none |
| R3 | yes | yes: no per-asset attribution | only book weights; offer C9/C17 | none |
| R4 | yes | yes: no live portfolio | historical experiment only; offer C12/C17 | none |
| R5 | yes | yes: in-sample, no forecast | backtest graphs; offer C8 | none |
| R6 | yes | yes: Tiingo price/valuation withheld | `fundamentals:final` mask; offer C20 | none |
| R7 | yes | yes: no market causes | decisions, not causes; offer C6 | none |
| R8 | yes | yes: executives not loaded | no executive data; offer the missing-source statement | none |
| R9 | yes | yes: no analyst opinions | generated fundamental assessment; offer C4/C12/C19 | none |

## Proposed edits for Reviewer A (separate, not applied)

1. Update the **status label** of C1, C2, C3, C6, C7, C8, C10, C11, C12, C14, C15, C16 and C17
   from “needs the reload”/“partial” to “available now” after phase 2 verifies them.
2. Keep C9’s causal caveat: the concentration/drawdown series answer the measured part; “preceded”
   remains not answerable.

No case wording, configuration name, window or graph changes are proposed.
