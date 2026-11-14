# Create the Talk to Your Graph agent by hand

The agent is Workbench state, not graph data: it is **not** carried by a repository export and does
not travel with a GraphDB backup. Recreate it in the Workbench after the `portfolio` repository has
the final schema and data. The repository is the source of truth for the RDF and instruction inputs; this page is
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
| Repository ID | `portfolio` for the delivered agent. Use `portfolio_test` only for a rehearsal, never for the delivered agent. |
| Query methods | **SPARQL only**. Disable full-text search, similarity search and the ChatGPT retrieval connector. |
| SPARQL ontology | Choose **Use a CONSTRUCT query** and paste the whole file [`ontology_construct_curated_v2_1.rq`](ontology_construct_curated_v2_1.rq). Do not retype or edit it; [`README.md`](README.md) records its SHA-256. Do **not** paste `ontology_construct_curated_v3.rq`: the form rejects it with a "SPARQL method requires an ontology graph…" validation message even though the query runs over REST. |
| Auto-add missing namespaces | **Ticked.** Use the form setting that the accepted v2.1 CONSTRUCT was created with. |
| Model | The model from `graphdb.llm.model`, or the provider's equivalent offered by the form. |
| Temperature | `0.1`. |
| Additional instructions | The **single `text` fence** in [`instructions-v1.4.md`](instructions-v1.4.md). Open the file in the repository and paste that one block; do not copy it into this page. Do not reuse a copy from the scratch folder: that rehearsal copy had different GUARD rules. |
| Context window / Top P / base instructions | Leave the defaults unless the provider rejects one of them. |

Click **Create Agent**. If the form blocks Create Agent, first suspect the SPARQL ontology input:
paste the byte-exact v2.1 file, tick **Auto-add missing namespaces**, and confirm the `portfolio`
repository has its schema graphs loaded. v3 is rejected by this form.

After pasting the instructions, open **Review agent instructions**. It must show exactly
**23,766 characters** (the length of the single fence in `instructions-v1.4.md`). If the number is
different, **STOP**: the paste is stale or partial; reopen the repository file and paste the whole
fence again.

Before asking anything, confirm that the agent chat selector at the top shows the repository
`portfolio` (not `portfolio_test`). Ask **one question per chat** so a wrong answer is not carried
into the next question by the conversation history.

The instructions are language-neutral on purpose: `portfolio-app` appends a final line to every
question stating the requested language, and the agent answers in that language. Do not add a
Spanish-only or English-only rule to the agent.

## Operating method

- Ask one question at a time and allow **two attempts per question**. If the first answer is wrong
  or fails, adjust the relevant line of the instructions (or the query) and repeat the question;
  after two attempts, record the failure instead of guessing.
- A backtest answer starts with the datum, states the run label, the window, the configuration and
  the dates it used, shows the one SPARQL query that decided the answer, and says the result is
  in-sample when it reports final performance. A fundamentals or conceptual answer starts with the
  datum and carries none of that boilerplate: no "in-sample", run, window or arm statement. No
  answer opens with "Yes, it is in the knowledge base used" unless the datum is missing.
- When an answer gives a counting rule, the rule must match the filter in the shown query. If it
  says the alerts fall inside a date range, the query must filter `:alertDate` on that range.
- For the System's `:objective`, the answer must not present `min_var` as the weighting objective.
  The literal is a fixed per-arm label; the delivery describes a minimum-variance selection of up
  to 30 names followed by minimum-CVaR weighting. The book weighting and caps come from the
  `RunConfiguration_final` comment, not from `:bookWeightingRule` or the
  `:AttractivenessWeightScheme` knobs.
- For a fundamentals question, the agent looks up the metric by its label in `urn:graph:labels` and
  uses the direct property (`:returnOnInvestedCapital`, not a predicate containing "roic"). A masked
  asset (`:pricesNotPublished true`) has no published price or valuation metrics because its price
  source is Tiingo. If an asset has no filing in the graph, the answer says there are no financial
  filings for this company in the knowledge base used.
- A rule described as "flag only" (for example `BREAK_TREND_200`) is an indicator: it marks a name
  but neither excludes it nor subtracts points. Never call it a veto or an exclusion cause.
- Never run a full `?s ?p ?o` scan filtered by `CONTAINS`/`REGEX` on `STR(?s)`/`STR(?o)`. Find a
  company inside `:Asset` by `:tickerSymbol` (e.g. `:tickerSymbol "AAPL"`) or `:companyName`, and
  bound every query to a graph with `LIMIT`.

## Related

- [`README.md`](README.md) — the source files and the CONSTRUCT hashes.
- [`instructions-v1.4.md`](instructions-v1.4.md) — the single instruction block.
- [`investor-recipes.md`](investor-recipes.md) — the bounded recipes and the human test procedure.
- [`../second-user-setup.md`](../second-user-setup.md) — the colleague's local repository, read-only
  user and first smoke questions.
- [`../final-delivery.md`](../final-delivery.md) — the production load sequence and the agent step.
