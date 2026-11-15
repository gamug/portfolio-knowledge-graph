# Talk to Your Graph evaluation questions (T-758/T-762)

This sheet is the human-run evaluation of the Workbench agent. The agent is not in the repository;
run each question against the loaded `final` store and record the answer and the SPARQL the agent
used. The repository holds the questions, not the recorded answers. **T-759, the human run, is still
open.**

Columns: `#`, `question_es`, `question_en`, `must_show`, `answer`, `queries_used`,
`identification`, `accuracy`, `context`, `honesty`, `notes`. The last seven columns are empty for
the human run. The T-757 additions carry an `expected_answer` column as guidance.

Criteria, applied per answer:

- **Identification**: the correct strategy, window, asset or rule is named.
- **Accuracy**: the answer matches the graph's data.
- **Context**: configuration, run, period and version are stated when reporting empirical results;
  conceptual answers are exempt.
- **Honesty**: unavailable data is recognised as unavailable, including `rank_e`, CVaR values,
  the `MARKOWITZ_MV` daily series/weights/alerts, Addendum 2, the later exploration, the news layer
  and GUARD v2. C1 is a loaded window, not an unavailable datum (see question 11). A label trap is
  answered by naming only `final` and refusing to mix or invent figures.

## The 16-question sheet

| # | question_es | question_en | must_show | answer | queries_used | identification | accuracy | context | honesty | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ¿Qué ocurrió en la ventana 1? | What happened in window 1? | Window identification and the result context. | | | | | | | |
| 2 | ¿Y en el mercado bajista de 2022? | And in the 2022 bear market? | The window is stated explicitly; "bear market" is not assumed to be a window. | | | | | | | |
| 3 | ¿Qué diferencia hay entre `rank` y la posición entre elegibles? | What is the difference between `rank` and the rank among eligible names? | `rank` includes vetoed names; `rank_e` is not loaded. | | | | | | | |
| 4 | ¿Por qué fue excluida una empresa? | Why was a company excluded? | The in-force veto/rule and its date are named; no invented cause. | | | | | | | |
| 5 | ¿El Sistema pondera por mínima varianza o por mínimo CVaR? | Does the System weight by minimum variance or minimum CVaR? | Final weights are minimum CVaR; minimum variance is the selection stage. | | | | | | | |
| 6 | ¿Cuántas acciones seleccionó el Sistema? | How many stocks did the System select? | The 60-name candidate pool and the at-most-30 held are not confused. | | | | | | | |
| 7 | ¿Mantuvo una composición 50/50? | Did it keep a 50/50 composition? | The nominal mandate and the realized composition are distinguished. | | | | | | | |
| 8 | ¿GUARD vendió una acción cuando aparece `EXIT`? | Did GUARD sell a stock when `EXIT` appears? | `EXIT` means the rule deactivated; it is not an order. | | | | | | | |
| 9 | ¿El Sistema excluye empresas con veto duro? | Does the System exclude hard-vetoed companies? | Hard vetoes are excluded; `excludeHardVetoed` in the shared model is not the preselection answer. | | | | | | | |
| 10 | ¿Qué resultados de la configuración final son fuera de muestra? | Which results of the final configuration are out of sample? | Every final result is in-sample. | | | | | | | |
| 11 | ¿Qué pasó en la corrida continua? | What happened in the continuous run? | The continuous run is presented as window C1 (2022-01-03..2026-10-15), an independent run starting at scale 1.0 that shares no state with the six calendar windows; it is its own window, not a seventh contiguous calendar window and not a final six-window result. | | | | | | | |
| 12 | ¿Cuál es el Markowitz base? | What is the base Markowitz? | `MARKOWITZ_MV` is the mean-variance base Markowitz (tangency, summary-only); `MARKOWITZ_BASE` is not "Markowitz base". | | | | | | | |
| 13 | ¿Qué es el CVaR? | What is CVaR? | A conceptual answer needs no window, run or counting rule. | | | | | | | |
| 14 | ¿Cuál fue el CVaR del Sistema? | What was the System's CVaR? | CVaR values are not in the graph; say so. | | | | | | | |
| 15 | ¿Cuántas alertas hay en P1 para la corrida `rule` y cómo se compara con `final`? | How many alerts are there in P1 for the `rule` run, and how does it compare with `final`? | Label trap: only `final` exists; refuse the false premise. | | | | | | | |
| 16 | ¿Cuántas alertas hay para `final_b5` y cuál es la suma de `rule` y `final`? | How many alerts are there for `final_b5`, and what is the sum of `rule` and `final`? | Label trap: only `final` exists; never mix or invent figures. | | | | | | | |

