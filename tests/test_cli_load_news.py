"""``cli/load_news.py`` as a subprocess (Work item 46, block D)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_news.py"


def _universe_db(tmp_path: Path) -> Path:
    path = tmp_path / "universe.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS universe_membership (symbol TEXT NOT NULL, "
            "security TEXT NOT NULL, gics_sector TEXT, gics_sub_industry TEXT, cik TEXT, "
            "valid_from TEXT NOT NULL, valid_to TEXT)"
        )
        connection.execute("DELETE FROM universe_membership")
        connection.execute(
            "INSERT INTO universe_membership VALUES "
            "('AAPL', 'Apple Inc.', 'Information Technology', 'Technology Hardware', "
            "'0000320193', '2021-01-01', NULL)"
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _write(tmp_path: Path) -> Path:
    root = tmp_path / "delivery"
    folder = root / "news"
    folder.mkdir(parents=True)
    row = {
        "model_revision": "snapshot-c3a753affa5d",
        "item_kind": "sub_news",
        "item_id": "251045",
        "ticker": "AAPL",
        "asset_id": 4,
        "date": "2021-12-01",
        "date_source": "published",
        "title": "Here are Wednesday's biggest analyst calls",
        "text": "UBS reiterates Apple as buy.",
        "text_source": "original",
        "sentiment": "positive",
        "sentiment_score": 0.7824,
        "p_positive": 0.7824,
        "p_negative": 0.1916,
        "p_neutral": 0.0260,
        "sentiment_revision": "sentiment-5999fe131d8f",
        "category": "market_analyst_sentiment",
        "category_score": 0.9901,
        "group_label": "market_view",
        "category_revision": "category-9b2c6a65a6f4",
        "article_id": 174832,
        "body_hash": "a" * 64,
        "source_domain": "cnbc.com",
        "url": None,
    }
    data = folder / "news_rows.jsonl"
    data.write_text(json.dumps(row) + "\n", encoding="utf-8")
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    series = root / "series.csv"
    series.write_text("date,value\n2021-12-01,1\n", encoding="utf-8")
    series_hash = hashlib.sha256(series.read_bytes()).hexdigest()
    mask = root / "mask.csv"
    mask.write_text("AAPL\n", encoding="utf-8")
    mask_hash = hashlib.sha256(mask.read_bytes()).hexdigest()
    configurations = [
        {
            "configuration": configuration,
            "source_kind": "series_csv",
            "runs": [
                {
                    "window": "P1",
                    "daily_file": "series.csv",
                    "daily_sha256": series_hash,
                }
            ],
        }
        for configuration in (
            "SYSTEM_WITH_HIERARCHY",
            "SYSTEM_WITHOUT_HIERARCHY",
            "MARKOWITZ_BASE",
            "MARKOWITZ_MV",
            "SPY",
        )
    ]
    manifest = {
        "manifest_version": "1",
        "label": "final",
        "created_at": "2026-11-17",
        "key": ["label", "configuration", "window"],
        "windows": ["P1", "H1", "P3", "H2", "P2", "H3", "C1"],
        "price_mask": {"file": "mask.csv", "sha256": mask_hash, "rule": "none"},
        "prereg": {"SPEC.md": "a" * 64},
        "configurations": configurations,
        "news_rows_file": {
            "file": "news/news_rows.jsonl",
            "sha256": digest,
            "rows": 1,
            "model_revision": "snapshot-c3a753affa5d",
            "columns": list(row),
            "readme": "news/README.md",
        },
    }
    (root / "manifest_final.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "SHA256SUMS").write_text(f"{digest}  news/news_rows.jsonl\n", encoding="utf-8")
    return root


def _run(tmp_path: Path, *args: str, repository: str = "test") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
        "SQL_UNIVERSE_DB": str(_universe_db(tmp_path)),
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
        "--universe-db",
        "--check-store",
        "--write",
        "--to-production",
    ):
        assert flag in result.stdout


def test_a_missing_label_or_dir_exits_2(tmp_path: Path) -> None:
    assert _run(tmp_path, "--dir", str(tmp_path)).returncode == 2
    assert _run(tmp_path, "--label", "final").returncode == 2


def test_impossible_flag_combinations_exit_2(tmp_path: Path) -> None:
    root = _write(tmp_path)
    result = _run(tmp_path, "--label", "final", "--dir", str(root), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(
        tmp_path,
        "--label",
        "final",
        "--dir",
        str(root),
        "--check-store",
        "--to-production",
    )
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr
    result = _run(tmp_path, "--label", "final", "--dir", str(root), "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_dry_run_prints_rows_graph_triples_and_shacl(tmp_path: Path) -> None:
    root = _write(tmp_path)
    result = _run(tmp_path, "--label", "final", "--dir", str(root))
    assert result.returncode == 0, result.stderr
    assert "rows: 1" in result.stdout
    assert "graph: urn:graph:derived:news:final:2021" in result.stdout
    assert "triples: urn:graph:derived:news:final:2021:" in result.stdout
    assert "unresolved assets: 0 row(s); asset_id null: 0" in result.stdout
    assert "SHACL: conforms" in result.stdout


def test_a_bad_manifest_exits_1(tmp_path: Path) -> None:
    root = _write(tmp_path)
    manifest = json.loads((root / "manifest_final.json").read_text(encoding="utf-8"))
    manifest["news_rows_file"]["rows"] = 2
    (root / "manifest_final.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = _run(tmp_path, "--label", "final", "--dir", str(root))
    assert result.returncode == 1
    assert "the manifest says 2" in result.stderr


def test_a_production_write_without_the_flag_exits_2(tmp_path: Path) -> None:
    root = _write(tmp_path)
    result = _run(
        tmp_path,
        "--label",
        "final",
        "--dir",
        str(root),
        "--write",
        repository="portfolio",
    )
    assert result.returncode == 2
    assert "--to-production" in result.stderr
