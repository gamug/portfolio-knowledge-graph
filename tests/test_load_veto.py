"""The one Veto Hierarchy loader CLI: draft dry run and production write guard (T-866)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fixtures.backtest_rows import backtest_db, final_scenario_rows, universe_db

from projection import load_veto
from projection.load_veto import (
    _check_decision_close_count,
    _decision_close_expected,
    build_delivery,
    main,
)
from projection.veto_manifest import read_manifest


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "delivery"
    folder.mkdir()
    universe = universe_db(tmp_path)
    mask = folder / "mask.csv"
    mask.write_text("ticker\nAAA\n")
    config = folder / "config_final.md"
    config.write_text(
        "---\nlabel: final\ncode_commit: abc1234\npr: 158\nresults_doc: docs/results.md\n---\n"
        "Frozen body with & and '.\n"
    )
    dbs: dict[str, Path] = {}
    for name, rows in (
        ("system_with", final_scenario_rows("P1")),
        ("system_without", final_scenario_rows("P1")),
        ("markowitz", final_scenario_rows("P1")),
    ):
        dbs[name] = backtest_db(folder, name=f"{name}.db", rows=rows)
    series = folder / "series"
    series.mkdir()
    series_files = {}
    for name in ("mv_daily.csv", "mv_weights.csv", "mv_agg.json", "spy_daily.csv"):
        path = series / name
        path.write_text("date,value\n")
        series_files[name] = path
    runs = []
    for configuration, file_name, book_code, book_id in (
        ("SYSTEM_WITH_HIERARCHY", "system_with", "TOPN_MV_GUARD_NO_NLP", 3),
        ("SYSTEM_WITHOUT_HIERARCHY", "system_without", "TOPN_MV_NOGUARD", 2),
        ("MARKOWITZ_BASE", "markowitz", "MARKOWITZ_BASE", 1),
    ):
        path = dbs[file_name]
        runs.append(
            {
                "configuration": configuration,
                "name_es": configuration,
                "name_en": configuration,
                "source_kind": "engine_db",
                "runs": [
                    {
                        "window": "P1",
                        "db_file": str(path.relative_to(folder)),
                        "db_sha256": _hash(path),
                        "run_id": 1,
                        "book_code": book_code,
                        "book_id": book_id,
                    }
                ],
            }
        )
    runs.extend(
        [
            {
                "configuration": "MARKOWITZ_MV",
                "name_es": "MV",
                "name_en": "MV",
                "source_kind": "series_csv",
                "runs": [
                    {
                        "window": "P1",
                        "daily_file": str(series_files["mv_daily.csv"].relative_to(folder)),
                        "daily_sha256": _hash(series_files["mv_daily.csv"]),
                        "weights_file": str(series_files["mv_weights.csv"].relative_to(folder)),
                        "weights_sha256": _hash(series_files["mv_weights.csv"]),
                        "aggregates_file": str(series_files["mv_agg.json"].relative_to(folder)),
                        "aggregates_sha256": _hash(series_files["mv_agg.json"]),
                    }
                ],
            },
            {
                "configuration": "SPY",
                "name_es": "SPY",
                "name_en": "SPY",
                "source_kind": "series_csv",
                "runs": [
                    {
                        "window": "P1",
                        "daily_file": str(series_files["spy_daily.csv"].relative_to(folder)),
                        "daily_sha256": _hash(series_files["spy_daily.csv"]),
                    }
                ],
            },
        ]
    )
    manifest = {
        "manifest_version": "pilot",
        "status": "BORRADOR",
        "label": "final",
        "created_at": "2026-11-13",
        "key": ["label", "configuration", "window"],
        "windows": ["P1", "H1", "P3", "H2", "P2", "H3", "C1"],
        "price_mask": {"file": "mask.csv", "sha256": _hash(mask), "rule": "none"},
        "prereg": {"SPEC.md": "a" * 64},
        "configurations": runs,
        "control_counts": "PENDIENTE",
    }
    path = folder / "manifest_final.json"
    path.write_text(json.dumps(manifest))
    return path, universe


def test_a_draft_manifest_dry_run_projects_every_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    assert main(["--manifest", str(path)]) == 0
    out = capsys.readouterr().out
    assert "dry run complete" in out
    assert "urn:graph:derived:backtest:final:P1:system_with_hierarchy" in out
    assert "urn:graph:derived:backtest:selection:final:P1:system_with_hierarchy" in out
    assert "urn:graph:derived:backtest:final:P1:markowitz_base" in out


def test_a_draft_manifest_cannot_be_written_to_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)

    class Production:
        repository = "portfolio"
        host = "test"

    monkeypatch.setattr(load_veto.GraphDB, "from_env", classmethod(lambda cls: Production()))
    assert main(["--manifest", str(path), "--write", "--to-production"]) == 2
    assert "draft manifest cannot be written to production" in capsys.readouterr().err


def test_a_dry_run_never_opens_the_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: pytest.fail("a dry run must not contact the store")),
    )
    assert main(["--manifest", str(path)]) == 0


def test_the_manifest_label_must_match(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    with pytest.raises(ValueError, match="differs from --label"):
        build_delivery(read_manifest(path), "other", assets_db=tmp_path / "missing.db")


class _Store:
    repository = "portfolio_test"
    host = "test"


def test_a_draft_manifest_can_be_written_to_a_scratch_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(load_veto.GraphDB, "from_env", classmethod(lambda cls: _Store()))
    monkeypatch.setattr(load_veto, "plan_delivery", lambda store, result, minimum_free_pct=8.0: [])
    monkeypatch.setattr(load_veto, "write_delivery", lambda store, plans: ((), None))
    monkeypatch.setattr(load_veto, "verify_delivery", lambda store, result, manifest: None)
    assert main(["--manifest", str(path), "--write"]) == 0


def test_check_store_does_not_require_the_production_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: type("P", (), {"repository": "portfolio", "host": "test"})()),
    )
    monkeypatch.setattr(load_veto, "plan_delivery", lambda store, result, minimum_free_pct=8.0: [])
    assert main(["--manifest", str(path), "--check-store"]) == 0


def test_write_to_production_without_the_flag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, universe = _manifest(tmp_path)
    monkeypatch.setattr(load_veto.config, "universe_db_path", lambda: universe)
    monkeypatch.setattr(
        load_veto.GraphDB,
        "from_env",
        classmethod(lambda cls: type("P", (), {"repository": "portfolio", "host": "test"})()),
    )
    assert main(["--manifest", str(path), "--write"]) == 2
    assert "needs --to-production" in capsys.readouterr().err


def test_decision_close_control_count_is_optional_and_hard_checked(
    tmp_path: Path,
) -> None:
    path, _ = _manifest(tmp_path)
    manifest = read_manifest(path)
    manifest = type(manifest)(
        **{
            **manifest.__dict__,
            "control_counts": {
                "configurations": {"SYSTEM_WITH_HIERARCHY": {"P1": {"decision_close_episodes": 2}}}
            },
        }
    )
    assert _decision_close_expected(manifest, "SYSTEM_WITH_HIERARCHY", "P1") == 2
    _check_decision_close_count(
        manifest, "SYSTEM_WITH_HIERARCHY", "P1", {"memory_episodes_decision_close": 2}
    )
    with pytest.raises(ValueError, match="decision_close_episodes mismatch"):
        _check_decision_close_count(
            manifest, "SYSTEM_WITH_HIERARCHY", "P1", {"memory_episodes_decision_close": 1}
        )
