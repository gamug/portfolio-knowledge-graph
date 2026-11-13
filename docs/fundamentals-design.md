# Fundamentals block C loader — design (Work item 45, T-810)

**Status:** design, 2026-11-12; implemented in T-813–T-815, 2026-11-13.

**Source delivery:** `/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales/`
(the v2 delivery; the first delivery's figures remain only in the historical tables of §1).
`SHA256SUMS` hashes to `fd32daed391f515e5ff76e030acaab2dd018fea8dadf4d206429274bbe6ee677`;
all six listed entries verify with `sha256sum -c`. `source.json` names `scored_llm.db` with
`sha256 2187c36bae42296b84d63031e9058df5aba997a77da2a4aa6665279452e184ca`. The
`provenance/export_bloque_c.py` script is listed in the manifest and is required for this delivery
(unlike Work item 44, where `provenance/` was optional). The Tiingo mask,
`mascara_tiingo/tiingo_assets.csv`, hashes to
`4712c7c224bd76b4661260d77d95ce3c62fe80710c0b7d30a1ce44ac00c39dce`.

**Scope of T-810:** this document, the Work item 45 entries in `PLAN.md` and `TASKS.md`, tests only
for the touched documentation, and a PR. No loader, schema, label, count or GraphDB change is made
here. The implementation is reserved for T-811–T-815 after Reviewer A answers §7.

> **Addendum 4 (2026-11-13, Reviewer A, implementation).** The final metric set is **37** direct
> properties: the 38 source names minus `value_inputs`; it includes the 31 base metrics, the three
> valuation yields, `utility_cash_coverage_3y`, `market_capitalization` and `enterprise_value`.
> The v2 delivery is `/workspaces/thesis/knoledge graph/2026-11-12_respuesta_4/bloque_c_fundamentales/`
> (`SHA256SUMS` `fd32daed…`, 509,933 metric rows, 70,445 valuation rows, all for unmasked assets).
> The 37 metrics are 495,294 rows / 406,570 non-null; the expected batch is **834,586 asserted
> triples** (873,889 with inference), including the 33 `:pricesNotPublished` flags. The mask is a
> loader check, not a schema filter: stop on any `valuation` row of a masked asset; `value_inputs`
> rows are discarded for every asset and never raise an error. The other 550 assets load all five
> valuation metrics. There is no
> `--include-valuation-ratios` flag and no `:containsPriceDerivedValue`/`:metricIdsJson`. There is
> no `:assessmentOfSnapshot` link and no `:promptHash`: the assessment carries its own score and
> rating, and the constant prompt hash stays in the delivery hash/`source.json`. The loader count is
> measured in T-813–T-815; the schema count is in `PLAN.md`/`TASKS.md` and
> `docs/labels-fundamentals-review.md`.
>
> **Correction 2026-11-13 (mask flag).** `:pricesNotPublished true` is written for **all 33**
> assets in `mascara_tiingo/tiingo_assets.csv`, not only the 31 with block C filings. FRC
> (asset_id 229) and SBNY (469) have no block C filing but appear in rankings, positions and
> alerts, so they carry the flag too. The loader derives the set from the SHA-256-verified
> `tiingo_assets.csv`, independent of `filings.csv`; each masked ticker must resolve to an
> `:Asset` through the same universe/reference resolution the backtest projector uses, and an
> unresolved ticker stops the load with the list (no minted assets). The flag set is **33
> triples**, not 31.

---

## 0. Recommendation in one paragraph

Load **one `:FundamentalMetricSet` per filing** with **37 direct decimal properties** (the 38
source names minus `value_inputs`; includes the five valuation metrics and
`utility_cash_coverage_3y`), plus **one `:FundamentalAssessment` per assessment** that carries its
own score and rating. The v2 delivery has 509,933 metric rows; the 37 properties are 495,294 rows
(406,570 non-null), 70,445 valuation rows all for unmasked assets, and 14,639 `value_inputs` rows
without a property. The expected batch is **834,586 asserted triples** over all 14,639 filings
(873,889 with the one inferred type per individual, and 33 `:pricesNotPublished` flags), roughly
**20% of the current ~4.18M-triple production store**. The mask is a loader check, not a schema
filter: a masked valuation row stops the load and `value_inputs` rows are discarded for every
asset; the other 550 assets load all five valuation metrics. `market_capitalization` and
`enterprise_value` are in the graph; only `value_inputs` has no property. The reified-observation
variants remain rejected on volume.

---

## 1. Delivery profile and the volume problem

> The A/B/C tables below are the pre-Addendum-4 comparison on the first delivery (512,683 metric
> rows, 31/35 metrics). They are retained as the volume argument that led to the metric-set model;
> the final 37-metric v2 figures are in §0 and Addendum 4.

### 1.1 Files, keys and measured profile

| File | Rows | Unique key | One row per |
|---|---:|---|---|
| `filings.csv` | 14,639 | `filing_id` | 10-K or 10-Q filing |
| `metrics.csv` | 512,683 | `metric_id`; also `(filing_id, metric_group, metric_name)` | computed ratio of one filing |
| `assessments.jsonl` | 10,025 | `snapshot_id`; also one `filing_id` in this delivery | assessment of one filing |

Measured from the real files:

- **Filings:** 14,639 rows, 581 assets/tickers, 10-Q 10,887 and 10-K 3,752. Filing dates
  2020-01-02..2026-10-16; `available_at` 2020-01-03..2026-10-19. **0** rows have
  `available_at <= filing_date`; the source's availability is always strictly after the filing date.
- **Metrics:** 512,683 rows, **422,964 non-null** values and 89,719 null values. 10 groups, 38 metric
  names. Units: `ratio` 293,098; `x` 146,390; `usd` 73,195. Rows per filing: min 30, median 34, max
  38. Every metric row's `available_at` equals its filing's `available_at` (0 mismatches). 14,510
  filings have one `computed_at`; 129 have two, one second apart.
- **Assessments:** 10,025 rows, 10,025 distinct filings and 579 assets. **9,896**
  `generated_by_language_model=true` (`DeepSeek-V4.1-Flash [thinking=disabled]`) and **129** false
  (`unscored-pillar-coverage-v1`). All 9,896 true rows have a score and a rating; all 129 false rows
  have `score_raw_0_100=null` and `rating=null`. Every assessment's `available_at` equals its
  filing's and every `event_time` equals the filing's `period_end` (0 mismatches). Narrative length
  187–1,366 characters, average 934.6. Strengths 38,819 and risks 39,512 items in total (3.87 and
  3.94 per assessment). `prompt_hash` is present on all 10,025 rows, including the 129 rule rows.
  Ratings: bullish 4,263, neutral 4,183, bearish 1,450, null 129.
- **Masked assets:** `mascara_tiingo/tiingo_assets.csv` (sha256
  `4712c7c224bd76b4661260d77d95ce3c62fe80710c0b7d30a1ce44ac00c39dce`) lists **33 assets**, 550
  filings, 19,280 metric rows, 2,750 valuation rows and 695 `rule_input` rows. 333 assessments
  belong to 31 of the 33 assets; two masked assets have no assessment.

Groups:

| Group | Metrics | Rows | Non-null | Masked rows |
|---|---:|---:|---:|---:|
| `profitability` | 5 | 73,195 | 62,766 | 2,750 |
| `liquidity` | 3 | 43,917 | 35,575 | 1,650 |
| `leverage` | 5 | 73,195 | 59,718 | 2,750 |
| `efficiency` | 3 | 43,917 | 33,439 | 1,650 |
| `growth` | 4 | 58,448 | 49,763 | 2,200 |
| `cashflow` | 4 | 58,556 | 48,827 | 2,200 |
| `roic` | 4 | 58,556 | 47,877 | 2,200 |
| `cagr` | 3 | 11,313 | 10,053 | 435 |
| `valuation` | 5 | 73,195 | 57,967 | 2,750 |
| `rule_input` | 2 | 18,391 | 16,979 | 695 |

### 1.2 Baseline and the counting rule

The production repository is at about **4.18M asserted triples** today (the schema graphs are the
5 graphs / 5,828 triples of T-756; the rest is run data). For each option below the asserted count is

```
filings × 10
+ metric sets × 5            (options B/C; not in A)
+ metric observations × 7 + non-null values   (option A)
+ metric values (non-null)   (options B/C)
+ assessments × 12 + scored × 2 + strengths + risks
+ metric-definition rows in labels.ttl
```

with these measured inputs:

- filings 14,639 (all) or 10,025 (assessed-only pilot);
- metric observations: 512,683 all / 421,097 default 31 / 288,176 default 31 and assessed-only;
- non-null values: 422,964 all / 348,018 default 31 / 242,459 default 31 and assessed-only;
- assessments 10,025; scored 9,896; strengths 38,819; risks 39,512;
- labels: 38 concepts = 386 triples, or 31 concepts = 316 triples (10 per concept + 6 for the scheme).

The per-assessment budget is: type, filing, asset, `snapshot_id`, narrative, model, computed
time, event time, available time, generated flag, provenance note (11 fixed); plus
`:scoreRaw0to100` and `:rating` for the 9,896 scored rows (2 each); plus one triple per strength and
risk. The score is stored on the assessment; there is no `ScoreSnapshot` link and no `:promptHash`
(the constant prompt hash stays in the delivery hash/`source.json`).

The per-metric-set budget is: type, filing link, `availableAt`, `computedAt`, `engineVersion`
(5 fixed). The per-filing budget is: type, asset, form, filing date, period end,
fiscal year, fiscal period, `availableAt`, accession number, `filingId` (10 fixed).

### 1.3 Model A — one reified observation per metric row

Every one of the 512,683 metric rows becomes a `:FundamentalMetricObservation` with:

```
:FundamentalMetricObservation_final_<metric_id>
    a :FundamentalMetricObservation ;
    :metricOfFiling :Filing_final_<filing_id> ;
    :metricDefinition :FundamentalMetric_<metric_name> ;
    :availableAt "<filing available_at>"^^xsd:date ;
    :computedAt "<row computed_at>"^^xsd:dateTime ;
    :engineVersion "metrics-v10" ;
    :provenanceId "metric:<metric_id>" ;
    :metricValue "<value>"^^xsd:decimal .       # only when non-null
```

The `:metricDefinition` is a SKOS concept in `labels.ttl` carrying `metric_group`, `metric_unit`,
the bilingual labels/comments and the notation. The observation does not repeat group/name/unit.

| Variant | Asserted | Inferred | Total | Store after |
|---|---:|---:|---:|---:|
| A, all 38 metrics, all filings | 4,376,944 | 537,347 | 4,914,291 | ~9.1M |
| A, default 31, all filings | 3,660,826 | 445,761 | 4,106,587 | ~8.3M |
| A, default 31, assessed-only | 2,578,680 | 308,226 | 2,886,906 | ~7.1M |

**Agent query** ("ROIC of X at date D"):

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?value ?available WHERE {
  ?filing :filingOfAsset ?asset ; :availableAt ?available .
  ?obs :metricOfFiling ?filing ;
       :metricDefinition :FundamentalMetric_return_on_invested_capital ;
       :metricValue ?value .
  VALUES ?asset { :A }
  FILTER(?available <= "2024-06-30"^^xsd:date)
  FILTER NOT EXISTS {
    ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
    ?laterObs :metricOfFiling ?later ;
              :metricDefinition :FundamentalMetric_return_on_invested_capital ;
              :metricValue ?laterValue .
    FILTER(?laterAvailable <= "2024-06-30"^^xsd:date && ?laterAvailable > ?available)
  }
}
ORDER BY DESC(?available) LIMIT 1
```

**SHACL/class/property needs:** `FundamentalMetricObservationShape` (required filing, definition,
available/computed times, engine version, provenance; optional decimal value),
`FundamentalMetricDefinitionShape` (notation, group, unit, bilingual labels), `FundamentalAssessmentShape`,
`FundamentalFilingShape`; two OWL classes (`FundamentalMetricObservation`, `FundamentalAssessment`)
and about 20 new properties plus the 38 metric concepts in `labels.ttl`.

**Inference:** one extra `:Observation` type per observation, assessment and filing (~0.54M for the
all-38 variant). No subproperty hierarchy is used; a `:metricValue` superproperty would add one
inferred triple per value and is avoided.

**Why not:** it doubles the store and the 31-metric restriction still costs 3.66M asserted. It is
the right model only if every `metric_id` must be an individually addressable RDF resource.

### 1.4 Model B — one metric set per filing, 38 direct properties

One `:FundamentalMetricSet` per filing:

```
:FundamentalMetricSet_final_<filing_id>
    a :FundamentalMetricSet ;
    :metricSetOfFiling :Filing_final_<filing_id> ;
    :availableAt "<filing available_at>"^^xsd:date ;
    :computedAt "<latest row computed_at>"^^xsd:dateTime ;
    :engineVersion "metrics-v10" ;
    :returnOnInvestedCapital "0.184"^^xsd:decimal ;
    :netMargin "0.213"^^xsd:decimal ;
    ... .
```

Each metric is a `owl:DatatypeProperty` with domain `:FundamentalMetricSet`, range
`xsd:decimal` and `owl:FunctionalProperty`. A null value is **no triple**, not a null literal. No
per-metric ID map is stored in the final model: the graph keys a value by
`(filing_id, metric_name)`, and the delivery's `metric_id` stays in the source file.

| Variant | Asserted | Inferred | Total | Store after |
|---|---:|---:|---:|---:|
| B, all 38 metrics, first delivery (pre-addendum) | 875,997 | 39,303 | 915,300 | ~5.1M |

**Agent query:** `?set :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?value`, with the same
`availableAt <= D` and latest-filing pattern as A (the property replaces the observation join).

**SHACL/class/property needs:** `FundamentalMetricSetShape` with 38 (or 37) `sh:property` blocks,
each `sh:datatype xsd:decimal` and `sh:maxCount 1`; `FundamentalAssessmentShape`;
`FundamentalFilingShape`; two OWL classes and the metric properties plus the metric concepts in
`labels.ttl`.

**Inference:** one extra `:Observation` type per set, assessment and filing (~39k). **Do not** make
the metric properties subproperties of a generic `:metricValue`: that would add one inferred triple
per value and defeat the compactness.

### 1.5 Model C — the final 37-metric set (recommended)

Model B with the **37** source names minus `value_inputs`, all 14,639 filings. The five valuation
metrics are included; a valuation row of a masked asset stops the load, while the other 550 assets
load all five valuation metrics. `value_inputs` has no property and its 14,639 rows are discarded
for every asset. The v2 delivery has 509,933 metric rows; the 37 metrics are 495,294 rows
and 406,570 non-null.

| Variant | Asserted | Inferred | Total | Store after |
|---|---:|---:|---:|---:|
| C, 37 metrics, all filings | **834,586** | 39,303 | **873,889** | ~5.0M |
| C-pilot, 37 metrics, assessed-only (10,025 filings) | 644,512 | 30,075 | 674,587 | ~4.8M |

**Agent query:** the same direct-property pattern as B, e.g.:

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?value ?available WHERE {
  VALUES ?asset { :A }
  ?filing :filingOfAsset ?asset ; :availableAt ?available .
  ?set :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?value .
  FILTER(?available <= "2024-06-30"^^xsd:date)
  FILTER NOT EXISTS {
    ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
    ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterValue .
    FILTER(?laterAvailable <= "2024-06-30"^^xsd:date && ?laterAvailable > ?available)
  }
}
ORDER BY DESC(?available) LIMIT 1
```

**SHACL/class/property needs:** `FundamentalMetricSetShape` with 37 decimal properties,
`FundamentalAssessmentShape`, `FundamentalFilingShape`, `FundamentalMetricDefinitionShape`; two OWL
classes (`FundamentalMetricSet`, `FundamentalAssessment`) and 37 metric properties plus the
assessment/filing properties; 37 metric concepts in `labels.ttl` under a new
`FundamentalMetricScheme`. Each TBox class/property gets bilingual `rdfs:label`/`rdfs:comment`
(the T-754 pattern); each metric concept gets the full `labels.ttl` row (notation, scheme,
`labelScheme`, bilingual label/comment, optional altLabels, group/unit).

**Inference:** one extra `:Observation` type per metric set, assessment and filing (~39k for all
filings, ~30k for the pilot). No subproperty hierarchy. The 37 properties' `rdfs:domain` infers the
already-asserted `:FundamentalMetricSet` type, so it adds no new triple beyond that type.

### 1.6 Comparison and recommendation

| Criterion | A (reified, pre-addendum) | B (38 direct, pre-addendum) | C (37, final) |
|---|---|---|---|
| Asserted triples (all filings) | 4,376,944 | 875,997 | **834,586** |
| Total with inference | 4,914,291 | 915,300 | **873,889** |
| Store after (approx.) | ~2.2× | ~1.22× | **~1.21×** |
| Agent query | observation join | direct property | **direct property** |
| Per-`metric_id` IRI | yes | no | no |
| New metric properties | 0 (one link) | 38 | **37** |
| New `labels.ttl` concepts | 38 | 38 | **37** |
| SHACL blocks | 4 shapes, one observation shape | 4 shapes, 38 property blocks | **4 shapes, 37 property blocks** |
| Inference per value | 1 type per observation | none | **none** |
| Mask | per-row unit check | property allowlist | **loader check on a masked valuation row; value_inputs discarded; 33 flags** |

**Recommendation: C.** It keeps the graph queryable with plain SPARQL, avoids the 4M reified
observations, and follows the final 37-metric delivery. The mask is not structural in the schema:
the loader checks the SHA-256-verified mask file and stops on a valuation row of a masked asset;
`value_inputs` rows are discarded for every asset. The other 550 assets load all five valuation
metrics. If Reviewer A needs per-`metric_id` RDF identity, the fallback is model A restricted to
the 37 metrics and the assessed-only pilot.

---

## 2. Point in time

### 2.1 The measured clocks

| Field | Meaning | Measured |
|---|---|---|
| `filings.available_at` | first date the filing can be used | always **after** `filing_date` (0 exceptions) |
| `metrics.available_at` | same date as the filing | 509,933 / 509,933 equal |
| `assessments.available_at` | same date as the filing | 10,025 / 10,025 equal |
| `assessments.event_time` | the period the assessment is about | 10,025 / 10,025 equal to `filings.period_end` |
| `computed_at` | when the row/text was produced | one value per filing except 129 filings with two, one second apart |
| `filing_date` | when EDGAR received the filing | always before `available_at` |

The delivery has **one** source availability date per filing, not one per metric. That is what makes
the per-filing metric set possible: `availableAt`, `computedAt` and `engineVersion` are set-level
properties, and every metric value shares them in this delivery. The 129 two-timestamp filings keep
the latest `computed_at` on the set; the one-second difference is not usable for a time query.

### 2.2 Reuse decision: `availableAt`, not `knowledgeDate` or `validFrom`

- **Use `:availableAt`** for filings, metric sets and assessments. It is already the only as-of
  filter for `ScoreSnapshot` (`docs/07` "As-of reads (T-101)"), so the TTYG agent has one rule.
  The current `rdfs:domain :ScoreSnapshot` must be removed (or widened to a union that includes
  `:SECFiling` and `:Observation`; `:SECFiling` is a `:SourceDocument`, not an `:Observation`), so
  the filing and the assessment can carry it. The property comment should say: "the date the row
  became usable; every as-of-D query filters `availableAt <= D`; never `eventTime` or
  `computedAt`."
- **Widen `:computedAt` and `:eventTime` the same way.** `:computedAt` currently has domain
  `:AttractivenessSnapshot` and `:eventTime` has domain `:ScoreSnapshot`; both new classes are
  `:Observation`s, so widen them to `:Observation` (or remove the domain) rather than duplicating
  them as `:metricComputedAt`/`:assessmentEventTime`. `:engineVersion` already has no domain and is
  reused unchanged.
- **Do not use `:knowledgeDate`.** It is the m018 row's knowledge date, not a source availability
  date; using it here would make two different clocks look identical.
- **Do not use `:validFrom`/`:validTo`.** They are valid time for versioned records, not observation
  availability. Encoding "this filing is the latest until the next one" as a valid interval would
  require updating the previous set when a new filing arrives, which contradicts the append-only
  graph and adds a second truth to keep in sync. The latest-available query below is the correct
  point-in-time read.

### 2.3 SPARQL pattern for the TTYG agent

For a metric fact:

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?asset ?value ?available WHERE {
  VALUES ?asset { :A }
  ?filing :filingOfAsset ?asset ; :availableAt ?available .
  ?set :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?value .
  FILTER(?available <= "2024-06-30"^^xsd:date)
  FILTER NOT EXISTS {
    ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
    ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterValue .
    FILTER(?laterAvailable <= "2024-06-30"^^xsd:date && ?laterAvailable > ?available)
  }
}
ORDER BY DESC(?available) LIMIT 1
```

The `FILTER NOT EXISTS` picks the latest filing **that has the metric**; a later filing with a null
value does not hide an earlier non-null one. For an assessment text:

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?assessment ?narrative ?available ?computed WHERE {
  VALUES ?asset { :A }
  ?assessment :assessmentOfAsset ?asset ;
              :availableAt ?available ;
              :computedAt ?computed ;
              :narrative ?narrative ;
              :generatedByLanguageModel true .
  FILTER(?available <= "2024-06-30"^^xsd:date)
  FILTER NOT EXISTS {
    ?later :assessmentOfAsset ?asset ; :availableAt ?laterAvailable .
    FILTER(?laterAvailable <= "2024-06-30"^^xsd:date && ?laterAvailable > ?available)
  }
}
ORDER BY DESC(?available) LIMIT 1
```

**Text rule:** Reviewer A's rule is `availableAt <= D` for every row, including the assessment text.
There is no separate text clock and no `:textAvailableAt`. The generated flag and provenance note
tell the reader that the narrative is a generated interpretation, not a verified fact; the agent
must not present it as one.

---

## 3. Provenance of generated text

### 3.1 The measured split

| `generated_by_language_model` | Rows | `model` | Score/rating | `prompt_hash` | Text |
|---|---:|---|---|---|---|
| `true` | 9,896 | `DeepSeek-V4.1-Flash [thinking=disabled]` | present | present | narrative + strengths + risks |
| `false` | 129 | `unscored-pillar-coverage-v1` | null | present (same hash) | fixed coverage-rule text |

The 129 false rows are **not model output**. They are the fixed text of the rule that leaves a
company unscored when a pillar has no value; they must carry `generatedByLanguageModel false` and a
rule provenance note, never the model label.

### 3.2 Proposed model

`:FundamentalAssessment` (one per `snapshot_id`) carries:

- `:assessmentOfFiling` → `:SECFiling`;
- `:assessmentOfAsset` → `:Asset` (redundant with the filing, but keeps the agent's asset query one
  hop);
- `:snapshotId` (integer, the delivery key);
- `:scoreRaw0to100` (decimal 0-100; absent on the 129 unscored rows);
- `:rating` (`bullish | neutral | bearish`; absent on the 129 unscored rows);
- `:narrative`, repeated `:strength`, repeated `:risk` (literals);
- `:model`, `:computedAt`, `:eventTime`, `:availableAt`;
- `:generatedByLanguageModel` (boolean, required);
- `:provenanceNote` (string, required) with the delivery text **verbatim**:
  - true: `generated by a language model from computed ratios; not a verified fact`
  - false: `rule-based text: no fundamental score (coverage rule); not generated by a model`

The score and rating are stored **on the assessment**; the 129 unscored rows have neither. There is
no `:assessmentOfSnapshot` link and no `:promptHash` (the constant prompt hash stays in the delivery
hash/`source.json`).

**Text isolation.** The narrative, strengths and risks live only on `:FundamentalAssessment`. They
are never attached to `:SECFiling`, `:FundamentalMetricSet`, `:Asset` or `:ScoreSnapshot`, so a
reader cannot mistake generated prose for a filing fact. The `:generatedByLanguageModel` boolean and
the `:provenanceNote` are on the same node as the text. The graph also stores no narrative in
`labels.ttl` or in a metric value.

### 3.3 SHACL and wording

`FundamentalAssessmentShape`:

- required: filing, asset, `snapshotId`, narrative, model, computed time, event time, available
  time, generated flag, provenance note;
- `generatedByLanguageModel true` → `scoreRaw0to100` required and in `[0, 100]`, `rating` in
  `{bullish, neutral, bearish}`, `provenanceNote` exactly the generated string;
- `generatedByLanguageModel false` → `model "unscored-pillar-coverage-v1"`, no score, no `rating`,
  `provenanceNote` exactly the rule string;
- `rating` `sh:in ("bullish" "neutral" "bearish")` when present;
- `narrative` `sh:minLength 1`; `strength`/`risk` strings.

The implementation must copy the two provenance strings character-for-character from the delivery
(or from this document); no paraphrase.

---

## 4. Price masking

### 4.1 Why the mask

The v2 delivery contains no literal price. The valuation group has five metrics:

| Metric | Unit | What it is | Load rule |
|---|---|---|---|
| `market_capitalization` | `usd` | absolute market cap at the filing | load for the 550 unmasked assets; a masked row stops the load |
| `enterprise_value` | `usd` | absolute enterprise value | load for the 550 unmasked assets; a masked row stops the load |
| `enterprise_fcf_yield` | `ratio` | FCF / enterprise value | load for the 550 unmasked assets; a masked row stops the load |
| `free_cash_flow_yield` | `ratio` | FCF / market cap | load for the 550 unmasked assets; a masked row stops the load |
| `sbc_adjusted_fcf_yield` | `ratio` | SBC-adjusted FCF yield | load for the 550 unmasked assets; a masked row stops the load |

The reason is the one in Reviewer A's delivery note: market capitalization and the
shares-outstanding figures can reconstruct the price at each filing date. That is why the **33
Tiingo assets** in `mascara_tiingo/tiingo_assets.csv` get **no valuation group at all**, not just no
absolute market cap: the three valuation yields are derived from the same market cap/EV, so they
are masked together. The v2 delivery is already clean for that rule: 70,445 valuation rows, **0**
for a masked asset, all five valuation metrics for the other 550 assets.

`value_inputs` is not a valuation metric and not a price; it is a rule input. It has **no
property** (the 37 loaded properties are the 38 source names minus `value_inputs`), so its 14,639
rows are discarded for every asset, masked or not, and never raise an error. Only a `valuation`
row of a masked asset stops the load. The delivered v2 file still contains 550 masked
`value_inputs` rows; they are dropped before projection and are not an error.

Nothing else is filtered: the loader loads the other 37 metric names for every filing, including the
five valuation metrics for the 550 unmasked assets.

### 4.2 Delivery v2 and counts

- v2 `metrics.csv`: **509,933 rows**, `SHA256SUMS` `fd32daed…`.
- 37 loaded metrics: **495,294 rows**, **406,570 non-null** (the 38 names minus 14,639
  `value_inputs` rows).
- valuation: **70,445 rows**, all unmasked; **0** masked.
- `value_inputs`: 14,639 rows (550 masked), no property, not loaded.
- `:pricesNotPublished true`: **33 triples**, one per masked asset, including FRC and SBNY.
- Expected data graph: **834,586 asserted triples** (873,889 with the one inferred type per metric
  set, assessment and filing), about 20% of the current ~4.18M store.
- The other 550 assets load all five valuation metrics; no price or daily-return property is
  written.

### 4.3 Planned loader tests

- A masked asset with a `valuation` row stops the load with the row list.
- A `value_inputs` row of a masked asset is discarded, not an error.
- An unmasked asset loads all five valuation metrics.
- The batch contains no price or daily-return property: no `:closePrice`, `:PriceObservation`,
  `:observationDate`, `:dailyReturnPct`, `:atr14` or equivalent; `:marketCapitalization` and
  `:enterpriseValue` are the only valuation USD properties and they are metric values, not prices.
- The 33 `:pricesNotPublished` flags are present, including FRC/SBNY.

### 4.4 SHACL

`FundamentalMetricSetShape` is closed over the 37 metric properties plus the metadata properties;
it rejects any price or daily-return property (for example `:closePrice`) and any unknown metric.
`FundamentalMetricDefinitionShape` allows `:metricUnit "usd"` on `ebitda`, `nopat`,
`marketCapitalization` and `enterpriseValue`, and no other name. There is no
`:containsPriceDerivedValue` property and no structural valuation exclusion; the mask is the loader
check above.

---

## 5. Keys, IRIs, graph and existing `ScoreSnapshot`

### 5.1 Graph

Proposed graph: **`urn:graph:derived:fundamentals:final`** — one append-only graph per label, same
shape as `backtest:meta:{label}` and `backtest:aggregates:{label}`. The gate pattern is

```
urn:graph:derived:fundamentals:([a-z][a-z0-9_]{1,31})
```

and it is added to `APPEND_ONLY_PATTERNS`/`check_target` in the implementation. A later delivery is
a new label or a dated suffix, never an append to this graph. The graph does not touch any
`urn:graph:derived:backtest:*`, `urn:graph:ingest:FUNDAMENTAL:*` or engine graph.

### 5.2 Stable IRIs

| Entity | IRI | Key |
|---|---|---|
| Filing | `:Filing_{label}_{filing_id}` | `filing_id` |
| Metric set | `:FundamentalMetricSet_{label}_{filing_id}` | `filing_id` |
| Assessment | `:FundamentalAssessment_{label}_{snapshot_id}` | `snapshot_id` |
| Metric definition | `:FundamentalMetric_{metric_name}` in `labels.ttl` | `metric_name` |
| Graph | `urn:graph:derived:fundamentals:{label}` | label |

The label is included in every data IRI, following the Work item 44 pattern. The loader **always
mints** `:Filing_{label}_{filing_id}` in this graph; it does not query the store for an existing
`:SECFiling` by `accessionNumber` and does not restate an unlabelled filing. The metric set and
assessment are new individuals keyed by `filing_id`/`snapshot_id` and point at that filing IRI.

### 5.3 Keys and deduplication

- `filing_id` unique in `filings.csv`; `accession_number` unique; one metric set per filing.
- `metric_id` unique; `(filing_id, metric_name)` unique (one value per metric per filing). The
  loader refuses a duplicate. The final model does **not** store a per-metric ID map; a value is
  keyed by `(filing_id, metric_name)`, and the delivery's `metric_id` stays in the source file. A
  reviewer who needs every `metric_id` as an IRI must choose model A.
- `snapshot_id` unique; one assessment node per row. `filing_id` may in principle repeat (this
  delivery has exactly one assessment per filing, but the loader keys by `snapshot_id` and does not
  enforce one-per-filing unless Reviewer A asks).
- The loader loads only the selected 37 metric names; a missing name is null (no triple), never an
  error, and every non-null value has its decimal triple. Null values have no triple.
- The loader refuses a metric row whose `filing_id` is not in `filings.csv`, a value that is not a
  decimal (empty is a legitimate null), an unknown unit, an unknown group/name, a `computed_at`
  that is not a dateTime, and an `available_at` that differs from the filing's.

### 5.4 Existing `ScoreSnapshot` data

The final model does **not** link to or require existing `ScoreSnapshot` individuals: production has
zero `:ScoreSnapshot` individuals (checked 2026-11-13), and this loader does not create any. The
assessment carries its own `:scoreRaw0to100` and `:rating`; the 129 rule rows have neither. No
`ScoreSnapshot` is minted and no score is duplicated. If a later store has snapshots, a link can be
added by a follow-up; it is not part of T-813–T-815.

---

## 6. Loader plan

### 6.1 Files and CLI

- `src/projection/fundamentals.py`: strict parser, manifest check, projector, stored-graph check,
  CLI logic (mirroring `src/projection/mv_base.py`).
- `cli/load_fundamentals.py`: thin entry point with the same `sys.path` bootstrap as
  `cli/load_mv_base.py`.
- `tests/test_fundamentals.py`: hermetic parser/projector/gate tests with a small fixture.
- `tests/test_cli_load_fundamentals.py`: subprocess help/flag/manifest tests, like
  `test_cli_load_mv_base.py`.
- Schema/labels changes in the implementation PR, not here: the TBox delta below, the new
  `FundamentalMetricScheme` in `labels.ttl`, the four shapes, the gate target and the runbook step.

Proposed TBox delta:

| Layer | New terms | Reused terms |
|---|---|---|
| Filing | `:filingId` (integer), `:periodEnd` (date), `:fiscalYear` (integer), `:fiscalPeriod` (string) | `:formType`, `:filingDate`, `:accessionNumber`, `:filingOfAsset`, `:availableAt` |
| Asset | `:pricesNotPublished` (boolean, 33 masked assets) | `:tickerSymbol`, `:cikNumber` |
| Metric set | `:FundamentalMetricSet` (class, `rdfs:subClassOf :Observation`), `:metricSetOfFiling`, 37 metric decimal properties | `:availableAt`, `:computedAt`, `:engineVersion` |
| Assessment | `:FundamentalAssessment` (class, `rdfs:subClassOf :Observation`), `:assessmentOfFiling`, `:assessmentOfAsset`, `:snapshotId`, `:scoreRaw0to100`, `:rating`, `:narrative`, `:strength`, `:risk`, `:model`, `:generatedByLanguageModel`, `:provenanceNote` | `:computedAt`, `:eventTime`, `:availableAt` |
| SHACL | `FundamentalFilingShape`, `FundamentalMetricSetShape`, `FundamentalAssessmentShape`, `FundamentalMetricDefinitionShape` | existing gate/shape machinery |
| Labels | `:FundamentalMetricScheme` + 37 `:FundamentalMetric_<name>` concepts in `labels.ttl`; bilingual `rdfs:label`/`rdfs:comment` on every new TBox term | `:PresentationScheme`, `:LabelConceptShape` |

`SECFiling` keeps its place under `SourceDocument`; the metric set and the assessment are
`Observation`s. `:availableAt` loses its `:ScoreSnapshot` domain; `:computedAt`/`:eventTime` are
widened to `:Observation`.

### 6.2 Manifest and strict parser

`SHA256SUMS` lists `README.md`, `filings.csv`, `metrics.csv`, `assessments.jsonl`, `source.json`
and `provenance/export_bloque_c.py`; all six must be present and match. The v2 manifest's own hash
is `fd32daed…`; the loader prints it and the `source.json` database hash for the run record. The
manifest is checked before the store is contacted.

Strict rules, all refused with a message naming the file/row/key:

- exact header and no unknown/missing columns in the two CSVs and the JSONL object;
- unique `filing_id`, `accession_number`, `metric_id`, `(filing_id, metric_name)`, `snapshot_id`;
- `filing_id` foreign keys in metrics/assessments; `asset_id`/`ticker` consistent with the filing;
- `form` in `10-K | 10-Q`; dates parse; `available_at` matches the filing; `computed_at` is a
  dateTime; `value` is a decimal or empty; `unit` in `ratio | x | usd` and matches the metric's
  declared unit; `metric_group` in the 10 groups; `metric_name` in the 38 names; `engine_version` is
  `metrics-v10`. The source occasionally writes scientific notation
  (`-1.8058872198019004e-05`); the loader accepts it and writes the expanded `xsd:decimal` form;
- `generated_by_language_model` is a JSON boolean; `model`, `prompt_hash`, `rating` strings;
  `strengths`/`risks` are arrays of strings; `narrative` non-empty; the 129 false rows have the
  rule model and null score/rating; the 9,896 true rows have a score and rating;
- **mask check:** if a masked asset has a `valuation` row, stop with the row list. The v2
  delivery has no masked valuation rows; its 550 masked `value_inputs` rows are discarded before
  projection and never raise an error (see §4.1);
- `value_inputs` has no property; its 14,639 rows are counted and dropped. There is no
  `--include-valuation-ratios` flag;
- unknown metric names/values and extra columns are refused, not ignored.

### 6.3 Dry run, `--check-store`, `--write`

- **Dry run** (no `--check-store`, no `--write`): parse, project, print counts per class/property,
  and run `SHACL: conforms (gate.validate)`; contacts no store.
- **`--check-store`**: builds the same batch, opens the store **without** `--write` (the T-791
  `open_store` pattern: `check_store or write`), calls `gate.plan` with `SELECT` only, prints
  `would-be-written` / `already-in-store` / `refused`, and writes nothing. The target banner is
  printed as today.
- **`--write`**: plans first, writes the one graph only after the plan is accepted; production
  requires `--to-production`; the engine graphs are untouched. On a verification failure, print the
  exact one-graph `DROP GRAPH <urn:graph:derived:fundamentals:final>` for the maintainer; the agent
  never runs it. Never `CLEAR ALL`, `DROP ALL`, a repository delete or a second graph.
- **Verification**: stored graph triple count equals the batch, per-class counts, sample values,
  the 37-metric policy, the 33 `:pricesNotPublished` flags, the 9,896 scores/ratings and the 129
  rule rows; no engine graph receives a triple.

### 6.4 Counts and tests

The design's full-delivery expected count for C (37 metrics, all filings, no metric ID map) is
**834,586 asserted** (873,889 with inference). The assessed-only pilot is **644,512 asserted**
(674,587 with inference). The schema counts are **9125 quads**, load plan **21/9402** and production
**5/8881**; 72 classes, 58 disjoint leaves, 57 named shapes. The implementation must measure the actual
`D` and update every asserted count in the same PR (NR-001): FR-001, the schema/labels counts, the
load-plan/production counts if the schema files change, and the loader fixture count. The
full-delivery count is recorded in the runbook and the dry-run output, not in a hermetic test; the
hermetic test uses a small fixture and asserts its exact batch count and the refusal cases.

The test file should cover: manifest mismatch/missing entry, unknown column/value, duplicate
`filing_id`/`metric_id`/`snapshot_id`, a metric row with a mismatched `available_at`, an unknown
metric/unit/group, a masked valuation row, a masked `value_inputs` row that is discarded without
an error, the five valuation metrics for an unmasked asset, the 33 flags, the 9,896 scores and the
129 rule rows, the exact fixture triple count, SHACL conformance, and the `--check-store` no-write
path.

### 6.5 Runbook and no DROP

Add a section to `docs/backtest-load-runbook.md` after the external Markowitz step, and a step 7c
to `docs/final-delivery.md` if the maintainer wants one command sequence: dry run → `--check-store`
→ `--write --to-production` → verify. Both are added (runbook §1h and final-delivery §7c). The
runbook records the measured counts, the manifest hash, the `source.json` hash, the graph name and
the one-graph rollback command. The loader and the agent never run a DROP; only the maintainer may
drop the one graph after a failed write, following `docs/backtest-load-runbook.md` §9.

### 6.6 Measured dry run (2026-11-13)

The v2 delivery, the verified mask and `/workspaces/thesis/data/universe_history_gics.db` were
read without a store. The loader printed **834,586 asserted triples**, **33**
`:pricesNotPublished` flags, 14,639 filings/metric sets, 10,025 assessments (9,896 scored and 129
rule rows), and `SHACL: conforms (gate.validate)`. Timing: 23.065 s manifest+parse+project,
580.902 s SHACL and 603.967 s total; peak memory 4,511.8 MB. The whole-batch SHACL is the same
order as the 932 s engine dry run recorded in `final-delivery.md`, so no batching is proposed for
this delivery; a larger delivery should batch the SHACL pass before a write. Nothing was written.

---

## 7. Questions for Reviewer A

1. **`value_inputs` in the v2 delivery (resolved 2026-11-13).** The v2 file has 550
   `value_inputs` rows for masked assets. The loader discards `value_inputs` for every asset (no
   property) and never treats those rows as an error; it stops only on a `valuation` row of a
   masked asset. The delivery does not need to be regenerated.
2. **Filing scope.** Load all 14,639 filings (834,586 asserted) or the 10,025 assessed filings first
   (644,512 asserted, C-pilot)? The pilot drops 4,614 filings that have metrics but no assessment.
3. **Metric IDs.** The final model has no per-metric map; values are keyed by
   `(filing_id, metric_name)`. Is that enough, or must every `metric_id` be an individually
   addressable RDF resource? If the latter, the fallback is model A restricted to 37 metrics and
   the assessed-only pilot.
4. **Text nodes.** Is storing narrative/strengths/risks as repeated literals on the assessment
   enough, or do you want separate narrative/point nodes?
5. **Labels.** Reviewer A approved the 58-row table (2 classes + 19 properties + 37 metric
   concepts); the 37 concepts are now in `labels.ttl` under `:FundamentalMetricScheme`.
6. **Shape count.** Four new shapes take the named count from 40 to 44; confirm the rebaseline.
7. **Graph name.** Confirm `urn:graph:derived:fundamentals:{label}` and the append-only/no-DROP
   rule; `final` is the only label for this delivery.

## Appendix A — the 38 metrics and the assessment citations

The citation column is a case-insensitive alias count over `narrative` + `strengths` + `risks`
(e.g. `ROIC`, `return on invested capital`, `FCF margin`); it is an indicative count, not a
semantic parse. The v2 row counts are shown; `load` means the 37-metric allowlist loads it for every
filing, with the loader stopping on a valuation row of a masked asset. `value_inputs` is the only
`never` (no property; its rows are dropped).

| Metric | Group | Unit | Rows | Non-null | Assessments citing | Policy |
|---|---|---|---:|---:|---:|---|
| `return_on_equity` | profitability | ratio | 14,639 | 13,330 | 9,202 | load |
| `return_on_invested_capital` | roic | ratio | 14,639 | 11,535 | 8,821 | load |
| `interest_coverage` | leverage | x | 14,639 | 11,757 | 8,638 | load |
| `net_margin` | profitability | ratio | 14,639 | 14,599 | 8,386 | load |
| `operating_cash_flow_margin` | cashflow | ratio | 14,639 | 12,683 | 8,376 | load |
| `capex_intensity` | cashflow | ratio | 14,639 | 12,443 | 8,371 | load |
| `free_cash_flow_margin` | cashflow | ratio | 14,639 | 12,414 | 8,369 | load |
| `ebitda` | leverage | usd | 14,639 | 12,048 | 8,209 | load |
| `operating_margin` | profitability | ratio | 14,639 | 12,923 | 7,885 | load |
| `net_debt_to_ebitda` | leverage | x | 14,639 | 11,084 | 7,817 | load |
| `free_cash_flow_conversion` | cashflow | x | 14,639 | 11,287 | 7,804 | load |
| `gross_margin` | profitability | ratio | 14,639 | 9,529 | 7,554 | load |
| `return_on_assets` | profitability | ratio | 14,639 | 12,385 | 7,541 | load |
| `cash_ratio` | liquidity | x | 14,639 | 12,124 | 6,761 | load |
| `current_ratio` | liquidity | x | 14,639 | 12,315 | 6,380 | load |
| `free_cash_flow_yield` | valuation | ratio | 14,089 | 11,601 | 6,098 | load |
| `revenue_growth` | growth | ratio | 14,612 | 14,585 | 5,246 | load |
| `debt_to_equity` | leverage | x | 14,639 | 11,955 | 4,999 | load |
| `quick_ratio` | liquidity | x | 14,639 | 11,136 | 3,638 | load |
| `debt_to_assets` | leverage | ratio | 14,639 | 12,874 | 3,455 | load |
| `net_income_growth` | growth | ratio | 14,612 | 13,192 | 3,025 | load |
| `operating_income_growth` | growth | ratio | 14,612 | 11,894 | 2,840 | load |
| `free_cash_flow_growth` | growth | ratio | 14,612 | 10,092 | 2,643 | load |
| `return_on_invested_capital_effective_rate` | roic | ratio | 14,639 | 10,462 | 2,499 | load |
| `asset_turnover` | efficiency | x | 14,639 | 14,145 | 2,458 | load |
| `sbc_adjusted_fcf_yield` | valuation | ratio | 14,089 | 10,274 | 2,341 | load |
| `effective_tax_rate` | roic | ratio | 14,639 | 13,053 | 2,081 | load |
| `enterprise_fcf_yield` | valuation | ratio | 14,089 | 8,900 | 1,972 | load |
| `receivables_turnover` | efficiency | x | 14,639 | 12,315 | 1,885 | load |
| `inventory_turnover` | efficiency | x | 14,639 | 6,979 | 1,069 | load |
| `net_income_cagr` | cagr | ratio | 3,771 | 3,157 | 1,013 | load |
| `revenue_cagr` | cagr | ratio | 3,771 | 3,708 | 986 | load |
| `operating_cash_flow_cagr` | cagr | ratio | 3,771 | 3,188 | 844 | load |
| `enterprise_value` | valuation | usd | 14,089 | 11,526 | 273 | load |
| `market_capitalization` | valuation | usd | 14,089 | 13,468 | 167 | load |
| `utility_cash_coverage_3y` | rule_input | ratio | 3,752 | 2,783 | 138 | load |
| `nopat` | roic | usd | 14,639 | 12,827 | 49 | load |
| `value_inputs` | rule_input | usd | 14,639 | 14,196 | 3 | never |

## Appendix B — reproducibility

All counts in this document were computed from the real files with standard-library Python
(`csv`, `json`, `re`, `hashlib`) and `sha256sum -c`; no GraphDB command was run. The manifest,
`source.json` and `provenance/export_bloque_c.py` were read-only. The full metric table, the group
table, the masked-asset counts and the model budgets are reproducible from the files in the delivery
folder; the implementation tests must use a hermetic fixture, not this folder.
