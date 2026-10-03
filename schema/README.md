# Portfolio Knowledge Graph — Schema Implementation

Implements `06-ontology-definition.md` and `07-ontology-topology.md` as loadable OWL/SHACL/TriG.
Supersedes the earlier single-file `schema/portfolio-kg.ttl` sketch, split here per the topology
document's named-graph design — and extended with four refinements that only became visible while
actually building it (each flagged inline in the file that surfaced it, and summarized below).

## File-to-named-graph map

| File | Format | Loads into | Contents |
|---|---|---|---|
| `tbox.ttl` | Turtle | `urn:graph:tbox` | Classes, properties, OWL cardinality restrictions. |
| `shapes.ttl` | Turtle | `urn:graph:tbox` | SHACL data-quality shapes (kept as a separate file/concern from `tbox.ttl` — OWL semantics vs. SHACL validation, see below). |
| `reference.ttl` | Turtle | `urn:graph:reference` | GICS sector/industry taxonomy + asset master data (5 worked-example tickers). |
| `rules.ttl` | Turtle | `urn:graph:rules:catalog` | The active veto catalog: upstream's 6 rules (T-103) as single-leaf `RuleDefinition`s; v1's original 6 plus `VETO_MKT_02` (7 unambiguous `RuleClause`-tree rules) are kept closed with `validTo 2026-10-02` as design history; and the `AttractivenessWeightScheme`. |
| `instances.trig` | **TriG** | *(self-describing — see below)* | Dated ABox: universe membership, agent snapshots, evidence, vetoes, filings, portfolio; sector-aggregate and attractiveness-ranking output (added 2026-08-13). |

`instances.trig` is TriG, not Turtle — it contains explicit `GRAPH <urn:graph:...> { ... }` blocks,
so it's the one file that's self-describing about which named graph each triple belongs to. Every
other file loads wholesale into the single graph named in the table. No new file was added for the
attractiveness-ranking feature: its `urn:graph:ingest:SECTOR:{date}` graph pattern is populated
from within `instances.trig` like every other per-agent ingest graph.

Two more files live in this directory but load into nothing (neither is part of the load order
above):

- `graphdb-repo-config.ttl` — **not data**: the GraphDB repository configuration (reasoning profile),
  never loaded into a graph. See `docs/graphdb-setup.md`.
- `protege-view.ttl` — a **generated**, flattened plain-Turtle bundle for Protégé (which can't
  open `.trig`), derived from the four authoritative sources plus a `:sourceNamedGraph` annotation
  that exists only in this file. Never hand-edit it; regenerate it from a Protégé session after a
  `tbox`/`shapes`/`reference`/`rules` edit rather than trusting a stale copy.
- `protege-view.txt` — an earlier, superseded cut of the same generated bundle, kept only as a
  historical artifact of how the Protégé view was produced before `protege-view.ttl` existed.
- `taxonomy-quality-review-2026-08-23.md` — the write-up of the programmatic `rdfs:subClassOf`
  audit referenced under "Validation" below (cycle/orphan/multi-parent detection); not loaded by
  anything, kept as the record of that pass.

