"""``kg_store.graphdb``: every failure of the store reaches its callers as ``GraphDBError``.

Hermetic: ``urlopen`` is replaced, so no socket is opened (constitution Project structure #10).
"""

from __future__ import annotations

import http.client
from typing import Any

import pytest

from kg_store import graphdb
from kg_store.graphdb import GraphDB, GraphDBError


@pytest.mark.parametrize(
    "failure",
    [
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        ConnectionResetError(104, "Connection reset by peer"),
        TimeoutError("timed out"),
        http.client.IncompleteRead(b"partial"),
    ],
    ids=["closed", "reset", "timeout", "incomplete"],
)
def test_a_connection_lost_while_the_answer_is_read_is_a_store_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    # PR #72 review round 7, finding 1: urlopen wraps a failure to send, not one while the answer
    # is read, so these escaped as a raw OSError: a projection did not see a store failure, and
    # its CLI called it a file error.
    def lose(*_: Any, **__: Any) -> None:
        raise failure

    monkeypatch.setattr(graphdb.urllib.request, "urlopen", lose)
    db = GraphDB("http://h", "replay", "", "")
    with pytest.raises(GraphDBError, match=r"connection to GraphDB at http://h lost"):
        db.select("SELECT * WHERE { ?s ?p ?o } LIMIT 1")
    with pytest.raises(GraphDBError, match=type(failure).__name__):
        db.add(b"", "text/turtle", "urn:graph:x")
