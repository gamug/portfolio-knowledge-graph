"""``cli/project_reference.py`` as a subprocess: the entry point really runs (T-354)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.backtest_rows import universe_db
from fixtures.reference_rows import ASSETS, reference_db, scenario_rows

CLI = Path(__file__).resolve().parent.parent / "cli" / "project_reference.py"


def _run(tmp_path: Path, *args: str, repository: str = "test") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SQL_UNIVERSE_DB": str(universe_db(tmp_path, ASSETS)),
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
    path = reference_db(tmp_path)
    result = _run(tmp_path, "--db", f"fixture={path}", "--as-of", "2026-11-04")
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:ticker-history:fixture:2026-11-04" in result.stdout
    assert "urn:graph:derived:orchestrator:fixture:1" in result.stdout
    assert "asset links: v_ticker_history: 4 exact, 4 by CIK" in result.stdout
    assert "asset link omitted: v_ticker_history: 1" in result.stdout
    assert "SHACL-valid, not written" in result.stdout
    assert "already in the store: not checked (dry run)" in result.stdout


def test_the_empty_orchestrator_views_say_nothing_to_write(tmp_path: Path) -> None:
    rows = scenario_rows()
    rows["v_orchestrator_run"] = []
    rows["v_orchestrator_step"] = []
    path = reference_db(tmp_path, rows=rows)
    result = _run(tmp_path, "--db", f"fixture={path}", "--as-of", "2026-11-04")
    assert result.returncode == 0, result.stderr
    assert "v_orchestrator_run: 0 rows, v_orchestrator_step: 0 rows: nothing to write" in (
        result.stdout
    )
    assert "urn:graph:derived:orchestrator" not in result.stdout


def test_two_labels_are_projected_in_one_run(tmp_path: Path) -> None:
    first = reference_db(tmp_path, name="one.db")
    second = reference_db(tmp_path, name="two.db")
    result = _run(
        tmp_path,
        "--db",
        f"one={first}",
        "--db",
        f"two={second}",
        "--as-of",
        "2026-11-04",
    )
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:ticker-history:one:2026-11-04" in result.stdout
    assert "urn:graph:derived:ticker-history:two:2026-11-04" in result.stdout


def test_a_missing_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", str(reference_db(tmp_path)))
    assert result.returncode == 2
    assert "expected LABEL=PATH" in result.stderr


def test_a_malformed_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"Fixture={reference_db(tmp_path)}")
    assert result.returncode == 2
    assert "run label" in result.stderr


def test_a_repeated_label_exits_2(tmp_path: Path) -> None:
    first = reference_db(tmp_path, name="one.db")
    second = reference_db(tmp_path, name="two.db")
    result = _run(tmp_path, "--db", f"fixture={first}", "--db", f"fixture={second}")
    assert result.returncode == 2
    assert "label given twice" in result.stderr


def test_a_bad_as_of_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"fixture={reference_db(tmp_path)}", "--as-of", "2026-13-01")
    assert result.returncode == 2
    assert "YYYY-MM-DD" in result.stderr


def test_to_production_without_write_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--db",
        f"fixture={reference_db(tmp_path)}",
        "--to-production",
    )
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--db",
        f"fixture={reference_db(tmp_path)}",
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "ticker-history snapshot is reference data" in result.stderr


def test_a_missing_database_exits_1(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", f"fixture={tmp_path / 'no.db'}")
    assert result.returncode == 1
    assert "source error:" in result.stderr
