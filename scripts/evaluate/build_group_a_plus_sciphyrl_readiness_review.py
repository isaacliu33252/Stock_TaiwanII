#!/usr/bin/env python3
"""Build a research-only SciPhyRL readiness review for GroupA+.

This imports governance ideas from arXiv 2607.15195, not the RL/PINN optimizer:
target-holding control, explicit cumulative costs, turnover/capacity checks,
and signal-quality requirements before any optimizer can be considered.
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
DEFAULT_OPTION_COVERAGE = PROJECT_ROOT / "report/group_a_plus/latest/option_state_coverage_review.json"
DEFAULT_ADVERSARIAL_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/adversarial_market_integrity_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sciphyrl_readiness_review_20260720.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/sciphyrl_readiness/history"


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


def _nested(payload: dict[str, Any], keys: list[str], default: Any = None) -> Any:
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
    option_coverage_path: Path,
    adversarial_review_path: Path,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    rebalance = _load(rebalance_review_path)
    option_coverage = _load(option_coverage_path)
    adversarial = _load(adversarial_review_path)

    execution_allowed = bool(live.get("execution_allowed"))
    rebalance_decision = rebalance.get("decision") or {}
    option_gate_passed = bool(_nested(option_coverage, ["decision", "option_state_gate_passed"], False))
    adversarial_blocked = adversarial.get("status") == "blocked"
    signal_alignment = live.get("signal_alignment") or {}
    leverage_suitability = signal_alignment.get("leverage_suitability") or {}
    latest_features = live.get("latest_features") or {}

    blockers: list[str] = []
    warnings: list[str] = []
    if not execution_allowed:
        blockers.append("live_signal_execution_not_allowed")
    if rebalance_decision.get("target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")
    if not option_gate_passed:
        blockers.append("option_state_gate_not_passed")
    if adversarial_blocked:
        blockers.append("adversarial_market_integrity_not_passed")
    if leverage_suitability.get("action") in {"0050_only", "avoid_00631l"}:
        blockers.append("leverage_suitability_disallows_00631l_add")
    if latest_features.get("total_risk_score", 0) >= 8:
        warnings.append("high_total_risk_score_for_optimizer")
    if signal_alignment.get("alignment") == "wide_divergence":
        warnings.append("signal_alignment_wide_divergence")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_sciphyrl_readiness_review",
        "status": "blocked" if blockers else "available_for_shadow_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_readiness_only_no_weight_change",
        "as_of": live.get("requested_as_of_date") or live.get("actual_data_date"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "imported_concepts": [
                "target_holding_control_instead_of_slow_trading_rate",
                "explicit_cumulative_cost_state",
                "quadratic_transaction_cost_and_price_impact_awareness",
                "turnover_and_capacity_as_first_class_constraints",
                "offline_single_sweep_shadow_training_governance",
                "signal_quality_must_be_measured_before_optimizer_claims",
            ],
            "not_imported": [
                "PINN_HJB_optimizer",
                "engineered_oracle_signal_results",
                "Gibbs_policy_live_execution",
                "automatic_target_weight_change",
            ],
        },
        "paper_limitations_for_group_a_plus": {
            "uses_engineered_oracle_signal": True,
            "uses_us_etf_universe_not_taiwan_group_a_plus": True,
            "uses_illustrative_uncalibrated_control_parameters": True,
            "overlapping_test_windows_reduce_statistical_independence": True,
            "reported_returns_are_mechanism_demo_not_track_record": True,
        },
        "group_a_plus_mapping": {
            "strategy_id": live.get("strategy_id"),
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
            "execution_allowed": execution_allowed,
            "target_weights": live.get("target_weights") or {},
            "latest_features": latest_features,
            "signal_alignment": {
                "alignment": signal_alignment.get("alignment"),
                "dominant_direction": signal_alignment.get("dominant_direction"),
                "leverage_suitability_action": leverage_suitability.get("action"),
            },
            "rebalance_decision": {
                "auto_rebalance_allowed": rebalance_decision.get("auto_rebalance_allowed"),
                "target_weight_change_allowed": rebalance_decision.get("target_weight_change_allowed"),
                "allow_00631l_add": rebalance_decision.get("allow_00631l_add"),
            },
            "option_state_gate_passed": option_gate_passed,
            "adversarial_market_integrity_status": adversarial.get("status"),
        },
        "readiness_checklist": {
            "real_signal_quality_oos_required": True,
            "turnover_cap_required": True,
            "quadratic_cost_or_slippage_calibration_required": True,
            "capacity_and_notional_constraint_required": True,
            "stress_window_validation_required": True,
            "manual_approval_required_before_live": True,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import target-holding and explicit-cost governance only. The SciPhyRL optimizer and "
                "reported Sharpe ratios rely on an engineered oracle signal and uncalibrated illustrative "
                "parameters, while current GroupA+ governance gates remain blocked."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "rebalance_review": str(rebalance_review_path),
            "option_coverage": str(option_coverage_path),
            "adversarial_review": str(adversarial_review_path),
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    stamp = str(as_of).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(
    review: dict[str, Any],
    *,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review["as_of"])).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--rebalance-review", default=str(DEFAULT_REBALANCE_REVIEW))
    parser.add_argument("--option-coverage", default=str(DEFAULT_OPTION_COVERAGE))
    parser.add_argument("--adversarial-review", default=str(DEFAULT_ADVERSARIAL_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        rebalance_review_path=_resolve(args.rebalance_review),
        option_coverage_path=_resolve(args.option_coverage),
        adversarial_review_path=_resolve(args.adversarial_review),
    )
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"SciPhyRL readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review['as_of'])}")
    print(
        json.dumps(
            {
                "status": review["status"],
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
