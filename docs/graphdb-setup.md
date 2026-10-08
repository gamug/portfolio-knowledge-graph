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
   `MAINTAIN_REPO_portfolio`; the Workbench lists these as Read / Write / Repository admin). Without repository roles the user gets 403 on every query.

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

Loads `tbox → shapes → reference → rules → instances.trig` per the graph map in
[`schema/README.md`](../schema/README.md). It first drops every graph it is about to write, so a
re-run (for example after a schema edit) replaces rather than duplicates. It then parses the same
files with `rdflib` and compares the asserted triple count of each of those graphs with the store's
(inferred statements excluded), exiting non-zero on any mismatch; the counts are printed, not
hard-coded here. The drops and uploads run in one transaction, so a failed load changes nothing.
Graphs that are not in `schema/` (for example ingest graphs written later) are left alone and only
counted in a closing note; a graph removed from `schema/` has to be dropped by hand. **T-105 migration:** a repository loaded before T-105 still holds `urn:graph:ingest:QUANTITATIVE:2026-08-05`; run `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` once, or the same snapshots will exist under both `agentOrigin` values and fail `ScoreSnapshotShape`.
Needs write access (`WRITE_REPO_portfolio`). It loads `schema/` only; the ETL's `data.ttl` and
projected upstream data belong to Work item 4.

## Ingest gate (T-023)

```bash
uv run python cli/ingest.py batch.ttl --graph urn:graph:ingest:SEMANTIC:2026-08-06 [--check]
```

The sanctioned way to write an ABox batch. [`kg_store.gate`](../src/kg_store/gate.py) writes a
Turtle batch only if all of these hold, and otherwise raises `IngestRejected` (exit status 2) with
nothing written:

1. the target is named as `07` prescribes: `urn:graph:ingest:{agent}:{date}` (`FUNDAMENTAL` by
   quarter, `EDGAR` by date or quarter), `urn:graph:derived:entity-resolution:{date|quarter}`,
   `urn:graph:derived:quant:{date}`, `urn:graph:universe:{year}-Q{n}` or `urn:graph:portfolio:current` (TBox, reference and rules go
   through `cli/load_schema.py`);
2. an append-only graph (all but `portfolio:current`) does not exist yet;
3. every IRI is absolute and every `rdf:type` is one of the 27 leaf classes (the
   `owl:AllDisjointClasses` members), so neither a typo nor a bare abstract category can dodge the
   shapes;
4. a subject with no `rdf:type` in the batch, which no shape can see, only gets relations to other
   individuals (object properties such as `:hasScoreObservation`, `:supersededBy`; the object must
   be an IRI, not a literal) or an `xsd:date` `:validTo`; adding a value to an existing observation
   is refused;
5. the batch conforms to `shapes.ttl` under `pyshacl`. The shapes target by class and reference no
   other individuals, so a batch is validated on its own;
6. no typed individual in the batch already exists in the store (explicit statements, any graph):
   a batch may only introduce new individuals, so re-declaring a stored observation with another
   value is refused. Closing a record is the untyped `:validTo` path (check 4).

What is written is the validated triples as N-Triples, not the submitted text. `--check` runs
checks 1, 3, 4 and 5 without contacting the store, so it cannot see an existing graph (check 2)
or an existing individual (check 6).
Validation reads `tbox.ttl` and `shapes.ttl` from `schema/` on disk (once per process); reload with
`cli/load_schema.py` after a schema edit so the store's copy matches. Limits: this is a code path,
not a server-side lock, so anyone holding the write credentials can still write around it; and the
existence check and the write are two requests, so two simultaneous writers could both pass it.

## Acceptance check (T-025)

```bash
uv run python cli/verify_store.py
```

Runs the three checks Work item 3 requires of a running store with `schema/` loaded, and exits
non-zero if any fails ([`kg_store.acceptance`](../src/kg_store/acceptance.py)). It writes nothing.

| Check | What it proves |
|---|---|
| SPARQL query | `SELECT ?s WHERE { ?s a :Asset } LIMIT 5` over HTTP returns individuals |
| Malformed write | a `ScoreSnapshot` that is valid except for the missing `:timestamp` is refused by the gate with a SHACL `minCount` violation on `:timestamp`, and that is the only violation reported (a rejection for any other reason fails the check; the probe carries `rawValue` and `availableAt` so `ScoreSnapshotShape` is otherwise satisfied); the store's size is unchanged and the target graph does not exist |
| Reasoning profile | the repository reports `rdfsplus-optimized` and `disableSameAs` true, and `?x a :Observation` is answered by inference (nothing is asserted with it) and includes a `ScoreSnapshot`, which is two `rdfs:subClassOf` steps below it, so the chain is followed and not just one hop |

### Live run (T-141, 2026-10-08)

`uv run python cli/verify_store.py` against the live repository `portfolio` (GraphDB 11.5.1) with the
current acceptance probe (T-142's `sh:ValidationResult` count): exit 0, all three checks pass.

| Check | Result |
|---|---|
| SPARQL query | 5 assets returned, the first `:AAPL` |
| Malformed write | rejected by SHACL (`:timestamp` `minCount`, the only violation); store size unchanged at 2435; `urn:graph:ingest:SEMANTIC:2099-01-01` absent |
| Reasoning profile | `rdfsplus-optimized`, `disableSameAs` true; `?x a :Observation` = 41 inferred, 0 asserted |

The script writes nothing, and nothing was written.

**Found by the run: the store's schema is older than the repository's.** The store holds 2435
triples; `schema/` parses to 2547 quads (T-121 added the per-run weight-scheme terms). The check
does not look at this, so it passes either way. The gate reads `tbox.ttl` and `shapes.ttl` from disk,
so writes through `cli/ingest.py` are validated against the current shapes, but the store's own copy
(what a SPARQL query and the reasoner see) lacks the T-121 terms. Reloading is a write
(`cli/load_schema.py`), so it was not done; it needs the maintainer's go-ahead (T-174). The store has neither `:cycleDate` nor `:bookWeightingRule`.

## Connecting

Variables are documented in [`.env.example`](../.env.example); real values live in the gitignored
`.env` (never commit credentials).

| Variable | Meaning |
|---|---|
| `KG_HOST` | `http://host.docker.internal:7200` from the devcontainer (`localhost` is the container itself) |
| `KG_REPOSITORY` | `portfolio` (production; a replay, `cli/project_scores.py --replay`, refuses it and needs a repository of its own, which also keeps its own key files) |
| `KG_USER` / `KG_PASSWORD` | HTTP Basic credentials of `portfolio.app` |

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