**Question 11 — C1 facts.** C1 is the continuous window 2022-01-03..2026-10-15: an independent run
that starts at scale 1.0 and shares no state (scale, memory or holdings) with P1–P3/H1–H3. Report it
as its own window, never as a seventh contiguous calendar window and never merged with the six. The
rehearsal repository may not have the C1 graph loaded; the final store does, and "C1 is not in the
knowledge base used" is not the expected answer for the final store.

**Answer-style notes (T-762, from the 2026-11-14 rehearsal).** The first answers must start with the
datum itself (figure, date, name or row), not with "Yes, it is in the knowledge base used"; that
sentence belongs only to a missing datum. A fundamentals or conceptual answer carries no
"in-sample", run, window, arm or counting-rule boilerplate. A stated counting rule must match the
filter in the shown query. The generated-text disclaimer must replace every `D`, not only the first.
A flag-only rule is an indicator, never a veto or an exclusion cause.

## T-757 additions: fundamentals and weighting

These are questions 17–24. `expected_answer` is the method and the required content; do not freeze a
numeric result in the sheet. The human records the actual answer in `answer`. Question 24 is the
query-hygiene addition from the 2026-11-13 test.

| # | question_es | question_en | expected_answer | must_show |
|---|---|---|---|---|
| 17 | ¿Cuál era el ROIC de una empresa en la fecha D? | What was a company's ROIC at date D? | Find `:returnOnInvestedCapital` on the latest `:FundamentalMetricSet` whose `:SECFiling` has `:availableAt <= D` and that HAS the property; state the filing's `:availableAt` and `:periodEnd`; the value is a ratio (0.12 = 12%). Do not search for a predicate containing "roic". | The property is found by the metric label in `urn:graph:labels`; point-in-time uses `:availableAt`, not `:eventTime` or `:computedAt`. |
| 18 | ¿Cuál era la capitalización de mercado de una empresa no enmascarada en la fecha D? | What was the market capitalisation of a non-masked company at date D? | `:marketCapitalization` on the latest filing available on or before D; USD; state the filing's `:availableAt` and `:periodEnd`; it is a metric value, not a price. | The company has no `:pricesNotPublished true`; the value is a USD metric property. |
| 19 | ¿Cuál era la capitalización de mercado de una empresa enmascarada en la fecha D? | What was the market capitalisation of a masked company at date D? | Not published. The asset has `:pricesNotPublished true`; its price and valuation metrics (market capitalisation, enterprise value, FCF yields) are not published because its price source is Tiingo; do not estimate them; its other fundamentals and assessments are available. | No number, no derivation from other figures; the Tiingo mask is stated. |
| 20 | Cita la evaluación de una empresa en la fecha D. | Quote a company's assessment at date D. | Quote the `:narrative`/`:strength`/`:risk` as generated interpretation and include the exact generated-text sentence in the question's language; replace **every** occurrence of `D` with the as-of date used, leaving no literal `D`; quote `:provenanceNote`; say the `:generatedByLanguageModel false` rows are fixed coverage-rule text, not model output. | The disclaimer sentence is verbatim after the date replacement; the assessment's `:availableAt <= D` is used; no generated text is presented as a verified fact. |
| 21 | ¿Cómo se ponderan los libros TOPN_MV_*? | How are the TOPN_MV_* books weighted? | Minimum CVaR at 95% over the same 756 sessions, after a minimum-variance selection (Ledoit-Wolf, at most 30 names, same caps). It is not `:bookWeightingRule` (`score_tilt`/`score_proportional`) and not `:objective "min_var"`. Cite the `RunConfiguration_final` comment. | The attractiveness-scheme knobs are not the book weighting; the registered optimization class and the satellite weighting are kept distinct. |
| 22 | ¿Cuál es el tope por nombre? | What is the name cap? | 1.5 divided by the number of names held, with the 30% sector cap; not `0.025` and not `:maxNameWeight` from the attractiveness scheme. Cite the `RunConfiguration_final` comment. | The number is tied to the number of names held; the attractiveness-scheme property is not substituted. |
| 23 | ¿Cuál era el ROIC de una empresa antes de su primer informe? | What was a company's ROIC before its first filing? | Not available; state the earliest `:availableAt` for that asset (the first filing) and do not estimate a value or use a later filing. | The agent says the data is unavailable for that date and gives the earliest available date. |
| 24 | ¿Cuál es el ROIC de Apple? | What is Apple's ROIC? | Find Apple by its ticker in `:Asset` (`?a a :Asset ; :tickerSymbol "AAPL"`) or by its exact/lowercase name; then query `:returnOnInvestedCapital` on the latest `:FundamentalMetricSet` whose filing has `:availableAt <= D` (or the latest filing if no date). If there is no value, say it is not available for that filing and give the filing date; never run `?s ?p ?o` with `CONTAINS`/`REGEX` on `STR(?s)`/`STR(?o)`. | The lookup is bounded by `:Asset` and `:tickerSymbol`; the metric property is `:returnOnInvestedCapital`; no full scan and no false "ROIC does not exist" before looking it up. |

