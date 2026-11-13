# Investor recipes for the TTYG agent

These are bounded, named SPARQL recipes for the twenty compound investor questions C1–C20 in
Reviewer A's catalogue (2026-11-14). The agent should run the smallest recipe that answers the
question instead of composing a long cross-layer query. The recipes use only the vocabulary that
exists in `schema/tbox.ttl`, `schema/shapes.ttl`, `schema/rules.ttl` and `schema/labels.ttl` on
master. No recipe adds a class or a property.

## How to read a recipe

- **Status** is one of *available now* (HOY), *needs the reload* (RECARGA), *partial* or *not
  answerable*.
- **Graphs** names the exact graphs the recipe reads. The query uses a `VALUES` row with the
  `final`/`P1`/`SYSTEM_WITH_HIERARCHY` example; change the label, window, configuration, slug,
  ticker and dates together in that row.
- **Columns** lists the output; **Read it as** explains the row; **Honest limits** states what the
  graph cannot prove.
- Every recipe has a `LIMIT`. The selection graphs hold roughly 322k triples per run, so every
  recipe enters them with a date, ticker or one-cycle filter, never with a whole-graph aggregate.
- No recipe reads an individual price, close, stop level, daily return or valuation metric. The 33
  Tiingo-masked assets keep their events and their non-valuation fundamentals; a recipe that can
  return one of them surfaces `?pricesNotPublished`.
- `MARKOWITZ_MV` is summary-only. No recipe uses it for composition; composition comparisons use
  `MARKOWITZ_BASE`.
- Generated analyst text is model output. When a recipe returns an assessment, it returns
  `?generatedByLanguageModel`; quote the sentence in the agent instructions when the value is true.

## Status summary

| Question | Status | Main reason |
|---|---|---|
| C1 | needs the reload | stop events and the final fundamentals graph |
| C2 | needs the reload | replacement events |
| C3 | partial | weighted quality works on the loaded books; the five final configurations need the reload |
| C4 | available now | selection vetoes + assessments |
| C5 | available now | selection vetoes + sector + assessments |
| C6 | needs the reload | C1 window, stops with destinations, masked banks |
| C7 | needs the reload | new L0 episodes and both System configurations |
| C8 | needs the reload | System with/without hierarchy summaries and paired tests |
| C9 | available now | weights, sectors and drawdowns of the loaded books |
| C10 | needs the reload | stop destinations and cash causes |
| C11 | needs the reload | stop menu, chosen destination and replacement |
| C12 | partial | profile now; holdings, stops, memory and rankings after the reload |
| C13 | available now | filings and assessments with `availableAt <= D` |
| C14 | needs the reload | retention decisions, holds and rejections |
| C15 | needs the reload | StopMemory episodes |
| C16 | needs the reload | `:chooser` and the stop menu |
| C17 | partial | composition now for loaded books; five final configurations after the reload |
| C18 | available now | holdings + latest non-valuation metrics + assessment |
| C19 | available now | assessment history, if the company has more than one assessment |
| C20 | available now | filing/assessment coverage and the Tiingo mask |

## C1. Were the companies the system stopped weak or strong when it sold them?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph
`urn:graph:derived:backtest:final:P1:system_with_hierarchy`, the fundamentals graph
`urn:graph:derived:fundamentals:final`, and `urn:graph:universe:2026-Q4` for tickers.

**Pregunta:** ¿Las acciones que el sistema vendió por una parada eran empresas débiles o sólidas
cuando las vendió?

<!-- recipe: C1 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?stopDate ?ticker ?roic ?debt ?score ?rating ?generatedByLanguageModel ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?stop a :StopEvent ; :stopOfBook ?book ; :stopDate ?stopDate ; :stoppedAsset ?asset .
    ?book :runLabel ?label ; :windowId ?window .
    FILTER (?stopDate <= ?asOf)
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?filing :filingOfAsset ?asset ; :availableAt ?available .
      FILTER (?available <= ?stopDate)
      ?metricSet :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?roic ; :debtToEquity ?debt .
      FILTER NOT EXISTS {
        ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
        ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterRoic .
        FILTER (?laterAvailable <= ?stopDate && ?laterAvailable > ?available)
      }
      FILTER NOT EXISTS {
        ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
        ?laterSet :metricSetOfFiling ?later ; :debtToEquity ?laterDebt .
        FILTER (?laterAvailable <= ?stopDate && ?laterAvailable > ?available)
      }
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?assessment :assessmentOfAsset ?asset ; :availableAt ?assessmentAvailable ;
                  :scoreRaw0to100 ?score ; :rating ?rating ;
                  :generatedByLanguageModel ?generatedByLanguageModel .
      FILTER (?assessmentAvailable <= ?stopDate)
      FILTER NOT EXISTS {
        ?laterAssessment :assessmentOfAsset ?asset ; :availableAt ?laterAssessmentAvailable .
        FILTER (?laterAssessmentAvailable <= ?stopDate && ?laterAssessmentAvailable > ?assessmentAvailable)
      }
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?stopDate ?ticker
LIMIT 200
```

**Columns:** stop date, ticker, ROIC, debt-to-equity, assessment score and rating, the generated-text
flag and the mask flag. **Read it as:** each row is one stop and the latest filing/assessment
available on that stop date. **Honest limits:** the graph does not say whether the company was a good
or bad investment after the sale; it only compares the fundamentals known at the stop. A name without
a filing or assessment is not weak, it is uncovered. The 33 masked names publish no valuation metric
and no price.

## C2. When it replaced a stopped holding, was the replacement a better company and in which sector?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph, fundamentals,
universe and reference.

**Pregunta:** Cuando vendió una acción y compró otra en su lugar, ¿la nueva era mejor empresa, del
mismo sector o de otro?

<!-- recipe: C2a -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?stopDate ?soldTicker ?replacementTicker ?orderDate ?executionDate
       ?soldSector ?replacementSector ?sameSector ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?purchase a :ReplacementPurchase ; :purchaseOfStop ?stop ; :replacementAsset ?newAsset ;
              :orderDate ?orderDate ; :replacementExecutionDate ?executionDate .
    ?stop a :StopEvent ; :stoppedAsset ?oldAsset ; :stopDate ?stopDate ; :stopOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe {
    ?oldAsset :tickerSymbol ?soldTicker ; :classifiedAs ?oldIndustry .
    ?newAsset :tickerSymbol ?replacementTicker ; :classifiedAs ?newIndustry .
  }
  GRAPH <urn:graph:reference> {
    ?oldIndustry :memberOfSector ?oldSector . ?oldSector skos:prefLabel ?soldSector .
    ?newIndustry :memberOfSector ?newSector . ?newSector skos:prefLabel ?replacementSector .
  }
  BIND (?oldSector = ?newSector AS ?sameSector)
  OPTIONAL { GRAPH ?fundGraph { ?oldAsset :pricesNotPublished ?oldMasked } }
  OPTIONAL { GRAPH ?fundGraph { ?newAsset :pricesNotPublished ?newMasked } }
  BIND (COALESCE(?oldMasked, false) || COALESCE(?newMasked, false) AS ?pricesNotPublished)
}
ORDER BY ?stopDate ?soldTicker
LIMIT 100
```

**Columns:** stop date, sold ticker, replacement ticker, order/execution dates, both GICS sectors,
whether they match and the mask flag. **Read it as:** the replacement is the asset the engine bought
with the freed weight; sector equality is a GICS comparison. **Honest limits:** a different sector is
not a better company, and a same-sector replacement is not a clone; use C2b to compare the metrics.
Masked names show the event but no valuation.

