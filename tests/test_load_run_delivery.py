"""Delivery loading: six windows, manifest, configuration and the metadata graph (Work item 35)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import rdflib
from fixtures.backtest_rows import ASSETS, backtest_db, load_catalog, scenario_rows
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, RDFS
from rdflib.term import URIRef

from kg_store import gate
from kg_store.graphdb import GraphDBError
from projection import load_run, run_metadata
from projection.backtest import validation_context
from projection.delivery import (
    FINAL_WINDOWS,
    Delivery,
    RunConfiguration,
    WindowSource,
    config_path,
    load_config,
    read_config,
    read_manifest,
    verify_manifest,
)
from projection.disk_space import DiskMonitor, DiskSpaceError, free_disk_percent

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
LABEL = "rule"
META = f"urn:graph:derived:backtest:meta:{LABEL}"
WINDOWS: dict[str, tuple[str, str]] = {
    "P1": ("2022-01-03", "2022-10-12"),
    "H1": ("2022-10-13", "2023-10-26"),
    "P3": ("2023-10-27", "2024-08-02"),
    "H2": ("2024-08-05", "2025-02-18"),
    "P2": ("2025-02-19", "2025-09-23"),
    "H3": ("2025-09-24", "2026-10-15"),
}
BODY = (
    "Portfolio system configuration Y2 (round 4).\n"
    "Every 21 trading sessions the book is rebuilt as 50% SPY (core) and 50% satellite.\n"
    'A hard veto excludes "the name" & keeps the rest.\n'
)


def _rows(window: str) -> dict[str, list[dict[str, Any]]]:
    rows = scenario_rows(window)
    rows["backtest_run"][0]["d_start"], rows["backtest_run"][0]["d_end"] = WINDOWS[window]
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _config_text(
    *,
    label: str = LABEL,
    body: str = BODY,
    extra: str = "",
    config_label: str | None = None,
) -> str:
    return (
        "---\n"
        f"label: {config_label or label}\n"
        "config_id: Y2\n"
        "code_commit: 537e864\n"
        "pr: 192\n"
        "results_doc: docs/backtest_v4_experiments_results.md\n"
        "status: candidate (the system may still change in round 5; the final delivery will be "
        'label "final")\n'
        f"{extra}"
        "---\n"
        "\n"
        f"{body}"
    )


def _delivery(
    tmp_path: Path,
    *,
    windows: tuple[str, ...] = FINAL_WINDOWS,
    config_text: str | None = None,
    manifest: bool = True,
) -> tuple[Path, dict[str, Path]]:
    paths = {
        window: backtest_db(
            tmp_path,
            name=f"{LABEL}_{window}.db",
            window=window,
            rows=_rows(window),
        )
        for window in windows
    }
    (tmp_path / f"config_{LABEL}.md").write_text(
        config_text if config_text is not None else _config_text(), encoding="utf-8"
    )
    if manifest:
        (tmp_path / "SHA256SUMS").write_text(
            "".join(f"{_sha256(path)}  {path.name}\n" for path in paths.values()),
            encoding="utf-8",
        )
    return tmp_path, paths


def _store(*, fail_graph: str | None = None, low_disk: bool = False) -> DatasetStore:
    dataset = rdflib.Dataset(default_union=True)
    context = dataset.graph(URIRef("urn:graph:test:context"))
    for triple in validation_context(ASSETS, load_catalog()):
        context.add(triple)
    if low_disk:
        return LowDiskStore(dataset, fail_graph or "")
    return DatasetStore(dataset)


def _graph(store: DatasetStore, name: str) -> rdflib.Graph:
    return store.dataset.graph(URIRef(name))


def _has_graph(store: DatasetStore, name: str) -> bool:
    return any(str(graph.identifier) == name and len(graph) for graph in store.dataset.graphs())


def _patch_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)


class LowDiskStore(DatasetStore):
    """A store whose write of one graph hits GraphDB's critical-disk HTTP 500."""

    def __init__(self, dataset: rdflib.Dataset, fail_graph: str) -> None:
        super().__init__(dataset)
        self.fail_graph = fail_graph

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        if graph == self.fail_graph:
            raise GraphDBError(
                "POST /statements -> HTTP 500: Critically low disk space! The repository cannot "
                "accept writes."
            )
        super().add(data, content_type, graph)


