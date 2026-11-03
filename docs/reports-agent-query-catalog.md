# Reports-agent query catalog

The contract between this knowledge graph and the reports agent: the SPARQL
queries that answer the questions the agent receives, the questions the graph
cannot answer, and the limits of what a term definition can prove. The
catalog is executable: every fenced `sparql` block below is tagged with
`<!-- q:NAME expect:... -->` and is run by `tests/test_query_catalog.py`
against the schema bundle and the synthetic two-window backtest of
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
| `urn:graph:derived:backtest:*` | one append-only graph per completed run | `GRAPH ?g { ... } FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))` |

The backtest graph's full name is
`urn:graph:derived:backtest:{window_id}:{backtest_run_id}`. **Do not hardcode
the run id.** Bind the graph with `GRAPH ?g` and the prefix filter above, and
select the window with `:windowId`, not with a substring of the graph name. A
later change to the graph naming then changes the filter in one place, not
every query. The synthetic test projects two windows whose run and book ids
collide (`P1:1` and `P2:1`), so a query that confuses the window with the graph
name fails there.

Inside a `GRAPH`, `OPTIONAL` is scoped to that graph. An `OPTIONAL` that must
add a FIBO definition to a term has to hold **both** the `:term rdfs:seeAlso
?fibo` pattern and the FIBO lookup; splitting them into two `OPTIONAL`s makes
the FIBO branch independent and cross-joins every FIBO entry. Query `A1` below
is the template.

## 2. Appendix A — what a term means

### A1. One or more of our terms, with the FIBO link in the same `OPTIONAL`

`A1` explains several of our terms at once. `:Asset` deliberately has no FIBO
link: one `:Asset` is one ticker symbol, not one company, so FIBO's
`LegalPerson`/`PubliclyHeldCompany` would misstate multi-class companies and
reused tickers. The `:Asset` row therefore comes back with every `?fibo*`
variable unbound; it is not dropped, and it does not cross-join the glossary.

<!-- q:A1-terms expect:6 -->

```sparql
PREFIX :     <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?labelEs ?defEs ?fibo ?fiboLabelEs ?fiboDefEs ?fiboDef
WHERE {
  VALUES ?term { :Portfolio :PortfolioPosition :Sector :Industry :SECFiling :Asset }

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

## 5. The backtest battery

Every query in this section binds the graph with `GRAPH ?g` and filters it
with `STRSTARTS(STR(?g), "urn:graph:derived:backtest:")`. Every query that
answers a per-window question selects the window with `:windowId` (directly,
or through the action's book or the weight's book); the property inventory in
§5.7 deliberately spans both windows. None names a run id or a graph suffix.

### 5.1 Performance per window, arm and segment

One row per `:PortfolioPeriodSummary`. The fixture has a summary for
`MARKOWITZ_BASE` and `TOPN_MV_GUARD_NO_NLP` in each of the two windows; the
no-guard arm has none in the synthetic scenario, which is why the query returns
four rows rather than six.

<!-- q:performance-window-arm-segment expect:4 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?arm ?segment ?cumulativeReturn ?annualizedReturn ?exPostSharpe
WHERE {
  GRAPH ?g {
    ?summary a :PortfolioPeriodSummary ;
      :windowId ?window ; :armCode ?arm ; :segment ?segment ;
      :cumulativeReturn ?cumulativeReturn ;
      :annualizedReturn ?annualizedReturn ;
      :exPostSharpe ?exPostSharpe .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
ORDER BY ?window ?arm
```

### 5.2 GUARD alerts by window, month and rule

The month is derived from `:alertDate`; the window is the `:windowId` filter.
The example keeps `P1` and February 2022. Change both filters for another
window or month; the join to the rule catalog is what turns an alert into a
rule id.