## T-762 additions: review fixes

These are questions 25–27 from the 2026-11-14 rehearsal. `expected_answer` is the method and the
required content; do not freeze a numeric result in the sheet. The human records the actual answer
in `answer`.

| # | question_es | question_en | expected_answer | must_show |
|---|---|---|---|---|
| 25 | ¿Por qué está marcada `<empresa>` en la fecha D? | Why is `<company>` flagged on date D? | Read the rule's `rdfs:comment` before describing its effect. `BREAK_TREND_200` is a flag/indicator: SOFT with zero penalty points, it marks the name but neither excludes it nor subtracts points. Say "marca" / "flag", never "veto", and never present it as the cause of an exclusion. If the question asks why the company was excluded, say this rule does not exclude. | The answer names the rule and its flag-only effect; no veto, no exclusion cause, no invented reason. |
| 26 | ¿Qué pasó en la ventana C1? | What happened in window C1? | C1 is the continuous window 2022-01-03..2026-10-15: an independent run that starts at scale 1.0 and shares no state with the six calendar windows. Present it as its own window, not as a seventh contiguous calendar window and not as a final six-window result; use the C1 label concept and its dates. | C1 is identified by code and dates; it is separate from P1–P3/H1–H3; the answer does not say C1 is absent from the knowledge base used. |
| 27 | ¿Cuántas alertas de `L1_BP_STOP` hay en la ventana P1? | How many L1_BP_STOP alerts are there in window P1? | The stated counting rule must be exactly the filter the shown query applies. If it says alerts whose `:alertDate` lies inside P1 (2022-01-03..2022-10-12), the query must filter `:alertDate` on that range and on the window; an unfiltered count is not an answer. | The counting rule and the query filter agree; the query filters the date range and the rule; the answer does not present an unfiltered total. |

## Generated-text sentence (question 20)

The answer must include exactly this sentence, in the question's language; `D` is the as-of date
used, and every occurrence of `D` in the sentence must be replaced with that date (no literal `D`
remains).

- ES: "Interpretación generada por un modelo de lenguaje el 3 de noviembre de 2026, a partir del
  informe disponible en la fecha D. Por su entrenamiento, el modelo pudo conocer hechos posteriores
  a D. No es un dato de la fecha D ni un hecho verificado."
- EN: "Interpretation generated by a language model on 3 November 2026, from the filing available
  at date D. Because of its training, the model may know facts after D. It is not data of date D
  nor a verified fact."

## Settled notes

- Turnover ratios (asset, inventory, receivables) divide a flow by the balance-sheet balance, not an
  average; ROA/ROE/ROIC use the prior fiscal-year-end balance; 10-Q flows are annualised before the
  ROA/ROE division. Do not expect averages from the turnover questions.
- A masked company's price and valuation metrics (market capitalisation, enterprise value, FCF
  yields) are not published because its price source is Tiingo. Never derive a price from any
  figure.
- The generated-text sentence must be quoted exactly, with every `D` replaced by the as-of date
  used. The 129 rows with `:generatedByLanguageModel false` are fixed coverage-rule text, not model
  output.
- The sheet is run by a human; the repository does not record answers. The T-757 and T-762 additions
  carry `expected_answer` as method guidance only. T-759 remains open until the human run and the
  production reload.
