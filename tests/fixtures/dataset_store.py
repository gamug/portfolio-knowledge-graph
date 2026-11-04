"""An in-memory ``rdflib.Dataset`` standing in for GraphDB's read-only verifier queries."""

from __future__ import annotations

import rdflib
from rdflib.query import ResultRow
from rdflib.term import Node

from kg_store.graphdb import EXPLICIT_GRAPH


class DatasetStore:
    """A fake GraphDB backed by an in-memory dataset; ``select`` only, as the verifier promises."""

    def __init__(self, dataset: rdflib.Dataset, repository: str = "test") -> None:
        self.dataset = dataset
        self.repository = repository
        self.host = "http://store.invalid"
        self.queries: list[str] = []

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


def _lexical(term: Node | None) -> str:
    return "" if term is None else str(term)
