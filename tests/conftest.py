"""Shared fixtures for the hermetic suite (constitution Project structure #10).

Shared fixtures only: ``src/`` reaches the import path through ``pyproject.toml``'s
``[tool.pytest.ini_options] pythonpath``, never through ``sys.path`` edits here.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
import rdflib
from rdflib.term import Node

from kg_store.gate import load_gate_schema, references
from kg_store.graphdb import GraphDB, GraphDBError

SCHEMA = Path(__file__).resolve().parent.parent / "schema"


def instance_graphs() -> dict[str, rdflib.Graph]:
    """``schema/instances.trig``'s named graphs, by name (the worked example)."""
    ds = rdflib.Dataset(default_union=False)
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return {str(g.identifier): g for g in ds.graphs() if len(g)}


def context_for(name: str) -> rdflib.Graph:
    """What the rest of the worked example says about the individuals graph ``name`` points at,
    as the store would hold it once the other graphs are loaded (T-146)."""
    graphs = instance_graphs()
    refs = references(graphs[name], load_gate_schema(SCHEMA.resolve()))
    # The Assets are typed in reference.ttl; the other graphs hold the Portfolios.
    others = {k: g for k, g in graphs.items() if k != name}
    others["urn:graph:reference"] = rdflib.Graph().parse(SCHEMA / "reference.ttl", format="turtle")
    context = rdflib.Graph()
    for graph in others.values():
        for ref in refs:
            for p, o in graph.predicate_objects(ref):
                context.add((ref, p, o))
    return context


class FakeGraphDB:
    """Records what ``kg_store`` sends; stands in for ``GraphDB`` without a store.

    ``rows`` is returned by every ``select``, ``terms`` by every ``select_terms``; ``sizes`` by
    ``explicit_graph_sizes``.
    """

    def __init__(
        self,
        rows: list[dict[str, str]] | None = None,
        terms: list[dict[str, Node]] | None = None,
        sizes: dict[str, int] | None = None,
        fail_on_add: bool = False,
    ) -> None:
        self.rows = rows or []
        self.terms = terms or []
        self.sizes = sizes or {}
        self.fail_on_add = fail_on_add
        self.queries: list[str] = []
        self.added: list[tuple[bytes, str, str | None]] = []
        self.updates: list[str] = []
        self.rolled_back = False

    def select(self, sparql: str) -> list[dict[str, str]]:
        self.queries.append(sparql)
        return self.rows

    def select_terms(self, sparql: str) -> list[dict[str, Node]]:
        self.queries.append(sparql)
        return self.terms

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        if self.fail_on_add:
            raise GraphDBError("HTTP 500")
        self.added.append((data, content_type, graph))

    def update(self, sparql: str) -> None:
        self.updates.append(sparql)

    def explicit_graph_sizes(self) -> dict[str, int]:
        return self.sizes

    @contextlib.contextmanager
    def transaction(self) -> Iterator[FakeGraphDB]:
        try:
            yield self
        except BaseException:
            self.rolled_back = True
            raise

    @property
    def db(self) -> GraphDB:
        """This fake typed as the ``GraphDB`` the code under test expects."""
        return cast(GraphDB, self)


@pytest.fixture
def make_db() -> Callable[..., FakeGraphDB]:
    """Factory for a :class:`FakeGraphDB`: ``make_db(rows=..., terms=..., ...)``."""
    return FakeGraphDB
