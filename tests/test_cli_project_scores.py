"""``cli/project_scores.py``: its arguments and how it reports a stopped run (T-031)."""

from __future__ import annotations

import datetime
import importlib.util
import sqlite3
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from kg_store.graphdb import GraphDBError
from projection.boundary import GRAPH_WRITTEN, BoundaryReport, Failure
from projection.score_snapshots import ProjectionError, RunResult, StoreInterrupted

CLI = Path(__file__).resolve().parent.parent / "cli" / "project_scores.py"


def _cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("project_scores", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen(monkeypatch: pytest.MonkeyPatch, day: str = "2026-10-07") -> ModuleType:
    """The CLI with its clock stopped on ``day`` (UTC), so no test depends on midnight."""
    cli = _cli()
    monkeypatch.setattr(cli, "today", lambda: day)
    return cli


def test_the_run_day_defaults_to_today_in_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _frozen(monkeypatch).parse_args([]).run_day == "2026-10-07"


def test_today_is_the_utc_date() -> None:
    before = datetime.datetime.now(datetime.UTC).date()
    today = datetime.date.fromisoformat(_cli().today())
    assert before <= today <= before + datetime.timedelta(days=1)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--run-day", "2026-10-08"], "is after today (2026-10-07 UTC)"),
        (["--run-day", "2026-10-08", "--write", "--replay"], "is after today"),
        (["--run-day", "2026-03-01", "--write"], "--write with it needs --replay"),
    ],
    ids=["future", "future-replay", "past-write-without-replay"],
)
def test_a_run_day_the_run_cannot_use_is_refused_before_anything_is_read(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    with pytest.raises(SystemExit) as stop:
        _frozen(monkeypatch).parse_args(argv)
    assert stop.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--run-day", "2026-03-01"],  # a dry-run replay
        ["--run-day", "2026-03-01", "--write", "--replay"],
        ["--run-day", "2026-10-07", "--write"],
    ],
)
def test_a_past_day_dry_run_or_a_replay_write_is_allowed(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    assert _frozen(monkeypatch).parse_args(argv).run_day == argv[1]


def test_a_malformed_run_day_is_refused_before_anything_is_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stop:
        _cli().parse_args(["--run-day", "7/10/2026"])
    assert stop.value.code == 2
    assert "is not a YYYY-MM-DD date" in capsys.readouterr().err


def test_a_projection_error_stops_the_run_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli()

    class Source:
        closed = False

        def close(self) -> None:
            Source.closed = True

    def fail(*_: Any, **__: Any) -> None:
        raise ProjectionError("v_score_snapshot id=3: event_time 'x' is not a date")

    monkeypatch.setattr(cli.FinancialSource, "open", lambda _path: Source())
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: set())
    monkeypatch.setattr(cli, "run", fail)
    assert cli.main([]) == 1
    assert "STOPPED" in capsys.readouterr().err
    assert Source.closed


def test_a_replay_never_writes_to_the_production_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _frozen(monkeypatch)
    _stub(monkeypatch, cli, _result())
    called = []
    monkeypatch.setattr(cli, "run", lambda *a, **k: called.append(a))
    monkeypatch.setattr(
        cli.GraphDB,
        "from_env",
        classmethod(lambda _c: cli.GraphDB("http://h", "portfolio", "", "")),
    )
    with pytest.raises(SystemExit) as stop:
        cli.main(["--run-day", "2026-03-01", "--write", "--replay"])
    assert stop.value.code == 2
    assert "never writes to the production repository" in capsys.readouterr().err
    assert not called

    monkeypatch.setattr(
        cli.GraphDB, "from_env", classmethod(lambda _c: cli.GraphDB("http://h", "replay", "", ""))
    )
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _result())
    assert cli.main(["--run-day", "2026-03-01", "--write", "--replay"]) == 0


def test_a_missing_source_database_exits_1_with_a_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _frozen(monkeypatch)
    monkeypatch.setattr(cli.config, "financial_db_path", lambda: tmp_path / "no" / "f.db")
    assert cli.main([]) == 1
    assert "source error:" in capsys.readouterr().err


def test_a_database_without_upstreams_tables_exits_1_with_a_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _frozen(monkeypatch)
    empty = tmp_path / "f.db"
    sqlite3.connect(empty).close()
    monkeypatch.setattr(cli.config, "financial_db_path", lambda: empty)
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: set())
    assert cli.main([]) == 1
    assert "source error: no such table:" in capsys.readouterr().err


def test_a_store_failure_partway_prints_what_was_written_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _frozen(monkeypatch)
    _stub(monkeypatch, cli, _result())
    partial = _result(written={"urn:graph:ingest:FUNDAMENTAL:2025-Q1": 7})

    def fail(*_: Any, **__: Any) -> None:
        raise StoreInterrupted(partial, GraphDBError("HTTP 503"))

    monkeypatch.setattr(cli, "run", fail)
    assert cli.main([]) == 1
    printed = capsys.readouterr()
    assert "written: urn:graph:ingest:FUNDAMENTAL:2025-Q1: 7 triples" in printed.out
    assert "stopped partway: HTTP 503" in printed.err


def _stub(monkeypatch: pytest.MonkeyPatch, cli: ModuleType, result: Any) -> None:
    class Source:
        def close(self) -> None:
            pass

    monkeypatch.setattr(cli.FinancialSource, "open", lambda _path: Source())
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: set())
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: result)


def _result(**fields: Any) -> RunResult:
    return RunResult(BoundaryReport(), Counter(), **fields)


def test_a_graph_the_gate_refused_makes_the_run_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _cli()
    _stub(monkeypatch, cli, _result(rejected={"urn:graph:ingest:TECHNICAL:2026-10-08": "no"}))
    assert cli.main([]) == 1


def test_a_lost_row_is_listed_but_does_not_fail_the_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli()
    result = _result()
    result.report.lost.append(
        Failure("v_score_snapshot", GRAPH_WRITTEN, None, "already written", key=(11,))
    )
    _stub(monkeypatch, cli, result)
    assert cli.main([]) == 0
    assert "lost: v_score_snapshot row (11,): graph_written" in capsys.readouterr().out