def test_a_six_window_delivery_is_ordered_written_and_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path)
    store = _store()
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--write"]) == 0
    printed = capsys.readouterr()
    assert "manifest: 6 file(s) verified" in printed.out
    positions = [
        printed.out.index(f"dry run m018: {folder / f'{LABEL}_{window}.db'}")
        for window in FINAL_WINDOWS
    ]
    assert positions == sorted(positions)
    assert printed.out.index(f"dry run m018: {folder / 'rule_P3.db'}") < printed.out.index(
        f"dry run m018: {folder / 'rule_P2.db'}"
    )
    assert _has_graph(store, META)
    assert [graph for graph, _ in store.writes][-1] == META
    meta = _graph(store, META)
    runs = set(meta.subjects(RDF.type, KG.BacktestRun))
    assert len(runs) == 6
    configs = set(meta.subjects(RDF.type, KG.RunConfiguration))
    assert len(configs) == 1
    config = next(iter(configs))
    assert str(meta.value(config, RDFS.comment)) == BODY
    assert str(meta.value(config, KG.configPr)) == "192"
    assert str(meta.value(config, KG.configCodeCommit)) == "537e864"
    for window in FINAL_WINDOWS:
        run = KG[f"BacktestRun_{LABEL}_{window}"]
        assert meta.value(run, KG.windowId) == rdflib.Literal(window)
        assert meta.value(run, KG.sourceFile) == rdflib.Literal(f"{LABEL}_{window}.db")
        assert len(str(meta.value(run, KG.sourceSha256))) == 64
        assert meta.value(run, KG.runConfiguration) == config
    assert "30/30" in printed.out
    assert "pilot mode" not in printed.err


def test_a_manifest_mismatch_stops_before_the_store_is_contacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, paths = _delivery(tmp_path)
    lines = (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    name = f"{LABEL}_P1.db"
    lines = [
        line.replace(_sha256(paths["P1"]), "0" * 64) if line.endswith(name) else line
        for line in lines
    ]
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        load_run,
        "_open_check_store",
        lambda: pytest.fail("the store must not be contacted before the manifest passes"),
    )
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--check-store"]) == 2
    error = capsys.readouterr().err
    assert name in error
    assert "SHA-256 mismatch" in error
    assert "0" * 64 in error
    assert _sha256(paths["P1"]) in error


def test_a_missing_manifest_entry_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path)
    lines = [
        line
        for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        if not line.endswith(f"{LABEL}_H2.db")
    ]
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert load_run.main(["--label", LABEL, "--dir", str(folder)]) == 2
    assert "no entry in" in capsys.readouterr().err


def test_a_missing_database_file_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, paths = _delivery(tmp_path, windows=("P1", "P2"))
    missing = paths["P1"]
    missing.unlink()
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--db", str(missing)]) == 2
    assert "missing file" in capsys.readouterr().err


def test_an_unknown_window_file_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, paths = _delivery(tmp_path, windows=("P1",))
    (folder / f"{LABEL}_Q1.db").write_bytes(paths["P1"].read_bytes())
    assert load_run.main(["--label", LABEL, "--dir", str(folder)]) == 2
    error = capsys.readouterr().err
    assert "unknown window 'Q1'" in error
    assert "P1, H1, P3, H2, P2, H3" in error


def test_a_missing_windows_entry_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path, windows=("P1",))
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--windows", "P1,H3"]) == 2
    assert "no database for H3" in capsys.readouterr().err


def test_a_config_label_mismatch_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(
        tmp_path, windows=("P1",), config_text=_config_text(config_label="candidate")
    )
    assert load_run.main(["--label", LABEL, "--dir", str(folder)]) == 2
    assert "differs from --label" in capsys.readouterr().err


def test_a_present_manifest_cannot_be_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path, windows=("P1",))
    assert (
        load_run.main(["--label", LABEL, "--dir", str(folder), "--no-manifest", "--no-config"]) == 2
    )
    assert "cannot ignore a present delivery file" in capsys.readouterr().err


def test_a_pilot_folder_needs_both_legacy_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path, windows=("P1",), manifest=False)
    (folder / f"config_{LABEL}.md").unlink()
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--no-manifest"]) == 2
    assert "go together" in capsys.readouterr().err
    assert (
        load_run.main(["--label", LABEL, "--dir", str(folder), "--no-manifest", "--no-config"]) == 0
    )


