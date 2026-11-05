"""The FIBO Phase 2 slice, its Spanish layer and the Appendix A lookups (T-211).

Hermetic: the committed ``schema/fibo.ttl`` is the unit under test. The real ``prod.ttl.zip`` is
read only by the opt-in reproducibility test, which is skipped unless ``FIBO_ZIP`` points at it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import zipfile
from collections import Counter
from pathlib import Path

import pytest
import rdflib
import rdflib.collection
from rdflib import Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS
from rdflib.query import ResultRow
from rdflib.term import Literal, Node, URIRef

from etl.asset_master import Stint, build_assets
from projection.fibo_slice import (
    CMNS_AV,
    HEADER_IRI,
    HEADER_SHA,
    KEPT_PREDICATES,
    build_result,
    build_slice,
    serialize,
)
from projection.fibo_terms import (
    FIBO_BASE,
    OUR_NAMESPACE,
    PINNED_SHA256,
    SKOS,
    FiboTermsError,
    sha256,
)

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
REPO = SCHEMA.parent
SLICE = SCHEMA / "fibo.ttl"
TERMS = SCHEMA / "fibo_terms.csv"
DOCS_06 = REPO / "docs" / "06-ontology-definition.md"
KG = Namespace(OUR_NAMESPACE)
FIBO_EQUITY_INDEX = URIRef(FIBO_BASE + "IND/MarketIndices/BasketIndices/EquityIndex")

SCHEMA_FILES = [
    SCHEMA / "tbox.ttl",
    SCHEMA / "shapes.ttl",
    SCHEMA / "reference.ttl",
    SCHEMA / "rules.ttl",
    SCHEMA / "instances.trig",
    REPO / "kg_target_schema.ttl",
]

_V18 = (
    "TickerHistory",
    "OrchestratorRun",
    "OrchestratorStep",
    "StrategyBook",
    "BookRebalance",
    "GuardAlert",
    "GuardAction",
    "BookWeightDaily",
    "BookDailyPerformance",
    "PortfolioPeriodSummary",
    "BacktestTest",
)
_V18_SHA256 = "5a7f7b6ec81adfa553cf119260bc7323b867f5e707f8804a529df6635d90698e"

QUERY_A1 = """PREFIX :     <https://thesis.local/kg/portfolio#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?labelEs ?defEs ?fibo ?fiboLabelEs ?fiboDefEs ?fiboDef
WHERE {
  GRAPH <urn:graph:tbox> {
    :Portfolio rdfs:label ?labelEs ; skos:definition ?defEs .
    FILTER (lang(?labelEs) = "es" && lang(?defEs) = "es")
  }
  OPTIONAL {
    GRAPH <urn:graph:tbox> { :Portfolio rdfs:seeAlso ?fibo . }
    GRAPH <urn:graph:reference:fibo> {
      ?fibo skos:definition ?fiboDef .
      FILTER (!langMatches(lang(?fiboDef), "es"))
      OPTIONAL { ?fibo rdfs:label      ?fiboLabelEs FILTER (lang(?fiboLabelEs) = "es") }
      OPTIONAL { ?fibo skos:definition ?fiboDefEs   FILTER (lang(?fiboDefEs)   = "es") }
    }
  }
}"""

QUERY_A2 = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?term ?defEs ?fiboDef
WHERE {
  GRAPH <urn:graph:reference:fibo> {
    ?term rdfs:label ?l .
    FILTER (lang(?l) = "es" && lcase(str(?l)) = "volatilidad")
    ?term skos:definition ?fiboDef .
    FILTER (!langMatches(lang(?fiboDef), "es"))
    OPTIONAL { ?term skos:definition ?defEs FILTER (lang(?defEs) = "es") }
  }
}"""


@pytest.fixture(scope="module")
def slice_graph() -> rdflib.Graph:
    return rdflib.Graph().parse(SLICE, format="turtle")


def _entries(graph: rdflib.Graph) -> set[URIRef]:
    return {
        subject
        for subject in graph.subjects()
        if isinstance(subject, URIRef) and str(subject).startswith(FIBO_BASE)
    }


def _english(graph: rdflib.Graph, subject: Node, predicate: URIRef) -> list[Literal]:
    return [
        obj
        for obj in graph.objects(subject, predicate)
        if isinstance(obj, Literal) and obj.language in (None, "en")
    ]


def _spanish(graph: rdflib.Graph, subject: Node, predicate: URIRef) -> list[Literal]:
    return [
        obj
        for obj in graph.objects(subject, predicate)
        if isinstance(obj, Literal) and obj.language == "es"
    ]


