# Critical Review and Natural Evolution of the Knowledge-Graph Portfolio Architecture

**Source reviewed:** `Avance arquitectura del sistema.docx`
**Scope:** S&P 500 universe · news (2022–present) · EDGAR/SEC filings · daily pricing
**Stated goal:** build and maintain an investment portfolio using a knowledge graph that reflects
temporal/current conditions (best-performing companies and sectors)

---

## 0. What the source document actually specifies

The document is short (6 sections) but tightly designed. For traceability, every critique point
below is anchored to one of these:

| § | Content |
|---|---|
| 1 | **Guiding principle**: the graph is a persistent-memory / relational-reasoning / audit layer only. It performs no heavy computation. All financial, statistical, and NLP computation happens in specialist **Agents** (Fundamental, Quantitative, Technical, Semantic), which write timestamped observations back into the graph. The Orchestrator Agent reasons over explicit edges, not free text. |
| 2 | **Two-speed cycles**: (A) slow quarterly *Selection Cycle* — Fundamental Agent screens the full S&P 500 (500 assets) on solvency/liquidity/financial-health criteria, selects a 50–80 name watchlist, triggered by 10-K/10-Q publication; modeled as a temporalized edge `(Asset)-[:PERTENECE_A_UNIVERSO {fecha_inicio, fecha_fin}]->(Universe)`, closed (not overwritten) when a name exits. (B) fast daily *Monitoring Cycle* — Quantitative, Technical, Semantic agents, scoped only to the current candidate universe (`fecha_fin = NULL`) plus open portfolio positions. The Semantic Agent owns all unstructured/text content: news, Item 1A (Risk Factors) and Item 3 (Legal Proceedings) of 10-K/10-Q, and director extraction from DEF 14A. |
| 3 | **Observation modeling**: risk/quality measurements are never written as mutable node attributes. Each is an immutable `ScoreSnapshot` node (`normalized_score ∈ [0,1]`, `raw_value`, `metric_type`, `agent_origin`, `timestamp`) linked via `(Asset)-[:HAS_SCORE_OBSERVATION]->(ScoreSnapshot)`. Alerts are backed by a navigable, multi-hop evidence chain: `(Asset)-[:TIENE_EVENTO_RIESGO]->(Veto)-[:DISPARADO_POR]->(RiskEvent)-[:RESPALDADO_POR]->(NewsArticle | SECFilingSection)`. |
| 4 | **Orchestrator + veto catalog**: veto state is a global, inclusive OR across a ranked catalog of 6 boolean rules (full text below). Includes a contagion rule (`VETO_RED_01`, shared-executive network effect) that is explicitly de-recursed (only considers primary vetoes not themselves caused by `VETO_RED_01`) and lagged one cycle (`T-1`, reads the *previous* orchestrator run's persisted state) specifically to remain parallelizable without a fixed-point/topological-sort computation. |
| 5 | **Multiple activations**: if several rules fire, the full list is stored in `reglas_gatillo: LIST<STRING>`; the lowest-rank rule is used as "primary" for audit queries. |
| 6 | **Initialization**: cold start (`T=0`, no prior veto state, `VETO_RED_01` forced `FALSE`); universe-exit transition (name leaves fast monitoring unless still an open position); and a stated invariant — `FUNDAMENTAL`-origin snapshots stay constant immediately before/after a fast-cycle event — used implicitly as a self-consistency check on the two-speed design.

**The veto catalog, verbatim (with formulas restored from the document's embedded math):**

| Rank | Rule ID | Category | Mechanism | Boolean expression | Thresholds |
|---|---|---|---|---|---|
| 1 | `VETO_LEG_01` | Legal | Single signal | `RiskEvent.category='LEGAL' ∧ RiskEvent.severity='CRITICAL'` | — |
| 2 | `VETO_FIN_01` | Financial | Single signal | `ScoreFinanciero > Ufin_crit` | `Ufin_crit = 0.85` |
| 3 | `VETO_COMP_02` | Legal/Reputational | Confluent | `RiskEvent.category='LEGAL' ∧ RiskEvent.severity='HIGH' ∧ Sentiment<Usent_legal ∨ ScoreCuantitativo>Ucuant_mod` | `Usent_legal=-0.50`, `Ucuant_mod=0.65` |
| 4 | `VETO_COMP_01` | Financial/Market | Confluent | `ScoreFinanciero>Ufin_mod ∧ Sentiment<Usent_mercado ∨ ScoreTécnico>Utec_mod` | `Ufin_mod=0.65`, `Usent_mercado=-0.60`, `Utec_mod=0.70` |
| 5 | `VETO_RED_01` | Network/Contagion | Confluent | `HasSharedPrimaryVeto(Executive,A) ∧ Sentiment<Usent_legal ∨ ScoreFinanciero>Ufin_mod` | `T-1` lag, `Usent_legal=-0.50`, `Ufin_mod=0.65` |
| 6 | `VETO_COMP_03` | Market/Volatility | Confluent | `ScoreCuantitativo>Ucuant_crit ∧ ScoreTécnico>Utec_crit` | `Ucuant_crit=0.75`, `Utec_crit=0.75` |

---

## Part A — Critical review

### A.1 What's right, and worth keeping as-is

- **Graph = memory, Agents = compute (§1).** This is the correct division of labor for a KG-backed
  decision system. It avoids the common failure mode of encoding analytics as graph traversals,
  and keeps the graph queryable, small, and fast.
- **Immutable `ScoreSnapshot` observations instead of mutable attributes (§3A).** This is exactly
  right for a system whose core value proposition is auditability. Overwriting a `risk_score`
  property on an `Asset` node destroys history; modeling each measurement as its own timestamped
  node preserves it for free and makes "what did we know on date X" queries trivial.
- **Temporalized universe membership (§2A).** `PERTENECE_A_UNIVERSO {fecha_inicio, fecha_fin}`,
  closed rather than overwritten on exit, is a direct, explicit defense against **survivorship
  bias** — a first-order threat to validity for any historical S&P 500 study, since the S&P 500's
  constituent list itself changes continuously. This detail should be called out explicitly in the
  thesis methodology section as a deliberate bias-mitigation choice, not just a modeling nicety.
- **Deterministic, declarative veto catalog (§4) instead of an opaque model.** For a hard
  exclusion/risk-control gate, a transparent boolean rule set that can be unit-tested,
  independently audited, and explained rule-by-rule is the right choice — an ML classifier here
  would trade explainability for marginal accuracy in a place where explainability is the point.
- **The `T-1` lag + recursion exclusion in `VETO_RED_01` (§4).** This is the strongest piece of
  engineering in the document. Contagion-style rules are naturally cyclic (A's veto can depend on
  B's veto and vice versa); the design sidesteps a fixed-point iteration or topological sort by
  reading the *previous* cycle's persisted state and explicitly excluding second-order contagion.
  That trade-off (one cycle of "staleness" in exchange for parallel, order-independent evaluation)
  is stated and justified, not left implicit — this is publication-quality systems reasoning.
- **The §5/§6 self-consistency invariant.** Stating that slow-agent snapshots must remain constant
  across a fast-cycle event turns the two-speed design into something testable, not just
  descriptive — effectively a built-in regression check.

### A.2 Gaps and issues, ranked by severity

**1. Likely correctness bug: unparenthesized boolean precedence in every confluent rule.**
All four confluent rules (`VETO_COMP_01/02/03`, `VETO_RED_01`) mix `∧` and `∨` with no grouping,
e.g. rule 4:

```
ScoreFinanciero > Ufin_mod  ∧  Sentiment < Usent_mercado  ∨  ScoreTécnico > Utec_mod
```

Under standard precedence (`∧` binds tighter than `∨`), this parses as:

```
(ScoreFinanciero > Ufin_mod  ∧  Sentiment < Usent_mercado)  ∨  (ScoreTécnico > Utec_mod)
```

i.e. a high technical score **alone** — with zero financial deterioration and zero negative
sentiment — triggers a rule named "Financial/Market". That almost certainly isn't the intended
semantics; the rule's own name and the "confluent signal" framing in §4 imply the reading
`Financial AND (Sentiment OR Technical)`:

```
ScoreFinanciero > Ufin_mod  ∧  (Sentiment < Usent_mercado  ∨  ScoreTécnico > Utec_mod)
```

These two readings select **different companies for veto**. This needs to be resolved with
explicit parentheses in the spec before any implementation, and the resolution should be applied
consistently to all four confluent rules (see the corrected form in the Artifact).

**2. No portfolio-construction layer.** The document fully specifies *exclusion* (universe
selection + veto) but says nothing about *inclusion mechanics*: how survivors are scored/ranked
against each other, how position sizes are set, rebalancing cadence, diversification/correlation
constraints, or transaction costs. As written, this is a **screening system**, not yet a
portfolio-construction system — which is the thesis's stated primary goal. This is the largest
gap relative to scope.

> **Update (2026-08-13):** the ranking half of this gap is now closed — see
> `AttractivenessSnapshot` in `06-ontology-definition.md`'s attractiveness-ranking subsection and
> `docs/superpowers/specs/2026-08-13-attractiveness-sector-momentum-design.md`. Position sizing,
> rebalancing cadence, and diversification/correlation constraints remain open.

**3. No sector/industry layer.** The stated requirement is to track "current best-performing
companies **and sectors**," but there is no `Sector`/`Industry` node type anywhere in the model,
no sector-level score roll-up, and no relative-strength or rotation signal. Sector-level reasoning
cannot be bolted on later without touching the core schema, so it belongs in the next design
iteration, not deferred indefinitely.

> **Update (2026-08-13):** a sector-relative-momentum signal (one metric, feeding both a new veto
> rule and the attractiveness score) is now implemented — see `SectorAggregateSnapshot`. The full
> sector-rotation dashboard (relative-strength-vs-benchmark roll-ups, a dedicated Sector Agent's
> broader signal set) described in layer B2 remains open beyond this one signal.

**4. Hardcoded, uncalibrated thresholds.** Every threshold (`0.85`, `0.65`, `-0.50`, `-0.60`,
`0.70`, `0.75`) appears with no stated derivation — no sensitivity analysis, no backtest, no
walk-forward fit. For a thesis, uncalibrated magic numbers are a defensible v1 placeholder but not
a defensible final result; they should be treated as free parameters with an explicit calibration
methodology, which doubles conveniently as the thesis's empirical evaluation chapter (see B5).

**5. No missing-data / NULL policy.** If an agent fails to produce a score on a given day (source
outage, parser failure, rate limit), the boolean expressions above are evaluated over an undefined
`NULL`. There's no stated fallback: skip the rule, treat as no-signal, carry forward the last known
value, or block the cycle for that asset. This needs an explicit policy before implementation,
not an implicit one discovered in production.

**6. The veto catalog isn't versioned data.** Rules and thresholds appear to live in application
logic, not as graph entities with their own `valid_from/valid_to`. This is inconsistent with the
rigor already applied to universe membership in §2A, and it undercuts the stated audit goal: if a
threshold is later retuned, the graph has no way to reconstruct *which ruleset produced a given
historical decision*. Given §1's premise ("the graph is the audit mechanism"), the rules
themselves should live in the graph too.

**7. No entity-resolution layer**, despite `VETO_RED_01` structurally requiring one. Matching "the
same executive" or "the same company" across news text, DEF 14A filings, and price-data tickers is
a nontrivial NLP/KG problem (name variants, ticker changes, subsidiary vs. parent entities). If
unresolved, the contagion rule will silently under- or over-fire without anyone noticing, since
its failure mode is quiet (missed or spurious edges) rather than a crash.

**8. No transaction-time, only valid-time.** `fecha_inicio/fecha_fin` records *when something was
true* but not *when the system learned it*. If a 10-K is later restated/amended, the current model
can't distinguish "what we believed as of date X" from "what was actually true as of date X" — a
distinction that audit-grade financial systems generally need, and one the thesis can address
cheaply by adding a second temporal pair now rather than retrofitting it later.

**9. No formal ontology artifact.** The document conveys node/edge types through inline Cypher-like
snippets rather than a complete, diagrammed schema (full property lists, cardinalities, and an
inventory of every entity type touched — `Executive` and `RiskEvent`, for instance, are used but
never fully specified). This is expected scaffolding for a thesis architecture chapter and is
addressed directly by the diagrams accompanying this document.

> **Update (2026-08-23):** closing this gap with a full class inventory (`06`) turned out to leave
> a narrower structural sub-gap behind it — the 24 resulting classes were disjoint but otherwise
> flat, with no `rdfs:subClassOf` hierarchy among them at all (only the GICS `Sector`/`Industry`
> pair had real taxonomic structure, via SKOS). `06-ontology-definition.md` §1.2 now organizes all
> 24 into an explicit taxonomy — 6 broad categories, 4 mid-level — and upgrades the three
> `owl:unionOf` domain-widening helpers (`ObservationSnapshot`, `EvidenceSource`, `RuleOperand`)
> into ordinary, queryable superclasses along the way. Additive only; no existing class, property,
> or SHACL shape changed.

**10. No feedback/evaluation loop.** Nothing connects realized forward returns back to
veto/threshold calibration. As written this is a one-way screening pipeline, not a system that
adapts — worth flagging explicitly since "maintain the portfolio over time" is part of the stated
scope.

---

## Part B — Natural evolution: architecture v2

The v1 core (graph/compute separation, two-speed cycles, immutable snapshots, deterministic veto
catalog) is sound and should not be rewritten. The evolution below is **additive**: ten layers,
each closing one of the gaps in A.2, that turn the existing screening engine into a full
portfolio-construction-and-maintenance system.

| Layer | Adds | Closes gap |
|---|---|---|
| **B1. Formal ontology** | Complete class/relationship inventory — `Asset`, `Sector`, `Universe`, `ScoreSnapshot`, `RiskEvent`, `NewsArticle`, `SECFilingSection`, `Executive`, `Veto`, `RuleDefinition`, `Portfolio`, `Position` — with full property lists and cardinalities. | #9 |
| **B2. Sector/rotation layer** | `Sector`/`Industry` nodes aggregating member `ScoreSnapshot`s; relative-strength-vs-benchmark and sector-momentum signals computed by a new Sector Agent (sector-relative-momentum signal implemented 2026-08-13; broader roll-up dashboard still open). | #3 |
| **B3. Portfolio construction layer** | An attractiveness/ranking score (the positive counterpart to the veto score) over surviving names; a sizing module (vol-scaled or risk-budgeted weights, correlation/concentration caps); a rebalancing cadence (attractiveness/ranking score implemented 2026-08-13; sizing module still open). | #2 |
| **B4. Rules as versioned graph data** | `RuleDefinition` nodes (`expression`, `thresholds`, `valid_from`, `valid_to`) — the orchestrator reads its active ruleset from the graph instead of code, exactly mirroring the pattern already used for universe membership in §2A. | #4, #6 |
| **B5. Calibration & backtesting framework** | Walk-forward threshold fitting plus a per-rule ablation study (portfolio performance with vs. without each veto rule active) — this *is* the thesis's empirical evaluation chapter. | #4 |
| **B6. Data-quality / null-handling policy** | Explicit `confidence`/`staleness` flags on `ScoreSnapshot`, and a documented fallback (no-signal vs. carry-forward vs. block) consumed by rule evaluation instead of implicit `NULL` semantics. | #5 |
| **B7. Entity resolution service** | A canonical-identity layer (`CanonicalEntity` nodes + resolution edges) disambiguating companies/executives across news, filings, and price data — a hard prerequisite for a trustworthy `VETO_RED_01`. | #7 |
| **B8. Bitemporal upgrade** | Add `recorded_at`/`superseded_at` (transaction-time) alongside the existing `fecha_inicio/fecha_fin` (valid-time) on the same edges, so filing amendments/restatements don't corrupt the historical record. | #8 |
| **B9. Graph-grounded explainability** | Auto-generated natural-language audit narratives produced from the existing evidence subgraph (GraphRAG-style: retrieve the `Veto→RiskEvent→Source` path, then generate prose grounded in it) — turns the audit *trace* into a readable investment memo. A strong, demoable thesis artifact in its own right. | (new capability, not a gap fix) |
| **B10. Outcome feedback loop** | Track forward returns following veto/inclusion events; feed the result back into B5's calibration. Positions the system as adaptive rather than static — reasonable to scope as "future work" if the thesis timeline is tight. | #10 |

### Suggested sequencing

If everything can't fit the thesis timeline, B1 (ontology) and B4 (versioned rules) are the
highest-leverage layers to do first: B1 is pure documentation debt that unblocks writing the
architecture chapter, and B4 is a small schema change that make B5's backtesting story (and the
whole audit-reproducibility claim) actually coherent. B2 (sector layer) and B3 (portfolio
construction) are next because they close the two gaps between "screening system" and "portfolio
system" that are named directly in the thesis's own stated scope. B5–B10 are natural candidates
for the evaluation chapter and future-work section, roughly in that order of effort vs. payoff.

---

## Diagrams

See the companion Artifact for:
1. A recap diagram of the v1 two-speed cycle.
2. The layered v2 architecture (v1 core + B1–B10), color-coded by which gap each layer closes.
3. The corrected `VETO_COMP_01` expression tree — ambiguous vs. parenthesized reading, side by
   side — illustrating issue A.2 #1 concretely.
