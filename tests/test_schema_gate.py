"""The FR-001 gate as a test: ``schema/`` parses in load order and ``pyshacl``-conforms (T-134).

Runs against the real ``schema/`` files (they are the unit under test, not an upstream
dependency), so it stays hermetic: no network, no store, no ETL databases. The counts
``SPEC.md`` states for the bundle are checked too (NR-001), so a schema edit that moves
them must update the numbers in the same change.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pyshacl
import pytest
import rdflib
import rdflib.collection
from rdflib.namespace import SH

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
SPEC = SCHEMA.parent / ".specify" / "memory" / "SPEC.md"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

# Load order from schema/README.md; everything but instances.trig is Turtle.
TURTLE_FILES = ("tbox.ttl", "shapes.ttl", "reference.ttl", "rules.ttl")

# Graph name prefixes docs/07-ontology-topology.md assigns to the worked-example ABox.
ABOX_GRAPH_PREFIXES = (
    "urn:graph:ingest:",
    "urn:graph:derived:",
    "urn:graph:universe:",
    "urn:graph:portfolio:",
)


@pytest.fixture(scope="module")
def bundle() -> rdflib.Dataset:
    ds = rdflib.Dataset()
    for name in TURTLE_FILES:
        ds.parse(SCHEMA / name, format="turtle")
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return ds


@pytest.fixture(scope="module")
def shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _flat(ds: rdflib.Dataset) -> rdflib.Graph:
    """Every quad's triple in one graph, the shape ``pyshacl`` validates."""
    g = rdflib.Graph()
    for s, p, o, _ in ds.quads():
        g.add((s, p, o))
    return g


def _named_graphs(ds: rdflib.Dataset) -> set[str]:
    return {
        str(g.identifier)
        for g in ds.graphs()
        if len(g) and g.identifier != rdflib.graph.DATASET_DEFAULT_GRAPH_ID
    }


def _violations(
    data: rdflib.Graph, shapes: rdflib.Graph
) -> set[tuple[rdflib.term.Node | None, rdflib.term.Node | None]]:
    """``(focus node, result path)`` of every SHACL result, path ``None`` for node-level ones."""
    conforms, results, _ = pyshacl.validate(data, shacl_graph=shapes, meta_shacl=True)
    assert isinstance(results, rdflib.Graph)
    found = {
        (results.value(r, SH.focusNode), results.value(r, SH.resultPath))
        for r in results.subjects(SH.focusNode, None)
    }
    assert conforms == (not found)
    return found


def test_each_file_parses_alone() -> None:
    for name in TURTLE_FILES:
        assert len(rdflib.Graph().parse(SCHEMA / name, format="turtle")) > 0, name
    assert len(rdflib.Dataset().parse(SCHEMA / "instances.trig", format="trig")) > 0


