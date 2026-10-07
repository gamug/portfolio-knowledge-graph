"""T-025 acceptance run: the three checks PLAN Work item 3 asks of a running store.

1. a basic SPARQL query returns real results;
2. a deliberately malformed write is rejected by the ingest gate and the store is unchanged;
3. the reasoning profile is the one ``07-ontology-topology.md`` documents, shown both from the
   repository configuration and by behaviour (a query on a class two ``rdfs:subClassOf`` steps
   above the asserted types is answered by inference).

Needs the schema loaded (``cli/load_schema.py``). Read-only: the malformed batch is refused
before any write, and the run compares the store's size before and after to prove it.
"""

from __future__ import annotations

from collections.abc import Callable

import rdflib
from rdflib.namespace import SH

from kg_store.gate import IngestRejected, ShaclRejected, ingest
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB

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
    found = [
        (results.value(r, SH.resultPath), results.value(r, SH.sourceConstraintComponent))
        for r in results.subjects(rdflib.RDF.type, SH.ValidationResult)
    ]
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


CHECKS: list[tuple[str, Callable[[GraphDB], str]]] = [
    ("SPARQL query returns real results", check_query),
    ("malformed write rejected by the gate", check_gate),
    ("reasoning profile matches 07", check_reasoning),
]