**Load order for a fresh GraphDB/Fuseki repository:** `tbox.ttl` → `shapes.ttl` → `reference.ttl`
→ `rules.ttl` → `instances.trig`. Nothing strictly requires this order at load time (a quad store
doesn't validate on ingest unless SHACL validation is explicitly turned on), but it matches
dependency order and is the sequence `10-integration-roadmap.md` step 1 assumes.

## Why both OWL restrictions (`tbox.ttl` §4) and SHACL shapes (`shapes.ttl`)

They answer different questions and neither substitutes for the other:

- **OWL** (`tbox.ttl`) is open-world: a cardinality restriction lets a reasoner *infer* things
  (e.g. "this RuleClause's second operand, if unstated, still logically exists somewhere") but
  never *rejects* incoming data for missing a required property.
- **SHACL** (`shapes.ttl`) is closed-world validation: it's what a real ingestion pipeline runs
  against incoming data before accepting it — missing `operand2` on a `RuleClause` is a validation
  failure, not an inference opportunity.

A thesis-grade ontology benefits from stating both: OWL for what the classes *mean*, SHACL for
what the store *enforces*.

## Refinements found during implementation (not anticipated in the design docs)

1. **Two new leaf types.** `06-ontology-definition.md` §1.5 only worked through `VETO_COMP_01`,
   whose leaves are all numeric. Encoding the full 6-rule catalog (`rules.ttl`) surfaced that
   `VETO_LEG_01`/`VETO_COMP_02` gate on `RiskEvent.category`/`severity` (categorical, not numeric)
   and `VETO_RED_01` gates on a graph-structural predicate (not a scalar comparison at all) — hence
   `CategoricalComparison` and `GraphPredicate` in `tbox.ttl`, each with their own SHACL shape.
2. **Raw-vs-normalized comparison convention.** Populating real numbers in `instances.trig` forced
   an explicit answer to a question the ontology alone doesn't resolve: `Score*` metrics compare
   via `normalizedScore` ([0,1]), but `Sentiment` compares via `rawValue` ([-1,1]) — v1's own
   thresholds (`-0.50`, `-0.60`) are only meaningful on the raw scale. Documented on
   `ThresholdComparison` in `tbox.ttl`. T-103 (2026-10-03) extended the convention to upstream's own
   metrics (`leverage.debt_to_equity`, `cashflow.free_cash_flow_margin`, `liquidity.current_ratio`,
   `max_drawdown_90d`, `fundamental_score_age_days`): they are not `ScoreSnapshot` types, carry
   upstream's identifiers, and compare on the raw value (they have no `normalizedScore`).
3. **Two more named-graph placements.** `07-ontology-topology.md` assigned graphs to every
   *agent's* daily output but not to the Orchestrator's own decisions or to entity resolution's
   derived facts. Resolved: `urn:graph:ingest:ORCHESTRATOR:{date}` and
   `urn:graph:derived:entity-resolution:{date}` (both documented in `instances.trig`'s header).
4. **Shared-property domain collision when reusing `ScoreSnapshot`'s fields for a sibling class.**
   Adding `SectorAggregateSnapshot` (2026-08-13, attractiveness-score feature) needed to reuse
   `metricType`/`agentOrigin`/`timestamp`/`normalizedScore`, but those properties' `rdfs:domain`
   was declared as `:ScoreSnapshot` specifically — reusing them as-is would RDFS-entail that a
   `SectorAggregateSnapshot` individual is also a `:ScoreSnapshot`, contradicting
   `AllDisjointClasses`. Originally resolved with a union class (`:ObservationSnapshot`) widening
   the four properties' domain instead of duplicating them under new names — **superseded by
   refinement 5 below.**
5. **Class taxonomy + MetricType vocabulary (added 2026-08-23).** Two changes, both in
   `06-ontology-definition.md` §1.2/§1.9:
   - The 24 disjoint leaf classes had no `rdfs:subClassOf` structure among themselves at all —
     only `AllDisjointClasses` (horizontal exclusivity), never a vertical hierarchy. `tbox.ttl`
     §1.2 adds one: 6 broad categories, 4 mid-level, every leaf re-parented. Along the way,
     `EvidenceSource`/`RuleOperand`/`ObservationSnapshot` (refinement 4 above) were upgraded from
     `owl:unionOf` helpers — excluded from `AllDisjointClasses`, never used as an individual's
     `rdf:type` — to ordinary superclasses, same IRIs. This was a required change, not a
     preference: layering new `rdfs:subClassOf` assertions (e.g. `AttractivenessSnapshot
     rdfs:subClassOf :ObservationSnapshot`) *on top of* the old `owl:unionOf` axiom would have made
     `ObservationSnapshot` unsatisfiable under a DL reasoner (`owl:unionOf` asserts an
     equivalence — every member must be `ScoreSnapshot` or `SectorAggregateSnapshot` — which
     `AttractivenessSnapshot`'s `AllDisjointClasses` membership directly contradicts). Plain
     `rdfs:subClassOf` has no such equivalence, so removing the `unionOf` triples first and
     replacing them with ordinary subclass assertions was the correct fix, not just a style choice.
     `RuleOperand`'s real union also already included `RuleClause` itself (nested clauses) —
     preserved as `:RuleClause rdfs:subClassOf :RuleOperand`.
   - `ScoreSnapshot.metricType` / `ThresholdComparison.metricName` / `WeightComponent
     .weightMetricName` were open strings with no controlled vocabulary — same situation GICS
     sectors were in before this file's `:GICSScheme`. `reference.ttl` now has a matching
     `:MetricTypeScheme` (5 `skos:Concept`s — **exactly** the 5 values `grep`-verified present in
     `rules.ttl`/`instances.trig`: `ScoreFinanciero`, `ScoreCuantitativo`, `ScoreTecnico`,
     `Sentiment`, `SectorRelativeMomentum`). `shapes.ttl`'s three shapes referencing these fields
     now enforce `sh:in` over that closed set; `SectorAggregateSnapshotShape.metricType` is
     tightened further to `sh:hasValue "ScoreTecnico"` (its only real value). **Found in the
     process, not fixed:** `09-nlp-finbert-architecture.md`'s worked example shows a metricType of
     `"NEWS_SENTIMENT_FINBERT"` that is never actually used anywhere in this schema — real Sentiment
     snapshots use plain `"Sentiment"` throughout. That's a live inconsistency in `09`'s example,
     left as a flag for whoever next edits that document rather than silently perpetuated into a
     6th vocabulary entry here.

## Validation

Parsed and checked with `rdflib` (Turtle + TriG) and validated end-to-end with `pyshacl` —
see the conformance report captured at the bottom of this implementation pass. Re-run:

**Re-verified 2026-08-23** after refinement 5 above (both the `rdflib` parse and the `pyshacl`
conformance check below, run against the full combined graph — `tbox.ttl` + `shapes.ttl` +
`reference.ttl` + `rules.ttl` + `instances.trig` — in that load order): **parses clean, 1607
quads; conforms: True**, including the three newly-added `sh:in`/`sh:hasValue` constraints on
`metricType`/`metricName`/`weightMetricName`. The `sh:in` tightening is a real, non-vacuous check
here (not just syntax validation): if any actual data value had fallen outside the 5-member
vocabulary, this would have failed.

**Re-verified 2026-10-03 (T-103, rule catalog migration):** the same combined-graph parse and
`pyshacl` check — **1718 quads; conforms: True**. The migration added the six upstream
`RuleDefinition`s, closed the seven tree rules with `validTo`, added `:ruleSeverity` and widened
`ThresholdComparisonShape`'s `metricName` list; no new class, so the then-24-member `AllDisjointClasses` (25 since T-104)
block and the 14 node shapes are unchanged.

**T-102 (veto stints), same day:** `:Veto` gains `raisedOn` (required), `clearedOn`, `lastSeenOn`
(`xsd:date` cycle dates) and `vetoSeverity` (HARD | SOFT, per stint; absent = the `primaryRule`'s
`ruleSeverity`), enforced by a new `VetoShape` (node shapes 14 → 15) that also rejects a
`clearedOn`/`lastSeenOn` earlier than `raisedOn`. `lastSeenOn` is deliberately multi-valued
because the ORCHESTRATOR graphs are append-only: each cycle adds its own value, current = `MAX`.
A stint is closed by writing `clearedOn` in the clearing cycle's graph, never by deleting the
`Veto`; the worked example closes `Veto_XOM_20260804` on 2026-08-05 and gives
`Veto_XOM_MKT_20260805` a SOFT `vetoSeverity`. Upstream's wall-clock `cleared_at` is dropped.
**1771 quads; conforms: True.**

**T-104 (D5, decided 2026-10-03: model it).** `:DataQualityIssue` is an `EvidenceSource` leaf — one row of upstream's `data_quality_issue` (`dqGateCode`, `dqSeverity`, `quarantined`, `gatedValue`, `dqIssueOfAsset`) — so a HARD gate that raises the `DATA_QUALITY` veto has an evidence target: a `RiskEvent` is `backedBy` it. Written to the FUNDAMENTAL ingest graph (the Ring-1 gates run in the fundamental agent). `DataQualityIssueShape` is the 16th shape; `dqSeverity` is not enumerated because only HARD is documented upstream. The 25th class joins `AllDisjointClasses`. Review follow-up: the issue also carries `dqRaisedOn` (required, the as-of key), optional `dqIssueOfFiling`/`dqMetricName`/`provenanceId`, and the worked example is a HARD issue on JNJ (graph `FUNDAMENTAL:2026-Q4`) backing `Veto_JNJ_DQ_20261005` through a `RiskEvent` in `ORCHESTRATOR:2026-10-05` — dated after `Rule_DATA_QUALITY`'s `validFrom` (2026-10-02) so `:appliesRule` resolves to a rule valid on the veto's date; the gate code and values are illustrative. `instances.trig` now has 14 `GRAPH` blocks. The cutoff checks above (08-03…08-05) are unchanged; at 2026-10-05 the query also returns `Veto_JNJ_DQ_20261005` (plus the earlier stints, whose `lastSeenOn` the worked data does not advance). `protege-view.ttl` has no generator in this repo and is stale (it predates T-102–T-104); regenerate it before relying on it in Protégé. **1881 quads; conforms: True.**

**T-101 (D2, decided 2026-10-03: new properties, not graph-date encoding).** `ScoreSnapshot` gains `:availableAt` (xsd:date, **required**) and `:eventTime` (xsd:date, never after `availableAt`; optional in the shape so a source row that lacks `event_time` still validates, although every agent defines it and the worked data and the news ETL always set it). `timestamp` stays the compute/ingest time. Encoding it in the ingest-graph date was rejected: graphs are dated by ingest batch, and a quarterly FUNDAMENTAL graph would still mix filings with different availability. Every as-of-D reader of `ScoreSnapshot`s filters `availableAt <= D` (never `eventTime`/`timestamp`). `SectorAggregateSnapshot` and `AttractivenessSnapshot` are same-cycle derived outputs and get no second clock: they are usable from the date of their `timestamp`/`computedAt`. Worked data: the Q3 FUNDAMENTAL snapshots have `eventTime` 2026-06-30 (period-end) and `availableAt` 2026-07-06 (the first trading day after an illustrative filing date; 07-05 is a Sunday); the daily agents use the cycle date for both. `src/etl/news_to_rdf.py` now emits `eventTime` (article day) and `availableAt` (the later of the article day and the day the score was processed) on its SEMANTIC snapshots. `RiskEvent`/`DataQualityIssue` are not covered yet (they keep `detectedAt`/`dqRaisedOn`). 1951 quads; conforms: True.

**T-105 (D6, 2026-10-03: `QUANTITATIVE` → `VALORIZATION`).** `agentOrigin` is now `FUNDAMENTAL | SEMANTIC | VALORIZATION | TECHNICAL | SECTOR` (matches upstream migration m006); the worked graph is `urn:graph:ingest:VALORIZATION:2026-08-05` and `src/kg_store/gate.py` accepts that name (`QUANTITATIVE` graphs are no longer valid ingest names). **Migration:** an already-loaded repository must `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` once (`load_schema.py` leaves removed graphs in place; see `docs/graphdb-setup.md`). The `:Snap_*_Quant_*` IRI stems are historical. The metric id `ScoreCuantitativo` is **kept** (rules and blend weights reference it; upstream's metric id is pinned in T-109) and now carries a note. What `eventTime` means per score type: FUNDAMENTAL = filing period-end; TECHNICAL, VALORIZATION and SECTOR = cycle date; SEMANTIC = article day. Extra upstream provenance not yet modelled (handed to T-106, whose scope now names them): `forensic_flags_json`, `prompt_hash` (FUNDAMENTAL), `correction_rule` (`financial_facts`). **1953 quads; conforms: True.**

**T-106 (D7, 2026-10-03: run provenance).** Decision: properties on `ScoreSnapshot`, no `Run` class (it would change the 25-class counts across the docs for data that stays upstream). New optional `runId`, `runAsOf`, `codeVersion`, `engineVersion` (with `ScoreSnapshotShape` entries); `provenanceId` keeps its meaning on evidence leaves. Dispositions of the T-105 extras: `forensic_flags_json` and `prompt_hash` (FUNDAMENTAL) are upstream-internal audit detail, **not projected** — reachable via `runId`; `correction_rule` (`financial_facts`) is not projected either, since no `v_*` view exposes `financial_facts` (T-109 gap list). Worked example: the five VALORIZATION snapshots carry illustrative run values. **2009 quads; conforms: True.**

"Active at cutoff" is the general predicate; the **T-1 lag is the same query with `?cutoff` bound to
the previous cycle date**. It needs the store to query the union of the named graphs (GraphDB does
by default; Fuseki needs `unionDefaultGraph`). Checked on the worked data: cutoff 2026-08-03 →
none; 2026-08-04 → `Veto_XOM_20260804` only; 2026-08-05 → the three others (XOM's FIN_01 stint is
closed that day).

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?asset ?veto WHERE {
  ?asset :triggeredVeto ?veto . ?veto :raisedOn ?r .
  OPTIONAL { ?veto :clearedOn ?c }
  FILTER (?r <= ?cutoff && (!BOUND(?c) || ?c > ?cutoff))
}
```

**Second re-verification, same day, taxonomy-quality review pass:** a programmatic audit of the
`rdfs:subClassOf` graph (cycle detection, orphan detection, multi-parent detection — all via
`rdflib`, not eyeballed) found `tbox.ttl` disagreed with its own design doc
(`06-ontology-definition.md` §1.2.1) and with the companion diagram (`saved_resource.html`) on one
point: `RuleClause`'s taxonomic parentage. The doc and diagram both specified `RuleClause` as
dual-parented (`RuleSystem` direct + `RuleOperand`, since a clause can nest inside another clause);
`tbox.ttl` only had the `RuleOperand` edge. Fixed by adding the missing
`:RuleClause rdfs:subClassOf :RuleSystem .` triple — **1608 quads, conforms: True** after the fix.
Full audit results (0 cycles, 0 self-loops, all 37 classes (38 since T-104, `DataQualityIssue` under `EvidenceSource`) reach one of the 6 taxonomy roots, all
24 leaves have ≥1 taxonomy parent, exactly 3 classes are legitimately multi-parented —
`RuleClause`, and `Sector`/`Industry` via a pre-existing `skos:Concept` edge unrelated to this
taxonomy) are recorded in the conversation that produced this pass, not re-derived here.

```bash
uv run python -c "
import rdflib
g = rdflib.Dataset()
for f, fmt in [('tbox.ttl','turtle'), ('shapes.ttl','turtle'), ('reference.ttl','turtle'), ('rules.ttl','turtle')]:
    g.parse(f, format=fmt)
g.parse('instances.trig', format='trig')
print('quads:', len(list(g.quads())))
"
```

`pyshacl` conformance and hand-verified attractiveness-score/VETO_MKT_02 arithmetic are checked by
the script in Task 5 of `docs/superpowers/plans/2026-08-13-attractiveness-sector-momentum.md` —
re-run it the same way after any future schema edit that touches `ScoreSnapshot`,
`SectorAggregateSnapshot`, or `AttractivenessSnapshot`.
