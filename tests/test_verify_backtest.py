"""``projection.verify_backtest``: the stored graph matches its source (T-280).

The store is an in-memory :class:`rdflib.Dataset` holding the deterministic projection of
``tests/fixtures/backtest_rows.py``; the verifier's SPARQL queries run against it exactly as they
run against GraphDB (the GraphDB-only explicit-statements ``FROM`` is dropped by the adapter).
The source database is the synthetic m018 fixture, not a real one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db, load_catalog, scenario_rows
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF
from rdflib.term import URIRef

from projection import verify_backtest as cli
from projection.backtest import SourceProjection, project_source
from projection.source import FinancialSource
from projection.verify_backtest import (
    Check,
    GraphIdentity,
    Verification,
    graph_identity,
    verify,
)

NS = "https://thesis.local/kg/portfolio#"
KG = rdflib.Namespace(NS)
GRAPH = "urn:graph:derived:backtest:rule:P1:1"

CHECK_NAMES = {
    "graph",
    "triples",
    "individuals StrategyBook",
    "individuals BookRebalance",
    "individuals GuardAlert",
    "individuals GuardAction",
    "individuals BookWeightDaily",
    "individuals BookDailyPerformance",
    "individuals PortfolioPeriodSummary",
    "individuals BacktestTest",
    "holding links",
    "guard links",
    "unlinked v_book_weight_daily",
    "unlinked v_guard_alert",
    "unlinked v_guard_action",
    "GuardAlert by rule, layer and state",
    "GuardAction by status",
    "nGuardActions by decision date",
    "Basing Points publication",
    "last NAV per arm",
    "CASH rows",
    "runLabel through the book",
    "knowledgeDate",
}


def _built(
    tmp_path: Path,
    label: str = "rule",
    window: str = "P1",
    rows: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[Path, SourceProjection]:
    path = backtest_db(tmp_path, window=window, rows=rows)
    source = FinancialSource.open(path)
    try:
        return path, project_source(source, ASSETS, load_catalog(), label)
    finally:
        source.close()


def _dataset(source_projection: SourceProjection) -> rdflib.Dataset:
    dataset = rdflib.Dataset()
    for name, builder in source_projection.projection.graphs.items():
        graph = dataset.graph(URIRef(name))
        for triple in builder.triples:
            graph.add(triple)
    return dataset


def _verification(
    tmp_path: Path,
    label: str = "rule",
    graph: str = GRAPH,
    *,
    dataset: rdflib.Dataset | None = None,
    rows: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[Verification, DatasetStore, Path]:
    path, source_projection = _built(tmp_path, label=label, rows=rows)
    store = DatasetStore(dataset if dataset is not None else _dataset(source_projection))
    result = verify(
        store,
        graph,
        path,
        label,
        assets=ASSETS,
        catalog=load_catalog(),
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


# --- the happy path -----------------------------------------------------------------------------


def test_a_fresh_projection_passes_every_check(tmp_path: Path) -> None:
    result, store, _ = _verification(tmp_path)
    assert result.ok, result.summary()
    assert {check.name for check in result.checks} == CHECK_NAMES
    assert store.queries
    assert all(query.lstrip().startswith("PREFIX") for query in store.queries)
    assert all("SELECT" in query for query in store.queries)
    assert not any("INSERT" in query or "DELETE" in query for query in store.queries)


def test_the_summary_names_the_repository_and_graph(tmp_path: Path) -> None:
    result, _, path = _verification(tmp_path)
    summary = result.summary()
    assert f"repository: test ({result.host})" in summary
    assert f"graph: {GRAPH}" in summary
    assert f"source: {path}" in summary
    assert "PASS  triples:" in summary
    assert "23 checks: 23 passed, 0 failed" in summary


def test_the_checks_report_real_source_rows_and_triples(tmp_path: Path) -> None:
    result, _, _ = _verification(tmp_path)
    details = {check.name: check.detail for check in result.checks}
    assert "3 stored, 3 source rows" in details["individuals StrategyBook"]
    assert "8 stored, 8 source rows" in details["individuals BookWeightDaily"]
    assert "6 stored, 6 source rows" in details["individuals GuardAction"]
    assert "4 stored, 4 source rows" in details["individuals BacktestTest"]
    assert "209,886" not in details["triples"]  # the synthetic fixture is deliberately small


# --- the failure cases the task names -----------------------------------------------------------


def test_a_missing_class_is_reported(tmp_path: Path) -> None:
    path, source_projection = _built(tmp_path)
    dataset = _dataset(source_projection)
    for subject in _subjects(dataset, GRAPH, KG.GuardAction):
        dataset.graph(URIRef(GRAPH)).remove((subject, RDF.type, KG.GuardAction))
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "individuals GuardAction")
    detail = next(c.detail for c in result.checks if c.name == "individuals GuardAction")
    assert "0 stored" in detail


def test_an_altered_individual_count_is_reported(tmp_path: Path) -> None:
    path, source_projection = _built(tmp_path)
    dataset = _dataset(source_projection)
    subject = _subjects(dataset, GRAPH, KG.BookWeightDaily)[0]
    _remove_subject(dataset, GRAPH, subject)
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "individuals BookWeightDaily")
    assert not _check(result, "triples")


def test_a_missing_link_is_reported(tmp_path: Path) -> None:
    path, source_projection = _built(tmp_path)
    dataset = _dataset(source_projection)
    graph = dataset.graph(URIRef(GRAPH))
    subject = next(graph.subjects(KG.holdingAsset, KG["BRK.B"]))
    graph.remove((subject, KG.holdingAsset, KG["BRK.B"]))
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "holding links")
    assert not _check(result, "unlinked v_book_weight_daily")


def test_n_guard_actions_counts_applied_actions_by_decision_date(tmp_path: Path) -> None:
    """Work item 34: the segment counts APPLIED actions by decision_date, not effective_date."""
    result, _, _ = _verification(tmp_path)
    assert _check(result, "nGuardActions by decision date")
    detail = next(c.detail for c in result.checks if c.name == "nGuardActions by decision date")
    assert "2 (book, arm, segment)" in detail


def test_a_wrong_n_guard_actions_value_is_reported(tmp_path: Path) -> None:
    path, source_projection = _built(tmp_path)
    dataset = _dataset(source_projection)
    summary = next(dataset.graph(URIRef(GRAPH)).subjects(RDF.type, KG.PortfolioPeriodSummary))
    graph = dataset.graph(URIRef(GRAPH))
    graph.set((summary, KG.nGuardActions, rdflib.Literal("999", datatype=rdflib.XSD.integer)))
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "nGuardActions by decision date")


def test_a_source_summary_that_disagrees_with_its_actions_is_reported(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["backtest_summary"][0]["n_guard_actions"] = 999
    result, _, _ = _verification(tmp_path, rows=rows)
    assert not result.ok
    assert not _check(result, "nGuardActions by decision date")


def test_a_basing_points_alert_with_a_threshold_in_the_graph_is_reported(tmp_path: Path) -> None:
    """Work item 34: no :alertThreshold may be published for an L1_BP_* alert."""
    rows = scenario_rows()
    rows["guard_alert"].append(
        {
            "id": 6,
            "backtest_run_id": 1,
            "date": "2022-02-13",
            "layer": 1,
            "asset_id": 6,
            "rule_id": "L1_BP_STOP",
            "value": 0.5,
            "threshold": 401.25,
            "state": "ENTER",
        }
    )
    result, _, _ = _verification(tmp_path, rows=rows)
    assert result.ok, result.summary()
    assert _check(result, "Basing Points publication")
    detail = next(c.detail for c in result.checks if c.name == "Basing Points publication")
    assert "3 stored, 3 source L1_BP_* alerts; 0 :alertThreshold" in detail

    path, source_projection = _built(tmp_path, rows=rows)
    dataset = _dataset(source_projection)
    alert = KG.GuardAlert_rule_P1_6
    dataset.graph(URIRef(GRAPH)).add(
        (alert, KG.alertThreshold, rdflib.Literal("401.25", datatype=rdflib.XSD.decimal))
    )
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "Basing Points publication")


def test_the_first_decision_date_without_weight_rows_is_not_a_gap(tmp_path: Path) -> None:
    """Weights appear on the execution date; the decision date itself is legitimately absent."""
    _, source_projection = _built(tmp_path)
    graph = _dataset(source_projection).graph(URIRef(GRAPH))
    days = {str(day) for day in graph.objects(None, KG.weightDate)}
    assert "2022-01-03" not in days  # the first decision date
    assert "2022-01-04" in days  # its execution date
    result, _, _ = _verification(tmp_path)
    assert result.ok, result.summary()
    assert _check(result, "individuals BookWeightDaily")
    assert not any("gap" in check.name.lower() for check in result.checks)


def test_a_wrong_label_is_reported(tmp_path: Path) -> None:
    path, source_projection = _built(tmp_path, label="champ_v1")
    # Put champ_v1's batch under rule's graph name: the store has it, but its :runLabel is wrong.
    champ_graph = next(iter(source_projection.projection.graphs))
    dataset = rdflib.Dataset()
    graph = dataset.graph(URIRef(GRAPH))
    for triple in source_projection.projection.graphs[champ_graph].triples:
        graph.add(triple)
    store = DatasetStore(dataset)
    result = verify(
        store, GRAPH, path, "rule", assets=ASSETS, catalog=load_catalog(), repository="test"
    )
    assert not result.ok
    assert not _check(result, "graph")
    detail = next(c for c in result.checks if c.name == "graph").detail
    assert "champ_v1" in detail
    assert "not [('rule', 'P1', '1')]" in detail


def test_a_wrong_graph_name_is_reported(tmp_path: Path) -> None:
    result, _, _ = _verification(tmp_path, graph="urn:graph:derived:backtest:rule:P2:1")
    assert not result.ok
    assert not _check(result, "graph")
    graph_check = next(check for check in result.checks if check.name == "graph")
    assert "does not exist" in graph_check.detail
    assert "source projects" in graph_check.detail


def test_a_non_backtest_graph_name_fails_before_any_query(tmp_path: Path) -> None:
    path, _ = _built(tmp_path)
    store = DatasetStore(rdflib.Dataset())
    result = verify(store, "urn:graph:tbox", path, "rule", assets=ASSETS, catalog=load_catalog())
    assert not result.ok
    assert [check.name for check in result.checks] == ["graph"]
    assert store.queries == []


def test_graph_identity_parses_the_three_parts() -> None:
    assert graph_identity(GRAPH) == GraphIdentity("rule", "P1", 1)
    assert graph_identity("urn:graph:derived:backtest:champ_v1:P2:42") == GraphIdentity(
        "champ_v1", "P2", 42
    )
    assert graph_identity("urn:graph:derived:backtest:P1:1") is None
    assert graph_identity("urn:graph:tbox") is None


# --- the command line ---------------------------------------------------------------------------


def test_the_cli_prints_the_repository_and_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, store, _ = _verification(tmp_path)
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda _cls: store))
    monkeypatch.setattr(cli, "verify", lambda *_args, **_kwargs: result)
    assert cli.main(["--graph", GRAPH, "--db", str(tmp_path / "x.db"), "--label", "rule"]) == 0
    printed = capsys.readouterr().out
    assert "repository: test" in printed
    assert f"graph: {GRAPH}" in printed
    assert "23 checks: 23 passed, 0 failed" in printed


def test_the_cli_returns_1_when_a_check_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = DatasetStore(rdflib.Dataset())
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda _cls: store))
    monkeypatch.setattr(
        cli,
        "verify",
        lambda *_args, **_kwargs: Verification(
            "test", "", GRAPH, "rule", tmp_path / "x.db", [Check("graph", False, "no")]
        ),
    )
    assert cli.main(["--graph", GRAPH, "--db", str(tmp_path / "x.db"), "--label", "rule"]) == 1
    assert "1 checks: 0 passed, 1 failed" in capsys.readouterr().out


def test_the_cli_refuses_a_malformed_label(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--graph", GRAPH, "--db", "x.db", "--label", "Rule"])
    assert stop.value.code == 2
    assert "run label" in capsys.readouterr().err


def test_every_check_has_a_name_and_a_detail(tmp_path: Path) -> None:
    result, _, _ = _verification(tmp_path)
    assert len(result.checks) == len(CHECK_NAMES)
    assert all(check.name and check.detail for check in result.checks)
