# Live day loader — SYSTEM_LIVE (Work item 47)

This loader puts **one live day** of the Veto Hierarchy system into GraphDB. It is the last step of
the live operator: the operator exports a `graph_export/` folder for a day and runs this command.
Querying the graph is the person's job from the application; the operator only loads.

It is deliberately isolated from the evaluated delivery:

- it writes only the repository named by `--repository` (default `portfolio_live`) and refuses
  `portfolio` whatever `KG_REPOSITORY` says; it never creates or deletes a repository;
- it writes six fixed graphs of `portfolio_live` and never touches the `final` graphs or anything
  the final TTYG agent (repository `portfolio`) sees;
- it projects exactly like one final run of one configuration/one window through
  `projection.load_veto.build_delivery`: same manifest filters, same detail/selection projection,
  same `shapes.ttl`, same sibling context. Only the manifest adapter, the replace-per-day write and
  the exit/JSON contract are new.

The code is `src/projection/load_live.py`, `src/projection/live_manifest.py` and
`cli/load_live.py`. The operator handoff is `/workspaces/thesis/kg_handoff/load_live/` (a
self-contained snapshot of `src/` and `schema/`, so the operator container does not need the repo
checkout).

## 1. The fixed graphs

Every day replaces the same six graphs (the last three since Work item 50):

```text
urn:graph:derived:backtest:meta:live
urn:graph:derived:backtest:live:LIVE:system_live
urn:graph:derived:backtest:selection:live:LIVE:system_live
urn:graph:derived:news:live:LIVE                      # news rows (:NewsItem)
urn:graph:derived:backtest:agents:live:LIVE:news      # news GUARD: levels B/C/D, actions, evidence
urn:graph:derived:backtest:series:live:spy            # SPY daily series (:DailySeriesPoint)
```

The last three are filled only when the day's export brings the optional files of §1bis; on a day
without them they are empty, and the swap empties them in the store so no previous day's rows
survive.

The write stages every non-empty graph under the label `live_staging`, then sends one SPARQL Update
with one exact `MOVE <staging> TO <live>` per non-empty graph and one exact
`DROP SILENT GRAPH <live>` per empty one:

```text
urn:graph:derived:backtest:meta:live_staging
urn:graph:derived:backtest:live_staging:LIVE:system_live
urn:graph:derived:backtest:selection:live_staging:LIVE:system_live
urn:graph:derived:news:live_staging:LIVE
urn:graph:derived:backtest:agents:live_staging:LIVE:news
urn:graph:derived:backtest:series:live_staging:spy
```

One request is one GraphDB transaction. If anything fails before the swap, the previous day is
untouched and the staging graphs are dropped. Every `DROP`/`MOVE` names one exact graph IRI; the
loader never uses `DROP ALL`, `CLEAR ALL`, `DROP DEFAULT` or deletes a repository.

## 1bis. The optional news rows and SPY series (Work item 50)

Both follow the final delivery's formats and both are optional, independently:

| Manifest key | Value | Content |
|---|---|---|
| `news_rows_file` | object `{file, sha256, rows, model_revision, columns}` (optional `readme`) | `news/news_rows.jsonl`: the block D rows, one JSON object per line, the same 24 columns in the same order as the final delivery |
| `spy_series_file` | string, path relative to the day's folder | `series_diarias_referencia/spy_daily.csv`: `window,date,daily_total_return,value`; `window` is `LIVE`; one row per session from the formation to the day, both included |

Rules the loader enforces before anything is written (exit 2 otherwise):

- each file is inside the day's folder, listed in the folder's `SHA256SUMS` with its relative path
  (`news/news_rows.jsonl`, `series_diarias_referencia/spy_daily.csv`) and named in `files_sha256`
  (`"news_rows_file"`, `"spy_series_file"`); `news_rows_file.sha256` equals the `SHA256SUMS` entry;
- the news rows pass the final loader's parser (`projection.news.parse_rows`): key and types,
  `rows` equal to the line count, one `model_revision`;
- every row cited by a `test_rows` entry of the day's `news.json` (`news_actions_file`) is in the
  news rows. The news rows of a day are every row the news actions cite plus every row, of every
  ticker, dated from the first session of the evidence window of the first decision in `news.json`
  (`dates[0].window[0]`) to the day; the base window is not needed;
