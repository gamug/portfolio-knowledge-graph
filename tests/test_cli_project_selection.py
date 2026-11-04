"""``cli/project_selection.py`` as a subprocess: the entry point really runs (Work item 26)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.backtest_rows import backtest_db, universe_db

CLI = Path(__file__).resolve().parent.parent / "cli" / "project_selection.py"


def _run(tmp_path: Path, *args: str, repository: str = "test") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SQL_UNIVERSE_DB": str(universe_db(tmp_path)),
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
    }
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, tmp_path arguments
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )


def test_a_dry_run_over_a_synthetic_database_exits_0(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"rule={backtest_db(tmp_path)}")
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:backtest:selection:rule:P1:1" in result.stdout
    assert "SHACL-valid, not written" in result.stdout
    assert "already in the store: not checked (dry run)" in result.stdout


def test_two_databases_are_projected_in_one_run(tmp_path: Path) -> None:
    first = backtest_db(tmp_path, name="p1.db", window="P1")
    second = backtest_db(tmp_path, name="p2.db", window="P2")
    result = _run(tmp_path, "--db", f"rule={first}", "--db", f"rule={second}")
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:backtest:selection:rule:P1:1" in result.stdout
    assert "urn:graph:derived:backtest:selection:rule:P2:1" in result.stdout


def test_a_missing_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", str(backtest_db(tmp_path)))
    assert result.returncode == 2
    assert "expected LABEL=PATH" in result.stderr


def test_to_production_without_write_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"rule={backtest_db(tmp_path)}", "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--db",
        f"rule={backtest_db(tmp_path)}",
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "a backtest is a frozen artifact" in result.stderr


def test_a_missing_database_exits_1(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"rule={tmp_path / 'no.db'}")
    assert result.returncode == 1
    assert "source error:" in result.stderr
