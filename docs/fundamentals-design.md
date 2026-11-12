# Fundamentals block C loader — design (Work item 45, T-810)

**Status:** design, 2026-11-12. No code, no schema edit, no GraphDB write.

**Source delivery:** `/workspaces/thesis/knoledge graph/bloque_c_fundamentales/`.
`SHA256SUMS` hashes to `f640ba4d81ce94bc4bbfa2887b310f43651d9f600d6e295e16c23808afcb5d12`;
all six listed entries verify with `sha256sum -c`. `source.json` names `scored_llm.db` with
`sha256 2187c36bae42296b84d63031e9058df5aba997a77da2a4aa6665279452e184ca`. The
`provenance/export_bloque_c.py` script is listed in the manifest and is required for this delivery
(unlike Work item 44, where `provenance/` was optional).

**Scope of T-810:** this document, the Work item 45 entries in `PLAN.md` and `TASKS.md`, tests only
for the touched documentation, and a PR. No loader, schema, label, count or GraphDB change is made
here. The implementation is reserved for T-811–T-815 after Reviewer A answers §7.

> **Addendum 2026-11-13 (Reviewer A, implementation).** The final metric set is **35** direct
> properties: the 31 base metrics plus `enterprise_fcf_yield`, `free_cash_flow_yield`,
> `sbc_adjusted_fcf_yield` and `utility_cash_coverage_3y`. The three valuation yields are skipped
> row-level for the 33 masked assets; there is no `--include-valuation-ratios` flag and no
> `:containsPriceDerivedValue`/`:metricIdsJson`. There is no `:assessmentOfSnapshot` link and no
> `:promptHash`: the assessment carries its own score and rating, and the constant prompt hash
> stays in the delivery hash/`source.json`. The loader count is measured in T-813–T-815; the
> schema count is in `PLAN.md`/`TASKS.md` and `docs/labels-fundamentals-review.md`.

---

## 0. Recommendation in one paragraph

Load **one `:FundamentalMetricSet` per filing** with **31 direct decimal properties** (the default
set: every metric except the five `valuation` metrics and the two `rule_input` metrics), plus **one
`:FundamentalAssessment` per assessment** that links to the existing `FUNDAMENTAL` `:ScoreSnapshot`
instead of duplicating its score. The expected batch is **800,981 asserted triples** over all 14,639
filings (about **840k** including the one inferred type per individual, or **815,620 / 855k** with
the optional `:containsPriceDerivedValue` guard), roughly **20% of the current ~4.18M-triple
production store**. The three reified-observation variants would add 2.6M–4.4M asserted triples and
are rejected. The 31-metric set is every metric except the five `valuation` and two `rule_input`
metrics; every one of the 31 is cited in at least 49 assessment records, and 30 of them in at least
844. The three valuation yields are behind an explicit, off-by-default flag; the two price-derived
absolute USD metrics are never loaded.

---

## 1. Delivery profile and the volume problem

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
+ metric sets × 6            (options B/C; not in A)
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

The per-assessment budget is: type, filing, asset, `snapshot_id`, narrative, model, prompt hash,
computed time, event time, available time, generated flag, provenance note (12 fixed); plus the
`ScoreSnapshot` link and `rating` for the 9,896 scored rows (2 each); plus one triple per strength
and risk. The score itself is **not** repeated; it is read from the linked snapshot. If the score is
also stored on the assessment, add 9,896 triples.

The per-metric-set budget is: type, filing link, `availableAt`, `computedAt`, `engineVersion`,
`metricIdsJson` (6 fixed). The per-filing budget is: type, asset, form, filing date, period end,
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
    :metricIdsJson "{\"return_on_invested_capital\": 1234, ...}" ;
    :returnOnInvestedCapital "0.184"^^xsd:decimal ;
    :netMargin "0.213"^^xsd:decimal ;
    ... .
