"""The ingest gate (``kg_store.gate``): target names, parsing, type checks and SHACL (T-136)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import rdflib

from kg_store import gate

if TYPE_CHECKING:
    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
PREFIXES = b"@prefix : <https://thesis.local/kg/portfolio#> .\n"


def _instance_graphs() -> dict[str, rdflib.Graph]:
    ds = rdflib.Dataset(default_union=False)
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return {str(g.identifier): g for g in ds.graphs() if len(g)}


def _reject(batch: rdflib.Graph) -> str:
    with pytest.raises(gate.IngestRejected) as info:
        gate.validate(batch)
    return str(info.value)


# --- check_target -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_instance_graphs()))
def test_every_instances_graph_is_an_accepted_target(name: str) -> None:
    """The worked example's own graph names are what the gate must let through."""
    assert gate.check_target(name) is (name != "urn:graph:portfolio:current")


def test_the_mutable_graph_is_not_append_only() -> None:
    assert gate.check_target("urn:graph:portfolio:current") is False


@pytest.mark.parametrize(
    "name",
    [
        "urn:graph:tbox",
        "urn:graph:derived:quant:2026-Q3",  # quant is dated, never quarterly (docs/07)
        "urn:graph:derived:quant:",
        "urn:graph:ingest:UNKNOWN:2026-08-05",
        "urn:graph:ingest:SEMANTIC:2026-Q3",  # only FUNDAMENTAL and EDGAR take a quarter
        "urn:graph:universe:2026-08-05",
        "urn:graph:ingest:SEMANTIC:2026-08-05/extra",
        "",
    ],
)
def test_other_graph_names_are_refused(name: str) -> None:
    with pytest.raises(gate.IngestRejected, match="not an ingest target"):
        gate.check_target(name)


def test_an_impossible_date_is_refused() -> None:
    with pytest.raises(gate.IngestRejected, match="impossible date"):
        gate.check_target("urn:graph:derived:quant:2026-02-30")


def test_the_refusal_lists_the_quant_graph() -> None:
    with pytest.raises(gate.IngestRejected, match=r"derived:quant:YYYY-MM-DD"):
        gate.check_target("urn:graph:nope")


# --- parse_batch ------------------------------------------------------------------------------


def test_parse_batch_reads_turtle() -> None:
    assert len(gate.parse_batch(PREFIXES + b":a a :Asset .")) == 1


def test_parse_batch_refuses_bad_syntax() -> None:
    with pytest.raises(gate.IngestRejected, match="cannot parse batch as turtle"):
        gate.parse_batch(b":a a")


def test_parse_batch_refuses_an_empty_batch() -> None:
    with pytest.raises(gate.IngestRejected, match="empty"):
        gate.parse_batch(PREFIXES)


def test_parse_batch_refuses_relative_iris() -> None:
    with pytest.raises(gate.IngestRejected, match="relative IRIs"):
        gate.parse_batch(PREFIXES + b"<rel> a :Asset .")


# --- unknown_types and untyped_writes ---------------------------------------------------------


@pytest.fixture(scope="module")
def schema() -> gate.GateSchema:
    return gate.load_gate_schema(SCHEMA.resolve())


def test_the_gate_reads_the_disjoint_leaf_classes(schema: gate.GateSchema) -> None:
    assert {KG.Asset, KG.Veto, KG.BenchmarkObservation, KG.AssetCoOccurrence} <= schema.leaf_classes
    assert KG.ObservationSnapshot not in schema.leaf_classes


def test_unknown_types_flags_a_typo_and_an_abstract_class(schema: gate.GateSchema) -> None:
    batch = gate.parse_batch(
        PREFIXES + b":a a :ScoreSnapshott . :b a :ObservationSnapshot . :c a :Asset ."
    )
    assert gate.unknown_types(batch, schema) == {
        str(KG.ScoreSnapshott),
        str(KG.ObservationSnapshot),
    }


def test_untyped_subject_may_only_take_relations_or_a_closing_date(schema: gate.GateSchema) -> None:
    ok = gate.parse_batch(
        PREFIXES
        + b':x :hasScoreObservation :y . :x :validTo "2026-01-31"^^<http://www.w3.org/2001/XMLSchema#date> .'
    )
    assert gate.untyped_writes(ok, schema) == []


