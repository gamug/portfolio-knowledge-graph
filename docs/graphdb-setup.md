# GraphDB deployment — setup and connection

How the triple store behind this ontology is run and reached. Task trail: T-020 (choice), T-022
(reasoning profile), T-024 (this document). The reasoning rationale lives in
[`07-ontology-topology.md`](07-ontology-topology.md) ("Reasoning profile"); this file only records
how it is configured.

## Choice

GraphDB Free 11.5.1 (`ontotext/graphdb:11.5.1`), run as a Docker container on the host, outside the
devcontainer. Repository id `portfolio`.

## Run it

The home directory is bind-mounted so that the repository, users and licence survive container
recreation (`THESIS_HOST_DIR` is the same host variable `.devcontainer/devcontainer.json` uses):

```bat
docker run -d --name portfolio -p 127.0.0.1:7200:7200 -v "%THESIS_HOST_DIR%:/opt/graphdb/home" ontotext/graphdb:11.5.1
```

(Windows `cmd` syntax; in bash use `"$THESIS_HOST_DIR"`.) Port 7200 is bound to the host's loopback
only, which is what was tested: Docker Desktop (WSL2) forwards `host.docker.internal` to it.

On a **native Linux** Docker host that name resolves to the bridge gateway, not loopback, so the
loopback bind is unreachable from the devcontainer. Do not widen it to `0.0.0.0` (that exposes the
store on every interface). Instead bind to the bridge address, `-p 172.17.0.1:7200:7200`, and add
`"--add-host=host.docker.internal:host-gateway"` to `runArgs` in `.devcontainer/devcontainer.json`.
This path is untested here.

On a **fresh** mount, once:

