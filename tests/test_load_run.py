"""``projection.load_run``: the pre-flight, the ordered writes and the rollback commands.

The store is the in-memory :class:`fixtures.dataset_store.DatasetStore`: it holds the typed assets
and the real ``schema/rules.ttl`` catalog as context, so ``gate.plan`` runs the real
``fetch_context`` path instead of a fake with canned answers. The source database is the synthetic
m018 fixture, not a real one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, SCHEMA, backtest_db, load_catalog
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF
from rdflib.term import URIRef

from kg_store.graphdb import AnswerLost
from projection import load_run
from projection.backtest import (
    load_selection_catalog,
    project_selection_source,
    project_source,
    validation_context,
)
from projection.source import FinancialSource
from projection.verify_backtest import Check, Verification

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
M018 = "urn:graph:derived:backtest:rule:P1:1"
SELECTION = "urn:graph:derived:backtest:selection:rule:P1:1"


class FailingStore(DatasetStore):
    """A store whose ``add`` loses the answer for one graph (the gate reports it as in doubt)."""

    def __init__(self, dataset: rdflib.Dataset, fail_graph: str) -> None:
        super().__init__(dataset)
        self.fail_graph = fail_graph

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        if graph == self.fail_graph:
            raise AnswerLost("connection lost while awaiting the store's answer")
        super().add(data, content_type, graph)


def _patch_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    return backtest_db(tmp_path)


def _store(*, fail_graph: str | None = None) -> DatasetStore:
    """A store holding the assets and rules the projection links, as the real store would."""
    dataset = rdflib.Dataset(default_union=True)
    context = dataset.graph(URIRef("urn:graph:test:context"))
    for triple in validation_context(ASSETS, load_catalog()):
        context.add(triple)
    if fail_graph is not None:
        return FailingStore(dataset, fail_graph)
    return DatasetStore(dataset)


def _graph(store: DatasetStore, name: str) -> rdflib.Graph:
    return store.dataset.graph(URIRef(name))


def _has_graph(store: DatasetStore, name: str) -> bool:
    return any(str(graph.identifier) == name and len(graph) for graph in store.dataset.graphs())


def _m018_projection(path: Path) -> Any:
    source = FinancialSource.open(path)
    try:
        return project_source(source, ASSETS, load_catalog(), "rule")
    finally:
        source.close()


def _selection_projection(path: Path) -> Any:
    source = FinancialSource.open(path)
    try:
        return project_selection_source(
            source, ASSETS, load_selection_catalog(SCHEMA / "rules.ttl"), "rule"
        )
    finally:
        source.close()


def _preload(store: DatasetStore, graph: str, projection: Any) -> None:
    target = _graph(store, graph)
    for triple in projection.projection.graphs[graph].triples:
        target.add(triple)


def _preload_one_selection_subject(store: DatasetStore, path: Path) -> None:
    projection = _selection_projection(path)
    builder = projection.projection.graphs[SELECTION]
    subject, predicate, value = next(
        (subject, predicate, value)
        for subject, predicate, value in builder.triples
        if predicate == RDF.type and isinstance(subject, URIRef)
    )
    _graph(store, "urn:graph:test:preloaded").add((subject, predicate, value))


def test_a_dry_run_prints_both_graphs_and_a_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    assert load_run.main(["--label", "rule", "--db", str(path)]) == 0
    printed = capsys.readouterr().out
    assert M018 in printed
    assert SELECTION in printed
    assert "not verified (dry run)" in printed
    assert "pre-flight" not in printed


def test_a_directory_is_discovered_by_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    backtest_db(tmp_path, name="rule_P1.db", window="P1")
    backtest_db(tmp_path, name="rule_P2.db", window="P2")
    (tmp_path / "other.db").write_bytes(b"not a database")
    assert load_run.main(["--label", "rule", "--dir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "backtest:rule:P1:1" in printed
    assert "backtest:rule:P2:1" in printed
    assert "other.db" not in printed


def test_a_bad_directory_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert load_run.main(["--label", "rule", "--dir", "/no/such/directory"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_two_databases_naming_the_same_graph_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    first = backtest_db(tmp_path, name="a.db")
    second = backtest_db(tmp_path, name="b.db")
    assert load_run.main(["--label", "rule", "--db", str(first), "--db", str(second)]) == 2
    assert "would both write" in capsys.readouterr().err


def test_all_graphs_are_planned_then_written_and_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store()
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 0
    printed = capsys.readouterr()
    assert f"pre-flight {load_run.WOULD_WRITE}: {M018}" in printed.out
    assert f"pre-flight {load_run.WOULD_WRITE}: {SELECTION}" in printed.out
    assert "PASS" in printed.out
    assert "21/21" in printed.out
    assert "15/15" in printed.out
    assert [graph for graph, _ in store.writes] == [M018, SELECTION]
    assert len(_graph(store, M018)) == len(_m018_projection(path).projection.graphs[M018])
    assert len(_graph(store, SELECTION)) == len(
        _selection_projection(path).projection.graphs[SELECTION]
    )
    assert not printed.err


def test_a_later_graph_refused_writes_no_earlier_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression Work item 31 exists for: a refused selection graph leaves no m018 graph."""
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store()
    _preload_one_selection_subject(store, path)
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 1
    printed = capsys.readouterr()
    assert f"pre-flight {load_run.REFUSED}: {SELECTION}" in printed.out
    assert "already exist in the store" in printed.out
    assert "nothing was written" in printed.err
    assert store.writes == []
    assert not _has_graph(store, M018)
    assert not _has_graph(store, SELECTION)


