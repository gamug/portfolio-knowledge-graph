"""``kg_store.graphdb``: every failure of the store reaches its callers as ``GraphDBError``."""

from __future__ import annotations

from typing import Any

import pytest

from kg_store import graphdb
from kg_store.graphdb import GraphDB, GraphDBError


def test_a_connection_closed_before_the_answer_is_a_store_error(hangs_up: str) -> None:
    # PR #72 review round 7, finding 1: it escaped as a raw OSError (RemoteDisconnected), so a
    # projection did not see a store failure and the CLI called it a file error.
    with pytest.raises(GraphDBError, match=r"connection to GraphDB at .* lost"):
        GraphDB(hangs_up, "replay", "", "").select("SELECT * WHERE { ?s ?p ?o } LIMIT 1")


def test_a_read_timeout_is_a_store_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def time_out(*_: Any, **__: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(graphdb.urllib.request, "urlopen", time_out)
    with pytest.raises(GraphDBError, match="TimeoutError"):
        GraphDB("http://h", "replay", "", "").add(b"", "text/turtle", "urn:graph:x")
