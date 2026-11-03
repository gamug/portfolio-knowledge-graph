"""The reports-agent query catalog is executable (T-240-T-243).

Every fenced ``sparql`` block in ``docs/reports-agent-query-catalog.md`` carries an HTML comment
``<!-- q:NAME expect:... -->``. This test parses those tags, builds one in-memory
:class:`rdflib.Dataset` from the schema graphs and the two-window synthetic backtest scenario of
``tests/fixtures/backtest_rows.py``, and runs every query against it. A query added to the doc
without a tag, a tag without its block, or a result that no longer matches its expectation fails.

The dataset is hermetic: committed ``.ttl`` files and synthetic rows only, never a live GraphDB
repository and never a real backtest database.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db, load_catalog
from rdflib.query import ResultRow
from rdflib.term import URIRef

from projection.backtest import VIEWS, Projection, project, read_view
from projection.source import FinancialSource

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "schema"
CATALOG = REPO / "docs" / "reports-agent-query-catalog.md"

NS = "https://thesis.local/kg/portfolio#"

#: ``<!-- q:NAME expect:... -->`` immediately followed by its fenced block.
TAGGED_QUERY = re.compile(
    r"<!--\s*q:(?P<name>[A-Za-z0-9_.-]+)\s+expect:(?P<expect>[^\s]+)\s*-->"
    r"\s*```sparql\n(?P<query>.*?)```",
    re.DOTALL,
)
SPARQL_BLOCK = re.compile(r"```sparql\n.*?```", re.DOTALL)
TABLE_ROW = re.compile(r"^\| (Q\d+) \| (.+?) \| (.+?) \| (.+?) \|$", re.MULTILINE)
BACKTEST_ROW = re.compile(r"^\| (B\d+) \|", re.MULTILINE)

#: Names the test expects. A rename in the doc without a rename here fails, so the catalog cannot
#: grow an untested query by accident.
EXPECTED_NAMES = frozenset(
    {
        "A1-terms",
        "A2-volatilidad",
        "fibo-missing-sharpe",
        "active-rules",
        "performance-window-arm-segment",
        "guard-alerts-window-month-rule",
        "latest-nav-known-on-date",
        "layer1-cut-tickers",
        "cut-explanation",
        "book-knowledge-dates",
        "book-weight-daily-properties",
        "weight-scale",
    }
)

#: The backtest queries. They must not hardcode a graph name or a run id.
BACKTEST_NAMES = frozenset(
    {
        "performance-window-arm-segment",
        "guard-alerts-window-month-rule",
        "latest-nav-known-on-date",
        "layer1-cut-tickers",
        "cut-explanation",
        "book-knowledge-dates",
        "book-weight-daily-properties",
        "weight-scale",
    }
)

#: The five status labels of the limits table (brief §6).
STATUSES = (
    "Today",
    "After the asset catalog",
    "After T-209",
    "After T-208",
    "Never by design",
)


@dataclass(frozen=True)
class CatalogQuery:
    """One tagged query: its name, its expectation, and the SPARQL text."""

    name: str
    expect: str
    query: str


def _document() -> str:
    return CATALOG.read_text(encoding="utf-8")


def _catalog_queries() -> list[CatalogQuery]:
    return [
        CatalogQuery(match.group("name"), match.group("expect"), match.group("query"))
        for match in TAGGED_QUERY.finditer(_document())
    ]


def _query(name: str) -> str:
    for catalog_query in _catalog_queries():
        if catalog_query.name == name:
            return catalog_query.query
    raise AssertionError(f"{name}: no tagged query in {CATALOG}")


def _projection(tmp_path: Path, window: str) -> Projection:
    """The synthetic scenario of one window, read through its views and projected."""
    source = FinancialSource.open(backtest_db(tmp_path, window=window))
    try:
        rows = {view: read_view(source, view) for view in VIEWS}
    finally:
        source.close()
    return project(rows, ASSETS, load_catalog())


def _rows(dataset: rdflib.Dataset, query: str) -> list[ResultRow]:
    """The SELECT rows of ``query``; an ASK/GRAPH result is a test bug, not a row."""
    result = dataset.query(query)
    return [row for row in result if isinstance(row, ResultRow)]


@pytest.fixture(scope="module")
def catalog_dataset(tmp_path_factory: pytest.TempPathFactory) -> rdflib.Dataset:
    """The four schema graphs plus both synthetic backtest windows, in one in-memory dataset."""
    dataset = rdflib.Dataset()
    for path, graph_iri in (
        (SCHEMA / "tbox.ttl", "urn:graph:tbox"),
        (SCHEMA / "fibo.ttl", "urn:graph:reference:fibo"),
        (SCHEMA / "rules.ttl", "urn:graph:rules:catalog"),
        (SCHEMA / "reference.ttl", "urn:graph:reference"),
    ):
        dataset.graph(URIRef(graph_iri)).parse(path, format="turtle")

    for window in ("P1", "P2"):
        projection = _projection(tmp_path_factory.mktemp(window), window)
        for name, builder in projection.graphs.items():
            graph = dataset.graph(URIRef(name))
            for triple in builder.triples:
                graph.add(triple)
    return dataset


# --- the doc and the test cannot drift ----------------------------------------------------------


def test_every_sparql_block_has_one_tag() -> None:
    text = _document()
    queries = _catalog_queries()
    assert len(SPARQL_BLOCK.findall(text)) == len(queries)
    names = [query.name for query in queries]
    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_NAMES


def test_the_limits_table_lists_eleven_questions() -> None:
    rows = TABLE_ROW.findall(_document())
    assert [row[0] for row in rows] == [f"Q{number}" for number in range(1, 12)]
    for _, _, status, _ in rows:
        assert any(label in status for label in STATUSES), status


def test_the_backtest_table_lists_the_battery() -> None:
    assert BACKTEST_ROW.findall(_document()) == [f"B{number}" for number in range(1, 9)]


def test_the_boundary_rule_is_stated() -> None:
    text = " ".join(_document().replace(">", " ").split())
    assert "never why an asset was in or out of a portfolio" in text
    for status in STATUSES:
        assert status in text


def test_backtest_queries_do_not_name_a_graph_or_a_run() -> None:
    for name in BACKTEST_NAMES:
        query = _query(name)
        assert "GRAPH ?g" in query, name
        assert 'STRSTARTS(STR(?g), "urn:graph:derived:backtest:")' in query, name
        assert not re.search(r"urn:graph:derived:backtest:[A-Za-z0-9{]", query), name
        # The property list deliberately spans both windows: it inventories the classes, it does
        # not answer a per-window question. Every other query selects a window, directly or through
        # the book (`:weightOfBook` -> `:windowId`).
        if name != "book-weight-daily-properties":
            assert ":windowId" in query or ":weightOfBook" in query, name


# --- every tagged query runs and matches its expectation ----------------------------------------


@pytest.mark.parametrize("catalog_query", _catalog_queries(), ids=lambda item: item.name)
def test_every_query_matches_its_expectation(
    catalog_dataset: rdflib.Dataset, catalog_query: CatalogQuery
) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, catalog_query.query)
    expect = catalog_query.expect
    if expect == "nonempty":
        assert rows, f"{catalog_query.name}: the query returned no rows"
    elif expect.startswith("rule="):
        rule_id = expect.split("=", 1)[1]
        assert any(str(row["ruleId"]) == rule_id for row in rows), (
            f"{catalog_query.name}: no row carries ruleId {rule_id}"
        )
    else:
        assert len(rows) == int(expect), (
            f"{catalog_query.name}: {len(rows)} rows, expected {expect}"
        )


# --- the promises the catalog makes about specific queries --------------------------------------


def test_a1_returns_asset_without_a_fibo_row(catalog_dataset: rdflib.Dataset) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("A1-terms"))
    by_term = {str(row["term"]): row for row in rows}
    asset = by_term[f"{NS}Asset"]
    assert asset["fibo"] is None
    assert sum(1 for row in rows if row["fibo"] is not None) == 5


def test_a2_returns_the_fibo_volatility_term(catalog_dataset: rdflib.Dataset) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("A2-volatilidad"))
    assert str(rows[0]["term"]) == (
        "https://spec.edmcouncil.org/fibo/ontology/IND/Indicators/Indicators/Volatility"
    )
    assert str(rows[0]["defEs"]).startswith("Medida estadística")
    assert str(rows[0]["fiboDef"]).startswith("statistical measure")


def test_fibo_does_not_define_sharpe(catalog_dataset: rdflib.Dataset) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("fibo-missing-sharpe"))
    assert {str(row["term"]).rsplit("#", 1)[-1] for row in rows} == {
        "PortfolioPeriodSummary",
        "BacktestTest",
    }


def test_active_rules_are_ten_selection_and_five_guard(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("active-rules"))
    counts = Counter(str(row["category"]) for row in rows)
    assert counts == {"FINANCIAL": 5, "DATA_QUALITY": 1, "MARKET": 4, "GUARD": 5}
    assert sum(counts.values()) == 15


def test_the_weight_classes_expose_no_per_asset_return_or_drifted_weight(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("book-weight-daily-properties"))
    names = {str(row["property"]).rsplit("#", 1)[-1].lower() for row in rows}
    assert not any("drift" in name for name in names)
    assert not any("dailyreturn" in name or "perasset" in name for name in names)
    # The two target weights are the only weight properties; both are decision/execution values.
    assert "markowitztargetweight" in names
    assert "finaltargetweight" in names
    # The daily performance series is portfolio-level, never per asset.
    assert "nav" in names
    assert "netreturn" in names