<!-- recipe: C2b -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?stopDate ?soldTicker ?replacementTicker
       ?soldRoic ?replacementRoic ?soldDebt ?replacementDebt
       ?soldScore ?replacementScore ?oldGeneratedByLanguageModel ?newGeneratedByLanguageModel
       ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?purchase a :ReplacementPurchase ; :purchaseOfStop ?stop ; :replacementAsset ?newAsset ;
              :orderDate ?orderDate .
    ?stop a :StopEvent ; :stoppedAsset ?oldAsset ; :stopDate ?stopDate ; :stopOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe {
    ?oldAsset :tickerSymbol ?soldTicker .
    ?newAsset :tickerSymbol ?replacementTicker .
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?oldFiling :filingOfAsset ?oldAsset ; :availableAt ?oldAvailable .
      FILTER (?oldAvailable <= ?orderDate)
      ?oldSet :metricSetOfFiling ?oldFiling ; :returnOnInvestedCapital ?soldRoic ; :debtToEquity ?soldDebt .
      FILTER NOT EXISTS {
        ?oldLater :filingOfAsset ?oldAsset ; :availableAt ?oldLaterAvailable .
        ?oldLaterSet :metricSetOfFiling ?oldLater ; :returnOnInvestedCapital ?oldLaterRoic .
        FILTER (?oldLaterAvailable <= ?orderDate && ?oldLaterAvailable > ?oldAvailable)
      }
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?newFiling :filingOfAsset ?newAsset ; :availableAt ?newAvailable .
      FILTER (?newAvailable <= ?orderDate)
      ?newSet :metricSetOfFiling ?newFiling ; :returnOnInvestedCapital ?replacementRoic ; :debtToEquity ?replacementDebt .
      FILTER NOT EXISTS {
        ?newLater :filingOfAsset ?newAsset ; :availableAt ?newLaterAvailable .
        ?newLaterSet :metricSetOfFiling ?newLater ; :returnOnInvestedCapital ?newLaterRoic .
        FILTER (?newLaterAvailable <= ?orderDate && ?newLaterAvailable > ?newAvailable)
      }
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?oldAssessment :assessmentOfAsset ?oldAsset ; :availableAt ?oldAssessmentAvailable ;
                     :scoreRaw0to100 ?soldScore ;
                     :generatedByLanguageModel ?oldGeneratedByLanguageModel .
      FILTER (?oldAssessmentAvailable <= ?orderDate)
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?newAssessment :assessmentOfAsset ?newAsset ; :availableAt ?newAssessmentAvailable ;
                     :scoreRaw0to100 ?replacementScore ;
                     :generatedByLanguageModel ?newGeneratedByLanguageModel .
      FILTER (?newAssessmentAvailable <= ?orderDate)
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?oldAsset :pricesNotPublished ?oldMasked } }
  OPTIONAL { GRAPH ?fundGraph { ?newAsset :pricesNotPublished ?newMasked } }
  BIND (COALESCE(?oldMasked, false) || COALESCE(?newMasked, false) AS ?pricesNotPublished)
}
ORDER BY ?stopDate ?soldTicker
LIMIT 100
```

**Columns:** the same stop/replacement pair with ROIC, debt-to-equity, assessment score and the
generated-text flag for each side, plus the mask flag. **Read it as:** compare the two metric sets known on the order date; a
missing value is not zero. **Honest limits:** a higher ROIC is not a forecast, the graph has no
valuation, and a masked side has no valuation metric at all.

## C3. What quality profile did the portfolio have at each decision, and how does it compare with minimum variance (MARKOWITZ_BASE)?

**Status:** partial. It works on the loaded books now; the five final configurations need the reload.
**Graphs:** the System and `MARKOWITZ_BASE` final book graphs, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Qué perfil de calidad tenía la cartera en cada decisión (rentabilidad y deuda
ponderadas por peso) y cómo se compara con la cartera de mínima varianza (MARKOWITZ_BASE)?

<!-- recipe: C3 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?configuration
       (SUM(?weight * ?roic) / SUM(?weight) AS ?weightedRoic)
       (SUM(?weight * ?debt) / SUM(?weight) AS ?weightedDebt)
       (SUM(?weight) AS ?coveredWeight)
       (COUNT(DISTINCT ?asset) AS ?positions)
WHERE {
  VALUES (?label ?window ?asOf ?configuration ?slug ?bookGraph ?fundGraph) {
    ("final" "P1" "2022-06-30"^^xsd:date "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>)
    ("final" "P1" "2022-06-30"^^xsd:date "MARKOWITZ_BASE" "markowitz_base"
     <urn:graph:derived:backtest:final:P1:markowitz_base>
     <urn:graph:derived:fundamentals:final>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?fundGraph {
    ?filing :filingOfAsset ?asset ; :availableAt ?available .
    FILTER (?available <= ?asOf)
    ?metricSet :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?roic ; :debtToEquity ?debt .
    FILTER NOT EXISTS {
      ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
      ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterRoic .
      FILTER (?laterAvailable <= ?asOf && ?laterAvailable > ?available)
    }
    FILTER NOT EXISTS {
      ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
      ?laterSet :metricSetOfFiling ?later ; :debtToEquity ?laterDebt .
      FILTER (?laterAvailable <= ?asOf && ?laterAvailable > ?available)
    }
  }
}
GROUP BY ?configuration
ORDER BY ?configuration
LIMIT 10
```

**Columns:** configuration, weight-weighted ROIC and debt, the weight covered by names with both
metrics and the number of covered positions. **Read it as:** the denominator is the covered weight,
not the whole book; compare the two rows only when `coveredWeight` is similar. **Honest limits:**
names without both metrics are excluded, `MARKOWITZ_MV` is summary-only and cannot be compared for
composition, and the weights exist only on decision/execution dates. A masked name contributes
only its non-valuation metrics; no valuation metric is read.

## C4. Does the fundamental analyst agree with the system's vetoes?

**Status:** available now (HOY). **Graphs:** the selection graph
`urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy`,
`urn:graph:rules:catalog`, `urn:graph:derived:fundamentals:final`, `urn:graph:universe:2026-Q4`.

**Pregunta:** ¿Está de acuerdo el analista fundamental con los vetos del sistema?

### C4a. Vetoed companies with a high assessment

<!-- recipe: C4a -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?ruleId ?score ?rating ?generatedByLanguageModel ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?minScore
          ?selectionGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date 70
     <urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?selectionGraph {
    ?veto a :Veto ; :vetoOfAsset ?asset ; :appliesRule ?rule ; :raisedOn ?raised .
    OPTIONAL { ?veto :clearedOn ?cleared }
  }
  FILTER (STR(?raised) <= STR(?asOf))
  FILTER (!BOUND(?cleared) || STR(?cleared) > STR(?asOf))
  GRAPH <urn:graph:rules:catalog> { ?rule :ruleId ?ruleId }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?fundGraph {
    ?assessment :assessmentOfAsset ?asset ; :availableAt ?available ;
                :scoreRaw0to100 ?score ; :rating ?rating ;
                :generatedByLanguageModel ?generatedByLanguageModel .
  }
  FILTER (STR(?available) <= STR(?asOf))
  FILTER NOT EXISTS {
    GRAPH ?fundGraph {
      ?later :assessmentOfAsset ?asset ; :availableAt ?laterAvailable .
    }
    FILTER (STR(?laterAvailable) <= STR(?asOf) && STR(?laterAvailable) > STR(?available))
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
  FILTER (?score >= ?minScore)
}
ORDER BY DESC(?score) ?ticker
LIMIT 50
```

**Columns:** ticker, rule, assessment score/rating, generated flag, mask flag. **Read it as:** these
are selection veto stints in force on the date whose latest assessment is high. **Honest limits:** a
high assessment is a second opinion, not proof that the veto was wrong; the assessment may be generated
text and is labelled as such. A masked name keeps its assessment but no price or valuation.

### C4b. Selected companies with a low assessment

<!-- recipe: C4b -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?score ?rating ?generatedByLanguageModel ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?maxScore
          ?selectionGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date 40
     <urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?selectionGraph {
    ?snapshot a :AttractivenessSnapshot ; :runLabel ?label ; :windowId ?window ;
              :rankingOfCycle ?cycle ; :attractivenessOfAsset ?asset ;
              :rankingTicker ?ticker ; :selectedForBook true .
    ?cycle :runAsOf ?asOf .
  }
  GRAPH ?fundGraph {
    ?assessment :assessmentOfAsset ?asset ; :availableAt ?available ;
                :scoreRaw0to100 ?score ; :rating ?rating ;
                :generatedByLanguageModel ?generatedByLanguageModel .
  }
  FILTER (STR(?available) <= STR(?asOf))
  FILTER NOT EXISTS {
    GRAPH ?fundGraph {
      ?later :assessmentOfAsset ?asset ; :availableAt ?laterAvailable .
    }
    FILTER (STR(?laterAvailable) <= STR(?asOf) && STR(?laterAvailable) > STR(?available))
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
  FILTER (?score < ?maxScore)
}
ORDER BY ?score ?ticker
LIMIT 50
```

