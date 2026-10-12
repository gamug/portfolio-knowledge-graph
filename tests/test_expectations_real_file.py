"""The shipped view expectations over the rows of a real version-12 database.

Opt in with ``-m integration`` and ``PILOT_DB=<path to financial_pilot_v12.db>`` (exported). Every
other test builds its rows in memory, so none of them can tell that an expectation is wrong for
what upstream really writes (T-157: a natural key of ``metric_id`` alone, which repeats on every
filing, passed 670 tests and stopped the real file). Run it before every re-pin and note the
result in the PR; nothing runs it for you (no CI, constitution Code & Git #1). The file is opened
read-only.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from projection.boundary import validate
from projection.expectations import load_expectations
from projection.view_contract import VIEW_COLUMNS

ENV_VAR = "PILOT_DB"


def _rows(conn: sqlite3.Connection, view: str) -> list[dict[str, Any]]:
    cursor = conn.execute(f"SELECT * FROM {view}")  # noqa: S608 -- a pinned view name, not input
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


@pytest.mark.integration
@pytest.mark.parametrize("view", sorted(VIEW_COLUMNS))
def test_the_shipped_expectations_hold_over_the_real_rows(view: str) -> None:
    value = os.environ.get(ENV_VAR)
    if not value:
        pytest.skip(f"{ENV_VAR} is not set")
    path = Path(value)
    if not path.is_file():  # a typo must not read as "1 skipped"
        pytest.fail(f"{ENV_VAR}={value} is not a file")
    expectations = load_expectations()
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as conn:
        rows = _rows(conn, view)
    result = validate({view: rows}, {view: expectations[view]})  # raises BoundaryError on a stop
    print(f"\n{view}: {len(rows)} rows, {len(result.rows[view])} kept")
