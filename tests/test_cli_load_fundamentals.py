"""``cli/load_fundamentals.py`` and the fundamentals CLI (Work item 45)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from fixtures.fundamentals_rows import write_fixture

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection import fundamentals
from projection.fundamentals import graph_name, project, validation_graph

CLI = Path(__file__).resolve().parent.parent / "cli" / "load_fundamentals.py"


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": "test",
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
        "--mask",
        "--universe-db",
        "--check-store",
        "--write",
        "--to-production",
    ):
        assert flag in result.stdout


def test_a_missing_dir_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "final")
    assert result.returncode == 2
    assert "--dir" in result.stderr


def test_impossible_flag_combinations_exit_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--dir", str(tmp_path), "--check-store", "--write")
    assert result.returncode == 2
    assert "--check-store only reads" in result.stderr
    result = _run(tmp_path, "--dir", str(tmp_path), "--check-store", "--to-production")
    assert result.returncode == 2
    assert "--check-store never writes" in result.stderr
    result = _run(tmp_path, "--dir", str(tmp_path), "--to-production")
    assert result.returncode == 2
    assert "--to-production only matters with --write" in result.stderr


def test_a_label_outside_the_pattern_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, "--label", "Final", "--dir", str(tmp_path))
    assert result.returncode == 2
    assert "run label" in result.stderr


def test_a_manifest_mismatch_exits_1(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)
    result = _run(
        tmp_path,
        "--dir",
        str(fixture.directory),
        "--mask",
        str(fixture.mask),
        "--universe-db",
        str(fixture.universe_db),
    )
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_a_dry_run_prints_the_counts_and_shacl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = write_fixture(tmp_path)
    monkeypatch.setattr(fundamentals, "MANIFEST_SHA256", fixture.manifest_sha256)
    monkeypatch.setattr(fundamentals, "MASK_SHA256", fixture.mask_sha256)
    code = fundamentals.main(
        [
            "--label",
            "final",
            "--dir",
            str(fixture.directory),
            "--mask",
            str(fixture.mask),
            "--universe-db",
            str(fixture.universe_db),
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "urn:graph:derived:fundamentals:final" in output
    assert "filings: 4; metric sets: 4; assessments: 4" in output
    assert "triples: 147" in output
    assert "masked flags: 2" in output
    assert "SHACL: conforms (gate.validate)" in output
    assert "peak memory:" in output
    assert "timing: total" in output


def test_a_production_write_without_the_opt_in_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = write_fixture(tmp_path)
    monkeypatch.setattr(fundamentals, "MANIFEST_SHA256", fixture.manifest_sha256)
    monkeypatch.setattr(fundamentals, "MASK_SHA256", fixture.mask_sha256)
    monkeypatch.setenv("KG_HOST", "http://host.invalid")
    monkeypatch.setenv("KG_REPOSITORY", "portfolio")
    with pytest.raises(SystemExit) as info:
        fundamentals.main(
            [
                "--dir",
                str(fixture.directory),
                "--mask",
                str(fixture.mask),
                "--universe-db",
                str(fixture.universe_db),
                "--write",
            ]
        )
    assert info.value.code == 2


def test_check_store_reads_the_plan_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = write_fixture(tmp_path)
    monkeypatch.setattr(fundamentals, "MANIFEST_SHA256", fixture.manifest_sha256)
    monkeypatch.setattr(fundamentals, "MASK_SHA256", fixture.mask_sha256)
    monkeypatch.setenv("KG_HOST", "http://host.invalid")
    monkeypatch.setenv("KG_REPOSITORY", "test")
    data = fundamentals.load_file(
        "final",
        fixture.directory,
        mask_path=fixture.mask,
        universe_db=fixture.universe_db,
    )
    dataset = rdflib.Dataset()
    for triple in validation_graph(data):
        dataset.default_graph.add(triple)
    store = DatasetStore(dataset)
    monkeypatch.setattr(fundamentals.GraphDB, "from_env", classmethod(lambda cls: store))
    code = fundamentals.main(
        [
            "--dir",
            str(fixture.directory),
            "--mask",
            str(fixture.mask),
            "--universe-db",
            str(fixture.universe_db),
            "--check-store",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert f"pre-flight: would-be-written: {graph_name('final')}" in output
    assert store.writes == []
    assert not any("INSERT" in query or "DELETE" in query for query in store.queries)
    assert len(project(data)) == 147
    plan = gate.plan(cast(GraphDB, store), project(data).turtle(), graph_name("final"))
    assert plan.status is gate.IngestPlanStatus.WOULD_WRITE
