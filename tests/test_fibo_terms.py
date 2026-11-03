"""The FIBO Phase 1 terms file, its schema links and the release checker (T-210).

Hermetic: the real ``prod.ttl.zip`` is neither committed nor read here. The checker's logic runs
over a tiny synthetic zip, and the real-release run is ``cli/check_fibo_terms.py`` with the zip
supplied from outside the repo.
"""

from __future__ import annotations

import csv
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest
import rdflib
from rdflib.namespace import RDF, RDFS

from projection.fibo_terms import (
    FIBO_BASE,
    OUR_NAMESPACE,
    FiboTermsError,
    HashMismatch,
    check_release,
    read_terms,
    sha256,
)

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
REPO = SCHEMA.parent
TERMS = SCHEMA / "fibo_terms.csv"
CLI = REPO / "cli" / "check_fibo_terms.py"
OLD_FIBO = "https://www.omg.org/spec/EDMC-FIBO/"
KG = rdflib.Namespace(OUR_NAMESPACE)
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")

#: The six linked rows of the brief §2, in the terms file's order (the Phase 2 :SP500Index row is
#: deliberately absent from this list and checked separately by the slice/ETL tests).
EXPECTED = [
    (
        f"{FIBO_BASE}FND/OwnershipAndControl/Ownership/Portfolio",
        f"{OUR_NAMESPACE}Portfolio",
        "same",
    ),
    (
        f"{FIBO_BASE}FBC/ProductsAndServices/FinancialProductsAndServices/Position",
        f"{OUR_NAMESPACE}PortfolioPosition",
        "same",
    ),
    (
        f"{FIBO_BASE}SEC/Securities/SecuritiesIdentification/TickerSymbol",
        f"{OUR_NAMESPACE}tickerSymbol",
        "same",
    ),
    (
        (
            f"{FIBO_BASE}SEC/Securities/SecuritiesClassification/"
            "GlobalIndustryClassificationStandardsClassifier"
        ),
        f"{OUR_NAMESPACE}Sector",
        "same",
    ),
    (
        f"{FIBO_BASE}FND/Arrangements/ClassificationSchemes/IndustrySectorClassifier",
        f"{OUR_NAMESPACE}Industry",
        "broader",
    ),
    (
        f"{FIBO_BASE}FND/Arrangements/Reporting/Report",
        f"{OUR_NAMESPACE}SECFiling",
        "broader",
    ),
]

#: The 18 glossary-only seeds of brief §4.1, in order. Their ``our_term`` stays empty.
GLOSSARY = [
    f"{FIBO_BASE}SEC/Equities/EquityInstruments/ListedShare",
    f"{FIBO_BASE}BE/LegalEntities/CorporateBodies/PubliclyHeldCompany",
    f"{FIBO_BASE}SEC/Equities/EquityInstruments/EquityPosition",
    f"{FIBO_BASE}FBC/FunctionalEntities/Markets/Exchange",
    (
        f"{FIBO_BASE}FBC/FunctionalEntities/NorthAmericanEntities/USRegulatoryAgencies/"
        "SecuritiesAndExchangeCommission"
    ),
    f"{FIBO_BASE}BE/OwnershipAndControl/Executives/BoardMember",
    f"{FIBO_BASE}BE/OwnershipAndControl/Executives/CorporateOfficer",
    f"{FIBO_BASE}FBC/FinancialInstruments/InstrumentPricing/ClosingPrice",
    f"{FIBO_BASE}FBC/FinancialInstruments/InstrumentPricing/AdjustedClosingPrice",
    f"{FIBO_BASE}FBC/FinancialInstruments/InstrumentPricing/RateOfReturn",
    f"{FIBO_BASE}IND/Indicators/Indicators/Volatility",
    f"{FIBO_BASE}FND/Utilities/Analytics/Variance",
    f"{FIBO_BASE}FND/Utilities/Analytics/StandardDeviation",
    f"{FIBO_BASE}IND/EconomicIndicators/EconomicIndicators/ConsumerPriceIndex",
    (
        f"{FIBO_BASE}IND/EconomicIndicators/NorthAmericanIndicators/USEconomicIndicators/"
        "UrbanConsumerPriceIndex"
    ),
    f"{FIBO_BASE}IND/EconomicIndicators/EconomicIndicators/InflationRate",
    f"{FIBO_BASE}IND/MarketIndices/BasketIndices/MarketCapitalization",
    f"{FIBO_BASE}SEC/Equities/EquityInstruments/Dividend",
]
SP500 = f"{FIBO_BASE}IND/MarketIndices/BasketIndices/EquityIndex"