**Columns:** ticker, score, rating, generated flag, mask flag. **Read it as:** these are names in the
selected candidate pool with a low assessment on the decision date. **Honest limits:** `selectedForBook`
is the candidate pool, not a holding; a low assessment does not say the name underperformed.

## C5. Which sectors concentrated the vetoes, and were they also the weakest?

**Status:** available now (HOY). **Graphs:** the selection graph, `urn:graph:rules:catalog`,
`urn:graph:universe:2026-Q4`, `urn:graph:reference`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Qué sectores concentraron los vetos en cada ventana y eran también los de peor
calidad fundamental?

<!-- recipe: C5 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?sectorLabel ?ruleId
       (COUNT(DISTINCT ?veto) AS ?vetoes)
       (AVG(?score) AS ?averageAssessment)
       (SUM(IF(COALESCE(?generated, false), 1, 0)) AS ?generatedAssessments)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?from ?to
          ?selectionGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     "2022-01-03"^^xsd:date "2022-10-12"^^xsd:date
     <urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?selectionGraph {
    ?veto a :Veto ; :vetoOfAsset ?asset ; :appliesRule ?rule ; :raisedOn ?raised .
    FILTER (?raised >= ?from && ?raised <= ?to)
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :ruleId ?ruleId }
  GRAPH ?universe { ?asset :classifiedAs ?industry }
  GRAPH <urn:graph:reference> {
    ?industry :memberOfSector ?sector .
    ?sector skos:prefLabel ?sectorLabel .
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?assessment :assessmentOfAsset ?asset ; :availableAt ?available ;
                  :scoreRaw0to100 ?score ;
                  :generatedByLanguageModel ?generated .
      FILTER (?available <= ?to)
      FILTER NOT EXISTS {
        ?later :assessmentOfAsset ?asset ; :availableAt ?laterAvailable .
        FILTER (?laterAvailable <= ?to && ?laterAvailable > ?available)
      }
    }
  }
}
GROUP BY ?sectorLabel ?ruleId
ORDER BY DESC(?vetoes) ?sectorLabel ?ruleId
LIMIT 50
```

**Columns:** GICS sector, rule, distinct veto stints, average assessment and the count of generated
assessments. **Read it as:** a sector with many vetoes and a low average score is a concentration
signal; the count of generated assessments says how much of the average is model text. **Honest
limits:** vetoes without a resolved asset are omitted, and a low average is not proof that the
sector was the worst in the market. Masked names contribute only their assessment; no valuation is
read.

## C6. How did the system react to the 2022–2023 banking stress?

**Status:** needs the reload (RECARGA, C1 window). **Graphs:** the C1 System book graph,
`urn:graph:derived:backtest:final:C1:system_with_hierarchy`, `urn:graph:universe:2026-Q4`,
`urn:graph:reference`, `urn:graph:rules:catalog`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Cómo reaccionó el sistema al estrés bancario de 2022–2023? ¿Tenía bancos, los sacó,
cuánto bajó su exposición y qué compró?

### C6a. Bank exposure by decision date

<!-- recipe: C6a -->
```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?date ?exposureScale
       (SUM(?weight) AS ?bankWeight)
       (COUNT(DISTINCT ?asset) AS ?bankNames)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?universe) {
    ("final" "C1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:C1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?book a :StrategyBook ; :runLabel ?label ; :windowId ?window .
    ?decision a :DecisionEvent ; :decisionOfBook ?book ; :decisionDate ?date ;
              :exposureScale ?exposureScale .
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?date ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
  }
  VALUES ?industryLabel { "Banks" }
  GRAPH ?universe { ?asset :classifiedAs ?industry }
  GRAPH <urn:graph:reference> { ?industry skos:prefLabel ?industryLabel }
}
GROUP BY ?date ?exposureScale
ORDER BY ?date
LIMIT 100
```

**Columns:** decision date, exposure scale and the summed bank weight and names. **Read it as:** the
scale is the layer-0 exposure multiplier (`1` means no cut); the bank weight is the sum of the held
banks on that date. **Honest limits:** the recipe shows the system's reaction, not the cause of the
banking stress; FRC and SBNY are masked, so their events are visible but their prices never are.
Masked banks contribute their weight; no price or valuation is read.

### C6b. Bank stops, destinations and replacements

<!-- recipe: C6b -->
```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?date ?ticker ?cashCause ?chooser ?destination ?pricesNotPublished ?replacementTicker
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "C1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:C1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?stop a :StopEvent ; :stopOfBook ?book ; :stopDate ?date ; :stoppedAsset ?asset .
    ?book :runLabel ?label ; :windowId ?window .
    OPTIONAL { ?stop :stopCashCause ?cashCause }
    OPTIONAL { ?stop :chooser ?chooser }
    OPTIONAL { ?stop :chosenCash ?chosenCash }
    OPTIONAL { ?stop :chosenOption ?chosen . ?chosen :optionAsset ?chosenAsset ; :optionIsSpy ?isSpy . }
    OPTIONAL { ?purchase :purchaseOfStop ?stop ; :replacementAsset ?replacement . }
  }
  VALUES ?industryLabel { "Banks" }
  GRAPH <urn:graph:reference> { ?industry skos:prefLabel ?industryLabel }
  GRAPH ?universe {
    ?asset :classifiedAs ?industry ; :tickerSymbol ?ticker .
    OPTIONAL { ?replacement :tickerSymbol ?replacementTicker }
    OPTIONAL { ?chosenAsset :tickerSymbol ?chosenTicker }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
  BIND (IF(COALESCE(?chosenCash, false), "cash",
        IF(COALESCE(?isSpy, false), "SPY", COALESCE(?chosenTicker, "no destination")))
       AS ?destination)
}
ORDER BY ?date ?ticker
LIMIT 100
```

**Columns:** stop date, bank ticker, cash cause, chooser, chosen destination, mask flag and replacement
ticker. **Read it as:** each row is one bank stop; `chooser` says whether the rule or the agent chose
the destination. **Honest limits:** a stop is not a market forecast; the graph does not say why the
bank failed. Masked banks have events but no prices or valuation.

## C7. What happened in each portfolio tail-risk episode?

**Status:** needs the reload (RECARGA). **Graphs:** the System with/without hierarchy book graphs and
`urn:graph:rules:catalog`.

**Pregunta:** En cada episodio de riesgo de cola de la cartera: ¿cuándo se activó, cuánto bajó la
exposición, cuándo volvió, y cómo le fue al valor de la cartera frente a la versión sin jerarquía
durante el episodio?

### C7a. Layer-0 episodes

<!-- recipe: C7a -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?date ?ruleId ?status ?weightBefore ?weightAfter ?exposureScale ?cashWeight
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?alert a :GuardAlert ; :alertRule ?rule ; :alertDate ?date ;
           :alertHasGuardAction ?action .
    ?action :actionOfBook ?book ; :status ?status ; :effectiveDate ?effective .
    ?book :runLabel ?label ; :windowId ?window .
    FILTER (?status = "APPLIED")
    OPTIONAL { ?action :weightBefore ?weightBefore ; :weightAfter ?weightAfter }
    OPTIONAL {
      ?perf a :BookDailyPerformance ; :performanceOfBook ?book ;
            :performanceDate ?effective ; :cashWeight ?cashWeight .
    }
  }
  GRAPH <urn:graph:rules:catalog> {
    ?rule :ruleId ?ruleId ; :guardLayer 0 .
  }
}
ORDER BY ?date ?ruleId
LIMIT 100
```

