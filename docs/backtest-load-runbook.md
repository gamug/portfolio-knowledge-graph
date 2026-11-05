# Backtest load runbook

Copy-pasteable procedure for the final backtest: load a delivery of six date-ordered window
databases into their append-only graphs (m018, selection and one metadata graph per label) and
prove that the store matches the source and the delivery's `SHA256SUMS`. The one-command path is
`cli/load_run.py`; the older step-by-step commands remain as the manual fallback. Everything here
is read-only except the explicitly marked write steps (`cli/load_universe.py --write` or
`--delta --write`, `cli/project_backtest.py --write`, `cli/project_selection.py --write` and
`cli/load_run.py --write`); the verifier never writes.

The verifier's checks are in `SPEC.md` FR-009, the one-command load is FR-011, the graph naming
and projectors are in `SPEC.md` §2.6 and `docs/07-ontology-topology.md`, and the measured
reference numbers are in [`graphdb-setup.md`](graphdb-setup.md). Work item 24 built the first
verifier and this runbook; Work item 29 extended both to the selection side; Work item 35 added
the six-window delivery, the integrity manifest, the configuration and the metadata graph.

## 0. What "loaded" means

One delivery has six contiguous windows, in this chronological order (never by window name):
`P1`, `H1`, `P3`, `H2`, `P2`, `H3`. Any subset is valid (the pilot has `P1`–`P3`); a delivery adds
one `:BacktestRun` per window to the label's metadata graph. One completed database becomes
**two data graphs** per backtest run:

```text
urn:graph:derived:backtest:{label}:{window_id}:{backtest_run_id}
urn:graph:derived:backtest:selection:{label}:{window_id}:{backtest_run_id}
```

and the whole delivery adds **one metadata graph** per label:

```text
urn:graph:derived:backtest:meta:{label}
```

The metadata graph holds one `:BacktestRun_{label}_{window}` per window (source file, verified
lowercase SHA-256, run id, window id, knowledge date and a configuration link) and one
`:RunConfiguration_{label}` with the required `code_commit`, `pr` and `results_doc`, the optional
`config_id` and `status`, and the frozen configuration body in `rdfs:comment`. It is written last,
after every m018 and selection graph, and is verified read-only.

The label is yours (`rule`, `champ_v1`, …), the window and run id come from `v_book`. The label is
also part of every individual IRI, so two result families never share an individual. Both graphs
are append-only: once written, they are never edited or appended to. The selection graph is a
sibling, not a replacement: an already-written m018 graph is neither a target nor rewritten.

The m018 graph holds the eight backtest/GUARD views; the selection graph holds the six selection
views (`v_cycle_run`, `v_weight_scheme`, `v_weight_component`, `v_cycle_ranking`,
`v_cycle_ranking_component`, `v_veto`). The verifier's cross-graph check proves that every
`:cycleRunId` on a TOPN `BookRebalance` in the m018 graph has its `SelectionCycle` in the
selection graph; `MARKOWITZ_BASE` and `MARKOWITZ_BASE_GUARD` have none on purpose.

The read side is [`reports-agent-query-catalog.md`](reports-agent-query-catalog.md). Every query
there takes the run label and the window (and the arm where relevant) as parameters; its discovery
queries list the labels, date-ordered windows, arms, rebalance dates and decision/warm-up cycles
that a loaded store holds. The catalog shows the core ETF `SPY` as `ETF núcleo`, never as an
unclassified asset, and it publishes only aggregates (no per-asset price, return, veto evidence or
Basing Points threshold).

The same database also carries the three remaining Contract v18 views. They are projected
separately by `cli/project_reference.py` into:

```text
urn:graph:derived:ticker-history:{label}:{snapshot_date}   # one complete snapshot
urn:graph:derived:orchestrator:{label}:{run_id}            # one graph per run
```

A ticker-history snapshot is labelled and dated, and every IRI carries both, so a later refresh is
a new graph with new individuals, never a re-declaration. An orchestrator run is immutable; a
later run is a new id and a new graph. Both are append-only like the backtest graph.

## 1. One-command flow (recommended)

`cli/load_run.py` runs the backtest procedure in order and stops at the first failure. The
reference/process graphs (`cli/project_reference.py`, §5a) are a separate stream and are not part
of this command:

1. discover the delivery's `<label>_<window>.db` files, reject any window outside
   `P1/H1/P3/H2/P2/H3`, and verify `SHA256SUMS` by streaming every database in 1 MiB chunks
   **before any database is opened for its rows**;
