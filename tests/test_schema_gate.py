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

_COMPONENT = (KG.WC_Run, rdflib.RDF.type, KG.WeightComponent)
_SCHEME = KG.WS_Run


def _scheme(
    bundle: rdflib.Dataset, extra: list[tuple[rdflib.term.Node, rdflib.term.Node]]
) -> rdflib.Graph:
    """The worked example plus one scheme (one component, no ``:inverted``) with ``extra`` triples."""
    g = _flat(bundle)
    D, L = rdflib.XSD.decimal, rdflib.Literal
    g.add(_COMPONENT)
    g.add((KG.WC_Run, KG.weightMetricName, L("ScoreFinanciero")))
    g.add((KG.WC_Run, KG.weightValue, L("0.4", datatype=D)))
    g.add((_SCHEME, rdflib.RDF.type, KG.AttractivenessWeightScheme))
    g.add((_SCHEME, KG.schemeId, L("cycle_run:42")))
    g.add((_SCHEME, KG.hasWeightComponent, KG.WC_Run))
    for p, o in extra:
        g.add((_SCHEME, p, o))
    return g


_DATE = rdflib.Literal("2026-10-08", datatype=rdflib.XSD.date)
_DEC = rdflib.XSD.decimal
_INT = rdflib.XSD.integer


@pytest.mark.parametrize(
    "extra",
    [
        [(KG.runAsOf, _DATE)],
        [(KG.validFrom, _DATE)],
        [
            (KG.runAsOf, _DATE),
            (KG.bookWeightingRule, rdflib.Literal("score_tilt")),
            (KG.topN, rdflib.Literal("30", datatype=_INT)),
            (KG.maxNameWeight, rdflib.Literal("0.05", datatype=_DEC)),
            (KG.maxSectorWeight, rdflib.Literal("0.25", datatype=_DEC)),
            (KG.softVetoPenalty, rdflib.Literal("15", datatype=_DEC)),
        ],
    ],
    ids=["run date only", "valid-time only", "every knob"],
)
def test_a_per_run_scheme_conforms(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    extra: list[tuple[rdflib.term.Node, rdflib.term.Node]],
) -> None:
    assert _violations(_scheme(bundle, extra), shapes) == set()


@pytest.mark.parametrize(
    ("extra", "path"),
    [
        ([], None),  # neither date: the sh:or fails on the node itself
        (
            [
                (KG.runAsOf, _DATE),
                (KG.runAsOf, rdflib.Literal("2026-10-09", datatype=rdflib.XSD.date)),
            ],
            KG.runAsOf,
        ),
        ([(KG.runAsOf, _DATE), (KG.topN, rdflib.Literal("0", datatype=_INT))], KG.topN),
        ([(KG.runAsOf, _DATE), (KG.topN, rdflib.Literal("5.5", datatype=_DEC))], KG.topN),
        (
            [(KG.runAsOf, _DATE), (KG.maxNameWeight, rdflib.Literal("1.5", datatype=_DEC))],
            KG.maxNameWeight,
        ),
        (
            [(KG.runAsOf, _DATE), (KG.maxSectorWeight, rdflib.Literal("-0.1", datatype=_DEC))],
            KG.maxSectorWeight,
        ),
        (
            [(KG.runAsOf, _DATE), (KG.softVetoPenalty, rdflib.Literal("-1", datatype=_DEC))],
            KG.softVetoPenalty,
        ),
    ],
    ids=[
        "no date",
        "two run dates",
        "topN 0",
        "topN not an integer",
        "name cap above 1",
        "sector cap below 0",
        "negative penalty",
    ],
)
def test_a_malformed_per_run_scheme_is_caught(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    extra: list[tuple[rdflib.term.Node, rdflib.term.Node]],
    path: rdflib.term.Node | None,
) -> None:
    assert _violations(_scheme(bundle, extra), shapes) == {(_SCHEME, path)}


def test_a_weight_component_may_omit_inverted(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """``_scheme`` builds its component without ``:inverted``; one given still has to be a boolean."""
    g = _scheme(bundle, [(KG.runAsOf, _DATE)])
    assert _violations(g, shapes) == set()
    g.add((KG.WC_Run, KG.inverted, rdflib.Literal("yes")))
    assert _violations(g, shapes) == {(KG.WC_Run, KG.inverted)}
