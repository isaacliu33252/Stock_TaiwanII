#!/usr/bin/env python3
"""Review remediation attempts for the GIFT micro-tilt 5 bps cost warning.

This searches a narrow, pre-declared micro-tilt family to see whether the
warning cost scenario can be promoted to a required scenario. It is
research-only and never trains models or emits target weights.
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

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_cost_aware_micro_tilt_guard_shadow import (  # noqa: E402
    DEFAULT_PANEL_OUTPUT,
    DEFAULT_WF_AUDIT,
    build_review as build_micro_tilt_review,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _resolve  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_cost_warning_remediation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_cost_warning_remediation_review/history"


def _float_list(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    high_scores: list[float] | None = None,
    required_cost_bps: list[float] | None = None,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    high_scores = high_scores or [1.01, 1.02, 1.03]
    required_cost_bps = required_cost_bps or [0.0, 2.0, 5.0]
    rows: list[dict[str, Any]] = []
    for high_score in high_scores:
        review = build_micro_tilt_review(
            panel_path=panel_path,
            walk_forward_audit_path=walk_forward_audit_path,
            low_score=1.0,
            high_score=high_score,
            max_high_score=max(high_scores),
            required_cost_bps=required_cost_bps,
            warning_cost_bps=[],
            min_positive_final_folds=min_positive_final_folds,
            min_positive_sharpe_folds=min_positive_sharpe_folds,
            min_non_worse_drawdown_folds=min_non_worse_drawdown_folds,
            as_of=as_of,
        )
        rows.append(
            {
                "high_score": high_score,
                "status": review["status"],
                "passed": review["summary"]["micro_tilt_guard_passed"],
                "required_cost_scenarios_passed": review["summary"]["required_cost_scenarios_passed"],
                "scenario_results": review["scenario_results"],
                "blocking_reasons": review["blocking_reasons"],
            }
        )

    passed = [row for row in rows if row["passed"]]
    best = max(
        rows,
        key=lambda row: (
            int(row["required_cost_scenarios_passed"] or 0),
            -float(row["high_score"]),
        ),
    ) if rows else None
    blockers = [] if passed else ["no_micro_tilt_candidate_passes_required_cost_scenarios"]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_cost_warning_remediation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "cost_warning_remediation_review_only_no_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "walk_forward_audit": str(walk_forward_audit_path),
            "high_scores": high_scores,
            "required_cost_bps": required_cost_bps,
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "evaluated_count": len(rows),
            "passed_count": len(passed),
            "best_high_score": best["high_score"] if best else None,
            "best_required_cost_scenarios_passed": best["required_cost_scenarios_passed"] if best else None,
            "recommended_candidate": passed[0] if passed else None,
            "cost_warning_resolved": bool(passed),
        },
        "candidate_results": rows,
        "blocking_reasons": blockers,
        "warning_reasons": [],
        "interpretation": [
            "This review tests whether a smaller micro-tilt can satisfy the 5 bps cost scenario.",
            "If no candidate passes, shadow training readiness should remain blocked by the unresolved cost warning.",
            "The review does not authorize model training, PPO training, target weights, or live rebalance.",
        ],
        "decision": {
            "available_for_manual_offline_review": True,
            "cost_warning_resolved": bool(passed),
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
    return history_dir / f"llm_state_reward_cost_warning_remediation_review_{stamp}.json"


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
    parser.add_argument("--high-scores", default="1.01,1.02,1.03")
    parser.add_argument("--required-cost-bps", default="0,2,5")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        high_scores=_float_list(args.high_scores),
        required_cost_bps=_float_list(args.required_cost_bps),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward cost warning remediation review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "cost_warning_resolved": review["summary"]["cost_warning_resolved"],
                "passed_count": review["summary"]["passed_count"],
                "best_high_score": review["summary"]["best_high_score"],
                "blocking_reasons": review["blocking_reasons"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
