"""T-025 acceptance run: the three checks PLAN Work item 3 asks of a running store (plus T-176's two and T-181's one).

1. a basic SPARQL query returns real results;
2. a deliberately malformed write is rejected by the ingest gate and the store is unchanged;
3. the reasoning profile is the one ``07-ontology-topology.md`` documents, shown both from the
   repository configuration and by behaviour (a query on a class two ``rdfs:subClassOf`` steps
   above the asserted types is answered by inference).

T-176 adds two checks and T-181 a third that read the store against ``schema/``:

4. each graph ``schema/`` owns has the asserted size a fresh load gives (a graph the store holds
   that ``schema/`` does not own is reported, not failed);
5. no individual has two ``:agentOrigin`` values or one outside ``ScoreSnapshotShape``'s list;
6. the worked example's quant batch passes the gate beside what the store holds about its
   Portfolios, i.e. a stored string is read in the form the shapes compare (T-181).

Needs the schema loaded (``cli/load_schema.py``), the worked example's Portfolios and Assets
(``instances.trig``, ``reference.ttl``) included. Read-only: the malformed batch is refused
before any write, and the run compares the store's size before and after to prove it.
"""

from __future__ import annotations

from collections.abc import Callable

import rdflib
import rdflib.collection
from rdflib.namespace import SH

from kg_store.gate import (
    IngestRejected,
    ShaclRejected,
    fetch_context,
    ingest,
    load_gate_schema,
    references,
    validate,
)
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB, schema_dir
from kg_store.load_schema import SchemaError, expected_sizes, verify

PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"
#: The one SHACL result the probe must produce: ``(sh:resultPath, sh:sourceConstraintComponent)``.
EXPECTED_VIOLATION = (
    rdflib.URIRef("https://thesis.local/kg/portfolio#timestamp"),
    SH.MinCountConstraintComponent,
)
#: The graph the malformed batch is aimed at; it must still be absent afterwards.
PROBE_GRAPH = "urn:graph:ingest:SEMANTIC:2099-01-01"
#: The worked example's quant batch, whose Portfolios and Assets the store holds once ``schema/`` is loaded.
QUANT_GRAPH = "urn:graph:derived:quant:2026-08-05"
#: A ScoreSnapshot that is valid except for the required ``:timestamp`` it lacks.
MALFORMED = b"""@prefix : <https://thesis.local/kg/portfolio#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:acceptance_probe a :ScoreSnapshot ;
    :agentOrigin "SEMANTIC" ; :metricType "Sentiment" ; :rawValue "-0.5"^^xsd:decimal ;
    :availableAt "2099-01-01"^^xsd:date .
"""


def check_query(db: GraphDB) -> str:
    rows = db.select(PREFIX + "SELECT ?s WHERE { ?s a :Asset } ORDER BY ?s LIMIT 5")
    if not rows:
        raise AssertionError("no :Asset individuals; is schema/ loaded (cli/load_schema.py)?")
    return f"{len(rows)} assets returned, first {rows[0]['s']}"


def violations(
    results: rdflib.Graph,
) -> list[tuple[rdflib.term.Node | None, rdflib.term.Node | None]]:
    """``(sh:resultPath, sh:sourceConstraintComponent)`` of each ``sh:ValidationResult``."""
    return [
        (results.value(r, SH.resultPath), results.value(r, SH.sourceConstraintComponent))
        for r in results.subjects(rdflib.RDF.type, SH.ValidationResult)
    ]


def check_gate(db: GraphDB) -> str:
    before = db.size()
    try:
        ingest(db, MALFORMED, PROBE_GRAPH)
    except ShaclRejected as exc:
        results = exc.results
    except IngestRejected as exc:
        raise AssertionError(f"rejected, but not by SHACL: {str(exc)[:200]}") from exc
    else:
        raise AssertionError("the malformed batch was accepted")
    # "Valid except for :timestamp" means that is the only violation, so a shape change that
    # makes the probe fail for another reason is caught here instead of passing silently.
    found = violations(results)
    if found != [EXPECTED_VIOLATION]:
        raise AssertionError(f"expected :timestamp minCount to be the only violation, got {found}")
    after = db.size()
    if before != after:
        raise AssertionError(f"store size changed {before} -> {after}")
    if db.select(f"SELECT * WHERE {{ GRAPH <{PROBE_GRAPH}> {{ ?s ?p ?o }} }} LIMIT 1"):
        raise AssertionError(f"{PROBE_GRAPH} exists")
    return f"rejected by SHACL (:timestamp minCount); store size unchanged at {after}, {PROBE_GRAPH} absent"


def check_reasoning(db: GraphDB) -> str:
    params = db.repository_params()
    ruleset, same_as = params.get("ruleset"), params.get("disableSameAs")
    if (ruleset, same_as) != ("rdfsplus-optimized", "true"):
        raise AssertionError(f"ruleset={ruleset} disableSameAs={same_as}")
    query = "SELECT (COUNT(DISTINCT ?x) AS ?n) {from_} WHERE {{ ?x a :Observation }}"
    inferred = int(db.select(PREFIX + query.format(from_=""))[0]["n"])
    explicit = int(db.select(PREFIX + query.format(from_=f"FROM <{EXPLICIT_GRAPH}>"))[0]["n"])
    if not (inferred > 0 and explicit == 0):
        raise AssertionError(f"inferred={inferred} explicit={explicit}")
    # PriceObservation is one hop below :Observation; a ScoreSnapshot is two (via
    # :ObservationSnapshot), so a hit proves transitivity, not just single-step entailment.
    if not db.select(PREFIX + "SELECT ?x WHERE { ?x a :ScoreSnapshot, :Observation } LIMIT 1"):
        raise AssertionError("no :ScoreSnapshot is also an :Observation: no transitive inference")
    return (
        f"ruleset {ruleset}, disableSameAs {same_as}; ?x a :Observation = {inferred} inferred, "
        f"{explicit} asserted (a :ScoreSnapshot is an :Observation via two subClassOf steps)"
    )


