# Final delivery — production sequence for label `final`

This is the maintainer-run, end-to-end sequence that turns the current GraphDB installation into the
delivered store: one repository named `portfolio`, one run label `final`, loaded from
`/workspaces/thesis/scratch/final/final_corregida` (`code_commit` 5958c6b, PR 195). `portfolio_test`
is only the rehearsal repository; it is never delivered. The Talk to Your Graph agent is Workbench
state, not graph data: recreate it with [`ttyg/create-agent.md`](ttyg/create-agent.md). The
colleague's local copy of the store and its app is [`second-user-setup.md`](second-user-setup.md).

Everything is read-only unless a step says **write**. The agent never runs a `DROP`: the maintainer
reviews the listing, takes the backup and runs the one-graph statements. Never delete the
repository: the TTYG agents and the ruleset live in GraphDB, not in the exported graph.

**Live day (SYSTEM_LIVE) is separate and out of this sequence.** Its loader writes three fixed
graphs in `portfolio_live`, never in `portfolio`, and never touches the `final` graphs or the TTYG
agent. Setup, command, exit codes and checks: [`live-day-loader.md`](live-day-loader.md).

## 0bis. Work item 46 reload — exact order for 18–19 November 2026

**This section supersedes §3–§8 for the Veto Hierarchy delivery; the older six-window sequence
remains for the legacy `rule` family.** The agent never runs a write, a `DROP`, a schema load or a
backup restore: every command below is for the maintainer after reviewing the listing and the
backup. The new loader is `cli/load_veto.py`; it refuses a non-empty target and never drops.

### 0bis.1 Rehearse on `portfolio_test` first (read-only dry run)

Use the pilot DB and a **draft** manifest (PENDIENTE control counts, real pilot hashes). A draft is
accepted only for a dry run or a scratch repository:

Source `.env` first, then export the scratch target: sourcing it after an export would override
`KG_REPOSITORY` with the production value.

```bash
set -a; . ./.env; set +a
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
export KG_REPOSITORY=portfolio_test
uv run python cli/load_veto.py --manifest /path/to/pilot/manifest_final.json
```

The dry run verifies every hash, filters the manifest books, projects meta + m018 + detail +
selection, SHACL-validates each configuration/window and prints one line per graph. It contacts no
store. For the read-only pre-flight against the scratch store:

```bash
export KG_REPOSITORY=portfolio_test
uv run python cli/load_veto.py --manifest /path/to/pilot/manifest_final.json --check-store
```

`--check-store` needs no `--to-production` even when the target is production; it only plans.

### 0bis.2 Backup the NEW production TriG first

Run the read-only export of §1 exactly as written and keep `SHA256SUMS`; do not proceed until
`sha256sum -c` passes. The export is the rollback (plan B) and must include every graph, including
the schema and `urn:graph:derived:fundamentals:final`.

### 0bis.3 List the graphs and DROP the old `final` family, one graph at a time

Generate the exact list (read-only):

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
FROM <http://www.ontotext.com/explicit>
WHERE { GRAPH ?graph { ?s ?p ?o } }
GROUP BY ?graph
ORDER BY ?graph
```

The old family is the run-id named one, not the new configuration-keyed one. Review these exact
IRIs in the listing before running any of them:

```text
urn:graph:derived:backtest:final:P1:1
urn:graph:derived:backtest:final:H1:1
urn:graph:derived:backtest:final:P3:1
urn:graph:derived:backtest:final:H2:1
urn:graph:derived:backtest:final:P2:1
urn:graph:derived:backtest:final:H3:1
urn:graph:derived:backtest:selection:final:P1:1
urn:graph:derived:backtest:selection:final:H1:1
urn:graph:derived:backtest:selection:final:P3:1
urn:graph:derived:backtest:selection:final:H2:1
urn:graph:derived:backtest:selection:final:P2:1
urn:graph:derived:backtest:selection:final:H3:1
urn:graph:derived:backtest:meta:final
urn:graph:derived:backtest:aggregates:final
urn:graph:derived:backtest:external:final
```

Drop one exact IRI per request (repeat per graph; never `CLEAR ALL`, `DROP ALL`, `DROP DEFAULT` or
a repository delete):

```bash
curl -fsS -u "$KG_USER:$KG_PASSWORD" -X POST \
  -H 'Content-Type: application/sparql-update' \
  --data-binary 'DROP GRAPH <urn:graph:derived:backtest:final:P1:1>' \
  "$KG_HOST/repositories/portfolio/statements"
```

After the drops, rerun the listing and confirm that no old run-id `final` graph remains. The new
`final:P1:system_with_hierarchy` family must not exist yet; if it does, stop and restore the backup.

### 0bis.4 Load the schema only after the DROP

```bash
KG_REPOSITORY=portfolio uv run python cli/load_schema.py --to-production
KG_REPOSITORY=portfolio uv run python cli/verify_store.py --to-production
```

The new `rules.ttl` removes `L1_STOP_LOSS`, `L1_REENTRY`, `L2_NEWS`, `L3_VOL` and `L4_DD`; loading
it before the old `final` graphs are gone would leave their alerts pointing at removed rules.

### 0bis.5 Load the manifest runs

```bash
# dry run first; inspect every graph and the per-graph triple counts
uv run python cli/load_veto.py --manifest /path/to/final/manifest_final.json
# read-only pre-flight against the target store
KG_REPOSITORY=portfolio uv run python cli/load_veto.py \
  --manifest /path/to/final/manifest_final.json --check-store
# production write, after the maintainer's go-ahead
KG_REPOSITORY=portfolio uv run python cli/load_veto.py \
  --manifest /path/to/final/manifest_final.json --write --to-production