def test_bundle_conforms_to_shapes(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    assert _violations(_flat(bundle), shapes) == set()


def test_a_missing_ticker_is_caught(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """The gate is not vacuous: the ticker rule alone rejects an asset with no ticker."""
    g = _flat(bundle)
    g.add((KG.BadAsset, rdflib.RDF.type, KG.Asset))
    g.add((KG.BadAsset, KG.cikNumber, rdflib.Literal("0000000001")))
    assert _violations(g, shapes) == {(KG.BadAsset, KG.tickerSymbol)}

    g.add((KG.BadAsset, KG.tickerSymbol, rdflib.Literal("BAD")))
    assert _violations(g, shapes) == set()


def test_quad_count_matches_spec(bundle: rdflib.Dataset, spec_text: str) -> None:
    """NR-001: every quad count SPEC.md states is the real one."""
    stated = {int(a or b) for a, b in re.findall(r"(\d+) quads|quads: (\d+)", spec_text)}
    assert stated, "SPEC.md states no quad count"
    assert stated == {len(list(bundle.quads()))}


def test_named_graphs_match_spec(bundle: rdflib.Dataset, spec_text: str) -> None:
    """``instances.trig`` fills as many named graphs as SPEC.md says, all with documented names."""
    names = _named_graphs(bundle)
    stated = re.search(r"(\d+)-named-graph", spec_text)
    assert stated, "SPEC.md states no named-graph count"
    assert len(names) == int(stated.group(1))
    assert {n for n in names if not n.startswith(ABOX_GRAPH_PREFIXES)} == set()
    assert "urn:graph:portfolio:current" in names


# --- per-run weight schemes (T-121) -----------------------------------------------------------

_SCHEME = KG.WS_Run
_DEC = rdflib.XSD.decimal
_INT = rdflib.XSD.integer
Extra = list[tuple[rdflib.term.Node, rdflib.term.Node]]


def _date(text: str = "2026-10-07") -> rdflib.Literal:
    return rdflib.Literal(text, datatype=rdflib.XSD.date)


def _scheme(bundle: rdflib.Dataset, extra: Extra) -> rdflib.Graph:
    """The worked example plus one scheme (one component, no ``:inverted``) with ``extra`` triples."""
    g = _flat(bundle)
    g.add((KG.WC_Run, rdflib.RDF.type, KG.WeightComponent))
    g.add((KG.WC_Run, KG.weightMetricName, rdflib.Literal("ScoreFinanciero")))
    g.add((KG.WC_Run, KG.weightValue, rdflib.Literal("0.4", datatype=_DEC)))
    g.add((_SCHEME, rdflib.RDF.type, KG.AttractivenessWeightScheme))
    g.add((_SCHEME, KG.schemeId, rdflib.Literal("cycle_run:42")))
    g.add((_SCHEME, KG.hasWeightComponent, KG.WC_Run))
    for p, o in extra:
        g.add((_SCHEME, p, o))
    return g


@pytest.mark.parametrize(
    "extra",
    [
        [(KG.cycleDate, _date())],
        [(KG.validFrom, _date())],
        [(KG.validFrom, _date()), (KG.validTo, _date("2026-10-08"))],
        [
            (KG.cycleDate, _date()),
            (KG.runId, rdflib.Literal("cycle_run:42")),
            (KG.bookWeightingRule, rdflib.Literal("score_tilt")),
            (KG.topN, rdflib.Literal("30", datatype=_INT)),
            (KG.maxNameWeight, rdflib.Literal("0.05", datatype=_DEC)),
            (KG.maxSectorWeight, rdflib.Literal("0.25", datatype=_DEC)),
            (KG.softVetoPenalty, rdflib.Literal("15", datatype=_DEC)),
        ],
    ],
    ids=["per-run", "valid-time", "valid-time closed", "per-run, every knob"],
)
def test_a_weight_scheme_of_either_kind_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, extra: Extra
) -> None:
    assert _violations(_scheme(bundle, extra), shapes) == set()


_RUN = (KG.cycleDate, _date())


@pytest.mark.parametrize(
    ("extra", "path"),
    [
        ([], None),  # neither kind: the sh:xone fails on the node itself
        ([_RUN, (KG.validFrom, _date())], None),  # both kinds
        ([_RUN, (KG.validTo, _date("2026-10-08"))], None),  # a per-run scheme is never closed
        ([_RUN, (KG.cycleDate, _date("2026-10-08"))], KG.cycleDate),
        ([(KG.cycleDate, rdflib.Literal("2026-10-07"))], KG.cycleDate),  # the only date, a string
        ([_RUN, (KG.runId, rdflib.Literal(42))], KG.runId),
        (
            [
                _RUN,
                (KG.runId, rdflib.Literal("cycle_run:42")),
                (KG.runId, rdflib.Literal("cycle_run:43")),
            ],
            KG.runId,
        ),
        ([_RUN, (KG.topN, rdflib.Literal("0", datatype=_INT))], KG.topN),
        ([_RUN, (KG.topN, rdflib.Literal("5.5", datatype=_DEC))], KG.topN),
        ([_RUN, (KG.maxNameWeight, rdflib.Literal("1.5", datatype=_DEC))], KG.maxNameWeight),
        ([_RUN, (KG.maxSectorWeight, rdflib.Literal("-0.1", datatype=_DEC))], KG.maxSectorWeight),
        ([_RUN, (KG.softVetoPenalty, rdflib.Literal("-1", datatype=_DEC))], KG.softVetoPenalty),
        ([_RUN, (KG.bookWeightingRule, rdflib.Literal(1))], KG.bookWeightingRule),
        (
            [
                _RUN,
                (KG.bookWeightingRule, rdflib.Literal("a")),
                (KG.bookWeightingRule, rdflib.Literal("b")),
            ],
            KG.bookWeightingRule,
        ),
    ],
    ids=[
        "no date",
        "both dates",
        "closed per-run",
        "two cycle dates",
        "cycle date not a date",
        "run id not a string",
        "two run ids",
        "topN 0",
        "topN not an integer",
        "name cap above 1",
        "sector cap below 0",
        "negative penalty",
        "rule not a string",
        "two rules",
    ],
)
def test_a_malformed_weight_scheme_is_caught(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    extra: Extra,
    path: rdflib.term.Node | None,
) -> None:
    assert _violations(_scheme(bundle, extra), shapes) == {(_SCHEME, path)}


def test_a_weight_component_may_omit_inverted(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """``_scheme`` builds its component without ``:inverted``; one given still has to be a boolean."""
    g = _scheme(bundle, [_RUN])
    assert _violations(g, shapes) == set()
    g.add((KG.WC_Run, KG.inverted, rdflib.Literal("yes")))
    assert _violations(g, shapes) == {(KG.WC_Run, KG.inverted)}


# --- how many components a scheme weighs (T-190) -----------------------------------------------

# FUNDAMENTAL, VALORIZATION, TECHNICAL
_NEW_RUN = ("ScoreFinanciero", "ScoreCuantitativo", "ScoreTecnico")


def _weighing(bundle: rdflib.Dataset, names: tuple[str, ...]) -> rdflib.Graph:
    """A per-run scheme with one component per ``names`` (none at all when ``names`` is empty)."""
    g = _scheme(bundle, [_RUN])
    g.remove((_SCHEME, KG.hasWeightComponent, KG.WC_Run))
    g.remove((KG.WC_Run, None, None))
    for i, name in enumerate(names):
        node = KG[f"WC_Run_{i}"]
        g.add((node, rdflib.RDF.type, KG.WeightComponent))
        g.add((node, KG.weightMetricName, rdflib.Literal(name)))
        g.add((node, KG.weightValue, rdflib.Literal("0.25", datatype=_DEC)))
        g.add((_SCHEME, KG.hasWeightComponent, node))
    return g


@pytest.mark.parametrize(
    "names",
    [
        _NEW_RUN,  # a new run weighs three score types, no Sentiment
        (*_NEW_RUN, "Sentiment"),  # an earlier run weighed four
        _NEW_RUN[:2],  # an asset can lack a component in a three-type run (T-155)
        _NEW_RUN[:1],
    ],
    ids=["three, no Sentiment", "four, with Sentiment", "two", "one"],
)
def test_a_scheme_weighing_one_to_four_score_types_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, names: tuple[str, ...]
) -> None:
    assert _violations(_weighing(bundle, names), shapes) == set()


def test_the_shape_neither_sums_the_weights_nor_rejects_a_repeated_name(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """The shape checks neither (two ``ScoreFinanciero`` of 0.25 conform); the read boundary rejects the repeat."""
    assert _violations(_weighing(bundle, ("ScoreFinanciero", "ScoreFinanciero")), shapes) == set()


def test_a_scheme_weighing_nothing_is_caught(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    assert _violations(_weighing(bundle, ()), shapes) == {(_SCHEME, KG.hasWeightComponent)}


def test_a_component_named_outside_the_five_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _weighing(bundle, (*_NEW_RUN, "ScoreMacro"))
    assert _violations(g, shapes) == {(KG.WC_Run_3, KG.weightMetricName)}


# --- FUNDAMENTAL's rawValue range (T-177) -------------------------------------------------------


def _fundamental(bundle: rdflib.Dataset, raw: str) -> rdflib.Graph:
    """The worked example plus one FUNDAMENTAL snapshot with ``raw`` as its ``rawValue``."""
    g = _flat(bundle)
    snap = KG.Snap_Fundamental_T177
    g.add((snap, rdflib.RDF.type, KG.ScoreSnapshot))
    g.add((snap, KG.agentOrigin, rdflib.Literal("FUNDAMENTAL")))
    g.add((snap, KG.metricType, rdflib.Literal("ScoreFinanciero")))
    g.add((snap, KG.timestamp, rdflib.Literal("2026-10-09T06:00:00", datatype=rdflib.XSD.dateTime)))
    g.add((snap, KG.availableAt, _date("2026-10-09")))
    g.add((snap, KG.rawValue, rdflib.Literal(raw, datatype=_DEC)))
    return g


@pytest.mark.parametrize(
    "raw", ["0.0", "57.3", "100.0"], ids=["lower bound", "middle", "upper bound"]
)
def test_a_fundamental_raw_value_in_0_to_100_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, raw: str
) -> None:
    assert _violations(_fundamental(bundle, raw), shapes) == set()


@pytest.mark.parametrize("raw", ["-0.1", "100.1"], ids=["below 0", "above 100"])
def test_a_fundamental_raw_value_outside_0_to_100_is_rejected(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, raw: str
) -> None:
    """Only ``rawValue`` differs from the conforming cases above, so the bound is what rejects it."""
    assert _violations(_fundamental(bundle, raw), shapes) == {(KG.Snap_Fundamental_T177, None)}


@pytest.mark.parametrize(
    "value",
    [rdflib.Literal("50", datatype=_INT), rdflib.Literal("50")],
    ids=["integer", "string"],
)
def test_a_fundamental_raw_value_that_is_not_a_decimal_is_rejected(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, value: rdflib.Literal
) -> None:
    """In range by value, wrong by type: the new branch keeps ``sh:datatype xsd:decimal``.

    The property's own datatype shape also reports on ``rawValue``, so both results are expected.
    """
    g = _fundamental(bundle, "50.0")
    g.remove((KG.Snap_Fundamental_T177, KG.rawValue, None))
    g.add((KG.Snap_Fundamental_T177, KG.rawValue, value))
    assert _violations(g, shapes) == {
        (KG.Snap_Fundamental_T177, None),
        (KG.Snap_Fundamental_T177, KG.rawValue),
    }


def test_a_fundamental_raw_value_is_bounded_even_with_a_normalized_score(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """``normalizedScore`` is optional for FUNDAMENTAL (T-171), not a way around the bound."""
    g = _fundamental(bundle, "100.1")
    g.add((KG.Snap_Fundamental_T177, KG.normalizedScore, rdflib.Literal("0.5", datatype=_DEC)))
    assert _violations(g, shapes) == {(KG.Snap_Fundamental_T177, None)}


def test_a_second_fundamental_raw_value_is_rejected_whatever_its_range(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """Two values, one of them out of range: the functional-property rule and the bound both apply."""
    g = _fundamental(bundle, "50.0")
    g.add((KG.Snap_Fundamental_T177, KG.rawValue, rdflib.Literal("150.0", datatype=_DEC)))
    assert (KG.Snap_Fundamental_T177, KG.rawValue) in _violations(g, shapes)


def _raw_value_bounds(path: Path, metric: str) -> set[tuple[str, str]]:
    """``(minInclusive, maxInclusive)`` of the ``rawValue`` branch that pairs with ``metric``."""
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    bounds: set[tuple[str, str]] = set()
    for or_list in g.objects(None, SH["or"]):
        branches = list(rdflib.collection.Collection(g, or_list))
        if not any(
            (inner, SH.hasValue, rdflib.Literal(metric)) in g
            for b in branches
            for inner in g.objects(b, SH["not"])
        ):
            continue
        for b in branches:
            if (b, SH.path, KG.rawValue) in g:
                bounds.add((str(g.value(b, SH.minInclusive)), str(g.value(b, SH.maxInclusive))))
    return bounds


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("ScoreFinanciero", ("0.0", "100.0")),
        ("SectorRelativeMomentum", ("-100.0", "100.0")),
        ("Sentiment", ("-1.0", "1.0")),
    ],
)
def test_the_target_schema_bounds_raw_value_like_shapes_ttl(
    metric: str, expected: tuple[str, str]
) -> None:
    """``kg_target_schema.ttl`` is the proposal sent upstream; round 5 of PR #82 found it unbounded."""
    in_shapes = _raw_value_bounds(SCHEMA / "shapes.ttl", metric)
    assert in_shapes == {expected}
    assert _raw_value_bounds(SCHEMA.parent / "kg_target_schema.ttl", metric) == in_shapes


# --- a Veto's sightings against its clearing (T-185) --------------------------------------------

_VETO = KG.Veto_T185


def _veto(bundle: rdflib.Dataset, *, cleared: str | None, seen: tuple[str, ...]) -> rdflib.Graph:
    """The worked example plus one Veto raised 2026-01-01 with the given clearing and sighting dates."""
    g = _flat(bundle)
    g.add((_VETO, rdflib.RDF.type, KG.Veto))
    g.add((_VETO, KG.raisedOn, _date("2026-01-01")))
    if cleared:
        g.add((_VETO, KG.clearedOn, _date(cleared)))
    for day in seen:
        g.add((_VETO, KG.lastSeenOn, _date(day)))
    return g


@pytest.mark.parametrize(
    ("cleared", "seen"),
    [
        ("2026-03-31", ("2026-02-10", "2026-03-15")),  # cleared after its last sighting
        ("2026-03-31", ("2026-03-31",)),  # the same day passes
        (None, ("2026-02-10", "2026-04-07")),  # still active: nothing to compare
        ("2026-03-31", ()),  # never seen again after it was raised
    ],
    ids=["cleared after", "same day", "still active", "no sightings"],
)
def test_a_veto_cleared_on_or_after_its_sightings_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, cleared: str | None, seen: tuple[str, ...]
) -> None:
    assert _violations(_veto(bundle, cleared=cleared, seen=seen), shapes) == set()


def test_a_veto_cleared_before_a_sighting_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """One sighting after the clearing is enough, whatever the others are."""
    g = _veto(bundle, cleared="2026-03-31", seen=("2026-02-10", "2026-04-07"))
    assert _violations(g, shapes) == {(_VETO, KG.lastSeenOn)}


def _less_than_or_equals(path: Path) -> set[tuple[str, str]]:
    """(property, target) for each ``sh:lessThanOrEquals`` inside the Veto shape of ``path``."""
    g = rdflib.Graph().parse(path, format="turtle")
    sh = SH
    found: set[tuple[str, str]] = set()
    for prop in g.objects(KG.VetoShape, sh.property):
        for target in g.objects(prop, sh.lessThanOrEquals):
            found.add(
                (str(g.value(prop, sh.path)).rpartition("#")[2], str(target).rpartition("#")[2])
            )
    return found


def _expires_on_shape(path: Path) -> tuple[set[str], set[str]]:
    """The datatype and the ``sh:maxCount`` values of the ``expiresOn`` property shape in ``VetoShape``."""
    g = rdflib.Graph().parse(path, format="turtle")
    types: set[str] = set()
    counts: set[str] = set()
    for prop in g.objects(KG.VetoShape, SH.property):
        if (prop, SH.path, KG.expiresOn) in g:
            types |= {str(t) for t in g.objects(prop, SH.datatype)}
            counts |= {str(c) for c in g.objects(prop, SH.maxCount)}
    return types, counts


def test_the_target_schema_shapes_expires_on_like_shapes_ttl() -> None:
    """Present in both, an ``xsd:date``, and with no ``maxCount`` (multi-valued like ``lastSeenOn``)."""
    in_shapes = _expires_on_shape(SCHEMA / "shapes.ttl")
    assert in_shapes == ({"http://www.w3.org/2001/XMLSchema#date"}, set())
    assert _expires_on_shape(SCHEMA.parent / "kg_target_schema.ttl") == in_shapes


def test_the_target_schema_orders_a_veto_like_shapes_ttl() -> None:
    """``kg_target_schema.ttl`` carries the same Veto date order. The dates come from upstream's own
    ``veto`` rows, so the proposal is kept equal to ``shapes.ttl`` and needs no action from them."""
    in_shapes = _less_than_or_equals(SCHEMA / "shapes.ttl")
    assert in_shapes == {
        ("raisedOn", "lastSeenOn"),
        ("raisedOn", "expiresOn"),
        ("lastSeenOn", "clearedOn"),
    }
    assert _less_than_or_equals(SCHEMA.parent / "kg_target_schema.ttl") == in_shapes


# --- T-187: the nine-rule catalog and ``:penaltyPoints`` -----------------------------------------

_RULE = KG.Rule_T187


def _rule(bundle: rdflib.Dataset, **extra: rdflib.term.Node) -> rdflib.Graph:
    """The worked example plus one SOFT rule, a single threshold leaf, with extra properties."""
    g = _flat(bundle)
    leaf = KG.Cmp_T187
    g.add((leaf, rdflib.RDF.type, KG.ThresholdComparison))
    g.add((leaf, KG.metricName, rdflib.Literal("liquidity.current_ratio")))
    g.add((leaf, KG.operator, rdflib.Literal("<")))
    g.add((leaf, KG.thresholdValue, rdflib.Literal("1.0", datatype=rdflib.XSD.decimal)))
    g.add((_RULE, rdflib.RDF.type, KG.RuleDefinition))
    g.add((_RULE, KG.ruleId, rdflib.Literal("T187")))
    g.add((_RULE, KG.ruleSeverity, rdflib.Literal("SOFT")))
    g.add((_RULE, KG.validFrom, _date("2026-10-13")))
    g.add((_RULE, KG.hasClause, leaf))
    for name, value in extra.items():
        g.add((_RULE, KG[name], value))
    return g


def _decimal(text: str) -> rdflib.Literal:
    return rdflib.Literal(text, datatype=rdflib.XSD.decimal)


@pytest.mark.parametrize("points", ["0", "15", "2.5"])
def test_penalty_points_of_at_least_zero_conform(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, points: str
) -> None:
    assert _violations(_rule(bundle, penaltyPoints=_decimal(points)), shapes) == set()


def test_a_rule_without_penalty_points_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    assert _violations(_rule(bundle), shapes) == set()


def test_negative_penalty_points_are_caught(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _rule(bundle, penaltyPoints=_decimal("-1"))
    assert _violations(g, shapes) == {(_RULE, KG.penaltyPoints)}


def test_penalty_points_that_are_not_a_decimal_are_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _rule(bundle, penaltyPoints=rdflib.Literal("15"))
    assert _violations(g, shapes) == {(_RULE, KG.penaltyPoints)}


def test_two_penalty_points_values_are_caught(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _rule(bundle, penaltyPoints=_decimal("15"))
    g.add((_RULE, KG.penaltyPoints, _decimal("0")))
    assert _violations(g, shapes) == {(_RULE, KG.penaltyPoints)}


def test_a_priority_rank_of_nine_conforms_and_ten_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    nine = _rule(bundle, priorityRank=rdflib.Literal(9))
    assert _violations(nine, shapes) == set()
    ten = _rule(bundle, priorityRank=rdflib.Literal(10))
    assert _violations(ten, shapes) == {(_RULE, KG.priorityRank)}


_ACTIVE_IDS = {
    "LEVERAGE_EXTREME": None,
    "NEGATIVE_FCF": None,
    "DATA_QUALITY": None,
    "VOLATILITY_SHOCK": None,
    "CRASH_Z_SCORE": None,
    "LIQUIDITY_DISTRESS": "15",
    "PRICE_CRASH": "15",
    "EARNINGS_MISSING": "15",
    "BREAK_TREND_200": "0",
}


def _rules_file() -> rdflib.Graph:
    """``rules.ttl`` alone: the file the store loads wholesale into ``urn:graph:rules:catalog``
    (``schema/README.md``), so a rule defined in another file is not found. Parsed on each call: a test may add to it
    without leaking into another."""
    return rdflib.Graph().parse(SCHEMA / "rules.ttl", format="turtle")


def _active_rules() -> dict[str, rdflib.term.Node]:
    """``ruleId`` to the one rule with no ``validTo`` (an active definition) in the catalog graph."""
    g = _rules_file()
    found: dict[str, rdflib.term.Node] = {}
    for rule in g.subjects(rdflib.RDF.type, KG.RuleDefinition):
        if (rule, KG.validTo, None) in g:
            continue
        rule_id = str(g.value(rule, KG.ruleId))
        assert rule_id not in found, f"two active definitions of {rule_id}"
        found[rule_id] = rule
    return found


def test_the_active_catalog_is_upstreams_nine_rules() -> None:
    """The ids with no ``validTo`` in ``rules.ttl`` are exactly the nine (and none is defined twice)."""
    assert set(_active_rules()) == set(_ACTIVE_IDS)


def test_penalty_points_sit_on_the_soft_rules_only() -> None:
    """15 on the SOFT rules, 0 on ``BREAK_TREND_200``, none on a HARD rule."""
    g = _rules_file()
    for rule_id, rule in _active_rules().items():
        expected = _ACTIVE_IDS[rule_id]
        points = g.value(rule, KG.penaltyPoints)
        assert (None if points is None else str(points)) == expected, rule_id
        severity = str(g.value(rule, KG.ruleSeverity))
        assert (severity == "SOFT") == (expected is not None), rule_id


def test_the_active_ranks_are_one_to_nine_without_repeats() -> None:
    """``primaryRule`` picks the lowest rank, so the active ranks must be distinct."""
    g = _rules_file()
    ranks = sorted(int(str(g.value(rule, KG.priorityRank))) for rule in _active_rules().values())
    assert ranks == list(range(1, 10))


_DEFINITION_ON = """
SELECT ?rule WHERE {
  ?rule a :RuleDefinition ; :ruleId "LIQUIDITY_DISTRESS" ; :validFrom ?from .
  OPTIONAL { ?rule :validTo ?to }
  FILTER (?from <= ?day && (!BOUND(?to) || ?day < ?to))
}
"""


def _liquidity_dates() -> tuple[datetime.date, datetime.date]:
    """The old definition's ``validFrom`` and its ``validTo`` (the day the redefinition starts)."""
    g = _rules_file()
    old = g.value(KG.Rule_LIQUIDITY_DISTRESS, KG.validTo)
    first = g.value(KG.Rule_LIQUIDITY_DISTRESS, KG.validFrom)
    assert isinstance(old, rdflib.Literal) and isinstance(first, rdflib.Literal)
    return first.toPython(), old.toPython()


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-1, KG.Rule_LIQUIDITY_DISTRESS),  # the day before the redefinition
        (0, KG.Rule_LIQUIDITY_DISTRESS_v11),  # the day it starts (validTo is exclusive)
        (1, KG.Rule_LIQUIDITY_DISTRESS_v11),  # after it
    ],
)
def test_a_stint_resolves_to_the_definition_valid_on_its_raised_on(
    offset: int, expected: rdflib.URIRef
) -> None:
    """The boundary is read from the old rule's ``validTo``, so moving it moves the test with it."""
    _, boundary = _liquidity_dates()
    day = rdflib.Literal(boundary + datetime.timedelta(days=offset))
    rows = _rules_file().query(_DEFINITION_ON, initNs={"": KG}, initBindings={"day": day})
    assert [row[0] for row in rows if isinstance(row, tuple)] == [expected]