```

Each of the 38 metrics is a `owl:DatatypeProperty` with domain `:FundamentalMetricSet`, range
`xsd:decimal` and `owl:FunctionalProperty`. A null value is **no triple**, not a null literal. The
legacy `metric_id` of every metric in the selected set is preserved in the one `:metricIdsJson` map,
with `null` for a missing value. The map covers all 31 (or 38) keys, so the delivery key is
auditable even when the value is null; the value triple is absent for a null.

| Variant | Asserted | Inferred | Total | Store after |
|---|---:|---:|---:|---:|
| B, all 38 metrics, all filings | 875,997 | 39,303 | 915,300 | ~5.1M |
| B, default 31, all filings | 800,981 | 39,303 | 840,284 | ~5.0M |

**Agent query:** `?set :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?value`, with the same
`availableAt <= D` and latest-filing pattern as A (the property replaces the observation join).

**SHACL/class/property needs:** `FundamentalMetricSetShape` with 38 (or 31) `sh:property` blocks,
each `sh:datatype xsd:decimal` and `sh:maxCount 1`; `FundamentalAssessmentShape`;
`FundamentalFilingShape`; two OWL classes and 38 properties plus the 38 metric concepts in
`labels.ttl`.

**Inference:** one extra `:Observation` type per set, assessment and filing (~39k). **Do not** make
the 38 properties subproperties of a generic `:metricValue`: that would add one inferred triple per
value (~0.42M) and defeat the compactness.

**Why not:** 38 properties and 38 `labels.ttl` rows are a lot of schema for metrics that the
assessments rarely cite; the 31-metric set is the same model with a smaller, price-safe vocabulary.

### 1.5 Model C — the restricted metric set (recommended)

Model B with **31 metrics** (all groups except `valuation` and `rule_input`), all 14,639 filings.
This is the set the assessments actually cite: every one of the 31 appears in at least 49
assessment records, and 30 of them appear in at least 844. The five valuation metrics (73,195 rows)
and two `rule_input` metrics (18,391 rows) are excluded by the price-masking policy of §4. The
optional `--include-valuation-ratios` flag adds only the three valuation **ratio** metrics
(`enterprise_fcf_yield`, `free_cash_flow_yield`, `sbc_adjusted_fcf_yield`, 43,917 rows); the two
absolute USD valuation metrics are never loaded.

All C rows below are **before** the optional `:containsPriceDerivedValue` guard of §4.3; add
14,639 to each asserted and total count if the guard is kept.

| Variant | Asserted | Inferred | Total | Store after |
|---|---:|---:|---:|---:|
| C, default 31, all filings | 800,981 | 39,303 | 840,284 | ~5.0M |
| C-pilot, default 31, assessed-only (10,025 filings) | 621,598 | 30,075 | 651,673 | ~4.8M |
| C + flag, 34 metrics (31 + 3 valuation ratios), all filings | 844,898 | 39,303 | 884,201 | ~5.1M |

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

**SHACL/class/property needs:** `FundamentalMetricSetShape` with 31 decimal properties,
`FundamentalAssessmentShape`, `FundamentalFilingShape`, `FundamentalMetricDefinitionShape`; two OWL
classes (`FundamentalMetricSet`, `FundamentalAssessment`) and 31 metric properties plus the
assessment/filing properties; 31 metric concepts in `labels.ttl` under a new
`FundamentalMetricScheme`. Each TBox class/property gets bilingual `rdfs:label`/`rdfs:comment`
(the T-754 pattern); each metric concept gets the full `labels.ttl` row (notation, scheme,
`labelScheme`, bilingual label/comment, optional altLabels, group/unit).

**Inference:** one extra `:Observation` type per metric set, assessment and filing (~39k for all
filings, ~30k for the pilot). No subproperty hierarchy. The 31 properties' `rdfs:domain` infers the
already-asserted `:FundamentalMetricSet` type, so it adds no new triple beyond that type.

### 1.6 Comparison and recommendation

| Criterion | A (reified) | B (all 38) | C (31, recommended) |
|---|---|---|---|
| Asserted triples (all filings) | 4,376,944 | 875,997 | **800,981** |
| Total with inference | 4,914,291 | 915,300 | **840,284** |
| Store after (approx.) | ~2.2× | ~1.22× | **~1.20×** |
| Agent query | observation join | direct property | **direct property** |
| Per-`metric_id` IRI | yes | no (`metricIdsJson`) | no (`metricIdsJson`) |
| New metric properties | 0 (one link) | 38 | **31** |
| New `labels.ttl` concepts | 38 | 38 | **31** |
| SHACL blocks | 4 shapes, one observation shape | 4 shapes, 38 property blocks | **4 shapes, 31 property blocks** |
| Inference per value | 1 type per observation | none | **none** |
| Price-mask safety | needs a unit check per row | properties can omit the two USD names | **two USD names have no property at all** |

**Recommendation: C.** It keeps the graph queryable with plain SPARQL, preserves the source
`metric_id` in one map per filing, avoids the 4M reified observations, and makes the price-masking
policy structural: the two price-derived absolute USD metrics have no property in the TBox, so a
loader bug cannot write them. If Reviewer A needs per-`metric_id` RDF identity, the fallback is A
restricted to the 31 metrics and the assessed-only pilot (2.58M asserted), not A all-38.

The 17 metrics cited in at least 50% of assessments are a possible tier-1 first load, but they omit
common questions (`debt_to_equity` at 4,999 records, `quick_ratio` at 3,638, the growth/cagr set) and
are not recommended as the default. The 31-metric set is the best coverage/volume compromise.

---

## 2. Point in time

### 2.1 The measured clocks

| Field | Meaning | Measured |
|---|---|---|
| `filings.available_at` | first date the filing can be used | always **after** `filing_date` (0 exceptions) |
| `metrics.available_at` | same date as the filing | 512,683 / 512,683 equal |
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

**Text caveat:** the narrative was computed in 2026 (`computed_at` 2026-11-03) from a filing that
became available years earlier. For a strict "what existed at D" answer, the agent must not present
the narrative as a contemporaneous fact before `computedAt`. It may use the filing fact at
`availableAt` and quote the narrative as a **current generated interpretation**, with the generated
flag and note. If Reviewer A wants one filter for text, the loader can also write
`:textAvailableAt = max(available_at, computed_at)` (one extra triple per assessment) and the agent
filters text on that; this is question Q5 in §7.

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
- `:assessmentOfSnapshot` → the existing `FUNDAMENTAL` `:ScoreSnapshot` (optional, 9,896 scored
  rows; see §5.4);
- `:snapshotId` (integer, the delivery key);
- `:rating` (`bullish | neutral | bearish`; absent on the 129 unscored rows);
- `:narrative`, repeated `:strength`, repeated `:risk` (literals);
- `:model`, `:promptHash`, `:computedAt`, `:eventTime`, `:availableAt`;
- `:generatedByLanguageModel` (boolean, required);
- `:provenanceNote` (string, required) with the delivery text **verbatim**:
  - true: `generated by a language model from computed ratios; not a verified fact`
  - false: `rule-based text: no fundamental score (coverage rule); not generated by a model`

The score is **not** stored on the assessment when the snapshot link exists; it is
`:ScoreSnapshot :rawValue`. This is the "do not duplicate, link" rule. The 129 unscored rows have no
score to link and no `:rating`.

**Text isolation.** The narrative, strengths and risks live only on `:FundamentalAssessment`. They
are never attached to `:SECFiling`, `:FundamentalMetricSet`, `:Asset` or `:ScoreSnapshot`, so a
reader cannot mistake generated prose for a filing fact. The `:generatedByLanguageModel` boolean and
the `:provenanceNote` are on the same node as the text. The graph also stores no narrative in
`labels.ttl` or in a metric value.

### 3.3 SHACL and wording

`FundamentalAssessmentShape`:

- required: filing, asset, `snapshotId`, narrative, model, computed time, event time, available
  time, generated flag, provenance note;
- `generatedByLanguageModel true` → `promptHash` required, `assessmentOfSnapshot` required,
  `rating` in `{bullish, neutral, bearish}`, `provenanceNote` exactly the generated string;
- `generatedByLanguageModel false` → `model "unscored-pillar-coverage-v1"`, no `rating`, no
  `assessmentOfSnapshot`, `provenanceNote` exactly the rule string; the `promptHash` may be present
  as source provenance but is not used as a model signal;
- `rating` `sh:in ("bullish" "neutral" "bearish")` when present;
- `narrative` `sh:minLength 1`; `strength`/`risk` strings.

The implementation must copy the two provenance strings character-for-character from the delivery
(or from this document); no paraphrase.

---

## 4. Price masking

### 4.1 What is and is not a price

The delivery contains **no literal price**. The valuation group has five metrics:

| Metric | Unit | What it is | Mask decision |
|---|---|---|---|
| `market_capitalization` | `usd` | absolute market cap at the filing; price-derived | **never load** |
| `enterprise_value` | `usd` | absolute enterprise value; price-derived | **never load** |
| `enterprise_fcf_yield` | `ratio` | FCF / enterprise value; derived ratio | flag only |
| `free_cash_flow_yield` | `ratio` | FCF / market cap; derived ratio | flag only |
| `sbc_adjusted_fcf_yield` | `ratio` | SBC-adjusted FCF yield; derived ratio | flag only |

The other `usd` metrics are **not prices**:

- `ebitda` (leverage): income-statement amount;
- `nopat` (roic): income-statement amount;
- `value_inputs` (rule_input): a rule input amount, not a price.

`market_capitalization` and `enterprise_value` are the two price-derived absolute USD values. They
are the metrics the rule must never load, for any asset, not only the 33 masked ones. The three
valuation yields are derived ratios, but they are still derived from market cap/EV; the default
loader excludes them too, and only an explicit flag can add them. No metric in the delivery is a
literal traded price, so the SHACL assertion below is written as "no absolute price-derived USD
value", not "no price field" (there is no price field to forbid).

### 4.2 Default exclusion and counts

Default batch (flag off):

- exclude the whole `valuation` group: **73,195 rows** (14.3% of 512,683); of these **2,750** are
  masked-asset rows. This is the price-mask requirement;
- exclude the whole `rule_input` group: **18,391 rows**; of these **695** are masked-asset rows.
  This is a separate coverage decision, not a price rule: `rule_input` is an internal rule input,
  not an agent-facing ratio, and its two names are cited only 138 and 3 times;
- total excluded: **91,586 rows** (17.9%), **3,445** masked-asset rows;
- loaded: **421,097 rows** (31 metrics), **15,835** masked-asset rows.

Absolute price-derived rows excluded even with the flag on:

- `market_capitalization` 14,639 rows (550 masked);
- `enterprise_value` 14,639 rows (550 masked);
- total **29,278 rows** (1,100 masked).

Flag `--include-valuation-ratios` (off by default):

- adds the three ratio metrics: 43,917 rows (1,650 masked);
- never adds the two absolute USD metrics;
- the batch becomes 465,014 rows (34 metrics), 17,485 masked-asset rows.

If a future flag ever includes `rule_input`, `value_inputs` (14,639 rows, 550 masked) is an
absolute USD rule input, not a price; it may be loaded only if the agent needs it, and it is not part
of the recommended set.

### 4.3 Structural guard and SHACL assertion

The compact model makes the mask structural: the TBox has **no property** for
`market_capitalization` or `enterprise_value`, so the loader's allowlist cannot write them. The
loader also refuses any input row whose metric name is outside the selected 31/34 and any `usd` row
whose name is not `ebitda` or `nopat` (plus `value_inputs` only under a future rule-input flag).

`FundamentalMetricSetShape` adds the auditable assertion:

- `:containsPriceDerivedValue` (boolean, required, `sh:hasValue false`) on every metric set; the
  loader writes `false` because it cannot write the two price-derived properties. This costs one
  triple per filing (14,639) and gives the agent a direct check.
- The 31 metric properties are decimal and have no `:metricUnit "usd"` value; the unit is a
  property of the metric definition in `labels.ttl`. `FundamentalMetricDefinitionShape` asserts
  `:metricUnit "usd"` only for `ebitda` and `nopat` (and `value_inputs` if the rule-input flag is
  ever added), and never for `market_capitalization`/`enterprise_value`.
- The target graph pattern is separate from `PriceObservation`/`derived:quant`; no price property
  or price graph is touched. The batch contains no `:closePrice`, `:PriceObservation`,
  `:marketCapitalization` or `:enterpriseValue` triple.

The count with `:containsPriceDerivedValue` is 800,981 + 14,639 = **815,620 asserted** for C all
filings (840,284 + 14,639 = **854,923 total** with inference). We include it in the recommendation;
if Reviewer A prefers no extra guard triple, the shape-only version is 800,981.

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

The label is included in every data IRI, following the Work item 44 pattern. If a `:SECFiling` with
the same `accessionNumber` already exists, the loader **reuses** that IRI (adds `:filingId`,
`:availableAt`, `:periodEnd`, `:fiscalYear`, `:fiscalPeriod` if missing) instead of minting a second
filing; the `:Filing_{label}_{filing_id}` form is the fallback when no existing filing matches. The
metric set and assessment are new individuals keyed by `filing_id`/`snapshot_id` and point at the
filing IRI actually used.

### 5.3 Keys and deduplication

- `filing_id` unique in `filings.csv`; `accession_number` unique; one metric set per filing.
- `metric_id` unique; `(filing_id, metric_name)` unique (one value per metric per filing). The
  loader refuses a duplicate. The `metric_id` map is stored as `:metricIdsJson` on the set:
  `{"return_on_invested_capital": 1234, "net_margin": 1235, ...}`. This keeps the delivery key
  without 512k reified nodes. A reviewer who needs every `metric_id` as an IRI must choose model A.
- `snapshot_id` unique; one assessment node per row. `filing_id` may in principle repeat (this
  delivery has exactly one assessment per filing, but the loader keys by `snapshot_id` and does not
  enforce one-per-filing unless Reviewer A asks).
- Every non-null `metric_id` in `:metricIdsJson` is an integer and a null value is `null`; the
  loader checks the map has exactly the selected metric names (31 or 38) and that its non-null
  entries equal the number of value triples.
- The loader refuses a metric row whose `filing_id` is not in `filings.csv`, a value that is not a
  decimal (empty is a legitimate null), an unknown unit, an unknown group/name, a `computed_at`
  that is not a dateTime, and an `available_at` that differs from the filing's.

### 5.4 Existing `ScoreSnapshot` data

The 9,896 scored assessments are **not** a new score source; they are links to the `FUNDAMENTAL`
`ScoreSnapshot` rows already in the graph (the `v_score_snapshot`/`score_snapshots.py` projection).
The loader resolves the link with a read-only SPARQL query by natural key:

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>
SELECT ?snapshot ?timestamp WHERE {
  VALUES ?asset { :A }
  ?asset :hasScoreObservation ?snapshot .
  ?snapshot :agentOrigin "FUNDAMENTAL" ;
            :metricType "ScoreFinanciero" ;
            :eventTime "2021-09-30"^^xsd:date ;
            :availableAt "2021-10-22"^^xsd:date ;
            :rawValue 26.2 ;
            :timestamp ?timestamp .
}
ORDER BY DESC(?timestamp)
```

