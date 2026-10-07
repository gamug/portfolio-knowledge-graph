"""The FR-001 gate as a test: ``schema/`` parses in load order and ``pyshacl``-conforms (T-134).

Runs against the real ``schema/`` files (they are the unit under test, not an upstream
dependency), so it stays hermetic: no network, no store, no ETL databases.
"""

from __future__ import annotations

import re
from pathlib import Path

import pyshacl
import pytest
import rdflib

SCHEMA = Path(__file__).resolve().parent.parent / "schema"

# Load order from schema/README.md; everything but instances.trig is Turtle.
TURTLE_FILES = ("tbox.ttl", "shapes.ttl", "reference.ttl", "rules.ttl")


@pytest.fixture(scope="module")
def bundle() -> rdflib.Dataset:
    ds = rdflib.Dataset()
    for name in TURTLE_FILES:
        ds.parse(SCHEMA / name, format="turtle")
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return ds


def _flat(ds: rdflib.Dataset) -> rdflib.Graph:
    """Every quad's triple in one graph, the shape ``pyshacl`` validates."""
    g = rdflib.Graph()
    for s, p, o, _ in ds.quads():
        g.add((s, p, o))
    return g


def test_each_file_parses_alone() -> None:
    for name in TURTLE_FILES:
        assert len(rdflib.Graph().parse(SCHEMA / name, format="turtle")) > 0, name
    assert len(rdflib.Dataset().parse(SCHEMA / "instances.trig", format="trig")) > 0


def test_instances_are_split_over_named_graphs(bundle: rdflib.Dataset) -> None:
    names = {str(g.identifier) for g in bundle.graphs() if len(g)}
    assert any(n.startswith("urn:graph:ingest:") for n in names)
    assert "urn:graph:portfolio:current" in names


def test_bundle_conforms_to_shapes(bundle: rdflib.Dataset) -> None:
    conforms, _, report = pyshacl.validate(_flat(bundle), shacl_graph=_flat_shapes())
    assert conforms, report


def _flat_shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


def test_quad_count_matches_spec(bundle: rdflib.Dataset) -> None:
    """NR-001: the count SPEC FR-001 states is the real one, so a schema edit that moves it
    must update the number (and ``schema/README.md``) in the same change."""
    spec = (SCHEMA.parent / ".specify" / "memory" / "SPEC.md").read_text(encoding="utf-8")
    stated = re.search(r"\*\*FR-001\*\*.*?`quads: (\d+)`", spec)
    assert stated, "SPEC FR-001 states no `quads: N` count"
    assert len(list(bundle.quads())) == int(stated.group(1))


def test_a_nonconforming_instance_is_caught(bundle: rdflib.Dataset) -> None:
    """The gate is not vacuous: an asset with no ticker must fail its shape."""
    g = _flat(bundle)
    ns = rdflib.Namespace("https://thesis.local/kg/portfolio#")
    g.add((ns.BadAsset, rdflib.RDF.type, ns.Asset))
    conforms, _, _ = pyshacl.validate(g, shacl_graph=_flat_shapes())
    assert not conforms
