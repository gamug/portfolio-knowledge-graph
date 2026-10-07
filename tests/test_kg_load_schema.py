"""``kg_store.load_schema``: expected sizes, load order, verification and ``main`` (T-136)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import rdflib
from conftest import FakeGraphDB

from kg_store import load_schema
from kg_store.graphdb import GraphDB, GraphDBError

SCHEMA = Path(__file__).resolve().parent.parent / "schema"


def _db(fake: FakeGraphDB) -> GraphDB:
    return cast(GraphDB, fake)


def _copy_schema(tmp_path: Path) -> Path:
    for name, _ in load_schema.LOAD_PLAN:
        (tmp_path / name).write_bytes((SCHEMA / name).read_bytes())
    return tmp_path


def test_expected_sizes_cover_every_graph_the_files_name() -> None:
    sizes = load_schema.expected_sizes(SCHEMA)
    assert {"urn:graph:tbox", "urn:graph:reference", "urn:graph:rules:catalog"} <= set(sizes)
    assert "urn:graph:portfolio:current" in sizes
    assert all(n > 0 for n in sizes.values())


def test_tbox_and_shapes_share_one_graph() -> None:
    sizes = load_schema.expected_sizes(SCHEMA)
    parts = sum(
        len(rdflib.Graph().parse(SCHEMA / f, format="turtle")) for f in ("tbox.ttl", "shapes.ttl")
    )
    # Triples in both files are stored once, so the shared graph is at most the sum.
    assert 0 < sizes["urn:graph:tbox"] <= parts


def test_expected_sizes_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(load_schema.SchemaError, match="cannot read"):
        load_schema.expected_sizes(tmp_path)


def test_expected_sizes_refuses_unparsable_turtle(tmp_path: Path) -> None:
    directory = _copy_schema(tmp_path)
    (directory / "rules.ttl").write_text(":a :b")
    with pytest.raises(load_schema.SchemaError, match=r"cannot parse rules\.ttl"):
        load_schema.expected_sizes(directory)


def test_expected_sizes_refuses_triples_outside_a_graph_block(tmp_path: Path) -> None:
    directory = _copy_schema(tmp_path)
    trig = directory / "instances.trig"
    trig.write_text(
        "@prefix : <https://thesis.local/kg/portfolio#> .\n"
        ":a :b :c .\nGRAPH <urn:graph:x> { :d :e :f . }\n"
    )
    with pytest.raises(load_schema.SchemaError, match="outside a GRAPH block"):
        load_schema.expected_sizes(directory)


def test_load_drops_then_uploads_in_load_order(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeGraphDB()
    expected = load_schema.load(_db(fake), SCHEMA)
    assert expected == load_schema.expected_sizes(SCHEMA)
    assert fake.updates == [f"DROP SILENT GRAPH <{g}>" for g in expected]
    assert [(ct, graph) for _, ct, graph in fake.added] == [
        ("text/turtle", "urn:graph:tbox"),
        ("text/turtle", "urn:graph:tbox"),
        ("text/turtle", "urn:graph:reference"),
        ("text/turtle", "urn:graph:rules:catalog"),
        ("application/x-trig", None),
    ]
    assert [d for d, _, _ in fake.added][-1] == (SCHEMA / "instances.trig").read_bytes()
    assert capsys.readouterr().out.splitlines()[0] == "loaded tbox.ttl -> urn:graph:tbox"


def test_load_rolls_back_when_an_upload_fails() -> None:
    class Failing(FakeGraphDB):
        def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
            raise GraphDBError("HTTP 500")

    fake = Failing()
    with pytest.raises(GraphDBError):
        load_schema.load(_db(fake), SCHEMA)
    assert fake.rolled_back


def test_load_touches_nothing_when_the_files_are_bad(tmp_path: Path) -> None:
    fake = FakeGraphDB()
    with pytest.raises(load_schema.SchemaError):
        load_schema.load(_db(fake), tmp_path)
    assert fake.updates == [] and fake.added == []


def test_verify_passes_when_sizes_match_and_lists_other_graphs() -> None:
    expected = {"urn:graph:tbox": 10, "urn:graph:reference": 5}
    fake = FakeGraphDB(sizes={**expected, "urn:graph:ingest:SEMANTIC:2026-08-05": 3})
    problems, others = load_schema.verify(_db(fake), expected)
    assert problems == []
    assert others == ["urn:graph:ingest:SEMANTIC:2026-08-05"]


def test_verify_reports_a_size_mismatch_and_a_missing_graph() -> None:
    expected = {"urn:graph:tbox": 10, "urn:graph:reference": 5}
    fake = FakeGraphDB(sizes={"urn:graph:tbox": 9})
    problems, others = load_schema.verify(_db(fake), expected)
    assert problems == [
        "urn:graph:tbox: expected 10, store has 9",
        "urn:graph:reference: expected 5, store has 0",
    ]
    assert others == []


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeGraphDB:
    """``main`` against a fake store that reports exactly what a correct load produces."""
    fake = FakeGraphDB(sizes=load_schema.expected_sizes(SCHEMA))
    monkeypatch.setattr(GraphDB, "from_env", classmethod(lambda cls: fake))
    return fake


def test_main_returns_0_on_a_verified_load(
    store: FakeGraphDB, capsys: pytest.CaptureFixture[str]
) -> None:
    assert load_schema.main(["--dir", str(SCHEMA)]) == 0
    assert "verified:" in capsys.readouterr().out


def test_main_notes_other_graphs_without_failing(
    store: FakeGraphDB, capsys: pytest.CaptureFixture[str]
) -> None:
    store.sizes = {**store.sizes, "urn:graph:ingest:SEMANTIC:2099-01-01": 3}
    assert load_schema.main(["--dir", str(SCHEMA)]) == 0
    assert "1 other graph(s)" in capsys.readouterr().out


def test_main_returns_1_on_a_size_mismatch(
    store: FakeGraphDB, capsys: pytest.CaptureFixture[str]
) -> None:
    store.sizes = {**store.sizes, "urn:graph:tbox": 1}
    assert load_schema.main(["--dir", str(SCHEMA)]) == 1
    assert "verification FAILED" in capsys.readouterr().err


def test_main_returns_1_when_the_store_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(load_schema, "GraphDB", GraphDB)
    monkeypatch.setattr(GraphDB, "from_env", classmethod(_unconfigured))
    assert load_schema.main(["--dir", str(SCHEMA)]) == 1
    assert "error: set KG_HOST" in capsys.readouterr().err


def test_main_returns_1_on_a_bad_schema_directory(
    store: FakeGraphDB, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert load_schema.main(["--dir", str(tmp_path)]) == 1
    assert "cannot read" in capsys.readouterr().err


def _unconfigured(cls: type[GraphDB]) -> GraphDB:
    raise GraphDBError("set KG_HOST, KG_REPOSITORY (see .env.example)")
