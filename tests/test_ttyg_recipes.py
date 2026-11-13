"""The investor recipes are bounded, schema-backed and executable on a synthetic graph.

The file extracts every ``<!-- recipe: ID -->`` SPARQL block from
``docs/ttyg/investor-recipes.md``, parses it with rdflib, rejects prices/levels and the five removed
GUARD rules, verifies every local IRI against the schema bundle, checks R1-R9, and runs the
available-now recipes that the catalogue requires against a small in-memory graph. No GraphDB
repository, pilot database or external file is used.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
import rdflib
from rdflib.namespace import RDF, XSD
from rdflib.plugins.sparql import prepareQuery

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "schema"
DOC = REPO / "docs" / "ttyg" / "investor-recipes.md"
NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)

RECIPE_BLOCK = re.compile(
    r"<!--\s*recipe:\s*(?P<name>C\d+[a-z]?)\s*-->\s*```sparql\n(?P<query>.*?)```",
    re.DOTALL,
)
SPARQL_BLOCK = re.compile(r"```sparql\n.*?```", re.DOTALL)
REFUSAL_ROW = re.compile(r"^\|\s*(R\d+)\s*\|", re.MULTILINE)

SCHEMA_FILES = (
    ("tbox.ttl", "urn:graph:tbox"),
    ("shapes.ttl", "urn:graph:tbox"),
    ("rules.ttl", "urn:graph:rules:catalog"),
    ("labels.ttl", "urn:graph:labels"),
)

FORBIDDEN_PROPERTIES = re.compile(
    r":(?:closePrice|dailyReturnPct|alertValue|alertThreshold|marketCapitalization|"
    r"enterpriseValue|enterpriseFcfYield|freeCashFlowYield|sbcAdjustedFcfYield|"
    r"stopLevel|stopPrice|price|close)\b"
)
FORBIDDEN_RULES = re.compile(r"\b(?:L1_STOP_LOSS|L1_REENTRY|L2_NEWS|L3_VOL|L4_DD)\b")
LOCAL_IRI = re.compile(r"(?<![A-Za-z0-9_:]):([A-Za-z_][A-Za-z0-9_]*)")

UNIVERSE_GRAPH = "urn:graph:universe:2026-Q4"
FUNDAMENTALS_GRAPH = "urn:graph:derived:fundamentals:final"
BOOK_GRAPH = "urn:graph:derived:backtest:final:P1:system_with_hierarchy"
SELECTION_GRAPH = "urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy"


def _document() -> str:
    return DOC.read_text(encoding="utf-8")


def _recipes() -> dict[str, str]:
    return {
        match.group("name"): match.group("query") for match in RECIPE_BLOCK.finditer(_document())
    }


def _query(name: str) -> str:
    recipes = _recipes()
    assert name in recipes, f"{name}: no tagged recipe in {DOC}"
    return recipes[name]


def _schema_terms() -> set[str]:
    terms: set[str] = set()
    for file_name, _graph_name in SCHEMA_FILES:
        graph = rdflib.Graph()
        graph.parse(SCHEMA / file_name, format="turtle")
        for subject, predicate, obj in graph:
            for term in (subject, predicate, obj):
                if isinstance(term, rdflib.URIRef) and str(term).startswith(NS):
                    terms.add(str(term)[len(NS) :])
    return terms


def _local_iris(query: str) -> set[str]:
    without_prefixes = re.sub(r"^\s*PREFIX.*$", "", query, flags=re.MULTILINE)
    without_comments = re.sub(r"^\s*#.*$", "", without_prefixes, flags=re.MULTILINE)
    without_strings = re.sub(r'"[^"]*"', '""', without_comments)
    return set(LOCAL_IRI.findall(without_strings))


def test_every_sparql_block_is_tagged_and_parses() -> None:
    document = _document()
    assert len(SPARQL_BLOCK.findall(document)) == len(RECIPE_BLOCK.findall(document))
    recipes = _recipes()
    assert {f"C{number}" for number in range(1, 21)} <= {
        name.rstrip("abcdefghijklmnopqrstuvwxyz") for name in recipes
    }
    for name, query in recipes.items():
        prepareQuery(query)
        assert re.search(r"\bLIMIT\s+\d+", query, re.IGNORECASE), name
        assert "GRAPH" in query, name
        assert "?s ?p ?o" not in query, name


def test_every_recipe_iri_exists_in_the_schema_bundle() -> None:
    terms = _schema_terms()
    for name, query in _recipes().items():
        unknown = sorted(_local_iris(query) - terms)
        assert not unknown, f"{name}: unknown local IRI(s): {', '.join(unknown)}"


def test_no_recipe_reads_a_price_or_an_old_rule() -> None:
    for name, query in _recipes().items():
        assert not FORBIDDEN_PROPERTIES.search(query), name
        assert not FORBIDDEN_RULES.search(query), name
        assert "MARKOWITZ_MV" not in query, name
    # The mask flag itself is the one allowed property with "price" in its name.
    assert "pricesNotPublished" in _document()


def test_the_refusal_table_is_exactly_r1_to_r9() -> None:
    assert REFUSAL_ROW.findall(_document()) == [f"R{number}" for number in range(1, 10)]


def _rows(dataset: rdflib.Dataset, name: str) -> list[rdflib.query.ResultRow]:
    result = dataset.query(_query(name))
    return [row for row in result if isinstance(row, rdflib.query.ResultRow)]


def _literal(value: object) -> str:
    return str(value)


@pytest.fixture(scope="module")
def recipe_dataset() -> rdflib.Dataset:  # noqa: PLR0915 -- one synthetic graph
    dataset = rdflib.Dataset(default_union=False)
    for file_name, graph_name in (
        ("tbox.ttl", "urn:graph:tbox"),
        ("rules.ttl", "urn:graph:rules:catalog"),
        ("reference.ttl", "urn:graph:reference"),
        ("labels.ttl", "urn:graph:labels"),
    ):
        dataset.graph(rdflib.URIRef(graph_name)).parse(SCHEMA / file_name, format="turtle")

    universe = dataset.graph(rdflib.URIRef(UNIVERSE_GRAPH))
    fundamentals = dataset.graph(rdflib.URIRef(FUNDAMENTALS_GRAPH))
    book = dataset.graph(rdflib.URIRef(BOOK_GRAPH))
    selection = dataset.graph(rdflib.URIRef(SELECTION_GRAPH))

    def date(value: str) -> rdflib.Literal:
        return rdflib.Literal(value, datatype=XSD.date)

    def decimal(value: str) -> rdflib.Literal:
        return rdflib.Literal(Decimal(value))

    for asset, ticker, industry in (
        (KG.AAA, "AAA", KG.Ind_Banks),
        (KG.BBB, "BBB", KG.Ind_SoftwareServices),
        (KG.CCC, "CCC", KG.Ind_Banks),
    ):
        universe.add((asset, RDF.type, KG.Asset))
        universe.add((asset, KG.tickerSymbol, rdflib.Literal(ticker)))
        universe.add((asset, KG.classifiedAs, industry))

    for asset, ticker, score, roic, debt, generated in (
        (KG.AAA, "AAA", "80", "0.20", "0.5", True),
        (KG.BBB, "BBB", "20", "0.02", "2.0", False),
    ):
        filing = KG[f"Filing_{ticker}"]
        metrics = KG[f"MetricSet_{ticker}"]
        assessment = KG[f"Assessment_{ticker}"]
        fundamentals.add((filing, RDF.type, KG.SECFiling))
        fundamentals.add((filing, KG.filingOfAsset, asset))
        fundamentals.add((filing, KG.availableAt, date("2022-01-05")))
        fundamentals.add((filing, KG.periodEnd, date("2021-12-31")))
        fundamentals.add((filing, KG.formType, rdflib.Literal("10-K")))
        fundamentals.add((metrics, RDF.type, KG.FundamentalMetricSet))
        fundamentals.add((metrics, KG.metricSetOfFiling, filing))
        fundamentals.add((metrics, KG.availableAt, date("2022-01-05")))
        fundamentals.add((metrics, KG.returnOnInvestedCapital, decimal(roic)))
        fundamentals.add((metrics, KG.debtToEquity, decimal(debt)))
        fundamentals.add((assessment, RDF.type, KG.FundamentalAssessment))
        fundamentals.add((assessment, KG.assessmentOfFiling, filing))
        fundamentals.add((assessment, KG.assessmentOfAsset, asset))
        fundamentals.add((assessment, KG.availableAt, date("2022-01-05")))
        fundamentals.add((assessment, KG.scoreRaw0to100, decimal(score)))
        fundamentals.add(
            (
                assessment,
                KG.rating,
                rdflib.Literal("bullish" if int(score) >= 50 else "bearish"),
            )
        )
        fundamentals.add((assessment, KG.generatedByLanguageModel, rdflib.Literal(generated)))

    fundamentals.add((KG.BBB, KG.pricesNotPublished, rdflib.Literal(True)))

    book.add((KG.BookSH, RDF.type, KG.StrategyBook))
    book.add((KG.BookSH, KG.runLabel, rdflib.Literal("final")))
    book.add((KG.BookSH, KG.windowId, rdflib.Literal("P1")))
    book.add((KG.BookSH, KG.armCode, rdflib.Literal("TOPN_MV_GUARD_NO_NLP")))
    for asset, weight in ((KG.AAA, "0.4"), (KG.BBB, "0.3"), (KG.CCC, "0.2")):
        row = KG[f"Weight_{str(asset).rsplit('#', 1)[-1]}"]
        book.add((row, RDF.type, KG.BookWeightDaily))
        book.add((row, KG.weightOfBook, KG.BookSH))
        book.add((row, KG.weightDate, date("2022-06-30")))
        book.add((row, KG.holdingAsset, asset))
        book.add((row, KG.finalTargetWeight, decimal(weight)))

    selection.add((KG.Cycle1, RDF.type, KG.SelectionCycle))
    selection.add((KG.Cycle1, KG.runLabel, rdflib.Literal("final")))
    selection.add((KG.Cycle1, KG.windowId, rdflib.Literal("P1")))
    selection.add((KG.Cycle1, KG.runAsOf, date("2022-06-30")))
    selection.add((KG.V1, RDF.type, KG.Veto))
    selection.add((KG.V1, KG.vetoOfAsset, KG.AAA))
    selection.add((KG.V1, KG.vetoTicker, rdflib.Literal("AAA")))
    selection.add((KG.V1, KG.appliesRule, KG.Rule_LEVERAGE_EXTREME))
    selection.add((KG.V1, KG.raisedOn, date("2022-01-01")))
    selection.add((KG.V1, KG.vetoSeverity, rdflib.Literal("HARD")))
    for name, asset, ticker, selected, vetoed in (
        ("S1", KG.AAA, "AAA", False, True),
        ("S2", KG.BBB, "BBB", True, False),
    ):
        snapshot = KG[name]
        selection.add((snapshot, RDF.type, KG.AttractivenessSnapshot))
        selection.add((snapshot, KG.runLabel, rdflib.Literal("final")))
        selection.add((snapshot, KG.windowId, rdflib.Literal("P1")))
        selection.add((snapshot, KG.rankingOfCycle, KG.Cycle1))
        selection.add((snapshot, KG.attractivenessOfAsset, asset))
        selection.add((snapshot, KG.rankingTicker, rdflib.Literal(ticker)))
        selection.add((snapshot, KG.selectedForBook, rdflib.Literal(selected)))
        selection.add((snapshot, KG.vetoedAtRanking, rdflib.Literal(vetoed)))
    return dataset


def test_c4_agrees_and_disagrees_with_the_assessment(recipe_dataset: rdflib.Dataset) -> None:
    high = _rows(recipe_dataset, "C4a")
    assert len(high) == 1
    assert _literal(high[0]["ticker"]) == "AAA"
    assert _literal(high[0]["ruleId"]) == "LEVERAGE_EXTREME"
    assert _literal(high[0]["score"]) == "80"
    assert _literal(high[0]["generatedByLanguageModel"]) == "true"
    low = _rows(recipe_dataset, "C4b")
    assert len(low) == 1
    assert _literal(low[0]["ticker"]) == "BBB"
    assert _literal(low[0]["score"]) == "20"
    assert _literal(low[0]["pricesNotPublished"]) == "true"


def test_c9_reports_the_top_weights_and_concentration(recipe_dataset: rdflib.Dataset) -> None:
    top = _rows(recipe_dataset, "C9a")
    assert [_literal(row["ticker"]) for row in top] == ["AAA", "BBB", "CCC"]
    assert _literal(top[0]["weight"]) == "0.4"
    summary = _rows(recipe_dataset, "C9b")
    assert len(summary) == 1
    assert _literal(summary[0]["positions"]) == "3"
    assert _literal(summary[0]["hhi"]) == "0.29"
    sectors = _rows(recipe_dataset, "C9c")
    assert _literal(sectors[0]["bucket"]) == "Financials"
    assert _literal(sectors[0]["sectorWeight"]) == "0.6"


def test_c13_reads_only_what_was_available_on_the_date(
    recipe_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(recipe_dataset, "C13")
    assert len(rows) == 1
    row = rows[0]
    assert _literal(row["formType"]) == "10-K"
    assert _literal(row["periodEnd"]) == "2021-12-31"
    assert _literal(row["availableAt"]) == "2022-01-05"
    assert Decimal(_literal(row["roic"])) == Decimal("0.2")
    assert Decimal(_literal(row["debt"])) == Decimal("0.5")
    assert _literal(row["score"]) == "80"
    assert _literal(row["generatedByLanguageModel"]) == "true"
    assert _literal(row["pricesNotPublished"]) == "false"


def test_c18_names_the_weak_signals_and_the_mask(recipe_dataset: rdflib.Dataset) -> None:
    rows = _rows(recipe_dataset, "C18")
    assert len(rows) == 1
    row = rows[0]
    assert _literal(row["ticker"]) == "BBB"
    assert _literal(row["pricesNotPublished"]) == "true"
    assert _literal(row["reason"]) == "low ROIC; high debt; low assessment"


def test_c20_counts_filings_and_assessments_per_holding(
    recipe_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(recipe_dataset, "C20")
    assert len(rows) == 3
    by_ticker = {_literal(row["ticker"]): row for row in rows}
    assert _literal(by_ticker["AAA"]["filings"]) == "1"
    assert _literal(by_ticker["AAA"]["assessments"]) == "1"
    assert _literal(by_ticker["AAA"]["pricesNotPublished"]) == "false"
    assert _literal(by_ticker["BBB"]["filings"]) == "1"
    assert _literal(by_ticker["BBB"]["pricesNotPublished"]) == "true"
    assert _literal(by_ticker["CCC"]["filings"]) == "0"
    assert _literal(by_ticker["CCC"]["assessments"]) == "0"
