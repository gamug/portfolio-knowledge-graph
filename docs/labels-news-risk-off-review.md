# Proposed labels for the news risk-off aggregate column (block B2, 2026-11-16)

**Status: proposed for Reviewer A; not approved yet.** This table follows
`docs/labels-veto-review.md`: one row per term, with the Spanish and English label and comment.
The new column is `news_risk_off` in `aggregates_final.json` (letter 26, block A). Reviewer A's
decision is the authority; where this table and the letter differ, the letter wins.

The schema already carries the property and the shape so the corrected delivery can be loaded;
the English/Spanish texts below are the ones in `schema/tbox.ttl` and must be reviewed before
they are treated as frozen.

## 1. New property

| id | code / IRI | kind | ES label | EN label | ES comment | EN comment | Reviewer A decision | Notes |
|---|---|---|---|---|---|---|---|---|
| AGG-NEWS-01 | `newsRiskOff` | datatype property (boolean) | Entrada de noticias de aversión al riesgo | News risk-off input | True cuando la regla de noticias de nivel D puso el filtro de tendencia en efectivo en esta decisión; es una entrada independiente del estado de precio. | True when the level D news rule put the trend filter in cash at this decision; it is an input independent of the price state. | pending | Domain `:TrendFilterState`, range `xsd:boolean`, functional; required by `:TrendFilterStateShape` |

## 2. Changed class and property texts

These rows change only the comment/definition of existing terms; no new class or shape is added.

| id | code / IRI | kind | ES text | EN text | Reviewer A decision | Notes |
|---|---|---|---|---|---|---|
| AGG-NEWS-02 | `TrendFilterState` | class definition/comment | Estado del filtro de tendencia de la cartera TOPN_MV_GUARD en una fecha de decisión: la entrada de precio (el índice de retorno total de SPY frente a la media simple de sus últimos 210 cierres), la entrada de noticias del nivel D (`news_risk_off`), la fracción de la cartera movida a efectivo y el brazo al que se aplica. No publica ningún nivel de precio ni la media. | One row of `aggregates_<label>.json` `trend_filter`: the price input of SPY against the simple mean of its last 210 session closes, the level D news input (`newsRiskOff`), the cash fraction the filter moved to cash, and the one Top-N arm it applies to. `:trendState` is `below` \| `at_or_above` \| `not_evaluable`; no price level or mean is published. Work item 37; the news input was added in 2026-11-16. | pending | The class keeps its IRI and its `:Observation` subclass |
| AGG-NEWS-03 | `trendState` | datatype property | below, at_or_above o not_evaluable para la entrada de precio: el índice de retorno total de SPY (dividendos reinvertidos) frente a la media simple de sus últimos 210 cierres; no se publica nivel de precio ni media. | below, at_or_above or not_evaluable for the price input: SPY's total-return index (dividends reinvested) against the simple mean of its last 210 session closes; no price level or mean is published. | pending | The property is now one of two filter inputs |
| AGG-NEWS-04 | `cashFraction` | datatype property | Fracción del objetivo TOPN_MV_GUARD movida a efectivo por el filtro de tendencia en esta decisión, mantenida hasta la siguiente fecha de decisión; 0,5 cuando la entrada de precio está below o `newsRiskOff` es true, y 0,0 en otro caso. | Fraction of the TOPN_MV_GUARD target moved to cash by the trend filter at this decision, held until the next decision date; 0.5 when the price input is below or `newsRiskOff` is true, otherwise 0.0. | pending | The value remains `xsd:decimal` in [0, 1] |
| AGG-NEWS-05 | `appliesToArm` | datatype property | TOPN_MV_GUARD: el único brazo al que se aplica el filtro de tendencia, leído de `trend_filter_applies_to_arms`. Los brazos MARKOWITZ_* y SYSTEM_WITHOUT_HIERARCHY nunca lo usan. SHACL exige este valor en cada fila. | TOPN_MV_GUARD: the one arm the trend filter applies to, read from `trend_filter_applies_to_arms`. The MARKOWITZ_* arms and SYSTEM_WITHOUT_HIERARCHY never use it. SHACL requires this value on every row. | pending | Shape cardinality is now exactly 1 |

## 3. Source column (for the record)

| Column | Type | Meaning |
|---|---|---|
| `news_risk_off` | boolean | True when the level D news rule put the filter in cash. It is true in 15 of the 61 final rows; in 8 of those SPY is also below its mean. |

The price column `spy_vs_sma210` is only the price input. `cash_fraction` is 0.5 when
`spy_vs_sma210 == "below"` or `news_risk_off == true`, otherwise 0.0.