#: The hand-maintained schema files P4(a) names. ``protege-view.ttl``/``.txt`` are generated and are
#: the documented exception: they still carry the old EDMC-FIBO IRIs until T-070/T-071 regenerates
#: them, so this test scopes to the files a person edits.
SCHEMA_FILES = [
    SCHEMA / "tbox.ttl",
    SCHEMA / "shapes.ttl",
    SCHEMA / "reference.ttl",
    SCHEMA / "rules.ttl",
    SCHEMA / "instances.trig",
    REPO / "kg_target_schema.ttl",
]


def _rows() -> list[dict[str, str]]:
    with TERMS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _iris(path: Path) -> set[str]:
    """Every IRI mentioned as a subject, predicate or object of ``path``."""
    if path.suffix == ".trig":
        dataset = rdflib.Dataset().parse(path, format="trig")
        terms = [term for quad in dataset.quads() for term in quad[:3]]
    else:
        graph = rdflib.Graph().parse(path, format="turtle")
        terms = [term for triple in graph for term in triple]
    return {
        str(term)
        for term in terms
        if isinstance(term, rdflib.URIRef) and str(term).startswith(OLD_FIBO)
    }


def _fibo_links(path: Path) -> set[tuple[rdflib.term.Node, rdflib.term.Node]]:
    graph = rdflib.Graph().parse(path, format="turtle")
    return {
        (subject, obj)
        for subject, obj in graph.subject_objects(RDFS.seeAlso)
        if str(obj).startswith(FIBO_BASE)
    }


def _declared(path: Path) -> set[str]:
    graph = rdflib.Graph().parse(path, format="turtle")
    return {str(subject) for subject in graph.subjects(RDF.type, None)}


# --- P4(c): the terms file ----------------------------------------------------------------------


def test_the_terms_file_has_the_25_phase_two_rows() -> None:
    rows = _rows()
    assert list(rows[0]) == ["fibo_iri", "our_term", "fit", "label_es", "definition_es"]
    assert len(rows) == 25
    assert [(row["fibo_iri"], row["our_term"], row["fit"]) for row in rows[:6]] == EXPECTED
    assert (rows[6]["fibo_iri"], rows[6]["our_term"], rows[6]["fit"]) == (
        SP500,
        f"{OUR_NAMESPACE}SP500Index",
        "same",
    )
    assert [(row["fibo_iri"], row["our_term"], row["fit"]) for row in rows[7:]] == [
        (iri, "", "glossary") for iri in GLOSSARY
    ]
    assert all(row["label_es"] and row["definition_es"] for row in rows)
    assert len({row["fibo_iri"] for row in rows}) == 25
    assert len({row["our_term"] for row in rows if row["our_term"]}) == 7


def test_every_fibo_iri_is_unversioned_and_under_the_fibo_ontology() -> None:
    for row in _rows():
        assert row["fibo_iri"].startswith(FIBO_BASE)
        assert "/master/" not in row["fibo_iri"]
        assert row["fit"] in {"same", "broader", "glossary"}
        if row["fit"] == "glossary":
            assert row["our_term"] == ""
        else:
            assert row["our_term"].startswith(OUR_NAMESPACE)