@pytest.mark.parametrize(
    "triple",
    [
        b':x :rawValue "1.0" .',  # a value added to an existing observation
        b':x :hasScoreObservation "not an individual" .',  # relation to a literal
        b':x :validTo "2026-01-31" .',  # a plain string, not xsd:date
        b':x :validTo "2026-02-30"^^<http://www.w3.org/2001/XMLSchema#date> .',  # impossible date
    ],
)
def test_untyped_subject_writes_are_flagged(triple: bytes, schema: gate.GateSchema) -> None:
    assert gate.untyped_writes(gate.parse_batch(PREFIXES + triple), schema)


def test_a_typed_subject_is_not_an_untyped_write(schema: gate.GateSchema) -> None:
    batch = gate.parse_batch(PREFIXES + b':a a :Asset ; :tickerSymbol "A" .')
    assert gate.untyped_writes(batch, schema) == []


# --- validate ---------------------------------------------------------------------------------


#: Worked-example graphs that cannot be a batch on their own: they point at individuals the
#: batch does not declare (an Asset or Portfolio typed in another graph, or a Veto closed by
#: ``:clearedOn``), which ``validate`` refuses. ``strict`` xfail: it fails loudly once fixed.
_NOT_SELF_CONTAINED = {
    "urn:graph:derived:entity-resolution:2026-08-05": "sh:class :Asset on an Asset typed elsewhere",
    "urn:graph:derived:quant:2026-08-05": "sh:class on an Asset/Portfolio typed elsewhere",
    "urn:graph:ingest:ORCHESTRATOR:2026-08-05": ":clearedOn on a Veto typed elsewhere",
}
_SHACL_GAPS = [n for n in _NOT_SELF_CONTAINED if "ORCHESTRATOR" not in n]


def _batch_params() -> list[object]:
    return [
        pytest.param(
            name,
            marks=pytest.mark.xfail(
                strict=True, raises=gate.IngestRejected, reason=_NOT_SELF_CONTAINED[name]
            ),
        )
        if name in _NOT_SELF_CONTAINED
        else name
        for name in sorted(_instance_graphs())
        if "portfolio:current" not in name
    ]


@pytest.mark.parametrize("name", _batch_params())
def test_a_conforming_batch_passes(name: str) -> None:
    """Each worked-example graph, taken alone as a batch, clears every check."""
    gate.validate(_instance_graphs()[name])


@pytest.mark.parametrize("name", _SHACL_GAPS)
def test_the_standalone_gap_is_only_a_class_check_on_a_reference(name: str) -> None:
    """The two SHACL xfails fail for the documented reason and no other (T-146)."""
    with pytest.raises(gate.ShaclRejected) as info:
        gate.validate(_instance_graphs()[name])
    components = {
        c for c in info.value.results.objects(None, rdflib.namespace.SH.sourceConstraintComponent)
    }
    assert components == {rdflib.namespace.SH.ClassConstraintComponent}


def test_the_orchestrator_gap_is_the_untyped_subject_rule_on_cleared_on() -> None:
    graph = _instance_graphs()["urn:graph:ingest:ORCHESTRATOR:2026-08-05"]
    message = _reject(graph)
    assert "no rdf:type" in message
    assert ":clearedOn" in message


def test_a_per_run_weight_scheme_is_accepted_into_an_orchestrator_graph(make_db: MakeDB) -> None:
    """T-121 places a per-run scheme (and its components) in the ORCHESTRATOR graph of its date."""
    batch = (
        PREFIXES
        + b"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        + b':WS_cycle_run_42 a :AttractivenessWeightScheme ; :schemeId "cycle_run:42" ;'
        + b' :cycleDate "2026-10-07"^^xsd:date ; :bookWeightingRule "score_tilt" ;'
        + b' :topN 30 ; :softVetoPenalty "15"^^xsd:decimal ; :hasWeightComponent :WC_42_FUND .\n'
        + b':WC_42_FUND a :WeightComponent ; :weightMetricName "ScoreFinanciero" ;'
        + b' :weightValue "0.3333"^^xsd:decimal .\n'
    )
    fake = make_db()
    written = gate.ingest(fake.db, batch, "urn:graph:ingest:ORCHESTRATOR:2026-10-07")
    assert written == 10
    assert fake.added[0][2] == "urn:graph:ingest:ORCHESTRATOR:2026-10-07"


def test_validate_rejects_an_unknown_type() -> None:
    message = _reject(gate.parse_batch(PREFIXES + b":a a :ScoreSnapshott ."))
    assert "not leaf classes" in message