def test_the_old_definition_resolves_from_its_own_valid_from() -> None:
    first, _ = _liquidity_dates()
    rows = _rules_file().query(
        _DEFINITION_ON, initNs={"": KG}, initBindings={"day": rdflib.Literal(first)}
    )
    assert [row[0] for row in rows if isinstance(row, tuple)] == [KG.Rule_LIQUIDITY_DISTRESS]


def test_a_query_by_rule_id_finds_a_stint_of_each_era() -> None:
    """A consumer matches ``appliesRule/ruleId``: matching the rule's IRI would drop one era."""
    g = _rules_file()
    g.add((KG.Veto_before, KG.appliesRule, KG.Rule_LIQUIDITY_DISTRESS))
    g.add((KG.Veto_after, KG.appliesRule, KG.Rule_LIQUIDITY_DISTRESS_v11))
    g.add((KG.Veto_other, KG.appliesRule, KG.Rule_PRICE_CRASH))
    rows = g.query(
        'SELECT ?veto WHERE { ?veto :appliesRule/:ruleId "LIQUIDITY_DISTRESS" }',
        initNs={"": KG},
    )
    assert {row[0] for row in rows if isinstance(row, tuple)} == {KG.Veto_before, KG.Veto_after}


def test_penalty_points_on_a_hard_rule_are_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """A HARD rule excludes the asset, so upstream's ``penalty_points`` is null and there is no triple."""
    g = _rule(bundle, penaltyPoints=_decimal("15"))
    g.set((_RULE, KG.ruleSeverity, rdflib.Literal("HARD")))
    assert _violations(g, shapes) == {(_RULE, None)}


