"""The FR-001 gate as a test: ``schema/`` parses in load order and ``pyshacl``-conforms (T-134).

Runs against the real ``schema/`` files (they are the unit under test, not an upstream
dependency), so it stays hermetic: no network, no store, no ETL databases. The counts
``SPEC.md`` states for the bundle are checked too (NR-001), so a schema edit that moves
them must update the numbers in the same change.
"""

from __future__ import annotations

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

_NEW_RUN = (
    "ScoreFinanciero",
    "ScoreCuantitativo",
    "ScoreTecnico",
)  # FUNDAMENTAL, VALORIZATION, TECHNICAL


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


def test_the_target_schema_orders_a_veto_like_shapes_ttl() -> None:
    """``kg_target_schema.ttl`` carries the same Veto date order. The dates come from upstream's own
    ``veto`` rows, so the proposal is kept equal to ``shapes.ttl`` and needs no action from them."""
    in_shapes = _less_than_or_equals(SCHEMA / "shapes.ttl")
    assert in_shapes == {("raisedOn", "lastSeenOn"), ("lastSeenOn", "clearedOn")}
    assert _less_than_or_equals(SCHEMA.parent / "kg_target_schema.ttl") == in_shapes
