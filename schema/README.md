# Portfolio Knowledge Graph — Schema Implementation

Implements `06-ontology-definition.md` and `07-ontology-topology.md` as loadable OWL/SHACL/TriG.
Supersedes the earlier single-file `schema/portfolio-kg.ttl` sketch, split here per the topology
document's named-graph design — and extended with four refinements that only became visible while
actually building it (each flagged inline in the file that surfaced it, and summarized below).

## File-to-named-graph map

| File | Format | Loads into | Contents |
|---|---|---|---|
| `tbox.ttl` | Turtle | `urn:graph:tbox` | 58 classes (44 mutually disjoint leaf/domain classes + a 13-class `rdfs:subClassOf` taxonomic backbone + `:ExchangeTradedFund` under `:Asset`), properties, OWL cardinality restrictions. |
| `shapes.ttl` | Turtle | `urn:graph:tbox` | 40 named SHACL node shapes plus two blank-node conditional shapes (data-quality shapes kept as a separate file/concern from `tbox.ttl` — OWL semantics vs. SHACL validation, see below). |
| `reference.ttl` | Turtle | `urn:graph:reference` | GICS sector/industry taxonomy + asset master data (five worked-example S&P 500 tickers plus the core ETF `SPY`). |
| `fibo.ttl` | Turtle | `urn:graph:reference:fibo` | The 25-term FIBO 2026Q2 glossary slice (54 entries, 277 statements) plus the authors' Spanish `@es` layer; built by `cli/build_fibo_slice.py`, never hand-edited. |
| `labels.ttl` | Turtle | `urn:graph:labels` | The bilingual SKOS presentation vocabulary (90 concepts, 892 triples) for codes and literals; loaded after `rules.ttl` and before `instances.trig`. |
| `rules.ttl` | Turtle | `urn:graph:rules:catalog` | The active catalog: 10 selection rules (upstream's 9 plus `UTILITY_CASH_COVERAGE` from T-071, T-206) as `RuleDefinition`s, 7 GUARD protection rules (`L1_STOP_LOSS`, `L1_REENTRY`, `L1_BP_STOP`, `L1_BP_REENTRY`, `L2_NEWS`, `L3_VOL`, `L4_DD`) in their own section, the 7 original tree rules plus the pre-2026-10-10 `LIQUIDITY_DISTRESS` kept closed as design history, and the `AttractivenessWeightScheme`. |
| `instances.trig` | **TriG** | *(self-describing — see below)* | Dated ABox: universe membership, agent snapshots, evidence, vetoes, filings, portfolio; sector-aggregate and attractiveness-ranking output (added 2026-08-13). |

`instances.trig` is TriG, not Turtle — it contains explicit `GRAPH <urn:graph:...> { ... }` blocks,
so it's the one file that's self-describing about which named graph each triple belongs to. Every
other file loads wholesale into the single graph named in the table. No new file was added for the
attractiveness-ranking feature: its `urn:graph:ingest:SECTOR:{date}` graph pattern is populated
from within `instances.trig` like every other per-agent ingest graph.

Several more files live in this directory but load into nothing (none is part of the load order
above):

- `fibo_terms.csv` — the FIBO terms file (header + 25 rows, T-210/T-211), **not RDF** and not
  loaded: it is the single source for the seven `rdfs:seeAlso` links (six in `tbox.ttl`, one in the
  ETL output) and for the 25 seeds of the glossary slice. `cli/check_fibo_terms.py` checks every
  `fibo_iri` against the pinned `prod.ttl.zip` (label and definition); rows 1–7 name one of our
  terms (`fit` `same` or `broader`), rows 8–25 are `glossary` only and leave `our_term` empty. All
  25 now carry the reviewed Spanish columns.
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
→ `fibo.ttl` → `rules.ttl` → `labels.ttl` → `instances.trig`. Nothing strictly requires this order at load time (a
quad store doesn't validate on ingest unless SHACL validation is explicitly turned on), but it
matches dependency order and is the sequence `10-integration-roadmap.md` step 1 assumes.

`reference.ttl`'s six worked-example individuals (five S&P 500 `:Asset`s plus the core ETF `:SPY`, an `:ExchangeTradedFund`) are the master. The real asset master
(`universe.db`) is ABox data and is written through the ingest gate by `cli/load_universe.py` into
`urn:graph:universe:{year}-Q{n}` (`docs/07`), never into `urn:graph:reference`: `cli/load_schema.py`
drops and rewrites that graph as a whole on every schema reload. A later refresh is an incremental
delta in `urn:graph:universe:{year}-Q{n}:delta:{n}` (new assets, new memberships and `:validTo`
closures only; drift is reported and never written), so the base quarter graph stays the one-time
catalog boundary and no stored individual is re-declared.

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
   `max_drawdown_90d`, `fundamental_score_age_days`; T-187 adds `leverage.interest_coverage` and
   `cashflow.operating_cash_flow_margin`): they are not `ScoreSnapshot` types, carry
   upstream's identifiers, and compare on the raw value (they have no `normalizedScore`).
   **T-081 (Work item 9, 2026-10-05: the shape now enforces it for `Sentiment`).** `ScoreSnapshotShape`
   no longer demands `normalizedScore` of a `Sentiment` snapshot (as for `SectorRelativeMomentum`), and
   instead demands `rawValue`, an `xsd:decimal` in `[-1, 1]`, of every `Sentiment` snapshot, whatever else
   it carries (two `sh:or` constraints). Chosen over normalizing in the ETL because it keeps this one
   convention instead of a second, derived scale for the same metric, touches only `shapes.ttl`, and
   survives T-033 retiring the per-article snapshots; it would also cover upstream's future per-`(asset, day)`
   SEMANTIC aggregate if that carries a `[-1, 1]` raw value, but its scale is not defined upstream
   (`score_snapshot` has no `SEMANTIC` rows as of 2026-10-05, and the score types it does hold are on a
   0–100 scale), so T-033 will have to check it. Eight synthetic cases (rawValue-only, both values and
   `SectorRelativeMomentum` pass; neither value, `rawValue` 1.5, `normalizedScore` without `rawValue`, and
   a `ScoreTecnico` with only `rawValue` fail) and a real ETL smoke run (`--limit 3000`: 3000 violations on the
   old shape, none on the new) agree. No new class or property; `AllDisjointClasses` is unchanged.
   **2400 quads; conforms: True.**
   **T-140 (Work item 14, 2026-10-06: PR #48 post-merge review).** Three gaps the T-081 rewrite left:
   `SectorRelativeMomentum` was exempt from `normalizedScore` without needing a `rawValue` (an empty
   snapshot conformed), so it now requires one, at first in `[-1, 1]` (the range `06` §1.8 defined for a
   `ScoreTecnico` minus its sector aggregate, and the attractiveness formula's `(rawValue + 1) / 2`
   needed; widened to `[-100, 100]` by T-155, below); mapping upstream's SECTOR score into it is T-031's job; `rawValue` gets `sh:maxCount 1` on every `ScoreSnapshot`, matching its
   `owl:FunctionalProperty` in `tbox.ttl` (two `rawValue`s conformed); and an `sh:xone` ties
   `agentOrigin` to `metricType` one-to-one (FUNDAMENTAL→`ScoreFinanciero`, VALORIZATION→
   `ScoreCuantitativo`, TECHNICAL→`ScoreTecnico`, SECTOR→`SectorRelativeMomentum`, SEMANTIC→
   `Sentiment`), the mapping every worked-example `ScoreSnapshot` already follows
   (`SectorAggregateSnapshot`s keep their own shape). Eighteen synthetic cases, the store acceptance
   probe (still exactly one violation, `:timestamp`), `docs/09`'s example and the ETL smoke run
   (`--limit 3000`) agree. No new class or property. **2458 quads; conforms: True.**
   **T-171 (Work item 15, third upstream reply, 2026-10-06, D17).** A fourth metric joins the
   rawValue-not-normalizedScore side of the convention, for a different reason than the first
   three: `ScoreFinanciero` (FUNDAMENTAL). Upstream rewrites a FUNDAMENTAL row's
   `normalized_score` in place on every cycle that re-normalizes its filing against that cycle's
   cohort, so the stored value is whichever cycle last touched it — a mutation this ontology's
   audit-trail principle (constitution; immutable observations, never updated in place) does not
   allow for a `ScoreSnapshot` individual. `ScoreSnapshotShape`'s `sh:or` (T-080/T-081) now also
   exempts `ScoreFinanciero` from requiring `normalizedScore` — optional, not forbidden, so the
   FUNDAMENTAL individuals already in `instances.trig` and the closed design-history rules that
   compare on it (`VETO_FIN_01`, `VETO_COMP_01`/`02`, `VETO_RED_01`) still conform. Dropping that
   requirement must not leave a FUNDAMENTAL snapshot free to carry neither value, so a third `sh:or`
   pairs the exemption with a mandatory `rawValue`, the same pattern `SectorRelativeMomentum` and
   `Sentiment` already use (PR #56 review). The per-cycle, cohort-relative value this loses is not
   actually lost: it is correctly scoped to one `cycle_run` as `:componentValue` on
   `AttractivenessSnapshot`'s effective-weight `WeightComponent` (T-155, PROPOSED), which upstream's
   correction to the same reply already adds. Unlike `SectorRelativeMomentum`/`Sentiment`,
   FUNDAMENTAL's `rawValue` was first left unbounded — upstream confirmed it is stable at the
   source but had not stated its range (open question Q6); the shape required it present and
   stayed silent on bounding it for `ScoreFinanciero` until T-177 (below). Four synthetic FUNDAMENTAL (T-171)
   snapshots agree (neither value and `normalizedScore` only fail; `rawValue` only and both pass),
   and the projector stops writing the value too: `src/projection/score_scale.py` rejects the
   FUNDAMENTAL lane, pinned by `tests/test_score_scale.py`, since the shape alone can't (it keeps
   `normalizedScore` optional for legacy data). No new class or property.
   **2474 quads; conforms: True.**
   **T-155 (Work item 15, second reply, 2026-10-06: the schema half; the projection waits on T-031).**
   Two bounds only served a formula this repo no longer computes. `SectorRelativeMomentum`'s `rawValue`
   widens from `[-1, 1]` (justified only by `(rawValue + 1) / 2`) to `[-100, 100]`: upstream's SECTOR
   `raw_value` is the asset's TECHNICAL raw score minus its sector's mean, in TECHNICAL points
   (observed -54 to +46), read verbatim; its 0–100 `normalized_score` stays an optional
   `normalizedScore` (T-031 rescales it). `AttractivenessSnapshotShape` drops `attractivenessScore`'s
   lower bound and keeps `maxInclusive 1.0`: upstream's `blended_score / 100` goes negative when
   the SOFT-veto penalties exceed the blend (the sum of the active SOFT stints' rules' `:penaltyPoints`, 15 each unless the stint's rule declares its own: T-189). The `attractivenessScore`,
   `AttractivenessWeightScheme`, `WeightComponent` and `:inverted` comments in `tbox.ttl`, the
   `SectorRelativeMomentum` comment in `reference.ttl`, `rules.ttl`'s `WeightScheme_v1` header, `docs/06`
   §1.8 (the formula is kept as design history) and the 2026-08-13 design spec no longer describe the
   blend as computed here. Eleven synthetic cases agree: a SECTOR `rawValue` of -54, 46, ±100 pass and
   ±146 fail; an `attractivenessScore` of -0.10, 0.5 and 1.0 pass and 1.2 fails (the pre-change shape
   rejects -54, 46 and -0.10, so each case fails without the change). No new class or property;
   `AllDisjointClasses` is unchanged. **2473 quads; conforms: True** (one `sh:minInclusive` less).
   **T-153, the comment half (Work item 15, second reply, 2026-10-06).** `:availableAt`'s comment now
   covers the cycle lanes: for TECHNICAL, VALORIZATION and SECTOR it is the cycle date as upstream's
   `v_score_snapshot` defines it (their T-144), read from upstream and never filled in here, so a row
   without it is not projected. `:normalizedScore`'s comment says it is projected as `1 - x/100` from
   upstream's cohort-relative `normalized_score` (50 + 10·z, clamped to [0, 100]), a relative risk reading,
   not an absolute level. Comments only (the same text `kg_target_schema.ttl` proposes); the shapes,
   `:promptHash` and the forensic flags wait on upstream's T-144/T-074. **2473 quads; conforms: True.**
   **T-121 (Work item 12, 2026-10-07: per-run weight schemes).** An `AttractivenessWeightScheme` is now
   one upstream `cycle_run`, not a standing versioned scheme. *Decision:* a per-run scheme is an
   immutable observation, not a valid-time record. Closing the previous run's scheme with `validTo`
   would mutate old records and is ambiguous when SELECTION and MONITORING runs interleave. Its date is a
   new functional `:cycleDate` (`v_weight_scheme.cycle_date` verbatim; no `rdfs:domain`, like `:runId`, since other views carry `cycle_date` too), not `:runAsOf`, which is the run
   log's `as_of` and is not assumed equal to it (T-151 checks the two). `AttractivenessWeightSchemeShape`
   requires exactly one of two kinds (`sh:xone`): a `validFrom` (the design-history `WeightScheme_v1`,
   unchanged), or a `cycleDate` with no `validTo` (never closed). Five more functional properties, read
   verbatim: `:bookWeightingRule` (upstream `scheme_id`, open vocabulary), `:topN` (integer, at least 1),
   `:maxNameWeight` and `:maxSectorWeight` (fractions of the book, [0, 1]; effective cap on SELECTION,
   configured on MONITORING; `maxNameWeight` optional) and `:softVetoPenalty` (points of upstream's
   0-100 blend, default 15, at least 0, not a fraction). `:runId` may also appear once (as proposed
   upstream); it equals `schemeId` and is emitted only under T-151's checks. `:inverted` becomes optional
   (`minCount` dropped). Placement: `urn:graph:ingest:ORCHESTRATOR:{cycleDate}`, beside the snapshots
   that point at the scheme (`docs/07`). Nineteen cases in `tests/test_schema_gate.py` (each kind, every
   knob, both dates, neither, a closed per-run scheme, `cycleDate` and `runId` typed and single-valued, each bound, `bookWeightingRule` typed and
   single-valued, `inverted` omitted or not a boolean) and one in `tests/test_kg_gate.py` (a per-run
   scheme batch is accepted into an ORCHESTRATOR graph). No new class; `AllDisjointClasses` is
   unchanged. **2547 quads; conforms: True.**

   **T-190 (2026-10-12: how many components a scheme weighs).** No shape change. A new run weighs three score
   types (upstream's FUNDAMENTAL, VALORIZATION and TECHNICAL, our `ScoreFinanciero`, `ScoreCuantitativo` and
   `ScoreTecnico`); an earlier run weighed four, the SEMANTIC `Sentiment` as well (upstream's sixth reply, `SPEC.md` §2.6; T-183 (6)).
   `AttractivenessWeightSchemeShape` asks for at least one `:hasWeightComponent` and `WeightComponentShape` only that the
   name is one of the five listed, so both readings conform, and so does an asset that lacks a component in a
   three-type run (T-155). Seven cases in `tests/test_schema_gate.py`: three, four, two and one components conform; none fails on the
   scheme; a name outside the five fails on the component; and a repeated name with weights that do not add to 1
   conforms. That last case pins what the gate's shape leaves open, so "three or four components" is not read as "one per
   score type, adding to 1": the read boundary rejects a repeated `score_type` (`v_weight_component.json` keys the view on
   `(cycle_run_id, score_type)`, so the row is quarantined before any triple is built), and nothing sums the weights
   (it checks each in 0 to 1).
   The projection (T-121's data half) writes whatever components the run has. **2550 quads, unchanged.**

   **T-187 (2026-10-13: the catalog goes from six rules to nine).** Read from upstream's code at `6a80ec3` (`SPEC.md` §2.6,
   seventh reply).
   - **Rules.** `VOLATILITY_SHOCK`, `CRASH_Z_SCORE` and `BREAK_TREND_200` are new (ranks 7 to 9, ours); `LIQUIDITY_DISTRESS`
     is redefined as a new `RuleDefinition` with the same `:ruleId`, and the old one is closed with `validTo`.
   - **Validity.** The four start on 2026-10-10 (upstream's merge; that the three new rules took the same day is assumed,
     T-191 ask (7)), so a stint raised from then on resolves. `validTo` is exclusive on a `RuleDefinition` (valid on `d` when
     `validFrom <= d < validTo`). Picking the definition for a stint's `:raisedOn` is not built (T-201).
   - **`:penaltyPoints`.** New, optional (`xsd:decimal`, at least 0, at most one), on SOFT rules only. A shape refuses it on a
     HARD rule (upstream's is null, so no triple); a SOFT rule without it is allowed and costs the run's `soft_veto_penalty`
     (15, T-189). **Assumed, not confirmed (T-191 ask (8)):** a SOFT stint of a HARD rule, which has none, costs the same.
   - **Two gaps found while encoding, flagged like the earlier ones.** (a) The three new rules compare two quantities or test
     against the sector median, which no `ThresholdComparison` states, so each is a `GraphPredicate` "evaluated upstream" (a
     new use of that leaf, as `DATA_QUALITY`'s was); its `predicateName` is a label chosen here, not an upstream id. (b) The
     redefined `LIQUIDITY_DISTRESS` is not applied to GICS Financials or Utilities, which `CategoricalComparison` (equality
     only) cannot state, so the exemption is in the rule's comment, not the tree (T-202).
   - **Shapes.** `metricName` gains `leverage.interest_coverage` and `cashflow.operating_cash_flow_margin`; `priorityRank`
     allows 1 to 9. No new class; `AllDisjointClasses` is unchanged. **2640 quads; conforms: True.**

   **T-188 (2026-10-13: `Veto` `:expiresOn`).** A new optional `:expiresOn` (`xsd:date`) on `Veto`, upstream's
   `expires_on`, filled only on the stints of the temporary HARD rules (`VOLATILITY_SHOCK`, `CRASH_Z_SCORE`); a NULL
   is no triple (the bundle was 2640 quads after T-187; the property, its comment and its shape add 8).
   - **Multi-valued, like `:lastSeenOn`.** While the condition holds upstream moves `expires_on` 10 NYSE sessions on,
     and ORCHESTRATOR graphs are append-only, so each move adds a value in its own graph and the current one is
     `MAX(?expiresOn)`. A functional property would make the gate refuse the re-confirmation.
   - **Who writes it.** `v_veto.expires_on` is one column changed in place, so the projection writes a value only
     when it differs from the stored `MAX` (unlike `lastSeenOn`, which gets one per cycle); an unchanged column
     adds nothing. Upstream only moves it forward, so a value earlier than the stored `MAX` is a fault the gate
     refuses (T-203).
   - **Shape.** `VetoShape` requires each value to be an `xsd:date` not before `:raisedOn` (`sh:lessThanOrEquals`,
     so the same day passes). It does not order the values among themselves or against `:clearedOn`, and it does
     not require HARD (it cannot see the rule's severity, and the date is harmless on a SOFT stint): the order
     among values is the gate's (T-203).
   - **Gate.** It adds no check yet: it accepts a later `lastSeenOn` on a stored Veto but not a moved `expiresOn`
     (T-203; nothing writes one today).
   - **No cutoff query.** `MAX(?expiresOn)` over all graphs also sees moves made after a cutoff. No reader needs the
     expiry as of a cutoff, since the date never closes a stint, so none is given; the first consumer that does
     files the task (it would read the value's graph date).
   - **It does not close a Veto:** at the first cycle on or after the current value upstream re-evaluates the rule
     and writes `clearedOn` if the condition is gone (seventh reply, `SPEC.md` §2.6). So a reader tests `clearedOn`
     only and the active-at-cutoff SPARQL has no `expiresOn` term.
   - No new class; `AllDisjointClasses` is unchanged. **2648 quads; conforms: True.**

   **T-189 (2026-10-14: the SOFT penalty's identity).** Comments and docs only. The penalty is the sum of the active SOFT
   stints' rules' `:penaltyPoints`; a SOFT stint whose rule has none costs the run's `soft_veto_penalty` (15), never 0. That includes a
   SOFT stint of a HARD rule (`LEVERAGE_EXTREME` emits one for a negative-equity firm): our assumption, not confirmed by
   upstream (T-191 ask (8)); nothing reads the penalty yet, so a wrong guess costs a comment. Reworded in the
   `:softVetoPenalty` and `:vetoSeverity` comments (and in `kg_target_schema.ttl`), `AttractivenessSnapshotShape`'s comment and `docs/06`. **2648 quads, unchanged.**

   **T-032 (Work item 4, 2026-10-12: how a restatement is written).** Comment only: `:supersededBy`'s comment in
   `tbox.ttl` now says a section is superseded once, by a new section of the same `itemLabel` declared in the same
   batch (the ingest gate's check 8), and that the sections not superseded are the current ones. No shape or
   property change. `kg_target_schema.ttl` does not carry `:supersededBy`, so it has no twin to update, and
   `protege-view.ttl` (generated) keeps the old comment until T-070 regenerates it. The rule is in `07`
   ("Restatements and re-runs"); the live store's copy of that one literal differed until the next reload, and
   `verify_store`'s size check still passed. **2550 quads, unchanged.**

   **T-151, the rule half (Work item 15, 2026-10-07).** Upstream can reuse a run id after a deletion, so
   `:runId` (`<run table>:<id>`) is not unique on its own. Its comment in `tbox.ttl` now says it is
   emitted only when read checks pass (run row exists, `cycle_type` matches for `cycle_run`, row time
   inside the run), which lowers the risk but does not prove uniqueness, until upstream's T-145 and T-100
   have landed; the full rule is in `SPEC.md` D7. Comment only (the same text `kg_target_schema.ttl`
   proposes); the checks themselves are code and land with T-031/T-163. **2473 quads; conforms: True.**
   **T-177, FUNDAMENTAL's `rawValue` range (Work item 15, 2026-10-10).** (The quad counts in this list are
   those of each change when it was written, not a running series.) Upstream answered Q6 (fifth
   reply): `raw_value` is the assessment's `score`, bounded `[0, 100]` by their model, and the
   rule-based fallback clamps to the same range. The `ScoreFinanciero` branch of `ScoreSnapshotShape`
   that requires a `rawValue` now also has `sh:minInclusive 0.0` and `sh:maxInclusive 100.0`. No new
   class or property; `AllDisjointClasses` is unchanged; the worked example conforms unchanged.
   Nine synthetic cases in `tests/test_schema_gate.py`, plus a check that `kg_target_schema.ttl` bounds `rawValue` like this file (FUNDAMENTAL, SECTOR, Sentiment) (0, 100, a mid value pass; below 0, above
   100, an integer, a string, a bound broken beside a `normalizedScore`, and a second value fail).
   Reloading the store (`cli/load_schema.py`, then `cli/verify_store.py`; the `urn:graph:tbox` graph grows by 2)
   was T-179, done 2026-10-10: the store then held 2549 triples (2550 since T-193) and `verify_store` passed (`docs/graphdb-setup.md`).
   **2549 quads (2547 before this change, plus the two bounds); conforms: True.**
3. **Two more named-graph placements (a third added by T-108).** `07-ontology-topology.md` assigned graphs to every
   *agent's* daily output but not to the Orchestrator's own decisions or to entity resolution's
   derived facts. Resolved: `urn:graph:ingest:ORCHESTRATOR:{date}` and
   `urn:graph:derived:entity-resolution:{date}` (and, since T-108, `urn:graph:derived:quant:{date}`; documented in `instances.trig`'s header).
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

6. **Upstream score polarity and scale (T-030, 2026-10-05).** Projecting real
   `portfolio-financial-analysis` scores surfaced a convention `06`/`07` never had to state:
   upstream's `normalized_score` is a 0–100 *strength* score (50 = cohort average, higher =
   better), while every `normalizedScore` here is a [0, 1] *risk* reading (`06` §1.8, the
   reason `WeightComponent.inverted` exists). The projection converts it as
   `1 − normalized_score/100` for VALORIZATION/TECHNICAL
   (`src/projection/score_scale.py`; FUNDAMENTAL until T-171, which stopped converting it
   because upstream rewrites its `normalized_score` in place, see refinement 2), and for `v_sector_aggregate_snapshot.mean_normalized` (the
   mean of members' TECHNICAL score) into `SectorAggregateSnapshot.normalizedScore`, so no shape
   and no `inverted` flag changes. Upstream's
   own `raw_value` maps to `rawValue`. **Open, not fixed:** SEMANTIC (= `Sentiment`) has a 0–100 `normalized_score`
   upstream but no `normalizedScore` here, and its `rawValue` must land in `[-1, 1]`
   (refinement 2, T-081); mapping upstream's values into that range is T-031's to decide
   (`SPEC.md` §2.6). SECTOR (= `SectorRelativeMomentum`) is settled by T-155: `rawValue` is read
   verbatim in `[-100, 100]`, and its 0–100 `normalized_score` is an optional `normalizedScore` that
   T-031 rescales like the other lanes.

7. **Contract v18 classes, shapes and GUARD rules (T-206, 2026-11-01).** The 11 views added between
   v12 and v18 now have ontology terms: `TickerHistory` (m016), `OrchestratorRun`/`OrchestratorStep`
   (m015) and the eight m018 backtest/GUARD classes `StrategyBook`, `BookRebalance`, `GuardAlert`,
   `GuardAction`, `BookWeightDaily`, `BookDailyPerformance`, `PortfolioPeriodSummary` and
   `BacktestTest`. `tbox.ttl` goes from 40 to **51 classes** (38 disjoint leaves, 13 backbone) and
   `shapes.ttl` from 20 to **31 named shapes**; `AllDisjointClasses` gains the 11 leaves. Placement is
   by property shape (`06` §1.2): `TickerHistory`/`BookRebalance` under `TemporalRelation`,
   `StrategyBook` under `Collection`, `GuardAction` under `RiskAndDecision`, and the other seven
   under `Observation` (dated records with scalar fields, not `ObservationSnapshot`s).
   - **Spanish labels/definitions** are the handoff §6.2 text verbatim (outer « » dropped), one
     `rdfs:label`@es and one `skos:definition`@es per class; English labels/comments stay. No FIBO
     `rdfs:seeAlso`: handoff §6.1 says FIBO has no class for backtest runs, strategy arms, GUARD
     rules, Sharpe, drawdown, turnover, costs or paired tests.
   - **Properties.** Every column of the 11 views has a property. The shared ones (`bookId`,
     `backtestRunId`, `armCode`, `windowId`, `knowledgeDate`, `status`, `decisionDate`,
     `guardTicker`, `guardLayer`, `segment`, `handle`, `startedAt`, `finishedAt`, `runKind`) carry
     **no `rdfs:domain`**, the `:runId` pattern (T-106), so sharing does not entail a disjoint class.
     Every m018 individual carries `:knowledgeDate` (xsd:date) for uniform `knowledgeDate <= D`
     queries. A book or a test links to its backtest run by the literal `:backtestRunId`: there is no
     `BacktestRun` class and no invented node. `v_guard_alert` has no `book_id`, so an alert reaches a
     book through its `:alertHasGuardAction` actions, not a direct property.
   - **TickerHistory's interval is inclusive.** `v_ticker_history.valid_to` is the symbol's last
     valid date (handoff §3.1), and the lookup is `date BETWEEN valid_from AND
     COALESCE(valid_to, '9999-12-31')`, so `TickerHistoryShape` uses `sh:lessThanOrEquals` and a
     one-day symbol (`validFrom == validTo`) conforms. `UniverseMembershipShape` is inclusive too
     since T-260 (upstream's `valid_to` is the last day of membership), so `validFrom == validTo`
     is a real one-day stint. The shared `:validTo` stays exclusive on `RuleDefinition` (T-187),
     `PortfolioPosition` and `AttractivenessWeightScheme`; the gate's `CLOSABLE` entry carries an
     `inclusive` flag for `TickerHistory` and `UniverseMembership`.
   - **Nullable columns.** `sh:minCount` is 1 only where the m015/m016/m018 DDL or handoff §3.3
     guarantees a value. Never required: `v_book_rebalance.cycle_run_id`, `v_guard_alert`
     asset/ticker/value, `v_guard_action` asset/ticker/weight_before/weight_after,
     `v_book_weight_daily` asset/holding_name/both target weights, `v_book.guard_layers`,
     `v_ticker_history` valid_to/evidence_url/evidence_date. The Orchestrator shapes require only
     their natural keys (`orchestratorRunId`; `stepOfOrchestratorRun` + `ordinal`): handoff §3.1 gives
     no base-table nullability and both views have 0 rows. A CASH weight row has no `:holdingAsset`
     and needs no `:Asset` node.
   - **Sourcery-review constraints.** `bookId` is required on `BookRebalance`/`GuardAction`;
     `BacktestTest`'s `pValue` is in [0,1] and `nObs` at least 1; six row-date properties are
     `sh:equals` to `:knowledgeDate` (rebalance `executionDate`, alert `alertDate`, action
     `effectiveDate`, weight `weightDate`, performance `performanceDate`, summary `dateTo`); a CASH
     weight row must have no `:holdingAsset`. `StrategyBook`/`BacktestTest` are deliberately not
     equated: their `knowledgeDate` is the run's `created_at` day, not a row date.
   - **Data over the DDL comments.** `v_book.guard_layers` is NULL on `MARKOWITZ_BASE` and
     `TOPN_MV_NOGUARD` (the DDL says `'[]'`), so it is optional; `exclude_hard_vetoed` is 0 on all
     three arms (the DDL says 1 for `TOPN_MV_*`), so the shape requires only an `xsd:boolean` and never
     a per-arm value. `drawdown`, `cost_return` and `max_drawdown` are non-negative in P1/P2/P3, but
     the handoff states no sign convention, so no sign or range constraint is placed on them.
   - **Rule catalog.** `UTILITY_CASH_COVERAGE` (HARD, `rule_input.utility_cash_coverage_3y < 0.05`,
     rank 10, valid from 2026-10-14 — the day T-071 part 2a (PR #167, merge commit `7ae8ba8`)
     reached upstream master, 2026-10-14 20:51:47 -0500 (already 2026-10-15 in UTC); T-216 supplied
     that real date, replacing 2026-10-31, the last safe date, used until then. It is not backdated
     to 2019/2020: valid-time means when a definition was in force in production, not that a
     backtest applies a rule retroactively — the P1 backtest replays history with today's catalog
     and raised this rule's veto on 2022-03-03, which is why backtest vetoes cannot resolve their
     rule by `raisedOn` (T-209); upstream's `v_rule_catalog.created_at` (2026-10-31T19:37:32) is a
     technical persistence timestamp, not the adoption date) joins the 9
     selection rules; the `LEVERAGE_EXTREME`/`NEGATIVE_FCF`/`LIQUIDITY_DISTRESS` comments record the
     APP-00 profile exemptions (financial firms; regulated utilities; equity REITs), with no
     threshold/severity/clause change. The 7 GUARD rules are `RuleDefinition`s in their own section,
     one `GraphPredicate` leaf each, `:category "GUARD"`, `:guardLayer` 1..4, frozen parameters only in
     `rdfs:comment`; `L2_NEWS` is disabled in the 2022–2025 backtest. They carry no
     `:ruleSeverity`/`:penaltyPoints`/`:priorityRank`. `RuleDefinitionShape` gets one extra `sh:or`
     branch for `:category "GUARD"`, keeps the severity requirement for every other active rule and
     makes `:priorityRank` mandatory for non-GUARD rules (range widened to `[1,10]`); `VetoShape`
     refuses a GUARD rule as `:appliesRule`/`:primaryRule`. A GUARD rule is not a veto rule.
   - **Projector (T-207).** The eight m018 views are now projected by `src/projection/backtest.py`
     (policy in `src/projection/project_backtest.py`, CLI `cli/project_backtest.py`) into
     `urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}` (T-231 added the run
     label), one append-only graph per run. The window qualifies the name because the P1/P2/P3
     databases each start their run/book ids at 1; the label qualifies it again because the views
     expose no run identity, so several result families can share a window.
     A dry run is the default and SHACL-validates each graph; `--write` appends through the gate
     and production also needs `--to-production`. The writer keeps every masked/NULL column out of
     the Turtle, links an asset only when the universe database has the ticker (point
     `SQL_UNIVERSE_DB` at `/workspaces/thesis/data/universe_history_gics.db` and load it with
     `cli/load_universe.py` first, or a real write is refused for want of the stored `:Asset`
     individuals; the full load is one-time per repository, and a later change is the
     `cli/load_universe.py --delta` incremental batch described in
     `docs/backtest-load-runbook.md` §1b), resolves
     `:alertRule` to `:Rule_{rule_id}` and refuses an unknown rule or a layer disagreement.
     `cli/verify_backtest.py` (logic in `src/projection/verify_backtest.py`, T-280) re-projects the
     source read-only and prints one `PASS`/`FAIL` line per check, including the run identity,
     triple and class counts, links, key aggregates, `:runLabel` and `:knowledgeDate`. No schema
     file changed, so the bundle stayed **4178 quads at that revision; conforms: True**.
   - **Not done here:** no change to the v18 pin, no ingest-gate pattern change beyond the
     schema-driven `CLOSABLE` entry, its `inclusive` flag for `TickerHistory` and
     `UniverseMembership` (a one-day symbol or stint must not be refused) and T-207's/T-231's
     backtest graph name, no GraphDB write/reload, and
     `protege-view.ttl` is not regenerated (generated file; T-070/T-071).

8. **Backtest selection side (Work item 26, 2026-11-04).** `v_cycle_run` now has a
   `:SelectionCycle` class (an `Observation`, like the other run-log classes), and the ranking side
   adds the T-155 properties `:rankPosition`, `:selectedForBook`, `:vetoedAtRanking`,
   `:targetWeight`, `:hasEffectiveWeight` and `:componentValue`; `:rankingOfCycle`,
   `:rankingTicker`, `:vetoTicker`, `:vetoRulesJson` and `:cycleType` carry the rest. `:cycleRunId`
   loses its `BookRebalance`-only `rdfs:domain` and is shared by `BookRebalance`, `SelectionCycle`
   and `AttractivenessWeightScheme`, the `:runId` pattern. A ranking snapshot keeps
   `:attractivenessOfAsset` optional and requires an asset link **or** `:rankingTicker`, because the
   shared universe database does not know every backtest ticker; a no-component row stays visible
   as upstream's placeholder (score 0.0, `vetoRulesJson` `["UNSCORED"]`/`["UNPRICED"]`, no
   `:hasEffectiveWeight`). `v_veto.evidence_json` is not projected (price-derived per-asset values
   are not published). The selection graph is the sibling
   `urn:graph:derived:backtest:selection:{run_label}:{P<n>|H<n>}:{run_id}`, accepted by the gate.
   `tbox.ttl` is now **58 classes (44 disjoint leaves, 13 backbone)** and `shapes.ttl` **39 named
   shapes** (the three new ones are `SelectionCycleShape`, `BacktestRankingShape` and
   `EffectiveWeightComponentShape`); `kg_target_schema.ttl` mirrors the new terms. **4915 quads;
   conforms: True.** No GraphDB write or reload was made.

9. **Final-backtest vocabulary (Work item 33, 2026-11-04).** The six date-ordered windows
   (`P1`, `H1`, `P3`, `H2`, `P2`, `H3`) and their segments use `^[PH][0-9]+$` /
   `^[PH][0-9]+[a-z]?$` in every shape, in `projection.backtest` and in both gate graph patterns;
   `MARKOWITZ_BASE_GUARD` joins the closed arm list (`guardLayers "[1, 3, 4]"`,
   `excludeHardVetoed false`). `L1_BP_STOP`/`L1_BP_REENTRY` are layer-1 GUARD rules valid from
   2026-11-04, and the alert shape forbids `:alertThreshold` on them (the threshold is an
   individual asset's stop price level; upstream's licence forbids redistributing it) while every
   other alert keeps its required threshold. `:ExchangeTradedFund` is an `:Asset` subclass for the
   core ETF; `SPY` is declared in `reference.ttl` with no CIK, membership or GICS classification,
   and `AssetShape` admits it while ordinary assets keep the CIK/closed-membership rule. There is
   no FIBO mapping for exchange-traded funds: the pinned 2026Q2 slice has no such term, so none is
   invented. `:BacktestRun` and `:RunConfiguration` are the run-metadata leaves, written to the
   append-only graph `urn:graph:derived:backtest:meta:{label}`; the configuration carries
   `configCodeCommit`, `configPr`, `configResultsDoc` and optional `configId`/`configStatus`, with
   the frozen English body text verbatim, hard line breaks included, in its `rdfs:comment`.
   Counts: **58 classes (44 disjoint leaves), 39 named shapes, 4915 quads; conforms: True.** The
   catalog is 643 written assets plus the six in `reference.ttl` = **649**.

10. **Ranking and severity comments (Work item 34, 2026-11-05).** Comments only, no structural
   change and no new count: `:selectedForBook` is candidate-pool membership (60 per decision
   cycle), not the at most 30 names held; `:targetWeight` is the cycle's own weight over that pool,
   never a portfolio weight (the held weights are `:finalTargetWeight`); `:rankPosition` counts
   vetoed names too; `:vetoSeverity` is read per veto row and is authoritative, so
   `LEVERAGE_EXTREME` can be `SOFT` although its catalog severity is `HARD`; `:topN` is the pool
   size (60), not the held cap. The `:AttractivenessSnapshot` English comment and Spanish
   `skos:definition` say the same, and `kg_target_schema.ttl` mirrors the four property comments.
   The Spanish `:StrategyBook` definition now says the Top-N arms use the cycle's Top-N pool
   ("selección del pool Top-N del ciclo"), not a fixed Top-30. No shape or term was added.
   This item adds no terms or shapes; the merged bundle is **4915 quads; conforms: True** (Work
   item 37 added the aggregates terms and Work item 38 added `bootstrap_mdd`). The store must be
   reloaded afterwards (`cli/load_schema.py`, then `cli/verify_store.py`) to pick up the changed
   comment/definition literals.

11. **Aggregates file (Work item 37, 2026-11-05).** Three new disjoint leaves under
   `:Observation`: `:AggregatesSet` (one per label), `:TrendFilterState` (one per window and decision
   date) and `:ReferenceReturn` (one per window, segment and reference). The set carries the source
   file name, its lowercase manifest SHA-256, the `config_id` and the three textual source
   descriptions; the rows carry `:trendState`/`:cashFraction` and the two Top-N arms, or
   `:referenceName`/`:referenceTotalReturn`/`:referenceMaxDrawdown`/`:nSessions`. The new properties
   `:trendWindow`, `:trendDecisionDate`, `:returnWindow`, `:returnSegment`, `:referenceDateFrom`,
   `:referenceDateTo`, `:nSessions`, `:referenceName`, `:referenceTotalReturn`,
   `:referenceMaxDrawdown`, `:cashFraction`, `:appliesToArm`, `:aggregatesSet` and the six
   `:AggregatesSet` fields avoid reusing a property whose `rdfs:domain` would entail a disjoint
   class. Every new property's English `rdfs:comment` is the file's dictionary text verbatim; the
   three shapes close the label/window/segment/state/reference lists with `sh:pattern`/`sh:in`.
   The append-only graph is `urn:graph:derived:backtest:aggregates:{label}`; `sources.
   spy_total_return_series_sha256` is validated and never projected, and no daily series, price
   level or 210-session mean is stored. Counts: **58 classes (44 disjoint leaves), 39 named shapes,
   4915 quads; conforms: True.**

12. **Bootstrap MDD test name (Work item 38, 2026-11-05).** `bootstrap_mdd` joins the closed
   `:testName` list in `BacktestTestShape` and the two `:testName` comments in `tbox.ttl` (and the
   `kg_target_schema.ttl` mirror). It is upstream's paired circular block bootstrap of the
   maximum-drawdown difference MDD(arm_a) − MDD(arm_b) in the segment (block 5, 4999 replicates,
   seed 20261104; the statistic is that difference as a fraction, positive when arm_a fell more;
   the p-value is two-sided), from `src/cycle/backtest/stats.py::bootstrap_mdd_diff`. No other
   shape, term or check changed: arms, rule ids, alert states, action statuses, cycle types, veto
   severities and the window/segment patterns stay as they were. The extra `sh:in` member adds two
   triples, so the bundle is **4915 quads; conforms: True** and the load plan is **5192 asserted
   triples**. The store must be reloaded afterwards (`cli/load_schema.py` with
   `KG_REPOSITORY=portfolio_test`, then `cli/verify_store.py`).

13. **`:objective` comment (Work item 41, 2026-11-09).** Comment only: the `:objective` comment in
    `tbox.ttl` (and the `kg_target_schema.ttl` mirror) now says upstream's `_insert_books` writes
    `'min_var'` as a fixed literal for every optimized arm and `'equal_weight'` for the benchmark
    `SP500_EW_INTERNAL`, independent of the run's `satellite_weighting`; the delivery's
    `config_final.md` describes a minimum-variance optimisation keeping at most 30 names followed
    by minimum-CVaR weighting, so `'min_var'` is not the `TOPN_MV_*` weighting objective and must
    not be presented as such; upstream's confirmation is pending. No shape, term or count changed:
    **4915 quads; conforms: True**, load plan **5192 asserted triples**. The store must be reloaded
    afterwards to pick up the literal.

14. **External mean-variance base Markowitz (Work item 44, 2026-11-09).** `MARKOWITZ_MV` joins
    every closed `:armCode` `sh:in` list (the eight arm-bearing shapes) and `:dataSource`
    (`xsd:string`, optional, at most one) is declared on `:StrategyBook`; the `:codeVersion`
    comment now also covers the external simulator's SHA-256. `src/projection/mv_base.py` and
    `cli/load_mv_base.py` load the external summary-only book into
    `urn:graph:derived:backtest:external:{label}`; its `bookId` is the engine's maximum + 1 and its
    `backtestRunId` is the engine's own run id, both read read-only from `final_<window>.db`
    (`objective "max_sharpe"`, pending Reviewer A). The gate accepts that graph name. No class or
    named shape was added: **58 classes (44 disjoint leaves), 39 named shapes, 4940 quads;
    conforms: True**, load plan **5217 asserted triples** (production **4696**). The store must be
    reloaded afterwards (`cli/load_schema.py` with `KG_REPOSITORY=portfolio_test`, then
    `cli/verify_store.py`).

15. **Presentation vocabulary (Work item 43, T-752, 2026-11-10).** `labels.ttl` loads into
    `urn:graph:labels`; `LabelConceptShape` requires one `skos:notation`, one `skos:inScheme`, one
    `rdfs:label`/`rdfs:comment` per language and only `@en`/`@es` `skos:altLabel`s on every concept
    marked with `:labelScheme :PresentationScheme`. The file is now in the FR-001 bundle and the
    load plan. Counts: **58 classes (44 disjoint leaves), 40 named shapes, 6072 quads;
    conforms: True**; load plan **21 graphs / 6349 asserted triples** (production **5 / 5828**).
    The store must be reloaded afterwards.

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
`clearedOn`/`lastSeenOn` earlier than `raisedOn` (T-185, in the next paragraph, adds a `lastSeenOn` later than
`clearedOn`). `lastSeenOn` is deliberately multi-valued because the ORCHESTRATOR graphs are append-only: each
cycle adds its own value, current = `MAX`. `:expiresOn` (T-188, below) is the other multi-valued
Veto property: written only when upstream moves it.
A stint is closed by writing `clearedOn` in the clearing cycle's graph, never by deleting the
`Veto`; the worked example closes `Veto_XOM_20260804` on 2026-08-05 and gives
`Veto_XOM_MKT_20260805` a SOFT `vetoSeverity`. Upstream's wall-clock `cleared_at` is dropped.
**1771 quads; conforms: True.**

**T-185 (a Veto's sightings against its clearing, 2026-10-11).** `VetoShape`'s `lastSeenOn` gains
`sh:lessThanOrEquals :clearedOn`: a cycle that clears a stint did not see it raised, so no sighting is later
than the clearing (the same day passes). One triple in `shapes.ttl`; no class or property; **2550 quads;
conforms: True.** The `urn:graph:tbox` graph (which holds `shapes.ttl`) grows by 1 in the store; the reload
(T-193, as T-179 was) was done 2026-10-12: the store holds 2550 triples.

**T-104 (D5, decided 2026-10-03: model it).** `:DataQualityIssue` is an `EvidenceSource` leaf — one row of upstream's `data_quality_issue` (`dqGateCode`, `dqSeverity`, `quarantined`, `gatedValue`, `dqIssueOfAsset`) — so a HARD gate that raises the `DATA_QUALITY` veto has an evidence target: a `RiskEvent` is `backedBy` it. Written to the FUNDAMENTAL ingest graph (the Ring-1 gates run in the fundamental agent). `DataQualityIssueShape` is the 16th shape; `dqSeverity` is not enumerated because only HARD is documented upstream. The 25th class joins `AllDisjointClasses`. Review follow-up: the issue also carries `dqRaisedOn` (required, the as-of key), optional `dqIssueOfFiling`/`dqMetricName`/`provenanceId`, and the worked example is a HARD issue on JNJ (graph `FUNDAMENTAL:2026-Q4`) backing `Veto_JNJ_DQ_20261005` through a `RiskEvent` in `ORCHESTRATOR:2026-10-05` — dated after `Rule_DATA_QUALITY`'s `validFrom` (2026-10-02) so `:appliesRule` resolves to a rule valid on the veto's date; the gate code and values are illustrative. `instances.trig` now has 14 `GRAPH` blocks. The cutoff checks above (08-03…08-05) are unchanged; at 2026-10-05 the query also returns `Veto_JNJ_DQ_20261005` (plus the earlier stints, whose `lastSeenOn` the worked data does not advance). `protege-view.ttl` has no generator in this repo and is stale (it predates T-102–T-104); regenerate it before relying on it in Protégé. **1881 quads; conforms: True.**

**T-101 (D2, decided 2026-10-03: new properties, not graph-date encoding).** `ScoreSnapshot` gains `:availableAt` (xsd:date, **required**) and `:eventTime` (xsd:date, never after `availableAt`; optional in the shape so a source row that lacks `event_time` still validates, although every agent defines it and the worked data and the news ETL always set it). `timestamp` stays the compute/ingest time. Encoding it in the ingest-graph date was rejected: graphs are dated by ingest batch, and a quarterly FUNDAMENTAL graph would still mix filings with different availability. Every as-of-D reader of `ScoreSnapshot`s filters `availableAt <= D` (never `eventTime`/`timestamp`). `SectorAggregateSnapshot` and `AttractivenessSnapshot` are same-cycle derived outputs and get no second clock: they are usable from the date of their `timestamp`/`computedAt`. Worked data: the Q3 FUNDAMENTAL snapshots have `eventTime` 2026-06-30 (period-end) and `availableAt` 2026-07-06 (the first trading day after an illustrative filing date; 07-05 is a Sunday); the daily agents use the cycle date for both. `src/etl/news_to_rdf.py` now emits `eventTime` (article day) and `availableAt` (the later of the article day and the day the score was processed) on its SEMANTIC snapshots. `RiskEvent`/`DataQualityIssue` are not covered yet (they keep `detectedAt`/`dqRaisedOn`). 1951 quads; conforms: True.

**T-105 (D6, 2026-10-03: `QUANTITATIVE` → `VALORIZATION`).** `agentOrigin` is now `FUNDAMENTAL | SEMANTIC | VALORIZATION | TECHNICAL | SECTOR` (matches upstream migration m006); the worked graph is `urn:graph:ingest:VALORIZATION:2026-08-05` and `src/kg_store/gate.py` accepts that name (`QUANTITATIVE` graphs are no longer valid ingest names). **Migration:** an already-loaded repository must `DROP GRAPH <urn:graph:ingest:QUANTITATIVE:2026-08-05>` once (`load_schema.py` leaves removed graphs in place; see `docs/graphdb-setup.md`). The `:Snap_*_Quant_*` IRI stems are historical. The metric id `ScoreCuantitativo` is **kept, decided in the T-109 review** (upstream identifies a score only by `score_type`, i.e. `agentOrigin`; `metricType` is this ontology's own vocabulary, so there is no upstream id to rename to) and now carries a note. What `eventTime` means per score type: FUNDAMENTAL = filing period-end; TECHNICAL, VALORIZATION and SECTOR = cycle date; SEMANTIC = article day. Extra upstream provenance not yet modelled (handed to T-106, whose scope now names them): `forensic_flags_json`, `prompt_hash` (FUNDAMENTAL), `correction_rule` (`financial_facts`). **1953 quads; conforms: True.**

**T-106 (D7, 2026-10-03: run provenance).** Decision: four optional properties, no `Run` class. `runId`, `runAsOf`, `codeVersion`, `engineVersion` have **no `rdfs:domain`** (like `provenanceId`): D7 says every upstream row carries `run_id`, and a domain on `ScoreSnapshot` would have entailed that type on a `Veto` and clashed with `AllDisjointClasses`. SHACL allows them (optional) on `ScoreSnapshot`, `SectorAggregateSnapshot`, `Veto`, `PortfolioPosition`, `DataQualityIssue` (T-107) `AssetCoOccurrence` and (T-108) `BenchmarkObservation`; `AttractivenessSnapshot` is computed here, not upstream, so it has none. Why not a `Run` class: run values are identical across a run's rows and the run log (params, dirty-tree reason) stays upstream, so a node would duplicate it; the price is ~6–9M triples (see `docs/07`'s scale table), accepted for a single-node store and to be revisited if it grows. Read rule for several `engineVersion`s of one key: `docs/07` 'Run provenance'. **Extras (T-105 hand-off):** `forensic_flags_json` and `prompt_hash` (FUNDAMENTAL) and `correction_rule` (`financial_facts`) are **not projected**. They are per-row upstream fields, not run-log fields, so `runId` does not by itself reach them (the row key does); T-109 confirmed `v_score_snapshot` exposes neither, and no view exposes `financial_facts`. On `Veto` and `PortfolioPosition` (appended to by later cycles) the four properties record only the run that **opened** the record; later cycles must not re-emit them. The example `runId`/`codeVersion`/`engineVersion` values in `instances.trig` are placeholders (upstream's `run_id` is an integer, T-109), and `runAsOf` is omitted from the cycle-type examples (it equals `eventTime`). **2064 quads; conforms: True.**

**T-107 (D10, 2026-10-03: candidate edges are not `sharedExecutiveWith`).** Decision: a new reified class `:AssetCoOccurrence` (under `Observation`, 26th disjoint leaf) with `coOccurrenceAsset` (exactly 2), `coOccurrenceKind` (`SHARED_EXECUTIVE_CANDIDATE` only), `coOccurrenceMethod`, `coOccurrenceWeight`, and an optional `coOccurrenceComputedOn` (no upstream computed-at column is confirmed; `runId`/`runAsOf` can carry the date; T-109). The four T-106 run properties are optional on it too. Rationale: the edge carries data (method, weight), so by this ontology's n-ary convention it is a class, and a plain property would either assert weak news evidence as fact or lose the method. `:sharedExecutiveWith` stays for verified directorships only. No `confidence` is modelled: upstream emits only `weight` (mean NER score sits in `evidence_json`, not projected). `media_cooccurrence` (non-executive, empty until upstream's T-082) is deferred: its endpoints may not be two assets, so a `MEDIA` kind and its own shape rules are decided once its columns are known (T-109). Weights are in each method's own unit, so readers must filter by method. Recomputes are new individuals in new dated graphs. The ETL projector is not built yet. **2150 quads; conforms: True.**

**T-108 (D11, 2026-10-03: quant scope).** Decision (maintainer, filtered by "integration, not processing"): only what upstream already computed and exposes through a `v_*` view is projected: benchmark books (`v_quant_portfolio`), their weights (`v_quant_position`), performance numbers (`v_quant_benchmark_performance`) and active weight vs the live book (`v_quant_vs_live`). Shape: `:Portfolio` gains a required `portfolioKind` (`LIVE`/`BENCHMARK`, written explicitly by the projection according to the source view: `v_portfolio_position` is LIVE, `v_quant_portfolio` is BENCHMARK) and `benchmarkObjective` (upstream's label, verbatim) under a new `PortfolioShape`; benchmark weights are plain `PortfolioPosition`s; a new reified `:BenchmarkObservation` (under `Observation`, 27th disjoint leaf) carries `quantPortfolio`, `quantMetric` (free text), `quantValue`, optional `quantAsset` (per-asset active weight), `quantUnit` (upstream's unit, never converted) and `quantAsOf`; `quantPortfolio` must point at a BENCHMARK or the LIVE book (`QuantSubjectShape`). A benchmark book has one stable IRI like the live book; later runs close old weights by `validTo`. Upstream's weights and returns are fractions, so the unit is `fraction` (a plain proportion), `fraction_annual` (`expected_*`) or `fraction_daily` (`realized_return`, `active_return`, …; vocabulary in the T-109 paragraph below), and only `quant_position` weights are scaled ×100 into `weightPct` (settled in T-109), plus the optional T-106 run properties. Not projected: return series, μ, Σ, `risk_free_rate`, `corporate_action`, `benchmark_series`, `quant_frontier_point` (an optimizer output; judging it is upstream's job). Nothing is computed or derived here. New graph `urn:graph:derived:quant:{date}`. The ETL projector is not built yet. **2298 quads; conforms: True.**

**T-109 (2026-10-05: upstream contract read from `portfolio-financial-analysis` @`8da3868`).** Settled by reading upstream's `kg_schema`: `schema_version` floor 9; `v_cycle_ranking` returns every run; upstream `run_id` is an integer numbered per run table, so `runId` stays a string written `<run table>:<id>` (e.g. `cycle_run:42`). Quant: `v_quant_portfolio` also holds `kind='live_book'` (upstream's snapshot of the live book, used to measure its return). It is **not** projected as a `Portfolio` (it would duplicate the live holdings under a BENCHMARK label); its performance numbers attach to the LIVE `Portfolio` (`quantPortfolio` may point at either kind; `BenchmarkBookShape` became `QuantSubjectShape`). New optional `benchmarkKind` (upstream's `kind`, the `v_quant_vs_live` join key) beside `benchmarkObjective` (`objective`), and `quantBenchmark` (the reference index an `active_return` is measured against). `quantUnit` vocabulary: `fraction`, `fraction_annual`, `fraction_daily`, `ratio`, `count`. **2352 quads; conforms: True.**

**T-111 (D14, 2026-10-05: `scoreMethod` discriminator).** `ScoreSnapshot` gains an optional, functional `:scoreMethod` (xsd:string, **open vocabulary**, no `sh:in`). Why: upstream's boundary note (`semantic-score-boundary.md` W11, rollout step 4) wants a discriminator on `score_snapshot[SEMANTIC]` so that two producers of the same `(agentOrigin, metricType)` can coexist through the cut-over without a reader double-counting. Our per-article FinBERT `Sentiment` snapshots from `src/etl/` now carry `ARTICLE_SENTIMENT`; the future per-`(asset, day)` aggregate that `portfolio-financial-analysis` materializes will carry whatever value upstream settles on, which is why the vocabulary is not enumerated. The five worked per-`(asset, day)` SEMANTIC snapshots in `instances.trig` carry `ASSET_DAY_AGGREGATE`, an **illustrative placeholder** to be replaced by upstream's value. Convention: every SEMANTIC snapshot carries `scoreMethod`; one without it is the only method of its `agentOrigin` (all non-SEMANTIC today). It is not upstream's `score_snapshot.model` (a method label defaulting to `'deterministic'`). Reader rule: a query for SEMANTIC scores should filter or group on `scoreMethod`, never mix an article-level and an asset-day row in one average. The "remove the SEMANTIC write path" half of upstream's step 4 needs no code here (the ETL only ever wrote Turtle); the stale attribution sits in upstream's `README.md`/`docs/README.md`/`docs/kg_schema.md`. `protege-view.ttl` is not regenerated (T-071). **2366 quads; conforms: True.**

**T-100 (D1, 2026-10-05: `universe.db` is the asset master).** Maintainer decision: the ETL reads `portfolio-data-mining`'s point-in-time `universe.db` instead of Wikipedia's live table, so every membership stint becomes a `:UniverseMembership` (`validFrom`, and `validTo` while closed; `validTo` is inclusive, the last day of membership, corrected by T-260) in one `:Universe` (`:SP500Index`, emitted by the ETL into `data.ttl`, not stored here). One shape change: `AssetShape`'s `cikNumber` is no longer unconditionally required. It is now `sh:maxCount 1` plus a `sh:or`: either the asset has a `cikNumber`, or it has at least one `:UniverseMembership` and every one of them has a `validTo`. Why: upstream records no CIK for a company that has left the index (all closed stints lack it), and inventing one would put false data in the graph; a current member without a CIK still fails. `UniverseMembershipShape` also declares `validTo` (`xsd:date`, at most one) and requires `validFrom` not after it, so a one-day stint conforms; a `validTo` before `validFrom` holds on no date and is rejected (upstream's two one-day 1976 stints, `HNG` and `AYE`, are kept by the reader and dropped by `--since`). Checked with five cases (closed-only without CIK passes; open without CIK, closed-plus-open without CIK, and no membership without CIK fail; CIK without membership passes). No new class or property; `AllDisjointClasses` is unchanged. **2383 quads; conforms: True.**

**T-206 (Contract v18 ontology, 2026-11-01).** The 11 new classes, their properties and 11 shapes are in `tbox.ttl`/`shapes.ttl` (refinement 7 above), and `rules.ttl` now has the 10 selection rules plus the 5 GUARD rules. `TickerHistory`'s interval is inclusive (`validFrom <= d <= validTo`; a one-day symbol is valid), and the Orchestrator shapes require only their natural keys (`orchestratorRunId`; `stepOfOrchestratorRun` + `ordinal`) because handoff §3.1 gives no base-table nullability and both views have 0 rows. The bundle parses clean and `pyshacl` conforms: **4178 quads at that revision; conforms: True.** The canonical command is the same as above (`tbox.ttl` + `shapes.ttl` + `reference.ttl` + `rules.ttl` + `instances.trig`); the test suite also validates the flat union with `rules.ttl` included. No GraphDB write or reload was made in that change; the store was reloaded with T-212 on 2026-11-02 (`docs/graphdb-setup.md`), and `verify_store` passes. `schema/protege-view.ttl` is generated and was not regenerated (T-070/T-071).

**T-210 (FIBO Phase 1, 2026-11-03).** FIBO is a reference vocabulary, not a dependency: six
`rdfs:seeAlso` links, no `owl:imports`/`owl:equivalentClass`/`rdfs:subClassOf`, no FIBO axioms in
reasoning. `tbox.ttl` loses the two broken `https://www.omg.org/spec/EDMC-FIBO/` links (`:Asset`'s
`LegalPerson`, with no replacement because `:Asset` is one node per company line for a pure rename
(T-264) and FIBO has no matching term; `:SECFiling`'s
`Filing`, replaced by `Report`) and gains the six links in `fibo_terms.csv`: `:Portfolio`,
`:PortfolioPosition`, `:tickerSymbol`, `:Sector`, `:Industry` and `:SECFiling`. `kg_target_schema.ttl`
gets the same removals and four of the six links (it does not declare `:Sector` or `:Industry`; it
only refers to them as ranges). The net is +4 triples in `tbox.ttl`: the bundle is **4182 quads;
conforms: True**. `schema/fibo_terms.csv` is the source for the links and the later slice; the
Spanish columns are empty until Phase 2. `cli/check_fibo_terms.py` (logic in
`src/projection/fibo_terms.py`) checks the six IRIs against the pinned FIBO 2026Q2
`prod.ttl.zip` (sha256 `7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579`) with a
label and a definition; it is outside the hermetic suite because the zip is not committed. The
real run printed six `IRI -> label` lines in 1.6 s at ~111 MB peak. `protege-view.ttl`/`.txt` are
generated and still carry the old EDMC-FIBO IRIs until T-070/T-071; the Phase 2 slice (`fibo.ttl`,
`@es` text, S1–S5) is not started.

**T-211 (FIBO Phase 2, 2026-11-03).** `schema/fibo.ttl` is the 25-seed glossary slice: 54 entries
(25 seeds plus 29 ancestors), 223 English statements (54 labels, 54 definitions, 63 named
`rdfs:subClassOf` edges, 37 explanatory notes, 7 abbreviations, 6 synonyms, 2 usage notes), 50
Spanish statements (25 `rdfs:label`@es + 25 `skos:definition`@es) and 4 header statements (version,
sha256, verbatim MIT licence, comment), 277 in total. It has no `rdf:type`, so no FIBO term is an
`owl:Class` here. `schema/fibo_terms.csv` now has 25 rows with the reviewed Spanish columns;
`cli/build_fibo_slice.py` (logic in `src/projection/fibo_slice.py`) refuses any other sha256 and
rebuilds the file deterministically. `tbox.ttl` gains one `@es` label and one `@es` definition on
each of the 27 pre-existing leaf classes (the 11 v18 texts are unchanged), so the FR-001 bundle was
**4236 quads at that revision; conforms: True**. `fibo.ttl` loads into `urn:graph:reference:fibo` after
`reference.ttl` (S1); with it that load was 20 graphs and 4513 asserted triples.
No GraphDB write or reload was made in that change; the store was reloaded with T-212 on
2026-11-02, and the live Appendix A queries ran with T-213 the same day (`docs/graphdb-setup.md`).
`protege-view.ttl`/`.txt` are still generated and stale (T-070/T-071).

**T-220 (asset master through the ingest gate, 2026-11-03).** `UniverseMembershipShape` gains
`sh:class :Asset` on `:membershipAsset` so the gate's context read follows a stored Asset a
membership batch points at. Without it `gate.context_predicates` fetched only `rdf:type` for the
five assets `reference.ttl` already declares, and `AssetShape` then failed on
`:tickerSymbol`/`:cikNumber`. The `:membershipUniverse` half waited on T-227 (the backtest
projector's dry-run context did not type `:SP500Index`); T-227 typed it and added the second
`sh:class` triple, so both ends are now checked. At
that revision the FR-001 bundle was **4237 quads; conforms: True** (4236 + 1; 4204 after T-227 and
T-233/T-234), and a fresh `cli/load_schema.py` load was 20 graphs and 4514 asserted triples
(4513 + 1; 4481 after T-227 and T-233/T-234); no store was
reloaded in that change.
`cli/load_universe.py`
(logic in `src/kg_store/universe.py`) loads the real `:Universe`/`:Asset`/`:UniverseMembership`
population from `universe.db` into `urn:graph:universe:{year}-Q{n}` through the gate; `reference.ttl`
keeps its six worked-example individuals, and the loader gives the five index constituents memberships without re-declaring
them. Work item 28 adds `--delta`: it reads the stored assets and `:SP500Index` memberships with
`SELECT`, writes only new assets/memberships and untyped `:validTo` closures into
`urn:graph:universe:{year}-Q{n}:delta:{n}`, and reports drift without applying it. The gate accepts
that suffix as append-only; the base quarter pattern is unchanged. The overlap with
`instances.trig`'s worked-example memberships is documented in `docs/07`.
**T-216 (`UTILITY_CASH_COVERAGE` `validFrom`, 2026-11-03).** The upstream maintainer supplied
T-071's real integration date: part 2a (PR #167, merge commit `7ae8ba8`) reached upstream master on
2026-10-14 20:51:47 -0500 (already 2026-10-15 in UTC), so the rule's `validFrom` is now 2026-10-14,
not 2026-10-31, the last safe date, used until then. Only that literal and the surrounding
block/`rdfs:comment` changed in `rules.ttl`; the bundle was unchanged at **4236 quads at that
revision**. No GraphDB write or reload: the live store keeps 2026-10-31 for this rule until the next
`cli/load_schema.py` (T-212).

**T-233/T-234 (run labels and the window vocabulary, 2026-11-03).** A completed backtest run's
views expose neither an input hash nor its parameters, so two result families of the same window
would project the same graph and the same individual IRIs. `:runLabel` (xsd:string,
`[a-z][a-z0-9_]{1,31}`) is now **required** on `StrategyBook` and `BacktestTest`, the two m018
classes with no book link; a book's children reach its label through the book, and an alert
through its actions. The CLI names it (`--db LABEL=PATH`), the graph is
`urn:graph:derived:backtest:{run_label}:{window_id}:{backtest_run_id}` and every individual IRI
stem carries it (`Book_{label}_{window}_{arm}`, `BookWeight_{label}_{window}_{arm}_{date}_{key}`,
…). `windowId` and `segment` stop being closed `sh:in` lists: they are `sh:pattern` `^[PH][0-9]+$`
and `^[PH][0-9]+[a-z]?$` in `shapes.ttl`, in the projector and in the gate's graph pattern, so a
fourth window or a new sub-period needs no schema edit. **Trade-off:** a typo in a window id is
no longer caught by SHACL (`P4` for `P1` is a well-formed window); the arm list stays closed. Five
window lists and two segment lists become one triple each (−50) and `:runLabel` adds 16 (a
property with its comment in `tbox.ttl`, and a required `sh:property` with five constraints in each
of the two shapes), so after merging with T-220 the bundle is **4634 quads at Work item 33; conforms: True**
(4236 + 2 − 50 + 16, the +2 being T-220's `sh:class :Asset` and T-227's `sh:class :Universe`) and a
fresh load is 20 graphs and 4708 asserted triples (4513 + 2 − 34).
`kg_target_schema.ttl` carries the same property and shapes. No GraphDB load was made; the
maintainer must reload the schema and drop any backtest graph written under the retired unlabelled
name (`urn:graph:derived:backtest:{window_id}:{run}`) before projecting with labels.

**T-260/T-264 (inclusive membership end and the CIK fold, 2026-11-04).** `UniverseMembershipShape`
switches `sh:lessThan` to `sh:lessThanOrEquals`, so a one-day stint (`validFrom == validTo`) is
valid and only a `validTo` before `validFrom` fails; `gate.CLOSABLE` also treats a membership as
inclusive. The asset catalog is resolved by CIK in `etl.asset_master.resolve_assets`: a pure ticker
succession is one `:Asset` named by its latest symbol, while concurrent classes, a mixed CIK and a
CIK-less symbol stay per symbol. `projection.backtest.universe_assets` and
`projection.score_snapshots.universe_symbols` use the same resolver. No class or property changes,
so the FR-001 bundle is still **4204 quads; conforms: True**. No GraphDB write or reload was made.
On `universe_history_gics.db` at the default `--since`, the final dry run wrote 643 `:Asset`s plus
six in `reference.ttl` (649 assets from 654 symbols; six successions folded), 658 memberships,
6548 triples; 59 written assets lack `:classifiedAs` and the P1/P2/P3 dry runs leave 0 tickers
unlinked.

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
Full audit results (0 cycles, 0 self-loops, all 37 classes (38 since T-104, 39 since T-107, 40 since T-108: `DataQualityIssue` under `EvidenceSource`, `AssetCoOccurrence` and `BenchmarkObservation` under `Observation`) reach one of the 6 taxonomy roots, all
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
