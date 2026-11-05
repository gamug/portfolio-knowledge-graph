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

#: The frozen English configuration body from config_<label>.md, hard line breaks included.
RUN_CONFIGURATION_TEXT = """Portfolio system configuration Y2 (round 4). Every 21 trading sessions the book is rebuilt as 50% SPY (core) and
50% satellite. The satellite is chosen from the point-in-time S&P 500 members: technical, valuation and LLM-scored
fundamental scores are blended, hard vetoes exclude a company and soft vetoes lower its score, and the top 60 names
form the candidate pool. A minimum-variance optimisation (Ledoit-Wolf constant-correlation covariance, 756 sessions)
then holds at most 30 names, with a 5% name cap and a 30% sector cap. A trend filter (SPY against its 210-session
average, adapted from Faber 2007) moves half of the book to cash at a decision date when SPY is below its average.
After every close, GUARD sets the next session's weights. Layer 1 is a Basing Points stop (Edwards & Magee,
Bassetti's rules 1-4) on satellite names. Layer 3 scales exposure by volatility (Moreira & Muir 2017). Layer 4
scales exposure by drawdown (Grossman & Zhou 1993). Layer 2 (news) is off. Costs are 10 basis points per trade, and
cash earns the Kenneth French daily risk-free rate. The four arms compare this system with and without GUARD against
a minimum-variance book over the whole eligible universe, with and without GUARD. That book's GUARD keeps the
original layer-1 stop-loss, inspired by Kaminski & Lo (2014)."""

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


def _membership(bundle: rdflib.Dataset, valid_from: str, valid_to: str | None) -> rdflib.Graph:
    """A minimal conforming membership for :UniverseMembershipShape's date cases."""
    g = _flat(bundle)
    g.add((KG.TESTASSET, rdflib.RDF.type, KG.Asset))
    g.add((KG.TESTASSET, KG.tickerSymbol, rdflib.Literal("TEST")))
    g.add((KG.TESTASSET, KG.cikNumber, rdflib.Literal("0000000001")))
    g.add((KG.SP500Index, rdflib.RDF.type, KG.Universe))
    g.add((KG.UM_TEST, rdflib.RDF.type, KG.UniverseMembership))
    g.add((KG.UM_TEST, KG.membershipAsset, KG.TESTASSET))
    g.add((KG.UM_TEST, KG.membershipUniverse, KG.SP500Index))
    g.add(
        (
            KG.UM_TEST,
            KG.validFrom,
            rdflib.Literal(valid_from, datatype=rdflib.XSD.date),
        )
    )
    if valid_to is not None:
        g.add(
            (
                KG.UM_TEST,
                KG.validTo,
                rdflib.Literal(valid_to, datatype=rdflib.XSD.date),
            )
        )
    return g


def test_a_one_day_membership_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """validTo is inclusive, so validFrom == validTo is a real one-day stint (T-260)."""
    assert _violations(_membership(bundle, "2023-07-05", "2023-07-05"), shapes) == set()