If exactly one snapshot matches, write `:assessmentOfSnapshot` and do not write
`:scoreRaw0to100`. If the graph has several engine versions, choose the latest `:timestamp` among
`availableAt <= D` (the existing `docs/07` rule), and report the choice. If no snapshot matches a
scored assessment, the loader stops by default and lists the missing `snapshot_id`s; a pilot flag
`--allow-missing-snapshot` may load the assessment without the link and without a score, with
`:snapshotLinkStatus "missing"` (question Q1). The 129 unscored rows never have a snapshot link and
never get a score.

The assessment IRI includes `snapshot_id`; if the existing snapshot projector later adds a
`:snapshotId` literal, the loader can use that as the primary key and fall back to the natural key
above. No duplicate `ScoreSnapshot` is minted, and no `rawValue` is repeated on the assessment.

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
| Metric set | `:FundamentalMetricSet` (class, `rdfs:subClassOf :Observation`), `:metricSetOfFiling`, `:metricIdsJson`, 31 metric decimal properties | `:availableAt`, `:computedAt`, `:engineVersion` |
| Assessment | `:FundamentalAssessment` (class, `rdfs:subClassOf :Observation`), `:assessmentOfFiling`, `:assessmentOfAsset`, `:assessmentOfSnapshot`, `:snapshotId`, `:rating`, `:narrative`, `:strength`, `:risk`, `:model`, `:promptHash`, `:generatedByLanguageModel`, `:provenanceNote` | `:computedAt`, `:eventTime`, `:availableAt` |
| SHACL | `FundamentalFilingShape`, `FundamentalMetricSetShape`, `FundamentalAssessmentShape`, `FundamentalMetricDefinitionShape` | existing gate/shape machinery |
| Labels | `:FundamentalMetricScheme` + 31 `:FundamentalMetric_<name>` concepts in `labels.ttl`; bilingual `rdfs:label`/`rdfs:comment` on every new TBox term | `:PresentationScheme`, `:LabelConceptShape` |