```

The write is append-only and refuses a target graph that already holds triples. It writes the meta
graph, then each m018/detail graph and its selection sibling, one graph at a time, and prints the
written list. A failure stops and lists what was already written; no graph is dropped. The
read-only pre-flight validates each m018 graph beside its sibling selection graph as context (and
the reverse); that context is never written.

The detail loader derives `not_ranked` stop-memory releases from the run's `rankings_file` (the
manifest hash is already verified). At every decision date it enforces the control rule: the assets
in memory (including stops of that close) must split exactly into price releases, ranking releases
and `L1_BP_STOP_BLOCKED` rows. A mismatch stops the load with the date and assets; it is never
adjusted. The pilot reconciles on all ten decision dates (0 ranking releases).

A blocked asset with no open memory episode opens a `decision_close` episode at that date (the engine
writes no stop record); its count is not hard-coded. A final manifest must carry the full
`control_counts` object; the loader computes every key and compares it, including
`control_counts.<configuration>.<window>.decision_close_episodes` and stops with configuration,
window, expected and computed on a mismatch. A draft may omit `control_counts` (the loader prints
"control counts not provided" and continues), but any key it does carry is compared. Ranking
releases use every row of the ranking file, including vetoed rows. The loader fails clearly if a
final System run lacks its `rankings_file`/`scales_file` or the manifest hash differs.

**Declared limitation:** if an asset stops on the close of a decision date and is already out of
that same decision's ranking, the engine releases it from memory with no record; it cannot be
detected from the files and is not represented in the graph.

### 0bis.6 MARKOWITZ_MV, fundamentals and aggregates

**For the final-1 delivery use §0quater instead of this subsection's `--engine-dir` path:** the
final `mv_base/` has only `aggregates_mv_base.json`, and the exact engine-directory decision is
T-895. The command below is the older `final_corregida` rehearsal form and is kept for history.

The external MARKOWITZ_MV statistics depend on the new engine run ids; point `--engine-dir` at the
new engine folder (default is the old scratch folder and must not be relied on):

```bash
KG_REPOSITORY=portfolio uv run python cli/load_mv_base.py --label final \
  --dir "/workspaces/thesis/knoledge graph/mv_base" \
  --engine-dir "/workspaces/thesis/scratch/final/final_corregida" \
  --write --to-production
```

Fundamentals is **untouched** by this reload: do not reload
`urn:graph:derived:fundamentals:final`; verify it exists in the backup/listing. Aggregates are
loaded after the runs:

```bash
KG_REPOSITORY=portfolio uv run python cli/load_aggregates.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-17_final" --write --to-production
```

The block D news rows are independent of the backtest graphs and load after the runs (see §7e for
the full dry-run/pre-flight/write sequence):

```bash
KG_REPOSITORY=portfolio uv run python cli/load_news.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-17_final" --write --to-production
```

### 0bis.7 Verify, test, decide and roll back

```bash
KG_REPOSITORY=portfolio uv run python cli/verify_store.py \
  --to-production --manifest /path/to/final/manifest_final.json
uv run pytest -q
```

`verify_store --manifest` re-projects the manifest read-only and checks every stored graph count,
the control counts (including the three memory-release totals derived from `StopMemory`), the
removed-rule stop and the price mask. The decision point is after the
verification and the full suite: if either fails, stop and restore the backup; if both pass, the
delivery is accepted. Plan B is the §0bis.2 TriG backup. Restore only after a deliberate decision,
into an emptied repository or with Workbench **Import**; a large single POST can time out (see §1).

## 0quater. Final delivery 2026-11-17 — manifest, load order and what is not loaded

The final delivery is the read-only folder
`/workspaces/thesis/knoledge graph/2026-11-17_final/`. Its manifest is
`/workspaces/thesis/knoledge graph/2026-11-17_final/manifest_final.json`
(`manifest_version` `final-1`, status `FINAL`, label `final`), with **35 keys** (five
configurations × seven windows), the top-level `news_rows_file` block, the per-run
`bull_mode_file`, `manager_calls_file`, `narrator_file` and `news_actions_file`, and the
`SHA256SUMS` file next to it. The top-level `bull_mode_file` is a note (`"por corrida:
configurations[].runs[].bull_mode_file"`); the actual per-run file is the run key. The delivery
is never copied; all commands read it in place.

Set the target once, in this order (sourcing `.env` after the exports would overwrite
`KG_REPOSITORY`):

```bash
set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
```

The load order for a clean `portfolio_test` is:

```bash
# 1. Schema (the 5 graphs; verify_store --manifest later checks the backtest family)
uv run python cli/load_schema.py
uv run python cli/verify_store.py

# 2. Universe and reference catalog
uv run python cli/load_universe.py --as-of 2026-11-09 --write

# 3. Fundamentals (block C). The production reload does not repeat this graph; a clean
#    portfolio_test needs it, and the manifest price mask is the same Tiingo mask.
uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db "$SQL_UNIVERSE_DB" --write

# 4. Veto Hierarchy backtests (meta, m018/detail, selection)
uv run python cli/load_veto.py \
  --manifest "/workspaces/thesis/knoledge graph/2026-11-17_final/manifest_final.json"
uv run python cli/load_veto.py \
  --manifest "/workspaces/thesis/knoledge graph/2026-11-17_final/manifest_final.json" \
  --check-store
# write only after the maintainer's go-ahead, and only on the target chosen above:
# uv run python cli/load_veto.py --manifest ".../manifest_final.json" --write

# 5. External Markowitz mean-variance summary (see the path note below)
uv run python cli/load_mv_base.py --label final \
  --dir "/workspaces/thesis/knoledge graph/mv_base"

# 6. Aggregates from the delivery root (61 rows, news_risk_off included)
uv run python cli/load_aggregates.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-17_final" --write

# 7. Series (SPY and MARKOWITZ_MV); point at the series subfolder, not the delivery root
uv run python cli/load_series.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-17_final/series_diarias_referencia" --write
```

**Aggregates source check (T-896, fixed 2026-11-16).** The corrected delivery has
`aggregates_final.json` SHA-256 `b2cc35dc1b7e6b4a9169d9437d4d992aaeb9478fdbb37f976d5c0ffc39aabaaa`,
`trend_filter_applies_to_arms: ["TOPN_MV_GUARD"]`, 61 rows with the boolean `news_risk_off` and
`cash_fraction` 0.5 when the price input is `below` or the news input is on. The loader accepts the
root `SHA256SUMS` with nested paths and finds the one database per
`SYSTEM_WITH_HIERARCHY/<window>/` folder. T-896 is done; the aggregate graph is loadable. If an
older `urn:graph:derived:backtest:aggregates:final` is already in the target, `--check-store`
reports the old arm/source hash and `--write` refuses the non-empty graph: drop that one exact IRI
after the backup, then run the write. The `load_aggregates` command in the sequence above is the
write only after its dry run and `--check-store` pass.

