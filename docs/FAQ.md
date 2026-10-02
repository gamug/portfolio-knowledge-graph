# FAQ — Graph Population Q&A

A running log of questions asked and answered during the "populating the graph" work
sessions, companion to the **[Population Ledger](https://claude.ai/code/artifact/6b434b58-7a91-4a0e-8c8a-7f11be020034)**
artifact (which covers the same ground visually — node patterns, dates, named-graph
filtering, and the population roadmap). This file exists for anything that needs the fuller,
prose form of an answer, or that came up as a follow-up after the artifact was published.

Grounded in `schema/`, `07-ontology-topology.md`, `08-agent-architecture.md`, and
`10-integration-roadmap.md` — an entry that cites a graph name, class, or property is quoting
what's actually in this repo, not general RDF theory. New entries get appended at the bottom
as the conversation continues; nothing here gets rewritten after the fact except to correct
an error (marked as such where it happens).

---

## Q: You said there are "eleven" named graphs to query — what does that actually mean?

**Short answer:** it's an artifact of the worked example, not a fixed number. Four graphs
have permanent, fixed names and exist exactly once. Everything else is a *template* that
mints a brand-new graph every time an agent runs — the count grows without bound as the
system operates.

**Full answer:**

`schema/instances.trig` — the 5-asset worked example — happens to contain exactly 11
`GRAPH <urn:graph:...> { }` blocks:

```
urn:graph:universe:2026-Q3
urn:graph:ingest:FUNDAMENTAL:2026-Q3
urn:graph:ingest:QUANTITATIVE:2026-08-05
urn:graph:ingest:TECHNICAL:2026-08-05
urn:graph:ingest:SEMANTIC:2026-08-05
urn:graph:ingest:EDGAR:2026-Q3
urn:graph:ingest:EDGAR:2026-08-10
urn:graph:derived:entity-resolution:2026-Q3
urn:graph:ingest:ORCHESTRATOR:2026-08-04
urn:graph:ingest:ORCHESTRATOR:2026-08-05
urn:graph:portfolio:current
```

That's an undercount of what's actually loaded, though: `tbox.ttl`, `reference.ttl`, and
`rules.ttl` each load wholesale into their own named graph (`urn:graph:tbox`,
`urn:graph:reference`, `urn:graph:rules:catalog`) per `schema/README.md`'s load order — but
because those are plain Turtle, not TriG, they never appear as a `GRAPH { }` block inside
`instances.trig`. So "everything currently loaded" is **14 concrete graphs**, not 11.

More importantly, `07-ontology-topology.md`'s design table doesn't define graphs — it defines
10 graph *name patterns*, split into two very different kinds:

| Kind | Patterns | Behavior |
|---|---|---|
| Fixed, one instance ever | `tbox`, `reference`, `rules:catalog`, `portfolio:current` | Same URI forever; `portfolio:current` is the one graph mutated in place (via `validTo`-closing). |
| Templated, spawns a new graph every batch | `ingest:{agent}:{date}`, `ingest:FUNDAMENTAL:{year}-Q{n}`, `ingest:ORCHESTRATOR:{date}`, `ingest:EDGAR:{date-or-quarter}`, `derived:entity-resolution:{date}`, `universe:{year}-Q{n}` | A new concrete URI is minted every time an agent runs. |

The 11-block count in `instances.trig` is just what those templated patterns look like after
one quarter plus two days. Run the `MonitoringCycleGraph` for a full year and
`ingest:TECHNICAL:{date}` alone mints ~250 distinct graphs — one per trading day. There is no
ceiling on the real number.

**What this means for querying:** you never pick from a fixed menu of graphs. Either you
compute the exact URI you want from the template (you already know the agent and the date)
and scope directly to it, or you leave the graph as a variable and query across the whole
family, filtering on the data inside the triples (`timestamp`, `validFrom`) instead of the
graph name. See the next entry for the concrete form of both.

*(Asked 2026-08-18, in response to the Population Ledger artifact's Section 3.)*

---

## Q: For "get the semantic score for company XXX on 2026-08-18," you gave `FROM <urn:graph:ingest:SEMANTIC:2026-08-18>` — but how do we filter by asset if the graph itself isn't asset-specific?

**Short answer:** the named graph and the asset are two independent axes, not one. The graph
URI only narrows by *when it was written and by which agent* — it says nothing about *which
company*. Narrowing to one company is an ordinary SPARQL triple-pattern match layered on top,
identical to what you'd write if named graphs didn't exist at all.

**Full answer:**

The actual shape of `urn:graph:ingest:SEMANTIC:2026-08-05` in `instances.trig`:

```turtle
GRAPH <urn:graph:ingest:SEMANTIC:2026-08-05> {
    :Snap_AAPL_Sent_20260805 a :ScoreSnapshot ; :agentOrigin "SEMANTIC" ; :metricType "Sentiment" ;
        :rawValue "-0.65" ; :normalizedScore "0.83" ; :timestamp "2026-08-05T09:00:00" .
    :Snap_JPM_Sent_20260805  a :ScoreSnapshot ; ... .
    :Snap_XOM_Sent_20260805  a :ScoreSnapshot ; ... .
    :Snap_JNJ_Sent_20260805  a :ScoreSnapshot ; ... .
    :Snap_PG_Sent_20260805   a :ScoreSnapshot ; ... .

    :AAPL :hasScoreObservation :Snap_AAPL_Sent_20260805 .
    :JPM  :hasScoreObservation :Snap_JPM_Sent_20260805 .
    :XOM  :hasScoreObservation :Snap_XOM_Sent_20260805 .
    ...
}
```

Two things worth noticing:

1. **The link triple (`:AAPL :hasScoreObservation :Snap_...`) is written in the same batch as
   the snapshot itself**, not somewhere in `reference.ttl`. The Semantic Agent asserts the
   observation and the pointer to it together, in the same `INSERT`, because both are new
   facts as of that run.
2. **In production this one graph holds every company's snapshot from that day side by
   side** — 5 in the demo, ~500 at full scale. Scoping to the graph only gets you into the
   right batch; it deliberately doesn't pre-filter by company.

So the query composes two independent constraints — `GRAPH` does the coarse cut (which
batch), the asset's own IRI does the fine cut (which company):

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?rawValue ?normalizedScore ?timestamp
WHERE {
  GRAPH <urn:graph:ingest:SEMANTIC:2026-08-18> {   # coarse: which batch
    :AAPL :hasScoreObservation ?snap .              # fine: which company
    ?snap a :ScoreSnapshot ;
          :rawValue ?rawValue ;
          :normalizedScore ?normalizedScore ;
          :timestamp ?timestamp .
  }
}
```

If the exact date isn't known and the goal is "AAPL's most recent semantic score, whenever it
was written," drop the fixed graph and let it vary instead, sorting on the timestamp:

```sparql
SELECT ?rawValue ?normalizedScore ?timestamp
WHERE {
  GRAPH ?g {
    :AAPL :hasScoreObservation ?snap .
    ?snap a :ScoreSnapshot ; :metricType "Sentiment" ;
          :rawValue ?rawValue ; :normalizedScore ?normalizedScore ; :timestamp ?timestamp .
  }
}
ORDER BY DESC(?timestamp)
LIMIT 1
```

*(Asked 2026-08-18, follow-up to the previous entry.)*

---

<!-- New Q&A entries get appended below this line as the work session continues. -->
