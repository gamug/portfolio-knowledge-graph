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

## 0bis. Work item 46 reload — exact order for 18–19 November 2026

**This section supersedes §3–§8 for the Veto Hierarchy delivery; the older six-window sequence
remains for the legacy `rule` family.** The agent never runs a write, a `DROP`, a schema load or a
backup restore: every command below is for the maintainer after reviewing the listing and the
backup. The new loader is `cli/load_veto.py`; it refuses a non-empty target and never drops.

### 0bis.1 Rehearse on `portfolio_test` first (read-only dry run)

Use the pilot DB and a **draft** manifest (PENDIENTE control counts, real pilot hashes). A draft is
accepted only for a dry run or a scratch repository:

```bash
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
written list. A failure stops and lists what was already written; no graph is dropped.

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

### 0bis.7 Verify, test, decide and roll back

```bash
KG_REPOSITORY=portfolio uv run python cli/verify_store.py \
  --to-production --manifest /path/to/final/manifest_final.json
uv run pytest -q
```

`verify_store --manifest` re-projects the manifest read-only and checks every stored graph count,
the control counts, the removed-rule stop and the price mask. The decision point is after the
verification and the full suite: if either fails, stop and restore the backup; if both pass, the
delivery is accepted. Plan B is the §0bis.2 TriG backup. Restore only after a deliberate decision,
into an emptied repository or with Workbench **Import**; a large single POST can time out (see §1).

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

```bash
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
set -a; . ./.env; set +a

curl -fsS -u "$KG_USER:$KG_PASSWORD" -H 'Accept: application/sparql-results+json' \
  --data-urlencode 'query=SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g' \
  "$KG_HOST/repositories/portfolio_test/statements"
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
export KG_REPOSITORY=portfolio_test
export SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db
set -a; . ./.env; set +a

uv run python cli/load_schema.py
uv run python cli/load_universe.py --as-of 2026-11-09 --write
uv run python cli/load_fundamentals.py --label final \
  --dir "/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales" \
  --mask "/workspaces/thesis/knoledge graph/mascara_tiingo/tiingo_assets.csv" \
  --universe-db "$SQL_UNIVERSE_DB" --write
uv run python cli/load_veto.py \
  --manifest /workspaces/thesis/scratch/rehearsal/manifest_pilot_draft.json --write
uv run python cli/verify_store.py \
  --manifest /workspaces/thesis/scratch/rehearsal/manifest_pilot_draft.json
```

`load_veto --write` accepts the draft only because the repository is `portfolio_test`; the loader
refuses a draft on production. It writes the meta, m018/detail and selection graphs and never drops.

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

Expected:

| Window | `:GuardAlert` rows |
|---|---:|
| P1 | 978 |
| H1 | 933 |
| P3 | 603 |
| H2 | 441 |
| P2 | 714 |
| H3 | 1,289 |
| **Total** | **4,958** |

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
external `urn:graph:derived:backtest:external:final` graph and the fundamentals
`urn:graph:derived:fundamentals:final` graph are separate streams and are checked in steps 5, 7,
7b and 7c.

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

## 11. Failure and rollback

A refused pre-flight writes nothing: fix the cause and rerun the same command. A write that fails
after the pre-flight names the graphs written and the graph in doubt, and prints the exact one-graph
`DROP GRAPH` statements. The maintainer decides whether to use them; never drop the in-doubt graph
blindly and never widen a drop to the whole repository. The single-graph and whole-label procedures
are in [`backtest-load-runbook.md` §9 and §9a](backtest-load-runbook.md#9-roll-back-exactly-one-graph).
A changed delivery needs a new label or run id, not a rewrite of an append-only graph.
