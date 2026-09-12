from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
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
        "train_start_2330": "2015-01-01",
        "skip_ncf_data_validation": False,
        "ncf_max_ohlcv_gap_days": 14,
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


def test_research_governance_command_builder_keeps_snapshot_and_gate_paths() -> None:
    module = _load_module()

    commands = module._build_research_governance_commands(stamp="20260627", as_of="2026-06-27")

    assert list(commands) == [
        "research_shadow_decision_snapshot",
        "research_governance_gate",
        "shadow_artifact_registry",
        "latest_strategy_target_weight_export",
        "latest_strategy_explain_snapshot",
        "data_freshness_gate",
        "ncf_panel_drift_auto_attribution",
        "golden_release_separation_audit",
    ]
    assert commands["research_shadow_decision_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py"
    )
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--ncf-decision-calibration") + 1
    ].endswith("results/ncf_decision_calibration_shadow_20260627.json")
    assert commands["research_governance_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_research_governance_gate.py"
    )
    assert commands["research_governance_gate"][commands["research_governance_gate"].index("--as-of") + 1] == (
        "2026-06-27"
    )
    assert commands["research_governance_gate"][commands["research_governance_gate"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/research_governance_gate.json"
    )
    assert commands["shadow_artifact_registry"][1] == (
        "scripts/evaluate/build_group_a_plus_shadow_artifact_registry.py"
    )
    assert commands["shadow_artifact_registry"][commands["shadow_artifact_registry"].index("--as-of") + 1] == (
        "2026-06-27"
    )
    assert commands["shadow_artifact_registry"][commands["shadow_artifact_registry"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/shadow_artifact_registry.json"
    )
    assert commands["latest_strategy_target_weight_export"][1] == (
        "scripts/evaluate/export_group_a_plus_latest_strategy_target_weights.py"
    )
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--end") + 1
    ] == "latest"
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--output-json") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.json")
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--output-csv") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.csv")
    assert "latest_strategy_target_weight_export" in module.BEST_EFFORT_STEP_NAMES
    assert commands["latest_strategy_explain_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plusplus_latest_strategy_explain_snapshot.py"
    )
    assert commands["latest_strategy_explain_snapshot"][
        commands["latest_strategy_explain_snapshot"].index("--target-weights") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.json")
    assert commands["latest_strategy_explain_snapshot"][
        commands["latest_strategy_explain_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/group_a_plusplus_latest_strategy_explain_snapshot.json")
    assert commands["data_freshness_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_data_freshness_gate.py"
    )
    assert commands["data_freshness_gate"][commands["data_freshness_gate"].index("--ohlcv-freshness") + 1].endswith(
        "results/ohlcv_freshness_20260627.json"
    )
    assert commands["data_freshness_gate"][commands["data_freshness_gate"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/data_freshness_gate.json"
    )
    assert commands["ncf_panel_drift_auto_attribution"][1] == (
        "scripts/evaluate/build_ncf_panel_drift_auto_attribution.py"
    )
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--diagnosis") + 1
    ].endswith("results/ncf_panel_drift_diagnosis_20260627.json")
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--data-freshness-gate") + 1
    ].endswith("report/group_a_plus/latest/data_freshness_gate.json")
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/ncf_panel_drift_auto_attribution.json")
    assert commands["golden_release_separation_audit"][1] == (
        "scripts/evaluate/build_group_a_plus_golden_release_separation_audit.py"
    )
    assert commands["golden_release_separation_audit"][
        commands["golden_release_separation_audit"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/golden_release_separation_audit.json")


def test_ctbc_command_builder_keeps_date_stamped_panels_and_outputs() -> None:
    module = _load_module()
    db_path = Path("/tmp/stock_data.db")

    commands = module._build_ctbc_2509_02986_commands(stamp="20260627", db_path=db_path)

    assert list(commands) == [
        "ctbc_debounce_shadow_2509_02986",
        "ctbc_00713_debounce_shadow_2509_02986",
        "ctbc_00713_domain_randomization_2509_02986",
        "ctbc_groupa_plusplus_review_2509_02986",
        "ctbc_promotion_readiness_gate_2509_02986",
    ]
    assert commands["ctbc_debounce_shadow_2509_02986"][
        commands["ctbc_debounce_shadow_2509_02986"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["ctbc_00713_debounce_shadow_2509_02986"][
        commands["ctbc_00713_debounce_shadow_2509_02986"].index("--panel-00713") + 1
    ].endswith("results/ncf_00713_panel_latest_20260627.csv")
    assert commands["ctbc_00713_debounce_shadow_2509_02986"][
        commands["ctbc_00713_debounce_shadow_2509_02986"].index("--curves-output") + 1
    ].endswith("results/2509_02986_ctbc_00713_debounce_shadow_curves_20260627.csv")
    assert commands["ctbc_promotion_readiness_gate_2509_02986"][
        commands["ctbc_promotion_readiness_gate_2509_02986"].index("--domain-randomization") + 1
    ].endswith("report/group_a_plus/latest/2509_02986_ctbc_00713_domain_randomization.json")
    assert list(commands).index("ctbc_groupa_plusplus_review_2509_02986") < list(commands).index(
        "ctbc_promotion_readiness_gate_2509_02986"
    )


def test_daily_pipeline_does_not_write_frozen_golden_release_artifacts() -> None:
    module = _load_module()
    commands = module.build_commands(_command_args())

    protected = {module._normalize_project_path(path) for path in module.PROTECTED_GOLDEN_RELEASE_ARTIFACTS}
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

    with pytest.raises(ValueError, match="protected frozen Golden release"):
        module._assert_no_protected_golden_release_output_targets(commands)


def test_daily_pipeline_blocks_golden2_0830_release_output_target() -> None:
    module = _load_module()
    protected = module.PROJECT_ROOT / "results" / "golden2_0830" / "ncf_00631l_panel_golden2_0830.csv"
    commands = {
        "bad_step": [
            "python",
            "some_script.py",
            "--csv",
            str(protected),
        ]
    }

    with pytest.raises(ValueError, match="protected frozen Golden release"):
        module._assert_no_protected_golden_release_output_targets(commands)


def test_infer_no_external_panel_path() -> None:
    module = _load_module()

    assert module._infer_no_external_panel_path("results/ncf_00631l_panel_latest_20260716.csv") == (
        "results/ncf_00631l_panel_latest_20260716_no_external.csv"
    )
    assert module._infer_no_external_panel_path("results/ncf_00631l_panel_latest_20260716_no_external.csv") == (
        "results/ncf_00631l_panel_latest_20260716_no_external.csv"
    )
    assert module._infer_no_external_panel_path("results/not_a_panel.json") == "results/not_a_panel.json"


def test_parse_args_dfl_defaults_use_stable_latest_files(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setattr(sys, "argv", ["run_ncf_daily_pipeline.py"])

    args = module.parse_args()

    assert args.dfl_shadow_result == "results/a2118_decision_focused_action_shadow_dfl_main_latest.json"
    assert args.dfl_advisory_input == "results/a2118_decision_focused_action_shadow_dfl_main_latest.json"
    assert args.dfl_selective_p50_input == "results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json"
    assert args.dfl_selective_p70_input == "results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json"
    assert args.dfl_overlap_result == "results/a2118_decision_focused_action_overlap_dfl_latest.json"


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
        "ncf_data_validation",
        "ncf_00631l",
        "ncf_00632r",
        "ncf_0050",
        "ncf_00713",
        "ncf_signal_archive",
        "ncf_2330",
        "ncf_00631l_no_external_shadow",
        "ncf_panel_manifest",
        "ncf_0050_threshold_eval",
        "ctbc_debounce_shadow_2509_02986",
        "ctbc_00713_debounce_shadow_2509_02986",
        "ctbc_00713_domain_randomization_2509_02986",
        "ctbc_groupa_plusplus_review_2509_02986",
        "ctbc_promotion_readiness_gate_2509_02986",
        "auxiliary_policy_lift_shadow_2608_15841",
        "auxiliary_churn_shadow_2608_15841",
        "auxiliary_purged_walkforward_2608_15841",
        "auxiliary_regime_decay_audit_2608_15841",
        "auxiliary_lifecycle_audit_2608_15841",
        "delayed_credit_audit_2608_15841",
        "candidate_auxiliary_bank_blueprint_2608_15841",
        "auxiliary_task_discovery_readiness_2608_15841",
        "ncf_panel_drift",
        "ncf_panel_refresh_recommendation",
        "ncf_panel_drift_no_external_vs_external",
        "ncf_panel_drift_diagnosis",
        "panel_drift_triage",
        "ncf_panel_drift_remediation_plan_initial",
        "ncf_panel_drift_no_tabnet_baseline_vs_today",
        "ncf_panel_drift_model_set_isolation_report",
        "ncf_panel_same_method_baseline_manifest",
        "external_sensitivity_observation_log",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "golden1_combined_signal",
        "daily_signal",
        "riccati_mv_shadow",
        "current_policy_re_evaluation_gate",
        "rebalance_review",
        "compounding_regime",
        "gjr_garch_shadow",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "add_0050_instead_shadow_log",
        "adaptive_review_interval_shadow_log",
        "gatedlinear_drawdown_forecast_shadow_log",
        "cvar_tail_risk_diagnostic",
        "taiwan_etf_2607_16450_review",
        "taiwan_etf_2607_16450_tail_scorecard",
        "taiwan_etf_2607_16450_cost_robustness",
        "taiwan_etf_2607_16450_candidate_tail_review",
        "taiwan_etf_2607_16450_regime_vol_forecast_quality",
        "taiwan_etf_2607_16450_regime_vol_gate",
        "taiwan_etf_2607_16450_tail_dependence_monitor",
        "taiwan_etf_2607_16450_geopolitical_cvar_overlay",
        "taiwan_etf_2607_16450_bootstrap_promotion_gate",
        "paper_2609_07946_00635u_instrument_review",
        "paper_2609_07946_stock_bond_gold_forward_shadow",
        "paper_2609_07946_bond_only_forward_shadow",
        "paper_2609_07946_complementarity_promotion_gate",
        "paper_2609_07946_adoption_matrix",
        "paper_2609_08106_complementarity_forward_shadow",
        "paper_2609_08106_latest_target_weight_replay",
        "paper_2609_08106_latest_target_weight_param_sweep",
        "paper_2609_08106_adoption_matrix",
        "paper_2609_07989_order_flow_regime_shadow",
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
            "scr_readiness_review_2602_24037",
            "scr_readiness_robustness_2602_24037",
            "scr_readiness_window_split_2602_24037",
            "scr_scenario_stress_score_2602_24037",
            "cvar_cost_window_split_2606_26625",
            "rolling_tail_no_add_gate_2606_26625",
            "dynamic_cvar_constraint_shadow_2608_20179",
            "dynamic_cvar_forward_validation_2608_20179",
            "dynamic_cvar_tail_cost_readiness_review",
            "synthetic_augmentation_validation_audit",
            "synthetic_augmentation_validation_readiness_review",
        "intervention_history",
        "broker_holdings_time_series_sample",
        "broker_holdings_reconciliation_review",
        "assigned_realized_deployment_shadow_2608_08405",
        "capacity_grid_shadow_2608_08405",
        "erosion_persistence_shadow_2608_08405",
        "instrument_readiness_shadow_2608_08405",
        "ramp_path_dependence_shadow_2608_08405",
        "capacity_crowding_readiness_2608_08405",
        "intervention_fatigue_risk_budget_readiness_review",
        "letf_tracking_error_effective_fee_readiness_review",
        "00632r_discipline_guard",
        "letf_liquidity_feedback_watch_shadow_backtest",
        "asian_etf_tail_analytics_readiness_review",
        "gift_human_exception_record_draft",
        "gift_human_exception_approval_record_schema",
        "gift_signed_approval_record_template",
        "gift_signed_approval_validation",
        "gift_signed_approval_checklist_review",
        "gift_signed_approval_validator_smoke",
        "gift_manual_approval_readiness",
        "gift_pdf_advantage_coverage_review",
        "defensive_cash_floor_signed_approval_validation",
        "defensive_cash_floor_guarded_candidate",
        "defensive_cash_floor_guarded_monitor",
        "ncf_panel_drift_auto_attribution",
        "dfl_shadow_refresh_main",
        "dfl_shadow_refresh_p50",
        "dfl_shadow_refresh_p70",
        "dfl_advisory",
            "dfl_shadow_refresh_overlap",
            "dfl_active_date_audit",
            "dfl_shadow_ensemble",
            "a2118_seed_averaging_live_inference_snapshot",
            "a2118_seed_averaging_forward_shadow_monitor",
            "a2118_seed_averaging_promotion_gate",
            "a2118_risk_down_mapped_shadow",
            "paper_2606_09104_00631l_regime_split",
            "paper_2606_09104_00631l_staged_ladder_readiness",
            "paper_2606_09104_extreme_state_monitor",
            "relative_reentry_opportunity_shadow",
            "relative_reentry_advisory_shadow",
            "relative_reentry_candidate_review",
        "relative_reentry_promotion_gate",
        "staged_reentry_event_study",
        "staged_reentry_promotion_review",
        "staged_reentry_confirmatory_tracker_2609_04917",
        "ncf_decision_calibration_shadow",
        "tsi_stress_shadow",
        "tsi_stress_oos",
        "tsi_no_add_shadow",
        "daily_artifact_integrity",
        "research_shadow_decision_snapshot",
        "research_governance_gate",
        "shadow_artifact_registry",
        "latest_strategy_target_weight_export",
        "latest_strategy_explain_snapshot",
        "data_freshness_gate",
        "golden_release_separation_audit",
            "daily_status",
            "deployment_consistency_review",
            "deployment_summary",
            "promotion_gate",
            "golden2_same_window_candidate_backtests",
            "golden2_multi_window_gate",
            "golden2_promotion_candidate_review",
            "multi_window_failure_attribution",
        "promotion_blocked_diagnostic",
        "daily_status_final",
        "moira_relative_exposure_thesis_shadow",
        "moira_hierarchical_credit_review_shadow",
        "moira_event_aware_execution_quality_shadow",
        "moira_policy_critic_shadow",
        "moira_policy_critic_validation_shadow",
        "moira_execution_guard_hard_stop_backtest_shadow",
        "daily_semantic_context_summary",
        "paper_convergence_review",
        "final_governance_snapshot",
        "ncf_2330_checklist",
    ]
    assert commands["refresh_group_data"][-1] == "--force"
    assert commands["ncf_data_validation"][1] == "ncf_data_quality.py"
    assert "--fail-on-degraded-freshness" not in commands["ncf_data_validation"]
    assert "ncf_data_validation" not in module.BEST_EFFORT_STEP_NAMES
    assert commands["ctbc_debounce_shadow_2509_02986"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_2509_02986_ctbc_debounce_shadow.py"
    )
    assert commands["ctbc_debounce_shadow_2509_02986"][
        commands["ctbc_debounce_shadow_2509_02986"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["ctbc_00713_debounce_shadow_2509_02986"][
        commands["ctbc_00713_debounce_shadow_2509_02986"].index("--panel-00713") + 1
    ].endswith("results/ncf_00713_panel_latest_20260627.csv")
    assert commands["ctbc_00713_domain_randomization_2509_02986"][
        commands["ctbc_00713_domain_randomization_2509_02986"].index("--panel-00713") + 1
    ].endswith("results/ncf_00713_panel_latest_20260627.csv")
    assert list(commands).index("ctbc_groupa_plusplus_review_2509_02986") < list(commands).index("daily_signal")
    assert "ctbc_debounce_shadow_2509_02986" in module.BEST_EFFORT_STEP_NAMES
    assert "ctbc_00713_debounce_shadow_2509_02986" in module.BEST_EFFORT_STEP_NAMES
    assert "ctbc_00713_domain_randomization_2509_02986" in module.BEST_EFFORT_STEP_NAMES
    assert "ctbc_promotion_readiness_gate_2509_02986" in module.BEST_EFFORT_STEP_NAMES
    assert "ctbc_groupa_plusplus_review_2509_02986" in module.BEST_EFFORT_STEP_NAMES
    assert commands["a2120_shadow_pipeline"][1] == "scripts/run/run_a2120_daily_shadow_pipeline.py"
    assert commands["a2120_shadow_pipeline"][commands["a2120_shadow_pipeline"].index("--date-stamp") + 1] == "20260627"
    assert "a2120_shadow_pipeline" in module.BEST_EFFORT_STEP_NAMES
    assert commands["golden1_combined_signal"][1] == "scripts/run/run_group_a_combined_signal.py"
    assert commands["golden1_combined_signal"][
        commands["golden1_combined_signal"].index("--as-of-date") + 1
    ] == "2026-06-27"
    assert list(commands).index("golden1_combined_signal") < list(commands).index("daily_signal")
    assert "golden1_combined_signal" not in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["add_0050_instead_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_add_0050_instead_shadow_log.py"
    )
    assert commands["add_0050_instead_shadow_log"][
        commands["add_0050_instead_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "add_0050_instead_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert commands["adaptive_review_interval_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_adaptive_review_interval_shadow_log.py"
    )
    assert commands["adaptive_review_interval_shadow_log"][
        commands["adaptive_review_interval_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "adaptive_review_interval_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert commands["cvar_tail_risk_diagnostic"][1] == (
        "scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py"
    )
    assert "cvar_tail_risk_diagnostic" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_review"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_taiwan_etf_review.py"
    )
    assert "taiwan_etf_2607_16450_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_tail_scorecard"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_tail_sensitive_scorecard.py"
    )
    assert "taiwan_etf_2607_16450_tail_scorecard" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_cost_robustness"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_turnover_cost_robustness.py"
    )
    assert "taiwan_etf_2607_16450_cost_robustness" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_candidate_tail_review"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_candidate_tail_review.py"
    )
    assert "taiwan_etf_2607_16450_candidate_tail_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_regime_vol_forecast_quality"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py"
    )
    assert commands["taiwan_etf_2607_16450_regime_vol_forecast_quality"][
        commands["taiwan_etf_2607_16450_regime_vol_forecast_quality"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2607_16450_regime_switching_volatility_forecast_quality.json")
    assert "taiwan_etf_2607_16450_regime_vol_forecast_quality" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_regime_vol_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_regime_switching_volatility_gate.py"
    )
    assert "taiwan_etf_2607_16450_regime_vol_gate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_tail_dependence_monitor"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_tail_dependence_monitor.py"
    )
    assert "taiwan_etf_2607_16450_tail_dependence_monitor" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_geopolitical_cvar_overlay"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_geopolitical_cvar_overlay.py"
    )
    assert "taiwan_etf_2607_16450_geopolitical_cvar_overlay" in module.BEST_EFFORT_STEP_NAMES
    assert commands["taiwan_etf_2607_16450_bootstrap_promotion_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_2607_16450_bootstrap_promotion_gate.py"
    )
    assert "taiwan_etf_2607_16450_bootstrap_promotion_gate" in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["capacity_crowding_readiness_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_capacity_crowding_readiness.py"
    )
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--capital") + 1
    ] == "1000000"
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--market-impact") + 1
    ].endswith("report/group_a_plus/latest/market_impact_readiness_review.json")
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--capacity-grid") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json")
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--erosion-persistence") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json")
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--instrument-readiness") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json")
    assert commands["capacity_crowding_readiness_2608_08405"][
        commands["capacity_crowding_readiness_2608_08405"].index("--ramp-path-dependence") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json")
    assert "capacity_crowding_readiness_2608_08405" in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["scr_readiness_review_2602_24037"][1] == (
        "scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py"
    )
    assert commands["scr_readiness_review_2602_24037"][
        commands["scr_readiness_review_2602_24037"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_review.json")
    assert "scr_readiness_review_2602_24037" in module.BEST_EFFORT_STEP_NAMES
    assert commands["scr_readiness_robustness_2602_24037"][1] == (
        "scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py"
    )
    assert commands["scr_readiness_robustness_2602_24037"][
        commands["scr_readiness_robustness_2602_24037"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json")
    assert "scr_readiness_robustness_2602_24037" in module.BEST_EFFORT_STEP_NAMES
    assert commands["scr_readiness_window_split_2602_24037"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_2602_24037_scr_readiness_window_split.py"
    )
    assert commands["scr_readiness_window_split_2602_24037"][
        commands["scr_readiness_window_split_2602_24037"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json")
    assert "scr_readiness_window_split_2602_24037" in module.BEST_EFFORT_STEP_NAMES
    assert commands["scr_scenario_stress_score_2602_24037"][1] == (
        "scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py"
    )
    assert commands["scr_scenario_stress_score_2602_24037"][
        commands["scr_scenario_stress_score_2602_24037"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json")
    assert "scr_scenario_stress_score_2602_24037" in module.BEST_EFFORT_STEP_NAMES
    assert commands["dynamic_cvar_tail_cost_readiness_review"][1] == (
        "scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py"
    )
    assert commands["dynamic_cvar_tail_cost_readiness_review"][
        commands["dynamic_cvar_tail_cost_readiness_review"].index("--cvar-cost-window-split") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json")
    assert commands["dynamic_cvar_tail_cost_readiness_review"][
        commands["dynamic_cvar_tail_cost_readiness_review"].index("--rolling-tail-no-add") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json")
    assert commands["dynamic_cvar_tail_cost_readiness_review"][
        commands["dynamic_cvar_tail_cost_readiness_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert "dynamic_cvar_tail_cost_readiness_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["cvar_cost_window_split_2606_26625"][1] == (
        "scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py"
    )
    assert commands["cvar_cost_window_split_2606_26625"][
        commands["cvar_cost_window_split_2606_26625"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json")
    assert commands["cvar_cost_window_split_2606_26625"][
        commands["cvar_cost_window_split_2606_26625"].index("--md-output") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.md")
    assert "cvar_cost_window_split_2606_26625" in module.BEST_EFFORT_STEP_NAMES
    assert commands["rolling_tail_no_add_gate_2606_26625"][1] == (
        "scripts/evaluate/build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py"
    )
    assert commands["rolling_tail_no_add_gate_2606_26625"][
        commands["rolling_tail_no_add_gate_2606_26625"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json")
    assert commands["rolling_tail_no_add_gate_2606_26625"][
        commands["rolling_tail_no_add_gate_2606_26625"].index("--md-output") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.md")
    assert "rolling_tail_no_add_gate_2606_26625" in module.BEST_EFFORT_STEP_NAMES
    assert commands["dynamic_cvar_constraint_shadow_2608_20179"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_20179_dynamic_cvar_constraint_shadow.py"
    )
    assert commands["dynamic_cvar_constraint_shadow_2608_20179"][
        commands["dynamic_cvar_constraint_shadow_2608_20179"].index("--rolling-tail-gate") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json")
    assert commands["dynamic_cvar_constraint_shadow_2608_20179"][
        commands["dynamic_cvar_constraint_shadow_2608_20179"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.json")
    assert commands["dynamic_cvar_constraint_shadow_2608_20179"][
        commands["dynamic_cvar_constraint_shadow_2608_20179"].index("--md-output") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.md")
    assert "dynamic_cvar_constraint_shadow_2608_20179" in module.BEST_EFFORT_STEP_NAMES
    assert commands["dynamic_cvar_forward_validation_2608_20179"][1] == (
        "scripts/evaluate/validate_group_a_plus_2608_20179_dynamic_cvar_forward.py"
    )
    assert commands["dynamic_cvar_forward_validation_2608_20179"][
        commands["dynamic_cvar_forward_validation_2608_20179"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json")
    assert commands["dynamic_cvar_forward_validation_2608_20179"][
        commands["dynamic_cvar_forward_validation_2608_20179"].index("--md-output") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.md")
    assert "dynamic_cvar_forward_validation_2608_20179" in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["assigned_realized_deployment_shadow_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py"
    )
    assert commands["assigned_realized_deployment_shadow_2608_08405"][
        commands["assigned_realized_deployment_shadow_2608_08405"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["assigned_realized_deployment_shadow_2608_08405"][
        commands["assigned_realized_deployment_shadow_2608_08405"].index("--broker-reconciliation") + 1
    ].endswith("report/group_a_plus/latest/broker_holdings_reconciliation_review.json")
    assert commands["assigned_realized_deployment_shadow_2608_08405"][
        commands["assigned_realized_deployment_shadow_2608_08405"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json")
    assert "assigned_realized_deployment_shadow_2608_08405" in module.BEST_EFFORT_STEP_NAMES
    assert commands["capacity_grid_shadow_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_capacity_grid_shadow.py"
    )
    assert commands["capacity_grid_shadow_2608_08405"][
        commands["capacity_grid_shadow_2608_08405"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["capacity_grid_shadow_2608_08405"][
        commands["capacity_grid_shadow_2608_08405"].index("--assigned-realized") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json")
    assert commands["capacity_grid_shadow_2608_08405"][
        commands["capacity_grid_shadow_2608_08405"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json")
    assert "capacity_grid_shadow_2608_08405" in module.BEST_EFFORT_STEP_NAMES
    assert commands["erosion_persistence_shadow_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_erosion_persistence_shadow.py"
    )
    assert commands["erosion_persistence_shadow_2608_08405"][
        commands["erosion_persistence_shadow_2608_08405"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["erosion_persistence_shadow_2608_08405"][
        commands["erosion_persistence_shadow_2608_08405"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json")
    assert "erosion_persistence_shadow_2608_08405" in module.BEST_EFFORT_STEP_NAMES
    assert commands["instrument_readiness_shadow_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_instrument_readiness_shadow.py"
    )
    assert commands["instrument_readiness_shadow_2608_08405"][
        commands["instrument_readiness_shadow_2608_08405"].index("--securities-lending-status") + 1
    ].endswith("report/group_a_plus/latest/securities_lending_0050_source_status.json")
    assert commands["instrument_readiness_shadow_2608_08405"][
        commands["instrument_readiness_shadow_2608_08405"].index("--assigned-realized") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json")
    assert commands["instrument_readiness_shadow_2608_08405"][
        commands["instrument_readiness_shadow_2608_08405"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json")
    assert "instrument_readiness_shadow_2608_08405" in module.BEST_EFFORT_STEP_NAMES
    assert commands["ramp_path_dependence_shadow_2608_08405"][1] == (
        "scripts/evaluate/build_group_a_plus_2608_08405_ramp_path_dependence_shadow.py"
    )
    assert commands["ramp_path_dependence_shadow_2608_08405"][
        commands["ramp_path_dependence_shadow_2608_08405"].index("--intervention-history") + 1
    ].endswith("report/group_a_plus/latest/intervention_history.json")
    assert commands["ramp_path_dependence_shadow_2608_08405"][
        commands["ramp_path_dependence_shadow_2608_08405"].index("--assigned-realized") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json")
    assert commands["ramp_path_dependence_shadow_2608_08405"][
        commands["ramp_path_dependence_shadow_2608_08405"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json")
    assert "ramp_path_dependence_shadow_2608_08405" in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["00632r_discipline_guard"][1] == (
        "scripts/evaluate/build_group_a_plus_00632r_discipline_guard.py"
    )
    assert commands["00632r_discipline_guard"][
        commands["00632r_discipline_guard"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["00632r_discipline_guard"][
        commands["00632r_discipline_guard"].index("--letf-readiness") + 1
    ].endswith("report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json")
    assert commands["00632r_discipline_guard"][
        commands["00632r_discipline_guard"].index("--max-manual-weight") + 1
    ] == "0.05"
    assert commands["00632r_discipline_guard"][
        commands["00632r_discipline_guard"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/00632r_discipline_guard.json")
    assert "00632r_discipline_guard" in module.BEST_EFFORT_STEP_NAMES
    assert commands["letf_liquidity_feedback_watch_shadow_backtest"][1] == (
        "scripts/evaluate/backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py"
    )
    assert commands["letf_liquidity_feedback_watch_shadow_backtest"][
        commands["letf_liquidity_feedback_watch_shadow_backtest"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json")
    assert commands["letf_liquidity_feedback_watch_shadow_backtest"][
        commands["letf_liquidity_feedback_watch_shadow_backtest"].index("--min-trigger-count") + 1
    ] == "20"
    assert "letf_liquidity_feedback_watch_shadow_backtest" in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["defensive_cash_floor_signed_approval_validation"][1] == (
        "scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py"
    )
    assert commands["defensive_cash_floor_signed_approval_validation"][
        commands["defensive_cash_floor_signed_approval_validation"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["defensive_cash_floor_signed_approval_validation"][
        commands["defensive_cash_floor_signed_approval_validation"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json")
    assert "defensive_cash_floor_signed_approval_validation" in module.BEST_EFFORT_STEP_NAMES
    assert commands["defensive_cash_floor_guarded_candidate"][1] == (
        "scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py"
    )
    assert commands["defensive_cash_floor_guarded_candidate"][
        commands["defensive_cash_floor_guarded_candidate"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["defensive_cash_floor_guarded_candidate"][
        commands["defensive_cash_floor_guarded_candidate"].index("--signed-review") + 1
    ].endswith("report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json")
    assert commands["defensive_cash_floor_guarded_candidate"][
        commands["defensive_cash_floor_guarded_candidate"].index("--as-of") + 1
    ] == "2026-06-27"
    assert "--enable" in commands["defensive_cash_floor_guarded_candidate"]
    assert commands["defensive_cash_floor_guarded_candidate"][
        commands["defensive_cash_floor_guarded_candidate"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json")
    assert "defensive_cash_floor_guarded_candidate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["defensive_cash_floor_guarded_monitor"][1] == (
        "scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_monitor.py"
    )
    assert commands["defensive_cash_floor_guarded_monitor"][
        commands["defensive_cash_floor_guarded_monitor"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["defensive_cash_floor_guarded_monitor"][
        commands["defensive_cash_floor_guarded_monitor"].index("--log") + 1
    ].endswith("results/defensive_cash_floor_guarded_candidate_log.jsonl")
    assert commands["defensive_cash_floor_guarded_monitor"][
        commands["defensive_cash_floor_guarded_monitor"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/defensive_cash_floor_guarded_monitor.json")
    assert "defensive_cash_floor_guarded_monitor" in module.BEST_EFFORT_STEP_NAMES
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
        commands["research_shadow_decision_snapshot"].index("--scr-readiness") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--scr-robustness") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--scr-window-split") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--scr-stress-score") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--dynamic-cvar") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--cvar-cost-window-split-2606-26625") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--rolling-tail-no-add-2606-26625") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--dynamic-cvar-constraint-2608-20179") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--dynamic-cvar-forward-2608-20179") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json")
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
        commands["research_shadow_decision_snapshot"].index("--ncf-decision-calibration") + 1
    ].endswith("results/ncf_decision_calibration_shadow_20260627.json")
    assert commands["research_shadow_decision_snapshot"][
        commands["research_shadow_decision_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/research_shadow_decision_snapshot.json")
    assert "research_shadow_decision_snapshot" in module.BEST_EFFORT_STEP_NAMES
    assert commands["research_governance_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_research_governance_gate.py"
    )
    assert commands["research_governance_gate"][
        commands["research_governance_gate"].index("--reports-dir") + 1
    ].endswith("report/group_a_plus/latest")
    assert commands["research_governance_gate"][
        commands["research_governance_gate"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["research_governance_gate"][
        commands["research_governance_gate"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/research_governance_gate.json")
    assert commands["research_governance_gate"][
        commands["research_governance_gate"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/research_governance_gate.md")
    assert "research_governance_gate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["shadow_artifact_registry"][1] == (
        "scripts/evaluate/build_group_a_plus_shadow_artifact_registry.py"
    )
    assert commands["shadow_artifact_registry"][
        commands["shadow_artifact_registry"].index("--reports-dir") + 1
    ].endswith("report/group_a_plus/latest")
    assert commands["shadow_artifact_registry"][
        commands["shadow_artifact_registry"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/shadow_artifact_registry.json")
    assert commands["shadow_artifact_registry"][
        commands["shadow_artifact_registry"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/shadow_artifact_registry.md")
    assert "shadow_artifact_registry" in module.BEST_EFFORT_STEP_NAMES
    assert commands["latest_strategy_target_weight_export"][1] == (
        "scripts/evaluate/export_group_a_plus_latest_strategy_target_weights.py"
    )
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--db") + 1
    ] == "/nonexistent/path/stock_data.db"
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--end") + 1
    ] == "latest"
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--output-json") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.json")
    assert commands["latest_strategy_target_weight_export"][
        commands["latest_strategy_target_weight_export"].index("--output-csv") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.csv")
    assert "latest_strategy_target_weight_export" in module.BEST_EFFORT_STEP_NAMES
    assert commands["latest_strategy_explain_snapshot"][1] == (
        "scripts/evaluate/build_group_a_plusplus_latest_strategy_explain_snapshot.py"
    )
    assert commands["latest_strategy_explain_snapshot"][
        commands["latest_strategy_explain_snapshot"].index("--watchlist") + 1
    ].endswith("config/group_a_plus_watchlist.json")
    assert commands["latest_strategy_explain_snapshot"][
        commands["latest_strategy_explain_snapshot"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/group_a_plusplus_latest_strategy_explain_snapshot.json")
    assert commands["latest_strategy_explain_snapshot"][
        commands["latest_strategy_explain_snapshot"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/group_a_plusplus_latest_strategy_explain_snapshot.md")
    assert "latest_strategy_explain_snapshot" in module.BEST_EFFORT_STEP_NAMES
    assert commands["data_freshness_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_data_freshness_gate.py"
    )
    assert commands["data_freshness_gate"][
        commands["data_freshness_gate"].index("--live-signal") + 1
    ].endswith("report/group_a_plus/latest/live_signal.json")
    assert commands["data_freshness_gate"][
        commands["data_freshness_gate"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/data_freshness_gate.md")
    assert "data_freshness_gate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["ncf_panel_drift_auto_attribution"][1] == (
        "scripts/evaluate/build_ncf_panel_drift_auto_attribution.py"
    )
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--remediation-plan") + 1
    ].endswith("results/ncf_panel_drift_remediation_plan_20260627.json")
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--external-sensitivity-governance") + 1
    ].endswith("results/ncf_panel_external_feature_sensitivity_governance_20260627.json")
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--panel-manifest") + 1
    ].endswith("results/ncf_panel_manifest_20260627.json")
    assert commands["ncf_panel_drift_auto_attribution"][
        commands["ncf_panel_drift_auto_attribution"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/ncf_panel_drift_auto_attribution.md")
    assert "ncf_panel_drift_auto_attribution" in module.BEST_EFFORT_STEP_NAMES
    assert commands["golden_release_separation_audit"][1] == (
        "scripts/evaluate/build_group_a_plus_golden_release_separation_audit.py"
    )
    assert commands["golden_release_separation_audit"][
        commands["golden_release_separation_audit"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/golden_release_separation_audit.json")
    assert commands["golden_release_separation_audit"][
        commands["golden_release_separation_audit"].index("--output-md") + 1
    ].endswith("report/group_a_plus/latest/golden_release_separation_audit.md")
    assert "golden_release_separation_audit" in module.BEST_EFFORT_STEP_NAMES
    assert commands["daily_status"][
        commands["daily_status"].index("--gift-signed-approval-checklist-review") + 1
    ].endswith("report/group_a_plus/latest/gift_signed_approval_checklist_review.json")
    assert commands["daily_status"][
        commands["daily_status"].index("--gift-signed-approval-validator-smoke") + 1
    ].endswith("report/group_a_plus/latest/gift_signed_approval_validator_smoke.json")
    assert any(item.endswith("results/ohlcv_freshness_20260627.json") for item in commands["ohlcv_freshness"])
    assert any(item.endswith("results/ncf_00631l_latest_20260627.json") for item in commands["ncf_00631l"])
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in commands["ncf_00632r"])
    assert commands["ncf_0050"][1] == "scripts/misc/ncf_0050.py"
    assert any(item.endswith("results/ncf_0050_latest_20260627.json") for item in commands["ncf_0050"])
    assert any(item.endswith("results/ncf_0050_panel_latest_20260627.csv") for item in commands["ncf_0050"])
    assert "--full-panel" in commands["ncf_00631l"]
    assert "--no-tabnet" not in commands["ncf_00631l"]
    assert "--full-panel" in commands["ncf_0050"]
    assert "--no-tabnet" not in commands["ncf_0050"]
    assert commands["ncf_00631l_no_external_shadow"][1] == "scripts/misc/ncf_00631l.py"
    assert "--no-external-features" in commands["ncf_00631l_no_external_shadow"]
    assert "--no-tabnet" not in commands["ncf_00631l_no_external_shadow"]
    assert any(
        item.endswith("results/ncf_00631l_latest_20260627_no_external.json")
        for item in commands["ncf_00631l_no_external_shadow"]
    )
    assert any(
        item.endswith("results/ncf_00631l_panel_latest_20260627_no_external.csv")
        for item in commands["ncf_00631l_no_external_shadow"]
    )
    assert "--full-panel" in commands["ncf_00632r"]
    assert "--full-panel" in commands["ncf_2330"]
    assert commands["ncf_2330"][commands["ncf_2330"].index("--feature-mode") + 1] == "after_close"
    assert any(item.endswith("results/ncf_0050_panel_latest_20260627.csv") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_2330_panel_latest_20260627.csv") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_panel_manifest_20260627.json") for item in commands["ncf_panel_manifest"])
    assert commands["ncf_0050_threshold_eval"][1] == "scripts/evaluate/evaluate_ncf_0050_panel_thresholds.py"
    assert commands["ncf_0050_threshold_eval"][
        commands["ncf_0050_threshold_eval"].index("--panel") + 1
    ].endswith("results/ncf_0050_panel_latest_20260627.csv")
    assert commands["ncf_0050_threshold_eval"][
        commands["ncf_0050_threshold_eval"].index("--output") + 1
    ].endswith("results/ncf_0050_threshold_eval_20260627.json")
    assert commands["ncf_0050_threshold_eval"][
        commands["ncf_0050_threshold_eval"].index("--output-md") + 1
    ].endswith("results/ncf_0050_threshold_eval_20260627.md")
    assert "ncf_0050_threshold_eval" in module.BEST_EFFORT_STEP_NAMES
    lift_cmd = commands["auxiliary_policy_lift_shadow_2608_15841"]
    assert lift_cmd[1] == "scripts/evaluate/evaluate_ncf_downside_upside_net_derisk_score.py"
    assert "auxiliary_policy_lift_shadow_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in lift_cmd)
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in lift_cmd)
    assert lift_cmd[lift_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json"
    )
    churn_cmd = commands["auxiliary_churn_shadow_2608_15841"]
    assert churn_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_churn_shadow.py"
    assert "auxiliary_churn_shadow_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert churn_cmd[churn_cmd.index("--policy-lift") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json"
    )
    assert churn_cmd[churn_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json"
    )
    wf_cmd = commands["auxiliary_purged_walkforward_2608_15841"]
    assert wf_cmd[1] == "scripts/evaluate/evaluate_group_a_plus_2608_15841_auxiliary_purged_walkforward.py"
    assert "auxiliary_purged_walkforward_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("auxiliary_policy_lift_shadow_2608_15841") < list(commands).index(
        "auxiliary_churn_shadow_2608_15841"
    )
    assert list(commands).index("auxiliary_churn_shadow_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert list(commands).index("auxiliary_purged_walkforward_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in wf_cmd)
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in wf_cmd)
    regime_decay_cmd = commands["auxiliary_regime_decay_audit_2608_15841"]
    assert regime_decay_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py"
    assert "auxiliary_regime_decay_audit_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("auxiliary_regime_decay_audit_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in regime_decay_cmd)
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in regime_decay_cmd)
    assert any(item.endswith("results/ncf_0050_panel_latest_20260627.csv") for item in regime_decay_cmd)
    assert regime_decay_cmd[regime_decay_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json"
    )
    lifecycle_cmd = commands["auxiliary_lifecycle_audit_2608_15841"]
    assert lifecycle_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py"
    assert "auxiliary_lifecycle_audit_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("auxiliary_regime_decay_audit_2608_15841") < list(commands).index(
        "auxiliary_lifecycle_audit_2608_15841"
    )
    assert list(commands).index("auxiliary_lifecycle_audit_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert lifecycle_cmd[lifecycle_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json"
    )
    delayed_cmd = commands["delayed_credit_audit_2608_15841"]
    assert delayed_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_delayed_credit_audit.py"
    assert "delayed_credit_audit_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("delayed_credit_audit_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in delayed_cmd)
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in delayed_cmd)
    assert any(item.endswith("results/ncf_0050_panel_latest_20260627.csv") for item in delayed_cmd)
    assert delayed_cmd[delayed_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_delayed_credit_audit.json"
    )
    blueprint_cmd = commands["candidate_auxiliary_bank_blueprint_2608_15841"]
    assert blueprint_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py"
    assert "candidate_auxiliary_bank_blueprint_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("candidate_auxiliary_bank_blueprint_2608_15841") < list(commands).index(
        "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert blueprint_cmd[blueprint_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json"
    )
    aux_cmd = commands["auxiliary_task_discovery_readiness_2608_15841"]
    assert aux_cmd[1] == "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py"
    assert "auxiliary_task_discovery_readiness_2608_15841" in module.BEST_EFFORT_STEP_NAMES
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in aux_cmd)
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in aux_cmd)
    assert any(item.endswith("results/ncf_0050_panel_latest_20260627.csv") for item in aux_cmd)
    assert any(item.endswith("results/ncf_00631l_latest_20260627.json") for item in aux_cmd)
    assert any(item.endswith("results/ncf_00632r_latest_20260627.json") for item in aux_cmd)
    assert any(item.endswith("results/ncf_0050_latest_20260627.json") for item in aux_cmd)
    assert aux_cmd[aux_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json"
    )
    assert aux_cmd[aux_cmd.index("--policy-lift") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json"
    )
    assert aux_cmd[aux_cmd.index("--purged-wf") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json"
    )
    assert aux_cmd[aux_cmd.index("--churn-shadow") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json"
    )
    assert aux_cmd[aux_cmd.index("--regime-decay") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json"
    )
    assert aux_cmd[aux_cmd.index("--candidate-bank-blueprint") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json"
    )
    assert aux_cmd[aux_cmd.index("--lifecycle-audit") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json"
    )
    assert aux_cmd[aux_cmd.index("--delayed-credit") + 1].endswith(
        "report/group_a_plus/latest/2608_15841_delayed_credit_audit.json"
    )
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.json") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.csv") for item in commands["ncf_panel_drift"])
    assert "--outcome-aware" in commands["ncf_panel_drift"]
    assert commands["ncf_panel_refresh_recommendation"][1] == (
        "scripts/evaluate/build_ncf_panel_refresh_recommendation.py"
    )
    assert commands["ncf_panel_refresh_recommendation"][
        commands["ncf_panel_refresh_recommendation"].index("--drift-audit") + 1
    ].endswith("results/ncf_panel_drift_active_vs_20260627.json")
    assert commands["ncf_panel_refresh_recommendation"][
        commands["ncf_panel_refresh_recommendation"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/ncf_panel_refresh_recommendation.json")
    assert commands["ncf_panel_refresh_recommendation"][
        commands["ncf_panel_refresh_recommendation"].index("--snapshot-output") + 1
    ].endswith("results/ncf_panel_refresh_recommendation_20260627.json")
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
    assert commands["ncf_panel_drift_diagnosis"][
        commands["ncf_panel_drift_diagnosis"].index("--baseline-no-external-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260630_no_external.csv")
    assert commands["ncf_panel_drift_diagnosis"][
        commands["ncf_panel_drift_diagnosis"].index("--candidate-no-external-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627_no_external.csv")
    assert commands["ncf_panel_drift_diagnosis"][
        commands["ncf_panel_drift_diagnosis"].index("--sensitivity-audit") + 1
    ].endswith("results/ncf_panel_drift_no_external_vs_external_20260627.json")
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
    assert commands["ncf_panel_drift_no_tabnet_baseline_vs_today"][1] == (
        "scripts/evaluate/evaluate_ncf_panel_drift.py"
    )
    assert commands["ncf_panel_drift_no_tabnet_baseline_vs_today"][
        commands["ncf_panel_drift_no_tabnet_baseline_vs_today"].index("--baseline-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260630_no_tabnet.csv")
    assert commands["ncf_panel_drift_no_tabnet_baseline_vs_today"][
        commands["ncf_panel_drift_no_tabnet_baseline_vs_today"].index("--candidate-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["ncf_panel_drift_no_tabnet_baseline_vs_today"][
        commands["ncf_panel_drift_no_tabnet_baseline_vs_today"].index("--output") + 1
    ].endswith("results/ncf_panel_drift_no_tabnet_baseline_vs_20260627.json")
    assert commands["ncf_panel_drift_model_set_isolation_report"][1] == (
        "scripts/evaluate/build_ncf_panel_drift_model_set_isolation_report.py"
    )
    assert commands["ncf_panel_drift_model_set_isolation_report"][
        commands["ncf_panel_drift_model_set_isolation_report"].index("--original-vs-today") + 1
    ].endswith("results/ncf_panel_drift_active_vs_20260627.json")
    assert commands["ncf_panel_drift_model_set_isolation_report"][
        commands["ncf_panel_drift_model_set_isolation_report"].index("--original-vs-no-tabnet") + 1
    ].endswith("results/ncf_panel_drift_tabnet_vs_no_tabnet_20260630.json")
    assert commands["ncf_panel_drift_model_set_isolation_report"][
        commands["ncf_panel_drift_model_set_isolation_report"].index("--no-tabnet-vs-today") + 1
    ].endswith("results/ncf_panel_drift_no_tabnet_baseline_vs_20260627.json")
    assert commands["ncf_panel_same_method_baseline_manifest"][1] == (
        "scripts/evaluate/build_ncf_panel_same_method_baseline_manifest.py"
    )
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--original-baseline-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260630.csv")
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--same-method-baseline-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260630_no_tabnet.csv")
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--same-method-baseline-signal") + 1
    ].endswith("results/ncf_00631l_latest_20260630_no_tabnet.json")
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--validation-drift-audit") + 1
    ].endswith("results/ncf_panel_drift_no_tabnet_baseline_vs_20260627.json")
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--isolation-report") + 1
    ].endswith("results/ncf_panel_drift_model_set_isolation_report_20260627.json")
    assert commands["ncf_panel_same_method_baseline_manifest"][
        commands["ncf_panel_same_method_baseline_manifest"].index("--output") + 1
    ].endswith("results/ncf_panel_same_method_baseline_manifest_20260627.json")
    assert commands["ncf_panel_drift_no_external_vs_external"][1] == "scripts/evaluate/evaluate_ncf_panel_drift.py"
    assert commands["ncf_panel_drift_no_external_vs_external"][
        commands["ncf_panel_drift_no_external_vs_external"].index("--baseline-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627_no_external.csv")
    assert commands["ncf_panel_drift_no_external_vs_external"][
        commands["ncf_panel_drift_no_external_vs_external"].index("--candidate-panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["ncf_panel_drift_no_external_vs_external"][
        commands["ncf_panel_drift_no_external_vs_external"].index("--output") + 1
    ].endswith("results/ncf_panel_drift_no_external_vs_external_20260627.json")
    assert "--outcome-aware" in commands["ncf_panel_drift_no_external_vs_external"]
    for best_effort_name in (
        "ncf_00631l_no_external_shadow",
        "ncf_panel_refresh_recommendation",
        "ncf_panel_drift_no_tabnet_baseline_vs_today",
        "ncf_panel_drift_model_set_isolation_report",
        "ncf_panel_same_method_baseline_manifest",
        "ncf_panel_drift_no_external_vs_external",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
    ):
        assert best_effort_name in module.BEST_EFFORT_STEP_NAMES
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
    assert commands["gjr_garch_shadow"][1] == "scripts/evaluate/build_group_a_plus_gjr_garch_shadow.py"
    assert commands["gjr_garch_shadow"][commands["gjr_garch_shadow"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/gjr_garch_shadow.json"
    )
    assert commands["gjr_garch_shadow"][commands["gjr_garch_shadow"].index("--log") + 1].endswith(
        "results/gjr_garch_shadow_log.jsonl"
    )
    assert "gjr_garch_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["dfl_advisory"][1] == "scripts/run/build_a2118_dfl_advisory.py"
    assert "--input" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_dfl_main_latest.json"
    )
    assert "--selective-inputs" in commands["dfl_advisory"]
    selective_inputs = commands["dfl_advisory"][commands["dfl_advisory"].index("--selective-inputs") + 1]
    assert "p50=results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json" in selective_inputs
    assert "p70=results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json" in selective_inputs
    assert "--live-signal" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert commands["dfl_active_date_audit"][1] == "scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py"
    assert "--input" in commands["dfl_active_date_audit"]
    assert commands["dfl_active_date_audit"][commands["dfl_active_date_audit"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_dfl_main_latest.json"
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
    assert commands["a2118_seed_averaging_live_inference_snapshot"][1] == (
        "scripts/evaluate/build_a2118_seed_averaging_live_inference_snapshot.py"
    )
    seed_inference_cmd = commands["a2118_seed_averaging_live_inference_snapshot"]
    assert seed_inference_cmd[seed_inference_cmd.index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert seed_inference_cmd[seed_inference_cmd.index("--holdings-snapshot") + 1].endswith(
        "report/group_a_plus/latest/holdings_authoritative_snapshot.json"
    )
    assert seed_inference_cmd[seed_inference_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
    )
    assert commands["a2118_seed_averaging_forward_shadow_monitor"][1] == (
        "scripts/evaluate/build_a2118_seed_averaging_forward_shadow_monitor.py"
    )
    seed_monitor_cmd = commands["a2118_seed_averaging_forward_shadow_monitor"]
    assert seed_monitor_cmd[seed_monitor_cmd.index("--shadow") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_shadow.json"
    )
    assert seed_monitor_cmd[seed_monitor_cmd.index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert seed_monitor_cmd[seed_monitor_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
    )
    assert seed_monitor_cmd[seed_monitor_cmd.index("--log") + 1].endswith(
        "results/a2118_seed_averaging_forward_shadow_monitor_log.jsonl"
    )
    assert seed_monitor_cmd[seed_monitor_cmd.index("--optional-inference-snapshot") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
    )
    assert "a2118_seed_averaging_live_inference_snapshot" in module.BEST_EFFORT_STEP_NAMES
    assert "a2118_seed_averaging_forward_shadow_monitor" in module.BEST_EFFORT_STEP_NAMES
    assert commands["a2118_seed_averaging_promotion_gate"][1] == (
        "scripts/evaluate/build_a2118_seed_averaging_promotion_gate.py"
    )
    seed_gate_cmd = commands["a2118_seed_averaging_promotion_gate"]
    assert seed_gate_cmd[seed_gate_cmd.index("--monitor") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
    )
    assert seed_gate_cmd[seed_gate_cmd.index("--log") + 1].endswith(
        "results/a2118_seed_averaging_forward_shadow_monitor_log.jsonl"
    )
    assert seed_gate_cmd[seed_gate_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_promotion_gate.json"
    )
    assert "a2118_seed_averaging_promotion_gate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["a2118_risk_down_mapped_shadow"][1] == (
        "scripts/evaluate/build_a2118_risk_down_mapped_shadow.py"
    )
    assert "a2118_risk_down_mapped_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2606_09104_00631l_regime_split"][1] == (
        "scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_regime_split.py"
    )
    assert commands["paper_2606_09104_00631l_staged_ladder_readiness"][1] == (
        "scripts/evaluate/build_group_a_plus_2606_09104_00631l_staged_ladder_readiness.py"
    )
    staged_ladder_cmd = commands["paper_2606_09104_00631l_staged_ladder_readiness"]
    assert staged_ladder_cmd[staged_ladder_cmd.index("--live-snapshot") + 1].endswith(
        "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
    )
    assert staged_ladder_cmd[staged_ladder_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json"
    )
    assert commands["paper_2606_09104_extreme_state_monitor"][1] == (
        "scripts/evaluate/build_group_a_plus_2606_09104_extreme_state_monitor.py"
    )
    extreme_monitor_cmd = commands["paper_2606_09104_extreme_state_monitor"]
    assert extreme_monitor_cmd[extreme_monitor_cmd.index("--ladder") + 1].endswith(
        "report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json"
    )
    assert extreme_monitor_cmd[extreme_monitor_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/2606_09104_extreme_state_monitor.json"
    )
    assert "paper_2606_09104_00631l_regime_split" in module.BEST_EFFORT_STEP_NAMES
    assert "paper_2606_09104_00631l_staged_ladder_readiness" in module.BEST_EFFORT_STEP_NAMES
    assert "paper_2606_09104_extreme_state_monitor" in module.BEST_EFFORT_STEP_NAMES
    assert commands["relative_reentry_opportunity_shadow"][1] == (
        "scripts/evaluate/evaluate_00631l_0050_relative_reentry_opportunity.py"
    )
    relative_cmd = commands["relative_reentry_opportunity_shadow"]
    relative_windows = relative_cmd[relative_cmd.index("--windows") + 1]
    assert "live_2024_2026:2024-01-02:latest:" in relative_windows
    assert "active_2025_2026:2025-01-02:latest:" in relative_windows
    assert "results/ncf_00631l_panel_latest_20260627.csv:tuning_window" in relative_windows
    assert "2018_correction:2018-01-02:2018-12-31:" in relative_windows
    assert relative_cmd[relative_cmd.index("--actions") + 1] == "KEEP,SHIFT_00631L_2,SHIFT_00631L_5"
    assert "--slow-bear-gate" in relative_cmd
    assert "--risk-up-permission-gate" in relative_cmd
    assert relative_cmd[relative_cmd.index("--risk-up-permission-min-probability") + 1] == "0.50"
    assert relative_cmd[relative_cmd.index("--output") + 1].endswith(
        "results/00631l_0050_relative_reentry_opportunity_latest.json"
    )
    assert relative_cmd[relative_cmd.index("--latest-output") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_opportunity_shadow.json"
    )
    assert "relative_reentry_opportunity_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["relative_reentry_advisory_shadow"][1] == (
        "scripts/run/build_00631l_0050_relative_reentry_advisory_shadow.py"
    )
    advisory_cmd = commands["relative_reentry_advisory_shadow"]
    assert advisory_cmd[advisory_cmd.index("--input") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_opportunity_shadow.json"
    )
    assert advisory_cmd[advisory_cmd.index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert advisory_cmd[advisory_cmd.index("--strategy-trust-log") + 1].endswith(
        "results/strategy_trust_shadow_log.jsonl"
    )
    assert advisory_cmd[advisory_cmd.index("--risk-mechanism-log") + 1].endswith(
        "results/risk_mechanism_shadow_log.jsonl"
    )
    assert advisory_cmd[advisory_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_advisory_shadow.json"
    )
    assert advisory_cmd[advisory_cmd.index("--output-md") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_advisory_shadow.md"
    )
    assert "relative_reentry_advisory_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["relative_reentry_candidate_review"][1] == (
        "scripts/evaluate/build_00631l_0050_relative_reentry_candidate_review.py"
    )
    candidate_review_cmd = commands["relative_reentry_candidate_review"]
    assert candidate_review_cmd[candidate_review_cmd.index("--input") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_opportunity_shadow.json"
    )
    assert candidate_review_cmd[candidate_review_cmd.index("--advisory") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_advisory_shadow.json"
    )
    assert candidate_review_cmd[candidate_review_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_candidate_review.json"
    )
    assert candidate_review_cmd[candidate_review_cmd.index("--output-md") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_candidate_review.md"
    )
    assert "relative_reentry_candidate_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["relative_reentry_promotion_gate"][1] == (
        "scripts/evaluate/build_00631l_0050_relative_reentry_promotion_gate.py"
    )
    promotion_gate_cmd = commands["relative_reentry_promotion_gate"]
    assert promotion_gate_cmd[promotion_gate_cmd.index("--advisory") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_advisory_shadow.json"
    )
    assert promotion_gate_cmd[promotion_gate_cmd.index("--review") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_candidate_review.json"
    )
    assert promotion_gate_cmd[promotion_gate_cmd.index("--output") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_promotion_gate.json"
    )
    assert promotion_gate_cmd[promotion_gate_cmd.index("--output-md") + 1].endswith(
        "report/group_a_plus/latest/relative_reentry_promotion_gate.md"
    )
    assert "relative_reentry_promotion_gate" in module.BEST_EFFORT_STEP_NAMES
    assert commands["staged_reentry_event_study"][1] == (
        "scripts/evaluate/build_group_a_plus_staged_reentry_shadow.py"
    )
    assert "--evaluate-history" in commands["staged_reentry_event_study"]
    assert "staged_reentry_event_study" in module.BEST_EFFORT_STEP_NAMES
    assert commands["staged_reentry_promotion_review"][1] == (
        "scripts/evaluate/build_group_a_plus_staged_reentry_promotion_review.py"
    )
    assert "staged_reentry_promotion_review" in module.BEST_EFFORT_STEP_NAMES
    assert commands["staged_reentry_confirmatory_tracker_2609_04917"][1] == (
        "scripts/evaluate/build_group_a_plusplus_2609_04917_staged_reentry_confirmatory_tracker.py"
    )
    assert commands["staged_reentry_confirmatory_tracker_2609_04917"][
        commands["staged_reentry_confirmatory_tracker_2609_04917"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_04917_staged_reentry_confirmatory_tracker.json")
    assert commands["staged_reentry_confirmatory_tracker_2609_04917"][
        commands["staged_reentry_confirmatory_tracker_2609_04917"].index("--markdown") + 1
    ].endswith("report/group_a_plus/latest/2609_04917_staged_reentry_confirmatory_tracker.md")
    assert "staged_reentry_confirmatory_tracker_2609_04917" in module.BEST_EFFORT_STEP_NAMES
    assert commands["ncf_decision_calibration_shadow"][1] == "scripts/evaluate/evaluate_ncf_decision_calibration.py"
    assert commands["ncf_decision_calibration_shadow"][
        commands["ncf_decision_calibration_shadow"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert commands["ncf_decision_calibration_shadow"][
        commands["ncf_decision_calibration_shadow"].index("--advisory") + 1
    ].endswith("report/group_a_plus/latest/a2118_dfl_advisory.json")
    assert commands["ncf_decision_calibration_shadow"][
        commands["ncf_decision_calibration_shadow"].index("--dfl-shadow") + 1
    ].endswith("results/a2118_decision_focused_action_shadow_dfl_main_latest.json")
    assert commands["ncf_decision_calibration_shadow"][
        commands["ncf_decision_calibration_shadow"].index("--output") + 1
    ].endswith("results/ncf_decision_calibration_shadow_20260627.json")
    assert "ncf_decision_calibration_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["tsi_stress_shadow"][1] == "scripts/evaluate/build_group_a_plus_tsi_stress_shadow.py"
    assert commands["tsi_stress_shadow"][commands["tsi_stress_shadow"].index("--as-of") + 1] == "2026-06-27"
    assert commands["tsi_stress_shadow"][commands["tsi_stress_shadow"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/tsi_stress_shadow.json"
    )
    assert commands["tsi_stress_shadow"][commands["tsi_stress_shadow"].index("--history-dir") + 1].endswith(
        "report/group_a_plus/tsi_stress_shadow/history"
    )
    assert "tsi_stress_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["tsi_stress_oos"][1] == "scripts/evaluate/evaluate_group_a_plus_tsi_stress_oos.py"
    assert commands["tsi_stress_oos"][commands["tsi_stress_oos"].index("--as-of") + 1] == "2026-06-27"
    assert commands["tsi_stress_oos"][commands["tsi_stress_oos"].index("--output-md") + 1].endswith(
        "report/group_a_plus/latest/tsi_stress_oos.md"
    )
    assert "tsi_stress_oos" in module.BEST_EFFORT_STEP_NAMES
    assert commands["tsi_no_add_shadow"][1] == "scripts/evaluate/evaluate_group_a_plus_tsi_no_add_shadow.py"
    assert commands["tsi_no_add_shadow"][commands["tsi_no_add_shadow"].index("--threshold") + 1] == "0.90"
    assert commands["tsi_no_add_shadow"][commands["tsi_no_add_shadow"].index("--output") + 1].endswith(
        "report/group_a_plus/latest/tsi_no_add_shadow.json"
    )
    assert "tsi_no_add_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["daily_artifact_integrity"][1] == (
        "scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py"
    )
    assert commands["daily_artifact_integrity"][
        commands["daily_artifact_integrity"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["daily_artifact_integrity"][
        commands["daily_artifact_integrity"].index("--execution-plan") + 1
    ].endswith("report/group_a_plus/latest/execution_plan.json")
    assert commands["daily_artifact_integrity"][
        commands["daily_artifact_integrity"].index("--panel-refresh-recommendation") + 1
    ].endswith("report/group_a_plus/latest/ncf_panel_refresh_recommendation.json")
    assert commands["daily_artifact_integrity"][
        commands["daily_artifact_integrity"].index("--ncf-decision-calibration") + 1
    ].endswith("results/ncf_decision_calibration_shadow_20260627.json")
    assert commands["daily_artifact_integrity"][
        commands["daily_artifact_integrity"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/daily_artifact_integrity.json")
    assert "daily_artifact_integrity" in module.BEST_EFFORT_STEP_NAMES
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
    assert "--scr-readiness-review-2602-24037" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--scr-readiness-review-2602-24037") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_review.json")
    assert "--scr-readiness-robustness-2602-24037" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--scr-readiness-robustness-2602-24037") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json")
    assert "--scr-readiness-window-split-2602-24037" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--scr-readiness-window-split-2602-24037") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json")
    assert "--scr-scenario-stress-score-2602-24037" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--scr-scenario-stress-score-2602-24037") + 1
    ].endswith("report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json")
    assert "--dynamic-cvar-tail-cost-readiness-review" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--dynamic-cvar-tail-cost-readiness-review") + 1
    ].endswith("report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json")
    assert "--cvar-cost-window-split-2606-26625" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--cvar-cost-window-split-2606-26625") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json")
    assert "--rolling-tail-no-add-2606-26625" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--rolling-tail-no-add-2606-26625") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json")
    assert "--dynamic-cvar-constraint-2608-20179" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--dynamic-cvar-constraint-2608-20179") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.json")
    assert "--dynamic-cvar-forward-2608-20179" in commands["daily_status"]
    assert commands["daily_status"][
        commands["daily_status"].index("--dynamic-cvar-forward-2608-20179") + 1
    ].endswith("report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json")
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
    assert "--daily-artifact-integrity" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--daily-artifact-integrity") + 1].endswith(
        "report/group_a_plus/latest/daily_artifact_integrity.json"
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
    assert commands["golden2_promotion_candidate_review"][1] == (
        "scripts/evaluate/build_group_a_plus_golden2_promotion_candidate_review.py"
    )
    assert commands["golden2_promotion_candidate_review"][
        commands["golden2_promotion_candidate_review"].index("--promotion-gate") + 1
    ].endswith("results/group_a_plus_promotion_gate_20260627.json")
    assert commands["golden2_promotion_candidate_review"][
        commands["golden2_promotion_candidate_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/golden2_promotion_candidate_review.json")
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
    assert commands["moira_relative_exposure_thesis_shadow"][1] == (
        "scripts/evaluate/build_group_a_plus_relative_exposure_thesis_shadow.py"
    )
    assert commands["moira_relative_exposure_thesis_shadow"][
        commands["moira_relative_exposure_thesis_shadow"].index("--live-signal") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["moira_relative_exposure_thesis_shadow"][
        commands["moira_relative_exposure_thesis_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/relative_exposure_thesis_shadow.json")
    assert "moira_relative_exposure_thesis_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["moira_hierarchical_credit_review_shadow"][1] == (
        "scripts/evaluate/build_group_a_plus_hierarchical_credit_review_shadow.py"
    )
    assert commands["moira_hierarchical_credit_review_shadow"][
        commands["moira_hierarchical_credit_review_shadow"].index("--forecast") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert commands["moira_hierarchical_credit_review_shadow"][
        commands["moira_hierarchical_credit_review_shadow"].index("--actual") + 1
    ].endswith("results/group_a_plus_live_signal_v2_20260627.json")
    assert "moira_hierarchical_credit_review_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["moira_event_aware_execution_quality_shadow"][1] == (
        "scripts/evaluate/build_group_a_plus_event_aware_execution_quality_shadow.py"
    )
    assert commands["moira_event_aware_execution_quality_shadow"][
        commands["moira_event_aware_execution_quality_shadow"].index("--execution-plan") + 1
    ].endswith("report/group_a_plus/latest/execution_plan.json")
    assert commands["moira_event_aware_execution_quality_shadow"][
        commands["moira_event_aware_execution_quality_shadow"].index("--liquidity-feedback") + 1
    ].endswith("report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json")
    assert "moira_event_aware_execution_quality_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["moira_policy_critic_shadow"][1] == (
        "scripts/evaluate/build_group_a_plus_moira_policy_critic_shadow.py"
    )
    assert commands["moira_policy_critic_shadow"][
        commands["moira_policy_critic_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/moira_policy_critic_shadow.json")
    assert "moira_policy_critic_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["moira_policy_critic_validation_shadow"][1] == (
        "scripts/evaluate/validate_group_a_plus_moira_policy_critic_shadow.py"
    )
    assert commands["moira_policy_critic_validation_shadow"][
        commands["moira_policy_critic_validation_shadow"].index("--signal-glob") + 1
    ] == "results/group_a_plus_live_signal_v2_2026*.json"
    assert commands["moira_policy_critic_validation_shadow"][
        commands["moira_policy_critic_validation_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/moira_policy_critic_validation_shadow.json")
    assert "moira_policy_critic_validation_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["moira_execution_guard_hard_stop_backtest_shadow"][1] == (
        "scripts/evaluate/backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py"
    )
    assert commands["moira_execution_guard_hard_stop_backtest_shadow"][
        commands["moira_execution_guard_hard_stop_backtest_shadow"].index("--signal-glob") + 1
    ] == "results/group_a_plus_live_signal_v2_2026*.json"
    assert commands["moira_execution_guard_hard_stop_backtest_shadow"][
        commands["moira_execution_guard_hard_stop_backtest_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/moira_execution_guard_hard_stop_backtest_shadow.json")
    assert "moira_execution_guard_hard_stop_backtest_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["daily_semantic_context_summary"][1] == (
        "scripts/evaluate/build_group_a_plus_daily_semantic_context_summary.py"
    )
    assert commands["daily_semantic_context_summary"][
        commands["daily_semantic_context_summary"].index("--critic") + 1
    ].endswith("report/group_a_plus/latest/moira_policy_critic_shadow.json")
    assert commands["daily_semantic_context_summary"][
        commands["daily_semantic_context_summary"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/daily_semantic_context_summary.json")
    assert "daily_semantic_context_summary" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2609_08106_complementarity_forward_shadow"][1] == (
        "scripts/run/build_group_a_plus_2609_08106_complementarity_forward_shadow.py"
    )
    assert commands["paper_2609_08106_complementarity_forward_shadow"][
        commands["paper_2609_08106_complementarity_forward_shadow"].index("--as-of") + 1
    ] == "2026-06-27"
    assert commands["paper_2609_08106_complementarity_forward_shadow"][
        commands["paper_2609_08106_complementarity_forward_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_complementarity_forward_shadow_latest.json")
    assert commands["paper_2609_08106_complementarity_forward_shadow"][
        commands["paper_2609_08106_complementarity_forward_shadow"].index("--log") + 1
    ].endswith("results/2609_08106_complementarity_forward_shadow_log.jsonl")
    assert "paper_2609_08106_complementarity_forward_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2609_08106_latest_target_weight_replay"][1] == (
        "scripts/evaluate/replay_group_a_plus_2609_08106_latest_target_weights.py"
    )
    assert commands["paper_2609_08106_latest_target_weight_replay"][
        commands["paper_2609_08106_latest_target_weight_replay"].index("--target-weights") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.csv")
    assert commands["paper_2609_08106_latest_target_weight_replay"][
        commands["paper_2609_08106_latest_target_weight_replay"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_latest_target_weight_replay.json")
    assert "paper_2609_08106_latest_target_weight_replay" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2609_08106_latest_target_weight_param_sweep"][1] == (
        "scripts/evaluate/sweep_group_a_plus_2609_08106_latest_target_replay_params.py"
    )
    assert commands["paper_2609_08106_latest_target_weight_param_sweep"][
        commands["paper_2609_08106_latest_target_weight_param_sweep"].index("--target-weights") + 1
    ].endswith("report/group_a_plus/latest/latest_strategy_historical_target_weights.csv")
    assert commands["paper_2609_08106_latest_target_weight_param_sweep"][
        commands["paper_2609_08106_latest_target_weight_param_sweep"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_latest_target_weight_replay_param_sweep.json")
    assert "paper_2609_08106_latest_target_weight_param_sweep" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2609_08106_adoption_matrix"][1] == (
        "scripts/evaluate/build_group_a_plus_2609_08106_adoption_matrix.py"
    )
    assert commands["paper_2609_08106_adoption_matrix"][
        commands["paper_2609_08106_adoption_matrix"].index("--latest-target-replay") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_latest_target_weight_replay.json")
    assert commands["paper_2609_08106_adoption_matrix"][
        commands["paper_2609_08106_adoption_matrix"].index("--latest-target-param-sweep") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_latest_target_weight_replay_param_sweep.json")
    assert commands["paper_2609_08106_adoption_matrix"][
        commands["paper_2609_08106_adoption_matrix"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_adoption_matrix.json")
    assert "paper_2609_08106_adoption_matrix" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_2609_07989_order_flow_regime_shadow"][1] == (
        "scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py"
    )
    assert commands["paper_2609_07989_order_flow_regime_shadow"][
        commands["paper_2609_07989_order_flow_regime_shadow"].index("--input") + 1
    ].endswith("results/intraday_signed_order_flow_latest.csv")
    assert commands["paper_2609_07989_order_flow_regime_shadow"][
        commands["paper_2609_07989_order_flow_regime_shadow"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.json")
    assert commands["paper_2609_07989_order_flow_regime_shadow"][
        commands["paper_2609_07989_order_flow_regime_shadow"].index("--log") + 1
    ].endswith("results/2609_07989_order_flow_regime_shadow_log.jsonl")
    assert "paper_2609_07989_order_flow_regime_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert commands["paper_convergence_review"][1] == (
        "scripts/evaluate/build_group_a_plus_paper_convergence_review.py"
    )
    assert commands["paper_convergence_review"][
        commands["paper_convergence_review"].index("--output") + 1
    ].endswith("report/group_a_plus/latest/paper_convergence_review.json")
    assert commands["paper_convergence_review"][
        commands["paper_convergence_review"].index("--cvar-cost-window-split") + 1
    ].endswith("report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json")
    assert commands["paper_convergence_review"][
        commands["paper_convergence_review"].index("--history-dir") + 1
    ].endswith("report/group_a_plus/paper_convergence_review/history")
    assert commands["paper_convergence_review"][
        commands["paper_convergence_review"].index("--adoption-2609-08106") + 1
    ].endswith("report/group_a_plus/latest/2609_08106_adoption_matrix.json")
    assert "paper_convergence_review" in module.BEST_EFFORT_STEP_NAMES
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
        "ncf_data_validation",
            "ncf_00631l",
            "ncf_00632r",
            "ncf_0050",
            "ncf_00713",
            "ncf_signal_archive",
            "ncf_2330",
            "ncf_panel_manifest",
            "ncf_0050_threshold_eval",
                "ctbc_debounce_shadow_2509_02986",
                "ctbc_00713_debounce_shadow_2509_02986",
                "ctbc_00713_domain_randomization_2509_02986",
                "ctbc_groupa_plusplus_review_2509_02986",
                "ctbc_promotion_readiness_gate_2509_02986",
            "auxiliary_policy_lift_shadow_2608_15841",
        "auxiliary_churn_shadow_2608_15841",
        "auxiliary_purged_walkforward_2608_15841",
        "auxiliary_regime_decay_audit_2608_15841",
        "auxiliary_lifecycle_audit_2608_15841",
        "delayed_credit_audit_2608_15841",
        "candidate_auxiliary_bank_blueprint_2608_15841",
        "auxiliary_task_discovery_readiness_2608_15841",
        "ncf_panel_drift",
        "ncf_panel_refresh_recommendation",
        "ncf_panel_drift_diagnosis",
        "panel_drift_triage",
        "ncf_panel_drift_remediation_plan_initial",
        "ncf_panel_drift_no_tabnet_baseline_vs_today",
        "ncf_panel_drift_model_set_isolation_report",
        "ncf_panel_same_method_baseline_manifest",
        "external_sensitivity_observation_log",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "golden1_combined_signal",
        "daily_signal",
        "riccati_mv_shadow",
        "current_policy_re_evaluation_gate",
        "rebalance_review",
        "compounding_regime",
        "gjr_garch_shadow",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "add_0050_instead_shadow_log",
        "adaptive_review_interval_shadow_log",
        "gatedlinear_drawdown_forecast_shadow_log",
        "cvar_tail_risk_diagnostic",
        "taiwan_etf_2607_16450_review",
        "taiwan_etf_2607_16450_tail_scorecard",
        "taiwan_etf_2607_16450_cost_robustness",
        "taiwan_etf_2607_16450_candidate_tail_review",
        "taiwan_etf_2607_16450_regime_vol_forecast_quality",
        "taiwan_etf_2607_16450_regime_vol_gate",
            "taiwan_etf_2607_16450_tail_dependence_monitor",
            "taiwan_etf_2607_16450_geopolitical_cvar_overlay",
            "taiwan_etf_2607_16450_bootstrap_promotion_gate",
            "paper_2609_07946_00635u_instrument_review",
            "paper_2609_07946_stock_bond_gold_forward_shadow",
            "paper_2609_07946_bond_only_forward_shadow",
            "paper_2609_07946_complementarity_promotion_gate",
            "paper_2609_07946_adoption_matrix",
            "paper_2609_08106_complementarity_forward_shadow",
            "paper_2609_08106_latest_target_weight_replay",
            "paper_2609_08106_latest_target_weight_param_sweep",
            "paper_2609_08106_adoption_matrix",
            "paper_2609_07989_order_flow_regime_shadow",
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
            "scr_readiness_review_2602_24037",
            "scr_readiness_robustness_2602_24037",
            "scr_readiness_window_split_2602_24037",
            "scr_scenario_stress_score_2602_24037",
            "cvar_cost_window_split_2606_26625",
            "rolling_tail_no_add_gate_2606_26625",
            "dynamic_cvar_constraint_shadow_2608_20179",
            "dynamic_cvar_forward_validation_2608_20179",
            "dynamic_cvar_tail_cost_readiness_review",
            "synthetic_augmentation_validation_audit",
            "synthetic_augmentation_validation_readiness_review",
        "intervention_history",
        "broker_holdings_time_series_sample",
        "broker_holdings_reconciliation_review",
        "assigned_realized_deployment_shadow_2608_08405",
        "capacity_grid_shadow_2608_08405",
        "erosion_persistence_shadow_2608_08405",
        "instrument_readiness_shadow_2608_08405",
        "ramp_path_dependence_shadow_2608_08405",
            "capacity_crowding_readiness_2608_08405",
            "intervention_fatigue_risk_budget_readiness_review",
            "letf_tracking_error_effective_fee_readiness_review",
            "00632r_discipline_guard",
            "letf_liquidity_feedback_watch_shadow_backtest",
            "asian_etf_tail_analytics_readiness_review",
            "gift_human_exception_record_draft",
            "gift_human_exception_approval_record_schema",
            "gift_signed_approval_record_template",
            "gift_signed_approval_validation",
            "gift_signed_approval_checklist_review",
            "gift_signed_approval_validator_smoke",
            "gift_manual_approval_readiness",
                "gift_pdf_advantage_coverage_review",
        "defensive_cash_floor_signed_approval_validation",
        "defensive_cash_floor_guarded_candidate",
        "defensive_cash_floor_guarded_monitor",
        "ncf_panel_drift_auto_attribution",
        "dfl_shadow_refresh_main",
        "dfl_shadow_refresh_p50",
        "dfl_shadow_refresh_p70",
        "dfl_advisory",
            "dfl_shadow_refresh_overlap",
            "dfl_active_date_audit",
            "dfl_shadow_ensemble",
            "a2118_seed_averaging_live_inference_snapshot",
                "a2118_seed_averaging_forward_shadow_monitor",
                "a2118_seed_averaging_promotion_gate",
                "a2118_risk_down_mapped_shadow",
                "paper_2606_09104_00631l_regime_split",
                "paper_2606_09104_00631l_staged_ladder_readiness",
                "paper_2606_09104_extreme_state_monitor",
                "relative_reentry_opportunity_shadow",
                "relative_reentry_advisory_shadow",
                "relative_reentry_candidate_review",
        "relative_reentry_promotion_gate",
        "staged_reentry_event_study",
        "staged_reentry_promotion_review",
        "staged_reentry_confirmatory_tracker_2609_04917",
        "ncf_decision_calibration_shadow",
        "tsi_stress_shadow",
        "tsi_stress_oos",
        "tsi_no_add_shadow",
        "daily_artifact_integrity",
            "research_shadow_decision_snapshot",
            "research_governance_gate",
            "shadow_artifact_registry",
            "latest_strategy_target_weight_export",
            "latest_strategy_explain_snapshot",
            "data_freshness_gate",
            "golden_release_separation_audit",
                    "daily_status",
                    "deployment_consistency_review",
                    "deployment_summary",
                    "promotion_gate",
                    "golden2_same_window_candidate_backtests",
                    "golden2_multi_window_gate",
                    "golden2_promotion_candidate_review",
            "multi_window_failure_attribution",
        "promotion_blocked_diagnostic",
        "daily_status_final",
        "moira_relative_exposure_thesis_shadow",
        "moira_hierarchical_credit_review_shadow",
        "moira_event_aware_execution_quality_shadow",
        "moira_policy_critic_shadow",
                "moira_policy_critic_validation_shadow",
                "moira_execution_guard_hard_stop_backtest_shadow",
                "daily_semantic_context_summary",
            "paper_convergence_review",
            "final_governance_snapshot",
            "ncf_2330_checklist",
        ]
    assert "--no-external-features" in commands["ncf_00631l"]
    assert "--no-external-features" in commands["ncf_00632r"]
    assert "--no-external-features" in commands["ncf_0050"]
    assert "--no-external-features" in commands["ncf_2330"]
    assert "ncf_00631l_no_external_shadow" not in commands
    assert "ncf_panel_drift_no_external_vs_external" not in commands


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
    assert commands["riccati_mv_shadow"][commands["riccati_mv_shadow"].index("--execution-plan") + 1] == expected


def test_riccati_mv_shadow_is_best_effort_after_daily_signal() -> None:
    module = _load_module()
    commands = module.build_commands(_command_args())

    assert "riccati_mv_shadow" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("daily_signal") < list(commands).index("riccati_mv_shadow")
    assert commands["riccati_mv_shadow"][1] == "scripts/run/build_group_a_plus_riccati_mv_shadow.py"
    assert commands["riccati_mv_shadow"][commands["riccati_mv_shadow"].index("--execution-plan") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )


def test_current_policy_re_evaluation_gate_is_best_effort_after_riccati_shadow() -> None:
    module = _load_module()
    commands = module.build_commands(_command_args())

    assert "current_policy_re_evaluation_gate" in module.BEST_EFFORT_STEP_NAMES
    assert list(commands).index("riccati_mv_shadow") < list(commands).index("current_policy_re_evaluation_gate")
    assert commands["current_policy_re_evaluation_gate"][1] == (
        "scripts/evaluate/build_group_a_plus_current_policy_re_evaluation_gate.py"
    )
    assert commands["current_policy_re_evaluation_gate"][
        commands["current_policy_re_evaluation_gate"].index("--shadow") + 1
    ].endswith("report/group_a_plus/latest/riccati_mv_shadow.json")


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
    assert outputs["instrument_readiness_shadow_2608_08405"].endswith(
        "report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json"
    )
    assert outputs["instrument_readiness_shadow_2608_08405_md"].endswith(
        "report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.md"
    )
    assert outputs["ramp_path_dependence_shadow_2608_08405"].endswith(
        "report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json"
    )
    assert outputs["ramp_path_dependence_shadow_2608_08405_md"].endswith(
        "report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.md"
    )
    assert outputs["00632r_discipline_guard"].endswith(
        "report/group_a_plus/latest/00632r_discipline_guard.json"
    )
    assert outputs["00632r_discipline_guard_md"].endswith(
        "report/group_a_plus/latest/00632r_discipline_guard.md"
    )
    assert outputs["daily_status_pointer"].endswith("report/group_a_plus/latest/daily_status.json")
