"""A synthetic block-F delivery (Work item 46, T-900-T-909).

One window, one manager call, two narrator texts, one news action/date and one bull decision.
The fixture is hermetic: no `/workspaces/thesis` path, no engine database and no store.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

WINDOW = "P1"
DATE = "2022-01-03"
SHA = "a" * 64


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manager_call(*, call_index: int = 0, fallback: bool = False) -> dict[str, Any]:
    return {
        "agent_arm": "A2g",
        "answer_choice": {
            "asset_id": None if fallback else 2,
            "label": "CASH" if fallback else "O01",
            "size_fraction": 0 if fallback else 0.5,
            "is_cash": fallback,
            "is_spy": False,
        },
        "attempts": [{"attempt": 1, "elapsed_s": 1.0, "status": "ok", "turn": 1, "wait_s": 0}],
        "call_index": call_index,
        "chosen": {"asset_id": 2, "is_spy": False, "size_fraction": 0.5},
        "date": DATE,
        "elapsed_s": 1.5,
        "fallback": {
            "cause": "no_menu" if fallback else None,
            "detail": "rule took over" if fallback else "",
            "used_cash": fallback,
            "used_rule": fallback,
        },
        "finish_reasons": ["stop"],
        "first_raw_answer": None,
        "first_validator": None,
        "label_maps": {
            "item_map": {
                "CASH": {"asset_id": None, "is_cash": True, "is_spy": False, "size_fraction": 0},
                "O01": {"asset_id": 2, "is_cash": False, "is_spy": False, "size_fraction": 1},
            }
        },
        "model": {
            "model_id": "deepseek-flash",
            "reasoning_effort": "high",
            "reasoning_effort_used": True,
            "requested": "deepseek-flash",
            "resolved": "DeepSeek-V4.1-Flash",
            "response_model": None,
            "revision": "deepseek-flash",
            "source": "models",
            "thinking": "enabled",
        },
        "prompt_sha256": SHA,
        "prompt_template_sha256": SHA,
        "raw_answer": "SECRET RAW ANSWER",
        "raw_message": "SECRET RAW MESSAGE",
        "repair_cause": None,
        "repair_detail": "",
        "repair_used": False,
        "shuffle_seed": 7,
        "skill_file_sha256": SHA,
        "skill_path": "/skills/manager.md",
        "skill_policy_sha256": SHA,
        "stopped_asset_id": 1,
        "system_prompt": "SECRET SYSTEM PROMPT",
        "tool_order": ["get_menu"],
        "tool_outputs_sha256": SHA,
        "turns": [{}],
        "usage": {
            "cacheReadInputTokens": 1,
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 15,
        },
        "user_prompt": "SECRET USER PROMPT",
        "validator": {"cause": None, "detail": "ok", "passed": True},
    }


def narrator_text(*, source: str = "model", kind: str = "stop") -> dict[str, Any]:
    generated = source == "model"
    return {
        "asset_id": 1,
        "date": DATE,
        "generated_by_language_model": generated,
        "kind": kind,
        "model": {
            "model_id": "deepseek-flash",
            "reasoning_effort": "high",
            "reasoning_effort_used": False,
            "requested": "deepseek-flash",
            "resolved": "DeepSeek-V4.1-Flash",
            "response_model": None,
            "revision": "deepseek-flash",
            "source": "models",
            "thinking": "disabled",
        },
        "omitted_fields": [],
        "prompt_sha256": SHA,
        "source": source,
        "source_asset_id": 1,
        "source_date": DATE,
        "source_kind": kind,
        "source_line": 1,
        "template_sha256": SHA,
        "text": f"{source} text",
        "validator": {"detail": "OK", "passed": True},
    }


def _evidence() -> dict[str, Any]:
    return {
        "a": 0,
        "asset_id": 1,
        "b": 2,
        "covered": True,
        "mean_probability_margin": -0.5,
        "n": 2,
        "negative_by_tier": {"1": 1, "2": 0},
        "neutral_by_tier": {"1": 0, "2": 0},
        "positive_by_tier": {"1": 1, "2": 0},
        "state": "VALID",
        "ticker": "AAA",
        "test": {
            "base_rates": {
                "pooled_negative": "1/2",
                "pooled_positive": "1/2",
                "signal_possible": True,
                "tiers": {},
                "total_rows": 2,
            },
            "conflict": False,
            "critical_negative": 4,
            "critical_positive": None,
            "p_negative": "1/2",
            "p_positive": "1/3",
            "promotion_candidate": False,
            "size_negative": "1/4",
            "size_positive": "0/1",
            "statistic_negative": 1,
            "statistic_positive": 2,
            "veto_candidate": True,
        },
        "test_rows": [[10, "AAA"]],
    }


def news_payload() -> dict[str, Any]:
    action = {
        "action": "veto",
        "asset_id": 1,
        "decision_date": DATE,
        "evidence": _evidence(),
        "replaced_by": 2,
        "replaces": None,
        "test_rows": [[10, "AAA"]],
        "ticker": "AAA",
    }
    fill = {"asset_id": 2, "decision_date": DATE, "replaces": 1, "ticker": "BBB"}
    return {
        "actions": [action],
        "canonical_tickers": {"AAA": 1, "BBB": 2},
        "dates": [
            {
                "actions": [action],
                "admitted": 10,
                "admitted_in_base_window": 2,
                "admitted_in_evidence_window": 2,
                "base_rates": {
                    "pooled_negative": "1/2",
                    "pooled_positive": "1/2",
                    "signal_possible": True,
                    "tiers": {},
                    "total_rows": 2,
                },
                "base_window": [DATE],
                "bench_states": {},
                "complete_pool": True,
                "coverage": {"first_session": DATE, "last_session": DATE},
                "decision_date": DATE,
                "dropped_conditions": [],
                "expected": {
                    "lower_bound": True,
                    "negative": "1/6",
                    "positive": "1/6",
                    "tests": 1,
                    "total": "1/3",
                },
                "fills": [fill],
                "has_temporal_coverage": True,
                "missing_body_hash": 0,
                "pool": [1, 2],
                "pool_states": {},
                "rejected_by_cause": {"duplicate": 0},
                "sentiment_checked": 10,
                "sentiment_checked_known": 10,
                "surplus_promotions": [],
                "undated": 0,
                "untickered": 0,
                "window": [DATE],
            }
        ],
        "fills": [fill],
        "levels_v2": {
            "b_news_exits": 1,
            "decisions": [
                {
                    "b_threshold": 3,
                    "c_flagged": [],
                    "c_flags": {},
                    "c_thresholds": {},
                    "d_fired": True,
                    "d_p20": 0.4,
                    "d_tone21": 0.4,
                    "date": DATE,
                    "filter_inputs": {"news": False, "price": False},
                }
            ],
            "sessions": [{"b_signals": 1, "c_blocked_assets": 0, "date": DATE}],
            "spec": "v2",
        },
        "news_alpha": 0.1,
        "news_mode": "v2",
        "news_table_sha256": SHA,
        "run_id": 1,
        "window": WINDOW,
    }


def bull_payload() -> dict[str, Any]:
    return {
        "bull_beta_target": 0.9,
        "bull_mode": "n11",
        "bull_z_star": -1,
        "decisions": [
            {
                "date": DATE,
                "evaluable": True,
                "n": 2,
                "n11": {
                    "beta_sat": 0.6,
                    "core_weight": 0.5,
                    "evaluable": True,
                    "ex_ante_beta": 0.8,
                },
                "n5a": None,
                "rung": 1,
                "t1": "invested",
                "triggered": True,
                "z": -1.2,
            }
        ],
        "formation_date": DATE,
        "guard_reoptimizations": [],
        "window": WINDOW,
    }


NEWS_COLUMNS = [
    "model_revision",
    "item_kind",
    "item_id",
    "ticker",
    "asset_id",
    "date",
    "date_source",
    "title",
    "text",
    "text_source",
    "sentiment",
    "sentiment_score",
    "p_positive",
    "p_negative",
    "p_neutral",
    "sentiment_revision",
    "category",
    "category_score",
    "group_label",
    "category_revision",
    "article_id",
    "body_hash",
    "source_domain",
    "url",
]


def news_row() -> dict[str, Any]:
    return {
        "model_revision": "rev1",
        "item_kind": "body",
        "item_id": "10",
        "ticker": "AAA",
        "asset_id": 1,
        "date": DATE,
        "date_source": "published",
        "title": "A title",
        "text": "A fragment.",
        "text_source": "original",
        "sentiment": "neutral",
        "sentiment_score": 0.5,
        "p_positive": 0.4,
        "p_negative": 0.3,
        "p_neutral": 0.3,
        "sentiment_revision": "s1",
        "category": "general",
        "category_score": 0.5,
        "group_label": "g",
        "category_revision": "c1",
        "article_id": 1,
        "body_hash": "b" * 64,
        "source_domain": "example.com",
        "url": None,
    }


def write_delivery(tmp_path: Path, *, overrides: dict[str, Any] | None = None) -> Path:
    """Write one complete P1 delivery and return its root."""
    root = tmp_path / "delivery"
    folder = root / "SYSTEM_WITH_HIERARCHY" / WINDOW
    folder.mkdir(parents=True)
    news_dir = root / "news"
    news_dir.mkdir()
    news_rows_path = news_dir / "news_rows.jsonl"
    news_rows_path.write_text(
        json.dumps(news_row(), separators=(",", ":")) + "\n", encoding="utf-8"
    )
    manager = [manager_call()]
    narrator = [narrator_text(), narrator_text(source="template", kind="blocked")]
    news = news_payload()
    bull = bull_payload()
    detail = [
        {"kind": "stop", "date": DATE, "asset_id": 1},
        {"kind": "decision", "date": DATE, "eligible_counts": {"news_sector": 4}},
    ]
    files = {
        "manager_calls": ("H1B-A2g-P1.manager_calls.jsonl", manager, "jsonl"),
        "narrator": ("H1B-A2g-P1.narrator.jsonl", narrator, "jsonl"),
        "news_actions": ("H1B-A2g-P1.news.json", news, "json"),
        "bull_mode": ("H1B-A2g-P1.bull_mode.json", bull, "json"),
        "jsonl": ("H1B-A2g-P1.cartera_v1_3.kg.jsonl", detail, "jsonl"),
    }
    hashes: dict[str, str] = {}
    relative: dict[str, str] = {}
    for key, (name, payload, kind) in files.items():
        path = folder / name
        if kind == "jsonl":
            content = "\n".join(json.dumps(item, separators=(",", ":")) for item in payload) + "\n"
        else:
            content = json.dumps(payload, separators=(",", ":")) + "\n"
        path.write_text(content, encoding="utf-8")
        relative[key] = f"SYSTEM_WITH_HIERARCHY/{WINDOW}/{name}"
        hashes[key] = _sha(content.encode())
    if overrides:
        for key, value in overrides.items():
            relative[key] = value
    controls = {
        "SYSTEM_WITH_HIERARCHY": {
            WINDOW: {
                "manager_calls": 1,
                "manager_fallbacks": 0,
                "manager_repairs": 0,
                "narrator_texts": 2,
                "news_pool_actions": {"veto": 1, "promotion": 0},
                "news_date_records": 1,
                "news_level_c_decisions": 0,
                "news_level_d_decisions": 1,
                "news_exits": 1,
                "news_sector_rejections": 4,
                "bull_triggered": 1,
            }
        }
    }
    manifest = {
        "manifest_version": "1",
        "status": "FINAL",
        "label": "final",
        "key": ["label", "configuration", "window"],
        "key_note": "test",
        "windows": [WINDOW],
        "price_mask": {},
        "prereg": {},
        "configurations": [
            {
                "configuration": "SYSTEM_WITH_HIERARCHY",
                "name_en": "System",
                "name_es": "Sistema",
                "source_kind": "engine_db",
                "selected_variant": None,
                "runs": [
                    {
                        "window": WINDOW,
                        "db_file": f"SYSTEM_WITH_HIERARCHY/{WINDOW}/H1B-A2g-P1.db",
                        "db_sha256": SHA,
                        "run_id": 1,
                        "book_code": "TOPN_MV_GUARD",
                        "book_id": 1,
                        "jsonl_file": relative["jsonl"],
                        "manager_calls_file": relative["manager_calls"],
                        "narrator_file": relative["narrator"],
                        "news_actions_file": relative["news_actions"],
                        "bull_mode_file": relative["bull_mode"],
                        "files_sha256": hashes,
                    }
                ],
            }
        ],
        "news_rows_file": {
            "file": "news/news_rows.jsonl",
            "sha256": _sha(news_rows_path.read_bytes()),
            "rows": 1,
            "model_revision": "rev1",
            "columns": NEWS_COLUMNS,
        },
        "control_counts": controls,
    }
    (root / "manifest_final.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    relative["news_rows"] = "news/news_rows.jsonl"
    sums = [f"{digest}  {name}" for name, digest in sorted(relative_digest(root, relative).items())]
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return root


def relative_digest(root: Path, relative: dict[str, str]) -> dict[str, str]:
    return {
        path: _sha((root / path).read_bytes())
        for path in relative.values()
        if (root / path).is_file()
    }


def refresh_hashes(root: Path) -> None:
    """Recompute the run's file hashes and SHA256SUMS after a test edits a source file."""
    manifest_path = root / "manifest_final.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run = manifest["configurations"][0]["runs"][0]
    relative: dict[str, str] = {}
    for key in ("manager_calls", "narrator", "news_actions", "bull_mode", "jsonl"):
        path = run[f"{key}_file"]
        relative[key] = path
        run["files_sha256"][key] = _sha((root / path).read_bytes())
    news_file = manifest.get("news_rows_file")
    if isinstance(news_file, dict) and (root / news_file["file"]).is_file():
        relative["news_rows"] = news_file["file"]
        news_file["sha256"] = _sha((root / news_file["file"]).read_bytes())
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"{digest}  {name}" for name, digest in sorted(relative_digest(root, relative).items())
    ]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
