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
uv run python cli/load_schema.py [--dir path/to/schema]
```

Loads `tbox → shapes → reference → fibo → rules → instances.trig` per the graph map in
[`schema/README.md`](../schema/README.md). It first drops every graph it is about to write, so a
re-run (for example after a schema edit) replaces rather than duplicates. It then parses the same
files with `rdflib` and compares the asserted triple count of each of those graphs with the store's
(inferred statements excluded), exiting non-zero on any mismatch; the counts are printed, not
hard-coded here. The drops and uploads run in one transaction, so a failed load changes nothing.
Graphs that are not in `schema/` (for example ingest graphs written later) are left alone and only
counted in a closing note; a graph removed from `schema/` has to be dropped by hand. **T-105 migration:** a repository loaded before T-105 still holds `urn:graph:ingest:QUANTITATIVE:2026-08-05`; run `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` once, or the same snapshots will exist under both `agentOrigin` values and fail `ScoreSnapshotShape`.
Needs write access (`WRITE_REPO_portfolio`). It loads `schema/` only; the ETL's `data.ttl` and
projected upstream data belong to Work item 4.

## Loading the asset master (T-220)

After `schema/` is loaded (the gate validates the batch beside the stored reference individuals),
and before any batch that links `:Asset` nodes (`cli/project_backtest.py`, a score projection or an
ORCHESTRATOR batch):

```bash
uv run python cli/load_universe.py                       # dry run: read, build, SHACL-validate
uv run python cli/load_universe.py --as-of 2026-11-03 --write
```

It reads `SQL_UNIVERSE_DB` (`portfolio-data-mining`'s point-in-time `universe.db`, read-only
through `portfolio_common.db`) and reuses `etl.asset_master`: the `:SP500Index` `:Universe`
(with its FIBO `rdfs:seeAlso`), one `:Asset` per symbol and one `:UniverseMembership` per stint.
The five `:Asset`s `schema/reference.ttl` already declares get memberships but are not re-declared
(the gate's check 6 refuses a second declaration, and `cikNumber` is functional). A membership's
`validTo` is inclusive: it is the last day of membership, and a point-in-time read on D is
`validFrom <= D AND (no validTo OR validTo >= D)`, so a member on its last day is still in and a
one-day stint is kept.

| Option | Meaning |
|---|---|
| `--since YYYY-MM-DD` | Keep a stint with no `valid_to` or `valid_to >= since` (default `2019-01-02`). A ticker reused by another company (`CEG`, `DELL`, `Q`) keeps only the era the backtests and the live index can see, and the dropped stints are counted, never silently omitted. |
| `--as-of YYYY-MM-DD` | The day the catalog is seen as of; it names the graph. Default: today in UTC. |
| `--write` | Append the batch through `cli/ingest.py`'s gate (`kg_store.gate.ingest`). Default: a dry run that reads, builds and SHACL-validates through `gate.validate`, contacting no store. |
| `--to-production` | With `--write`, allow the production repository (`KG_REPOSITORY=portfolio`); without it the run exits 2 before reading anything, as `cli/project_backtest.py` does. |

The target is the quarter graph `urn:graph:universe:{year}-Q{n}` computed from `--as-of` (the gate
accepts that pattern; it was not changed). It is not `urn:graph:reference`: `cli/load_schema.py`
drops and rewrites every graph `schema/` owns on each reload, so ABox individuals written there
would disappear, and an existing graph is never appended to. The load is append-only and one-time
per repository: a second run into the same quarter is refused because the graph exists, and a run
into another quarter re-declares the same `:Asset`/`:Universe` individuals and is refused by check
6. A later quarter's changed memberships are a separate batch of new individuals; a new automation
gets its own repository (Work item 17). Exit status: 0 on success, 1 if the source, the shapes, the
gate or the store stop the run, 2 on a bad argument or the production guard.

A dry run of 2026-11-03 over `/workspaces/thesis/data/universe_history.db` (read-only; no write was
made) kept 657 of 891 stints over 653 symbols and dropped 234 stints of 229 symbols (214 not
loaded at all, 15 with a later stint kept), wrote 648 `:Asset`s plus the five already in
`reference.ttl`, 657 memberships (503 open, 154 closed), and built 6476 triples; `gate.validate`
reported SHACL conforms in 1.3 s. Every ticker in `v_book_weight_daily` (CASH excluded),
`v_guard_alert` and `v_guard_action` of `rule_P1/P2/P3.db` is in the loaded set (P1 100, P2 123,
P3 115; 0 missing). The known overlap with the worked example's `2026-Q3` memberships is recorded
in `docs/07`.

A second dry run, 2026-11-04 over
`/workspaces/thesis/data/universe_history_gics.db` after T-260 made `validTo` inclusive (still
read-only; no write was made), kept 658 of 894 stints over 654 symbols and dropped 236 stints of
230 symbols (215 not loaded at all, 15 with a later stint kept), wrote 649 `:Asset`s plus the five
already in `reference.ttl`, 658 memberships (503 open, 155 closed), and built 6567 triples;
`gate.validate` reported SHACL conforms in 1.2 s. The three one-day stints (`PHIN` on 2023-07-05,
and `HNG`/`AYE` on 1976-06-30) are now kept by the reader; `--since` then drops the two 1976 ones.
70 written `:Asset`s carry no `:classifiedAs` because their latest GICS sub-industry has no rollup
entry (six distinct values). Every ticker in `v_book_weight_daily` (CASH excluded),
`v_guard_alert` and `v_guard_action` of `rule_P1/P2/P3.db` remains in the loaded set (P1 100,
P2 123, P3 115; 0 missing).

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
   `urn:graph:derived:backtest:{run_label}:{P<number>}:{run}`,
   `urn:graph:universe:{year}-Q{n}` or `urn:graph:portfolio:current` (TBox, reference and rules go
   through `cli/load_schema.py`);
2. an append-only graph (all but `portfolio:current`) does not exist yet;
3. every IRI is absolute and every `rdf:type` is one of the 38 leaf classes (the
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
   a ticker-history row or a design-history weight scheme, never a per-run one; `:clearedOn`: a Veto), with no value for it
   yet, and the batch gives it one date, later than the one it opened on (`:validFrom` /
   `:raisedOn`). A closure of an unknown subject, of an observation, of a record already closed or
   closed before it opened is refused. The store is read in any graph, so a new quarter's graph can
   close the previous quarter's memberships. The check reads, then writes: two batches closing the
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
reads `:validTo`). T-207 adds the accepted backtest graph
`urn:graph:derived:backtest:{window_id}:{backtest_run_id}` to check 1; its last capture group is a
positive integer id, not a date, so `check_target` validates the window and id on a separate branch
instead of passing the id to `_date_ok`. The projector that writes those graphs
(`src/projection/backtest.py`, CLI `cli/project_backtest.py`) was run here as a dry run only, and
that change made no GraphDB write or reload; the store was then still pre-T-206. It was reloaded
on 2026-11-02 (T-212, below), and `verify_store` passes.

**T-231/T-234 note (run labels and the window vocabulary).** The accepted backtest graph is now
`urn:graph:derived:backtest:{run_label}:{P<number>}:{backtest_run_id}`: the label pattern is
`[a-z][a-z0-9_]{1,31}` and the window is open to `P<number>` instead of `P1|P2|P3`. The retired
unlabelled names (`urn:graph:derived:backtest:{window}:{run}`) are no longer accepted; no real data
uses them, but a scratch repository may still hold one, and the maintainer should drop it before
projecting the same window with a label. The FR-001 bundle is now **4204 quads** (T-220's
`sh:class :Asset` and T-227's `sh:class :Universe` +2, five `sh:in`
window lists and two segment lists became `sh:pattern`, −50, and `:runLabel` adds 16). No GraphDB
load was made in this change: the schema must be reloaded (the T-212 command) before a labelled
projection writes, because the store's `shapes.ttl` still lacks `:runLabel`.

**T-211 note (FIBO Phase 2).** `schema/fibo.ttl` is a 277-statement reference slice and loads into
its own graph, `urn:graph:reference:fibo`, after `reference.ttl`. The loader therefore owns 20
graphs and 4481 asserted triples on a fresh load (4513 at the T-212 reload; +2 for T-220's and
T-227's `sh:class` triples and −34 for T-233/T-234, whose bundle is now 4204 quads; the slice adds
277). No
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

## Acceptance check (T-025)

```bash
uv run python cli/verify_store.py
```

Runs the three checks Work item 3 requires of a running store with `schema/` loaded, plus the two
of T-176 and the one of T-181 below, and exits non-zero if any fails ([`kg_store.acceptance`](../src/kg_store/acceptance.py)). It writes nothing.

| Check | What it proves |
|---|---|
| SPARQL query | `SELECT ?s WHERE { ?s a :Asset } LIMIT 5` over HTTP returns individuals |
| Malformed write | a `ScoreSnapshot` that is valid except for the missing `:timestamp` is refused by the gate with a SHACL `minCount` violation on `:timestamp`, and that is the only violation reported (a rejection for any other reason fails the check; the probe carries `rawValue` and `availableAt` so `ScoreSnapshotShape` is otherwise satisfied); the store's size is unchanged and the target graph does not exist |
| Reasoning profile | the repository reports `rdfsplus-optimized` and `disableSameAs` true, and `?x a :Observation` is answered by inference (nothing is asserted with it) and includes a `ScoreSnapshot`, which is two `rdfs:subClassOf` steps below it, so the chain is followed and not just one hop |
| Schema graphs (T-176) | each graph `schema/` owns (read from `schema/` by `load_schema.expected_sizes`) has the asserted size a fresh load gives; a graph the store holds that `schema/` does not own is reported, not failed, so dated `urn:graph:ingest:…` graphs do not break a healthy store |
| `:agentOrigin` (T-176) | no individual has more than one `:agentOrigin`, and none has a value outside the `sh:in` list of `ScoreSnapshotShape`, read from `shapes.ttl` |
| Quant batch (T-181) | the worked example's quant batch (`urn:graph:derived:quant:2026-08-05` in `instances.trig`, read from `schema/`, never written) passes the gate beside what the store holds about its Portfolios, fetched by `gate.fetch_context`: its `:portfolioKind` rules (`sh:in`, `sh:hasValue "BENCHMARK"`) compare terms, so it fails if a stored string is read in a form other than the plain literal the batches use. Like the schema-graphs check it takes the store to be a fresh `schema/` load, the worked example included (`instances.trig`, `reference.ttl`): on a store that holds none of the batch's individuals it fails with "load schema/ first", and an example batch missing from `instances.trig` fails instead of validating nothing. Added in T-181; it ran against the live repository with T-212 (2026-11-02) and passes |

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
