#!/usr/bin/env python3
"""Build a research-only adversarial market integrity review for GroupA+.

This imports governance ideas from arXiv 2510.18990, not an attack model:
forecast-model outputs should be treated as potentially perturbable inputs and
must be cross-checked before any live target-weight change.
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
DEFAULT_CRASH_RISK = PROJECT_ROOT / "report/group_a_plus/latest/crash_risk_alert.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/adversarial_market_integrity_review_20260720.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/adversarial_market_integrity/history"


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
    crash_risk_path: Path,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    rebalance = _load(rebalance_review_path)
    option_coverage = _load(option_coverage_path)
    crash = _load(crash_risk_path)

    signal_alignment = live.get("signal_alignment") or {}
    market_state = live.get("market_state") or {}
    trough_inputs = _nested(live, ["trough_nowcast", "inputs"], {})
    multisource = trough_inputs.get("multisource") if isinstance(trough_inputs, dict) else {}
    multisource = multisource if isinstance(multisource, dict) else {}
    execution_allowed = bool(live.get("execution_allowed"))
    rebalance_decision = rebalance.get("decision") or {}
    option_gate_passed = bool(_nested(option_coverage, ["decision", "option_state_gate_passed"], False))
    crash_alert_active = bool(crash.get("alert_active"))

    blockers: list[str] = []
    warnings: list[str] = []
    if not execution_allowed:
        blockers.append("live_signal_execution_not_allowed")
    if not option_gate_passed:
        blockers.append("option_state_gate_not_passed")
    if rebalance_decision.get("target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")
    if crash_alert_active:
        blockers.append("crash_risk_alert_active")
    if signal_alignment.get("alignment") == "wide_divergence":
        warnings.append("signal_alignment_wide_divergence")
    if market_state.get("risk_level") in {"medium_high", "high"}:
        warnings.append(f"market_risk_level_{market_state.get('risk_level')}")

    missing_model_state = [
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
    if missing_model_state:
        blockers.append("adversarial_robustness_state_incomplete")
    as_of = live.get("requested_as_of_date") or live.get("actual_data_date") or "unknown"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adversarial_market_integrity_review",
        "status": "blocked" if blockers else "available_for_manual_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_governance_only_no_weight_change",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2510.18990.pdf",
            "title": "The Black Tuesday Attack: How to Crash the Stock Market with Adversarial Examples to Financial Forecasting Models",
            "imported_concepts": [
                "forecast_models_are_attack_surface",
                "small_sparse_market_perturbations_can_mislead_models",
                "transferability_across_models_trained_on_similar_public_data",
                "defense_requires_cross_checks_not_single_model_auto_execution",
                "detection_and_smoothing_are_imperfect_but_useful_as_governance_checks",
            ],
            "not_imported": [
                "attack_construction",
                "surrogate_model_attack",
                "adversarial_training_for_live_trading",
                "automatic_target_weight_change",
            ],
        },
        "group_a_plus_mapping": {
            "strategy_id": live.get("strategy_id"),
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
            "execution_allowed": execution_allowed,
            "execution_guard_reasons": live.get("execution_guard_reasons") or [],
            "target_weights": live.get("target_weights") or {},
            "market_state": market_state,
            "signal_alignment": signal_alignment,
            "missing_adversarial_robustness_state": missing_model_state,
        },
        "defense_checklist": {
            "single_model_auto_execution_allowed": False,
            "requires_fresh_source_data": True,
            "requires_option_state_gate": True,
            "requires_signal_cross_check": True,
            "requires_crash_risk_check": True,
            "requires_manual_review_for_weight_change": True,
            "suggested_future_shadow_tests": [
                "sparse_input_perturbation_sensitivity_on_ncf_panel",
                "feature_smoothing_vs_raw_prediction_stability",
                "cross_model_direction_consensus_under_small_ohlcv_perturbations",
            ],
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import as adversarial-robustness governance only. Current GroupA+ live signal is already "
                "execution-blocked and option/model-state coverage is incomplete, so no target-weight change "
                "or 00631L add should be unlocked."
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
            "crash_risk": str(crash_risk_path),
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
    parser.add_argument("--crash-risk", default=str(DEFAULT_CRASH_RISK))
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
        crash_risk_path=_resolve(args.crash_risk),
    )
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"Adversarial market integrity review: {output}")
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
