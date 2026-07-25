#!/usr/bin/env python3
"""Attribute the GIFT 5 bps warning failure to turnover cost vs raw signal.

The report compares each fold at 0 bps and the warning cost level. It explains
whether failed folds are already weak before costs or are pushed below gate
thresholds by turnover drag. It is research-only and never emits target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.audit_group_a_plus_llm_state_reward_frozen_panel_walk_forward import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_WF_AUDIT,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_EXCLUDED_TICKERS,
    _aggregate_folds,
    _fold_backtest,
    _load_panel,
    _sha256_file,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_cost_warning_turnover_attribution.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_cost_warning_turnover_attribution/history"


def _float_list(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _delta(row: dict[str, Any], metric: str) -> float:
    return float((row.get("delta_vs_equal_weight") or {}).get(metric) or 0.0)


def _metric_cost_classification(no_cost: dict[str, Any], with_cost: dict[str, Any]) -> dict[str, str]:
    classifications: dict[str, str] = {}
    checks = {
        "final_value": ("positive_after_cost", "cost_caused_final_failure", "raw_signal_final_failure"),
        "sharpe_ratio": ("positive_after_cost", "cost_caused_sharpe_failure", "raw_signal_sharpe_failure"),
        "max_drawdown": ("non_worse_after_cost", "cost_caused_drawdown_failure", "raw_signal_drawdown_failure"),
    }
    for metric, (passed_label, cost_label, raw_label) in checks.items():
        raw_value = _delta(no_cost, metric)
        cost_value = _delta(with_cost, metric)
        if metric == "max_drawdown":
            raw_pass = raw_value >= 0.0
            cost_pass = cost_value >= 0.0
        else:
            raw_pass = raw_value > 0.0
            cost_pass = cost_value > 0.0
        if cost_pass:
            classifications[metric] = passed_label
        elif raw_pass:
            classifications[metric] = cost_label
        else:
            classifications[metric] = raw_label
    return classifications


def _fold_turnover_summary(
    fold: dict[str, Any],
    *,
    no_cost: dict[str, Any],
    with_cost: dict[str, Any],
    warning_cost_bps: float,
) -> dict[str, Any]:
    candidate = with_cost.get("candidate") or {}
    classifications = _metric_cost_classification(no_cost, with_cost)
    return {
        "fold": fold.get("fold"),
        "train_start": fold.get("train_start"),
        "train_end": fold.get("train_end"),
        "test_start": fold.get("test_start"),
        "test_end": fold.get("test_end"),
        "warning_cost_bps": warning_cost_bps,
        "mean_daily_turnover": candidate.get("mean_daily_turnover"),
        "total_turnover": candidate.get("total_turnover"),
        "estimated_cost_drag_return": (
            float(candidate.get("total_turnover") or 0.0) * warning_cost_bps / 10_000.0
        ),
        "no_cost_delta_vs_equal_weight": no_cost.get("delta_vs_equal_weight") or {},
        "with_cost_delta_vs_equal_weight": with_cost.get("delta_vs_equal_weight") or {},
        "cost_drag_delta_vs_equal_weight": {
            "final_value": _delta(with_cost, "final_value") - _delta(no_cost, "final_value"),
            "sharpe_ratio": _delta(with_cost, "sharpe_ratio") - _delta(no_cost, "sharpe_ratio"),
            "max_drawdown": _delta(with_cost, "max_drawdown") - _delta(no_cost, "max_drawdown"),
        },
        "metric_cost_classification": classifications,
        "cost_caused_any_failure": any(value.startswith("cost_caused_") for value in classifications.values()),
        "raw_signal_any_failure": any(value.startswith("raw_signal_") for value in classifications.values()),
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    high_scores: list[float] | None = None,
    warning_cost_bps: float = 5.0,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
    low_score: float = 1.00,
    mid_score: float = 1.00,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    audit = _load_json(walk_forward_audit_path)
    blockers: list[str] = []

    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not audit:
        blockers.append("missing_walk_forward_audit")
    elif audit.get("status") != "available_for_manual_offline_review":
        blockers.append(f"walk_forward_audit_not_available:{audit.get('status')}")

    expected_hash = audit.get("inputs", {}).get("actual_panel_sha256") if audit else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")

    excluded = set(excluded_tickers or DEFAULT_EXCLUDED_TICKERS)
    all_tickers = sorted(panel["ticker"].dropna().unique()) if "ticker" in panel.columns else []
    eligible_tickers = [ticker for ticker in all_tickers if ticker not in excluded]
    if len(eligible_tickers) < 2:
        blockers.append("too_few_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        blockers.append("leveraged_or_inverse_ticker_not_excluded")

    folds = audit.get("folds") if isinstance(audit.get("folds"), list) else []
    if not folds:
        blockers.append("missing_walk_forward_folds")

    high_scores = high_scores or [1.01, 1.02, 1.03]
    candidate_results: list[dict[str, Any]] = []
    for high_score in high_scores:
        no_cost_rows: list[dict[str, Any]] = []
        with_cost_rows: list[dict[str, Any]] = []
        fold_summaries: list[dict[str, Any]] = []
        if not blockers:
            for fold in folds:
                no_cost = _fold_backtest(
                    panel,
                    fold,
                    eligible_tickers=eligible_tickers,
                    low_quantile=low_quantile,
                    high_quantile=high_quantile,
                    low_score=low_score,
                    mid_score=mid_score,
                    high_score=high_score,
                    cost_bps=0.0,
                )
                with_cost = _fold_backtest(
                    panel,
                    fold,
                    eligible_tickers=eligible_tickers,
                    low_quantile=low_quantile,
                    high_quantile=high_quantile,
                    low_score=low_score,
                    mid_score=mid_score,
                    high_score=high_score,
                    cost_bps=warning_cost_bps,
                )
                no_cost_rows.append(no_cost)
                with_cost_rows.append(with_cost)
                fold_summaries.append(
                    _fold_turnover_summary(
                        fold,
                        no_cost=no_cost,
                        with_cost=with_cost,
                        warning_cost_bps=warning_cost_bps,
                    )
                )

        no_cost_aggregate = _aggregate_folds(no_cost_rows)
        with_cost_aggregate = _aggregate_folds(with_cost_rows)
        cost_caused_folds = [row for row in fold_summaries if row["cost_caused_any_failure"]]
        raw_signal_failure_folds = [row for row in fold_summaries if row["raw_signal_any_failure"]]
        candidate_results.append(
            {
                "high_score": high_score,
                "warning_cost_bps": warning_cost_bps,
                "no_cost_aggregate": no_cost_aggregate,
                "with_cost_aggregate": with_cost_aggregate,
                "aggregate_cost_drag": {
                    "mean_delta_final_value": (
                        (with_cost_aggregate.get("mean_delta_final_value") or 0.0)
                        - (no_cost_aggregate.get("mean_delta_final_value") or 0.0)
                    ),
                    "mean_delta_sharpe_ratio": (
                        (with_cost_aggregate.get("mean_delta_sharpe_ratio") or 0.0)
                        - (no_cost_aggregate.get("mean_delta_sharpe_ratio") or 0.0)
                    ),
                    "mean_delta_max_drawdown": (
                        (with_cost_aggregate.get("mean_delta_max_drawdown") or 0.0)
                        - (no_cost_aggregate.get("mean_delta_max_drawdown") or 0.0)
                    ),
                },
                "fold_results": fold_summaries,
                "cost_caused_failure_folds": cost_caused_folds,
                "raw_signal_failure_folds": raw_signal_failure_folds,
                "cost_caused_failure_fold_count": len(cost_caused_folds),
                "raw_signal_failure_fold_count": len(raw_signal_failure_folds),
                "passes_required_thresholds_after_cost": bool(
                    with_cost_aggregate.get("positive_final_value_folds", 0) >= min_positive_final_folds
                    and with_cost_aggregate.get("positive_sharpe_folds", 0) >= min_positive_sharpe_folds
                    and with_cost_aggregate.get("non_worse_drawdown_folds", 0) >= min_non_worse_drawdown_folds
                ),
            }
        )

    best = max(
        candidate_results,
        key=lambda row: (
            int(row["with_cost_aggregate"].get("positive_final_value_folds", 0) or 0),
            int(row["with_cost_aggregate"].get("positive_sharpe_folds", 0) or 0),
            int(row["with_cost_aggregate"].get("non_worse_drawdown_folds", 0) or 0),
            -int(row["cost_caused_failure_fold_count"]),
            float(row["with_cost_aggregate"].get("mean_delta_sharpe_ratio") or 0.0),
        ),
    ) if candidate_results else None
    best_cause = None
    if best:
        best_cause = (
            "turnover_cost_and_raw_signal"
            if best["cost_caused_failure_fold_count"] and best["raw_signal_failure_fold_count"]
            else "turnover_cost"
            if best["cost_caused_failure_fold_count"]
            else "raw_signal"
            if best["raw_signal_failure_fold_count"]
            else "no_fold_failure_detected"
        )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_cost_warning_turnover_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "cost_warning_turnover_attribution_only_no_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "high_scores": high_scores,
            "warning_cost_bps": warning_cost_bps,
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "mid_score": mid_score,
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "evaluated_count": len(candidate_results),
            "best_high_score": best["high_score"] if best else None,
            "best_failure_cause": best_cause,
            "best_cost_caused_failure_fold_count": best["cost_caused_failure_fold_count"] if best else None,
            "best_raw_signal_failure_fold_count": best["raw_signal_failure_fold_count"] if best else None,
            "best_no_cost_aggregate": best["no_cost_aggregate"] if best else None,
            "best_with_cost_aggregate": best["with_cost_aggregate"] if best else None,
            "best_aggregate_cost_drag": best["aggregate_cost_drag"] if best else None,
        },
        "candidate_results": candidate_results,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": [],
        "interpretation": [
            "If a fold passes at 0 bps but fails at the warning cost, turnover cost caused that fold failure.",
            "If a fold already fails at 0 bps, the raw micro-tilt signal is insufficient in that fold.",
            "This report is diagnostic only and does not authorize training or live changes.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "turnover_cost_attribution_ready": bool(not blockers and candidate_results),
            "shadow_training_ready": False,
            "shadow_training_request_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_cost_warning_turnover_attribution_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--walk-forward-audit", default=str(DEFAULT_WF_AUDIT))
    parser.add_argument("--exclude-ticker", action="append", default=[])
    parser.add_argument("--high-scores", default="1.01,1.02,1.03")
    parser.add_argument("--warning-cost-bps", type=float, default=5.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        high_scores=_float_list(args.high_scores),
        warning_cost_bps=args.warning_cost_bps,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward cost warning turnover attribution: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "best_high_score": review["summary"]["best_high_score"],
                "best_failure_cause": review["summary"]["best_failure_cause"],
                "best_cost_caused_failure_fold_count": review["summary"]["best_cost_caused_failure_fold_count"],
                "best_raw_signal_failure_fold_count": review["summary"]["best_raw_signal_failure_fold_count"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
