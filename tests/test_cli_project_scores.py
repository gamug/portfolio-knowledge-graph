"""``cli/project_scores.py`` as a subprocess: the entry point really runs (T-031).

Its logic lives in ``projection.project_scores`` and is tested in ``test_project_scores.py``;
these run the script itself, as constitution Project structure #10 asks, over synthetic
databases passed through the environment. None of them writes: no store is needed.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fixtures.snapshot_rows import financial_db, fundamental_row

CLI = Path(__file__).resolve().parent.parent / "cli" / "project_scores.py"


def _universe(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
        "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
    )
    conn.execute(
        "INSERT INTO universe_membership VALUES ('AAA', 'AAA Inc.', NULL, NULL, NULL, "
        "'2000-01-01', NULL)"
    )
    conn.commit()
    conn.close()
    return path


def _run(
    tmp_path: Path, *args: str, financial: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        # The shell's environment wins over .env (load_env does not override it).
        "SQL_FINANCIAL_DB": str(financial or tmp_path / "financial.db"),
        "SQL_UNIVERSE_DB": str(_universe(tmp_path / "universe.db")),
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
    financial_db(tmp_path, [fundamental_row(id=10)]).close()
    keys = tmp_path / "keys" / "late.json"
    result = _run(tmp_path, "--late-keys", str(keys))
    assert result.returncode == 0, result.stderr
    assert "already in the store: not checked (dry run)" in result.stdout
    assert keys.parent.is_dir()  # the key folder is created, even on a dry run


def test_a_run_day_after_today_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--run-day", "2999-01-01")
    assert result.returncode == 2
    assert "is after today" in result.stderr


def test_a_missing_source_database_exits_1_with_a_message(tmp_path: Path) -> None:
    result = _run(tmp_path, financial=tmp_path / "no" / "financial.db")
    assert result.returncode == 1
    assert "source error:" in result.stderr
