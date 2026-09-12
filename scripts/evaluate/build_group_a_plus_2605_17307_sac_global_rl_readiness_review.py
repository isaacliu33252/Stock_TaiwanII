#!/usr/bin/env python3
"""Build a GroupA+ readiness review for arXiv 2605.17307 SAC portfolio RL."""

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


DEFAULT_STRATEGY = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_sac_global_rl_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_sac_global_rl_readiness_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_review(*, strategy_path: Path = DEFAULT_STRATEGY) -> dict[str, Any]:
    strategy = _load_json(_resolve(strategy_path))
    active = strategy.get("active_strategy") if isinstance(strategy.get("active_strategy"), dict) else {}
    active_strategy_id = active.get("id")
    blockers = [
        "paper_rl_does_not_show_statistically_significant_outperformance_across_all_markets",
        "full_sac_training_cost_high_relative_to_current_groupa_plus_need",
        "groupa_plus_universe_is_small_regime_etf_allocation_not_large_cross_sectional_stock_selection",
        "cash_and_turnover_lessons_are_already_covered_by_existing_governance_layers",
    ]
    reusable = [
        {
            "concept": "walk_forward_plus_adaptive_retraining_review",
            "action": "keep_as_governance_pattern",
            "reason": "paper uses 5y train / 1y validation / 1y test and retrains only when validation Sharpe deteriorates",
        },
        {
            "concept": "hierarchical_equity_cash_decision",
            "action": "test_as_shadow_only_if_reopened",
            "reason": "hierarchical policy lowered volatility/drawdown versus flat policy in the paper",
        },
        {
            "concept": "cash_allowed_flexible_exposure",
            "action": "retain_existing_cash_floor_and_staged_target_preference",
            "reason": "cash-allowed configurations improved drawdown/IR2 versus fully invested variants",
        },
        {
            "concept": "turnover_and_concentration_penalized_reward",
            "action": "retain_as_execution_governance_not_rl_reward_training",
            "reason": "paper directly penalizes turnover and HHI concentration; GroupA+ already uses turnover/cost gates",
        },
        {
            "concept": "regime_dependent_active_allocation_value",
            "action": "map_to_existing_high_uncertainty_shadow_monitors",
            "reason": "paper finds RL value is regime dependent and stronger during elevated uncertainty/lower trend persistence",
        },
        {
            "concept": "cross_market_ensemble_diversification",
            "action": "consider_as_monitoring_lens_only",
            "reason": "paper ensemble improves IR2 economically, but statistical evidence remains limited",
        },
    ]
    rejected = [
        "train_full_sac_actor_critic_now",
        "train_lstm_or_transformer_policy_now",
        "replace_a2118_with_global_rl_policy",
        "allow_rl_generated_target_weights",
        "promote_hierarchical_dirichlet_policy_to_live",
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_sac_global_rl_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "title": "Deep Reinforcement Learning Framework for Diversified Portfolio Management Across Global Equity Markets",
            "core_method": "SAC with LSTM/Transformer encoders, Dirichlet allocation, walk-forward optimization, adaptive retraining",
        },
        "paper_result_summary": {
            "central_hypothesis": "partially_confirmed_only",
            "statistical_outperformance_vs_buy_hold_across_all_markets": False,
            "strongest_single_market": "EURO_STOXX_50",
            "transformer_superiority": False,
            "cash_allowed_helped_drawdown_control": True,
            "hierarchical_policy_helped_risk_control": True,
            "ensemble_improved_ir2_economically_but_not_conclusively": True,
        },
        "latest_strategy": {
            "active_strategy_id": active_strategy_id,
            "strategy_status": active.get("status"),
            "strategy_runner": active.get("runner"),
        },
        "reusable_concepts": reusable,
        "rejected_imports": rejected,
        "decision": {
            "import_as_review_layer": True,
            "train_sac_now": False,
            "train_lstm_or_transformer_policy_now": False,
            "allow_rl_generated_target_weights": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "latest_strategy_remains": active_strategy_id,
            "summary": "Use 2605.17307 as governance evidence for WFO, cash flexibility, turnover penalties, and regime-aware review; do not train or promote a SAC optimizer now.",
        },
        "blocking_reasons": blockers,
    }


def write_review(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d")
    (history_dir / f"2605_17307_sac_global_rl_readiness_review_{stamp}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_review(strategy_path=_resolve(args.strategy))
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
