"""T-176: ``acceptance.check_schema_graphs`` and ``check_agent_origin`` against a fake store.

The fake runs the check's own SPARQL on an in-memory dataset, so a doubled or out-of-list
``:agentOrigin`` is found by the real query, not by a canned answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import rdflib
from support import load_cli

from kg_store import acceptance
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB, schema_dir
from kg_store.load_schema import expected_sizes

ORIGIN = rdflib.URIRef("https://thesis.local/kg/portfolio#agentOrigin")


class FakeStore:
    def __init__(
        self,
        sizes: dict[str, int],
        origins: list[tuple[str, str]] | None = None,
        repository: str = "test",
    ):
        self.sizes = sizes
        self.repository = repository
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


class ReasoningStore:
    """A production schema-only store: no ABox observation, but the TBox chain is inferred."""

    repository = acceptance.PRODUCTION_REPOSITORY

    def __init__(self, subclass_inferred: bool = True) -> None:
        self.subclass_inferred = subclass_inferred

    def repository_params(self) -> dict[str, str]:
        return {"ruleset": "rdfsplus-optimized", "disableSameAs": "true"}

    def select(self, query: str) -> list[dict[str, str]]:
        if "COUNT(DISTINCT ?x)" in query:
            return [{"n": "0"}]
        if "?x a :ScoreSnapshot }" in query:
            return []
        if "rdfs:subClassOf :Observation" in query:
            return (
                [{"x": str(rdflib.URIRef("https://thesis.local/kg/portfolio#ScoreSnapshot"))}]
                if (self.subclass_inferred)
                else []
            )
        return []


def test_reasoning_passes_on_the_tbox_when_production_has_no_abox_yet() -> None:
    """Work item 39: the same two-step chain is proved without an example ScoreSnapshot."""
    message = acceptance.check_reasoning(cast(GraphDB, ReasoningStore()))
    assert "no ABox observation yet" in message
    assert "two subClassOf steps" in message


def test_reasoning_fails_when_the_tbox_chain_is_not_inferred() -> None:
    with pytest.raises(AssertionError, match="no transitive inference"):
        acceptance.check_reasoning(cast(GraphDB, ReasoningStore(subclass_inferred=False)))


def test_equal_sizes_pass() -> None:
    assert "have the size a fresh load gives" in acceptance.check_schema_graphs(
        _db(FakeStore(_healthy()))
    )


def test_production_expected_sizes_exclude_the_worked_example() -> None:
    """Work item 39: production's fresh load has only the five schema graphs."""
    sizes = dict(expected_sizes(schema_dir(), include_examples=False))
    message = acceptance.check_schema_graphs(
        _db(FakeStore(sizes, repository=acceptance.PRODUCTION_REPOSITORY))
    )
    assert "5 schema graphs" in message


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
    assert len(names) == 6
    assert names[-1] == "a stored vocabulary string is read as the shapes compare"


def test_an_unreadable_schema_is_a_fail_line_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = load_cli("verify_store")
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda c: FakeStore({})))
    monkeypatch.setattr(cli, "CHECKS", [("schema graphs", acceptance.check_schema_graphs)])
    monkeypatch.setenv("KG_SCHEMA_DIR", str(tmp_path / "missing"))
    assert cli.main([]) == 1
    assert "FAIL  schema graphs" in capsys.readouterr().out


@pytest.mark.parametrize("broken", ["instances.trig", "shapes.ttl"])
def test_an_unparsable_schema_file_is_a_fail_line_for_the_quant_batch_check(
    broken: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The quant-batch check reads the schema itself; a parse error is a FAIL line."""
    for name in ("tbox.ttl", "shapes.ttl", "instances.trig"):
        (tmp_path / name).write_bytes((schema_dir() / name).read_bytes())
    (tmp_path / broken).write_text("this is { not rdf")
    cli = load_cli("verify_store")
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda c: FakeStore({})))
    monkeypatch.setattr(cli, "CHECKS", [("quant batch", acceptance.check_quant_batch)])
    monkeypatch.setenv("KG_SCHEMA_DIR", str(tmp_path))
    assert cli.main([]) == 1
    assert "FAIL  quant batch: cannot parse the schema files" in capsys.readouterr().out
