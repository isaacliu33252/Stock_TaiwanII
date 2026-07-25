#!/usr/bin/env python3
"""Parameter sweep for the GroupA+ GIFT relative drawdown circuit shadow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_relative_drawdown_circuit_shadow import (  # noqa: E402
    DEFAULT_BASELINE,
    DEFAULT_PANEL_OUTPUT,
    build_review,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _resolve  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_relative_drawdown_circuit_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_relative_drawdown_circuit_param_sweep/history"


def _score(summary: dict[str, Any]) -> tuple[int, int, int, float, float, float]:
    agg = summary["relative_drawdown_circuit"]
    return (
        int(agg["non_worse_drawdown_folds"]),
        int(agg["positive_final_value_folds"]),
        int(agg["positive_sharpe_folds"]),
        float(agg["mean_delta_max_drawdown"] or -999.0),
        float(agg["mean_delta_final_value"] or -999.0),
        float(agg["mean_delta_sharpe_ratio"] or -999.0),
    )


def build_sweep(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    triggers: list[float] | None = None,
    recoveries: list[float] | None = None,
    min_days: list[int] | None = None,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    trigger_grid = triggers or [0.0005, 0.001, 0.002, 0.005, 0.01]
    recovery_grid = recoveries or [0.0001, 0.0005, 0.001]
    min_day_grid = min_days or [3, 5, 10]
    rows: list[dict[str, Any]] = []
    for trigger, recovery, min_circuit_days in product(trigger_grid, recovery_grid, min_day_grid):
        review = build_review(
            panel_path=panel_path,
            baseline_path=baseline_path,
            relative_drawdown_trigger=trigger,
            relative_recovery_threshold=recovery,
            min_circuit_days=min_circuit_days,
            min_positive_final_folds=min_positive_final_folds,
            min_positive_sharpe_folds=min_positive_sharpe_folds,
            min_non_worse_drawdown_folds=min_non_worse_drawdown_folds,
            as_of=as_of,
        )
        agg = review["summary"]["relative_drawdown_circuit"]
        rows.append(
            {
                "relative_drawdown_trigger": trigger,
                "relative_recovery_threshold": recovery,
                "min_circuit_days": min_circuit_days,
                "status": review["status"],
                "passed": bool(review["decision"]["relative_drawdown_circuit_passed_shadow_gate"]),
                "positive_final_value_folds": agg["positive_final_value_folds"],
                "positive_sharpe_folds": agg["positive_sharpe_folds"],
                "non_worse_drawdown_folds": agg["non_worse_drawdown_folds"],
                "mean_delta_final_value": agg["mean_delta_final_value"],
                "mean_delta_sharpe_ratio": agg["mean_delta_sharpe_ratio"],
                "mean_delta_max_drawdown": agg["mean_delta_max_drawdown"],
                "mean_circuit_rate": review["summary"]["mean_circuit_rate"],
                "warning_reasons": review["warning_reasons"],
                "blocking_reasons": review["blocking_reasons"],
            }
        )
    passed = [row for row in rows if row["passed"]]
    ranked = sorted(rows, key=lambda row: _score({"relative_drawdown_circuit": row}), reverse=True)
    best = ranked[0] if ranked else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_relative_drawdown_circuit_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "available_for_manual_offline_review",
        "policy": "relative_drawdown_circuit_param_sweep_shadow_only_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "baseline_shadow_backtest": str(baseline_path),
            "triggers": trigger_grid,
            "recoveries": recovery_grid,
            "min_days": min_day_grid,
            "min_positive_final_folds": min_positive_final_folds,
            "min_positive_sharpe_folds": min_positive_sharpe_folds,
            "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
        },
        "summary": {
            "evaluated_count": len(rows),
            "passed_count": len(passed),
            "best_by_drawdown_then_return": best,
            "recommended_candidate": passed[0] if passed else None,
            "has_recommended_candidate": bool(passed),
        },
        "results": ranked,
        "decision": {
            "available_for_manual_offline_review": True,
            "recommended_candidate_available": bool(passed),
            "next_shadow_model_design_allowed": bool(passed),
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
    return history_dir / f"llm_state_reward_interface_relative_drawdown_circuit_param_sweep_{stamp}.json"


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


def _float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def _int_list(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--triggers", default="0.0005,0.001,0.002,0.005,0.01")
    parser.add_argument("--recoveries", default="0.0001,0.0005,0.001")
    parser.add_argument("--min-days", default="3,5,10")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_sweep(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        triggers=_float_list(args.triggers),
        recoveries=_float_list(args.recoveries),
        min_days=_int_list(args.min_days),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward relative drawdown circuit param sweep: {_resolve(args.output)}")
    print(json.dumps(review["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
