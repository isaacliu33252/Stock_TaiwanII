from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_research_shadow_decision_snapshot import (
    build_snapshot,
    write_snapshot,
)


def test_build_snapshot_blocks_when_research_shadows_block(tmp_path: Path) -> None:
    finstressts = tmp_path / "fin.json"
    trigate = tmp_path / "tri.json"
    systemic = tmp_path / "systemic.json"
    illiquidity = tmp_path / "illiquidity.json"
    speculative = tmp_path / "speculative.json"
    sin_lite = tmp_path / "sin_lite.json"
    hmm_wj = tmp_path / "hmm_wj.json"
    dynamic_cvar = tmp_path / "dynamic_cvar.json"
    synthetic_augmentation = tmp_path / "synthetic_augmentation.json"
    intervention_fatigue = tmp_path / "intervention_fatigue.json"
    letf_tracking = tmp_path / "letf_tracking.json"
    asian_etf_tail = tmp_path / "asian_etf_tail.json"
    reduced_rank = tmp_path / "reduced_rank.json"
    reduced_rank_proxy = tmp_path / "reduced_rank_proxy.json"
    reduced_rank_proxy_sweep = tmp_path / "reduced_rank_proxy_sweep.json"
    reduced_rank_crash_backtest = tmp_path / "reduced_rank_crash_backtest.json"
    reduced_rank_confirmation_overlap = tmp_path / "reduced_rank_confirmation_overlap.json"
    rl_governance = tmp_path / "rl_governance.json"
    llm_state_reward_interface = tmp_path / "llm_state_reward_interface.json"
    llm_state_reward_diagnostic_refinement = tmp_path / "llm_state_reward_diagnostic_refinement.json"
    llm_state_reward_shadow_training_readiness = tmp_path / "llm_state_reward_shadow_training_readiness.json"
    llm_state_reward_regime_filtered_micro_tilt = tmp_path / "llm_state_reward_regime_filtered_micro_tilt.json"
    llm_state_reward_manual_approval_readiness = tmp_path / "llm_state_reward_manual_approval_readiness.json"
    llm_state_reward_signed_approval_validation = tmp_path / "llm_state_reward_signed_approval_validation.json"
    finstressts.write_text(
        json.dumps({"status": "blocked", "decision": {"allow_00631l_add": False}}),
        encoding="utf-8",
    )
    trigate.write_text(
        json.dumps(
            {
                "tri_gate_state": {"state": "blocked_for_leverage_add", "stress_gate_count": 3},
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    systemic.write_text(
        json.dumps(
            {
                "states": {"overall_state": "blocked_for_leverage_add", "systemic_score": 2},
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    illiquidity.write_text(
        json.dumps(
            {
                "status": "blocked",
                "daily_ohlcv_liquidity_stress_proxy": {
                    "status": "available_research_proxy",
                    "paper_equivalent": False,
                    "stress_score": 0.21,
                    "stress_state": "elevated",
                    "manual_review_required": True,
                    "coverage_tickers": 9,
                },
                "decision": {
                    "illiquidity_network_ready": False,
                    "crash_guard_allowed": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    speculative.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "speculative_influence_network_ready": False,
                    "hmm_bubble_state_ready": False,
                    "transfer_entropy_network_ready": False,
                    "maxloss_validation_ready": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    sin_lite.write_text(
        json.dumps(
            {
                "status": "blocked",
                "latest": {
                    "state": "normal",
                    "sin_lite_score": 0.38,
                    "manual_review_required": False,
                },
                "coverage": {"usable_ticker_count": 14},
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    hmm_wj.write_text(
        json.dumps(
            {
                "status": "blocked",
                "data_readiness": {"all_required_tickers_ready": True},
                "decision": {"can_generate_scenarios_for_decision": False, "allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    dynamic_cvar.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "tail_cost_readiness_ready": False,
                    "dynamic_optimizer_ready": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    synthetic_augmentation.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "synthetic_validation_ready": False,
                    "directional_synthetic_alpha_allowed": False,
                    "synthetic_generator_promotion_allowed": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    intervention_fatigue.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "intervention_fatigue_ready": False,
                    "risk_budget_pacing_ready": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    letf_tracking.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "tracking_error_readiness_ready": False,
                    "realized_effective_fee_proxy_ready": False,
                    "hedge_neutrality_ready": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    asian_etf_tail.write_text(
        json.dumps(
            {
                "status": "blocked",
                "data_readiness": {"paper_etf_coverage": {"available_paper_etf_count": 1}},
                "decision": {
                    "tail_analytics_ready": False,
                    "optimizer_ready": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    reduced_rank.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "reduced_rank_correlation_ready": False,
                    "weak_proxy_ready_for_research": True,
                    "paper_equivalent_ready": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    reduced_rank_proxy.write_text(
        json.dumps(
            {
                "status": "available_for_manual_review",
                "latest": {"state": "normal", "manual_review_required": False},
                "coverage": {"usable_ticker_count": 36},
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    reduced_rank_proxy_sweep.write_text(
        json.dumps(
            {
                "status": "blocked",
                "grid": {"available_candidate_count": 24},
                "aggregate": {"available_state_counts": {"normal": 16, "watch": 8}, "manual_review_candidate_count": 8},
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    reduced_rank_crash_backtest.write_text(
        json.dumps(
            {
                "status": "blocked",
                "aggregate": {
                    "stress_window_watch_or_worse_rate": 0.25,
                    "non_window_watch_or_worse_rate": 0.42,
                    "stress_window_elevated_or_worse_rate": 0.02,
                    "non_window_elevated_or_worse_rate": 0.19,
                },
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    reduced_rank_confirmation_overlap.write_text(
        json.dumps(
            {
                "status": "blocked",
                "summary": {
                    "confirmed_reduced_rank": {
                        "stress_watch_or_worse_rate": 0.19,
                        "non_window_watch_or_worse_rate": 0.08,
                        "stress_to_non_rate_ratio": 2.27,
                    }
                },
                "decision": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    rl_governance.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "rl_governance_ready": False,
                    "rl_component_promotable": False,
                    "live_rl_allocator_allowed": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_interface.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {
                    "llm_state_reward_interface_ready": False,
                    "feature_proposal_governance_imported": True,
                    "reward_shaping_governance_imported": True,
                    "live_llm_trading_allowed": False,
                    "live_ppo_allocator_allowed": False,
                    "allow_00631l_add": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_diagnostic_refinement.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "mean_reward_snr": 2.15,
                    "mean_reward_future_return_alignment": -0.0142,
                    "mean_reward_future_downside_alignment": -0.04,
                    "reward_alignment_grade": "red",
                    "ppo_training_queue_allowed_by_alignment": False,
                },
                "warning_reasons": ["weak_reward_future_return_alignment:-0.0142"],
                "decision": {
                    "diagnostic_refinement_ready_for_research_review": True,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_shadow_training_readiness.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "warning_reasons": ["cost_warning_resolved_by_regime_filtered_micro_tilt"],
                "decision": {
                    "shadow_training_ready": True,
                    "shadow_training_request_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_regime_filtered_micro_tilt.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "recommended_candidate": {
                        "regime_rule": "trend_above_train_median",
                        "high_score": 1.03,
                        "cost_bps": 5.0,
                        "aggregate": {
                            "positive_final_value_folds": 5,
                            "positive_sharpe_folds": 4,
                            "non_worse_drawdown_folds": 4,
                        },
                    },
                },
                "decision": {
                    "regime_filter_resolves_5bps_warning": True,
                    "model_training_allowed": False,
                    "promote_to_live": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_manual_approval_readiness.write_text(
        json.dumps(
            {
                "status": "available_for_manual_approval_review",
                "training_queue_blocking_reasons": [
                    "signed_human_exception_approval_record_missing_or_invalid",
                ],
                "decision": {
                    "manual_approval_review_ready": True,
                    "manual_approval_to_queue_training_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_state_reward_signed_approval_validation.write_text(
        json.dumps(
            {
                "status": "blocked",
                "blocking_reasons": ["missing_signed_human_exception_approval_record"],
                "decision": {
                    "signed_approval_record_valid": False,
                    "human_exception_approved": False,
                    "non_ppo_shadow_queue_review_allowed": False,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_snapshot(
        finstressts_path=finstressts,
        trigate_path=trigate,
        systemic_bubble_path=systemic,
        illiquidity_network_path=illiquidity,
        speculative_influence_path=speculative,
        sin_lite_proxy_path=sin_lite,
        hmm_wj_path=hmm_wj,
        dynamic_cvar_path=dynamic_cvar,
        synthetic_augmentation_path=synthetic_augmentation,
        intervention_fatigue_path=intervention_fatigue,
        letf_tracking_path=letf_tracking,
        asian_etf_tail_analytics_path=asian_etf_tail,
        reduced_rank_correlation_path=reduced_rank,
        reduced_rank_proxy_path=reduced_rank_proxy,
        reduced_rank_proxy_sweep_path=reduced_rank_proxy_sweep,
        reduced_rank_crash_backtest_path=reduced_rank_crash_backtest,
        reduced_rank_confirmation_overlap_path=reduced_rank_confirmation_overlap,
        rl_governance_path=rl_governance,
        llm_state_reward_interface_path=llm_state_reward_interface,
        llm_state_reward_diagnostic_refinement_path=llm_state_reward_diagnostic_refinement,
        llm_state_reward_shadow_training_readiness_path=llm_state_reward_shadow_training_readiness,
        llm_state_reward_regime_filtered_micro_tilt_path=llm_state_reward_regime_filtered_micro_tilt,
        llm_state_reward_manual_approval_readiness_path=llm_state_reward_manual_approval_readiness,
        llm_state_reward_signed_approval_validation_path=llm_state_reward_signed_approval_validation,
    )

    assert snapshot["status"] == "blocked"
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert snapshot["decision"]["allow_00632r_open"] is False
    assert "finstressts_snapshot_blocked" in snapshot["blocking_reasons"]
    assert "trigate_vol_memory_blocks_leverage_add" in snapshot["blocking_reasons"]
    assert "systemic_bubble_time_at_risk_blocks_leverage_add" in snapshot["blocking_reasons"]
    assert "illiquidity_network_readiness_blocked" in snapshot["blocking_reasons"]
    assert "speculative_influence_network_readiness_blocked" in snapshot["blocking_reasons"]
    assert "sin_lite_proxy_blocked" in snapshot["blocking_reasons"]
    assert "hmm_wj_synthetic_scenario_readiness_blocked" in snapshot["blocking_reasons"]
    assert "dynamic_cvar_tail_cost_readiness_blocked" in snapshot["blocking_reasons"]
    assert "synthetic_augmentation_validation_readiness_blocked" in snapshot["blocking_reasons"]
    assert "intervention_fatigue_risk_budget_readiness_blocked" in snapshot["blocking_reasons"]
    assert "letf_tracking_error_effective_fee_readiness_blocked" in snapshot["blocking_reasons"]
    assert "asian_etf_tail_analytics_readiness_blocked" in snapshot["blocking_reasons"]
    assert "reduced_rank_correlation_readiness_blocked" in snapshot["blocking_reasons"]
    assert "llm_state_reward_interface_readiness_blocked" in snapshot["blocking_reasons"]
    assert snapshot["summary"]["systemic_bubble_score"] == 2
    assert snapshot["summary"]["illiquidity_network_ready"] is False
    assert snapshot["summary"]["illiquidity_network_crash_guard_allowed"] is False
    assert snapshot["summary"]["illiquidity_daily_proxy_status"] == "available_research_proxy"
    assert snapshot["summary"]["illiquidity_daily_proxy_stress_score"] == 0.21
    assert snapshot["summary"]["illiquidity_daily_proxy_stress_state"] == "elevated"
    assert snapshot["summary"]["illiquidity_daily_proxy_manual_review_required"] is True
    assert snapshot["summary"]["speculative_influence_network_status"] == "blocked"
    assert snapshot["summary"]["speculative_influence_network_ready"] is False
    assert snapshot["summary"]["speculative_influence_hmm_bubble_state_ready"] is False
    assert snapshot["summary"]["speculative_influence_transfer_entropy_ready"] is False
    assert snapshot["summary"]["speculative_influence_maxloss_validation_ready"] is False
    assert snapshot["summary"]["sin_lite_proxy_state"] == "normal"
    assert snapshot["summary"]["sin_lite_proxy_score"] == 0.38
    assert snapshot["summary"]["sin_lite_proxy_usable_ticker_count"] == 14
    assert snapshot["summary"]["hmm_wj_data_ready"] is True
    assert snapshot["summary"]["dynamic_cvar_tail_cost_ready"] is False
    assert snapshot["summary"]["dynamic_cvar_optimizer_ready"] is False
    assert snapshot["summary"]["synthetic_validation_ready"] is False
    assert snapshot["summary"]["directional_synthetic_alpha_allowed"] is False
    assert snapshot["summary"]["intervention_fatigue_ready"] is False
    assert snapshot["summary"]["risk_budget_pacing_ready"] is False
    assert snapshot["summary"]["letf_tracking_error_readiness_ready"] is False
    assert snapshot["summary"]["letf_effective_fee_proxy_ready"] is False
    assert snapshot["summary"]["letf_hedge_neutrality_ready"] is False
    assert snapshot["summary"]["asian_etf_tail_analytics_ready"] is False
    assert snapshot["summary"]["asian_etf_available_paper_etf_count"] == 1
    assert snapshot["summary"]["reduced_rank_correlation_status"] == "blocked"
    assert snapshot["summary"]["reduced_rank_correlation_ready"] is False
    assert snapshot["summary"]["reduced_rank_weak_proxy_ready"] is True
    assert snapshot["summary"]["reduced_rank_paper_equivalent_ready"] is False
    assert snapshot["summary"]["reduced_rank_allow_00631l_add"] is False
    assert snapshot["summary"]["reduced_rank_proxy_status"] == "available_for_manual_review"
    assert snapshot["summary"]["reduced_rank_proxy_state"] == "normal"
    assert snapshot["summary"]["reduced_rank_proxy_manual_review_required"] is False
    assert snapshot["summary"]["reduced_rank_proxy_usable_ticker_count"] == 36
    assert snapshot["summary"]["reduced_rank_proxy_allow_00631l_add"] is False
    assert snapshot["summary"]["reduced_rank_proxy_sweep_status"] == "blocked"
    assert snapshot["summary"]["reduced_rank_proxy_sweep_available_candidate_count"] == 24
    assert snapshot["summary"]["reduced_rank_proxy_sweep_state_counts"] == {"normal": 16, "watch": 8}
    assert snapshot["summary"]["reduced_rank_proxy_sweep_manual_review_candidate_count"] == 8
    assert snapshot["summary"]["reduced_rank_proxy_sweep_allow_00631l_add"] is False
    assert snapshot["summary"]["reduced_rank_crash_backtest_status"] == "blocked"
    assert snapshot["summary"]["reduced_rank_crash_backtest_stress_watch_rate"] == 0.25
    assert snapshot["summary"]["reduced_rank_crash_backtest_non_window_watch_rate"] == 0.42
    assert snapshot["summary"]["reduced_rank_crash_backtest_stress_elevated_rate"] == 0.02
    assert snapshot["summary"]["reduced_rank_crash_backtest_non_window_elevated_rate"] == 0.19
    assert snapshot["summary"]["reduced_rank_crash_backtest_allow_00631l_add"] is False
    assert snapshot["summary"]["reduced_rank_confirmation_overlap_status"] == "blocked"
    assert snapshot["summary"]["reduced_rank_confirmed_stress_watch_rate"] == 0.19
    assert snapshot["summary"]["reduced_rank_confirmed_non_window_watch_rate"] == 0.08
    assert snapshot["summary"]["reduced_rank_confirmed_stress_to_non_ratio"] == 2.27
    assert snapshot["summary"]["reduced_rank_confirmation_overlap_allow_00631l_add"] is False
    assert snapshot["summary"]["rl_governance_status"] == "blocked"
    assert snapshot["summary"]["rl_governance_ready"] is False
    assert snapshot["summary"]["rl_component_promotable"] is False
    assert snapshot["summary"]["live_rl_allocator_allowed"] is False
    assert snapshot["summary"]["rl_governance_allow_00631l_add"] is False
    assert snapshot["summary"]["llm_state_reward_interface_status"] == "blocked"
    assert snapshot["summary"]["llm_state_reward_interface_ready"] is False
    assert snapshot["summary"]["feature_proposal_governance_imported"] is True
    assert snapshot["summary"]["reward_shaping_governance_imported"] is True
    assert snapshot["summary"]["live_llm_trading_allowed"] is False
    assert snapshot["summary"]["live_ppo_allocator_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_interface_allow_00631l_add"] is False
    assert snapshot["summary"]["llm_state_reward_diagnostic_refinement_status"] == "available_for_manual_offline_review"
    assert snapshot["summary"]["llm_state_reward_diagnostic_refinement_ready"] is True
    assert snapshot["summary"]["llm_state_reward_diagnostic_mean_reward_snr"] == 2.15
    assert snapshot["summary"]["llm_state_reward_diagnostic_mean_reward_future_return_alignment"] == -0.0142
    assert snapshot["summary"]["llm_state_reward_diagnostic_mean_reward_future_downside_alignment"] == -0.04
    assert snapshot["summary"]["llm_state_reward_diagnostic_grade"] == "red"
    assert snapshot["summary"]["llm_state_reward_diagnostic_ppo_training_queue_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_diagnostic_warning_count"] == 1
    assert snapshot["summary"]["llm_state_reward_diagnostic_allow_00631l_add"] is False
    assert snapshot["summary"]["llm_state_reward_diagnostic_allow_00632r_open"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_readiness_status"] == (
        "available_for_manual_offline_review"
    )
    assert snapshot["summary"]["llm_state_reward_shadow_training_ready"] is True
    assert snapshot["summary"]["llm_state_reward_shadow_training_request_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_model_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_ppo_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_promote_to_live"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_allow_00631l_add"] is False
    assert snapshot["summary"]["llm_state_reward_shadow_training_allow_00632r_open"] is False
    assert snapshot["summary"]["llm_state_reward_regime_filtered_micro_tilt_status"] == (
        "available_for_manual_offline_review"
    )
    assert snapshot["summary"]["llm_state_reward_regime_filter_resolves_5bps_warning"] is True
    assert (
        snapshot["summary"]["llm_state_reward_regime_filtered_recommended_candidate"]["regime_rule"]
        == "trend_above_train_median"
    )
    assert snapshot["summary"]["llm_state_reward_regime_filtered_model_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_regime_filtered_promote_to_live"] is False
    assert snapshot["summary"]["llm_state_reward_manual_approval_readiness_status"] == (
        "available_for_manual_approval_review"
    )
    assert snapshot["summary"]["llm_state_reward_manual_approval_review_ready"] is True
    assert snapshot["summary"]["llm_state_reward_manual_approval_to_queue_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_manual_approval_queue_blocking_reasons"] == [
        "signed_human_exception_approval_record_missing_or_invalid",
    ]
    assert snapshot["summary"]["llm_state_reward_manual_approval_model_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_manual_approval_ppo_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_manual_approval_promote_to_live"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_validation_status"] == "blocked"
    assert snapshot["summary"]["llm_state_reward_signed_approval_record_valid"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_human_exception_approved"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_training_queue_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_model_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_ppo_training_allowed"] is False
    assert snapshot["summary"]["llm_state_reward_signed_approval_promote_to_live"] is False
    assert "llm_state_reward_diagnostic_refinement_status:available_for_manual_offline_review" in snapshot[
        "warning_reasons"
    ]
    assert (
        "llm_state_reward_diagnostic_refinement:weak_reward_future_return_alignment:-0.0142"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_shadow_training_readiness_status:available_for_manual_offline_review"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_shadow_training_readiness:cost_warning_resolved_by_regime_filtered_micro_tilt"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_regime_filtered_micro_tilt_status:available_for_manual_offline_review"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_manual_approval_readiness_status:available_for_manual_approval_review"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_manual_approval_readiness:signed_human_exception_approval_record_missing_or_invalid"
        in snapshot["warning_reasons"]
    )
    assert "llm_state_reward_signed_approval_validation_blocked" in snapshot["warning_reasons"]
    assert (
        "llm_state_reward_signed_approval_validation_status:blocked"
        in snapshot["warning_reasons"]
    )
    assert (
        "llm_state_reward_signed_approval_validation:missing_signed_human_exception_approval_record"
        in snapshot["warning_reasons"]
    )


def test_write_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    snapshot = {"report_type": "group_a_plus_research_shadow_decision_snapshot"}

    write_snapshot(snapshot, output)

    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