**Markowitz MV and `--engine-dir`.** The delivery's `mv_base/` contains only
`aggregates_mv_base.json`; it does not contain `config_mv_base.md`, `SHA256SUMS` or the
`final_<window>.db` files that `cli/load_mv_base.py` reads. Do not point `--engine-dir` at
`2026-11-17_final/mv_base` and expect it to work: the loader's engine directory must contain
`final_P1.db` … `final_C1.db`. The production runbook must either stage symlinks to the final
engine databases (for example `final_P1.db -> SYSTEM_WITH_HIERARCHY/P1/H1B-A2g-P1.db`, whose
book 1 is `MARKOWITZ_BASE`) or receive a corrected mv_base folder from the maintainer. This is a
delivery-path decision, not a graph/schema decision; it is listed as an open item in TASKS.md
T-895.

### 0quater.1 New `control_counts` definitions (final-1)

All of these are computed from the files, compared exactly with the manifest, and only for
`SYSTEM_WITH_HIERARCHY` (the other configurations have no manager/narrator/news/bull files):

| Key | Definition |
|---|---|
| `manager_calls` | lines of `manager_calls_file` |
| `manager_fallbacks` | calls whose `fallback.cause` is not null |
| `manager_repairs` | calls whose `repair_used` is true |
| `narrator_texts` | lines of `narrator_file` |
| `news_pool_actions` | object `{veto, promotion}` counted from the `actions` list of `*.news.json` |
| `news_date_records` | length of the `dates` list of `*.news.json` |
| `news_level_c_decisions` | decisions whose `levels_v2.decisions[].c_flags` (or `c_flagged`) is non-empty |
| `news_level_d_decisions` | decisions whose `levels_v2.decisions[].d_fired` is true |
| `news_exits` | stops in the JSON-lines whose `trigger` is `news_shock`; these are the `L1_BP_STOP` alerts that are news exits, not price stops |
| `news_sector_rejections` | sum of every stop's `eligible_counts.news_sector` (the level C sector rejections) |
| `bull_triggered` | decisions in `bull_mode.json` whose `triggered` is true |

The same new stop fields are accepted by the detail parser and **not projected**:
`trigger`, `news_neg3`, `news_pos3`, `news_threshold`, `sector_limit_changes`, the
`portfolio_check.fallback`/`fallback_reasons`, and the `weight_after_e3` on a replacement. The
cash entry in a stop menu is also accepted and skipped. `news_sector` and `PORTFOLIO_CHECK` are
accepted in `eligible_counts` and skipped because there is no schema property yet. `verify_store
--manifest` prints these keys as `not store-verifiable: not loaded yet` and does **not** fail:
`manager_calls`, `manager_fallbacks`, `manager_repairs`, `narrator_texts`, `news_pool_actions`,
`news_date_records`, `news_level_c_decisions`, `news_level_d_decisions`, `news_exits`,
`news_sector_rejections` and `bull_triggered`.

A manifest/file mismatch in any of these counts **is** a failure: `build_delivery` computes the
value from the file before it contacts a store. A missing `news_rows_file` hash, a per-run
manager/narrator/news/bull hash or an unknown new manifest key also stops the load.

### 0quater.2 Not loaded yet (later PR)

The following final-delivery data is deliberately outside this PR and is not in the graph:

- `manager_calls_file` (`:ManagerCall`) and `narrator_file` (`:NarratorText`);
- `news_actions_file` (`:NewsAction`, pool actions, date records, evidence) and the NLP
  `news/news_rows.jsonl` rows (`:NewsItem`);
- `bull_mode.json` records;
- the cash entry of a stop menu (no `DestinationOption` property for cash) and the
  `news_sector`/`PORTFOLIO_CHECK` rejection counts (no schema property yet).

Those files are still hash-verified and parsed for the counts above. The later PR decides the
classes/properties and the `SHACL` shapes. The store check still compares every control count
exactly: `destination_options` in the manifest counts every menu entry, including cash, while the
graph intentionally holds only the non-cash `DestinationOption` individuals (cash is
`:chosenCash`). `verify_store_control_counts` subtracts the number of cash entries parsed from the
same delivery JSON-lines before comparing, so this is an exact check, not a waiver.

### 0quater.3 Large graphs and write batching

`load_veto` writes every graph through `gate.write_batched` in 20,000-triple chunks. The client
timeout is 120 s; a lost answer leaves that graph **in doubt** and the loader stops without
retrying. In the final delivery the following graphs exceed 300,000 triples and must be treated
as multi-request writes: all System selection graphs except H2 (P1/H1/P3/P2/H3/C1 for both
System configurations), `SYSTEM_WITH_HIERARCHY` C1 m018, `SYSTEM_WITHOUT_HIERARCHY` C1 m018 and
`MARKOWITZ_BASE` C1 m018. The dry-run prints the count and the `>300,000` flag per graph.

## 0ter. Rehearsal kit — scratch `portfolio_test` with the P1 pilot

**The manifest is outside the repository** at
`/workspaces/thesis/scratch/rehearsal/manifest_pilot_draft.json`. It is a `BORRADOR` with the real
pilot hashes (DB, JSON-lines, rankings, scales and mask) and Reviewer A's real `control_counts` for
`SYSTEM_WITH_HIERARCHY`/P1 and `MARKOWITZ_BASE`/P1 from
`18b_A_control_counts_piloto_P1.json`. The other configurations are present as draft entries without
control counts; the loader prints "control counts not provided" for them.

To regenerate it: copy `H1C-B5-P1.db`, `H1C-B5-P1.cartera_v1_3.kg.jsonl`,
`H1C-B5-P1.rankings.json`, `H1C-B5-P1.scales.json` and the Tiingo mask into
`/workspaces/thesis/scratch/rehearsal/`, hash each file into the manifest, set `status` to a
`BORRADOR...` string, and copy the `control_counts` object verbatim from A's JSON. The manifest is
draft-only; never use it for production.

