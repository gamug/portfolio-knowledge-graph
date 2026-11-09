"""Synthetic ``mv_base`` delivery used by the Work item 44 tests."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
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


def write_engine(
    tmp_path: Path,
    doc: dict[str, Any] | None = None,
    *,
    book_id: int = 5,
    run_id: int = 42,
    rebalances: dict[tuple[str, str], int] | None = None,
) -> Path:
    """A synthetic final_corregida folder with only the two views the loader reads."""
    payload = copy.deepcopy(doc) if doc is not None else document()
    engine = tmp_path / "engine"
    engine.mkdir(exist_ok=True)
    rows = payload["summary"]
    by_window: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_window.setdefault(row["window"], []).append(row)
    for window, window_rows in by_window.items():
        path = engine / f"final_{window}.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE v_book (book_id INTEGER, backtest_run_id INTEGER, window_id TEXT, "
                "d_start TEXT, d_end TEXT, formation_date TEXT, run_status TEXT, arm_code TEXT, "
                "objective TEXT, exclude_hard_vetoed INTEGER, guard_layers TEXT, "
                "code_version TEXT, knowledge_date TEXT)"
            )
            connection.execute(
                "CREATE TABLE v_portfolio_period_summary (book_id INTEGER, "
                "backtest_run_id INTEGER, arm_code TEXT, window_id TEXT, segment TEXT, "
                "date_from TEXT, date_to TEXT, cumulative_return REAL, annualized_return REAL, "
                "annualized_vol REAL, ex_post_sharpe REAL, max_drawdown REAL, total_turnover REAL, "
                "total_cost_bps REAL, n_rebalances INTEGER, n_guard_actions INTEGER, "
                "knowledge_date TEXT)"
            )
            whole = next(row for row in window_rows if row["segment"] == window)
            connection.execute(
                "INSERT INTO v_book VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    book_id,
                    run_id,
                    window,
                    whole["date_from"],
                    whole["date_to"],
                    None,
                    "completed",
                    "MARKOWITZ_BASE",
                    "min_var",
                    0,
                    None,
                    None,
                    whole["date_to"],
                ),
            )
            for row in window_rows:
                n_rebalances = row["n_rebalances"]
                if rebalances and (window, row["segment"]) in rebalances:
                    n_rebalances = rebalances[(window, row["segment"])]
                connection.execute(
                    "INSERT INTO v_portfolio_period_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        book_id,
                        run_id,
                        "MARKOWITZ_BASE",
                        window,
                        row["segment"],
                        row["date_from"],
                        row["date_to"],
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        n_rebalances,
                        0,
                        row["date_to"],
                    ),
                )
            connection.commit()
        finally:
            connection.close()
    return engine
