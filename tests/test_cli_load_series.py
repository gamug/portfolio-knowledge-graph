"""``cli/load_series.py`` as a subprocess (Work item 46, block E)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_series.py"
WINDOWS = ("P1", "H1", "P3", "H2", "P2", "H3", "C1")
DATES = {
    "P1": "2022-01-03",
    "H1": "2022-10-13",
    "P3": "2023-10-27",
    "H2": "2024-08-05",
    "P2": "2025-02-19",
    "H3": "2025-09-24",
    "C1": "2022-01-03",
}


def _write(tmp_path: Path) -> Path:
    folder = tmp_path / "series"
    (folder / "markowitz_mv").mkdir(parents=True)
    names = []
    spy = ["window,date,daily_total_return,value"]
    spy.extend(f"{window},{DATES[window]},0.001,1.001" for window in WINDOWS)
    (folder / "spy_daily.csv").write_text("\n".join(spy) + "\n", encoding="utf-8")
    names.append("spy_daily.csv")
    for window in WINDOWS:
        name = f"markowitz_mv/mv_daily_{window}.csv"
        (folder / name).write_text(
            "date,gross_return,net_return,turnover,cost,cash_weight\n"
            f"{DATES[window]},0.001,-0.001,0.1,0.0001,0.01\n",
            encoding="utf-8",
        )
        names.append(name)
    weights = ["window,decision_date,asset_id,weight"]
    weights.extend(f"{window},{DATES[window]},1,0.1" for window in WINDOWS)
    (folder / "markowitz_mv/mv_weights.csv").write_text("\n".join(weights) + "\n", encoding="utf-8")
    names.append("markowitz_mv/mv_weights.csv")
    lines = [
        f"{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}" for name in names
    ]
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


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
    for flag in ("--label", "--dir", "--check-store", "--write", "--to-production"):
        assert flag in result.stdout


def test_a_missing_label_or_dir_exits_2(tmp_path: Path) -> None:
    assert _run(tmp_path, "--dir", str(tmp_path)).returncode == 2
    assert _run(tmp_path, "--label", "final").returncode == 2


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


def test_a_dry_run_prints_the_manifest_and_shacl(tmp_path: Path) -> None:
    folder = _write(tmp_path)
    result = _run(tmp_path, "--label", "final", "--dir", str(folder))
    assert result.returncode == 0, result.stderr
    assert "manifest: spy_daily.csv is listed" in result.stdout
    assert "rows: markowitz_mv/mv_weights.csv: 7" in result.stdout
    assert "urn:graph:derived:backtest:series:final:markowitz_mv" in result.stdout
    assert "urn:graph:derived:backtest:series:final:spy" in result.stdout
    assert "SHACL: conforms (markowitz_mv, gate.validate)" in result.stdout
    assert "SHACL: conforms (spy, gate.validate)" in result.stdout


def test_a_manifest_mismatch_exits_1(tmp_path: Path) -> None:
    folder = _write(tmp_path)
    path = folder / "spy_daily.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = _run(tmp_path, "--label", "final", "--dir", str(folder))
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_a_production_write_without_the_opt_in_exits_2(tmp_path: Path) -> None:
    folder = _write(tmp_path)
    result = _run(
        tmp_path, "--label", "final", "--dir", str(folder), "--write", repository="portfolio"
    )
    assert result.returncode == 2
    assert "needs --to-production" in result.stderr


def test_a_label_outside_the_pattern_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Final", "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "run label" in result.stderr