2. read `config_<label>.md` and build the one metadata batch (front matter strings plus the body
   verbatim);
3. optional view-contract check (`--contract`);
4. dry run of both projectors and SHACL validation of the metadata batch (rows, triples, unlinked
   counts; no store contacted);
5. the read-only pre-flight: `gate.plan` for **every** m018 and selection graph and the metadata
   graph, with the store's real context and `SELECT` only. A refused graph stops the command
   before anything is written; a graph already in the store is reported and skipped;
6. with `--write`, the plans the pre-flight already computed, applied with `gate.write` (all m018
   graphs first, then the selection siblings, then the metadata graph); the free-disk guard runs
   before the run and between windows, and a window over 30 minutes is listed as
   `STOP AND ASK upstream`;
7. the read-only verifier for **every** m018 and selection graph, then the metadata verifier
   (stored hashes equal the manifest, one configuration, every window has its run and links to it);
8. a final table of graph, stored triples, status and checks passed.

The window order is chronological by each database's `v_book.d_start`/`d_end`; `P3` precedes
`P2`. `--windows P1,H1` requires those windows to be present. `--check-store` runs steps 1–5 and
the pre-flight report only, and writes nothing; it is the one-command form of the per-projector
pre-flight in §4a and refuses `--write` and `--to-production`.

### 1a. Prerequisites

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

The store's shapes must know `:runLabel`, the open `P<number>`/`H<number>` window vocabulary and the selection
terms (T-233/T-234, Work item 26). Reload after any `schema/` change:

```bash
uv run python cli/load_schema.py
uv run python cli/verify_store.py
```

`verify_store` must exit 0. If it reports `urn:graph:tbox: expected N, store has M`, stop and reload
the schema; do not load a backtest against a stale store.

The delivery folder must contain the six `<label>_<window>.db` files, the `SHA256SUMS` manifest in
sha256sum format (lowercase hash, two spaces, file name) and `config_<label>.md` (front matter plus
body; §1e). A delivery is refused when a file named in `--windows` is absent, when a file names an
unknown window, when a manifest entry is missing or does not match, or when the configuration
label differs from `--label`. The pilot folder has neither delivery file; it uses the explicit
`--no-manifest --no-config` legacy mode and builds no metadata graph.

Check free disk space on the mounted data directory before a write. GraphDB refuses every write
when the data disk has less than 5% free (HTTP 500, "Critically low disk space"), so keep several GB
beyond the 5% line:

```bash
df -h /workspaces/thesis
```

GraphDB 11.5.1 exposes no free-disk value on its read-only REST surface (checked against the live
store; `/rest/locations` has no space fields and `/rest/monitor/structures` carries cache/query
metrics, not disk). `cli/load_run.py` therefore prints a `df -h` reminder before `--write` and
refuses to continue below `--min-free-pct` only when a value is exposed; the default is 8 and the
hard floor is 5. A probed value, when a later GraphDB exposes one, is printed before the run and
between windows. If the directory is backed by a Docker Desktop virtual disk, trim and compact it
as `docs/graphdb-setup.md` records before retrying.

### 1b. Load the asset catalog once, then extend it with deltas

Before any backtest that links `:Asset` nodes, and **before the first backtest write** (replace
`2026-11-04` with the day of your load; it is the date of the reference run), write the whole
catalog once:

```bash
# dry run first: reads SQL_UNIVERSE_DB, builds and SHACL-validates, contacts no store
uv run python cli/load_universe.py --as-of 2026-11-04
# then the one full write:
uv run python cli/load_universe.py --as-of 2026-11-04 --write
# production also needs the explicit opt-in:
uv run python cli/load_universe.py --as-of 2026-11-04 --write --to-production
```

The full loader writes all `:Asset`, `:Universe` and `:UniverseMembership` individuals into
`urn:graph:universe:{year}-Q{n}`. That graph is the catalog's one-time boundary and is never
appended to again: a second full load into the same quarter is refused because the graph exists
(gate check 2), and a full load into a later quarter re-declares the same `:Asset`/`:Universe`
typed individuals and is refused by check 6 even if no value changed. A new quarter alone does not
make a reload possible.

**After the first load, use `--delta` for every catalog refresh.** It reads the source with the
loader's own `--since` and `resolve_assets` and the store with `SELECT` only, then writes just the
four-category difference:

```bash
# dry run: reports the categories, the drift list, the target graph and the full gate pre-flight
uv run python cli/load_universe.py --delta --as-of 2026-11-04
# write the actionable delta (empty delta = no write):
uv run python cli/load_universe.py --delta --as-of 2026-11-04 --write
# production also needs the explicit opt-in:
uv run python cli/load_universe.py --delta --as-of 2026-11-04 --write --to-production
```

