"""Synthetic Contract v18 backtest databases for the m018 projector tests (T-207).

The DDL and the eight ``CREATE VIEW`` statements are copied verbatim from handoff §3.2. The
default scenario covers every nullable case of §3.3, and two calls with different ``window``
values produce the same run/book ids so the tests can prove the window-qualified IRIs and graph
names do not collide.

Built in memory/tmp_path under ``tests/fixtures/`` as constitution Project structure #10 places
shared fixtures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from projection.backtest import AssetInfo, GuardCatalog, load_guard_catalog

SCHEMA = Path(__file__).resolve().parent.parent.parent / "schema"

#: The universe the projector must see. ``ZZZ`` is deliberately absent: the backtest database
#: knows it, the universe database does not.
ASSETS: dict[str, AssetInfo] = {
    "AAA": AssetInfo("AAA", "0000000001", (("2000-01-01", None),)),
    "BBB": AssetInfo("BBB", "0000000002", (("2000-01-01", None),)),
    "BRK.B": AssetInfo("BRK.B", "0000000003", (("2000-01-01", None),)),
}

_DDL = """
CREATE TABLE schema_version (version INTEGER, applied_at TEXT, description TEXT);
INSERT INTO schema_version VALUES (18, 'x', 'x');

CREATE TABLE v_cycle_run (run_id INTEGER PRIMARY KEY, cycle_type TEXT);

CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    company_name TEXT
);

