#!/usr/bin/env python3
"""Build GroupA+ deep-hedging overlay review from arXiv 2512.12420.

Research-only. This imports governance ideas from the paper, not its RL actor:
cost-aware overlay review, bounded hedge/leverage notional, cadence, state
freshness, and deterministic auditability.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260720_estimate.json"
DEFAULT_REBALANCE_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_HETEROGENEOUS_VOL = PROJECT_ROOT / "report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json"
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_DENSITY_PROMOTION = (
    PROJECT_ROOT / "report/group_a_plus/latest/density_head_tail_risk_promotion_review.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json"
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _get_nested(payload: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def build_review(
    *,
    live_signal_path: Path,
    rebalance_review_path: Path,
    heterogeneous_vol_path: Path,
    cvar_path: Path,
    density_promotion_path: Path,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    rebalance = _load(rebalance_review_path)
    hetero = _load(heterogeneous_vol_path)
    cvar = _load(cvar_path)
    density = _load(density_promotion_path)

    target_weights = live.get("target_weights") or {}
    latest_features = live.get("latest_features") or {}
    market_state = live.get("market_state") or {}
    multisource = _get_nested(live, ["trough_nowcast", "inputs", "multisource"], {})
    execution_allowed = bool(live.get("execution_allowed"))
    rebalance_decision = rebalance.get("decision") or {}
    cvar_rank = cvar.get("ranking_by_starr95") or []
    cvar_best = cvar_rank[0] if cvar_rank else {}
    cvar_golden = next(
        (row for row in cvar_rank if row.get("strategy") == "golden1_frozen_proxy_50_20_30"),
        {},
    )

    option_state_missing = [
        name
        for name in (
            "txo_pcr_volume_z20",
            "txo_pcr_oi_z20",
            "soxx_put_call_iv_skew_z252",
            "soxx_put_call_volume_ratio_z60",
            "soxx_put_call_oi_ratio_z60",
        )
        if multisource.get(name) is None
    ]
    high_risk_context = bool(
        (latest_features.get("total_risk_score") or 0) >= 8
        or (market_state.get("risk_level") in {"high", "medium_high"})
        or (rebalance.get("risk_and_freshness", {}).get("heterogeneous_vol_advisory", {}).get("level") == "high")
    )
    density_promoted = bool(_get_nested(density, ["decision", "promote_to_live"], False))
    target_631l = float(target_weights.get("00631L.TW") or 0.0)
    paper_overlay_cap = 0.20

    blockers: list[str] = []
    warnings: list[str] = []
    if not execution_allowed:
        blockers.append("live_signal_execution_not_allowed")
    if option_state_missing:
        blockers.append("option_surface_state_incomplete")
    if high_risk_context:
        blockers.append("medium_high_or_high_risk_context")
    if not rebalance_decision.get("allow_00631l_add", False):
        blockers.append("rebalance_review_disallows_00631l_add")
    if not density_promoted:
        warnings.append("density_head_gmm_not_promoted")
    if cvar_best and cvar_best.get("strategy") != "golden1_frozen_proxy_50_20_30":
        warnings.append("cvar_ranking_does_not_prefer_golden1_proxy")

    allow_overlay_increase = not blockers and target_631l <= paper_overlay_cap
    allow_deep_hedging_rl_import = False

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_deep_hedging_overlay_review",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_review_only_no_weight_change",
        "active_allocation_impact": "none",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.12420.pdf",
            "title": "Deep Hedging with Reinforcement Learning: A Practical Framework for Option Risk Management",
            "imported_concepts": [
                "cost_aware_overlay_reward",
                "position_limits",
                "rebalance_cadence_review",
                "option_surface_and_macro_state_features",
                "deterministic_replay_and_monitoring",
                "overlay_as_risk_management_sleeve_not_alpha_claim",
            ],
            "not_imported": [
                "actor_critic_rl_policy",
                "SPX_SPY_specific_trained_agent",
                "automatic_hedge_execution",
            ],
        },
        "paper_evidence_summary": {
            "final_test_sharpe": 0.502,
            "selected_rebalance_every_days": 25,
            "selected_slippage_bps": 8,
            "transaction_cost_bps_per_abs_delta_position": 10,
            "position_limit": 2.0,
            "authors_limitations": [
                "confidence_intervals_overlap_long_spy_benchmark",
                "daily_bars_ignore_intraday_inventory_and_execution_costs",
                "formal_model_selection_left_for_future_work",
            ],
        },
        "group_a_plus_mapping": {
            "strategy_id": live.get("strategy_id"),
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
            "execution_regime": live.get("execution_regime"),
            "market_state": market_state,
            "target_weights": target_weights,
            "00631l_overlay_weight": target_631l,
            "paper_style_overlay_cap_reference": paper_overlay_cap,
            "state_features_available": {
                "total_risk_score": latest_features.get("total_risk_score"),
                "tail_risk_score": latest_features.get("tail_risk_score"),
                "drawdown": latest_features.get("drawdown"),
                "txo_foreign_put_call_net_oi_chg5_z60": multisource.get("txo_foreign_put_call_net_oi_chg5_z60"),
                "tx_foreign_net_oi_z60": multisource.get("tx_foreign_net_oi_z60"),
                "usdtwd_ret5_z60": multisource.get("usdtwd_ret5_z60"),
            },
            "option_state_missing": option_state_missing,
        },
        "cross_checks": {
            "live_signal_execution_allowed": execution_allowed,
            "rebalance_review": {
                "auto_rebalance_allowed": rebalance_decision.get("auto_rebalance_allowed"),
                "allow_00631l_add": rebalance_decision.get("allow_00631l_add"),
                "target_weight_change_allowed": rebalance_decision.get("target_weight_change_allowed"),
            },
            "heterogeneous_vol_level": hetero.get("advisory", {}).get("level") or hetero.get("level"),
            "density_promotion": {
                "promote_to_live": density_promoted,
                "recommended_research_baseline": _get_nested(
                    density,
                    ["decision", "recommended_research_baseline"],
                ),
                "blockers": _get_nested(density, ["decision", "blockers"], []),
            },
            "cvar_tail_risk": {
                "best_strategy_by_starr95": cvar_best.get("strategy"),
                "golden1_starr95": cvar_golden.get("starr_95"),
                "golden1_max_drawdown": cvar_golden.get("max_drawdown"),
            },
        },
        "overlay_review": {
            "allow_overlay_increase": allow_overlay_increase,
            "allow_00631l_auto_add": False,
            "allow_deep_hedging_rl_import": allow_deep_hedging_rl_import,
            "suggested_rebalance_cadence_days_if_researched": 20,
            "cost_stress_required": True,
            "position_limit_required": True,
            "deterministic_replay_required": True,
            "monitoring_required": [
                "rolling_sharpe",
                "turnover",
                "realized_cost_per_weight_change",
                "option_state_coverage",
                "policy_drift_vs_rule_baseline",
            ],
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import governance ideas only. Do not import the RL actor or change GroupA+ weights; "
                "current stale/incomplete option state and high-risk context block any 00631L overlay increase."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "manual_review_required": True,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "rebalance_review": str(rebalance_review_path),
            "heterogeneous_vol_regime_advisory": str(heterogeneous_vol_path),
            "cvar_tail_risk_diagnostic": str(cvar_path),
            "density_head_tail_risk_promotion_review": str(density_promotion_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--rebalance-review", default=str(DEFAULT_REBALANCE_REVIEW))
    parser.add_argument("--heterogeneous-vol", default=str(DEFAULT_HETEROGENEOUS_VOL))
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--density-promotion", default=str(DEFAULT_DENSITY_PROMOTION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = _resolve(args.output)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        rebalance_review_path=_resolve(args.rebalance_review),
        heterogeneous_vol_path=_resolve(args.heterogeneous_vol),
        cvar_path=_resolve(args.cvar),
        density_promotion_path=_resolve(args.density_promotion),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Deep hedging overlay review: {output}")
    print(
        json.dumps(
            {
                "promote_to_live": review["decision"]["promote_to_live"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
