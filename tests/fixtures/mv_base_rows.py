"""Synthetic ``mv_base`` delivery used by the Work item 44 tests."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ARM = "MARKOWITZ_MV"
SIM_HASH = "4d23f30749f7e246a4304b3eab3e5a1e3d92cd604a5dc3beb47e485ddeae17b2"

CONFIG = """---
label: final
book_code: MARKOWITZ_MV
status: final
revision: 2026-11-09
---

The mean-variance base case (tangency portfolio), computed outside the engine.

Integrity. sha256 of `sim_v3.py`: `4d23f30749f7e246a4304b3eab3e5a1e3d92cd604a5dc3beb47e485ddeae17b2`.
"""


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


def write_mv_base(tmp_path: Path, doc: dict[str, Any] | None = None, config: str = CONFIG) -> Path:
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
