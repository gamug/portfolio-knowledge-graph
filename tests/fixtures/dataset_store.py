"""An in-memory ``rdflib.Dataset`` standing in for GraphDB in tests.

The verifier only reads, but the gate's pre-flight and write path need the same two calls a real
store gets: ``select_terms`` for the context fetch and ``add`` for an accepted plan. This adapter
implements both, so a test can run the real ``gate.plan``/``gate.write`` path instead of a fake
with canned answers.
"""

from __future__ import annotations

import rdflib
from rdflib.query import ResultRow
from rdflib.term import Node, URIRef

from kg_store.graphdb import EXPLICIT_GRAPH


class DatasetStore:
    """A fake GraphDB backed by an in-memory dataset; reads and appends, never updates."""

    def __init__(self, dataset: rdflib.Dataset, repository: str = "test") -> None:
        self.dataset = dataset
        self.repository = repository
        self.host = "http://store.invalid"
        self.queries: list[str] = []
        self.writes: list[tuple[str | None, bytes]] = []

    def select(self, sparql: str) -> list[dict[str, str]]:
        self.queries.append(sparql)
        # GraphDB's explicit-statements virtual graph has no rdflib counterpart; the rest of the
        # query is standard SPARQL and runs unchanged over the fake store's named graphs.
        query = sparql.replace(f"FROM <{EXPLICIT_GRAPH}> ", "")
        result = self.dataset.query(query)
        rows: list[dict[str, str]] = []
        for row in result:
            assert isinstance(row, ResultRow)
            rows.append({str(name): _lexical(row[name]) for name in result.vars or ()})
        return rows

    def select_terms(self, sparql: str) -> list[dict[str, Node]]:
        """Like :meth:`select`, but keep each term's IRI/literal datatype as the store holds it."""
        self.queries.append(sparql)
        query = sparql.replace(f"FROM <{EXPLICIT_GRAPH}> ", "")
        result = self.dataset.query(query)
        rows: list[dict[str, Node]] = []
        for row in result:
            assert isinstance(row, ResultRow)
            rows.append({str(name): _term(row[name]) for name in result.vars or ()})
        return rows

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        """Append RDF to ``graph`` (the gate always names one); ``add`` is never an update."""
        self.writes.append((graph, data))
        parsed = rdflib.Graph()
        fmt = {"application/n-triples": "nt", "text/turtle": "turtle"}.get(content_type)
        if fmt is None:
            raise ValueError(f"unsupported content type {content_type!r}")
        parsed.parse(data=data, format=fmt)
        target = self.dataset.graph(URIRef(graph)) if graph else self.dataset.default_graph
        for triple in parsed:
            target.add(triple)


def _lexical(term: Node | None) -> str:
    return "" if term is None else str(term)


def _term(term: Node | None) -> Node:
    assert term is not None
    return term
