# Second-user setup: local GraphDB + `portfolio-app`

For a colleague who will run `portfolio-app` locally against their own GraphDB, using the
maintainer's delivered store. The delivered graph is one repository named `portfolio`, one run
label `final`; `portfolio_test` is only the maintainer's rehearsal and is never shipped.

The colleague needs GraphDB, the exported graph, the TTYG agent and the app. The app must use a
**read-only** GraphDB user; only the person creating the agent and importing the graph needs a
repository-manager account. The maintainer's production sequence is
[`final-delivery.md`](final-delivery.md).

## 1. GraphDB

Install **GraphDB 11.5.1 Free** and start it locally. In the Workbench:

1. Create a repository named `portfolio` from
   [`schema/graphdb-repo-config.ttl`](../schema/graphdb-repo-config.ttl) (Setup → Repositories →
   Create → upload RDF config). The config sets the required
   `graphdb:ruleset "rdfsplus-optimized"` and `graphdb:disable-sameAs "true"`.
2. Enable security and create the users below.
3. Do not load `instances.trig` or the worked-example ABox; the delivered export already contains
   the production graph set.

Check the repository profile before importing anything:

```bash
curl -fsS -u "$KG_ADMIN_USER:$KG_ADMIN_PASSWORD" -H 'Accept: text/turtle' \
  "$KG_HOST/rest/repositories/portfolio" | grep -E 'graphdb:(ruleset|disable-sameAs)'
```

## 2. Verify and import the maintainer's export

The maintainer delivers an export folder with:

- `portfolio-<stamp>.trig` — every named graph, exported from the `portfolio` repository;
- `portfolio-repository-config.ttl` — the repository configuration;
- `SHA256SUMS` — one SHA-256 per file.

Verify the hashes **before** importing. A mismatch means the copy is incomplete or changed; ask for
a fresh copy instead of importing it.

```bash
cd /path/to/delivered-export
sha256sum -c SHA256SUMS
```

Replace `<stamp>` in the file name below with the delivered value.

Create the empty `portfolio` repository first (section 1), then import the TriG into it. The
statements endpoint appends the named graphs; the repository must be empty so nothing is merged
with an older copy.

```bash
curl -fsS -u "$KG_ADMIN_USER:$KG_ADMIN_PASSWORD" \
  -H 'Content-Type: application/x-trig' \
  --data-binary @portfolio-<stamp>.trig \
  "$KG_HOST/repositories/portfolio/statements"
```

**Not yet verified on a live store.** The TriG export through
`/repositories/portfolio/statements` and the re-import of a file of roughly 4.2 million triples have
not been tried on this installation. A large single POST can hit timeouts or memory limits. Rehearse
the export and import into a scratch repository first; if the POST fails, import with Workbench
**Import** (upload or server files).

Read-only checks after the import:

```bash
curl -fsS -u "$KG_USER:$KG_PASSWORD" \
  "$KG_HOST/repositories/portfolio/size"
```

and, from a checkout of this repository with `.env` pointing at the local GraphDB:

```bash
KG_REPOSITORY=portfolio uv run python cli/verify_store.py --to-production
```

`verify_store` must print one `PASS` per check and exit 0. It reads only; the production repository
is named `portfolio`, so the `--to-production` flag is required even for the read-only verifier.

## 3. Recreate the TTYG agent

The agent is Workbench state and is not in the export. Follow
[`ttyg/create-agent.md`](ttyg/create-agent.md) exactly: SPARQL only, the curated CONSTRUCT, the
single instruction fence, temperature `0.1`, and the operator's own `graphdb.llm.*` settings. The
form requires a repository-manager account; after the agent exists, the read-only user can use it.

## 4. Read-only user

Create a dedicated app user, for example `<READ_ONLY_USER>`, and grant **Read** on the `portfolio`
repository only (`READ_REPO_portfolio`). Do not give the app a repository-admin or maintainer role,
and do not put the maintainer's credentials in the app.

The app's GraphDB settings are the local values:

```text
KG_HOST=http://localhost:7200          # adjust to the local GraphDB
KG_REPOSITORY=portfolio
KG_USER=<READ_ONLY_USER>
KG_PASSWORD=<READ_ONLY_PASSWORD>
```

The password stays in the colleague's local, git-ignored `.env`; never commit it and never share it.

## 5. `portfolio-app`

Pin `portfolio-app` to **`<pinned version>`** (the maintainer fills this placeholder; do not invent a
version). Follow the app's own README for installation. Point it at the local GraphDB with the
read-only user above.

The app may also need an LLM key for its own features. The key is the colleague's own, stored only
in their local `.env` (and, for the GraphDB TTYG connector, in `graphdb.llm.api-key` or
`graphdb.llm.api-key@file`). It is never committed to this repository, never shared with the
maintainer or another user, and never pasted into an issue or chat.

## 6. First smoke questions

Ask the agent these in order. They exercise the run label, the date-ordered windows, a concrete
count, the weighting wording and the in-sample caveat:

| Question | Healthy answer |
|---|---|
| Which run labels does the graph have? | Only `final`; no `rule` or `candidate`. |
| List the windows in calendar order. | `P1, H1, P3, H2, P2, H3`, with their dates; never sort by name. |
| How many GUARD alerts does P1 have? | 978, with the counting rule and the window stated. |
| What is the Sistema's weighting objective: minimum variance or minimum CVaR? | Minimum CVaR. `:objective "min_var"` is a fixed per-arm label, not the weighting objective. |
| Is a reported performance figure definitive? | No: all six windows were seen before the final round, so the result is in-sample. |

A healthy conversation has these properties:

- every answer states the run label, window, arm and dates used, and the counting rule;
- the answer shows exactly one SPARQL query, the one that decided it;
- performance answers say **in-sample**;
- the agent says "the graph does not have that data" instead of estimating a missing value;
- answers are at most 10 lines and use the language requested by the app's final line;
- no answer contains a per-asset price, per-asset daily return, Basing Points threshold or an
  invented figure.

If a smoke question fails, retry it once (two attempts per question). If it still fails, check the
repository label, the agent's instruction fence and the `graphdb.llm.*` model before changing
anything.

## 7. What not to do

- Do not import the export into a non-empty repository; it appends and can merge with stale graphs.
- Do not give the app write or admin credentials.
- Do not import `instances.trig`, the worked-example ABox, into the local production repository.
- Do not copy the maintainer's `.env`, credentials or LLM key.
- Do not treat `portfolio_test` as a delivered store.
