#!/usr/bin/env python3
"""Build goal/horizon reward readiness review for Group A+.

Inspired by arXiv:2511.18076. This imports the paper's goal-based reward
framing as governance only: target wealth, horizon, contribution cost, and
transaction-cost terms must be explicit before any RL/reward overlay can be
considered. It never changes live weights or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json"
DEFAULT_EXECUTION_PLAN = (
    PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_20260810_1m_workbook_20260807_latest_strategy_preview.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/goal_horizon_reward_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/goal_horizon_reward_readiness/history"

GOAL_KEYS = ("financial_goal_target_value", "target_portfolio_value", "goal_target_value")
DATE_KEYS = ("financial_goal_target_date", "target_date", "goal_target_date")
CONTRIBUTION_KEYS = ("planned_periodic_contribution", "contribution_plan", "monthly_contribution")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload.get("data"), dict):
        data = dict(payload["data"])
        data["_envelope_metadata"] = payload.get("metadata") or {}
        return data
    return payload


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    metadata = payload.get("_envelope_metadata") or {}
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _weights(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("target_weights") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def _goal_path_readiness(signal: dict[str, Any], execution_plan: dict[str, Any]) -> dict[str, Any]:
    goal = _first_present(signal, GOAL_KEYS) or _first_present(execution_plan, GOAL_KEYS)
    target_date = _first_present(signal, DATE_KEYS) or _first_present(execution_plan, DATE_KEYS)
    contribution = _first_present(signal, CONTRIBUTION_KEYS) or _first_present(execution_plan, CONTRIBUTION_KEYS)
    target_weights = _weights(signal)
    cash_weight = target_weights.get("cash")
    leveraged_weight = target_weights.get("00631L.TW", 0.0)
    inverse_weight = target_weights.get("00632R.TW", 0.0)
    risky_weight = sum(value for key, value in target_weights.items() if key != "cash")
    return {
        "financial_goal_target_value": goal,
        "financial_goal_target_date": target_date,
        "planned_periodic_contribution": contribution,
        "has_goal_target": goal is not None,
        "has_goal_horizon": target_date is not None,
        "has_contribution_plan": contribution is not None,
        "has_target_weights": bool(target_weights),
        "target_weight_summary": {
            "cash": cash_weight,
            "risky_weight": risky_weight if target_weights else None,
            "00631l_weight": leveraged_weight,
            "00632r_weight": inverse_weight,
        },
        "execution_cost_available": bool(
            _nested(execution_plan, "summary", "estimated_total_cost")
            or _nested(execution_plan, "totals", "estimated_total_cost")
            or execution_plan.get("estimated_total_cost")
        ),
    }


def build_review(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    execution_plan_path: Path = DEFAULT_EXECUTION_PLAN,
    as_of: str = "2026-08-08",
) -> dict[str, Any]:
    signal = _load(live_signal_path)
    execution_plan = _load(execution_plan_path)
    readiness = _goal_path_readiness(signal, execution_plan)

    blockers: list[str] = []
    warnings: list[str] = []
    if not signal:
        blockers.append("missing_live_signal")
    if not execution_plan:
        warnings.append("missing_execution_plan")
    if not readiness["has_goal_target"]:
        blockers.append("missing_explicit_financial_goal_target_value")
    if not readiness["has_goal_horizon"]:
        blockers.append("missing_explicit_goal_target_date")
    if not readiness["has_contribution_plan"]:
        blockers.append("missing_periodic_contribution_plan")
    if not readiness["execution_cost_available"]:
        warnings.append("missing_explicit_transaction_cost_summary_for_reward_penalty")
    if not readiness["has_target_weights"]:
        blockers.append("missing_target_weights")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_goal_horizon_reward_readiness_review",
        "status": "blocked" if blockers else "research_ready",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "research_only_goal_horizon_reward_review_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2511.18076.pdf",
            "title": "Reinforcement Learning for Portfolio Optimization with a Financial Goal and Defined Time Horizons",
            "arxiv": "2511.18076v1",
            "date_in_pdf": "2025-11-22",
            "imported_concepts": [
                "explicit_target_wealth_and_target_date",
                "periodic_contribution_cost_penalty",
                "underachievement_penalty_against_goal_path",
                "transaction_cost_penalty_for_rebalancing",
                "reward_parameters_must_remain_shadow_until_trade_level_validation",
            ],
            "not_imported": [
                "g_learning_live_allocator",
                "girl_inverse_rl_parameter_fitting",
                "gbm_simulation_results_as_taiwan_etf_evidence",
                "sharpe_0_483_as_group_a_plus_promotion_evidence",
                "automatic_contribution_or_rebalance_changes",
            ],
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
        },
        "goal_path_readiness": readiness,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "recommendation": {
            "summary": (
                "Useful concept: add an explicit goal/horizon/contribution reward-readiness layer. "
                "Do not import the paper's G-Learning/GIRL allocator into latest strategy."
            ),
            "next_shadow_step": (
                "Before any reward overlay, require target wealth, target date, contribution plan, "
                "and transaction-cost terms in the strategy contract."
            ),
        },
        "decision": {
            "goal_horizon_reward_layer_imported_as_review": True,
            "ready_for_reward_overlay_backtest": False if blockers else True,
            "live_rl_allocator_allowed": False,
            "girl_parameter_learning_allowed_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "creates_orders": False,
            "keep_golden1_0531_unchanged": True,
            "promotion_ready": False,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"goal_horizon_reward_readiness_{stamp}.json"


def write_review(report: dict[str, Any], output: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--as-of", default="2026-08-08")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_review(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        as_of=args.as_of,
    )
    write_review(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report["blocking_reasons"],
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
