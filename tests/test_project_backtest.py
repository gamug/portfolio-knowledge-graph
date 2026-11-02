"""``projection.project_backtest``: arguments, the production guard and exit status (T-207).

The work itself is tested in ``test_backtest.py``; this file exercises the command policy with a
fake store, as ``test_project_scores.py`` does. The ``cli/project_backtest.py`` entry point is run
as a subprocess in ``test_cli_project_backtest.py``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from fixtures.backtest_rows import ASSETS, backtest_db

from kg_store.graphdb import GraphDBError
from projection import project_backtest as cli
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


def test_to_production_needs_write(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", "x.db", "--to-production"])
    assert stop.value.code == 2
    assert "--to-production only matters with --write" in capsys.readouterr().err


def test_a_repeated_database_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.parse_args(["--db", "x.db", "--db", "x.db"])
    assert stop.value.code == 2
    assert "given twice" in capsys.readouterr().err


def test_a_dry_run_checks_the_graph_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    args = cli.parse_args(["--db", str(backtest_db(tmp_path))])
    results = cli.project(args)
    assert len(results) == 1
    _, result = results[0]
    assert result.checked == ["urn:graph:derived:backtest:P1:1"]
    assert result.written == {}
    assert result.store_consulted is False


def test_two_databases_make_two_window_qualified_graphs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    first = backtest_db(tmp_path, name="p1.db", window="P1")
    second = backtest_db(tmp_path, name="p2.db", window="P2")
    results = cli.project(cli.parse_args(["--db", str(first), "--db", str(second)]))
    assert [result.checked for _, result in results] == [
        ["urn:graph:derived:backtest:P1:1"],
        ["urn:graph:derived:backtest:P2:1"],
    ]


def test_two_databases_that_would_name_the_same_graph_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    first = backtest_db(tmp_path, name="a.db")
    second = backtest_db(tmp_path, name="b.db")
    with pytest.raises(SystemExit) as stop:
        cli.project(cli.parse_args(["--db", str(first), "--db", str(second)]))
    assert stop.value.code == 2
    assert "would both write" in capsys.readouterr().err


def test_a_production_write_needs_the_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(
        cli.GraphDB,
        "from_env",
        classmethod(lambda _c: cli.GraphDB("http://h", "portfolio", "", "")),
    )
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: pytest.fail("must not read"))
    with pytest.raises(SystemExit) as stop:
        cli.project(cli.parse_args(["--db", str(backtest_db(tmp_path)), "--write"]))
    assert stop.value.code == 2
    assert "a backtest is a frozen artifact" in capsys.readouterr().err


def test_a_production_write_with_the_opt_in_is_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(
        cli.GraphDB,
        "from_env",
        classmethod(lambda _c: cli.GraphDB("http://h", "portfolio", "", "")),
    )
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _result(written={"g": 1}))
    assert cli.main(["--db", str(backtest_db(tmp_path)), "--write", "--to-production"]) == 0


def test_a_boundary_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise BoundaryError(BoundaryReport(stopped=True, stop_reasons=["no"]))

    monkeypatch.setattr(cli, "run", fail)
    assert cli.main(["--db", str(backtest_db(tmp_path))]) == 1
    assert "STOPPED" in capsys.readouterr().err


def test_a_projection_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: (_ for _ in ()).throw(ProjectionError("bad")))
    assert cli.main(["--db", str(backtest_db(tmp_path))]) == 1
    assert "STOPPED" in capsys.readouterr().err


def test_a_rejected_graph_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _result(rejected={"g": "no"}))
    assert cli.main(["--db", str(backtest_db(tmp_path))]) == 1
    assert "rejected: g: no" in capsys.readouterr().out


def test_a_store_failure_partway_reports_what_was_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    partial = _result(written={"g": 7})

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise StoreInterrupted(partial, GraphDBError("HTTP 503"))

    monkeypatch.setattr(cli, "run", fail)
    assert cli.main(["--db", str(backtest_db(tmp_path))]) == 1
    printed = capsys.readouterr()
    assert "written: g: 7 triples" in printed.out
    assert "stopped partway: HTTP 503" in printed.err


def test_a_missing_database_exits_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert cli.main(["--db", str(tmp_path / "no.db")]) == 1
    assert "source error:" in capsys.readouterr().err


def test_a_non_completed_run_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_universe(monkeypatch)
    path = backtest_db(tmp_path, status="running")
    assert cli.main(["--db", str(path)]) == 1
    err = capsys.readouterr().err
    assert "STOPPED" in err
    assert "not 'completed'" in err
