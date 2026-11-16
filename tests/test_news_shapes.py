"""Synthetic positive/negative cases for :NewsItemShape (Work item 46, block D)."""

from __future__ import annotations

from pathlib import Path

import pyshacl
import rdflib
from rdflib.namespace import RDF, SH, XSD
from rdflib.term import Node

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

ITEM = KG.NewsItem_T890_251045_DAL


def shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


def _date(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.date)


def _decimal(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.decimal)


def _integer(value: int) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.integer)


def _item() -> rdflib.Graph:
    g = rdflib.Graph()
    g.add((ITEM, RDF.type, KG.NewsItem))
    g.add((ITEM, KG.modelRevision, rdflib.Literal("snapshot-c3a753affa5d")))
    g.add((ITEM, KG.itemKind, rdflib.Literal("sub_news")))
    g.add((ITEM, KG.itemId, rdflib.Literal("251045")))
    g.add((ITEM, KG.newsTicker, rdflib.Literal("DAL")))
    g.add((ITEM, KG.newsAssetId, _integer(148)))
    g.add((ITEM, KG.newsDate, _date("2021-12-01")))
    g.add((ITEM, KG.dateSource, rdflib.Literal("published")))
    g.add((ITEM, KG.newsTitle, rdflib.Literal("Cramer's lightning round")))
    g.add((ITEM, KG.newsText, rdflib.Literal("Delta is very interesting.")))
    g.add((ITEM, KG.textSource, rdflib.Literal("original")))
    g.add((ITEM, KG.newsSentiment, rdflib.Literal("positive")))
    g.add((ITEM, KG.sentimentScore, _decimal("0.5484206646837547")))
    g.add((ITEM, KG.pPositive, _decimal("0.5484206646837547")))
    g.add((ITEM, KG.pNegative, _decimal("0.3411248730675417")))
    g.add((ITEM, KG.pNeutral, _decimal("0.1104544622487036")))
    g.add((ITEM, KG.sentimentRevision, rdflib.Literal("sentiment-5999fe131d8f")))
    g.add((ITEM, KG.newsCategory, rdflib.Literal("market_analyst_sentiment")))
    g.add((ITEM, KG.categoryScore, _decimal("0.99")))
    g.add((ITEM, KG.groupLabel, rdflib.Literal("market_view")))
    g.add((ITEM, KG.categoryRevision, rdflib.Literal("category-9b2c6a65a6f4")))
    g.add((ITEM, KG.articleId, _integer(174832)))
    g.add((ITEM, KG.bodyHash, rdflib.Literal("a" * 64)))
    g.add((ITEM, KG.sourceDomain, rdflib.Literal("cnbc.com")))
    return g


def _validate(data: rdflib.Graph) -> tuple[bool, rdflib.Graph]:
    conforms, results, _ = pyshacl.validate(data, shacl_graph=shapes())
    assert isinstance(results, rdflib.Graph)
    return conforms, results


def _focus_paths(results: rdflib.Graph) -> set[tuple[Node | None, Node | None]]:
    return {
        (results.value(result, SH.focusNode), results.value(result, SH.resultPath))
        for result in results.subjects(SH.focusNode, None)
    }


def test_the_positive_fixture_conforms() -> None:
    conforms, results = _validate(_item())
    assert conforms, results.serialize(format="turtle")


def test_a_missing_item_id_is_caught() -> None:
    g = _item()
    g.remove((ITEM, KG.itemId, None))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.itemId)}


def test_a_string_date_is_caught() -> None:
    g = _item()
    g.set((ITEM, KG.newsDate, rdflib.Literal("2021-12-01")))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.newsDate)}


def test_a_probability_above_one_is_caught() -> None:
    g = _item()
    g.set((ITEM, KG.sentimentScore, _decimal("1.2")))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.sentimentScore)}


def test_a_text_over_two_thousand_characters_is_caught() -> None:
    g = _item()
    g.set((ITEM, KG.newsText, rdflib.Literal("x" * 2001)))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.newsText)}


def test_an_unknown_item_kind_is_caught() -> None:
    g = _item()
    g.set((ITEM, KG.itemKind, rdflib.Literal("article")))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.itemKind)}


def test_an_untyped_asset_link_is_caught() -> None:
    g = _item()
    g.add((ITEM, KG.newsItemOfAsset, KG.NotAnAsset))
    assert _focus_paths(_validate(g)[1]) == {(ITEM, KG.newsItemOfAsset)}
