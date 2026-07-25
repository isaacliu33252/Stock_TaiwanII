#!/usr/bin/env python3
"""Build a manual rebalance review artifact for GroupA+.

Research/review only. This does not alter target weights or execution guards.
It packages the 2606.30997 "preview before apply" and active-cash concepts into
a concrete daily review record.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal_20260720_estimate.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_HETEROGENEOUS_VOL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "heterogeneous_vol_regime_advisory.json"
DEFAULT_GOLDEN1 = PROJECT_ROOT / "results" / "group_a_release_Golden1_0531.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rebalance_review_20260720.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _weights_from_execution_plan(plan: dict[str, Any]) -> dict[str, float]:
    total = float(plan.get("current_total_assets") or 0.0)
    prices = {str(k): float(v) for k, v in (plan.get("current_prices") or {}).items()}
    holdings = {str(k): int(v) for k, v in (plan.get("current_holdings") or {}).items()}
    if total <= 0:
        return {}
    weights = {ticker: (shares * prices.get(ticker, 0.0)) / total for ticker, shares in holdings.items()}
    weights["cash"] = float(plan.get("current_cash_input") or 0.0) / total
    return weights


def _max_weight_drift(current: dict[str, float], target: dict[str, float]) -> float | None:
    if not current:
        return None
    keys = set(current) | set(target)
    return max(abs(float(target.get(key, 0.0)) - float(current.get(key, 0.0))) for key in keys)


def _golden1_reference_weights(live: dict[str, Any], golden1: dict[str, Any]) -> dict[str, float]:
    # The frozen release has an old operational snapshot, so prefer the current
    # live golden1 estimate when the live execution regime is golden1.
    if str(live.get("execution_regime")) == "golden1" and isinstance(live.get("target_weights"), dict):
        return {str(k): float(v) for k, v in live["target_weights"].items()}
    snapshot = golden1.get("latest_operational_snapshot") or {}
    return {str(k): float(v) for k, v in (snapshot.get("target_weights") or {}).items()}


def build_review(
    *,
    live_signal_path: Path,
    execution_plan_path: Path,
    heterogeneous_vol_path: Path,
    golden1_path: Path,
    rebalance_threshold: float,
) -> dict[str, Any]:
    live_payload = _load(live_signal_path)
    live = _payload_data(live_payload)
    execution_plan = _payload_data(_load(execution_plan_path))
    hetero = _load(heterogeneous_vol_path)
    golden1 = _load(golden1_path)

    target_weights = {str(k): float(v) for k, v in (live.get("target_weights") or {}).items()}
    current_weights_reference = _weights_from_execution_plan(execution_plan)
    max_drift = _max_weight_drift(current_weights_reference, target_weights)

    requested_date = live.get("requested_as_of_date")
    actual_date = live.get("actual_data_date")
    execution_plan_date = execution_plan.get("actual_data_date")
    execution_plan_stale = bool(execution_plan_date and actual_date and execution_plan_date != actual_date)

    execution_allowed = bool(live.get("execution_allowed"))
    hetero_advisory = hetero.get("advisory") or {}
    hetero_blocks_add = bool(hetero_advisory.get("active")) and str(
        hetero_advisory.get("suggested_review")
    ) == "avoid_adding_00631l_until_manual_review"

    blocking_reasons = []
    blocking_reasons.extend(str(item) for item in (live.get("execution_guard_reasons") or []))
    if execution_plan_stale:
        blocking_reasons.append(
            f"execution_plan actual_data_date {execution_plan_date} does not match live actual_data_date {actual_date}"
        )
    if hetero_blocks_add:
        blocking_reasons.append("heterogeneous_vol_regime_advisory recommends avoiding 00631L add until manual review")

    warning_reasons = [str(item) for item in (live.get("execution_warning_reasons") or [])]

    allow_00631l_add = bool(execution_allowed and not hetero_blocks_add)
    auto_rebalance_allowed = bool(execution_allowed and not execution_plan_stale and not hetero_blocks_add)
    manual_review_required = bool((not auto_rebalance_allowed) or blocking_reasons or warning_reasons)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_rebalance_review",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "manual_review_only_no_weight_change",
        "active_allocation_impact": "none",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.30997.pdf",
            "imported_concepts": [
                "active_cash_buffer",
                "allocation_driven_rebalance_threshold",
                "redeployment_aware_turnover_review",
                "objective_conditioned_review",
                "preview_before_apply",
            ],
        },
        "dates": {
            "requested_as_of_date": requested_date,
            "actual_data_date": actual_date,
            "execution_plan_actual_data_date": execution_plan_date,
            "execution_plan_stale_vs_live": execution_plan_stale,
        },
        "strategy": {
            "strategy_id": live.get("strategy_id"),
            "strategy_status": live.get("strategy_status"),
            "execution_regime": live.get("execution_regime"),
            "base_regime": live.get("base_regime"),
            "market_state": live.get("market_state"),
        },
        "objective": {
            "primary": "capital_preservation_with_core_0050_exposure",
            "secondary": "avoid_00631l_auto_add",
            "rationale": "Medium-high risk pullback, stale required source, NCF date mismatch, and high heterogeneous volatility advisory.",
        },
        "weights": {
            "target_weights": target_weights,
            "golden1_reference_weights": _golden1_reference_weights(live, golden1),
            "last_known_current_weights_from_execution_plan": current_weights_reference,
            "current_weights_reliable_for_20260720": False,
            "cash_buffer_policy": "active_risk_buffer",
            "cash_buffer_target": target_weights.get("cash"),
            "cash_buffer_actual_reference": current_weights_reference.get("cash") if current_weights_reference else None,
            "cash_buffer_gap_reference": (
                target_weights.get("cash", 0.0) - current_weights_reference.get("cash", 0.0)
                if current_weights_reference
                else None
            ),
        },
        "rebalance_review": {
            "rebalance_threshold": float(rebalance_threshold),
            "max_weight_drift_reference": max_drift,
            "rebalance_needed_by_drift_reference": bool(max_drift is not None and max_drift >= float(rebalance_threshold)),
            "rebalance_allowed_by_freshness": bool(execution_allowed and not execution_plan_stale),
            "allow_00631l_add": allow_00631l_add,
            "manual_review_required": manual_review_required,
            "auto_rebalance_allowed": auto_rebalance_allowed,
            "preview_before_apply": True,
            "apply_disabled_until_data_fresh_and_user_confirmed": True,
        },
        "risk_and_freshness": {
            "execution_allowed_from_live_signal": execution_allowed,
            "execution_guard_reasons": live.get("execution_guard_reasons") or [],
            "execution_warning_reasons": live.get("execution_warning_reasons") or [],
            "heterogeneous_vol_advisory": {
                "status": hetero.get("status"),
                "level": hetero_advisory.get("level"),
                "suggested_review": hetero_advisory.get("suggested_review"),
                "allow_auto_weight_change": hetero_advisory.get("allow_auto_weight_change"),
                "param_sweep_best": ((hetero.get("evidence") or {}).get("param_sweep_best")),
            },
        },
        "blocking_reasons": blocking_reasons,
        "warning_reasons": warning_reasons,
        "decision": {
            "summary": "Do not auto-rebalance for 2026-07-20. Keep target weights as reference only; require manual review before any execution.",
            "auto_rebalance_allowed": auto_rebalance_allowed,
            "manual_review_required": manual_review_required,
            "allow_00631l_add": allow_00631l_add,
            "target_weight_change_allowed": False,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path) if execution_plan_path.exists() else None,
            "heterogeneous_vol_regime_advisory": str(heterogeneous_vol_path) if heterogeneous_vol_path.exists() else None,
            "golden1_release": str(golden1_path) if golden1_path.exists() else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--heterogeneous-vol", default=str(DEFAULT_HETEROGENEOUS_VOL))
    parser.add_argument("--golden1", default=str(DEFAULT_GOLDEN1))
    parser.add_argument("--rebalance-threshold", type=float, default=0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = _resolve(args.output)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        heterogeneous_vol_path=_resolve(args.heterogeneous_vol),
        golden1_path=_resolve(args.golden1),
        rebalance_threshold=float(args.rebalance_threshold),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Review: {output}")
    print(
        json.dumps(
            {
                "requested_as_of_date": review["dates"]["requested_as_of_date"],
                "actual_data_date": review["dates"]["actual_data_date"],
                "auto_rebalance_allowed": review["decision"]["auto_rebalance_allowed"],
                "manual_review_required": review["decision"]["manual_review_required"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
