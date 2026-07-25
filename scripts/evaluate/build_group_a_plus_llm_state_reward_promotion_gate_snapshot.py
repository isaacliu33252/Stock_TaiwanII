#!/usr/bin/env python3
"""Build the GroupA+ GIFT state-reward promotion gate snapshot.

This consolidates the frozen-interface diagnostics, no-model shadow backtests,
drawdown attribution, risk overlays, and circuit sweeps into one hard gate. It
does not run training, generate target weights, or authorize live changes.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = LATEST / "llm_state_reward_interface_promotion_gate_snapshot.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_promotion_gate_snapshot/history"

DEFAULT_INPUTS = {
    "proposal_comparison": LATEST / "llm_state_reward_interface_proposal_comparison_review.json",
    "frozen_manifest": LATEST / "llm_state_reward_interface_frozen_manifest.json",
    "frozen_panel_review": LATEST / "llm_state_reward_interface_frozen_panel_review.json",
    "walk_forward_audit": LATEST / "llm_state_reward_interface_frozen_panel_walk_forward_audit.json",
    "baseline_shadow": LATEST / "llm_state_reward_interface_frozen_panel_baseline_shadow_backtest.json",
    "baseline_param_sweep": LATEST / "llm_state_reward_interface_frozen_panel_baseline_param_sweep.json",
    "drawdown_attribution": LATEST / "llm_state_reward_interface_baseline_drawdown_attribution.json",
    "risk_control_overlay": LATEST / "llm_state_reward_interface_risk_control_overlay_shadow_backtest.json",
    "cost_aware_micro_tilt_guard": LATEST
    / "llm_state_reward_interface_cost_aware_micro_tilt_guard_shadow_backtest.json",
    "stress_regime_gate": LATEST / "llm_state_reward_interface_stress_regime_gate_shadow_backtest.json",
    "bucket_guard": LATEST / "llm_state_reward_interface_bucket_guard_shadow_backtest.json",
    "relative_drawdown_circuit": LATEST / "llm_state_reward_interface_relative_drawdown_circuit_shadow_backtest.json",
    "relative_drawdown_circuit_sweep": LATEST / "llm_state_reward_interface_relative_drawdown_circuit_param_sweep.json",
    "v3_high_dividend_active_pain_dgr": LATEST / "llm_state_reward_interface_high_dividend_active_pain_dgr_review.json",
    "v3_high_dividend_active_pain_smoke": LATEST / "llm_state_reward_interface_high_dividend_active_pain_offline_smoke.json",
    "v3_high_dividend_active_pain_panel_audit": LATEST / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit.json",
    "v3_high_dividend_active_pain_param_sweep": LATEST / "llm_state_reward_interface_high_dividend_active_pain_param_sweep.json",
}

OPTIONAL_BRANCH_COMPONENTS = {
    "v3_high_dividend_active_pain_dgr",
    "v3_high_dividend_active_pain_smoke",
    "v3_high_dividend_active_pain_panel_audit",
    "v3_high_dividend_active_pain_param_sweep",
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _metric_block(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "proposal_comparison":
        return {
            "best_candidate": _nested(payload, "summary", "best_candidate"),
            "best_objective_alignment": _nested(payload, "summary", "best_objective_alignment"),
            "best_reward_snr": _nested(payload, "summary", "best_reward_snr"),
        }
    if name == "frozen_manifest":
        return {
            "freeze_id": payload.get("freeze_id") or _nested(payload, "manifest", "freeze_id"),
            "proposal_id": payload.get("proposal_id") or _nested(payload, "manifest", "proposal_id"),
            "frozen_manifest_sha256": payload.get("frozen_manifest_sha256"),
        }
    if name == "frozen_panel_review":
        return {
            "rows": _nested(payload, "summary", "rows") or payload.get("rows"),
            "ticker_count": _nested(payload, "summary", "ticker_count") or payload.get("ticker_count"),
            "panel_sha256": _nested(payload, "summary", "panel_sha256") or payload.get("panel_sha256"),
        }
    if name == "walk_forward_audit":
        return {
            "fold_count": _nested(payload, "summary", "fold_count"),
            "warnings": _nested(payload, "summary", "warning_count") or len(payload.get("warning_reasons") or []),
            "duplicate_date_ticker_rows": _nested(payload, "summary", "duplicate_date_ticker_rows"),
        }
    if name == "baseline_shadow":
        return _nested(payload, "summary") or {}
    if name == "baseline_param_sweep":
        has_recommended = _nested(payload, "summary", "has_recommended_candidate")
        if has_recommended is None:
            has_recommended = _nested(payload, "decision", "recommended_baseline_variant_available")
        return {
            "evaluated_count": _nested(payload, "summary", "evaluated_count"),
            "recommended_count": _nested(payload, "summary", "recommended_count"),
            "has_recommended_candidate": has_recommended,
        }
    if name == "drawdown_attribution":
        return {
            "failing_drawdown_folds": _nested(payload, "summary", "failing_drawdown_folds"),
            "worst_fold": _nested(payload, "summary", "worst_fold"),
            "worst_delta_max_drawdown": _nested(payload, "summary", "worst_delta_max_drawdown"),
        }
    if name == "risk_control_overlay":
        return {
            "overlay": _nested(payload, "summary", "overlay"),
            "pass_risk_control_overlay_gate": _nested(payload, "summary", "pass_risk_control_overlay_gate"),
        }
    if name == "cost_aware_micro_tilt_guard":
        return {
            "required_cost_scenarios": _nested(payload, "summary", "required_cost_scenarios"),
            "required_cost_scenarios_passed": _nested(payload, "summary", "required_cost_scenarios_passed"),
            "warning_cost_scenarios": _nested(payload, "summary", "warning_cost_scenarios"),
            "warning_cost_scenarios_passed": _nested(payload, "summary", "warning_cost_scenarios_passed"),
            "micro_tilt_guard_passed": _nested(payload, "summary", "micro_tilt_guard_passed"),
        }
    if name == "stress_regime_gate":
        return {
            "stress_gate": _nested(payload, "summary", "stress_gate"),
            "pass_stress_regime_gate": _nested(payload, "summary", "pass_stress_regime_gate"),
            "mean_stress_gate_rate": _nested(payload, "summary", "mean_stress_gate_rate"),
        }
    if name == "bucket_guard":
        return {
            "bucket_guard": _nested(payload, "summary", "bucket_guard"),
            "pass_bucket_guard_gate": _nested(payload, "summary", "pass_bucket_guard_gate"),
            "mean_bucket_guard_rates": _nested(payload, "summary", "mean_bucket_guard_rates"),
        }
    if name == "relative_drawdown_circuit":
        return {
            "relative_drawdown_circuit": _nested(payload, "summary", "relative_drawdown_circuit"),
            "pass_relative_drawdown_circuit_gate": _nested(payload, "summary", "pass_relative_drawdown_circuit_gate"),
            "mean_circuit_rate": _nested(payload, "summary", "mean_circuit_rate"),
        }
    if name == "relative_drawdown_circuit_sweep":
        return {
            "evaluated_count": _nested(payload, "summary", "evaluated_count"),
            "passed_count": _nested(payload, "summary", "passed_count"),
            "has_recommended_candidate": _nested(payload, "summary", "has_recommended_candidate"),
            "best_by_drawdown_then_return": _nested(payload, "summary", "best_by_drawdown_then_return"),
        }
    if name == "v3_high_dividend_active_pain_dgr":
        return {
            "proposal_id": payload.get("proposal_id"),
            "alignment_grade": _nested(payload, "summary", "alignment_grade"),
            "redesigned_alignment": _nested(
                payload, "summary", "redesigned_reward_alignment_to_future_high_dividend_active_pain"
            ),
            "pass_high_dividend_active_pain_dgr": _nested(payload, "summary", "pass_high_dividend_active_pain_dgr"),
        }
    if name == "v3_high_dividend_active_pain_smoke":
        return {
            "proposal_id": payload.get("proposal_id"),
            "smoke": _nested(payload, "summary", "high_dividend_active_pain_offline_smoke"),
            "event_probe_active_drag_improved": _nested(payload, "summary", "event_probe_active_drag_improved"),
            "pass_high_dividend_active_pain_offline_smoke": _nested(
                payload, "summary", "pass_high_dividend_active_pain_offline_smoke"
            ),
        }
    if name == "v3_high_dividend_active_pain_panel_audit":
        return {
            "row_count": _nested(payload, "summary", "row_count"),
            "fold_count": _nested(payload, "summary", "fold_count"),
            "duplicate_fold_date_ticker_rows": _nested(payload, "summary", "duplicate_fold_date_ticker_rows"),
            "v3_walk_forward_panel_audit_passed": _nested(
                payload, "decision", "v3_walk_forward_panel_audit_passed"
            ),
        }
    if name == "v3_high_dividend_active_pain_param_sweep":
        return {
            "evaluated_count": _nested(payload, "summary", "evaluated_count"),
            "passed_count": _nested(payload, "summary", "passed_count"),
            "robustness_passed": _nested(payload, "summary", "robustness_passed"),
            "recommended_candidate": _nested(payload, "summary", "recommended_candidate"),
        }
    return {}


def _component(name: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    decision = _decision(payload)
    return {
        "path": str(path),
        "exists": bool(payload),
        "status": payload.get("status"),
        "blocking_reasons": payload.get("blocking_reasons") or [],
        "warning_reasons": payload.get("warning_reasons") or [],
        "key_metrics": _metric_block(name, payload),
        "decision": {
            "next_shadow_model_design_allowed": decision.get("next_shadow_model_design_allowed"),
            "model_training_allowed": decision.get("model_training_allowed"),
            "ppo_training_allowed": decision.get("ppo_training_allowed"),
            "promote_to_live": decision.get("promote_to_live"),
            "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
            "allow_00631l_add": decision.get("allow_00631l_add"),
            "allow_00632r_open": decision.get("allow_00632r_open"),
        },
    }


def build_snapshot(
    input_paths: dict[str, Path] | None = None,
    *,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    paths = input_paths or DEFAULT_INPUTS
    payloads = {name: _load(path) for name, path in paths.items()}
    components = {name: _component(name, paths[name], payload) for name, payload in payloads.items()}
    blockers: list[str] = []
    warnings: list[str] = []

    for name, payload in payloads.items():
        if not payload:
            blockers.append(f"missing_{name}")
            continue
        if payload.get("status") == "blocked":
            if name in OPTIONAL_BRANCH_COMPONENTS:
                warnings.append(f"{name}_blocked")
            else:
                blockers.append(f"{name}_blocked")
        decision = _decision(payload)
        if decision.get("model_training_allowed") is True or decision.get("ppo_training_allowed") is True:
            warnings.append(f"{name}_reports_training_allowed_unexpected")
        if decision.get("promote_to_live") is True or decision.get("target_weight_change_allowed") is True:
            warnings.append(f"{name}_reports_live_action_allowed_unexpected")
        if decision.get("allow_00631l_add") is True or decision.get("allow_00632r_open") is True:
            warnings.append(f"{name}_reports_leveraged_or_inverse_action_allowed_unexpected")

    baseline = _nested(payloads.get("baseline_shadow") or {}, "summary") or {}
    baseline_sweep_payload = payloads.get("baseline_param_sweep") or {}
    baseline_sweep_recommended = _nested(baseline_sweep_payload, "summary", "has_recommended_candidate")
    if baseline_sweep_recommended is None:
        baseline_sweep_recommended = _nested(
            baseline_sweep_payload,
            "decision",
            "recommended_baseline_variant_available",
        )
    baseline_sweep_aggregate = (
        _nested(baseline_sweep_payload, "summary", "best_recommended_aggregate")
        if baseline_sweep_recommended is True
        else None
    )
    baseline_gate_metrics = baseline_sweep_aggregate or baseline
    baseline_final = int(baseline.get("positive_final_value_folds", 0) or 0)
    baseline_sharpe = int(baseline.get("positive_sharpe_folds", 0) or 0)
    baseline_drawdown = int(baseline.get("non_worse_drawdown_folds", 0) or 0)
    baseline_gate_final = int(baseline_gate_metrics.get("positive_final_value_folds", 0) or 0)
    baseline_gate_sharpe = int(baseline_gate_metrics.get("positive_sharpe_folds", 0) or 0)
    baseline_gate_drawdown = int(baseline_gate_metrics.get("non_worse_drawdown_folds", 0) or 0)

    v3_dgr_pass = _nested(payloads.get("v3_high_dividend_active_pain_dgr") or {}, "decision", "high_dividend_active_pain_dgr_passed") is True
    v3_smoke = _nested(payloads.get("v3_high_dividend_active_pain_smoke") or {}, "summary", "high_dividend_active_pain_offline_smoke") or {}
    v3_smoke_pass = (
        _nested(payloads.get("v3_high_dividend_active_pain_smoke") or {}, "decision", "high_dividend_active_pain_offline_smoke_passed")
        is True
    )
    v3_panel_audit_pass = (
        _nested(payloads.get("v3_high_dividend_active_pain_panel_audit") or {}, "decision", "v3_walk_forward_panel_audit_passed")
        is True
    )
    v3_param_robustness_pass = (
        _nested(payloads.get("v3_high_dividend_active_pain_param_sweep") or {}, "decision", "v3_active_pain_param_robustness_passed")
        is True
    )
    v3_final = int(v3_smoke.get("positive_final_value_folds", 0) or 0)
    v3_sharpe = int(v3_smoke.get("positive_sharpe_folds", 0) or 0)
    v3_drawdown = int(v3_smoke.get("non_worse_drawdown_folds", 0) or 0)
    v3_gate_pass = bool(
        v3_dgr_pass
        and v3_smoke_pass
        and v3_panel_audit_pass
        and v3_param_robustness_pass
        and v3_final >= min_positive_final_folds
        and v3_sharpe >= min_positive_sharpe_folds
        and v3_drawdown >= min_non_worse_drawdown_folds
    )

    if baseline_gate_final < min_positive_final_folds and not v3_gate_pass:
        blockers.append(f"baseline_positive_final_folds_below_threshold:{baseline_gate_final}<{min_positive_final_folds}")
    if baseline_gate_sharpe < min_positive_sharpe_folds and not v3_gate_pass:
        blockers.append(f"baseline_positive_sharpe_folds_below_threshold:{baseline_gate_sharpe}<{min_positive_sharpe_folds}")
    if baseline_gate_drawdown < min_non_worse_drawdown_folds and not v3_gate_pass:
        blockers.append(
            f"baseline_non_worse_drawdown_folds_below_threshold:{baseline_gate_drawdown}<{min_non_worse_drawdown_folds}"
        )

    overlay_pass = _nested(payloads.get("risk_control_overlay") or {}, "summary", "pass_risk_control_overlay_gate") is True
    micro_tilt_pass = (
        _nested(payloads.get("cost_aware_micro_tilt_guard") or {}, "summary", "micro_tilt_guard_passed") is True
    )
    stress_pass = _nested(payloads.get("stress_regime_gate") or {}, "summary", "pass_stress_regime_gate") is True
    bucket_pass = _nested(payloads.get("bucket_guard") or {}, "summary", "pass_bucket_guard_gate") is True
    circuit_pass = _nested(payloads.get("relative_drawdown_circuit") or {}, "summary", "pass_relative_drawdown_circuit_gate") is True
    circuit_sweep_recommended = (
        _nested(payloads.get("relative_drawdown_circuit_sweep") or {}, "summary", "has_recommended_candidate") is True
    )
    if not any([overlay_pass, micro_tilt_pass, stress_pass, bucket_pass, circuit_pass, circuit_sweep_recommended, v3_gate_pass]):
        blockers.append("no_shadow_risk_control_passed_promotion_gate")

    if baseline_sweep_recommended is not True and not v3_gate_pass:
        blockers.append("baseline_param_sweep_has_no_recommended_candidate")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_promotion_gate_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "hard_promotion_gate_shadow_only_no_live_action",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.08450.pdf",
            "title": "GIFT: LLM-Guided State-Reward Interface for Financial Reinforcement Learning",
            "arxiv": "2606.08450v1",
            "date_in_pdf": "2026-06-07",
        },
        "gate_thresholds": {
            "min_positive_final_folds": min_positive_final_folds,
            "min_positive_sharpe_folds": min_positive_sharpe_folds,
            "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            "requires_at_least_one_shadow_risk_control_gate_pass": True,
            "requires_baseline_param_recommended_candidate": True,
        },
        "component_results": components,
        "summary": {
            "baseline_shadow": {
                "positive_final_value_folds": baseline_final,
                "positive_sharpe_folds": baseline_sharpe,
                "non_worse_drawdown_folds": baseline_drawdown,
            },
            "baseline_gate_metrics": {
                "source": "baseline_param_sweep_best_recommended" if baseline_sweep_aggregate else "baseline_shadow",
                "positive_final_value_folds": baseline_gate_final,
                "positive_sharpe_folds": baseline_gate_sharpe,
                "non_worse_drawdown_folds": baseline_gate_drawdown,
            },
            "risk_control_gate_passes": {
                "risk_control_overlay": overlay_pass,
                "cost_aware_micro_tilt_guard": micro_tilt_pass,
                "stress_regime_gate": stress_pass,
                "bucket_guard": bucket_pass,
                "relative_drawdown_circuit": circuit_pass,
                "relative_drawdown_circuit_sweep_recommended": circuit_sweep_recommended,
                "v3_high_dividend_active_pain": v3_gate_pass,
            },
            "v3_high_dividend_active_pain": {
                "dgr_passed": v3_dgr_pass,
                "offline_smoke_passed": v3_smoke_pass,
                "panel_audit_passed": v3_panel_audit_pass,
                "param_robustness_passed": v3_param_robustness_pass,
                "positive_final_value_folds": v3_final,
                "positive_sharpe_folds": v3_sharpe,
                "non_worse_drawdown_folds": v3_drawdown,
            },
            "baseline_param_sweep_has_recommended_candidate": baseline_sweep_recommended,
            "promotion_gate_passed": False if blockers else True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The original frozen state/reward interface had useful signal but failed the drawdown promotion gate.",
            "The v3 high-dividend active-pain redesign may clear the shadow research gate only after DGR, offline smoke, panel audit, and parameter robustness pass.",
            "Passing this gate permits only additional shadow research; it never permits PPO/model training or live allocation.",
        ],
        "decision": {
            "available_for_manual_offline_review": True,
            "promotion_gate_passed": False if blockers else True,
            "llm_state_reward_interface_research_catalog_allowed": True,
            "next_shadow_model_design_allowed": False if blockers else True,
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
    return history_dir / f"llm_state_reward_interface_promotion_gate_snapshot_{stamp}.json"


def write_snapshot(snapshot: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, snapshot.get("as_of")).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot(as_of=args.as_of)
    write_snapshot(snapshot, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward promotion gate snapshot: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": snapshot["status"],
                "promotion_gate_passed": snapshot["decision"]["promotion_gate_passed"],
                "next_shadow_model_design_allowed": snapshot["decision"]["next_shadow_model_design_allowed"],
                "blocking_reasons": snapshot["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
