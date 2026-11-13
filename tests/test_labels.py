"""The presentation vocabulary in ``schema/labels.ttl`` (Work item 43, T-751; T-816).

It is in FR-001 and the load plan. This test fixes the vocabulary contract: one label and one
comment per language, one notation per scheme, the six windows, the five final strategies, the
37 fundamental metric concepts and the absence of C1/rule/candidate_y2.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, SKOS

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

SCHEMES = {
    "WindowScheme",
    "RunLabelScheme",
    "StrategyScheme",
    "GuardScheme",
    "VetoClassScheme",
    "MarkerScheme",
    "ScoreComponentScheme",
    "RankScheme",
    "ConfigScheme",
    "ProcessScheme",
    "FundamentalMetricScheme",
}
WINDOW_CODES = {"P1", "H1", "P3", "H2", "P2", "H3", "C1"}
STRATEGY_CODES = {
    "TOPN_MV_GUARD_NO_NLP",
    "TOPN_MV_NOGUARD",
    "MARKOWITZ_BASE",
    "MARKOWITZ_BASE_GUARD",
    "MARKOWITZ_MV",
}


def graph() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "labels.ttl", format="turtle")


def _lang(
    g: rdflib.Graph, subject: rdflib.URIRef, predicate: rdflib.URIRef, language: str
) -> rdflib.term.Node | None:
    return next(
        (
            value
            for value in g.objects(subject, predicate)
            if getattr(value, "language", None) == language
        ),
        None,
    )


def concepts(g: rdflib.Graph) -> set[rdflib.URIRef]:
    return {
        s
        for s in g.subjects(RDF.type, SKOS.Concept)
        if isinstance(s, rdflib.URIRef) and (s, KG.labelScheme, KG.PresentationScheme) in g
    }


def test_the_file_parses_and_has_the_eleven_schemes() -> None:
    g = graph()
    schemes = {
        str(s).rsplit("#", 1)[-1]
        for s in g.subjects(RDF.type, SKOS.ConceptScheme)
        if isinstance(s, rdflib.URIRef)
    }
    assert schemes == SCHEMES


FUNDAMENTAL_METRIC_CODES = {
    "asset_turnover",
    "capex_intensity",
    "cash_ratio",
    "current_ratio",
    "debt_to_assets",
    "debt_to_equity",
    "ebitda",
    "effective_tax_rate",
    "free_cash_flow_conversion",
    "free_cash_flow_growth",
    "free_cash_flow_margin",
    "gross_margin",
    "interest_coverage",
    "inventory_turnover",
    "net_debt_to_ebitda",
    "net_income_cagr",
    "net_income_growth",
    "net_margin",
    "nopat",
    "operating_cash_flow_cagr",
    "operating_cash_flow_margin",
    "operating_income_growth",
    "operating_margin",
    "quick_ratio",
    "receivables_turnover",
    "return_on_assets",
    "return_on_equity",
    "return_on_invested_capital",
    "return_on_invested_capital_effective_rate",
    "revenue_cagr",
    "revenue_growth",
    "enterprise_fcf_yield",
    "free_cash_flow_yield",
    "sbc_adjusted_fcf_yield",
    "utility_cash_coverage_3y",
    "market_capitalization",
    "enterprise_value",
}


def test_the_fundamental_metric_scheme_has_the_37_final_concepts() -> None:
    g = graph()
    fundamental = [
        concept
        for concept in concepts(g)
        if (concept, SKOS.inScheme, KG.FundamentalMetricScheme) in g
    ]
    assert len(fundamental) == 37
    assert {
        str(g.value(concept, SKOS.notation)) for concept in fundamental
    } == FUNDAMENTAL_METRIC_CODES
    assert "value_inputs" not in FUNDAMENTAL_METRIC_CODES
    for concept in fundamental:
        assert g.value(concept, KG.metricGroup) is not None
        assert str(g.value(concept, KG.metricUnit)) in {"ratio", "x", "usd"}


def test_every_concept_has_one_notation_per_scheme_and_both_languages() -> None:
    g = graph()
    notations: dict[str, set[str]] = defaultdict(set)
    for concept in concepts(g):
        assert (concept, KG.labelScheme, KG.PresentationScheme) in g
        schemes = list(g.objects(concept, SKOS.inScheme))
        assert len(schemes) == 1, concept
        scheme = str(schemes[0]).rsplit("#", 1)[-1]
        assert scheme in SCHEMES
        values = list(g.objects(concept, SKOS.notation))
        assert len(values) == 1, concept
        notation = str(values[0])
        assert notation not in notations[scheme], (scheme, notation)
        notations[scheme].add(notation)
        for predicate in (RDFS.label, RDFS.comment):
            en = [o for o in g.objects(concept, predicate) if getattr(o, "language", None) == "en"]
            es = [o for o in g.objects(concept, predicate) if getattr(o, "language", None) == "es"]
            assert len(en) == 1, (concept, predicate)
            assert len(es) == 1, (concept, predicate)
        for alt in g.objects(concept, SKOS.altLabel):
            assert getattr(alt, "language", None) in {"en", "es"}, (concept, alt)


def test_the_seven_windows_have_dates_and_the_six_have_conditions() -> None:
    g = graph()
    window_concepts = [c for c in concepts(g) if (c, SKOS.inScheme, KG.WindowScheme) in g]
    assert len(window_concepts) == 7
    codes = {str(g.value(c, SKOS.notation)) for c in window_concepts}
    assert codes == WINDOW_CODES
    for concept in window_concepts:
        assert (concept, KG.windowStart, None) in g
        assert (concept, KG.windowEnd, None) in g
        if str(g.value(concept, SKOS.notation)) != "C1":
            assert len(list(g.objects(concept, KG.historicalCondition))) == 2
            assert len(list(g.objects(concept, KG.finalConfigurationCondition))) == 2
    window_5 = next(c for c in window_concepts if str(g.value(c, SKOS.notation)) == "P2")
    assert "Feb\u2013Sep 2025 (P2)" in str(_lang(g, window_5, RDFS.label, "en"))
    assert not any("volatil" in str(alt).lower() for alt in g.objects(window_5, SKOS.altLabel))


def test_the_run_label_is_only_final() -> None:
    g = graph()
    labels = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.RunLabelScheme) in g
    }
    assert labels == {"final"}
    assert not any(str(g.value(c, SKOS.notation)) in {"rule", "candidate_y2"} for c in concepts(g))


def test_the_five_strategy_notations_are_the_only_ones() -> None:
    g = graph()
    strategies = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.StrategyScheme) in g
    }
    assert strategies == STRATEGY_CODES
    assert not any(
        code in strategies
        for code in (
            "B0",
            "B0 NOGUARD",
            "MCF",
            "MARKOWITZ_SAMPLE",
            "MARKOWITZ_SAMPLE_GUARD",
            "BMK_EXPO",
            "BMK_BETA",
            "BMK_VOL",
            "TOPN_MV_GUARD",
        )
    )
    mean_variance = next(
        c for c in concepts(g) if g.value(c, SKOS.notation) == rdflib.Literal("MARKOWITZ_MV")
    )
    assert "Base Markowitz (mean-variance)" in str(_lang(g, mean_variance, RDFS.label, "en"))
    assert "Markowitz base de media-varianza" in str(_lang(g, mean_variance, RDFS.label, "es"))


def test_guard_layers_states_and_action_statuses_are_present() -> None:
    g = graph()
    guard = [c for c in concepts(g) if (c, SKOS.inScheme, KG.GuardScheme) in g]
    notations = {str(g.value(c, SKOS.notation)) for c in guard}
    assert {"GUARD", "1"} <= notations
    assert {"ENTER", "EXIT", "ACTIVE", "COOLDOWN", "SCALE"} <= notations
    assert {"APPLIED", "ARM_DISABLED", "NOT_HELD", "SUPERSEDED"} <= notations
    layer_1 = next(c for c in guard if g.value(c, SKOS.notation) == rdflib.Literal(1))
    assert "Basing Points" in str(_lang(g, layer_1, RDFS.comment, "en"))
    assert "Basing Points" in str(_lang(g, layer_1, RDFS.comment, "es"))
    assert KG.Concept_PortfolioGuard in guard
    assert KG.Concept_RetentionCounter not in guard


def test_the_three_veto_classes_and_markers_are_present() -> None:
    g = graph()
    veto = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.VetoClassScheme) in g
    }
    markers = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.MarkerScheme) in g
    }
    assert veto == {"HARD", "SOFT", "INDICATOR"}
    assert markers == {"HARD", "UNSCORED", "UNPRICED", "NO_RISK_MODEL"}


def test_rank_and_score_components_are_present() -> None:
    g = graph()
    rank = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.RankScheme) in g
    }
    assert rank == {"rank", "rank_e"}
    rank_e = next(c for c in concepts(g) if g.value(c, SKOS.notation) == rdflib.Literal("rank_e"))
    assert "not loaded" in str(_lang(g, rank_e, RDFS.comment, "en")).lower()
    components = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.ScoreComponentScheme) in g
    }
    assert components == {"FUNDAMENTAL", "TECHNICAL", "VALORIZATION", "SECTOR"}


def test_the_objective_concept_is_the_registered_class_not_the_weighting() -> None:
    g = graph()
    objective = next(
        c for c in concepts(g) if g.value(c, SKOS.notation) == rdflib.Literal("min_var")
    )
    assert str(_lang(g, objective, RDFS.label, "en")) == "Registered optimization class"
    comment = str(_lang(g, objective, RDFS.comment, "en")).lower()
    assert "not the satellite weighting" in comment
    assert "satellite_weighting" in comment


def test_configuration_and_process_terms_use_the_expected_schemes() -> None:
    g = graph()
    config = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.ConfigScheme) in g
    }
    assert {
        "core_weight",
        "pool_m",
        "top_n",
        "satellite_weighting",
        "min_var",
    } <= config
    process = {
        str(g.value(c, SKOS.notation))
        for c in concepts(g)
        if (c, SKOS.inScheme, KG.ProcessScheme) in g
    }
    assert {
        "IN_SAMPLE",
        "COUNTING_RULE",
        "CONCEPTUAL_ANSWER",
        "NOT_IN_KNOWLEDGE_BASE",
    } <= process


def test_the_vocabulary_has_no_run_iri() -> None:
    g = graph()
    subjects = {str(subject) for subject in g.subjects()}
    assert all(subject.startswith(str(KG)) for subject in subjects)
    assert not any(
        marker in subject
        for subject in subjects
        for marker in (
            "Book_",
            "GuardAlert_",
            "GuardAction_",
            "Veto_",
            "PeriodSummary_",
        )
    )
