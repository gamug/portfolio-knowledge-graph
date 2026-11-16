"""The block E daily series: manifest, CSV contract, projection and store checks (Work item 46)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, XSD

from kg_store import gate
from kg_store.graphdb import AnswerLost, GraphDB
from projection import load_veto, series
from projection.series import (
    MARKOWITZ_SLUG,
    MV_DAILY_FILES,
    SPY_FILE,
    SPY_SLUG,
    WEIGHTS_FILE,
    ManifestError,
    SeriesError,
    graph_name,
    load_file,
    project,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
WINDOW_DATES = {
    "P1": "2022-01-03",
    "H1": "2022-10-13",
    "P3": "2023-10-27",
    "H2": "2024-08-05",
    "P2": "2025-02-19",
    "H3": "2025-09-24",
    "C1": "2022-01-03",
}


def _manifest(folder: Path, names: list[str]) -> None:
    lines = []
    for name in names:
        digest = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_series(  # noqa: PLR0913 -- the fixture mirrors the CSV options
    tmp_path: Path,
    *,
    spy_header: str | None = None,
    mv_header: str | None = None,
    weights_header: str | None = None,
    duplicate: bool = False,
    missing_c1: bool = False,
) -> Path:
    folder = tmp_path / "series"
    folder.mkdir()
    (folder / "markowitz_mv").mkdir()
    names: list[str] = []
    spy_lines = [spy_header or "window,date,daily_total_return,value"]
    for window, day in WINDOW_DATES.items():
        spy_lines.append(f"{window},{day},0.001,1.001")
    if duplicate:
        spy_lines.append("P1,2022-01-03,0.002,1.002")
    (folder / SPY_FILE).write_text("\n".join(spy_lines) + "\n", encoding="utf-8")
    names.append(SPY_FILE)
    for window, day in WINDOW_DATES.items():
        if missing_c1 and window == "C1":
            continue
        name = MV_DAILY_FILES[window]
        lines = [mv_header or "date,gross_return,net_return,turnover,cost,cash_weight"]
        lines.append(f"{day},0.001,-0.001,0.1,0.0001,0.01")
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        names.append(name)
    lines = [weights_header or "window,decision_date,asset_id,weight"]
    for window, day in WINDOW_DATES.items():
        lines.append(f"{window},{day},1,0.1")
    (folder / WEIGHTS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    names.append(WEIGHTS_FILE)
    _manifest(folder, names)
    return folder


def _move_manifest_to_parent(folder: Path, *, extra: bool = False) -> Path:
    """Put the manifest at the delivery root with series/... keys, like the final layout."""
    lines = (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    (folder / "SHA256SUMS").unlink()
    root = folder.parent
    moved = []
    for line in lines:
        digest, name = line.split("  ", 1)
        moved.append(f"{digest}  {folder.name}/{name}")
    if extra:
        moved.append(f"{'0' * 64}  unrelated/ignored.bin")
    manifest = root / "SHA256SUMS"
    manifest.write_text("\n".join(moved) + "\n", encoding="utf-8")
    return manifest


def _data(tmp_path: Path) -> series.SeriesFile:
    return load_file("final", write_series(tmp_path))


def _store(builders: dict[str, rdflib.Graph], label: str = "final") -> DatasetStore:
    dataset = rdflib.Dataset(default_union=True)
    store = DatasetStore(dataset)
    for slug, builder in builders.items():
        store.add(
            builder.serialize(format="turtle").encode(), "text/turtle", graph_name(label, slug)
        )
    return store


def test_a_root_manifest_covers_the_series_subfolder(tmp_path: Path) -> None:
    folder = write_series(tmp_path)
    manifest = _move_manifest_to_parent(folder, extra=True)
    data = load_file("final", folder)
    assert data.manifest == manifest
    assert len(data.hashes) == 9


def test_a_root_manifest_mismatch_is_refused(tmp_path: Path) -> None:
    folder = write_series(tmp_path)
    _move_manifest_to_parent(folder)
    path = folder / SPY_FILE
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        load_file("final", folder)


def test_an_unlisted_series_file_in_a_root_manifest_is_refused(tmp_path: Path) -> None:
    folder = write_series(tmp_path)
    manifest = _move_manifest_to_parent(folder)
    removed = f"{folder.name}/{MV_DAILY_FILES['C1']}"
    lines = [
        line for line in manifest.read_text(encoding="utf-8").splitlines() if removed not in line
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ManifestError, match=r"not listed: .*mv_daily_C1[.]csv"):
        load_file("final", folder)


def test_no_manifest_in_the_folder_or_a_parent_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "delivery" / "series_diarias_referencia"
    folder.mkdir(parents=True)
    with pytest.raises(ManifestError, match="no SHA256SUMS"):
        load_file("final", folder)


def test_real_headers_parse_and_project_c1_and_weights(tmp_path: Path) -> None:
    data = _data(tmp_path)
    assert len(data.spy_daily) == 7
    assert all(len(data.mv_daily[window]) == 1 for window in series.WINDOWS)
    assert len(data.weights) == 7
    assert {row.window for row in data.spy_daily} == set(series.WINDOWS)

    builders = project(data)
    assert gate.check_target(graph_name("final", MARKOWITZ_SLUG)) is True
    for builder in builders.values():
        gate.validate(gate.parse_batch(builder.turtle()))

    graph = rdflib.Graph()
    graph.parse(data=builders[SPY_SLUG].turtle(), format="turtle")
    c1 = next(graph.subjects(KG.windowId, rdflib.Literal("C1")))
    assert (c1, RDF.type, KG.DailySeriesPoint) in graph
    assert (c1, KG.seriesOfConfiguration, KG.Configuration_SPY) in graph
    assert (c1, KG.dailyTotalReturn, rdflib.Literal("0.001", datatype=XSD.decimal)) in graph
    assert (c1, KG.seriesDate, rdflib.Literal("2022-01-03", datatype=XSD.date)) in graph

    mv = rdflib.Graph()
    mv.parse(data=builders[MARKOWITZ_SLUG].turtle(), format="turtle")
    weight = next(mv.subjects(RDF.type, KG.SeriesWeightPoint))
    assert (weight, KG.seriesOfConfiguration, KG.Configuration_MarkowitzMV) in mv
    assert (weight, KG.seriesAssetId, rdflib.Literal(1, datatype=XSD.integer)) in mv
    assert (weight, KG.seriesWeight, rdflib.Literal("0.1", datatype=XSD.decimal)) in mv


def test_a_header_drift_is_refused(tmp_path: Path) -> None:
    folder = write_series(tmp_path, spy_header="window,date,daily_total_return,value_x")
    with pytest.raises(SeriesError, match="header drift"):
        load_file("final", folder)


def test_a_hash_mismatch_is_refused_before_parsing(tmp_path: Path) -> None:
    folder = write_series(tmp_path)
    path = folder / SPY_FILE
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        load_file("final", folder)


def test_a_duplicate_window_date_is_refused(tmp_path: Path) -> None:
    folder = write_series(tmp_path, duplicate=True)
    with pytest.raises(SeriesError, match=r"duplicate \(window, date\)"):
        load_file("final", folder)


def test_missing_c1_is_refused(tmp_path: Path) -> None:
    folder = write_series(tmp_path, missing_c1=True)
    with pytest.raises(ManifestError, match="C1"):
        load_file("final", folder)


def test_the_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)
    monkeypatch.setattr(
        series.GraphDB,
        "from_env",
        classmethod(lambda cls: pytest.fail("a dry run must not contact the store")),
    )
    assert series.main(["--label", "final", "--dir", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "SHACL: conforms (markowitz_mv, gate.validate)" in out
    assert "SHACL: conforms (spy, gate.validate)" in out
    assert "rows: spy_daily.csv: 7" in out


def test_a_production_write_without_the_opt_in_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)

    class Production:
        repository = "portfolio"
        host = "http://store.invalid"

    monkeypatch.setattr(series.GraphDB, "from_env", classmethod(lambda cls: Production()))
    with pytest.raises(SystemExit) as exc:
        series.main(["--label", "final", "--dir", str(folder), "--write"])
    assert exc.value.code == 2
    assert "needs --to-production" in capsys.readouterr().err


def test_a_large_graph_is_written_in_batches(tmp_path: Path) -> None:
    data = _data(tmp_path)
    builders = project(data)
    graph = graph_name("final", MARKOWITZ_SLUG)
    store = DatasetStore(rdflib.Dataset())
    plan = gate.plan(cast(GraphDB, store), builders[MARKOWITZ_SLUG].turtle(), graph)
    written = gate.write_batched(cast(GraphDB, store), plan, batch_size=5)
    assert written == plan.triples
    assert len(store.writes) > 1
    assert all(target == graph for target, _ in store.writes)


def test_write_creates_both_series_graphs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)
    store = DatasetStore(rdflib.Dataset())
    monkeypatch.setattr(series.GraphDB, "from_env", classmethod(lambda cls: store))
    monkeypatch.setattr(series, "announce_target", lambda db: None)
    code = series.main(["--label", "final", "--dir", str(folder), "--write", "--batch-size", "5"])
    assert code == 0, capsys.readouterr().err
    graphs = {str(graph.identifier) for graph in store.dataset.graphs() if len(graph)}
    assert graphs == {
        graph_name("final", MARKOWITZ_SLUG),
        graph_name("final", SPY_SLUG),
    }


def test_check_store_is_idempotent_after_a_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)
    data = load_file("final", folder)
    builders = project(data)
    store = DatasetStore(rdflib.Dataset())
    monkeypatch.setattr(series.GraphDB, "from_env", classmethod(lambda cls: store))
    monkeypatch.setattr(series, "announce_target", lambda db: None)
    for slug in (MARKOWITZ_SLUG, SPY_SLUG):
        plan = gate.plan(cast(GraphDB, store), builders[slug].turtle(), graph_name("final", slug))
        gate.write_batched(cast(GraphDB, store), plan, batch_size=5)
    writes = len(store.writes)
    capsys.readouterr()
    assert series.main(["--label", "final", "--dir", str(folder), "--check-store"]) == 0
    out = capsys.readouterr().out
    assert out.count("already-in-the-store") == 2
    assert "PASS  stored" in out
    assert len(store.writes) == writes


def test_check_store_accepts_a_mixed_present_and_absent_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)
    data = load_file("final", folder)
    builders = project(data)
    store = DatasetStore(rdflib.Dataset())
    plan = gate.plan(
        cast(GraphDB, store), builders[SPY_SLUG].turtle(), graph_name("final", SPY_SLUG)
    )
    gate.write_batched(cast(GraphDB, store), plan, batch_size=5)
    writes = len(store.writes)
    monkeypatch.setattr(series.GraphDB, "from_env", classmethod(lambda cls: store))
    monkeypatch.setattr(series, "announce_target", lambda db: None)
    capsys.readouterr()
    assert series.main(["--label", "final", "--dir", str(folder), "--check-store"]) == 0
    out = capsys.readouterr().out
    assert "already-in-the-store" in out
    assert "would-be-written" in out
    assert "FAIL" not in out
    assert len(store.writes) == writes


def test_a_lost_answer_is_reported_as_graph_in_doubt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)

    class TimeoutStore(DatasetStore):
        def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
            if self.writes:
                self.writes.append((graph, data))
                raise AnswerLost("read timed out")
            super().add(data, content_type, graph)

    timeout = TimeoutStore(rdflib.Dataset())
    monkeypatch.setattr(series.GraphDB, "from_env", classmethod(lambda cls: timeout))
    monkeypatch.setattr(series, "announce_target", lambda db: None)
    code = series.main(["--label", "final", "--dir", str(folder), "--write", "--batch-size", "5"])
    assert code == 1
    assert "graph is in doubt" in capsys.readouterr().err
    assert len(timeout.writes) == 2  # one accepted chunk, one lost answer, no retry


@pytest.mark.parametrize(
    ("slug", "configuration"),
    [(SPY_SLUG, "SPY"), (MARKOWITZ_SLUG, "MARKOWITZ_MV")],
)
def test_verify_store_checks_daily_rows_when_the_series_graph_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], slug: str, configuration: str
) -> None:
    folder = write_series(tmp_path)
    data = load_file("final", folder)
    builders = project(data)
    store = DatasetStore(rdflib.Dataset())
    store.add(builders[slug].turtle(), "text/turtle", graph_name("final", slug))
    daily = folder / SPY_FILE if slug == SPY_SLUG else folder / MV_DAILY_FILES["C1"]
    run = SimpleNamespace(
        configuration=configuration,
        window="C1",
        source_kind="series_csv",
        slug=slug,
        files={"daily_file": daily},
    )
    manifest = SimpleNamespace(label="final", runs=(run,))
    failures = load_veto._series_daily_row_failures(cast(GraphDB, store), cast(Any, manifest))
    assert failures == []
    assert f"PASS  daily_rows {configuration}/C1: 1" in capsys.readouterr().out


def test_verify_store_leaves_an_absent_series_graph_not_verifiable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_series(tmp_path)
    store = DatasetStore(rdflib.Dataset())
    run = SimpleNamespace(
        configuration="SPY",
        window="C1",
        source_kind="series_csv",
        slug=SPY_SLUG,
        files={"daily_file": folder / SPY_FILE},
    )
    manifest = SimpleNamespace(label="final", runs=(run,))
    assert load_veto._series_daily_row_failures(cast(GraphDB, store), cast(Any, manifest)) == []
    assert "not store-verifiable" in capsys.readouterr().out


def _graph(builder: Any) -> rdflib.Graph:
    graph = rdflib.Graph()
    graph.parse(data=builder.turtle(), format="turtle")
    return graph


def test_a_spy_point_without_its_value_is_rejected(tmp_path: Path) -> None:
    graph = _graph(project(_data(tmp_path))[SPY_SLUG])
    point = next(graph.subjects(RDF.type, KG.DailySeriesPoint))
    graph.remove((point, KG.seriesValue, None))
    with pytest.raises(gate.ShaclRejected):
        gate.validate(graph)


def test_a_markowitz_point_without_all_value_columns_is_rejected(tmp_path: Path) -> None:
    graph = _graph(project(_data(tmp_path))[MARKOWITZ_SLUG])
    point = next(graph.subjects(RDF.type, KG.DailySeriesPoint))
    graph.remove((point, KG.seriesNetReturn, None))
    with pytest.raises(gate.ShaclRejected):
        gate.validate(graph)


def test_a_weight_point_without_an_asset_id_is_rejected(tmp_path: Path) -> None:
    graph = _graph(project(_data(tmp_path))[MARKOWITZ_SLUG])
    point = next(graph.subjects(RDF.type, KG.SeriesWeightPoint))
    graph.remove((point, KG.seriesAssetId, None))
    with pytest.raises(gate.ShaclRejected):
        gate.validate(graph)


def test_a_series_point_with_an_unknown_window_is_rejected(tmp_path: Path) -> None:
    graph = _graph(project(_data(tmp_path))[SPY_SLUG])
    point = next(graph.subjects(RDF.type, KG.DailySeriesPoint))
    graph.remove((point, KG.windowId, None))
    graph.add((point, KG.windowId, rdflib.Literal("ZZ")))
    with pytest.raises(gate.ShaclRejected):
        gate.validate(graph)
