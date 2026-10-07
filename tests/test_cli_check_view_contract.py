"""``cli/check_view_contract.py`` as a subprocess: its exit code is the CI gate (T-136)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from projection.view_contract import VIEW_COLUMNS

CLI = Path(__file__).resolve().parent.parent / "cli" / "check_view_contract.py"

_ENSURE = (
    "from . import views\n"
    "def ensure(db, run_migrations=False):\n"
    "    for name, select in views.VIEWS.items():\n"
    "        db.execute(f'CREATE VIEW {name} AS {select}')\n"
)


def _upstream(root: Path, views: dict[str, str]) -> Path:
    """A miniature upstream checkout whose ``kg_schema`` defines exactly ``views``."""
    pkg = root / "src" / "kg_schema"
    pkg.mkdir(parents=True)
    (pkg / "views.py").write_text(f"VIEWS = {views!r}\n")
    (pkg / "__init__.py").write_text(_ENSURE)
    return root


def _matching_views() -> dict[str, str]:
    """One constant-select view per pinned view, with exactly the pinned columns."""
    return {
        view: "SELECT " + ", ".join(f"1 AS {c}" for c in columns)
        for view, columns in VIEW_COLUMNS.items()
    }


def _run(upstream: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, tmp_path argument
        [sys.executable, str(CLI), str(upstream)], capture_output=True, text=True, check=False
    )


def test_exit_0_when_upstream_matches_the_pin(tmp_path: Path) -> None:
    result = _run(_upstream(tmp_path, _matching_views()))
    assert result.returncode == 0, result.stderr
    assert "view contract: OK" in result.stdout
    assert "DRIFT" not in result.stdout


def test_exit_1_and_a_drift_line_when_a_pinned_column_goes(tmp_path: Path) -> None:
    view, columns = next(iter(VIEW_COLUMNS.items()))
    views = _matching_views()
    views[view] = "SELECT " + ", ".join(f"1 AS {c}" for c in columns[1:])
    result = _run(_upstream(tmp_path, views))
    assert result.returncode == 1
    assert f"DRIFT {view}: pinned columns removed ['{columns[0]}']" in result.stdout
    assert "1 drift(s)" in result.stdout


def test_added_column_is_a_note_and_still_exit_0(tmp_path: Path) -> None:
    view = next(iter(VIEW_COLUMNS))
    views = _matching_views()
    views[view] += ", 1 AS brand_new_column"
    result = _run(_upstream(tmp_path, views))
    assert result.returncode == 0, result.stderr
    assert f"NOTE  {view}: columns added upstream ['brand_new_column']" in result.stdout


def test_a_view_ensure_cannot_create_exits_1_with_a_traceback_and_no_drift_lines(
    tmp_path: Path,
) -> None:
    """The exit code alone does not tell this from drift (PR #57 review): stderr and stdout do."""
    view = next(iter(VIEW_COLUMNS))
    views = _matching_views()
    views[view] = "SELECT no_such_column FROM assets"
    result = _run(_upstream(tmp_path, views))
    assert result.returncode == 1
    assert "Traceback" in result.stderr
    assert "no_such_column" in result.stderr
    assert "DRIFT" not in result.stdout
    assert "view contract" not in result.stdout