def _see_also_targets(path: Path) -> set[URIRef]:
    if path.suffix == ".trig":
        dataset = rdflib.Dataset().parse(path, format="trig")
        triples = [triple for quad in dataset.quads() for triple in (quad[:3],)]
    else:
        graph = rdflib.Graph().parse(path, format="turtle")
        triples = list(graph)
    return {
        obj
        for _subject, predicate, obj in triples
        if predicate == RDFS.seeAlso and isinstance(obj, URIRef) and str(obj).startswith(FIBO_BASE)
    }


# --- §4.2 counts and shape ---------------------------------------------------------------------


def test_the_slice_has_the_measured_counts(slice_graph: rdflib.Graph) -> None:
    entries = _entries(slice_graph)
    assert len(entries) == 54
    english: Counter[str] = Counter()
    spanish = 0
    for subject in entries:
        for predicate, obj in slice_graph.predicate_objects(subject):
            if predicate not in KEPT_PREDICATES:
                continue
            if isinstance(obj, Literal) and obj.language == "es":
                spanish += 1
            else:
                english[str(predicate)] += 1
    expected = {
        str(RDFS.label): 54,
        str(SKOS.definition): 54,
        str(RDFS.subClassOf): 63,
        str(CMNS_AV.explanatoryNote): 37,
        str(CMNS_AV.abbreviation): 7,
        str(CMNS_AV.synonym): 6,
        str(CMNS_AV.usageNote): 2,
        str(CMNS_AV.example): 0,
    }
    assert {predicate: english.get(predicate, 0) for predicate in expected} == expected
    assert spanish == 50
    assert len(slice_graph) == 277


def _rows() -> list[dict[str, str]]:
    with TERMS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _seeds() -> list[URIRef]:
    return [URIRef(row["fibo_iri"]) for row in _rows()]


def test_every_entry_has_one_english_label_and_definition_and_every_seed_the_spanish_pair(
    slice_graph: rdflib.Graph,
) -> None:
    for subject in _entries(slice_graph):
        assert len(_english(slice_graph, subject, RDFS.label)) == 1, subject
        assert len(_english(slice_graph, subject, SKOS.definition)) == 1, subject
    for subject in _seeds():
        assert len(_spanish(slice_graph, subject, RDFS.label)) == 1, subject
        assert len(_spanish(slice_graph, subject, SKOS.definition)) == 1, subject


def test_the_slice_declares_no_rdf_type_or_owl_class(slice_graph: rdflib.Graph) -> None:
    assert list(slice_graph.triples((None, RDF.type, None))) == []
    assert list(slice_graph.triples((None, RDF.type, OWL.Class))) == []
    assert list(slice_graph.subjects(RDF.type, OWL.Class)) == []
    rows = list(
        slice_graph.query(
            "PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT ?c WHERE { ?c a owl:Class }"
        )
    )
    assert rows == []


def test_the_slice_has_29_ancestors_and_16_external_parents(slice_graph: rdflib.Graph) -> None:
    entries = _entries(slice_graph)
    assert len(entries) - len(_seeds()) == 29
    external = {
        obj
        for _subject, _predicate, obj in slice_graph.triples((None, RDFS.subClassOf, None))
        if isinstance(obj, URIRef) and str(obj).startswith("https://www.omg.org/spec/Commons/")
    }
    assert len(external) == 16
    assert not (external & entries)


def test_every_named_fibo_parent_is_an_entry_and_parents_are_named(
    slice_graph: rdflib.Graph,
) -> None:
    entries = _entries(slice_graph)
    for _subject, _predicate, obj in slice_graph.triples((None, RDFS.subClassOf, None)):
        assert isinstance(obj, URIRef)
        if str(obj).startswith(FIBO_BASE):
            assert obj in entries


def test_the_header_carries_the_release_version_sha_and_licence(slice_graph: rdflib.Graph) -> None:
    assert str(slice_graph.value(HEADER_IRI, OWL.versionInfo)) == "FIBO 2026Q2"
    assert str(slice_graph.value(HEADER_IRI, HEADER_SHA)) == PINNED_SHA256
    licence = str(slice_graph.value(HEADER_IRI, DCTERMS.license))
    assert "Copyright (c) 2018-2026 EDM Association dba EDM Council, Inc." in licence
    assert "Copyright (c) 2018-2025 Object Management Group, Inc." in licence
    assert "MIT" in licence


def test_the_25_terms_are_seeds_and_all_are_reviewed(slice_graph: rdflib.Graph) -> None:
    with TERMS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    entries = _entries(slice_graph)
    assert len(rows) == 25
    for row in rows:
        seed = URIRef(row["fibo_iri"])
        assert seed in entries
        assert row["label_es"] and row["definition_es"]
        assert str(_spanish(slice_graph, seed, RDFS.label)[0]) == row["label_es"]
        assert str(_spanish(slice_graph, seed, SKOS.definition)[0]) == row["definition_es"]


