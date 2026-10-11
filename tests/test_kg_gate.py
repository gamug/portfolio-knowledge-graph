"""The ingest gate (``kg_store.gate``): target names, parsing, type checks and SHACL (T-136)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import rdflib

from kg_store import gate
from kg_store.graphdb import AnswerLost, GraphDBError

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


def _context_for(name: str) -> rdflib.Graph:
    """What the rest of the worked example says about the individuals graph ``name`` points at,
    as the store would hold it once the other graphs are loaded (T-146)."""
    graphs = _instance_graphs()
    schema = gate.load_gate_schema(SCHEMA.resolve())
    refs = gate.references(graphs[name], schema)
    # The Assets are typed in reference.ttl; the other graphs hold the Portfolios.
    others = {k: g for k, g in graphs.items() if k != name}
    others["urn:graph:reference"] = rdflib.Graph().parse(SCHEMA / "reference.ttl", format="turtle")
    context = rdflib.Graph()
    for graph in others.values():
        for ref in refs:
            for p, o in graph.predicate_objects(ref):
                context.add((ref, p, o))
    return context


@pytest.mark.parametrize(
    "name", [n for n in sorted(_instance_graphs()) if "portfolio:current" not in n]
)
def test_a_conforming_batch_passes(name: str) -> None:
    """Each worked-example graph, taken as a batch beside what the store holds about the
    individuals it points at, clears every check."""
    gate.validate(_instance_graphs()[name], context=_context_for(name))


@pytest.mark.parametrize(
    "name",
    ["urn:graph:derived:entity-resolution:2026-08-05", "urn:graph:derived:quant:2026-08-05"],
)
def test_a_reference_the_store_does_not_hold_fails_the_class_check(name: str) -> None:
    """Without the referenced Assets and Portfolios the batch fails for that reason only."""
    with pytest.raises(gate.ShaclRejected) as info:
        gate.validate(_instance_graphs()[name])
    components = {
        c for c in info.value.results.objects(None, rdflib.namespace.SH.sourceConstraintComponent)
    }
    assert components == {rdflib.namespace.SH.ClassConstraintComponent}


def test_the_stored_portfolio_kind_is_what_the_quant_rule_reads() -> None:
    """A book metric about the stored LIVE portfolio is refused; about a BENCHMARK one it passes."""
    name = "urn:graph:derived:quant:2026-08-05"
    batch = rdflib.Graph()
    batch += _instance_graphs()[name]
    live_obs = KG.BObs_LiveActive_20260805
    batch.set((live_obs, KG.quantMetric, rdflib.Literal("sharpe")))
    context = _context_for(name)
    with pytest.raises(gate.ShaclRejected):
        gate.validate(batch, context=context)
    context.set((KG.MainPortfolio_2026, KG.portfolioKind, rdflib.Literal("BENCHMARK")))
    gate.validate(batch, context=context)


def test_references_are_the_untyped_objects_of_relations(schema: gate.GateSchema) -> None:
    batch = gate.parse_batch(
        PREFIXES + b":c a :AssetCoOccurrence ; :coOccurrenceAsset :A, :B . :A a :Asset ."
    )
    assert gate.references(batch, schema) == {KG.B}


def test_fetch_context_types_the_stored_values(make_db: MakeDB, schema: gate.GateSchema) -> None:
    type_iri = str(rdflib.RDF.type)
    fake = make_db(
        rows=[
            {"s": str(KG.P), "p": type_iri, "o": str(KG.Portfolio)},
            {"s": str(KG.P), "p": str(KG.portfolioKind), "o": "BENCHMARK"},
            {"s": str(KG.P), "p": "https://x.test/odd", "o": "free"},
            {"s": str(KG.P)},  # a row without a statement is skipped
        ]
    )
    batch = gate.parse_batch(PREFIXES + b":o a :BenchmarkObservation ; :quantPortfolio :P .")
    context = gate.fetch_context(fake.db, {KG.P}, schema, batch)
    assert (KG.P, rdflib.RDF.type, KG.Portfolio) in context
    assert (
        KG.P,
        KG.portfolioKind,
        rdflib.Literal("BENCHMARK", datatype=rdflib.XSD.string),
    ) in context
    assert (KG.P, rdflib.URIRef("https://x.test/odd"), rdflib.Literal("free")) in context
    assert "http://www.ontotext.com/explicit" in fake.queries[0]


def test_fetch_context_also_reads_the_memberships_of_a_referenced_asset(
    make_db: MakeDB, schema: gate.GateSchema
) -> None:
    """An Asset without a CIK conforms only if its memberships are closed (``validTo``), so
    the query follows ``hasUniverseMembership`` one step (a reviewer's catch on PR #86)."""
    batch = gate.parse_batch(
        PREFIXES + b":c a :AssetCoOccurrence ; :coOccurrenceAsset :GONE, :OTHER ;"
        b' :coOccurrenceKind "SHARED_EXECUTIVE_CANDIDATE" ; :coOccurrenceMethod "m" ;'
        b' :coOccurrenceWeight 1.0 . :OTHER a :Asset ; :tickerSymbol "O" ; :cikNumber "1" .'
    )
    stored = gate.parse_batch(
        PREFIXES + b':GONE a :Asset ; :tickerSymbol "G" ; :hasUniverseMembership :UM .'
        b' :UM a :UniverseMembership ; :validTo "2026-01-31"^^<http://www.w3.org/2001/XMLSchema#date> .'
    )
    context = rdflib.Graph()
    for t in stored:
        if t[0] != KG.UM or t[1] != rdflib.RDF.type:  # the stored memberships' type is not needed
            context.add(t)
    gate.validate(batch, context=context)
    fake = make_db()
    gate.fetch_context(fake.db, {KG.GONE}, schema, batch)
    assert "VALUES ?r {" in fake.queries[0]
    assert f"?r <{KG.hasUniverseMembership}> ?s" in fake.queries[0]


def test_the_context_reads_only_what_the_shapes_of_the_references_read(
    make_db: MakeDB, schema: gate.GateSchema
) -> None:
    """A referenced Asset's snapshot links grow with the store's history; none is fetched."""
    name = "urn:graph:derived:entity-resolution:2026-08-05"
    batch = _instance_graphs()[name]
    refs = gate.references(batch, schema)
    paths = gate.context_predicates(batch, refs, schema)
    assert {rdflib.RDF.type, KG.tickerSymbol, KG.cikNumber, KG.hasUniverseMembership} <= paths
    assert KG.hasScoreObservation not in paths
    assert KG.portfolioKind not in paths  # a Portfolio's shape is not the batch's concern

    fake = make_db()
    gate.fetch_context(fake.db, refs, schema, batch)
    assert "VALUES ?p {" in fake.queries[0]
    assert "hasScoreObservation" not in fake.queries[0]
    assert f"?r <{KG.hasUniverseMembership}> ?s" in fake.queries[0]
    assert f"VALUES ?p {{ <{KG.validTo}> }}" in fake.queries[0]
    assert gate.nested_paths(schema, KG.hasUniverseMembership) == {KG.validTo}
    assert gate.nested_paths(schema, KG.coOccurrenceAsset) == set()


def test_a_portfolio_reference_makes_no_membership_hop(
    make_db: MakeDB, schema: gate.GateSchema
) -> None:
    batch = gate.parse_batch(
        PREFIXES + b':o a :BenchmarkObservation ; :quantPortfolio :P ; :quantMetric "m" .'
    )
    fake = make_db()
    gate.fetch_context(fake.db, gate.references(batch, schema), schema, batch)
    assert "VALUES ?p {" in fake.queries[0]
    assert "hasUniverseMembership" not in fake.queries[0]


def test_a_relation_without_a_class_asks_only_for_the_type(schema: gate.GateSchema) -> None:
    """``:supersededBy`` requires nothing of its target, so nothing but ``rdf:type`` is fetched."""
    batch = gate.parse_batch(PREFIXES + b":x :supersededBy :y .")
    assert gate.context_predicates(batch, gate.references(batch, schema), schema) == {
        rdflib.RDF.type
    }


def test_the_quant_context_reads_the_portfolio_kind(schema: gate.GateSchema) -> None:
    name = "urn:graph:derived:quant:2026-08-05"
    batch = _instance_graphs()[name]
    paths = gate.context_predicates(batch, gate.references(batch, schema), schema)
    assert {KG.portfolioKind, KG.portfolioName} <= paths


def _counting_context(calls: list[int]) -> Callable[[], rdflib.Graph]:
    def context() -> rdflib.Graph:
        calls.append(1)
        return rdflib.Graph()

    return context


@pytest.mark.parametrize(
    "body",
    [b":x a :ScoreSnapshott .", b':x :rawValue "1.0" .'],  # an unknown type; a stray write
)
def test_validate_does_not_call_the_context_for_a_batch_the_first_checks_refuse(
    body: bytes,
) -> None:
    calls: list[int] = []
    with pytest.raises(gate.IngestRejected):
        gate.validate(gate.parse_batch(PREFIXES + body), context=_counting_context(calls))
    assert calls == []


def test_validate_calls_the_context_once_for_a_batch_that_passes_the_first_checks() -> None:
    calls: list[int] = []
    gate.validate(
        gate.parse_batch(PREFIXES + b':a a :Asset ; :tickerSymbol "A" ; :cikNumber "1" .'),
        context=_counting_context(calls),
    )
    assert calls == [1]


def test_a_refused_batch_costs_no_context_query(make_db: MakeDB) -> None:
    """The store-free checks run first: an unknown type is refused before any SELECT."""
    fake = make_db()
    batch = (
        PREFIXES + b":c a :AssetCoOccurrence ; :coOccurrenceAsset :A, :B . :x a :ScoreSnapshott .\n"
    )
    with pytest.raises(gate.IngestRejected, match="not leaf classes"):
        gate.ingest(fake.db, batch, "urn:graph:derived:entity-resolution:2026-08-05")
    assert fake.queries == []


def test_fetch_context_refuses_an_iri_that_could_inject_sparql(
    make_db: MakeDB, schema: gate.GateSchema
) -> None:
    with pytest.raises(gate.IngestRejected, match="illegal in an IRI"):
        gate.fetch_context(
            make_db().db, {rdflib.URIRef("https://x.test/a b")}, schema, rdflib.Graph()
        )


@pytest.mark.parametrize("prop", ["validTo", "clearedOn"])
def test_a_closing_date_is_allowed_on_an_untyped_subject(
    prop: str, schema: gate.GateSchema
) -> None:
    batch = gate.parse_batch(
        PREFIXES + f':x :{prop} "2026-01-31"^^<http://www.w3.org/2001/XMLSchema#date> .'.encode()
    )
    assert gate.untyped_writes(batch, schema) == []


def test_a_cleared_on_that_is_not_a_date_is_flagged(schema: gate.GateSchema) -> None:
    batch = gate.parse_batch(PREFIXES + b':x :clearedOn "2026-01-31" .')
    assert "must be an xsd:date literal" in gate.untyped_writes(batch, schema)[0]


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


def test_ingest_checks_a_batch_against_what_the_store_holds_about_its_references(
    make_db: MakeDB,
) -> None:
    """T-146: the co-occurrence batch names Assets typed elsewhere; the store's answer lets it in."""
    name = "urn:graph:derived:entity-resolution:2026-08-05"
    batch = _instance_graphs()[name].serialize(format="turtle").encode()
    rows = [
        {"s": str(s), "p": str(p), "o": str(o)} for s, p, o in _context_for(name)
    ]  # what GraphDB returns: lexical values only
    fake = make_db()

    def select(sparql: str) -> list[dict[str, str]]:
        fake.queries.append(sparql)
        if "SELECT ?s ?p ?o" not in sparql:
            return []
        assert "VALUES ?r {" in sparql  # bounded to the referenced IRIs, never the whole store
        assert "VALUES ?p {" in sparql  # and to the properties the shapes read
        return rows

    fake.select = select  # type: ignore[method-assign]
    assert gate.ingest(fake.db, batch, name) > 0
    assert fake.added[0][2] == name

    empty = make_db()  # the store holds neither Asset: the class check refuses the batch
    with pytest.raises(gate.ShaclRejected):
        gate.ingest(empty.db, batch, name)
    assert empty.added == []


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


# --- a store failure during ingest: in doubt only once the batch was sent (PR #72 round 9) -------


def test_an_answer_lost_after_sending_leaves_the_write_in_doubt(
    make_db: MakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = make_db()

    def lose(*_: object) -> None:
        raise AnswerLost("connection to GraphDB at h lost")

    monkeypatch.setattr(fake, "add", lose)
    with pytest.raises(gate.WriteInDoubt, match="connection to GraphDB at h lost"):
        gate.ingest(fake.db, GOOD, "urn:graph:ingest:SEMANTIC:2026-08-05")


def test_an_http_error_on_sending_is_not_in_doubt(make_db: MakeDB) -> None:
    fake = make_db(fail_on_add=True)
    with pytest.raises(GraphDBError, match="HTTP 500") as raised:
        gate.ingest(fake.db, GOOD, "urn:graph:ingest:SEMANTIC:2026-08-05")
    assert not isinstance(raised.value, gate.WriteInDoubt)


def test_an_answer_lost_before_sending_is_not_in_doubt(
    make_db: MakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gate's own checks only read: losing their answer cannot have written the batch.
    fake = make_db()

    def lose(_sparql: str) -> list[dict[str, str]]:
        raise AnswerLost("connection to GraphDB at h lost")

    monkeypatch.setattr(fake, "select", lose)
    with pytest.raises(AnswerLost) as raised:
        gate.ingest(fake.db, GOOD, "urn:graph:ingest:SEMANTIC:2026-08-05")
    assert not isinstance(raised.value, gate.WriteInDoubt)
    assert fake.added == []