`SECFiling` keeps its place under `SourceDocument`; the metric set and the assessment are
`Observation`s. `:availableAt` loses its `:ScoreSnapshot` domain; `:computedAt`/`:eventTime` are
widened to `:Observation`.

### 6.2 Manifest and strict parser

`SHA256SUMS` lists `README.md`, `filings.csv`, `metrics.csv`, `assessments.jsonl`, `source.json`
and `provenance/export_bloque_c.py`; all six must be present and match. The loader also prints the
manifest's own sha256 `f640ba4d…` and the `source.json` database hash for the run record. The
manifest is checked before the store is contacted.

Strict rules, all refused with a message naming the file/row/key:

- exact header and no unknown/missing columns in the two CSVs and the JSONL object;
- unique `filing_id`, `accession_number`, `metric_id`, `(filing_id, metric_name)`, `snapshot_id`;
- `filing_id` foreign keys in metrics/assessments; `asset_id`/`ticker` consistent with the filing;
- `form` in `10-K | 10-Q`; dates parse; `available_at` matches the filing; `computed_at` is a
  dateTime; `value` is a decimal or empty; `unit` in `ratio | x | usd` and matches the metric's
  declared unit; `metric_group` in the 10 groups; `metric_name` in the 38 names (or the selected
  subset); `engine_version` is `metrics-v10`;