def test_validate_rejects_a_stray_write() -> None:
    message = _reject(gate.parse_batch(PREFIXES + b':x :rawValue "1.0" .'))
    assert "no rdf:type" in message


def test_validate_rejects_a_shape_violation_with_the_results_graph() -> None:
    batch = gate.parse_batch(PREFIXES + b':a a :Asset ; :cikNumber "0000000001" .')
    with pytest.raises(gate.ShaclRejected) as info:
        gate.validate(batch)
    assert "SHACL validation failed" in str(info.value)
    assert any(info.value.results.subjects(rdflib.RDF.type, rdflib.namespace.SH.ValidationResult))


# --- existing_subjects and ingest -------------------------------------------------------------

GOOD = PREFIXES + b':a a :Asset ; :tickerSymbol "AAA" ; :cikNumber "0000000001" .'


def test_existing_subjects_reports_what_the_store_has(make_db: MakeDB) -> None:
    fake = make_db(rows=[{"s": "https://thesis.local/kg/portfolio#a"}])
    db = fake.db
    found = gate.existing_subjects(db, gate.parse_batch(GOOD))
    assert found == ["https://thesis.local/kg/portfolio#a"]
    assert "http://www.ontotext.com/explicit" in fake.queries[0]


def test_existing_subjects_queries_in_chunks_of_200(make_db: MakeDB) -> None:
    fake = make_db()
    db = fake.db
    lines = b"".join(b":s%d a :Asset .\n" % i for i in range(450))
    gate.existing_subjects(db, gate.parse_batch(PREFIXES + lines))
    assert len(fake.queries) == 3


def test_existing_subjects_refuses_an_iri_that_could_inject_sparql(make_db: MakeDB) -> None:
    fake = make_db()
    db = fake.db
    batch = rdflib.Graph()
    batch.add((rdflib.URIRef("https://x.test/a b"), rdflib.RDF.type, KG.Asset))
    with pytest.raises(gate.IngestRejected, match="illegal in an IRI"):
        gate.existing_subjects(db, batch)
    assert fake.queries == []


def test_ingest_writes_the_validated_triples_as_ntriples(make_db: MakeDB) -> None:
    fake = make_db()
    db = fake.db
    written = gate.ingest(db, GOOD, "urn:graph:ingest:SEMANTIC:2026-08-05")
    assert written == 3
    [(data, content_type, graph)] = fake.added
    assert content_type == "application/n-triples"
    assert graph == "urn:graph:ingest:SEMANTIC:2026-08-05"
    assert len(rdflib.Graph().parse(data=data, format="nt")) == 3


def test_ingest_into_the_mutable_graph_skips_the_exists_check(make_db: MakeDB) -> None:
    fake = make_db()
    db = fake.db
    gate.ingest(db, GOOD, "urn:graph:portfolio:current")
    assert len(fake.queries) == 1  # only existing_subjects, no GRAPH <...> LIMIT 1 probe
    assert len(fake.added) == 1


def test_ingest_refuses_an_existing_append_only_graph(make_db: MakeDB) -> None:
    fake = make_db(rows=[{"s": "x"}])
    db = fake.db
    with pytest.raises(gate.IngestRejected, match="already exists and is append-only"):
        gate.ingest(db, GOOD, "urn:graph:ingest:SEMANTIC:2026-08-05")
    assert fake.added == []


def test_ingest_refuses_individuals_already_in_the_store(make_db: MakeDB) -> None:
    fake = make_db(rows=[{"s": "https://thesis.local/kg/portfolio#a"}])
    db = fake.db
    with pytest.raises(gate.IngestRejected, match="already exist in the store"):
        gate.ingest(db, GOOD, "urn:graph:portfolio:current")
    assert fake.added == []


@pytest.mark.parametrize(
    ("data", "graph"),
    [
        (GOOD, "urn:graph:tbox"),
        (PREFIXES + b":a a :ScoreSnapshott .", "urn:graph:portfolio:current"),
        (PREFIXES + b':a a :Asset ; :cikNumber "1" .', "urn:graph:portfolio:current"),
    ],
)
def test_a_refused_batch_writes_nothing(data: bytes, graph: str, make_db: MakeDB) -> None:
    fake = make_db()
    db = fake.db
    with pytest.raises(gate.IngestRejected):
        gate.ingest(db, data, graph)
    assert fake.added == []
