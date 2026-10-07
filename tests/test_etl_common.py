"""Hermetic tests for ``etl.common`` (T-133): G1-G3 formulas, GICS rollup, provenance, Turtle."""

from __future__ import annotations

from pathlib import Path

import pytest
import rdflib

from etl.common import gics_rollup, provenance, severity, turtle_util

REFERENCE_TTL = Path(__file__).resolve().parent.parent / "schema" / "reference.ttl"


# --- G1 -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("positive", "negative", "expected"),
    [(0.9, 0.1, 0.8), (0.1, 0.9, -0.8), (0.5, 0.5, 0.0), (1.0, 0.0, 1.0), (0.0, 1.0, -1.0)],
)
def test_sentiment_raw_value_is_net_polarity(
    positive: float, negative: float, expected: float
) -> None:
    assert severity.sentiment_raw_value(positive, negative) == pytest.approx(expected)


def test_sentiment_raw_value_clamps_out_of_range_inputs() -> None:
    assert severity.sentiment_raw_value(2.0, -1.0) == 1.0
    assert severity.sentiment_raw_value(-2.0, 1.0) == -1.0


# --- G2 -------------------------------------------------------------------------------
def test_category_bucket_covers_nine_dimensions_in_four_buckets() -> None:
    assert len(severity.CATEGORY_BUCKET) == 9
    assert set(severity.CATEGORY_BUCKET.values()) == {"LEGAL", "FINANCIAL", "MARKET", "NETWORK"}


def test_winning_category_maps_known_label_and_keeps_score() -> None:
    assert severity.winning_category_and_score("legal_regulatory", 0.91) == ("LEGAL", 0.91)


@pytest.mark.parametrize("label", ["other", "", "not_a_label"])
def test_winning_category_is_none_for_other_or_unknown(label: str) -> None:
    assert severity.winning_category_and_score(label, 0.9) == (None, 0.9)


def test_creation_gate_boundaries() -> None:
    assert severity.creation_gate(0.50, 0.0)  # negative path, inclusive
    assert not severity.creation_gate(0.4999, 0.6999)
    assert severity.creation_gate(0.0, 0.70)  # category path, inclusive
    assert not severity.creation_gate(0.0, 0.0)


# --- G3 -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("negative", "top", "category", "tier"),
    [
        (0.85, 0.80, "LEGAL", "CRITICAL"),
        (0.85, 0.80, "FINANCIAL", "CRITICAL"),
        (0.85, 0.80, "MARKET", "HIGH"),  # critical needs LEGAL/FINANCIAL
        (0.85, 0.79, "LEGAL", "HIGH"),  # and top_score >= 0.80
        (0.84, 0.99, "LEGAL", "HIGH"),
        (0.70, 0.0, "MARKET", "HIGH"),
        (0.69, 0.0, "MARKET", "MODERATE"),
        (0.50, 0.0, "MARKET", "MODERATE"),
        (0.49, 0.75, "MARKET", "LOW"),  # category-confidence path alone
    ],
)
def test_compute_severity_ladder(negative: float, top: float, category: str, tier: str) -> None:
    assert severity.compute_severity(negative, top, category, "") == tier


@pytest.mark.parametrize(
    ("negative", "top", "tier"),
    [(0.2, 0.0, "MODERATE"), (0.55, 0.0, "HIGH"), (0.75, 0.0, "CRITICAL")],
)
def test_hard_trigger_keyword_bumps_one_tier(negative: float, top: float, tier: str) -> None:
    got = severity.compute_severity(negative, top, "MARKET", "Company faces a Class Action")
    assert got == tier


def test_hard_trigger_bump_caps_at_critical() -> None:
    assert severity.compute_severity(0.9, 0.9, "LEGAL", "fraud and a subpoena") == "CRITICAL"


def test_no_keyword_means_no_bump() -> None:
    assert severity.compute_severity(0.55, 0.0, "MARKET", "quarterly results") == "MODERATE"


# --- GICS rollup ----------------------------------------------------------------------
def test_lookup_known_and_unknown_sub_industry() -> None:
    sub = next(iter(gics_rollup.SUB_INDUSTRY_TO_INDUSTRY))
    assert gics_rollup.lookup(sub) == gics_rollup.SUB_INDUSTRY_TO_INDUSTRY[sub]
    assert gics_rollup.lookup("Not A Sub-Industry") is None


def test_every_rolled_up_industry_has_a_sector() -> None:
    industries = set(gics_rollup.SUB_INDUSTRY_TO_INDUSTRY.values())
    assert industries <= set(gics_rollup.INDUSTRY_TO_SECTOR)
    assert set(gics_rollup.INDUSTRY_TO_SECTOR.values()) <= set(
        gics_rollup.SECTOR_LOCAL_NAME.values()
    )


def test_rollup_targets_exist_in_reference_ttl() -> None:
    g = rdflib.Graph().parse(REFERENCE_TTL, format="turtle")
    ns = "https://thesis.local/kg/portfolio#"
    names = {s.removeprefix(ns) for s in set(g.subjects()) if isinstance(s, rdflib.URIRef)}
    assert set(gics_rollup.SUB_INDUSTRY_TO_INDUSTRY.values()) <= names
    assert set(gics_rollup.SECTOR_LOCAL_NAME.values()) <= names


def test_sector_matches() -> None:
    sub = next(iter(gics_rollup.SUB_INDUSTRY_TO_INDUSTRY))
    industry = gics_rollup.SUB_INDUSTRY_TO_INDUSTRY[sub]
    sector_local = gics_rollup.INDUSTRY_TO_SECTOR[industry]
    sector = next(k for k, v in gics_rollup.SECTOR_LOCAL_NAME.items() if v == sector_local)
    other = next(k for k, v in gics_rollup.SECTOR_LOCAL_NAME.items() if v != sector_local)
    assert gics_rollup.sector_matches(industry, sector)
    assert not gics_rollup.sector_matches(industry, other)
    assert not gics_rollup.sector_matches(industry, "Unknown Sector")


# --- provenance -----------------------------------------------------------------------
def test_article_provenance_id() -> None:
    assert provenance.article_provenance_id(42) == "articles:42"


# --- Turtle literals ------------------------------------------------------------------
def test_esc_escapes_quote_backslash_and_control_whitespace() -> None:
    assert turtle_util.esc('a"b\\c\nd\re\tf') == 'a\\"b\\\\c\\nd\\re\\tf'


def test_str_lit_round_trips_through_rdflib() -> None:
    raw = 'He said "hi"\\\nnext\ttab'
    g = rdflib.Graph().parse(data=f"<urn:s> <urn:p> {turtle_util.str_lit(raw)} .", format="turtle")
    assert str(next(iter(g.objects()))) == raw


def test_typed_literals_parse_with_their_datatypes() -> None:
    prefix = "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    lits = [
        turtle_util.date_lit("2023-01-25"),
        turtle_util.datetime_lit("2023-01-25T10:00:00Z"),
        turtle_util.decimal_lit(0.25),
    ]
    body = " ".join(f"<urn:s> <urn:p{i}> {lit} ." for i, lit in enumerate(lits))
    g = rdflib.Graph().parse(data=prefix + body, format="turtle")
    xsd = rdflib.XSD
    assert {o.datatype for o in g.objects() if isinstance(o, rdflib.Literal)} == {
        xsd.date,
        xsd.dateTime,
        xsd.decimal,
    }


def test_clamp() -> None:
    assert turtle_util.clamp(5, 0, 1) == 1
    assert turtle_util.clamp(-5, 0, 1) == 0
    assert turtle_util.clamp(0.5, 0, 1) == 0.5
