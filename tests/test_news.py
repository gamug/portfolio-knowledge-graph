"""The block D news rows: contract, parser, projection and store checks (Work item 46)."""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF

from projection import news
from projection.backtest import AssetInfo, GraphBuilder
from projection.news import (
    NEWS_COLUMNS,
    ManifestError,
    NewsError,
    NewsRow,
    graph_name,
    link_assets,
    load_file,
    news_item_iri,
    project,
    rows_by_graph,
    unresolved_summary,
    verify_manifest_store,
    verify_stored,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
REVISION = "snapshot-c3a753affa5d"


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "model_revision": REVISION,
        "item_kind": "sub_news",
        "item_id": "251045",
        "ticker": "DAL",
        "asset_id": 148,
        "date": "2021-12-01",
        "date_source": "published",
        "title": "Cramer's lightning round",
        "text": "Delta is very interesting.",
        "text_source": "original",
        "sentiment": "positive",
        "sentiment_score": 0.5484,
        "p_positive": 0.5484,
        "p_negative": 0.3411,
        "p_neutral": 0.1105,
        "sentiment_revision": "sentiment-5999fe131d8f",
        "category": "market_analyst_sentiment",
        "category_score": 0.99,
        "group_label": "market_view",
        "category_revision": "category-9b2c6a65a6f4",
        "article_id": 174832,
        "body_hash": "a" * 64,
        "source_domain": "cnbc.com",
        "url": None,
    }
    row.update(overrides)
    return row


def _body_row(**overrides: object) -> dict[str, object]:
    fingerprint = "b" * 64
    row = _row(
        item_kind="body",
        item_id=fingerprint,
        body_hash=fingerprint,
        article_id=None,
        source_domain=None,
    )
    row.update(overrides)
    return row


def _write(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    manifest_rows: int | None = None,
    columns: tuple[str, ...] = NEWS_COLUMNS,
    sums_hash: str | None = None,
) -> Path:
    root = tmp_path / "delivery"
    folder = root / "news"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "news_rows.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
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
            "rows": len(rows) if manifest_rows is None else manifest_rows,
            "model_revision": REVISION,
            "columns": list(columns),
            "readme": "news/README.md",
        },
    }
    (root / "manifest_final.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "SHA256SUMS").write_text(
        f"{sums_hash or digest}  news/news_rows.jsonl\n", encoding="utf-8"
    )
    return root


def _data(tmp_path: Path, rows: list[dict[str, object]] | None = None) -> news.NewsFile:
    return load_file("final", _write(tmp_path, rows or [_row()]))


def _news_row(index: int, **overrides: object) -> NewsRow:
    values: dict[str, object] = {
        "line": index,
        "model_revision": REVISION,
        "item_kind": "sub_news",
        "item_id": str(index),
        "ticker": "DAL",
        "asset_id": None,
        "date": datetime.date(2021, 12, 1),
        "date_source": "published",
        "title": "t",
        "text": "x",
        "text_source": "original",
        "sentiment": "positive",
        "sentiment_score": Decimal("0.5"),
        "p_positive": Decimal("0.5"),
        "p_negative": Decimal("0.3"),
        "p_neutral": Decimal("0.2"),
        "sentiment_revision": "sentiment-1",
        "category": "c",
        "category_score": Decimal("0.9"),
        "group_label": "g",
        "category_revision": "category-1",
        "article_id": 1,
        "body_hash": "a" * 64,
        "source_domain": "cnbc.com",
        "url": None,
    }
    values.update(overrides)
    return NewsRow(**values)  # type: ignore[arg-type]


def test_the_file_is_verified_against_the_manifest_and_sums(tmp_path: Path) -> None:
    data = _data(tmp_path)
    assert data.contract.rows == 1
    assert data.rows[0].date.isoformat() == "2021-12-01"
    assert len(data.rows) == 1


def test_a_manifest_row_count_mismatch_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row()], manifest_rows=2)
    with pytest.raises(NewsError, match="the manifest says 2"):
        load_file("final", root)


def test_a_file_hash_mismatch_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row()])
    (root / "news" / "news_rows.jsonl").write_text(
        json.dumps(_row(item_id="999999")) + "\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        load_file("final", root)


def test_a_sums_hash_mismatch_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row()], sums_hash="0" * 64)
    with pytest.raises(ManifestError, match="the manifest says"):
        load_file("final", root)


def test_a_missing_sums_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row()])
    (root / "SHA256SUMS").unlink()
    with pytest.raises(ManifestError, match="no SHA256SUMS"):
        load_file("final", root)


def test_a_reordered_row_header_stops(tmp_path: Path) -> None:
    row = _row()
    reordered = {"ticker": row.pop("ticker"), **row}
    root = _write(tmp_path, [reordered])
    with pytest.raises(NewsError, match="header drift"):
        load_file("final", root)