- `generated_by_language_model` is a JSON boolean; `model`, `prompt_hash`, `rating` strings;
  `strengths`/`risks` are arrays of strings; `narrative` non-empty; the 129 false rows have the
  rule model and null score/rating; the 9,896 true rows have a score and rating;
- the default metric policy: `valuation` and `rule_input` rows are counted and skipped; if
  `--include-valuation-ratios` is set, only the three ratio names are added; the two absolute USD
  names are refused even with the flag;
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
  the 31/34 metric policy, the `:containsPriceDerivedValue false` count, the 9,896 snapshot links
  and the 129 rule rows; no engine graph receives a triple.

### 6.4 Counts and tests

The design's full-delivery expected count for C (31 metrics, all filings, including the
`:containsPriceDerivedValue` guard) is **815,620 asserted**; without the guard triple it is
**800,981**. The `--include-valuation-ratios` batch is 844,898 + 14,639 = **859,537 asserted**. The
implementation must measure the actual `D` and update every asserted count in the same PR (NR-001):
FR-001 and the `labels.ttl`/`tbox.ttl` schema counts, the load-plan/production counts if the schema
files change, the shape count (40 → 44 if the four new shapes are added), and the loader test's
fixture count. The full-delivery count is recorded in the runbook and the dry-run output, not in a
hermetic test; the hermetic test uses a small fixture and asserts its exact batch count and the
refusal cases.

