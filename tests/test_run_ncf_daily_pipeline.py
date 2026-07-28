from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import duckdb
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run" / "run_ncf_daily_pipeline.py"
    spec = importlib.util.spec_from_file_location("_test_run_ncf_daily_pipeline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _command_args(**overrides) -> argparse.Namespace:
    values = {
        "date_stamp": "20260627",
        "skip_refresh": False,
        "force_refresh": True,
        "refresh_target_date": "auto",
        "strict_refresh": False,
        "skip_shareholding": False,
        "chip_start": "2026-06-06",
        "chip_end": "2026-06-27",
        "per_start": "2023-06-27",
        "ohlcv_target_date": "auto",
        "max_ohlcv_lag_days": 3,
        "fail_on_ohlcv_warning": False,
        "train_start_00631l": "2020-01-01",
        "train_start_00632r": "2015-01-01",
        "val_start": "2025-01-02",
        "val_end": "latest",
        "no_external_features": False,
        "refresh_external_cache": False,
        "checklist_external_start": "2023-07-02",
        "checklist_external_end": "2026-07-03",
        "db": "/nonexistent/path/stock_data.db",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_daily_pipeline_does_not_write_golden1_0531_release_artifacts() -> None:
    module = _load_module()
    commands = module.build_commands(_command_args())

    protected = {module._normalize_project_path(path) for path in module.PROTECTED_GOLDEN1_RELEASE_ARTIFACTS}
    output_targets = []
    for cmd in commands.values():
        for index, token in enumerate(cmd[:-1]):
            if token in module.OUTPUT_TARGET_FLAGS:
                output_targets.append(module._normalize_project_path(cmd[index + 1]))

    assert protected.isdisjoint(output_targets)


def test_daily_pipeline_blocks_golden1_0531_release_output_target() -> None:
    module = _load_module()
    protected = module.PROJECT_ROOT / "results" / "group_a_release_Golden1_0531.json"
    commands = {
        "bad_step": [
            "python",
            "some_script.py",
            "--output",
            str(protected),
        ]
    }

    with pytest.raises(ValueError, match="protected Golden1_0531 release"):
        module._assert_no_protected_golden1_output_targets(commands)


def test_build_commands_includes_refresh_ncf_and_advisory_steps() -> None:
    module = _load_module()
    args = _command_args()

    commands = module.build_commands(args)

    assert list(commands) == [
        "refresh_group_data",
        "refresh_taifex",
        "refresh_taifex_options",
        "refresh_institutional",
        "refresh_margin",
        "refresh_market_margin",
        "refresh_derivative_institutional",
        "refresh_securities_lending",
        "securities_lending_0050_source_status",
        "refresh_dealer_positions",
        "refresh_foreign_shareholding",
        "refresh_short_sale_balances",
        "refresh_day_trading",
        "refresh_soxx_options_iv",
        "refresh_cross_market_ohlcv",
        "refresh_2330_per",
        "refresh_shareholding",
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "ncf_signal_archive",
        "ncf_2330",
        "ncf_panel_manifest",
        "ncf_panel_drift",
        "ncf_panel_drift_diagnosis",
        "panel_drift_triage",
        "ncf_panel_drift_remediation_plan_initial",
        "external_sensitivity_observation_log",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
        "compounding_regime",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "cvar_tail_risk_diagnostic",
        "network_volatility_spillover_shadow",
        "option_state_coverage_review",
        "adversarial_market_integrity_review",
        "sciphyrl_readiness_review",
        "market_impact_readiness_review",
        "finstressts_readiness_review",
        "finstressts_counterfactual_shadow",
        "finstressts_baseline_compare_shadow",
        "finstressts_decision_snapshot",
        "trigate_vol_memory_shadow",
        "systemic_bubble_time_at_risk_review",
        "illiquidity_network_readiness_review",
        "speculative_influence_network_readiness_review",
        "sin_lite_proxy",
        "hmm_wj_synthetic_scenario_readiness_review",
        "dynamic_cvar_tail_cost_readiness_review",
        "synthetic_augmentation_validation_audit",
        "synthetic_augmentation_validation_readiness_review",
        "intervention_history",
        "broker_holdings_time_series_sample",
        "broker_holdings_reconciliation_review",
        "intervention_fatigue_risk_budget_readiness_review",
        "letf_tracking_error_effective_fee_readiness_review",
        "asian_etf_tail_analytics_readiness_review",
        "gift_human_exception_record_draft",
        "gift_human_exception_approval_record_schema",
        "gift_signed_approval_record_template",
        "gift_signed_approval_validation",
        "gift_signed_approval_checklist_review",
        "gift_signed_approval_validator_smoke",
        "gift_manual_approval_readiness",
        "gift_pdf_advantage_coverage_review",
        "research_shadow_decision_snapshot",
        "dfl_advisory",
        "dfl_active_date_audit",
        "dfl_shadow_ensemble",
        "daily_status",
        "deployment_consistency_review",
        "deployment_summary",
        "promotion_gate",
        "multi_window_failure_attribution",
        "promotion_blocked_diagnostic",
        "daily_status_final",
        "final_governance_snapshot",
        "ncf_2330_checklist",
    ]
    assert commands["refresh_group_data"][-1] == "--force"
    assert commands["a2120_shadow_pipeline"][1] == "scripts/run/run_a2120_daily_shadow_pipeline.py"
    assert commands["a2120_shadow_pipeline"][commands["a2120_shadow_pipeline"].index("--date-stamp") + 1] == "20260627"
    assert "a2120_shadow_pipeline" in module.BEST_EFFORT_STEP_NAMES
    assert commands["recovery_boost_spillover_gate_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py"
    )
    assert commands["recovery_boost_spillover_gate_shadow_log"][
        commands["recovery_boost_spillover_gate_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "recovery_boost_spillover_gate_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert commands["trough_override_eligibility_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_trough_override_eligibility_shadow_log.py"
    )
    assert commands["trough_override_eligibility_shadow_log"][
        commands["trough_override_eligibility_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "trough_override_eligibility_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert commands["cvar_tail_risk_diagnostic"][1] == (
        "scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py"
    )
    assert "cvar_tail_risk_diagnostic" in module.BEST_EFFORT_STEP_NAMES
    assert commands["network_volatility_spillover_shadow"][1] == (
        "scripts/evaluate/build_group_a_plus_network_volatility_spillover_shadow.py"
    )
    assert commands["network_volatility_spillover_shadow"][
        commands["network_volatility_spillover_shadow"].index("--end") + 1
    ] == "2026-06-27"
    assert "network_volatility_spillover_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["option_state_coverage_review"][1] == (
        "scripts/evaluate/build_group_a_plus_option_state_coverage_review.py"
    )
    assert commands["option_state_coverage_review"][
        commands["option_state_coverage_review"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "option_state_coverage_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["adversarial_market_integrity_review"][1] == (
        "scripts/evaluate/build_group_a_plus_adversarial_market_integrity_review.py"
    )
    assert commands["adversarial_market_integrity_review"][
        commands["adversarial_market_integrity_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/adversarial_market_integrity_review.json")
    assert "adversarial_market_integrity_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["sciphyrl_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_sciphyrl_readiness_review.py"
    )
    assert commands["sciphyrl_readiness_review"][
        commands["sciphyrl_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/sciphyrl_readiness_review.json")
    assert "sciphyrl_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["market_impact_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_market_impact_readiness_review.py"
    )
    assert commands["market_impact_readiness_review"][
        commands["market_impact_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/market_impact_readiness_review.json")
    assert "market_impact_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["finstressts_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py"
    )
    assert commands["finstressts_readiness_review"][
        commands["finstressts_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/finstressts_readiness_review.json")
    assert "finstressts_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["deployment_consistency_review"][1] == (
        "scripts/evaluate/build_group_a_plus_deployment_consistency_review.py"
    )
    assert commands["deployment_consistency_review"][
        commands["deployment_consistency_review"].index("--securities-lending-source-status") + 1
    ].endswith("report/group_a_plus/latest/securities_lending_0050_source_status.json")
    assert commands["deployment_consistency_review"][
        commands["deployment_consistency_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/deployment_consistency_review.json")
    assert "deployment_consistency_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["deployment_summary"][1] == "scripts/evaluate/build_group_a_plus_deployment_summary.py"
    assert commands["deployment_summary"][
        commands["deployment_summary"].index("--deployment") + 1
    ].endswith("report/group_a_plus/latest/deployment_consistency_review.json")
    assert commands["deployment_summary"][
        commands["deployment_summary"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/deployment_summary.json")
    assert "deployment_summary" in module.BEST_EFFORT_STEP_NAMES
    assert commands["finstressts_counterfactual_shadow"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py"
    )
    assert commands["finstressts_counterfactual_shadow"][
        commands["finstressts_counterfactual_shadow"].index("--output") + 1
    ].endswith("results/group_a_plus_finstressts_counterfactual_shadow_20260627.json")
    assert commands["finstressts_counterfactual_shadow"][
        commands["finstressts_counterfactual_shadow"].index("--latest") + 1
    ].endswith("report/group_a_plus/latest/finstressts_counterfactual_shadow.json")
    assert "finstressts_counterfactual_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["finstressts_baseline_compare_shadow"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py"
    )
    assert commands["finstressts_baseline_compare_shadow"][
        commands["finstressts_baseline_compare_shadow"].index("--output") + 1
    ].endswith("results/group_a_plus_finstressts_baseline_compare_shadow_20260627.json")
    assert commands["finstressts_baseline_compare_shadow"][
        commands["finstressts_baseline_compare_shadow"].index("--latest") + 1
    ].endswith("report/group_a_plus/latest/finstressts_baseline_compare_shadow.json")
    assert "finstressts_baseline_compare_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["finstressts_decision_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plus_finstressts_decision_snapshot.py"
    )
    assert commands["finstressts_decision_snapshot"][
        commands["finstressts_decision_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/finstressts_decision_snapshot.json")
    assert "finstressts_decision_snapshot" in module.BEST_EFFORT_STEP_NAMES
    assert commands["securities_lending_0050_source_status"][1] == (
        "scripts/evaluate/build_group_a_plus_securities_lending_source_status.py"
    )
    assert commands["securities_lending_0050_source_status"][
        commands["securities_lending_0050_source_status"].index("--query-end") + 1
    ] == "2026-06-27"
    assert commands["securities_lending_0050_source_status"][
        commands["securities_lending_0050_source_status"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/securities_lending_0050_source_status.json")
    assert "securities_lending_0050_source_status" in module.BEST_EFFORT_STEP_NAMES
    assert commands["trigate_vol_memory_shadow"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py"
    )
    assert commands["trigate_vol_memory_shadow"][
        commands["trigate_vol_memory_shadow"].index("--output") + 1
    ].endswith("results/group_a_plus_trigate_vol_memory_shadow_20260627.json")
    assert commands["trigate_vol_memory_shadow"][
        commands["trigate_vol_memory_shadow"].index("--latest") + 1
    ].endswith("report/group_a_plus/latest/trigate_vol_memory_shadow.json")
    assert "trigate_vol_memory_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["systemic_bubble_time_at_risk_review"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py"
    )
    assert commands["systemic_bubble_time_at_risk_review"][
        commands["systemic_bubble_time_at_risk_review"].index("--output") + 1
    ].endswith("results/group_a_plus_systemic_bubble_time_at_risk_review_20260627.json")
    assert commands["systemic_bubble_time_at_risk_review"][
        commands["systemic_bubble_time_at_risk_review"].index("--latest") + 1
    ].endswith("report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json")
    assert "systemic_bubble_time_at_risk_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["illiquidity_network_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py"
    )
    assert commands["illiquidity_network_readiness_review"][
        commands["illiquidity_network_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/illiquidity_network_readiness_review.json")
    assert "illiquidity_network_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["speculative_influence_network_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_speculative_influence_network_readiness_review.py"
    )
    assert commands["speculative_influence_network_readiness_review"][
        commands["speculative_influence_network_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/speculative_influence_network_readiness_review.json")
    assert "speculative_influence_network_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["sin_lite_proxy"][1] == "scripts/evaluate/build_group_a_plus_sin_lite_proxy.py"
    assert commands["sin_lite_proxy"][commands["sin_lite_proxy"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/sin_lite_proxy.json"
    )
    assert "sin_lite_proxy" in module.BEST_EFFORT_STEP_NAMES
    assert commands["hmm_wj_synthetic_scenario_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py"
    )
    assert commands["hmm_wj_synthetic_scenario_readiness_review"][
        commands["hmm_wj_synthetic_scenario_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json")
    assert "hmm_wj_synthetic_scenario_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["dynamic_cvar_tail_cost_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py"
    )
    assert commands["dynamic_cvar_tail_cost_readiness_review"][
        commands["dynamic_cvar_tail_cost_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert "dynamic_cvar_tail_cost_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["synthetic_augmentation_validation_audit"][1] == (
        "scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_audit.py"
    )
    assert commands["synthetic_augmentation_validation_audit"][
        commands["synthetic_augmentation_validation_audit"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["synthetic_augmentation_validation_audit"][
        commands["synthetic_augmentation_validation_audit"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["synthetic_augmentation_validation_audit"][
        commands["synthetic_augmentation_validation_audit"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/synthetic_augmentation_validation_audit.json")
    assert "synthetic_augmentation_validation_audit" in module.BEST_EFFORT_STEP_NAMES
    assert commands["synthetic_augmentation_validation_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py"
    )
    assert commands["synthetic_augmentation_validation_readiness_review"][
        commands["synthetic_augmentation_validation_readiness_review"].index("--validation-audit") + 1
    ].endswith("report/group_a_plus/latest/synthetic_augmentation_validation_audit.json")
    assert commands["synthetic_augmentation_validation_readiness_review"][
        commands["synthetic_augmentation_validation_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json")
    assert "synthetic_augmentation_validation_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["intervention_history"][1] == (
        "scripts/evaluate/build_group_a_plus_intervention_history_from_daily_status.py"
    )
    assert commands["intervention_history"][
        commands["intervention_history"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/intervention_history.json")
    assert "intervention_history" in module.BEST_EFFORT_STEP_NAMES
    assert commands["broker_holdings_time_series_sample"][1] == (
        "scripts/evaluate/build_group_a_plus_broker_holdings_time_series_sample.py"
    )
    assert commands["broker_holdings_time_series_sample"][
        commands["broker_holdings_time_series_sample"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_time_series_sample.json")
    assert "broker_holdings_time_series_sample" in module.BEST_EFFORT_STEP_NAMES
    assert commands["broker_holdings_reconciliation_review"][1] == (
        "scripts/evaluate/build_group_a_plus_broker_holdings_reconciliation_review.py"
    )
    assert commands["broker_holdings_reconciliation_review"][
        commands["broker_holdings_reconciliation_review"].index("--sample") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_time_series_sample.json")
    assert commands["broker_holdings_reconciliation_review"][
        commands["broker_holdings_reconciliation_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_reconciliation_review.json")
    assert "broker_holdings_reconciliation_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["intervention_fatigue_risk_budget_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py"
    )
    assert commands["intervention_fatigue_risk_budget_readiness_review"][
        commands["intervention_fatigue_risk_budget_readiness_review"].index("--intervention-history") + 1
    ].endswith("report/group_a_plus/latest/intervention_history.json")
    assert commands["intervention_fatigue_risk_budget_readiness_review"][
        commands["intervention_fatigue_risk_budget_readiness_review"].index("--broker-holdings-history") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_time_series_sample.json")
    assert commands["intervention_fatigue_risk_budget_readiness_review"][
        commands["intervention_fatigue_risk_budget_readiness_review"].index("--broker-reconciliation") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_reconciliation_review.json")
    assert commands["intervention_fatigue_risk_budget_readiness_review"][
        commands["intervention_fatigue_risk_budget_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json")
    assert "intervention_fatigue_risk_budget_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["letf_tracking_error_effective_fee_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py"
    )
    assert commands["letf_tracking_error_effective_fee_readiness_review"][
        commands["letf_tracking_error_effective_fee_readiness_review"].index("--intervention-fatigue") + 1
    ].endswith("report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json")
    assert commands["letf_tracking_error_effective_fee_readiness_review"][
        commands["letf_tracking_error_effective_fee_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json")
    assert "letf_tracking_error_effective_fee_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["asian_etf_tail_analytics_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py"
    )
    assert commands["asian_etf_tail_analytics_readiness_review"][
        commands["asian_etf_tail_analytics_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json")
    assert "asian_etf_tail_analytics_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_human_exception_record_draft"][1] == (
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_record_draft.py"
    )
    assert commands["gift_human_exception_record_draft"][
        commands["gift_human_exception_record_draft"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_human_exception_record_draft" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_human_exception_approval_record_schema"][1] == (
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_approval_record_schema.py"
    )
    assert commands["gift_human_exception_approval_record_schema"][
        commands["gift_human_exception_approval_record_schema"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_human_exception_approval_record_schema" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_signed_approval_record_template"][1] == (
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_signed_approval_record_template.py"
    )
    assert commands["gift_signed_approval_record_template"][
        commands["gift_signed_approval_record_template"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_signed_approval_record_template" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_signed_approval_validation"][1] == (
        "scripts/evaluate/validate_group_a_plus_llm_state_reward_human_exception_signed_approval_record.py"
    )
    assert commands["gift_signed_approval_validation"][
        commands["gift_signed_approval_validation"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_signed_approval_validation" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_signed_approval_checklist_review"][1] == (
        "scripts/evaluate/build_group_a_plus_gift_signed_approval_checklist_review.py"
    )
    assert commands["gift_signed_approval_checklist_review"][
        commands["gift_signed_approval_checklist_review"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_signed_approval_checklist_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_signed_approval_validator_smoke"][1] == (
        "scripts/evaluate/build_group_a_plus_gift_signed_approval_validator_smoke.py"
    )
    assert commands["gift_signed_approval_validator_smoke"][
        commands["gift_signed_approval_validator_smoke"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_signed_approval_validator_smoke" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_manual_approval_readiness"][1] == (
        "scripts/evaluate/build_group_a_plus_llm_state_reward_manual_approval_readiness_review.py"
    )
    assert commands["gift_manual_approval_readiness"][
        commands["gift_manual_approval_readiness"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_manual_approval_readiness" in module.BEST_EFFORT_STEP_NAMES
    assert commands["gift_pdf_advantage_coverage_review"][1] == (
        "scripts/evaluate/build_group_a_plus_gift_pdf_advantage_coverage_review.py"
    )
    assert commands["gift_pdf_advantage_coverage_review"][
        commands["gift_pdf_advantage_coverage_review"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "gift_pdf_advantage_coverage_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["research_shadow_decision_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py"
    )
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--systemic-bubble") + 1
    ].endswith("report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--illiquidity-network") + 1
    ].endswith("report/group_a_plus/latest/illiquidity_network_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--speculative-influence") + 1
    ].endswith("report/group_a_plus/latest/speculative_influence_network_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--sin-lite-proxy") + 1
    ].endswith("report/group_a_plus/latest/sin_lite_proxy.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--hmm-wj") + 1
    ].endswith("report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--dynamic-cvar") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--synthetic-augmentation") + 1
    ].endswith("report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--intervention-fatigue") + 1
    ].endswith("report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--letf-tracking") + 1
    ].endswith("report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--asian-etf-tail-analytics") + 1
    ].endswith("report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--llm-state-reward-signed-approval-validation") + 1
    ].endswith("report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_validation.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/research_shadow_decision_snapshot.json")
    assert "research_shadow_decision_snapshot" in module.BEST_EFFORT_STEP_NAMES
    assert commands["daily_status"][
        commands["daily_status"].index("--gift-signed-approval-checklist-review") + 1
    ].endswith("report/group_a_plus/latest/gift_signed_approval_checklist_review.json")
    assert commands["daily_status"][
        commands["daily_status"].index("--gift-signed-approval-validator-smoke") + 1
    ].endswith("report/group_a_plus/latest/gift_signed_approval_validator_smoke.json")
    assert any(item.endswith("results/ohlcv_freshness_20260627.json") for item in commands["ohlcv_freshness"])
    assert any(item.endswith("results/ncf_00631l_latest_20260627.json") for item in commands["ncf_00631l"])
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in commands["ncf_00632r"])
    assert "--full-panel" in commands["ncf_00631l"]
    assert "--no-tabnet" in commands["ncf_00631l"]
    assert "--full-panel" in commands["ncf_00632r"]
    assert "--full-panel" in commands["ncf_2330"]
    assert commands["ncf_2330"][commands["ncf_2330"].index("--feature-mode") + 1] == "after_close"
    assert any(item.endswith("results/ncf_2330_panel_latest_20260627.csv") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_panel_manifest_20260627.json") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.json") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.csv") for item in commands["ncf_panel_drift"])
    assert any(
        item.endswith("results/ncf_panel_drift_active_vs_20260627.json")
        for item in commands["ncf_panel_drift_diagnosis"]
    )
    assert any(
        item.endswith("results/ncf_panel_drift_diagnosis_20260627.json")
        for item in commands["ncf_panel_drift_diagnosis"]
    )
    assert commands["ncf_panel_drift_diagnosis"][
        commands["ncf_panel_drift_diagnosis"].index("--baseline-signal") + 1
    ].endswith("results/ncf_00631l_latest_20260630.json")
    assert commands["ncf_panel_drift_diagnosis"][
        commands["ncf_panel_drift_diagnosis"].index("--candidate-signal") + 1
    ].endswith("results/ncf_00631l_latest_20260627.json")
    assert commands["panel_drift_triage"][1] == "scripts/evaluate/build_group_a_plus_panel_drift_triage.py"
    assert commands["panel_drift_triage"][commands["panel_drift_triage"].index("--diagnosis") + 1].endswith(
        "results/ncf_panel_drift_diagnosis_20260627.json"
    )
    assert commands["panel_drift_triage"][commands["panel_drift_triage"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/panel_drift_triage.json"
    )
    assert commands["ncf_panel_drift_remediation_plan_initial"][
        commands["ncf_panel_drift_remediation_plan_initial"].index("--diagnosis") + 1
    ].endswith("results/ncf_panel_drift_diagnosis_20260627.json")
    assert any(
        item.endswith("results/ncf_panel_drift_remediation_plan_initial_20260627.json")
        for item in commands["ncf_panel_drift_remediation_plan_initial"]
    )
    assert commands["external_sensitivity_observation_log"][1] == (
        "scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py"
    )
    assert commands["external_sensitivity_observation_log"][
        commands["external_sensitivity_observation_log"].index("--sensitivity-audit") + 1
    ].endswith("results/ncf_panel_drift_no_external_vs_external_20260627.json")
    assert commands["external_sensitivity_observation_log"][
        commands["external_sensitivity_observation_log"].index("--same-method-baseline-manifest") + 1
    ].endswith("results/ncf_panel_same_method_baseline_manifest_20260627.json")
    assert commands["external_sensitivity_observation_log"][
        commands["external_sensitivity_observation_log"].index("--observation-date") + 1
    ] == "2026-06-27"
    assert commands["external_sensitivity_observation_log"][
        commands["external_sensitivity_observation_log"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/external_sensitivity_observation_log.json")
    assert commands["ncf_panel_external_feature_sensitivity_governance"][
        commands["ncf_panel_external_feature_sensitivity_governance"].index("--sensitivity-audit") + 1
    ].endswith("results/ncf_panel_drift_no_external_vs_external_20260627.json")
    assert commands["ncf_panel_external_feature_sensitivity_governance"][
        commands["ncf_panel_external_feature_sensitivity_governance"].index("--observation-log") + 1
    ].endswith("report/group_a_plus/latest/external_sensitivity_observation_log.json")
    assert "--allow-missing-sensitivity-audit" in commands["ncf_panel_external_feature_sensitivity_governance"]
    assert commands["ncf_panel_drift_remediation_plan"][
        commands["ncf_panel_drift_remediation_plan"].index("--external-sensitivity-governance") + 1
    ].endswith("results/ncf_panel_external_feature_sensitivity_governance_20260627.json")
    assert commands["ncf_panel_drift_remediation_plan"][
        commands["ncf_panel_drift_remediation_plan"].index("--model-set-isolation-report") + 1
    ].endswith("results/ncf_panel_drift_model_set_isolation_report_20260627.json")
    assert commands["ncf_panel_drift_remediation_plan"][
        commands["ncf_panel_drift_remediation_plan"].index("--same-method-baseline-manifest") + 1
    ].endswith("results/ncf_panel_same_method_baseline_manifest_20260627.json")
    assert any(
        item.endswith("results/ncf_panel_drift_remediation_plan_20260627.json")
        for item in commands["ncf_panel_drift_remediation_plan"]
    )
    assert commands["panel_drift_resolution_progress"][1] == (
        "scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py"
    )
    assert commands["panel_drift_resolution_progress"][
        commands["panel_drift_resolution_progress"].index("--remediation-plan") + 1
    ].endswith("results/ncf_panel_drift_remediation_plan_20260627.json")
    assert commands["panel_drift_resolution_progress"][
        commands["panel_drift_resolution_progress"].index("--external-sensitivity-governance") + 1
    ].endswith("results/ncf_panel_external_feature_sensitivity_governance_20260627.json")
    assert any(item.endswith("results/ncf_panel_coverage_20260627.json") for item in commands["ncf_panel_coverage"])
    assert any(
        "ncf_2330_panel_latest_20260627.csv=external_market_ohlcv:yfinance:2330.TW" in item
        for item in commands["ncf_panel_coverage"]
    )
    assert any(item.endswith("results/ncf_advisory_panel_latest_20260627.csv") for item in commands["advisory_panel"])
    assert any(
        item.endswith("results/00631l_leveraged_compounding_regime_20260627.json")
        for item in commands["compounding_regime"]
    )
    assert any(
        item.endswith("results/00631l_leveraged_compounding_regime_20260627.csv")
        for item in commands["compounding_regime"]
    )
    assert commands["dfl_advisory"][1] == "scripts/run/build_a2118_dfl_advisory.py"
    assert "--input" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json"
    )
    assert "--selective-inputs" in commands["dfl_advisory"]
    selective_inputs = commands["dfl_advisory"][commands["dfl_advisory"].index("--selective-inputs") + 1]
    assert "p50=results/a2118_decision_focused_action_shadow_selective_p50_7win_20260714.json" in selective_inputs
    assert "p70=results/a2118_decision_focused_action_shadow_selective_p70_7win_20260714.json" in selective_inputs
    assert "--live-signal" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert commands["dfl_active_date_audit"][1] == "scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py"
    assert "--input" in commands["dfl_active_date_audit"]
    assert commands["dfl_active_date_audit"][commands["dfl_active_date_audit"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json"
    )
    assert any(
        item.endswith("results/a2118_dfl_active_date_audit_20260627.json")
        for item in commands["dfl_active_date_audit"]
    )
    assert commands["dfl_shadow_ensemble"][1] == "scripts/run/build_a2118_dfl_shadow_ensemble_log.py"
    assert "--advisory" in commands["dfl_shadow_ensemble"]
    assert commands["dfl_shadow_ensemble"][commands["dfl_shadow_ensemble"].index("--advisory") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_advisory.json"
    )
    assert "--log" in commands["dfl_shadow_ensemble"]
    assert commands["dfl_shadow_ensemble"][commands["dfl_shadow_ensemble"].index("--log") + 1].endswith(
        "results/a2118_dfl_shadow_ensemble_log.jsonl"
    )
    assert any(item.endswith("results/group_a_plus_daily_status_20260627") for item in commands["daily_status"])
    assert "--execution-plan" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--execution-plan") + 1].endswith(
        "report/group_a_plus/latest/execution_plan.json"
    )
    assert commands["daily_status"][commands["daily_status"].index("--status-stage") + 1] == "pre_promotion"
    assert "--compounding-regime" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--compounding-regime") + 1].endswith(
        "results/00631l_leveraged_compounding_regime_20260627.json"
    )
    assert "--dfl-advisory" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-advisory") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_advisory.json"
    )
    assert "--dfl-shadow-ensemble" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-shadow-ensemble") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json"
    )
    assert "--dfl-active-date-audit" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-active-date-audit") + 1].endswith(
        "results/a2118_dfl_active_date_audit_20260627.json"
    )
    assert "--finstressts-decision-snapshot" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--finstressts-decision-snapshot") + 1].endswith(
        "report/group_a_plus/latest/finstressts_decision_snapshot.json"
    )
    assert "--trigate-vol-memory-shadow" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--trigate-vol-memory-shadow") + 1].endswith(
        "report/group_a_plus/latest/trigate_vol_memory_shadow.json"
    )
    assert "--systemic-bubble-time-at-risk-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--systemic-bubble-time-at-risk-review") + 1
    ].endswith("report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json")
    assert "--illiquidity-network-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--illiquidity-network-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/illiquidity_network_readiness_review.json")
    assert "--speculative-influence-network-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--speculative-influence-network-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/speculative_influence_network_readiness_review.json")
    assert "--sin-lite-proxy" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--sin-lite-proxy") + 1].endswith(
        "report/group_a_plus/latest/sin_lite_proxy.json"
    )
    assert "--hmm-wj-synthetic-scenario-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--hmm-wj-synthetic-scenario-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json")
    assert "--dynamic-cvar-tail-cost-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--dynamic-cvar-tail-cost-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert "--synthetic-augmentation-validation-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--synthetic-augmentation-validation-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json")
    assert "--intervention-fatigue-risk-budget-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--intervention-fatigue-risk-budget-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json")
    assert "--letf-tracking-error-effective-fee-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--letf-tracking-error-effective-fee-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json")
    assert "--asian-etf-tail-analytics-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--asian-etf-tail-analytics-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json")
    assert "--research-shadow-decision-snapshot" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--research-shadow-decision-snapshot") + 1].endswith(
        "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
    )
    assert any(item.endswith("results/group_a_plus_promotion_gate_20260627.json") for item in commands["promotion_gate"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.json") for item in commands["promotion_gate"])
    assert "--multi-window-gate" in commands["promotion_gate"]
    assert "--deployment-consistency" in commands["promotion_gate"]
    assert commands["promotion_gate"][commands["promotion_gate"].index("--deployment-consistency") + 1].endswith(
        "report/group_a_plus/latest/deployment_consistency_review.json"
    )
    assert "--deployment-summary" in commands["promotion_gate"]
    assert commands["promotion_gate"][commands["promotion_gate"].index("--deployment-summary") + 1].endswith(
        "report/group_a_plus/latest/deployment_summary.json"
    )
    assert commands["multi_window_failure_attribution"][1] == (
        "scripts/evaluate/build_group_a_plus_multi_window_failure_attribution.py"
    )
    assert commands["multi_window_failure_attribution"][
        commands["multi_window_failure_attribution"].index("--multi-window-gate") + 1
    ].endswith("results/group_a_plus_multi_window_gate_20260706.json")
    assert commands["multi_window_failure_attribution"][
        commands["multi_window_failure_attribution"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/multi_window_failure_attribution.json")
    assert commands["promotion_blocked_diagnostic"][1] == (
        "scripts/evaluate/build_group_a_plus_promotion_blocked_diagnostic.py"
    )
    assert commands["promotion_blocked_diagnostic"][
        commands["promotion_blocked_diagnostic"].index("--promotion-gate") + 1
    ].endswith("results/group_a_plus_promotion_gate_20260627.json")
    assert commands["promotion_blocked_diagnostic"][
        commands["promotion_blocked_diagnostic"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/promotion_blocked_diagnostic.json")
    assert commands["daily_status_final"][1] == "scripts/misc/check_group_a_plus_daily_status.py"
    assert commands["daily_status_final"][commands["daily_status_final"].index("--promotion-gate") + 1].endswith(
        "results/group_a_plus_promotion_gate_20260627.json"
    )
    assert commands["daily_status_final"][commands["daily_status_final"].index("--output-prefix") + 1].endswith(
        "results/group_a_plus_daily_status_final_20260627"
    )
    assert commands["daily_status_final"][commands["daily_status_final"].index("--status-stage") + 1] == "final"
    assert commands["daily_status_final"][commands["daily_status_final"].index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert commands["final_governance_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plus_final_governance_snapshot.py"
    )
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--promotion-gate") + 1
    ].endswith("results/group_a_plus_promotion_gate_20260627.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--promotion-blocked-diagnostic") + 1
    ].endswith("report/group_a_plus/latest/promotion_blocked_diagnostic.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--multi-window-failure-attribution") + 1
    ].endswith("report/group_a_plus/latest/multi_window_failure_attribution.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--panel-drift-triage") + 1
    ].endswith("report/group_a_plus/latest/panel_drift_triage.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--panel-drift-resolution-progress") + 1
    ].endswith("report/group_a_plus/latest/panel_drift_resolution_progress.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--external-sensitivity-observation-log") + 1
    ].endswith("report/group_a_plus/latest/external_sensitivity_observation_log.json")
    assert commands["final_governance_snapshot"][
        commands["final_governance_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/final_governance_snapshot.json")
    assert any(item.endswith("results/ncf_2330_checklist_20260627.json") for item in commands["ncf_2330_checklist"])
    assert commands["refresh_2330_per"][commands["refresh_2330_per"].index("--start") + 1] == "2023-06-27"


def test_build_commands_can_skip_refresh_and_disable_external_features() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert list(commands) == [
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "ncf_signal_archive",
        "ncf_2330",
        "ncf_panel_manifest",
        "ncf_panel_drift",
        "ncf_panel_drift_diagnosis",
        "panel_drift_triage",
        "ncf_panel_drift_remediation_plan_initial",
        "external_sensitivity_observation_log",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
        "compounding_regime",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "cvar_tail_risk_diagnostic",
        "network_volatility_spillover_shadow",
        "option_state_coverage_review",
        "adversarial_market_integrity_review",
        "sciphyrl_readiness_review",
        "market_impact_readiness_review",
        "finstressts_readiness_review",
        "finstressts_counterfactual_shadow",
        "finstressts_baseline_compare_shadow",
        "finstressts_decision_snapshot",
        "trigate_vol_memory_shadow",
        "systemic_bubble_time_at_risk_review",
        "illiquidity_network_readiness_review",
        "speculative_influence_network_readiness_review",
        "sin_lite_proxy",
        "hmm_wj_synthetic_scenario_readiness_review",
        "dynamic_cvar_tail_cost_readiness_review",
        "synthetic_augmentation_validation_audit",
        "synthetic_augmentation_validation_readiness_review",
        "intervention_history",
        "broker_holdings_time_series_sample",
        "broker_holdings_reconciliation_review",
            "intervention_fatigue_risk_budget_readiness_review",
            "letf_tracking_error_effective_fee_readiness_review",
            "asian_etf_tail_analytics_readiness_review",
            "gift_human_exception_record_draft",
            "gift_human_exception_approval_record_schema",
            "gift_signed_approval_record_template",
            "gift_signed_approval_validation",
            "gift_signed_approval_checklist_review",
            "gift_signed_approval_validator_smoke",
            "gift_manual_approval_readiness",
            "gift_pdf_advantage_coverage_review",
            "research_shadow_decision_snapshot",
        "dfl_advisory",
        "dfl_active_date_audit",
        "dfl_shadow_ensemble",
        "daily_status",
        "deployment_consistency_review",
        "deployment_summary",
        "promotion_gate",
        "multi_window_failure_attribution",
        "promotion_blocked_diagnostic",
        "daily_status_final",
        "final_governance_snapshot",
        "ncf_2330_checklist",
    ]
    assert "--no-external-features" in commands["ncf_00631l"]
    assert "--no-external-features" in commands["ncf_00632r"]
    assert "--no-external-features" in commands["ncf_2330"]


def test_build_commands_can_use_ncf_2330_pre_open_feature_mode() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260707",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-16",
        chip_end="2026-07-07",
        per_start="2023-07-07",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        train_start_2330="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        ncf_2330_feature_mode="pre_open",
        refresh_external_cache=False,
        checklist_external_start="2023-07-07",
        checklist_external_end="2026-07-08",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert commands["ncf_2330"][commands["ncf_2330"].index("--feature-mode") + 1] == "pre_open"


def test_build_commands_can_skip_promotion_gate() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        skip_promotion_gate=True,
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "promotion_gate" not in commands
    assert "multi_window_failure_attribution" not in commands
    assert "promotion_blocked_diagnostic" not in commands
    assert "daily_status_final" not in commands
    assert "final_governance_snapshot" not in commands
    assert "ncf_panel_drift" in commands


def test_build_commands_can_override_promotion_drift_audit() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        promotion_drift_audit="results/custom_drift.json",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "ncf_panel_drift" in commands
    assert commands["promotion_gate"][commands["promotion_gate"].index("--drift-audit") + 1] == "results/custom_drift.json"


def test_build_commands_can_override_downstream_live_signal() -> None:
    module = _load_module()
    args = _command_args(live_signal_override="results/group_a_plus_live_signal_v2_20260723_from_20260722.json")

    commands = module.build_commands(args)

    expected = "results/group_a_plus_live_signal_v2_20260723_from_20260722.json"
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--live-signal") + 1] == expected
    assert commands["daily_status"][commands["daily_status"].index("--live-signal") + 1] == expected
    assert commands["daily_status_final"][commands["daily_status_final"].index("--live-signal") + 1] == expected
    assert commands["deployment_consistency_review"][
        commands["deployment_consistency_review"].index("--live-signal") + 1
    ] == expected
    assert commands["deployment_summary"][commands["deployment_summary"].index("--live-signal") + 1] == expected


def test_build_commands_can_pin_refresh_target_date_and_strict_mode() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260702",
        skip_refresh=False,
        force_refresh=True,
        refresh_target_date="2026-07-02",
        strict_refresh=True,
        skip_shareholding=False,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=True,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    refresh_cmd = commands["refresh_group_data"]
    assert "--target-date" in refresh_cmd
    assert refresh_cmd[refresh_cmd.index("--target-date") + 1] == "2026-07-02"
    assert "--strict" in refresh_cmd
    assert "--force" in refresh_cmd
    freshness_cmd = commands["ohlcv_freshness"]
    assert freshness_cmd[freshness_cmd.index("--target-date") + 1] == "2026-07-02"
    assert "--fail-on-warning" in freshness_cmd


def test_pipeline_db_path_falls_back_when_args_has_no_db() -> None:
    module = _load_module()
    args = argparse.Namespace(date_stamp="20260714")

    assert module._pipeline_db_path(args).name == "stock_data.db"


def test_build_commands_refresh_external_cache_includes_checklist_tickers() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260702",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=True,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "refresh_ncf_2330_checklist_external_cache" in commands
    refresh_cmd = commands["refresh_ncf_2330_checklist_external_cache"]
    assert "scripts/fetch/fetch_ncf_2330_checklist_external_cache.py" in refresh_cmd
    assert "--allow-download" in refresh_cmd
    assert refresh_cmd[refresh_cmd.index("--start") + 1] == "2023-07-02"
    assert refresh_cmd[refresh_cmd.index("--end") + 1] == "2026-07-03"


def _base_args(tmp_db: str, **overrides) -> argparse.Namespace:
    defaults = dict(
        date_stamp="20260702",
        skip_refresh=False,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=False,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db=tmp_db,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_resolve_chip_start_falls_back_to_default_when_db_missing(tmp_path: Path) -> None:
    module = _load_module()
    missing_db = tmp_path / "does_not_exist.db"

    result = module._resolve_chip_start(missing_db, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_resolve_chip_start_extends_backward_when_gap_exceeds_default(tmp_path: Path) -> None:
    """The M8 scenario: pipeline was down for a month, default lookback
    (chip_start) only covers the last few weeks -- the resolved start must
    reach back to the day after the last known row, not leave the gap."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-05-01')")
    finally:
        con.close()

    # default_start (2026-06-11) is *after* the last known row (2026-05-01)
    # plus a month-long gap -- resolved start must move back to 2026-05-02.
    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-05-02"


def test_resolve_chip_start_does_not_narrow_when_table_is_fresh(tmp_path: Path) -> None:
    """A table fresher than the default lookback must not narrow the
    window -- still use the default trailing window (harmless, covers
    late-arriving upstream revisions)."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-07-01')")
    finally:
        con.close()

    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_resolve_chip_start_handles_missing_table(tmp_path: Path) -> None:
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE some_other_table (x INT)")
    finally:
        con.close()

    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_build_commands_extends_chip_start_for_stale_table_only(tmp_path: Path) -> None:
    """Each of the 4 chip-data commands gets its own resolved start based
    on its own table's freshness -- a gap in one table doesn't affect the
    others."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("CREATE TABLE derivative_institutional_data (product_id VARCHAR, dt DATE)")
        # institutional_data has a real gap; derivative_institutional_data is fresh.
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-05-01')")
        con.execute("INSERT INTO derivative_institutional_data VALUES ('TX', '2026-07-01')")
    finally:
        con.close()

    args = _base_args(str(db_path), chip_start="2026-06-11", chip_end="2026-07-02")
    commands = module.build_commands(args)

    institutional_cmd = commands["refresh_institutional"]
    derivative_cmd = commands["refresh_derivative_institutional"]
    assert institutional_cmd[institutional_cmd.index("--start") + 1] == "2026-05-02"
    assert derivative_cmd[derivative_cmd.index("--start") + 1] == "2026-06-11"


def test_run_pipeline_commands_continues_past_best_effort_step_failure(tmp_path: Path, monkeypatch) -> None:
    """Fable audit (2026-07-08, #2): a transient failure in a best-effort
    refresh step must not stop the whole run -- the NCF/signal steps below
    can still proceed against already-fetched or cached data."""
    module = _load_module()
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)

    def fake_run(cmd, *, dry_run, env_extra=None, log_fh=None):
        if cmd[0] == "refresh_taifex":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(module, "_run", fake_run)
    commands = {
        "refresh_group_data": ["refresh_group_data"],
        "refresh_taifex": ["refresh_taifex"],
        "ncf_00631l": ["ncf_00631l"],
    }

    completed = module.run_pipeline_commands(
        commands,
        date_stamp="20260709",
        dry_run=False,
        refresh_external_cache=False,
        log_path=tmp_path / "logs" / "daily.log",
    )

    assert completed == ["refresh_group_data", "ncf_00631l"]
    assert not (tmp_path / "ncf_daily_pipeline_20260709.json").exists()


def test_run_pipeline_commands_writes_partial_manifest_and_notifies_on_critical_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """A critical (non-refresh) step's failure must halt the run, but not
    silently -- it should record which step failed for
    collect_pipeline_health() to see, and push a direct notification since
    daily_signal/alert_state never got to run."""
    module = _load_module()
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)
    notified: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        module,
        "_notify_pipeline_failure",
        lambda date_stamp, name, error: notified.append((date_stamp, name, error)),
    )

    def fake_run(cmd, *, dry_run, env_extra=None, log_fh=None):
        if cmd[0] == "ncf_00631l":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(module, "_run", fake_run)
    commands = {
        "refresh_group_data": ["refresh_group_data"],
        "ncf_00631l": ["ncf_00631l"],
        "daily_signal": ["daily_signal"],
    }

    with pytest.raises(subprocess.CalledProcessError):
        module.run_pipeline_commands(
            commands,
            date_stamp="20260709",
            dry_run=False,
            refresh_external_cache=False,
            log_path=tmp_path / "logs" / "daily.log",
        )

    assert notified == [("20260709", "ncf_00631l", notified[0][2])]
    manifest = json.loads((tmp_path / "ncf_daily_pipeline_20260709.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["failed_step"] == "ncf_00631l"
    assert manifest["completed_steps"] == ["refresh_group_data"]


def test_main_manifest_includes_latest_deployment_summary_outputs(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: argparse.Namespace(
            date_stamp="20260709",
            dry_run=False,
            only_refresh=False,
            skip_refresh=True,
            skip_promotion_gate=False,
            refresh_external_cache=False,
            skip_commentary=True,
        ),
    )
    monkeypatch.setattr(module, "build_commands", lambda args: {"daily_status": ["daily_status"]})
    monkeypatch.setattr(module, "run_pipeline_commands", lambda commands, **kwargs: ["daily_status"])
    monkeypatch.setattr(
        module,
        "_signal_summary",
        lambda path: {
            "ticker": path.name,
            "direction": "flat",
            "probability_up": 0.5,
            "data_freshness_status": "ok",
            "last_close_date": "2026-07-09",
        },
    )

    module.main()

    manifest = json.loads((tmp_path / "ncf_daily_pipeline_20260709.json").read_text())
    outputs = manifest["outputs"]
    assert outputs["deployment_summary"].endswith("report/group_a_plus/latest/deployment_summary.json")
    assert outputs["panel_drift_triage"].endswith("report/group_a_plus/latest/panel_drift_triage.json")
    assert outputs["external_sensitivity_observation_log"].endswith(
        "report/group_a_plus/latest/external_sensitivity_observation_log.json"
    )
    assert outputs["panel_drift_resolution_progress"].endswith(
        "report/group_a_plus/latest/panel_drift_resolution_progress.json"
    )
    assert outputs["multi_window_failure_attribution"].endswith(
        "report/group_a_plus/latest/multi_window_failure_attribution.json"
    )
    assert outputs["promotion_blocked_diagnostic"].endswith(
        "report/group_a_plus/latest/promotion_blocked_diagnostic.json"
    )
    assert outputs["daily_status_final"].endswith("group_a_plus_daily_status_final_20260709.json")
    assert outputs["final_governance_snapshot"].endswith(
        "report/group_a_plus/latest/final_governance_snapshot.json"
    )
    assert outputs["securities_lending_0050_source_status"].endswith(
        "report/group_a_plus/latest/securities_lending_0050_source_status.json"
    )
    assert outputs["daily_status_pointer"].endswith("report/group_a_plus/latest/daily_status.json")
