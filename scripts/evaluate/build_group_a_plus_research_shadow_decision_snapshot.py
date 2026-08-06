#!/usr/bin/env python3
"""Build a consolidated research-shadow decision snapshot for GroupA+.

This summary combines research-only diagnostics such as FinStressTS, tri-gate
volatility memory, systemic bubble time-at-risk, and HMM-WJ scenario readiness.
It never changes live target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINSTRESSTS = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_decision_snapshot.json"
DEFAULT_TRIGATE = PROJECT_ROOT / "report/group_a_plus/latest/trigate_vol_memory_shadow.json"
DEFAULT_SYSTEMIC_BUBBLE = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json"
DEFAULT_ILLIQUIDITY_NETWORK = PROJECT_ROOT / "report/group_a_plus/latest/illiquidity_network_readiness_review.json"
DEFAULT_SPECULATIVE_INFLUENCE = (
    PROJECT_ROOT / "report/group_a_plus/latest/speculative_influence_network_readiness_review.json"
)
DEFAULT_SIN_LITE_PROXY = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_proxy.json"
DEFAULT_HMM_WJ = PROJECT_ROOT / "report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json"
DEFAULT_DYNAMIC_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_SYNTHETIC_AUGMENTATION = (
    PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json"
)
DEFAULT_INTERVENTION_FATIGUE = (
    PROJECT_ROOT / "report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json"
)
DEFAULT_LETF_TRACKING = (
    PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
)
DEFAULT_ASIAN_ETF_TAIL_ANALYTICS = (
    PROJECT_ROOT / "report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json"
)
DEFAULT_REDUCED_RANK_CORRELATION = (
    PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json"
)
DEFAULT_REDUCED_RANK_PROXY = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy.json"
DEFAULT_REDUCED_RANK_PROXY_SWEEP = (
    PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json"
)
DEFAULT_REDUCED_RANK_CRASH_BACKTEST = (
    PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json"
)
DEFAULT_REDUCED_RANK_CONFIRMATION_OVERLAP = (
    PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json"
)
DEFAULT_RL_GOVERNANCE = PROJECT_ROOT / "report/group_a_plus/latest/rl_governance_readiness_review.json"
DEFAULT_LLM_STATE_REWARD_INTERFACE = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json"
)
DEFAULT_LLM_STATE_REWARD_DIAGNOSTIC_REFINEMENT = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_diagnostic_refinement_review.json"
)
DEFAULT_LLM_STATE_REWARD_SHADOW_TRAINING_READINESS = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_shadow_training_readiness_review.json"
)
DEFAULT_LLM_STATE_REWARD_REGIME_FILTERED_MICRO_TILT = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_regime_filtered_micro_tilt_shadow_backtest.json"
)
DEFAULT_LLM_STATE_REWARD_MANUAL_APPROVAL_READINESS = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_manual_approval_readiness_review.json"
)
DEFAULT_LLM_STATE_REWARD_SIGNED_APPROVAL_VALIDATION = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_validation.json"
)
DEFAULT_NCF_DECISION_CALIBRATION = PROJECT_ROOT / "results/ncf_decision_calibration_shadow_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def build_snapshot(
    *,
    finstressts_path: Path,
    trigate_path: Path,
    systemic_bubble_path: Path = DEFAULT_SYSTEMIC_BUBBLE,
    illiquidity_network_path: Path = DEFAULT_ILLIQUIDITY_NETWORK,
    speculative_influence_path: Path = DEFAULT_SPECULATIVE_INFLUENCE,
    sin_lite_proxy_path: Path = DEFAULT_SIN_LITE_PROXY,
    hmm_wj_path: Path = DEFAULT_HMM_WJ,
    dynamic_cvar_path: Path = DEFAULT_DYNAMIC_CVAR,
    synthetic_augmentation_path: Path = DEFAULT_SYNTHETIC_AUGMENTATION,
    intervention_fatigue_path: Path = DEFAULT_INTERVENTION_FATIGUE,
    letf_tracking_path: Path = DEFAULT_LETF_TRACKING,
    asian_etf_tail_analytics_path: Path = DEFAULT_ASIAN_ETF_TAIL_ANALYTICS,
    reduced_rank_correlation_path: Path = DEFAULT_REDUCED_RANK_CORRELATION,
    reduced_rank_proxy_path: Path = DEFAULT_REDUCED_RANK_PROXY,
    reduced_rank_proxy_sweep_path: Path = DEFAULT_REDUCED_RANK_PROXY_SWEEP,
    reduced_rank_crash_backtest_path: Path = DEFAULT_REDUCED_RANK_CRASH_BACKTEST,
    reduced_rank_confirmation_overlap_path: Path = DEFAULT_REDUCED_RANK_CONFIRMATION_OVERLAP,
    rl_governance_path: Path = DEFAULT_RL_GOVERNANCE,
    llm_state_reward_interface_path: Path = DEFAULT_LLM_STATE_REWARD_INTERFACE,
    llm_state_reward_diagnostic_refinement_path: Path = DEFAULT_LLM_STATE_REWARD_DIAGNOSTIC_REFINEMENT,
    llm_state_reward_shadow_training_readiness_path: Path = DEFAULT_LLM_STATE_REWARD_SHADOW_TRAINING_READINESS,
    llm_state_reward_regime_filtered_micro_tilt_path: Path = DEFAULT_LLM_STATE_REWARD_REGIME_FILTERED_MICRO_TILT,
    llm_state_reward_manual_approval_readiness_path: Path = DEFAULT_LLM_STATE_REWARD_MANUAL_APPROVAL_READINESS,
    llm_state_reward_signed_approval_validation_path: Path = DEFAULT_LLM_STATE_REWARD_SIGNED_APPROVAL_VALIDATION,
    ncf_decision_calibration_path: Path = DEFAULT_NCF_DECISION_CALIBRATION,
) -> dict[str, Any]:
    finstressts = _load(finstressts_path)
    trigate = _load(trigate_path)
    systemic_bubble = _load(systemic_bubble_path)
    illiquidity_network = _load(illiquidity_network_path)
    speculative_influence = _load(speculative_influence_path)
    sin_lite_proxy = _load(sin_lite_proxy_path)
    hmm_wj = _load(hmm_wj_path)
    dynamic_cvar = _load(dynamic_cvar_path)
    synthetic_augmentation = _load(synthetic_augmentation_path)
    intervention_fatigue = _load(intervention_fatigue_path)
    letf_tracking = _load(letf_tracking_path)
    asian_etf_tail_analytics = _load(asian_etf_tail_analytics_path)
    reduced_rank_correlation = _load(reduced_rank_correlation_path)
    reduced_rank_proxy = _load(reduced_rank_proxy_path)
    reduced_rank_proxy_sweep = _load(reduced_rank_proxy_sweep_path)
    reduced_rank_crash_backtest = _load(reduced_rank_crash_backtest_path)
    reduced_rank_confirmation_overlap = _load(reduced_rank_confirmation_overlap_path)
    rl_governance = _load(rl_governance_path)
    llm_state_reward_interface = _load(llm_state_reward_interface_path)
    llm_state_reward_diagnostic_refinement = _load(llm_state_reward_diagnostic_refinement_path)
    llm_state_reward_shadow_training_readiness = _load(llm_state_reward_shadow_training_readiness_path)
    llm_state_reward_regime_filtered_micro_tilt = _load(llm_state_reward_regime_filtered_micro_tilt_path)
    llm_state_reward_manual_approval_readiness = _load(llm_state_reward_manual_approval_readiness_path)
    llm_state_reward_signed_approval_validation = _load(llm_state_reward_signed_approval_validation_path)
    ncf_decision_calibration = _load(ncf_decision_calibration_path)
    fin_decision = _decision(finstressts)
    tri_decision = _decision(trigate)
    systemic_decision = _decision(systemic_bubble)
    illiquidity_network_decision = _decision(illiquidity_network)
    speculative_influence_decision = _decision(speculative_influence)
    sin_lite_decision = _decision(sin_lite_proxy)
    hmm_wj_decision = _decision(hmm_wj)
    dynamic_cvar_decision = _decision(dynamic_cvar)
    synthetic_augmentation_decision = _decision(synthetic_augmentation)
    intervention_fatigue_decision = _decision(intervention_fatigue)
    letf_tracking_decision = _decision(letf_tracking)
    asian_etf_tail_analytics_decision = _decision(asian_etf_tail_analytics)
    reduced_rank_correlation_decision = _decision(reduced_rank_correlation)
    reduced_rank_proxy_decision = _decision(reduced_rank_proxy)
    reduced_rank_proxy_sweep_decision = _decision(reduced_rank_proxy_sweep)
    reduced_rank_crash_backtest_decision = _decision(reduced_rank_crash_backtest)
    reduced_rank_confirmation_overlap_decision = _decision(reduced_rank_confirmation_overlap)
    rl_governance_decision = _decision(rl_governance)
    llm_state_reward_interface_decision = _decision(llm_state_reward_interface)
    llm_state_reward_diagnostic_refinement_decision = _decision(llm_state_reward_diagnostic_refinement)
    llm_state_reward_shadow_training_readiness_decision = _decision(llm_state_reward_shadow_training_readiness)
    llm_state_reward_regime_filtered_micro_tilt_decision = _decision(llm_state_reward_regime_filtered_micro_tilt)
    llm_state_reward_manual_approval_readiness_decision = _decision(llm_state_reward_manual_approval_readiness)
    llm_state_reward_signed_approval_validation_decision = _decision(llm_state_reward_signed_approval_validation)
    tri_state = trigate.get("tri_gate_state") or {}
    systemic_states = systemic_bubble.get("states") or {}
    illiquidity_proxy = illiquidity_network.get("daily_ohlcv_liquidity_stress_proxy") or {}
    sin_lite_latest = sin_lite_proxy.get("latest") or {}

    blockers: list[str] = []
    warnings: list[str] = []
    if not finstressts:
        blockers.append("missing_finstressts_decision_snapshot")
    if not trigate:
        blockers.append("missing_trigate_vol_memory_shadow")
    if not systemic_bubble:
        blockers.append("missing_systemic_bubble_time_at_risk_review")
    if not illiquidity_network:
        blockers.append("missing_illiquidity_network_readiness_review")
    if not speculative_influence:
        blockers.append("missing_speculative_influence_network_readiness_review")
    if not sin_lite_proxy:
        blockers.append("missing_sin_lite_proxy")
    if not hmm_wj:
        blockers.append("missing_hmm_wj_synthetic_scenario_readiness_review")
    if not dynamic_cvar:
        blockers.append("missing_dynamic_cvar_tail_cost_readiness_review")
    if not synthetic_augmentation:
        blockers.append("missing_synthetic_augmentation_validation_readiness_review")
    if not intervention_fatigue:
        blockers.append("missing_intervention_fatigue_risk_budget_readiness_review")
    if not letf_tracking:
        blockers.append("missing_letf_tracking_error_effective_fee_readiness_review")
    if not asian_etf_tail_analytics:
        blockers.append("missing_asian_etf_tail_analytics_readiness_review")
    if not reduced_rank_correlation:
        blockers.append("missing_reduced_rank_correlation_readiness_review")
    if not rl_governance:
        blockers.append("missing_rl_governance_readiness_review")
    if not llm_state_reward_interface:
        blockers.append("missing_llm_state_reward_interface_readiness_review")
    if not llm_state_reward_diagnostic_refinement:
        blockers.append("missing_llm_state_reward_interface_diagnostic_refinement_review")
    if not llm_state_reward_shadow_training_readiness:
        warnings.append("missing_llm_state_reward_shadow_training_readiness_review")
    if not llm_state_reward_regime_filtered_micro_tilt:
        warnings.append("missing_llm_state_reward_regime_filtered_micro_tilt_shadow_backtest")
    if not llm_state_reward_manual_approval_readiness:
        warnings.append("missing_llm_state_reward_manual_approval_readiness_review")
    if not llm_state_reward_signed_approval_validation:
        warnings.append("missing_llm_state_reward_signed_approval_validation")
    if not ncf_decision_calibration:
        warnings.append("missing_ncf_decision_calibration_shadow")
    if finstressts.get("status") == "blocked":
        blockers.append("finstressts_snapshot_blocked")
    if tri_state.get("state") == "blocked_for_leverage_add":
        blockers.append("trigate_vol_memory_blocks_leverage_add")
    if systemic_states.get("overall_state") == "blocked_for_leverage_add":
        blockers.append("systemic_bubble_time_at_risk_blocks_leverage_add")
    if illiquidity_network.get("status") == "blocked":
        blockers.append("illiquidity_network_readiness_blocked")
    if speculative_influence.get("status") == "blocked":
        blockers.append("speculative_influence_network_readiness_blocked")
    if sin_lite_proxy.get("status") == "blocked":
        blockers.append("sin_lite_proxy_blocked")
    if hmm_wj.get("status") == "blocked":
        blockers.append("hmm_wj_synthetic_scenario_readiness_blocked")
    if dynamic_cvar.get("status") == "blocked":
        blockers.append("dynamic_cvar_tail_cost_readiness_blocked")
    if synthetic_augmentation.get("status") == "blocked":
        blockers.append("synthetic_augmentation_validation_readiness_blocked")
    if intervention_fatigue.get("status") == "blocked":
        blockers.append("intervention_fatigue_risk_budget_readiness_blocked")
    if letf_tracking.get("status") == "blocked":
        blockers.append("letf_tracking_error_effective_fee_readiness_blocked")
    if asian_etf_tail_analytics.get("status") == "blocked":
        blockers.append("asian_etf_tail_analytics_readiness_blocked")
    if reduced_rank_correlation.get("status") == "blocked":
        blockers.append("reduced_rank_correlation_readiness_blocked")
    if rl_governance.get("status") == "blocked":
        blockers.append("rl_governance_readiness_blocked")
    if llm_state_reward_interface.get("status") == "blocked":
        blockers.append("llm_state_reward_interface_readiness_blocked")
    if llm_state_reward_diagnostic_refinement.get("status") == "blocked":
        blockers.append("llm_state_reward_interface_diagnostic_refinement_blocked")
    if llm_state_reward_shadow_training_readiness.get("status") == "blocked":
        warnings.append("llm_state_reward_shadow_training_readiness_blocked")
    if llm_state_reward_regime_filtered_micro_tilt.get("status") == "blocked":
        warnings.append("llm_state_reward_regime_filtered_micro_tilt_blocked")
    if llm_state_reward_manual_approval_readiness.get("status") == "blocked":
        warnings.append("llm_state_reward_manual_approval_readiness_blocked")
    if llm_state_reward_signed_approval_validation.get("status") == "blocked":
        warnings.append("llm_state_reward_signed_approval_validation_blocked")
    if tri_state.get("stress_gate_count") is not None:
        warnings.append(f"trigate_stress_gate_count:{tri_state.get('stress_gate_count')}")
    if systemic_states.get("systemic_score") is not None:
        warnings.append(f"systemic_bubble_score:{systemic_states.get('systemic_score')}")
    if illiquidity_network.get("status"):
        warnings.append(f"illiquidity_network_status:{illiquidity_network.get('status')}")
    if illiquidity_proxy.get("stress_score") is not None:
        warnings.append(f"illiquidity_daily_proxy_score:{illiquidity_proxy.get('stress_score')}")
    if illiquidity_proxy.get("stress_state"):
        warnings.append(f"illiquidity_daily_proxy_state:{illiquidity_proxy.get('stress_state')}")
    if speculative_influence.get("status"):
        warnings.append(f"speculative_influence_network_status:{speculative_influence.get('status')}")
    if sin_lite_latest.get("sin_lite_score") is not None:
        warnings.append(f"sin_lite_score:{sin_lite_latest.get('sin_lite_score')}")
    if sin_lite_latest.get("state"):
        warnings.append(f"sin_lite_state:{sin_lite_latest.get('state')}")
    if hmm_wj.get("status"):
        warnings.append(f"hmm_wj_status:{hmm_wj.get('status')}")
    if dynamic_cvar.get("status"):
        warnings.append(f"dynamic_cvar_status:{dynamic_cvar.get('status')}")
    if synthetic_augmentation.get("status"):
        warnings.append(f"synthetic_augmentation_status:{synthetic_augmentation.get('status')}")
    if intervention_fatigue.get("status"):
        warnings.append(f"intervention_fatigue_status:{intervention_fatigue.get('status')}")
    if letf_tracking.get("status"):
        warnings.append(f"letf_tracking_status:{letf_tracking.get('status')}")
    if asian_etf_tail_analytics.get("status"):
        warnings.append(f"asian_etf_tail_analytics_status:{asian_etf_tail_analytics.get('status')}")
    if reduced_rank_correlation.get("status"):
        warnings.append(f"reduced_rank_correlation_status:{reduced_rank_correlation.get('status')}")
    if reduced_rank_proxy.get("status"):
        warnings.append(f"reduced_rank_proxy_status:{reduced_rank_proxy.get('status')}")
    if reduced_rank_proxy_sweep.get("status"):
        warnings.append(f"reduced_rank_proxy_sweep_status:{reduced_rank_proxy_sweep.get('status')}")
    if reduced_rank_crash_backtest.get("status"):
        warnings.append(f"reduced_rank_crash_backtest_status:{reduced_rank_crash_backtest.get('status')}")
    if reduced_rank_confirmation_overlap.get("status"):
        warnings.append(f"reduced_rank_confirmation_overlap_status:{reduced_rank_confirmation_overlap.get('status')}")
    if rl_governance.get("status"):
        warnings.append(f"rl_governance_status:{rl_governance.get('status')}")
    if llm_state_reward_interface.get("status"):
        warnings.append(f"llm_state_reward_interface_status:{llm_state_reward_interface.get('status')}")
    if llm_state_reward_diagnostic_refinement.get("status"):
        warnings.append(
            "llm_state_reward_diagnostic_refinement_status:"
            f"{llm_state_reward_diagnostic_refinement.get('status')}"
        )
    for reason in llm_state_reward_diagnostic_refinement.get("warning_reasons") or []:
        warnings.append(f"llm_state_reward_diagnostic_refinement:{reason}")
    if llm_state_reward_shadow_training_readiness.get("status"):
        warnings.append(
            "llm_state_reward_shadow_training_readiness_status:"
            f"{llm_state_reward_shadow_training_readiness.get('status')}"
        )
    for reason in llm_state_reward_shadow_training_readiness.get("warning_reasons") or []:
        warnings.append(f"llm_state_reward_shadow_training_readiness:{reason}")
    if llm_state_reward_regime_filtered_micro_tilt.get("status"):
        warnings.append(
            "llm_state_reward_regime_filtered_micro_tilt_status:"
            f"{llm_state_reward_regime_filtered_micro_tilt.get('status')}"
        )
    if llm_state_reward_manual_approval_readiness.get("status"):
        warnings.append(
            "llm_state_reward_manual_approval_readiness_status:"
            f"{llm_state_reward_manual_approval_readiness.get('status')}"
        )
    for reason in llm_state_reward_manual_approval_readiness.get("training_queue_blocking_reasons") or []:
        warnings.append(f"llm_state_reward_manual_approval_readiness:{reason}")
    if llm_state_reward_signed_approval_validation.get("status"):
        warnings.append(
            "llm_state_reward_signed_approval_validation_status:"
            f"{llm_state_reward_signed_approval_validation.get('status')}"
        )
    for reason in llm_state_reward_signed_approval_validation.get("blocking_reasons") or []:
        warnings.append(f"llm_state_reward_signed_approval_validation:{reason}")
    ncf_calibration_governance = ncf_decision_calibration.get("calibration_governance") or (
        (ncf_decision_calibration.get("snapshot") or {}).get("governance") or {}
    )
    if ncf_calibration_governance.get("status"):
        warnings.append(f"ncf_decision_calibration_governance_status:{ncf_calibration_governance.get('status')}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_research_shadow_decision_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_shadow_summary_no_weight_change",
        "status": "blocked" if blockers else "available_for_manual_review",
        "summary": {
            "finstressts_status": finstressts.get("status"),
            "finstressts_allow_00631l_add": fin_decision.get("allow_00631l_add"),
            "trigate_state": tri_state.get("state"),
            "trigate_stress_gate_count": tri_state.get("stress_gate_count"),
            "trigate_allow_00631l_add": tri_decision.get("allow_00631l_add"),
            "systemic_bubble_state": systemic_states.get("overall_state"),
            "systemic_bubble_score": systemic_states.get("systemic_score"),
            "systemic_bubble_allow_00631l_add": systemic_decision.get("allow_00631l_add"),
            "illiquidity_network_status": illiquidity_network.get("status"),
            "illiquidity_network_ready": illiquidity_network_decision.get("illiquidity_network_ready"),
            "illiquidity_network_crash_guard_allowed": illiquidity_network_decision.get("crash_guard_allowed"),
            "illiquidity_network_allow_00631l_add": illiquidity_network_decision.get("allow_00631l_add"),
            "illiquidity_daily_proxy_status": illiquidity_proxy.get("status"),
            "illiquidity_daily_proxy_paper_equivalent": illiquidity_proxy.get("paper_equivalent"),
            "illiquidity_daily_proxy_stress_score": illiquidity_proxy.get("stress_score"),
            "illiquidity_daily_proxy_stress_state": illiquidity_proxy.get("stress_state"),
            "illiquidity_daily_proxy_manual_review_required": illiquidity_proxy.get("manual_review_required"),
            "illiquidity_daily_proxy_coverage_tickers": illiquidity_proxy.get("coverage_tickers"),
            "speculative_influence_network_status": speculative_influence.get("status"),
            "speculative_influence_network_ready": speculative_influence_decision.get(
                "speculative_influence_network_ready"
            ),
            "speculative_influence_hmm_bubble_state_ready": speculative_influence_decision.get(
                "hmm_bubble_state_ready"
            ),
            "speculative_influence_transfer_entropy_ready": speculative_influence_decision.get(
                "transfer_entropy_network_ready"
            ),
            "speculative_influence_maxloss_validation_ready": speculative_influence_decision.get(
                "maxloss_validation_ready"
            ),
            "speculative_influence_allow_00631l_add": speculative_influence_decision.get("allow_00631l_add"),
            "sin_lite_proxy_status": sin_lite_proxy.get("status"),
            "sin_lite_proxy_state": sin_lite_latest.get("state"),
            "sin_lite_proxy_score": sin_lite_latest.get("sin_lite_score"),
            "sin_lite_proxy_usable_ticker_count": (sin_lite_proxy.get("coverage") or {}).get("usable_ticker_count"),
            "sin_lite_proxy_manual_review_required": sin_lite_latest.get("manual_review_required"),
            "sin_lite_proxy_allow_00631l_add": sin_lite_decision.get("allow_00631l_add"),
            "hmm_wj_status": hmm_wj.get("status"),
            "hmm_wj_data_ready": (hmm_wj.get("data_readiness") or {}).get("all_required_tickers_ready"),
            "hmm_wj_can_generate_scenarios_for_decision": hmm_wj_decision.get("can_generate_scenarios_for_decision"),
            "hmm_wj_allow_00631l_add": hmm_wj_decision.get("allow_00631l_add"),
            "dynamic_cvar_status": dynamic_cvar.get("status"),
            "dynamic_cvar_tail_cost_ready": dynamic_cvar_decision.get("tail_cost_readiness_ready"),
            "dynamic_cvar_optimizer_ready": dynamic_cvar_decision.get("dynamic_optimizer_ready"),
            "dynamic_cvar_allow_00631l_add": dynamic_cvar_decision.get("allow_00631l_add"),
            "synthetic_augmentation_status": synthetic_augmentation.get("status"),
            "synthetic_validation_ready": synthetic_augmentation_decision.get("synthetic_validation_ready"),
            "directional_synthetic_alpha_allowed": synthetic_augmentation_decision.get(
                "directional_synthetic_alpha_allowed"
            ),
            "synthetic_generator_promotion_allowed": synthetic_augmentation_decision.get(
                "synthetic_generator_promotion_allowed"
            ),
            "synthetic_augmentation_allow_00631l_add": synthetic_augmentation_decision.get("allow_00631l_add"),
            "intervention_fatigue_status": intervention_fatigue.get("status"),
            "intervention_fatigue_ready": intervention_fatigue_decision.get("intervention_fatigue_ready"),
            "risk_budget_pacing_ready": intervention_fatigue_decision.get("risk_budget_pacing_ready"),
            "intervention_fatigue_allow_00631l_add": intervention_fatigue_decision.get("allow_00631l_add"),
            "letf_tracking_status": letf_tracking.get("status"),
            "letf_tracking_error_readiness_ready": letf_tracking_decision.get("tracking_error_readiness_ready"),
            "letf_effective_fee_proxy_ready": letf_tracking_decision.get("realized_effective_fee_proxy_ready"),
            "letf_hedge_neutrality_ready": letf_tracking_decision.get("hedge_neutrality_ready"),
            "letf_allow_00631l_add": letf_tracking_decision.get("allow_00631l_add"),
            "letf_allow_00632r_open": letf_tracking_decision.get("allow_00632r_open"),
            "asian_etf_tail_analytics_status": asian_etf_tail_analytics.get("status"),
            "asian_etf_tail_analytics_ready": asian_etf_tail_analytics_decision.get("tail_analytics_ready"),
            "asian_etf_optimizer_ready": asian_etf_tail_analytics_decision.get("optimizer_ready"),
            "asian_etf_available_paper_etf_count": (
                ((asian_etf_tail_analytics.get("data_readiness") or {}).get("paper_etf_coverage") or {}).get(
                    "available_paper_etf_count"
                )
            ),
            "asian_etf_allow_00631l_add": asian_etf_tail_analytics_decision.get("allow_00631l_add"),
            "reduced_rank_correlation_status": reduced_rank_correlation.get("status"),
            "reduced_rank_correlation_ready": reduced_rank_correlation_decision.get(
                "reduced_rank_correlation_ready"
            ),
            "reduced_rank_weak_proxy_ready": reduced_rank_correlation_decision.get(
                "weak_proxy_ready_for_research"
            ),
            "reduced_rank_paper_equivalent_ready": reduced_rank_correlation_decision.get("paper_equivalent_ready"),
            "reduced_rank_allow_00631l_add": reduced_rank_correlation_decision.get("allow_00631l_add"),
            "reduced_rank_proxy_status": reduced_rank_proxy.get("status"),
            "reduced_rank_proxy_state": (reduced_rank_proxy.get("latest") or {}).get("state"),
            "reduced_rank_proxy_manual_review_required": (reduced_rank_proxy.get("latest") or {}).get(
                "manual_review_required"
            ),
            "reduced_rank_proxy_usable_ticker_count": (reduced_rank_proxy.get("coverage") or {}).get(
                "usable_ticker_count"
            ),
            "reduced_rank_proxy_allow_00631l_add": reduced_rank_proxy_decision.get("allow_00631l_add"),
            "reduced_rank_proxy_sweep_status": reduced_rank_proxy_sweep.get("status"),
            "reduced_rank_proxy_sweep_available_candidate_count": (reduced_rank_proxy_sweep.get("grid") or {}).get(
                "available_candidate_count"
            ),
            "reduced_rank_proxy_sweep_state_counts": (reduced_rank_proxy_sweep.get("aggregate") or {}).get(
                "available_state_counts"
            ),
            "reduced_rank_proxy_sweep_manual_review_candidate_count": (
                reduced_rank_proxy_sweep.get("aggregate") or {}
            ).get("manual_review_candidate_count"),
            "reduced_rank_proxy_sweep_allow_00631l_add": reduced_rank_proxy_sweep_decision.get("allow_00631l_add"),
            "reduced_rank_crash_backtest_status": reduced_rank_crash_backtest.get("status"),
            "reduced_rank_crash_backtest_stress_watch_rate": (
                reduced_rank_crash_backtest.get("aggregate") or {}
            ).get("stress_window_watch_or_worse_rate"),
            "reduced_rank_crash_backtest_non_window_watch_rate": (
                reduced_rank_crash_backtest.get("aggregate") or {}
            ).get("non_window_watch_or_worse_rate"),
            "reduced_rank_crash_backtest_stress_elevated_rate": (
                reduced_rank_crash_backtest.get("aggregate") or {}
            ).get("stress_window_elevated_or_worse_rate"),
            "reduced_rank_crash_backtest_non_window_elevated_rate": (
                reduced_rank_crash_backtest.get("aggregate") or {}
            ).get("non_window_elevated_or_worse_rate"),
            "reduced_rank_crash_backtest_allow_00631l_add": reduced_rank_crash_backtest_decision.get(
                "allow_00631l_add"
            ),
            "reduced_rank_confirmation_overlap_status": reduced_rank_confirmation_overlap.get("status"),
            "reduced_rank_confirmed_stress_watch_rate": (
                (reduced_rank_confirmation_overlap.get("summary") or {}).get("confirmed_reduced_rank") or {}
            ).get("stress_watch_or_worse_rate"),
            "reduced_rank_confirmed_non_window_watch_rate": (
                (reduced_rank_confirmation_overlap.get("summary") or {}).get("confirmed_reduced_rank") or {}
            ).get("non_window_watch_or_worse_rate"),
            "reduced_rank_confirmed_stress_to_non_ratio": (
                (reduced_rank_confirmation_overlap.get("summary") or {}).get("confirmed_reduced_rank") or {}
            ).get("stress_to_non_rate_ratio"),
            "reduced_rank_confirmation_overlap_allow_00631l_add": reduced_rank_confirmation_overlap_decision.get(
                "allow_00631l_add"
            ),
            "rl_governance_status": rl_governance.get("status"),
            "rl_governance_ready": rl_governance_decision.get("rl_governance_ready"),
            "rl_component_promotable": rl_governance_decision.get("rl_component_promotable"),
            "live_rl_allocator_allowed": rl_governance_decision.get("live_rl_allocator_allowed"),
            "rl_governance_allow_00631l_add": rl_governance_decision.get("allow_00631l_add"),
            "llm_state_reward_interface_status": llm_state_reward_interface.get("status"),
            "llm_state_reward_interface_ready": llm_state_reward_interface_decision.get(
                "llm_state_reward_interface_ready"
            ),
            "feature_proposal_governance_imported": llm_state_reward_interface_decision.get(
                "feature_proposal_governance_imported"
            ),
            "reward_shaping_governance_imported": llm_state_reward_interface_decision.get(
                "reward_shaping_governance_imported"
            ),
            "live_llm_trading_allowed": llm_state_reward_interface_decision.get("live_llm_trading_allowed"),
            "live_ppo_allocator_allowed": llm_state_reward_interface_decision.get("live_ppo_allocator_allowed"),
            "llm_state_reward_interface_allow_00631l_add": llm_state_reward_interface_decision.get(
                "allow_00631l_add"
            ),
            "llm_state_reward_diagnostic_refinement_status": llm_state_reward_diagnostic_refinement.get("status"),
            "llm_state_reward_diagnostic_refinement_ready": llm_state_reward_diagnostic_refinement_decision.get(
                "diagnostic_refinement_ready_for_research_review"
            ),
            "llm_state_reward_diagnostic_mean_reward_snr": (
                llm_state_reward_diagnostic_refinement.get("summary") or {}
            ).get("mean_reward_snr"),
            "llm_state_reward_diagnostic_mean_reward_future_return_alignment": (
                llm_state_reward_diagnostic_refinement.get("summary") or {}
            ).get("mean_reward_future_return_alignment"),
            "llm_state_reward_diagnostic_mean_reward_future_downside_alignment": (
                llm_state_reward_diagnostic_refinement.get("summary") or {}
            ).get("mean_reward_future_downside_alignment"),
            "llm_state_reward_diagnostic_grade": (
                llm_state_reward_diagnostic_refinement.get("summary") or {}
            ).get("reward_alignment_grade"),
            "llm_state_reward_diagnostic_ppo_training_queue_allowed": (
                llm_state_reward_diagnostic_refinement.get("summary") or {}
            ).get("ppo_training_queue_allowed_by_alignment"),
            "llm_state_reward_diagnostic_warning_count": len(
                llm_state_reward_diagnostic_refinement.get("warning_reasons") or []
            )
            if llm_state_reward_diagnostic_refinement
            else None,
            "llm_state_reward_diagnostic_allow_00631l_add": llm_state_reward_diagnostic_refinement_decision.get(
                "allow_00631l_add"
            ),
            "llm_state_reward_diagnostic_allow_00632r_open": llm_state_reward_diagnostic_refinement_decision.get(
                "allow_00632r_open"
            ),
            "llm_state_reward_shadow_training_readiness_status": llm_state_reward_shadow_training_readiness.get(
                "status"
            ),
            "llm_state_reward_shadow_training_ready": llm_state_reward_shadow_training_readiness_decision.get(
                "shadow_training_ready"
            ),
            "llm_state_reward_shadow_training_request_allowed": (
                llm_state_reward_shadow_training_readiness_decision.get("shadow_training_request_allowed")
            ),
            "llm_state_reward_shadow_training_model_training_allowed": (
                llm_state_reward_shadow_training_readiness_decision.get("model_training_allowed")
            ),
            "llm_state_reward_shadow_training_ppo_training_allowed": (
                llm_state_reward_shadow_training_readiness_decision.get("ppo_training_allowed")
            ),
            "llm_state_reward_shadow_training_promote_to_live": (
                llm_state_reward_shadow_training_readiness_decision.get("promote_to_live")
            ),
            "llm_state_reward_shadow_training_allow_00631l_add": (
                llm_state_reward_shadow_training_readiness_decision.get("allow_00631l_add")
            ),
            "llm_state_reward_shadow_training_allow_00632r_open": (
                llm_state_reward_shadow_training_readiness_decision.get("allow_00632r_open")
            ),
            "llm_state_reward_regime_filtered_micro_tilt_status": llm_state_reward_regime_filtered_micro_tilt.get(
                "status"
            ),
            "llm_state_reward_regime_filter_resolves_5bps_warning": (
                llm_state_reward_regime_filtered_micro_tilt_decision.get("regime_filter_resolves_5bps_warning")
            ),
            "llm_state_reward_regime_filtered_recommended_candidate": (
                (llm_state_reward_regime_filtered_micro_tilt.get("summary") or {}).get("recommended_candidate")
            ),
            "llm_state_reward_regime_filtered_model_training_allowed": (
                llm_state_reward_regime_filtered_micro_tilt_decision.get("model_training_allowed")
            ),
            "llm_state_reward_regime_filtered_promote_to_live": (
                llm_state_reward_regime_filtered_micro_tilt_decision.get("promote_to_live")
            ),
            "llm_state_reward_manual_approval_readiness_status": (
                llm_state_reward_manual_approval_readiness.get("status")
            ),
            "llm_state_reward_manual_approval_review_ready": (
                llm_state_reward_manual_approval_readiness_decision.get("manual_approval_review_ready")
            ),
            "llm_state_reward_manual_approval_to_queue_training_allowed": (
                llm_state_reward_manual_approval_readiness_decision.get(
                    "manual_approval_to_queue_training_allowed"
                )
            ),
            "llm_state_reward_manual_approval_queue_blocking_reasons": (
                llm_state_reward_manual_approval_readiness.get("training_queue_blocking_reasons") or []
            ),
            "llm_state_reward_manual_approval_model_training_allowed": (
                llm_state_reward_manual_approval_readiness_decision.get("model_training_allowed")
            ),
            "llm_state_reward_manual_approval_ppo_training_allowed": (
                llm_state_reward_manual_approval_readiness_decision.get("ppo_training_allowed")
            ),
            "llm_state_reward_manual_approval_promote_to_live": (
                llm_state_reward_manual_approval_readiness_decision.get("promote_to_live")
            ),
            "llm_state_reward_signed_approval_validation_status": (
                llm_state_reward_signed_approval_validation.get("status")
            ),
            "llm_state_reward_signed_approval_record_valid": (
                llm_state_reward_signed_approval_validation_decision.get("signed_approval_record_valid")
            ),
            "llm_state_reward_signed_approval_human_exception_approved": (
                llm_state_reward_signed_approval_validation_decision.get("human_exception_approved")
            ),
            "llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed": (
                llm_state_reward_signed_approval_validation_decision.get(
                    "non_ppo_shadow_queue_review_allowed"
                )
            ),
            "llm_state_reward_signed_approval_training_queue_allowed": (
                llm_state_reward_signed_approval_validation_decision.get("training_queue_allowed")
            ),
            "llm_state_reward_signed_approval_model_training_allowed": (
                llm_state_reward_signed_approval_validation_decision.get("model_training_allowed")
            ),
            "llm_state_reward_signed_approval_ppo_training_allowed": (
                llm_state_reward_signed_approval_validation_decision.get("ppo_training_allowed")
            ),
            "llm_state_reward_signed_approval_promote_to_live": (
                llm_state_reward_signed_approval_validation_decision.get("promote_to_live")
            ),
            "ncf_decision_calibration_status": ncf_decision_calibration.get("status"),
            "ncf_decision_calibration_governance_status": ncf_calibration_governance.get("status"),
            "ncf_decision_confidence_contract": ncf_calibration_governance.get("decision_confidence_contract"),
            "ncf_decision_calibration_model_default_enabled": ncf_calibration_governance.get(
                "calibration_model_default_enabled"
            ),
            "ncf_decision_calibration_live_gate_allowed": ncf_calibration_governance.get("live_gate_allowed"),
            "ncf_decision_calibration_target_weight_change_allowed": ncf_calibration_governance.get(
                "target_weight_change_allowed"
            ),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Research shadow diagnostics do not permit 00631L add: at least one research-only "
                "readiness, volatility-memory, systemic bubble time-at-risk, HMM-WJ scenario-readiness, "
                "illiquidity-network readiness, speculative-influence-network readiness, SIN-lite proxy, dynamic CVaR tail/cost diagnostic, synthetic augmentation validation gate, or "
                "intervention fatigue/risk-budget gate, LETF tracking-error/effective-fee gate, Asian ETF tail-analytics gate, reduced-rank correlation readiness, RL governance, or LLM state-reward interface readiness is blocked."
            )
            if blockers
            else "Research shadow diagnostics are available for manual review only.",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "finstressts": str(finstressts_path),
            "trigate_vol_memory": str(trigate_path),
            "systemic_bubble_time_at_risk": str(systemic_bubble_path),
            "illiquidity_network_readiness": str(illiquidity_network_path),
            "speculative_influence_network_readiness": str(speculative_influence_path),
            "sin_lite_proxy": str(sin_lite_proxy_path),
            "hmm_wj_synthetic_scenario_readiness": str(hmm_wj_path),
            "dynamic_cvar_tail_cost_readiness": str(dynamic_cvar_path),
            "synthetic_augmentation_validation_readiness": str(synthetic_augmentation_path),
            "intervention_fatigue_risk_budget_readiness": str(intervention_fatigue_path),
            "letf_tracking_error_effective_fee_readiness": str(letf_tracking_path),
            "asian_etf_tail_analytics_readiness": str(asian_etf_tail_analytics_path),
            "reduced_rank_correlation_readiness": str(reduced_rank_correlation_path),
            "reduced_rank_correlation_proxy": str(reduced_rank_proxy_path),
            "reduced_rank_correlation_proxy_param_sweep": str(reduced_rank_proxy_sweep_path),
            "reduced_rank_correlation_crash_window_backtest": str(reduced_rank_crash_backtest_path),
            "reduced_rank_confirmation_overlap_backtest": str(reduced_rank_confirmation_overlap_path),
            "rl_governance_readiness": str(rl_governance_path),
            "llm_state_reward_interface_readiness": str(llm_state_reward_interface_path),
            "llm_state_reward_interface_diagnostic_refinement": str(llm_state_reward_diagnostic_refinement_path),
            "llm_state_reward_shadow_training_readiness": str(llm_state_reward_shadow_training_readiness_path),
            "llm_state_reward_regime_filtered_micro_tilt": str(llm_state_reward_regime_filtered_micro_tilt_path),
            "llm_state_reward_manual_approval_readiness": str(llm_state_reward_manual_approval_readiness_path),
            "llm_state_reward_signed_approval_validation": str(llm_state_reward_signed_approval_validation_path),
            "ncf_decision_calibration": str(ncf_decision_calibration_path),
        },
    }


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finstressts", default=str(DEFAULT_FINSTRESSTS))
    parser.add_argument("--trigate", default=str(DEFAULT_TRIGATE))
    parser.add_argument("--systemic-bubble", default=str(DEFAULT_SYSTEMIC_BUBBLE))
    parser.add_argument("--illiquidity-network", default=str(DEFAULT_ILLIQUIDITY_NETWORK))
    parser.add_argument("--speculative-influence", default=str(DEFAULT_SPECULATIVE_INFLUENCE))
    parser.add_argument("--sin-lite-proxy", default=str(DEFAULT_SIN_LITE_PROXY))
    parser.add_argument("--hmm-wj", default=str(DEFAULT_HMM_WJ))
    parser.add_argument("--dynamic-cvar", default=str(DEFAULT_DYNAMIC_CVAR))
    parser.add_argument("--synthetic-augmentation", default=str(DEFAULT_SYNTHETIC_AUGMENTATION))
    parser.add_argument("--intervention-fatigue", default=str(DEFAULT_INTERVENTION_FATIGUE))
    parser.add_argument("--letf-tracking", default=str(DEFAULT_LETF_TRACKING))
    parser.add_argument("--asian-etf-tail-analytics", default=str(DEFAULT_ASIAN_ETF_TAIL_ANALYTICS))
    parser.add_argument("--reduced-rank-correlation", default=str(DEFAULT_REDUCED_RANK_CORRELATION))
    parser.add_argument("--reduced-rank-proxy", default=str(DEFAULT_REDUCED_RANK_PROXY))
    parser.add_argument("--reduced-rank-proxy-sweep", default=str(DEFAULT_REDUCED_RANK_PROXY_SWEEP))
    parser.add_argument("--reduced-rank-crash-backtest", default=str(DEFAULT_REDUCED_RANK_CRASH_BACKTEST))
    parser.add_argument("--reduced-rank-confirmation-overlap", default=str(DEFAULT_REDUCED_RANK_CONFIRMATION_OVERLAP))
    parser.add_argument("--rl-governance", default=str(DEFAULT_RL_GOVERNANCE))
    parser.add_argument("--llm-state-reward-interface", default=str(DEFAULT_LLM_STATE_REWARD_INTERFACE))
    parser.add_argument(
        "--llm-state-reward-diagnostic-refinement",
        default=str(DEFAULT_LLM_STATE_REWARD_DIAGNOSTIC_REFINEMENT),
    )
    parser.add_argument(
        "--llm-state-reward-shadow-training-readiness",
        default=str(DEFAULT_LLM_STATE_REWARD_SHADOW_TRAINING_READINESS),
    )
    parser.add_argument(
        "--llm-state-reward-regime-filtered-micro-tilt",
        default=str(DEFAULT_LLM_STATE_REWARD_REGIME_FILTERED_MICRO_TILT),
    )
    parser.add_argument(
        "--llm-state-reward-manual-approval-readiness",
        default=str(DEFAULT_LLM_STATE_REWARD_MANUAL_APPROVAL_READINESS),
    )
    parser.add_argument(
        "--llm-state-reward-signed-approval-validation",
        default=str(DEFAULT_LLM_STATE_REWARD_SIGNED_APPROVAL_VALIDATION),
    )
    parser.add_argument("--ncf-decision-calibration", default=str(DEFAULT_NCF_DECISION_CALIBRATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    snapshot = build_snapshot(
        finstressts_path=_resolve(args.finstressts),
        trigate_path=_resolve(args.trigate),
        systemic_bubble_path=_resolve(args.systemic_bubble),
        illiquidity_network_path=_resolve(args.illiquidity_network),
        speculative_influence_path=_resolve(args.speculative_influence),
        sin_lite_proxy_path=_resolve(args.sin_lite_proxy),
        hmm_wj_path=_resolve(args.hmm_wj),
        dynamic_cvar_path=_resolve(args.dynamic_cvar),
        synthetic_augmentation_path=_resolve(args.synthetic_augmentation),
        intervention_fatigue_path=_resolve(args.intervention_fatigue),
        letf_tracking_path=_resolve(args.letf_tracking),
        asian_etf_tail_analytics_path=_resolve(args.asian_etf_tail_analytics),
        reduced_rank_correlation_path=_resolve(args.reduced_rank_correlation),
        reduced_rank_proxy_path=_resolve(args.reduced_rank_proxy),
        reduced_rank_proxy_sweep_path=_resolve(args.reduced_rank_proxy_sweep),
        reduced_rank_crash_backtest_path=_resolve(args.reduced_rank_crash_backtest),
        reduced_rank_confirmation_overlap_path=_resolve(args.reduced_rank_confirmation_overlap),
        rl_governance_path=_resolve(args.rl_governance),
        llm_state_reward_interface_path=_resolve(args.llm_state_reward_interface),
        llm_state_reward_diagnostic_refinement_path=_resolve(args.llm_state_reward_diagnostic_refinement),
        llm_state_reward_shadow_training_readiness_path=_resolve(
            args.llm_state_reward_shadow_training_readiness
        ),
        llm_state_reward_regime_filtered_micro_tilt_path=_resolve(
            args.llm_state_reward_regime_filtered_micro_tilt
        ),
        llm_state_reward_manual_approval_readiness_path=_resolve(
            args.llm_state_reward_manual_approval_readiness
        ),
        llm_state_reward_signed_approval_validation_path=_resolve(
            args.llm_state_reward_signed_approval_validation
        ),
        ncf_decision_calibration_path=_resolve(args.ncf_decision_calibration),
    )
    write_snapshot(snapshot, _resolve(args.output))
    print(f"Research shadow decision snapshot: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": snapshot["status"],
                "allow_00631l_add": snapshot["decision"]["allow_00631l_add"],
                "allow_00632r_open": snapshot["decision"]["allow_00632r_open"],
                "blocking_reasons": snapshot["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
