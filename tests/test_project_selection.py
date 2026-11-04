"""``projection.project_selection``: arguments, labels, the production guard and exit status."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from fixtures.backtest_rows import ASSETS, backtest_db

from kg_store.graphdb import GraphDB, GraphDBError
from projection import project_backtest
from projection import project_selection as cli
from projection.backtest import ProjectionError, RunResult, StoreInterrupted
from projection.boundary import BoundaryError, BoundaryReport


def _result(**fields: Any) -> RunResult:
    return RunResult(BoundaryReport(), Counter(), Counter(), **fields)


def _patch_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "universe_assets", lambda _path: ASSETS)


def test_a_database_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args([])
    assert stop.value.code == 2
    assert "--db" in capsys.readouterr().err


def test_a_database_without_a_label_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", str(backtest_db(tmp_path))])
    assert stop.value.code == 2
    assert "expected LABEL=PATH" in capsys.readouterr().err


@pytest.mark.parametrize("label", ["Rule", "r", "rule-1", "rule v2", "_rule", "r" * 33])
def test_a_malformed_label_is_refused(
    label: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", f"{label}={backtest_db(tmp_path)}"])
    assert stop.value.code == 2
    assert "run label" in capsys.readouterr().err


def test_to_production_needs_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", f"rule={tmp_path / 'x.db'}", "--to-production"])
    assert stop.value.code == 2
    assert "--to-production only matters with --write" in capsys.readouterr().err


def test_a_repeated_database_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = backtest_db(tmp_path)
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", f"rule={path}", "--db", f"champ={path}"])
    assert stop.value.code == 2
    assert "given twice" in capsys.readouterr().err


def test_a_dry_run_checks_the_selection_graph_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    args = cli.parse_args(["--db", f"rule={backtest_db(tmp_path)}"])
    results = cli.project(args)
    assert len(results) == 1
    _, result = results[0]
    assert result.checked == ["urn:graph:derived:backtest:selection:rule:P1:1"]
    assert result.written == {}
    assert result.store_consulted is False


def test_two_databases_make_two_window_qualified_graphs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    first = backtest_db(tmp_path, name="p1.db", window="P1")
    second = backtest_db(tmp_path, name="p2.db", window="P2")
    results = cli.project(cli.parse_args(["--db", f"rule={first}", "--db", f"rule={second}"]))
    assert [result.checked for _, result in results] == [
        ["urn:graph:derived:backtest:selection:rule:P1:1"],
        ["urn:graph:derived:backtest:selection:rule:P2:1"],
    ]


def test_two_databases_that_would_name_the_same_graph_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    first = backtest_db(tmp_path, name="a.db")
    second = backtest_db(tmp_path, name="b.db")
    with pytest.raises(SystemExit) as stop:
        cli.project(cli.parse_args(["--db", f"rule={first}", "--db", f"rule={second}"]))
    assert stop.value.code == 2
    assert "would both write" in capsys.readouterr().err


def test_a_production_write_needs_the_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(
        project_backtest.GraphDB,
        "from_env",
        classmethod(lambda _c: GraphDB("http://h", "portfolio", "", "")),
    )
    monkeypatch.setattr(cli, "run_selection", lambda *_a, **_k: pytest.fail("must not read"))
    with pytest.raises(SystemExit) as stop:
        cli.project(cli.parse_args(["--db", f"rule={backtest_db(tmp_path)}", "--write"]))
    assert stop.value.code == 2
    assert "a backtest is a frozen artifact" in capsys.readouterr().err


def test_a_production_write_with_the_opt_in_is_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(
        project_backtest.GraphDB,
        "from_env",
        classmethod(lambda _c: GraphDB("http://h", "portfolio", "", "")),
    )
    monkeypatch.setattr(cli, "run_selection", lambda *_a, **_k: _result(written={"g": 1}))
    assert cli.main(["--db", f"rule={backtest_db(tmp_path)}", "--write", "--to-production"]) == 0


def test_a_boundary_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise BoundaryError(BoundaryReport(stopped=True, stop_reasons=["no"]))

    monkeypatch.setattr(cli, "run_selection", fail)
    assert cli.main(["--db", f"rule={backtest_db(tmp_path)}"]) == 1
    assert "STOPPED" in capsys.readouterr().err


def test_a_projection_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_selection",
        lambda *_a, **_k: (_ for _ in ()).throw(ProjectionError("bad")),
    )
    assert cli.main(["--db", f"rule={backtest_db(tmp_path)}"]) == 1
    assert "STOPPED" in capsys.readouterr().err


def test_a_rejected_graph_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(cli, "run_selection", lambda *_a, **_k: _result(rejected={"g": "no"}))
    assert cli.main(["--db", f"rule={backtest_db(tmp_path)}"]) == 1
    assert "rejected: g: no" in capsys.readouterr().out


def test_a_store_failure_partway_reports_what_was_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    partial = _result(written={"g": 7})

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise StoreInterrupted(partial, GraphDBError("HTTP 503"))

    monkeypatch.setattr(cli, "run_selection", fail)
    assert cli.main(["--db", f"rule={backtest_db(tmp_path)}"]) == 1
    printed = capsys.readouterr()
    assert "written: g: 7 triples" in printed.out
    assert "stopped partway: HTTP 503" in printed.err


def test_a_missing_database_exits_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert cli.main(["--db", f"rule={tmp_path / 'no.db'}"]) == 1
    assert "source error:" in capsys.readouterr().err
