"""The external mean-variance base delivery: parser, manifest, projector, gate (Work item 44)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.dataset_store import DatasetStore
from rdflib.namespace import RDF, XSD

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.mv_base import (
    ARM,
    GRAPH_PREFIX,
    ManifestError,
    MvBaseError,
    book_iri,
    graph_name,
    load_file,
    parse_aggregates,
    parse_config,
    project,
    records_changed,
    summary_iri,
    verify_manifest,
    verify_stored,
    with_config,
)

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
SCHEMA = Path(__file__).resolve().parent.parent / "schema"

_SIM_HASH = "4d23f30749f7e246a4304b3eab3e5a1e3d92cd604a5dc3beb47e485ddeae17b2"


def _row(  # noqa: PLR0913, PLR0917 - the fixture reads like the row
    window: str,
    segment: str,
    date_from: str,
    date_to: str,
    sessions: int,
    rebalances: int,
    *,
    cumulative: str = "0.1",
    cvar: str | None = "0.02",
) -> dict[str, Any]:
    return {
        "window": window,
        "segment": segment,
        "date_from": date_from,
        "date_to": date_to,
        "n_sessions": sessions,
        "cumulative_return": float(cumulative),
        "annualized_return": 0.12,
        "annualized_vol": 0.18,
        "ex_post_sharpe": 0.6,
        "max_drawdown": 0.2,
        "total_turnover": 3.0,
        "total_cost_bps": 300.0,
        "n_rebalances": rebalances,
        "n_guard_actions": 0,
        "cvar95": float(cvar) if cvar is not None else None,
    }


def document() -> dict[str, Any]:
    rows = [
        _row("P1", "P1", "2022-01-03", "2022-10-12", 196, 10),
        _row("H1", "H1", "2022-10-13", "2023-10-26", 261, 13),
        _row("P3", "P3", "2023-10-27", "2024-08-02", 192, 10),
        _row("H2", "H2", "2024-08-05", "2025-02-18", 135, 7),
        _row("P2", "P2", "2025-02-19", "2025-09-23", 150, 8),
        _row("P2", "P2a", "2025-02-19", "2025-05-06", 54, 3, cvar=None),
        _row("P2", "P2b", "2025-05-07", "2025-09-23", 96, 5, cvar=None),
        _row("H3", "H3", "2025-09-24", "2026-10-15", 267, 13),
    ]
    dictionary = {key: f"dictionary entry for {key}" for key in rows[0]}
    return {
        "label": "final",
        "book_code": ARM,
        "source": "independent simulator validated against the engine",
        "summary": rows,
        "dictionary": dictionary,
    }


_CONFIG = """---
label: final
book_code: MARKOWITZ_MV
status: final
revision: 2026-11-09
---

The mean-variance base case (tangency portfolio), computed outside the engine.