The test file should cover: manifest mismatch/missing entry, unknown column/value, duplicate
`filing_id`/`metric_id`/`snapshot_id`, a metric row with a mismatched `available_at`, an unknown
metric/unit/group, a `usd` price-derived row refusal, the default vs flag counts, the 129 rule rows,
the 9,896 snapshot links, a missing snapshot, the exact fixture triple count, SHACL conformance, and
the `--check-store` no-write path.

### 6.5 Runbook and no DROP

Add a section to `docs/backtest-load-runbook.md` after the external Markowitz step, and a step 7c
to `docs/final-delivery.md` if the maintainer wants one command sequence: dry run → `--check-store`
→ `--write --to-production` → verify. The runbook records the measured counts, the manifest hash,
the `source.json` hash, the graph name and the one-graph rollback command. The loader and the agent
never run a DROP; only the maintainer may drop the one graph after a failed write, following
`docs/backtest-load-runbook.md` §9.

---

## 7. Questions for Reviewer A

1. **Existing snapshots.** Are the 10,025 `score_snapshot` FUNDAMENTAL rows already in `portfolio`
   (or in an `ingest:FUNDAMENTAL:*` graph)? If not, should the implementation load them first, or
   may the assessment loader create the missing snapshot? What is the authoritative join key:
   `snapshot_id` in the IRI, or `(asset, eventTime, availableAt, rawValue)`?
