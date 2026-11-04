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

**Always name a `GRAPH`; never rely on the default union.** GraphDB's default
graph is the union of every named graph, so an unscoped query mixes the
ontology (`urn:graph:tbox`), the reference data (`urn:graph:reference`), the
FIBO slice (`urn:graph:reference:fibo`), the rule catalog
(`urn:graph:rules:catalog`) and every projected backtest. The symptom is
subtle: `?s a :Asset` returns the `:Asset` **class** from the TBox beside the
asset **individuals** from the reference graph, and a `?term rdfs:seeAlso
?fibo` pattern cross-joins the whole glossary unless the link and the FIBO
lookup sit in the same `OPTIONAL`. A query that works in the Workbench because
of the union returns nothing in the hermetic test, where the default graph is
empty. Scoping is therefore part of the query, not a Workbench setting.

| Graph | What it holds | How to name it |
|---|---|---|
| `urn:graph:tbox` | classes, properties, Spanish labels and definitions | `GRAPH <urn:graph:tbox> { ... }` |
| `urn:graph:reference` | GICS sectors/industries and the worked-example `:Asset`s | `GRAPH <urn:graph:reference> { ... }` |
| `urn:graph:reference:fibo` | the FIBO 2026Q2 glossary slice (54 entries) | `GRAPH <urn:graph:reference:fibo> { ... }` |
| `urn:graph:rules:catalog` | every `:RuleDefinition`, selection and GUARD | `GRAPH <urn:graph:rules:catalog> { ... }` |
| `urn:graph:derived:backtest:*` | one append-only graph per completed run family and window | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))` |
| `urn:graph:derived:ticker-history:*` | one append-only ticker-history snapshot per label and date | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:derived:ticker-history:"))` |
| `urn:graph:derived:orchestrator:*` | one append-only graph per orchestrator run | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:derived:orchestrator:"))` |

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

### 4.2 Which symbol did a company use on a date

`v_ticker_history` is projected as a dated snapshot per source label. The query picks the latest
snapshot (`urn:graph:derived:ticker-history:*`) and reads the **inclusive** interval
`validFrom <= D <= validTo`, so `D = 2022-06-08` is still the FB stint and the META stint starts
the next day. The example binds the former ticker `"FB"`; change `?symbol` for another symbol or
drop that `VALUES` and bind `?cik` instead. `?canonical` is the company's current symbol and
`?asset` is the loaded `:Asset` the row links to. A canonical symbol the catalog does not know is
resolved through the unique same-CIK asset (`FBIN` → `:FBHS`, `GAP` → `:GPS`) by the projector;
if no safe link exists `?asset` is unbound, never invented.

