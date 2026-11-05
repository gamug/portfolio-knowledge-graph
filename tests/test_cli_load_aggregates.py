"""``cli/load_aggregates.py`` as a subprocess (Work item 37).

The dry run contacts no store. The write path's gate/store behaviour is covered by
``tests/test_aggregates.py`` with the in-memory ``DatasetStore``; here the real script is run for
its argument contract, the manifest refusal and the dry-run table.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.aggregates_rows import (
    aggregates_document,
    p1_rows,
    p2_rows,
    write_aggregates,
)
from fixtures.backtest_rows import backtest_db

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_aggregates.py"


def _run(tmp_path: Path, *args: str, repository: str = "test") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
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


def _folder(tmp_path: Path) -> Path:
    write_aggregates(tmp_path, aggregates_document())
    backtest_db(tmp_path, name="rule_P1.db", window="P1", rows=p1_rows())
    backtest_db(tmp_path, name="rule_P2.db", window="P2", rows=p2_rows())
    return tmp_path


def test_help_exits_0() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and script, no arguments
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--label" in result.stdout
    assert "--dir" in result.stdout
    assert "--check-store" in result.stdout
    assert "--write" in result.stdout


def test_a_missing_label_or_dir_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "--label" in result.stderr
    result = _run(tmp_path, "--label", "rule")
    assert result.returncode == 2
    assert "--dir" in result.stderr


def test_a_malformed_label_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Rule", "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "run label" in result.stderr


def test_impossible_flag_combinations_exit_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "rule", "--dir", str(tmp_path), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--dir",
        str(tmp_path),
        "--check-store",
        "--to-production",
    )
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr
    result = _run(tmp_path, "--label", "rule", "--dir", str(tmp_path), "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_dry_run_prints_the_manifest_verifier_build_and_timings(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, "--label", "rule", "--dir", str(_folder(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "manifest: aggregates_rule.json is listed" in result.stdout
    assert "urn:graph:derived:backtest:aggregates:rule" in result.stdout
    assert "rows: trend_filter: 3; reference_returns: 8" in result.stdout
    assert "PASS  manifest" in result.stdout
    assert "PASS  trend filter P1" in result.stdout
    assert "PASS  reference returns P2a" in result.stdout
    assert "SHACL: conforms (gate.validate)" in result.stdout
    assert "timing: total" in result.stdout


def test_a_manifest_mismatch_exits_1_with_both_hashes(tmp_path: Path) -> None:
    directory = _folder(tmp_path)
    path = directory / "aggregates_rule.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = _run(tmp_path, "--label", "rule", "--dir", str(directory))
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr
    assert "manifest says" in result.stderr
    assert "the file has" in result.stderr


def test_a_missing_file_exits_1(tmp_path: Path) -> None:
    (tmp_path / "SHA256SUMS").write_text("", encoding="utf-8")
    result = _run(tmp_path, "--label", "rule", "--dir", str(tmp_path))
    assert result.returncode == 1
    assert "no aggregates file" in result.stderr


def test_a_file_label_that_differs_exits_1(tmp_path: Path) -> None:
    write_aggregates(tmp_path, aggregates_document("other"), label="rule")
    result = _run(tmp_path, "--label", "rule", "--dir", str(tmp_path))
    assert result.returncode == 1
    assert "the file's label is 'other'" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    directory = _folder(tmp_path)
    result = _run(
        tmp_path,
        "--label",
        "rule",
        "--dir",
        str(directory),
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "needs --to-production" in result.stderr