def test_a_membership_ending_before_it_starts_fails(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    assert _violations(_membership(bundle, "2023-07-05", "2023-07-04"), shapes) == {
        (KG.UM_TEST, KG.validFrom)
    }


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


# --- run labels and the open window vocabulary (T-233/T-234) ------------------------------------


def _shape_property_facts(path: Path, shape: str, prop: str) -> dict[str, str]:
    """The constraints one named shape puts on one property path, as text."""
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    keys = (SH.datatype, SH.minCount, SH.maxCount, SH.pattern, SH["in"])
    for node in g.objects(KG[shape], SH.property):
        if (node, SH.path, KG[prop]) in g:
            return {
                str(key).rsplit("#", 1)[-1]: str(g.value(node, key))
                for key in keys
                if g.value(node, key) is not None
            }
    return {}


@pytest.mark.parametrize(
    ("shape", "prop"),
    [
        ("StrategyBookShape", "runLabel"),
        ("BacktestTestShape", "runLabel"),
        ("StrategyBookShape", "windowId"),
        ("GuardAlertShape", "windowId"),
        ("BookDailyPerformanceShape", "windowId"),
        ("PortfolioPeriodSummaryShape", "windowId"),
        ("BacktestTestShape", "windowId"),
        ("PortfolioPeriodSummaryShape", "segment"),
        ("BacktestTestShape", "segment"),
    ],
)
def test_the_target_schema_carries_the_run_label_and_vocabulary_patterns(
    shape: str, prop: str
) -> None:
    """``kg_target_schema.ttl`` is the proposal sent upstream; T-233/T-234 changed both files."""
    in_shapes = _shape_property_facts(SCHEMA / "shapes.ttl", shape, prop)
    assert in_shapes
    assert _shape_property_facts(SCHEMA.parent / "kg_target_schema.ttl", shape, prop) == in_shapes


def test_the_target_schema_lists_all_four_test_names() -> None:
    """Work item 38: both schema files close ``:testName`` on the same four values."""
    expected = {"memmel_jk", "ledoit_wolf", "hac_mean_diff", "bootstrap_mdd"}
    for path in (SCHEMA / "shapes.ttl", SCHEMA.parent / "kg_target_schema.ttl"):
        graph = rdflib.Graph().parse(path, format="turtle")
        nodes = [
            node
            for node in graph.objects(KG.BacktestTestShape, SH.property)
            if (node, SH.path, KG.testName) in graph
        ]
        assert len(nodes) == 1, path
        values = graph.value(nodes[0], SH["in"])
        assert values is not None, path
        assert {str(value) for value in rdflib.collection.Collection(graph, values)} == expected


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
    # T-206: a non-GUARD rule now needs a priorityRank; the rank cases override it through extra.
    if "priorityRank" not in extra:
        g.add((_RULE, KG.priorityRank, rdflib.Literal(1)))
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


def test_a_priority_rank_of_ten_conforms_and_eleven_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    ten = _rule(bundle, priorityRank=rdflib.Literal(10))
    assert _violations(ten, shapes) == set()
    eleven = _rule(bundle, priorityRank=rdflib.Literal(11))
    assert _violations(eleven, shapes) == {(_RULE, KG.priorityRank)}


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
    "UTILITY_CASH_COVERAGE": None,
}


def _rules_file() -> rdflib.Graph:
    """``rules.ttl`` alone: the file the store loads wholesale into ``urn:graph:rules:catalog``
    (``schema/README.md``), so a rule defined in another file is not found. Parsed on each call: a test may add to it
    without leaking into another."""
    return rdflib.Graph().parse(SCHEMA / "rules.ttl", format="turtle")


def _active_rules() -> dict[str, rdflib.term.Node]:
    """``ruleId`` to the one ACTIVE SELECTION rule (no ``validTo``, not category ``GUARD``)."""
    g = _rules_file()
    found: dict[str, rdflib.term.Node] = {}
    for rule in g.subjects(rdflib.RDF.type, KG.RuleDefinition):
        if (rule, KG.validTo, None) in g:
            continue
        if str(g.value(rule, KG.category)) == "GUARD":
            continue
        rule_id = str(g.value(rule, KG.ruleId))
        assert rule_id not in found, f"two active definitions of {rule_id}"
        found[rule_id] = rule
    return found


def _guard_rules() -> dict[str, rdflib.term.Node]:
    """``ruleId`` to the one GUARD rule (category ``GUARD``, no ``validTo``)."""
    g = _rules_file()
    found: dict[str, rdflib.term.Node] = {}
    for rule in g.subjects(rdflib.RDF.type, KG.RuleDefinition):
        if (rule, KG.validTo, None) in g:
            continue
        if str(g.value(rule, KG.category)) != "GUARD":
            continue
        rule_id = str(g.value(rule, KG.ruleId))
        assert rule_id not in found, f"two GUARD definitions of {rule_id}"
        found[rule_id] = rule
    return found


def test_the_active_catalog_is_upstreams_ten_selection_rules() -> None:
    """The ids with no ``validTo`` and no GUARD category are exactly the ten selection rules."""
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


