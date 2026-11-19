"""The SYSTEM_LIVE day loader: adapter, replace-per-day, masks and exit codes (Work item 47)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF

from kg_store import gate
from kg_store.graphdb import GraphDBError
from projection import load_live
from projection.live_manifest import (
    live_graph_names,
    read_live_manifest,
    staging_graph_names,
)
from projection.load_veto import LoadResult, ShaclFailed, VetoBatch, VetoGraph
from projection.veto_manifest import (
    backtest_graph_name,
    meta_graph_name,
    selection_graph_name,
)

SUM_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
CONTEXT = (
    "urn:graph:tbox",
    "urn:graph:reference",
    "urn:graph:rules:catalog",
    "urn:graph:universe:2026-Q4",
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(folder: Path) -> dict[str, tuple[str, bytes]]:
    return {
        "rankings_file": ("H1B-A2g-LIVE.rankings.json", b"{}"),
        "panels_file": ("H1B-A2g-LIVE.panels.json", b"{}"),
        "scales_file": ("H1B-A2g-LIVE.scales.json", b"[]"),
        "retention_file": ("H1B-A2g-LIVE.retention.jsonl", b""),
        "verification_file": ("H1B-A2g-LIVE.verification.json", b"{}"),
        "news_actions_file": ("H1B-A2g-LIVE.news.json", b"{}"),
        "bull_mode_file": ("H1B-A2g-LIVE.bull_mode.json", b"{}"),
        "manager_calls_file": ("H1B-A2g-LIVE.manager_calls.jsonl", b""),
        "jsonl_file": ("H1B-A2g-LIVE.cartera_v1_3.kg.jsonl", b""),
    }


def _manifest(
    folder: Path, day: str = "2026-10-16", formation: str = "2026-10-15"
) -> dict[str, Any]:
    files = _files(folder)
    for _, (name, data) in files.items():
        (folder / name).write_bytes(data)
    db = folder.parent / f"{day}.db"
    db.write_bytes(b"db")
    mask = folder.parent / "tiingo_assets.csv"
    mask.write_text(
        "asset_id,ticker,tiingo_price_rows,first_date,last_date\n1,AAA,10,2020-01-01,2020-01-10\n"
    )
    return {
        "configuration": "SYSTEM_LIVE",
        "window": "LIVE",
        "day": day,
        "formation": formation,
        "run_id": "H1B-A2g-LIVE",
        "book_code": "TOPN_MV_GUARD",
        "book_id": 3,
        "db_file": str(db),
        "db_sha256": _hash(db.read_bytes()),
        "price_mask_file": str(mask),
        "price_mask_sha256": _hash(mask.read_bytes()),
        "files_sha256": {field: _hash(data) for field, (_, data) in files.items()},
        **{field: name for field, (name, _) in files.items()},
        "operator": "live-operator-v2",
    }


def _write_sums(folder: Path) -> None:
    lines = []
    for path in sorted(folder.iterdir()):
        if path.name == "SHA256SUMS":
            continue
        lines.append(f"{_hash(path.read_bytes())}  {path.name}")
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def _folder(tmp_path: Path, day: str = "2026-10-16", formation: str = "2026-10-15") -> Path:
    folder = tmp_path / f"graph_export_{day}"
    folder.mkdir()
    manifest = _manifest(folder, day, formation)
    (folder / "manifest_live.json").write_text(json.dumps(manifest, indent=1))
    _write_sums(folder)
    return folder


def _rewrite_manifest(folder: Path, change: dict[str, Any]) -> None:
    path = folder / "manifest_live.json"
    manifest = json.loads(path.read_text())
    manifest.update(change)
    path.write_text(json.dumps(manifest, indent=1))
    _write_sums(folder)


def _turtle(day: str, kind: str) -> bytes:
    return f'<urn:example:{kind}> <urn:example:day> "{day}" .\n'.encode()


def _result(day: str) -> LoadResult:
    meta = VetoGraph(meta_graph_name("live"), _turtle(day, "meta"), 1, "meta", None, None)
    m018 = VetoGraph(
        backtest_graph_name("live", "LIVE", "SYSTEM_LIVE"),
        _turtle(day, "m018"),
        1,
        "m018",
        "SYSTEM_LIVE",
        "LIVE",
    )
    selection = VetoGraph(
        selection_graph_name("live", "LIVE", "SYSTEM_LIVE"),
        _turtle(day, "selection"),
        1,
        "selection",
        "SYSTEM_LIVE",
        "LIVE",
    )
    batch = VetoBatch(("live", "SYSTEM_LIVE", "LIVE"), [m018, selection])
    return LoadResult((batch,), meta)


def _build_for(monkeypatch: pytest.MonkeyPatch, days: tuple[str, ...]) -> None:
    def build(manifest: Any, label: str, **kwargs: Any) -> LoadResult:
        day = json.loads(manifest.path.read_text())["day"]
        assert day in days
        return _result(day)

    monkeypatch.setattr(load_live, "build_delivery", build)


def _fake_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    def plan(  # noqa: PLR0913 -- mirrors the gate signature the loader calls
        db: Any,
        data: bytes,
        graph: str,
        directory: Path | None = None,
        context: rdflib.Graph | None = None,
        *,
        allow_existing: bool = False,
        context_only: bool = False,
    ) -> gate.IngestPlan:
        batch = gate.parse_batch(data)
        return gate.IngestPlan(graph, batch, gate.IngestPlanStatus.WOULD_WRITE, len(batch))

    monkeypatch.setattr(load_live.gate, "plan", plan)


def _store(fail_on_move: bool = False) -> DatasetStore:
    dataset = rdflib.Dataset(default_union=False)
    for name in CONTEXT:
        graph = dataset.graph(rdflib.URIRef(name))
        graph.add((rdflib.URIRef("urn:example:context"), RDF.type, rdflib.URIRef("urn:example:T")))
    return DatasetStore(dataset, fail_on_move=fail_on_move)


def _use_store(monkeypatch: pytest.MonkeyPatch, store: DatasetStore) -> None:
    monkeypatch.setattr(load_live, "_open_store", lambda repository: store)
    monkeypatch.setattr(load_live, "announce_target", lambda db: None)
    monkeypatch.setattr(load_live, "universe_assets", lambda path: {})
    monkeypatch.setattr(load_live, "load_guard_catalog", lambda path: None)
    monkeypatch.setattr(load_live, "_shacl_context", lambda assets, catalog: (None, rdflib.Graph()))


def _state(store: DatasetStore) -> dict[str, str]:
    state: dict[str, str] = {}
    for name in live_graph_names():
        graph = store.dataset.graph(rdflib.URIRef(name))
        lines = sorted(
            f"{subject.n3()} {predicate.n3()} {obj.n3()} ." for subject, predicate, obj in graph
        )
        state[name] = _hash("\n".join(lines).encode())
    return state


def _last_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out.strip().splitlines()
    assert out
    return cast(dict[str, Any], json.loads(out[-1]))


def _run(folder: Path, day: str = "2026-10-16", *extra: str) -> int:
    return load_live.main(
        ["--folder", str(folder), "--day", day, "--assets-db", "unused.db", *extra]
    )


def test_empty_manager_calls_and_retention_are_accepted(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    live = read_live_manifest(folder)
    assert live.files["manager_calls_file"].read_bytes() == b""
    assert live.files["retention_file"].read_bytes() == b""
    assert live.file_hashes[live.files["manager_calls_file"]] == SUM_EMPTY
    assert live.file_hashes[live.files["retention_file"]] == SUM_EMPTY


def test_dry_run_prints_the_json_last_and_contacts_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _build_for(monkeypatch, ("2026-10-16",))
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("dry run"))
    assert _run(folder) == 0
    payload = _last_json(capsys)
    assert payload == {
        "day": "2026-10-16",
        "repository": "portfolio_live",
        "graphs": 3,
        "triples": 3,
        "shacl": "conforms",
        "ok": True,
    }


def test_same_day_twice_gives_the_same_graphs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    _build_for(monkeypatch, ("2026-10-16",))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    assert _run(folder, "2026-10-16", "--write") == 0
    first = _state(store)
    assert _last_json(capsys)["ok"] is True
    assert _run(folder, "2026-10-16", "--write") == 0
    second = _state(store)
    assert first == second
    assert not [name for name in staging_graph_names() if store.explicit_graph_sizes().get(name)]


def test_day_d_then_d_plus_one_leaves_only_d_plus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _folder(tmp_path, "2026-10-16")
    second = _folder(tmp_path, "2026-10-17")
    store = _store()
    _build_for(monkeypatch, ("2026-10-16", "2026-10-17"))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    assert _run(first, "2026-10-16", "--write") == 0
    day_one = _state(store)
    assert _run(second, "2026-10-17", "--write") == 0
    day_two = _state(store)

    fresh = _store()
    _use_store(monkeypatch, fresh)
    assert _run(second, "2026-10-17", "--write") == 0
    assert day_two == _state(fresh)
    assert day_one != day_two


def test_wrong_folder_sha256sums_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    sums = folder / "SHA256SUMS"
    lines = sums.read_text().splitlines()
    lines[0] = "0" * 64 + "  " + lines[0].split("  ", 1)[1]
    sums.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "SHA-256 mismatch" in payload["error"]


def test_wrong_files_sha256_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    manifest["files_sha256"]["jsonl_file"] = "0" * 64
    _rewrite_manifest(folder, manifest)
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    assert "differs from SHA256SUMS" in _last_json(capsys)["error"]


def test_wrong_db_sha256_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _rewrite_manifest(folder, {"db_sha256": "0" * 64})
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    error = _last_json(capsys)["error"]
    assert "SHA-256 mismatch" in error and ".db" in error


def test_wrong_mask_sha256_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _rewrite_manifest(folder, {"price_mask_sha256": "0" * 64})
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    error = _last_json(capsys)["error"]
    assert "SHA-256 mismatch" in error and "tiingo_assets.csv" in error


def test_cli_day_must_equal_the_manifest_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-15", "--write") == 2
    assert "differs from the manifest day" in _last_json(capsys)["error"]


def test_shacl_failure_writes_nothing_and_exits_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    _use_store(monkeypatch, store)

    def fail(manifest: Any, label: str, **kwargs: Any) -> LoadResult:
        raise ShaclFailed("SHACL failed for SYSTEM_LIVE/LIVE")

    monkeypatch.setattr(load_live, "build_delivery", fail)
    assert _run(folder, "2026-10-16", "--write") == 3
    payload = _last_json(capsys)
    assert payload["shacl"] == "fails"
    assert payload["ok"] is False
    assert store.writes == []
    assert store.updates == []


def test_failure_between_staging_and_swap_keeps_the_previous_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _folder(tmp_path, "2026-10-16")
    second = _folder(tmp_path, "2026-10-17")
    store = _store()
    _build_for(monkeypatch, ("2026-10-16", "2026-10-17"))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    assert _run(first, "2026-10-16", "--write") == 0
    previous = _state(store)
    store.fail_on_move = True
    assert _run(second, "2026-10-17", "--write") == 5
    assert _state(store) == previous
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "swap failed" in payload["error"]
    sizes = store.explicit_graph_sizes()
    assert not [name for name in staging_graph_names() if sizes.get(name)]


def test_repository_portfolio_is_refused_before_any_store_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write", "--repository", "portfolio") == 4
    payload = _last_json(capsys)
    assert payload["repository"] == "portfolio"
    assert "refusing repository" in payload["error"]


def test_environment_repository_never_overrides_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    _build_for(monkeypatch, ("2026-10-16",))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    monkeypatch.setenv("KG_REPOSITORY", "portfolio")
    assert _run(folder, "2026-10-16", "--write", "--repository", "portfolio_live_scratch") == 0
    payload = _last_json(capsys)
    assert payload["repository"] == "portfolio_live_scratch"
    assert payload["ok"] is True


def test_check_store_only_plans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    _build_for(monkeypatch, ("2026-10-16",))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    assert _run(folder, "2026-10-16", "--check-store") == 0
    payload = _last_json(capsys)
    assert payload["ok"] is True
    assert store.writes == []
    assert store.updates == []


def test_a_missing_argument_still_ends_with_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert load_live.main(["--folder", "x"]) == 2
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "day" in payload["error"]


def test_no_secret_reaches_stdout_or_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    monkeypatch.setenv("KG_PASSWORD", "do-not-print-me")
    assert _run(folder, "2026-10-15", "--write") == 2
    captured = capsys.readouterr()
    assert "do-not-print-me" not in captured.out
    assert "do-not-print-me" not in captured.err


def test_context_graphs_are_required_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    store.dataset.remove_graph(rdflib.URIRef("urn:graph:tbox"))
    _build_for(monkeypatch, ("2026-10-16",))
    _use_store(monkeypatch, store)
    assert _run(folder, "2026-10-16", "--write") == 4
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "urn:graph:tbox" in payload["error"]
    assert store.updates == []


def test_staging_write_failure_keeps_the_previous_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _folder(tmp_path, "2026-10-16")
    second = _folder(tmp_path, "2026-10-17")
    store = _store()
    _build_for(monkeypatch, ("2026-10-16", "2026-10-17"))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    assert _run(first, "2026-10-16", "--write") == 0
    previous = _state(store)

    def fail_write(db: Any, plan: gate.IngestPlan) -> int:
        raise GraphDBError("simulated staging write failure")

    monkeypatch.setattr(load_live.gate, "write_batched", fail_write)
    assert _run(second, "2026-10-17", "--write") == 4
    assert _state(store) == previous
    assert _last_json(capsys)["ok"] is False
    sizes = store.explicit_graph_sizes()
    assert not [name for name in staging_graph_names() if sizes.get(name)]


def test_the_live_graph_names_are_fixed() -> None:
    assert live_graph_names() == (
        "urn:graph:derived:backtest:meta:live",
        "urn:graph:derived:backtest:live:LIVE:system_live",
        "urn:graph:derived:backtest:selection:live:LIVE:system_live",
    )
    assert staging_graph_names() == (
        "urn:graph:derived:backtest:meta:live_staging",
        "urn:graph:derived:backtest:live_staging:LIVE:system_live",
        "urn:graph:derived:backtest:selection:live_staging:LIVE:system_live",
    )


@pytest.mark.parametrize(
    ("key", "value"), [("configuration", "SYSTEM_WITH_HIERARCHY"), ("window", "P1")]
)
def test_a_non_live_configuration_or_window_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: str,
) -> None:
    folder = _folder(tmp_path)
    _rewrite_manifest(folder, {key: value})
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    assert key in _last_json(capsys)["error"]


def test_an_unknown_manifest_key_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _rewrite_manifest(folder, {"narrator_file": "x.json"})
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    assert "unknown key" in _last_json(capsys)["error"]


def test_a_missing_files_sha256_entry_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    del manifest["files_sha256"]["jsonl_file"]
    _rewrite_manifest(folder, manifest)
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    assert "missing file key" in _last_json(capsys)["error"]


def test_day_before_formation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path, "2026-10-16", "2026-10-17")
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))
    assert _run(folder, "2026-10-16", "--write") == 2
    assert "before formation" in _last_json(capsys)["error"]


def test_a_masked_asset_cannot_carry_a_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    monkeypatch.setattr(load_live, "_open_store", lambda repository: pytest.fail("no store"))

    def build(manifest: Any, label: str, **kwargs: Any) -> LoadResult:
        result = _result("2026-10-16")
        m018 = VetoGraph(
            backtest_graph_name("live", "LIVE", "SYSTEM_LIVE"),
            b'<urn:example:m018> <urn:example:day> "2026-10-16" .\n'
            b"<https://thesis.local/kg/portfolio#AAA> "
            b"<https://thesis.local/kg/portfolio#alertValue> 1 .\n",
            2,
            "m018",
            "SYSTEM_LIVE",
            "LIVE",
        )
        batch = VetoBatch(("live", "SYSTEM_LIVE", "LIVE"), [m018, result.batches[0].graphs[1]])
        return LoadResult((batch,), result.meta)

    monkeypatch.setattr(load_live, "build_delivery", build)
    assert _run(folder, "2026-10-16", "--write") == 2
    assert "price mask forbids" in _last_json(capsys)["error"]


def test_a_missing_universe_graph_is_a_store_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    store.dataset.remove_graph(rdflib.URIRef("urn:graph:universe:2026-Q4"))
    _build_for(monkeypatch, ("2026-10-16",))
    _use_store(monkeypatch, store)
    assert _run(folder, "2026-10-16", "--write") == 4
    assert "urn:graph:universe:*" in _last_json(capsys)["error"]


def test_the_store_check_finds_a_masked_asset_price() -> None:
    store = _store()
    graph = store.dataset.graph(rdflib.URIRef(live_graph_names()[1]))
    graph.add(
        (
            rdflib.URIRef("https://thesis.local/kg/portfolio#AAA"),
            rdflib.URIRef("https://thesis.local/kg/portfolio#alertValue"),
            rdflib.Literal("1"),
        )
    )
    failures = load_live._masked_store_prices(cast(Any, store), ("AAA",))
    assert failures
    assert "AAA" in failures[0]


def test_a_post_swap_verification_error_exits_five(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    store = _store()
    _build_for(monkeypatch, ("2026-10-16",))
    _fake_plan(monkeypatch)
    _use_store(monkeypatch, store)
    monkeypatch.setattr(
        load_live,
        "_verify_after_swap",
        lambda db, graphs, masked: (_ for _ in ()).throw(GraphDBError("simulated read failure")),
    )
    assert _run(folder, "2026-10-16", "--write") == 5
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "post-swap" in payload["error"]
