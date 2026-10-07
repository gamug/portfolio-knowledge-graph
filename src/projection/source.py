"""Open upstream's financial database for reading (T-031).

``portfolio-financial-analysis`` records its schema version in a ``schema_version`` table
(``MAX(version)``) and leaves ``PRAGMA user_version`` at 0, which is what
``portfolio_common.db.Database.schema_version`` reads. The boundary's source check wants the
first, so the database is wrapped here instead of being handed to it as it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from portfolio_common.db import Database


class FinancialSource:
    """A read-only connection whose ``schema_version`` is upstream's own table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @classmethod
    def open(cls, path: str | Path) -> FinancialSource:
        return cls(Database.connect(path, read_only=True))

    @property
    def schema_version(self) -> int:
        row = self._db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0] or 0)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return self._db.execute(sql, params)

    def close(self) -> None:
        self._db.close()