**Columns:** date, L0 rule, action status, weights before/after, effective exposure scale and cash
weight. **Read it as:** L0 alerts are daily; count actions or state changes, not alerts. **Honest
limits:** the episode is a rule activation, not a market diagnosis; the graph has no daily NAV series
for an individual stock.

### C7b. NAV during the same episode, with and without hierarchy

<!-- recipe: C7b -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?date ?navWith ?navWithout (?navWith / ?navWithout AS ?navRatio)
WHERE {
  VALUES (?label ?window ?from ?to ?withGraph ?withoutGraph) {
    ("final" "P1" "2022-01-03"^^xsd:date "2022-10-12"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:backtest:final:P1:system_without_hierarchy>)
  }
  GRAPH ?withGraph {
    ?perfWith a :BookDailyPerformance ; :performanceOfBook ?bookWith ;
              :performanceDate ?date ; :nav ?navWith .
    ?bookWith :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?withoutGraph {
    ?perfWithout a :BookDailyPerformance ; :performanceOfBook ?bookWithout ;
                 :performanceDate ?date ; :nav ?navWithout .
    ?bookWithout :runLabel ?label ; :windowId ?window .
  }
  FILTER (?date >= ?from && ?date <= ?to)
}
ORDER BY ?date
LIMIT 300
```

**Columns:** date, NAV of each configuration and their ratio. **Read it as:** a ratio above 1 means the
hierarchy book was worth more that day; this is a portfolio aggregate, not a stock return. **Honest
limits:** the window has one episode and no counterfactual outside it; the graph does not say the
hierarchy caused the difference.

## C8. Is the Veto Hierarchy worth it: with versus without hierarchy?

**Status:** needs the reload (RECARGA). **Graphs:** the System with/without hierarchy book graphs and
`urn:graph:rules:catalog` (not needed for the summaries).

**Pregunta:** ¿Vale la pena la Jerarquía de Veto? Con jerarquía contra sin jerarquía: retorno, caída
máxima, Sharpe, número de paradas y si la diferencia es estadísticamente real.

### C8a. Performance summary

<!-- recipe: C8a -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?configuration ?arm ?cumulativeReturn ?annualizedReturn ?exPostSharpe
       ?maxDrawdown ?nGuardActions
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
    ("final" "P1" "SYSTEM_WITHOUT_HIERARCHY" "system_without_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_without_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?summary a :PortfolioPeriodSummary ; :summaryOfBook ?book ;
             :windowId ?window ; :armCode ?arm ;
             :cumulativeReturn ?cumulativeReturn ;
             :annualizedReturn ?annualizedReturn ;
             :exPostSharpe ?exPostSharpe ;
             :maxDrawdown ?maxDrawdown ;
             :nGuardActions ?nGuardActions .
    ?book :runLabel ?label .
  }
}
ORDER BY ?configuration ?arm
LIMIT 20
```

**Columns:** configuration, arm, cumulative/annualized return, Sharpe, max drawdown and GUARD actions.
**Read it as:** compare the two configurations in the same window; the numbers are in-sample. **Honest
limits:** a higher return is not statistical significance; use C8b for the paired tests.

### C8b. Paired tests

<!-- recipe: C8b -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?testName ?armA ?armB ?windowId ?statistic ?pValue ?nObs
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?test a :BacktestTest ; :windowId ?windowId ; :armA ?armA ; :armB ?armB ;
          :testName ?testName ; :statistic ?statistic ; :pValue ?pValue ; :nObs ?nObs .
    FILTER (?windowId = ?window)
  }
}
ORDER BY ?testName ?armA ?armB
LIMIT 50
```

**Columns:** test name, arms, window, statistic, p-value and observations. **Read it as:** the four
tests are `memmel_jk`, `ledoit_wolf`, `hac_mean_diff` and `bootstrap_mdd`; a p-value is evidence, not
a guarantee. **Honest limits:** the tests are within-sample and their power is limited by the number
of windows.

## C9. How concentrated was the portfolio, and did concentration precede the worst drawdowns?

**Status:** available now (HOY) for the measured concentration and drawdowns; the causal part is not
answerable. **Graphs:** the System final book graph, `urn:graph:universe:2026-Q4`,
`urn:graph:reference`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Qué tan concentrada estaba la cartera (diez mayores pesos, sector más grande, número
efectivo de acciones) y esa concentración precedió a sus peores caídas?

### C9a. Ten largest weights

<!-- recipe: C9a -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?weight ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY DESC(?weight) ?ticker
LIMIT 10
```

**Columns:** ticker, weight, mask flag. **Read it as:** the ten largest final target weights on the
date. **Honest limits:** the weights exist only on decision/execution dates; a masked name has no
price or valuation.

### C9b. Effective number of positions

<!-- recipe: C9b -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?asset) AS ?positions)
       (SUM(?weight * ?weight) AS ?hhi)
       (1.0 / SUM(?weight * ?weight) AS ?effectivePositions)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
}
LIMIT 1
```

**Columns:** positions, Herfindahl index and its reciprocal. **Read it as:** `effectivePositions` is
the number of equally weighted names with the same concentration; it is not a count of holdings.
**Honest limits:** the measure includes only equity rows with `:holdingAsset`; CASH and an unlinked
holding are excluded. A masked name contributes its weight; no price or valuation is read.

### C9c. Largest sector

<!-- recipe: C9c -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?bucket (SUM(?weight) AS ?sectorWeight)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?bookGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  OPTIONAL { GRAPH ?universe { ?asset :classifiedAs ?industry } }
  OPTIONAL {
    GRAPH <urn:graph:reference> {
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
    }
  }
  BIND (COALESCE(?sectorLabel, "unclassified") AS ?bucket)
}
GROUP BY ?bucket
ORDER BY DESC(?sectorWeight)
LIMIT 5
```

**Columns:** bucket and weight. **Read it as:** the largest GICS sector, with an `unclassified`
bucket for names with no sector; SPY is an ETF and is not a sector. **Honest limits:** the bucket is
not a risk model and the graph has no live portfolio. A masked name contributes its weight; no
price or valuation is read.

### C9d. Worst drawdowns in the window

**Status:** the concentration and drawdown series are available now; the causal wording ("preceded")
is not answerable.

<!-- recipe: C9d -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?date ?drawdown
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?perf a :BookDailyPerformance ; :performanceOfBook ?book ;
          :performanceDate ?date ; :drawdown ?drawdown .
    ?book :runLabel ?label ; :windowId ?window .
  }
}
ORDER BY DESC(ABS(?drawdown))
LIMIT 10
```

**Columns:** date and drawdown. **Read it as:** the largest absolute drawdown rows first; check the
sign convention in the data. **Honest limits:** this does not show that concentration caused the
drawdown; the graph has no counterfactual and no market narrative.

## C10. Where did the stops end, and why cash?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph.

**Pregunta:** De las paradas, ¿qué proporción terminó en efectivo, por qué (filtro de tendencia
apagado, sin destino permitido, escala menor que 1) y cómo cambia entre ventanas?

<!-- recipe: C10 -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?cause (COUNT(?stop) AS ?stops) (SUM(?cashFlag) AS ?cashStops)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?bookGraph {
    ?stop a :StopEvent ; :stopOfBook ?book ; :stopCashCause ?cause .
    OPTIONAL { ?stop :chosenCash ?chosenCash }
    BIND (IF(COALESCE(?chosenCash, false), 1, 0) AS ?cashFlag)
    ?book :runLabel ?label ; :windowId ?window .
  }
}
GROUP BY ?window ?cause
ORDER BY ?window DESC(?stops)
LIMIT 50
```

