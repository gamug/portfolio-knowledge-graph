"""``cli/load_run.py`` as a subprocess: the one-command contract (Work item 29).

A dry run over the synthetic database contacts no store. The write path's projector/gate/verifier
behaviour is covered by their own tests; here the real script is run for its argument contract and
for the one-command dry-run table.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.backtest_rows import backtest_db, universe_db

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_run.py"
LEGACY = ("--no-manifest", "--no-config")


def _run(
    tmp_path: Path, *args: str, repository: str = "test", delivery: bool = False
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SQL_UNIVERSE_DB": str(universe_db(tmp_path)),
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
    }
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, tmp_path arguments
        [sys.executable, str(CLI), *args, *(LEGACY if not delivery else ())],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )


def test_help_exits_0() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and script, no arguments
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--label" in result.stdout
    assert "--db" in result.stdout
    assert "--dir" in result.stdout
    assert "--check-store" in result.stdout
    assert "--contract" in result.stdout


def test_a_missing_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--db", str(backtest_db(tmp_path)))
    assert result.returncode == 2
    assert "--label" in result.stderr


def test_no_database_or_directory_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "rule")
    assert result.returncode == 2
    assert "at least one --db PATH or --dir DIR" in result.stderr


def test_a_malformed_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Rule", "--db", str(backtest_db(tmp_path)))
    assert result.returncode == 2
    assert "run label" in result.stderr


def test_to_production_without_write_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--db",
        str(backtest_db(tmp_path)),
        "--to-production",
    )
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_check_store_rejects_write_and_to_production(tmp_path: Path) -> None:
    path = backtest_db(tmp_path)
    result = _run(tmp_path, "--label", "rule", "--db", str(path), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--db",
        str(path),
        "--check-store",
        "--to-production",
    )
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr


def test_a_dry_run_over_a_synthetic_database_exits_0(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "rule", "--db", str(backtest_db(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:backtest:rule:P1:1" in result.stdout
    assert "urn:graph:derived:backtest:selection:rule:P1:1" in result.stdout
    assert "not verified (dry run)" in result.stdout
    assert "pre-flight" not in result.stdout


def test_a_directory_dry_run_loads_every_final_file(tmp_path: Path) -> None:
    backtest_db(tmp_path, name="rule_P1.db", window="P1")
    backtest_db(tmp_path, name="rule_P2.db", window="P2")
    result = _run(tmp_path, "--label", "rule", "--dir", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "urn:graph:derived:backtest:rule:P1:1" in result.stdout
    assert "urn:graph:derived:backtest:rule:P2:1" in result.stdout
    assert "urn:graph:derived:backtest:selection:rule:P1:1" in result.stdout
    assert "urn:graph:derived:backtest:selection:rule:P2:1" in result.stdout


def test_check_store_announces_the_target_before_anything_else(tmp_path: Path) -> None:
    """Work item 39: the store is opened before the delivery is read, so the banner is first."""
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--db",
        str(backtest_db(tmp_path)),
        "--check-store",
    )
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == (
        "target: GraphDB http://host.invalid repository test [not production]"
    )


def test_a_missing_database_exits_1(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "rule", "--db", str(tmp_path / "no.db"))
    assert result.returncode == 1
    assert "source error:" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--db",
        str(backtest_db(tmp_path)),
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "a backtest is a frozen artifact" in result.stderr