def check_schema_graphs(db: GraphDB) -> str:
    expected = expected_sizes(schema_dir())
    problems, others = verify(db, expected)
    if problems:
        raise AssertionError("; ".join(problems))
    note = f"; {len(others)} other graph(s) in the store, not owned by schema/" if others else ""
    return f"{len(expected)} schema graphs have the size a fresh load gives{note}"


def allowed_agent_origins() -> list[str]:
    """The ``sh:in`` list of ``ScoreSnapshotShape``'s ``:agentOrigin``, read from ``shapes.ttl``."""
    shapes = load_gate_schema(schema_dir()).shapes
    ns = rdflib.Namespace("https://thesis.local/kg/portfolio#")
    for prop in shapes.objects(ns.ScoreSnapshotShape, SH.property):
        if shapes.value(prop, SH.path) == ns.agentOrigin and (
            members := shapes.value(prop, SH["in"])
        ):
            return sorted(str(m) for m in rdflib.collection.Collection(shapes, members))
    raise AssertionError("ScoreSnapshotShape has no sh:in list for :agentOrigin in shapes.ttl")


def check_agent_origin(db: GraphDB) -> str:
    allowed = allowed_agent_origins()
    in_list = ", ".join(rdflib.Literal(v).n3() for v in allowed)
    rows = db.select(
        PREFIX
        + 'SELECT ?s (COUNT(DISTINCT ?o) AS ?n) (GROUP_CONCAT(DISTINCT STR(?o); separator="|") AS ?vals) '
        + f"FROM <{EXPLICIT_GRAPH}> WHERE {{ ?s :agentOrigin ?o }} GROUP BY ?s "
        + f"HAVING (COUNT(DISTINCT ?o) > 1 || SUM(IF(?o IN ({in_list}), 0, 1)) > 0)"
    )
    if rows:
        shown = "; ".join(f"{r['s']} has {r['vals']}" for r in rows[:5])
        raise AssertionError(f"{len(rows)} individual(s) with a bad :agentOrigin: {shown}")
    return f"every :agentOrigin is single and one of {', '.join(allowed)}"


def check_quant_batch(db: GraphDB) -> str:
    """The worked example's quant batch passes the gate beside what the store holds (T-181).

    Its shapes compare a stored ``:portfolioKind`` by term (``sh:in ("LIVE" "BENCHMARK")``,
    ``sh:hasValue "BENCHMARK"``), and a plain literal is not equal to one typed ``xsd:string``,
    so this fails if the store writes a string in a form ``GraphDB.select_terms`` does not read
    as the gate expects. Read-only: the batch is read from ``schema/`` and only validated.

    Like the schema-graphs check, it takes the store to be a fresh ``schema/`` load, the worked
    example included: a store that holds none of the individuals the batch points at fails with
    that message (load ``schema/``), not with a gate rejection.
    """
    schema = load_gate_schema(schema_dir())
    dataset = rdflib.Dataset(default_union=False)
    try:
        dataset.parse(schema_dir() / "instances.trig", format="trig")
    except OSError as exc:
        raise SchemaError(f"cannot read instances.trig: {exc}") from exc
    except Exception as exc:  # rdflib raises a different parser error per syntax, as in load_schema
        raise SchemaError(f"cannot parse instances.trig: {exc}") from exc
    batch = rdflib.Graph()
    for triple in dataset.graph(rdflib.URIRef(QUANT_GRAPH)):
        batch.add(triple)
    refs = references(batch, schema)
    if not refs:  # an empty batch would pass vacuously
        raise AssertionError(
            f"instances.trig has no batch {QUANT_GRAPH} that points at individuals"
        )
    context = fetch_context(db, refs, schema, batch)
    held = set(context.subjects()) & refs  # the memberships the Asset hop adds are not counted
    if not held:
        raise AssertionError(
            "the store holds none of the individuals the quant batch points at: "
            "load schema/ first (cli/load_schema.py)"
        )
    try:
        validate(batch, context=context)
    except IngestRejected as exc:
        raise AssertionError(
            f"the quant batch of instances.trig fails beside the store: {exc}"
        ) from exc
    return f"the quant batch passes beside the {len(held)} stored individual(s) it points at"


CHECKS: list[tuple[str, Callable[[GraphDB], str]]] = [
    ("SPARQL query returns real results", check_query),
    ("malformed write rejected by the gate", check_gate),
    ("reasoning profile matches 07", check_reasoning),
    ("schema graphs have their expected size", check_schema_graphs),
    ("every :agentOrigin is single and in the shape's list", check_agent_origin),
    ("the quant batch passes beside the stored Portfolios", check_quant_batch),
]