The categories are: **new assets** (with their stints), **new memberships of a stored asset** (a
re-entry, or a symbol of a renamed company that still folds into the stored asset by CIK),
**closures** (only the closing `:validTo` triple of a stored open membership), and **drift**
(reported, never applied). Drift covers a changed company name, CIK or `:classifiedAs` (the store's
only sector/sub-industry fact), a stored membership with other dates or `membershipAsset`, a stored
closed membership whose source stint is open, and a stored membership or non-reference asset absent
from the source. Nothing is deleted, no stored value is rewritten, and the existing catalog graph
is never dropped. The reference dry run (2026-11-04, read-only) over `portfolio_test` with the
catalog's own `/workspaces/thesis/data/universe_history_gics.db` printed 0 new assets, 0 new
memberships, 0 closures and 0 drift; a temporary copy with one new symbol and one closed open stint
printed exactly 1/1/1/0. Use the empty result as the sanity check that the store and the source are
in sync before a backtest write. A non-empty dry run also runs `gate.plan` -- the same graph
existence (check 2), stored-individual (check 6) and closing-state (check 7) checks the write runs
-- and prints `pre-flight: would-be-written` or `pre-flight: already-in-the-store (skipped)`; a
refusal stops before writing.

The delta goes into `urn:graph:universe:{year}-Q{n}:delta:{n}`, where `{n}` is the next free
positive sequence for that quarter; each later delta gets the next number. It re-declares no stored
typed individual, so gate check 6 does not fire, and a closure is only the untyped `:validTo` path
(check 7). The run is idempotent: right after a `--write`, a second run prints an empty delta and
writes nothing. A store with no `:SP500Index` membership catalog is refused with a pointer to the
full load, and a `reference.ttl` asset missing from the store is refused with a pointer to the
schema load. If the store's catalog came from the same `universe.db`, the delta is empty by
definition; a non-empty result means either the source moved or the store carries drift.

Do not drop or rewrite the universe graph, hand-edit an `:Asset`, or bypass the gate. If drift
needs a real correction (not just a new membership), stop and open a task for a new graph/version;
the append-only store keeps both values.

### 1c. Copy the delivery folder

The inputs are read-only; work on copies so a later source refresh cannot change what you verified.
Copy the whole delivery, including `SHA256SUMS` and `config_<label>.md`, into one folder (the
manifest is looked up in that folder):

```bash
mkdir -p data/backtests
cp /path/to/delivery/SHA256SUMS data/backtests/
cp /path/to/delivery/config_final.md data/backtests/
cp /path/to/delivery/final_*.db data/backtests/
ls -l data/backtests/
```

For a candidate rehearsal use its own folder and label, for example `candidate`; production
receives only the `final` label. The pilot delivery is the older three-window folder
`/workspaces/thesis/scratch/final/runs/` (`rule_P1.db`–`rule_P3.db`) and needs the legacy flags.

`SQL_UNIVERSE_DB` must point at the catalog you loaded (for the full 2026-11-04 catalog,
`/workspaces/thesis/data/universe_history_gics.db`).

### 1d. Run it

The rehearsal is a candidate delivery; the delivery is the `final` one. Use the same commands,
changing only the folder and label:

```bash
# 1. candidate rehearsal: dry run (no store contacted), then read-only pre-flight
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label candidate --dir data/candidate --check-store

# 2. final delivery: dry run and pre-flight first
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests --check-store

# 3. write, only after the dry run and the pre-flight are clean
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests --write

# 4. production, only with the maintainer's explicit go-ahead and only the final label
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests --write --to-production
```

`--windows P1,H1,P3,H2,P2,H3` requires all six; omit it for any subset. The pilot folder has no
manifest or configuration, so its read-only check is the explicit legacy form:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label rule --dir /workspaces/thesis/scratch/final/runs \
  --no-manifest --no-config --check-store
