"""Synthetic ``aggregates_<label>.json`` files and their source databases (Work item 37).

The shapes mirror the real file's contract, never its data values: the dictionary text is the
upstream text the ontology must copy verbatim, and every date/return below is synthetic. The helper
writes the file and a strict ``SHA256SUMS`` entry so the CLI and verifier tests use the real
manifest path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fixtures.backtest_rows import scenario_rows

LABEL = "rule"
ARMS = ["TOPN_MV_NOGUARD", "TOPN_MV_GUARD_NO_NLP"]
TREND_FILTER_DICTIONARY = {
    "window": "backtest window id (P1, H1, P3, H2, P2, H3)",
    "decision_date": "ISO date of the decision session (the close the filter reads); the same dates as v_book_rebalance.decision_date of the Top-N arms",
    "spy_vs_sma210": "'below' = SPY's close at decision_date is below the simple mean of its last 210 session closes (filter triggered); 'at_or_above' = not triggered; 'not_evaluable' = fewer than 210 sessions (filter off). No level or mean value is published",
    "cash_fraction": "fraction of the Top-N target (SPY core + satellite) moved to cash by the filter at this decision, held until the next decision date: the run's filter_exit when 'below', else 0.0. GUARD layers act on top of it in TOPN_MV_GUARD_NO_NLP; the base arms (MARKOWITZ_BASE, MARKOWITZ_BASE_GUARD) never use the filter",
}
REFERENCE_RETURNS_DICTIONARY = {
    "window": "backtest window id",
    "segment": "reporting segment: the window itself, or P2a / P2b (cuts of P2)",
    "date_from": "ISO date of the segment's first session (the same as backtest_summary.date_from)",
    "date_to": "ISO date of the segment's last session (the same as backtest_summary.date_to)",
    "n_sessions": "number of sessions in the segment",
    "reference": "'SPY' (total return, dividends reinvested) or 'SP500_EW_INTERNAL'",
    "total_return": "prod(1 + r_t) - 1 over the segment's sessions, as a fraction (6 decimals)",
    "max_drawdown": "max_t(1 - NAV_t / max(1, NAV_1..NAV_t)), positive fraction, the same formula as backtest_summary.max_drawdown (6 decimals)",
}
SOURCES = {
    "run_databases": "the .db files listed in SHA256SUMS in this folder",
    "spy_total_return_series_sha256": "a" * 64,
    "spy_source": "Synthetic SPY series (test fixture)",
    "sp500_ew_internal": "Synthetic equal-weight S&P 500 series (test fixture)",
}


def aggregates_document(label: str = LABEL) -> dict[str, Any]:
    """One contract-shaped file with both references, P2a/P2b and a not_evaluable row."""
    return {
        "label": label,
        "config_id": "T37",
        "trend_filter_applies_to_arms": list(ARMS),
        "sources": dict(SOURCES),
        "dictionary": {
            "trend_filter": dict(TREND_FILTER_DICTIONARY),
            "reference_returns": dict(REFERENCE_RETURNS_DICTIONARY),
        },
        "trend_filter": [
            {
                "window": "P1",
                "decision_date": "2022-01-05",
                "spy_vs_sma210": "at_or_above",
                "cash_fraction": 0.0,
            },
            {
                "window": "P1",
                "decision_date": "2022-02-01",
                "spy_vs_sma210": "below",
                "cash_fraction": 0.5,
            },
            {
                "window": "P2",
                "decision_date": "2025-02-18",
                "spy_vs_sma210": "not_evaluable",
                "cash_fraction": 0.0,
            },
        ],
        "reference_returns": [
            *reference_pair("P1", "P1", "2022-01-03", "2022-10-12", 196, (-0.1, 0.05), (0.2, 0.1)),
            *reference_pair("P2", "P2", "2025-02-19", "2025-09-23", 150, (0.1, 0.04), (0.15, 0.12)),
            *reference_pair(
                "P2",
                "P2a",
                "2025-02-19",
                "2025-05-06",
                54,
                (-0.05, -0.02),
                (0.15, 0.12),
            ),
            *reference_pair(
                "P2",
                "P2b",
                "2025-05-07",
                "2025-09-23",
                96,
                (0.157894736842, 0.061224489796),
                (0.03, 0.02),
            ),
        ],
    }


def reference_pair(  # noqa: PLR0913, PLR0917
    window: str,
    segment: str,
    date_from: str,
    date_to: str,
    sessions: int,
    returns: tuple[float, float],
    drawdowns: tuple[float, float],
) -> list[dict[str, Any]]:
    """The two reference rows of one segment (SPY and SP500_EW_INTERNAL), in contract order."""
    return [
        {
            "window": window,
            "segment": segment,
            "date_from": date_from,
            "date_to": date_to,
            "n_sessions": sessions,
            "reference": reference,
            "total_return": total,
            "max_drawdown": drawdown,
        }
        for reference, total, drawdown in zip(
            ("SPY", "SP500_EW_INTERNAL"), returns, drawdowns, strict=True
        )
    ]


def write_aggregates(
    directory: Path, document: dict[str, Any] | None = None, *, label: str = LABEL
) -> Path:
    """Write ``aggregates_<label>.json`` and its lowercase-hash ``SHA256SUMS`` entry."""
    directory.mkdir(parents=True, exist_ok=True)
    data = document if document is not None else aggregates_document(label)
    path = directory / f"aggregates_{label}.json"
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "SHA256SUMS").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


def p1_rows() -> dict[str, list[dict[str, Any]]]:
    """The synthetic P1 database: both Top-N arms decide on 2022-01-05 and 2022-02-01."""
    rows = scenario_rows("P1")
    rows["book_rebalance"] += [
        {
            "id": 4,
            "book_id": 2,
            "decision_date": "2022-02-01",
            "execution_date": "2022-02-02",
            "quant_portfolio_id": 13,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
        {
            "id": 5,
            "book_id": 3,
            "decision_date": "2022-02-01",
            "execution_date": "2022-02-02",
            "quant_portfolio_id": 14,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
    ]
    return rows


def p2_rows() -> dict[str, list[dict[str, Any]]]:
    """The synthetic P2 database: its Top-N decision date and P2/P2a/P2b summary dates."""
    rows = scenario_rows("P2")
    books = {row["arm_code"]: row["id"] for row in rows["strategy_book"]}
    rows["book_rebalance"] = [
        {
            "id": 1,
            "book_id": books["MARKOWITZ_BASE"],
            "decision_date": "2025-02-18",
            "execution_date": "2025-02-19",
            "quant_portfolio_id": 10,
            "cycle_run_id": None,
            "risk_model_id": 5,
            "status": "executed",
        },
        {
            "id": 2,
            "book_id": books["TOPN_MV_NOGUARD"],
            "decision_date": "2025-02-18",
            "execution_date": "2025-02-19",
            "quant_portfolio_id": 11,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
        {
            "id": 3,
            "book_id": books["TOPN_MV_GUARD_NO_NLP"],
            "decision_date": "2025-02-18",
            "execution_date": "2025-02-19",
            "quant_portfolio_id": 12,
            "cycle_run_id": 7,
            "risk_model_id": 5,
            "status": "executed",
        },
    ]
    rows["backtest_summary"] = [
        _summary(books["MARKOWITZ_BASE"], segment, start, end, sessions)
        for segment, start, end, sessions in (
            ("P2", "2025-02-19", "2025-09-23", 150),
            ("P2a", "2025-02-19", "2025-05-06", 54),
            ("P2b", "2025-05-07", "2025-09-23", 96),
        )
    ]
    return rows


def _summary(
    book_id: int, segment: str, date_from: str, date_to: str, sessions: int
) -> dict[str, Any]:
    return {
        "book_id": book_id,
        "segment": segment,
        "date_from": date_from,
        "date_to": date_to,
        "cumulative_return": 0.1,
        "annualized_return": 0.1,
        "annualized_vol": 0.1,
        "ex_post_sharpe": 1.0,
        "max_drawdown": 0.1,
        "total_turnover": 1.0,
        "total_cost_bps": 10.0,
        "n_rebalances": 10,
        "n_guard_actions": 0,
    }