<!-- q:ticker-history-on-date expect:1 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?snapshot ?cik ?symbol ?canonical ?asset
WHERE {
  {
    SELECT (MAX(?candidate) AS ?snapshot)
    WHERE {
      GRAPH ?candidate { ?history a :TickerHistory }
      FILTER (STRSTARTS(STR(?candidate), "urn:graph:derived:ticker-history:"))
    }
  }
  GRAPH ?snapshot {
    ?history a :TickerHistory ;
             :tickerHistoryCik ?cik ;
             :historicalSymbol ?symbol ;
             :canonicalSymbol ?canonical ;
             :validFrom ?from .
    OPTIONAL { ?history :validTo ?to }
    OPTIONAL { ?history :tickerHistoryAsset ?asset }
  }
  # The company's former ticker; D is the last valid day of the FB stint (inclusive).
  VALUES ?symbol { "FB" }
  VALUES ?date { "2022-06-08"^^xsd:date }
  FILTER (?from <= ?date)
  FILTER (!BOUND(?to) || ?to >= ?date)
}
```

The result is one row: `FB`, canonical `META`, asset `:META`. A bare symbol lookup without the
date would also find the later META stint, so bind D; the interval predicate is the answer, not a
string comparison.

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
intentionally spans every label; the per-run queries in §5.1–§5.9 (except the
property inventory in §5.7) select one.

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

## 6. Limits: what this graph can and cannot answer

The status column is one of:

- **Today** — the query in this catalog answers it against the loaded schema
  and a projected backtest.
- **After the asset catalog** — the graph has the term, but not the
  per-company master data: company names, sector/industry classification,
  S&P 500 membership and the `:UniverseMembership` relation. **Loader note
  (2026-11-03, PR #117):** the loader exists as `cli/load_universe.py` (logic
  in `src/kg_store/universe.py`) and writes `:Asset`, `:UniverseMembership`
  and `:SP500Index`. The statuses above do not change yet: the store has not
  been loaded. They become **Today** once the maintainer has run the loader
  and the live check passes.
- **After T-209** — the backtest veto projector. Without it the graph knows
  GUARD cuts but not the selection vetoes that explain an asset's exit at a
  rebalance.
- **Today (ticker history)** — the ticker-history projector and
  `ticker-history-on-date` resolve a historical symbol and its asset. The
  orchestrator projector also exists, but the completed databases' two
  orchestrator views hold 0 rows, so there is no run/step data to query yet.
- **Never by design** — the source masks the data or the design excludes it.
  Per-asset daily returns and drifted weights are masked at the source under
  the Tiingo non-redistribution rule; weights are exposed only on decision and
  execution dates.
- **Not projected yet** — the graph has the term but no data of that kind and
  no projector is scheduled: executives of a company, the live portfolio.

### 6.1 The brief's eleven evaluation questions

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
| Q5 | ¿A qué sector GICS pertenece X y qué significa? | The meaning: Today (A1-terms :Sector). The sector of a given company: After the asset catalog | A1-terms; asset catalog |
| Q6 | ¿Qué es un informe 10-K y quién lo recibe? | Today | A1-terms (:SECFiling) plus A2 for "comisión de bolsa y valores de ee. uu. (sec)" |
| Q7 | ¿Qué papel tiene X en la empresa Y? | Not projected yet (needs :Executive individuals from DEF 14A; no projector exists or is scheduled) | A1-terms for the class :Executive only |
| Q8 | ¿Qué es la volatilidad y cómo la usa el sistema? | Today (A2 for "volatilidad" plus the VOLATILITY_SHOCK and BREAK_TREND_200 rules in the rule-catalog query) | A2-volatilidad; the rule catalog query |
| Q9 | (control) ¿Por qué salió X del portafolio? | GUARD cuts: Today; selection vetoes at a rebalance: After T-209 | cut-explanation |
| Q10 | (control) ¿Cuántas posiciones tiene el portafolio actual? | Not projected yet for the live portfolio (v_portfolio_position has no projector); for a backtest book, the number of equities per day is :nEquity on BookDailyPerformance (Today) and must NOT be presented as the live portfolio | n-equity-per-arm-on-last-day (new query) |
| Q11 | (control) ¿Qué empresas del portafolio son bancos o aseguradoras? | After the asset catalog (industries Banks and Insurance come from the GICS classification of the assets, never from FIBO); the brief states the answer must not change with the FIBO slice | note only; no query yet |

### 6.2 The backtest questions

| # | Question (Spanish) | Status | Where |
|---|---|---|---|
| B1 | ¿Cómo se comportó cada brazo en cada ventana y segmento? | Today | `performance-window-arm-segment` |
| B2 | ¿Qué alertas GUARD se dispararon por ventana, mes y regla? | Today | `guard-alerts-window-month-rule` |
| B3 | ¿Cuál fue el NAV más reciente de cada brazo conocido en la fecha D? | Today | `latest-nav-known-on-date` |
| B4 | ¿Qué tickers cortó más veces la capa 1? | Today | `layer1-cut-tickers` |
| B5 | ¿Por qué se cortó un activo? | Today for GUARD cuts; after T-209 for selection/veto exits | `cut-explanation` |
| B6 | ¿Qué fechas de conocimiento tienen los libros? | Today | `book-knowledge-dates` |
| B7 | ¿Qué propiedades exponen `BookWeightDaily` y `BookDailyPerformance`? | Today (and it shows what is absent) | `book-weight-daily-properties` |
| B8 | ¿Cuántos pesos hay por ventana y brazo? | Today | `weight-scale` |
| B9 | ¿Qué símbolo usaba la empresa X en la fecha D y a qué activo corresponde? | Today (`FB` → `META`) | `ticker-history-on-date` |

### 6.3 The boundary in one paragraph

A term query answers *what a thing means*; it never answers *why this asset
was in or out of a portfolio*. The reason is a `:Veto` (selection), a
`:GuardAlert`/`:GuardAction` pair (protection) or a `:BookRebalance` record,
and it is answered by the data queries in §5 or, for selection vetoes, after
T-209. Asking `A1` for `:Veto` and reading the FIBO definition does not tell
the agent why a specific asset was excluded; asking `cut-explanation` does not
tell it what a stop loss means. The two surfaces are complementary and must
not be substituted for each other.

The brief's control rule: the answers to questions 9 to 11 must not change
with or without the FIBO slice.

## 7. Keeping the catalog true

`tests/test_query_catalog.py`:

1. parses every `<!-- q:NAME expect:... -->` tag and the `sparql` block that
   follows it, and fails if a `sparql` block has no tag or a tag has no block;
2. builds one in-memory `rdflib.Dataset` from `schema/tbox.ttl`
   (`urn:graph:tbox`), `schema/fibo.ttl` (`urn:graph:reference:fibo`),
   `schema/rules.ttl` (`urn:graph:rules:catalog`) and `schema/reference.ttl`
   (`urn:graph:reference`), a small `urn:graph:universe:` graph with one
   rename chain, plus two run labels (`rule`, `champ_v1`) across two windows of
   the synthetic backtest scenario, projected with `projection.backtest.project`;
2a. adds one synthetic ticker-history snapshot projected with
   `projection.reference.project`, so `ticker-history-on-date` runs through the real
   `FB`→`META` data rather than a hand-written graph;
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
6. runs the performance, GUARD and NAV queries once per label and proves the
   `"rule"` and `"champ_v1"` results do not mix when the label filter is
   applied, and that `runs-available` lists both labels and both windows.

The test is hermetic: it reads the committed `.ttl` files and the synthetic
fixture, never a live GraphDB repository and never a real backtest database.
If a query is added to this document, add its tag and its expectation in the
same change; if a graph is renamed, change the one prefix filter in every
query and the test will tell you which block still runs.
