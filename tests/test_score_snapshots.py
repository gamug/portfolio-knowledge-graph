"""``projection.score_snapshots``: ``v_score_snapshot`` -> ``:ScoreSnapshot`` batches (T-031)."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from etl import config
from kg_store import gate
from projection import score_snapshots as ss
from projection.boundary import BoundaryError
from projection.expectations import load_expectations
from projection.source import FinancialSource

if TYPE_CHECKING:
    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]

NS = "https://thesis.local/kg/portfolio#"
ASSETS = {"AAA", "BBB", "CCC", "BF.B"}


def _row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "ticker": "AAA",
        "asset_id": 1,
        "score_type": "TECHNICAL",
        "raw_value": 70.0,
        "normalized_score": 60.0,
        "event_time": "2026-07-09",
        "computed_at": "2026-10-04T18:28:56+00:00",
        "run_id": 1,
        "run_kind": "cycle",
        "available_at": "2026-07-09",
    }
    row.update(over)
    return row


def _fundamental(**over: Any) -> dict[str, Any]:
    return _row(
        **{
            "score_type": "FUNDAMENTAL",
            "raw_value": 44.0,
            "normalized_score": 44.0,
            "event_time": "2024-12-31",
            "available_at": "2025-03-03",
            "run_kind": "analysis",
            **over,
        }
    )


# --- one snapshot ------------------------------------------------------------------------------


def _conforming(turtle: bytes) -> Any:
    batch = gate.parse_batch(turtle)
    gate.validate(batch)  # SHACL against shapes.ttl
    return batch


@pytest.mark.parametrize(
    "row",
    [
        _row(score_type="TECHNICAL"),
        _row(score_type="VALORIZATION"),
        _row(score_type="SECTOR", raw_value=-15.3),
        _fundamental(),
        _row(ticker="BF.B"),
    ],
    ids=["technical", "valorization", "sector", "fundamental", "dotted-ticker"],
)
def test_a_projected_snapshot_conforms_to_the_shapes(row: dict[str, Any]) -> None:
    block = ss.snapshot_block(row)
    _conforming((ss._PREFIXES + block.turtle).encode())


def test_a_cycle_lane_flips_the_strength_score_into_a_risk_reading() -> None:
    turtle = ss.snapshot_block(_row(normalized_score=65.25)).turtle
    assert ':normalizedScore "0.3475"^^xsd:decimal' in turtle
    assert ':rawValue "70.0"^^xsd:decimal' in turtle  # raw_value is read verbatim


def test_sector_normalized_score_is_rescaled_and_raw_is_verbatim() -> None:
    turtle = ss.snapshot_block(
        _row(score_type="SECTOR", raw_value=-15.5, normalized_score=40)
    ).turtle
    assert ':normalizedScore "0.6"^^xsd:decimal' in turtle
    assert ':rawValue "-15.5"^^xsd:decimal' in turtle


def test_fundamental_projects_its_raw_value_and_never_its_normalized_score() -> None:
    turtle = ss.snapshot_block(_fundamental()).turtle
    assert ":normalizedScore" not in turtle
    assert ':rawValue "44.0"^^xsd:decimal' in turtle


def test_a_tiny_or_huge_float_is_never_written_in_exponent_form() -> None:
    turtle = ss.snapshot_block(_row(raw_value=1e-7)).turtle
    assert ':rawValue "0.0000001"^^xsd:decimal' in turtle


@pytest.mark.parametrize("stamp", ["2026-10-04T18:28:56+00:00", "2026-10-04T18:28:56Z"])
def test_computed_at_is_written_as_a_utc_datetime(stamp: str) -> None:
    assert (
        ':timestamp "2026-10-04T18:28:56Z"^^xsd:dateTime'
        in ss.snapshot_block(_row(computed_at=stamp)).turtle
    )


def test_the_snapshot_is_linked_from_its_asset_and_carries_no_run_identity() -> None:
    block = ss.snapshot_block(_row(id=7))
    assert block.iri == "Snap_AAA_Tec_20260709_7"
    assert f":AAA :hasScoreObservation :{block.iri} ." in block.turtle
    assert ":runId" not in block.turtle  # T-151's rule is not implemented yet


# --- graphs ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("available", "graph"),
    [
        ("2025-01-01", "urn:graph:ingest:FUNDAMENTAL:2025-Q1"),
        ("2025-03-31", "urn:graph:ingest:FUNDAMENTAL:2025-Q1"),
        ("2025-04-01", "urn:graph:ingest:FUNDAMENTAL:2025-Q2"),
        ("2025-12-31", "urn:graph:ingest:FUNDAMENTAL:2025-Q4"),
    ],
)
def test_fundamental_goes_to_the_quarter_it_became_usable_in(available: str, graph: str) -> None:
    assert ss.graph_name("FUNDAMENTAL", available, "2026-10-07") == graph


@pytest.mark.parametrize("lane", ["VALORIZATION", "TECHNICAL", "SECTOR"])
def test_a_cycle_lane_goes_to_the_graph_of_the_run_day(lane: str) -> None:
    assert ss.graph_name(lane, "2026-07-09", "2026-10-07") == f"urn:graph:ingest:{lane}:2026-10-07"


def test_every_graph_the_projection_names_is_one_the_gate_accepts() -> None:
    for lane in ss.LANES:
        assert gate.check_target(ss.graph_name(lane, "2026-07-09", "2026-10-07"))


# --- project: what is left out, and counted ------------------------------------------------------


def test_project_skips_what_it_cannot_write_and_counts_each_reason() -> None:
    rows = [
        _row(id=1),
        _row(id=2, ticker="ZZZ"),  # not an asset
        _row(id=3, available_at=None),  # the boundary counts this one
        _fundamental(id=4, raw_value=None),
        _row(id=5, normalized_score=None),
        _row(id=6, score_type="SECTOR", raw_value=None),
    ]
    out = ss.project(rows, ASSETS, "2026-10-07")
    assert [b.key for b in out.graphs["urn:graph:ingest:TECHNICAL:2026-10-07"]] == [1]
    assert out.skipped == {ss.SKIP_NOT_AN_ASSET: 1, ss.SKIP_NO_VALUE: 3}


def test_an_unknown_lane_is_an_error_not_a_skip() -> None:
    with pytest.raises(ss.ProjectionError, match="no lane"):
        ss.project([_row(score_type="SEMANTIC")], ASSETS, "2026-10-07")


# --- run: the whole path over a synthetic database ------------------------------------------------

_DDL = """
CREATE TABLE schema_version (version INTEGER, applied_at TEXT, description TEXT);
INSERT INTO schema_version VALUES (9, 'x', 'x');
CREATE TABLE v_cycle_run (run_id INTEGER, cycle_type TEXT);
INSERT INTO v_cycle_run VALUES (1, 'SELECTION');
CREATE TABLE v_score_snapshot (
  id INTEGER, ticker TEXT, asset_id INTEGER, score_type TEXT, raw_value REAL, normalized_score REAL,
  event_time TEXT, computed_at TEXT, run_id INTEGER, run_kind TEXT, available_at TEXT);
