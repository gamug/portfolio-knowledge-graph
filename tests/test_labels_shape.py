"""``LabelConceptShape`` keeps the presentation vocabulary complete (Work item 43, T-752)."""

from __future__ import annotations

import copy
from pathlib import Path

import pyshacl
import pytest
import rdflib
from rdflib.namespace import RDFS, SH, SKOS

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


@pytest.fixture(scope="module")
def labels() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "labels.ttl", format="turtle")


@pytest.fixture(scope="module")
def shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


def _violations(
    data: rdflib.Graph, shapes: rdflib.Graph
) -> set[tuple[rdflib.term.Node | None, rdflib.term.Node | None]]:
    conforms, results, _ = pyshacl.validate(data, shacl_graph=shapes)
    assert isinstance(results, rdflib.Graph)
    found = {
        (results.value(r, SH.focusNode), results.value(r, SH.resultPath))
        for r in results.subjects(SH.focusNode, None)
    }
    assert conforms == (not found)
    return found


def test_the_labels_graph_conforms(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    assert _violations(labels, shapes) == set()


def _concept(labels: rdflib.Graph) -> rdflib.URIRef:
    concept = KG.Window_1
    assert (concept, KG.labelScheme, KG.PresentationScheme) in labels
    return concept


def test_a_missing_english_label_is_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    for value in list(data.objects(concept, RDFS.label)):
        if getattr(value, "language", None) == "en":
            data.remove((concept, RDFS.label, value))
    assert (concept, RDFS.label) in _violations(data, shapes)


def test_a_missing_spanish_comment_is_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    for value in list(data.objects(concept, RDFS.comment)):
        if getattr(value, "language", None) == "es":
            data.remove((concept, RDFS.comment, value))
    assert (concept, RDFS.comment) in _violations(data, shapes)


def test_a_missing_notation_is_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    data.remove((concept, SKOS.notation, None))
    assert (concept, SKOS.notation) in _violations(data, shapes)


def test_a_second_notation_is_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    data.add((concept, SKOS.notation, rdflib.Literal("P1-extra")))
    assert (concept, SKOS.notation) in _violations(data, shapes)


def test_a_wrong_language_on_an_alt_label_is_caught(
    labels: rdflib.Graph, shapes: rdflib.Graph
) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    data.add((concept, SKOS.altLabel, rdflib.Literal("Fenêtre 1", lang="fr")))
    assert (concept, SKOS.altLabel) in _violations(data, shapes)


def test_a_second_label_scheme_marker_is_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    data.remove((concept, KG.labelScheme, KG.PresentationScheme))
    # The target is subject-of :labelScheme; a removed marker takes the node out of the target,
    # so the shape is checked by adding a second concept with no marker and targeting it through
    # a different subject. Keep one bad subject in the target with a second marker.
    data.add((concept, KG.labelScheme, KG.PresentationScheme))
    data.add((concept, KG.labelScheme, KG.OtherScheme))
    assert (concept, KG.labelScheme) in _violations(data, shapes)


def test_two_schemes_on_one_concept_are_caught(labels: rdflib.Graph, shapes: rdflib.Graph) -> None:
    data = copy.deepcopy(labels)
    concept = _concept(data)
    data.add((concept, SKOS.inScheme, KG.StrategyScheme))
    assert (concept, SKOS.inScheme) in _violations(data, shapes)
