"""``projection.contract_check``: the pinned ``v_*`` contract vs. a synthetic miniature upstream."""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from projection import contract_check

# Upstream checkout builder: (views: name -> SELECT, broken: names whose view is never created).
MakeUpstream = Callable[..., Path]


@pytest.fixture
def make_upstream(tmp_path: Path) -> MakeUpstream:
    """Write a miniature ``src/kg_schema`` package: ``views.VIEWS`` plus ``ensure``."""

    def build(views: dict[str, str], broken: tuple[str, ...] = ()) -> Path:
        pkg = tmp_path / "src" / "kg_schema"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "views.py").write_text(f"VIEWS = {views!r}\n")
        (pkg / "__init__.py").write_text(
            "from . import views\n"
            f"BROKEN = {broken!r}\n"
            "def ensure(db, run_migrations=False):\n"
            "    for name, select in views.VIEWS.items():\n"
            "        if name not in BROKEN:\n"
            "            db.execute(f'CREATE VIEW {name} AS {select}')\n"
        )
        return tmp_path

    return build


@pytest.fixture(autouse=True)
def pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin two views and list one deliberately unread view, instead of the real contract."""
    monkeypatch.setattr(
        contract_check,
        "VIEW_COLUMNS",
        {"v_a": ["id", "ticker"], "v_b": ["id", "name"]},
    )
    monkeypatch.setattr(contract_check, "NOT_READ", {"v_frozen": "not read"})


_AB = {
    "v_a": "SELECT id, ticker FROM assets",
    "v_b": "SELECT id, name FROM sectors",
}


def test_matching_upstream_has_no_drift_and_no_notes(make_upstream: MakeUpstream) -> None:
    report = contract_check.check(make_upstream(_AB))
    assert report.drift == []
    assert report.notes == []


def test_removed_pinned_column_is_drift(make_upstream: MakeUpstream) -> None:
    views = {**_AB, "v_a": "SELECT id FROM assets"}
    report = contract_check.check(make_upstream(views))
    assert report.drift == ["v_a: pinned columns removed ['ticker']"]


def test_view_gone_upstream_is_drift(make_upstream: MakeUpstream) -> None:
    report = contract_check.check(make_upstream({"v_a": _AB["v_a"]}))
    assert report.drift == ["v_b: no longer defined upstream"]


def test_view_that_did_not_build_is_drift(make_upstream: MakeUpstream) -> None:
    report = contract_check.check(make_upstream(_AB, broken=("v_b",)))
    assert len(report.drift) == 1
    assert report.drift[0].startswith("v_b: did not build")


def test_new_unlisted_view_is_drift(make_upstream: MakeUpstream) -> None:
    views = {**_AB, "v_new": "SELECT id FROM assets"}
    report = contract_check.check(make_upstream(views))
    assert report.drift == ["v_new: new upstream view, neither pinned nor listed in NOT_READ"]


def test_new_view_listed_in_not_read_is_fine(make_upstream: MakeUpstream) -> None:
    views = {**_AB, "v_frozen": "SELECT id FROM assets"}
    assert contract_check.check(make_upstream(views)).drift == []


def test_added_column_is_a_note_not_drift(make_upstream: MakeUpstream) -> None:
    views = {**_AB, "v_a": "SELECT id, ticker, cik FROM assets"}
    report = contract_check.check(make_upstream(views))
    assert report.drift == []
    assert report.notes == ["v_a: columns added upstream ['cik']"]


def test_reordered_columns_are_a_note_not_drift(make_upstream: MakeUpstream) -> None:
    views = {**_AB, "v_a": "SELECT ticker, id FROM assets"}
    report = contract_check.check(make_upstream(views))
    assert report.drift == []
    assert report.notes == ["v_a: column order changed"]


def test_upstream_kg_schema_is_loaded_privately_and_unloaded(
    make_upstream: MakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A kg_schema already imported from elsewhere must be neither reused nor disturbed, and
    # the private upstream module must not leak into sys.modules afterwards.
    sentinel = object()
    monkeypatch.setitem(sys.modules, "kg_schema", sentinel)
    columns = contract_check.upstream_view_columns(make_upstream(_AB))
    assert columns == {"v_a": ["id", "ticker"], "v_b": ["id", "name"]}
    assert sys.modules["kg_schema"] is sentinel
    assert not [m for m in sys.modules if m.startswith("_upstream_kg_schema")]


def test_missing_kg_schema_package_raises_and_leaves_no_module(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        contract_check.upstream_view_columns(tmp_path)
    assert not [m for m in sys.modules if m.startswith("_upstream_kg_schema")]