def test_the_active_ranks_are_one_to_ten_without_repeats() -> None:
    """``primaryRule`` picks the lowest rank, so the active selection ranks must be distinct."""
    g = _rules_file()
    ranks = sorted(int(str(g.value(rule, KG.priorityRank))) for rule in _active_rules().values())
    assert ranks == list(range(1, 11))


# --- T-206: GUARD rules are RuleDefinitions but not veto rules -----------------------------------


def _guard_rule(bundle: rdflib.Dataset) -> rdflib.Graph:
    """The worked example plus one GUARD RuleDefinition with no veto-only fields."""
    g = _flat(bundle)
    leaf = KG.Pred_T206
    g.add((leaf, rdflib.RDF.type, KG.GraphPredicate))
    g.add((leaf, KG.predicateName, rdflib.Literal("GuardTest")))
    g.add((_RULE, rdflib.RDF.type, KG.RuleDefinition))
    g.add((_RULE, KG.ruleId, rdflib.Literal("L1_TEST")))
    g.add((_RULE, KG.category, rdflib.Literal("GUARD")))
    g.add((_RULE, KG.guardLayer, rdflib.Literal(1)))
    g.add((_RULE, KG.validFrom, _date("2019-01-02")))
    g.add((_RULE, KG.hasClause, leaf))
    return g


def test_the_guard_catalog_has_the_seven_rule_ids_and_layers() -> None:
    g = _rules_file()
    guards = _guard_rules()
    assert set(guards) == {
        "L1_STOP_LOSS",
        "L1_REENTRY",
        "L1_BP_STOP",
        "L1_BP_REENTRY",
        "L2_NEWS",
        "L3_VOL",
        "L4_DD",
    }
    assert {
        rule_id: int(str(g.value(rule, KG.guardLayer))) for rule_id, rule in guards.items()
    } == {
        "L1_STOP_LOSS": 1,
        "L1_REENTRY": 1,
        "L1_BP_STOP": 1,
        "L1_BP_REENTRY": 1,
        "L2_NEWS": 2,
        "L3_VOL": 3,
        "L4_DD": 4,
    }
    for rule in guards.values():
        assert (rule, KG.ruleSeverity, None) not in g
        assert (rule, KG.penaltyPoints, None) not in g
        assert (rule, KG.priorityRank, None) not in g


def test_a_guard_rule_without_veto_fields_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    assert _violations(_guard_rule(bundle), shapes) == set()


@pytest.mark.parametrize(
    "extra",
    [
        (KG.ruleSeverity, rdflib.Literal("SOFT")),
        (KG.penaltyPoints, _decimal("0")),
        (KG.priorityRank, rdflib.Literal(1)),
    ],
    ids=["severity", "penalty", "rank"],
)
def test_a_guard_rule_carrying_a_veto_field_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, extra: tuple[rdflib.term.Node, rdflib.term.Node]
) -> None:
    g = _guard_rule(bundle)
    g.add((_RULE, *extra))
    assert _violations(g, shapes) == {(_RULE, None)}


def test_a_non_guard_active_rule_without_a_severity_is_still_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """The GUARD branch must not weaken the rule for the other active definitions."""
    g = _rule(bundle)
    g.remove((_RULE, KG.ruleSeverity, None))
    assert _violations(g, shapes) == {(_RULE, None)}


def test_a_non_guard_rule_without_a_priority_rank_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _rule(bundle)
    g.remove((_RULE, KG.priorityRank, None))
    assert _violations(g, shapes) == {(_RULE, None)}


def test_a_veto_pointing_at_a_guard_rule_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _guard_rule(bundle)
    g.add((_VETO, rdflib.RDF.type, KG.Veto))
    g.add((_VETO, KG.raisedOn, _date("2026-01-01")))
    g.add((_VETO, KG.appliesRule, _RULE))
    g.add((_VETO, KG.primaryRule, _RULE))
    found = _violations(g, shapes)
    assert {(_VETO, KG.appliesRule), (_VETO, KG.primaryRule)} <= found
    # pyshacl also reports the inner sh:not failure on the value node.
    assert (_RULE, None) in found


