"""The live day's optional news rows, news actions and SPY series (Work item 50)."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.agents_delivery import NEWS_COLUMNS, news_payload, news_row
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, XSD

from etl import config
from kg_store import gate
from projection import load_live
from projection.live_extras import LiveExtrasError, build_extras, performance_dates
from projection.live_manifest import (
    LiveManifestError,
    live_graph_names,
    news_actions_graph_name,
    news_graph_name,
    read_live_manifest,
    spy_graph_name,
    staging_graph_names,
)
from projection.load_veto import LoadResult, VetoBatch, VetoGraph
from projection.veto_manifest import backtest_graph_name, meta_graph_name, selection_graph_name

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
DAY = "2026-10-19"
FORMATION = "2026-10-15"
SESSIONS = ("2026-10-15", "2026-10-16", "2026-10-19")
CONTEXT = (
    "urn:graph:tbox",
    "urn:graph:reference",
    "urn:graph:rules:catalog",
    "urn:graph:universe:2026-Q4",
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _spy_csv(sessions: tuple[str, ...] = SESSIONS, window: str = "LIVE") -> bytes:
    lines = ["window,date,daily_total_return,value"]
    value = 1.0
    for index, day in enumerate(sessions):
        daily = 0.001 * (index + 1)
        value *= 1 + daily
        lines.append(f"{window},{day},{daily},{value}")
    return ("\n".join(lines) + "\n").encode()


def _news_rows(*rows: dict[str, Any]) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode()


def _folder(  # noqa: PLR0913 -- each optional part is one switch of the test day
    tmp_path: Path,
    *,
    day: str = DAY,
    news: bool = True,
    spy: bool = True,
    rows: bytes | None = None,
    spy_data: bytes | None = None,
) -> Path:
    folder = tmp_path / f"graph_export_{day}"
    folder.mkdir(parents=True)
    files = {
        "rankings_file": ("H1B-A2g-LIVE.rankings.json", b"{}"),
        "panels_file": ("H1B-A2g-LIVE.panels.json", b"{}"),
        "scales_file": ("H1B-A2g-LIVE.scales.json", b"[]"),
        "retention_file": ("H1B-A2g-LIVE.retention.jsonl", b""),
        "verification_file": ("H1B-A2g-LIVE.verification.json", b"{}"),
        "news_actions_file": ("H1B-A2g-LIVE.news.json", json.dumps(news_payload()).encode()),
        "bull_mode_file": ("H1B-A2g-LIVE.bull_mode.json", b"{}"),
        "manager_calls_file": ("H1B-A2g-LIVE.manager_calls.jsonl", b""),
        "jsonl_file": ("H1B-A2g-LIVE.cartera_v1_3.kg.jsonl", b'{"kind": "decision"}\n'),
    }
    for name, data in files.values():
        (folder / name).write_bytes(data)
    db = tmp_path / f"{day}.db"
    db.write_bytes(b"db")
    mask = tmp_path / "tiingo_assets.csv"
    mask.write_text(
        "asset_id,ticker,tiingo_price_rows,first_date,last_date\n9,ZZZ,10,2020-01-01,2020-01-10\n"
    )
    manifest: dict[str, Any] = {
        "configuration": "SYSTEM_LIVE",
        "window": "LIVE",
        "day": day,
        "formation": FORMATION,
        "run_id": "H1B-A2g-LIVE",
        "book_code": "TOPN_MV_GUARD",
        "book_id": 3,
        "db_file": str(db),
        "db_sha256": _hash(b"db"),
        "price_mask_file": str(mask),
        "price_mask_sha256": _hash(mask.read_bytes()),
        "files_sha256": {field: _hash(data) for field, (_, data) in files.items()},
        **{field: name for field, (name, _) in files.items()},
        "operator": "live-operator-v2",
    }
    if news:
        data = rows if rows is not None else _news_rows(news_row())
        (folder / "news").mkdir()
        (folder / "news" / "news_rows.jsonl").write_bytes(data)
        manifest["news_rows_file"] = {
            "file": "news/news_rows.jsonl",
            "sha256": _hash(data),
            "rows": max(1, data.count(b"\n")),
            "model_revision": "rev1",
            "columns": NEWS_COLUMNS,
        }
        manifest["files_sha256"]["news_rows_file"] = _hash(data)
    if spy:
        data = spy_data if spy_data is not None else _spy_csv()
        (folder / "series_diarias_referencia").mkdir()
        (folder / "series_diarias_referencia" / "spy_daily.csv").write_bytes(data)
        manifest["spy_series_file"] = "series_diarias_referencia/spy_daily.csv"
        manifest["files_sha256"]["spy_series_file"] = _hash(data)
    (folder / "manifest_live.json").write_text(json.dumps(manifest, indent=1))
    _write_sums(folder)
    return folder


def _write_sums(folder: Path) -> None:
    lines = [
        f"{_hash(path.read_bytes())}  {path.relative_to(folder).as_posix()}"
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def _rewrite_manifest(folder: Path, change: dict[str, Any]) -> None:
    path = folder / "manifest_live.json"
    manifest = json.loads(path.read_text())
    manifest.update(change)
    path.write_text(json.dumps(manifest, indent=1))
    _write_sums(folder)


def _dates(*days: str) -> tuple[datetime.date, ...]:
    return tuple(datetime.date.fromisoformat(day) for day in days)


# --- manifest -----------------------------------------------------------------------------------


def test_the_optional_files_are_read_from_sub_folders(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path))
    assert live.news_rows is not None
    assert live.news_rows.path.name == "news_rows.jsonl"
    assert live.spy_series is not None
    assert live.spy_series.name == "spy_daily.csv"
    assert live.hashes[live.news_rows.path] == live.news_rows.sha256


def test_a_day_without_the_optional_files_still_reads(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path, news=False, spy=False))
    assert live.news_rows is None
    assert live.spy_series is None


def test_an_optional_file_needs_its_files_sha256_entry(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    del manifest["files_sha256"]["spy_series_file"]
    _rewrite_manifest(folder, {"files_sha256": manifest["files_sha256"]})
    with pytest.raises(LiveManifestError, match="missing file key"):
        read_live_manifest(folder)


def test_a_files_sha256_entry_without_its_file_key_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, spy=False)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    manifest["files_sha256"]["spy_series_file"] = "0" * 64
    _rewrite_manifest(folder, {"files_sha256": manifest["files_sha256"]})
    with pytest.raises(LiveManifestError, match="unknown file key"):
        read_live_manifest(folder)


def test_the_news_rows_sha256_must_match_sha256sums(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    manifest["news_rows_file"]["sha256"] = "f" * 64
    _rewrite_manifest(folder, {"news_rows_file": manifest["news_rows_file"]})
    with pytest.raises(LiveManifestError, match="differs from SHA256SUMS"):
        read_live_manifest(folder)


def test_the_news_columns_must_be_the_final_columns(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    manifest["news_rows_file"]["columns"] = list(reversed(NEWS_COLUMNS))
    _rewrite_manifest(folder, {"news_rows_file": manifest["news_rows_file"]})
    with pytest.raises(LiveManifestError, match="columns"):
        read_live_manifest(folder)


def test_a_changed_optional_file_fails_the_folder_hash(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "series_diarias_referencia" / "spy_daily.csv").write_bytes(_spy_csv()[:-5])
    with pytest.raises(LiveManifestError, match="SHA-256 mismatch"):
        read_live_manifest(folder)


# --- projection ---------------------------------------------------------------------------------


def test_news_rows_actions_and_spy_are_projected(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path))
    extras = build_extras(live, {}, _dates(*SESSIONS))
    assert extras.news_rows == 1
    assert extras.actions == 1
    assert extras.decision_dates == 1
    assert extras.spy_points == len(SESSIONS)
    assert [graph.graph for graph in extras.graphs] == [
        news_graph_name(),
        news_actions_graph_name(),
        spy_graph_name(),
    ]
    news = rdflib.Graph().parse(data=extras.news.data, format="turtle")
    item = KG["NewsItem_sub_news_10_AAA"]
    assert (item, RDF.type, KG.NewsItem) in news
    actions = rdflib.Graph().parse(data=extras.news_actions.data, format="turtle")
    runs = list(actions.subjects(RDF.type, KG.NewsRunRecord))
    assert len(runs) == 1
    assert (runs[0], KG.agentRecordOfConfiguration, KG.Configuration_SystemLive) in actions
    assert list(actions.subjects(KG.newsItem, item))
    assert all(str(value) == "LIVE" for value in actions.objects(None, KG.windowId))
    spy = rdflib.Graph().parse(data=extras.spy.data, format="turtle")
    points = set(spy.subjects(RDF.type, KG.DailySeriesPoint))
    assert len(points) == len(SESSIONS)
    assert {str(value) for value in spy.objects(None, KG.windowId)} == {"LIVE"}
    assert set(spy.objects(None, KG.seriesOfConfiguration)) == {KG.Configuration_SPY}


def test_a_day_without_news_or_spy_gives_three_empty_graphs(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path, news=False, spy=False))
    extras = build_extras(live, {}, _dates(*SESSIONS))
    assert [graph.triples for graph in extras.graphs] == [0, 0, 0]


def test_a_cited_row_missing_from_the_news_rows_is_refused(tmp_path: Path) -> None:
    other = {**news_row(), "item_id": "11"}
    live = read_live_manifest(_folder(tmp_path, rows=_news_rows(other)))
    with pytest.raises(LiveExtrasError, match="10:AAA"):
        build_extras(live, {}, _dates(*SESSIONS))


def test_the_news_rows_count_must_match_the_manifest(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    manifest = json.loads((folder / "manifest_live.json").read_text())
    manifest["news_rows_file"]["rows"] = 2
    _rewrite_manifest(folder, {"news_rows_file": manifest["news_rows_file"]})
    with pytest.raises(LiveExtrasError, match="the manifest says 2"):
        build_extras(read_live_manifest(folder), {}, _dates(*SESSIONS))


def test_the_spy_series_must_run_from_formation_to_the_day(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path, spy_data=_spy_csv(SESSIONS[1:])))
    with pytest.raises(LiveExtrasError, match="from the formation"):
        build_extras(live, {}, _dates(*SESSIONS[1:]))


def test_the_spy_series_must_carry_the_live_window(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path, spy_data=_spy_csv(window="C1")))
    with pytest.raises(LiveExtrasError, match="is not 'LIVE'"):
        build_extras(live, {}, _dates(*SESSIONS))


def test_the_spy_sessions_must_match_the_book_sessions(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path))
    with pytest.raises(LiveExtrasError, match="differ from the book"):
        build_extras(live, {}, _dates("2026-10-15", "2026-10-17", "2026-10-19"))


def test_the_extras_conform_to_the_shapes(tmp_path: Path) -> None:
    live = read_live_manifest(_folder(tmp_path))
    extras = build_extras(live, {}, _dates(*SESSIONS))
    context = rdflib.Graph().parse(config.schema_dir() / "tbox.ttl", format="turtle")
    for ticker in ("AAA", "BBB"):
        context.add((KG[ticker], RDF.type, KG.Asset))
        context.add((KG[ticker], KG.tickerSymbol, rdflib.Literal(ticker)))
        context.add((KG[ticker], KG.cikNumber, rdflib.Literal("0000000000")))
    load_live._validate_extras(extras, context)


def test_performance_dates_reads_the_book_sessions() -> None:
    builder = rdflib.Graph()
    for index, day in enumerate(SESSIONS):
        point = KG[f"Perf_{index}"]
        builder.add((point, KG.performanceDate, rdflib.Literal(day, datatype=XSD.date)))
    graph = VetoGraph("urn:x", builder.serialize(format="turtle").encode(), 3, "m018", None, None)
    assert performance_dates(graph) == _dates(*SESSIONS)


# --- the six-graph replace ----------------------------------------------------------------------


def _result(day: str) -> LoadResult:
    def graph(name: str, kind: str) -> VetoGraph:
        data = f'<urn:example:{kind}> <urn:example:day> "{day}" .\n'.encode()
        return VetoGraph(name, data, 1, kind, "SYSTEM_LIVE", "LIVE")

    meta = graph(meta_graph_name("live"), "meta")
    m018 = graph(backtest_graph_name("live", "LIVE", "SYSTEM_LIVE"), "m018")
    selection = graph(selection_graph_name("live", "LIVE", "SYSTEM_LIVE"), "selection")
    return LoadResult((VetoBatch(("live", "SYSTEM_LIVE", "LIVE"), [m018, selection]),), meta)


def _store() -> DatasetStore:
    dataset = rdflib.Dataset(default_union=False)
    for name in CONTEXT:
        dataset.graph(rdflib.URIRef(name)).add(
            (rdflib.URIRef("urn:example:context"), RDF.type, rdflib.URIRef("urn:example:T"))
        )
    return DatasetStore(dataset)


def _stub_loader(monkeypatch: pytest.MonkeyPatch, store: DatasetStore) -> None:
    def build(manifest: Any, label: str, **kwargs: Any) -> LoadResult:
        return _result(json.loads(manifest.path.read_text())["day"])

    def plan(db: Any, data: bytes, graph: str, *args: Any, **kwargs: Any) -> gate.IngestPlan:
        batch = gate.parse_batch(data)
        return gate.IngestPlan(graph, batch, gate.IngestPlanStatus.WOULD_WRITE, len(batch))

    monkeypatch.setattr(load_live, "build_delivery", build)
    monkeypatch.setattr(load_live.gate, "plan", plan)
    monkeypatch.setattr(load_live, "_validate_extras", lambda extras, context: None)
    monkeypatch.setattr(load_live, "universe_assets", lambda path: {})
    monkeypatch.setattr(load_live, "load_guard_catalog", lambda path: None)
    monkeypatch.setattr(load_live, "_shacl_context", lambda assets, catalog: (None, rdflib.Graph()))
    monkeypatch.setattr(load_live, "_open_store", lambda repository: store)
    monkeypatch.setattr(load_live, "announce_target", lambda db: None)


def _run(folder: Path, day: str, *extra: str) -> int:
    return load_live.main(["--folder", str(folder), "--day", day, "--assets-db", "x.db", *extra])


def _last_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(capsys.readouterr().out.strip().splitlines()[-1]))


def _sizes(store: DatasetStore) -> dict[str, int]:
    sizes = store.explicit_graph_sizes()
    return {name: sizes.get(name, 0) for name in live_graph_names()}


def test_a_day_without_news_empties_the_previous_days_news_and_spy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store()
    _stub_loader(monkeypatch, store)
    with_news = _folder(tmp_path / "a", day=DAY)
    assert _run(with_news, DAY, "--write") == 0
    first = _last_json(capsys)
    assert first["graphs"] == 6
    assert all(_sizes(store).values())

    without = _folder(tmp_path / "b", day=DAY, news=False, spy=False)
    assert _run(without, DAY, "--write") == 0
    second = _last_json(capsys)
    assert second["graphs"] == 3
    sizes = _sizes(store)
    assert sizes[news_graph_name()] == 0
    assert sizes[news_actions_graph_name()] == 0
    assert sizes[spy_graph_name()] == 0
    swap = store.updates[-1]
    for name in (news_graph_name(), news_actions_graph_name(), spy_graph_name()):
        assert f"DROP SILENT GRAPH <{name}>" in swap
    assert swap.count("MOVE <") == 3
    assert not [name for name in staging_graph_names() if store.explicit_graph_sizes().get(name)]


def test_the_same_day_with_news_twice_gives_the_same_graphs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store()
    _stub_loader(monkeypatch, store)
    folder = _folder(tmp_path, day=DAY)
    assert _run(folder, DAY, "--write") == 0
    first = _sizes(store)
    assert _run(folder, DAY, "--write") == 0
    assert _sizes(store) == first


def test_an_extras_failure_writes_nothing_and_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store()
    _stub_loader(monkeypatch, store)
    other = {**news_row(), "item_id": "11"}
    folder = _folder(tmp_path, day=DAY, rows=_news_rows(other))
    assert _run(folder, DAY, "--write") == 2
    payload = _last_json(capsys)
    assert payload["ok"] is False
    assert "10:AAA" in payload["error"]
    assert store.updates == []
    assert store.writes == []
