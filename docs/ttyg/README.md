# Talk to Your Graph agent sources

This folder is the repository's source of truth for the Talk to Your Graph (TTYG) agent in GraphDB
Workbench that answers questions about the final backtest and the fundamentals of its companies.
The agent itself lives in the Workbench; the RDF and instruction sources here are the reviewed
copies of what the agent must use, so a change is made in the repository and then pasted into the
agent form by hand.

## Files

| File | What it is |
|---|---|
| [`ontology_construct_curated_v2_1.rq`](ontology_construct_curated_v2_1.rq) | The current pasteable curated CONSTRUCT. It exposes the 29 classes and 257 properties the reports agent needs, including `SECFiling`, `FundamentalMetricSet`, `FundamentalAssessment`, `Veto`, `GuardAlert` and `returnOnInvestedCapital`. It intentionally carries no presentation labels or rule catalog; the instructions read those from the named graphs. |
| [`instructions-v1.5.md`](instructions-v1.5.md) | The evaluated English v1.5 "Additional instructions" (one pasteable `text` fence) plus usage notes. It keeps the v1.4 rules and adds the complete final graph: news (`sub_news`/`body`), aggregates and `:newsRiskOff`, SPY/MARKOWITZ_MV series, the external MARKOWITZ_MV summaries and the agent traceability graphs. v1.5 remains the evaluated version; v1.7 is the one currently pasted in the demo agent (`portfolio-final-v1-7`). |
| [`instructions-v1.7.md`](instructions-v1.7.md) | The demo English v1.7 "Additional instructions" (one pasteable `text` fence) plus usage notes. It is a demo correction after the v1.5 evaluation: v1.5 plus ready-made query templates and four rule fixes. v1.5 remains the evaluated version; the Workbench agent `portfolio-final-v1-7` holds v1.7. |
| [`instructions-live-v1.md`](instructions-live-v1.md) | The Additional instructions for the second TTYG agent `portfolio-live-v1` over repository `portfolio_live` (Work item 49): one pasteable `text` fence for the three fixed SYSTEM_LIVE graphs, six parameter-free templates and the missing news/SPY refusals. |
| [`investor-recipes.md`](investor-recipes.md) | Bounded SPARQL recipes for the twenty compound investor questions C1–C20, the R1–R9 refusal table and the human test procedure. `tests/test_ttyg_recipes.py` parses and executes the available-now recipes on a synthetic graph. |
| [`create-agent.md`](create-agent.md) | The step-by-step Workbench form: SPARQL only, the accepted v2.1 CONSTRUCT, temperature `0.1`, the single v1.7 instruction fence for the delivered demo agent `portfolio-final-v1-7` and the `graphdb.llm.*` placeholders; v1.5 remains the evaluated version. |
| [`evaluation-questions.md`](evaluation-questions.md) | The T-758/T-762 evaluation sheet: the original ES/EN questions, the T-757 fundamentals/weighting/query-hygiene additions and the T-762 review questions, with expected answers. Answers stay empty for the human run. |
| [`recipes-review-final.md`](recipes-review-final.md) | The C1–C20/R1–R9 review against the final graph: whether each question, configuration/window and answer type still hold, which graph answers it, and the separate status-label proposals for Reviewer A. |
| [`evaluation-recording-template.csv`](evaluation-recording-template.csv) | The blank human-run recording template: one row per case, attempt, answer, generated SPARQL, configuration/window, the four dimensions and notes. |
| [`ontology_construct_curated_v3.rq`](ontology_construct_curated_v3.rq) | **Reference only; not pasteable into the Workbench form.** It adds the presentation labels, the rule catalog and the MetricType labels, which is useful for review and tests, but the form rejects it with a "SPARQL method requires an ontology graph…" validation message while SPARQL runs fine over REST. |
| [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq) | Superseded by v2.1/v3. Kept as the historical copy; do not paste it into the agent. |
| [`instructions-v1.4.md`](instructions-v1.4.md) | Superseded by v1.5. Kept as the historical copy; do not paste it into the agent. |
| [`instructions-v1.3.md`](instructions-v1.3.md) | Superseded by v1.4. Kept as the historical copy; do not paste it into the agent. |
| [`instructions-v1.2.md`](instructions-v1.2.md) | Superseded by v1.4. Kept as the historical copy; do not paste it into the agent. |

SHA-256 of `ontology_construct_curated_v2_1.rq`:

```text
9f0b96af7427583015fbec1e0d59ce411c95db000d8173940454143c606bdc64
```

The file is a byte-exact copy (2,271 bytes) of
`/workspaces/thesis/knoledge graph/para_agente_ttyg/v2_1_con_fundamentales.rq`; `cmp` and `sha256sum`
agree before and after the copy. This is the only CONSTRUCT the Workbench form accepted on
2026-11-14.

SHA-256 of the reference-only `ontology_construct_curated_v3.rq`:

```text
781ac9171ae3328861c673795c6e5ec3d392baa4f1db4ac999f1b3cb4ec573aa
```

`tests/test_ttyg_docs.py` recomputes both hashes, parses and runs v2.1 against
`schema/tbox.ttl`, and keeps the v3 checks against `schema/tbox.ttl`, `schema/labels.ttl`,
`schema/reference.ttl` and `schema/rules.ttl`. The v2.1 CONSTRUCT selects 29 `owl:Class` subjects
and 257 properties (measured 2026-11-14), including the three fundamentals classes and the
`returnOnInvestedCapital` datatype property. The v3 reference query selects the same 29 classes plus
the 161 label/metric-type concepts, the 12 concept schemes and the 24 rule definitions with their
bilingual labels.

## How the files map to the agent form

| Agent form field | Value |
|---|---|
| Repository ID | `portfolio` for the delivered agent; `portfolio_test` is only the rehearsal repository. |
| Method | SPARQL only. |
| Curated CONSTRUCT | [`ontology_construct_curated_v2_1.rq`](ontology_construct_curated_v2_1.rq). |
| Auto-add missing namespaces | Ticked. |
| Temperature | `0.1`. |
| Additional instructions | The single `text` fence in [`instructions-v1.7.md`](instructions-v1.7.md) for the delivered demo agent `portfolio-final-v1-7`; v1.5 remains the evaluated version. |

## Evaluation questions (T-758/T-759/T-762)

The question list is [`evaluation-questions.md`](evaluation-questions.md): the original ES/EN
questions, the T-757 fundamentals, weighting and query-hygiene additions, and the T-762 review
questions (flag-only rule, C1, and a counting rule that must match the query). The human run (T-759)
is still pending; the repository holds the questions and expected-answer guidance, not recorded
answers.

The sheet includes Reviewer A's fundamentals note: the three turnover ratios and ROA/ROE divide a
flow by a balance-sheet balance, not an average; 10-Q flows are annualized before the ROA/ROE
division. A question that compares a 10-Q with a 10-K must not expect average-based turnover.

## Not covered here

- Switching the LLM provider or model behind the agent: see [`create-agent.md`](create-agent.md)'s
  `graphdb.llm.*` placeholders.
- Pasting the files into the Workbench: a manual human action; the step-by-step form is
  [`create-agent.md`](create-agent.md).
- The read-only user's setup, permissions and delivery: see
  [`../second-user-setup.md`](../second-user-setup.md).