def test_a_veto_pointing_at_a_selection_rule_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _veto(bundle, cleared=None, seen=())
    g.add((_VETO, KG.appliesRule, KG.Rule_PRICE_CRASH))
    g.add((_VETO, KG.primaryRule, KG.Rule_PRICE_CRASH))
    assert _violations(g, shapes) == set()


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
        paths = {
            str(g.value(prop, SH.path)).rpartition("#")[2]
            for prop in g.objects(negated, SH.property)
        }
        # The HARD exclusion is the sh:not carrying both ruleSeverity and penaltyPoints; T-206's
        # GUARD exclusion also carries :category, so select the HARD one explicitly.
        if {"ruleSeverity", "penaltyPoints"} <= paths:
            exclusion |= paths
    return ranks, points, exclusion


def test_the_target_schema_shapes_a_rule_like_shapes_ttl() -> None:
    """``kg_target_schema.ttl`` carries the same ``priorityRank`` bound and ``penaltyPoints`` rules."""
    in_shapes = _rule_shape_facts(SCHEMA / "shapes.ttl")
    assert in_shapes == ({"10"}, {"0.0"}, {"ruleSeverity", "penaltyPoints"})
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


# --- final-backtest vocabulary (Work item 33) ----------------------------------------------


def _m018_book(
    bundle: rdflib.Dataset,
    *,
    name: str = "Book_T470",
    window: str = "H1",
    arm: str = "MARKOWITZ_BASE_GUARD",
    guard_layers: str | None = "[1, 3, 4]",
) -> rdflib.Graph:
    g = _flat(bundle)
    book = KG[name]
    g.add((book, rdflib.RDF.type, KG.StrategyBook))
    g.add((book, KG.bookId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((book, KG.backtestRunId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((book, KG.runLabel, rdflib.Literal("final")))
    g.add((book, KG.windowId, rdflib.Literal(window)))
    g.add((book, KG.backtestStartDate, _date("2022-01-03")))
    g.add((book, KG.backtestEndDate, _date("2026-10-15")))
    g.add((book, KG.runStatus, rdflib.Literal("completed")))
    g.add((book, KG.armCode, rdflib.Literal(arm)))
    g.add((book, KG.objective, rdflib.Literal("min_var")))
    g.add((book, KG.excludeHardVetoed, rdflib.Literal(False)))
    if guard_layers is not None:
        g.add((book, KG.guardLayers, rdflib.Literal(guard_layers)))
    g.add((book, KG.knowledgeDate, _date("2026-11-04")))
    return g


@pytest.mark.parametrize("window", ["P1", "P2", "P3", "H1", "H2", "H3"])
def test_every_final_window_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, window: str
) -> None:
    assert _violations(_m018_book(bundle, window=window), shapes) == set()


@pytest.mark.parametrize("window", ["P2a", "P2b", "H3"])
def test_a_window_or_segment_with_a_holdout_letter_conforms_or_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, window: str
) -> None:
    """P2a/P2b are segments, not windows; H3 is a window and its own segment."""
    if window.startswith("P2"):
        g = _summary(bundle, segment=window)
    else:
        g = _summary(bundle, window=window, segment=window)
    assert _violations(g, shapes) == set()


def _summary(bundle: rdflib.Dataset, *, window: str = "P2", segment: str = "P2a") -> rdflib.Graph:
    g = _m018_book(bundle, name="Book_T470")
    summary = KG.Summary_T470
    g.add((summary, rdflib.RDF.type, KG.PortfolioPeriodSummary))
    g.add((summary, KG.summaryOfBook, KG.Book_T470))
    g.add((summary, KG.bookId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((summary, KG.backtestRunId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((summary, KG.armCode, rdflib.Literal("MARKOWITZ_BASE_GUARD")))
    g.add((summary, KG.windowId, rdflib.Literal(window)))
    g.add((summary, KG.segment, rdflib.Literal(segment)))
    g.add((summary, KG.dateFrom, _date("2025-02-19")))
    g.add((summary, KG.dateTo, _date("2025-09-23")))
    g.add((summary, KG.cumulativeReturn, rdflib.Literal("0.1", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.annualizedReturn, rdflib.Literal("0.12", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.annualizedVol, rdflib.Literal("0.18", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.exPostSharpe, rdflib.Literal("0.6", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.maxDrawdown, rdflib.Literal("0.2", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.totalTurnover, rdflib.Literal("3.0", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.totalCostBps, rdflib.Literal("300", datatype=rdflib.XSD.decimal)))
    g.add((summary, KG.nRebalances, rdflib.Literal("10", datatype=rdflib.XSD.integer)))
    g.add((summary, KG.nGuardActions, rdflib.Literal("5", datatype=rdflib.XSD.integer)))
    g.add((summary, KG.knowledgeDate, _date("2025-09-23")))
    return g


@pytest.mark.parametrize(
    "arm",
    [
        "MARKOWITZ_BASE",
        "TOPN_MV_NOGUARD",
        "TOPN_MV_GUARD_NO_NLP",
        "TOPN_MV_GUARD",
        "MARKOWITZ_BASE_GUARD",
    ],
)
def test_every_final_arm_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph, arm: str) -> None:
    guard = "[1, 3, 4]" if arm.endswith(("GUARD", "NO_NLP")) else None
    assert _violations(_m018_book(bundle, arm=arm, guard_layers=guard), shapes) == set()


def test_an_arm_outside_the_final_list_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018_book(bundle, arm="MARKOWITZ_BASE_GUARD_V2", guard_layers=None)
    assert _violations(g, shapes) == {(KG.Book_T470, KG.armCode)}


def _alert(
    bundle: rdflib.Dataset, *, rule: str, threshold: str | None, window: str = "H1"
) -> rdflib.Graph:
    g = _flat(bundle)
    alert = KG.Alert_T470
    g.add((alert, rdflib.RDF.type, KG.GuardAlert))
    g.add((alert, KG.alertId, rdflib.Literal("7", datatype=rdflib.XSD.integer)))
    g.add((alert, KG.backtestRunId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((alert, KG.windowId, rdflib.Literal(window)))
    g.add((alert, KG.alertDate, _date("2026-01-05")))
    g.add((alert, KG.guardLayer, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((alert, KG.alertRule, KG[f"Rule_{rule}"]))
    g.add((alert, KG.alertState, rdflib.Literal("ENTER")))
    g.add((alert, KG.knowledgeDate, _date("2026-01-05")))
    if threshold is not None:
        g.add((alert, KG.alertThreshold, rdflib.Literal(threshold, datatype=rdflib.XSD.decimal)))
    return g


@pytest.mark.parametrize("rule", ["L1_BP_STOP", "L1_BP_REENTRY"])
def test_a_basing_points_alert_without_a_threshold_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, rule: str
) -> None:
    assert _violations(_alert(bundle, rule=rule, threshold=None), shapes) == set()


@pytest.mark.parametrize("rule", ["L1_BP_STOP", "L1_BP_REENTRY"])
def test_a_basing_points_alert_with_a_threshold_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, rule: str
) -> None:
    """The BP threshold is an individual asset's stop price, not a publishable parameter."""
    assert _violations(_alert(bundle, rule=rule, threshold="123.45"), shapes) == {
        (KG.Alert_T470, None)
    }


@pytest.mark.parametrize("rule", ["L1_STOP_LOSS", "L1_REENTRY"])
def test_a_fixed_parameter_alert_still_requires_a_threshold(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, rule: str
) -> None:
    assert _violations(_alert(bundle, rule=rule, threshold=None), shapes) == {(KG.Alert_T470, None)}
    assert _violations(_alert(bundle, rule=rule, threshold="0.0108"), shapes) == set()


def test_an_exchange_traded_fund_may_omit_cik_classification_and_membership(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    g.add((KG.SPY_T470, rdflib.RDF.type, KG.ExchangeTradedFund))
    g.add((KG.SPY_T470, KG.tickerSymbol, rdflib.Literal("SPY")))
    g.add((KG.SPY_T470, KG.companyName, rdflib.Literal("SPDR S&P 500 ETF Trust")))
    assert _violations(g, shapes) == set()


def test_an_ordinary_asset_without_cik_classification_and_membership_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    g.add((KG.ORDINARY_T470, rdflib.RDF.type, KG.Asset))
    g.add((KG.ORDINARY_T470, KG.tickerSymbol, rdflib.Literal("ORD")))
    assert _violations(g, shapes) == {(KG.ORDINARY_T470, None)}


def _run_metadata(
    bundle: rdflib.Dataset, *, sha: str = "a" * 64, config: bool = True
) -> rdflib.Graph:
    g = _flat(bundle)
    config_iri = KG.Config_T470
    run = KG.Run_T470
    g.add((config_iri, rdflib.RDF.type, KG.RunConfiguration))
    g.add((config_iri, KG.runLabel, rdflib.Literal("final")))
    g.add((config_iri, KG.configCodeCommit, rdflib.Literal("537e864")))
    g.add((config_iri, KG.configPr, rdflib.Literal("192")))
    g.add((config_iri, KG.configResultsDoc, rdflib.Literal("docs/results.md")))
    g.add((config_iri, KG.configId, rdflib.Literal("Y2")))
    g.add(
        (
            config_iri,
            KG.configStatus,
            rdflib.Literal(
                'candidate (the system may still change in round 5; the final delivery will be label "final")'
            ),
        )
    )
    g.add((run, rdflib.RDF.type, KG.BacktestRun))
    g.add((run, KG.runLabel, rdflib.Literal("final")))
    g.add((run, KG.windowId, rdflib.Literal("H1")))
    g.add((run, KG.backtestRunId, rdflib.Literal("1", datatype=rdflib.XSD.integer)))
    g.add((run, KG.sourceFile, rdflib.Literal("final_H1.db")))
    g.add((run, KG.sourceSha256, rdflib.Literal(sha)))
    g.add((run, KG.knowledgeDate, _date("2026-11-04")))
    if config:
        g.add((run, KG.runConfiguration, config_iri))
    return g


def test_the_run_metadata_classes_conform(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    assert _violations(_run_metadata(bundle), shapes) == set()


@pytest.mark.parametrize(
    ("sha", "config", "path"),
    [
        ("A" * 64, True, KG.sourceSha256),  # uppercase is not the sha256sum format
        ("a" * 63, True, KG.sourceSha256),
        ("a" * 64, False, KG.runConfiguration),  # the required link is missing
    ],
    ids=["uppercase", "short", "missing configuration"],
)
def test_malformed_run_metadata_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, sha: str, config: bool, path: object
) -> None:
    assert _violations(_run_metadata(bundle, sha=sha, config=config), shapes) == {
        (KG.Run_T470, path)
    }


def test_the_run_configuration_body_round_trips_verbatim() -> None:
    """The fixed body keeps its hard line breaks, apostrophes and ampersands through Turtle."""
    tbox = rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")
    comment = tbox.value(KG.RunConfiguration, rdflib.RDFS.comment)
    assert comment is not None
    assert str(comment) == RUN_CONFIGURATION_TEXT
    assert "\n" in str(comment) and "&" in str(comment) and "'" in str(comment)
    again = rdflib.Graph().parse(data=tbox.serialize(format="turtle"), format="turtle")
    assert str(again.value(KG.RunConfiguration, rdflib.RDFS.comment)) == RUN_CONFIGURATION_TEXT


def test_run_configuration_front_matter_is_optional(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _run_metadata(bundle)
    g.remove((KG.Config_T470, KG.configId, None))
    g.remove((KG.Config_T470, KG.configStatus, None))
    assert _violations(g, shapes) == set()


def test_a_config_status_with_quotes_round_trips() -> None:
    """The status line keeps its quotes and parentheses through Turtle, like the body text."""
    expected = 'candidate (the system may still change in round 5; the final delivery will be label "final")'
    g = rdflib.Graph()
    g.add((KG.Config_T470, KG.configStatus, rdflib.Literal(expected)))
    reparsed = rdflib.Graph().parse(data=g.serialize(format="turtle"), format="turtle")
    assert str(reparsed.value(KG.Config_T470, KG.configStatus)) == expected