**Columns:** window, cash cause, stops and cash stops. **Read it as:** `FILTER_OFF`,
`SCALE_BELOW_ONE`, `NO_SIGNAL` and `NO_ALLOWED_DESTINATION` are the four causes; the system does not
buy in a bearish filter. **Honest limits:** a stop that ended in cash is not a market call, and the
cause is the engine's rule, not a prediction. Masked stops are counted as events; no price is read.

## C11. Tell one decision end to end

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph,
`urn:graph:rules:catalog`, `urn:graph:universe:2026-Q4`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** Cuéntame de principio a fin una decisión del sistema: una parada con la empresa, su
regla, el menú de destinos, lo que eligió, el reemplazo y qué pasó en la decisión siguiente.

### C11a. The stop and its menu

<!-- recipe: C11a -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?stopDate ?stoppedTicker ?ruleId ?chooser
       ?menuPosition ?optionTicker ?optionIsSpy ?chosenCash ?chosen ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?universe ?rulesGraph ?fundGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>
     <urn:graph:rules:catalog>
     <urn:graph:derived:fundamentals:final>)
  }
  GRAPH ?bookGraph {
    ?stop a :StopEvent ; :stopOfBook ?book ; :stopDate ?stopDate ; :stoppedAsset ?asset .
    ?book :runLabel ?label ; :windowId ?window .
    OPTIONAL { ?stop :chooser ?chooser }
    OPTIONAL { ?stop :chosenCash ?chosenCash }
    ?alert a :GuardAlert ; :alertDate ?stopDate ; :guardAsset ?asset ; :alertRule ?rule .
    ?option :optionOfStop ?stop ; :menuPosition ?menuPosition .
    OPTIONAL { ?option :optionAsset ?optionAsset }
    OPTIONAL { ?option :optionIsSpy ?optionIsSpy }
    OPTIONAL { ?stop :chosenOption ?chosenOption . ?chosenOption :optionAsset ?chosenAsset }
    BIND (BOUND(?chosenAsset) && BOUND(?optionAsset) && ?chosenAsset = ?optionAsset AS ?chosen)
  }
  GRAPH ?rulesGraph { ?rule :ruleId ?ruleId }
  GRAPH ?universe {
    ?asset :tickerSymbol ?stoppedTicker .
    OPTIONAL { ?optionAsset :tickerSymbol ?optionTicker }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
  FILTER (?ruleId = "L1_BP_STOP")
}
ORDER BY ?stopDate ?stoppedTicker ?menuPosition
LIMIT 100
```

**Columns:** stop date, stopped ticker, rule, chooser, menu position, option ticker/SPY, cash chosen
and whether the option was chosen. **Read it as:** the menu is the bounded set of allowed
destinations; the chosen option is one row. **Honest limits:** a destination is not an order history;
the graph does not say what the market did next.

### C11b. The replacement and the next check

<!-- recipe: C11b -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?stopDate ?soldTicker ?replacementTicker ?orderDate ?executionDate
       ?replacementWeight ?replacementRank ?checkDate ?candidate ?kept ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?universe ?fundGraph) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>
     <urn:graph:derived:fundamentals:final>)
  }
  GRAPH ?bookGraph {
    ?purchase a :ReplacementPurchase ; :purchaseOfStop ?stop ; :replacementAsset ?replacement ;
              :orderDate ?orderDate ; :replacementExecutionDate ?executionDate .
    ?stop a :StopEvent ; :stoppedAsset ?sold ; :stopDate ?stopDate ; :stopOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    OPTIONAL { ?purchase :replacementWeight ?replacementWeight ; :replacementRank ?replacementRank }
    OPTIONAL { ?check :checkOfPurchase ?purchase ; :checkDate ?checkDate ;
                      :candidate ?candidate ; :kept ?kept }
  }
  GRAPH ?universe {
    ?sold :tickerSymbol ?soldTicker .
    ?replacement :tickerSymbol ?replacementTicker .
  }
  OPTIONAL { GRAPH ?fundGraph { ?sold :pricesNotPublished ?soldMasked } }
  OPTIONAL { GRAPH ?fundGraph { ?replacement :pricesNotPublished ?newMasked } }
  BIND (COALESCE(?soldMasked, false) || COALESCE(?newMasked, false) AS ?pricesNotPublished)
}
ORDER BY ?stopDate ?soldTicker
LIMIT 100
```

**Columns:** stop, sold/replacement tickers, order/execution dates, replacement weight/rank and the
next check. **Read it as:** the check is the next decision's candidate/kept outcome. **Honest
limits:** a replacement purchase is a weight event, not proof of a profitable trade; the graph has no
per-asset return.

## C12. Company card for X

**Status:** partial. The profile works now; holdings, stops, memory and rankings need the reload.
**Graphs:** `urn:graph:universe:2026-Q4`, `urn:graph:reference`,
`urn:graph:derived:fundamentals:final`, the System final book and selection graphs.

**Pregunta:** Dame la ficha de la empresa X: sector, fundamentales con fecha, evaluación, veces que
estuvo en el ranking y en qué puesto, vetos, si el sistema la tuvo, si la detuvo y cuándo volvió.

### C12a. Profile and latest fundamentals

<!-- recipe: C12a -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?companyName ?sectorLabel ?roic ?debt ?score ?rating
       ?generatedByLanguageModel ?pricesNotPublished
