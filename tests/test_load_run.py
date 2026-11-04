"""``projection.load_run``: the ordered stages, the table and the rollback commands (Work item 29).

The projectors, gate and verifier have their own tests; these use the synthetic database and
replace only the expensive stages with recorded fakes, so the sequence and its stopping rule are
what is under test.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fixtures.backtest_rows import ASSETS, backtest_db

from projection import load_run
from projection.backtest import RunResult
from projection.boundary import BoundaryReport
from projection.project_backtest import Database
from projection.verify_backtest import Check, Verification

M018 = "urn:graph:derived:backtest:rule:P1:1"
SELECTION = "urn:graph:derived:backtest:selection:rule:P1:1"


class FakeStore:
    repository = "test"
    host = "http://store.invalid"


def _result(graphs: dict[str, int], written: dict[str, int] | None = None) -> RunResult:
    return RunResult(
        BoundaryReport(),
        Counter(),
        Counter(),
        graphs=graphs,
        written=written or {},
    )


def _patch_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    return backtest_db(tmp_path)


def _patch_stages(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verify_side_effect: Callable[[str], Verification],
) -> list[str]:
    calls: list[str] = []

    def dry(database: Database, *_args: Any) -> tuple[RunResult, RunResult]:
        calls.append(f"dry:{database.path.name}")
        return (
            _result({M018: 10}, {}),
            _result({SELECTION: 20}, {}),
        )

    def write_m018(database: Database, *_args: Any) -> RunResult:
        calls.append(f"write-m018:{database.path.name}")
        return _result({M018: 10}, {M018: 10})

    def write_selection(database: Database, *_args: Any) -> RunResult:
        calls.append(f"write-selection:{database.path.name}")
        return _result({SELECTION: 20}, {SELECTION: 20})

    def verify_graph(graph: str, *_args: Any, **_kwargs: Any) -> Verification:
        calls.append(f"verify:{graph}")
        return verify_side_effect(graph)

    monkeypatch.setattr(load_run, "_dry_run", dry)
    monkeypatch.setattr(load_run, "_write_m018", write_m018)
    monkeypatch.setattr(load_run, "_write_selection", write_selection)
    monkeypatch.setattr(load_run, "_verify_graph", verify_graph)
    monkeypatch.setattr(load_run, "open_store", lambda _args: FakeStore())
    return calls


def test_a_dry_run_prints_both_graphs_and_a_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    assert load_run.main(["--label", "rule", "--db", str(path)]) == 0
    printed = capsys.readouterr().out
    assert M018 in printed
    assert SELECTION in printed
    assert "not verified (dry run)" in printed


def test_a_directory_is_discovered_by_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    backtest_db(tmp_path, name="rule_P1.db", window="P1")
    backtest_db(tmp_path, name="rule_P2.db", window="P2")
    (tmp_path / "other.db").write_bytes(b"not a database")
    assert load_run.main(["--label", "rule", "--dir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "backtest:rule:P1:1" in printed
    assert "backtest:rule:P2:1" in printed
    assert "other.db" not in printed


def test_a_bad_directory_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert load_run.main(["--label", "rule", "--dir", "/no/such/directory"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_two_databases_naming_the_same_graph_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(load_run, "universe_assets", lambda _path: ASSETS)
    first = backtest_db(tmp_path, name="a.db")
    second = backtest_db(tmp_path, name="b.db")
    assert load_run.main(["--label", "rule", "--db", str(first), "--db", str(second)]) == 2
    assert "would both write" in capsys.readouterr().err


def test_a_verification_failure_stops_the_sequence_and_prints_the_drops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    calls = _patch_stages(
        monkeypatch,
        verify_side_effect=lambda graph: Verification(
            "test", "", graph, "rule", path, [Check("graph", False, "stored graph differs")]
        ),
    )
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 1
    printed = capsys.readouterr()
    assert [call for call in calls if call.startswith("verify:")] == [f"verify:{M018}"]
    assert f"DROP GRAPH <{M018}>" in printed.err
    assert f"DROP GRAPH <{SELECTION}>" in printed.err
    assert "0/1" in printed.out
    assert "stored graph differs" in printed.out


def test_a_passing_write_verifies_every_graph_and_prints_the_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    calls = _patch_stages(
        monkeypatch,
        verify_side_effect=lambda graph: Verification(
            "test", "", graph, "rule", path, [Check("graph", True, "ok")], triples=10
        ),
    )
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 0
    printed = capsys.readouterr()
    assert [call for call in calls if call.startswith("verify:")] == [
        f"verify:{M018}",
        f"verify:{SELECTION}",
    ]
    assert "1/1" in printed.out
    assert "DROP GRAPH" not in printed.err


def test_a_write_failure_after_m018_still_prints_the_written_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _patch_inputs(monkeypatch, tmp_path)
    calls = _patch_stages(
        monkeypatch,
        verify_side_effect=lambda graph: pytest.fail("verification must not run"),
    )

    def fail(*_args: Any, **_kwargs: Any) -> RunResult:
        raise load_run.LoadError("selection write refused")

    monkeypatch.setattr(load_run, "_write_selection", fail)
    assert load_run.main(["--label", "rule", "--db", str(path), "--write"]) == 1
    printed = capsys.readouterr()
    assert f"write-m018:{path.name}" in calls
    assert f"DROP GRAPH <{M018}>" in printed.err
    assert f"DROP GRAPH <{SELECTION}>" not in printed.err


def test_a_plan_error_exits_2_before_any_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = backtest_db(tmp_path)
    monkeypatch.setattr(load_run, "_dry_run", lambda *_args, **_kwargs: pytest.fail("must not run"))
    assert load_run.main(["--label", "rule", "--db", str(path), "--db", str(path)]) == 2
    assert "given twice" in capsys.readouterr().err