"""


def _database(tmp_path: Path, rows: list[dict[str, Any]], version: int = 9) -> FinancialSource:
    path = tmp_path / "financial.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.execute("UPDATE schema_version SET version = ?", (version,))
    for r in rows:
        conn.execute(
            f"INSERT INTO v_score_snapshot ({', '.join(ss.COLUMNS)}) VALUES "  # noqa: S608
            f"({', '.join('?' for _ in ss.COLUMNS)})",
            [r[c] for c in ss.COLUMNS],
        )
    conn.commit()
    conn.close()
    return FinancialSource.open(path)


def _cohort(lane: str, first_id: int, **over: Any) -> list[dict[str, Any]]:
    """Three assets whose normalized_score averages 50, the cohort mean the boundary expects."""
    return [
        _row(id=first_id + i, ticker=t, score_type=lane, normalized_score=score, **over)
        for i, (t, score) in enumerate([("AAA", 40.0), ("BBB", 50.0), ("CCC", 60.0)])
    ]


def test_a_dry_run_validates_every_graph_and_writes_nothing(tmp_path: Path) -> None:
    rows = [*_cohort("TECHNICAL", 1), _fundamental(id=10)]
    out = ss.run(_database(tmp_path, rows), ASSETS, None, "2026-10-07")
    assert sorted(out.checked) == [
        "urn:graph:ingest:FUNDAMENTAL:2025-Q1",
        "urn:graph:ingest:TECHNICAL:2026-10-07",
    ]
    assert not out.written
    assert not out.rejected


def test_the_source_check_runs_first_and_stops_a_database_below_the_floor(tmp_path: Path) -> None:
    with pytest.raises(BoundaryError, match="schema_version"):
        ss.run(_database(tmp_path, _cohort("TECHNICAL", 1), version=8), ASSETS, None, "2026-10-07")


def test_the_schema_version_is_read_from_upstreams_table_not_the_pragma(tmp_path: Path) -> None:
    source = _database(tmp_path, [])
    assert source.schema_version == 9  # PRAGMA user_version is 0 in this database


def test_a_cycle_row_with_no_available_at_is_counted_once_and_not_projected(tmp_path: Path) -> None:
    rows = _cohort("TECHNICAL", 1, available_at=None)
    out = ss.run(_database(tmp_path, rows), ASSETS, None, "2026-10-07")
    assert (
        out.report.skipped_by_design[
            ("v_score_snapshot", "available_at is NULL until upstream T-144")
        ]
        == 3
    )
    assert not out.checked


def test_a_write_goes_through_the_gate_and_skips_what_the_store_already_holds(
    tmp_path: Path, make_db: MakeDB
) -> None:
    rows = [_fundamental(id=10), _fundamental(id=11, ticker="BBB")]
    held = f"{NS}Snap_AAA_Fin_20241231_10"
    store = make_db()
    # Only a query that names the held snapshot finds it, as the store would.
    store.select = lambda sparql: [{"s": held}] if held in sparql else []  # type: ignore[method-assign]
    out = ss.run(_database(tmp_path, rows), ASSETS, store.db, "2026-10-07")
    assert out.already_in_store == 1
    written = b"".join(d for d, _, _ in store.added)
    assert b"Snap_BBB_Fin_20241231_11" in written
    assert b"Snap_AAA_Fin_20241231_10" not in written


# --- the late-key round trip, on the real read ---------------------------------------------------


def _allow_one_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    real = load_expectations()
    patched = {
        **real,
        "v_score_snapshot": dataclasses.replace(
            real["v_score_snapshot"], cap=1, cap_reason="test: one late row"
        ),
    }
    monkeypatch.setattr(ss, "load_expectations", lambda: patched)


def test_a_delayed_row_is_read_again_and_its_key_leaves_the_file_once_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    bad = _cohort("TECHNICAL", 1)
    bad[2]["raw_value"] = "n/a"  # a type failure: the row is quarantined, late in an ingest graph
    first = ss.run(
        _database(tmp_path, bad),
        ASSETS,
        make_db().db,
        "2026-10-07",
        late_keys_path=keys,
    )
    assert [f.key for f in first.report.late] == [(3,)]
    assert json.loads(keys.read_text())["v_score_snapshot"]["keys"] == [[3]]

    (tmp_path / "financial.db").unlink()
    fixed = _cohort("TECHNICAL", 1)
    store = make_db()
    second = ss.run(_database(tmp_path, fixed), ASSETS, store.db, "2026-10-08", late_keys_path=keys)
    assert not second.report.late
    assert b"Snap_CCC_Tec_20260709_3" in b"".join(d for d, _, _ in store.added)
    assert json.loads(keys.read_text()).get("v_score_snapshot", {"keys": []})["keys"] == []


def test_a_late_key_upstream_no_longer_has_is_reported_and_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    bad = _cohort("TECHNICAL", 1)
    bad[2]["raw_value"] = "n/a"
    ss.run(_database(tmp_path, bad), ASSETS, make_db().db, "2026-10-07", late_keys_path=keys)

    (tmp_path / "financial.db").unlink()
    gone = _cohort("TECHNICAL", 1)[:2]  # row 3 was deleted upstream
    out = ss.run(_database(tmp_path, gone), ASSETS, make_db().db, "2026-10-08", late_keys_path=keys)
    assert out.late_not_found == ["v_score_snapshot id=3"]
    assert json.loads(keys.read_text()).get("v_score_snapshot", {"keys": []})["keys"] == []


# --- the real database (opt in: -m integration) -------------------------------------------------


@pytest.mark.integration
def test_the_configured_databases_project_into_graphs_the_gate_accepts() -> None:
    financial, universe = config.financial_db_path(), config.universe_db_path()
    if not financial.exists() or not universe.exists():
        pytest.skip("SQL_FINANCIAL_DB / SQL_UNIVERSE_DB not present")
    source = FinancialSource.open(financial)
    try:
        out = ss.run(source, ss.universe_symbols(universe), None, "2026-10-07")
    finally:
        source.close()
    assert not out.report.stopped
    assert not out.rejected
    assert out.checked
