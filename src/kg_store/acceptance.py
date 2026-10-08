"""T-025 acceptance run: the three checks PLAN Work item 3 asks of a running store (plus T-176's two).

1. a basic SPARQL query returns real results;
2. a deliberately malformed write is rejected by the ingest gate and the store is unchanged;
3. the reasoning profile is the one ``07-ontology-topology.md`` documents, shown both from the
   repository configuration and by behaviour (a query on a class two ``rdfs:subClassOf`` steps
   above the asserted types is answered by inference).

T-176 adds two checks that read the store against ``schema/``:

4. each graph ``schema/`` owns has the asserted size a fresh load gives (a graph the store holds
   that ``schema/`` does not own is reported, not failed);
5. no individual has two ``:agentOrigin`` values or one outside ``ScoreSnapshotShape``'s list.

Needs the schema loaded (``cli/load_schema.py``). Read-only: the malformed batch is refused
before any write, and the run compares the store's size before and after to prove it.
"""

from __future__ import annotations

from collections.abc import Callable

import rdflib
import rdflib.collection
from rdflib.namespace import SH

from kg_store.gate import IngestRejected, ShaclRejected, ingest, load_gate_schema
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB, schema_dir
from kg_store.load_schema import expected_sizes, verify

PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"
#: The one SHACL result the probe must produce: ``(sh:resultPath, sh:sourceConstraintComponent)``.
EXPECTED_VIOLATION = (
    rdflib.URIRef("https://thesis.local/kg/portfolio#timestamp"),
    SH.MinCountConstraintComponent,
)
#: The graph the malformed batch is aimed at; it must still be absent afterwards.
PROBE_GRAPH = "urn:graph:ingest:SEMANTIC:2099-01-01"
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


CHECKS: list[tuple[str, Callable[[GraphDB], str]]] = [
    ("SPARQL query returns real results", check_query),
    ("malformed write rejected by the gate", check_gate),
    ("reasoning profile matches 07", check_reasoning),
    ("schema graphs have their expected size", check_schema_graphs),
    ("every :agentOrigin is single and in the shape's list", check_agent_origin),
]
