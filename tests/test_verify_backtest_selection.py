"""``projection.verify_backtest`` over a selection graph (Work item 29).

The store is an in-memory :class:`rdflib.Dataset` holding both the m018 and the selection
deterministic projections of ``tests/fixtures/backtest_rows.py``; the verifier's SPARQL runs
against it exactly as it runs against GraphDB. The source database is the synthetic fixture, not
a real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, SCHEMA, backtest_db, load_catalog
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF
from rdflib.term import URIRef

from projection import verify_backtest as cli
from projection.backtest import (
    SelectionRuleCatalog,
    SelectionSourceProjection,
    SourceProjection,
    load_selection_catalog,
    project_selection_source,
    project_source,
)
from projection.source import FinancialSource
from projection.verify_backtest import (
    Check,
    GraphIdentity,
    Verification,
    selection_graph_identity,
    verify,
    verify_selection,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
M018 = "urn:graph:derived:backtest:rule:P1:1"
SELECTION = "urn:graph:derived:backtest:selection:rule:P1:1"

CHECK_NAMES = {
    "graph",
    "triples",
    "individuals SelectionCycle",
    "individuals AttractivenessSnapshot",
    "individuals AttractivenessWeightScheme",
    "individuals Veto",
    "effective WeightComponent",
    "configured WeightComponent",
    "UNSCORED/UNPRICED placeholders",
    "attractiveness links",
    "veto links",
    "unlinked v_cycle_ranking",
    "unlinked v_veto",
    "vetoes by resolved rule",
    "cross-graph SelectionCycle",
}


def _catalog() -> SelectionRuleCatalog:
    return load_selection_catalog(SCHEMA / "rules.ttl")


def _built(
    tmp_path: Path, label: str = "rule"
) -> tuple[Path, SourceProjection, SelectionSourceProjection]:
    path = backtest_db(tmp_path)
    source = FinancialSource.open(path)
    try:
        backtest = project_source(source, ASSETS, load_catalog(), label)
        selection = project_selection_source(source, ASSETS, _catalog(), label)
    finally:
        source.close()
    return path, backtest, selection


def _dataset(
    backtest: SourceProjection, selection: SourceProjection | SelectionSourceProjection
) -> rdflib.Dataset:
    dataset = rdflib.Dataset()
    for projection in (backtest, selection):
        for name, builder in projection.projection.graphs.items():
            graph = dataset.graph(URIRef(name))
            for triple in builder.triples:
                graph.add(triple)
    return dataset


def _verification(
    tmp_path: Path,
    label: str = "rule",
    graph: str = SELECTION,
    *,
    dataset: rdflib.Dataset | None = None,
) -> tuple[Verification, DatasetStore, Path]:
    path, backtest, selection = _built(tmp_path, label=label)
    store = DatasetStore(dataset if dataset is not None else _dataset(backtest, selection))
    result = verify(
        store,
        graph,
        path,
        label,
        assets=ASSETS,
        selection_catalog=_catalog(),
        repository=store.repository,
        host=store.host,
    )
    return result, store, path


def _check(result: Verification, name: str) -> bool:
    matches = [check for check in result.checks if check.name == name]
    assert len(matches) == 1, name
    return matches[0].passed


def _remove_subject(dataset: rdflib.Dataset, graph_name: str, subject: URIRef) -> None:
    graph = dataset.graph(URIRef(graph_name))
    for triple in list(graph.triples((subject, None, None))):
        graph.remove(triple)


def _subjects(dataset: rdflib.Dataset, graph_name: str, rdf_type: URIRef) -> list[URIRef]:
    graph = dataset.graph(URIRef(graph_name))
    return [
        subject for subject in graph.subjects(RDF.type, rdf_type) if isinstance(subject, URIRef)
    ]


def test_a_fresh_selection_projection_passes_every_check(tmp_path: Path) -> None:
    result, store, _ = _verification(tmp_path)
    assert result.ok, result.summary()
    assert {check.name for check in result.checks} == CHECK_NAMES
    assert store.queries
    assert all("SELECT" in query for query in store.queries)
    assert not any("INSERT" in query or "DELETE" in query for query in store.queries)


def test_the_summary_names_the_repository_graph_and_selection_checks(tmp_path: Path) -> None:
    result, _, path = _verification(tmp_path)
    summary = result.summary()
    assert "repository: test (http://store.invalid)" in summary
    assert f"graph: {SELECTION}" in summary
    assert f"source: {path}" in summary
    assert "PASS  individuals SelectionCycle:" in summary
    assert "15 checks: 15 passed, 0 failed" in summary


def test_selection_check_details_name_the_source_rows(tmp_path: Path) -> None:
    result, _, _ = _verification(tmp_path)
    details = {check.name: check.detail for check in result.checks}
    assert "7 stored, 7 expected" in details["individuals SelectionCycle"]
    assert "5 stored, 5 expected" in details["individuals AttractivenessSnapshot"]
    assert "21 stored, 21 expected" in details["configured WeightComponent"]
    assert "12 stored, 12 expected" in details["effective WeightComponent"]
    assert "1 stored, 1 expected" in details["UNSCORED/UNPRICED placeholders"]
    assert "4 stored, 4 expected" in details["attractiveness links"]
    assert "2 stored, 2 expected" in details["veto links"]
    assert "1 stored, 1 reported by the projector" in details["unlinked v_cycle_ranking"]
    assert "1 stored, 1 reported by the projector" in details["unlinked v_veto"]


def test_a_missing_selection_class_is_reported(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path)
    dataset = _dataset(backtest, selection)
    for subject in _subjects(dataset, SELECTION, KG.SelectionCycle):
        dataset.graph(URIRef(SELECTION)).remove((subject, RDF.type, KG.SelectionCycle))
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "individuals SelectionCycle")
    detail = next(c.detail for c in result.checks if c.name == "individuals SelectionCycle")
    assert "0 stored" in detail


def test_an_altered_selection_count_is_reported(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path)
    dataset = _dataset(backtest, selection)
    subject = _subjects(dataset, SELECTION, KG.AttractivenessSnapshot)[0]
    _remove_subject(dataset, SELECTION, subject)
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "individuals AttractivenessSnapshot")
    assert not _check(result, "triples")


def test_a_missing_selection_link_is_reported(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path)
    dataset = _dataset(backtest, selection)
    graph = dataset.graph(URIRef(SELECTION))
    subject = next(graph.subjects(KG.attractivenessOfAsset, KG.AAA))
    graph.remove((subject, KG.attractivenessOfAsset, KG.AAA))
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "attractiveness links")
    assert not _check(result, "unlinked v_cycle_ranking")


def test_a_missing_placeholder_marker_is_reported(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path)
    dataset = _dataset(backtest, selection)
    graph = dataset.graph(URIRef(SELECTION))
    placeholders = [
        subject
        for subject in _subjects(dataset, SELECTION, KG.AttractivenessSnapshot)
        if not list(graph.objects(subject, KG.hasEffectiveWeight))
    ]
    assert len(placeholders) == 1
    graph.remove((placeholders[0], KG.vetoRulesJson, None))
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "UNSCORED/UNPRICED placeholders")


def test_a_wrong_selection_label_is_reported(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path, label="champ_v1")
    dataset = rdflib.Dataset()
    for projection in (backtest, selection):
        for name, builder in projection.projection.graphs.items():
            target = SELECTION if name.startswith("urn:graph:derived:backtest:selection:") else M018
            graph = dataset.graph(URIRef(target))
            for triple in builder.triples:
                graph.add(triple)
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "graph")
    detail = next(c for c in result.checks if c.name == "graph").detail
    assert "champ_v1" in detail
    assert "not [('rule', 'P1', '1')]" in detail


def test_a_wrong_selection_graph_name_is_reported(tmp_path: Path) -> None:
    result, _, _ = _verification(tmp_path, graph="urn:graph:derived:backtest:selection:rule:P2:1")
    assert not result.ok
    assert not _check(result, "graph")
    graph_check = next(check for check in result.checks if check.name == "graph")
    assert "does not exist" in graph_check.detail
    assert "source projects" in graph_check.detail


def test_a_malformed_selection_graph_name_fails_before_any_query(tmp_path: Path) -> None:
    path = backtest_db(tmp_path)
    store = DatasetStore(rdflib.Dataset())
    result = verify_selection(store, "urn:graph:derived:backtest:selection:rule:P1", path, "rule")
    assert not result.ok
    assert [check.name for check in result.checks] == ["graph"]
    assert store.queries == []


def test_a_missing_selection_cycle_breaks_the_cross_graph_check(tmp_path: Path) -> None:
    path, backtest, selection = _built(tmp_path)
    dataset = _dataset(backtest, selection)
    graph = dataset.graph(URIRef(SELECTION))
    cycle = next(
        subject
        for subject in _subjects(dataset, SELECTION, KG.SelectionCycle)
        if (subject, KG.cycleRunId, rdflib.Literal("7", datatype=rdflib.XSD.integer)) in graph
    )
    graph.remove((cycle, KG.cycleRunId, None))
    result = verify(
        DatasetStore(dataset),
        SELECTION,
        path,
        "rule",
        assets=ASSETS,
        selection_catalog=_catalog(),
    )
    assert not result.ok
    assert not _check(result, "cross-graph SelectionCycle")
    detail = next(c.detail for c in result.checks if c.name == "cross-graph SelectionCycle")
    assert "missing SelectionCycle for cycle 7" in detail


def test_selection_graph_identity_parses_the_three_parts() -> None:
    assert selection_graph_identity(SELECTION) == GraphIdentity("rule", "P1", 1)
    assert selection_graph_identity("urn:graph:derived:backtest:selection:champ_v1:P2:42") == (
        GraphIdentity("champ_v1", "P2", 42)
    )
    assert selection_graph_identity(M018) is None
    assert selection_graph_identity("urn:graph:tbox") is None


# --- the command line ---------------------------------------------------------------------------


def test_the_cli_prints_the_selection_repository_and_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, store, _ = _verification(tmp_path)
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda _cls: store))
    monkeypatch.setattr(cli, "verify", lambda *_args, **_kwargs: result)
    assert cli.main(["--graph", SELECTION, "--db", str(tmp_path / "x.db"), "--label", "rule"]) == 0
    printed = capsys.readouterr().out
    assert "repository: test" in printed
    assert f"graph: {SELECTION}" in printed
    assert "15 checks: 15 passed, 0 failed" in printed


def test_the_cli_returns_1_when_a_selection_check_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = DatasetStore(rdflib.Dataset())
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda _cls: store))
    monkeypatch.setattr(
        cli,
        "verify",
        lambda *_args, **_kwargs: Verification(
            "test", "", SELECTION, "rule", tmp_path / "x.db", [Check("graph", False, "no")]
        ),
    )
    assert cli.main(["--graph", SELECTION, "--db", str(tmp_path / "x.db"), "--label", "rule"]) == 1
    assert "1 checks: 0 passed, 1 failed" in capsys.readouterr().out