def test_the_configuration_body_and_strings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / f"config_{LABEL}.md"
    path.write_text(
        _config_text(
            extra="unknown_key: ignored\n",
            body='Line one with "quotes" & ampersands.\nLine two.\n',
        ),
        encoding="utf-8",
    )
    config, warnings = load_config(path, LABEL)
    assert isinstance(config, RunConfiguration)
    assert config.pr == "192"
    assert config.code_commit == "537e864"
    assert config.body == 'Line one with "quotes" & ampersands.\nLine two.\n'
    assert warnings == [f"{path}: unknown key 'unknown_key' ignored"]


def test_the_configuration_rejects_an_empty_body(tmp_path: Path) -> None:
    path = tmp_path / f"config_{LABEL}.md"
    path.write_text(_config_text(body=""), encoding="utf-8")
    with pytest.raises(ValueError, match="body is empty"):
        load_config(path, LABEL)


def test_a_second_write_is_skipped_and_does_not_append(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path, windows=("P1", "P2"))
    store = _store()
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--write"]) == 0
    writes = list(store.writes)
    capsys.readouterr()
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--write"]) == 0
    printed = capsys.readouterr()
    assert f"pre-flight {load_run.ALREADY_IN_STORE}: {META}" in printed.out
    assert store.writes == writes


def test_the_metadata_gate_refuses_a_real_second_write(tmp_path: Path) -> None:
    folder, paths = _delivery(tmp_path, windows=("P1",))
    info = run_metadata.read_run_info(paths["P1"], LABEL)
    config = read_config(config_path(folder, LABEL), LABEL)
    manifest = read_manifest(folder / "SHA256SUMS")
    hashes = verify_manifest(manifest, [paths["P1"]])
    projection = run_metadata.build_metadata(LABEL, [info], hashes, config)
    store = _store()
    plan = run_metadata.plan_metadata(store, projection)  # type: ignore[arg-type]
    gate.write(store, plan)  # type: ignore[arg-type]
    again = run_metadata.plan_metadata(store, projection)  # type: ignore[arg-type]
    assert again.status.value == "already-in-the-store"
    with pytest.raises(gate.IngestRejected):
        gate.write(store, again)  # type: ignore[arg-type]


def test_a_low_disk_write_names_the_graph_and_the_one_graph_drop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_inputs(monkeypatch)
    folder, _ = _delivery(tmp_path, windows=("P1",))
    selection = "urn:graph:derived:backtest:selection:rule:P1:1"
    store = _store(fail_graph=selection, low_disk=True)
    monkeypatch.setattr(load_run, "open_store", lambda _args: store)
    assert load_run.main(["--label", LABEL, "--dir", str(folder), "--write"]) == 1
    error = capsys.readouterr().err
    assert "critically low" in error.lower()
    assert selection in error
    assert f"DROP GRAPH <{selection}>" in error
    assert "DROP GRAPH <urn:graph:derived:backtest:rule:P1:1>" in error


class _DiskStore:
    host = "http://store.invalid"

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def _request(self, *_args: object, **_kwargs: object) -> bytes:
        if isinstance(self.payload, Exception):
            raise self.payload
        return json.dumps(self.payload).encode()


def test_the_disk_probe_uses_a_free_total_pair() -> None:
    store = _DiskStore({"freeSpace": 90, "totalSpace": 100})
    assert free_disk_percent(store) == pytest.approx(90.0)  # type: ignore[arg-type]
    monitor = DiskMonitor(store, 8.0)  # type: ignore[arg-type]
    monitor.check("before --write", before_write=True)


def test_the_disk_probe_refuses_below_the_threshold() -> None:
    store = _DiskStore({"freeSpace": 4, "totalSpace": 100})
    monitor = DiskMonitor(store, 8.0)  # type: ignore[arg-type]
    with pytest.raises(DiskSpaceError, match=r"below the 8\.0% minimum"):
        monitor.check("before --write", before_write=True)


def test_a_missing_disk_endpoint_prints_the_reminder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _DiskStore(GraphDBError("406 Not Acceptable"))
    monitor = DiskMonitor(store, 8.0)  # type: ignore[arg-type]
    monitor.check("before --write", before_write=True)
    assert "df -h" in capsys.readouterr().out


def test_a_window_over_thirty_minutes_is_flagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    window = WindowSource(
        "P1", tmp_path / "rule_P1.db", "2022-01-03", "2022-10-12", 1, "2026-10-31"
    )
    delivery = Delivery(LABEL, tmp_path, [window])
    load_run._print_window_timings(delivery, {"P1": 1801.0})
    printed = capsys.readouterr()
    assert "STOP AND ASK upstream: P1" in printed.out
    assert "STOP AND ASK upstream: P1" in printed.err
