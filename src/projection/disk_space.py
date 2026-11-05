"""Read-only free-disk guard for a GraphDB write (Work item 35).

GraphDB 11.5's documented REST surface has no free-disk endpoint (a read-only probe of
``/rest/monitor/system``, ``/rest/monitor/storage`` and ``/rest/monitor/disk`` answers 406 on the
live 11.5 store used for the final backtest). The loader therefore probes those paths, parses a
free/total pair when one appears, and otherwise prints a ``df -h`` reminder. It never guesses a
percentage and never writes.

GraphDB's own hard floor is 5% free: below it every write is refused with HTTP 500 "Critically low
disk space". The loader's default threshold is 8%, a safety margin above that floor; the user can
raise or lower it with ``--min-free-pct`` but the hard floor itself is not configurable.
"""

from __future__ import annotations

import json
from typing import Any

from kg_store.graphdb import GraphDB, GraphDBError

#: Candidate read-only monitoring endpoints, tried in order. Unknown paths answer 406 on 11.5.
_DISK_PATHS = ("/rest/monitor/system", "/rest/monitor/storage", "/rest/monitor/disk")
_FREE_WORDS = ("free", "available", "usable")
_TOTAL_WORDS = ("total", "capacity", "size")
_PERCENT = 100.0
_FULL_PERCENT = 100.0


class DiskSpaceError(RuntimeError):
    """The store's volume is below the configured free-space threshold (nothing was written)."""


def free_disk_percent(store: GraphDB) -> float | None:
    """The store volume's free percentage from a read-only endpoint, or None when unavailable."""
    request = getattr(store, "_request", None)
    if request is None:  # a test store with no HTTP surface
        return None
    for path in _DISK_PATHS:
        try:
            raw = request("GET", store.host + path, accept="application/json")
        except GraphDBError:
            continue
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            continue
        percent = _find_percent(payload)
        if percent is not None:
            return percent
    return None


class DiskMonitor:
    """Check the store's free space before the run and between windows, once per run."""

    def __init__(self, store: GraphDB, minimum: float) -> None:
        self.store = store
        self.minimum = minimum
        self._percent: float | None = None
        self._reminded = False

    def check(self, where: str, *, before_write: bool = False) -> None:
        # Re-probe between windows: a long delivery can consume the headroom the first probe saw.
        self._percent = free_disk_percent(self.store)
        if self._percent is None:
            if before_write or not self._reminded:
                print(
                    "disk: GraphDB exposes no free-disk REST endpoint; check the data volume with "
                    "`df -h` (below 5% free GraphDB refuses every write).",
                    flush=True,
                )
                self._reminded = True
            return
        print(
            f"disk: {where}: GraphDB volume free {self._percent:.1f}% "
            f"(minimum {self.minimum:.1f}%)",
            flush=True,
        )
        if self._percent < self.minimum:
            raise DiskSpaceError(
                f"GraphDB's data volume has {self._percent:.1f}% free, below the "
                f"{self.minimum:.1f}% minimum: free space before writing "
                "(GraphDB itself refuses writes below 5%)."
            )


def _find_percent(payload: Any) -> float | None:  # noqa: C901 -- one branch per payload shape
    """Find a percentage or a free/total pair anywhere in a monitoring payload."""
    if isinstance(payload, dict):
        flattened = {_key(key): value for key, value in payload.items()}
        for key, value in flattened.items():
            if "percent" in key and any(word in key for word in _FREE_WORDS):
                number = _number(value)
                if number is not None and 0 <= number <= _PERCENT:
                    return number
        free = _number(_matching(flattened, _FREE_WORDS))
        total = _number(_matching(flattened, _TOTAL_WORDS))
        if free is not None and total:
            return free / total * _PERCENT
        for value in payload.values():
            found = _find_percent(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_percent(value)
            if found is not None:
                return found
    return None


def _key(text: object) -> str:
    return "".join(character for character in str(text).lower() if character.isalnum())


def _matching(values: dict[str, Any], words: tuple[str, ...]) -> Any | None:
    for key, value in values.items():
        if any(word in key for word in words) and not isinstance(value, (dict, list)):
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
