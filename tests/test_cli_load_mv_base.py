"""``cli/load_mv_base.py`` as a subprocess (Work item 44)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.mv_base_rows import write_mv_base

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_mv_base.py"


def _run(tmp_path: Path, *args: str, repository: str = "test") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
    }
    return subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )


def test_help_exits_0() -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
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
    assert "--to-production" in result.stdout


def test_a_missing_label_or_dir_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "--label" in result.stderr
    result = _run(tmp_path, "--label", "final")
    assert result.returncode == 2
    assert "--dir" in result.stderr


def test_impossible_flag_combinations_exit_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "final", "--dir", str(tmp_path), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(
        tmp_path,
        "--label",
        "final",
        "--dir",
        str(tmp_path),
        "--check-store",
        "--to-production",
    )
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr
    result = _run(tmp_path, "--label", "final", "--dir", str(tmp_path), "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_dry_run_prints_the_manifest_config_graph_and_shacl(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "final", "--dir", str(write_mv_base(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "manifest: aggregates_mv_base.json is listed" in result.stdout
    assert "manifest: config_mv_base.md is listed" in result.stdout
    assert "config: final / MARKOWITZ_MV / final" in result.stdout
    assert "code version: sim_v3.py 4d23" in result.stdout
    assert "urn:graph:derived:backtest:external:final" in result.stdout
    assert "rows: 8 (6 windows, 2 cuts)" in result.stdout
    assert "SHACL: conforms (gate.validate)" in result.stdout
    assert "timing: total" in result.stdout


def test_a_manifest_mismatch_exits_1(tmp_path: Path) -> None:
    directory = write_mv_base(tmp_path)
    path = directory / "aggregates_mv_base.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = _run(tmp_path, "--label", "final", "--dir", str(directory))
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--label",
        "final",
        "--dir",
        str(write_mv_base(tmp_path)),
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "needs --to-production" in result.stderr


def test_a_label_outside_the_pattern_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Final", "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "run label" in result.stderr


def test_a_missing_config_exits_1(tmp_path: Path) -> None:
    directory = write_mv_base(tmp_path)
    (directory / "config_mv_base.md").unlink()
    result = _run(tmp_path, "--label", "final", "--dir", str(directory))
    assert result.returncode == 1
    assert "config_mv_base.md" in result.stderr
