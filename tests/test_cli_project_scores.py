"""``cli/project_scores.py``: its arguments and how it reports a stopped run (T-031)."""

from __future__ import annotations

import datetime
import importlib.util
import sqlite3
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
from snapshot_helpers import ASSETS, financial_db, fundamental_row, live_store

from kg_store.graphdb import GraphDBError
from projection.boundary import GRAPH_WRITTEN, BoundaryReport, Failure
from projection.score_snapshots import (
    ProjectionError,
    RunResult,
    StoreInterrupted,
    lost_keys_path,
)

if TYPE_CHECKING:
    from snapshot_helpers import MakeDB

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
        (["--run-day", "2026-03-01", "--replay"], "--replay only matters with --write"),
    ],
    ids=["future", "future-replay", "past-write-without-replay", "replay-without-write"],
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


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        ("portfolio", "late.json"),
        ("replay", "replay/late.json"),
        ("bt-2026_q3", "bt-2026_q3/late.json"),
    ],
)
def test_each_repository_keeps_its_own_key_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository: str, expected: str
) -> None:
    # Review round 4, finding 1: a replay never settles or hides production's keys.
    cli = _frozen(monkeypatch)
    store = cli.GraphDB("http://h", repository, "", "")
    assert cli.key_file(tmp_path / "late.json", store) == tmp_path / expected
    assert (tmp_path / expected).parent.is_dir()  # the folder is created
    assert cli.key_file(tmp_path / "late.json", None) == tmp_path / "late.json"  # dry run
    assert cli.key_file(None, store) is None


@pytest.mark.parametrize("late", ["late.json", "late", "keys/late.json", "late.lost.json"])
@pytest.mark.parametrize("repository", ["replay", "lost", "late", "json", "portfolio-bt"])
def test_no_key_file_of_another_repository_can_share_a_name_with_productions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, late: str, repository: str
) -> None:
    # Review round 5, finding 1: "late" with no extension, or a repository named "lost", made
    # round 4's file names collide with production's.
    cli = _frozen(monkeypatch)
    given = tmp_path / late
    own = cli.key_file(given, cli.GraphDB("http://h", repository, "", ""))
    files = {given, lost_keys_path(given), own, lost_keys_path(own)}
    assert len(files) == 4


@pytest.mark.parametrize("repository", ["portfolio", "replay", None], ids=str)
def test_the_key_folder_is_created_for_every_repository_and_a_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository: str | None
) -> None:
    # Review round 6, finding 1: only a non-production repository got its folder created.
    cli = _frozen(monkeypatch)
    store = cli.GraphDB("http://h", repository, "", "") if repository else None
    keys = cli.key_file(tmp_path / "keys" / "late.json", store)
    assert keys.parent.is_dir()


def test_a_production_write_with_the_documented_key_path_writes_and_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_db: MakeDB,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Review round 6, finding 1: ``--late-keys keys/late.json`` on a fresh checkout wrote the
    # graph, then crashed saving the lost-key file into a folder that did not exist.
    cli = _frozen(monkeypatch)
    financial_db(tmp_path, [fundamental_row(id=10)]).close()
    store = live_store(make_db)
    store.repository = "portfolio"
    monkeypatch.setattr(cli.GraphDB, "from_env", classmethod(lambda _c: store.db))
    monkeypatch.setattr(cli.config, "financial_db_path", lambda: tmp_path / "financial.db")
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: ASSETS)
    keys = tmp_path / "keys" / "late.json"
    assert cli.main(["--write", "--late-keys", str(keys)]) == 0
    assert "written: urn:graph:ingest:FUNDAMENTAL:2025-Q1" in capsys.readouterr().out
    assert [g for _, _, g in store.added] == ["urn:graph:ingest:FUNDAMENTAL:2025-Q1"]
    assert keys.parent.is_dir()


def test_a_damaged_late_key_file_stops_the_run_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Review round 7, finding 2: the boundary's ValueError escaped main() as a traceback.
    cli = _frozen(monkeypatch)
    financial_db(tmp_path, [fundamental_row(id=10)]).close()
    monkeypatch.setattr(cli.config, "financial_db_path", lambda: tmp_path / "financial.db")
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: ASSETS)
    keys = tmp_path / "late.json"
    keys.write_text('{"v_score_snapshot": [[1')
    assert cli.main(["--late-keys", str(keys)]) == 1
    err = capsys.readouterr().err
    assert "STOPPED" in err
    assert "the late-key file is not JSON" in err


def test_a_store_that_hangs_up_is_a_store_failure_not_a_file_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    hangs_up: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Review round 7, finding 1: a closed connection was a raw OSError, so the run skipped its
    # key bookkeeping and the CLI printed "file error".
    cli = _frozen(monkeypatch)
    financial_db(tmp_path, [fundamental_row(id=10)]).close()
    monkeypatch.setattr(
        cli.GraphDB, "from_env", classmethod(lambda _c: cli.GraphDB(hangs_up, "portfolio", "", ""))
    )
    monkeypatch.setattr(cli.config, "financial_db_path", lambda: tmp_path / "financial.db")
    monkeypatch.setattr(cli, "universe_symbols", lambda _path: ASSETS)
    assert cli.main(["--write", "--late-keys", str(tmp_path / "late.json")]) == 1
    printed = capsys.readouterr()
    assert "store error, the run stopped partway: connection to GraphDB" in printed.err
    assert "file error" not in printed.err
    assert "already in the store" in printed.out  # the partial summary is printed


def test_a_key_file_that_cannot_be_written_exits_1_with_a_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _frozen(monkeypatch)
    _stub(monkeypatch, cli, _result())

    def fail(*_: Any, **__: Any) -> None:
        raise PermissionError(13, "Permission denied", "keys/late.lost.json")

    monkeypatch.setattr(cli, "run", fail)
    assert cli.main([]) == 1
    assert "file error:" in capsys.readouterr().err


def test_a_repository_name_that_cannot_name_a_file_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = _frozen(monkeypatch)
    with pytest.raises(SystemExit) as stop:
        cli.key_file(tmp_path / "late.json", cli.GraphDB("http://h", "../x", "", ""))
    assert stop.value.code == 2


def test_a_replay_and_a_production_run_given_the_same_late_keys_use_different_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = _frozen(monkeypatch)
    _stub(monkeypatch, cli, _result())
    used: list[Path] = []

    def record(*_: Any, late_keys_path: Path, **__: Any) -> RunResult:
        used.append(late_keys_path)
        return _result()

    monkeypatch.setattr(cli, "run", record)
    for repository, argv in [
        ("replay", ["--run-day", "2026-03-01", "--write", "--replay"]),
        ("portfolio", ["--write"]),
    ]:
        monkeypatch.setattr(
            cli.GraphDB,
            "from_env",
            classmethod(lambda _c, repo=repository: cli.GraphDB("http://h", repo, "", "")),
        )
        assert cli.main([*argv, "--late-keys", str(tmp_path / "late.json")]) == 0
    assert used == [tmp_path / "replay" / "late.json", tmp_path / "late.json"]


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
