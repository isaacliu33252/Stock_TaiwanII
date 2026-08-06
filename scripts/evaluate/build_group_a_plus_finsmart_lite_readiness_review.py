#!/usr/bin/env python3
"""Build a FinSMART-lite readiness review for GroupA+.

This is a research/shadow artifact only. It translates the useful parts of
arXiv:2607.28127 into GroupA+ implementation boundaries without training an LLM
or changing live target weights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_PDF_PATH = Path("/mnt/c/Users/isaac/Downloads/2607.28127.pdf")
DEFAULT_DIAGNOSTIC = PROJECT_ROOT / "research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/finsmart_lite_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/finsmart_lite_readiness/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "sha256": _sha256_file(path)}


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_diagnostic_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if " vs 0050 return" not in line:
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 7:
            continue
        rows.append(
            {
                "series": parts[0],
                "n": int(float(parts[1])) if _parse_float(parts[1]) is not None else None,
                "corr_same_day": _parse_float(parts[2]),
                "corr_next_day": _parse_float(parts[3]),
                "n_gated_same": int(float(parts[4])) if _parse_float(parts[4]) is not None else None,
                "corr_same_day_gated_0_5pct": _parse_float(parts[5]),
                "corr_next_day_gated_0_5pct": _parse_float(parts[6]),
            }
        )
    return rows


def _best_alignment(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [
        row
        for row in rows
        if row.get("corr_next_day") is not None or row.get("corr_next_day_gated_0_5pct") is not None
    ]
    if not scored:
        return None
    return max(
        scored,
        key=lambda row: max(
            abs(float(row.get("corr_next_day") or 0.0)),
            abs(float(row.get("corr_next_day_gated_0_5pct") or 0.0)),
        ),
    )


def build_review(
    *,
    pdf_path: Path = DEFAULT_PDF_PATH,
    diagnostic_path: Path = DEFAULT_DIAGNOSTIC,
    as_of: str = "2026-08-06",
) -> dict[str, Any]:
    diagnostic_rows = _parse_diagnostic_table(diagnostic_path)
    best = _best_alignment(diagnostic_rows)
    blockers: list[str] = []
    warnings: list[str] = []

    if not pdf_path.exists():
        blockers.append("missing_source_pdf")
    if not diagnostic_path.exists():
        warnings.append("missing_reward_alignment_diagnostic")
    if best is None:
        warnings.append("no_existing_sentiment_return_alignment_rows")
    elif abs(float(best.get("corr_next_day") or 0.0)) < 0.05 and abs(
        float(best.get("corr_next_day_gated_0_5pct") or 0.0)
    ) < 0.05:
        warnings.append("weak_next_day_alignment_in_existing_sentiment_features")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finsmart_lite_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_shadow_design",
        "policy": "research_shadow_only_no_training_no_live_action",
        "sources": {
            "paper_pdf": _source(pdf_path),
            "diagnostic": _source(diagnostic_path),
        },
        "paper_takeaways": {
            "title": "FinSMART: Financial Sentiment Analysis for Algorithmic Trading through Market-Aligned Reinforcement Learning",
            "arxiv_id": "2607.28127",
            "usable_components": [
                "entity_or_ticker_gating_before_sentiment_enters_group_a_plus",
                "sentiment_gate_discards_unclear_positive_negative_neutral_outputs",
                "dual_filter_reward_requires_directional_return_and_alpha_threshold",
                "periodic_market_aligned_retraining_or_recalibration",
            ],
            "not_ported_now": [
                "full_grpo_or_lora_training",
                "same_day_return_live_signal",
                "direct_target_weight_changes_from_news_sentiment",
            ],
        },
        "diagnostic_summary": {
            "rows": diagnostic_rows,
            "best_existing_alignment": best,
            "interpretation": (
                "Ticker/entity-specific FinMind 0050 headlines show stronger same-day and next-day alignment "
                "than broad market LTN features; GroupA+ should prioritize strict article-to-asset mapping before "
                "any sentiment reward model is trusted."
            )
            if best
            else "No local diagnostic rows were available.",
        },
        "recommended_shadow_design": {
            "artifact_name": "market_aligned_sentiment_shadow",
            "output_path": "report/group_a_plus/latest/market_aligned_sentiment_shadow.json",
            "input_sources": [
                "report/group_a_plus/latest/watchlist_news.json",
                "report/group_a_plus/latest/watchlist_news_finmind.json",
                "FinRL/data/stock_data.db:ohlcv",
                "FinRL/data/sentiment/finbert_market_sentiment_daily.csv",
                "FinRL/data/sentiment/llm_market_sentiment_daily.csv",
            ],
            "entity_mapping_targets": [
                "0050.TW",
                "00631L.TW",
                "00632R.TW",
                "2330.TW",
                "TWII_proxy",
                "semiconductor_basket",
            ],
            "reward_spec": {
                "horizons_trading_days": [1, 3, 5],
                "alpha_threshold": 0.005,
                "transaction_cost_required": True,
                "labels": {"bullish": 1, "neutral": 0, "bearish": -1},
                "reward": {
                    "correct_direction": 2.0,
                    "correct_neutral": 0.1,
                    "opposite_direction": -1.5,
                    "missed_or_false_signal": -1.0,
                },
            },
            "integration_points": [
                "group_a_plus/integrations/watchlist_news.py",
                "group_a_plus/integrations/signal_alignment.py",
                "group_a_plus/integrations/llm_sentiment_features.py",
                "group_a_plus/integrations/strategy_trust_gate.py",
            ],
            "promotion_requirements": [
                "point_in_time_join_no_lookahead",
                "walk_forward_2024_2026_improves_next_day_alignment",
                "cost_adjusted_shadow_backtest_improves_sharpe_or_drawdown_without_turnover_regression",
                "manual_approval_before_any_training_or_live_weight_change",
            ],
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "finsmart_lite_shadow_design_allowed": not blockers,
            "market_aligned_sentiment_shadow_allowed": not blockers,
            "llm_training_allowed": False,
            "grpo_training_allowed": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
            "keep_latest_strategy_weights_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"finsmart_lite_readiness_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-08-06")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF_PATH))
    parser.add_argument("--diagnostic", default=str(DEFAULT_DIAGNOSTIC))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        pdf_path=Path(args.pdf),
        diagnostic_path=Path(args.diagnostic),
        as_of=args.as_of,
    )
    write_review(review, Path(args.output), None if args.no_history else Path(args.history_dir))
    print(f"FinSMART-lite readiness review: {Path(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "shadow_design_allowed": review["decision"]["finsmart_lite_shadow_design_allowed"],
                "llm_training_allowed": review["decision"]["llm_training_allowed"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