### 0ter.1 Empty `portfolio_test` safely

Set the target and list every graph (read-only):

Source `.env` first, then export the scratch target; the reverse order lets `.env` overwrite
`KG_REPOSITORY`.

```bash
set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db

curl -fsS -u "$KG_USER:$KG_PASSWORD" -H 'Accept: application/sparql-results+json' \
  --data-urlencode 'query=SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g' \
  "$KG_HOST/repositories/portfolio_test"
```

For the pilot kit the expected graph list is the five schema graphs
(`urn:graph:tbox`, `urn:graph:reference`, `urn:graph:reference:fibo`, `urn:graph:rules:catalog`,
`urn:graph:labels`), `urn:graph:universe:2026-Q4`, `urn:graph:derived:fundamentals:final`, and the
six backtest graphs this kit writes: `urn:graph:derived:backtest:meta:final`,
`urn:graph:derived:backtest:final:P1:system_with_hierarchy`,
`urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy`,
`urn:graph:derived:backtest:final:P1:system_without_hierarchy`,
`urn:graph:derived:backtest:selection:final:P1:system_without_hierarchy` and
`urn:graph:derived:backtest:final:P1:markowitz_base`. Drop **one exact graph per request**,
repeating for every IRI the listing returns (including any older backtest window); never use
`CLEAR ALL`, `DROP ALL`, `DROP DEFAULT` or a repository delete:

```bash
curl -fsS -u "$KG_USER:$KG_PASSWORD" -X POST \
  -H 'Content-Type: application/sparql-update' \
  --data-binary 'DROP GRAPH <urn:graph:tbox>' \
  "$KG_HOST/repositories/portfolio_test/statements"
```

### 0ter.2 Load the scratch rehearsal

```bash
set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db

uv run python cli/load_schema.py
uv run python cli/load_universe.py --as-of 2026-11-09 --write
uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db "$SQL_UNIVERSE_DB" --write
uv run python cli/load_veto.py \
  --manifest /workspaces/thesis/scratch/rehearsal/manifest_pilot_draft.json --write
uv run python cli/load_series.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/series_diarias_referencia" --write
uv run python cli/verify_store.py \
  --manifest /workspaces/thesis/scratch/rehearsal/manifest_pilot_draft.json
```

`load_veto --write` accepts the draft only because the repository is `portfolio_test`; the loader
refuses a draft on production. It writes the meta, m018/detail and selection graphs and never drops.
The pre-flight validates each m018 graph beside its sibling selection graph as context; the sibling
is not written by that check.
`verify_store --manifest` derives `memory_released_price` and `memory_released_not_ranked` from the
stored `StopMemory` `memoryReleaseCause`, and `memory_open_at_end` from `StopMemory` individuals with
no `memoryReleasedOn`.

### 0ter.3 Record the sizing table

Fill this after each write (explicit triple count from `store.size()` or the statements count;
inferred from the repository's inferred statement count; elapsed measured around each command with
`/usr/bin/time -p` or the shell's `time`):

```bash
curl -fsS -u "$KG_USER:$KG_PASSWORD" "$KG_HOST/repositories/portfolio_test/size"
```

That endpoint returns the explicit and inferred statement counts; run it immediately before and
after each step and subtract.

| Step | Explicit before | Explicit after | Inferred before | Inferred after | Elapsed |
|---|---:|---:|---:|---:|---:|
| load_schema | | | | | |
| load_universe | | | | | |
| load_fundamentals | | | | | |
| load_veto meta | | | | | |
| load_veto m018/detail | | | | | |
| load_veto selection | | | | | |
| load_series | | | | | |
| load_news | | | | | |
| load_agents | | | | | |
| verify_store | | | | | |

## 0. Preconditions (read-only)

From the repository root, with the delivery folder present:

```bash
cd /workspaces/portfolio-knowledge-graph
uv sync
grep -E '^(KG_HOST|KG_REPOSITORY|SQL_UNIVERSE_DB)=' .env
df -h /workspaces/thesis

# The curl steps below need the KG_* variables in the shell, not only in .env.
set -a; . ./.env; set +a

curl -fsS -u "$KG_USER:$KG_PASSWORD" "$KG_HOST/rest/info/version"
curl -fsS -u "$KG_USER:$KG_PASSWORD" -H 'Accept: text/turtle' \
  "$KG_HOST/rest/repositories/portfolio" | grep -E 'graphdb:(ruleset|disable-sameAs)'
```

The checks are:

- the maintainer has given the go-ahead for the production write;
- the disk has comfortable headroom above GraphDB's 5 % hard floor (`cli/load_run.py` defaults to
  `--min-free-pct 8`);