def test_the_new_rules_are_valid_from_the_day_of_upstreams_merge() -> None:
    """A stint raised from 2026-10-10 on must find a definition (upstream's merge ``b3c7661``)."""
    g = _rules_file()
    rules = _active_rules()
    for rule_id in ("VOLATILITY_SHOCK", "CRASH_Z_SCORE", "BREAK_TREND_200", "LIQUIDITY_DISTRESS"):
        assert g.value(rules[rule_id], KG.validFrom) == _date("2026-10-10"), rule_id


def test_a_stint_re_confirmed_after_the_redefinition_still_resolves_by_its_raised_on() -> None:
    """Raised 2026-10-02 and seen again on 2026-10-12 (under the new code): the later sighting does
    not move it to the new definition, the re-evaluation shows only in ``lastSeenOn``."""
    g = _rules_file()
    g.add((KG.Veto_T187, KG.raisedOn, _date("2026-10-02")))
    g.add((KG.Veto_T187, KG.lastSeenOn, _date("2026-10-12")))
    raised = g.value(KG.Veto_T187, KG.raisedOn)  # the day the resolution reads, not lastSeenOn
    assert isinstance(raised, rdflib.Literal)
    rows = g.query(_DEFINITION_ON, initNs={"": KG}, initBindings={"day": raised})
    assert [row[0] for row in rows if isinstance(row, tuple)] == [KG.Rule_LIQUIDITY_DISTRESS]


