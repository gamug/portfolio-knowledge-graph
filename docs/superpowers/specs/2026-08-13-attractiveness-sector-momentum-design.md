# Attractiveness Score + Sector-Relative Momentum — Design Spec

**Date:** 2026-08-13
**Status:** Approved for implementation (brainstorming session, chat-approved 2026-08-13)
**Closes:** critique-and-evolution.md gap #2 (no inclusion mechanics) in part — the ranking half
of B3, not the sizing/rebalancing half — and gap #3 (no sector layer) in part — the
sector-relative-momentum signal half of B2, not the full Sector/Industry roll-up dashboard.

## 1. Motivation

`schema/rules.ttl` implements the full 6-rule veto (exclusion) catalog, but v1 and the current
ontology have no positive counterpart: nothing ranks *surviving* candidates against each other.
critique-and-evolution.md already named this (gap #2, layer B3: "an attractiveness/ranking score,
the positive counterpart to the veto score") and separately named the missing sector layer (gap
#3, layer B2). This spec implements the intersection of both: a per-Asset **attractiveness score**
for ranking non-vetoed candidates, fed in part by a new **sector-relative momentum** signal, with
that same signal also wired into a new 7th veto rule (an asset can be excluded for badly
underperforming its sector peers, not just on the original 6 dimensions).

**Explicitly out of scope** (deferred to later B3/B2 work, not silently dropped — noted so a future
pass doesn't assume this spec covers them):
- Position sizing / weightPct assignment from the score (B3's sizing module).
- Full Sector/Industry dashboard-style roll-ups beyond the one aggregate metric needed here.
- Rebalancing cadence, correlation/concentration caps.

## 2. New TBox classes and properties (`schema/tbox.ttl`)

Three new classes, following the existing `ScoreSnapshot`/`Veto`/`RuleDefinition` shapes exactly
rather than inventing new patterns:

### `SectorAggregateSnapshot`
Immutable, one per (`Sector`, date). Same shape as `ScoreSnapshot`: `normalizedScore` (mean of
member assets' `ScoreTecnico` normalizedScore that day), `metricType`, `timestamp`,
`agentOrigin='SECTOR'`. New object property `sectorSnapshotOfSector` (domain
`SectorAggregateSnapshot`, range `Sector`, functional), inverse `hasSectorSnapshot`.

### `SectorRelativeMomentum` — no new class
This is a new `metricType` value on the *existing* `ScoreSnapshot` class, `agentOrigin='SECTOR'`,
domain `Asset` (via the existing `hasScoreObservation`). Computed as
`assetTecnicoNormalizedScore - sectorAggregateNormalizedScore` for that asset's sector that day,
stored in the existing `rawValue` field (range roughly `[-1.0, 1.0]`: negative = underperforming
sector peers, positive = outperforming). `normalizedScore` is left unset for this metricType (no
natural [0,1] reading of a signed delta) — first precedent for a `ScoreSnapshot` that populates
`rawValue` but not `normalizedScore`; SHACL's `minCount 1` on `normalizedScore` must be relaxed for
this one metricType (see §4).

### `AttractivenessSnapshot`
Immutable, one per (`Asset`, cycle) — parallel to `Veto`, not to `ScoreSnapshot`, since it's a
*computed decision output*, not a raw agent observation:
- `attractivenessScore` (`xsd:decimal`, `[0.0, 1.0]`, 1 = most attractive)
- `computedAt` (`xsd:dateTime`)
- `attractivenessOfAsset` (functional, → `Asset`)
- `computedWithScheme` (functional, → `AttractivenessWeightScheme`) — audit trail, same reason
  `Veto` points at `RuleDefinition` via `appliesRule`.

No stored rank field — rank is relative to whatever comparison set a query defines (all
candidates today vs. a sector subset vs. the current portfolio), so it's a query-time `ORDER BY
attractivenessScore`, never a persisted fact.

### `AttractivenessWeightScheme` + `WeightComponent`
Versioned graph data, mirroring `RuleDefinition`'s "rules live in the graph, not code" pattern
(closes the same class of problem as critique gap #6, applied to weights instead of thresholds):
- `AttractivenessWeightScheme`: `schemeId`, `validFrom`/`validTo`, `hasWeightComponent` (1..*, →
  `WeightComponent`).
- `WeightComponent`: `metricName` (`xsd:string`), `weight` (`xsd:decimal`), `inverted`
  (`xsd:boolean` — see §3 for why this flag exists).

### Disjointness
`AllDisjointClasses` grows from 20 → 24 members (add `SectorAggregateSnapshot`,
`AttractivenessSnapshot`, `AttractivenessWeightScheme`, `WeightComponent`). Comment above the
block must be updated to say 24, matching the pattern already established for the 20→24 change
(see `schema/README.md`'s own note on keeping this comment in sync).

## 3. Attractiveness score formula

Every existing `ScoreSnapshot.normalizedScore` in this ontology is a **risk** score — "0 = no risk,
1 = critical risk" (`tbox.ttl`'s own comment on `normalizedScore`). Attractiveness is the inverse
sense: low risk + positive sentiment + positive sector momentum = attractive. Rather than hardcode
that inversion per metric, `WeightComponent.inverted=true` marks the risk-oriented metrics
(`ScoreFinanciero`, `ScoreCuantitativo`, `ScoreTecnico`) so the Orchestrator's evaluator applies
`(1 - normalizedScore)` before weighting; `Sentiment` and `SectorRelativeMomentum` are
`inverted=false` and pulled from `rawValue`, rescaled from `[-1,1]` to `[0,1]` first
(`(rawValue + 1) / 2`), consistent with `ThresholdComparison`'s existing raw-vs-normalized
per-metric dispatch convention (`tbox.ttl`'s comment on `ThresholdComparison` — this spec adds
`SectorRelativeMomentum` as a third entry in that same dispatch table, compared via `rawValue`
exactly like `Sentiment`).

```
attractivenessScore = Σ weight_i * component_i   (weights sum to 1.0)
component_i = (1 - normalizedScore_i)     if inverted
component_i = (rawValue_i + 1) / 2         if not inverted
```

Initial `AttractivenessWeightScheme` (v1 of the scheme, placeholder pending calibration — same
status as every veto threshold today): equal-ish weighting across the five inputs
(`ScoreFinanciero` 0.25 inverted, `ScoreCuantitativo` 0.2 inverted, `ScoreTecnico` 0.2 inverted,
`Sentiment` 0.2 not inverted, `SectorRelativeMomentum` 0.15 not inverted).

## 4. New SHACL shapes (`schema/shapes.ttl`)

- `SectorAggregateSnapshotShape`, `AttractivenessSnapshotShape`, `AttractivenessWeightSchemeShape`,
  `WeightComponentShape` — mirror the existing shapes' style (targetClass, sh:property with
  min/maxCount and datatype/range constraints).
- **`ScoreSnapshotShape` amendment**: `normalizedScore`'s `sh:minCount 1` must become conditional —
  required for every `metricType` except `SectorRelativeMomentum`. SHACL expresses this with
  `sh:xone`/`sh:or` over two sub-shapes (one requiring `normalizedScore`, gated by
  `sh:not`+`sh:in` on `metricType`, one exempting it for `SectorRelativeMomentum`) rather than
  loosening the constraint for every metric — this is the one place existing validation behavior
  changes, so it needs its own conformance test in `instances.trig` (§6).

## 5. New veto rule — `VETO_MKT_02`

Rank 7 (appended after the existing 6, none of whose validated thresholds change), single-signal
(same shape as `VETO_FIN_01`):

```turtle
:Rule_VETO_MKT_02 a :RuleDefinition ;
    :ruleId "VETO_MKT_02" ; :category "MARKET" ; :priorityRank 7 ;
    :validFrom "2026-08-13"^^xsd:date ;
    :hasClause :Cmp_MKT02_SectorMomentumLow .

:Cmp_MKT02_SectorMomentumLow a :ThresholdComparison ;
    :metricName "SectorRelativeMomentum" ; :operator "<" ; :thresholdValue "-0.50"^^xsd:decimal .
```

Placeholder threshold (`-0.50`, matching the existing `-0.50`/`-0.60` magnitude convention for
raw-scale signed metrics), flagged for calibration in B5 like every other threshold in
`rules.ttl`.

## 6. Worked example (`schema/instances.trig`)

Extends the existing 5-ticker example rather than adding new ones, so the file stays internally
checkable by hand the same way it already is:
- A `SectorAggregateSnapshot` for each of the 5 worked sectors on 2026-08-05 (the date
  `ScoreTecnico` data exists for, not XOM's separate 2026-08-04 `VETO_FIN_01` date). Since each
  sector has only one member asset in this 5-ticker example, 4 of the 5 aggregates degenerate to
  that member's own value (relative momentum = 0) — a noted limitation of a 5-ticker example, not
  a modeling gap. `Sec_Energy`'s aggregate is deliberately set higher than XOM's own score to
  produce a non-zero, rule-firing example (see §6 in the implementation plan for exact numbers).
- A `SectorRelativeMomentum` `ScoreSnapshot` for XOM that day, demonstrating the `rawValue`-only
  (no `normalizedScore`) shape and validating the amended SHACL shape from §4.
- One `AttractivenessSnapshot` per ticker (all 5) for a single worked cycle date, with the full
  arithmetic shown in a comment so a reader can verify by hand — same convention as the existing
  veto worked examples.
- The `AttractivenessWeightScheme` individual with its 5 `WeightComponent`s (§3's initial values).

## 7. Agent architecture change (`08-agent-architecture.md`)

`MonitoringCycleGraph` gains one new node, **`sector_agent`**, inserted as a join *after* the
existing quant/technical/semantic fan-out (it needs every asset's `ScoreTecnico` already written
to compute a sector aggregate) and *before* two now-sibling join nodes that both consume its
output:

```
fan-out(quantitative, technical, semantic)
  → sector_agent   [writes SectorAggregateSnapshot + per-asset SectorRelativeMomentum]
      → orchestrator          [veto evaluation, now also reads SectorRelativeMomentum for VETO_MKT_02]
      → compute_attractiveness [NEW: reads AttractivenessWeightScheme, writes AttractivenessSnapshot]
```

`orchestrator` and `compute_attractiveness` are independent join nodes (not one node doing both
jobs) — veto-evaluation and ranking have independent audit trails and no data dependency on each
other, only a shared upstream dependency on `sector_agent`'s output.

## 8. Named-graph placement (`07-ontology-topology.md`)

| Named graph pattern | Contents | Mutability |
|---|---|---|
| `urn:graph:ingest:SECTOR:{date}` | `SectorAggregateSnapshot` + per-asset `SectorRelativeMomentum` `ScoreSnapshot`s | Append-only, same convention as the other per-agent ingest graphs. |
| `urn:graph:ingest:ORCHESTRATOR:{date}` | *(existing graph, extended)* now also holds `AttractivenessSnapshot` individuals alongside `Veto` — both are Orchestrator-layer decision output. | Append-only (unchanged). |

`AttractivenessWeightScheme`/`WeightComponent` load into the existing `urn:graph:rules:catalog`,
alongside `RuleDefinition` — same versioned-reference-data rationale.

## 9. Validation plan

1. `rdflib`/`pyshacl` parse-and-conform check (`schema/README.md`'s existing command) must still
   pass after every file change, including the amended `ScoreSnapshotShape`.
2. Hand-verify the worked `AttractivenessSnapshot` arithmetic in `instances.trig` against §3's
   formula.
3. Hand-verify `VETO_MKT_02` fires/doesn't fire correctly for the worked `SectorRelativeMomentum`
   value against the `-0.50` threshold.
4. `schema/protege-view.ttl` regenerated (flattened) from the updated sources — it's a generated
   file, never hand-edited independently.

## 10. Documentation and artifact updates required

Every doc/artifact that describes current schema state needs to move in lockstep, per this
project's own established convention (each prior schema change updated its cited class/shape
counts everywhere they're asserted, not just in the schema files):

- `schema/README.md` — file map (add nothing new, `SECTOR` output still lands via existing files),
  refinements list (add this as a 4th discovered-during-implementation refinement if anything
  surfaces during the build, per the file's own existing pattern).
- `06-ontology-definition.md` — new classes/properties section, class-count references.
- `07-ontology-topology.md` — named-graph table (§8 above), scale-estimate table (small addition:
  ~11 sectors × ~1,000 days ≈ 11K more `SectorAggregateSnapshot`s; low tens of thousands more
  `SectorRelativeMomentum`/`AttractivenessSnapshot` individuals — doesn't change the "15-20M
  triples" order-of-magnitude conclusion, but the table's rows should reflect the new sources).
- `08-agent-architecture.md` — `sector_agent` node (§7), state schema and tool-inventory table
  updates.
- `critique-and-evolution.md` — note that gap #2/#3 are now *partially* closed (ranking + one
  sector signal), not fully (sizing and full sector dashboard remain open), so the gap table
  doesn't silently read as "done."
- `10-integration-roadmap.md` — step 0's "✅ Implemented" summary line and class/shape counts.
- Published HTML artifacts for the above docs, plus the ontology visualization dashboard — find
  via `Artifact` list and redeploy to the same URLs so existing links stay live, per this
  project's established artifact-update convention.

## 10a. Addendum — domain-collision fix found during planning (not in the original design)

`SectorAggregateSnapshot` was specified in §2 to reuse `ScoreSnapshot`'s `metricType`/
`agentOrigin`/`timestamp`/`normalizedScore` fields. Those four properties currently declare
`rdfs:domain :ScoreSnapshot` explicitly in `tbox.ttl`; reusing them as-is on a class that
`AllDisjointClasses` also lists would RDFS-entail that a `SectorAggregateSnapshot` individual is
also a `:ScoreSnapshot` — an inconsistency under this project's own OWL 2 RL reasoning profile
(`07-ontology-topology.md`). Fixed by widening those four properties' domain to a new union class
`:ObservationSnapshot = unionOf(:ScoreSnapshot, :SectorAggregateSnapshot)`, following the exact
pattern `RuleOperand`/`EvidenceSource` already establish for the analogous range problem elsewhere
in this ontology. See the implementation plan's Task 1 for the precise edits.

## 11. Open questions for implementer (flag if any surface, don't silently resolve)

- Whether `sourceNamedGraph` annotations in `protege-view.ttl`'s generation script/process need
  any change (they shouldn't — new named graphs just get new annotation values) — worth a quick
  sanity check during regeneration, not a design decision.
- The equal-ish initial weight scheme (§3) is an explicit placeholder; if the user has a strong
  prior on relative importance (e.g. sentiment mattering more than sector momentum), that's a
  one-line change to `WeightComponent.weight` values, not a re-design.
