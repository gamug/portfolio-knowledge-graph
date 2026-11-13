# Talk to Your Graph agent sources

This folder is the repository's source of truth for the Talk to Your Graph (TTYG) agent in GraphDB
Workbench that answers questions about the final backtest and the fundamentals of its companies.
The agent itself lives in the Workbench; the RDF and instruction sources here are the reviewed
copies of what the agent must use, so a change is made in the repository and then pasted into the
agent form by hand.

## Files

| File | What it is |
|---|---|
| [`ontology_construct_curated_v3.rq`](ontology_construct_curated_v3.rq) | The current curated CONSTRUCT. It exposes the classes and properties the reports agent needs, the block C fundamentals model (`SECFiling`, `FundamentalMetricSet`, `FundamentalAssessment`, the 37 metric properties and `pricesNotPublished`), the presentation concepts from `urn:graph:labels`, the rule labels from `urn:graph:rules:catalog` and the MetricType labels from `urn:graph:reference`. |
| [`instructions-v1.3.md`](instructions-v1.3.md) | The current English v1.3 "Additional instructions" (one pasteable `text` fence) plus usage notes. It applies `docs/labels-design.md` §9 and the fundamentals/weighting rules. |
| [`create-agent.md`](create-agent.md) | The step-by-step Workbench form: SPARQL only, the curated CONSTRUCT, temperature `0.1`, the single instruction fence and the `graphdb.llm.*` placeholders. |
| [`evaluation-questions.md`](evaluation-questions.md) | The T-758 evaluation sheet: the 16 original ES/EN questions plus the T-757 fundamentals, weighting and query-hygiene additions with expected answers. Answers stay empty for the human run. |
| [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq) | Superseded by v3. Kept as the historical copy; do not paste it into the agent. |
| [`instructions-v1.2.md`](instructions-v1.2.md) | Superseded by v1.3. Kept as the historical copy; do not paste it into the agent. |

SHA-256 of `ontology_construct_curated_v3.rq`:

```text
781ac9171ae3328861c673795c6e5ec3d392baa4f1db4ac999f1b3cb4ec573aa
```

`tests/test_ttyg_docs.py` recomputes this hash, parses and runs the CONSTRUCT against
`schema/tbox.ttl`, `schema/labels.ttl`, `schema/reference.ttl` and `schema/rules.ttl`, and checks
the pasteable instruction block. The CONSTRUCT selects 29 `owl:Class` subjects from the TBox
(measured 2026-11-13), including the three new fundamentals classes. Its output also carries the
161 label/metric-type concepts (156 presentation concepts plus the 5 MetricType concepts), the 12
concept schemes and the rule definitions with their bilingual labels.

## How the files map to the agent form

| Agent form field | Value |
|---|---|
| Method | SPARQL only. |
| Curated CONSTRUCT | [`ontology_construct_curated_v3.rq`](ontology_construct_curated_v3.rq). |
| Temperature | `0.1`. |
| Additional instructions | The single `text` fence in [`instructions-v1.3.md`](instructions-v1.3.md). |

## Evaluation questions (T-758/T-759)

The question list is [`evaluation-questions.md`](evaluation-questions.md): the 16 original ES/EN
questions plus the T-757 fundamentals, weighting and query-hygiene additions with expected answers.
The human run (T-759) is still pending; the repository holds the questions and expected-answer
guidance, not recorded answers.

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
