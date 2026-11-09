"""``kg_store.load_schema``: expected sizes, load order, verification and ``main`` (T-136)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import rdflib

from kg_store import load_schema
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError

if TYPE_CHECKING:
    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]

SCHEMA = Path(__file__).resolve().parent.parent / "schema"


def _copy_schema(tmp_path: Path) -> Path:
    for name, _ in load_schema.LOAD_PLAN:
        (tmp_path / name).write_bytes((SCHEMA / name).read_bytes())
    return tmp_path


def test_expected_sizes_cover_every_graph_the_files_name() -> None:
    sizes = load_schema.expected_sizes(SCHEMA)
    assert {
        "urn:graph:tbox",
        "urn:graph:reference",
        "urn:graph:reference:fibo",
        "urn:graph:rules:catalog",
    } <= set(sizes)
    assert "urn:graph:portfolio:current" in sizes
    assert all(n > 0 for n in sizes.values())


def test_tbox_and_shapes_share_one_graph() -> None:
    union = rdflib.Graph()
    for name in ("tbox.ttl", "shapes.ttl"):
        union.parse(SCHEMA / name, format="turtle")
    assert load_schema.expected_sizes(SCHEMA)["urn:graph:tbox"] == len(union)


def test_the_load_plan_has_20_graphs_and_5192_asserted_triples() -> None:
    sizes = load_schema.expected_sizes(SCHEMA)
    assert len(sizes) == 20
    # 4513 at the T-212 reload; +2 for T-220's and T-227's sh:class triples, -34 for T-233/T-234
    # (two RDF lists removed, the run label added), +227 for Work item 26's selection terms/shapes,
    # +185 for Work item 33's final-backtest vocabulary (BP rules, ETF, metadata classes/shapes),
    # +279 for Work item 37's aggregates classes, properties and shapes, +2 for Work item 38's
    # bootstrap_mdd test name.
    assert sum(sizes.values()) == 5192
    assert sizes["urn:graph:reference:fibo"] == 277


def test_the_schema_only_plan_has_four_graphs_and_4671_triples() -> None:
    """Work item 39: production loads only the files, never the worked-example ABox."""
    sizes = load_schema.expected_sizes(SCHEMA, include_examples=False)
    assert len(sizes) == 4
    assert sum(sizes.values()) == 4671
    assert set(sizes) == {
        "urn:graph:tbox",
        "urn:graph:reference",
        "urn:graph:reference:fibo",
        "urn:graph:rules:catalog",
    }


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


def test_load_drops_then_uploads_in_load_order(
    make_db: MakeDB, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_db()
    expected = load_schema.load(fake.db, SCHEMA)
    assert expected == load_schema.expected_sizes(SCHEMA)
    assert fake.updates == [f"DROP SILENT GRAPH <{g}>" for g in expected]
    assert [(ct, graph) for _, ct, graph in fake.added] == [
        ("text/turtle", "urn:graph:tbox"),
        ("text/turtle", "urn:graph:tbox"),
        ("text/turtle", "urn:graph:reference"),
        ("text/turtle", "urn:graph:reference:fibo"),
        ("text/turtle", "urn:graph:rules:catalog"),
        ("application/x-trig", None),
    ]
    assert [d for d, _, _ in fake.added][-1] == (SCHEMA / "instances.trig").read_bytes()
    assert capsys.readouterr().out.splitlines()[0] == "loaded tbox.ttl -> urn:graph:tbox"


def test_load_without_examples_never_sends_instances_trig(make_db: MakeDB) -> None:
    """Work item 39: production never receives the worked-example content."""
    fake = make_db()
    expected = load_schema.load(fake.db, SCHEMA, include_examples=False)
    assert expected == load_schema.expected_sizes(SCHEMA, include_examples=False)
    assert fake.updates == [f"DROP SILENT GRAPH <{g}>" for g in expected]
    assert all(data != (SCHEMA / "instances.trig").read_bytes() for data, _, _ in fake.added)
    assert all(content_type == "text/turtle" for _, content_type, _ in fake.added)
    assert [str(graph) for _, _, graph in fake.added] == [
        "urn:graph:tbox",
        "urn:graph:tbox",
        "urn:graph:reference",
        "urn:graph:reference:fibo",
        "urn:graph:rules:catalog",
    ]


def test_load_rolls_back_when_an_upload_fails(make_db: MakeDB) -> None:
    fake = make_db(fail_on_add=True)
    with pytest.raises(GraphDBError):
        load_schema.load(fake.db, SCHEMA)
    assert fake.rolled_back


def test_load_touches_nothing_when_the_files_are_bad(tmp_path: Path, make_db: MakeDB) -> None:
    fake = make_db()
    with pytest.raises(load_schema.SchemaError):
        load_schema.load(fake.db, tmp_path)
    assert fake.updates == [] and fake.added == []


def test_verify_passes_when_sizes_match_and_lists_other_graphs(make_db: MakeDB) -> None:
    expected = {"urn:graph:tbox": 10, "urn:graph:reference": 5}
    fake = make_db(sizes={**expected, "urn:graph:ingest:SEMANTIC:2026-08-05": 3})
    problems, others = load_schema.verify(fake.db, expected)
    assert problems == []
    assert others == ["urn:graph:ingest:SEMANTIC:2026-08-05"]


def test_verify_reports_a_size_mismatch_and_a_missing_graph(make_db: MakeDB) -> None:
    expected = {"urn:graph:tbox": 10, "urn:graph:reference": 5}
    fake = make_db(sizes={"urn:graph:tbox": 9})
    problems, others = load_schema.verify(fake.db, expected)
    assert problems == [
        "urn:graph:tbox: expected 10, store has 9",
        "urn:graph:reference: expected 5, store has 0",
    ]
    assert others == []


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, make_db: MakeDB) -> FakeGraphDB:
    """``main`` against a fake store that reports exactly what a correct load produces."""
    fake = make_db(sizes=load_schema.expected_sizes(SCHEMA))
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


def test_main_refuses_production_without_the_flag_before_writing(
    make_db: MakeDB, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_db(sizes=load_schema.expected_sizes(SCHEMA, include_examples=False))
    fake.repository = PRODUCTION_REPOSITORY
    monkeypatch.setattr(GraphDB, "from_env", classmethod(lambda cls: fake))
    assert load_schema.main(["--dir", str(SCHEMA)]) == 2
    assert "--to-production" in capsys.readouterr().err
    assert fake.updates == [] and fake.added == []


def test_main_loads_only_the_schema_files_in_production_with_the_flag(
    make_db: MakeDB, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_db(sizes=load_schema.expected_sizes(SCHEMA, include_examples=False))
    fake.repository = PRODUCTION_REPOSITORY
    monkeypatch.setattr(GraphDB, "from_env", classmethod(lambda cls: fake))
    assert load_schema.main(["--dir", str(SCHEMA), "--to-production"]) == 0
    assert "examples: instances.trig not loaded in the production repository" in (
        capsys.readouterr().out
    )
    assert all(data != (SCHEMA / "instances.trig").read_bytes() for data, _, _ in fake.added)


def test_main_keeps_the_examples_outside_production(
    make_db: MakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = make_db(sizes=load_schema.expected_sizes(SCHEMA))
    fake.repository = "portfolio_test"
    monkeypatch.setattr(GraphDB, "from_env", classmethod(lambda cls: fake))
    assert load_schema.main(["--dir", str(SCHEMA)]) == 0
    assert fake.added[-1] == (
        (SCHEMA / "instances.trig").read_bytes(),
        "application/x-trig",
        None,
    )


def _unconfigured(cls: type[GraphDB]) -> GraphDB:
    raise GraphDBError("set KG_HOST, KG_REPOSITORY (see .env.example)")
