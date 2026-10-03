"""T-025 acceptance run: the three checks PLAN Work item 3 asks of a running store.

1. a basic SPARQL query returns real results;
2. a deliberately malformed write is rejected by the ingest gate and the store is unchanged;
3. the reasoning profile is the one ``07-ontology-topology.md`` documents, shown both from the
   repository configuration and by behaviour (a subclass query is answered by inference).

Needs the schema loaded (``cli/load_schema.py``). Read-only: the malformed batch is refused
before any write, and the run compares the store's size before and after to prove it.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from kg_store.gate import IngestRejected, ingest
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB

PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"
#: The graph the malformed batch is aimed at; it must still be absent afterwards.
PROBE_GRAPH = "urn:graph:ingest:SEMANTIC:2099-01-01"
#: A ScoreSnapshot without ``:timestamp`` and with a score outside [0, 1].
MALFORMED = b"""@prefix : <https://thesis.local/kg/portfolio#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:acceptance_probe a :ScoreSnapshot ;
    :agentOrigin "SEMANTIC" ; :metricType "Sentiment" ; :normalizedScore "7.5"^^xsd:decimal .
"""


def _size(db: GraphDB) -> int:
    return int(db._request("GET", f"{db._repo_url}/size").decode().strip())


def check_query(db: GraphDB) -> str:
    rows = db.select(PREFIX + "SELECT ?s WHERE { ?s a :Asset } ORDER BY ?s LIMIT 5")
    if not rows:
        raise AssertionError("no :Asset individuals; is schema/ loaded (cli/load_schema.py)?")
    return f"{len(rows)} assets returned, first {rows[0]['s']}"


def check_gate(db: GraphDB) -> str:
    before = _size(db)
    try:
        ingest(db, MALFORMED, PROBE_GRAPH)
    except IngestRejected as exc:
        reason = str(exc).splitlines()[0]
    else:
        raise AssertionError("the malformed batch was accepted")
    after = _size(db)
    if before != after:
        raise AssertionError(f"store size changed {before} -> {after}")
    if db.select(f"SELECT * WHERE {{ GRAPH <{PROBE_GRAPH}> {{ ?s ?p ?o }} }} LIMIT 1"):
        raise AssertionError(f"{PROBE_GRAPH} exists")
    return f"rejected ({reason}); store size unchanged at {after}, {PROBE_GRAPH} absent"


def check_reasoning(db: GraphDB) -> str:
    raw = db._request(
        "GET", f"{db.host}/rest/repositories/{db.repository}", accept="application/json"
    )
    params = json.loads(raw)["params"]
    ruleset, same_as = params["ruleset"]["value"], params["disableSameAs"]["value"]
    if (ruleset, same_as) != ("rdfsplus-optimized", "true"):
        raise AssertionError(f"ruleset={ruleset} disableSameAs={same_as}")
    query = "SELECT (COUNT(DISTINCT ?x) AS ?n) {from_} WHERE {{ ?x a :ObservationSnapshot }}"
    inferred = int(db.select(PREFIX + query.format(from_=""))[0]["n"])
    explicit = int(db.select(PREFIX + query.format(from_=f"FROM <{EXPLICIT_GRAPH}>"))[0]["n"])
    if not (inferred > 0 and explicit == 0):
        raise AssertionError(f"inferred={inferred} explicit={explicit}")
    return (
        f"ruleset {ruleset}, disableSameAs {same_as}; ?x a :ObservationSnapshot = {inferred} "
        f"inferred, {explicit} asserted (no individual is typed with that superclass)"
    )


CHECKS: list[tuple[str, Callable[[GraphDB], str]]] = [
    ("SPARQL query returns real results", check_query),
    ("malformed write rejected by the gate", check_gate),
    ("reasoning profile matches 07", check_reasoning),
]