def _rule_shape_facts(path: Path) -> tuple[set[str], set[str], set[str]]:
    """``priorityRank``'s upper bound, ``penaltyPoints``' lower bound, and the HARD exclusion's paths."""
    g = rdflib.Graph().parse(path, format="turtle")
    ranks: set[str] = set()
    points: set[str] = set()
    exclusion: set[str] = set()
    for prop in g.objects(KG.RuleDefinitionShape, SH.property):
        if (prop, SH.path, KG.priorityRank) in g:
            ranks.add(str(g.value(prop, SH.maxInclusive)))
        if (prop, SH.path, KG.penaltyPoints) in g:
            points.add(str(g.value(prop, SH.minInclusive)))
    for negated in g.objects(KG.RuleDefinitionShape, SH["not"]):
        for prop in g.objects(negated, SH.property):
            exclusion.add(str(g.value(prop, SH.path)).rpartition("#")[2])
    return ranks, points, exclusion


def test_the_target_schema_shapes_a_rule_like_shapes_ttl() -> None:
    """``kg_target_schema.ttl`` carries the same ``priorityRank`` bound and ``penaltyPoints`` rules."""
    in_shapes = _rule_shape_facts(SCHEMA / "shapes.ttl")
    assert in_shapes == ({"9"}, {"0.0"}, {"ruleSeverity", "penaltyPoints"})
    assert _rule_shape_facts(SCHEMA.parent / "kg_target_schema.ttl") == in_shapes