def test_read_terms_rejects_a_fit_the_brief_does_not_define(tmp_path: Path) -> None:
    path = tmp_path / "terms.csv"
    path.write_text(
        "fibo_iri,our_term,fit,label_es,definition_es\n"
        f"{FIBO_BASE}FND/OwnershipAndControl/Ownership/Portfolio,"
        f"{OUR_NAMESPACE}Portfolio,differs,,\n",
        encoding="utf-8",
    )
    with pytest.raises(FiboTermsError, match="fit"):
        read_terms(path)


def test_read_terms_rejects_a_glossary_row_with_our_term(tmp_path: Path) -> None:
    path = tmp_path / "terms.csv"
    path.write_text(
        "fibo_iri,our_term,fit,label_es,definition_es\n"
        f"{FIBO_BASE}SEC/Equities/EquityInstruments/ListedShare,"
        f"{OUR_NAMESPACE}Asset,glossary,,\n",
        encoding="utf-8",
    )
    with pytest.raises(FiboTermsError, match="empty our_term"):
        read_terms(path)


def test_read_terms_rejects_a_link_row_without_our_term(tmp_path: Path) -> None:
    path = tmp_path / "terms.csv"
    path.write_text(
        "fibo_iri,our_term,fit,label_es,definition_es\n"
        f"{FIBO_BASE}FND/OwnershipAndControl/Ownership/Portfolio,,same,,\n",
        encoding="utf-8",
    )
    with pytest.raises(FiboTermsError, match="our_term"):
        read_terms(path)


def test_read_terms_rejects_a_duplicate_fibo_iri(tmp_path: Path) -> None:
    path = tmp_path / "terms.csv"
    row = (
        f"{FIBO_BASE}FND/OwnershipAndControl/Ownership/Portfolio,{OUR_NAMESPACE}Portfolio,same,,\n"
    )
    path.write_text(
        "fibo_iri,our_term,fit,label_es,definition_es\n" + row + row,
        encoding="utf-8",
    )
    with pytest.raises(FiboTermsError, match="duplicate"):
        read_terms(path)


# --- P4(a): the broken links are gone -----------------------------------------------------------


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=[path.name for path in SCHEMA_FILES])
def test_no_old_edmc_fibo_iri_remains_in_a_hand_maintained_schema_file(path: Path) -> None:
    assert _iris(path) == set()


# --- P4(b): the seeAlso pairs equal the terms file ----------------------------------------------


def test_tbox_fibo_links_equal_the_terms_file_rows_it_declares() -> None:
    declared = _declared(SCHEMA / "tbox.ttl")
    expected = {
        (rdflib.URIRef(row["our_term"]), rdflib.URIRef(row["fibo_iri"]))
        for row in _rows()
        if row["our_term"]
        and row["our_term"] != f"{OUR_NAMESPACE}SP500Index"
        and row["our_term"] in declared
    }
    assert _fibo_links(SCHEMA / "tbox.ttl") == expected
    assert len(expected) == 6


def test_tbox_no_longer_links_asset_to_a_fibo_legal_person() -> None:
    graph = rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")
    assert (KG.Asset, RDFS.seeAlso, None) not in graph


def test_target_schema_mirrors_the_links_for_the_terms_it_declares() -> None:
    path = REPO / "kg_target_schema.ttl"
    declared = _declared(path)
    # The target schema does not declare :Sector or :Industry (it only refers to them as ranges),
    # so it mirrors four of the six links; that is the P3 finding recorded in the PR.
    linked = [row for row in _rows() if row["our_term"] and row["fit"] != "glossary"]
    declared_terms = {row["our_term"] for row in linked if row["our_term"] in declared}
    assert declared_terms == {
        f"{OUR_NAMESPACE}Portfolio",
        f"{OUR_NAMESPACE}PortfolioPosition",
        f"{OUR_NAMESPACE}tickerSymbol",
        f"{OUR_NAMESPACE}SECFiling",
    }
    expected = {
        (rdflib.URIRef(row["our_term"]), rdflib.URIRef(row["fibo_iri"]))
        for row in linked
        if row["our_term"] in declared
    }
    assert _fibo_links(path) == expected
    graph = rdflib.Graph().parse(path, format="turtle")
    assert (KG.Asset, RDFS.seeAlso, None) not in graph


