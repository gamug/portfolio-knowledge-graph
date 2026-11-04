# Backtest load runbook

Copy-pasteable procedure for the final backtest: load each completed database into its own
append-only backtest graph and prove that the store matches the source. Everything here is
read-only except the two explicitly marked write steps (`cli/load_universe.py --write` and
`cli/project_backtest.py --write`); the verifier never writes.

The verifier's checks are in `SPEC.md` FR-009, the graph naming and projector are in `SPEC.md`
§2.6 and `docs/07-ontology-topology.md`, and the measured reference numbers are in
[`graphdb-setup.md`](graphdb-setup.md). Work item 24 built this procedure; it was closed on
2026-11-04 with read-only dry runs, not with a live GraphDB write.

## 0. What "loaded" means

One completed backtest database becomes one graph per backtest run:

```text
urn:graph:derived:backtest:{label}:{window_id}:{backtest_run_id}
```

The label is yours (`rule`, `champ_v1`, …), the window and run id come from `v_book`. The label is
also part of every individual IRI, so two result families never share an individual. The graph is
append-only: once written, it is never edited or appended to.

The same database also carries the three remaining Contract v18 views. They are projected
separately by `cli/project_reference.py` into:

```text
urn:graph:derived:ticker-history:{label}:{snapshot_date}   # one complete snapshot
urn:graph:derived:orchestrator:{label}:{run_id}            # one graph per run
```

A ticker-history snapshot is labelled and dated, and every IRI carries both, so a later refresh is
a new graph with new individuals, never a re-declaration. An orchestrator run is immutable; a
later run is a new id and a new graph. Both are append-only like the backtest graph.

The selection side of the same run is a separate sibling graph:

```text
urn:graph:derived:backtest:selection:{label}:{window_id}:{backtest_run_id}
```

It is written by `cli/project_selection.py`; the m018 graph is neither a target nor rewritten.

## 1. Prerequisites

Run from the repository root, with `uv sync` already done and `.env` present (never commit it).

```bash
uv sync
```

Check the store settings. From the dev container GraphDB is reached at
`http://host.docker.internal:7200`, **not** `localhost` (inside the container `localhost` is the
container itself):

```bash
grep -E '^(KG_HOST|KG_REPOSITORY|SQL_UNIVERSE_DB)=' .env
```

### 1a. Schema must already be current

The store's shapes must know `:runLabel` and the open `P<number>` window vocabulary (T-233/T-234),
and the gate must accept the labelled graph name. Reload after any `schema/` change:

```bash
uv run python cli/load_schema.py
uv run python cli/verify_store.py
```

`verify_store` must exit 0. If it reports `urn:graph:tbox: expected N, store has M`, stop and reload
the schema; do not load a backtest against a stale store.

### 1b. The asset catalog is loaded once per repository

Before any backtest that links `:Asset` nodes, and **before the first backtest write** (replace
`2026-11-04` with the day of your load; it is the date of the reference run):

```bash
# dry run first: reads SQL_UNIVERSE_DB, builds and SHACL-validates, contacts no store
uv run python cli/load_universe.py --as-of 2026-11-04
# then the one write:
uv run python cli/load_universe.py --as-of 2026-11-04 --write
# production also needs the explicit opt-in:
uv run python cli/load_universe.py --as-of 2026-11-04 --write --to-production
```

The loader writes the whole catalog (all `:Asset`, `:Universe` and `:UniverseMembership`
individuals) into `urn:graph:universe:{year}-Q{n}`. It is not an incremental loader. The real limit:

- a second load into the same quarter is refused because the graph already exists (gate check 2);
- a load into a later quarter re-declares the same `:Asset`/`:Universe` typed individuals and is
  refused by gate check 6, even if no value changed;
- therefore a **new ticker cannot be added** to a repository that already has the catalog with
  `cli/load_universe.py`, and a **new quarter alone does not make a reload possible**.

The supported safe procedure is a fresh repository: load `schema/`, load the catalog once, then
write the backtests there. If you truly need new tickers in an existing repository, stop and open a
task for an incremental membership batch (only new `:Asset`/`:UniverseMembership` individuals plus
`:validTo` closures of stored memberships, through `cli/ingest.py` into a new quarter graph); do not
drop the universe graph, rewrite its individuals, or bypass the gate.

### 1c. Copy the databases

The inputs are read-only; work on copies so a later source refresh cannot change what you verified:

```bash
mkdir -p data/backtests
cp /workspaces/thesis/scratch/final/runs/rule_P1.db data/backtests/
cp /workspaces/thesis/scratch/final/runs/rule_P2.db data/backtests/
cp /workspaces/thesis/scratch/final/runs/rule_P3.db data/backtests/
ls -l data/backtests/
```

`SQL_UNIVERSE_DB` must point at the catalog you loaded (for the full 2026-11-04 catalog,
`/workspaces/thesis/data/universe_history_gics.db`).

## 2. Check the pinned view contract

Before reading the new database, confirm its views still match `src/projection/view_contract.py`:

```bash
# against an upstream checkout...
uv run python cli/check_view_contract.py /path/to/portfolio-financial-analysis
# ...or against its running contract endpoint:
uv run python cli/check_view_contract.py http://HOST:PORT/api/v1
```

A `DRIFT` line or a non-zero exit means the database and this repo's pin disagree: stop and re-pin
(T-157/T-173), do not project around a changed view.

## 3. Choose the label

The label names the result family and is part of the graph and every IRI:

```text
[a-z][a-z0-9_]{1,31}
```

Use `rule` for the final rule-based runs. A missing or malformed label exits 2 before anything is
read. The graph name is fixed by `v_book.window_id` and `v_book.backtest_run_id`; for the completed
databases the dry run below prints it, e.g. `urn:graph:derived:backtest:rule:P1:1`.

**A new run needs a new label when the graph name would repeat.** Re-projecting the same database
under `rule`/`P1`/`1` targets the same graph and the gate refuses it (append-only). Do not drop the
old graph to reuse the name: write the new family under a different label (for example
`rule2` or `rule_20261105`), which gives it a fresh graph and fresh IRIs. A genuinely new upstream
run normally has a new `backtest_run_id`, so the same label already produces a new graph name; use
the dry run to confirm.

## 4. Dry run

The default is a dry run: it reads every `--db`, runs the boundary, builds each graph and
SHACL-validates it beside the rules and universe assets. It contacts no store and writes nothing.

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db
```

Expect exit 0 and one `graph: urn:graph:derived:backtest:rule:P<n>:<run>: <triples> triples` line
per database, plus `SHACL-valid, not written`. Read the `rows:` lines and the
`asset link omitted: ...` lines; record both. A non-empty asset-link count is expected when the
catalog lacks a ticker (see §9). Stop on `STOPPED`, `rejected`, or a missing view.

## 4a. Check the live store context (read-only)

The dry run validates beside the full local `rules.ttl` and the universe database; the write uses
the gate's narrower `fetch_context` from the live store. `--check-store` performs that same fetch
with `SELECT` queries only, runs the gate's validation and prints `would be accepted` or
`would be refused` for each graph. It writes nothing, so it needs neither `--write` nor
`--to-production`; those flags are refused with it.

Run it for both backtest sides and the reference snapshot:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --check-store

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_selection.py \
  --db rule=data/backtests/rule_P1.db --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --check-store

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db rule=data/backtests/rule_P1.db --as-of 2026-11-04 --check-store
```

A `would be refused` line is the same failure the write would hit: stop and fix the gate/context
before writing. The 2026-11-04 read-only run against `portfolio_test` accepted all seven graphs
(six backtest graphs and the ticker-history snapshot). This step is exactly what catches a relation
whose context fetch is too narrow; the local dry run cannot see it.

## 5. Write (only after the dry run is clean)

For a scratch repository, or for production after the maintainer's decision:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db \
  --write
```

Writing to `KG_REPOSITORY=portfolio` additionally requires `--to-production`; without it the run
exits 2 before building anything, because a backtest is a frozen artifact and where it lives is the
maintainer's decision:

```bash
# production, only with the maintainer's explicit go-ahead
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --write --to-production
```

`written: <graph>: <n> triples` is the record. `already in the store: <graph>` means that graph
was left untouched (nothing was appended); use a new label (§3) if this was meant to be a new
family. The gate also refuses an existing graph, so a second write can never mutate the first.

## 5a. Ticker history and orchestrator runs

The three remaining v18 views are projected by the reference/process CLI. The default is a dry run;
it reads the same database, runs the boundary, builds each graph and SHACL-validates it beside the
loaded asset catalog, and contacts no store:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db rule=data/backtests/rule_P1.db --as-of 2026-11-04
```