# --- T-188: ``Veto`` ``:expiresOn`` -------------------------------------------------------------


def _expiring(bundle: rdflib.Dataset, *expires: str) -> rdflib.Graph:
    """The worked example plus one Veto raised 2026-01-01 with the given ``expiresOn`` values."""
    g = _veto(bundle, cleared=None, seen=())
    for day in expires:
        g.add((_VETO, KG.expiresOn, _date(day)))
    return g


@pytest.mark.parametrize(
    "expires",
    [(), ("2026-01-02",), ("2026-01-01",), ("2026-06-30",)],
    ids=["absent", "after raisedOn", "same day", "much later"],
)
def test_a_veto_expiring_on_or_after_it_was_raised_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, expires: tuple[str, ...]
) -> None:
    assert _violations(_expiring(bundle, *expires), shapes) == set()


def test_a_veto_expiring_before_it_was_raised_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    assert _violations(_expiring(bundle, "2025-12-31"), shapes) == {(_VETO, KG.raisedOn)}


def test_a_moved_expiry_is_a_second_value_and_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """Upstream moves ``expires_on`` 10 sessions on while the condition holds; the next cycle's graph adds
    a value (append-only), as ``lastSeenOn`` does. A functional property would refuse the re-confirmation."""
    assert _violations(_expiring(bundle, "2026-01-10", "2026-01-24"), shapes) == set()