# --- S4(a): every FIBO link points at an entry ------------------------------------------------


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=[path.name for path in SCHEMA_FILES])
def test_every_schema_fibo_link_targets_a_slice_entry(
    path: Path, slice_graph: rdflib.Graph
) -> None:
    assert _see_also_targets(path) <= _entries(slice_graph)


def test_the_etl_sp500_link_targets_a_slice_entry(slice_graph: rdflib.Graph) -> None:
    out = io.StringIO()
    build_assets([Stint("AAPL", "Apple Inc.", None, None, None, "2000-01-01", None)], out, [])
    graph = rdflib.Graph().parse(
        data="@prefix : <https://thesis.local/kg/portfolio#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + out.getvalue(),
        format="turtle",
    )
    targets = set(graph.objects(KG.SP500Index, RDFS.seeAlso))
    assert targets == {FIBO_EQUITY_INDEX}
    assert targets <= _entries(slice_graph)
    row = next(row for row in _rows() if row["our_term"] == f"{OUR_NAMESPACE}SP500Index")
    assert row["fibo_iri"] == str(FIBO_EQUITY_INDEX)


# --- S4(e): the Spanish layer of our classes ---------------------------------------------------


def _leaves(graph: rdflib.Graph) -> list[Node]:
    leaves: list[Node] = []
    for disjoint in graph.subjects(RDF.type, OWL.AllDisjointClasses):
        members = graph.value(disjoint, OWL.members)
        assert members is not None
        leaves.extend(rdflib.collection.Collection(graph, members))
    return leaves


def test_each_of_the_44_leaf_classes_has_one_spanish_label_and_definition() -> None:
    graph = rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")
    leaves = _leaves(graph)
    assert len(leaves) == 44
    for leaf in leaves:
        assert len(_spanish(graph, leaf, RDFS.label)) == 1, leaf
        assert len(_spanish(graph, leaf, SKOS.definition)) == 1, leaf


def test_the_11_v18_spanish_texts_are_unchanged() -> None:
    graph = rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")
    pairs = []
    for name in _V18:
        subject = KG[name]
        label = _spanish(graph, subject, RDFS.label)
        definition = _spanish(graph, subject, SKOS.definition)
        assert len(label) == 1 and len(definition) == 1, name
        pairs.append(f"{name}\t{label[0]}\t{definition[0]}")
    assert hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest() == _V18_SHA256


def test_no_spanish_literal_is_attached_to_a_fibo_term_outside_the_slice() -> None:
    for path in SCHEMA_FILES:
        if path.suffix == ".trig":
            dataset = rdflib.Dataset().parse(path, format="trig")
            triples = [triple for quad in dataset.quads() for triple in (quad[:3],)]
        else:
            triples = list(rdflib.Graph().parse(path, format="turtle"))
        for subject, _predicate, obj in triples:
            if (
                isinstance(subject, URIRef)
                and str(subject).startswith(FIBO_BASE)
                and isinstance(obj, Literal)
                and obj.language == "es"
            ):
                pytest.fail(f"{path}: @es literal on FIBO term {subject}")


# --- Appendix A, offline -----------------------------------------------------------------------


def _dataset() -> rdflib.Dataset:
    dataset = rdflib.Dataset(default_union=False)
    dataset.graph(URIRef("urn:graph:tbox")).parse(SCHEMA / "tbox.ttl", format="turtle")
    dataset.graph(URIRef("urn:graph:reference:fibo")).parse(SLICE, format="turtle")
    return dataset


def test_appendix_a1_returns_our_spanish_and_the_fibo_pair() -> None:
    rows = list(_dataset().query(QUERY_A1))
    assert len(rows) == 1
    assert isinstance(rows[0], ResultRow)
    row = rows[0].asdict()
    assert str(row["labelEs"]) == "portafolio"
    assert str(row["defEs"]) == "El libro de posiciones activas."
    assert str(row["fibo"]) == FIBO_BASE + "FND/OwnershipAndControl/Ownership/Portfolio"
    assert str(row["fiboLabelEs"]) == "portafolio"
    assert "Colección de tenencias" in str(row["fiboDefEs"])
    assert str(row["fiboDef"]).startswith("collection of holdings")


def test_appendix_a2_returns_the_glossary_term_by_its_spanish_label() -> None:
    rows = list(_dataset().query(QUERY_A2))
    assert len(rows) == 1
    assert isinstance(rows[0], ResultRow)
    row = rows[0].asdict()
    assert str(row["term"]) == FIBO_BASE + "IND/Indicators/Indicators/Volatility"
    assert str(row["defEs"]).startswith("Medida estadística")
    assert str(row["fiboDef"]).startswith("statistical measure")


