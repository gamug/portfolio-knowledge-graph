"""``kg_store.graphdb``: every failure of the store reaches its callers as ``GraphDBError``, and
one whose answer was lost after sending as its ``AnswerLost`` kind.

Hermetic: ``urlopen`` is replaced, so no socket is opened (constitution Project structure #10).
"""

from __future__ import annotations

import http.client
import io
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from rdflib import XSD, BNode, Literal, URIRef

from kg_store import graphdb
from kg_store.graphdb import AnswerLost, GraphDB, GraphDBError


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
    with pytest.raises(AnswerLost, match=r"connection to GraphDB at http://h lost"):
        db.select("SELECT * WHERE { ?s ?p ?o } LIMIT 1")
    with pytest.raises(AnswerLost, match=type(failure).__name__):
        db.add(b"", "text/turtle", "urn:graph:x")


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError("http://h", 400, "Bad Request", Message(), io.BytesIO(b"MALFORMED")),
        urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")),
    ],
    ids=["http-error", "not-sent"],
)
def test_an_answer_or_a_failure_to_send_is_not_an_answer_lost(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    # PR #72 review round 9, finding 1: an HTTP error is the store's answer, and urlopen raises
    # URLError only when the request could not be sent; neither may have written anything.
    def fail(*_: Any, **__: Any) -> None:
        raise failure

    monkeypatch.setattr(graphdb.urllib.request, "urlopen", fail)
    db = GraphDB("http://h", "replay", "", "")
    with pytest.raises(GraphDBError) as raised:
        db.add(b"", "text/turtle", "urn:graph:x")
    assert not isinstance(raised.value, AnswerLost)


def test_the_password_is_not_in_the_repr() -> None:
    # A failing test prints its fixtures, so a repr with the password would put it in the log.
    assert "s3cret" not in repr(GraphDB("http://h", "r", "u", "s3cret"))


def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str = "") -> None:
    """Point the helper at a temporary ``.env`` and start from no target variables."""
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.setattr(graphdb, "REPO_ROOT", tmp_path)
    for name in graphdb.TARGET_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_announce_target_prints_only_host_and_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Work item 39: target first, production named, never the credentials."""
    _isolated_env(monkeypatch, tmp_path)
    db = GraphDB("http://h:7200", "portfolio", "user", "s3cret")
    graphdb.announce_target(db)
    out = capsys.readouterr().out
    assert out.splitlines() == ["target: GraphDB http://h:7200 repository portfolio [PRODUCTION]"]
    assert "user" not in out and "s3cret" not in out


def test_environment_override_warns_only_for_a_different_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolated_env(
        monkeypatch,
        tmp_path,
        "KG_HOST=http://env.example\nKG_REPOSITORY=portfolio_test\n",
    )
    monkeypatch.setenv("KG_HOST", "http://env.example")
    monkeypatch.setenv("KG_REPOSITORY", "portfolio")
    monkeypatch.setenv("KG_USER", "user")
    monkeypatch.setenv("KG_PASSWORD", "s3cret")
    db = GraphDB.from_env()
    graphdb.announce_target(db)
    out = capsys.readouterr().out
    assert out.splitlines()[0] == (
        "target: GraphDB http://env.example repository portfolio [PRODUCTION]"
    )
    assert "warning: KG_REPOSITORY='portfolio'" in out
    assert "portfolio_test" in out
    assert "warning: KG_HOST" not in out
    assert "user" not in out and "s3cret" not in out
    assert db.repository == "portfolio"


def test_environment_override_stays_quiet_when_the_values_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolated_env(
        monkeypatch,
        tmp_path,
        "KG_HOST=http://env.example\nKG_REPOSITORY=portfolio_test\n",
    )
    monkeypatch.setenv("KG_HOST", "http://env.example")
    monkeypatch.setenv("KG_REPOSITORY", "portfolio_test")
    graphdb.announce_target(GraphDB.from_env())
    out = capsys.readouterr().out
    assert "warning:" not in out
    assert out.splitlines()[0].endswith("[not production]")


def _answering(
    monkeypatch: pytest.MonkeyPatch, bindings: list[dict[str, dict[str, str]]]
) -> GraphDB:
    answer = json.dumps({"results": {"bindings": bindings}}).encode()
    db = GraphDB("http://h", "replay", "", "")
    monkeypatch.setattr(GraphDB, "_request", lambda *_, **__: answer)
    return db


def test_select_terms_keeps_the_kind_of_each_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-181: ``select`` returns lexical values only; ``select_terms`` keeps IRI, blank node,
    datatype and language, which a shape reads."""
    xsd = "http://www.w3.org/2001/XMLSchema#"
    db = _answering(
        monkeypatch,
        [
            {
                "a": {"type": "uri", "value": "https://x.test/a"},
                "b": {"type": "bnode", "value": "b0"},
                "c": {"type": "literal", "value": "7", "datatype": xsd + "integer"},
                "d": {"type": "literal", "value": "hola", "xml:lang": "es"},
                "e": {"type": "literal", "value": "plain"},
                "f": {"type": "literal", "value": "typed", "datatype": xsd + "string"},
            }
        ],
    )
    [row] = db.select_terms("SELECT * WHERE { ?a ?b ?c }")
    assert row["a"] == URIRef("https://x.test/a")
    assert row["b"] == BNode("b0")
    assert row["c"] == Literal("7", datatype=XSD.integer)
    assert row["d"] == Literal("hola", lang="es")
    assert row["e"] == Literal("plain")
    # a string is the plain literal whether or not the store writes xsd:string (the shapes'
    # sh:in and sh:hasValue compare terms, and Literal("x") != Literal("x", datatype=XSD.string))
    assert row["f"] == Literal("typed")
    assert row["f"].datatype is None  # type: ignore[attr-defined]
    assert db.select("SELECT * WHERE { ?a ?b ?c }") == [
        {
            "a": "https://x.test/a",
            "b": "b0",
            "c": "7",
            "d": "hola",
            "e": "plain",
            "f": "typed",
        }
    ]


@pytest.mark.parametrize(
    "binding",
    [
        {"type": "mystery", "value": "x"},
        {"value": "x"},
        {"type": "literal"},
        {"type": "literal", "value": "x", "datatype": 5},
    ],
    ids=["unknown-type", "no-type", "no-value", "datatype-not-a-string"],
)
def test_select_terms_refuses_a_binding_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, binding: dict[str, str]
) -> None:
    db = _answering(monkeypatch, [{"a": binding}])
    with pytest.raises(GraphDBError, match="unexpected SPARQL result"):
        db.select_terms("SELECT * WHERE { ?a ?b ?c }")