```

A delivery folder with a manifest or configuration is never loaded with those flags: the command
refuses to ignore a present file. Explicit `--db PATH` remains available for a legacy folder, but
the delivery path is `--dir`. Add `--contract /path/to/portfolio-financial-analysis` (or its API
URL) to run the pinned view-contract check before anything is read; a `DRIFT` line stops the
command. Writing to `KG_REPOSITORY=portfolio` still needs `--to-production`; without it the command
exits 2 before any graph is written. **Production receives only the `final` label; `rule` and
`candidate` are rehearsal/pilot families.**

### 1e. The delivery files

`SHA256SUMS` is sha256sum format: 64 hex digits, two spaces, then the file name. The loader
stream-hashes every database to load in 1 MiB chunks and prints the time per file; hashes are
compared case-insensitively and stored lowercase. A missing entry, a missing file or a mismatch
prints the file, the expected hash and the actual hash and stops before any database is read. The
manifest is never ignored.

`config_<label>.md` starts with a `---` front matter and a closing `---`, one blank line, then the
English prose body. Required keys are `label`, `code_commit`, `pr` and `results_doc`; optional keys
are `config_id` and `status`; any other key is a warning. Every scalar stays a string, so
`pr: 192` and `code_commit: 537e864` keep their spelling. The body is stored byte for byte
(hard line breaks included) in `:RunConfiguration`'s `rdfs:comment`. The front-matter `label` must
equal `--label` and the file name; a missing required key, an empty value, an empty body or a label
mismatch stops the run. Do not commit a real configuration file to this repository.

A dry run ends with a table like this (the status and checks columns say `not checked` because no
store was contacted):

```text
graph                                                              triples  status                  checks
urn:graph:derived:backtest:rule:P1:1                                  209,886  not checked (dry run)   not verified (dry run)
urn:graph:derived:backtest:selection:rule:P1:1                        321,324  not checked (dry run)   not verified (dry run)
```

`--check-store` prints the pre-flight's per-graph status (`would-be-written`,
`already-in-the-store` or `refused`) and the same table; it contacts the store with `SELECT` only
and never writes.

A write run repeats the dry-run counts, runs the pre-flight for every graph, and only after every
graph is accepted applies those plans (all m018 graphs first, then the selection siblings, then the
metadata graph). It then runs the verifier for every graph and prints its `PASS`/`FAIL` lines and a
table with the stored triple count, the status and the number of checks passed. Exit 0 means every stage passed. A
refused pre-flight exits 1 with nothing written and lists each refused graph and the gate's
message. A verification failure stops the run and prints the exact one-graph `DROP GRAPH <iri>`
commands for the graphs this run wrote (see §9); the command itself never drops anything. A store
error after the pre-flight names the graphs written, the graph in doubt (if any) and the same
one-graph drops.

## 2. Manual fallback: check the pinned view contract

Before reading the new database, confirm its views still match `src/projection/view_contract.py`:

```bash
# against an upstream checkout...
uv run python cli/check_view_contract.py /path/to/portfolio-financial-analysis
# ...or against its running contract endpoint:
uv run python cli/check_view_contract.py http://HOST:PORT/api/v1
```

A `DRIFT` line or a non-zero exit means the database and this repo's pin disagree: stop and re-pin
(T-157/T-173), do not project around a changed view.

## 3. Manual fallback: choose the label

The label names the result family and is part of both data graph names, the metadata graph and
every IRI:

```text
[a-z][a-z0-9_]{1,31}
```

Use `final` for the delivery; `candidate` is the rehearsal and `rule` is the pilot family.
Production receives only `final`. A missing or malformed label exits 2 before anything is read.
The graph names are fixed by `v_book.window_id` and `v_book.backtest_run_id`; for the completed
databases the dry run below prints them, e.g.
`urn:graph:derived:backtest:final:P1:1`,
`urn:graph:derived:backtest:selection:final:P1:1` and
`urn:graph:derived:backtest:meta:final`.

**A new run needs a new label when the graph name would repeat.** Re-projecting the same database
under `rule`/`P1`/`1` targets the same graphs and the gate refuses them (append-only). Do not drop
the old graphs to reuse the names: write the new family under a different label (for example
`rule2` or `rule_20261105`), which gives it fresh graphs and fresh IRIs. A genuinely new upstream
run normally has a new `backtest_run_id`, so the same label already produces new graph names; use
the dry run to confirm.

## 4. Manual fallback: dry run both projectors

The default of each projector is a dry run: it reads every database, runs the boundary, builds
each graph and SHACL-validates it beside the rules and universe assets. It contacts no store and
writes nothing.

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_selection.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db
```

Expect exit 0 and one `graph: urn:graph:derived:backtest:{...}: <triples> triples` line per
database in each run, plus `SHACL-valid, not written`. Read the `rows:` lines and the
`asset link omitted: ...` lines; record both. A non-empty asset-link count is expected when the
catalog lacks a ticker (see §1b). Stop on `STOPPED`, `rejected`, or a missing view.