1. Open `http://localhost:7200`, register the free licence.
2. Create the repository from [`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl)
   (Setup → Repositories → Create → upload RDF config). It carries the reasoning profile.
3. Enable security (Setup → Users and Access) and create the application user `portfolio.app` with
   read, write and maintain on `portfolio` (`READ_REPO_portfolio`, `WRITE_REPO_portfolio`,
   `MAINTAIN_REPO_portfolio`; the Workbench lists these as Read / Write / Repository admin). Without repository roles the user gets 403 on every query (HTTP 401 means the login itself is rejected, so check the credentials or whether the user exists; 403 means the roles above are missing).

## Reasoning profile (T-022)

| `07` requirement | Setting |
|---|---|
| RDFS+ / OWL 2 RL-class only | `graphdb:ruleset "rdfsplus-optimized"` |
| `rdfs:subClassOf` transitivity on | included in that ruleset |
| Property chains / OWL DL off | not in that ruleset (`sharedExecutiveWith` is written explicitly) |
| `owl:sameAs` expansion | `graphdb:disable-sameAs "true"` |

OWL restrictions and `AllDisjointClasses` are **not** enforced by the store; `pyshacl` validates
them (T-023). Note: `enable-context-index` is `false`, as created; revisit if named-graph-scoped
queries prove slow.

## Loading `schema/` (T-021)

```bash
uv run python cli/load_schema.py [--dir path/to/schema] [--to-production]
```

Loads `tbox → shapes → reference → fibo → rules → instances.trig` per the graph map in
[`schema/README.md`](../schema/README.md). The production repository is the exception: it never
receives `instances.trig`'s worked-example ABox, so a production load writes only `tbox`, `shapes`,
`reference`, `fibo`, `rules` and `labels` (five graphs, 6584 asserted triples at this revision). A
`portfolio_test` or other non-production load keeps the 21 graphs and 7105 triples including the
examples. The target must be deliberate: `KG_REPOSITORY=portfolio` without `--to-production` exits
2 before any request, and `cli/verify_store.py` takes the same flag even though it only reads.
A production repository loaded before this change may still hold old example graphs: the loader
does not drop graphs it no longer loads, so list them and drop only the example graphs by hand
after a backup (never a real `urn:graph:portfolio:current` or ingest graph).

The command first drops every graph it is about to write, so a re-run (for example after a schema
edit) replaces rather than duplicates. It then parses the same files with `rdflib` and compares the
asserted triple count of each of those graphs with the store's (inferred statements excluded),
exiting non-zero on any mismatch; the counts are printed, not hard-coded here. The drops and
uploads run in one transaction, so a failed load changes nothing. Graphs that are not in `schema/`
(for example ingest graphs written later) are left alone and only counted in a closing note; a
graph removed from `schema/` has to be dropped by hand. **T-105 migration:** a repository loaded before T-105 still holds `urn:graph:ingest:QUANTITATIVE:2026-08-05`; run `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` once, or the same snapshots will exist under both `agentOrigin` values and fail `ScoreSnapshotShape`.
Needs write access (`WRITE_REPO_portfolio`). It loads `schema/` only; the ETL's `data.ttl` and
projected upstream data belong to Work item 4.

Every CLI that opens the store prints its target as the first output line, for example
`target: GraphDB http://host.docker.internal:7200 repository portfolio [PRODUCTION]`; a dry run
that never contacts GraphDB prints no banner. If `KG_HOST` or `KG_REPOSITORY` is set in the process
environment with a different value than `.env`, one warning line names the variable and both
values. Neither line ever prints `KG_USER`, `KG_PASSWORD` or another key.

## Loading the asset master (T-220)

After `schema/` is loaded (the gate validates the batch beside the stored reference individuals),
and before any batch that links `:Asset` nodes (`cli/project_backtest.py`, `cli/project_selection.py`, `cli/load_run.py`, a score projection or an
ORCHESTRATOR batch):

```bash
uv run python cli/load_universe.py                       # dry run: read, build, SHACL-validate
uv run python cli/load_universe.py --as-of 2026-11-03 --write
```

It reads `SQL_UNIVERSE_DB` (`portfolio-data-mining`'s point-in-time `universe.db`, read-only
through `portfolio_common.db`) and reuses `etl.asset_master`: the `:SP500Index` `:Universe`
(with its FIBO `rdfs:seeAlso`), one `:Asset` per company line for a pure ticker succession (or per
symbol for concurrent classes, a mixed CIK or a CIK-less stint) and one `:UniverseMembership` per
stint. The five S&P 500 `:Asset`s `schema/reference.ttl` already declares get memberships but are not re-declared (its sixth individual, the core ETF `SPY`, has no membership)
(the gate's check 6 refuses a second declaration, and `cikNumber` is functional). A membership's
`validTo` is inclusive: it is the last day of membership, and a point-in-time read on D is
`validFrom <= D AND (no validTo OR validTo >= D)`, so a member on its last day is still in and a
one-day stint is kept.

| Option | Meaning |
|---|---|
| `--since YYYY-MM-DD` | Keep a stint with no `valid_to` or `valid_to >= since` (default `2019-01-02`). A ticker reused by another company (`CEG`, `DELL`, `Q`) keeps only the era the backtests and the live index can see, and the dropped stints are counted, never silently omitted. |
| `--as-of YYYY-MM-DD` | The day the catalog is seen as of; it names the graph. Default: today in UTC. |
| `--delta` | Diff the source against the stored catalog and report/write only the incremental changes (new assets, new memberships, `:validTo` closures); drift is reported and never applied. It always opens the store read-only to diff, and a run with no actionable delta writes nothing. |
| `--write` | Append the batch through `cli/ingest.py`'s gate (`kg_store.gate.ingest`). Default: a dry run that reads, builds and SHACL-validates through `gate.validate`; the full load contacts no store, the delta reads it read-only. |
| `--to-production` | With `--write`, allow the production repository (`KG_REPOSITORY=portfolio`); without it the run exits 2 before writing, as `cli/project_backtest.py` does. A delta dry run may read production without the flag. |

The full load's target is the quarter graph `urn:graph:universe:{year}-Q{n}` computed from
`--as-of` (the gate accepts that pattern). It is not `urn:graph:reference`: `cli/load_schema.py`
drops and rewrites every graph `schema/` owns on each reload, so ABox individuals written there
would disappear, and an existing graph is never appended to. The full load is append-only and
one-time per repository: a second run into the same quarter is refused because the graph exists,
and a run into another quarter re-declares the same `:Asset`/`:Universe` individuals and is refused
by check 6. **The supported way to extend a catalog is `--delta`:** it reads `:Asset` and
`:SP500Index` `:UniverseMembership` individuals with `SELECT`, renders only the new asset blocks,
new membership blocks and closing `:validTo` triples, and appends them through the same gate into
`urn:graph:universe:{year}-Q{n}:delta:{n}` (the next free sequence for that quarter). It never
re-declares a stored typed individual, never changes a stored value and never drops a graph. Drift
(a changed name, CIK or `:classifiedAs`; a stored membership with other dates; a stored membership
or non-reference asset absent from the source) is printed and never applied. A store with no
`:SP500Index` membership catalog, or missing a `reference.ttl` asset, is refused with a pointer to
the full load/schema load. After a write, the next run's actionable delta is empty, so running it
twice is safe. A new automation still gets its own repository (Work item 17). Exit status: 0 on
success, 1 if the source, the shapes, the gate or the store stop the run, 2 on a bad argument or
the production guard. The runbook ([`backtest-load-runbook.md`](backtest-load-runbook.md)) carries
the procedure and the failure messages.

A dry run of 2026-11-04 over `/workspaces/thesis/data/universe_history_gics.db` (read-only; no
write was made) kept 657 of 891 stints over 653 symbols and dropped 234 stints of 229 symbols (214
not loaded at all, 15 with a later stint kept), wrote 648 `:Asset`s plus the five already in
`reference.ttl`, 657 memberships (503 open, 154 closed), and built 6563 triples; `gate.validate`
reported SHACL conforms in 1.2 s. The six historical GICS sub-industry strings that file carries
(`Alternative Carriers`, `Drug Retail`, `Home Furnishings`, `Household Appliances`, `Housewares &
Specialties`, `Thrifts & Mortgage Finance`) now roll up to existing `reference.ttl` groups, so the
run leaves no asset unmapped for them (6557 triples before those six mappings; 6476 was the
earlier `universe_history.db` run). Every ticker in
`v_book_weight_daily` (CASH excluded), `v_guard_alert` and `v_guard_action` of
`rule_P1/P2/P3.db` is in the loaded set (P1 100, P2 123, P3 115; 0 missing). The known overlap
with the worked example's `2026-Q3` memberships is recorded in `docs/07`.

A second dry run, 2026-11-04 over
`/workspaces/thesis/data/universe_history_gics.db` after T-260 made `validTo` inclusive (still
read-only; no write was made), kept 658 of 894 stints over 654 symbols and dropped 236 stints of
230 symbols (215 not loaded at all, 15 with a later stint kept), wrote 649 `:Asset`s plus the five
already in `reference.ttl`, 658 memberships (503 open, 155 closed), and built 6573 triples;
`gate.validate` reported SHACL conforms in 1.2 s. The three one-day stints (`PHIN` on 2023-07-05,
and `HNG`/`AYE` on 1976-06-30) are now kept by the reader; `--since` then drops the two 1976 ones.
64 written `:Asset`s carry no `:classifiedAs`: their latest stint has no GICS sub-industry at all
(the six historical values Work item 22 mapped are no longer among them). Every ticker in
`v_book_weight_daily` (CASH excluded),
`v_guard_alert` and `v_guard_action` of `rule_P1/P2/P3.db` remains in the loaded set (P1 100,
P2 123, P3 115; 0 missing).

A third dry run, 2026-11-04 after T-264 folded pure ticker successions into one `:Asset` (again
read-only; no write was made), kept the same 658 stints over 654 symbols, wrote 643 `:Asset`s plus
the five already in `reference.ttl` (648 assets from 654 symbols; six successions folded), 658
memberships (503 open, 155 closed), and built 6548 triples; SHACL conforms. 59 written assets have
no `:classifiedAs` (their latest stint has no GICS sub-industry; the fold removes five old symbols
that also lacked one). Of the 11 CIKs with more than one symbol, six are pure successions (`EG/RE`,
`WTW/WLTW`, `CPAY/FLT`, `META/FB`, `ECHO/SATS`, `DAY/CDAY`), four are concurrent classes
(`UA/UAA`, `NWS/NWSA`, `GOOG/GOOGL`, `FOX/FOXA`) and one is mixed (`DISCA`/`DISCK`/`WBD`) and
stays per symbol. The three real backtest dry runs (`cli/project_backtest.py --db rule=…` for P1,
P2 and P3) link every ticker in `v_book_weight_daily` (CASH excluded), `v_guard_alert` and
`v_guard_action`: 100, 123 and 115 distinct, 0 unlinked; the three graphs are SHACL-valid and were
not written.

**Incremental delta verification (Work item 28, read-only, 2026-11-04).** Against `portfolio_test`
with `SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db`,
`cli/load_universe.py --delta --as-of 2026-11-04` reported source 648 assets/658 memberships and
store 648 assets/658 memberships, then **0 new assets, 0 new memberships, 0 closures and 0 drift**:
the empty delta expected when the catalog came from the same file. On a temporary copy of that
database (never the original, never committed) with one new symbol (`ZZTEST`, `Systems Software`,
CIK `0002999999`, `valid_from` 2026-11-01) and one open stint closed (`DIS`, `valid_to`
2026-11-01), the same command reported exactly **1 new asset, 1 new membership, 1 closure and 0
drift** (`:ZZTEST`, `:UM_ZZTEST_2026-11-01`, `:UM_DIS_1976-07-01 validTo 2026-11-01`), target
`urn:graph:universe:2026-Q4:delta:1`, SHACL conforms. No GraphDB write was made; the first real
delta `--write` is still the maintainer's step (T-380). The full catalog write landed on
2026-11-04; see "Live load record, portfolio_test, 2026-11-04" below.

## Loading ticker history and orchestrator runs (T-208, T-352/T-353)

After `schema/` and the asset catalog are loaded, the three remaining Contract v18 views are
projected by:

```bash
uv run python cli/project_reference.py --db rule=rule_P1.db --as-of 2026-11-04        # dry run
uv run python cli/project_reference.py --db rule=rule_P1.db --as-of 2026-11-04 --write
```

`--db LABEL=PATH` is repeatable and the label reaches every graph and individual IRI. Ticker
history goes to `urn:graph:derived:ticker-history:{label}:{YYYY-MM-DD}` as a complete snapshot;
every `TickerHistory` IRI carries the label and date, so a later refresh uses a new date (or label)
and never re-declares a stored individual. Orchestrator runs go one per graph,
`urn:graph:derived:orchestrator:{label}:{run_id}`, keyed by the positive id. The production
repository also needs `--to-production` with `--write`.

`:tickerHistoryAsset` links by exact canonical symbol first, then to the one loaded `:Asset`
carrying the row's CIK (`FBIN` → `:FBHS`, `GAP` → `:GPS`); with no safe link the property is unset
and counted. No `:Asset` is created. A canonical symbol that is not the latest symbol of its CIK
stops the run. An optional `evidence_date` holding more than one date is omitted and counted;
`evidence_url` is kept verbatim.

The 2026-11-04 read-only dry runs over the completed databases:

| Database | `v_ticker_history` rows | Orchestrator rows | Ticker graph triples | Asset links (exact / by CIK / omitted) | Time | Peak RSS |
|---|---|---|---|---|---|---|
| `rule_P1.db` | 21 | 0 run, 0 step | 198 | 17 / 4 / 0 | 1.35 s | 73 MB |
| `rule_P2.db` | 21 | 0 run, 0 step | 198 | 17 / 4 / 0 | 1.42 s | 73 MB |
| `rule_P3.db` | 21 | 0 run, 0 step | 198 | 17 / 4 / 0 | 1.25 s | 73 MB |

Each ticker graph contains 21 `TickerHistory` individuals and is SHACL-conformant. The two
orchestrator views are empty in all three, so no orchestrator graph was built and the CLI printed
`v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to write`. That dry run made no
GraphDB write or reload; the live snapshot is in the record below. The pilot `financial.db` in this
checkout has no `schema_version` row (it reads 0
and is below the v18 floor), so it is not a valid v18 source; the task's `base.db`/`scored_rule.db`
paths are not present here.

## Loading the aggregates file (Work item 37)

After the m018 and selection graphs, load upstream's `aggregates_<label>.json` from the same
folder:

```bash
uv run python cli/load_aggregates.py --label final --dir /path/to/final        # dry run
uv run python cli/load_aggregates.py --label final --dir /path/to/final --check-store
uv run python cli/load_aggregates.py --label final --dir /path/to/final --write
```

The dry run checks the `SHA256SUMS` entry and hash, parses the whitelist, verifies the source
databases read-only, builds the deterministic batch and SHACL-validates it; it contacts no store.
`--check-store` runs the real `gate.plan` with the store's context and writes nothing; if the graph
already exists it also compares the stored rows with the file. `--write` appends the one graph
`urn:graph:derived:backtest:aggregates:{label}` and then runs that stored-row check. The target is
append-only: a second write of the same label is refused, and no other backtest graph is touched. A
mismatch between the manifest and the file's actual SHA-256 exits 1 and prints both hashes. There is
no daily series, price level or 210-session mean in the graph.

## Loading the external mean-variance base Markowitz (Work item 44)

The external `MARKOWITZ_MV` delivery (`aggregates_mv_base.json`, `config_mv_base.md`,
`SHA256SUMS`; `provenance/` is not required) is a separate summary-only stream:

```bash
uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base"        # dry run
uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base" --check-store
uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base" --write
```

It writes `urn:graph:derived:backtest:external:final` only: six `:StrategyBook` and eight
`:PortfolioPeriodSummary` individuals, with no daily series, weights or alerts. The engine's m018,
selection, meta and aggregates graphs are untouched, and the engine's
`urn:graph:derived:backtest:{label}:{window}:{run}` queries are unaffected. The dry run checks both
required manifest entries and hashes before parsing, and reports 8 rows / 236 triples / SHACL
conforms.

## Ingest gate (T-023)

```bash
uv run python cli/ingest.py batch.ttl --graph urn:graph:ingest:SEMANTIC:2026-08-06 [--check]
```

The sanctioned way to write an ABox batch. [`kg_store.gate`](../src/kg_store/gate.py) writes a
Turtle batch only if all of these hold, and otherwise raises `IngestRejected` (exit status 2) with
nothing written:

1. the target is named as `07` prescribes: `urn:graph:ingest:{agent}:{date}` (`FUNDAMENTAL` by
   quarter, `EDGAR` by date or quarter), `urn:graph:derived:entity-resolution:{date|quarter}`,
   `urn:graph:derived:quant:{date}`,
   `urn:graph:derived:backtest:{run_label}:{P<n>|H<n>}:{run}`,
   `urn:graph:derived:backtest:selection:{run_label}:{P<n>|H<n>}:{run}`,
   `urn:graph:derived:backtest:meta:{run_label}`,
   `urn:graph:derived:backtest:aggregates:{run_label}`,
   `urn:graph:derived:ticker-history:{run_label}:{YYYY-MM-DD}`,
   `urn:graph:derived:orchestrator:{run_label}:{positive run id}`,
   `urn:graph:universe:{year}-Q{n}` (or its `:delta:{n}` incremental suffix) or
   `urn:graph:portfolio:current` (TBox, reference and rules go through `cli/load_schema.py`);
2. an append-only graph (all but `portfolio:current`) does not exist yet;
3. every IRI is absolute and every `rdf:type` is one of the 44 leaf classes or a subclass of one (the
   `owl:AllDisjointClasses` members), so neither a typo nor a bare abstract category can dodge the
   shapes;
4. a subject with no `rdf:type` in the batch, which no shape can see, only gets relations to other
   individuals (object properties such as `:hasScoreObservation`, `:supersededBy`; the object must
   be an IRI, not a literal) or an `xsd:date` `:validTo` / `:clearedOn` (closing a record or a Veto
   stint) or `:lastSeenOn` (a cycle saw the stint); adding a value to an existing observation is refused;
5. the batch conforms to `shapes.ttl` under `pyshacl`, together with what the store holds about the
   individuals the batch points at but does not declare (T-146): a co-occurrence batch names two
   Assets and a quant batch a Portfolio, and the shapes check their class and the Portfolio's kind.
   Only the properties those classes' shapes read are fetched (for an Asset also its memberships'
   `:validTo`, which its CIK-or-closed rule reads), not the individual's snapshots. Each value keeps the
   datatype the store holds (T-181), so where a shape constrains it (`sh:datatype`, `sh:in`,
   `sh:hasValue`) a stored value of another datatype is now a SHACL failure; a string is read as a plain
   literal, as in the batches;
   A referenced individual the store does not hold fails the class check, so load the universe and
   the portfolio before the lanes that point at them;
6. no typed individual in the batch already exists in the store (explicit statements, any graph):
   a batch may only introduce new individuals, so re-declaring a stored observation with another
   value is refused. Closing a record is the untyped `:validTo` path (check 4); and
7. every closing triple closes a stored individual that is still open (T-180): the store must hold
   it, of a class the property closes (`gate.CLOSABLE`; `:validTo`: a membership, a position, a rule,
   a ticker-history or membership row or a design-history weight scheme, never a per-run one;
   `:clearedOn`: a Veto), with no value for it yet, and the batch gives it one date, later than the
   one it opened on (`:validFrom` / `:raisedOn`). For a TickerHistory or a UniverseMembership the
   interval is inclusive, so a closing date equal to the opening date is a one-day record and is
   accepted; a closure of an unknown subject, of an observation, of a record already closed or
   closed before it opened is refused. The store is read in any graph, so a new quarter's graph or
   an incremental `:delta:{n}` graph can close the previous quarter's memberships. The check reads,
   then writes: two batches closing the
   same record at once can both pass it. A Veto cleared before the latest `:lastSeenOn` is refused too
   (T-185; the same day passes), and `VetoShape` makes the same check for a Veto declared with both
   dates (one `sh:lessThanOrEquals`). A later cycle appends its `:lastSeenOn` to a
   stored Veto (T-194): the Veto must be stored and not cleared, the date not before it was raised, later
   than its latest sighting (an equal date is a replay and is refused) and not after the `:clearedOn` the
   same batch gives it, one date per batch. The gate does not enforce the spacing between cycles (at least
   15 days): a sighting one day after the last passes. The gate does not restrict the graph a sighting goes to (the closing is
   the same); Vetoes live in the ORCHESTRATOR graphs.
8. a restatement (`:supersededBy`, T-032) points from a `SECFilingSection`, stored or declared in the
   batch, to a `SECFilingSection` the same batch declares, with the same `:itemLabel` when both have
   one (no shape requires it, so an unlabelled section is not compared). A batch gives a section one
   replacement, a new section replaces one section, a section does not replace itself and no chain in
   the batch loops; the batch alone decides these, so `--check` runs them too. A stored section already
   superseded is not superseded again (the next correction replaces the latest section); the store is
   read for the old section's class, label and any `:supersededBy` it holds, in any graph. So each
   item's restatements form one chain with one current section. Limits: the label is the only tie
   between the two, and nothing checks that they belong to the same asset; and the gate does not
   restrict the graph a restatement goes to (`docs/07` scopes the rule to the graphs dated by ingestion
   and EDGAR), because it checks the restatement, not the lane.

What is written is the validated triples as N-Triples, not the submitted text. `--check` runs
checks 1, 3, 4 and 5 and the batch-only half of check 8 without contacting the store, so it cannot see an
existing graph (check 2), an existing individual (check 6), what a closing triple closes (check 7) or
whether a stored section a restatement replaces is current (check 8's other half), and a batch that points
at individuals it does not declare fails check 5 under `--check` for want of what the store holds about them (the rejection says so).

**T-206/T-207 note.** The Contract v18 ontology added `TickerHistory` to `gate.CLOSABLE` (its shape
reads `:validTo`). T-207 added the accepted backtest graph
`urn:graph:derived:backtest:{run_label}:{P<n>|H<n>}:{backtest_run_id}` to check 1; its last capture
group is a positive integer id, not a date, so `check_target` validates the label, window and id on
a separate branch instead of passing the id to `_date_ok`. The projector that writes those graphs
(`src/projection/backtest.py`, CLI `cli/project_backtest.py`) was run here as a dry run only, and
that change made no GraphDB write or reload; the store was then still pre-T-206. It was reloaded
on 2026-11-02 (T-212, below), and `verify_store` passes.

**T-231/T-234 note (run labels and the window vocabulary).** The accepted backtest graph is now
`urn:graph:derived:backtest:{run_label}:{P<n>|H<n>}:{backtest_run_id}`: the label pattern is
`[a-z][a-z0-9_]{1,31}` and the window is open to `P<number>`/`H<number>` instead of `P1|P2|P3`. The retired
unlabelled names (`urn:graph:derived:backtest:{window}:{run}`) are no longer accepted; no real data
uses them, but a scratch repository may still hold one, and the maintainer should drop it before
projecting the same window with a label. The FR-001 bundle is now **4431 quads** (T-220's
`sh:class :Asset` and T-227's `sh:class :Universe` +2, five `sh:in`
window lists and two segment lists became `sh:pattern`, −50, `:runLabel` adds 16, and Work item 26's
selection classes/properties/shapes add 227). No GraphDB load was made in this change: the schema
must be reloaded (the T-212 command) before a labelled or selection projection writes, because the
store's `shapes.ttl` still lacks `:runLabel` and `:SelectionCycle`.

**Work item 26 note (selection side).** The selection-side projector writes the sibling graph
`urn:graph:derived:backtest:selection:{run_label}:{P<n>|H<n>}:{backtest_run_id}` and the metadata graph
`urn:graph:derived:backtest:meta:{run_label}`. The ingest gate
accepts it on its own append-only branch (`_BACKTEST_SELECTION_TARGET`), so an already-written m018
graph is untouched. Run it dry first, then with `--write`:

```bash
uv run python cli/project_selection.py --db rule=rule_P1.db --db rule=rule_P2.db
uv run python cli/project_selection.py --db rule=rule_P1.db --write
```

For the final load, `cli/load_run.py` runs both projectors and the verifier in order
(`--label final --dir delivery --write`); the manual commands remain the fallback. A delivery is a
folder of six date-ordered windows (`P1`, `H1`, `P3`, `H2`, `P2`, `H3`) with `SHA256SUMS` and
`config_<label>.md`; the loader verifies the manifest before any database read, writes the one
`urn:graph:derived:backtest:meta:{label}` graph after the data graphs, and verifies its hashes,
configuration and per-window runs read-only. The pilot folder uses `--no-manifest --no-config`
and builds no metadata graph.

A backtest veto's rule is resolved by `:ruleId` on the run's knowledge date (2026-10-31), not by
`:raisedOn`; `LIQUIDITY_DISTRESS` resolves to `_v11` and an unknown id stops the run. The projector
reads the six selection views plus `v_ticker_history`, keeps `v_veto.evidence_json` out of the
graph (its values are price-derived), and links a ticker by exact `:Asset` symbol first, else to
the one loaded `:Asset` with the same CIK from `v_ticker_history` (`FBIN` → `:FBHS`, `GAP` →
`:GPS`); if neither is safe it keeps the ticker literal and counts the row. The schema must be
reloaded (the T-212 command) before a selection write, because the store's copy predates
`:SelectionCycle` and the ranking properties.

The 2026-11-04 selection dry runs after the link rule (read-only): P1 321,324 triples in 56.45 s
at 1,214,004 KB peak RSS, P2 309,728 in 53.94 s at 1,155,632 KB, P3 342,934 in 58.35 s at
1,285,948 KB; all `pyshacl` conformant, 0 unlinked ranking/veto rows (before: 34/0/2 and 9/2/3).
The increases over the exact-only runs (321,281 / 309,726 / 342,929) are the recovered links.

**T-352/T-353 note (ticker history and orchestrator runs).** `check_target` now also accepts
`urn:graph:derived:ticker-history:{run_label}:{YYYY-MM-DD}` and
`urn:graph:derived:orchestrator:{run_label}:{positive run id}`. The ticker-history target is
append-only and reference-like: a later snapshot uses a new date (or label), and every
`TickerHistory` IRI carries the label and date so the gate's check 6 does not see a re-declaration.
An orchestrator run gets one graph, keyed by its positive id; a later run is a new graph. The
projector is `src/projection/reference.py`, the policy is `src/projection/project_reference.py`,
and the CLI is `cli/project_reference.py`. No GraphDB write or reload was made in this change; the
live ticker-history snapshot is in the record below.

**T-211 note (FIBO Phase 2).** `schema/fibo.ttl` is a 277-statement reference slice and loads into
its own graph, `urn:graph:reference:fibo`, after `reference.ttl`. The loader therefore owns 20
graphs and 4708 asserted triples on a fresh load (4513 at the T-212 reload; +2 for T-220's and
T-227's `sh:class` triples, −34 for T-233/T-234 and +227 for Work item 26's selection terms and
shapes, whose FR-001 bundle is now 4431 quads; the slice adds 277). No
load was run for this change; the store was reloaded on 2026-11-02 (T-212, below), and the
live Appendix A queries ran the same day (T-213). The
slice is rebuilt only for a new FIBO release; `cli/build_fibo_slice.py` refuses any zip whose
sha256 is not the pinned value.

Validation reads `tbox.ttl` and `shapes.ttl` from `schema/` on disk (once per process); reload with
`cli/load_schema.py` after a schema edit so the store's copy matches. Limits: this is a code path,
not a server-side lock, so anyone holding the write credentials can still write around it; and the
existence check and the write are two requests, so two simultaneous writers could both pass it; the same
holds for check 8: two batches restating the same stored section can both pass "not yet superseded" and
leave it with two `:supersededBy` values, which the functional property forbids and nothing at the read
boundary catches.

When `ingest` raises `WriteInDoubt` (the batch was sent and the store's answer was lost), look in
the store before sending it again: if it landed, checks 6, 7 and 8 refuse the second attempt (a closure
says "already closed", with a note when the stored date is the batch's own; a restatement is refused
by check 6, since its new section already exists, and by check 8, "already superseded by …").

## Verifying a loaded backtest (T-280, Work item 29)

Once a run is written (or before writing, against a scratch repository), prove that **both** named
graphs hold what the deterministic projectors build from their source database:

```bash
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:rule:P1:1 \
  --db data/backtests/rule_P1.db --label rule
uv run python cli/verify_backtest.py \
  --graph urn:graph:derived:backtest:selection:rule:P1:1 \
  --db data/backtests/rule_P1.db --label rule
```

It reads the repository from `KG_HOST`/`KG_REPOSITORY` (the same environment as
`project_backtest`, `project_selection` and `verify_store`), prints the repository and graph it
checked, re-projects the source in memory through `projection.backtest.project_source` (m018) or
`project_selection_source` (selection), and prints one `PASS`/`FAIL` line per check. It only issues
SPARQL `SELECT` queries, so it is safe against any repository, including production; exit 0 means
every check passed. The m018 checks are unchanged. The selection checks add graph identity, total
triples, one individual per projected selection row, the placeholder count, the asset links and
their unlinked ceiling, vetoes grouped by resolved rule, and the cross-graph check that every TOPN
`:cycleRunId` in the m018 graph has its `SelectionCycle`; `MARKOWITZ_BASE` has none. The checks and
their details are in `SPEC.md` FR-009; the full load procedure is
[`backtest-load-runbook.md`](backtest-load-runbook.md).

`cli/load_run.py` runs the whole sequence in one command (delivery discovery, manifest and
configuration checks, optional contract check, both dry runs, both writes, the metadata graph, then
the verifier for every graph):

```bash
SQL_UNIVERSE_DB=/workspaces/thesis/data/universe_history_gics.db \
uv run python cli/load_run.py --label final --dir data/backtests --write
```

It prints the window order (chronological, so `P3` precedes `P2`), per-step and per-window timings,
and a final table of graph, stored triples and checks passed. A window over 30 minutes is listed as
`STOP AND ASK upstream`. It prints a `df -h` reminder before a write because GraphDB 11.5.1 exposes
no free-disk value on its read-only REST surface; if a later version does, the probed percentage is
printed before the run and between windows and the run stops below `--min-free-pct` (default 8,
hard floor 5). A verification failure stops the run and prints the exact one-graph `DROP GRAPH
<iri>` commands for the graphs it wrote; it never drops anything itself. The one-command flow and
its manual fallback are in [`backtest-load-runbook.md`](backtest-load-runbook.md).

Read-only dry runs on 2026-11-04 over the completed databases in
`/workspaces/thesis/scratch/final/runs/` (no store was contacted; `cli/load_run.py`, both
projectors):

| Database | `v_book_weight_daily` rows | m018 triples | Selection rows | Selection triples | Time | Peak RSS |
|---|---|---|---|---|---|---|
| `rule_P1.db` | 15,615 | 209,886 | 42,700 | 321,324 | 93.2 s | 1.16 GB |
| `rule_P2.db` | 15,641 | 196,840 | 41,259 | 309,728 | 90.2 s | 1.10 GB |
| `rule_P3.db` | 18,025 | 222,449 | 45,440 | 342,934 | 101.0 s | 1.22 GB |

Unlinked tickers: 0 ranking and 0 veto in every database after the shared CIK-aware link rule. On
2026-11-04 the verifier also ran against an in-memory `rdflib.Dataset` holding `rule_P1.db`'s two
projections: 21 of 21 m018 checks passed over 209,886 triples and 15 of 15 selection checks passed
over 321,324 triples, including the cross-graph check. It then ran against `portfolio_test`: the
m018 graphs passed 21/21 checks each and the selection graphs 15/15 each; see "Live load record,
portfolio_test, 2026-11-04" below.

## Acceptance check (T-025)

```bash
uv run python cli/verify_store.py [--to-production]
```

Runs the three checks Work item 3 requires of a running store with `schema/` loaded, plus the two
of T-176 and the one of T-181 below, and exits non-zero if any fails ([`kg_store.acceptance`](../src/kg_store/acceptance.py)). It writes nothing; `--to-production` is still required when the target is `portfolio`, so aiming the read-only checks at production is deliberate.

| Check | What it proves |
|---|---|
| SPARQL query | `SELECT ?s WHERE { ?s a :Asset } LIMIT 5` over HTTP returns individuals |
| Malformed write | a `ScoreSnapshot` that is valid except for the missing `:timestamp` is refused by the gate with a SHACL `minCount` violation on `:timestamp`, and that is the only violation reported (a rejection for any other reason fails the check; the probe carries `rawValue` and `availableAt` so `ScoreSnapshotShape` is otherwise satisfied); the store's size is unchanged and the target graph does not exist |
| Reasoning profile | the repository reports `rdfsplus-optimized` and `disableSameAs` true, and `?x a :Observation` is answered by inference (nothing is asserted with it) and includes a `ScoreSnapshot`, which is two `rdfs:subClassOf` steps below it, so the chain is followed and not just one hop. A production store with no ABox yet proves the same two-step chain on the TBox (`:ScoreSnapshot rdfs:subClassOf :Observation`) instead of requiring an example individual |
| Schema graphs (T-176) | each graph `schema/` owns (read from `schema/` by `load_schema.expected_sizes`) has the asserted size a fresh load gives; a graph the store holds that `schema/` does not own is reported, not failed, so dated `urn:graph:ingest:…` graphs do not break a healthy store. A production load owns five schema graphs; every other repository owns the 21 graphs that include the worked example |
| `:agentOrigin` (T-176) | no individual has more than one `:agentOrigin`, and none has a value outside the `sh:in` list of `ScoreSnapshotShape`, read from `shapes.ttl` |
| Stored vocabulary (T-181) | a stored string passes the gate beside what the store holds, fetched by `gate.fetch_context`: a non-production store uses the worked example's quant batch (`urn:graph:derived:quant:2026-08-05` in `instances.trig`, read from `schema/`, never written) and its `:portfolioKind` rules (`sh:in`, `sh:hasValue "BENCHMARK"`); production, which never receives `instances.trig`, uses a read-only Veto probe pointing at the stored `:Rule_LEVERAGE_EXTREME`, whose `:ruleSeverity` is the same kind of closed `sh:in` list. Both compare terms, so either fails if a stored string is read in a form other than the plain literal the batches use. Added in T-181 and generalized for production in Work item 39; the quant-batch form ran against the live repository with T-212 (2026-11-02) and passes |

### Live run (T-141, 2026-10-08)

`uv run python cli/verify_store.py` against the live repository `portfolio` (GraphDB 11.5.1) with the
acceptance probe of that date (T-142's `sh:ValidationResult` count): exit 0, all three checks that existed then pass.

| Check | Result |
|---|---|
| SPARQL query | 5 assets returned, the first `:AAPL` |
| Malformed write | rejected by SHACL (`:timestamp` `minCount`, the only violation); store size unchanged at 2435; `urn:graph:ingest:SEMANTIC:2099-01-01` absent |
| Reasoning profile | `rdfsplus-optimized`, `disableSameAs` true; `?x a :Observation` = 41 inferred, 0 asserted |

The script writes nothing, and nothing was written.

**Found by the run (at the time; fixed by T-174, below): the store's schema graphs were older than `schema/`, and it held a graph `schema/`
no longer has.** Compared per graph (`kg_store.load_schema.expected_sizes` against the store's
asserted sizes; the totals, 2435 against 2547, hide two opposite differences):

| Graph | Store | `schema/` |
|---|---|---|
| `urn:graph:tbox` | 1420 | 1567 |
| `urn:graph:ingest:QUANTITATIVE:2026-08-05` | 35 | not in `schema/` |
| every other graph in `schema/` | equal | equal |

- **`tbox` is short by 147 triples.** They are the changes made since the last load, not T-121
  alone: the per-run weight-scheme terms (`:cycleDate`, `:bookWeightingRule`, `:topN`,
  `:maxNameWeight`, `:maxSectorWeight`, `:softVetoPenalty` and their shapes), and edits to
  `:rawValue`, `:normalizedScore`, `:availableAt`, `:runId`, `:attractivenessScore` and
  `ScoreSnapshotShape`/`AttractivenessSnapshotShape` (from the tasks since the last load, among them T-121, T-151, T-153, T-155 and T-171).
- **The 35-triple graph is a leftover, and it made the live store inconsistent until T-174.** It held
  five snapshots (`Snap_AAPL_Quant_20260805`, `Snap_JNJ_…`, `Snap_JPM_…`, `Snap_PG_…`, `Snap_XOM_…`)
  under the agent name `QUANTITATIVE`, which T-105 renamed to `VALORIZATION` on 2026-10-03. The
  `VALORIZATION` graph was in the store, matched `schema/` (60 triples) and held **the same five
  IRIs** with the same `:metricType` and `:rawValue`; the only difference is `:agentOrigin`
  (`"QUANTITATIVE"` against `"VALORIZATION"`). So each of those five individuals had two
  `:agentOrigin` values in the store. A query over the union of graphs (the reasoner's
  `?x a :Observation`, "latest snapshot per asset") saw both. Checked with `pyshacl` on one of the
  five (`Snap_AAPL_Quant_20260805`) with the extra value added: it does not conform, because
  `"QUANTITATIVE"` is not in `ScoreSnapshotShape`'s `sh:in` list for `:agentOrigin` and its
  `sh:maxCount 1` is broken (`:agentOrigin` is also an `owl:FunctionalProperty` in `tbox.ttl`).
  `load_schema.load` drops only the graphs it is about to load, so a reload does **not** remove it;
  it prints it afterwards as a graph "not in `schema/`". Removing it was a separate write. Dropping
  it deleted no audit data: every individual in it still exists in the `VALORIZATION` graph.

The check does not look at either difference, so it passes either way. The gate reads `tbox.ttl` and
`shapes.ttl` from disk, so writes through `cli/ingest.py` are validated against the current shapes,
but the store's own copy (what a SPARQL query and the reasoner see) lacked the newer terms.
Reloading and dropping the leftover are writes, so neither was done in this run; both needed the
maintainer's go-ahead (T-174, done below).

### Bringing the store in line (T-174, 2026-10-08)

Both writes were made after the maintainer's go-ahead, by a Claude Code session they asked to run them.

1. `uv run python cli/load_schema.py`: reloaded the 19 graphs of `schema/`; its own check found all 19
   and 2547 asserted triples matching the local parse, and noted 1 other graph left untouched (the
   leftover). The store went from 2435 to 2582 triples (`tbox` +147; the leftover's 35 are still
   there).
2. The leftover `urn:graph:ingest:QUANTITATIVE:2026-08-05` was exported first (35 triples, N-Triples, kept
   outside the repository), then dropped with `DROP GRAPH` (HTTP 204). `/size` read 2582 just before
   and 2547 after: down by exactly 35, which is the total of the 19 graphs of `schema/`, so nothing is
   left outside them.
3. Each of the five snapshots in the `VALORIZATION` graph has exactly one `:agentOrigin`, and a query
   for any individual with more than one `:agentOrigin` over all graphs returns nothing.
4. `uv run python cli/verify_store.py` again: exit 0, all three checks pass, the probe's "store size
   unchanged" reads 2547.

The leftover's absence is shown by the size, not by a direct query: the read-only `ASK { GRAPH
<urn:graph:ingest:QUANTITATIVE:2026-08-05> { ?s ?p ?o } }` was blocked by the permission classifier and
not retried; it should answer false. The store now matches `schema/`. This is a one-time record; the standing guard is T-176, now in `verify_store` (two more checks; on the store above, exit 0, all five pass).

### Reloading after T-177 (T-179, 2026-10-10)

T-177 (PR #82) put two triples in `urn:graph:tbox` (1567 to 1569; 2547 to 2549 over the 19 graphs), so the
store was two behind `schema/`. Written after the maintainer's go-ahead, by a Claude Code session they asked to run it.

Before step 1, two attempts failed: `HTTP 401` (`/rest/login` answered "Bad credentials", for the application and
the admin account alike), then `HTTP 403` once the login was accepted (`portfolio.app` held no role on
`portfolio`; the admin account read the repository and its 2547 triples). The next attempt succeeded. The server's
user list was not inspected, so no cause is claimed; nothing in the repository changed.

1. `uv run python cli/verify_store.py` before (`/size` read 2547): four checks passed; "schema graphs have their expected size"
   failed with `urn:graph:tbox: expected 1569, store has 1567`, as expected.
2. `uv run python cli/load_schema.py`: exit 0, `verified: 19 graphs, 2549 asserted triples match the local parse`,
   and no "other graph" line (the leftover T-174 dropped is not back).
3. `uv run python cli/verify_store.py` after: exit 0, all five checks pass, the probe's "store size unchanged"
   reads 2549.
4. `uv run pytest -m integration tests/test_store_cli_exit_codes.py`: 6 passed, including
   `test_verify_store_passes_on_the_configured_store`. Run with `KG_ADMIN_USER`/`KG_ADMIN_PASSWORD` set: without
   them the scratch-repository tests skip instead of passing. Afterwards the server listed only `portfolio`, so no
   `kgtest-…` repository was left behind.

### Reloading after T-185 (T-193 and T-186, 2026-10-12)

T-185 (PR #94) put one triple in `urn:graph:tbox` (1569 to 1570; 2549 to 2550 over the 19 graphs), so the store was
one behind `schema/`. Written after the maintainer's go-ahead, by a Claude Code session they asked to run it, once
they had brought the database back up (the first attempt could not reach the server: `Network is unreachable`).
Run from `master` at `fad9196`.

1. `uv run python cli/verify_store.py` before: five of the six checks passed; "schema graphs have their expected size"
   failed with `urn:graph:tbox: expected 1570, store has 1569`, as expected.
2. `uv run python cli/load_schema.py`: exit 0, `verified: 19 graphs, 2550 asserted triples match the local parse`.
3. `uv run python cli/verify_store.py` after: exit 0, all six checks pass, the probe's "store size unchanged"
   reads 2550:
   - PASS SPARQL query returns real results (5 assets, first `:AAPL`)
   - PASS malformed write rejected by the gate (`:timestamp minCount`; store size unchanged at 2550)
   - PASS reasoning profile matches 07 (`rdfsplus-optimized`, `disableSameAs` true; 41 inferred `:Observation`, 0 asserted)
   - PASS schema graphs have their expected size (19 graphs)
   - PASS every `:agentOrigin` is single and in the shape's list
   - PASS the quant batch passes beside the stored Portfolios (3 stored individuals)

T-186 asked for these six lines from the live store (T-181's sixth check reads stored string literals through
`GraphDB._term`). The sixth line is the proof: that check fails when the store writes a string in a form
`select_terms` does not read as equal to `"BENCHMARK"` (`acceptance.check_quant_batch`), and it passed. They are
the record, and T-186 is done.

### Dropping the full FIBO graph (P1, 2026-11-02)

P1 of the FIBO integration brief, done by the maintainer by hand in the GraphDB Workbench on
2026-11-02 (local evening), repository `portfolio`. The full FIBO graph
`<https://spec.edmcouncil.org/fibo/ontology/2026Q2>` was dropped with `DROP GRAPH`; nothing else
was dropped.

| | Before | After |
|---|---|---|
| Explicit statements | 137,496 | 2,550 |
| Inferred statements | 180,948 | 908 |
| Graphs | 19 | 18 |

The difference is 134,946 explicit statements (exactly the graph's size) and 180,040 inferred. The
remaining 2,550 explicit statements equal the sum of the other 18 graphs, unchanged. `docs/06` §1.1
cites the same measurement as the cost of the 2026-10-27 evaluation load; this section records the
store operation behind it.

### Reloading after T-206 to T-211 (T-212 and T-213, 2026-11-02)

The schema reload for T-212 and the live Appendix A run for T-213, both done by the maintainer by
hand on 2026-11-02, from `master` at `0267d90` (the merge of PR #113), repository `portfolio`.

The maintainer's local `.env` had `KG_HOST=http://127.0.0.1:7200/`, which cannot reach GraphDB from
the devcontainer (Connection refused); it was changed locally to `http://host.docker.internal:7200`.
The `.env` is git-ignored and is not recorded here. No `verify_store` run was made before the
reload.

1. `uv run python cli/load_schema.py`: exit 0.

```text
loaded tbox.ttl -> urn:graph:tbox
loaded shapes.ttl -> urn:graph:tbox
loaded reference.ttl -> urn:graph:reference
loaded fibo.ttl -> urn:graph:reference:fibo
loaded rules.ttl -> urn:graph:rules:catalog
loaded instances.trig
verified: 20 graphs, 4513 asserted triples match the local parse
```

The loader owns 20 graphs and 4513 asserted triples. `urn:graph:reference:fibo` holds the 277
statements of `schema/fibo.ttl`; that number follows from the arithmetic 4513 − 4236 (the FR-001
bundle without the slice), not from a separate per-graph count, which was not measured.

2. `uv run python cli/verify_store.py`: exit 0, all six checks pass.

```text
PASS SPARQL query returns real results: 5 assets returned, first https://thesis.local/kg/portfolio#AAPL
PASS malformed write rejected by the gate: rejected by SHACL (:timestamp minCount); store size unchanged at 4513, urn:graph:ingest:SEMANTIC:2099-01-01 absent
PASS reasoning profile matches 07: ruleset rdfsplus-optimized, disableSameAs true; ?x a :Observation = 41 inferred, 0 asserted
PASS schema graphs have their expected size: 20 schema graphs have the size a fresh load gives
PASS every :agentOrigin is single and in the shape's list (FUNDAMENTAL, SECTOR, SEMANTIC, TECHNICAL, VALORIZATION)
PASS the quant batch passes beside the stored Portfolios: the quant batch passes beside the 3 stored individual(s) it points at
```

3. The live Appendix A queries (T-213), run by the maintainer in the Workbench on 2026-11-02,
   repository `portfolio`, the two queries exactly as in `docs/06` §1.1:
   - A2 for "volatilidad" returned one row: `fibo:IND/Indicators/Indicators/Volatility` (shown by
     the Workbench as `fibo-ind-ind-ind:Volatility`), the authors' Spanish definition «Medida
     estadística de la dispersión alrededor de la media de una variable aleatoria durante un
     período de tiempo.»@es and FIBO's English definition "statistical measure of the dispersion
     around the average of some random variable over some period of time".
   - A1 for `:Portfolio` returned one row: `labelEs` "portafolio"@es; `defEs` «El libro de
     posiciones activas.»@es; FIBO `fibo:FND/OwnershipAndControl/Ownership/Portfolio` (shown as
     `fibo-fnd-oac-own:Portfolio`); `fiboLabelEs` "portafolio"@es; `fiboDefEs` «Colección de
     tenencias reunidas y mantenidas como una unidad con fines de gestión para alcanzar objetivos
     estratégicos.»@es; `fiboDef` "collection of holdings assembled and maintained as a unit for
     management purposes to achieve strategic objectives".

Both match the offline versions in `tests/test_fibo_slice.py`, so the live graph layout
(`urn:graph:tbox`, `urn:graph:reference:fibo`) is confirmed. T-212 and T-213 are done.

### Final-backtest vocabulary (Work item 33)

The schema now accepts `P1`–`P3`, `H1`–`H3` and the `P2a`/`P2b` segments, the fourth arm
`MARKOWITZ_BASE_GUARD`, the Basing Points GUARD rules `L1_BP_STOP`/`L1_BP_REENTRY`, the core ETF
`SPY` (`:ExchangeTradedFund`, no CIK/membership/classification) and the run-metadata graph
`urn:graph:derived:backtest:meta:{label}`. A Basing Points alert must not carry
`:alertThreshold`; every other alert still must. `reference.ttl` now has six individuals, so a
fresh catalog is 643 written assets + 6 = **649**; the live 2026-11-04 record above stays as it
was (it wrote five reference memberships, and `SPY` has none to write). The user reloads the schema
with `cli/load_schema.py` and verifies with `cli/verify_store.py`; pilot data remains valid.

## Live load record, portfolio_test, 2026-11-04

The first real catalog and backtest load into `portfolio_test`. The schema was reloaded from
`master` after PR #123; `cli/verify_store.py` passed 6/6 checks.

| Load | Result |
|---|---|
| Asset catalog, `universe_history_gics.db`, `urn:graph:universe:2026-Q4` | 643 `:Asset` written plus the 5 in `reference.ttl`; 658 memberships (503 open, 155 closed); 6548 triples; 59 assets without `:classifiedAs` on purpose |
| m018 backtest graphs, label `rule` | P1 209,886, P2 196,840, P3 222,449 triples; `cli/verify_backtest.py` 21/21 checks each |
| Selection graphs, label `rule` | P1 321,324, P2 309,728, P3 342,934 triples; `cli/verify_backtest.py` 15/15 checks each |
| Ticker history, `urn:graph:derived:ticker-history:rule:2026-11-04` | 21 rows; 198 triples; 17 exact plus 4 same-CIK asset links; 4 multi-date evidence cells omitted and counted |
| Orchestrator | `v_orchestrator_run` and `v_orchestrator_step` have 0 rows; nothing written |

Selection individuals per class:

| Class | P1 | P2 | P3 |
|---|---|---|---|
| `SelectionCycle` | 22 | 20 | 22 |
| `AttractivenessSnapshot` | 10,484 | 10,060 | 11,066 |
| `AttractivenessWeightScheme` | 22 | 20 | 22 |
| `WeightComponent` | 30,730 | 29,805 | 32,634 |
| `Veto` | 1,442 | 1,354 | 1,696 |

Placeholders with no effective weight: 3 / 11 / 16. Distinct linked tickers: ranking 516 / 529 /
530, veto 485 / 498 / 504; 0 unlinked.

**Lesson 1 — the gate must see the referenced individuals' shape data.** The first live selection
write was refused by the gate: `:attractivenessOfAsset`, `:vetoOfAsset`, `:appliesRule` and
`:primaryRule` declared no `sh:class`, so `fetch_context` returned only `rdf:type` for the
referenced assets and rules, and the batch failed `AssetShape` and `RuleDefinitionShape` (dozens of
violations). Work item 30 fixed it with the relation's `rdfs:range` fallback and added
`--check-store`; the dry run alone cannot see this class of problem.

**Lesson 2 — GraphDB refuses every write below 5% free disk space.** The store answered HTTP 500
"Critically low disk space" with 23 GB free on a 465 GB disk. GraphDB 11.5.1's read-only REST
surface exposes no free-disk value: `/rest/locations` returns the location identity without space
fields, and `/rest/monitor/structures` carries cache/query metrics, not disk. `cli/load_run.py`
therefore prints a `df -h` reminder before a write and translates the HTTP 500 into a stop that
names the graph being written and prints its one-graph `DROP GRAPH`; the default
`--min-free-pct` is 8 and the hard floor is 5. Docker Desktop's `docker_data.vhdx`
had grown to 210.5 GB with about 76 GB in real use. The procedure that worked, and its result
(210.5 GB to 78.5 GB): free space inside, then run
`docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -- fstrim -av`, quit Docker Desktop,
run `wsl --shutdown`, and in an elevated prompt use `diskpart`:
`select vdisk file="...\docker_data.vhdx"`, `attach vdisk readonly`, `compact vdisk`,
`detach vdisk`. A compaction without the trim step recovered nothing.

## Connecting

Variables are documented in [`.env.example`](../.env.example); real values live in the gitignored
`.env` (never commit credentials).

| Variable | Meaning |
|---|---|
| `KG_HOST` | `http://host.docker.internal:7200` from the devcontainer (`localhost` is the container itself) |
| `KG_REPOSITORY` | `portfolio` (production; a replay, `cli/project_scores.py --replay`, refuses it and needs a repository of its own, which also keeps its own key files) |
| `KG_USER` / `KG_PASSWORD` | HTTP Basic credentials of `portfolio.app` |
| `KG_ADMIN_USER` / `KG_ADMIN_PASSWORD` | optional; an account that may create repositories, read only by the T-175 integration tests (`portfolio.app` gets HTTP 403); a run killed midway leaves a `kgtest-…` repository, to delete in the Workbench |

| Operation | Endpoint |
|---|---|
| SPARQL query | `{KG_HOST}/repositories/{KG_REPOSITORY}` |
| SPARQL update | `{KG_HOST}/repositories/{KG_REPOSITORY}/statements` |
| Named-graph store | `{KG_HOST}/repositories/{KG_REPOSITORY}/rdf-graphs/service?graph=urn:graph:...` |
| Triple count | `{KG_HOST}/repositories/{KG_REPOSITORY}/size` |

An unauthenticated or wrong-password request returns 401. To test emptiness use `/size`: a bare
`ASK { ?s ?p ?o }` is true even on an empty repository because the ruleset adds axioms.

The devcontainer reads `.env` only at (re)build time (`--env-file`); rebuild after editing it.
The `SQL_*_DB` variables are unrelated to the store (see T-026).
