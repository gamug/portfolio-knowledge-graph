"""``cli/load_agents.py`` as a subprocess (Work item 46, block F)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.agents_delivery import write_delivery

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_agents.py"


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
    for flag in (
        "--label",
        "--dir",
        "--window",
        "--only",
        "--check-store",
        "--write",
        "--to-production",
    ):
        assert flag in result.stdout


def test_impossible_flag_combinations_exit_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "final", "--dir", str(tmp_path), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(
        tmp_path, "--label", "final", "--dir", str(tmp_path), "--check-store", "--to-production"
    )
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr
    result = _run(tmp_path, "--label", "final", "--dir", str(tmp_path), "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_dry_run_prints_the_graphs_and_shacl(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    result = _run(tmp_path, "--label", "final", "--dir", str(root), "--window", "P1")
    assert result.returncode == 0, result.stderr
    assert "manifest: " in result.stdout
    for slug in ("manager_calls", "narrator", "news", "bull_mode"):
        assert f"urn:graph:derived:backtest:agents:final:P1:{slug}" in result.stdout
        assert (
            f"SHACL: conforms (urn:graph:derived:backtest:agents:final:P1:{slug}" in result.stdout
        )
    assert "manager_calls=1" in result.stdout
    assert "narrator_texts=2" in result.stdout


def test_only_and_window_select_one_graph(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    result = _run(
        tmp_path, "--label", "final", "--dir", str(root), "--window", "P1", "--only", "news"
    )
    assert result.returncode == 0, result.stderr
    assert "agents:final:P1:news" in result.stdout
    assert "agents:final:P1:manager_calls" not in result.stdout
    assert result.stdout.count("SHACL: conforms") == 1


def test_a_manifest_mismatch_exits_1(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    path = root / "SYSTEM_WITH_HIERARCHY" / "P1" / "H1B-A2g-P1.news.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = _run(tmp_path, "--label", "final", "--dir", str(root), "--window", "P1")
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    root = write_delivery(tmp_path)
    result = _run(
        tmp_path,
        "--label",
        "final",
        "--dir",
        str(root),
        "--window",
        "P1",
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "needs --to-production" in result.stderr


def test_a_label_outside_the_pattern_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Final", "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "run label" in result.stderr
