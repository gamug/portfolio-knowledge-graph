# Create the Talk to Your Graph agent by hand

The agent is Workbench state, not graph data: it is **not** carried by a repository export and does
not travel with a GraphDB backup. Recreate it in the Workbench after the `portfolio` repository has
the final schema and data. The repository is the source of truth for the two inputs; this page is
only the form recipe.

## Prerequisites

- GraphDB 11.5.1 Free, with the `portfolio` repository created from
  [`schema/graphdb-repo-config.ttl`](../../schema/graphdb-repo-config.ttl) (ruleset
  `rdfsplus-optimized`).
- The final schema and data loaded, as in [`../final-delivery.md`](../final-delivery.md).
- A Workbench account with the repository-manager role: only a manager can create an agent. A
  read-only user can chat with the agent once it exists.
- An LLM key owned by the operator. Never commit it and never share it.

## LLM settings (`graphdb.llm.*`)

Configure the GraphDB LLM connector in `conf/graphdb.properties` (or as environment variables) with
placeholders only in documentation:

```properties
# The API type. Use openai-completions for an OpenAI-compatible provider such as DeepSeek.
graphdb.llm.api = openai-completions
# The provider's base URL; omit only for OpenAI's default endpoint.
graphdb.llm.url = <PROVIDER_BASE_URL>
# The operator's own key. Never a real value in this repository.
graphdb.llm.api-key = <YOUR_LLM_API_KEY>
# The provider's model id.
graphdb.llm.model = <MODEL_ID>
```

GraphDB 11.5.1 documents `graphdb.llm.api`, `graphdb.llm.url`, `graphdb.llm.api-key` and
`graphdb.llm.model` in its
[Talk to Your Graph and LLM properties](https://graphdb.ontotext.com/documentation/11.5/directories-and-config-properties.html#talk-to-your-graph-and-llm-properties).
The key can also be kept out of the properties file with `graphdb.llm.api-key@file` pointing at a
local file; the file is still private and never committed.

**Tested providers:** DeepSeek works with this agent. Gemini 3.x failed in testing; do not use it
for the delivered agent unless it has been retested. This is an observation from testing, not a
promise about other providers or models.

## Workbench form

Open **Lab → Talk to Your Graph → Create a new agent** (or **Create your first agent**) and fill the
form:

| Field | Value |
|---|---|
| Agent name | `portfolio-final` (a descriptive local name; it is not part of the graph). |
| Repository ID | `portfolio`. |
| Query methods | **SPARQL only**. Disable full-text search, similarity search and the ChatGPT retrieval connector. |
| SPARQL ontology | Choose **Use a CONSTRUCT query** and paste the whole file [`ontology_construct_curated_v2.rq`](ontology_construct_curated_v2.rq). Do not retype or edit it; [`README.md`](README.md) records its SHA-256. |
| Auto-add missing namespaces | Leave the form default unless the Workbench requires it for the CONSTRUCT; the curated query declares its own prefixes. |
| Model | The model from `graphdb.llm.model`, or the provider's equivalent offered by the form. |
| Temperature | `0.1`. |
| Additional instructions | The **single `text` fence** in [`instructions-v1.2.md`](instructions-v1.2.md). Open the file and paste that one block; do not copy it into this page. |
| Context window / Top P / base instructions | Leave the defaults unless the provider rejects one of them. |

Click **Create Agent**.

The instructions are language-neutral on purpose: `portfolio-app` appends a final line to every
question stating the requested language, and the agent answers in that language. Do not add a
Spanish-only or English-only rule to the agent.

## Operating method

- Ask one question at a time and allow **two attempts per question**. If the first answer is wrong
  or fails, adjust the relevant line of the instructions (or the query) and repeat the question;
  after two attempts, record the failure instead of guessing.
- A healthy answer states the run label, the window, the arm and the dates it used, shows the one
  SPARQL query that decided the answer, and says the result is in-sample when it reports final
  performance. It never invents a figure, date or cause.
- For the Sistema's `:objective`, the answer must not present `min_var` as the weighting objective.
  The literal is a fixed per-arm label; the delivery describes a minimum-variance selection of up
  to 30 names followed by minimum-CVaR weighting (Work item 41).

## Related

- [`README.md`](README.md) — the source files and the CONSTRUCT hash.
- [`instructions-v1.2.md`](instructions-v1.2.md) — the single instruction block.
- [`../second-user-setup.md`](../second-user-setup.md) — the colleague's local repository, read-only
  user and first smoke questions.
- [`../final-delivery.md`](../final-delivery.md) — the production load sequence.
