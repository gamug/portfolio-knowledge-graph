"""Shared fixtures for the hermetic suite (constitution Project structure #10).

Shared fixtures only: ``src/`` reaches the import path through ``pyproject.toml``'s
``[tool.pytest.ini_options] pythonpath``, never through ``sys.path`` edits here.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator


class FakeGraphDB:
    """Records what ``kg_store`` sends; stands in for ``GraphDB`` without a store.

    ``rows`` is returned by every ``select``; ``sizes`` by ``explicit_graph_sizes``.
    """

    def __init__(
        self, rows: list[dict[str, str]] | None = None, sizes: dict[str, int] | None = None
    ) -> None:
        self.rows = rows or []
        self.sizes = sizes or {}
        self.queries: list[str] = []
        self.added: list[tuple[bytes, str, str | None]] = []
        self.updates: list[str] = []
        self.rolled_back = False

    def select(self, sparql: str) -> list[dict[str, str]]:
        self.queries.append(sparql)
        return self.rows

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
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
