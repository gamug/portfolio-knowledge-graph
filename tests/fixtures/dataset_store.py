"""An in-memory ``rdflib.Dataset`` standing in for GraphDB in tests.

The verifier only reads, but the gate's pre-flight and write path need the same two calls a real
store gets: ``select_terms`` for the context fetch and ``add`` for an accepted plan. This adapter
implements both, so a test can run the real ``gate.plan``/``gate.write`` path instead of a fake
with canned answers.
"""

from __future__ import annotations

import re

import rdflib
from rdflib.query import ResultRow
from rdflib.term import Node, URIRef

from kg_store.graphdb import EXPLICIT_GRAPH, GraphDBError

_DROP = re.compile(r"DROP SILENT GRAPH <([^>]+)>", re.IGNORECASE)
_CREATE = re.compile(r"CREATE SILENT GRAPH <([^>]+)>", re.IGNORECASE)
_MOVE = re.compile(r"MOVE <([^>]+)> TO <([^>]+)>", re.IGNORECASE)


class DatasetStore:
    """A fake GraphDB backed by an in-memory dataset; reads and appends, never updates."""

    def __init__(
        self, dataset: rdflib.Dataset, repository: str = "test", fail_on_move: bool = False
    ) -> None:
        self.dataset = dataset
        self.repository = repository
        self.host = "http://store.invalid"
        self.fail_on_move = fail_on_move
        self.queries: list[str] = []
        self.writes: list[tuple[str | None, bytes]] = []
        self.updates: list[str] = []

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

    def update(self, sparql: str) -> None:
        """Apply the exact DROP/CREATE/MOVE statements the live loader emits.

        The real store runs the whole request in one transaction; the fake applies the statements
        in order, which is enough for the loader's replace tests.
        """
        self.updates.append(sparql)
        if self.fail_on_move and "MOVE" in sparql.upper():
            raise GraphDBError("simulated swap failure")
        for statement in (part.strip() for part in sparql.split(";")):
            if not statement:
                continue
            drop = _DROP.fullmatch(statement)
            if drop:
                self._graph(drop.group(1)).remove((None, None, None))
                continue
            create = _CREATE.fullmatch(statement)
            if create:
                self._graph(create.group(1))
                continue
            move = _MOVE.fullmatch(statement)
            if move:
                source = self._graph(move.group(1))
                target = self._graph(move.group(2))
                triples = list(source)
                target.remove((None, None, None))
                source.remove((None, None, None))
                for triple in triples:
                    target.add(triple)
                continue
            raise ValueError(f"unsupported update statement: {statement!r}")

    def _graph(self, name: str) -> rdflib.Graph:
        return self.dataset.graph(URIRef(name))

    def repository_params(self) -> dict[str, str]:
        return {}

    def explicit_graph_sizes(self) -> dict[str, int]:
        return {str(graph.identifier): len(graph) for graph in self.dataset.graphs() if len(graph)}


def _lexical(term: Node | None) -> str:
    return "" if term is None else str(term)


def _term(term: Node | None) -> Node:
    assert term is not None
    return term
