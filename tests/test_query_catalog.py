"""The reports-agent query catalog is executable (T-240-T-243).

Every fenced ``sparql`` block in ``docs/reports-agent-query-catalog.md`` carries an HTML comment
``<!-- q:NAME expect:... -->``. This test parses those tags, builds one in-memory
:class:`rdflib.Dataset` from the schema graphs, a small universe graph (one rename chain) and the
two-label, two-window synthetic backtest scenario of ``tests/fixtures/backtest_rows.py``, and runs
every query against it. A query added to the doc
without a tag, a tag without its block, or a result that no longer matches its expectation fails.

The dataset is hermetic: committed ``.ttl`` files and synthetic rows only, never a live GraphDB
repository and never a real backtest database. It reproduces the real split between the asset
catalog's quarter graph and the reference taxonomy, and enables GraphDB's default union for the
one documented cross-graph sub-select.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db, load_catalog, scenario_rows
from fixtures.reference_rows import ASSETS as REFERENCE_ASSETS
from fixtures.reference_rows import reference_db
from rdflib.query import ResultRow
from rdflib.term import URIRef

from projection.backtest import (
    SELECTION_VIEWS,
    VIEWS,
    AssetInfo,
    Projection,
    load_selection_catalog,
    project,
    project_selection,
    read_view,
)
from projection.reference import VIEWS as REFERENCE_VIEWS
from projection.reference import project as project_reference
from projection.reference import read_view as read_reference_view
from projection.source import FinancialSource

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "schema"
CATALOG = REPO / "docs" / "reports-agent-query-catalog.md"

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)
RDF = rdflib.RDF
RDFS = rdflib.RDFS
SKOS = rdflib.SKOS
XSD = rdflib.XSD
UNIVERSE_GRAPH = "urn:graph:universe:2026-Q4"

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
        "A2-equity-index",
        "A2-price-close",
        "A2-sec",
        "fibo-missing-sharpe",
        "active-rules",
        "universe-members-on-date",
        "ticker-history-on-date",
        "performance-window-arm-segment",
        "guard-alerts-window-month-rule",
        "latest-nav-known-on-date",
        "layer1-cut-tickers",
        "cut-explanation",
        "book-knowledge-dates",
        "book-weight-daily-properties",
        "weight-scale",
        "n-equity-per-arm-on-last-day",
        "runs-available",
        "selection-ranking-at-rebalance",
        "selection-vetoes-in-force",
        "selection-why-not-top30",
        "layer1-cuts-by-window-sector",
        "sector-composition-on-rebalance",
        "held-tickers-by-window-industry",
        "sector-coverage-of-held-assets",
        "unclassified-assets-by-validto-year",
        "sector-of-asset",
    }
)

#: The backtest queries. They must not hardcode a graph name, a run label or a run id.
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
        "n-equity-per-arm-on-last-day",
        "runs-available",
        "selection-ranking-at-rebalance",
        "selection-vetoes-in-force",
        "selection-why-not-top30",
        "layer1-cuts-by-window-sector",
        "sector-composition-on-rebalance",
        "held-tickers-by-window-industry",
        "sector-coverage-of-held-assets",
    }
)

#: The eleven questions of the brief's §6, verbatim and in its order.
EXPECTED_QUESTIONS = (
    "¿Qué es una posición en el portafolio?",
    "¿Por qué GOOGL y GOOG aparecen como dos activos?",
    "¿Qué es el S&P 500 y cómo se relaciona con el universo de activos?",
    "¿Qué precio de cierre usa el sistema? ¿Está ajustado por dividendos?",
    "¿A qué sector GICS pertenece X y qué significa?",
    "¿Qué es un informe 10-K y quién lo recibe?",
    "¿Qué papel tiene X en la empresa Y?",
    "¿Qué es la volatilidad y cómo la usa el sistema?",
    "(control) ¿Por qué salió X del portafolio?",
    "(control) ¿Cuántas posiciones tiene el portafolio actual?",
    "(control) ¿Qué empresas del portafolio son bancos o aseguradoras?",
)

#: The five status labels of the limits table (brief §6 plus "Not projected yet").
STATUSES = (
    "Today",
    "After the asset catalog",
    "After T-209",
    "Never by design",
    "Not projected yet",
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


def _projections(tmp_path: Path, window: str, label: str) -> list[Projection]:
    """The synthetic scenario of one window, projected on both the m018 and selection sides."""
    source = FinancialSource.open(backtest_db(tmp_path, window=window))
    try:
        rows = {view: read_view(source, view) for view in VIEWS}
        selection = {view: read_view(source, view) for view in ("v_book", *SELECTION_VIEWS)}
    finally:
        source.close()
    return [
        project(rows, ASSETS, load_catalog(), label),
        project_selection(selection, ASSETS, load_selection_catalog(SCHEMA / "rules.ttl"), label),
    ]


def _rows(dataset: rdflib.Dataset, query: str) -> list[ResultRow]:
    """The SELECT rows of ``query``; an ASK/GRAPH result is a test bug, not a row."""
    result = dataset.query(query)
    return [row for row in result if isinstance(row, ResultRow)]


def _add_universe_catalog(dataset: rdflib.Dataset) -> None:
    """The real layout of the asset catalog in ``urn:graph:universe:2026-Q4``.

    ``:Asset`` and ``:classifiedAs`` live in the quarter graph; the ``:Industry`` and ``:Sector``
    taxonomy stays in ``urn:graph:reference``. ``AAPL`` is deliberately in both graphs: the five
    worked-example assets also appear in the universe graph (T-225), so a union join without
    ``SELECT DISTINCT`` would count them twice. The ``OLD*`` assets have closed memberships and no
    classification, as the 2019-2021 leavers do.
    """
    universe = dataset.graph(URIRef(UNIVERSE_GRAPH))
    universe.add((KG.SP500Index, RDF.type, KG.Universe))
    for ticker, industry in (
        ("AAA", "Ind_Banks"),
        ("BBB", "Ind_Insurance"),
        ("BRK.B", "Ind_FinancialServices"),
        ("AAPL", "Ind_TechHardwareEquip"),  # the same asset is declared in reference.ttl
    ):
        asset = KG[ticker]
        universe.add((asset, RDF.type, KG.Asset))
        universe.add((asset, KG.tickerSymbol, rdflib.Literal(ticker)))
        universe.add((asset, KG.classifiedAs, KG[industry]))

    for ticker, valid_from, valid_to in (
        ("OLD2019", "2010-01-01", "2019-06-30"),
        ("OLD2021A", "2010-01-01", "2021-03-31"),
        ("OLD2021B", "2010-01-01", "2021-12-31"),
    ):
        asset = KG[ticker]
        membership = KG[f"UM_{ticker}_{valid_from}"]
        universe.add((asset, RDF.type, KG.Asset))
        universe.add((asset, KG.tickerSymbol, rdflib.Literal(ticker)))
        universe.add((asset, KG.hasUniverseMembership, membership))
        universe.add((membership, RDF.type, KG.UniverseMembership))
        universe.add((membership, KG.membershipAsset, asset))
        universe.add((membership, KG.membershipUniverse, KG.SP500Index))
        universe.add((membership, KG.validFrom, rdflib.Literal(valid_from, datatype=XSD.date)))
        universe.add((membership, KG.validTo, rdflib.Literal(valid_to, datatype=XSD.date)))


def _base_dataset() -> rdflib.Dataset:
    """The schema graphs, the real-layout universe graph and two Spanish sector probes.

    The shipped ``reference.ttl`` has no per-sector Spanish note; the probes exercise the
    optional comment/definition branch of ``sector-of-asset`` without changing the real schema.
    """
    # GraphDB's default graph is the union of every named graph; the sector sub-select in §6
    # depends on that union, so the hermetic dataset reproduces it.
    dataset = rdflib.Dataset(default_union=True)
    for path, graph_iri in (
        (SCHEMA / "tbox.ttl", "urn:graph:tbox"),
        (SCHEMA / "fibo.ttl", "urn:graph:reference:fibo"),
        (SCHEMA / "rules.ttl", "urn:graph:rules:catalog"),
        (SCHEMA / "reference.ttl", "urn:graph:reference"),
    ):
        dataset.graph(URIRef(graph_iri)).parse(path, format="turtle")
    _add_universe_catalog(dataset)
    reference = dataset.graph(URIRef("urn:graph:reference"))
    reference.add(
        (KG.Sec_Financials, RDFS.comment, rdflib.Literal("Sector financiero (prueba).", lang="es"))
    )
    reference.add(
        (
            KG.Sec_InformationTechnology,
            SKOS.definition,
            rdflib.Literal("Sector de tecnología (prueba).", lang="es"),
        )
    )
    return dataset


@pytest.fixture(scope="module")
def catalog_dataset(tmp_path_factory: pytest.TempPathFactory) -> rdflib.Dataset:
    """The base dataset plus two labels across both synthetic backtest windows."""
    dataset = _base_dataset()
    # One rename chain as the asset loader writes it: the FB stint ends on 2022-06-08
    # (inclusive) and the META stint starts on 2022-06-09, both on the same :META asset
    # (one CIK, one company).
    universe = dataset.graph(URIRef("urn:graph:universe:2026-Q4"))
    universe.add((KG.UM_FB, RDF.type, KG.UniverseMembership))
    universe.add((KG.UM_FB, KG.membershipAsset, KG.META))
    universe.add((KG.UM_FB, KG.membershipUniverse, KG.SP500Index))
    universe.add((KG.UM_FB, KG.validFrom, rdflib.Literal("2013-12-23", datatype=XSD.date)))
    universe.add((KG.UM_FB, KG.validTo, rdflib.Literal("2022-06-08", datatype=XSD.date)))
    universe.add((KG.UM_META, RDF.type, KG.UniverseMembership))
    universe.add((KG.UM_META, KG.membershipAsset, KG.META))
    universe.add((KG.UM_META, KG.membershipUniverse, KG.SP500Index))
    universe.add((KG.UM_META, KG.validFrom, rdflib.Literal("2022-06-09", datatype=XSD.date)))
    universe.add((KG.META, RDF.type, KG.Asset))
    universe.add((KG.META, KG.tickerSymbol, rdflib.Literal("META")))
    universe.add((KG.SP500Index, RDF.type, KG.Universe))

    # One ticker-history snapshot, projected through the real reference projector. The rename
    # query reads only this graph; it does not depend on the universe graph above.
    reference_source = FinancialSource.open(reference_db(tmp_path_factory.mktemp("reference")))
    try:
        reference_rows = {
            view: read_reference_view(reference_source, view) for view in REFERENCE_VIEWS
        }
    finally:
        reference_source.close()
    reference_projection = project_reference(reference_rows, REFERENCE_ASSETS, "rule", "2026-11-04")
    for name, builder in reference_projection.graphs.items():
        graph = dataset.graph(URIRef(name))
        for triple in builder.triples:
            graph.add(triple)

    for label in ("rule", "champ_v1"):
        for window in ("P1", "P2"):
            for projection in _projections(
                tmp_path_factory.mktemp(f"{label}-{window}"), window, label
            ):
                for name, builder in projection.graphs.items():
                    graph = dataset.graph(URIRef(name))
                    for triple in builder.triples:
                        graph.add(triple)
    return dataset


@pytest.fixture(scope="module")
def composition_dataset(tmp_path_factory: pytest.TempPathFactory) -> rdflib.Dataset:
    """A rebalance with a classified, an unclassified and an unlinked holding.

    ``AAA`` is classified (Banks -> Financials), ``QQQ`` is a catalog asset without
    ``:classifiedAs`` and ``ZZZ`` has no ``:holdingAsset`` at all. The two unlinkable holdings
    must land in ``unclassified`` so sectors + unclassified + CASH = 1.
    """
    dataset = _base_dataset()
    rows = scenario_rows(window="P1")
    rows["book_weight_daily"] = [
        row
        for row in rows["book_weight_daily"]
        if not (row["book_id"] == 1 and row["date"] == "2022-01-04")
    ]
    for ticker, asset_id, weight in (
        ("AAA", 1, 0.60),
        ("QQQ", None, 0.30),
        ("ZZZ", 4, 0.05),
        ("CASH", None, 0.05),
    ):
        rows["book_weight_daily"].append(
            {
                "book_id": 1,
                "date": "2022-01-04",
                "holding_key": ticker,
                "asset_id": asset_id,
                "markowitz_target_weight": weight,
                "drifted_weight": weight,
                "pre_guard_weight": weight,
                "final_target_weight": weight,
            }
        )
    for perf in rows["book_daily_performance"]:
        if perf["book_id"] == 1 and perf["date"] == "2022-01-04":
            perf["cash_weight"] = 0.05
            perf["n_equity"] = 3

    assets = {**ASSETS, "QQQ": AssetInfo("QQQ", "0000000005", (("2020-01-01", None),))}
    source = FinancialSource.open(
        backtest_db(tmp_path_factory.mktemp("composition"), window="P1", rows=rows)
    )
    try:
        views = {view: read_view(source, view) for view in VIEWS}
    finally:
        source.close()
    projection = project(views, assets, load_catalog(), "rule")
    for name, builder in projection.graphs.items():
        graph = dataset.graph(URIRef(name))
        for triple in builder.triples:
            graph.add(triple)

    universe = dataset.graph(URIRef(UNIVERSE_GRAPH))
    universe.add((KG.QQQ, RDF.type, KG.Asset))
    universe.add((KG.QQQ, KG.tickerSymbol, rdflib.Literal("QQQ")))
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
    assert [row[1] for row in rows] == list(EXPECTED_QUESTIONS)
    for _, _, status, _ in rows:
        assert any(label in status for label in STATUSES), status
    assert "Not projected yet" in rows[6][2]  # Q7, executives
    assert "Not projected yet" in rows[9][2]  # Q10, live portfolio
    assert "Today" in rows[4][2]  # Q5, the sector of an asset
    assert "Today" in rows[10][2]  # Q11, banks and insurers


def test_the_asset_catalog_limits_are_stated() -> None:
    text = " ".join(_document().split())
    assert "Known limits of the asset catalog" in text
    assert "56 closed stints" in text
    assert "no classification in the source" in text
    assert "src/etl/common/gics_rollup.py" in text
    assert "universe_patches.py" in text
    for ticker in ("MBC", "FTRE", "PHIN"):
        assert ticker in text
    assert "Work item 23" in text


def test_the_backtest_table_lists_the_battery() -> None:
    assert BACKTEST_ROW.findall(_document()) == [f"B{number}" for number in range(1, 10)]


def test_the_boundary_rule_is_stated() -> None:
    text = " ".join(_document().replace(">", " ").split())
    assert "never why an asset was in or out of a portfolio" in text
    assert "questions 9 to 11 must not change with or without the FIBO slice" in text
    for status in STATUSES:
        assert status in text


def test_the_hard_veto_marker_note_is_stated() -> None:
    text = " ".join(_document().replace("`", "").split())
    assert 'only the marker "HARD"' in text
    assert "every rule missing from the JSON is a HARD rule" in text
    assert "no JSON rule is ever extra" in text
    assert "join it with the Veto stints in force" in text
    assert "selection-vetoes-in-force" in text


def test_backtest_queries_do_not_name_a_graph_or_a_run() -> None:
    for name in BACKTEST_NAMES:
        query = _query(name)
        assert "GRAPH ?g" in query, name
        assert 'STRSTARTS(STR(?g), "urn:graph:derived:backtest:")' in query, name
        assert not re.search(r"urn:graph:derived:backtest:[A-Za-z0-9{]", query), name
        # The property list and runs-available deliberately span labels; every other query selects
        # one label (`:runLabel`) and one window, directly or through the book.
        if name not in {"book-weight-daily-properties", "runs-available"}:
            assert 'FILTER (?label = "rule")' in query, name
            assert ":windowId" in query or ":weightOfBook" in query, name
        else:
            assert "FILTER (?label" not in query, name


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


def test_a1_returns_the_no_fibo_terms_without_a_fibo_row(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("A1-terms"))
    assert len(rows) == 10
    by_term = {str(row["term"]): row for row in rows}
    for name in ("Asset", "Universe", "UniverseMembership", "PriceObservation", "Executive"):
        assert by_term[f"{NS}{name}"]["fibo"] is None
    assert sum(1 for row in rows if row["fibo"] is not None) == 5


def test_a2_returns_the_fibo_volatility_term(catalog_dataset: rdflib.Dataset) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("A2-volatilidad"))
    assert str(rows[0]["term"]) == (
        "https://spec.edmcouncil.org/fibo/ontology/IND/Indicators/Indicators/Volatility"
    )
    assert str(rows[0]["defEs"]).startswith("Medida estadística")
    assert str(rows[0]["fiboDef"]).startswith("statistical measure")


def test_a2_returns_the_labels_the_evaluation_questions_name(
    catalog_dataset: rdflib.Dataset,
) -> None:
    equity = _rows(catalog_dataset, _query("A2-equity-index"))
    assert len(equity) == 1
    assert str(equity[0]["term"]).endswith("/EquityIndex")

    prices = _rows(catalog_dataset, _query("A2-price-close"))
    assert {str(row["term"]).rsplit("/", 1)[-1] for row in prices} == {
        "ClosingPrice",
        "AdjustedClosingPrice",
    }

    sec = _rows(catalog_dataset, _query("A2-sec"))
    assert len(sec) == 1
    assert str(sec[0]["term"]).endswith("/SecuritiesAndExchangeCommission")


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


def test_a_membership_on_its_last_day_is_still_in(catalog_dataset: rdflib.Dataset) -> None:
    """validTo is inclusive: the FB stint ends 2022-06-08 and META starts 2022-06-09."""
    rows = _rows(catalog_dataset, _query("universe-members-on-date"))
    assert [str(row["ticker"]) for row in rows] == ["META"]
    assert str(rows[0]["to"]) == "2022-06-08"


def test_ticker_history_resolves_a_former_symbol_to_its_asset(
    catalog_dataset: rdflib.Dataset,
) -> None:
    """FB on 2022-06-08 is the last day of its stint; the canonical symbol is META."""
    rows = _rows(catalog_dataset, _query("ticker-history-on-date"))
    assert len(rows) == 1
    row = rows[0]
    assert str(row["symbol"]) == "FB"
    assert str(row["canonical"]) == "META"
    assert str(row["cik"]) == "0001326801"
    assert str(row["asset"]) == f"{NS}META"
    assert str(row["snapshot"]).startswith("urn:graph:derived:ticker-history:")


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


def test_n_equity_is_the_latest_performance_row(catalog_dataset: rdflib.Dataset) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("n-equity-per-arm-on-last-day"))
    assert len(rows) == 6
    by_key = {(str(row["window"]), str(row["arm"])): row for row in rows}
    markowitz = by_key[("P1", "MARKOWITZ_BASE")]
    assert str(markowitz["date"]) == "2022-01-05"
    assert int(str(markowitz["nEquity"])) == 2
    no_guard = by_key[("P2", "TOPN_MV_NOGUARD")]
    assert str(no_guard["date"]) == "2022-01-06"
    assert int(str(no_guard["nEquity"])) == 1


def test_runs_available_lists_both_labels_and_windows(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows: list[ResultRow] = _rows(catalog_dataset, _query("runs-available"))
    assert {(str(row["label"]), str(row["window"]), int(str(row["books"]))) for row in rows} == {
        ("rule", "P1", 3),
        ("rule", "P2", 3),
        ("champ_v1", "P1", 3),
        ("champ_v1", "P2", 3),
    }


def test_the_fixture_uses_the_real_asset_catalog_split(
    catalog_dataset: rdflib.Dataset,
) -> None:
    universe = catalog_dataset.graph(URIRef(UNIVERSE_GRAPH))
    reference = catalog_dataset.graph(URIRef("urn:graph:reference"))
    assert (KG.AAA, RDF.type, KG.Asset) in universe
    assert (KG.AAA, KG.classifiedAs, KG.Ind_Banks) in universe
    assert (KG.AAPL, RDF.type, KG.Asset) in universe
    assert (KG.AAPL, RDF.type, KG.Asset) in reference
    assert (KG.Ind_Banks, KG.memberOfSector, KG.Sec_Financials) in reference
    assert (KG.Ind_Banks, KG.memberOfSector, None) not in universe


def test_the_layer1_cut_total_matches_the_enter_alerts(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("layer1-cuts-by-window-sector"))
    p1_cuts = sum(int(str(row["cuts"])) for row in rows if str(row["window"]) == "P1")
    alerts = _rows(
        catalog_dataset,
        """