def test_a_duplicate_key_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row(), _row()])
    with pytest.raises(NewsError, match="duplicate key"):
        load_file("final", root)


def test_the_same_iri_under_two_revisions_stops(tmp_path: Path) -> None:
    second = _row(model_revision="snapshot-ffffffffffff")
    root = _write(tmp_path, [_row(), second])
    with pytest.raises(NewsError, match="two revisions"):
        load_file("final", root)


def test_an_unknown_revision_stops(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row(model_revision="snapshot-ffffffffffff")])
    with pytest.raises(NewsError, match="differs from the manifest"):
        load_file("final", root)


def test_a_body_row_without_article_id_and_source_domain_loads(tmp_path: Path) -> None:
    data = _data(tmp_path, [_body_row()])
    assert data.rows[0].item_kind == "body"
    assert data.rows[0].article_id is None
    assert data.rows[0].source_domain is None


def test_a_body_item_id_must_be_64_lowercase_hex(tmp_path: Path) -> None:
    root = _write(tmp_path, [_body_row(item_id="B" * 64, body_hash="B" * 64)])
    with pytest.raises(NewsError, match="64 lowercase hex"):
        load_file("final", root)


def test_a_body_item_id_must_equal_body_hash(tmp_path: Path) -> None:
    root = _write(tmp_path, [_body_row(body_hash="c" * 64)])
    with pytest.raises(NewsError, match="must equal body_hash"):
        load_file("final", root)


def test_a_body_with_an_empty_article_value_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, [_body_row(article_id="")])
    with pytest.raises(NewsError, match="expected an integer"):
        load_file("final", root)
    root = _write(tmp_path, [_body_row(source_domain="")])
    with pytest.raises(NewsError, match="expected a non-empty string"):
        load_file("final", root)


def test_a_sub_news_with_a_null_article_or_source_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, [_row(article_id=None)])
    with pytest.raises(NewsError, match="expected an integer"):
        load_file("final", root)
    root = _write(tmp_path, [_row(source_domain=None)])
    with pytest.raises(NewsError, match="expected a non-empty string"):
        load_file("final", root)


