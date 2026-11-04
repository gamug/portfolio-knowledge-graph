"""The gate's context fetch falls back to the TBox range when a relation has no ``sh:class``.

Regression for the first real selection write (Work item 30): a dry run validated beside the full
local rules/asset graphs, but the write fetched only ``rdf:type`` for the referenced assets and
rules, so ``AssetShape`` and ``RuleDefinitionShape`` failed on nodes that were not in the batch.
The test exercises the real ``gate.fetch_context`` against an in-memory dataset.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db
from rdflib.query import ResultRow

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.backtest import (
    SELECTION_VIEWS,
    load_selection_catalog,
    project_selection,
    read_view,
    selection_graph_name,
)
from projection.source import FinancialSource

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
UNIVERSE = "urn:graph:universe:2026-Q4"


class DatasetTermsDB:
    """A read-only stand-in for GraphDB whose SPARQL runs against an in-memory Dataset."""

    def __init__(self, dataset: rdflib.Dataset) -> None:
        self.dataset = dataset

    def select_terms(self, query: str) -> list[dict[str, Any]]:
        query = query.replace("FROM <http://www.ontotext.com/explicit> ", "")
        rows = cast(Iterable[ResultRow], self.dataset.query(query))
        return [{str(label): row[label] for label in row.labels} for row in rows]


def _dataset() -> rdflib.Dataset:
    dataset = rdflib.Dataset(default_union=True)
    dataset.graph(rdflib.URIRef("urn:graph:rules:catalog")).parse(
        SCHEMA / "rules.ttl", format="turtle"
    )
    universe = dataset.graph(rdflib.URIRef(UNIVERSE))
    universe.add((KG.SP500Index, rdflib.RDF.type, KG.Universe))
    for symbol, info in ASSETS.items():
        asset = KG[symbol]
        membership = KG[f"Membership_{symbol}"]
        universe.add((asset, rdflib.RDF.type, KG.Asset))
        universe.add((asset, KG.tickerSymbol, rdflib.Literal(symbol)))
        if info.cik is not None:
            universe.add((asset, KG.cikNumber, rdflib.Literal(info.cik)))
        universe.add((asset, KG.hasUniverseMembership, membership))
        universe.add((membership, rdflib.RDF.type, KG.UniverseMembership))
        universe.add((membership, KG.membershipAsset, asset))
        universe.add((membership, KG.membershipUniverse, KG.SP500Index))
        universe.add(
            (
                membership,
                KG.validFrom,
                rdflib.Literal("2000-01-01", datatype=rdflib.XSD.date),
            )
        )
    # A closed, CIK-less line: AssetShape's other branch, not referenced by this batch.
    old = KG.OLD
    membership = KG.Membership_OLD
    universe.add((old, rdflib.RDF.type, KG.Asset))
    universe.add((old, KG.tickerSymbol, rdflib.Literal("OLD")))
    universe.add((old, KG.hasUniverseMembership, membership))
    universe.add((membership, rdflib.RDF.type, KG.UniverseMembership))
    universe.add((membership, KG.membershipAsset, old))
    universe.add((membership, KG.membershipUniverse, KG.SP500Index))
    universe.add((membership, KG.validFrom, rdflib.Literal("2010-01-01", datatype=rdflib.XSD.date)))
    universe.add((membership, KG.validTo, rdflib.Literal("2019-06-30", datatype=rdflib.XSD.date)))
    return dataset


def _selection_batch(tmp_path: Path) -> rdflib.Graph:
    source = FinancialSource.open(backtest_db(tmp_path))
    try:
        rows = {view: read_view(source, view) for view in ("v_book", *SELECTION_VIEWS)}
    finally:
        source.close()
    projection = project_selection(
        rows, ASSETS, load_selection_catalog(SCHEMA / "rules.ttl"), "rule"
    )
    name = selection_graph_name("rule", "P1", 1)
    return gate.parse_batch(projection.turtle(name))


def _context(batch: rdflib.Graph) -> rdflib.Graph:
    schema = gate.load_gate_schema(SCHEMA.resolve())
    refs = gate.references(batch, schema)
    return gate.fetch_context(cast(GraphDB, DatasetTermsDB(_dataset())), refs, schema, batch)


def test_the_selection_batch_fetches_the_asset_and_rule_shape_predicates(tmp_path: Path) -> None:
    batch = _selection_batch(tmp_path)
    context = _context(batch)
    for asset in (KG.AAA, KG.BBB, KG["BRK.B"], KG.CCC):
        assert any(context.triples((asset, KG.tickerSymbol, None))), asset
        assert any(context.triples((asset, KG.cikNumber, None))), asset
        assert any(context.triples((asset, KG.hasUniverseMembership, None))), asset
    for rule in (KG.Rule_DATA_QUALITY, KG.Rule_LIQUIDITY_DISTRESS_v11):
        assert any(context.triples((rule, KG.ruleId, None))), rule
        assert any(context.triples((rule, KG.category, None))), rule
        assert any(context.triples((rule, KG.ruleSeverity, None))), rule
        assert any(context.triples((rule, KG.hasClause, None))), rule
    # The old bug's shape: six triples (one rdf:type per referenced asset/rule) would fail here.
    assert len(context) > len(gate.references(batch, gate.load_gate_schema(SCHEMA.resolve())))
    gate.validate(batch, context=context)


def test_validate_against_store_uses_the_real_fetch(tmp_path: Path) -> None:
    batch = _selection_batch(tmp_path)
    gate.validate_against_store(cast(GraphDB, DatasetTermsDB(_dataset())), batch, SCHEMA)


def test_a_guard_rule_on_a_veto_is_refused_once_its_category_is_fetched(tmp_path: Path) -> None:
    batch = _selection_batch(tmp_path)
    for subject in list(batch.subjects(KG.appliesRule, None)):
        batch.remove((subject, KG.appliesRule, None))
        batch.add((subject, KG.appliesRule, KG.Rule_L1_STOP_LOSS))
    for subject in list(batch.subjects(KG.primaryRule, None)):
        batch.remove((subject, KG.primaryRule, None))
        batch.add((subject, KG.primaryRule, KG.Rule_L1_STOP_LOSS))
    with pytest.raises(gate.ShaclRejected):
        gate.validate(batch, context=_context(batch))


@pytest.mark.parametrize(
    "relation",
    [KG.tickerHistoryAsset, KG.holdingAsset, KG.guardAsset],
    ids=["ticker-history", "holding", "guard"],
)
def test_the_existing_asset_relations_still_fetch_the_asset_shape(relation: Any) -> None:
    batch = rdflib.Graph()
    batch.add((KG.subject, relation, KG.AAA))
    paths = gate.context_predicates(batch, {KG.AAA}, gate.load_gate_schema(SCHEMA.resolve()))
    assert {
        rdflib.RDF.type,
        KG.tickerSymbol,
        KG.cikNumber,
        KG.hasUniverseMembership,
    } <= paths