- the SPY series runs from the formation to the day, and its dates are exactly the book's
  `:performanceDate` sessions. Its `value` is SPY's total-return index normalised to 1.0 at the close
  of the session before the formation, the same base as the book's `:nav`, so the two compare on
  the same date.

What the loader projects, with the final delivery's own projectors (no fork):

- `urn:graph:derived:news:live:LIVE` — one `:NewsItem` per `(item_kind, item_id, ticker)`, linked to
  its `:Asset` when the universe database resolves the ticker (`projection.news`);
- `urn:graph:derived:backtest:agents:live:LIVE:news` — from `news.json`, already in every live
  export: the `:NewsRunRecord` (level-B news exits, level-C sector rejections), one `:DateRecord` per
  news decision date with the B/C/D levels in force and the filter flags, and each pool
  `:NewsAction` (veto or promotion) with its `:NewsEvidence`, whose `:newsItem` links name the news
  rows behind it (`projection.agents`, with `SYSTEM_LIVE` as the configuration). It is projected only
  when the day brings its news rows, because every evidence row must resolve;
- `urn:graph:derived:backtest:series:live:spy` — one `:DailySeriesPoint` per session
  (`:Configuration_SPY`, `:windowId "LIVE"`, `:dailyTotalReturn`, `:seriesValue`).

Each graph is checked by the gate's own shape check beside the disk universe in the dry run, and
again when it is staged.

## 2. One-time setup (the USER does this)

### 2.1 Create `portfolio_live`