<!-- q:guard-alerts-window-month-rule expect:5 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?month ?ruleId (COUNT(?alert) AS ?alerts)
WHERE {
  GRAPH ?g {
    ?alert a :GuardAlert ; :windowId ?window ; :alertDate ?date ; :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :ruleId ?ruleId . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  FILTER (?window = "P1")
  BIND (SUBSTR(STR(?date), 1, 7) AS ?month)
  # February 2022 is the synthetic scenario's whole alert window.
  FILTER (?month = "2022-02")
}
GROUP BY ?window ?month ?ruleId
ORDER BY ?ruleId
```

### 5.3 Latest NAV per arm known on a date D

The knowledge date is `:knowledgeDate`, not the performance date. A row whose
`:knowledgeDate` is after `D` did not exist for the agent on `D` and must not
be used, even if its `:performanceDate` is earlier. Change the two occurrences
of `D` together; the inner `NOT EXISTS` picks the latest performance date among
the rows known by `D`.

<!-- q:latest-nav-known-on-date expect:3 -->

```sparql
PREFIX :   <https://thesis.local/kg/portfolio#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?arm ?date ?nav
WHERE {
  GRAPH ?g {
    ?perf a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
      :performanceDate ?date ; :nav ?nav ; :knowledgeDate ?known .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  FILTER (?window = "P1")
  # D = 2022-01-06
  FILTER (?known <= "2022-01-06"^^xsd:date)
  FILTER NOT EXISTS {
    GRAPH ?g2 {
      ?later a :BookDailyPerformance ; :windowId ?window ; :armCode ?arm ;
        :performanceDate ?laterDate ; :knowledgeDate ?laterKnown .
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
counterfactuals, not cuts, and are excluded. The count is grouped by window
(the window comes from the action's book), so the same ticker cut once in
each window appears once per window rather than as a single count of 2.

<!-- q:layer1-cut-tickers expect:2 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?ticker (COUNT(?action) AS ?cuts)
WHERE {
  GRAPH ?g {
    ?action a :GuardAction ; :actionAlert ?alert ; :guardTicker ?ticker ;
      :status "APPLIED" ; :actionOfBook ?book .
    ?book :windowId ?window .
    ?alert :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :guardLayer 1 . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
GROUP BY ?window ?ticker
ORDER BY ?window DESC(?cuts) ?ticker
```

### 5.5 One end-to-end explanation of a cut

This is the report's "why was AAA cut?" answer: the alert, its rule id and the
rule's own note, and the action status per arm. The alert has no direct book
link; the action is the bridge. In the synthetic scenario alert 1 is a
layer-1 stop loss on `AAA`, applied on `MARKOWITZ_BASE` and registered as
`ARM_DISABLED` on `TOPN_MV_NOGUARD`.

<!-- q:cut-explanation expect:rule=L1_STOP_LOSS -->

```sparql
PREFIX :    <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?window ?alert ?ruleId ?ruleNote ?arm ?status
WHERE {
  GRAPH ?g {
    ?alert a :GuardAlert ; :alertId 1 ; :windowId ?window ; :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> {
    ?rule :ruleId ?ruleId ; rdfs:comment ?ruleNote .
  }
  OPTIONAL {
    GRAPH ?g2 {
      ?action a :GuardAction ; :actionAlert ?alert ; :armCode ?arm ; :status ?status .
    }
    FILTER (STRSTARTS(STR(?g2), "urn:graph:derived:backtest:"))
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
  FILTER (?window = "P1")
}
ORDER BY ?arm ?status
```

### 5.6 The knowledge dates of the books

One row per book (window × arm), with the first and last `:knowledgeDate`.
This is the transaction-time answer to "what did the agent know when?"; it is
not a valid-time interval.

<!-- q:book-knowledge-dates expect:6 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?arm (MIN(?known) AS ?firstKnown) (MAX(?known) AS ?lastKnown)
WHERE {
  GRAPH ?g {
    ?book a :StrategyBook ; :windowId ?window ; :armCode ?arm ;
      :knowledgeDate ?known .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
GROUP BY ?window ?arm
ORDER BY ?window ?arm
```

### 5.7 The full property list of `BookWeightDaily` and `BookDailyPerformance`

This query lists every predicate actually present on the two classes, with a
count. It is the evidence that the graph has **no** per-asset daily return and
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

The Workbench timing query. `:BookWeightDaily` has no `:windowId` of its own;
the window comes from `:weightOfBook` → `:StrategyBook :windowId`. The result
is one row per window × arm, with the count of weight rows the window's graph
holds.

<!-- q:weight-scale expect:6 -->

```sparql
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT ?window ?arm (COUNT(?weight) AS ?weights)
WHERE {
  GRAPH ?g {
    ?weight a :BookWeightDaily ; :armCode ?arm ; :weightOfBook ?book .
    ?book :windowId ?window .
  }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
GROUP BY ?window ?arm
ORDER BY ?window ?arm
```

## 6. Limits: what this graph can and cannot answer

The status column is one of:

- **Today** — the query in this catalog answers it against the loaded schema
  and a projected backtest.
- **After the asset catalog** — the graph has the term, but not the
  per-company master data: company names, sector/industry classification,
  S&P 500 membership and the `:UniverseMembership` relation.
- **After T-209** — the backtest veto projector. Without it the graph knows
  GUARD cuts but not the selection vetoes that explain an asset's exit at a
  rebalance.
- **After T-208** — the ticker-history and orchestrator-view projectors.
  Without them the graph cannot resolve a historical symbol or a run/step.
- **Never by design** — the source masks the data or the design excludes it.
  Per-asset daily returns and drifted weights are masked at the source under
  the Tiingo non-redistribution rule; weights are exposed only on decision and
  execution dates.

### 6.1 The brief's eleven evaluation questions

The integration brief is an external, untracked document (`docs/fibo_kg/` is
gitignored); this table is the catalog's record of the eleven questions its
§6 asks the reports agent to answer, kept here so the contract is
self-contained and the test can pin the count and the statuses.

| # | Question (Spanish) | Status | Where |
|---|---|---|---|
| Q1 | ¿Qué es un portafolio y qué es una posición del portafolio? | Today | `A1-terms` |
| Q2 | ¿Qué es un sector y qué es una industria? | Today (the terms); after the asset catalog (which companies belong to each) | `A1-terms`; asset catalog |
| Q3 | ¿Qué es un documento presentado ante la SEC y qué formularios cubre? | Today | `A1-terms` |
| Q4 | ¿Qué es un activo y por qué no es exactamente una empresa? | Today (the definition, with no FIBO row by design) | `A1-terms` |
| Q5 | ¿Qué es la volatilidad? | Today | `A2-volatilidad` |
| Q6 | ¿Qué es el Sharpe y qué mide un resumen de período? | Today (our own `@es` definition; FIBO has no Sharpe term) | `fibo-missing-sharpe` |
| Q7 | ¿Qué empresas están en el S&P 500 y cuál es su relación de pertenencia al universo, con símbolo, nombre, sector e industria? | After the asset catalog | asset catalog and `:UniverseMembership` |
| Q8 | ¿Cómo se comportó cada brazo en cada ventana y segmento? | Today | `performance-window-arm-segment` |
| Q9 | ¿Por qué salió un activo en un rebalanceo? | After T-209 (GUARD cuts are already explainable today) | `cut-explanation` today; T-209 for selection vetoes |
| Q10 | ¿Qué símbolo tenía una empresa en una fecha pasada y qué pasos ejecutó el orquestador? | After T-208 | ticker-history and orchestrator views |
| Q11 | ¿Cuál fue el retorno diario de un activo y cómo derivó su peso entre rebalanceos? | Never by design | `book-weight-daily-properties` shows the absence |

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

### 6.3 The boundary in one paragraph

A term query answers *what a thing means*; it never answers *why this asset
was in or out of a portfolio*. The reason is a `:Veto` (selection), a
`:GuardAlert`/`:GuardAction` pair (protection) or a `:BookRebalance` record,
and it is answered by the data queries in §5 or, for selection vetoes, after
T-209. Asking `A1` for `:Veto` and reading the FIBO definition does not tell
the agent why a specific asset was excluded; asking `cut-explanation` does not
tell it what a stop loss means. The two surfaces are complementary and must
not be substituted for each other.

## 7. Keeping the catalog true

`tests/test_query_catalog.py`:

1. parses every `<!-- q:NAME expect:... -->` tag and the `sparql` block that
   follows it, and fails if a `sparql` block has no tag or a tag has no block;
2. builds one in-memory `rdflib.Dataset` from `schema/tbox.ttl`
   (`urn:graph:tbox`), `schema/fibo.ttl` (`urn:graph:reference:fibo`),
   `schema/rules.ttl` (`urn:graph:rules:catalog`) and `schema/reference.ttl`
   (`urn:graph:reference`), plus the two windows of the synthetic backtest
   scenario, projected with `projection.backtest.project`;
3. runs every query and checks its expectation: an exact row count, a
   non-empty result, or a named rule (`expect:rule=...`);
4. checks the two extra facts the catalog promises: `:Asset` has no FIBO row
   in `A1`, and no property named like a drifted weight or a per-asset daily
   return appears on `BookWeightDaily`/`BookDailyPerformance`;
5. checks that the limits table still lists eleven evaluation questions and
   the eight backtest questions, and that the statuses use the five labels
   above.

The test is hermetic: it reads the committed `.ttl` files and the synthetic
fixture, never a live GraphDB repository and never a real backtest database.
If a query is added to this document, add its tag and its expectation in the
same change; if a graph is renamed, change the one prefix filter in every
query and the test will tell you which block still runs.
