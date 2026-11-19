# Second-user setup: local GraphDB + `portfolio-app`

For a colleague who will run `portfolio-app` locally against their own GraphDB, using the
maintainer's delivered store. The delivered graph is one repository named `portfolio`, one run
label `final`; `portfolio_test` is only the maintainer's rehearsal and is never shipped.

The colleague needs GraphDB, the exported graph, the TTYG agent and the app. The app must use a
**read-only** GraphDB user; only the person creating the agent and importing the graph needs a
repository-manager account. The maintainer's production sequence is
[`final-delivery.md`](final-delivery.md).

## 1. GraphDB

Install **GraphDB 11.5.1 Free** and start it locally. In the Workbench:

1. Create a repository named `portfolio` from the delivered
   `portfolio-repository-config.ttl`, or from
   [`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl) (Setup → Repositories →
   Create → upload RDF config). Both carry the required `graphdb:ruleset "rdfsplus-optimized"` and
   `graphdb:disable-sameAs "true"`.
2. Enable security and create the users below.
3. Do not load `instances.trig` or the worked-example ABox; the delivered export already contains
   the production graph set.

Check the repository profile before importing anything:

```bash
curl -fsS -u "$KG_ADMIN_USER:$KG_ADMIN_PASSWORD" -H 'Accept: text/turtle' \
  "$KG_HOST/rest/repositories/portfolio" | grep -E 'graphdb:(ruleset|disable-sameAs)'
```

## 2. Verify and import the maintainer's export

The maintainer delivers the folder **`portfolio-final-20261117T154804Z`** with:

- `portfolio-final-20261117T154804Z.trig` — every named graph, exported from the `portfolio`
  repository. The delivered file is **1,161,572,478 bytes (about 1.16 GB)** and holds
  **12,727,091 explicit triples in 86 named graphs**;
- `portfolio-repository-config.ttl` — the repository configuration (the repository ID is
  `portfolio`);
- `SHA256SUMS` — one SHA-256 for the TriG and one for the repository configuration.

Verify the hashes **before** importing. A mismatch means the copy is incomplete or changed; ask for
a fresh copy instead of importing it.

```bash
cd /path/to/portfolio-final-20261117T154804Z
sha256sum -c SHA256SUMS
```

Create the empty `portfolio` repository first (section 1), then import the TriG into it. **Prefer
Workbench → Import → Server files** (or the equivalent upload form) for a 1.16 GB file: a single
HTTP POST of that size can hit timeouts or memory limits, and the import takes **minutes, not seconds**. The statements endpoint remains an alternative; it appends the named graphs, so the
repository must be empty.

```bash
curl -fsS -u "$KG_ADMIN_USER:$KG_ADMIN_PASSWORD" \
  -H 'Content-Type: application/x-trig' \
  --data-binary @portfolio-final-20261117T154804Z.trig \
  "$KG_HOST/repositories/portfolio/statements"
```

**Not yet verified on a live store.** The TriG export through
`/repositories/portfolio/statements` and the re-import of the 12,727,091-triple file have not been
tried on this installation. Rehearse the import into a scratch repository first; if the POST fails,
use Workbench **Import** (upload or server files).

Read-only checks after the import:

```bash
curl -fsS -u "$KG_USER:$KG_PASSWORD" \
  "$KG_HOST/repositories/portfolio/size"
```

and, from a checkout of this repository with `.env` pointing at the local GraphDB:

```bash
KG_REPOSITORY=portfolio uv run python cli/verify_store.py --to-production
```

`verify_store` must print one `PASS` per check and exit 0. It reads only; the production repository
is named `portfolio`, so the `--to-production` flag is required even for the read-only verifier.

## 3. Recreate the TTYG agent

The agent is Workbench state and is not in the export. The delivered demo agent is named
**`portfolio-final-v1-7`** (the maintainer's Workbench UUID is
`bfa836ca-3c91-409d-82e6-f506bfb22089`; a local recreation gets its own UUID) and holds
**instructions v1.7** ([`ttyg/instructions-v1.7.md`](ttyg/instructions-v1.7.md)). v1.7 is the demo
version; v1.5 ([`ttyg/instructions-v1.5.md`](ttyg/instructions-v1.5.md)) remains the evaluated
version. The evaluated agent `portfolio-final` is a different agent; do not replace it with this
demo recipe. Follow [`ttyg/create-agent.md`](ttyg/create-agent.md) exactly: SPARQL only, the
curated v2.1 CONSTRUCT, the single v1.7 instruction fence, temperature `0.1`, and the operator's
own `graphdb.llm.*` settings. The form requires a repository-manager account; after the agent
exists, the read-only user can use it.

## 4. Read-only user

Create a dedicated app user, for example `<READ_ONLY_USER>`, and grant **Read** on the `portfolio`
repository only (`READ_REPO_portfolio`). Do not give the app a repository-admin or maintainer role,
and do not put the maintainer's credentials in the app.

The app's GraphDB settings are the local values:

```text
KG_HOST=http://localhost:7200          # adjust to the local GraphDB
KG_REPOSITORY=portfolio
KG_USER=<READ_ONLY_USER>
KG_PASSWORD=<READ_ONLY_PASSWORD>
```

The password stays in the colleague's local, git-ignored `.env`; never commit it and never share it.

## 5. `portfolio-app`

Pin `portfolio-app` to **`<pinned version>`** (the maintainer fills this placeholder; do not invent a
version). Follow the app's own README for installation. Point it at the local GraphDB with the
read-only user above.

Set the app's chat timeout to **`KG_CHAT_TIMEOUT_SECONDS=300`**. The measured worst case on the
delivered graph was 37 s (120 s also works); 300 s is the conservative margin for a slower local
machine.

The app may also need an LLM key for its own features. The key is the colleague's own, stored only
in their local `.env` (and, for the GraphDB TTYG connector, in `graphdb.llm.api-key` or
`graphdb.llm.api-key@file`). It is never committed to this repository, never shared with the
maintainer or another user, and never pasted into an issue or chat.

## 6. First smoke questions

Ask the agent these in order. They exercise the run label, the date-ordered windows, the five
configurations, a concrete count, the weighting wording, the in-sample caveat and the two 2026-11-19
result facts:

| Question | Healthy answer |
|---|---|
| Which run labels does the graph have? | Only `final`; no `rule`, `candidate_y2` or `candidate`. |
| List the windows in calendar order. | `P1` 2022-01-03..2022-10-12, `H1` 2022-10-13..2023-10-26, `P3` 2023-10-27..2024-08-02, `H2` 2024-08-05..2025-02-18, `P2` 2025-02-19..2025-09-23, `H3` 2025-09-24..2026-10-15. `C1` (2022-01-03..2026-10-15) is an independent continuous run, not a seventh contiguous window. |
| Which five configurations does the graph have? | System with the Veto Hierarchy (`SYSTEM_WITH_HIERARCHY`, final book `TOPN_MV_GUARD`), System without the Veto Hierarchy (`SYSTEM_WITHOUT_HIERARCHY`), minimum variance (`MARKOWITZ_BASE`), mean-variance base Markowitz (`MARKOWITZ_MV`) and the SPY total-return reference (`SPY`). `:configuration` identifies the configuration; `:armCode` is engine provenance. |
| How many GUARD alerts does P1 have? | 271, all in the System with the Veto Hierarchy graphs; 0 in the other configurations. State the counting rule and the window. |
| What is the Sistema's weighting objective: minimum variance or minimum CVaR? | Minimum CVaR after a minimum-variance selection. `:objective "min_var"` is a fixed per-arm label for the selection stage, not the book weighting. |
| Is a reported performance figure definitive? | No: all loaded windows (the six calendar windows and C1) were seen during selection, so final performance is in-sample. |
| Are the backtest tests statistically significant? | 72 `:BacktestTest` rows; **0** have p ≤ 0.05, and the smallest is p = 0.077. There is no test between the two System configurations or against SPY/MARKOWITZ_MV. |
| Does the System beat SPY in return? | Over C1 it does not: the System returned **+38.8%** against SPY's **+73.1%**. Its value is risk control: its C1 maximum drawdown is **15.7%** against SPY's **24.5%**, and it is lower than SPY's in five of the six calendar windows (H2 is the exception). |

A healthy conversation has these properties:

- every backtest answer states the run label, window, configuration and dates used, and the
  counting rule;
- the answer shows exactly one SPARQL query, the one that decided it;
- performance answers say **in-sample**;
- the agent says "the graph does not have that data" instead of estimating a missing value;
- answers are at most 10 lines and use the language requested by the app's final line;
- no answer contains a per-asset price, per-asset daily return, Basing Points threshold or an
  invented figure.

### Sources for the smoke-table numbers

Every number above is either stated in a repository document or recorded by one of these read-only
queries against the delivered `portfolio` store (run 2026-11-20):

- the six window dates and C1's dates: [`ttyg/instructions-v1.7.md`](ttyg/instructions-v1.7.md),
  "Windows"; the five configurations: the same file, "Configurations".
- P1's 271 GUARD alerts (and the other windows):

  ```sparql
  PREFIX : <https://thesis.local/kg/portfolio#>
  SELECT ?window (COUNT(DISTINCT ?alert) AS ?alerts)
  WHERE {
    GRAPH ?graph { ?alert a :GuardAlert ; :windowId ?window }
    FILTER(STRSTARTS(STR(?graph), "urn:graph:derived:backtest:final:"))
  }
  GROUP BY ?window
  ORDER BY ?window
  # result: P1 271, H1 205, P3 125, H2 77, P2 103, H3 274, C1 2,084 (total 3,139);
  #         all in the SYSTEM_WITH_HIERARCHY graphs, none in the other configurations
  ```
- the 72 tests, 0 significant and smallest p = 0.077:

  ```sparql
  PREFIX : <https://thesis.local/kg/portfolio#>
  SELECT (COUNT(*) AS ?tests)
         (SUM(IF(?p <= 0.05, 1, 0)) AS ?significant)
         (MIN(?p) AS ?minP)
  WHERE { GRAPH ?g { ?t a :BacktestTest ; :pValue ?p } }
  # result: tests = 72, significant = 0, minP = 0.077
  ```

- the C1 return and drawdown comparison:

  ```sparql
  PREFIX : <https://thesis.local/kg/portfolio#>
  SELECT ?cum ?mdd WHERE {
    GRAPH ?g {
      ?s a :PortfolioPeriodSummary ; :summaryOfBook ?book ;
         :segment "C1" ; :cumulativeReturn ?cum ; :maxDrawdown ?mdd .
      ?book :configuration :Configuration_SystemWithHierarchy .
    }
  }
  # result: cum = 0.3878572942350562 (+38.8%), mdd = 0.15732741647140225 (15.7%)

  SELECT ?d ?v WHERE {
    GRAPH <urn:graph:derived:backtest:series:final:spy> {
      ?p a :DailySeriesPoint ; :windowId "C1" ; :seriesDate ?d ; :seriesValue ?v
    }
  } ORDER BY ?d
  # result: first 2022-01-03 = 1.0057899613640617,
  #         last 2026-10-15 = 1.7314818153304654.
  #         The series is normalised to 1.0 on the close before the window, so the return is
  #         1.7314818153304654 - 1 = +73.1%. Including that 1.0 base, the maximum drawdown over
  #         the 1,201 points is 24.5%.
  ```

  The six calendar rows use the same `:cumulativeReturn`/`:maxDrawdown` query on each `:segment`
  and SPY's `:referenceTotalReturn`/`:referenceMaxDrawdown` from `:ReferenceReturn`; the C1 row
  uses the series values above. The System's drawdown is lower in P1, H1, P3, P2 and H3, and
  higher in H2.

  | Segment | System return | SPY return | System max drawdown | SPY max drawdown |
  |---|---:|---:|---:|---:|
  | P1 | −15.7% | −24.1% | 15.7% | 24.5% |
  | H1 | +3.6% | +17.5% | 7.2% | 9.6% |
  | P3 | +20.0% | +30.5% | 5.1% | 5.7% |
  | H2 | +10.4% | +15.5% | 5.4% | 4.2% |
  | P2 | +5.6% | +9.4% | 4.5% | 18.8% |
  | H3 | +17.9% | +17.6% | 5.1% | 8.9% |
  | C1 | +38.8% | +73.1% | 15.7% | 24.5% |

If a smoke question fails, retry it once (two attempts per question). If it still fails, check the
repository label, the agent's instruction fence and the `graphdb.llm.*` model before changing
anything.

## 7. Live day (`portfolio_live`) — optional

The delivered final graph does not need this. A separate repository `portfolio_live` can hold one
live day at a time for the live product; its loader replaces three fixed graphs and never touches
`portfolio`, the `final` graphs or the TTYG agent. Setup, command, exit codes and checks are in
[`live-day-loader.md`](live-day-loader.md).

## 8. What not to do

- Do not import the export into a non-empty repository; it appends and can merge with stale graphs.
- Do not give the app write or admin credentials.
- Do not import `instances.trig`, the worked-example ABox, into the local production repository.
- Do not copy the maintainer's `.env`, credentials or LLM key.
- Do not treat `portfolio_test` as a delivered store.