WHERE {
  VALUES (?ticker ?label ?asOf ?fundGraph ?universe) {
    ("AAA" "final" "2022-06-30"^^xsd:date
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?universe {
    ?asset :tickerSymbol ?ticker .
    OPTIONAL { ?asset :companyName ?companyName }
    OPTIONAL { ?asset :classifiedAs ?industry }
  }
  OPTIONAL {
    GRAPH <urn:graph:reference> {
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?filing :filingOfAsset ?asset ; :availableAt ?available .
      FILTER (?available <= ?asOf)
      ?metricSet :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?roic ; :debtToEquity ?debt .
      FILTER NOT EXISTS {
        ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
        ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterRoic .
        FILTER (?laterAvailable <= ?asOf && ?laterAvailable > ?available)
      }
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?assessment :assessmentOfAsset ?asset ; :availableAt ?assessmentAvailable ;
                  :scoreRaw0to100 ?score ; :rating ?rating ;
                  :generatedByLanguageModel ?generatedByLanguageModel .
      FILTER (?assessmentAvailable <= ?asOf)
      FILTER NOT EXISTS {
        ?laterAssessment :assessmentOfAsset ?asset ; :availableAt ?laterAssessmentAvailable .
        FILTER (?laterAssessmentAvailable <= ?asOf && ?laterAssessmentAvailable > ?assessmentAvailable)
      }
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?ticker
LIMIT 10
```

**Columns:** ticker, name, sector, ROIC, debt, assessment, generated flag and mask flag. **Read it
as:** the latest data available on the as-of date, not the latest filing in the store. **Honest
limits:** a missing metric is not zero; masked names have no valuation; generated text is labelled.

### C12b. Holdings, stops and memory

<!-- recipe: C12b -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?event ?date ?weight ?cause ?destination ?pricesNotPublished
WHERE {
  VALUES (?ticker ?label ?window ?configuration ?slug ?bookGraph ?universe ?fundGraph) {
    ("AAA" "final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>
     <urn:graph:derived:fundamentals:final>)
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?bookGraph {
    {
      ?weightRow a :BookWeightDaily ; :holdingAsset ?asset ; :weightDate ?date ;
                 :finalTargetWeight ?weight ; :weightOfBook ?book .
      ?book :runLabel ?label ; :windowId ?window .
      BIND ("holding" AS ?event)
      BIND ("" AS ?cause)
      BIND ("" AS ?destination)
    }
    UNION
    {
      ?stop a :StopEvent ; :stoppedAsset ?asset ; :stopDate ?date ; :stopOfBook ?book .
      ?book :runLabel ?label ; :windowId ?window .
      BIND ("stop" AS ?event)
      BIND ("" AS ?weight)
      OPTIONAL { ?stop :stopCashCause ?cause }
      OPTIONAL { ?stop :chosenCash ?chosenCash }
      OPTIONAL { ?stop :chosenOption ?chosen . ?chosen :optionAsset ?chosenAsset }
      BIND (IF(COALESCE(?chosenCash, false), "cash", COALESCE(?cause, "asset")) AS ?destination)
    }
    UNION
    {
      ?memory a :StopMemory ; :memoryAsset ?asset ; :memorySince ?date ; :memoryOfBook ?book .
      ?book :runLabel ?label ; :windowId ?window .
      BIND ("memory" AS ?event)
      BIND ("" AS ?weight)
      BIND ("" AS ?destination)
      OPTIONAL { ?memory :memoryReleaseCause ?cause }
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?date ?event
LIMIT 200
```

**Columns:** event kind, date, weight, cash cause and destination. **Read it as:** the rows combine
holdings, stops and memory episodes for the company; memory is one node per episode. **Honest
limits:** a missing weight on a non-decision date is not a zero holding; the graph does not publish
daily weights.

### C12c. Ranking appearances

<!-- recipe: C12c -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?date ?window ?rank ?score ?selected ?vetoed ?rules ?pricesNotPublished
WHERE {
  VALUES (?ticker ?label ?window ?configuration ?slug ?selectionGraph ?fundGraph ?universe) {
    ("AAA" "final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?selectionGraph {
    ?snapshot a :AttractivenessSnapshot ; :runLabel ?label ; :windowId ?window ;
              :rankingTicker ?ticker ; :rankingOfCycle ?cycle ;
              :rankPosition ?rank ; :attractivenessScore ?score ;
              :selectedForBook ?selected ; :vetoedAtRanking ?vetoed .
    ?cycle :runAsOf ?date .
    OPTIONAL { ?snapshot :vetoRulesJson ?rules }
    OPTIONAL { ?snapshot :attractivenessOfAsset ?asset }
  }
  OPTIONAL { GRAPH ?universe { ?asset :tickerSymbol ?ticker } }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?date ?rank
LIMIT 100
```

**Columns:** date, window, rank, score, selected, vetoed and the veto marker. **Read it as:**
`:selectedForBook` is the candidate pool, not a holding; rank includes vetoed names. **Honest
limits:** `vetoRulesJson` keeps only `"HARD"` for hard vetoes; use C4/C5 to resolve the rule.

### C12d. Veto stints for X

<!-- recipe: C12d -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?raised ?cleared ?ruleId ?severity
WHERE {
  VALUES (?ticker ?label ?window ?configuration ?slug
          ?selectionGraph ?rulesGraph ?universe) {
    ("AAA" "final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy>
     <urn:graph:rules:catalog>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?selectionGraph {
    ?veto a :Veto ; :vetoOfAsset ?asset ; :appliesRule ?rule ;
          :raisedOn ?raised ; :vetoSeverity ?severity .
    OPTIONAL { ?veto :clearedOn ?cleared }
  }
  GRAPH ?rulesGraph { ?rule :ruleId ?ruleId }
}
ORDER BY ?raised
LIMIT 40
```

**Columns:** raised/cleared dates, rule and severity. **Read it as:** a veto stint is in force from
`raisedOn` until `clearedOn`; an absent `clearedOn` means it was still in force at the run's
knowledge date. **Honest limits:** the graph has no reason beyond the rule and severity; a veto is
not a market forecast.

## C13. What did the system know about X on date D?

**Status:** available now (HOY). **Graphs:** `urn:graph:universe:2026-Q4`,
`urn:graph:derived:fundamentals:final`.

**Pregunta:** En la fecha D, ¿qué sabía el sistema de la empresa X?

<!-- recipe: C13 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?formType ?periodEnd ?availableAt ?roic ?debt ?score ?rating
       ?generatedByLanguageModel ?pricesNotPublished
WHERE {
  VALUES (?ticker ?asOf ?fundGraph ?universe) {
    ("AAA" "2022-06-30"^^xsd:date
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?fundGraph {
    ?filing :filingOfAsset ?asset ; :availableAt ?availableAt ;
            :periodEnd ?periodEnd ; :formType ?formType .
    OPTIONAL {
      ?metricSet :metricSetOfFiling ?filing ;
                 :returnOnInvestedCapital ?roic ; :debtToEquity ?debt .
    }
    OPTIONAL {
      ?assessment :assessmentOfFiling ?filing ; :availableAt ?assessmentAvailable ;
                  :scoreRaw0to100 ?score ; :rating ?rating ;
                  :generatedByLanguageModel ?generatedByLanguageModel .
    }
  }
  FILTER (STR(?availableAt) <= STR(?asOf))
  FILTER (!BOUND(?assessmentAvailable) || STR(?assessmentAvailable) <= STR(?asOf))
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY DESC(?availableAt)
LIMIT 20
```

**Columns:** form, period end, availability date, ROIC, debt, score/rating, generated flag and mask
flag. **Read it as:** a filing is knowable only when `:availableAt <= D`; `:periodEnd` is the period
it describes, not the date it became known. **Honest limits:** this is the point-in-time record; it
does not say the market had digested it. Masked names have no valuation.

## C14. Did the system retain names that were no longer top-ranked?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph,
`urn:graph:universe:2026-Q4`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Mantuvo acciones que ya no estaban entre las mejores (retención)? ¿Cuántas veces, por
cuántas decisiones seguidas, y terminaron detenidas?

<!-- recipe: C14 -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?decisionDate ?ticker ?outcome ?retentionCounter ?rejectionCause
       ?laterStopDate ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?decision a :RetentionDecision ; :retentionOfBook ?book ; :retentionDate ?decisionDate .
    ?book :runLabel ?label ; :windowId ?window .
    {
      ?hold a :RetentionHold ; :holdOfDecision ?decision ; :retainedAsset ?asset ;
            :retentionCounter ?retentionCounter .
      BIND ("retained" AS ?outcome)
      BIND ("" AS ?rejectionCause)
    }
    UNION
    {
      ?reject a :RetentionRejection ; :rejectionOfDecision ?decision ; :rejectedAsset ?asset ;
              :retentionCounter ?retentionCounter ; :rejectionCause ?rejectionCause .
      BIND ("rejected" AS ?outcome)
    }
    OPTIONAL {
      ?stop a :StopEvent ; :stoppedAsset ?asset ; :stopDate ?laterStopDate .
      FILTER (?laterStopDate > ?decisionDate)
    }
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?decisionDate ?ticker
LIMIT 200
```

**Columns:** decision date, ticker, retained/rejected, retention counter, rejection cause, next stop
date and mask flag. **Read it as:** retained counters run 1..3 and rejection counters 0..3; the counter
is the number of decisions in which the name was a candidate only by retention, **not** a count of
consecutive calendar decisions. A rejection counter of 3 with cause `counter` is the limit. **Honest
limits:** a later stop does not prove retention failed; the graph has no per-asset return.

## C15. How long does a stopped stock take to return, and is it stopped again?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph,
`urn:graph:universe:2026-Q4`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿Cuánto tarda en volver una acción detenida, y las que vuelven, vuelven a ser detenidas?

<!-- recipe: C15 -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?ticker ?startKind ?since ?released ?releaseCause ?nextStopDate ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?memory a :StopMemory ; :memoryOfBook ?book ; :memoryAsset ?asset ;
            :memorySince ?since ; :memoryStartKind ?startKind .
    ?book :runLabel ?label ; :windowId ?window .
    OPTIONAL { ?memory :memoryReleasedOn ?released ; :memoryReleaseCause ?releaseCause }
    OPTIONAL {
      ?laterStop a :StopEvent ; :stoppedAsset ?asset ; :stopDate ?nextStopDate .
      FILTER (!BOUND(?released) || ?nextStopDate > ?released)
    }
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?since ?ticker
LIMIT 100
```

**Columns:** ticker, start kind (`stop` or `decision_close`), start date, release date/cause, next stop
date and mask flag. **Read it as:** each row is one episode; the difference between `since` and
`released` is the time in memory. **Honest limits:** the graph does not say the price level or whether
the return was profitable; a masked name has no price.

## C16. Did the rule or the manager choose the destination?

**Status:** needs the reload (RECARGA). **Graphs:** the System final book graph.

**Pregunta:** En cada parada, ¿decidió la regla o el agente gestor? ¿Eligieron destinos distintos?

<!-- recipe: C16 -->
```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?chooser ?destination (COUNT(?stop) AS ?stops)
WHERE {
  VALUES (?label ?window ?configuration ?slug ?bookGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?stop a :StopEvent ; :stopOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    OPTIONAL { ?stop :chooser ?chooser }
    OPTIONAL { ?stop :chosenCash ?chosenCash }
    OPTIONAL {
      ?stop :chosenOption ?chosen .
      ?chosen :optionAsset ?chosenAsset ; :optionIsSpy ?isSpy .
      OPTIONAL { GRAPH ?universe { ?chosenAsset :tickerSymbol ?chosenTicker } }
    }
  }
  BIND (IF(COALESCE(?chosenCash, false), "cash",
        IF(COALESCE(?isSpy, false), "SPY", COALESCE(?chosenTicker, "no destination")))
       AS ?destination)
}
GROUP BY ?chooser ?destination
ORDER BY ?chooser DESC(?stops)
LIMIT 20
```

**Columns:** chooser, destination and stop count. **Read it as:** `chooser` is `rule` or `agent`;
the destination is cash, SPY or the chosen ticker. **Honest limits:** the graph does not load the
manager prompt/answer, so it says who chose, not the quality of the choice. Masked stops are counted
as events; no price is read.

## C17. How does the System portfolio differ from minimum variance (MARKOWITZ_BASE) on the same date?

**Status:** partial. It works for the loaded books now; the five final configurations need the reload.
**Graphs:** the System and `MARKOWITZ_BASE` final book graphs, `urn:graph:universe:2026-Q4`,
`urn:graph:reference`, `urn:graph:derived:fundamentals:final`.

**Pregunta:** ¿En qué se diferencia la cartera del Sistema de la cartera de mínima varianza (MARKOWITZ_BASE) en la misma fecha:
sectores, nombres en común, número de posiciones?

### C17a. Composition side by side

<!-- recipe: C17a -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?configuration ?ticker ?weight ?sectorLabel ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?asOf ?configuration ?slug ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "2022-06-30"^^xsd:date "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
    ("final" "P1" "2022-06-30"^^xsd:date "MARKOWITZ_BASE" "markowitz_base"
     <urn:graph:derived:backtest:final:P1:markowitz_base>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe {
    ?asset :tickerSymbol ?ticker .
    OPTIONAL { ?asset :classifiedAs ?industry }
  }
  OPTIONAL {
    GRAPH <urn:graph:reference> {
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?configuration DESC(?weight) ?ticker
LIMIT 100
```

**Columns:** configuration, ticker, weight, sector and mask flag. **Read it as:** the same as-of date
for both books; compare names, weights and sectors. **Honest limits:** `MARKOWITZ_MV` is not here
because it has no composition; the book is a backtest, not a live portfolio.

### C17b. Common names

<!-- recipe: C17b -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?systemWeight ?markowitzWeight ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?asOf ?systemGraph ?markowitzGraph ?universe ?fundGraph) {
    ("final" "P1" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:backtest:final:P1:markowitz_base>
     <urn:graph:universe:2026-Q4>
     <urn:graph:derived:fundamentals:final>)
  }
  GRAPH ?systemGraph {
    ?wSystem a :BookWeightDaily ; :weightOfBook ?bookSystem ; :weightDate ?asOf ;
             :holdingAsset ?asset ; :finalTargetWeight ?systemWeight .
    FILTER (?systemWeight > 0)
    ?bookSystem :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?markowitzGraph {
    ?wMarkowitz a :BookWeightDaily ; :weightOfBook ?bookMarkowitz ; :weightDate ?asOf ;
                :holdingAsset ?asset ; :finalTargetWeight ?markowitzWeight .
    FILTER (?markowitzWeight > 0)
    ?bookMarkowitz :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY DESC(?systemWeight) ?ticker
LIMIT 50
```

**Columns:** common ticker and both weights. **Read it as:** only names held by both books on the
date appear; the count of rows is the overlap. **Honest limits:** a name in common can have very
different weights; no return attribution.

### C17c. Position count

<!-- recipe: C17c -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?configuration (COUNT(DISTINCT ?asset) AS ?positions) (SUM(?weight) AS ?investedWeight)
WHERE {
  VALUES (?label ?window ?asOf ?configuration ?slug ?bookGraph) {
    ("final" "P1" "2022-06-30"^^xsd:date "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
    ("final" "P1" "2022-06-30"^^xsd:date "MARKOWITZ_BASE" "markowitz_base"
     <urn:graph:derived:backtest:final:P1:markowitz_base>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
}
GROUP BY ?configuration
ORDER BY ?configuration
LIMIT 10
```

**Columns:** configuration, number of held equity rows and their summed weight. **Read it as:** the
count is equity holdings with a positive target weight; CASH and unlinked rows are excluded.
**Honest limits:** a count of names is not diversification, and MARKOWITZ_MV has no composition.

## C18. Which held companies have weak fundamental signals on date D?

**Status:** available now (HOY). **Graphs:** the System final book graph,
`urn:graph:derived:fundamentals:final`, `urn:graph:universe:2026-Q4`.

**Pregunta:** ¿Qué empresas de la cartera tienen señales fundamentales débiles (deuda alta,
rentabilidad baja, evaluación baja) en la fecha D?

<!-- recipe: C18 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?roic ?debt ?score ?rating ?generatedByLanguageModel
       ?pricesNotPublished ?reason
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?minRoic ?maxDebt ?minScore
          ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     0.08 1.5 40
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?fundGraph {
    ?filing :filingOfAsset ?asset ; :availableAt ?available .
    ?metricSet :metricSetOfFiling ?filing ; :returnOnInvestedCapital ?roic ; :debtToEquity ?debt .
  }
  FILTER (STR(?available) <= STR(?asOf))
  FILTER NOT EXISTS {
    GRAPH ?fundGraph {
      ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
      ?laterSet :metricSetOfFiling ?later ; :returnOnInvestedCapital ?laterRoic .
    }
    FILTER (STR(?laterAvailable) <= STR(?asOf) && STR(?laterAvailable) > STR(?available))
  }
  FILTER NOT EXISTS {
    GRAPH ?fundGraph {
      ?later :filingOfAsset ?asset ; :availableAt ?laterAvailable .
      ?laterSet :metricSetOfFiling ?later ; :debtToEquity ?laterDebt .
    }
    FILTER (STR(?laterAvailable) <= STR(?asOf) && STR(?laterAvailable) > STR(?available))
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?assessment :assessmentOfAsset ?asset ; :availableAt ?assessmentAvailable ;
                  :scoreRaw0to100 ?score ; :rating ?rating ;
                  :generatedByLanguageModel ?generatedByLanguageModel .
    }
  }
  FILTER (!BOUND(?assessmentAvailable) || STR(?assessmentAvailable) <= STR(?asOf))
  FILTER NOT EXISTS {
    GRAPH ?fundGraph {
      ?laterAssessment :assessmentOfAsset ?asset ; :availableAt ?laterAssessmentAvailable .
    }
    FILTER (STR(?laterAssessmentAvailable) <= STR(?asOf) && STR(?laterAssessmentAvailable) > STR(?assessmentAvailable))
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
  FILTER (?roic < ?minRoic || ?debt > ?maxDebt || COALESCE(?score, 100) < ?minScore)
  BIND (CONCAT(
    IF(?roic < ?minRoic, "low ROIC; ", ""),
    IF(?debt > ?maxDebt, "high debt; ", ""),
    IF(COALESCE(?score, 100) < ?minScore, "low assessment", "")
  ) AS ?reason)
}
ORDER BY ?ticker
LIMIT 50
```

**Columns:** ticker, ROIC, debt, assessment score/rating, generated flag, mask flag and the rule that
fired. **Read it as:** the thresholds are explicit in the `VALUES` row; the `reason` names the failed
signals. **Honest limits:** a low score is a second opinion, not a sell signal; a name with no filing
is absent, not healthy; masked names have no valuation.

## C19. How did the assessment of X change between quarters, and did it coincide with its exit?

**Status:** available now (HOY) if the company has more than one assessment; otherwise it returns one
row. **Graphs:** `urn:graph:universe:2026-Q4`, `urn:graph:derived:fundamentals:final`, the System
final book graph.

**Pregunta:** ¿Cómo cambió la evaluación de la empresa X entre trimestres y coincidió con su salida?

<!-- recipe: C19 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?periodEnd ?availableAt ?score ?rating ?generatedByLanguageModel
       ?previousScore ?stopDate ?pricesNotPublished
WHERE {
  VALUES (?ticker ?label ?window ?configuration ?slug ?from ?to
          ?fundGraph ?universe ?bookGraph) {
    ("AAA" "final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy"
     "2021-01-01"^^xsd:date "2022-12-31"^^xsd:date
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>)
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  GRAPH ?fundGraph {
    ?assessment :assessmentOfAsset ?asset ; :assessmentOfFiling ?filing ;
                :availableAt ?availableAt ; :scoreRaw0to100 ?score ; :rating ?rating ;
                :generatedByLanguageModel ?generatedByLanguageModel .
    ?filing :periodEnd ?periodEnd .
    FILTER (?availableAt >= ?from && ?availableAt <= ?to)
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?previous :assessmentOfAsset ?asset ; :availableAt ?previousAvailable ;
               :scoreRaw0to100 ?previousScore .
      FILTER (?previousAvailable < ?availableAt)
      FILTER NOT EXISTS {
        ?between :assessmentOfAsset ?asset ; :availableAt ?betweenAvailable .
        FILTER (?betweenAvailable < ?availableAt && ?betweenAvailable > ?previousAvailable)
      }
    }
  }
  OPTIONAL {
    GRAPH ?bookGraph {
      ?stop a :StopEvent ; :stoppedAsset ?asset ; :stopDate ?stopDate .
      FILTER (?stopDate >= ?from && ?stopDate <= ?to)
    }
  }
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
ORDER BY ?availableAt
LIMIT 40
```

**Columns:** ticker, fiscal period end, availability, score/rating, generated flag, previous score,
stop date and mask flag. **Read it as:** the previous score is the immediately preceding assessment;
a stop date near the assessment date is a coincidence in time, not a cause. **Honest limits:** the
graph does not say why the assessment changed or that it caused the exit; masked names have no
valuation.

## C20. Which portfolio companies have filings, which do not, and why?

**Status:** available now (HOY). **Graphs:** the System final book graph,
`urn:graph:derived:fundamentals:final`, `urn:graph:universe:2026-Q4`.

**Pregunta:** ¿Para cuántas empresas de la cartera hay informes financieros y cuáles no, y por qué?

<!-- recipe: C20 -->
```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker (COUNT(DISTINCT ?filing) AS ?filings)
       (COUNT(DISTINCT ?assessment) AS ?assessments) ?pricesNotPublished
WHERE {
  VALUES (?label ?window ?configuration ?slug ?asOf ?bookGraph ?fundGraph ?universe) {
    ("final" "P1" "SYSTEM_WITH_HIERARCHY" "system_with_hierarchy" "2022-06-30"^^xsd:date
     <urn:graph:derived:backtest:final:P1:system_with_hierarchy>
     <urn:graph:derived:fundamentals:final>
     <urn:graph:universe:2026-Q4>)
  }
  GRAPH ?bookGraph {
    ?weightRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?asOf ;
               :holdingAsset ?asset ; :finalTargetWeight ?weight .
    FILTER (?weight > 0)
    ?book :runLabel ?label ; :windowId ?window .
  }
  GRAPH ?universe { ?asset :tickerSymbol ?ticker }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?filing :filingOfAsset ?asset ; :availableAt ?filingAvailable .
    }
  }
  OPTIONAL {
    GRAPH ?fundGraph {
      ?assessment :assessmentOfAsset ?asset ; :availableAt ?assessmentAvailable .
    }
  }
  FILTER (!BOUND(?filingAvailable) || STR(?filingAvailable) <= STR(?asOf))
  FILTER (!BOUND(?assessmentAvailable) || STR(?assessmentAvailable) <= STR(?asOf))
  OPTIONAL { GRAPH ?fundGraph { ?asset :pricesNotPublished ?masked } }
  BIND (COALESCE(?masked, false) AS ?pricesNotPublished)
}
GROUP BY ?asset ?ticker ?pricesNotPublished
ORDER BY ?ticker
LIMIT 100
```

**Columns:** ticker, filing count, assessment count and mask flag. **Read it as:** zero filings means
no SEC filing is loaded for that asset; `pricesNotPublished = true` means the Tiingo mask withholds
prices and valuation metrics, not the non-valuation fundamentals. **Honest limits:** the graph does
not say a company never filed; it says the delivery has no row. A masked name can have a filing and
still publish no price or valuation.

## Refusal table R1–R9

The agent must reject these with an honest explanation and the offered alternative, never with an
estimated number.

| # | Question | Reason | What to offer instead |
|---|---|---|---|
| R1 | ¿Cuánto subió o cayó la acción X después de que el sistema la vendió? | The graph has no individual prices or returns. | The stop date, rule and destination; the portfolio-level effect (C8). |
| R2 | ¿Fue buena la parada de X? | Judging it requires later prices, which are not published. | The hierarchy's aggregate effect (C8), not a per-stock verdict. |
| R3 | ¿Cuánto aportó la acción X al retorno? | There is no per-asset return attribution. | X's weight on the decision dates (C9/C17). |
| R4 | ¿Qué debo comprar hoy? ¿Cuál es mi cartera actual? | The graph is a historical experiment, not a live portfolio. | What the system would have selected on a historical date (C12/C17). |
| R5 | ¿Funcionará el sistema el año que viene? | The results are in-sample; the rules were calibrated in 2019–2021. | How it behaved in each window (C8). |
| R6 | ¿Cuál es el precio, la capitalización o el rendimiento de flujo de caja de una de las 33 empresas de Tiingo? | The Tiingo licence withholds price and valuation metrics for those companies. | Fundamentals without valuation and the mask reason (C20); events only. |
| R7 | ¿Por qué cayó el mercado en marzo de 2023? | The graph records the system's decisions, not market causes. | What the system did in that period (C6). |
| R8 | ¿Quién es el director ejecutivo de Y? | Executives are not loaded. | The class definition and the missing source; no invented name. |
| R9 | ¿Qué opinan los analistas de bolsa de X? | That source is not loaded. | The generated fundamental assessment, labelled as generated text (C4/C12/C19). |

## How to test the recipes

1. Run `uv run pytest tests/test_ttyg_recipes.py -q`; it parses every fenced query, checks the LIMIT
   and forbidden tokens, verifies every `:IRI` against the schema bundle, checks R1–R9, and executes
   the available-now recipes C4, C9, C13, C18 and C20 against a synthetic graph.
2. In the Workbench, ask the twenty Spanish questions one at a time. Mark each answer
   **correct / incomplete / invented**. A correct answer cites dates, tickers and figures that exist
   in the graph and names the window, arm and as-of date.
3. Ask R1–R9. A refusal passes only when it explains the missing data and offers the alternative; a
   number fails.
4. For every answer with an assessment, check that the generated-text sentence appears when
   `generatedByLanguageModel` is true. For every masked ticker, check that no price or valuation
   appears and that `pricesNotPublished` is stated.
5. If an answer fails because the agent improvised a long query, replace it with the matching recipe
   in this file, not with a new instruction paragraph.
