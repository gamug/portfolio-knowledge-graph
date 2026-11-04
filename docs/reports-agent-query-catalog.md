# Reports-agent query catalog

The contract between this knowledge graph and the reports agent: the SPARQL
queries that answer the questions the agent receives, the questions the graph
cannot answer, and the limits of what a term definition can prove. The
catalog is executable: every fenced `sparql` block below is tagged with
`<!-- q:NAME expect:... -->` and is run by `tests/test_query_catalog.py`
against the schema bundle and the synthetic two-label, two-window backtest of
`tests/fixtures/backtest_rows.py`. Adding, renaming or deleting a query
without updating its tag and its expectation fails that test.

This file is a query catalog, not a query service. It does not add an
endpoint, a new package or a computation; it records how the reports agent
reads what this repository already projects. The FIBO boundary is the brief's
§5 rule, restated here because it decides what the agent may ask a definition
to do:

> **FIBO explains what terms mean, never why an asset was in or out of a
> portfolio.**

A definition query may explain `:Veto`, `:GuardAction`, `:PortfolioPosition`
or `:BookWeightDaily`; it may not turn a term into a reason. The reason for an
inclusion or an exclusion is a `:Veto`, a `:GuardAlert`/`:GuardAction` or a
rebalance record, and it is answered by the data queries below, not by
`rdfs:seeAlso`.

## 1. How to scope every query

**Name a `GRAPH` for every pattern that belongs to one graph; never rely on
the default union by accident.** GraphDB's default graph is the union of every
named graph, so an unscoped query mixes the ontology (`urn:graph:tbox`), the
reference data (`urn:graph:reference`), the FIBO slice
(`urn:graph:reference:fibo`), the rule catalog (`urn:graph:rules:catalog`) and
every projected backtest. The symptom is subtle: `?s a :Asset` returns the
`:Asset` **class** from the TBox beside the asset **individuals** from the
reference graph, and a `?term rdfs:seeAlso ?fibo` pattern cross-joins the whole
glossary unless the link and the FIBO lookup sit in the same `OPTIONAL`.

The one deliberate exception is the asset-to-sector sub-select in §6: the
asset classification lives in `urn:graph:universe:*` and the taxonomy in
`urn:graph:reference`, so that sub-select runs outside `GRAPH` and uses the
union on purpose. It is a `SELECT DISTINCT`, and it is the only unscoped
pattern in this catalog. The hermetic test builds its dataset with the same
default union, so the exception is exercised; every other query still has to
name its graph. Outside that sub-select, a query that needs the union is a bug:
it mixes graphs, and enabling the union for the test does not license a second
unscoped pattern.

| Graph | What it holds | How to name it |
|---|---|---|
| `urn:graph:tbox` | classes, properties, Spanish labels and definitions | `GRAPH <urn:graph:tbox> { ... }` |
| `urn:graph:reference` | GICS sectors/industries and the worked-example `:Asset`s | `GRAPH <urn:graph:reference> { ... }` |
| `urn:graph:universe:{year}-Q{n}` | the asset catalog: `:Asset`, `:classifiedAs`, `:UniverseMembership` | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:universe:"))`, or the §6 sub-select |
| `urn:graph:reference:fibo` | the FIBO 2026Q2 glossary slice (54 entries) | `GRAPH <urn:graph:reference:fibo> { ... }` |
| `urn:graph:rules:catalog` | every `:RuleDefinition`, selection and GUARD | `GRAPH <urn:graph:rules:catalog> { ... }` |
| `urn:graph:derived:backtest:*` | one append-only graph per completed run family and window: the m018 book/GUARD graph and the selection-side sibling (`...:selection:...`) | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))` |

The backtest graph's full name is
`urn:graph:derived:backtest:{label}:{window}:{run_id}`.
**Do not hardcode the run label or the run id.** Bind the graph with
`GRAPH ?g` and the prefix filter above, select the run family with
`FILTER (?label = "rule")` from `:runLabel` on its `:StrategyBook`, and select
the window with `:windowId`, not with a substring of the graph name. A later
change to the graph naming then changes the filter in one place, not every
query. The synthetic test projects two labels in one window as well as two
windows (`rule:P1:1`, `rule:P2:1`, `champ_v1:P1:1`, `champ_v1:P2:1`), so a
query that confuses the label or the window with the graph name fails there.

Inside a `GRAPH`, `OPTIONAL` is scoped to that graph. An `OPTIONAL` that must
add a FIBO definition to a term has to hold **both** the `:term rdfs:seeAlso
?fibo` pattern and the FIBO lookup; splitting them into two `OPTIONAL`s makes
the FIBO branch independent and cross-joins every FIBO entry. Query `A1` below
is the template.

## 2. Appendix A — what a term means

### A1. One or more of our terms, with the FIBO link in the same `OPTIONAL`

`A1` explains ten of our terms at once: `:Portfolio`, `:PortfolioPosition`,
`:Sector`, `:Industry`, `:SECFiling`, `:Asset`, `:Universe`,
`:UniverseMembership`, `:PriceObservation` and `:Executive`. Five of them have
a FIBO link (`:Portfolio`, `:PortfolioPosition`, `:Sector`, `:Industry` and
`:SECFiling`); the other five come back with every `?fibo*` variable unbound.
`:Asset` is deliberately one of the unbound ones: since T-264 it is one node
per company line for a pure ticker succession (`FB`→`META`), but still one
node per symbol for concurrent share classes (its own definition names GOOGL
and GOOG) and for a mixed CIK, so FIBO's `LegalPerson`/`PubliclyHeldCompany`
would misstate those classes and a reused ticker. `:Universe` and `:UniverseMembership`, `:PriceObservation`
and `:Executive` have no FIBO link for the reasons `docs/06` §1.1 gives. The
rows are not dropped, and they do not cross-join the glossary.

<!-- q:A1-terms expect:10 -->

```sparql
PREFIX :     <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?labelEs ?defEs ?fibo ?fiboLabelEs ?fiboDefEs ?fiboDef
WHERE {
  VALUES ?term {
    :Portfolio :PortfolioPosition :Sector :Industry :SECFiling :Asset
    :Universe :UniverseMembership :PriceObservation :Executive
  }

  GRAPH <urn:graph:tbox> {
    ?term rdfs:label ?labelEs ; skos:definition ?defEs .
    FILTER (lang(?labelEs) = "es" && lang(?defEs) = "es")
  }

  # The seeAlso and the FIBO lookup are ONE OPTIONAL on purpose. A second
  # OPTIONAL would make the FIBO branch independent of ?term and cross-join
  # the whole 54-entry glossary.
  OPTIONAL {
    GRAPH <urn:graph:tbox> { ?term rdfs:seeAlso ?fibo . }
    GRAPH <urn:graph:reference:fibo> {
      ?fibo skos:definition ?fiboDef .
      FILTER (!langMatches(lang(?fiboDef), "es"))
      OPTIONAL { ?fibo rdfs:label      ?fiboLabelEs FILTER (lang(?fiboLabelEs) = "es") }
      OPTIONAL { ?fibo skos:definition ?fiboDefEs   FILTER (lang(?fiboDefEs)   = "es") }
    }
  }
}
ORDER BY ?term
```

### A2. A general finance term by its Spanish label

`A2` searches the FIBO slice by the authors' Spanish label. The English
definition is FIBO's own text; the `@es` definition is the authors'
translation, never FIBO's words. `"volatilidad"` is the Appendix A example.

<!-- q:A2-volatilidad expect:1 -->

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) = "volatilidad")
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}
```

