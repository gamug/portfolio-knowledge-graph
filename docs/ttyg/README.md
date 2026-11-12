# Talk to Your Graph agent sources

This folder is the repository's source of truth for the Talk to Your Graph (TTYG) agent in GraphDB
Workbench that answers questions about the final backtest. The agent itself lives in the Workbench;
the two RDF sources here are the reviewed copies of what the agent must use, so a change is made in
the repository and then pasted into the agent form by hand.

## Files

| File | What it is |
|---|---|
| [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq) | The curated CONSTRUCT that exposes only the classes and properties a reports agent needs. It is a byte-identical copy of the source file (40 lines). |
| [`instructions-v1.2.md`](instructions-v1.2.md) | The English v1.2 "Additional instructions" (one pasteable `text` fence) plus usage notes. It applies Reviewer A's close-out changes and keeps every other v1.1 rule. |
| [`create-agent.md`](create-agent.md) | The step-by-step Workbench form: SPARQL only, the curated CONSTRUCT, temperature `0.1`, the single instruction fence and the `graphdb.llm.*` placeholders. |

SHA-256 of `ontology_construct_curated_v2.rq`:

```text
9dd728d02c5e16bcb415cd3ed7db16bf70d45490684c83125369f9e7cd9561bd
```

`tests/test_ttyg_docs.py` recomputes this hash, parses and runs the CONSTRUCT against
`schema/tbox.ttl`, and checks the pasteable instruction block. The CONSTRUCT selects 26 `owl:Class`
subjects from the TBox (measured 2026-11-09).

## How the files map to the agent form

| Agent form field | Value |
|---|---|
| Method | SPARQL only. |
| Curated CONSTRUCT | [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq). |
| Temperature | `0.1`. |
| Additional instructions | The single `text` fence in [`instructions-v1.2.md`](instructions-v1.2.md). |

## Pending evaluation questions (T-758)

When the 16-question evaluation sheet is written, include Reviewer A's fundamentals note: the three
turnover ratios and ROA/ROE divide a flow by a balance-sheet balance, not an average; 10-Q flows are
annualized before the ROA/ROE division. A question that compares a 10-Q with a 10-K must not expect
average-based turnover.

## Not covered here

- Switching the LLM provider or model behind the agent: see [`create-agent.md`](create-agent.md)'s
  `graphdb.llm.*` placeholders.
- Pasting the files into the Workbench: a manual human action; the step-by-step form is
  [`create-agent.md`](create-agent.md).
- The read-only user's setup, permissions and delivery: see
  [`../second-user-setup.md`](../second-user-setup.md).
