# Talk to Your Graph agent sources

This folder is the repository's source of truth for the Talk to Your Graph (TTYG) agent in GraphDB
Workbench that answers questions about the final backtest. The agent itself lives in the Workbench;
the two files here are the reviewed copies of what the agent must use, so a change is made in the
repository and then pasted into the agent form by hand.

## Files

| File | What it is |
|---|---|
| [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq) | The curated CONSTRUCT that exposes only the classes and properties a reports agent needs. It is a byte-identical copy of the source file (40 lines). |
| [`instructions-v1.2.md`](instructions-v1.2.md) | The English v1.2 "Additional instructions" (one pasteable `text` fence) plus usage notes. It applies Reviewer A's close-out changes and keeps every other v1.1 rule. |

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

## Not covered here

- Switching the LLM provider or model behind the agent.
- Creating the agent step by step in the Workbench.
- The read-only user's setup, permissions and delivery: separate work.
- Pasting the files into the Workbench: a manual human action.
