"""T-176: ``acceptance.check_schema_graphs`` and ``check_agent_origin`` against a fake store.

The fake runs the check's own SPARQL on an in-memory dataset, so a doubled or out-of-list
``:agentOrigin`` is found by the real query, not by a canned answer.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import cast

import pytest
import rdflib

from kg_store import acceptance
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB, schema_dir
from kg_store.load_schema import expected_sizes

ORIGIN = rdflib.URIRef("https://thesis.local/kg/portfolio#agentOrigin")


class FakeStore:
    def __init__(self, sizes: dict[str, int], origins: list[tuple[str, str]] | None = None):
        self.sizes = sizes
        self.data = rdflib.Dataset()
        explicit = self.data.graph(rdflib.URIRef(EXPLICIT_GRAPH))
        # rdflib tries to fetch a FROM graph it does not hold, so the graph must exist.
        explicit.add((rdflib.URIRef("urn:x:unrelated"), rdflib.RDF.type, rdflib.OWL.Thing))
        for subject, value in origins or []:
            explicit.add((rdflib.URIRef(f"urn:x:{subject}"), ORIGIN, rdflib.Literal(value)))

    def explicit_graph_sizes(self) -> dict[str, int]:
        return dict(self.sizes)

    def select(self, query: str) -> list[dict[str, str]]:
        result = self.data.query(query)
        names = [str(v) for v in result.vars or []]
        return [
            {n: str(v) for n, v in zip(names, cast(tuple, row), strict=True) if v is not None}
            for row in result
        ]


def _db(store: FakeStore) -> GraphDB:
    return cast(GraphDB, store)


def _healthy() -> dict[str, int]:
    return dict(expected_sizes(schema_dir()))


def test_equal_sizes_pass() -> None:
    assert "have the size a fresh load gives" in acceptance.check_schema_graphs(
        _db(FakeStore(_healthy()))
    )


def test_a_short_graph_fails() -> None:
    sizes = _healthy()
    sizes["urn:graph:tbox"] -= 1
    with pytest.raises(AssertionError, match="urn:graph:tbox: expected"):
        acceptance.check_schema_graphs(_db(FakeStore(sizes)))


def test_a_missing_graph_fails() -> None:
    sizes = _healthy()
    del sizes["urn:graph:reference"]
    with pytest.raises(AssertionError, match="urn:graph:reference"):
        acceptance.check_schema_graphs(_db(FakeStore(sizes)))


def test_an_extra_graph_is_reported_and_passes() -> None:
    sizes = _healthy()
    sizes["urn:graph:ingest:QUANTITATIVE:2026-08-05"] = 35
    message = acceptance.check_schema_graphs(_db(FakeStore(sizes)))
    assert "1 other graph(s)" in message


def test_the_allowed_origins_come_from_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit a copy of the shape: the check follows it, so the list is read, not copied."""
    for name in ("tbox.ttl", "shapes.ttl"):
        text = (schema_dir() / name).read_text()
        if name == "shapes.ttl":
            assert '"TECHNICAL" "SECTOR")' in text
            text = text.replace('"TECHNICAL" "SECTOR")', '"TECHNICAL" "SECTOR" "EXTRA")', 1)
        (tmp_path / name).write_text(text)
    monkeypatch.setenv("KG_SCHEMA_DIR", str(tmp_path))
    assert "EXTRA" in acceptance.allowed_agent_origins()
    assert "FUNDAMENTAL" in acceptance.allowed_agent_origins()


def test_the_real_shape_lists_the_five_agents() -> None:
    assert set(acceptance.allowed_agent_origins()) >= {"SEMANTIC", "SECTOR"}


def test_single_listed_origins_pass() -> None:
    store = FakeStore(_healthy(), [("a", "SEMANTIC"), ("b", "TECHNICAL")])
    assert "single" in acceptance.check_agent_origin(_db(store))


def test_no_origins_pass() -> None:
    assert "single" in acceptance.check_agent_origin(_db(FakeStore(_healthy())))


def test_a_doubled_origin_fails() -> None:
    store = FakeStore(_healthy(), [("a", "SEMANTIC"), ("a", "QUANTITATIVE"), ("b", "SECTOR")])
    with pytest.raises(AssertionError, match=r"1 individual\(s\).*urn:x:a"):
        acceptance.check_agent_origin(_db(store))


def test_an_origin_outside_the_list_fails() -> None:
    store = FakeStore(_healthy(), [("a", "QUANTITATIVE")])
    with pytest.raises(AssertionError, match="QUANTITATIVE"):
        acceptance.check_agent_origin(_db(store))


def test_the_checks_are_registered_after_the_original_three() -> None:
    names = [name for name, _ in acceptance.CHECKS]
    assert names[:3] == [
        "SPARQL query returns real results",
        "malformed write rejected by the gate",
        "reasoning profile matches 07",
    ]
    assert len(names) == 5


def test_an_unreadable_schema_is_a_fail_line_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = importlib.util.spec_from_file_location(
        "verify_store_cli", Path(__file__).resolve().parent.parent / "cli" / "verify_store.py"
    )
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda c: FakeStore({})))
    monkeypatch.setattr(cli, "CHECKS", [("schema graphs", acceptance.check_schema_graphs)])
    monkeypatch.setenv("KG_SCHEMA_DIR", str(tmp_path / "missing"))
    assert cli.main() == 1
    assert "FAIL  schema graphs" in capsys.readouterr().out