Read the `rows: v_ticker_history`, `rows: v_orchestrator_run` and
`rows: v_orchestrator_step` lines, the `asset links:` line (exact, by CIK) and any
`asset link omitted:` line. A canonical symbol the catalog does not know is linked to the one
loaded `:Asset` with the same CIK (`FBIN` → `:FBHS`, `GAP` → `:GPS`); with no safe link it is left
unset and counted, never invented. A ticker-history snapshot is complete and immutable: a later
refresh uses a new `--as-of` date (or a new label), not a rewrite of the existing graph.

When both orchestrator views are empty, the run exits 0 and prints
`v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to write`; that is the expected
result for the completed P1/P2/P3 databases, not a failure.

Write after a clean dry run, with the same production guard as the backtest projector:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_reference.py \
  --db rule=data/backtests/rule_P1.db --as-of 2026-11-04 --write
```

`written: <graph>: <n> triples` is the record. `already in the store: <graph>` means the graph was
left untouched; use a new snapshot date/label for ticker history, or a new run id for an
orchestrator run. The production repository additionally needs `--to-production`.

## 5b. Selection side

The selection projector writes the sibling graph for the same run:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_selection.py --db rule=data/backtests/rule_P1.db
```

The dry run reads `v_cycle_run`, `v_weight_scheme`, `v_weight_component`, `v_cycle_ranking`,
`v_cycle_ranking_component`, `v_veto` and `v_ticker_history`, builds the selection graph and
SHACL-validates it beside `rules.ttl` and the universe assets. A ranking or veto ticker links by
exact `:Asset` symbol first, else to the one loaded `:Asset` with the same CIK from
`v_ticker_history` (`FBIN` → `:FBHS`, `GAP` → `:GPS`); otherwise it keeps its literal and is
counted. The 2026-11-04 dry runs report 0 unlinked ranking/veto rows (before: 34/0/2 and 9/2/3),
321,324 / 309,728 / 342,934 triples for P1/P2/P3, and each graph is SHACL-conformant.

Write after a clean dry run with `--write`; the production repository also needs
`--to-production`, and an existing graph is reported and skipped rather than appended to.

## 6. Verify the store against the source

Run once per graph. The verifier reads only `SELECT` queries, so it is safe against any repository,
including production. It prints the repository and graph first, then one `PASS`/`FAIL` line per
check:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:rule:P1:1 \
  --db data/backtests/rule_P1.db \
  --label rule
