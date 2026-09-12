"""Cross-paper convergence review for GroupA+ research imports.

This module ranks paper-derived candidate uses by evidence, data availability,
implementation readiness, and live-safety blockers. It is review-only and must
not change targets, orders, or strategy state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


WEIGHTS = {
    "evidence_strength": 0.30,
    "data_fit": 0.20,
    "implementation_readiness": 0.20,
    "actionability": 0.15,
    "live_safety": 0.15,
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _score(fields: dict[str, float]) -> float:
    return round(sum(fields[key] * WEIGHTS[key] for key in WEIGHTS), 4)


def _decision(score: float, blockers: list[str], *, signed_blocked: bool = False) -> str:
    if signed_blocked:
        return "best_candidate_but_signed_review_blocked"
    if score >= 0.75 and not blockers:
        return "candidate_ready_for_guarded_monitoring"
    if score >= 0.55:
        return "research_candidate_needs_validation"
    return "review_context_only"


def _defensive_cash_floor_candidate(
    *,
    signed_review: dict[str, Any] | None,
    signed_approval_validation: dict[str, Any] | None,
    guarded_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    review = signed_review or {}
    decision = review.get("decision") if isinstance(review.get("decision"), dict) else {}
    validation_decision = (
        signed_approval_validation.get("decision")
        if isinstance(signed_approval_validation, dict) and isinstance(signed_approval_validation.get("decision"), dict)
        else {}
    )
    manual_signature_valid = bool(validation_decision.get("manual_signature_valid") or decision.get("manual_signature_valid"))
    signed_ready = bool(review.get("signed_review_ready") or decision.get("signed_review_ready"))
    guarded_exists = isinstance(guarded_candidate, dict) and bool(guarded_candidate)
    blockers: list[str] = []
    if not signed_ready:
        blockers.append("signed_review_package_not_ready")
    if not manual_signature_valid:
        blockers.append("manual_signature_not_valid")
    if not guarded_exists:
        blockers.append("disabled_guarded_candidate_artifact_missing")

    fields = {
        "evidence_strength": 0.72 if signed_ready else 0.58,
        "data_fit": 0.66,
        "implementation_readiness": 0.88 if guarded_exists else 0.68,
        "actionability": 0.78,
        "live_safety": 0.90,
    }
    total = _score(fields)
    return {
        "candidate_id": "defensive_cash_floor_high_risk_state",
        "theme": "adaptive_defensive_cash_floor",
        "supporting_papers": ["2605.24345", "2606.26625", "2511.12476", "2605.12462", "2008_stress_tuning"],
        "proposed_use": "raise_cash_floor_in_group_a_plus_defensive_high_risk_state",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers, signed_blocked=not manual_signature_valid),
        "evidence": {
            "signed_review_ready": signed_ready,
            "manual_signature_valid": manual_signature_valid,
            "approval_validation_status": (
                signed_approval_validation.get("status") if isinstance(signed_approval_validation, dict) else "missing"
            ),
        },
        "why_this_is_closest": [
            "acts_on_cash_floor_instead_of_trying_to_predict_every_00631l_turn",
            "has_existing_sweep_validation_ablation_and_signed_review_package",
            "does_not_add_00631l_or_open_00632r",
        ],
        "next_validation": [
            "manual_signature_required_before_any_guarded_candidate",
            "extend_crisis_window_validation",
            "monitor_first_10_trigger_days_with_rollback_thresholds",
        ],
    }


def _letf_liquidity_candidate(
    *,
    liquidity_feedback: dict[str, Any] | None,
    tracking_review: dict[str, Any] | None,
    market_impact: dict[str, Any] | None,
) -> dict[str, Any]:
    feedback = liquidity_feedback or {}
    summary = feedback.get("summary") if isinstance(feedback.get("summary"), dict) else {}
    coverage = feedback.get("input_coverage") if isinstance(feedback.get("input_coverage"), dict) else {}
    ready = bool(summary.get("ready_for_manual_review"))
    trigger_count = int(_as_float(coverage.get("trigger_count"), 0.0))
    tracking_status = str((tracking_review or {}).get("status") or "missing")
    impact_status = str((market_impact or {}).get("status") or "missing")

    blockers = ["review_only_no_weight_change"]
    if not ready:
        blockers.append("liquidity_feedback_needs_more_trigger_history")
    if tracking_status != "ok":
        blockers.append(f"tracking_error_review_{tracking_status}")
    if impact_status != "ok":
        blockers.append(f"market_impact_review_{impact_status}")

    fields = {
        "evidence_strength": 0.63 if ready and trigger_count >= 300 else 0.48,
        "data_fit": 0.45,
        "implementation_readiness": 0.72,
        "actionability": 0.58,
        "live_safety": 0.84,
    }
    total = _score(fields)
    return {
        "candidate_id": "letf_large_trade_staging_review",
        "theme": "letf_liquidity_tracking_market_impact",
        "supporting_papers": ["2603.05862", "1610.09404", "2004.01917", "2603.29086", "2504.20116"],
        "proposed_use": "warn_and_stage_large_00631l_or_00632r_trades_when_liquidity_feedback_stress_is_present",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "liquidity_trigger_count": trigger_count,
            "liquidity_ready_for_manual_review": ready,
            "tracking_review_status": tracking_status,
            "market_impact_status": impact_status,
        },
        "next_validation": [
            "replace_daily_liquidity_proxy_with_quote_or_order_book_data_if_available",
            "separate_00631l_add_staging_from_00632r_hedge_staging",
            "validate_trade_outcomes_after_large_target_delta_days",
        ],
    }


def _moira_governance_candidate(
    *,
    moira_validation: dict[str, Any] | None,
    moira_backtest: dict[str, Any] | None,
    event_quality: dict[str, Any] | None,
) -> dict[str, Any]:
    validation = moira_validation or {}
    backtest = moira_backtest or {}
    event = event_quality or {}
    validation_status = str(validation.get("status") or validation.get("summary", {}).get("recommendation") or "available")
    strict_trigger_count = int(
        _as_float(
            backtest.get("strict_actionable_trigger_count")
            or backtest.get("input_coverage", {}).get("strict_actionable_trigger_count")
            or backtest.get("input_coverage", {}).get("trigger_count"),
            0.0,
        )
    )
    event_status = str(event.get("status") or "missing")
    blockers = ["policy_critic_review_only", "llm_cannot_change_target_weights"]
    if strict_trigger_count < 20:
        blockers.append("strict_trigger_count_below_promotion_threshold")
    if event_status not in {"ok", "pass", "available"}:
        blockers.append(f"event_quality_{event_status}")

    fields = {
        "evidence_strength": 0.42 if strict_trigger_count < 20 else 0.62,
        "data_fit": 0.70,
        "implementation_readiness": 0.78,
        "actionability": 0.44,
        "live_safety": 0.92,
    }
    total = _score(fields)
    return {
        "candidate_id": "moira_hierarchical_review_and_policy_critic",
        "theme": "llm_rl_governance_attribution",
        "supporting_papers": ["2605.01954", "2606.08450", "2512.10913", "2605.12653"],
        "proposed_use": "daily_forecast_miss_attribution_and_research_only_rule_proposals",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "validation_status": validation_status,
            "strict_trigger_count": strict_trigger_count,
            "event_quality_status": event_status,
        },
        "next_validation": [
            "collect_more_signal_and_execution_plan_replay_pairs",
            "promote_only_proposals_that_pass_trigger_count_and_signed_review",
            "keep_immutable_contract_forbidding_weights_orders_and_code_changes",
        ],
    }


def _tail_cvar_governance_candidate(
    *,
    cvar_review: dict[str, Any] | None,
    tail_review: dict[str, Any] | None,
    cvar_cost_window_split: dict[str, Any] | None,
) -> dict[str, Any]:
    cvar_status = str((cvar_review or {}).get("status") or "missing")
    tail_status = str((tail_review or {}).get("status") or "missing")
    window_status = str((cvar_cost_window_split or {}).get("status") or "missing")
    window_summary = (cvar_cost_window_split or {}).get("summary") or {}
    blockers = ["optimizer_not_promoted"]
    if cvar_status != "ok":
        blockers.append(f"dynamic_cvar_tail_cost_{cvar_status}")
    if tail_status != "ok":
        blockers.append(f"asian_etf_tail_analytics_{tail_status}")
    if window_summary.get("tail_cost_window_split_passed") is not True:
        blockers.append(f"cvar_cost_window_split_2606_26625_{window_status}")

    fields = {
        "evidence_strength": 0.50,
        "data_fit": 0.62,
        "implementation_readiness": 0.70,
        "actionability": 0.40,
        "live_safety": 0.86,
    }
    total = _score(fields)
    return {
        "candidate_id": "tail_risk_governance_not_optimizer",
        "theme": "cvar_tail_cost_readiness",
        "supporting_papers": ["2606.26625", "2511.12476", "2606.30037"],
        "proposed_use": "keep_tail_cost_and_density_head_checks_as_promotion_blockers",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "dynamic_cvar_tail_cost_status": cvar_status,
            "asian_etf_tail_analytics_status": tail_status,
            "cvar_cost_window_split_2606_26625_status": window_status,
            "cvar_cost_window_split_2606_26625_passed": window_summary.get("tail_cost_window_split_passed"),
            "cvar_cost_window_split_2606_26625_latest_loses_to_no_00631l_windows": window_summary.get(
                "latest_loses_to_no_00631l_windows"
            ),
            "cvar_cost_window_split_2606_26625_latest_loses_to_no_letf_windows": window_summary.get(
                "latest_loses_to_no_letf_windows"
            ),
        },
        "next_validation": [
            "do_not_use_return_seeking_optimizer_until_tail_and_cost_reviews_pass",
            "compare_against_defensive_cash_floor_candidate",
        ],
    }


def _current_policy_re_evaluation_candidate(
    *,
    re_evaluation_gate: dict[str, Any] | None,
) -> dict[str, Any]:
    gate = re_evaluation_gate or {}
    decision = gate.get("decision") if isinstance(gate.get("decision"), dict) else {}
    evidence = gate.get("evidence") if isinstance(gate.get("evidence"), dict) else {}
    checks = gate.get("checks") if isinstance(gate.get("checks"), dict) else {}
    blockers = ["research_only_no_weight_change"]
    blockers.extend(str(item) for item in decision.get("blockers", []) if item)
    promotion_allowed = bool(decision.get("promotion_allowed"))
    all_core_checks_pass = bool(checks) and all(bool(value) for value in checks.values())

    fields = {
        "evidence_strength": 0.34 if not promotion_allowed else 0.64,
        "data_fit": 0.52 if not promotion_allowed else 0.58,
        "implementation_readiness": 0.82 if gate else 0.35,
        "actionability": 0.24 if not promotion_allowed else 0.52,
        "live_safety": 0.94,
    }
    total = _score(fields)
    return {
        "candidate_id": "current_policy_re_evaluation_gate_2608_17808",
        "theme": "self_consistent_adjoint_policy_iteration_transfer",
        "supporting_papers": ["2608.17808"],
        "proposed_use": "keep_current_policy_re_evaluation_as_daily_shadow_promotion_gate",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "gate_decision": decision.get("decision", "missing"),
            "promotion_allowed": promotion_allowed,
            "all_core_checks_pass": all_core_checks_pass,
            "two_pass_l1_delta_second_minus_first": evidence.get("two_pass_l1_delta_second_minus_first"),
            "active_set_verdict": evidence.get("active_set_verdict"),
            "matched_budget_verdict": evidence.get("matched_budget_verdict"),
            "error_decomposition_verdict": evidence.get("error_decomposition_verdict"),
            "tail_bank_decision": (evidence.get("tail_bank") or {}).get("decision")
            if isinstance(evidence.get("tail_bank"), dict)
            else None,
        },
        "next_validation": [
            "keep_collecting_daily_gate_rows_without_changing_weights",
            "require_tail_bank_promotion_allowed_before_manual_review",
            "require_error_certificate_and_stability_tuned_gate_to_pass_together",
        ],
    }


def _auxiliary_task_discovery_candidate(
    *,
    readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    report = readiness or {}
    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    panels = report.get("panels") if isinstance(report.get("panels"), list) else []
    promotion_allowed = bool(decision.get("promotion_allowed"))
    standalone_passed = bool(checks.get("aux_head_standalone_quality_passed"))
    available = bool(checks.get("existing_aux_heads_available"))
    blockers = ["research_only_no_weight_change"]
    blockers.extend(str(item) for item in decision.get("blockers", []) if item)

    fields = {
        "evidence_strength": 0.52 if standalone_passed else 0.36,
        "data_fit": 0.66 if available else 0.42,
        "implementation_readiness": 0.74 if report else 0.30,
        "actionability": 0.34 if not promotion_allowed else 0.58,
        "live_safety": 0.92,
    }
    total = _score(fields)
    return {
        "candidate_id": "auxiliary_task_discovery_readiness_2608_15841",
        "theme": "self_supervised_auxiliary_task_discovery_for_ncf_heads",
        "supporting_papers": ["2608.15841"],
        "proposed_use": "audit_existing_ncf_tail_gain_drawdown_heads_before_any_quest_trader_style_training",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "readiness_decision": decision.get("decision", "missing"),
            "promotion_allowed": promotion_allowed,
            "existing_aux_heads_available": available,
            "aux_head_standalone_quality_passed": standalone_passed,
            "live_feature_freshness_ok": checks.get("live_feature_freshness_ok"),
            "panel_count": len(panels),
            "panel_ranges": {
                str(panel.get("ticker")): {
                    "rows": panel.get("rows"),
                    "date_start": panel.get("date_start"),
                    "date_end": panel.get("date_end"),
                }
                for panel in panels
                if isinstance(panel, dict)
            },
        },
        "next_validation": [
            "validate_auxiliary_heads_by_downstream_policy_lift_not_auc_only",
            "run_purged_walk_forward_policy_impact_test",
            "compare_turnover_and_cost_before_any_latest_strategy_change",
        ],
    }


def _stock_bond_gold_complementarity_candidate(
    *,
    adoption_matrix: dict[str, Any] | None,
    promotion_gate: dict[str, Any] | None,
    instrument_review: dict[str, Any] | None,
) -> dict[str, Any]:
    adoption = adoption_matrix or {}
    gate = promotion_gate or {}
    instrument = instrument_review or {}
    adoption_decision = adoption.get("decision") if isinstance(adoption.get("decision"), dict) else {}
    gate_decision = gate.get("decision") if isinstance(gate.get("decision"), dict) else {}
    instrument_decision = instrument.get("decision") if isinstance(instrument.get("decision"), dict) else {}
    candidates = adoption.get("candidates") if isinstance(adoption.get("candidates"), list) else []
    complementarity = next(
        (
            row
            for row in candidates
            if isinstance(row, dict) and row.get("candidate") == "stock_bond_gold_complementarity_sleeve"
        ),
        {},
    )
    bond_only = next(
        (row for row in candidates if isinstance(row, dict) and row.get("candidate") == "bond_only_complementarity_sleeve"),
        {},
    )
    comp_evidence = complementarity.get("evidence") if isinstance(complementarity.get("evidence"), dict) else {}
    top_combo = comp_evidence.get("top_combo") if isinstance(comp_evidence.get("top_combo"), dict) else {}
    robust_count = int(_as_float(comp_evidence.get("robust_combo_count"), 0.0))
    any_ready = bool(gate_decision.get("any_ready_for_live_review"))
    stock_bond_gold_ready = bool(gate_decision.get("stock_bond_gold_ready_for_live_review"))
    bond_only_ready = bool(gate_decision.get("bond_only_ready_for_live_review"))
    instrument_live_ready = bool(instrument_decision.get("instrument_ready_for_live_core"))
    blockers = ["forward_shadow_only_no_weight_change"]
    if not adoption:
        blockers.append("adoption_matrix_missing")
    if not gate:
        blockers.append("promotion_gate_missing")
    if not any_ready:
        blockers.append("promotion_gate_not_ready")
    if not instrument_live_ready:
        blockers.append("00635u_not_live_instrument_ready")

    fields = {
        "evidence_strength": 0.68 if robust_count >= 10 else 0.48,
        "data_fit": 0.58 if instrument_live_ready else 0.50,
        "implementation_readiness": 0.82 if adoption and gate else 0.45,
        "actionability": 0.30 if not any_ready else 0.56,
        "live_safety": 0.94,
    }
    total = _score(fields)
    return {
        "candidate_id": "stock_bond_gold_complementarity_2609_07946",
        "theme": "dynamic_stock_bond_gold_complementarity",
        "supporting_papers": ["2609.07946"],
        "proposed_use": "continue_forward_shadow_for_00631l_to_bond_or_gold_complementarity_sleeves",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "adopt_into_latest_strategy_now": adoption_decision.get("adopt_into_latest_strategy_now"),
            "promotion_gate_ready": adoption_decision.get("promotion_gate_ready"),
            "stock_bond_gold_ready_for_live_review": stock_bond_gold_ready,
            "bond_only_ready_for_live_review": bond_only_ready,
            "00635u_instrument_ready_for_live_core": instrument_live_ready,
            "robust_combo_count": robust_count,
            "top_combo_universe": top_combo.get("universe"),
            "top_combo_avg_delta_total_return": top_combo.get("avg_delta_total_return"),
            "top_combo_avg_delta_sharpe": top_combo.get("avg_delta_sharpe"),
            "bond_only_verdict": bond_only.get("verdict"),
        },
        "next_validation": [
            "collect_at_least_20_forward_observations_and_3_triggered_days",
            "require_realized_trigger_outcomes_to_pass_promotion_gate",
            "keep_00635u_out_of_live_until_instrument_and_monitoring_review_is_explicitly_approved",
        ],
    }


def _nystrom_complementarity_candidate(
    *,
    adoption_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    adoption = adoption_matrix or {}
    decision = adoption.get("decision") if isinstance(adoption.get("decision"), dict) else {}
    forward_gate = adoption.get("forward_evidence_gate") if isinstance(adoption.get("forward_evidence_gate"), dict) else {}
    candidates = adoption.get("candidates") if isinstance(adoption.get("candidates"), list) else []
    complementarity = next(
        (
            row
            for row in candidates
            if isinstance(row, dict) and row.get("candidate") == "cross_asset_complementarity_score"
        ),
        {},
    )
    mom5 = next(
        (row for row in candidates if isinstance(row, dict) and row.get("candidate") == "mom5_gated_bond_sleeve"),
        {},
    )
    advisory_allowed = bool(decision.get("advisory_import_allowed"))
    live_weight_change_allowed = bool(decision.get("live_weight_change_allowed"))
    forward_passed = bool(forward_gate.get("passed"))
    triggered_count = int(_as_float(forward_gate.get("triggered_count"), 0.0))
    realized_count = int(_as_float(forward_gate.get("realized_count"), 0.0))

    blockers = ["forward_shadow_only_no_weight_change"]
    if not adoption:
        blockers.append("adoption_matrix_missing")
    if not forward_passed:
        blockers.append("forward_evidence_gate_not_passed")
    if triggered_count < 5:
        blockers.append("triggered_forward_samples_below_5")
    if realized_count < 5:
        blockers.append("realized_forward_samples_below_5")
    if live_weight_change_allowed:
        blockers.append("unexpected_live_weight_permission_in_adoption_matrix")

    fields = {
        "evidence_strength": 0.60 if advisory_allowed else 0.42,
        "data_fit": 0.72,
        "implementation_readiness": 0.84 if adoption else 0.40,
        "actionability": 0.42 if advisory_allowed else 0.22,
        "live_safety": 0.96,
    }
    total = _score(fields)
    return {
        "candidate_id": "nystrom_attention_complementarity_2609_08106",
        "theme": "cross_asset_low_rank_complementarity_diagnostic",
        "supporting_papers": ["2609.08106"],
        "proposed_use": "import_cross_asset_complementarity_score_as_advisory_and_continue_mom5_gated_bond_forward_shadow",
        "scores": fields | {"total": total},
        "blockers": blockers,
        "decision": _decision(total, blockers),
        "evidence": {
            "adopt_into_latest_strategy_now": decision.get("adopt_into_latest_strategy_now"),
            "advisory_import_allowed": advisory_allowed,
            "live_weight_change_allowed": live_weight_change_allowed,
            "forward_gate_passed": forward_passed,
            "forward_sample_count": forward_gate.get("sample_count"),
            "triggered_forward_samples": triggered_count,
            "realized_forward_samples": realized_count,
            "complementarity_verdict": complementarity.get("verdict"),
            "mom5_sleeve_verdict": mom5.get("verdict"),
        },
        "next_validation": [
            "keep_daily_forward_shadow_logging_until_forward_gate_passes",
            "use_complementarity_score_in_advisory_reporting_only",
            "do_not_import_graph_topk_sparse_masks_or_nystrom_replacement_for_the_current_small_live_sleeve",
        ],
    }


def build_paper_convergence_review(
    *,
    as_of: str,
    signed_review: dict[str, Any] | None = None,
    signed_approval_validation: dict[str, Any] | None = None,
    guarded_candidate: dict[str, Any] | None = None,
    liquidity_feedback: dict[str, Any] | None = None,
    tracking_review: dict[str, Any] | None = None,
    market_impact: dict[str, Any] | None = None,
    moira_validation: dict[str, Any] | None = None,
    moira_backtest: dict[str, Any] | None = None,
    event_quality: dict[str, Any] | None = None,
    cvar_review: dict[str, Any] | None = None,
    cvar_cost_window_split: dict[str, Any] | None = None,
    tail_review: dict[str, Any] | None = None,
    re_evaluation_gate: dict[str, Any] | None = None,
    auxiliary_task_readiness: dict[str, Any] | None = None,
    adoption_2609_07946: dict[str, Any] | None = None,
    promotion_gate_2609_07946: dict[str, Any] | None = None,
    instrument_review_00635u: dict[str, Any] | None = None,
    adoption_2609_08106: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = [
        _defensive_cash_floor_candidate(
            signed_review=signed_review,
            signed_approval_validation=signed_approval_validation,
            guarded_candidate=guarded_candidate,
        ),
        _letf_liquidity_candidate(
            liquidity_feedback=liquidity_feedback,
            tracking_review=tracking_review,
            market_impact=market_impact,
        ),
        _moira_governance_candidate(
            moira_validation=moira_validation,
            moira_backtest=moira_backtest,
            event_quality=event_quality,
        ),
        _tail_cvar_governance_candidate(
            cvar_review=cvar_review,
            tail_review=tail_review,
            cvar_cost_window_split=cvar_cost_window_split,
        ),
        _current_policy_re_evaluation_candidate(re_evaluation_gate=re_evaluation_gate),
        _auxiliary_task_discovery_candidate(readiness=auxiliary_task_readiness),
        _stock_bond_gold_complementarity_candidate(
            adoption_matrix=adoption_2609_07946,
            promotion_gate=promotion_gate_2609_07946,
            instrument_review=instrument_review_00635u,
        ),
        _nystrom_complementarity_candidate(adoption_matrix=adoption_2609_08106),
    ]
    candidates = sorted(candidates, key=lambda item: item["scores"]["total"], reverse=True)
    top = candidates[0]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_paper_convergence_review",
        "policy": "review_only_no_target_weight_change",
        "as_of": as_of,
        "ranking_method": {
            "weights": WEIGHTS,
            "interpretation": "rank_paper_imports_by_actionable_review_value_not_live_alpha",
        },
        "top_candidate_id": top["candidate_id"],
        "top_candidate_decision": top["decision"],
        "candidates": candidates,
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "promote_to_live": False,
            "requires_signed_approval_before_any_candidate": True,
        },
        "summary": {
            "correct_use_found": True,
            "correct_use": "paper_imports_are_most_useful_as_ranked_review_guards_with_defensive_cash_floor_as_current_best_candidate",
            "why_not_live": [
                "manual_signature_missing_or_invalid",
                "sample_size_and_proxy_data_limitations",
                "execution_and_market_impact_reviews_still_block_some_actions",
                "llm_rl_imports_are_governance_not_order_generation",
            ],
        },
    }


def load_inputs_and_build(
    *,
    as_of: str,
    signed_review_path: Path | None = None,
    signed_approval_validation_path: Path | None = None,
    guarded_candidate_path: Path | None = None,
    liquidity_feedback_path: Path | None = None,
    tracking_review_path: Path | None = None,
    market_impact_path: Path | None = None,
    moira_validation_path: Path | None = None,
    moira_backtest_path: Path | None = None,
    event_quality_path: Path | None = None,
    cvar_review_path: Path | None = None,
    cvar_cost_window_split_path: Path | None = None,
    tail_review_path: Path | None = None,
    re_evaluation_gate_path: Path | None = None,
    auxiliary_task_readiness_path: Path | None = None,
    adoption_2609_07946_path: Path | None = None,
    promotion_gate_2609_07946_path: Path | None = None,
    instrument_review_00635u_path: Path | None = None,
    adoption_2609_08106_path: Path | None = None,
) -> dict[str, Any]:
    return build_paper_convergence_review(
        as_of=as_of,
        signed_review=_load_optional_json(signed_review_path),
        signed_approval_validation=_load_optional_json(signed_approval_validation_path),
        guarded_candidate=_load_optional_json(guarded_candidate_path),
        liquidity_feedback=_load_optional_json(liquidity_feedback_path),
        tracking_review=_load_optional_json(tracking_review_path),
        market_impact=_load_optional_json(market_impact_path),
        moira_validation=_load_optional_json(moira_validation_path),
        moira_backtest=_load_optional_json(moira_backtest_path),
        event_quality=_load_optional_json(event_quality_path),
        cvar_review=_load_optional_json(cvar_review_path),
        cvar_cost_window_split=_load_optional_json(cvar_cost_window_split_path),
        tail_review=_load_optional_json(tail_review_path),
        re_evaluation_gate=_load_optional_json(re_evaluation_gate_path),
        auxiliary_task_readiness=_load_optional_json(auxiliary_task_readiness_path),
        adoption_2609_07946=_load_optional_json(adoption_2609_07946_path),
        promotion_gate_2609_07946=_load_optional_json(promotion_gate_2609_07946_path),
        instrument_review_00635u=_load_optional_json(instrument_review_00635u_path),
        adoption_2609_08106=_load_optional_json(adoption_2609_08106_path),
    )
