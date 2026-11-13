"""A tiny fundamentals delivery cut from the v2 block C export (Work item 45).

The fixture carries the seven cases the loader tests need:

* a masked asset with filings (``ABMD``, asset 6);
* a masked asset without filings (``FRC``, asset 229);
* an unmasked asset with all five valuation metrics (``A``, asset 1);
* a null metric (``ABMD``'s ``interest_coverage``);
* a rule-text assessment (``APA``, snapshot 36);
* a two-timestamp filing (``ABBV`` filing 62, whose ``value_inputs`` row is one second later);
* a ``value_inputs`` row of a masked asset (``ABMD``), which the loader discards silently.

The rows are copied from the real delivery. The fixture is self-contained: the CSVs, the mask,
the universe database and the manifest are written into ``tmp_path`` and never read the delivery
folder. The expected batch is 148 asserted triples.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

FILINGS = [
    {
        "filing_id": 76,
        "asset_id": 6,
        "ticker": "ABMD",
        "cik": "0000815094",
        "form": "10-Q",
        "fiscal_year": 2021,
        "fiscal_period": "2021Q3",
        "period_end": "2021-12-31",
        "filing_date": "2022-02-03",
        "available_at": "2022-02-04",
        "accession_number": "0001564590-22-003810",
    },
    {
        "filing_id": 1,
        "asset_id": 1,
        "ticker": "A",
        "cik": "0001090872",
        "form": "10-Q",
        "fiscal_year": 2022,
        "fiscal_period": "2022Q1",
        "period_end": "2022-01-31",
        "filing_date": "2022-03-03",
        "available_at": "2022-03-04",
        "accession_number": "0001090872-22-000007",
    },
    {
        "filing_id": 62,
        "asset_id": 5,
        "ticker": "ABBV",
        "cik": "0001551152",
        "form": "10-Q",
        "fiscal_year": 2023,
        "fiscal_period": "2023Q1",
        "period_end": "2023-03-31",
        "filing_date": "2023-05-05",
        "available_at": "2023-05-08",
        "accession_number": "0001551152-23-000023",
    },
    {
        "filing_id": 10888,
        "asset_id": 42,
        "ticker": "APA",
        "cik": "0001841666",
        "form": "10-Q",
        "fiscal_year": 2021,
        "fiscal_period": "2021Q3",
        "period_end": "2021-09-30",
        "filing_date": "2021-11-05",
        "available_at": "2021-11-08",
        "accession_number": "0001673379-21-000029",
    },
]

METRICS = [
    # The masked ABMD filing: a null metric, a value and a value_inputs row.
    (
        2629,
        76,
        "leverage",
        "interest_coverage",
        "",
        "x",
        "metrics-v10",
        "2026-10-23T03:50:06+00:00",
        "2022-02-04",
    ),
    (
        2623,
        76,
        "profitability",
        "return_on_equity",
        "0.10005151634797976",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:50:06+00:00",
        "2022-02-04",
    ),
    (
        2652,
        76,
        "rule_input",
        "value_inputs",
        "133036000.0",
        "usd",
        "metrics-v10",
        "2026-10-23T03:50:06+00:00",
        "2022-02-04",
    ),
    # The unmasked A filing: all five valuation metrics, ROE and a value_inputs row.
    (
        29,
        1,
        "valuation",
        "market_capitalization",
        "42074753249.9599",
        "usd",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        30,
        1,
        "valuation",
        "enterprise_value",
        "43646753249.9599",
        "usd",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        31,
        1,
        "valuation",
        "free_cash_flow_yield",
        "0.030422044126930677",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        32,
        1,
        "valuation",
        "sbc_adjusted_fcf_yield",
        "0.027712580821875915",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        33,
        1,
        "valuation",
        "enterprise_fcf_yield",
        "0.02877762734851656",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        5,
        1,
        "profitability",
        "return_on_equity",
        "0.22360363703841157",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    (
        34,
        1,
        "rule_input",
        "value_inputs",
        "1205000000.0",
        "usd",
        "metrics-v10",
        "2026-10-23T03:46:24+00:00",
        "2022-03-04",
    ),
    # The two-timestamp ABBV filing: the value_inputs row is one second later.
    (
        2133,
        62,
        "profitability",
        "net_margin",
        "1.9550102249488752e-02",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:49:26+00:00",
        "2023-05-08",
    ),
    (
        2135,
        62,
        "profitability",
        "return_on_equity",
        "0.4396082067926278",
        "ratio",
        "metrics-v10",
        "2026-10-23T03:49:26+00:00",
        "2023-05-08",
    ),
    (
        2164,
        62,
        "rule_input",
        "value_inputs",
        "7585000000.0",
        "usd",
        "metrics-v10",
        "2026-10-23T03:49:27+00:00",
        "2023-05-08",
    ),
    # The APA rule-text filing.
    (
        381386,
        10888,
        "growth",
        "revenue_growth",
        "0.8383928571428572",
        "ratio",
        "metrics-v10",
        "2026-10-29T14:44:26+00:00",
        "2021-11-08",
    ),
    (
        381396,
        10888,
        "profitability",
        "net_margin",
        "-0.054881010199125786",
        "ratio",
        "metrics-v10",
        "2026-10-29T14:44:26+00:00",
        "2021-11-08",
    ),
    (
        381404,
        10888,
        "rule_input",
        "value_inputs",
        "",
        "usd",
        "metrics-v10",
        "2026-10-29T14:44:26+00:00",
        "2021-11-08",
    ),
]

ASSESSMENTS_JSONL: list[str] = [
    r"""{"snapshot_id": 36, "asset_id": 42, "ticker": "APA", "filing_id": 10888, "score_raw_0_100": null, "rating": null, "narrative": "No fundamental score: an applicable pillar has no value (D1's coverage rule, MET-00 -- an empty metric is never a neutral reading): cash_flow (prior_year_missing). The member is unscored (T-119).", "strengths": [], "risks": [], "model": "unscored-pillar-coverage-v1", "prompt_hash": "c1de2b6ef3e390843d128c086bd26de3a9c0f4a4336981f2b274e3778056d54f", "computed_at": "2026-11-03T16:09:13+00:00", "event_time": "2021-09-30", "available_at": "2021-11-08", "generated_by_language_model": false, "provenance_note": "rule-based text: no fundamental score (coverage rule); not generated by a model"}""",
    r"""{"snapshot_id": 535, "asset_id": 6, "ticker": "ABMD", "filing_id": 76, "score_raw_0_100": 73.2, "rating": "bullish", "narrative": "Profitability is strong on the income statement, with an 81.8% gross margin converting to a 24.7% operating margin and 17.5% net margin, and ROIC of 14.7% (13.1% at the filing's own effective tax rate) confirms real capital returns. Financial strength is the standout: debt-to-equity and debt-to-assets are both 0.0, net debt/EBITDA of -4.03 reflects net cash, and a 6.98 current ratio with a 5.28 cash ratio means coverage rests almost entirely on cash and short-term investments. Cash flow quality is excellent, with a 29.2% operating cash flow margin, only 4.7% capex intensity, a 24.5% free cash flow margin and 1.85x conversion of net income. Growth is the weak pillar: revenue rose 12.7% but operating income fell 9.5% and net income fell 26.1%, so the top line is expanding while margins compress, and the 17.6% FCF growth is a single-quarter figure that should not be annualized.", "strengths": ["Zero debt with a substantial net cash position", "24.5% free cash flow margin on light 4.7% capex", "81.8% gross margin and 14.7% ROIC", "Liquidity of 6.98x current and 5.28x cash coverage"], "risks": ["Operating income down 9.5% and net income down 26.1% despite 12.7% revenue growth", "Margin compression could persist if cost growth outpaces the top line", "Interest coverage unavailable because interest expense is not reported", "Valuation yields withheld, so no price-based read is possible"], "model": "DeepSeek-V4.1-Flash [thinking=disabled]", "prompt_hash": "c1de2b6ef3e390843d128c086bd26de3a9c0f4a4336981f2b274e3778056d54f", "computed_at": "2026-11-03T16:34:45+00:00", "event_time": "2021-12-31", "available_at": "2022-02-04", "generated_by_language_model": true, "provenance_note": "generated by a language model from computed ratios; not a verified fact"}""",
    r"""{"snapshot_id": 961, "asset_id": 1, "ticker": "A", "filing_id": 1, "score_raw_0_100": 69.0, "rating": "bullish", "narrative": "Profitability is a clear strength, with a 54.4% gross margin, 22.5% operating margin and 22.4% ROE, though the margin figures are single-quarter flows rather than annual rates. The balance sheet is conservatively run: debt-to-equity of 0.53, debt-to-assets of 0.26, interest coverage near 18x and net debt/EBITDA of 0.91x, backed by a 2.19 current ratio. Cash generation is the best pillar, with a 23.3% operating cash flow margin, 19.9% free cash flow margin on only 3.4% capex intensity, and FCF conversion of 1.06x net income. Growth is the weak spot: revenue rose 8.1% and operating income 14.6%, but net income fell 1.7% and free cash flow fell 8.6%, suggesting pressure below the operating line. Returns on capital of 16.8% ROIC support the overall picture, while the REIT-flagged FCF yields of 3.04% are only a partial valuation read.", "strengths": ["Strong cash conversion at 1.06x net income", "High gross and operating margins (54.4% / 22.5%)", "Conservative leverage with ~18x interest coverage", "Comfortable liquidity at 2.19 current ratio"], "risks": ["Net income and free cash flow declining despite revenue growth", "Single-quarter margin figures not representative of full-year rates", "Valuation read limited by REIT treatment of FCF yields", "ROIC unadjusted for R&D and operating leases"], "model": "DeepSeek-V4.1-Flash [thinking=disabled]", "prompt_hash": "c1de2b6ef3e390843d128c086bd26de3a9c0f4a4336981f2b274e3778056d54f", "computed_at": "2026-11-03T16:57:01+00:00", "event_time": "2022-01-31", "available_at": "2022-03-04", "generated_by_language_model": true, "provenance_note": "generated by a language model from computed ratios; not a verified fact"}""",
    r"""{"snapshot_id": 7442, "asset_id": 5, "ticker": "ABBV", "filing_id": 62, "score_raw_0_100": 51.0, "rating": "neutral", "narrative": "Profitability is split: gross margin of 67.4% and operating margin of 22.6% are strong, but a 1.96% net margin means non-operating items absorb most of the operating result, and ROE of 44.0% versus ROA of 9.2% shows leverage rather than asset returns driving equity. Financial strength is the weak pillar, with debt/equity at 4.68x, debt/assets at 0.46x, a current ratio of 0.96 and cash covering only 24% of current liabilities, though interest coverage of 5.0x and net debt/EBITDA of 2.24x keep debt serviceable. Cash flow is the standout: a 42.7% operating cash flow margin with 1.25% capex intensity yields a 41.5% free cash flow margin, and ROIC of 17.9% confirms capital is deployed productively. Growth is the alarm, with revenue down 9.7%, operating income down 41.3% and net income down 94.7% in the quarter, and the 8.34% FCF yield is attractive but must be read with the REIT caveat that depreciation distorts earnings-based measures.", "strengths": ["67.4% gross margin and 22.6% operating margin", "41.5% free cash flow margin on only 1.25% capex intensity", "ROIC of 17.9% well above cost of capital", "Interest coverage of 5.0x with net debt/EBITDA of 2.24x"], "risks": ["Net income down 94.7% and operating income down 41.3% in the quarter", "Current ratio of 0.96 with cash covering only 24% of current liabilities", "Debt/equity of 4.68x, understated by excluded operating leases", "1.96% net margin far below the 22.6% operating margin"], "model": "DeepSeek-V4.1-Flash [thinking=disabled]", "prompt_hash": "c1de2b6ef3e390843d128c086bd26de3a9c0f4a4336981f2b274e3778056d54f", "computed_at": "2026-11-03T21:48:30+00:00", "event_time": "2023-03-31", "available_at": "2023-05-08", "generated_by_language_model": true, "provenance_note": "generated by a language model from computed ratios; not a verified fact"}""",
]

MASK_ROWS = [
    (6, "ABMD", 1002, "2019-01-02", "2022-12-21"),
    (229, "FRC", 1089, "2019-01-02", "2023-04-28"),
]

UNIVERSE_ROWS = [
    ("A", "Agilent Technologies Inc.", "0001090872", "2000-06-05", None),
    ("ABBV", "AbbVie Inc.", "0001551152", "2013-01-02", None),
    ("ABMD", "ABIOMED Inc.", "0000815094", "2018-05-31", "2022-12-21"),
    ("APA", "APA Corporation", "0001841666", "1997-07-28", None),
    ("FRC", "First Republic Bank", "0001132979", "2019-01-02", "2023-05-03"),
]

#: The source's own provenance, copied from the delivery; the parser verifies it.
SOURCE = {
    "source_db": "scored_llm.db",
    "source_db_sha256": "2187c36bae42296b84d63031e9058df5aba997a77da2a4aa6665279452e184ca",
}


@dataclass(frozen=True)
class Fixture:
    """The fixture paths and the exact counts the tests assert."""

    directory: Path
    mask: Path
    universe_db: Path
    manifest_sha256: str
    mask_sha256: str
    triples: int = 147


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_manifest(directory: Path) -> str:
    names = [
        "README.md",
        "filings.csv",
        "metrics.csv",
        "assessments.jsonl",
        "source.json",
        "provenance/export_bloque_c.py",
    ]
    lines = []
    for name in names:
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    manifest = directory / "SHA256SUMS"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def write_fixture(tmp_path: Path) -> Fixture:
    """Write the delivery, the mask and the universe database; return their paths and hashes."""
    directory = tmp_path / "bloque_c_fundamentales"
    directory.mkdir()
    (directory / "provenance").mkdir()
    (directory / "README.md").write_text("# Block C fixture\n", encoding="utf-8")
    (directory / "provenance" / "export_bloque_c.py").write_text(
        "# fixture stand-in for the export script\n", encoding="utf-8"
    )
    (directory / "source.json").write_text(json.dumps(SOURCE, indent=1) + "\n", encoding="utf-8")
    _write_csv(
        directory / "filings.csv",
        [
            "filing_id",
            "asset_id",
            "ticker",
            "cik",
            "form",
            "fiscal_year",
            "fiscal_period",
            "period_end",
            "filing_date",
            "available_at",
            "accession_number",
        ],
        [
            [
                row["filing_id"],
                row["asset_id"],
                row["ticker"],
                row["cik"],
                row["form"],
                row["fiscal_year"],
                row["fiscal_period"],
                row["period_end"],
                row["filing_date"],
                row["available_at"],
                row["accession_number"],
            ]
            for row in FILINGS
        ],
    )
    _write_csv(
        directory / "metrics.csv",
        [
            "metric_id",
            "filing_id",
            "metric_group",
            "metric_name",
            "value",
            "unit",
            "engine_version",
            "computed_at",
            "available_at",
        ],
        [list(row) for row in METRICS],
    )
    (directory / "assessments.jsonl").write_text(
        "\n".join(ASSESSMENTS_JSONL) + "\n", encoding="utf-8"
    )
    manifest_sha = write_manifest(directory)

    mask = tmp_path / "tiingo_assets.csv"
    _write_csv(
        mask,
        ["asset_id", "ticker", "tiingo_price_rows", "first_date", "last_date"],
        [list(row) for row in MASK_ROWS],
    )

    universe = tmp_path / "universe.db"
    connection = sqlite3.connect(universe)
    try:
        connection.execute(
            "CREATE TABLE universe_membership (symbol TEXT, security TEXT, gics_sector TEXT, "
            "gics_sub_industry TEXT, cik TEXT, valid_from TEXT, valid_to TEXT)"
        )
        connection.executemany(
            "INSERT INTO universe_membership VALUES (?, ?, NULL, NULL, ?, ?, ?)",
            [
                (symbol, security, cik, start, end)
                for symbol, security, cik, start, end in UNIVERSE_ROWS
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return Fixture(
        directory=directory,
        mask=mask,
        universe_db=universe,
        manifest_sha256=manifest_sha,
        mask_sha256=hashlib.sha256(mask.read_bytes()).hexdigest(),
    )
