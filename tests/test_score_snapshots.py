"""``projection.score_snapshots``: ``v_score_snapshot`` -> ``:ScoreSnapshot`` batches (T-031)."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fixtures.snapshot_rows import (
    ASSETS,
    NS,
    RUNS,
    financial_db,
    full_run,
    fundamental_row,
    live_store,
    snapshot_row,
)

from etl import config
from kg_store import gate
from kg_store.graphdb import AnswerLost, GraphDBError
from projection import score_snapshots as ss
from projection.boundary import GRAPH_WRITTEN, BoundaryError
from projection.expectations import load_expectations
from projection.source import FinancialSource

if TYPE_CHECKING:
    from conftest import FakeGraphDB

    MakeDB = Callable[..., FakeGraphDB]


# --- one snapshot ------------------------------------------------------------------------------


def _conforming(turtle: bytes) -> Any:
    batch = gate.parse_batch(turtle)
    gate.validate(batch)  # SHACL against shapes.ttl
    return batch


@pytest.mark.parametrize(
    "row",
    [
        snapshot_row(score_type="TECHNICAL"),
        snapshot_row(score_type="VALORIZATION"),
        snapshot_row(score_type="SECTOR", raw_value=-15.3),
        fundamental_row(),
        snapshot_row(ticker="BF.B"),
    ],
    ids=["technical", "valorization", "sector", "fundamental", "dotted-ticker"],
)
def test_a_projected_snapshot_conforms_to_the_shapes(row: dict[str, Any]) -> None:
    block = ss.snapshot_block(row)
    _conforming((ss._PREFIXES + block.turtle).encode())


def test_a_cycle_lane_flips_the_strength_score_into_a_risk_reading() -> None:
    turtle = ss.snapshot_block(snapshot_row(normalized_score=65.25)).turtle
    assert ':normalizedScore "0.3475"^^xsd:decimal' in turtle
    assert ':rawValue "70.0"^^xsd:decimal' in turtle  # raw_value is read verbatim


def test_sector_normalized_score_is_rescaled_and_raw_is_verbatim() -> None:
    turtle = ss.snapshot_block(
        snapshot_row(score_type="SECTOR", raw_value=-15.5, normalized_score=40)
    ).turtle
    assert ':normalizedScore "0.6"^^xsd:decimal' in turtle
    assert ':rawValue "-15.5"^^xsd:decimal' in turtle


def test_fundamental_projects_its_raw_value_and_never_its_normalized_score() -> None:
    turtle = ss.snapshot_block(fundamental_row()).turtle
    assert ":normalizedScore" not in turtle
    assert ':rawValue "44.0"^^xsd:decimal' in turtle


def test_a_tiny_or_huge_float_is_never_written_in_exponent_form() -> None:
    turtle = ss.snapshot_block(snapshot_row(raw_value=1e-7)).turtle
    assert ':rawValue "0.0000001"^^xsd:decimal' in turtle


@pytest.mark.parametrize("stamp", ["2026-10-04T18:28:56+00:00", "2026-10-04T18:28:56Z"])
def test_computed_at_is_written_as_a_utc_datetime(stamp: str) -> None:
    assert (
        ':timestamp "2026-10-04T18:28:56Z"^^xsd:dateTime'
        in ss.snapshot_block(snapshot_row(computed_at=stamp)).turtle
    )


def test_the_snapshot_is_linked_from_its_asset_and_carries_no_run_identity() -> None:
    block = ss.snapshot_block(snapshot_row(id=7))
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
        snapshot_row(id=1),
        snapshot_row(id=2, ticker="ZZZ"),  # not an asset
        snapshot_row(id=3, available_at=None),  # the boundary counts this one
        fundamental_row(id=4, raw_value=None),
        snapshot_row(id=5, normalized_score=None),
        snapshot_row(id=6, score_type="SECTOR", raw_value=None),
        snapshot_row(id=7, ticker="aaa"),  # not a well-formed symbol
    ]
    out = ss.project(rows, ASSETS, "2026-10-07")
    assert [b.key for b in out.graphs["urn:graph:ingest:TECHNICAL:2026-10-07"]] == [1]
    assert out.skipped == {ss.SKIP_NOT_AN_ASSET: 1, ss.SKIP_NO_VALUE: 3, ss.SKIP_BAD_TICKER: 1}
    assert out.left_out == {
        2: ss.SKIP_NOT_AN_ASSET,
        3: ss.LEFT_NULL_AVAILABLE_AT,
        4: ss.SKIP_NO_VALUE,
        5: ss.SKIP_NO_VALUE,
        6: ss.SKIP_NO_VALUE,
        7: ss.SKIP_BAD_TICKER,
    }


@pytest.mark.parametrize(
    ("available", "written"),
    [("2026-09-30", True), ("2026-10-01", False), ("2026-10-07", False)],
)
def test_a_fundamental_quarter_is_written_only_once_it_has_closed(
    available: str, written: bool
) -> None:
    out = ss.project([fundamental_row(available_at=available)], ASSETS, "2026-10-07", RUNS)
    assert bool(out.graphs) is written
    assert out.deferred == ({} if written else {ss.DEFER_QUARTER_OPEN: 1})
    assert not out.skipped
    assert not out.left_out  # a later run writes it, so a late key would stay


def test_a_closed_quarter_waits_until_a_full_upstream_run_has_covered_it() -> None:
    # Upstream computed a Q3 filing in an August run; the calendar quarter is over on Oct 1,
    # but upstream's run after Q3 (which emits the rest of Q3) has not happened yet.
    august = fundamental_row(id=1, available_at="2026-07-15", computed_at="2026-08-20T10:00:00Z")
    out = ss.project([august], ASSETS, "2026-10-01", [full_run(as_of="2026-08-20")])
    assert not out.graphs
    assert out.deferred == {ss.DEFER_QUARTER_UNCOVERED: 1}

    october = fundamental_row(
        id=2, ticker="BBB", available_at="2026-09-20", computed_at="2026-10-04T10:00:00Z"
    )
    runs = [full_run(1, "2026-08-20"), full_run(2, "2026-10-04")]
    out = ss.project([august, october], ASSETS, "2026-10-05", runs)
    assert [b.key for b in out.graphs["urn:graph:ingest:FUNDAMENTAL:2026-Q3"]] == [1, 2]
    assert not out.deferred


# Review round 3, finding 1: each run below would have closed Q3 under the old rule (the newest
# ``computed_at``); none of them read every Q3 filing.
_AUGUST = fundamental_row(id=1, available_at="2026-07-15", computed_at="2026-08-20T10:00:00Z")
_LATE_RERUN = fundamental_row(
    id=2, ticker="BBB", event_time="2023-12-31", available_at="2024-02-20",
    computed_at="2026-10-01T10:00:00Z",
)  # fmt: skip


@pytest.mark.parametrize(
    "run",
    [
        full_run(as_of="2026-10-01", tickers=["BBB"]),
        full_run(as_of="2026-10-01", forms=["10-K"]),
        full_run(as_of="2026-10-01", since_year=2024, until_year=2024),
        full_run(as_of="2026-10-01", limit=5),
        dataclasses.replace(full_run(as_of="2026-10-01"), status="failed"),
        ss.AnalysisRun(1, "2026-10-01", "completed", {"forms": ["10-K", "10-Q"]}),
    ],
    ids=["one-ticker", "one-form", "old-years", "limit", "not-completed", "scope-unknown"],
)
def test_a_scoped_or_unfinished_run_does_not_close_a_quarter(run: ss.AnalysisRun) -> None:
    out = ss.project([_AUGUST, _LATE_RERUN], ASSETS, "2026-10-02", [run])
    assert "urn:graph:ingest:FUNDAMENTAL:2026-Q3" not in out.graphs
    assert out.deferred[ss.DEFER_QUARTER_UNCOVERED] >= 1


def test_a_run_as_of_inside_the_quarter_does_not_close_it_whenever_it_was_computed() -> None:
    # Computed on Oct 4 but as of Sep 15: it saw no filing after Sep 15.
    out = ss.project([_AUGUST], ASSETS, "2026-10-05", [full_run(as_of="2026-09-15")])
    assert not out.graphs
    assert out.deferred == {ss.DEFER_QUARTER_UNCOVERED: 1}


def test_a_full_run_with_failed_units_still_closes_the_quarter() -> None:
    # Its failures are an accepted loss (the T-031 note): they are listed as lost if they return.
    run = ss.AnalysisRun.from_row(
        {
            "run_id": 1,
            "as_of": "2026-10-04",
            "status": "completed",
            "failed_units": 3,
            "params_json": json.dumps(full_run().params),
        }
    )
    out = ss.project([_AUGUST], ASSETS, "2026-10-05", [run])
    assert list(out.graphs) == ["urn:graph:ingest:FUNDAMENTAL:2026-Q3"]


def test_the_run_years_must_reach_the_quarter_and_the_fiscal_year_before_it() -> None:
    assert full_run(since_year=2025, until_year=2026).covers(2026)
    assert not full_run(since_year=2026, until_year=2026).covers(2026)
    assert not full_run(since_year=2020, until_year=2025).covers(2026)
    assert full_run(since_year=None, until_year=None).covers(2026)


@pytest.mark.parametrize("params_json", [None, "not json", "[1]"])
def test_a_run_whose_params_cannot_be_read_stops_the_projection(params_json: Any) -> None:
    row = {"run_id": 4, "as_of": "2026-10-04", "status": "completed", "params_json": params_json}
    with pytest.raises(ss.ProjectionError, match="v_analysis_run run_id=4: params_json"):
        ss.AnalysisRun.from_row(row)


def test_a_completed_run_without_its_as_of_is_named_by_its_run_id() -> None:
    # Review round 5, finding 2: the message named v_score_snapshot and no row.
    row = {"run_id": 7, "as_of": None, "status": "completed", "params_json": "{}"}
    with pytest.raises(ss.ProjectionError) as stop:
        ss.AnalysisRun.from_row(row)
    assert str(stop.value) == "v_analysis_run run_id=7: as_of None is not a date"


def test_a_snapshot_row_with_a_bad_date_is_named_by_its_id() -> None:
    with pytest.raises(ss.ProjectionError, match=r"^v_score_snapshot id=9: event_time 'x'"):
        ss.snapshot_block(snapshot_row(id=9, event_time="x"))


# --- the run day is the as-of day ----------------------------------------------------------------


def test_a_row_not_yet_available_on_the_run_day_waits_for_a_later_run_day() -> None:
    # Review round 3, finding 2: an October row never lands in a March graph.
    october = snapshot_row(id=1, event_time="2026-10-05", available_at="2026-10-05")
    out = ss.project([october], ASSETS, "2026-03-01")
    assert not out.graphs
    assert out.deferred == {ss.DEFER_NOT_AVAILABLE: 1}
    out = ss.project([october], ASSETS, "2026-10-05")
    assert list(out.graphs) == ["urn:graph:ingest:TECHNICAL:2026-10-05"]


def test_a_replay_counts_only_the_runs_as_of_its_run_day() -> None:
    # On 2026-04-02 the run that covers Q4 2025 has not happened yet (as of 2026-04-20).
    q4 = fundamental_row(available_at="2025-11-10")
    later = [full_run(as_of="2026-04-20")]
    assert not ss.project([q4], ASSETS, "2026-04-02", later).graphs
    assert ss.project([q4], ASSETS, "2026-04-21", later).graphs


def test_an_unknown_lane_is_an_error_not_a_skip() -> None:
    with pytest.raises(ss.ProjectionError, match="no lane"):
        ss.project([snapshot_row(score_type="SEMANTIC")], ASSETS, "2026-10-07")


# --- run: the whole path over a synthetic database ------------------------------------------------


def _cohort(lane: str, first_id: int, **over: Any) -> list[dict[str, Any]]:
    """Three assets whose normalized_score averages 50, the cohort mean the boundary expects."""
    return [
        snapshot_row(id=first_id + i, ticker=t, score_type=lane, normalized_score=score, **over)
        for i, (t, score) in enumerate([("AAA", 40.0), ("BBB", 50.0), ("CCC", 60.0)])
    ]


def test_a_dry_run_validates_every_graph_and_writes_nothing(tmp_path: Path) -> None:
    rows = [*_cohort("TECHNICAL", 1), fundamental_row(id=10)]
    out = ss.run(financial_db(tmp_path, rows), ASSETS, None, "2026-10-07")
    assert sorted(out.checked) == [
        "urn:graph:ingest:FUNDAMENTAL:2025-Q1",
        "urn:graph:ingest:TECHNICAL:2026-10-07",
    ]
    assert not out.written
    assert not out.rejected
    # It never asked the store, so it does not claim what the gate would say.
    assert "SHACL-valid, not written (store not consulted)" in out.summary()
    # Review round 4, finding 5: no store count it never took.
    assert "already in the store: not checked (dry run)" in out.summary()
    assert "accepted by the gate" not in out.summary()


def _drop_schema_version(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("DROP TABLE schema_version")
        conn.commit()


@pytest.mark.parametrize(
    ("drop", "version"), [(False, 8), (True, 0)], ids=["version-8", "no-table"]
)
def test_the_source_check_runs_first_and_stops_a_database_below_the_floor(
    tmp_path: Path, drop: bool, version: int
) -> None:
    source = financial_db(tmp_path, _cohort("TECHNICAL", 1), version=8)
    if drop:
        _drop_schema_version(tmp_path / "financial.db")
    with pytest.raises(BoundaryError, match=f"schema_version.*{version} is below the floor 9"):
        ss.run(source, ASSETS, None, "2026-10-07")


def test_the_schema_version_is_read_from_upstreams_table_not_the_pragma(tmp_path: Path) -> None:
    source = financial_db(tmp_path, [])
    assert source.schema_version == 9  # PRAGMA user_version is 0 in this database


def test_a_missing_or_empty_schema_version_table_reads_as_zero(tmp_path: Path) -> None:
    source = financial_db(tmp_path, [])
    with closing(sqlite3.connect(tmp_path / "financial.db")) as conn:
        conn.execute("DELETE FROM schema_version")
        conn.commit()
    assert source.schema_version == 0
    _drop_schema_version(tmp_path / "financial.db")
    assert source.schema_version == 0


def test_a_cycle_row_with_no_available_at_is_counted_once_and_not_projected(tmp_path: Path) -> None:
    rows = _cohort("TECHNICAL", 1, available_at=None)
    out = ss.run(financial_db(tmp_path, rows), ASSETS, None, "2026-10-07")
    assert (
        out.report.skipped_by_design[
            ("v_score_snapshot", "available_at is NULL until upstream T-144")
        ]
        == 3
    )
    assert not out.checked


def _store(make_db: MakeDB, graphs: tuple[str, ...] = (), held: tuple[str, ...] = ()) -> Any:
    """A fake store that answers like GraphDB: a graph-existence query finds ``graphs``, a
    subject query finds the ``held`` snapshots it names, and nothing else."""
    store = make_db()

    def select(sparql: str) -> list[dict[str, str]]:
        if any(f"GRAPH <{g}>" in sparql for g in graphs):
            return [{"s": "x", "p": "x", "o": "x"}]
        return [{"s": f"{NS}{h}"} for h in held if f"{NS}{h}>" in sparql]

    store.select = select  # type: ignore[method-assign]
    return store


def _added(store: Any) -> bytes:
    return b"".join(d for d, _, _ in store.added)


def test_a_write_goes_through_the_gate_into_a_new_graph(tmp_path: Path, make_db: MakeDB) -> None:
    store = _store(make_db)
    out = ss.run(financial_db(tmp_path, [fundamental_row(id=10)]), ASSETS, store.db, "2026-10-07")
    assert list(out.written) == ["urn:graph:ingest:FUNDAMENTAL:2025-Q1"]
    assert b"Snap_AAA_Fin_20241231_10" in _added(store)


def test_a_rerun_with_nothing_new_writes_nothing_and_fails_nothing(
    tmp_path: Path, make_db: MakeDB
) -> None:
    store = _store(
        make_db,
        graphs=("urn:graph:ingest:FUNDAMENTAL:2025-Q1",),
        held=("Snap_AAA_Fin_20241231_10",),
    )
    out = ss.run(financial_db(tmp_path, [fundamental_row(id=10)]), ASSETS, store.db, "2026-10-07")
    assert out.already_in_store == 1
    assert not store.added
    assert not out.rejected
    assert not out.skipped


def test_a_new_row_for_a_written_quarter_is_counted_as_lost_not_rejected(
    tmp_path: Path, make_db: MakeDB
) -> None:
    rows = [fundamental_row(id=10), fundamental_row(id=11, ticker="BBB")]  # both 2025-Q1
    store = _store(
        make_db,
        graphs=("urn:graph:ingest:FUNDAMENTAL:2025-Q1",),
        held=("Snap_AAA_Fin_20241231_10",),
    )
    out = ss.run(financial_db(tmp_path, rows), ASSETS, store.db, "2026-10-07")
    assert out.already_in_store == 1
    assert not store.added
    assert not out.rejected  # the gate is never asked to append to the existing graph
    # Lost, as SPEC §13 item 10 says, not a design skip.
    assert [(f.check, f.key) for f in out.report.lost] == [(GRAPH_WRITTEN, (11,))]
    assert "Snap_BBB_Fin_20241231_11 is lost" in out.report.lost[0].detail
    assert not out.skipped
    assert not out.report.skipped_by_design
    assert "lost: v_score_snapshot row (11,): graph_written" in out.summary()


def test_a_same_day_rerun_defers_a_new_cycle_row_to_the_next_run_day(
    tmp_path: Path, make_db: MakeDB
) -> None:
    rows = _cohort("TECHNICAL", 1)
    held = ("Snap_AAA_Tec_20260709_1", "Snap_BBB_Tec_20260709_2")  # row 3 is new
    same_day = _store(make_db, graphs=("urn:graph:ingest:TECHNICAL:2026-10-07",), held=held)
    out = ss.run(financial_db(tmp_path, rows), ASSETS, same_day.db, "2026-10-07")
    assert not same_day.added
    assert not out.rejected
    assert out.deferred[ss.DEFER_DAY_WRITTEN] == 1

    (tmp_path / "financial.db").unlink()
    next_day = _store(make_db, graphs=("urn:graph:ingest:TECHNICAL:2026-10-07",), held=held)
    out = ss.run(financial_db(tmp_path, rows), ASSETS, next_day.db, "2026-10-08")
    assert list(out.written) == ["urn:graph:ingest:TECHNICAL:2026-10-08"]
    assert b"Snap_CCC_Tec_20260709_3" in _added(next_day)
    assert b"Snap_AAA_Tec_20260709_1" not in _added(next_day)


def test_the_summary_lists_each_skip_once_and_deferrals_apart(tmp_path: Path) -> None:
    # Review round 3, finding 4.
    rows = [
        *_cohort("TECHNICAL", 1),
        fundamental_row(id=10, ticker="ZZZ"),  # left out by design: not an asset
        fundamental_row(id=11, available_at="2026-10-03"),  # deferred: its quarter is open
    ]
    out = ss.run(financial_db(tmp_path, rows), ASSETS, None, "2026-10-07")
    text = out.summary()
    assert text.count(ss.SKIP_NOT_AN_ASSET) == 1
    assert f"skipped by design: v_score_snapshot / {ss.SKIP_NOT_AN_ASSET}: 1" in text
    assert text.count(ss.DEFER_QUARTER_OPEN) == 1
    assert f"deferred: {ss.DEFER_QUARTER_OPEN}: 1" in text
    assert "not projected" not in text
    assert ("v_score_snapshot", ss.DEFER_QUARTER_OPEN) not in out.report.skipped_by_design


def test_a_replay_over_two_days_writes_each_row_once_into_the_first_day_it_was_usable(
    tmp_path: Path, make_db: MakeDB
) -> None:
    # Review round 3, finding 2: a cycle row available on Oct 6 is not in the Oct 5 graph.
    rows = [
        *_cohort("TECHNICAL", 1, event_time="2026-10-05", available_at="2026-10-05"),
        *_cohort("TECHNICAL", 4, event_time="2026-10-06", available_at="2026-10-06"),
    ]
    store = live_store(make_db)
    first = ss.run(financial_db(tmp_path, rows), ASSETS, store.db, "2026-10-05")
    assert first.deferred == {ss.DEFER_NOT_AVAILABLE: 3}
    (tmp_path / "financial.db").unlink()
    second = ss.run(financial_db(tmp_path, rows), ASSETS, store.db, "2026-10-06")
    assert list(first.written) == ["urn:graph:ingest:TECHNICAL:2026-10-05"]
    assert list(second.written) == ["urn:graph:ingest:TECHNICAL:2026-10-06"]
    assert second.already_in_store == 3
    by_graph = {g: d for d, _, g in store.added}
    assert b"_Tec_20261005_1>" in by_graph["urn:graph:ingest:TECHNICAL:2026-10-05"]
    assert b"_Tec_20261006_4>" in by_graph["urn:graph:ingest:TECHNICAL:2026-10-06"]
    assert b"_20261005_" not in by_graph["urn:graph:ingest:TECHNICAL:2026-10-06"]


def test_a_quarter_is_not_written_from_a_database_without_a_full_run(tmp_path: Path) -> None:
    out = ss.run(
        financial_db(tmp_path, [fundamental_row(id=10)], runs=[]), ASSETS, None, "2026-10-07"
    )
    assert not out.checked
    assert out.deferred == {ss.DEFER_QUARTER_UNCOVERED: 1}


def test_a_run_upstream_has_not_finished_is_counted_and_never_stops_the_projection(
    tmp_path: Path,
) -> None:
    # Review round 4, finding 2: a run just started may lack its as_of and params.
    source = financial_db(tmp_path, [fundamental_row(id=10)])
    conn = sqlite3.connect(tmp_path / "financial.db")
    conn.execute("INSERT INTO v_analysis_run (run_id, status) VALUES (2, 'running')")
    conn.execute("INSERT INTO v_analysis_run (run_id) VALUES (3)")  # no status yet
    conn.commit()
    conn.close()
    out = ss.run(source, ASSETS, None, "2026-10-07")
    assert out.runs_not_counted == 2
    assert out.checked == ["urn:graph:ingest:FUNDAMENTAL:2025-Q1"]  # run 1 still covers it
    assert "analysis runs not completed, not counted: 2" in out.summary()


def test_a_completed_run_without_its_params_stops_the_projection(tmp_path: Path) -> None:
    source = financial_db(tmp_path, [fundamental_row(id=10)], runs=[])
    conn = sqlite3.connect(tmp_path / "financial.db")
    conn.execute(
        "INSERT INTO v_analysis_run (run_id, as_of, status) VALUES (5, '2026-10-05', 'completed')"
    )
    conn.commit()
    conn.close()
    with pytest.raises(ss.ProjectionError, match="run_id=5: params_json is not JSON"):
        ss.run(source, ASSETS, None, "2026-10-07")


# --- losses: a new one stands out -------------------------------------------------------------


def _written_q1(make_db: MakeDB) -> Any:
    return _store(
        make_db,
        graphs=("urn:graph:ingest:FUNDAMENTAL:2025-Q1",),
        held=("Snap_AAA_Fin_20241231_10",),
    )


def test_a_loss_is_listed_once_then_counted_as_known(tmp_path: Path, make_db: MakeDB) -> None:
    # Review round 3, finding 5.
    keys = tmp_path / "late.json"
    lost = tmp_path / "late.lost.json"  # beside the late-key file
    rows = [fundamental_row(id=10), fundamental_row(id=11, ticker="BBB")]
    out = ss.run(
        financial_db(tmp_path, rows),
        ASSETS,
        _written_q1(make_db).db,
        "2026-10-07",
        late_keys_path=keys,
    )
    assert [f.key for f in out.report.lost] == [(11,)]
    assert json.loads(lost.read_text()) == {"v_score_snapshot": [[11]]}

    (tmp_path / "financial.db").unlink()
    rows.append(fundamental_row(id=12, ticker="CCC"))
    out = ss.run(
        financial_db(tmp_path, rows),
        ASSETS,
        _written_q1(make_db).db,
        "2026-10-08",
        late_keys_path=keys,
    )
    assert [f.key for f in out.report.lost] == [(12,)]  # only the new loss is listed
    assert out.lost_before == 1
    assert "lost in an earlier run (listed then): 1" in out.summary()
    assert json.loads(lost.read_text()) == {"v_score_snapshot": [[11], [12]]}


def test_a_dry_run_reads_the_lost_key_file_but_never_writes_it(tmp_path: Path) -> None:
    keys = tmp_path / "late.json"
    lost = ss.lost_keys_path(keys)
    ss.run(
        financial_db(tmp_path, [fundamental_row(id=10)]),
        ASSETS,
        None,
        "2026-10-07",
        late_keys_path=keys,
    )
    assert not lost.exists()


@pytest.mark.parametrize("damaged", ["[1]", '{"v_score_snapshot": [[1'], ids=["shape", "truncated"])
def test_a_malformed_lost_key_file_stops_the_run_before_anything_is_written(
    tmp_path: Path, make_db: MakeDB, damaged: str
) -> None:
    # Review round 6, finding 2: it was read after the writes, so the run stopped having written.
    keys = tmp_path / "late.json"
    lost = ss.lost_keys_path(keys)
    lost.write_text(damaged)
    store = live_store(make_db)
    with pytest.raises(ss.ProjectionError, match="lost-key file"):
        ss.run(
            financial_db(tmp_path, [fundamental_row(id=10)]),
            ASSETS,
            store.db,
            "2026-10-07",
            late_keys_path=keys,
        )
    assert not store.added
    assert lost.read_text() == damaged


def test_a_missing_key_folder_stops_the_run_before_anything_is_written(
    tmp_path: Path, make_db: MakeDB
) -> None:
    # Review round 6, finding 1: the lost-key file could not be saved after the graph was written.
    store = live_store(make_db)
    with pytest.raises(ss.ProjectionError, match="key files' folder does not exist"):
        ss.run(
            financial_db(tmp_path, [fundamental_row(id=10)]),
            ASSETS,
            store.db,
            "2026-10-07",
            late_keys_path=tmp_path / "keys" / "late.json",
        )
    assert not store.added


def test_the_lost_key_file_is_kept_only_with_a_loss_and_replaced_whole(
    tmp_path: Path, make_db: MakeDB
) -> None:
    keys = tmp_path / "late.json"
    lost = ss.lost_keys_path(keys)
    rows = [fundamental_row(id=10)]
    ss.run(financial_db(tmp_path, rows), ASSETS, live_store(make_db).db, "2026-10-07",
           late_keys_path=keys)  # fmt: skip
    assert not lost.exists()  # nothing lost, nothing to keep

    (tmp_path / "financial.db").unlink()
    rows.append(fundamental_row(id=11, ticker="BBB"))
    ss.run(financial_db(tmp_path, rows), ASSETS, _written_q1(make_db).db, "2026-10-07",
           late_keys_path=keys)  # fmt: skip
    assert json.loads(lost.read_text()) == {"v_score_snapshot": [[11]]}
    assert sorted(p.name for p in tmp_path.iterdir() if "lost" in p.name) == ["late.lost.json"]


def test_a_replay_with_its_own_key_files_never_hides_a_production_loss(
    tmp_path: Path, make_db: MakeDB
) -> None:
    # Review round 4, finding 1: the CLI gives a replay repository its own key files
    # (``<repository>/late.json``); with them, production still lists its own new loss.
    rows = [fundamental_row(id=10), fundamental_row(id=11, ticker="BBB")]
    replay_keys, production_keys = tmp_path / "replay" / "late.json", tmp_path / "late.json"
    replay_keys.parent.mkdir()  # the CLI's key_file creates it
    ss.run(
        financial_db(tmp_path, rows), ASSETS, _written_q1(make_db).db, "2026-10-06",
        late_keys_path=replay_keys,
    )  # fmt: skip
    (tmp_path / "financial.db").unlink()
    out = ss.run(
        financial_db(tmp_path, rows), ASSETS, _written_q1(make_db).db, "2026-10-07",
        late_keys_path=production_keys,
    )  # fmt: skip
    assert [f.key for f in out.report.lost] == [(11,)]
    assert out.lost_before == 0


# --- the store failing partway -------------------------------------------------------------------


def test_a_store_failure_partway_keeps_what_was_written_and_its_late_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    # Review round 3, finding 6: the FUNDAMENTAL graph is written, then the store fails.
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)

    def ingest(_store: Any, _data: bytes, graph: str) -> int:
        if "TECHNICAL" in graph:
            raise gate.WriteInDoubt("connection to GraphDB at h lost")
        return 7

    monkeypatch.setattr(ss.gate, "ingest", ingest)
    rows = [*_cohort("TECHNICAL", 1), fundamental_row(id=10)]
    with pytest.raises(ss.StoreInterrupted, match="connection to GraphDB at h lost") as stop:
        ss.run(
            financial_db(tmp_path, rows), ASSETS, make_db().db, "2026-10-08", late_keys_path=keys
        )
    assert stop.value.result.written == {"urn:graph:ingest:FUNDAMENTAL:2025-Q1": 7}
    assert _late(keys) == [[3]]  # its graph was never written: the next run re-reads it
    # Review round 8, finding 2: the graph sent whose answer was lost may be in the store; it is
    # named, not counted as written, and its keys stay until a run finds it.
    result = stop.value.result
    assert result.in_doubt == "urn:graph:ingest:TECHNICAL:2026-10-08"
    assert "in doubt: urn:graph:ingest:TECHNICAL:2026-10-08: it was sent" in result.summary()


_Q1 = "urn:graph:ingest:FUNDAMENTAL:2025-Q1"


@pytest.mark.parametrize(
    "case",
    [
        ("projection check", AnswerLost("connection lost"), None),
        ("gate check", AnswerLost("connection lost"), None),
        ("send", GraphDBError("POST /statements -> HTTP 400: MALFORMED"), None),
        ("send", AnswerLost("connection lost"), _Q1),
    ],
    ids=["projection-check-lost", "gate-check-lost", "send-answered-http-400", "send-answer-lost"],
)
def test_only_a_graph_sent_whose_answer_was_lost_is_in_doubt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_db: MakeDB,
    case: tuple[str, GraphDBError, str | None],
) -> None:
    # Review round 9, finding 1: a failed check (before anything is sent, whether the
    # projection's or the gate's own) and an HTTP error (the store's answer) write nothing.
    where, error, in_doubt = case
    store = live_store(make_db)

    def fail(*_: Any) -> Any:
        raise error

    if where == "projection check":
        monkeypatch.setattr(store, "select", fail)
    elif where == "send":
        monkeypatch.setattr(store, "add", fail)
    else:
        real = gate.ingest

        def ingest(db: Any, data: bytes, graph: str) -> int:
            monkeypatch.setattr(store, "select", fail)  # the gate's own checks fail
            return real(db, data, graph)

        monkeypatch.setattr(ss.gate, "ingest", ingest)
    with pytest.raises(ss.StoreInterrupted) as stop:
        ss.run(financial_db(tmp_path, [fundamental_row(id=10)]), ASSETS, store.db, "2026-10-07")
    result = stop.value.result
    assert store.added == []
    assert result.in_doubt == in_doubt
    assert ("in doubt" in result.summary()) == (in_doubt is not None)


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
        financial_db(tmp_path, bad),
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
    second = ss.run(
        financial_db(tmp_path, fixed), ASSETS, store.db, "2026-10-08", late_keys_path=keys
    )
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
    ss.run(financial_db(tmp_path, bad), ASSETS, make_db().db, "2026-10-07", late_keys_path=keys)

    (tmp_path / "financial.db").unlink()
    gone = _cohort("TECHNICAL", 1)[:2]  # row 3 was deleted upstream
    out = ss.run(
        financial_db(tmp_path, gone), ASSETS, make_db().db, "2026-10-08", late_keys_path=keys
    )
    assert out.late_not_found == ["v_score_snapshot id=3"]
    assert json.loads(keys.read_text()).get("v_score_snapshot", {"keys": []})["keys"] == []


def _delay_row_3(tmp_path: Path, make_db: MakeDB, keys: Path) -> None:
    """A first run that writes rows 1 and 2 on 2026-10-07 and delays row 3 (a type failure)."""
    bad = _cohort("TECHNICAL", 1)
    bad[2]["raw_value"] = "n/a"
    ss.run(financial_db(tmp_path, bad), ASSETS, make_db().db, "2026-10-07", late_keys_path=keys)
    assert _late(keys) == [[3]]
    (tmp_path / "financial.db").unlink()


def _late(keys: Path) -> list[list[int]]:
    keys_now: list[list[int]] = json.loads(keys.read_text()).get("v_score_snapshot", {"keys": []})[
        "keys"
    ]
    return keys_now


def test_a_dry_run_reports_a_vanished_late_key_but_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)
    gone = _cohort("TECHNICAL", 1)[:2]
    out = ss.run(financial_db(tmp_path, gone), ASSETS, None, "2026-10-08", late_keys_path=keys)
    assert out.late_not_found == ["v_score_snapshot id=3"]
    assert _late(keys) == [[3]]


def test_a_late_key_whose_row_is_left_out_by_design_is_closed_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)
    fixed = _cohort("TECHNICAL", 1, available_at=None)  # every cycle row before upstream T-144
    out = ss.run(
        financial_db(tmp_path, fixed), ASSETS, make_db().db, "2026-10-08", late_keys_path=keys
    )
    assert out.late_closed == [f"v_score_snapshot id=3 ({ss.LEFT_NULL_AVAILABLE_AT})"]
    assert _late(keys) == []


def test_a_late_key_whose_snapshot_is_already_in_the_store_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)
    store = _store(make_db, held=("Snap_CCC_Tec_20260709_3",))
    fixed = _cohort("TECHNICAL", 1)
    out = ss.run(financial_db(tmp_path, fixed), ASSETS, store.db, "2026-10-08", late_keys_path=keys)
    assert out.late_closed == [f"v_score_snapshot id=3 ({ss.LEFT_IN_STORE})"]
    assert _late(keys) == []


def test_a_late_key_stays_while_its_row_waits_for_a_later_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)
    store = _store(
        make_db,
        graphs=("urn:graph:ingest:TECHNICAL:2026-10-07",),
        held=("Snap_AAA_Tec_20260709_1", "Snap_BBB_Tec_20260709_2"),
    )
    fixed = _cohort("TECHNICAL", 1)
    out = ss.run(financial_db(tmp_path, fixed), ASSETS, store.db, "2026-10-07", late_keys_path=keys)
    assert out.deferred[ss.DEFER_DAY_WRITTEN] == 1
    assert not out.late_closed
    assert _late(keys) == [[3]]


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


def test_a_refused_graph_is_reported_and_keeps_its_late_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db: MakeDB
) -> None:
    _allow_one_loss(monkeypatch)
    keys = tmp_path / "late.json"
    _delay_row_3(tmp_path, make_db, keys)

    def refuse(*_: Any, **__: Any) -> int:
        raise gate.IngestRejected("shapes.ttl: no")

    monkeypatch.setattr(ss.gate, "ingest", refuse)
    store = _store(make_db)
    fixed = _cohort("TECHNICAL", 1)
    out = ss.run(financial_db(tmp_path, fixed), ASSETS, store.db, "2026-10-08", late_keys_path=keys)
    assert out.rejected == {"urn:graph:ingest:TECHNICAL:2026-10-08": "shapes.ttl: no"}
    assert not out.written
    assert not store.added
    assert not out.late_closed
    assert _late(keys) == [[3]]  # the row is not in the store: the next run re-reads it
