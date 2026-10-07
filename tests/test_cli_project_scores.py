"""``cli/project_scores.py``: its arguments and how it reports a stopped run (T-031)."""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from projection.score_snapshots import ProjectionError

CLI = Path(__file__).resolve().parent.parent / "cli" / "project_scores.py"


def _cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("project_scores", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_run_day_defaults_to_today_in_utc() -> None:
    assert _cli().parse_args([]).run_day == datetime.datetime.now(datetime.UTC).date().isoformat()


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
