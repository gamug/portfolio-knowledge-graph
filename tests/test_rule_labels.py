"""Bilingual labels and comments on the GUARD and veto rule individuals (Work item 43, T-753)."""

from __future__ import annotations

from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

GUARD_RULES = {
    "L0_CARTERA_ACTIVATION",
    "L0_CARTERA_SCALE_CHANGE",
    "L0_CARTERA_RECOVERY",
    "L1_BP_STOP",
    "L1_BP_REENTRY",
    "L1_BP_STOP_BLOCKED",
}
VETO_RULES = {
    "LEVERAGE_EXTREME",
    "NEGATIVE_FCF",
    "UTILITY_CASH_COVERAGE",
    "DATA_QUALITY",
    "VOLATILITY_SHOCK",
    "CRASH_Z_SCORE",
    "PRICE_CRASH",
    "LIQUIDITY_DISTRESS",
    "EARNINGS_MISSING",
    "BREAK_TREND_200",
}


def graph() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "rules.ttl", format="turtle")


def rules(g: rdflib.Graph, ids: set[str]) -> list[rdflib.URIRef]:
    out = []
    for subject in g.subjects(RDF.type, KG.RuleDefinition):
        if not isinstance(subject, rdflib.URIRef):
            continue
        if str(g.value(subject, KG.ruleId)) in ids:
            out.append(subject)
    return out


def _values(g: rdflib.Graph, subject: rdflib.URIRef, predicate: rdflib.URIRef) -> list[str]:
    return [str(value) for value in g.objects(subject, predicate)]


def test_every_guard_and_veto_rule_has_two_labels_and_two_comments() -> None:
    g = graph()
    for rule in rules(g, GUARD_RULES | VETO_RULES):
        labels = list(g.objects(rule, RDFS.label))
        comments = list(g.objects(rule, RDFS.comment))
        assert {getattr(value, "language", None) for value in labels} == {"en", "es"}, rule
        assert {getattr(value, "language", None) for value in comments} == {
            "en",
            "es",
        }, rule


def test_the_rule_labels_are_the_glossary_names() -> None:
    g = graph()
    expected = {
        "LEVERAGE_EXTREME": "Extreme leverage",
        "NEGATIVE_FCF": "Negative free cash flow",
        "UTILITY_CASH_COVERAGE": "Weak operating cash flow to debt (regulated utilities)",
        "DATA_QUALITY": "Data-quality failure",
        "VOLATILITY_SHOCK": "Volatility shock",
        "CRASH_Z_SCORE": "Abnormal price drop",
        "PRICE_CRASH": "Deep 90-day drawdown",
        "LIQUIDITY_DISTRESS": "Liquidity distress",
        "EARNINGS_MISSING": "Stale fundamentals",
        "BREAK_TREND_200": "Below 200-day trend (flag only)",
        "L1_BP_STOP": "Exit by Basing Points rule",
        "L1_BP_REENTRY": "Re-entry after Basing Points exit",
        "L1_BP_STOP_BLOCKED": "Blocked Basing Points stop",
        "L0_CARTERA_ACTIVATION": "Portfolio tail-risk activation",
        "L0_CARTERA_SCALE_CHANGE": "Portfolio tail-risk scale change",
        "L0_CARTERA_RECOVERY": "Portfolio tail-risk recovery",
    }
    for code, label in expected.items():
        candidates = rules(g, {code})
        assert candidates, code
        assert label in {
            str(value)
            for value in g.objects(candidates[0], RDFS.label)
            if getattr(value, "language", None) == "en"
        }, code


def test_the_five_removed_guard_rules_are_absent() -> None:
    g = graph()
    for code in ("L1_STOP_LOSS", "L1_REENTRY", "L2_NEWS", "L3_VOL", "L4_DD"):
        assert not rules(g, {code}), code


def test_no_rule_comment_mentions_tiingo_or_grossman_zhou() -> None:
    g = graph()
    for rule in rules(g, GUARD_RULES | VETO_RULES):
        for comment in _values(g, rule, RDFS.comment):
            lowered = comment.lower()
            assert "tiingo" not in lowered, rule
            assert "grossman" not in lowered, rule
            assert "zhou" not in lowered, rule


def test_break_trend_is_a_flag_not_a_veto() -> None:
    g = graph()
    rule = rules(g, {"BREAK_TREND_200"})[0]
    en = next(
        str(value)
        for value in g.objects(rule, RDFS.comment)
        if getattr(value, "language", None) == "en"
    )
    assert "neither excludes it nor subtracts points" in en
    assert "never say it was vetoed" in en


def test_the_superseded_liquidity_rule_keeps_its_history() -> None:
    g = graph()
    old = next(
        subject
        for subject in g.subjects(RDF.type, KG.RuleDefinition)
        if g.value(subject, KG.ruleId) == rdflib.Literal("LIQUIDITY_DISTRESS")
        and g.value(subject, KG.validTo) is not None
    )
    en = next(
        str(value)
        for value in g.objects(old, RDFS.comment)
        if getattr(value, "language", None) == "en"
    )
    assert "Superseded on 2026-10-10" in en
