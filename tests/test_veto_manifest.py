"""The Veto Hierarchy manifest, hashes, graph names and row filters (Work item 46, T-847-T-852)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from projection.veto_manifest import (
    CONFIGURATIONS,
    WINDOWS,
    VetoManifestError,
    aggregates_graph_name,
    backtest_graph_name,
    configuration_iri,
    configuration_slug,
    entity_stem,
    external_graph_name,
    filter_rows,
    meta_graph_name,
    read_manifest,
    selection_graph_name,
    verify_files,
)

LABEL = "final"


def _write(path: Path, data: bytes = b"x") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _manifest(tmp_path: Path, *, final: bool = True) -> tuple[Path, dict[str, Path]]:
    """A complete synthetic final manifest and the files it names."""
    files: dict[str, Path] = {}
    mask = tmp_path / "mask" / "tiingo_assets.csv"
    mask_hash = _write(mask, b"AAPL\n")
    files["mask"] = mask
    runs: list[dict[str, Any]] = []
    for number, configuration in enumerate(
        ("SYSTEM_WITH_HIERARCHY", "SYSTEM_WITHOUT_HIERARCHY", "MARKOWITZ_BASE"), 1
    ):
        db = tmp_path / "db" / f"{configuration}.db"
        detail = tmp_path / "db" / f"{configuration}.jsonl"
        db_hash = _write(db, f"db-{configuration}".encode())
        detail_hash = _write(detail, b"{}\n")
        files[configuration] = db
        runs.append(
            {
                "configuration": configuration,
                "name_es": configuration,
                "name_en": configuration,
                "source_kind": "engine_db",
                "runs": [
                    {
                        "window": "P1",
                        "db_file": str(db.relative_to(tmp_path)),
                        "db_sha256": db_hash,
                        "run_id": 1,
                        "book_code": {
                            "SYSTEM_WITH_HIERARCHY": "TOPN_MV_GUARD_NO_NLP",
                            "SYSTEM_WITHOUT_HIERARCHY": "TOPN_MV_NOGUARD",
                            "MARKOWITZ_BASE": "MARKOWITZ_BASE",
                        }[configuration],
                        "book_id": number,
                        "jsonl_file": str(detail.relative_to(tmp_path)),
                        "jsonl_sha256": detail_hash,
                        "files_sha256": {},
                    }
                ],
            }
        )
    mv_daily = tmp_path / "series" / "mv_daily.csv"
    mv_weights = tmp_path / "series" / "mv_weights.csv"
    mv_aggregates = tmp_path / "series" / "mv_aggregates.json"
    spy_daily = tmp_path / "series" / "spy_daily.csv"
    hashes = {
        "mv_daily": _write(mv_daily, b"date,value\n"),
        "mv_weights": _write(mv_weights, b"date,weight\n"),
        "mv_aggregates": _write(mv_aggregates, b"{}"),
        "spy_daily": _write(spy_daily, b"date,value\n"),
    }
    runs.extend(
        [
            {
                "configuration": "MARKOWITZ_MV",
                "name_es": "Markowitz MV",
                "name_en": "Markowitz MV",
                "source_kind": "series_csv",
                "runs": [
                    {
                        "window": "P1",
                        "daily_file": str(mv_daily.relative_to(tmp_path)),
                        "daily_sha256": hashes["mv_daily"],
                        "weights_file": str(mv_weights.relative_to(tmp_path)),
                        "weights_sha256": hashes["mv_weights"],
                        "aggregates_file": str(mv_aggregates.relative_to(tmp_path)),
                        "aggregates_sha256": hashes["mv_aggregates"],
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
                        "daily_file": str(spy_daily.relative_to(tmp_path)),
                        "daily_sha256": hashes["spy_daily"],
                        "window_filter": "window = P1",
                    }
                ],
            },
        ]
    )
    manifest: dict[str, Any] = {
        "manifest_version": "1",
        "label": LABEL,
        "created_at": "2026-11-17",
        "key": ["label", "configuration", "window"],
        "windows": list(WINDOWS),
        "price_mask": {
            "file": str(mask.relative_to(tmp_path)),
            "sha256": mask_hash,
            "rule": "no absolute price or daily return",
        },
        "prereg": {"SPEC.md": "a" * 64},
        "configurations": runs,
        "control_counts": {"P1": 1},
    }
    if not final:
        manifest["status"] = "BORRADOR: draft"
        manifest["configurations"][0]["runs"][0]["db_sha256"] = "PENDIENTE"
    path = tmp_path / "manifest_final.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, files


def test_a_final_manifest_parses_and_verifies(tmp_path: Path) -> None:
    path, files = _manifest(tmp_path)
    manifest = read_manifest(path)
    assert not manifest.draft
    assert manifest.label == LABEL
    assert manifest.windows == WINDOWS
    assert [item["configuration"] for item in manifest.configurations] == list(CONFIGURATIONS)
    assert len(manifest.engine_runs) == 3
    verified = verify_files(manifest)
    assert files["mask"].resolve() in verified
    assert files["SYSTEM_WITH_HIERARCHY"].resolve() in verified
    assert (
        verified[files["SYSTEM_WITH_HIERARCHY"].resolve()]
        == hashlib.sha256(b"db-SYSTEM_WITH_HIERARCHY").hexdigest()
    )


def test_a_draft_manifest_accepts_pending_values(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path, final=False)
    manifest = read_manifest(path)
    assert manifest.draft
    assert manifest.engine_runs[0].db_sha256 == "PENDIENTE"


def test_an_unknown_top_level_key_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["surprise"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="unknown top-level"):
        read_manifest(path)


def test_a_duplicate_configuration_window_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["configurations"][0]["runs"].append(data["configurations"][0]["runs"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="duplicate"):
        read_manifest(path)


def test_pending_in_a_final_manifest_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["configurations"][0]["runs"][0]["db_sha256"] = "PENDIENTE"
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="PENDIENTE"):
        read_manifest(path)


def test_an_unknown_configuration_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["configurations"][0]["configuration"] = "SOMETHING_ELSE"
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="not one of"):
        read_manifest(path)


def test_a_path_escape_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["configurations"][0]["runs"][0]["db_file"] = "../outside.db"
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="without"):
        read_manifest(path)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    path, files = _manifest(tmp_path)
    files["mask"].unlink()
    with pytest.raises(VetoManifestError, match="missing file"):
        verify_files(read_manifest(path))


def test_a_wrong_mask_hash_is_refused(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["price_mask"]["sha256"] = "b" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(VetoManifestError, match="SHA-256 mismatch"):
        verify_files(read_manifest(path))


def test_the_configuration_slug_is_closed_and_never_inferred_from_the_arm() -> None:
    assert configuration_slug("SYSTEM_WITH_HIERARCHY") == "system_with_hierarchy"
    assert configuration_iri("SYSTEM_WITH_HIERARCHY") == "Configuration_SystemWithHierarchy"
    with pytest.raises(VetoManifestError, match="not one of"):
        configuration_slug("TOPN_MV_GUARD_NO_NLP")


def test_graph_names_use_the_configuration_and_admit_c1() -> None:
    assert (
        backtest_graph_name("final", "P1", "SYSTEM_WITH_HIERARCHY")
        == "urn:graph:derived:backtest:final:P1:system_with_hierarchy"
    )
    assert (
        selection_graph_name("final", "C1", "SYSTEM_WITHOUT_HIERARCHY")
        == "urn:graph:derived:backtest:selection:final:C1:system_without_hierarchy"
    )
    assert meta_graph_name("final") == "urn:graph:derived:backtest:meta:final"
    assert (
        aggregates_graph_name("final", "MARKOWITZ_BASE")
        == "urn:graph:derived:backtest:aggregates:final:markowitz_base"
    )
    assert external_graph_name("final") == "urn:graph:derived:backtest:external:final"
    assert entity_stem("final", "C1", "SYSTEM_WITH_HIERARCHY") == ("final_C1_system_with_hierarchy")


def _rows() -> dict[str, list[dict[str, Any]]]:
    """Two books of one window: the configured System and its twin."""
    return {
        "v_book": [
            {
                "book_id": 3,
                "backtest_run_id": 1,
                "window_id": "P1",
                "arm_code": "TOPN_MV_GUARD_NO_NLP",
            },
            {"book_id": 2, "backtest_run_id": 1, "window_id": "P1", "arm_code": "TOPN_MV_NOGUARD"},
        ],
        "v_guard_action": [
            {"action_id": 1, "book_id": 3, "alert_id": 10, "status": "APPLIED"},
            {"action_id": 2, "book_id": 3, "alert_id": 11, "status": "ARM_DISABLED"},
            {"action_id": 3, "book_id": 2, "alert_id": 20, "status": "APPLIED"},
        ],
        "v_guard_alert": [
            {"alert_id": 10, "window_id": "P1"},
            {"alert_id": 11, "window_id": "P1"},
            {"alert_id": 20, "window_id": "P1"},
        ],
        "v_book_rebalance": [
            {"rebalance_id": 1, "book_id": 3},
            {"rebalance_id": 2, "book_id": 2},
        ],
        "v_book_weight_daily": [{"book_id": 3}, {"book_id": 2}],
        "v_book_daily_performance": [{"book_id": 3}, {"book_id": 2}],
        "v_portfolio_period_summary": [{"book_id": 3}, {"book_id": 2}],
        "v_backtest_test": [
            {"window_id": "P1", "arm_a": "TOPN_MV_GUARD_NO_NLP", "arm_b": "MARKOWITZ_BASE"},
            {"window_id": "P1", "arm_a": "MARKOWITZ_BASE_GUARD", "arm_b": "MARKOWITZ_BASE"},
            {"window_id": "P1", "arm_a": "TOPN_MV_GUARD_NO_NLP", "arm_b": "MARKOWITZ_BASE_GUARD"},
        ],
    }


def test_the_filter_keeps_only_the_manifest_book_and_loaded_actions() -> None:
    rows, report = filter_rows(
        _rows(),
        configuration="SYSTEM_WITH_HIERARCHY",
        window="P1",
        book_code="TOPN_MV_GUARD_NO_NLP",
        book_id=3,
    )
    assert [row["book_id"] for row in rows["v_book"]] == [3]
    assert {row["alert_id"] for row in rows["v_guard_alert"]} == {10}
    assert [row["action_id"] for row in rows["v_guard_action"]] == [1]
    assert len(rows["v_backtest_test"]) == 1
    assert rows["v_backtest_test"][0]["arm_b"] == "MARKOWITZ_BASE"
    assert report.removed["v_guard_alert"] == 2


def test_a_book_code_that_does_not_match_the_manifest_is_refused() -> None:
    with pytest.raises(VetoManifestError, match="expected one v_book row"):
        filter_rows(
            _rows(),
            configuration="SYSTEM_WITH_HIERARCHY",
            window="P1",
            book_code="TOPN_MV_GUARD",
            book_id=3,
        )


def test_the_filter_admits_c1() -> None:
    rows = _rows()
    for row in rows["v_book"]:
        row["window_id"] = "C1"
    for row in rows["v_guard_alert"]:
        row["window_id"] = "C1"
    for row in rows["v_backtest_test"]:
        row["window_id"] = "C1"
    filtered, _ = filter_rows(
        rows,
        configuration="SYSTEM_WITH_HIERARCHY",
        window="C1",
        book_code="TOPN_MV_GUARD_NO_NLP",
        book_id=3,
    )
    assert filtered["v_book"][0]["window_id"] == "C1"