Integrity. sha256 of `sim_v3.py`: `4d23f30749f7e246a4304b3eab3e5a1e3d92cd604a5dc3beb47e485ddeae17b2`.
"""


def _write(tmp_path: Path, doc: dict[str, Any] | None = None, config: str = _CONFIG) -> Path:
    payload = copy.deepcopy(doc) if doc is not None else document()
    (tmp_path / "aggregates_mv_base.json").write_text(
        json.dumps(payload, indent=1) + "\n", encoding="utf-8"
    )
    (tmp_path / "config_mv_base.md").write_text(config, encoding="utf-8")
    lines = []
    for name in ("aggregates_mv_base.json", "config_mv_base.md"):
        digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    # A provenance entry may be listed even when its file is not present: the loader ignores it.
    lines.append(f"{'0' * 64}  provenance/sim_v3.py")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def _data(tmp_path: Path, doc: dict[str, Any] | None = None) -> Any:
    directory = _write(tmp_path, doc)
    return load_file("final", directory)


def test_the_synthetic_document_has_the_real_shape() -> None:
    doc = document()
    assert set(doc) == {"label", "book_code", "source", "summary", "dictionary"}
    assert {row["segment"] for row in doc["summary"]} == {
        "P1",
        "H1",
        "P3",
        "H2",
        "P2",
        "P2a",
        "P2b",
        "H3",
    }
    assert (
        sum(row["n_rebalances"] for row in doc["summary"] if row["segment"] == row["window"]) == 61
    )


def test_the_graph_name_and_ids_do_not_collide_with_an_engine_book() -> None:
    assert graph_name("final") == f"{GRAPH_PREFIX}final"
    assert graph_name("final") != "urn:graph:derived:backtest:final:P1:1"
    assert book_iri("final", "P1") != KG.Book_final_P1_MARKOWITZ_BASE
    assert summary_iri("final", "P1", "P1") != KG.PeriodSummary_final_P1_MARKOWITZ_BASE_P1


def test_the_file_parses_and_the_config_supplies_the_simulator_hash(
    tmp_path: Path,
) -> None:
    data = _data(tmp_path)
    assert data.label == "final"
    assert data.book_code == ARM
    assert data.config.code_version == _SIM_HASH
    assert data.source == "independent simulator validated against the engine"
    assert data.json_sha256 and data.config_sha256
    assert len(data.rows) == 8


def test_the_projection_has_one_book_per_window_and_one_summary_per_segment(
    tmp_path: Path,
) -> None:
    data = _data(tmp_path)
    builder = project(data)
    graph = rdflib.Graph()
    graph.parse(data=builder.turtle(), format="turtle")
    books = set(graph.subjects(RDF.type, KG.StrategyBook))
    summaries = set(graph.subjects(RDF.type, KG.PortfolioPeriodSummary))
    assert len(books) == 6
    assert len(summaries) == 8
    for book in books:
        assert (book, KG.armCode, rdflib.Literal(ARM)) in graph
        assert (book, KG.dataSource, rdflib.Literal(data.source)) in graph
        assert (book, KG.codeVersion, rdflib.Literal(_SIM_HASH)) in graph
    for summary in summaries:
        assert (
            summary,
            KG.nGuardActions,
            rdflib.Literal(0, datatype=XSD.integer),
        ) in graph
        assert (summary, KG.armCode, rdflib.Literal(ARM)) in graph


def test_the_projection_conforms_to_the_real_shapes(tmp_path: Path) -> None:
    data = _data(tmp_path)
    gate.validate(gate.parse_batch(project(data).turtle()))


def test_the_external_graph_is_accepted_by_the_gate(tmp_path: Path) -> None:
    data = _data(tmp_path)
    graph = graph_name(data.label)
    assert gate.check_target(graph) is True
    fake = DatasetStore(rdflib.Dataset())
    store = cast(GraphDB, fake)
    plan = gate.plan(store, project(data).turtle(), graph)
    assert plan.status is gate.IngestPlanStatus.WOULD_WRITE
    written = gate.write(store, plan)
    assert written == len(project(data))
    assert {str(g.identifier) for g in fake.dataset.graphs() if len(g)} == {graph}
    assert verify_stored(store, data, project(data)).passed


def test_a_write_never_touches_an_engine_graph(tmp_path: Path) -> None:
    data = _data(tmp_path)
    external = graph_name(data.label)
    fake = DatasetStore(rdflib.Dataset())
    store = cast(GraphDB, fake)
    plan = gate.plan(store, project(data).turtle(), external)
    gate.write(store, plan)
    engine_graphs = {
        str(g.identifier) for g in fake.dataset.graphs() if len(g) and str(g.identifier) != external
    }
    assert engine_graphs == set()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda doc: doc.update({"extra": 1}), "unknown 'extra'"),
        (lambda doc: doc.pop("dictionary"), "missing 'dictionary'"),
        (lambda doc: doc["summary"][0].update({"level": 1}), "unknown 'level'"),
        (
            lambda doc: doc["summary"][0].update({"window": "P4"}),
            "not one of the six final windows",
        ),
        (lambda doc: doc["summary"][0].update({"segment": "P1a"}), "not one of"),
        (
            lambda doc: doc["summary"][0].update({"date_from": "2022-1-3"}),
            "strict YYYY-MM-DD",
        ),
        (
            lambda doc: doc["summary"][0].update({"cumulative_return": "x"}),
            "expected a JSON number",
        ),
        (lambda doc: doc["summary"][0].update({"n_guard_actions": 1}), "no GUARD"),
        (lambda doc: doc["summary"][0].update({"n_rebalances": 0}), "expected 61"),
    ],
)
def test_the_whitelist_names_the_row_and_key(tmp_path: Path, mutation: Any, message: str) -> None:
    doc = document()
    mutation(doc)
    with pytest.raises(MvBaseError, match=message):
        parse_aggregates(_write(tmp_path, doc) / "aggregates_mv_base.json", label="final")


def test_a_duplicate_identity_is_refused(tmp_path: Path) -> None:
    doc = document()
    doc["summary"].append(copy.deepcopy(doc["summary"][0]))
    with pytest.raises(MvBaseError, match="duplicate summary row"):
        parse_aggregates(_write(tmp_path, doc) / "aggregates_mv_base.json", label="final")


def test_a_bad_book_code_is_refused(tmp_path: Path) -> None:
    doc = document()
    doc["book_code"] = "MARKOWITZ_BASE"
    with pytest.raises(MvBaseError, match="book_code"):
        parse_aggregates(_write(tmp_path, doc) / "aggregates_mv_base.json", label="final")


def test_the_config_label_must_match(tmp_path: Path) -> None:
    directory = _write(tmp_path)
    config = parse_config(directory / "config_mv_base.md", "final")
    data = parse_aggregates(directory / "aggregates_mv_base.json", label="final")
    with pytest.raises(MvBaseError, match="config label"):
        with_config(data, config.__class__("other", ARM, "final", "x", _SIM_HASH))


def test_a_missing_manifest_entry_and_a_hash_mismatch_are_refused(
    tmp_path: Path,
) -> None:
    directory = _write(tmp_path)
    aggregate_hash = hashlib.sha256(
        (directory / "aggregates_mv_base.json").read_bytes()
    ).hexdigest()
    (directory / "SHA256SUMS").write_text(
        f"{aggregate_hash}  aggregates_mv_base.json\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match=r"config_mv_base\.md.*not listed"):
        verify_manifest(directory, ("aggregates_mv_base.json", "config_mv_base.md"))
    _write(tmp_path)
    (tmp_path / "aggregates_mv_base.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestError, match="SHA-256 mismatch"):
        verify_manifest(tmp_path, ("aggregates_mv_base.json", "config_mv_base.md"))


def test_provenance_is_not_required(tmp_path: Path) -> None:
    directory = _write(tmp_path)
    assert not (directory / "provenance").exists()
    data = load_file("final", directory)
    assert data.label == "final"


def test_a_config_without_the_simulator_hash_is_refused(tmp_path: Path) -> None:
    config = _CONFIG.replace(_SIM_HASH, "not-a-hash")
    directory = _write(tmp_path, config=config)
    with pytest.raises(MvBaseError, match=r"no SHA-256 for sim_v3\.py"):
        parse_config(directory / "config_mv_base.md", "final")


def test_the_optional_validation_csvs_are_warnings_not_failures(tmp_path: Path) -> None:
    data = _data(tmp_path)
    (tmp_path / "validation_engine_book.csv").write_text("abs_diff\n0.0\n", encoding="utf-8")
    warnings = records_changed(tmp_path)
    assert warnings == []
    assert data.label == "final"


def test_the_external_arm_is_in_the_shape_list_and_an_unknown_one_is_not(
    tmp_path: Path,
) -> None:
    data = _data(tmp_path)
    graph = graph_name(data.label)
    assert gate.check_target(graph)
    # The real shape accepts the projected MARKOWITZ_MV book.
    gate.validate(gate.parse_batch(project(data).turtle()))
    # A different arm on the same node is refused by StrategyBookShape.
    bad = rdflib.Graph()
    for triple in project(data).triples:
        bad.add(triple)
    first = next(bad.subjects(RDF.type, KG.StrategyBook))
    bad.remove((first, KG.armCode, None))
    bad.add((first, KG.armCode, rdflib.Literal("BOGUS")))
    with pytest.raises(gate.IngestRejected):
        gate.validate(gate.parse_batch(bad.serialize(format="turtle").encode()))


def test_the_manifest_ignores_provenance_entries(tmp_path: Path) -> None:
    directory = _write(tmp_path)
    entries = (directory / "SHA256SUMS").read_text(encoding="utf-8")
    assert "provenance/sim_v3.py" in entries
    verify_manifest(directory, ("aggregates_mv_base.json", "config_mv_base.md"))