def test_a_body_and_an_integer_sub_news_id_do_not_collide(tmp_path: Path) -> None:
    rows = [_row(item_id="10"), _body_row()]
    data = _data(tmp_path, rows)
    assert {row.item_kind for row in data.rows} == {"body", "sub_news"}
    assert news_item_iri(data.rows[0]) != news_item_iri(data.rows[1])


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"date": "2021-13-01"}, "not a calendar date"),
        ({"sentiment_score": 1.2}, r"outside \[0, 1\]"),
        ({"article_id": 0}, "not a positive integer"),
        ({"url": 42}, "expected a non-empty string"),
        ({"text": "x" * 2001}, "at most 2,000"),
        ({"item_kind": "article"}, "not body or sub_news"),
        ({"text_source": "full"}, "not original or summary"),
        ({"sentiment": "mixed"}, "not a known sentiment"),
        ({"date_source": "later"}, "not a known date source"),
    ],
)
def test_a_malformed_value_stops(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    root = _write(tmp_path, [_row(**overrides)])
    with pytest.raises(NewsError, match=message):
        load_file("final", root)


def test_the_iri_uses_only_item_kind_id_and_ticker() -> None:
    row = _news_row(1)
    assert news_item_iri(row) == KG.NewsItem_sub_news_1_DAL
    assert row.model_revision not in str(news_item_iri(row))


def test_the_asset_link_prefers_the_ticker_then_the_engine_id() -> None:
    assets = {
        "AAPL": AssetInfo("AAPL", "0000320193"),
        "PARA": AssetInfo("PARA", "0000813828"),
    }
    rows = (
        _news_row(1, ticker="AAPL", asset_id=1),
        _news_row(2, ticker="PSKY", asset_id=2),
        _news_row(3, ticker="PARA", asset_id=2),
        _news_row(4, ticker="EQR", asset_id=None),
    )
    linked = link_assets(rows, assets)
    assert [row.asset for row in linked] == ["AAPL", "PARA", "PARA", None]
    total, null_ids, tickers = unresolved_summary(linked)
    assert total == 1
    assert null_ids == 1
    assert tickers == {"EQR": 1}


def test_letter_26_psky_rows_link_to_skyd_through_asset_477() -> None:
    assets = {"SKYD": AssetInfo("SKYD", None)}
    rows = (
        _news_row(1, ticker="PSKY", asset_id=477),
        _news_row(2, ticker="SKYD", asset_id=477),
        _news_row(3, ticker="EQR", asset_id=None),
    )
    linked = link_assets(rows, assets)
    assert [row.asset for row in linked] == ["SKYD", "SKYD", None]
    total, null_ids, tickers = unresolved_summary(linked)
    assert (total, null_ids, tickers) == (1, 1, {"EQR": 1})


def test_the_projection_omits_article_and_source_for_a_body(tmp_path: Path) -> None:
    data = _data(tmp_path, [_body_row()])
    builder = project(data)["urn:graph:derived:news:final:2021"]
    item = news_item_iri(data.rows[0])
    triples = builder.triples
    assert (item, KG.articleId, None) not in triples
    assert (item, KG.sourceDomain, None) not in triples
    assert any(predicate == KG.bodyHash for _, predicate, _ in triples)
    assert any(predicate == KG.itemKind for _, predicate, _ in triples)


def test_the_projection_omits_present_article_and_source_for_a_body(tmp_path: Path) -> None:
    data = _data(
        tmp_path,
        [_body_row(article_id=174832, source_domain="cnbc.com")],
    )
    builder = project(data)["urn:graph:derived:news:final:2021"]
    item = news_item_iri(data.rows[0])
    assert not any(
        subject == item and predicate in (KG.articleId, KG.sourceDomain)
        for subject, predicate, _ in builder.triples
    )


def test_the_projection_writes_typed_values_and_the_asset_link(tmp_path: Path) -> None:
    data = _data(tmp_path)
    data = replace(data, rows=link_assets(data.rows, {"DAL": AssetInfo("DAL", None)}))
    builders = project(data)
    assert list(builders) == ["urn:graph:derived:news:final:2021"]
    builder = builders["urn:graph:derived:news:final:2021"]
    item = news_item_iri(data.rows[0])
    turtle = builder.turtle().decode()
    assert ":NewsItem" in turtle
    assert "2021-12-01" in turtle
    assert str(item) in turtle
    assert ":newsItemOfAsset" in turtle


def test_a_year_over_the_bound_is_split_into_its_halves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(news, "MAX_GRAPH_TRIPLES", 2)
    monkeypatch.setattr(news, "MAX_TRIPLES_PER_ROW", 1)
    rows = (
        _news_row(1, date=datetime.date(2024, 1, 1)),
        _news_row(2, date=datetime.date(2024, 2, 1)),
        _news_row(3, date=datetime.date(2024, 7, 1)),
    )
    groups = rows_by_graph("final", rows)
    assert list(groups) == [
        "urn:graph:derived:news:final:2024:01-06",
        "urn:graph:derived:news:final:2024:07-12",
    ]
    assert [len(group) for group in groups.values()] == [2, 1]


def _store(builders: dict[str, GraphBuilder]) -> DatasetStore:
    dataset = rdflib.Dataset(default_union=True)
    store = DatasetStore(dataset)
    for graph, builder in builders.items():
        store.add(builder.turtle(), "text/turtle", graph)
    return store


def test_verify_stored_passes_and_fails_a_missing_item(tmp_path: Path) -> None:
    data = _data(tmp_path)
    builders = project(data)
    store = _store(builders)
    checks = verify_stored(store, "final", data.rows, builders)
    assert all(check.passed for check in checks)
    graph = next(iter(builders))
    store.dataset.graph(rdflib.URIRef(graph)).remove(
        (news_item_iri(data.rows[0]), RDF.type, KG.NewsItem)
    )
    checks = verify_stored(store, "final", data.rows, builders)
    assert not checks[0].passed


def test_verify_manifest_store_reports_absent_graphs_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data(tmp_path)
    manifest = news.read_news_manifest(data.root)
    verify_manifest_store(DatasetStore(rdflib.Dataset()), manifest, "final")
    assert "not store-verifiable" in capsys.readouterr().out


def test_verify_manifest_store_checks_rows_and_tickers(tmp_path: Path) -> None:
    data = _data(tmp_path)
    store = _store(project(data))
    verify_manifest_store(store, news.read_news_manifest(data.root), "final")


def test_verify_manifest_store_fails_a_row_mismatch(tmp_path: Path) -> None:
    data = _data(tmp_path)
    builders = project(data)
    store = _store(builders)
    graph = next(iter(builders))
    store.dataset.graph(rdflib.URIRef(graph)).remove(
        (news_item_iri(data.rows[0]), RDF.type, KG.NewsItem)
    )
    with pytest.raises(NewsError, match="stored 0"):
        verify_manifest_store(store, news.read_news_manifest(data.root), "final")


def test_graph_names_are_year_and_half_bounded() -> None:
    assert graph_name("final", 2021) == "urn:graph:derived:news:final:2021"
    assert graph_name("final", 2024, "01-06") == "urn:graph:derived:news:final:2024:01-06"
    with pytest.raises(NewsError, match="not 01-06 or 07-12"):
        graph_name("final", 2024, "H2")