CREATE TABLE backtest_run (
    id              INTEGER PRIMARY KEY,
    window_id       TEXT NOT NULL,
    d_start         TEXT NOT NULL,
    d_end           TEXT NOT NULL,
    formation_date  TEXT,
    warmup_steps    INTEGER NOT NULL DEFAULT 0,
    params_json     TEXT NOT NULL,
    ips_json        TEXT NOT NULL,
    code_version    TEXT,
    input_db_sha256 TEXT,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE strategy_book (
    id                INTEGER PRIMARY KEY,
    backtest_run_id   INTEGER NOT NULL REFERENCES backtest_run(id) ON DELETE CASCADE,
    arm_code          TEXT NOT NULL,
    objective         TEXT NOT NULL,
    exclude_hard_vetoed INTEGER NOT NULL,
    guard_layers      TEXT,
    UNIQUE (backtest_run_id, arm_code)
);

CREATE TABLE book_rebalance (
    id                  INTEGER PRIMARY KEY,
    book_id             INTEGER NOT NULL REFERENCES strategy_book(id) ON DELETE CASCADE,
    decision_date       TEXT NOT NULL,
    execution_date      TEXT NOT NULL,
    quant_portfolio_id  INTEGER REFERENCES quant_portfolio(id),
    cycle_run_id        INTEGER REFERENCES cycle_run(id),
    risk_model_id       INTEGER REFERENCES quant_risk_model(id),
    status              TEXT NOT NULL
);

CREATE TABLE book_weight_daily (
    book_id                 INTEGER NOT NULL REFERENCES strategy_book(id) ON DELETE CASCADE,
    date                    TEXT NOT NULL,
    holding_key             TEXT NOT NULL,
    asset_id                INTEGER REFERENCES assets(id),
    markowitz_target_weight REAL,
    drifted_weight          REAL,
    pre_guard_weight        REAL,
    final_target_weight     REAL,
    PRIMARY KEY (book_id, date, holding_key)
);

CREATE TABLE guard_alert (
    id               INTEGER PRIMARY KEY,
    backtest_run_id  INTEGER NOT NULL REFERENCES backtest_run(id) ON DELETE CASCADE,
    date             TEXT NOT NULL,
    layer            INTEGER NOT NULL,
    asset_id         INTEGER REFERENCES assets(id),
    rule_id          TEXT NOT NULL,
    value            REAL,
    threshold        REAL,
    state            TEXT NOT NULL
);

CREATE TABLE guard_action (
    id            INTEGER PRIMARY KEY,
    book_id       INTEGER NOT NULL REFERENCES strategy_book(id) ON DELETE CASCADE,
    alert_id      INTEGER NOT NULL REFERENCES guard_alert(id) ON DELETE CASCADE,
    decision_date TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    asset_id      INTEGER REFERENCES assets(id),
    status        TEXT NOT NULL,
    weight_before REAL,
    weight_after  REAL
);

CREATE TABLE book_daily_performance (
    book_id          INTEGER NOT NULL REFERENCES strategy_book(id) ON DELETE CASCADE,
    date             TEXT NOT NULL,
    gross_return     REAL NOT NULL,
    turnover         REAL NOT NULL,
    cost_return      REAL NOT NULL,
    net_return       REAL NOT NULL,
    nav              REAL NOT NULL,
    drawdown         REAL NOT NULL,
    cash_weight      REAL NOT NULL,
    n_equity         INTEGER NOT NULL,
    benchmark_return REAL,
    PRIMARY KEY (book_id, date)
);

CREATE TABLE backtest_summary (
    book_id            INTEGER NOT NULL REFERENCES strategy_book(id) ON DELETE CASCADE,
    segment            TEXT NOT NULL,
    date_from          TEXT NOT NULL,
    date_to            TEXT NOT NULL,
    cumulative_return  REAL NOT NULL,
    annualized_return  REAL NOT NULL,
    annualized_vol     REAL NOT NULL,
    ex_post_sharpe     REAL NOT NULL,
    max_drawdown       REAL NOT NULL,
    total_turnover     REAL NOT NULL,
    total_cost_bps     REAL NOT NULL,
    n_rebalances       INTEGER NOT NULL,
    n_guard_actions    INTEGER NOT NULL,
    PRIMARY KEY (book_id, segment)
);

CREATE TABLE backtest_test (
    backtest_run_id INTEGER NOT NULL REFERENCES backtest_run(id) ON DELETE CASCADE,
    segment         TEXT NOT NULL,
    arm_a           TEXT NOT NULL,
    arm_b           TEXT NOT NULL,
    test            TEXT NOT NULL,
    statistic       REAL NOT NULL,
    p_value         REAL NOT NULL,
    n_obs           INTEGER NOT NULL,
    params_json     TEXT,
    PRIMARY KEY (backtest_run_id, segment, arm_a, arm_b, test)
);
"""

_VIEWS = """
CREATE VIEW v_book AS
SELECT b.id AS book_id, b.backtest_run_id, r.window_id, r.d_start, r.d_end,
       r.formation_date, r.status AS run_status, b.arm_code, b.objective,
       b.exclude_hard_vetoed, b.guard_layers, r.code_version,
       substr(r.created_at, 1, 10) AS knowledge_date
FROM strategy_book b
JOIN backtest_run r ON r.id = b.backtest_run_id;

CREATE VIEW v_book_rebalance AS
SELECT br.id AS rebalance_id, br.book_id, b.backtest_run_id, b.arm_code,
       br.decision_date, br.execution_date, br.quant_portfolio_id, br.cycle_run_id,
       br.risk_model_id, br.status,
       br.execution_date AS knowledge_date
FROM book_rebalance br
JOIN strategy_book b ON b.id = br.book_id;

CREATE VIEW v_guard_alert AS
SELECT ga.id AS alert_id, ga.backtest_run_id, r.window_id, ga.date, ga.layer,
       a.ticker, ga.asset_id, ga.rule_id,
       CASE WHEN ga.layer = 1 THEN NULL ELSE ga.value END AS value,
       ga.threshold, ga.state,
       ga.date AS knowledge_date
FROM guard_alert ga
JOIN backtest_run r ON r.id = ga.backtest_run_id
LEFT JOIN assets a ON a.id = ga.asset_id;

CREATE VIEW v_guard_action AS
SELECT act.id AS action_id, act.book_id, b.backtest_run_id, b.arm_code,
       act.alert_id, act.decision_date, act.effective_date,
       a.ticker, act.asset_id, act.status,
       CASE WHEN act.asset_id IS NOT NULL THEN NULL ELSE act.weight_before END
           AS weight_before,
       CASE WHEN act.asset_id IS NOT NULL THEN NULL ELSE act.weight_after END
           AS weight_after,
       act.effective_date AS knowledge_date
FROM guard_action act
JOIN strategy_book b ON b.id = act.book_id
LEFT JOIN assets a ON a.id = act.asset_id;

CREATE VIEW v_book_weight_daily AS
SELECT w.book_id, b.backtest_run_id, b.arm_code, w.date, w.holding_key, w.asset_id,
       a.company_name AS holding_name,
       CASE WHEN EXISTS (
           SELECT 1 FROM book_rebalance br
           WHERE br.book_id = w.book_id
             AND w.date IN (br.decision_date, br.execution_date)
       ) THEN w.markowitz_target_weight END AS markowitz_target_weight,
       CASE WHEN EXISTS (
           SELECT 1 FROM book_rebalance br
           WHERE br.book_id = w.book_id
             AND w.date IN (br.decision_date, br.execution_date)
       ) THEN w.final_target_weight END AS final_target_weight,
       w.date AS knowledge_date
FROM book_weight_daily w
JOIN strategy_book b ON b.id = w.book_id
LEFT JOIN assets a ON a.id = w.asset_id;

CREATE VIEW v_book_daily_performance AS
SELECT p.book_id, b.backtest_run_id, b.arm_code, r.window_id, p.date,
       p.gross_return, p.turnover, p.cost_return, p.net_return, p.nav, p.drawdown,
       p.cash_weight, p.n_equity, p.benchmark_return,
       p.date AS knowledge_date
FROM book_daily_performance p
JOIN strategy_book b ON b.id = p.book_id
JOIN backtest_run r ON r.id = b.backtest_run_id;

CREATE VIEW v_portfolio_period_summary AS
SELECT s.book_id, b.backtest_run_id, b.arm_code, r.window_id, s.segment,
       s.date_from, s.date_to, s.cumulative_return, s.annualized_return,
       s.annualized_vol, s.ex_post_sharpe, s.max_drawdown, s.total_turnover,
       s.total_cost_bps, s.n_rebalances, s.n_guard_actions,
       s.date_to AS knowledge_date
FROM backtest_summary s
JOIN strategy_book b ON b.id = s.book_id
JOIN backtest_run r ON r.id = b.backtest_run_id;

CREATE VIEW v_backtest_test AS
SELECT t.backtest_run_id, r.window_id, t.segment, t.arm_a, t.arm_b, t.test,
       t.statistic, t.p_value, t.n_obs, t.params_json,
       substr(r.created_at, 1, 10) AS knowledge_date
FROM backtest_test t
JOIN backtest_run r ON r.id = t.backtest_run_id;
"""


def load_catalog() -> GuardCatalog:
    """The repository's real GUARD catalog, read from ``schema/rules.ttl``."""
    return load_guard_catalog(SCHEMA / "rules.ttl")


def scenario_rows(
    window: str = "P1", run_id: int = 1, status: str = "completed"
) -> dict[str, list[dict[str, Any]]]:
    """One run of three books covering every §3.3 nullable case."""
    knowledge = "2026-10-31"
    books = [
        {
            "id": 1,
            "backtest_run_id": run_id,
            "arm_code": "MARKOWITZ_BASE",
            "objective": "min_var",
            "exclude_hard_vetoed": 0,
            "guard_layers": None,
        },
        {
            "id": 2,
            "backtest_run_id": run_id,
            "arm_code": "TOPN_MV_NOGUARD",
            "objective": "min_var",
            "exclude_hard_vetoed": 0,
            "guard_layers": None,
        },
        {
            "id": 3,
            "backtest_run_id": run_id,
            "arm_code": "TOPN_MV_GUARD_NO_NLP",
            "objective": "min_var",
            "exclude_hard_vetoed": 0,
            "guard_layers": "[1, 3, 4]",
        },
    ]
    return {
        "backtest_run": [
            {
                "id": run_id,
                "window_id": window,
                "d_start": "2022-01-03",
                "d_end": "2022-10-12",
                "formation_date": "2022-01-03",
                "warmup_steps": 0,
                "params_json": "{}",
                "ips_json": "{}",
                "code_version": "v1",
                "input_db_sha256": None,
                "status": status,
                "created_at": f"{knowledge}T19:37:32",
            }
        ],
        "strategy_book": books,
        "book_rebalance": [
            {
                "id": 1,
                "book_id": 1,
                "decision_date": "2022-01-03",
                "execution_date": "2022-01-04",
                "quant_portfolio_id": 10,
                "cycle_run_id": None,  # MARKOWITZ_BASE: the §3.3 nullable case
                "risk_model_id": 5,
                "status": "executed",
            },
            {
                "id": 2,
                "book_id": 2,
                "decision_date": "2022-01-05",
                "execution_date": "2022-01-06",
                "quant_portfolio_id": 11,
                "cycle_run_id": 7,
                "risk_model_id": 5,
                "status": "executed",
            },
            {
                "id": 3,
                "book_id": 3,
                "decision_date": "2022-01-05",
                "execution_date": "2022-01-06",
                "quant_portfolio_id": 12,
                "cycle_run_id": 7,
                "risk_model_id": 5,
                "status": "executed",
            },
        ],
        "guard_alert": [
            {  # layer 1: value masked by the view
                "id": 1,
                "backtest_run_id": run_id,
                "date": "2022-02-08",
                "layer": 1,
                "asset_id": 1,
                "rule_id": "L1_STOP_LOSS",
                "value": 0.5,
                "threshold": -0.1229,
                "state": "ENTER",
            },
            {  # layer 1 re-entry
                "id": 2,
                "backtest_run_id": run_id,
                "date": "2022-02-09",
                "layer": 1,
                "asset_id": 2,
                "rule_id": "L1_REENTRY",
                "value": 0.6,
                "threshold": 0.0108,
                "state": "EXIT",
            },
            {  # layer 2
                "id": 3,
                "backtest_run_id": run_id,
                "date": "2022-02-10",
                "layer": 2,
                "asset_id": 1,
                "rule_id": "L2_NEWS",
                "value": 0.3,
                "threshold": 0.0,
                "state": "ACTIVE",
            },
            {  # layer 3: no asset/ticker
                "id": 4,
                "backtest_run_id": run_id,
                "date": "2022-02-11",
                "layer": 3,
                "asset_id": None,
                "rule_id": "L3_VOL",
                "value": 0.8,
                "threshold": 0.2455,
                "state": "SCALE",
            },
            {  # layer 4: no asset/ticker
                "id": 5,
                "backtest_run_id": run_id,
                "date": "2022-02-12",
                "layer": 4,
                "asset_id": None,
                "rule_id": "L4_DD",
                "value": 0.7,
                "threshold": 0.6073,
                "state": "SCALE",
            },
        ],
        "guard_action": [
            {  # layer-1 asset action: weights masked
                "id": 1,
                "book_id": 1,
                "alert_id": 1,
                "decision_date": "2022-02-08",
                "effective_date": "2022-02-09",
                "asset_id": 1,
                "status": "APPLIED",
                "weight_before": 0.1,
                "weight_after": 0.0,
            },
            {  # the counterfactual action on the no-guard arm
                "id": 2,
                "book_id": 2,
                "alert_id": 1,
                "decision_date": "2022-02-08",
                "effective_date": "2022-02-09",
                "asset_id": 1,
                "status": "ARM_DISABLED",
                "weight_before": 0.1,
                "weight_after": 0.0,
            },
            {  # layer-3 portfolio action: weights kept
                "id": 3,
                "book_id": 1,
                "alert_id": 4,
                "decision_date": "2022-02-11",
                "effective_date": "2022-02-12",
                "asset_id": None,
                "status": "APPLIED",
                "weight_before": 1.0,
                "weight_after": 0.8,
            },
            {
                "id": 4,
                "book_id": 3,
                "alert_id": 4,
                "decision_date": "2022-02-11",
                "effective_date": "2022-02-12",
                "asset_id": None,
                "status": "APPLIED",
                "weight_before": 1.0,
                "weight_after": 0.8,
            },
            {  # NOT_HELD: no weights
                "id": 5,
                "book_id": 1,
                "alert_id": 5,
                "decision_date": "2022-02-12",
                "effective_date": "2022-02-13",
                "asset_id": None,
                "status": "NOT_HELD",
                "weight_before": None,
                "weight_after": None,
            },
            {
                "id": 6,
                "book_id": 3,
                "alert_id": 5,
                "decision_date": "2022-02-12",
                "effective_date": "2022-02-13",
                "asset_id": None,
                "status": "SUPERSEDED",
                "weight_before": 1.0,
                "weight_after": 1.0,
            },
        ],
        "book_weight_daily": [
            {  # execution date: targets kept
                "book_id": 1,
                "date": "2022-01-04",
                "holding_key": "AAA",
                "asset_id": 1,
                "markowitz_target_weight": 0.5,
                "drifted_weight": 0.5,
                "pre_guard_weight": 0.5,
                "final_target_weight": 0.5,
            },
            {
                "book_id": 1,
                "date": "2022-01-04",
                "holding_key": "CASH",
                "asset_id": None,
                "markowitz_target_weight": 0.5,
                "drifted_weight": 0.5,
                "pre_guard_weight": 0.5,
                "final_target_weight": 0.5,
            },
            {  # ordinary session: targets masked
                "book_id": 1,
                "date": "2022-01-05",
                "holding_key": "AAA",
                "asset_id": 1,
                "markowitz_target_weight": 0.6,
                "drifted_weight": 0.6,
                "pre_guard_weight": 0.6,
                "final_target_weight": 0.6,
            },
            {
                "book_id": 1,
                "date": "2022-01-05",
                "holding_key": "BBB",
                "asset_id": 2,
                "markowitz_target_weight": 0.4,
                "drifted_weight": 0.4,
                "pre_guard_weight": 0.4,
                "final_target_weight": 0.4,
            },
            {  # a ticker the universe database does not know
                "book_id": 2,
                "date": "2022-01-06",
                "holding_key": "ZZZ",
                "asset_id": 4,
                "markowitz_target_weight": 0.0,
                "drifted_weight": 0.0,
                "pre_guard_weight": 0.0,
                "final_target_weight": 0.0,
            },
            {
                "book_id": 2,
                "date": "2022-01-06",
                "holding_key": "CASH",
                "asset_id": None,
                "markowitz_target_weight": 0.7,
                "drifted_weight": 0.7,
                "pre_guard_weight": 0.7,
                "final_target_weight": 0.7,
            },
            {
                "book_id": 3,
                "date": "2022-01-06",
                "holding_key": "BRK.B",
                "asset_id": 3,
                "markowitz_target_weight": 0.4,
                "drifted_weight": 0.4,
                "pre_guard_weight": 0.4,
                "final_target_weight": 0.4,
            },
            {
                "book_id": 3,
                "date": "2022-01-06",
                "holding_key": "CASH",
                "asset_id": None,
                "markowitz_target_weight": 0.6,
                "drifted_weight": 0.6,
                "pre_guard_weight": 0.6,
                "final_target_weight": 0.6,
            },
        ],
        "book_daily_performance": [
            {
                "book_id": 1,
                "date": "2022-01-04",
                "gross_return": 0.01,
                "turnover": 0.0,
                "cost_return": 0.0,
                "net_return": 0.01,
                "nav": 1.01,
                "drawdown": 0.0,
                "cash_weight": 0.5,
                "n_equity": 2,
                "benchmark_return": 0.0,
            },
            {
                "book_id": 1,
                "date": "2022-01-05",
                "gross_return": -0.01,
                "turnover": 0.1,
                "cost_return": 0.001,
                "net_return": -0.011,
                "nav": 0.9989,
                "drawdown": 0.001,
                "cash_weight": 0.4,
                "n_equity": 2,
                "benchmark_return": 0.002,
            },
            {
                "book_id": 2,
                "date": "2022-01-06",
                "gross_return": 0.002,
                "turnover": 0.2,
                "cost_return": 0.002,
                "net_return": 0.0,
                "nav": 1.0,
                "drawdown": 0.0,
                "cash_weight": 0.7,
                "n_equity": 1,
                "benchmark_return": None,
            },
            {
                "book_id": 3,
                "date": "2022-01-06",
                "gross_return": 0.003,
                "turnover": 0.3,
                "cost_return": 0.003,
                "net_return": 0.0,
                "nav": 1.0,
                "drawdown": 0.0,
                "cash_weight": 0.6,
                "n_equity": 1,
                "benchmark_return": 0.001,
            },
        ],
        "backtest_summary": [
            {
                "book_id": 1,
                "segment": "P1",
                "date_from": "2022-01-03",
                "date_to": "2022-10-12",
                "cumulative_return": -0.1,
                "annualized_return": -0.12,
                "annualized_vol": 0.15,
                "ex_post_sharpe": -0.8,
                "max_drawdown": 0.16,
                "total_turnover": 2.0,
                "total_cost_bps": 20.0,
                "n_rebalances": 10,
                "n_guard_actions": 0,
            },
            {
                "book_id": 3,
                "segment": "P1",
                "date_from": "2022-01-03",
                "date_to": "2022-10-12",
                "cumulative_return": -0.2,
                "annualized_return": -0.24,
                "annualized_vol": 0.14,
                "ex_post_sharpe": -1.7,
                "max_drawdown": 0.22,
                "total_turnover": 18.0,
                "total_cost_bps": 180.0,
                "n_rebalances": 10,
                "n_guard_actions": 535,
            },
        ],
        "backtest_test": [
            {
                "backtest_run_id": run_id,
                "segment": "P1",
                "arm_a": "MARKOWITZ_BASE",
                "arm_b": "TOPN_MV_NOGUARD",
                "test": "memmel_jk",
                "statistic": 1.2,
                "p_value": 0.05,
                "n_obs": 100,
                "params_json": '{"block": 5}',
            },
            {
                "backtest_run_id": run_id,
                "segment": "P1",
                "arm_a": "TOPN_MV_GUARD_NO_NLP",
                "arm_b": "TOPN_MV_NOGUARD",
                "test": "ledoit_wolf",
                "statistic": -0.5,
                "p_value": 1.0,
                "n_obs": 1,
                "params_json": None,
            },
            {
                "backtest_run_id": run_id,
                "segment": "P1",
                "arm_a": "TOPN_MV_GUARD_NO_NLP",
                "arm_b": "MARKOWITZ_BASE",
                "test": "hac_mean_diff",
                "statistic": 0.0,
                "p_value": 0.0,
                "n_obs": 50,
                "params_json": None,
            },
        ],
    }


def backtest_db(  # noqa: PLR0913 -- a test builder's keyword-only knobs are clearer explicit
    tmp_path: Path,
    *,
    name: str | None = None,
    window: str = "P1",
    run_id: int = 1,
    status: str = "completed",
    rows: dict[str, list[dict[str, Any]]] | None = None,
    cycle_types: tuple[str, ...] = (),
) -> Path:
    """Write one synthetic backtest database and return its path."""
    path = tmp_path / (name or f"backtest_{window}.db")
    path.unlink(missing_ok=True)
    data = scenario_rows(window, run_id, status) if rows is None else rows
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.executescript(_VIEWS)
    conn.executemany(
        "INSERT INTO assets VALUES (?, ?, ?)",
        [
            (1, "AAA", "AAA Inc."),
            (2, "BBB", "BBB Inc."),
            (3, "BRK.B", "Berkshire Hathaway"),
            (4, "ZZZ", "ZZZ Corp"),
        ],
    )
    for index, cycle_type in enumerate(cycle_types, 1):
        conn.execute("INSERT INTO v_cycle_run VALUES (?, ?)", (index, cycle_type))
    for table, table_rows in data.items():
        if not table_rows:
            continue
        columns = list(table_rows[0])
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES "  # noqa: S608 -- test constants
            f"({', '.join('?' for _ in columns)})",
            [[row[column] for column in columns] for row in table_rows],
        )
    conn.commit()
    conn.close()
    return path


def universe_db(tmp_path: Path, assets: dict[str, AssetInfo] | None = None) -> Path:
    """A small ``universe.db`` carrying the same symbols the scenario's assets use."""
    path = tmp_path / "universe.db"
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
        "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
    )
    for symbol, info in (assets or ASSETS).items():
        valid_from, valid_to = info.stints[0]
        conn.execute(
            "INSERT INTO universe_membership VALUES (?, ?, NULL, NULL, ?, ?, ?)",
            (symbol, f"{symbol} Inc.", info.cik, valid_from, valid_to),
        )
    conn.commit()
    conn.close()
    return path


def rows_without(
    data: dict[str, list[dict[str, Any]]], table: str, index: int = 0
) -> dict[str, list[dict[str, Any]]]:
    """A copy of ``data`` with one row removed (``index``) from ``table``."""
    copy = {name: [dict(row) for row in rows] for name, rows in data.items()}
    del copy[table][index]
    return copy
