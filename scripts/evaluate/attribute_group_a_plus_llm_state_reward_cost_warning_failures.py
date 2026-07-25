#!/usr/bin/env python3
"""Attribute the GIFT micro-tilt warning-cost failure by walk-forward fold.

This report explains why the 5 bps warning scenario failed after remediation
attempts. It is research-only and never trains models or emits target weights.
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
    _load_panel,
    _sha256_file,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.sweep_group_a_plus_llm_state_reward_frozen_panel_baseline_params import (  # noqa: E402
    _fold_backtest_fast,
    _prepare_wide,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_cost_warning_failure_attribution.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_cost_warning_failure_attribution/history"


def _float_list(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _metric_failures(
    delta: dict[str, Any],
    *,
    min_delta_final_value: float = 0.0,
    min_delta_sharpe_ratio: float = 0.0,
    min_delta_max_drawdown: float = 0.0,
) -> list[str]:
    failures: list[str] = []
    if (delta.get("final_value") or 0.0) <= min_delta_final_value:
        failures.append("final_value_delta_not_positive")
    if (delta.get("sharpe_ratio") or 0.0) <= min_delta_sharpe_ratio:
        failures.append("sharpe_delta_not_positive")
    if (delta.get("max_drawdown") or 0.0) < min_delta_max_drawdown:
        failures.append("max_drawdown_delta_worse")
    return failures


def _fold_row_with_window(row: dict[str, Any], fold: dict[str, Any]) -> dict[str, Any]:
    delta = row.get("delta_vs_equal_weight") if isinstance(row.get("delta_vs_equal_weight"), dict) else {}
    failures = _metric_failures(delta)
    return {
        "fold": row.get("fold", fold.get("fold")),
        "status": row.get("status"),
        "train_start": fold.get("train_start"),
        "train_end": fold.get("train_end"),
        "test_start": fold.get("test_start"),
        "test_end": fold.get("test_end"),
        "delta_vs_equal_weight": delta,
        "failed_metrics": failures,
        "passed_all_delta_checks": not failures,
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    high_scores: list[float] | None = None,
    cost_bps: float = 5.0,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
    low_score: float = 1.00,
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
    prepared = _prepare_wide(panel, eligible_tickers=eligible_tickers) if not blockers else {}
    candidate_rows: list[dict[str, Any]] = []
    for high_score in high_scores:
        fold_rows = [
            _fold_backtest_fast(
                prepared,
                fold,
                eligible_tickers=eligible_tickers,
                low_quantile=low_quantile,
                high_quantile=high_quantile,
                low_score=low_score,
                high_score=high_score,
                cost_bps=cost_bps,
            )
            for fold in folds
        ] if not blockers else []
        detailed_folds = [_fold_row_with_window(row, fold) for row, fold in zip(fold_rows, folds)]
        aggregate = _aggregate_folds(fold_rows)
        failed_folds = [row for row in detailed_folds if row["failed_metrics"]]
        candidate_rows.append(
            {
                "high_score": high_score,
                "cost_bps": cost_bps,
                "aggregate": aggregate,
                "fold_results": detailed_folds,
                "failed_folds": failed_folds,
                "failure_metric_counts": {
                    "final_value_delta_not_positive": sum(
                        "final_value_delta_not_positive" in row["failed_metrics"] for row in detailed_folds
                    ),
                    "sharpe_delta_not_positive": sum(
                        "sharpe_delta_not_positive" in row["failed_metrics"] for row in detailed_folds
                    ),
                    "max_drawdown_delta_worse": sum(
                        "max_drawdown_delta_worse" in row["failed_metrics"] for row in detailed_folds
                    ),
                },
                "passes_required_thresholds": bool(
                    aggregate.get("positive_final_value_folds", 0) >= min_positive_final_folds
                    and aggregate.get("positive_sharpe_folds", 0) >= min_positive_sharpe_folds
                    and aggregate.get("non_worse_drawdown_folds", 0) >= min_non_worse_drawdown_folds
                ),
            }
        )

    best = max(
        candidate_rows,
        key=lambda row: (
            int(row["aggregate"].get("positive_final_value_folds", 0) or 0),
            int(row["aggregate"].get("positive_sharpe_folds", 0) or 0),
            int(row["aggregate"].get("non_worse_drawdown_folds", 0) or 0),
            float(row["aggregate"].get("mean_delta_sharpe_ratio") or 0.0),
        ),
    ) if candidate_rows else None
    threshold_passes = [row for row in candidate_rows if row["passes_required_thresholds"]]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_cost_warning_failure_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "cost_warning_failure_attribution_only_no_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "high_scores": high_scores,
            "cost_bps": cost_bps,
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "evaluated_count": len(candidate_rows),
            "candidate_passing_required_thresholds_count": len(threshold_passes),
            "best_high_score": best["high_score"] if best else None,
            "best_aggregate": best["aggregate"] if best else None,
            "dominant_failure_metric_for_best": (
                max(best["failure_metric_counts"], key=best["failure_metric_counts"].get) if best else None
            ),
            "cost_warning_failure_explained": bool(candidate_rows and not threshold_passes),
        },
        "candidate_results": candidate_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": [],
        "interpretation": [
            "The warning-cost failure is evaluated fold by fold against equal weight.",
            "A negative Sharpe delta is enough to fail the positive Sharpe fold-count gate even when final value improves.",
            "This report is diagnostic only and does not authorize training or live changes.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "cost_warning_failure_explained": bool(candidate_rows and not threshold_passes),
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
    return history_dir / f"llm_state_reward_cost_warning_failure_attribution_{stamp}.json"


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
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        high_scores=_float_list(args.high_scores),
        cost_bps=args.cost_bps,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward cost warning failure attribution: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "best_high_score": review["summary"]["best_high_score"],
                "candidate_passing_required_thresholds_count": review["summary"][
                    "candidate_passing_required_thresholds_count"
                ],
                "dominant_failure_metric_for_best": review["summary"]["dominant_failure_metric_for_best"],
                "cost_warning_failure_explained": review["decision"]["cost_warning_failure_explained"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