```

Repeat with `...rule:P2:1`/`rule_P2.db` and `...rule:P3:1`/`rule_P3.db`. Exit 0 means every check
passed; exit 1 means at least one `FAIL` line (or the source/store could not be read); exit 2 means
a bad argument. The header's `repository:` line is the proof of *which* repository was checked:
compare it with the `KG_REPOSITORY` you intended.

The checks are: graph name and stored run identity; total triples against the deterministic
re-projection; one individual per source row for each of the eight classes; distinct
`:holdingAsset`/`:guardAsset` tickers and the unlinked-row ceiling; GuardAlert groups by
rule/layer/state; GuardAction by status; last NAV per arm; CASH rows; `:runLabel` through the book;
and `:knowledgeDate`. A `FAIL` is a real difference, not a warning; investigate before calling the
load done.

## 7. Record the numbers

Add a dated row to [`graphdb-setup.md`](graphdb-setup.md)'s "Verifying a loaded backtest" table (or
a new "Live load record" section) with:

- date, repository, and the operator;
- each graph IRI and its triple count from the write (or from `verify_backtest`);
- the `v_book_weight_daily` row count and the other seven view counts from the dry run;
- the `verify_backtest` result (all checks passed, or the failure lines);
- any `asset link omitted` counts and why (ticker absent from the catalog).

The 2026-11-04 reference dry runs, for comparison: P1 15,615 `v_book_weight_daily` rows and
209,886 triples; P2 15,641 and 196,840; P3 18,025 and 222,449; 0.66–0.73 GB peak RSS and 44–48 s
per database. The reference/process dry run over the same P1 database reads 21 `v_ticker_history`
rows, 0 orchestrator runs and 0 steps; it builds one snapshot graph and reports 17 exact + 4 same-CIK
asset links (0 unlinked). The selection dry runs after the same-CIK rule build 321,324 / 309,728 /
342,934 triples for P1/P2/P3 with 0 unlinked ranking/veto rows (before: 34/0/2 and 9/2/3). A final
load with different data will differ; record what you measured.

## 8. Roll back exactly one graph

A backtest graph is append-only audit data. Drop one **only** when it was written incorrectly or
into the wrong repository, and only after deciding the loss is acceptable. Export it first if you
need a copy. In the GraphDB Workbench, against the intended repository, run exactly:

```sparql
DROP GRAPH <urn:graph:derived:backtest:rule:P1:1>
```

(Or the equivalent one-graph `DROP GRAPH` through the repository's `/statements` endpoint.) Never
use `CLEAR ALL`, `DROP ALL`, `DROP DEFAULT`, a repository delete, or a graph IRI other than the one
you are rolling back. After the drop, a `--write` of the same source and label can create the graph
again; the verifier should then pass. If only one arm or one file is wrong, still drop the whole
graph and re-project that database; never patch triples inside it.

## 9. Common failures

| Message / symptom | Meaning and action |
|---|---|
| `run label 'Rule' does not match ...` (exit 2) | The label must be lower-case, start with a letter, then letters/digits/underscore, 2–32 characters. Use e.g. `rule`, not `Rule`. |
| `--to-production only matters with --write` (exit 2) | Remove `--to-production` from a dry run. |
| `--write to the production repository needs --to-production` (exit 2) | You are writing to `KG_REPOSITORY=portfolio`; the maintainer must approve, then add `--to-production`. |
| `window_id 'Q1' does not match P[0-9]+` / gate refuses the graph | The source's window is not a `P<number>`. This is a bad input, not a label problem; do not edit the database. |
| `graph ... already exists` / `already in the store: ...` | Append-only: the graph was written before. Nothing was appended. Use a new label (§3); do not drop the old graph to reuse its name. |
| `asset link omitted: v_book_weight_daily: N` or `unlinked v_book_weight_daily: N stored, M reported` | The store or catalog lacks a ticker. The projector keeps `:holdingKey`/`:guardTicker` and counts it. For the supported path, use a fresh repository whose catalog includes the ticker; the current loader cannot extend an existing catalog (§1b). Do not add an `:Asset` by hand to the backtest graph. |
| `holding links: X stored, Y expected` / `guard links: ...` | The store's linked tickers differ from the source. Check that the catalog graph is the one you loaded and that `SQL_UNIVERSE_DB` is the same file used for the dry run. |
| `individuals <Class>: X stored, Y source rows` | A class count differs. Check `--label` and the graph name first; if they match, the graph was not built from this database. Re-project under a new label rather than editing the graph. |
| `last NAV per arm` / `GuardAlert by rule, layer and state` / `GuardAction by status` / `CASH rows` fails | The graph holds different values/groups from the source. Re-run the dry run against the same copied database; if it differs, the wrong graph or a stale source is being verified. |
| `source error: ...` (exit 1) | `--db` is missing, is not a completed m018 database, or lacks the eight views. Check the path and the contract check (§2). |
| `STOPPED ... schema_version` / `not 'completed'` | The source is below the v18 floor or its run is not completed. Use the final completed database; do not lower the floor. |
| `store error: cannot reach GraphDB ...` | `KG_HOST` is wrong. From the dev container use `http://host.docker.internal:7200`; `localhost` is the container. |
| The verifier header names the wrong repository | `KG_REPOSITORY` (or `.env`) points elsewhere. Shell environment wins over `.env`; fix it and re-run the read-only verifier. If a graph was written to the wrong repository, drop only that one graph there (§8), never production. |
| `DRIFT` from `cli/check_view_contract.py` | The pin and the new database disagree. Stop and re-pin (T-157/T-173); do not project. |
| `v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to write` | Expected for the completed P1/P2/P3 databases: the two m015 views are empty. The ticker-history snapshot is still built and validated; there is no orchestrator graph to write. |
| `canonical_symbol '...' is not the latest symbol` from `cli/project_reference.py` | The ticker-history view and the catalog disagree about a CIK line. Stop and report the CIK; do not edit the database or guess an asset. |
| `asset link omitted: v_ticker_history: N` | No exact symbol and no unique same-CIK asset. The history row is kept, the property is unset, and the row is counted; never add an `:Asset` by hand. |
| `already in the store: urn:graph:derived:ticker-history:...` | The snapshot date/label was used before. Choose a new `--as-of` date (or label); do not drop and rewrite the old snapshot. |
