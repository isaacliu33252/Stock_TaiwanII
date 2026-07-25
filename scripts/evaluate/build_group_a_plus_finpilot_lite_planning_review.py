#!/usr/bin/env python3
"""Build a FinPILOT-lite planning review for GroupA+.

This is a review-only interpretation of arXiv 2605.12653. It does not perform
inference-time policy updates, does not optimize actor weights, and does not
alter production target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal_20260720_estimate.json"
DEFAULT_REBALANCE_REVIEW = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rebalance_review_20260720.json"
DEFAULT_HETEROGENEOUS_VOL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "heterogeneous_vol_regime_advisory.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finpilot_lite_planning_review_20260720.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _candidate(
    *,
    name: str,
    weights: dict[str, float],
    expected_return_proxy: str,
    downside_penalty: str,
    freshness_penalty: str,
    turnover_penalty: str,
    auto_apply_allowed: bool,
    rationale: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "weights": weights,
        "expected_return_proxy": expected_return_proxy,
        "downside_penalty": downside_penalty,
        "freshness_penalty": freshness_penalty,
        "turnover_penalty": turnover_penalty,
        "auto_apply_allowed": auto_apply_allowed,
        "rationale": rationale,
    }


def build_review(
    *,
    live_signal_path: Path,
    rebalance_review_path: Path,
    heterogeneous_vol_path: Path,
) -> dict[str, Any]:
    live = _data(_load(live_signal_path))
    rebalance = _load(rebalance_review_path)
    hetero = _load(heterogeneous_vol_path)
    target = {str(k): float(v) for k, v in (live.get("target_weights") or {}).items()}
    no_add = dict(target)
    no_add["00631L.TW"] = 0.0
    no_add["cash"] = min(1.0, float(no_add.get("cash", 0.0)) + float(target.get("00631L.TW", 0.0)))
    higher_cash = dict(target)
    reduce_631l = min(float(higher_cash.get("00631L.TW", 0.0)), 0.10)
    higher_cash["00631L.TW"] = float(higher_cash.get("00631L.TW", 0.0)) - reduce_631l
    higher_cash["cash"] = min(1.0, float(higher_cash.get("cash", 0.0)) + reduce_631l)

    execution_allowed = bool(live.get("execution_allowed"))
    warnings = [str(item) for item in (live.get("execution_warning_reasons") or [])]
    guards = [str(item) for item in (live.get("execution_guard_reasons") or [])]
    forecast_freshness_failed = any("NCF live overlay skipped" in item for item in warnings)
    required_source_failed = bool(guards)
    hetero_level = ((hetero.get("advisory") or {}).get("level"))
    hetero_high = str(hetero_level) == "high"
    auto_apply_allowed = bool(execution_allowed and not forecast_freshness_failed and not hetero_high)

    candidates = [
        _candidate(
            name="base_target_reference_only",
            weights=target,
            expected_return_proxy="uses_latest_groupa_target_as_reference",
            downside_penalty="high" if hetero_high else "medium",
            freshness_penalty="failed" if forecast_freshness_failed or required_source_failed else "pass",
            turnover_penalty="unknown_until_fresh_execution_plan",
            auto_apply_allowed=False,
            rationale="Reference target remains useful, but stale/missing sources and high heterogeneous volatility block auto apply.",
        ),
        _candidate(
            name="no_00631l_add",
            weights=no_add,
            expected_return_proxy="lower_leveraged_upside",
            downside_penalty="lower_than_base_target",
            freshness_penalty="more_robust_to_forecast_mismatch",
            turnover_penalty="requires_fresh_holdings_before_execution",
            auto_apply_allowed=False,
            rationale="Preferred manual-review candidate while forecast freshness and volatility advisory are not clean.",
        ),
        _candidate(
            name="higher_cash_buffer",
            weights=higher_cash,
            expected_return_proxy="reduced_upside_capture",
            downside_penalty="reduced_00631l_downside",
            freshness_penalty="more_robust_to_forecast_mismatch",
            turnover_penalty="requires_fresh_execution_plan",
            auto_apply_allowed=False,
            rationale="Alternative if manual review wants to preserve core 0050 while lowering leveraged exposure.",
        ),
    ]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finpilot_lite_planning_review",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_planning_only_no_weight_change",
        "active_allocation_impact": "none",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.12653.pdf",
            "title": "Plan Before You Trade: Inference-Time Optimization for RL Trading Agents",
            "implementation_note": "FinPILOT-lite review only. No actor update, no gradient step, no live optimization.",
        },
        "dates": {
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
        },
        "strategy": {
            "strategy_id": live.get("strategy_id"),
            "execution_regime": live.get("execution_regime"),
            "market_state": live.get("market_state"),
        },
        "forecast_quality_gate": {
            "status": "failed" if forecast_freshness_failed or required_source_failed else "pass",
            "forecast_freshness_failed": forecast_freshness_failed,
            "required_source_failed": required_source_failed,
            "execution_guard_reasons": guards,
            "execution_warning_reasons": warnings,
        },
        "downside_risk_gate": {
            "status": "high" if hetero_high else "not_high",
            "heterogeneous_vol_level": hetero_level,
            "heterogeneous_vol_suggested_review": (hetero.get("advisory") or {}).get("suggested_review"),
        },
        "candidate_plans": candidates,
        "recommended_plan_for_manual_review": "no_00631l_add_or_wait_for_fresh_data",
        "auto_apply_allowed": auto_apply_allowed,
        "manual_review_required": True,
        "decision": {
            "summary": "Use FinPILOT-lite as preview-only planning. Do not auto-apply any plan until source data, NCF freshness, and execution plan are rebuilt.",
            "target_weight_change_allowed": False,
            "allow_00631l_auto_add": False,
            "allow_inference_time_policy_update": False,
            "allow_auto_rebalance": False,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "rebalance_review": str(rebalance_review_path) if rebalance_review_path.exists() else None,
            "heterogeneous_vol_regime_advisory": str(heterogeneous_vol_path) if heterogeneous_vol_path.exists() else None,
            "rebalance_review_decision": (rebalance.get("decision") or {}),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--rebalance-review", default=str(DEFAULT_REBALANCE_REVIEW))
    parser.add_argument("--heterogeneous-vol", default=str(DEFAULT_HETEROGENEOUS_VOL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = _resolve(args.output)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        rebalance_review_path=_resolve(args.rebalance_review),
        heterogeneous_vol_path=_resolve(args.heterogeneous_vol),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Review: {output}")
    print(
        json.dumps(
            {
                "forecast_quality_gate": review["forecast_quality_gate"]["status"],
                "downside_risk_gate": review["downside_risk_gate"]["status"],
                "recommended_plan_for_manual_review": review["recommended_plan_for_manual_review"],
                "auto_apply_allowed": review["auto_apply_allowed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