PREFIX : <https://thesis.local/kg/portfolio#>

SELECT (COUNT(DISTINCT ?alert) AS ?alerts)
WHERE {
  GRAPH ?g {
    ?action a :GuardAction ; :actionAlert ?alert ; :actionOfBook ?book .
    ?book :runLabel "rule" ; :windowId "P1" .
    ?alert :alertState "ENTER" ; :alertRule ?rule .
  }
  GRAPH <urn:graph:rules:catalog> { ?rule :guardLayer 1 . }
  FILTER (STRSTARTS(STR(?g), "urn:graph:derived:backtest:"))
}
""",
    )
    assert p1_cuts == 1
    assert p1_cuts == int(str(alerts[0]["alerts"]))


def test_the_sector_composition_sums_to_one_minus_cash(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("sector-composition-on-rebalance"))
    assert len(rows) == 1
    total = sum(Decimal(str(row["weight"])) for row in rows)
    cash = Decimal(str(rows[0]["cash"]))
    assert total + cash == Decimal(1)
    assert str(rows[0]["sector"]) == "Financials"  # AAA -> Banks -> Financials


def test_the_sector_composition_keeps_unclassified_holdings(
    composition_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(composition_dataset, _query("sector-composition-on-rebalance"))
    by_sector = {str(row["sector"]): Decimal(str(row["weight"])) for row in rows}
    assert by_sector == {"Financials": Decimal("0.60"), "unclassified": Decimal("0.35")}
    cash = Decimal(str(rows[0]["cash"]))
    assert cash == Decimal("0.05")
    assert sum(by_sector.values()) + cash == Decimal(1)


def test_sector_of_asset_returns_the_catalog_sector(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("sector-of-asset"))
    assert len(rows) == 1
    row = rows[0]
    assert str(row["ticker"]) == "AAA"
    assert row["companyName"] is None
    assert str(row["industryLabel"]) == "Banks"
    assert str(row["sectorLabel"]) == "Financials"
    assert str(row["sectorDefinition"]) == "Sector financiero (prueba)."


def test_sector_of_asset_deduplicates_a_worked_example_in_both_graphs(
    catalog_dataset: rdflib.Dataset,
) -> None:
    query = _query("sector-of-asset").replace('"AAA"', '"AAPL"')
    rows = _rows(catalog_dataset, query)
    assert len(rows) == 1
    row = rows[0]
    assert str(row["ticker"]) == "AAPL"
    assert str(row["companyName"]) == "Apple Inc."
    assert str(row["industryLabel"]) == "Technology Hardware & Equipment"
    assert str(row["sectorLabel"]) == "Information Technology"
    assert str(row["sectorDefinition"]) == "Sector de tecnología (prueba)."


def test_sector_of_asset_returns_no_row_for_an_unclassified_asset(
    catalog_dataset: rdflib.Dataset,
) -> None:
    query = _query("sector-of-asset").replace('"AAA"', '"OLD2019"')
    assert _rows(catalog_dataset, query) == []


def test_banks_and_insurers_are_listed_by_window(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("held-tickers-by-window-industry"))
    by_key = {(str(row["window"]), str(row["industry"])): row for row in rows}
    assert set(by_key) == {
        ("P1", "Banks"),
        ("P1", "Insurance"),
        ("P2", "Banks"),
        ("P2", "Insurance"),
    }
    assert int(str(by_key[("P1", "Banks")]["tickers"])) == 1
    assert "AAA" in str(by_key[("P1", "Banks")]["tickerList"])
    assert "BBB" in str(by_key[("P1", "Insurance")]["tickerList"])


def test_sector_coverage_separates_held_linked_and_classified(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("sector-coverage-of-held-assets"))
    assert {str(row["window"]) for row in rows} == {"P1", "P2"}
    for row in rows:
        # AAA, BBB and BRK.B are linked and classified; ZZZ is held but not in the catalog.
        assert int(str(row["heldTickers"])) == 4
        assert int(str(row["withAsset"])) == 3
        assert int(str(row["withSector"])) == 3


def test_unclassified_assets_are_counted_by_validto_year(
    catalog_dataset: rdflib.Dataset,
) -> None:
    rows = _rows(catalog_dataset, _query("unclassified-assets-by-validto-year"))
    assert [(int(str(row["year"])), int(str(row["unclassifiedAssets"]))) for row in rows] == [
        (2019, 1),
        (2021, 2),
    ]


def test_the_single_graph_sector_pattern_loses_the_catalog(
    catalog_dataset: rdflib.Dataset,
) -> None:
    """The documented trap: the classification and the taxonomy are in different graphs."""
    prefix = (
        "PREFIX :    <https://thesis.local/kg/portfolio#>\n"
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
    )
    path = (
        "?asset :classifiedAs ?industry . "
        "?industry :memberOfSector ?sector . "
        "?sector skos:prefLabel ?sectorLabel ."
    )
    correct = prefix + f"SELECT DISTINCT ?asset ?sectorLabel WHERE {{ {path} }}"
    in_universe = prefix + (
        f"SELECT DISTINCT ?asset ?sectorLabel WHERE {{ GRAPH <{UNIVERSE_GRAPH}> {{ {path} }} }}"
    )
    in_reference = prefix + (
        f"SELECT DISTINCT ?asset ?sectorLabel WHERE {{ GRAPH <urn:graph:reference> {{ {path} }} }}"
    )
    # A naive union of the two classification branches, then the taxonomy: AAPL is
    # a solution in both branches, so the T-225 overlap counts it twice.
    union = prefix + (
        "SELECT ?asset ?sectorLabel WHERE { "
        f"{{ GRAPH <{UNIVERSE_GRAPH}> {{ ?asset :classifiedAs ?industry . }} }} "
        f"UNION {{ GRAPH <urn:graph:reference> {{ ?asset :classifiedAs ?industry . }} }} "
        "?industry :memberOfSector ?sector . "
        "?sector skos:prefLabel ?sectorLabel . }"
    )
    correct_rows = _rows(catalog_dataset, correct)
    universe_rows = _rows(catalog_dataset, in_universe)
    reference_rows = _rows(catalog_dataset, in_reference)
    union_rows = _rows(catalog_dataset, union)

    assert len(correct_rows) == 8
    # The universe graph has the assets and their :classifiedAs, but no taxonomy.
    assert len(universe_rows) == 0
    # The reference graph has the taxonomy and only the five worked-example assets.
    assert len(reference_rows) == 5
    assert len(universe_rows) < len(correct_rows)
    assert len(reference_rows) < len(correct_rows)
    # Without DISTINCT the T-225 overlap counts AAPL twice.
    assert len(union_rows) == 9
    aapl = str(KG.AAPL)
    assert sum(1 for row in correct_rows if str(row["asset"]) == aapl) == 1
    assert sum(1 for row in union_rows if str(row["asset"]) == aapl) == 2


@pytest.mark.parametrize(
    "name",
    [
        "performance-window-arm-segment",
        "guard-alerts-window-month-rule",
        "latest-nav-known-on-date",
        "layer1-cuts-by-window-sector",
        "sector-composition-on-rebalance",
        "held-tickers-by-window-industry",
        "sector-coverage-of-held-assets",
    ],
)
def test_two_labels_in_one_window_do_not_mix(catalog_dataset: rdflib.Dataset, name: str) -> None:
    rule_query = _query(name)
    champ_query = rule_query.replace('FILTER (?label = "rule")', 'FILTER (?label = "champ_v1")')
    rule_rows = _rows(catalog_dataset, rule_query)
    champ_rows = _rows(catalog_dataset, champ_query)
    assert {str(row["label"]) for row in rule_rows} == {"rule"}
    assert {str(row["label"]) for row in champ_rows} == {"champ_v1"}
    assert rule_rows and champ_rows
    if name == "performance-window-arm-segment":
        assert {str(row["summary"]) for row in rule_rows}.isdisjoint(
            {str(row["summary"]) for row in champ_rows}
        )
