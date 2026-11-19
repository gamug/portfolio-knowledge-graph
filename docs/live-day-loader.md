# Live day loader — SYSTEM_LIVE (Work item 47)

This loader puts **one live day** of the Veto Hierarchy system into GraphDB. It is the last step of
the live operator: the operator exports a `graph_export/` folder for a day and runs this command.
Querying the graph is the person's job from the application; the operator only loads.

It is deliberately isolated from the evaluated delivery:

- it writes only the repository named by `--repository` (default `portfolio_live`) and refuses
  `portfolio` whatever `KG_REPOSITORY` says; it never creates or deletes a repository;
- it writes three fixed graphs and never touches the `final` graphs or anything the TTYG agent
  sees;
- it projects exactly like one final run of one configuration/one window through
  `projection.load_veto.build_delivery`: same manifest filters, same detail/selection projection,
  same `shapes.ttl`, same sibling context. Only the manifest adapter, the replace-per-day write and
  the exit/JSON contract are new.

The code is `src/projection/load_live.py`, `src/projection/live_manifest.py` and
`cli/load_live.py`. The operator handoff is `/workspaces/thesis/kg_handoff/load_live/` (a
self-contained snapshot of `src/` and `schema/`, so the operator container does not need the repo
checkout).

## 1. The fixed graphs

Every day replaces the same three graphs:

```text
urn:graph:derived:backtest:meta:live
urn:graph:derived:backtest:live:LIVE:system_live
urn:graph:derived:backtest:selection:live:LIVE:system_live
```

The write uses three staging graphs with the label `live_staging`, then one SPARQL Update with one
exact `MOVE <staging> TO <live>` per graph:

```text
urn:graph:derived:backtest:meta:live_staging
urn:graph:derived:backtest:live_staging:LIVE:system_live
urn:graph:derived:backtest:selection:live_staging:LIVE:system_live
```

One request is one GraphDB transaction. If anything fails before the swap, the previous day is
untouched and the staging graphs are dropped. Every `DROP`/`MOVE` names one exact graph IRI; the
loader never uses `DROP ALL`, `CLEAR ALL`, `DROP DEFAULT` or deletes a repository.

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

Run these from the repo checkout, with the live target exported. The `--to-production` flag here
means “schema only, no worked examples”; it is also required for the real `portfolio` repository.

```bash
set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_live
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db

uv run python cli/load_schema.py --to-production
uv run python cli/verify_store.py --to-production
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

If you prefer to copy instead of reloading, the read-only export/import is one graph at a time.
Only the four context graphs above (and optionally `urn:graph:reference:fibo`) are needed:

```bash
# read-only export from portfolio; repeat for each graph name
for graph in urn:graph:tbox urn:graph:reference urn:graph:reference:fibo \
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
them from the application. `build_delivery` uses the same `shapes.ttl`/`rules.ttl`/`reference.ttl`
and the same sibling-context logic as `cli/load_veto.py`.

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
| 2 | input/manifest/hash failure (folder `SHA256SUMS`, a `files_sha256` entry, `db_sha256`, `price_mask_sha256`, a manifest key/type, or `--day` ≠ manifest `day`) |
| 3 | SHACL failure; nothing was written |
| 4 | store/target failure (unreachable, refused repository, missing schema/context graph), or a staging failure before the swap; the previous day is intact |
| 5 | write/verify failure after the swap began; the message names the affected SYSTEM_LIVE graphs |

The last stdout line is always one JSON object, also on failure, and nothing is printed after it:

```json
{"day": "2026-11-17", "repository": "portfolio_live", "graphs": 3, "triples": 229375, "shacl": "conforms", "ok": true}
```

On failure it carries `"ok": false` and `"error"`, and `"shacl"` is `"fails"` (SHACL stopped the
load) or `"not_run"` (a check before SHACL). The JSON never contains a credential.

## 5. Re-running a day and checking the result

Re-run the same command; the three graphs are replaced, not appended. Loading the same day twice
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

The three live graphs must have the counts the loader printed; no `live_staging` graph may remain.
The loaded day is the `:knowledgeDate` of the metadata graph's `:BacktestRun`:

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?run ?window ?runId ?knowledge ?file
WHERE {
  GRAPH <urn:graph:derived:backtest:meta:live> {
    ?run a :BacktestRun ; :windowId ?window ; :backtestRunId ?runId ;
         :knowledgeDate ?knowledge ; :sourceFile ?file .
  }
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
6. the whole projected batch against the same shapes and sibling context as the veto loader;
7. the target repository exists, is not `portfolio`, and holds the context graphs above.

After the swap it verifies the per-graph triple counts, that no staging graph is left, and that no
asset in the Tiingo mask carries a price.

The 33 masked assets of `tiingo_assets.csv` get no price or valuation: the loader checks the
projected batch and the stored live graphs for `:alertValue`, `:alertThreshold`,
`:stopDistancePct`, `:closePrice` and `:dailyReturn` on those assets (or on an alert/veto/snapshot
linked to them) and refuses the load if any appears.