Create the repository in GraphDB with the same ruleset as `portfolio`. The repository config is
[`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl): copy it, change
`rep:repositoryID "portfolio"` to `rep:repositoryID "portfolio_live"`, and upload it (Workbench →
Setup → Repositories → Create → upload RDF config). The relevant profile is unchanged:

| Setting | Value |
|---|---|
| `graphdb:ruleset` | `rdfsplus-optimized` |
| `graphdb:disable-sameAs` | `true` |
| `graphdb:check-for-inconsistencies` | `false` |

The loader never creates the repository. If it does not exist, the run exits 4.

### 2.2 Load the schema and the universe catalog

Run these from the repo checkout, with the live target exported. `load_schema --to-production`
loads the schema graphs only, with no worked examples; its closing line
`verified: 5 graphs, 12213 asserted triples match the local parse` is the check. Do **not** run
`cli/verify_store.py --to-production` against `portfolio_live`: for any repository not named
`portfolio` it expects the worked-example graphs of `instances.trig` and reports two false FAILs
(`src/kg_store/acceptance.py:154`).

```bash
set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_live
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db

uv run python cli/load_schema.py --to-production
uv run python cli/load_universe.py --as-of 2026-11-09 --write
```

`load_universe` writes `urn:graph:universe:2026-Q4` (the same catalog graph the final delivery
uses): 643 `:Asset` individuals, their CIKs and membership stints. Re-running it is refused because
the quarter graph exists, which is the intended append-only behaviour.

### 2.3 Exactly which graphs the live batch needs

The loader checks these before staging (exit 4 if any is absent or empty):

| Graph | Why |
|---|---|
| `urn:graph:tbox` | classes, properties and the six `:BacktestConfiguration` individuals (including `:Configuration_SystemLive`); `load_schema` also puts `shapes.ttl` here |
| `urn:graph:reference` | `schema/reference.ttl` assets (SPY and the worked examples) the batch links by ticker |
| `urn:graph:rules:catalog` | the GUARD `:RuleDefinition` individuals the alerts/vetoes point at |
| `urn:graph:universe:2026-Q4` (or another non-empty `urn:graph:universe:*`) | every referenced `:Asset`, its `:tickerSymbol`, `:cikNumber` and membership stints |

Not needed: `urn:graph:labels`, `urn:graph:reference:fibo`, `urn:graph:derived:fundamentals:final`,
`urn:graph:portfolio:current`, and every `urn:graph:derived:backtest:*` graph of the final
delivery. Do not copy the final backtest graphs into `portfolio_live`.

The delivered final export's `urn:graph:tbox` predates `:Configuration_SystemLive` (it entered with
commit `db96068`). **Never copy `urn:graph:tbox` (or the shapes) from `portfolio`**;
`portfolio_live` must always get its schema from `load_schema` run from a clone of this repository
at a commit that contains the live loader. Only the other context graphs may be copied. Whoever
imported the final TriG must still do §2.2 from such a clone.

If you prefer to copy instead of reloading, the read-only export/import is one graph at a time.
Only the other context graphs (and optionally `urn:graph:reference:fibo`) may be copied; never the
tbox or the shapes:

```bash
# read-only export from portfolio; repeat for each graph name
for graph in urn:graph:reference urn:graph:reference:fibo \
             urn:graph:rules:catalog urn:graph:universe:2026-Q4; do
  name=$(printf '%s' "$graph" | tr ':/' '__')
  curl -fsS -u "$KG_USER:$KG_PASSWORD" \
    --get --data-urlencode "context=<$graph>" \
    -H 'Accept: application/n-triples' \
    "$KG_HOST/repositories/portfolio/statements" > "$name.nt"
  encoded=$(printf '%s' "<$graph>" | sed 's/</%3C/g; s/>/%3E/g')
  curl -fsS -u "$KG_USER:$KG_PASSWORD" -X POST \
    -H 'Content-Type: application/n-triples' \
    --data-binary "@$name.nt" \
    "$KG_HOST/repositories/portfolio_live/statements?context=$encoded"
done
```

The SHACL validation itself uses the local universe database (`SQL_UNIVERSE_DB`, default
`/workspaces/thesis/data/universe_history_gics.db` when present), exactly as the final dry run
does; the store graphs are checked because the written graph points at them and a person queries
them from the application. The database precedence is `--assets-db`, then `SQL_UNIVERSE_DB` (as
read by `etl.config.universe_db_path`), then the bundled default only when neither is set. `build_delivery` uses the same `shapes.ttl`/`rules.ttl`/`reference.ttl`
and the same sibling-context logic as `cli/load_veto.py`.

### 2.4 A company that entered the S&P 500 after the universe catalog

Assets are resolved at load time from the `SQL_UNIVERSE_DB` file (`universe_assets` in
`src/projection/backtest.py`), not from the store. The store's `urn:graph:universe:*` graph is only
checked for being non-empty (`_check_context` in `src/projection/load_live.py`).

If the database does not know the symbol, the projector omits that `:Asset` link and counts it as
`asset link omitted` (`src/projection/backtest.py`, `tests/test_backtest.py`). A row whose shape
requires the link — `:StopEvent :stoppedAsset`, `:DestinationOption :optionAsset` or
`:FormationTarget :targetAsset` — then fails SHACL: the loader exits **3**, its JSON line reports
`"shacl": "fails"`, and the error is `SHACL failed for LIVE/SYSTEM_LIVE:` followed by the shape
report; nothing is written (`src/projection/load_live.py`, `src/projection/load_veto.py`). If the
symbol appears only in rows with an optional asset link (for example `:BookWeightDaily` or
`:GuardAlert`), the load can still conform; check the omitted-link counts in the projection output.

If the database has the symbol, the load works, but that `:Asset` is absent from the store's
universe graph. `load_universe` refuses to write the same quarter graph twice, so the supported
procedure is to ship a universe database updated through the live day (the operator uses
`scratch/live/data/universe_live.db`) and point `SQL_UNIVERSE_DB` at it. This is **not tested end
to end**.

## 3. The command

The input is the operator's `graph_export/` folder and the day. The day must equal
`manifest_live.json`'s `day`.

```bash
# default: dry run — hashes, projection and SHACL; no store is contacted
uv run python cli/load_live.py \
  --folder /workspaces/thesis/scratch/live/final_run/2026-11-17/graph_export \
  --day 2026-11-17

# read-only store pre-flight: repository/context checks and the gate plan
KG_REPOSITORY=portfolio_live uv run python cli/load_live.py \
  --folder /workspaces/thesis/scratch/live/final_run/2026-11-17/graph_export \
  --day 2026-11-17 --check-store

# the real write
KG_REPOSITORY=portfolio_live uv run python cli/load_live.py \
  --folder /workspaces/thesis/scratch/live/final_run/2026-11-17/graph_export \
  --day 2026-11-17 --write
```

The target repository defaults to `portfolio_live`; `--repository` changes it (for a scratch
repository). `KG_REPOSITORY` never overrides it, and `portfolio` is always refused. Host and
credentials come only from `KG_HOST`, `KG_USER` and `KG_PASSWORD` (or the repo `.env`), never from
the command line.

The operator handoff runs from `/workspaces/thesis`:

```bash
uv run kg_handoff/load_live/load_live.py \
  --folder {folder} --day {day} --write
```

The exact `graph_load_command` list is:

```json
["uv", "run", "kg_handoff/load_live/load_live.py", "--folder", "{folder}", "--day", "{day}", "--write"]
```

## 4. Exit codes and the JSON line

| Exit | Meaning |
|---|---|
| 0 | success (dry run, pre-flight, or the swap and its verification) |
| 2 | input/manifest/hash failure (folder `SHA256SUMS`, a `files_sha256` entry, `db_sha256`, `price_mask_sha256`, a manifest key/type, `--day` ≠ manifest `day`), or a news-row/SPY rule of §1bis |
| 3 | SHACL failure; nothing was written |
| 4 | store/target failure (unreachable, refused repository, missing schema/context graph), or a staging failure before the swap; the previous day is intact |
| 5 | write/verify failure after the swap began; the message names the affected SYSTEM_LIVE graphs |

The last stdout line is always one JSON object, also on failure, and nothing is printed after it:

```json
{"day": "2026-11-17", "repository": "portfolio_live", "graphs": 3, "triples": 229375, "shacl": "conforms", "ok": true}
```

`"graphs"` counts the live graphs that hold triples after the load: 3 on a day without the optional
files, 6 on a day with both news rows and the SPY series. `"triples"` is their sum.

On failure it carries `"ok": false` and `"error"`, and `"shacl"` is `"fails"` (SHACL stopped the
load) or `"not_run"` (a check before SHACL). The JSON never contains a credential.

## 5. Re-running a day and checking the result

Re-run the same command; the six graphs are replaced, not appended. Loading the same day twice
gives the same graphs (same triple counts and an order-independent hash). Loading D+1 leaves only
D+1's state, because the engine re-runs the LIVE window from the formation to D+1.

Check the stored state (read-only):

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
FROM <http://www.ontotext.com/explicit>
WHERE { GRAPH ?graph { ?s ?p ?o } }
GROUP BY ?graph
ORDER BY ?graph
```

The live graphs must have the counts the loader printed (an empty news or SPY graph does not appear
in the result); no `live_staging` graph may remain.
The loaded day is the `:dateTo` of the live `:PortfolioPeriodSummary` (`:segment "LIVE"`), not the
`:knowledgeDate` of the metadata `:BacktestRun`: that date is when the run was created.

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?book ?loadedDay ?dateFrom ?dateTo
WHERE {
  GRAPH <urn:graph:derived:backtest:live:LIVE:system_live> {
    ?book a :StrategyBook ; :runLabel "live" ; :windowId "LIVE" .
    ?summary a :PortfolioPeriodSummary ; :summaryOfBook ?book ; :segment "LIVE" ;
             :dateFrom ?dateFrom ; :dateTo ?dateTo .
  }
  BIND (?dateTo AS ?loadedDay)
}
```

To roll back, re-run the previous day's folder with `--write`. The loader does not keep a copy of
the previous day: the operator's `graph_export/` folders are the source of truth. If a run exits 5,
the JSON error names the live graphs that were being swapped; re-run the last known-good day.

## 6. What the loader verifies before writing

1. the folder's `SHA256SUMS` (every listed file, including `manifest_live.json`);
2. every `files_sha256` entry, cross-checked against `SHA256SUMS`;
3. `db_file` exists and its streamed SHA-256 equals `db_sha256` (the ~3 GB database is never
   copied);
4. `price_mask_file` exists and its SHA-256 equals `price_mask_sha256`;
5. the manifest keys/types, `configuration == "SYSTEM_LIVE"`, `window == "LIVE"`, and
   `day >= formation`;
6. the whole projected batch against the same shapes and sibling context as the veto loader, and
   each news/SPY graph against the gate's shapes beside the disk universe (the news-actions graph
   beside the day's news rows); the §1bis rules;
7. the target repository exists, is not `portfolio`, and holds the context graphs above.

After the swap it verifies the per-graph triple counts, that no staging graph is left, and that no
asset in the Tiingo mask carries a price.

The 33 masked assets of `tiingo_assets.csv` get no price or valuation: the loader checks the
projected batch and the stored live graphs for `:alertValue`, `:alertThreshold`,
`:stopDistancePct`, `:closePrice` and `:dailyReturn` on those assets (or on an alert/veto/snapshot
linked to them) and refuses the load if any appears.