The same shape answers the other Spanish labels the evaluation questions name.
`A2-equity-index` is the FIBO `EquityIndex` term; the `:SP500Index` individual
itself is written by the asset loader, not by this slice. `A2-price-close`
returns both price terms, which have no `rdfs:seeAlso` from
`:PriceObservation`: FIBO's adjusted close includes dividends, while our
`PriceObservation` close is split-adjusted and price-only. `A2-sec` is the
regulator FIBO names.

<!-- q:A2-equity-index expect:1 -->

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) = "índice bursátil de renta variable")
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}
```

<!-- q:A2-price-close expect:2 -->

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) IN ("precio de cierre", "precio de cierre ajustado"))
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}
ORDER BY ?term
```

<!-- q:A2-sec expect:1 -->

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) = "comisión de bolsa y valores de ee. uu. (sec)")
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}
```

## 3. Terms FIBO does not define

FIBO has no class for a backtest run, a strategy arm, a GUARD rule, a Sharpe
ratio, a drawdown, turnover or a paired statistical test. Those terms are
ours: their `@es` definitions live in `urn:graph:tbox`, and `A1` returns no
FIBO row for them. The query below finds the two terms whose Spanish
definition mentions Sharpe; it is the check that the agent must not promise a
FIBO definition it cannot get.

<!-- q:fibo-missing-sharpe expect:2 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?definition
WHERE {
  GRAPH <urn:graph:tbox> {
    ?term skos:definition ?definition .
    FILTER (lang(?definition) = "es" && CONTAINS(LCASE(STR(?definition)), "sharpe"))
  }
}
ORDER BY ?term
```

The answer is `:PortfolioPeriodSummary` and `:BacktestTest`. Both are
backtest terms; neither has a FIBO link, and neither needs one.

## 4. The rule catalog

A rule is **active** when it has no `:validTo`; a closed rule is history and
must not be counted. The ten active selection rules are the `DATA_QUALITY`,
`FINANCIAL` and `MARKET` rows; the five GUARD rules are the `GUARD` rows.
`L1_STOP_LOSS` and `L1_REENTRY` are both layer 1, `L2_NEWS` layer 2, `L3_VOL`
layer 3 and `L4_DD` layer 4. `LIQUIDITY_DISTRESS` has two definitions with
the same `:ruleId`; only the active one (`..._v11`) is returned.

<!-- q:active-rules expect:15 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?category ?ruleId ?rule
WHERE {
  GRAPH <urn:graph:rules:catalog> {
    ?rule a :RuleDefinition ; :category ?category ; :ruleId ?ruleId .
    FILTER NOT EXISTS { ?rule :validTo ?closed }
  }
  FILTER (?category IN ("DATA_QUALITY", "FINANCIAL", "MARKET", "GUARD"))
}
ORDER BY ?category ?ruleId
```

The result is 5 `FINANCIAL` rules (`LEVERAGE_EXTREME`, `NEGATIVE_FCF`,
`LIQUIDITY_DISTRESS`, `EARNINGS_MISSING`, `UTILITY_CASH_COVERAGE`), 1
`DATA_QUALITY` rule, 4 `MARKET` rules (`PRICE_CRASH`, `VOLATILITY_SHOCK`,
`CRASH_Z_SCORE`, `BREAK_TREND_200`) and the 5 `GUARD` rules.

### 4.1 Who was in the S&P 500 on a date

`validTo` is **inclusive**: it is the last day of membership, not the first
day after it. A point-in-time read binds D in one place and keeps a membership
with `validFrom <= D AND (no validTo OR validTo >= D)`. The date below is the
last day of the old `FB` stint; the `META` stint starts the next day, so an
exclusive `validTo > D` predicate would return no row. The asset is already the
one `:Asset` for the company (`:META`), because the rename chain shares a CIK.
The `:Universe` graph is one of the quarter graphs written by
`cli/load_universe.py`; the query does not hardcode its quarter.

<!-- q:universe-members-on-date expect:1 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?asset ?ticker ?from ?to
WHERE {
  GRAPH ?g {
    ?membership a :UniverseMembership ;
                :membershipAsset ?asset ;
                :validFrom ?from .
    OPTIONAL { ?membership :validTo ?to }
    ?asset :tickerSymbol ?ticker .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:universe:"))
  FILTER (?from <= "2022-06-08"^^xsd:date)
  FILTER (!BOUND(?to) || ?to >= "2022-06-08"^^xsd:date)
}
ORDER BY ?ticker
```

## 5. The backtest battery