2. **Price mask.** Confirm the default excludes the whole `valuation` group (73,195 rows) and
   `rule_input` (18,391 rows), with `--include-valuation-ratios` adding only the three ratio
   metrics. Is excluding the three valuation ratios acceptable for the first agent version, or
   should they be on by default for non-masked assets? The two absolute USD metrics are never
   loaded.
3. **Metric subset.** Confirm the 31-metric default vs a narrower tier-1 set (17 metrics cited in
   ≥50% of assessments). The 31 set includes `nopat` (USD, 12,827 non-null, cited 49 times); keep
   or drop it? The 31 set covers all groups except valuation/rule_input.
4. **Filing scope.** Load all 14,639 filings (800,981 asserted) or the 10,025 assessed filings
   first (621,598 asserted, C-pilot)? The pilot drops 4,614 filings that have metrics but no
   assessment.
5. **Text clock.** For the generated narrative, should the agent filter on `availableAt` (filing
   date) or `computedAt` (2026-11-03)? The design recommends marking it generated and not treating
   it as a contemporaneous fact; a `:textAvailableAt = max(available_at, computed_at)` is the strict
   alternative.
6. **129 rule rows.** Keep their `prompt_hash` (present, same hash) or omit it? Confirm the exact
   `provenance_note` and that `score_raw_0_100`/`rating` stay null.
7. **Graph name.** Confirm `urn:graph:derived:fundamentals:{label}` and the append-only/no-DROP
   rule. Is `final` the only label for this delivery?
8. **Metric IDs.** Is the one `:metricIdsJson` map per filing enough, or must every `metric_id` be
   an individually addressable RDF resource? If the latter, the fallback is model A restricted to
   31 metrics and the assessed-only pilot.
9. **Text nodes.** Is storing narrative/strengths/risks as repeated literals on the assessment
   enough, or do you want separate `:AssessmentNarrative`/`:AssessmentPoint` nodes? The design
   recommends the repeated-literal form to keep the volume low; the boolean and note are on the
   same node.
