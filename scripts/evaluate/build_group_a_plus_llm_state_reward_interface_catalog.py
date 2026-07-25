#!/usr/bin/env python3
"""Build the research-only LLM state/reward proposal catalog for GroupA+."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_catalog.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_catalog/history"


FEATURE_FAMILIES: dict[str, dict[str, Any]] = {
    "momentum": {
        "allowed_primitives": [
            "relative_momentum",
            "multi_horizon_momentum",
            "rate_of_change",
            "moving_average_slope",
        ],
        "required_guards": ["lookback_in_allowed_range", "finite_output", "no_future_data"],
    },
    "volatility": {
        "allowed_primitives": [
            "realized_volatility",
            "atr_proxy",
            "bollinger_band_width",
            "rolling_range",
        ],
        "required_guards": ["lookback_in_allowed_range", "finite_output", "winsorized_or_clipped"],
    },
    "downside_risk": {
        "allowed_primitives": [
            "downside_deviation",
            "rolling_skewness",
            "rolling_kurtosis",
            "drawdown_depth",
        ],
        "required_guards": ["finite_output", "bounded_scale", "minimum_observation_count"],
    },
    "liquidity": {
        "allowed_primitives": [
            "volume_ratio",
            "turnover_ratio",
            "dollar_volume_proxy",
            "amihud_daily_proxy",
        ],
        "required_guards": ["finite_output", "zero_volume_guard", "no_high_frequency_assumption"],
    },
    "mean_reversion": {
        "allowed_primitives": [
            "zscore_price",
            "rolling_deviation_from_ma",
            "rsi_proxy",
            "stochastic_position",
        ],
        "required_guards": ["lookback_in_allowed_range", "finite_output", "bounded_scale"],
    },
    "trend_strength": {
        "allowed_primitives": [
            "adx_proxy",
            "ema_cross_strength",
            "sma_cross_strength",
            "macd_histogram_proxy",
        ],
        "required_guards": ["finite_output", "bounded_scale", "no_action_output"],
    },
    "bucket_active_pain": {
        "allowed_primitives": [
            "active_bucket_weight",
            "active_bucket_return_contribution",
            "active_bucket_drawdown_depth",
            "reward_signal_concentration_hhi",
            "high_dividend_active_pain",
        ],
        "required_guards": [
            "computed_against_equal_weight_baseline",
            "lagged_features_only",
            "finite_output",
            "bounded_scale",
            "no_action_output",
        ],
    },
}


REWARD_TERMS: dict[str, dict[str, Any]] = {
    "drawdown_penalty": {
        "maps_to_group_a_plus_artifact": "dynamic_cvar_tail_cost_readiness_review.json",
        "allowed_parameters": {"threshold": [0.03, 0.25], "penalty_scale": [0.0, 2.0]},
        "promotion_blocker_if_missing": "tail_cost_readiness_ready",
    },
    "turnover_penalty": {
        "maps_to_group_a_plus_artifact": "market_impact_readiness_review.json",
        "allowed_parameters": {"turnover_threshold": [0.0, 0.35], "penalty_scale": [0.0, 2.0]},
        "promotion_blocker_if_missing": "market_impact_ready",
    },
    "concentration_penalty": {
        "maps_to_group_a_plus_artifact": "research_shadow_decision_snapshot.json",
        "allowed_parameters": {"max_weight_soft_cap": [0.2, 0.8], "penalty_scale": [0.0, 1.5]},
        "promotion_blocker_if_missing": "research_shadow_snapshot_available",
    },
    "volatility_scaling": {
        "maps_to_group_a_plus_artifact": "dynamic_cvar_tail_cost_readiness_review.json",
        "allowed_parameters": {"vol_threshold": [0.01, 0.08], "scale_floor": [0.2, 1.0]},
        "promotion_blocker_if_missing": "tail_cost_readiness_ready",
    },
    "cash_defense_bonus": {
        "maps_to_group_a_plus_artifact": "intervention_fatigue_risk_budget_readiness_review.json",
        "allowed_parameters": {"stress_threshold": [0.0, 1.0], "bonus_scale": [0.0, 1.0]},
        "promotion_blocker_if_missing": "risk_budget_pacing_ready",
    },
    "letf_tail_decay_cost": {
        "maps_to_group_a_plus_artifact": "letf_tracking_error_effective_fee_readiness_review.json",
        "allowed_parameters": {"decay_scale": [0.0, 2.0], "tail_scale": [0.0, 2.0]},
        "promotion_blocker_if_missing": "tracking_error_readiness_ready",
    },
    "active_bucket_drawdown_penalty": {
        "maps_to_group_a_plus_artifact": "llm_state_reward_interface_drawdown_failure_event_audit.json",
        "allowed_parameters": {"active_weight_threshold": [0.0, 0.25], "penalty_scale": [0.0, 2.0]},
        "promotion_blocker_if_missing": "state_redesign_diagnostic_ready",
    },
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_catalog(*, readiness_path: Path = DEFAULT_READINESS, as_of: str = "2026-07-20") -> dict[str, Any]:
    readiness = _load(readiness_path)
    readiness_decision = readiness.get("decision") if isinstance(readiness.get("decision"), dict) else {}
    readiness_blocked = readiness.get("status") == "blocked"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_catalog",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "research_catalog_available_live_blocked",
        "policy": "allowlisted_research_proposals_only_no_live_action",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.08450.pdf",
            "arxiv": "2606.08450v1",
            "concept": "GIFT constrained LLM state/reward interface design",
        },
        "readiness_input": {
            "path": str(readiness_path),
            "exists": bool(readiness),
            "status": readiness.get("status"),
            "blocked": readiness_blocked,
            "blocking_reasons": readiness.get("blocking_reasons") or [],
        },
        "feature_allowlist": FEATURE_FAMILIES,
        "reward_allowlist": REWARD_TERMS,
        "proposal_validation_rules": {
            "must_preserve_raw_market_input": True,
            "must_append_features_only": True,
            "must_not_output_actions": True,
            "must_not_output_target_weights": True,
            "must_not_reference_future_data": True,
            "must_return_finite_numeric_values": True,
            "must_clip_parameters_to_allowed_ranges": True,
            "must_include_human_review_note": True,
            "must_include_walk_forward_plan": True,
            "must_freeze_interface_before_oos": True,
            "test_time_llm_queries_allowed": False,
            "generated_code_live_execution_allowed": False,
        },
        "explicit_rejections": [
            "llm_direct_trade_signal",
            "llm_target_weight_output",
            "ppo_live_allocator",
            "test_time_prompt_update",
            "high_frequency_order_book_dependency",
            "unbounded_reward_term",
            "synthetic_alpha_without_validation",
            "market_impact_blind_turnover_reward",
        ],
        "decision": {
            "catalog_available_for_research_review": True,
            "readiness_required_before_any_promotion": True,
            "llm_state_reward_interface_ready": readiness_decision.get("llm_state_reward_interface_ready", False),
            "live_llm_trading_allowed": False,
            "live_ppo_allocator_allowed": False,
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
    return history_dir / f"llm_state_reward_interface_catalog_{stamp}.json"


def write_catalog(catalog: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, catalog.get("as_of")).write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--readiness", default=str(DEFAULT_READINESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    catalog = build_catalog(readiness_path=_resolve(args.readiness), as_of=args.as_of)
    write_catalog(catalog, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward interface catalog: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": catalog["status"],
                "feature_family_count": len(catalog["feature_allowlist"]),
                "reward_term_count": len(catalog["reward_allowlist"]),
                "promote_to_live": catalog["decision"]["promote_to_live"],
                "allow_00631l_add": catalog["decision"]["allow_00631l_add"],
                "allow_00632r_open": catalog["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
