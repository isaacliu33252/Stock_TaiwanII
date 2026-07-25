#!/usr/bin/env python3
"""Cost-aware micro-tilt guard for the frozen GroupA+ GIFT panel.

This shadow check validates a very small reward tilt across explicit cost
scenarios. It does not train models, output target weights, or authorize live
rebalance decisions.
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
    _load_panel,
    _sha256_file,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.sweep_group_a_plus_llm_state_reward_frozen_panel_baseline_params import (  # noqa: E402
    _evaluate_params,
    _prepare_wide,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_cost_aware_micro_tilt_guard_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_cost_aware_micro_tilt_guard_shadow_backtest/history"


def _float_list(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _scenario_passes(
    aggregate: dict[str, Any],
    *,
    min_positive_final_folds: int,
    min_positive_sharpe_folds: int,
    min_non_worse_drawdown_folds: int,
) -> bool:
    return bool(
        int(aggregate.get("positive_final_value_folds", 0) or 0) >= min_positive_final_folds
        and int(aggregate.get("positive_sharpe_folds", 0) or 0) >= min_positive_sharpe_folds
        and int(aggregate.get("non_worse_drawdown_folds", 0) or 0) >= min_non_worse_drawdown_folds
    )


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
    low_score: float = 1.00,
    high_score: float = 1.03,
    max_high_score: float = 1.03,
    required_cost_bps: list[float] | None = None,
    warning_cost_bps: list[float] | None = None,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    audit = _load_json(walk_forward_audit_path)
    blockers: list[str] = []
    warnings: list[str] = []

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

    required_cost_bps = required_cost_bps or [0.0, 2.0]
    warning_cost_bps = warning_cost_bps or [5.0]
    if low_score != 1.0:
        blockers.append("low_score_must_remain_neutral_for_micro_tilt")
    if high_score > max_high_score:
        blockers.append(f"high_score_above_micro_tilt_cap:{high_score}>{max_high_score}")
    if high_score < 1.0:
        blockers.append("high_score_below_neutral")

    prepared = _prepare_wide(panel, eligible_tickers=eligible_tickers) if not blockers else {}
    scenario_results: list[dict[str, Any]] = []
    for cost_bps in sorted(set(required_cost_bps + warning_cost_bps)):
        if blockers:
            break
        result = _evaluate_params(
            prepared,
            folds,
            eligible_tickers=eligible_tickers,
            low_quantile=low_quantile,
            high_quantile=high_quantile,
            low_score=low_score,
            high_score=high_score,
            cost_bps=cost_bps,
        )
        required = cost_bps in set(required_cost_bps)
        passed = _scenario_passes(
            result["aggregate"],
            min_positive_final_folds=min_positive_final_folds,
            min_positive_sharpe_folds=min_positive_sharpe_folds,
            min_non_worse_drawdown_folds=min_non_worse_drawdown_folds,
        )
        if required and not passed:
            blockers.append(f"required_cost_scenario_failed:{cost_bps:g}bps")
        if not required and not passed:
            warnings.append(f"warning_cost_scenario_failed:{cost_bps:g}bps")
        scenario_results.append(
            {
                "cost_bps": cost_bps,
                "required_for_gate": required,
                "passed": passed,
                "params": result["params"],
                "aggregate": result["aggregate"],
                "rank_score": result["rank_score"],
            }
        )

    required_results = [row for row in scenario_results if row["required_for_gate"]]
    warning_results = [row for row in scenario_results if not row["required_for_gate"]]
    pass_gate = bool(not blockers and required_results and all(row["passed"] for row in required_results))

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_cost_aware_micro_tilt_guard_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "cost_aware_micro_tilt_guard_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "high_score": high_score,
            "max_high_score": max_high_score,
            "required_cost_bps": required_cost_bps,
            "warning_cost_bps": warning_cost_bps,
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "required_cost_scenarios": len(required_results),
            "required_cost_scenarios_passed": int(sum(row["passed"] for row in required_results)),
            "warning_cost_scenarios": len(warning_results),
            "warning_cost_scenarios_passed": int(sum(row["passed"] for row in warning_results)),
            "micro_tilt_guard_passed": pass_gate,
            "required_results": required_results,
            "warning_results": warning_results,
        },
        "scenario_results": scenario_results,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The guard permits only a neutral downside bucket and a very small high-reward tilt.",
            "Required cost scenarios must pass all fold-count thresholds before this can count as a shadow risk-control gate.",
            "This report is research-only and does not emit target weights or live rebalance instructions.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "cost_aware_micro_tilt_guard_ready_for_review": not blockers,
            "cost_aware_micro_tilt_guard_passed_shadow_gate": pass_gate,
            "next_shadow_model_design_allowed": pass_gate,
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
    return history_dir / f"llm_state_reward_interface_cost_aware_micro_tilt_guard_shadow_backtest_{stamp}.json"


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
    parser.add_argument("--low-quantile", type=float, default=0.30)
    parser.add_argument("--high-quantile", type=float, default=0.70)
    parser.add_argument("--low-score", type=float, default=1.00)
    parser.add_argument("--high-score", type=float, default=1.03)
    parser.add_argument("--max-high-score", type=float, default=1.03)
    parser.add_argument("--required-cost-bps", default="0,2")
    parser.add_argument("--warning-cost-bps", default="5")
    parser.add_argument("--min-positive-final-folds", type=int, default=4)
    parser.add_argument("--min-positive-sharpe-folds", type=int, default=4)
    parser.add_argument("--min-non-worse-drawdown-folds", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        low_quantile=args.low_quantile,
        high_quantile=args.high_quantile,
        low_score=args.low_score,
        high_score=args.high_score,
        max_high_score=args.max_high_score,
        required_cost_bps=_float_list(args.required_cost_bps),
        warning_cost_bps=_float_list(args.warning_cost_bps),
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward cost-aware micro-tilt guard shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "micro_tilt_guard_passed": review["summary"]["micro_tilt_guard_passed"],
                "required_cost_scenarios_passed": review["summary"]["required_cost_scenarios_passed"],
                "warning_cost_scenarios_passed": review["summary"]["warning_cost_scenarios_passed"],
                "next_shadow_model_design_allowed": review["decision"]["next_shadow_model_design_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