Every query in this section binds the graph with `GRAPH ?g` and filters it
with `STRSTARTS(STR(?g), "urn:graph:derived:backtest:")`. Every per-run query
also selects the run family with `FILTER (?label = "rule")`, read from
`:runLabel` on the run's `:StrategyBook` (an alert or an action reaches it
through its book), and the window with `:windowId`. `"rule"` is a parameter:
change it to another label for another result family. The property inventory
in §5.7 and `runs-available` in §5.10 deliberately span labels. None names a
run label, window or run id in the graph name.

### 5.1 Performance per window, arm and segment

One row per `:PortfolioPeriodSummary` for the selected label. The fixture has
a summary for `MARKOWITZ_BASE` and `TOPN_MV_GUARD_NO_NLP` in each of the two
windows; the no-guard arm has none in the synthetic scenario, which is why the
query returns four rows rather than six. The `:summaryOfBook` → `:runLabel`
join is what keeps two labels of the same window apart; a query without the
filter would return both.

<!-- q:performance-window-arm-segment expect:4 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?arm ?segment ?summary
       ?cumulativeReturn ?annualizedReturn ?exPostSharpe
WHERE {
  GRAPH ?g {
    ?summary a :PortfolioPeriodSummary ;
      :summaryOfBook ?book ;
      :windowId ?window ; :armCode ?arm ; :segment ?segment ;
      :cumulativeReturn ?cumulativeReturn ;
      :annualizedReturn ?annualizedReturn ;
      :exPostSharpe ?exPostSharpe .
    ?book :runLabel ?label .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
}
ORDER BY ?window ?arm
```

### 5.2 GUARD alerts by window, month and rule

The month is derived from `:alertDate`; the window is the `:windowId` filter.
The example keeps `P1` and February 2022. Change both filters for another
window or month; the join to the rule catalog is what turns an alert into a
rule id. The label filter goes from the alert through its action to the
action's book, so an alert that no book ever evaluated (no action) has no
label and is omitted when the filter is applied — in the synthetic scenario
those are `L1_REENTRY` and `L2_NEWS`. Remove the filter to see them, but then
labels mix.

<!-- q:guard-alerts-window-month-rule expect:3 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?month ?ruleId (COUNT(DISTINCT ?alert) AS ?alerts)
WHERE {
  GRAPH ?g {
    ?alert a :GuardAlert ; :windowId ?window ; :alertDate ?date ; :alertRule ?rule .
    ?alert :alertHasGuardAction ?action .
    ?action :actionOfBook ?book .
    ?book :runLabel ?label .
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :ruleId ?ruleId . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1")
  BIND (SUBSTR(STR(?date), 1, 7) AS ?month)
  # February 2022 is the synthetic scenario's whole alert window.
  FILTER (?month = "2022-02")
}
GROUP BY ?label ?window ?month ?ruleId
ORDER BY ?ruleId
```

### 5.3 Latest NAV per arm known on a date D

The knowledge date is `:knowledgeDate`, not the performance date. A row whose
`:knowledgeDate` is after `D` did not exist for the agent on `D` and must not
be used, even if its `:performanceDate` is earlier. Change the two occurrences
of `D` together; the inner `NOT EXISTS` picks the latest performance date among
the rows known by `D`, and its `:runLabel` join keeps that comparison inside
the selected label.

<!-- q:latest-nav-known-on-date expect:3 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?label ?arm ?date ?nav
WHERE {
  GRAPH ?g {
    ?perf a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
      :performanceDate ?date ; :nav ?nav ; :knowledgeDate ?known ;
      :performanceOfBook ?book .
    ?book :runLabel ?label .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1")
  # D = 2022-01-06
  FILTER (?known <= "2022-01-06"^^xsd:date)
  FILTER NOT EXISTS {
    GRAPH ?g2 {
      ?later a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
        :performanceDate ?laterDate ; :knowledgeDate ?laterKnown ;
        :performanceOfBook ?laterBook .
      ?laterBook :runLabel ?label .
    }
    FILTER (STRSTARTS(STR(?g2), "urn:graph:derived:backtest:"))
    FILTER (?laterKnown <= "2022-01-06"^^xsd:date)
    FILTER (?laterDate > ?date)
  }
}
ORDER BY ?arm
```

### 5.4 Tickers cut most often by layer 1

A layer-1 cut is a `:GuardAction` with status `"APPLIED"` whose alert's rule
is on `:guardLayer 1`. The action carries `:guardTicker` as a plain string, so
this query works even when the asset catalog was not loaded and no
`:guardAsset` link exists. `ARM_DISABLED` actions are the no-guard arm's
counterfactuals, not cuts, and are excluded. The count is grouped by label and
window (both come from the action's book), so the same ticker cut once in
each window appears once per window, and two labels never mix.

<!-- q:layer1-cut-tickers expect:2 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?ticker (COUNT(?action) AS ?cuts)
WHERE {
  GRAPH ?g {
    ?action a :GuardAction ; :actionAlert ?alert ; :guardTicker ?ticker ;
      :status "APPLIED" ; :actionOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    ?alert :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :guardLayer 1 . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
}
GROUP BY ?label ?window ?ticker
ORDER BY ?window DESC(?cuts) ?ticker
```

### 5.5 One end-to-end explanation of a cut

This is the report's "why was AAA cut?" answer: the alert, its rule id and the
rule's own note, and the action status per arm. The alert has no direct book
link; the action is the bridge, and that action's book is also where the
`:runLabel` filter comes from. In the synthetic scenario alert 1 is a layer-1
stop loss on `AAA`, applied on `MARKOWITZ_BASE` and registered as
`ARM_DISABLED` on `TOPN_MV_NOGUARD`, in the label selected by the filter.

<!-- q:cut-explanation expect:rule=L1_STOP_LOSS -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?label ?window ?alert ?ruleId ?ruleNote ?arm ?status
WHERE {
  GRAPH ?g {
    ?alert a :GuardAlert ; :alertId 1 ; :windowId ?window ; :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> {
    ?rule :ruleId ?ruleId ; rdfs:comment ?ruleNote .
  }
  OPTIONAL {
    GRAPH ?g2 {
      ?action a :GuardAction ; :actionAlert ?alert ; :armCode ?arm ; :status ?status ;
        :actionOfBook ?book .
      ?book :runLabel ?label .
    }
    FILTER (STRSTARTS(STR(?g2), "urn:graph:derived:backtest:"))
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1")
}
ORDER BY ?arm ?status
```

### 5.6 The knowledge dates of the books

One row per book (label × window × arm), with the first and last
`:knowledgeDate`. This is the transaction-time answer to "what did the agent
know when?"; it is not a valid-time interval.

<!-- q:book-knowledge-dates expect:6 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?arm (MIN(?known) AS ?firstKnown) (MAX(?known) AS ?lastKnown)
WHERE {
  GRAPH ?g {
    ?book a :StrategyBook ; :runLabel ?label ; :windowId ?window ; :armCode ?arm ;
      :knowledgeDate ?known .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
}
GROUP BY ?label ?window ?arm
ORDER BY ?window ?arm
```

### 5.7 The full property list of `BookWeightDaily` and `BookDailyPerformance`

This query lists every predicate actually present on the two classes, with a
count, across every label. It is an inventory of the classes, not a per-run
answer, which is why it intentionally has no `:runLabel` filter. It is the
evidence that the graph has **no** per-asset daily return and
**no** drifted weight: the only numeric weight properties are the decision
and execution targets (`:markowitzTargetWeight`, `:finalTargetWeight`), and the
daily performance is portfolio-level only (`:grossReturn`, `:netReturn`,
`:nav`, `:drawdown`, `:cashWeight`, `:turnover`, `:costReturn`, `:nEquity`,
`:benchmarkReturn`). Shared properties with no `rdfs:domain` (`:bookId`,
`:armCode`, `:knowledgeDate`, …) appear because they are present on the
individuals.

<!-- q:book-weight-daily-properties expect:27 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?class ?property (COUNT(*) AS ?triples)
WHERE {
  VALUES ?class { :BookWeightDaily :BookDailyPerformance }
  GRAPH ?g {
    ?s a ?class ; ?property ?o .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  FILTER (?property != rdf:type)
}
GROUP BY ?class ?property
ORDER BY ?class ?property
```

### 5.8 Scale: weights per window and arm

The Workbench timing query. `:BookWeightDaily` has no `:windowId` or
`:runLabel` of its own; both come from `:weightOfBook` → `:StrategyBook`.
The result is one row per label × window × arm, with the count of weight rows
the selected run's graph holds.

<!-- q:weight-scale expect:6 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?arm (COUNT(?weight) AS ?weights)
WHERE {
  GRAPH ?g {
    ?weight a :BookWeightDaily ; :armCode ?arm ; :weightOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
}
GROUP BY ?label ?window ?arm
ORDER BY ?window ?arm
```

### 5.9 Equities per arm on the last performance day

One row per label, window and arm with the `:nEquity` of the latest
`:performanceDate`. This is a **backtest book**, not the live portfolio: the
live portfolio is not projected yet (`v_portfolio_position` has no projector),
so this number must never be presented as the number of positions in the live
portfolio.

<!-- q:n-equity-per-arm-on-last-day expect:6 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window ?arm ?date ?nEquity
WHERE {
  GRAPH ?g {
    ?perf a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
      :performanceDate ?date ; :nEquity ?nEquity ; :performanceOfBook ?book .
    ?book :runLabel ?label .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER NOT EXISTS {
    GRAPH ?g2 {
      ?later a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
        :performanceDate ?laterDate ; :performanceOfBook ?laterBook .
      ?laterBook :runLabel ?label .
    }
    FILTER (STRSTARTS(STR(?g2), "urn:graph:derived:backtest:"))
    FILTER (?laterDate > ?date)
  }
}
ORDER BY ?window ?arm
```

### 5.10 The runs available in the store

One row per label × window, with the number of `:StrategyBook`s the store holds
for that run. This is the query to run first: it tells the agent which
`FILTER (?label = "...")` values and which `:windowId` values exist. It
intentionally spans every label; the per-run queries in §5.1–§5.13 (except the
property inventory in §5.7) select one.

### 5.11 The ranking at a rebalance

One row per asset in the selected cycle, in rank order. `:rankPosition` is upstream's rank,
`:selectedForBook` its selection flag, `:targetWeight` its book weight (absent when not selected)
and `:vetoRulesJson` upstream's rule ids/markers verbatim. A row with no `:hasEffectiveWeight`
entry is the UNSCORED/UNPRICED placeholder (score 0.0), as in `selection-why-not-top30`.

<!-- q:selection-ranking-at-rebalance expect:5 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?rank ?ticker ?score ?selected ?target ?vetoed ?rules
WHERE {
  GRAPH ?g {
    ?snap a :AttractivenessSnapshot ; :runLabel ?label ; :windowId ?window ;
      :rankingOfCycle ?cycle ; :rankPosition ?rank ; :rankingTicker ?ticker ;
      :attractivenessScore ?score ; :selectedForBook ?selected ;
      :vetoedAtRanking ?vetoed .
    ?cycle :runAsOf ?date .
    OPTIONAL { ?snap :targetWeight ?target }
    OPTIONAL { ?snap :vetoRulesJson ?rules }
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1" && ?date = "2022-01-05"^^xsd:date)
}
ORDER BY ?rank
```

### 5.12 The selection vetoes in force at a cutoff

A veto is in force at `C` iff `raisedOn <= C` and it has no `clearedOn` on or before `C`; the
T-1 lag is that read-time predicate, not a stored flag. The synthetic run has two such stints on
2022-01-05 (`CCC` DATA_QUALITY and `ZZZ` LIQUIDITY_DISTRESS); the BBB liquidity stint cleared on
2021-12-15 and is excluded.

<!-- q:selection-vetoes-in-force expect:2 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?ruleId ?severity ?raised ?cleared
WHERE {
  GRAPH ?g {
    ?veto a :Veto ; :runLabel ?label ; :windowId ?window ; :vetoTicker ?ticker ;
      :raisedOn ?raised ; :appliesRule ?rule .
    OPTIONAL { ?veto :clearedOn ?cleared }
    FILTER NOT EXISTS { ?veto :clearedOn ?closed FILTER (?closed <= "2022-01-05"^^xsd:date) }
    FILTER (?raised <= "2022-01-05"^^xsd:date)
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :ruleId ?ruleId }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1")
}
ORDER BY ?ticker ?ruleId
```

### 5.13 Why one asset did not make the Top-30

The row for `BRK.B` on the synthetic rebalance: rank 5, not selected, `vetoedAtRanking` true,
`vetoRulesJson` `["UNSCORED"]`, score 0.0 and zero effective-weight components. That absence is
the placeholder marker, not a missing projection.

<!-- q:selection-why-not-top30 expect:1 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?ticker ?rank ?selected ?vetoed ?rules ?score (COUNT(?component) AS ?components)
WHERE {
  GRAPH ?g {
    ?snap a :AttractivenessSnapshot ; :runLabel ?label ; :windowId ?window ;
      :rankingOfCycle ?cycle ; :rankingTicker ?ticker ; :rankPosition ?rank ;
      :selectedForBook ?selected ; :vetoedAtRanking ?vetoed ;
      :attractivenessScore ?score .
    ?cycle :runAsOf ?date .
    OPTIONAL { ?snap :vetoRulesJson ?rules }
    OPTIONAL { ?snap :hasEffectiveWeight ?component }
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1" && ?date = "2022-01-05"^^xsd:date && ?ticker = "BRK.B")
}
GROUP BY ?ticker ?rank ?selected ?vetoed ?rules ?score
```

<!-- q:runs-available expect:4 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?label ?window (COUNT(DISTINCT ?book) AS ?books)
WHERE {
  GRAPH ?g {
    ?book a :StrategyBook ; :runLabel ?label ; :windowId ?window .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
GROUP BY ?label ?window
ORDER BY ?label ?window
```

## 6. Sector and industry questions

The sector of an asset is split across two graph families. In `portfolio_test`
on 2026-11-04, `:Asset` and `:classifiedAs` live in
`urn:graph:universe:2026-Q4` (643 assets, 584 with a classification; the five
worked-example assets are declared separately in `reference.ttl`), while
`:Industry`, `:Sector`, `:memberOfSector` and their `skos:prefLabel`s live in
`urn:graph:reference`. Only the five worked-example assets that
`schema/reference.ttl` declares satisfy a pattern that holds the classification
and the taxonomy in one graph. A query with both in a single `GRAPH` block
therefore returns those five rows, or none if the block names the universe
graph, not the catalog.

The cross-graph rule is:

- keep the backtest part inside `GRAPH ?g` filtered to
  `urn:graph:derived:backtest:`, with the run label on `:StrategyBook`;
- take the asset-to-sector part from a de-duplicated sub-select **outside** it:

  ```text
  { SELECT DISTINCT ?asset ?sector WHERE {
      ?asset :classifiedAs ?industry .
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
  } }
  ```

The default graph of GraphDB is the union of every named graph, so that
sub-select can see the classification in the universe graph and the taxonomy in
the reference graph at once. The `DISTINCT` is load-bearing: the five
worked-example assets also appear in the universe graph for their memberships
(T-225), so without it the same asset-to-sector pair is counted twice. Do not
put the backtest triples in that union sub-select; they belong to one run graph
and are scoped by `GRAPH ?g`.

### 6.1 GUARD layer-1 cuts by window and sector

A layer-1 cut is an `:GuardAction` with status `"APPLIED"` whose
`:actionAlert` is a layer-1 rule and whose alert state is `"ENTER"`. An
`"EXIT"` alert is the re-entry, not a cut; `ARM_DISABLED` actions are the
no-guard arm's counterfactuals. The sector comes from `:guardAsset`; an action
whose ticker is not linked to an asset is reported as `unclassified` instead of
being silently dropped. On 2026-11-04 the query returned 157 cuts for P1, 56 for
P2 and 29 for P3, and the P1 total equalled the 157 layer-1 ENTER alerts.

<!-- q:layer1-cuts-by-window-sector expect:2 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?label ?window ?sector (COUNT(DISTINCT ?action) AS ?cuts)
WHERE {
  GRAPH ?g {
    ?action a :GuardAction ; :status "APPLIED" ;
      :actionAlert ?alert ; :actionOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    ?alert :alertState "ENTER" ; :alertRule ?rule .
    OPTIONAL { ?action :guardAsset ?asset . }
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :guardLayer 1 . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  # The classification is in urn:graph:universe:* and the taxonomy in
  # urn:graph:reference; this DISTINCT sub-select is the documented union exception.
  # The sentinel keeps an action without :guardAsset out of a cross-join.
  BIND (COALESCE(?asset, <urn:thesis:no-asset>) AS ?lookupAsset)
  OPTIONAL {
    SELECT DISTINCT ?lookupAsset ?sectorLabel WHERE {
      ?lookupAsset :classifiedAs ?industry .
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
    }
  }
  BIND (COALESCE(?sectorLabel, "unclassified") AS ?sector)
}
GROUP BY ?label ?window ?sector
ORDER BY ?window DESC(?cuts) ?sector
```

### 6.2 Sector composition of a book on a rebalance date

`:finalTargetWeight` exists only on a rebalance's decision and execution
dates. `:BookWeightDaily` rows exist on every day, but an ordinary session has
no target weight: the view masks it, and the property is absent rather than
zero. The query selects the execution-date row of the rebalance decided on `D`
(`?weightDate = ?execution`); change that filter to `?decision` to read the
decision-date row when the run carries one. The sector weights plus the
`unclassified` bucket sum to **1 minus the CASH weight**; CASH is not an asset
and has no sector, so it is read as its own `:finalTargetWeight`. A holding
whose asset has no `:classifiedAs` and a holding with no `:holdingAsset` at all
both land in `unclassified`, so neither is silently dropped.

The example uses the synthetic scenario's decision of 2022-01-03 (execution
2022-01-04). In `portfolio_test` the same P1 `MARKOWITZ_BASE` book decides on
2021-12-31 and executes on 2022-01-03; the date filter is the parameter.

<!-- q:sector-composition-on-rebalance expect:1 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>

SELECT ?label ?window ?arm ?decision ?weightDate ?sector
       (SUM(?weightValue) AS ?weight) ?cash
WHERE {
  GRAPH ?g {
    ?rebalance a :BookRebalance ; :rebalanceOfBook ?book ;
      :decisionDate ?decision ; :executionDate ?execution .
    ?book :runLabel ?label ; :windowId ?window ; :armCode ?arm .
    ?row a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?weightDate ;
      :holdingKey ?ticker ; :finalTargetWeight ?weightValue .
    ?cashRow a :BookWeightDaily ; :weightOfBook ?book ; :weightDate ?weightDate ;
      :holdingKey "CASH" ; :finalTargetWeight ?cash .
    FILTER (?ticker != "CASH")
    OPTIONAL { ?row :holdingAsset ?asset . }
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  FILTER (?window = "P1")
  FILTER (?arm = "MARKOWITZ_BASE")
  # D: the rebalance decision. Change this date together with the book and window above.
  FILTER (?decision = "2022-01-03"^^xsd:date)
  FILTER (?weightDate = ?execution)
  # The sentinel keeps a holding without :holdingAsset out of the catalog join.
  BIND (COALESCE(?asset, <urn:thesis:no-asset>) AS ?lookupAsset)
  OPTIONAL {
    SELECT DISTINCT ?lookupAsset ?sectorLabel WHERE {
      ?lookupAsset :classifiedAs ?industry .
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
    }
  }
  BIND (COALESCE(?sectorLabel, "unclassified") AS ?sector)
}
GROUP BY ?label ?window ?arm ?decision ?weightDate ?sector ?cash
ORDER BY DESC(?weight) ?sector
```

### 6.3 Distinct held tickers by window and industry

This is the Q11 answer for banks and insurers. The `VALUES` line is the
parameter: add or replace industry labels to ask about other GICS industries.
A ticker held by several books of the same label and window counts once, and
`GROUP_CONCAT` returns the ticker list. The list's order is not defined; treat
it as a set.

<!-- q:held-tickers-by-window-industry expect:4 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?label ?window ?industry
       (COUNT(DISTINCT ?ticker) AS ?tickers)
       (GROUP_CONCAT(DISTINCT ?ticker; SEPARATOR=", ") AS ?tickerList)
WHERE {
  {
    SELECT DISTINCT ?asset ?industry WHERE {
      ?asset :classifiedAs ?i .
      ?i skos:prefLabel ?industry .
    }
  }
  GRAPH ?g {
    ?row a :BookWeightDaily ; :holdingKey ?ticker ; :holdingAsset ?asset ;
      :weightOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    FILTER (?ticker != "CASH")
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  VALUES ?industry { "Banks" "Insurance" }
}
GROUP BY ?label ?window ?industry
ORDER BY ?window ?industry
```

### 6.4 Sector coverage of held assets

One row per label and window: the distinct tickers held (CASH excluded), how
many have a `:holdingAsset` link, and how many of those resolve to a sector.
On 2026-11-04 the real store returned 100/100/100 for P1, 123/123/123 for P2
and 115/115/115 for P3. A missing link means the ticker is not in the loaded
catalog; a missing sector means the source has no classification for it (see
§6.7). Neither is a query error.

<!-- q:sector-coverage-of-held-assets expect:2 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?label ?window
       (COUNT(DISTINCT ?ticker) AS ?heldTickers)
       (COUNT(DISTINCT ?asset) AS ?withAsset)
       (COUNT(DISTINCT ?sectorAsset) AS ?withSector)
WHERE {
  GRAPH ?g {
    ?row a :BookWeightDaily ; :holdingKey ?ticker ; :weightOfBook ?book .
    ?book :runLabel ?label ; :windowId ?window .
    FILTER (?ticker != "CASH")
    OPTIONAL { ?row :holdingAsset ?asset . }
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  # Optional run-label parameter: change "rule" to another label.
  FILTER (?label = "rule")
  # Sentinel keeps an unlinked ticker from cross-joining the whole catalog.
  BIND (COALESCE(?asset, <urn:thesis:no-asset>) AS ?lookupAsset)
  OPTIONAL {
    {
      SELECT DISTINCT ?lookupAsset ?sectorLabel WHERE {
        ?lookupAsset :classifiedAs ?industry .
        ?industry :memberOfSector ?sector .
        ?sector skos:prefLabel ?sectorLabel .
      }
    }
    BIND (?lookupAsset AS ?sectorAsset)
  }
}
GROUP BY ?label ?window
ORDER BY ?window
```

### 6.5 Unclassified assets by year of `validTo`

An asset is unclassified when no graph carries a `:classifiedAs` triple for it.
The query counts distinct assets, not membership stints, by the calendar year
of the closed membership's `:validTo`. A missing classification is a source
gap, not a malformed catalog: the note below records which stints the source
cannot classify and why.

<!-- q:unclassified-assets-by-validto-year expect:2 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?year (COUNT(DISTINCT ?asset) AS ?unclassifiedAssets)
WHERE {
  GRAPH ?g {
    ?asset a :Asset ; :hasUniverseMembership ?membership .
    ?membership :validTo ?validTo .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:universe:"))
  FILTER NOT EXISTS {
    GRAPH ?classifiedGraph { ?asset :classifiedAs ?industry . }
  }
  BIND (YEAR(?validTo) AS ?year)
}
GROUP BY ?year
ORDER BY ?year
```

### 6.6 The sector of one asset

This is the Q5 data answer. `VALUES ?ticker { "AAA" }` is the parameter; change
the literal for another ticker. The asset-to-sector part is the same cross-graph
`SELECT DISTINCT` sub-select as §6.1. The five worked-example assets are
declared in `reference.ttl` and appear again in the universe graph for their
memberships (T-225), so the `DISTINCT` is what makes `AAPL` return exactly one
row. A ticker with no `:classifiedAs` returns no row: that is the source gap
described in §6.7, not a query error. The optional `?sectorDefinition` is the
sector individual's Spanish `rdfs:comment` or `skos:definition`; the shipped
`reference.ttl` carries none, so it is normally unbound.

<!-- q:sector-of-asset expect:1 -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?ticker ?companyName ?industryLabel ?sectorLabel ?sectorDefinition
WHERE {
  VALUES ?ticker { "AAA" }
  {
    SELECT DISTINCT ?asset ?ticker ?companyName ?industryLabel ?sectorLabel ?sectorDefinition
    WHERE {
      ?asset :tickerSymbol ?ticker .
      ?asset :classifiedAs ?industry .
      ?industry skos:prefLabel ?industryLabel .
      ?industry :memberOfSector ?sector .
      ?sector skos:prefLabel ?sectorLabel .
      OPTIONAL { ?asset :companyName ?companyName . }
      OPTIONAL {
        {
          SELECT ?sector (SAMPLE(?definition) AS ?sectorDefinition)
          WHERE {
            { ?sector rdfs:comment ?definition . }
            UNION
            { ?sector skos:definition ?definition . }
            FILTER (lang(?definition) = "es")
          }
          GROUP BY ?sector
        }
      }
    }
  }
}
```

### 6.7 Known limits of the asset catalog

- GICS for a leaver comes from the last Wikipedia revision that lists the
  company, and those revisions stop at 2022-01-01. The 2019–2021 leavers
  therefore have no sector in the source: 56 closed stints (one unclassified
  asset each), reported as "no classification in the source", not as an error.
- The temporary spin-off members MBC (inference, no source), FTRE and PHIN
  (S&P DJI release of 2023-06-28, cited in `universe_patches.py`) have no
  sector either.
- GICS is a reference taxonomy rolled up by `src/etl/common/gics_rollup.py`;
  the catalog never invents a classification for an unmapped string.
- `validTo` is inclusive: it is the last day of membership. A pure ticker
  rename is one `:Asset` named by its latest symbol (Work item 23).
- 59 assets stay without `:classifiedAs` on purpose: the 56 closed stints of
  2019–2021 with no GICS source (above), plus the temporary members MBC, FTRE
  and PHIN.

## 7. Limits: what this graph can and cannot answer

The status column is one of:

- **Today** — the query in this catalog answers it against the loaded schema
  and a projected backtest.
- **After the asset catalog** — the graph has the term, but not the
  per-company master data: company names, sector/industry classification,
  S&P 500 membership and the `:UniverseMembership` relation. **Loader note
  (2026-11-04):** `cli/load_universe.py` (logic in `src/kg_store/universe.py`)
  has run in `portfolio_test`; `urn:graph:universe:2026-Q4` holds the catalog
  (643 `:Asset` individuals, 584 with `:classifiedAs`; the five
  `reference.ttl` assets are additional). The sector questions (Q5 and Q11) are
  therefore **Today**. The label stays for the rows whose own live check has
  not been recorded.
- **After T-209 (retired 2026-11-04, Work item 26)** — the backtest veto
  projector. It now exists: `selection-vetoes-in-force` answers the selection
  vetoes that explain an asset's exit at a rebalance, and
  `selection-ranking-at-rebalance` answers the rank/selection side. The label
  is kept here only for the record.
- **After T-208** — the ticker-history and orchestrator-view projectors.
  Without them the graph cannot resolve a historical symbol or a run/step.
- **Never by design** — the source masks the data or the design excludes it.
  Per-asset daily returns and drifted weights are masked at the source under
  the Tiingo non-redistribution rule; weights are exposed only on decision and
  execution dates.
- **Not projected yet** — the graph has the term but no data of that kind and
  no projector is scheduled: executives of a company, the live portfolio.

### 7.1 The brief's eleven evaluation questions

The integration brief is an external, untracked document (`docs/fibo_kg/` is
gitignored); the eleven questions below are reproduced verbatim from its §6,
in its order, so the contract is self-contained and the test can pin the exact
text and the statuses.

| # | Question (Spanish) | Status | Where |
|---|---|---|---|
| Q1 | ¿Qué es una posición en el portafolio? | Today | A1-terms (:PortfolioPosition, which also states that CASH is not a position) |
| Q2 | ¿Por qué GOOGL y GOOG aparecen como dos activos? | Today | A1-terms (:Asset's own definition names these share classes; no FIBO link by design) |
| Q3 | ¿Qué es el S&P 500 y cómo se relaciona con el universo de activos? | Today for the definitions (:Universe, :UniverseMembership); After the asset catalog for the :SP500Index individual and its FIBO EquityIndex link, which the asset loader writes | A1-terms and A2 by Spanish label "índice bursátil de renta variable" |
| Q4 | ¿Qué precio de cierre usa el sistema? ¿Está ajustado por dividendos? | Today | A1-terms (:PriceObservation says: split-adjusted close, not dividend-adjusted, price-only return) plus A2 for "precio de cierre" and "precio de cierre ajustado" (FIBO terms with no link, because FIBO's adjusted close includes dividends) |
| Q5 | ¿A qué sector GICS pertenece X y qué significa? | Today: the meaning from A1-terms, and the sector of a given asset from `sector-of-asset` | A1-terms; `sector-of-asset` |
| Q6 | ¿Qué es un informe 10-K y quién lo recibe? | Today | A1-terms (:SECFiling) plus A2 for "comisión de bolsa y valores de ee. uu. (sec)" |
| Q7 | ¿Qué papel tiene X en la empresa Y? | Not projected yet (needs :Executive individuals from DEF 14A; no projector exists or is scheduled) | A1-terms for the class :Executive only |
| Q8 | ¿Qué es la volatilidad y cómo la usa el sistema? | Today (A2 for "volatilidad" plus the VOLATILITY_SHOCK and BREAK_TREND_200 rules in the rule-catalog query) | A2-volatilidad; the rule catalog query |
| Q9 | (control) ¿Por qué salió X del portafolio? | Today: GUARD cuts via `cut-explanation`; selection vetoes at a rebalance via `selection-vetoes-in-force` | `cut-explanation`; `selection-vetoes-in-force` |
| Q10 | (control) ¿Cuántas posiciones tiene el portafolio actual? | Not projected yet for the live portfolio (v_portfolio_position has no projector); for a backtest book, the number of equities per day is :nEquity on BookDailyPerformance (Today) and must NOT be presented as the live portfolio | n-equity-per-arm-on-last-day (new query) |
| Q11 | (control) ¿Qué empresas del portafolio son bancos o aseguradoras? | Today (industries Banks and Insurance come from the GICS classification of the assets, never from FIBO); the brief states the answer must not change with the FIBO slice | `held-tickers-by-window-industry` (change its `VALUES` for other industries) |

### 7.2 The backtest questions

| # | Question (Spanish) | Status | Where |
|---|---|---|---|
| B1 | ¿Cómo se comportó cada brazo en cada ventana y segmento? | Today | `performance-window-arm-segment` |
| B2 | ¿Qué alertas GUARD se dispararon por ventana, mes y regla? | Today | `guard-alerts-window-month-rule` |
| B3 | ¿Cuál fue el NAV más reciente de cada brazo conocido en la fecha D? | Today | `latest-nav-known-on-date` |
| B4 | ¿Qué tickers cortó más veces la capa 1? | Today | `layer1-cut-tickers` |
| B5 | ¿Por qué se cortó un activo? | Today: GUARD cuts via `cut-explanation`; selection/veto exits via `selection-vetoes-in-force` | `cut-explanation`; `selection-vetoes-in-force` |
| B6 | ¿Qué fechas de conocimiento tienen los libros? | Today | `book-knowledge-dates` |
| B7 | ¿Qué propiedades exponen `BookWeightDaily` y `BookDailyPerformance`? | Today (and it shows what is absent) | `book-weight-daily-properties` |
| B8 | ¿Cuántos pesos hay por ventana y brazo? | Today | `weight-scale` |

### 7.3 The boundary in one paragraph

A term query answers *what a thing means*; it never answers *why this asset
was in or out of a portfolio*. The reason is a `:Veto` (selection), a
`:GuardAlert`/`:GuardAction` pair (protection) or a `:BookRebalance` record,
and it is answered by the data queries in §5: `cut-explanation` for GUARD
cuts and `selection-vetoes-in-force` for selection vetoes. Asking `A1` for `:Veto` and reading the FIBO definition does not tell
the agent why a specific asset was excluded; asking `cut-explanation` does not
tell it what a stop loss means. The two surfaces are complementary and must
not be substituted for each other.

The brief's control rule: the answers to questions 9 to 11 must not change
with or without the FIBO slice.

## 8. Keeping the catalog true

`tests/test_query_catalog.py`:

1. parses every `<!-- q:NAME expect:... -->` tag and the `sparql` block that
   follows it, and fails if a `sparql` block has no tag or a tag has no block;
2. builds one in-memory `rdflib.Dataset` with GraphDB's default union from
   `schema/tbox.ttl` (`urn:graph:tbox`), `schema/fibo.ttl`
   (`urn:graph:reference:fibo`), `schema/rules.ttl`
   (`urn:graph:rules:catalog`) and `schema/reference.ttl`
   (`urn:graph:reference`), plus a synthetic `urn:graph:universe:2026-Q4`
   that reproduces the real split: `:Asset` and `:classifiedAs` in the quarter
   graph, the `:Industry`/`:Sector` taxonomy in `urn:graph:reference`, and one
   asset (`AAPL`) in both graphs for the T-225 overlap; the same universe graph
   holds one rename chain (the `FB` stint ends on 2022-06-08, inclusive, and
   the `META` stint starts on 2022-06-09 on the one `:META` asset); plus two
   run labels (`rule`, `champ_v1`) across two windows of the synthetic
   backtest scenario, projected with `projection.backtest.project`, and a
   dedicated composition dataset with a classified holding, a catalog asset
   without `:classifiedAs` and an unlinked ticker;
3. runs every query and checks its expectation: an exact row count, a
   non-empty result, or a named rule (`expect:rule=...`);
4. checks the no-FIBO rows in `A1` (`:Asset`, `:Universe`,
   `:UniverseMembership`, `:PriceObservation`, `:Executive`) stay unbound
   while exactly five of the ten terms carry a FIBO link, and that no
   property named like a drifted weight or a per-asset daily return appears
   on `BookWeightDaily`/`BookDailyPerformance`;
5. checks that the limits table still lists the eleven evaluation questions
   verbatim and the eight backtest questions, and that the statuses use the
   six labels above;
6. runs the performance, GUARD, NAV and sector queries once per label and
   proves the `"rule"` and `"champ_v1"` results do not mix when the label
   filter is applied, and that `runs-available` lists both labels and both
   windows;
7. checks the sector promises: the P1 layer-1 cuts equal the layer-1 `"ENTER"`
   alert count; the composition weights plus CASH sum to 1, including an
   `unclassified` bucket for both an asset without `:classifiedAs` and a ticker
   without `:holdingAsset`; the Banks/Insurance query lists the expected
   tickers; the coverage counts separate held, linked and classified tickers;
   the unclassified query groups the closed memberships by year; and
   `sector-of-asset` returns one row for a catalog asset and for `AAPL`, the
   Spanish sector note when present, and no row for an unclassified asset;
8. has a negative test for the single-graph trap: the correct cross-graph
   `SELECT DISTINCT` returns more rows than the same pattern in either one
   graph, and the un-deduplicated union returns `AAPL` twice.

The test is hermetic: it reads the committed `.ttl` files and the synthetic
fixture, never a live GraphDB repository and never a real backtest database.
If a query is added to this document, add its tag and its expectation in the
same change; if a graph is renamed, change the one prefix filter in every
query and the test will tell you which block still runs.