## 4a. Check the live store (read-only pre-flight)

The local dry run cannot see the store. `--check-store` runs the **same `gate.plan` the real write
uses**, with `SELECT` queries only: the shape/context validation, the append-only target's
existence (gate check 2), the typed individuals already stored (check 6) and the closing-state
checks (check 7). It prints one of three results for each graph:

- `would-be-written`: the graph is new and every gate check passed;
- `already-in-the-store`: the append-only graph exists, so the write skips it;
- `refused`: the same rejection the write would hit; stop and fix it before writing.

It writes nothing, so it needs neither `--write` nor `--to-production`; those flags are refused
with it.

For the final backtest, the one-command form verifies the delivery files and plans every m018,
selection and metadata graph in one pass, and refuses to write anything if any graph is refused:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests --check-store
```

The per-projector commands below remain useful when only one side is in question. The examples use
the pilot's `rule`/P1–P3 files; a delivery uses `final` and its six windows. These commands do not
write the metadata graph. Run them for both backtest sides and the reference snapshot:

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

A `refused` line is the same failure the write would hit: stop and fix the gate/context before
writing. The 2026-11-04 read-only run against `portfolio_test` accepted all seven graphs (six
backtest graphs and the ticker-history snapshot); with this pre-flight they report
`would-be-written`, or `already-in-the-store` when the graph was written earlier. This step is
exactly what catches a relation whose context fetch is too narrow, a target graph that already
exists, an individual that is already stored or a closing triple the store cannot take; the local
dry run cannot see any of them.

## 5. Manual fallback: write (only after the dry runs are clean)

For a scratch repository, or for production after the maintainer's decision:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --write

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_selection.py \
  --db rule=data/backtests/rule_P1.db \
  --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --write
```

Writing to `KG_REPOSITORY=portfolio` additionally requires `--to-production` on each command;
without it the run exits 2 before building anything, because a backtest is a frozen artifact and
where it lives is the maintainer's decision:

```bash
# production, only with the maintainer's explicit go-ahead
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_backtest.py \
  --db rule=data/backtests/rule_P1.db --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --write --to-production

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/project_selection.py \
  --db rule=data/backtests/rule_P1.db --db rule=data/backtests/rule_P2.db \
  --db rule=data/backtests/rule_P3.db --write --to-production
```

`written: <graph>: <n> triples` is the record. `already in the store: <graph>` means that graph
was left untouched (nothing was appended); use a new label (§3) if this was meant to be a new
family. The gate also refuses an existing graph, so a second write can never mutate the first. Write
all m018 graphs before the selection graphs so a selection verification can always find its m018
sibling. These two commands do **not** write the metadata graph: only `cli/load_run.py` reads the
delivery manifest/configuration and writes `urn:graph:derived:backtest:meta:{label}`. For a
delivery, use the one-command path (§1d) rather than the manual fallback.

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

## 6. Manual fallback: verify every graph
Run once per graph. The verifier reads only `SELECT` queries, so it is safe against any repository,
including production. It prints the repository and graph first, then one `PASS`/`FAIL` line per
check:

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:rule:P1:1 \
  --db data/backtests/rule_P1.db \
  --label rule

SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:selection:rule:P1:1 \
  --db data/backtests/rule_P1.db \
  --label rule