# --- P4(e): the release checker, over a tiny synthetic zip ---------------------------------------

_TURTLE_HEADER = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n\n"
)


def _release_zip(
    tmp_path: Path,
    entries: Mapping[str, tuple[str | None, str | None]],
    *,
    name: str = "release.zip",
) -> Path:
    """A one-module synthetic release; a ``None`` label/definition is omitted."""
    lines = [_TURTLE_HEADER]
    for iri, (label, definition) in entries.items():
        lines.append(f"<{iri}> a owl:Class")
        if label is not None:
            lines.append(f' ; rdfs:label "{label}"')
        if definition is not None:
            lines.append(f' ; skos:definition "{definition}"')
        lines.append(" .\n\n")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fibo/ontology/master/2026Q2/Test.ttl", "".join(lines))
    return path


def _all_terms() -> dict[str, tuple[str | None, str | None]]:
    return {
        row["fibo_iri"]: (f"label {number}", f"definition {number}")
        for number, row in enumerate(_rows())
    }


def test_the_checker_accepts_a_release_with_a_label_and_definition_for_every_row(
    tmp_path: Path,
) -> None:
    path = _release_zip(tmp_path, _all_terms())
    result = check_release(path, TERMS, expected_sha256=sha256(path))
    assert result.ok
    assert {term.iri for term in result.found.values()} == {row["fibo_iri"] for row in _rows()}
    assert all(term.label.startswith("label ") for term in result.found.values())


def test_a_release_with_a_different_sha256_is_refused(tmp_path: Path) -> None:
    path = _release_zip(tmp_path, _all_terms())
    with pytest.raises(HashMismatch, match="refusing the release"):
        check_release(path, TERMS)  # the pinned FIBO 2026Q2 sha256


def test_an_iri_missing_from_the_release_is_reported(tmp_path: Path) -> None:
    entries = _all_terms()
    missing = EXPECTED[0][0]
    del entries[missing]
    path = _release_zip(tmp_path, entries)
    result = check_release(path, TERMS, expected_sha256=sha256(path))
    assert not result.ok
    assert result.failures == (f"{missing}: missing from the release",)


def test_an_iri_without_a_definition_is_reported(tmp_path: Path) -> None:
    entries = _all_terms()
    no_definition = EXPECTED[1][0]
    label, _definition = entries[no_definition]
    entries[no_definition] = (label, None)
    path = _release_zip(tmp_path, entries)
    result = check_release(path, TERMS, expected_sha256=sha256(path))
    assert not result.ok
    assert result.failures == (f"{no_definition}: no skos:definition in the release",)


def test_an_iri_without_a_label_is_reported(tmp_path: Path) -> None:
    entries = _all_terms()
    no_label = EXPECTED[2][0]
    _label, definition = entries[no_label]
    entries[no_label] = (None, definition)
    path = _release_zip(tmp_path, entries)
    result = check_release(path, TERMS, expected_sha256=sha256(path))
    assert not result.ok
    assert result.failures == (f"{no_label}: no rdfs:label in the release",)


# --- the CLI entry point ------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, tmp_path arguments
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_missing_zip_is_a_bad_argument(tmp_path: Path) -> None:
    result = _run("--zip", str(tmp_path / "no.zip"), "--terms", str(TERMS))
    assert result.returncode == 2
    assert "bad argument" in result.stderr


def test_a_missing_terms_file_is_a_bad_argument(tmp_path: Path) -> None:
    result = _run("--zip", str(_release_zip(tmp_path, _all_terms())), "--terms", "no.csv")
    assert result.returncode == 2
    assert "bad argument" in result.stderr


def test_a_non_pinned_zip_exits_1(tmp_path: Path) -> None:
    path = _release_zip(tmp_path, _all_terms())
    result = _run("--zip", str(path), "--terms", str(TERMS))
    assert result.returncode == 1
    assert "not the pinned" in result.stderr