- GraphDB is **11.5.1 Free**;
- the repository is named `portfolio` and carries
  `graphdb:ruleset "rdfsplus-optimized"` and `graphdb:disable-sameAs "true"` (the profile in
  [`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl));
- a `KG_REPOSITORY` exported in the terminal wins over `.env`, and the CLI prints a warning when
  the two differ (Work item 39); check the `target:` line of every command.

The catalog source is `/workspaces/thesis/data/universe_history_gics.db`. The final delivery folder
contains `final_<window>.db` for the six windows, `SHA256SUMS`, `config_final.md` and
`aggregates_final.json`.

## 1. Back up the current store (read-only)

Export every named graph and the repository configuration to a folder **outside the repository**,
then record a SHA-256 for every file:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=/workspaces/thesis/backups/portfolio-$STAMP
mkdir -p "$BACKUP"

# All named graphs as TriG, explicit statements only; the statements endpoint is a read.
curl -fsS -u "$KG_USER:$KG_PASSWORD" -H 'Accept: application/trig' \
  "$KG_HOST/repositories/portfolio/statements?infer=false" \
  -o "$BACKUP/portfolio-$STAMP.trig"

# The repository configuration (ruleset, sameAs, indexes) as Turtle.
curl -fsS -u "$KG_USER:$KG_PASSWORD" -H 'Accept: text/turtle' \
  "$KG_HOST/rest/repositories/portfolio" \
  -o "$BACKUP/portfolio-repository-config.ttl"

( cd "$BACKUP" && sha256sum portfolio-"$STAMP".trig portfolio-repository-config.ttl > SHA256SUMS )
( cd "$BACKUP" && sha256sum -c SHA256SUMS )
```

The export is a `GET`; the store's `/size` does not change. Keep `SHA256SUMS` with the backup and
with the copy delivered to the second user. The TTYG agent is not in this export; it is recreated
from [`ttyg/create-agent.md`](ttyg/create-agent.md).

**Not yet verified on a live store.** The TriG export through
`/repositories/portfolio/statements` and the re-import of a file of roughly 4.2 million triples have
not been tried on this installation. A large single POST can hit timeouts or memory limits. Rehearse
the export and import into a scratch repository first; if the POST fails, import with Workbench
**Import** (upload or server files).

## 2. List the graphs and clear the old data (maintainer `DROP`)

First list every graph and its asserted triple count. Run this in the Workbench or through the
repository's SPARQL endpoint:

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
FROM <http://www.ontotext.com/explicit>
WHERE { GRAPH ?graph { ?s ?p ?o } }
GROUP BY ?graph
ORDER BY ?graph
```

Save the result with the backup. Then the maintainer removes the old run families and any other
non-schema data graphs, one exact graph at a time. Use the listing-and-generation procedure in
[`backtest-load-runbook.md` §9a](backtest-load-runbook.md#9a-removing-a-run-label); do not duplicate
or widen it here. In particular:

- the old pilot `rule` graphs (m018, selection, metadata, aggregates and the `rule` ticker-history
  snapshot) and any `candidate` family are not part of the final store;
- an old `urn:graph:universe:*` or ingest graph must be dropped by its exact IRI after review;
- the schema graphs need no separate drop, because `cli/load_schema.py` replaces them in step 3
  anyway;
- never use `CLEAR ALL`, `DROP ALL`, `DROP DEFAULT` or a repository delete. The agent never runs the
  statements; the maintainer runs them after checking every row against the backup.

Read-only check: rerun the listing after the drops and confirm that every remaining graph is either
a schema graph or one you intend to keep.

## 3. Load and verify the schema (write)

Production receives the five schema files but **not** `instances.trig`'s worked-example ABox:

```bash
KG_REPOSITORY=portfolio uv run python cli/load_schema.py --to-production
KG_REPOSITORY=portfolio uv run python cli/verify_store.py --to-production
```

Expected: the loader reports the four schema graphs and prints
`examples: instances.trig not loaded in the production repository`; `verify_store` prints one
`PASS` line per check and exits 0. It is read-only even though it takes `--to-production`.

Two of the six acceptance checks take their production branch for the first time here: the
reasoning check proves the TBox chain without an ABox, and the rule-vocabulary probe uses a stored
`:RuleDefinition`. If either fails on this first production run, report it as a **code bug**, not as
a data problem: the store is a fresh schema load and has no backtest data yet.

## 4. Load the asset catalog (write)

Dry run first (reads the catalog, builds and SHACL-validates, contacts no store), then write:

```bash
KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_universe.py --as-of 2026-11-09

KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_universe.py --as-of 2026-11-09 --write --to-production
```

The catalog graph is `urn:graph:universe:2026-Q4` for that date. The read-only check after the write
is the empty delta: it reads the store and the source without writing.

```bash
KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_universe.py --delta --as-of 2026-11-09
```

The expected first-live-run result is `0 new assets, 0 new memberships, 0 closures and 0 drift`;
confirm it on the first live run rather than treating it as a measured result. A non-empty delta
means the source moved or the store differs; stop and inspect before continuing.

## 5. Load ticker history for label `final` (write)

The ticker-history snapshot is a separate, append-only graph. Use the first window database as the
source, as the runbook does:

```bash
KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db final=/workspaces/thesis/scratch/final/final_corregida/final_P1.db \
  --as-of 2026-11-09

KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db final=/workspaces/thesis/scratch/final/final_corregida/final_P1.db \
  --as-of 2026-11-09 --write --to-production
```

It writes `urn:graph:derived:ticker-history:final:2026-11-09`. The read-only check is the same
command with `--check-store`, which reads the live store and validates the batch beside its context:

```bash
KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db final=/workspaces/thesis/scratch/final/final_corregida/final_P1.db \
  --as-of 2026-11-09 --check-store
```

A later snapshot is a new date (or a new label), never a rewrite of this graph.

## 6. Load the six backtest windows (write)

**Superseded for the Work item 46 delivery by §0bis.5 (`cli/load_veto.py`).** This legacy command
and its run-id graph names remain for the old six-window family.

Dry run (no store contacted), read-only pre-flight (the real `gate.plan` with `SELECT` only), then
the write:

```bash
KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida

KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida --check-store

KG_REPOSITORY=portfolio SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida --write --to-production
```

The dry run prints one row per graph and `SHACL-valid, not written`. The pre-flight must report all
13 graphs as `would-be-written`; an `already-in-the-store` graph means the clear in step 2 was
incomplete or a previous attempt wrote it. Stop and inspect; do not drop blindly. The `--write` run
applies the accepted plans, then runs the verifier for every m018 and selection graph and the
metadata verifier. Exit 0 is the proof.

The six windows are loaded in calendar order (`P1`, `H1`, `P3`, `H2`, `P2`, `H3`), not by name. Each
window has one m018 graph and one selection sibling:

```text
urn:graph:derived:backtest:final:{window}:1
urn:graph:derived:backtest:selection:final:{window}:1
```

plus the one metadata graph `urn:graph:derived:backtest:meta:final`.

## 7. Load the aggregates file (write)

For the Work item 46 delivery, load aggregates after §0bis.5 runs; the rest of this section still
applies.

After the backtest graphs, load the delivery's per-segment aggregates file:

```bash
KG_REPOSITORY=portfolio uv run python cli/load_aggregates.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida

KG_REPOSITORY=portfolio uv run python cli/load_aggregates.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida --check-store

KG_REPOSITORY=portfolio uv run python cli/load_aggregates.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida --write --to-production
```

It writes `urn:graph:derived:backtest:aggregates:final` and touches no other graph. The read-only
check is a second `--check-store` after the write: it reads the stored rows and compares them with
the file.

## 7b. Load the external mean-variance base Markowitz delivery (write)

The external `MARKOWITZ_MV` delivery is a separate stream and does not change the engine's 13
graphs. Its folder is `/workspaces/thesis/knoledge graph/mv_base/`; `provenance/` is not required:

```bash
uv run python cli/load_mv_base.py --label final \
  --dir "/workspaces/thesis/knoledge graph/mv_base"

uv run python cli/load_mv_base.py --label final \
  --dir "/workspaces/thesis/knoledge graph/mv_base" --check-store

KG_REPOSITORY=portfolio uv run python cli/load_mv_base.py --label final \
  --dir "/workspaces/thesis/knoledge graph/mv_base" --write --to-production
```

The loader reads `bookId` and `backtestRunId` read-only from the engine's `final_<window>.db`
(`--engine-dir` defaults to `/workspaces/thesis/scratch/final/final_corregida`; it stops if a
database is missing) and cross-checks every segment's `date_from`/`date_to` against the engine's
`MARKOWITZ_BASE` rows. It writes `urn:graph:derived:backtest:external:final` with six
`:StrategyBook` individuals and eight `:PortfolioPeriodSummary` rows; no daily series, weights or
alerts are stored. The dry run
must end with `SHACL: conforms (gate.validate)` and the pre-flight must report `would-be-written`
(or `already-in-the-store` if the graph is already there). The engine graphs are untouched.

## 7c. Load the fundamentals block C delivery (write)

The v2 fundamentals delivery is `/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales/`;
`SHA256SUMS` hashes to `fd32daed391f515e5ff76e030acaab2dd018fea8dadf4d206429274bbe6ee677`
and the Tiingo mask to `4712c7c224bd76b4661260d77d95ce3c62fe80710c0b7d30a1ce44ac00c39dce`.
`filings.csv`, `metrics.csv`, `assessments.jsonl`, `source.json`, `README.md` and
`provenance/export_bloque_c.py` are all required and are verified against the manifest before the
store is contacted. The loader writes the append-only graph
`urn:graph:derived:fundamentals:final`; it never writes an engine, backtest or schema graph.

Dry run (contacts no store; it verifies the manifest and mask, projects and SHACL-validates the
whole batch), read-only pre-flight (the real `gate.plan` with `SELECT` only), then the write:

```bash
uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db /workspaces/thesis/data/universe_history_gics.db

KG_REPOSITORY=portfolio uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db /workspaces/thesis/data/universe_history_gics.db --check-store

KG_REPOSITORY=portfolio uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db /workspaces/thesis/data/universe_history_gics.db --write --to-production
```

The expected dry run (measured 2026-11-13, no store) is **834,586 asserted triples**, 14,639
filings and metric sets, 10,025 assessments (9,896 scored and 129 rule rows) and exactly **33**
`:pricesNotPublished` flags, including FRC and SBNY. It ends with `SHACL: conforms
(gate.validate)`; the measured wall time was 604.0 s (580.9 s of it SHACL) and peak memory 4.5 GB.
The whole-batch SHACL is acceptable at this size; a larger delivery should batch that pass before
a write. `--check-store` must print `pre-flight: would-be-written:
urn:graph:derived:fundamentals:final` (or `already-in-the-store` if a previous attempt wrote it).
The write verifies the stored graph triple-for-triple; on a mismatch it prints the exact one-graph
`DROP GRAPH <urn:graph:derived:fundamentals:final>`, which only the maintainer may run. Never use
`CLEAR ALL`, `DROP ALL`, a repository delete or a second graph.

## 7d. Load the daily reference series (write)

The block E series delivery is `/workspaces/thesis/knoledge graph/2026-11-17_final/series_diarias_referencia`
— the series folder inside the single final delivery folder `2026-11-17_final/`. That folder has
no `SHA256SUMS` of its own; the loader walks to the delivery root's `SHA256SUMS` and matches the
entries prefixed with `series_diarias_referencia/`. A standalone series folder with its own
manifest (for example `2026-11-12_respuesta_4/series_diarias_referencia`) still works unchanged.
Point `--dir` at the series folder (the one with `spy_daily.csv` and `markowitz_mv/`). The loader
verifies every series CSV against the selected manifest before reading it, rejects header drift,
duplicate `(window, date)` keys and a missing C1, then writes two append-only graphs:
`urn:graph:derived:backtest:series:final:markowitz_mv` and
`urn:graph:derived:backtest:series:final:spy`.

Dry run first (contacts no store), then the read-only pre-flight and the write:

```bash
SERIES_DIR="/workspaces/thesis/knoledge graph/2026-11-17_final/series_diarias_referencia"

uv run python cli/load_series.py --label final --dir "$SERIES_DIR"

set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
uv run python cli/load_series.py --label final --dir "$SERIES_DIR" --check-store

KG_REPOSITORY=portfolio uv run python cli/load_series.py --label final \
  --dir "$SERIES_DIR" --write --to-production
```

The dry run prints one `rows: <file>: <n>` line per CSV and `SHACL: conforms` for both graphs.
`--check-store` must print `would-be-written` for both graphs (or `already-in-the-store` after a
write). The write appends each graph in bounded N-Triples chunks; a lost answer prints
`store error, the graph is in doubt` and must not be retried blindly. The two graphs are separate
from the external summary graph; `MARKOWITZ_MV` weights are in the `markowitz_mv` series graph, not
in `urn:graph:derived:backtest:external:final`. After the write, `verify_store --manifest` verifies
the `daily_rows` of `MARKOWITZ_MV` and `SPY` against the series graphs; when a graph is absent it
stays "not verifiable" and does not fail the check.

## 7e. Load the news rows (write)

The block D news delivery is `/workspaces/thesis/knoledge graph/2026-11-17_final` — the delivery
root that holds `manifest_final.json` and `SHA256SUMS`; the file itself is `news/news_rows.jsonl`
(the row count and model revision are the ones the manifest's `news_rows_file` and the delivery's
`news/README.md` state). Point `--dir` at that root (or at its
`news/` folder). The loader checks the file against both the manifest's `news_rows_file` block and
the delivery `SHA256SUMS` before reading a row, then checks the row header against the manifest
columns, the row count and the key. It writes one append-only graph per calendar year,
`urn:graph:derived:news:final:{year}`; 2024 is split into `:2024:01-06` and `:2024:07-12` to stay under
the ~400,000-triple bound. Rows can be fragments (`item_kind "sub_news"`) or full article bodies
(`item_kind "body"`). A body's `item_id` is its 64-lowercase-hex body fingerprint and equals
`body_hash`; its `article_id` and `source_domain` are absent because the NLP delivery does not say
which article a body comes from, so the loader omits `:articleId`/`:sourceDomain` for bodies. A
body's title may be empty (the NLP delivery does not always carry one); a fragment's title is
required.
Letter 26 corrected the PSKY rows to engine `asset_id` 477, so they link to `:SKYD`; the EQR rows
stay unlinked because the engine has no asset or ticker interval for EQR. Counts are read from the
manifest's `news_rows_file` and the delivery's `news/README.md`, never fixed here. The loader
prints the row and triple counts by `item_kind` and the unresolved tickers. A future revision that
re-labels an already loaded fragment (same `item_id`, same ticker) writes one value per graph, so a
query must read the revision by graph.

Dry run first (contacts no store), then the read-only pre-flight and the write:

```bash
NEWS_DIR="/workspaces/thesis/knoledge graph/2026-11-17_final"

uv run python cli/load_news.py --label final --dir "$NEWS_DIR"

set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
uv run python cli/load_news.py --label final --dir "$NEWS_DIR" --check-store

KG_REPOSITORY=portfolio uv run python cli/load_news.py --label final \
  --dir "$NEWS_DIR" --write --to-production
```

The dry run prints the row count, the unresolved-asset count, one `graph:`/`triples:` pair per year
graph and `SHACL: conforms` for each. `--check-store` must print `would-be-written` (or
`already-in-the-store` after a write) per graph. The write appends each graph in bounded N-Triples
chunks; a lost answer prints `store error, the graph is in doubt` and must not be retried blindly.
After the write, `verify_store --manifest` sums the stored `NewsItem` rows across the year graphs
against the manifest and checks the distinct tickers; when the graphs are absent it reports
"not store-verifiable" and does not fail the check.

## 7f. Load the block F agent traceability files (write)

The block F files are the four per-window files of `SYSTEM_WITH_HIERARCHY`:

```
{window}/H1B-A2g-{window}.manager_calls.jsonl
{window}/H1B-A2g-{window}.narrator.jsonl
{window}/H1B-A2g-{window}.news.json
{window}/H1B-A2g-{window}.bull_mode.json
```

The loader reads `manifest_final.json` and the delivery's `SHA256SUMS` itself. The delivery root
is `KG_DELIVERY_DIR` (default `/workspaces/thesis/knoledge graph/2026-11-17_final`), so the
commands below need no absolute path when that variable is set. Load block F **after** the schema,
the universe/assets, the Veto Hierarchy detail (the manager and narrator stop links point at the
detail graph's `:StopEvent` individuals) and the block D `:NewsItem` graph (the evidence's
`:newsItem` links resolve against it; block F does not load that graph). `--check-store` and
`--write` therefore require the same label's veto and news graphs already loaded
(order: schema, universe, veto, news, agents).

Dry run first (no store contact), then the read-only pre-flight and the write:

```bash
export KG_DELIVERY_DIR="/workspaces/thesis/knoledge graph/2026-11-17_final"

uv run python cli/load_agents.py --label final

set -a; . ./.env; set +a
export KG_REPOSITORY=portfolio_test
[ "$KG_REPOSITORY" = "portfolio_test" ] || exit 1
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
uv run python cli/load_agents.py --label final --check-store

KG_REPOSITORY=portfolio uv run python cli/load_agents.py --label final \
  --write --to-production
```

The dry run prints the seven windows, the four graph names and their triple counts (43,468 in the
five windows that load: 7,726 manager, 22,244 narrator, 12,483 news, 1,015 bull-mode) and
`SHACL: conforms` for each graph. P1 and C1 currently stop before the news graph because two REGN
test rows (`280187`, `328156`) have no `news_rows.jsonl` row; the loader refuses to guess the item
kind. The other five windows load; once the delivery adds those two rows (or Reviewer A approves
a documented skip), the two windows are retried with `--window P1` and `--window C1`. `--check-store` must print `would-be-written` for every graph (or
`already-in-the-store` after a write) and the stored counts when a graph exists; an absent graph
prints `not store-verifiable`. The write appends each graph in bounded N-Triples chunks; a lost
answer prints `store error, the graph is in doubt` and must not be retried blindly. Any piece can
be loaded later without touching the others:

```bash
# one window, one file type
uv run python cli/load_agents.py --label final --window H1 --only news
```

`--only` accepts `manager_calls`, `narrator`, `news` and `bull_mode`; `--window` accepts `P1`,
`H1`, `P3`, `H2`, `P2`, `H3` and `C1`.

## 8. Acceptance (read-only)

### 8.1 The run label is only `final`

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT DISTINCT ?label
WHERE { ?book a :StrategyBook ; :runLabel ?label }
ORDER BY ?label
```

Expected: exactly one row, `final`. Any other label means an old backtest family is still in the
store; retire it with [§9a](backtest-load-runbook.md#9a-removing-a-run-label) before calling the
delivery done.

### 8.2 Alerts per window

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?window (COUNT(DISTINCT ?alert) AS ?alerts)
WHERE {
  GRAPH ?graph {
    ?alert a :GuardAlert ;
           :windowId ?window .
  }
  FILTER(STRSTARTS(STR(?graph), "urn:graph:derived:backtest:final:"))
}
GROUP BY ?window
ORDER BY ?window
```

Expected (read-only check of the delivered `portfolio` store, 2026-11-19; the total includes C1):

| Window | `:GuardAlert` rows |
|---|---:|
| P1 | 271 |
| H1 | 205 |
| P3 | 125 |
| H2 | 77 |
| P2 | 103 |
| H3 | 274 |
| C1 | 2,084 |
| **Total** | **3,139** |

All of them are in the `SYSTEM_WITH_HIERARCHY` graphs; the other configurations carry no
`:GuardAlert`. C1 is an independent continuous run (2022-01-03..2026-10-15), not a seventh
contiguous calendar window.

### 8.3 The 13 expected graphs exist

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
FROM <http://www.ontotext.com/explicit>
WHERE {
  GRAPH ?graph { ?s ?p ?o }
  FILTER(
    STRSTARTS(STR(?graph), "urn:graph:derived:backtest:final:") ||
    STRSTARTS(STR(?graph), "urn:graph:derived:backtest:selection:final:") ||
    STR(?graph) = "urn:graph:derived:backtest:meta:final"
  )
}
GROUP BY ?graph
ORDER BY ?graph
```

Expected: 13 rows, one for each `urn:graph:derived:backtest:final:{window}:1`, one for each
`urn:graph:derived:backtest:selection:final:{window}:1`, and
`urn:graph:derived:backtest:meta:final`. The ticker-history graph, the aggregates graph, the
external `urn:graph:derived:backtest:external:final` graph, the fundamentals
`urn:graph:derived:fundamentals:final` graph, the two series graphs and the four
`urn:graph:derived:backtest:agents:final:{window}:{slug}` graphs are separate streams and are
checked in steps 5, 7, 7b, 7c, 7d and 7e.

### 8.4 The old pilot is gone

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
FROM <http://www.ontotext.com/explicit>
WHERE {
  GRAPH ?graph { ?s ?p ?o }
  FILTER(
    STRSTARTS(STR(?graph), "urn:graph:derived:backtest:rule:") ||
    STRSTARTS(STR(?graph), "urn:graph:derived:backtest:selection:rule:") ||
    STRSTARTS(STR(?graph), "urn:graph:derived:ticker-history:rule:") ||
    STR(?graph) = "urn:graph:derived:backtest:meta:rule" ||
    STR(?graph) = "urn:graph:derived:backtest:aggregates:rule"
  )
}
GROUP BY ?graph
ORDER BY ?graph
```

Expected: no rows. The `rule` label is the pilot; it and its ticker-history are not part of the
final store. The same check applies to any `candidate` graph the operator used for rehearsal.

Finally, `KG_REPOSITORY=portfolio uv run python cli/verify_store.py --to-production` must still exit
0, and `cli/load_run.py --label final --dir ... --check-store` must report all 13 graphs as
`already-in-the-store`.

### 8.5 Create the agent (manual)

After the load and acceptance, create the Workbench agent from
[`ttyg/create-agent.md`](ttyg/create-agent.md) with **Repository ID `portfolio`**. The agent is
Workbench state: it is not in the export, the backup or the repository. Paste the v2.1 CONSTRUCT and
the single v1.5 instruction fence exactly as the recipe says, and confirm that **Review agent
instructions** shows the stated character count.

When the evaluation reaches questions 21 and 22 (book weighting and the name cap), the human answer
must quote the real `RunConfiguration_final` comment from `config_final.md`. The rehearsal
repository's placeholder "Pilot rehearsal body" is not the production comment and must not appear in
a delivered answer. T-759 stays open until the human run.

## Known pitfalls (notes, not commands)

- `.env` already defines `SQL_UNIVERSE_DB` with a path that may not exist on this machine. Sourcing
  `.env` sets that value, so export the real path explicitly **after** `set -a; . ./.env; set +a`;
  otherwise the loader reads the wrong database.
- The dev-container name changes when the container is recreated: find it with `docker ps`, and make
  sure the `portfolio` GraphDB container is running (`docker start portfolio`) before the store
  commands.

## 9. Rehearsal first

Run the same sequence in `portfolio_test` before touching production. Prefix every trial command
with `KG_REPOSITORY=portfolio_test`; the terminal-exported value wins over `.env` and the CLI prints
a warning when they differ (Work item 39). Do **not** add `--to-production` to a rehearsal command:
the flag is only required on `portfolio` and is accepted without effect elsewhere, so omitting it in
the rehearsal keeps a trial run from ever being mistaken for a production write.

```bash
# rehearsal example: same flags, scratch repository, no --to-production
KG_REPOSITORY=portfolio_test SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final \
  --dir /workspaces/thesis/scratch/final/final_corregida --check-store
```

Repeat the rehearsal after any change to the delivery, the schema or the loader, and only then run
the production block from step 3 onwards. The rehearsal store is not delivered.

## 10. Dry-run reference (2026-11-09)

The dry run of `cli/load_run.py --label final` over `final_corregida` contacted no store and took
932 s. All 13 graphs were SHACL-valid. Windows are in calendar order:

| Window | `v_guard_alert` rows | `v_book_weight_daily` rows | m018 triples | Selection triples |
|---|---:|---:|---:|---:|
| P1 | 978 | 21,085 | 276,819 | 321,954 |
| H1 | 933 | 31,278 | 393,664 | 391,365 |
| P3 | 603 | 26,335 | 324,780 | 343,594 |
| H2 | 441 | 18,387 | 227,463 | 295,780 |
| P2 | 714 | 23,806 | 297,392 | 310,341 |
| H3 | 1,289 | 48,012 | 591,900 | 389,440 |

The loader prints `unknown key 'revision' ignored` while reading `config_final.md`: the delivery's
front matter has a `revision` key the loader does not use. The warning is harmless. The write's
verifier prints the stored counts; compare them with the same run's source, not with this table.
The `v_guard_alert` column is the database source rows over all arms; it is not the stored
`:GuardAlert` count, which is the per-window table in §8.2.

## 11. Failure and rollback

A refused pre-flight writes nothing: fix the cause and rerun the same command. A write that fails
after the pre-flight names the graphs written and the graph in doubt, and prints the exact one-graph
`DROP GRAPH` statements. The maintainer decides whether to use them; never drop the in-doubt graph
blindly and never widen a drop to the whole repository. The single-graph and whole-label procedures
are in [`backtest-load-runbook.md` §9 and §9a](backtest-load-runbook.md#9-roll-back-exactly-one-graph).
A changed delivery needs a new label or run id, not a rewrite of an append-only graph.