def test_each_of_several_expiries_must_be_on_or_after_raised_on(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _expiring(bundle, "2026-01-10", "2025-12-31")
    assert _violations(g, shapes) == {(_VETO, KG.raisedOn)}


@pytest.mark.parametrize(
    "path", [SCHEMA / "tbox.ttl", SCHEMA.parent / "kg_target_schema.ttl"], ids=["tbox", "target"]
)
def test_expires_on_is_declared_and_not_functional(path: Path) -> None:
    """A datatype property in both files, never functional: upstream moves it and the graphs are append-only."""
    g = rdflib.Graph().parse(path, format="turtle")
    assert (KG.expiresOn, rdflib.RDF.type, rdflib.OWL.DatatypeProperty) in g
    assert (KG.expiresOn, rdflib.RDF.type, rdflib.OWL.FunctionalProperty) not in g


def test_an_expires_on_that_is_not_a_date_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _veto(bundle, cleared=None, seen=())
    g.add((_VETO, KG.expiresOn, rdflib.Literal("soon")))
    # the datatype fails, and "soon" cannot be ordered against raisedOn either
    assert _violations(g, shapes) == {(_VETO, KG.expiresOn), (_VETO, KG.raisedOn)}


def test_an_expiry_does_not_close_a_veto(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """A stint past its ``expiresOn`` and never cleared is still a valid, active Veto: only
    ``clearedOn`` closes it (upstream's seventh reply)."""
    g = _expiring(bundle, "2026-01-02")
    g.add((_VETO, KG.lastSeenOn, _date("2026-03-01")))
    assert _violations(g, shapes) == set()
    assert (_VETO, KG.clearedOn, None) not in g
