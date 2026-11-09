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
`urn:graph:derived:backtest:meta:final`. The ticker-history graph and the aggregates graph are
separate streams and are checked in steps 5 and 7.

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