10. **Labels.** Confirm the 31 metric concepts under a new `FundamentalMetricScheme` in
    `labels.ttl`, with `skos:notation` = the source `metric_name`, bilingual labels/comments and
    `metric_group`/`metric_unit`; and the TBox class/property labels in `tbox.ttl` (T-754 pattern).
11. **Shape count.** Four new shapes (`FundamentalFilingShape`, `FundamentalMetricSetShape`,
    `FundamentalAssessmentShape`, `FundamentalMetricDefinitionShape`) take the named shape count
    from 40 to 44; confirm the count update and the FR-001 rebaseline in the implementation PR.

---

## Appendix A — the 38 metrics and the assessment citations

The citation column is a case-insensitive alias count over `narrative` + `strengths` + `risks`
(e.g. `ROIC`, `return on invested capital`, `FCF margin`); it is an indicative count, not a
semantic parse. `load` = default 31, `flag` = only with `--include-valuation-ratios`, `never` =
not loaded.

| Metric | Group | Unit | Rows | Non-null | Assessments citing | Default |
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
| `free_cash_flow_yield` | valuation | ratio | 14,639 | 12,053 | 6,098 | flag |
| `revenue_growth` | growth | ratio | 14,612 | 14,585 | 5,246 | load |
| `debt_to_equity` | leverage | x | 14,639 | 11,955 | 4,999 | load |
| `quick_ratio` | liquidity | x | 14,639 | 11,136 | 3,638 | load |
| `debt_to_assets` | leverage | ratio | 14,639 | 12,874 | 3,455 | load |
| `net_income_growth` | growth | ratio | 14,612 | 13,192 | 3,025 | load |
| `operating_income_growth` | growth | ratio | 14,612 | 11,894 | 2,840 | load |
| `free_cash_flow_growth` | growth | ratio | 14,612 | 10,092 | 2,643 | load |
| `return_on_invested_capital_effective_rate` | roic | ratio | 14,639 | 10,462 | 2,499 | load |
| `asset_turnover` | efficiency | x | 14,639 | 14,145 | 2,458 | load |
| `sbc_adjusted_fcf_yield` | valuation | ratio | 14,639 | 10,712 | 2,341 | flag |
| `effective_tax_rate` | roic | ratio | 14,639 | 13,053 | 2,081 | load |
| `enterprise_fcf_yield` | valuation | ratio | 14,639 | 9,233 | 1,972 | flag |
| `receivables_turnover` | efficiency | x | 14,639 | 12,315 | 1,885 | load |
| `inventory_turnover` | efficiency | x | 14,639 | 6,979 | 1,069 | load |
| `net_income_cagr` | cagr | ratio | 3,771 | 3,157 | 1,013 | load |
| `revenue_cagr` | cagr | ratio | 3,771 | 3,708 | 986 | load |
| `operating_cash_flow_cagr` | cagr | ratio | 3,771 | 3,188 | 844 | load |
| `enterprise_value` | valuation | usd | 14,639 | 11,981 | 273 | never |
| `market_capitalization` | valuation | usd | 14,639 | 13,988 | 167 | never |
| `utility_cash_coverage_3y` | rule_input | ratio | 3,752 | 2,783 | 138 | never |
| `nopat` | roic | usd | 14,639 | 12,827 | 49 | load |
| `value_inputs` | rule_input | usd | 14,639 | 14,196 | 3 | never |

## Appendix B — reproducibility

All counts in this document were computed from the real files with standard-library Python
(`csv`, `json`, `re`, `hashlib`) and `sha256sum -c`; no GraphDB command was run. The manifest,
`source.json` and `provenance/export_bloque_c.py` were read-only. The full metric table, the group
table, the masked-asset counts and the model budgets are reproducible from the files in the delivery
folder; the implementation tests must use a hermetic fixture, not this folder.
