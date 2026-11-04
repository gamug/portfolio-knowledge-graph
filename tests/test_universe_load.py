"""``kg_store.universe``: the asset-master batch, ``--since``, the quarter graph and the gate
(T-220).

The loader reuses :mod:`etl.asset_master`; this file checks what it adds: which stints survive
``--since``, how a ticker's two eras become one ``:Asset``, that a ``schema/reference.ttl`` asset
keeps its memberships without a second ``:Asset`` block, the quarter graph name, deterministic
output, the gate's acceptance (including a CIK-less asset whose memberships are all closed) and a
write through a fake store.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import rdflib
from fixtures.universe_rows import ROWS, Row, universe_db
from rdflib.namespace import RDF, RDFS, SH

from kg_store import gate, universe

if TYPE_CHECKING:
    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
FIBO_EQUITY_INDEX = rdflib.URIRef(
    "https://spec.edmcouncil.org/fibo/ontology/IND/MarketIndices/BasketIndices/EquityIndex"
)
AS_OF = "2026-11-03"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return universe_db(tmp_path / "universe.db")


def _graph(batch: universe.UniverseBatch) -> rdflib.Graph:
    return gate.parse_batch(batch.data)


# --- the --since filter and build_assets reuse ------------------------------------------------
def test_since_drops_a_tickers_old_era_and_keeps_the_open_one(db: Path) -> None:
    batch = universe.plan(db, since="2019-01-02", as_of=AS_OF)
    kept = {(s.symbol, s.valid_from, s.valid_to) for s in batch.kept}
    assert ("CEG", "2022-02-02", None) in kept
    assert ("CEG", "1976-07-01", "2012-03-12") not in kept
    assert ("OLDT", "2005-01-03", "2018-12-31") not in kept
    assert {s.symbol for s in batch.dropped} == {"CEG", "OLDT"}
    graph = _graph(batch)
    assert (KG.CEG, KG.companyName, rdflib.Literal("Constellation Energy")) in graph
    assert (KG.CEG, KG.cikNumber, rdflib.Literal("0001868275")) in graph


def test_a_one_day_stint_is_kept_and_conforms(tmp_path: Path) -> None:
    """validTo is inclusive: PHIN's valid_from = valid_to = 2023-07-05 is a real stint."""
    rows: list[Row] = [
        *ROWS,
        (
            "PHIN",
            "PHINIA",
            "Consumer Discretionary",
            "Automotive Parts & Equipment",
            "0001968915",
            "2023-07-05",
            "2023-07-05",
        ),
    ]
    db = universe_db(tmp_path / "universe.db", rows)
    batch = universe.plan(db, as_of=AS_OF)
    assert ("PHIN", "2023-07-05", "2023-07-05") in {
        (s.symbol, s.valid_from, s.valid_to) for s in batch.kept
    }
    graph = _graph(batch)
    assert (KG.PHIN, RDF.type, KG.Asset) in graph
    assert (KG["UM_PHIN_2023-07-05"], KG.validTo, None) in graph
    universe.check(batch, SCHEMA)


def test_since_is_inclusive_on_a_closed_stint(db: Path) -> None:
    """``validTo`` is inclusive, so a stint closed on the date itself is still kept."""
    batch = universe.plan(db, since="2018-12-31", as_of=AS_OF)
    assert ("OLDT", "2005-01-03", "2018-12-31") in {
        (s.symbol, s.valid_from, s.valid_to) for s in batch.kept
    }


def test_a_ticker_with_two_eras_is_one_asset_described_by_the_kept_one(db: Path) -> None:
    batch = universe.plan(db, since="2019-01-02", as_of=AS_OF)
    graph = _graph(batch)
    assert len(set(graph.subjects(KG.tickerSymbol, rdflib.Literal("CEG")))) == 1
    assert (KG.CEG, KG.classifiedAs, KG.Ind_Utilities) in graph


# --- the batch itself -------------------------------------------------------------------------
def test_the_batch_declares_the_universe_and_keeps_its_fibo_link(db: Path) -> None:
    graph = _graph(universe.plan(db, as_of=AS_OF))
    assert (KG.SP500Index, RDF.type, KG.Universe) in graph
    assert list(graph.objects(KG.SP500Index, RDFS.seeAlso)) == [FIBO_EQUITY_INDEX]
    assert (KG.SP500Index, RDFS.label, None) in graph


def test_a_cik_less_asset_whose_memberships_are_all_closed_is_written(db: Path) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    graph = _graph(batch)
    assert (KG.GONE, RDF.type, KG.Asset) in graph
    assert (KG.GONE, KG.tickerSymbol, rdflib.Literal("GONE")) in graph
    assert (KG.GONE, KG.cikNumber, None) not in graph
    assert (KG["UM_GONE_2020-01-02"], KG.validTo, None) in graph
    assert batch.cik_less_open == ()


def test_a_symbol_with_a_dot_survives_the_turtle_round_trip(db: Path) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    graph = _graph(batch)
    assert (KG["BRK.B"], RDF.type, KG.Asset) in graph
    assert (KG["BRK.B"], KG.tickerSymbol, rdflib.Literal("BRK.B")) in graph
    assert (KG["UM_BRK.B_2019-01-02"], KG.membershipAsset, KG["BRK.B"]) in graph


