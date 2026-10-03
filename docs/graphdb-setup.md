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
only.

On a **fresh** mount, once:

1. Open `http://localhost:7200`, register the free licence.
2. Create the repository from [`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl)
   (Setup → Repositories → Create → upload RDF config). It carries the reasoning profile.
3. Enable security (Setup → Users and Access) and create the application user `portfolio.app` with
   read, write and maintain on `portfolio` (`READ_REPO_portfolio`, `WRITE_REPO_portfolio`,
   `MAINTAIN_REPO_portfolio`). Without repository roles the user gets 403 on every query.

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

## Connecting

Variables are documented in [`.env.example`](../.env.example); real values live in the gitignored
`.env` (never commit credentials).

| Variable | Meaning |
|---|---|
| `KG_HOST` | `http://host.docker.internal:7200` from the devcontainer (`localhost` is the container itself) |
| `KG_REPOSITORY` | `portfolio` |
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