```

Repeat with `...P2:1`/`rule_P2.db` and `...P3:1`/`rule_P3.db` on both sides. Exit 0 means every
check passed; exit 1 means at least one `FAIL` line (or the source/store could not be read); exit 2
means a bad argument. The header's `repository:` line is the proof of *which* repository was
checked: compare it with the `KG_REPOSITORY` you intended.

The m018 checks are: graph name and stored run identity; total triples against the deterministic
re-projection; one individual per source row for each of the eight classes; distinct
`:holdingAsset`/`:guardAsset` tickers and the unlinked-row ceiling; GuardAlert groups by
rule/layer/state; GuardAction by status; the `nGuardActions` rule (each summary's stored value
equals the `APPLIED` guard actions of that book whose `decision_date` is inside
`[dateFrom, dateTo]`, from both the source and the graph, so an action decided before the segment
and effective on its first day stays out); the Basing Points publication check (the `L1_BP_*` alert
count equals the source and none has `:alertThreshold`); last NAV per arm; CASH rows; `:runLabel`
through the book; and `:knowledgeDate`. A `SPY` holding/alert/action links to `:SPY` from
`urn:graph:reference` by the exact-symbol rule; it is not counted as unlinked.

The selection checks are: graph name and stored cycle identity; total triples; one individual per
projected source row for `SelectionCycle`, `AttractivenessSnapshot`, `AttractivenessWeightScheme`,
`Veto`, and the configured/effective `WeightComponent` links; the UNSCORED/UNPRICED placeholder
count; `:attractivenessOfAsset`/`:vetoOfAsset` links and the unlinked-ticker ceiling; vetoes grouped
by resolved rule; and the cross-graph check that every TOPN `BookRebalance` cycle in the m018 graph
has its `SelectionCycle` in the selection graph (the `MARKOWITZ` arms have none). A `FAIL` is a real
difference, not a warning; investigate before calling the load done.

The metadata verifier runs inside `cli/load_run.py` after the data graphs, read-only: it proves
the graph name, its exact triple count, one `:BacktestRun` per window, exactly one
`:RunConfiguration`, every run's link to it, and each window's stored `:sourceSha256`,
`:sourceFile`, `:knowledgeDate` and `:backtestRunId` against the verified delivery. The
configuration fields and the `rdfs:comment` body are compared with `config_<label>.md`.

## 7. Reference numbers

Read-only dry runs on 2026-11-04 over the completed databases in
`/workspaces/thesis/scratch/final/runs/`, measured with `cli/load_run.py` (both projectors, no store
contacted). Time and peak RSS are for the whole one-command dry run:

| Database | `v_book_weight_daily` rows | m018 triples | Selection rows | Selection triples | Time | Peak RSS |
|---|---|---|---|---|---|---|
| `rule_P1.db` | 15,615 | 209,886 | 42,700 | 321,324 | 93.2 s | 1.16 GB |
| `rule_P2.db` | 15,641 | 196,840 | 41,259 | 309,728 | 90.2 s | 1.10 GB |
| `rule_P3.db` | 18,025 | 222,449 | 45,440 | 342,934 | 101.0 s | 1.22 GB |

Unlinked tickers: 0 ranking and 0 veto in every database after the shared CIK-aware link rule. A
final load with different data will differ; record what you measured.

## 8. Record the numbers

Add a dated row to [`graphdb-setup.md`](graphdb-setup.md)'s "Verifying a loaded backtest" table (or
a new "Live load record" section) with:

- date, repository, and the operator;
- each graph IRI and its triple count from the write (or from `verify_backtest`);
- the `v_book_weight_daily` row count and the other view counts from the dry run;
- the selection row/triple counts and the two verifier results (all checks passed, or the failure
  lines);
- any `asset link omitted` counts and why (ticker absent from the catalog).

The 2026-11-04 `portfolio_test` load is recorded under "Live load record, portfolio_test,
2026-11-04" in `graphdb-setup.md`.

The 2026-11-04 reference dry runs, for comparison: P1 15,615 `v_book_weight_daily` rows and
209,886 triples; P2 15,641 and 196,840; P3 18,025 and 222,449; 0.66–0.73 GB peak RSS and 44–48 s
per database. The reference/process dry run over the same P1 database reads 21 `v_ticker_history`
rows, 0 orchestrator runs and 0 steps; it builds one snapshot graph and reports 17 exact + 4 same-CIK
asset links (0 unlinked). The selection dry runs after the same-CIK rule build 321,324 / 309,728 /
342,934 triples for P1/P2/P3 with 0 unlinked ranking/veto rows (before: 34/0/2 and 9/2/3). A final
load with different data will differ; record what you measured.

The 2026-11-05 read-only re-check (Work item 35) processed the same pilot folder in the required
chronological order (`P1`, `P3`, `P2`); the explicit `--check-store --no-manifest --no-config` run
against `portfolio_test` reported the six m018/selection graphs as `already-in-the-store`. No
GraphDB write or reload was made.

## 9. Roll back exactly one graph

A backtest graph is append-only audit data. Drop one **only** when it was written incorrectly or
into the wrong repository, and only after deciding the loss is acceptable. Export it first if you
need a copy. In the GraphDB Workbench, against the intended repository, run exactly one of:

```sparql
DROP GRAPH <urn:graph:derived:backtest:rule:P1:1>
```

```sparql
DROP GRAPH <urn:graph:derived:backtest:selection:rule:P1:1>
```

The one metadata graph of a label is dropped the same way, and only when that whole label is being
retired from this repository:

```sparql
DROP GRAPH <urn:graph:derived:backtest:meta:final>
```

(Or the equivalent one-graph `DROP GRAPH` through the repository's `/statements` endpoint.)
`cli/load_run.py` prints these exact commands for the graphs it wrote when a verification fails or
a write fails after the pre-flight; a graph listed as *in doubt* is not included, because the store
may not hold it. The command never runs a drop itself. Never use `CLEAR ALL`, `DROP ALL`,
`DROP DEFAULT`, a repository delete, or a graph IRI other than the one you are rolling back. After the drop, a `--write` of the same
source and label can create the graph again; the verifier should then pass. If only one arm or one
file is wrong, still drop the whole graph (and its selection sibling when the failure is on that
side) and re-project that database; never patch triples inside it.

## 10. Common failures

| Message / symptom | Meaning and action |
|---|---|
| `run label 'Rule' does not match ...` (exit 2) | The label must be lower-case, start with a letter, then letters/digits/underscore, 2–32 characters. Use e.g. `rule`, not `Rule`. |
| `at least one --db PATH or --dir DIR is required` (exit 2) | Give one or more explicit databases or a directory of `*_P<number>.db`/`*_H<number>.db` files. |
| `--dir ...: no *_P<number>.db or *_H<number>.db file` (exit 2) | The directory has no final-run file with that naming; use explicit `--db` paths. |
| `database given twice` / `would both write <graph>` (exit 2) | The same file or two files resolving to one graph were given. A graph belongs to one frozen run; use one database per run. |
| `--to-production only matters with --write` (exit 2) | Remove `--to-production` from a dry run. |
| `--write to the production repository needs --to-production` (exit 2) | You are writing to `KG_REPOSITORY=portfolio`; the maintainer must approve, then add `--to-production`. |
| `window_id 'Q1' does not match [PH][0-9]+` / gate refuses the graph | The source's window is not a `P<number>` or `H<number>`. This is a bad input, not a label problem; do not edit the database. |
| `graph ... already exists` / `already in the store: ...` | Append-only: the graph was written before. Nothing was appended. Use a new label (§3); do not drop the old graph to reuse its name. |
| `asset link omitted: v_cycle_ranking: N` or `unlinked v_cycle_ranking: N stored, M reported` | The store or catalog lacks a ticker. The projector keeps `:rankingTicker`/`:vetoTicker` and counts it. For the supported path, extend the catalog with `cli/load_universe.py --delta` (§1b), write the delta, then re-run the projection; a first catalog still needs the full load. Do not add an `:Asset` by hand to the backtest graph. |
| `attractiveness links: X stored, Y expected` / `veto links: ...` | The store's linked tickers differ from the source. Check that the catalog graph is the one you loaded and that `SQL_UNIVERSE_DB` is the same file used for the dry run. |
| `UNSCORED/UNPRICED placeholders` fails | A ranking row without effective weights is missing its `:vetoRulesJson` marker, or the placeholder count differs. Re-run the dry run; if it differs, the wrong graph or a stale source is being verified. |
| `vetoes by resolved rule` fails | The stored vetoes resolve to different rule IRIs than the source on the run's knowledge date. Check `schema/rules.ttl` and the graph's source database. |
| `cross-graph SelectionCycle` fails (`missing SelectionCycle for cycle N`, `MARKOWITZ_BASE has ...`, or `no BookRebalance`) | The m018 sibling is missing, was written from another source, or its TOPN rebalances point at a cycle the selection graph does not hold. Verify both graphs from the same database; write m018 first (§5). |
| `asset link omitted: v_book_weight_daily: N` or `unlinked v_book_weight_daily: N stored, M reported` | The store or catalog lacks a ticker. The projector keeps `:holdingKey`/`:guardTicker` and counts it. Extend the catalog with `cli/load_universe.py --delta` (§1b), write the delta, then re-run the projection; a first catalog still needs the full load. Do not add an `:Asset` by hand to the backtest graph. |
| `holding links: X stored, Y expected` / `guard links: ...` | The store's linked tickers differ from the source. Check that the catalog graph is the one you loaded and that `SQL_UNIVERSE_DB` is the same file used for the dry run. |
| `individuals <Class>: X stored, Y source rows` | A class count differs. Check `--label` and the graph name first; if they match, the graph was not built from this database. Re-project under a new label rather than editing the graph. |
| `last NAV per arm` / `GuardAlert by rule, layer and state` / `GuardAction by status` / `CASH rows` fails | The graph holds different values/groups from the source. Re-run the dry run against the same copied database; if it differs, the wrong graph or a stale source is being verified. |
| `source error: ...` (exit 1) | `--db` is missing, is not a completed backtest database, or lacks the views. Check the path and the contract check (§2). |
| `STOPPED ... schema_version` / `not 'completed'` | The source is below the v18 floor or its run is not completed. Use the final completed database; do not lower the floor. |
| `store error: cannot reach GraphDB ...` | `KG_HOST` is wrong. From the dev container use `http://host.docker.internal:7200`; `localhost` is the container. |
| The verifier header names the wrong repository | `KG_REPOSITORY` (or `.env`) points elsewhere. Shell environment wins over `.env`; fix it and re-run the read-only verifier. If a graph was written to the wrong repository, drop only that one graph there (§9), never production. |
| `DRIFT` from `cli/check_view_contract.py` or `--contract` | The pin and the new database disagree. Stop and re-pin (T-157/T-173); do not project. |
| `refused: <graph>` from `--check-store` | The pre-flight's `gate.plan` hit the same rejection the write would: an existing individual (check 6), a closing state the store cannot take (check 7) or a shape/context failure. Fix the source or gate; do not bypass it. |
| `pre-flight refused N graph(s); nothing was written` | `load_run.py --write` planned every graph before writing any and at least one was refused. Read each `pre-flight refused: <graph>` line and its gate message; nothing is in the store from this run. Fix the cause and re-run the pre-flight. |
| `already-in-the-store: <graph>` from `--check-store` | Append-only: the graph exists, so the write will skip it. Use a new label/date/run id if this should be a new artifact. |
| `--check-store only reads; do not combine it with --write` / `--check-store never writes; drop --to-production` (exit 2) | The read-only pre-flight refuses both write flags. Drop them and run it alone; the write is a separate command after a clean pre-flight. |
| `store error after the pre-flight: ...` from `load_run.py --write` | The write failed after every graph had been accepted. The message lists the graphs written and the one in doubt (the store's answer was lost). Use the printed one-graph `DROP GRAPH` commands only after deciding the loss is acceptable; never drop the in-doubt graph blindly. |
| HTTP 500 `Critically low disk space! ...` on a write | The GraphDB data disk is below its 5% free threshold; every write is refused. `cli/load_run.py` translates this into a stop that names the graph being written and prints its one-graph `DROP GRAPH`. Free space until there is comfortable headroom beyond 5% (`df -h /workspaces/thesis`), then re-run the pre-flight and the write. |
| `...: SHA-256 mismatch: manifest ..., actual ...` | A database changed after the manifest was made, or the wrong folder/manifest was copied. Do not edit the hash; re-copy the exact delivered file and manifest. Nothing was read or written. |
| `...: no entry in .../SHA256SUMS` | The delivery is incomplete. Add the database's manifest line from the delivery, or remove the file; a present manifest is never ignored. |
| `--dir ...: no rule_<window>.db file` / `unknown window 'Q1'` | The folder is not that label's delivery, or a file uses a window outside `P1/H1/P3/H2/P2/H3`. Do not rename a database to a convenient window; stop and ask upstream. |
| `front-matter label 'candidate' differs from --label 'final'` / `no config_<label>.md` | The configuration belongs to another label or is missing. Use the matching delivery folder; do not edit the delivered configuration. |
| `--no-manifest and --no-config go together` / `cannot ignore a present delivery file` | The pilot flags are only for a folder without delivery files. For a real delivery drop them; for the pilot pass both. |
| `STOP AND ASK upstream: P2 took ... min` | A window exceeded 30 minutes. Do not continue the delivery; report the window and timing to upstream. |
| `pre-flight refused ...: <meta graph>` | The metadata batch failed the gate (a missing field, a bad hash or an existing graph). Fix the delivery or use a new label; do not bypass the gate. |
| A `FAIL` after `load_run.py --write` | The command prints the exact `DROP GRAPH` commands for the graphs it wrote. Read the failing check, decide the loss is acceptable, then drop only those graphs (§9) and re-project from the same copied database. |
| `v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to write` | Expected for the completed P1/P2/P3 databases: the two m015 views are empty. The ticker-history snapshot is still built and validated; there is no orchestrator graph to write. |
| `canonical_symbol '...' is not the latest symbol` from `cli/project_reference.py` | The ticker-history view and the catalog disagree about a CIK line. Stop and report the CIK; do not edit the database or guess an asset. |
| `asset link omitted: v_ticker_history: N` | No exact symbol and no unique same-CIK asset. The history row is kept, the property is unset, and the row is counted; never add an `:Asset` by hand. |
| `already in the store: urn:graph:derived:ticker-history:...` | The snapshot date/label was used before. Choose a new `--as-of` date (or label); do not drop and rewrite the old snapshot. |