def test_a_reference_ttl_asset_gets_memberships_but_no_second_asset_block(db: Path) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    graph = _graph(batch)
    assert (KG.AAPL, RDF.type, KG.Asset) not in graph
    assert (KG.AAPL, KG.hasUniverseMembership, KG["UM_AAPL_2019-01-03"]) in graph
    assert (KG["UM_AAPL_2019-01-03"], KG.membershipAsset, KG.AAPL) in graph
    assert batch.summary.assets_written == 3
    assert "AAPL" in batch.already_defined


def test_the_dry_run_gate_accepts_the_batch(db: Path) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    universe.check(batch, SCHEMA)  # raises IngestRejected/ShaclRejected otherwise


def test_the_stored_reference_assets_are_not_redeclared(db: Path, make_db: MakeDB) -> None:
    """Gate check 6 refuses a stored individual; AAPL is in reference.ttl, so the batch must not
    type it -- only point at it and give it a membership."""
    parsed = gate.parse_batch(universe.plan(db, as_of=AS_OF).data)
    typed = set(parsed.subjects(RDF.type, None))
    assert KG.AAPL not in typed
    assert not typed & {KG[t] for t in ("AAPL", "JPM", "XOM", "JNJ", "PG")}
    # A store that holds AAPL (as a schema load leaves it) is only asked about the typed subjects,
    # so check 6 has nothing to refuse: AAPL does not appear in the query's VALUES list.
    fake = make_db()

    def select(sparql: str) -> list[dict[str, str]]:
        fake.queries.append(sparql)
        return [{"s": str(KG.AAPL)}] if str(KG.AAPL) in sparql else []

    fake.select = select  # type: ignore[method-assign]
    assert gate.existing_subjects(fake.db, parsed) == []


def test_the_target_graph_is_the_quarter_graph_and_the_gate_accepts_it(db: Path) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    assert batch.graph == "urn:graph:universe:2026-Q4"
    assert gate.check_target(batch.graph) is True


def test_the_output_is_deterministic(db: Path) -> None:
    first = universe.plan(db, since="2019-01-02", as_of=AS_OF)
    second = universe.plan(db, since="2019-01-02", as_of=AS_OF)
    assert first.data == second.data
    assert first.triples == second.triples


@pytest.mark.parametrize(
    ("as_of", "name"),
    [
        ("2026-01-01", "urn:graph:universe:2026-Q1"),
        ("2026-03-31", "urn:graph:universe:2026-Q1"),
        ("2026-04-01", "urn:graph:universe:2026-Q2"),
        ("2026-09-30", "urn:graph:universe:2026-Q3"),
        ("2026-10-01", "urn:graph:universe:2026-Q4"),
        ("2027-01-01", "urn:graph:universe:2027-Q1"),
    ],
)
def test_the_as_of_date_names_the_quarter(as_of: str, name: str) -> None:
    assert universe.graph_name(as_of) == name


# --- what the shapes refuse -------------------------------------------------------------------
def test_an_open_membership_without_a_cik_is_reported_and_refused(tmp_path: Path) -> None:
    rows: list[Row] = [*ROWS, ("NEWCO", "New Co", None, None, None, "2020-01-02", None)]
    db = universe_db(tmp_path / "universe.db", rows)
    batch = universe.plan(db, as_of=AS_OF)
    assert batch.cik_less_open == ("NEWCO",)
    with pytest.raises(gate.ShaclRejected) as info:
        universe.check(batch, SCHEMA)
    focus = {str(node) for node in info.value.results.objects(None, SH.focusNode)}
    assert str(KG.NEWCO) in focus


# --- a write through the gate, with a fake store ----------------------------------------------
def _store_context(batch: universe.UniverseBatch) -> list[dict[str, rdflib.term.Node]]:
    """What ``gate.fetch_context`` would read from a store that holds ``reference.ttl``.

    The fake returns the same rows for every query, so this gives exactly the properties the
    gate's own SPARQL would select: the referenced subjects' shape paths, no more.
    """
    data = gate.parse_batch(batch.data)
    schema = gate.load_gate_schema(SCHEMA.resolve())
    refs = gate.references(data, schema)
    paths = gate.context_predicates(data, refs, schema)
    reference = universe.reference_context(refs, SCHEMA)
    return [
        {"s": subject, "p": predicate, "o": obj}
        for subject, predicate, obj in reference
        if predicate in paths
    ]


def test_a_write_appends_the_validated_batch_through_the_gate(db: Path, make_db: MakeDB) -> None:
    batch = universe.plan(db, as_of=AS_OF)
    fake = make_db(terms=_store_context(batch))
    written = universe.write(batch, fake.db)
    assert written == batch.triples
    [(data, content_type, graph)] = fake.added
    assert content_type == "application/n-triples"
    assert graph == "urn:graph:universe:2026-Q4"
    stored = rdflib.Graph().parse(data=data, format="nt")
    assert len(stored) == batch.triples
    assert (KG.SP500Index, RDF.type, KG.Universe) in stored
    assert (KG.AAPL, RDF.type, KG.Asset) not in stored
    assert (KG.AAPL, KG.hasUniverseMembership, KG["UM_AAPL_2019-01-03"]) in stored
