"""Direct bilingual labels/comments on schema classes/properties (Work item 43, T-754)."""

from __future__ import annotations

from pathlib import Path

import rdflib
from rdflib.namespace import RDFS, SKOS

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

CLASSES = ("StrategyBook", "GuardAlert", "GuardAction", "Veto")
PROPERTIES = (
    "attractivenessScore",
    "componentValue",
    "targetWeight",
    "selectedForBook",
    "rankPosition",
    "nGuardActions",
    "bookWeightingRule",
    "topN",
    "maxNameWeight",
    "maxSectorWeight",
    "softVetoPenalty",
    "excludeHardVetoed",
    "cashFraction",
    "trendState",
    "nRebalances",
    "totalTurnover",
    "totalCostBps",
    "maxDrawdown",
    "exPostSharpe",
    "grossReturn",
    "netReturn",
    "turnover",
    "costReturn",
    "referenceName",
    "referenceTotalReturn",
    "referenceMaxDrawdown",
    "nSessions",
    "dateFrom",
    "dateTo",
)


def tbox() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")


def _values(
    g: rdflib.Graph, subject: rdflib.URIRef, predicate: rdflib.URIRef
) -> list[rdflib.Literal]:
    return [value for value in g.objects(subject, predicate) if isinstance(value, rdflib.Literal)]


def _languages(values: list[rdflib.Literal]) -> set[str | None]:
    return {value.language for value in values}


def test_the_selected_classes_have_bilingual_comments() -> None:
    g = tbox()
    for name in CLASSES:
        comments = _values(g, KG[name], RDFS.comment)
        assert _languages(comments) >= {"en", "es"}, name


def test_the_selected_properties_have_bilingual_labels_and_comments() -> None:
    g = tbox()
    for name in PROPERTIES:
        labels = _values(g, KG[name], RDFS.label)
        comments = _values(g, KG[name], RDFS.comment)
        assert _languages(labels) >= {"en", "es"}, name
        assert _languages(comments) >= {"en", "es"}, name


def test_objective_is_the_registered_class_and_keeps_the_wi41_facts() -> None:
    g = tbox()
    labels = _values(g, KG.objective, RDFS.label)
    assert "Registered optimization class" in {
        str(value) for value in labels if value.language == "en"
    }
    assert "Clasificación de optimización registrada" in {
        str(value) for value in labels if value.language == "es"
    }
    en = next(
        str(value) for value in _values(g, KG.objective, RDFS.comment) if value.language == "en"
    )
    assert "fixed literal per arm" in en
    assert "weighting objective of the TOPN_MV_* books" in en
    assert "max_sharpe" in en


def test_n_guard_actions_has_the_not_applicable_caveat() -> None:
    g = tbox()
    en = next(
        str(value) for value in _values(g, KG.nGuardActions, RDFS.comment) if value.language == "en"
    )
    es = next(
        str(value) for value in _values(g, KG.nGuardActions, RDFS.comment) if value.language == "es"
    )
    assert "0 means not applicable" in en
    assert "MARKOWITZ_BASE" in en and "TOPN_MV_NOGUARD" in en and "MARKOWITZ_MV" in en
    assert "0 significa no aplicable" in es


def test_metric_type_concepts_have_bilingual_labels_and_comments() -> None:
    g = rdflib.Graph().parse(SCHEMA / "reference.ttl", format="turtle")
    for name in (
        "ScoreFinanciero",
        "ScoreCuantitativo",
        "ScoreTecnico",
        "Sentiment",
        "SectorRelativeMomentum",
    ):
        concept = KG[name]
        labels = _values(g, concept, RDFS.label)
        comments = _values(g, concept, RDFS.comment)
        assert _languages(labels) >= {"en", "es"}, name
        assert _languages(comments) >= {"en", "es"}, name
        assert (concept, SKOS.inScheme, KG.MetricTypeScheme) in g


def test_the_book_weighting_rule_is_not_the_portfolio_weighting() -> None:
    g = tbox()
    en = next(
        str(value)
        for value in _values(g, KG.bookWeightingRule, RDFS.comment)
        if value.language == "en"
    )
    assert "attractiveness score scheme" in en
    assert "not satellite_weighting" in en