def test_a_graph_already_in_the_store_is_skipped_while_the_others_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store()
    _preload(store, M018, _m018_projection(path))
    before = len(_graph(store, M018))
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 0
    printed = capsys.readouterr()
    assert f"pre-flight {load_run.ALREADY_IN_STORE}: {M018}" in printed.out
    assert f"pre-flight {load_run.WOULD_WRITE}: {SELECTION}" in printed.out
    assert [graph for graph, _ in store.writes] == [SELECTION]
    assert len(_graph(store, M018)) == before
    assert "21/21" in printed.out
    assert "15/15" in printed.out


def test_check_store_reports_every_graph_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store()
    monkeypatch.setattr(load_run, "_open_check_store", lambda: store)
    assert load_run.main(["--label", "rule", "--db", str(path), "--check-store"]) == 0
    printed = capsys.readouterr()
    assert f"pre-flight {load_run.WOULD_WRITE}: {M018}" in printed.out
    assert f"pre-flight {load_run.WOULD_WRITE}: {SELECTION}" in printed.out
    assert "nothing was written (--check-store)" in printed.err
    assert store.writes == []
    assert not _has_graph(store, M018)
    assert not _has_graph(store, SELECTION)


def test_check_store_rejects_write_and_to_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as info:
        load_run.main(["--label", "rule", "--db", str(path), "--check-store", "--write"])
    assert info.value.code == 2
    assert "--check-store only reads" in capsys.readouterr().err
    with pytest.raises(SystemExit) as info:
        load_run.main(["--label", "rule", "--db", str(path), "--check-store", "--to-production"])
    assert info.value.code == 2
    assert "--check-store never writes" in capsys.readouterr().err


def test_a_verification_failure_stops_the_sequence_and_prints_the_drops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store()
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)

    def fail(graph: str, *_args: Any, **_kwargs: Any) -> Verification:
        return Verification(
            "test", "", graph, "rule", path, [Check("graph", False, "stored graph differs")]
        )

    monkeypatch.setattr(load_run, "_verify_graph", fail)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 1
    printed = capsys.readouterr()
    assert [graph for graph, _ in store.writes] == [M018, SELECTION]
    assert f"DROP GRAPH <{M018}>" in printed.err
    assert f"DROP GRAPH <{SELECTION}>" in printed.err
    assert "0/1" in printed.out
    assert "stored graph differs" in printed.out


def test_a_write_failure_after_the_preflight_prints_the_written_graph_and_drops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    store = _store(fail_graph=SELECTION)
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 1
    printed = capsys.readouterr()
    assert f"Graphs written: {M018}" in printed.err
    assert f"In doubt: {SELECTION}" in printed.err
    assert f"DROP GRAPH <{M018}>" in printed.err
    assert f"DROP GRAPH <{SELECTION}>" not in printed.err
    assert f"{load_run.WRITTEN}" in printed.out
    assert f"{load_run.IN_DOUBT}" in printed.out
    assert _has_graph(store, M018)
    assert not _has_graph(store, SELECTION)


def test_a_plan_error_exits_2_before_any_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = backtest_db(tmp_path)
    monkeypatch.setattr(load_run, "_dry_run", lambda *_args, **_kwargs: pytest.fail("must not run"))
    assert load_run.main(["--label", "rule", "--db", str(path), "--db", str(path)]) == 2
    assert "given twice" in capsys.readouterr().err
