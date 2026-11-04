"""``cli/verify_backtest.py`` as a subprocess: the entry point parses and refuses bad input (T-280).

The verification itself needs a store; its logic and the fake-store cases live in
``test_verify_backtest.py``. These run the real script for the argument contract, as constitution
Project structure #10 asks, and never contact GraphDB.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "cli" / "verify_backtest.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": "test",
    }
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, test arguments
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_help_exits_0() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "--graph" in result.stdout
    assert "--db" in result.stdout
    assert "--label" in result.stdout


def test_a_missing_graph_exits_2() -> None:
    result = _run("--db", "x.db", "--label", "rule")
    assert result.returncode == 2
    assert "--graph" in result.stderr


def test_a_missing_database_exits_2() -> None:
    result = _run("--graph", "urn:graph:derived:backtest:rule:P1:1", "--label", "rule")
    assert result.returncode == 2
    assert "--db" in result.stderr


def test_a_missing_label_exits_2() -> None:
    result = _run("--graph", "urn:graph:derived:backtest:rule:P1:1", "--db", "x.db")
    assert result.returncode == 2
    assert "--label" in result.stderr


def test_a_malformed_label_exits_2() -> None:
    result = _run(
        "--graph", "urn:graph:derived:backtest:rule:P1:1", "--db", "x.db", "--label", "Rule"
    )
    assert result.returncode == 2
    assert "run label" in result.stderr
