"""A tiny ``universe.db`` for the asset-master loader tests (T-220).

One row per membership stint, the shape ``etl.asset_master.read_stints`` reads. The scenario
covers what ``--since`` and the shapes must get right:

* ``CEG`` has two eras: an old closed stint (dropped by ``--since``) and a current open one.
* ``GONE`` is a CIK-less company whose only membership is closed (``AssetShape`` allows it).
* ``BRK.B`` carries a dot in its ticker.
* ``OLDT`` closed before ``--since`` and disappears entirely.
* ``AAPL`` is one of ``schema/reference.ttl``'s five worked-example assets, so the loader must
  give it memberships but never re-declare its ``:Asset`` block.
"""

from __future__ import annotations

from pathlib import Path

from portfolio_common.db import Database

Row = tuple[str, str, str | None, str | None, str | None, str, str | None]

_DDL = (
    "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
    "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
)
_INSERT = "INSERT INTO universe_membership VALUES (?,?,?,?,?,?,?)"

ROWS: list[Row] = [
    # symbol, security, sector, sub-industry, cik, valid_from, valid_to
    (
        "AAPL",
        "Apple Inc.",
        "Information Technology",
        "Technology Hardware, Storage & Peripherals",
        "0000320193",
        "2019-01-03",
        None,
    ),
    ("CEG", "Constellation Energy Group", None, None, None, "1976-07-01", "2012-03-12"),
    (
        "CEG",
        "Constellation Energy",
        "Utilities",
        "Electric Utilities",
        "0001868275",
        "2022-02-02",
        None,
    ),
    ("GONE", "Gone Corp", None, None, None, "2020-01-02", "2021-06-01"),
    (
        "BRK.B",
        "Berkshire Hathaway Inc.",
        "Financials",
        "Multi-Sector Holdings",
        "0001067983",
        "2019-01-02",
        None,
    ),
    (
        "OLDT",
        "Old Ticker Co",
        "Industrials",
        "Aerospace & Defense",
        "0000000009",
        "2005-01-03",
        "2018-12-31",
    ),
]


def universe_db(path: Path, rows: list[Row] | None = None) -> Path:
    """Write the scenario (or ``rows``) into ``path`` and return it."""
    db = Database.connect(path)
    try:
        db.execute(_DDL)
        db.executemany(_INSERT, rows if rows is not None else ROWS)
        db.commit()
    finally:
        db.close()
    return path