def test_the_docs_carry_the_two_lookup_queries_unchanged() -> None:
    text = DOCS_06.read_text(encoding="utf-8")
    assert QUERY_A1 in text
    assert QUERY_A2 in text


# --- the builder over a synthetic release ------------------------------------------------------


def _synthetic_zip(tmp_path: Path) -> Path:
    with TERMS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    graph = rdflib.Graph()
    graph.bind("fibo", FIBO_BASE)
    graph.bind("rdfs", RDFS)
    graph.bind("skos", SKOS)
    graph.add((URIRef(FIBO_BASE + "AboutFIBOProd/"), DCTERMS.license, Literal("MIT test licence")))
    ancestors = {
        URIRef(FIBO_BASE + "Test/AncestorA"): ("ancestor A", "definition A"),
        URIRef(FIBO_BASE + "Test/AncestorB"): ("ancestor B", "definition B"),
    }
    for ancestor, (label, definition) in ancestors.items():
        graph.add((ancestor, RDFS.label, Literal(label)))
        graph.add((ancestor, SKOS.definition, Literal(definition)))
    for number, row in enumerate(rows):
        seed = URIRef(row["fibo_iri"])
        graph.add((seed, RDFS.label, Literal(f"seed {number}")))
        graph.add((seed, SKOS.definition, Literal(f"definition {number}")))
        parent = list(ancestors)[number % 2]
        graph.add((seed, RDFS.subClassOf, parent))
        if number == 0:
            graph.add(
                (
                    seed,
                    RDFS.subClassOf,
                    URIRef("https://www.omg.org/spec/Commons/Classifiers/Classifier"),
                )
            )
        if number == 1:
            graph.add((seed, CMNS_AV.explanatoryNote, Literal("a note")))
    path = tmp_path / "release.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fibo/ontology/master/2026Q2/Test.ttl", graph.serialize(format="turtle"))
    return path


def test_the_builder_expands_only_release_ancestors_and_is_deterministic(tmp_path: Path) -> None:
    release = _synthetic_zip(tmp_path)
    result = build_result(release, TERMS, expected_sha256=sha256(release))
    assert len(result.entries) == 27
    assert not any(entry.endswith("Commons/Classifiers/Classifier") for entry in result.entries)
    assert result.english_counts[str(RDFS.label)] == 27
    assert result.english_counts[str(SKOS.definition)] == 27
    assert result.english_counts[str(RDFS.subClassOf)] == 26
    assert result.english_counts[str(CMNS_AV.explanatoryNote)] == 1
    assert result.spanish_statements == 50
    assert result.header_statements == 4
    assert not any(predicate == RDF.type for _subject, predicate, _obj in result.triples)
    first = serialize(result)
    second = serialize(build_result(release, TERMS, expected_sha256=sha256(release)))
    assert first == second


def test_the_builder_writes_byte_identical_files(tmp_path: Path) -> None:
    release = _synthetic_zip(tmp_path)
    one, two = tmp_path / "one.ttl", tmp_path / "two.ttl"
    build_slice(release, TERMS, one, expected_sha256=sha256(release))
    build_slice(release, TERMS, two, expected_sha256=sha256(release))
    assert one.read_bytes() == two.read_bytes()


def test_an_unreviewed_row_is_not_loaded(tmp_path: Path) -> None:
    release = _synthetic_zip(tmp_path)
    terms = tmp_path / "terms.csv"
    terms.write_text(
        "fibo_iri,our_term,fit,label_es,definition_es\n"
        f"{FIBO_BASE}IND/MarketIndices/BasketIndices/EquityIndex,"
        f"{OUR_NAMESPACE}SP500Index,same,,\n",
        encoding="utf-8",
    )
    result = build_result(release, terms, expected_sha256=sha256(release))
    assert result.spanish_statements == 0


def test_a_non_pinned_zip_is_refused(tmp_path: Path) -> None:
    release = _synthetic_zip(tmp_path)
    with pytest.raises(FiboTermsError, match="refusing the release"):
        build_result(release, TERMS)


@pytest.mark.integration
def test_rebuilding_from_the_real_release_is_byte_identical(tmp_path: Path) -> None:
    release = os.environ.get("FIBO_ZIP")
    if not release:
        pytest.skip("FIBO_ZIP is not set")
    out = tmp_path / "fibo.ttl"
    build_slice(release, TERMS, out)
    assert out.read_bytes() == SLICE.read_bytes()
