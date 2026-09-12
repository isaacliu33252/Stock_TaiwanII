from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_08405_capacity_crowding_readiness as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_capacity_crowding_report_is_research_only_even_with_artifacts(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    impact = tmp_path / "impact.json"
    liquidity = tmp_path / "liquidity.json"
    capacity_grid = tmp_path / "capacity_grid.json"
    erosion = tmp_path / "erosion.json"
    instrument = tmp_path / "instrument.json"
    ramp = tmp_path / "ramp.json"
    _write_json(
        live,
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-09-04",
                "actual_data_date": "2026-09-03",
                "target_weights": {"0050.TW": 0.53, "00631L.TW": 0.17, "00632R.TW": 0.0, "cash": 0.30},
            },
        },
    )
    _write_json(
        plan,
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-09-03",
                "target_shares": {"0050.TW": 4984, "00631L.TW": 4819, "00632R.TW": 0},
                "theoretical_target_shares": {"0050.TW": 4984, "00631L.TW": 4819, "00632R.TW": 0},
            },
        },
    )
    _write_json(
        impact,
        {
            "status": "available_for_manual_review",
            "computed": {
                "turnover": 0.02,
                "max_participation_of_volume": 0.001,
                "trade_rows": [{"ticker": "00631L.TW", "delta_shares": 10}],
            },
        },
    )
    _write_json(liquidity, {"as_of": "2026-09-03", "decision": {"promotion_allowed": False}})
    _write_json(
        capacity_grid,
        {"status": "not_identified_shadow_only", "decision": {"capacity_interval_reported": False}},
    )
    _write_json(
        erosion,
        {
            "status": "proxy_available_not_calibrated_kernel",
            "summary": {"proxy_available_count": 2},
            "decision": {"steady_state_kernel_calibrated_to_group_a_plus": False},
        },
    )
    _write_json(
        instrument,
        {
            "status": "blocked_shadow_only",
            "checks": {"first_stage_reported": False, "exclusion_restriction_pre_registered": False},
            "decision": {"instrument_promotable": False},
        },
    )
    _write_json(
        ramp,
        {
            "status": "blocked_shadow_only",
            "coverage": {"realized_two_sided_path_ticker_count": 0},
            "decision": {"ramp_path_dependence_claim_allowed": False},
        },
    )

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        market_impact_path=impact,
        liquidity_feedback_path=liquidity,
        capacity_grid_path=capacity_grid,
        erosion_persistence_path=erosion,
        instrument_readiness_path=instrument,
        ramp_path_dependence_path=ramp,
        capital=1_000_000.0,
        persistence=0.9177,
        hold_periods=(20, 60),
    )

    assert report["status"] == "blocked"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["latest_strategy_change_allowed"] is False
    assert report["checks"]["same_date_contrast_identifies_aggregate_crowding"] is False
    assert report["checks"]["impact_model_is_only_one_sided_upper_bound"] is True
    assert "impact_model_upper_bound_only" in report["blocking_reasons"]
    assert "finite_grid_capacity_interval_not_identified" in report["blocking_reasons"]
    assert report["capital_context"]["leveraged_or_inverse_weight"] == 0.17
    assert report["paper_method_mapping"]["finite_hold_attenuation"][0]["block_average_fraction_g_l"] < 1.0
    assert (
        "capacity_experiment_requires_pre_registration"
        in report["source_paper"]["imported_concepts"]
    )
    assert report["future_experiment_pre_registration"]["required_before_any_capacity_experiment"] is True
    assert (
        "assigned_and_realized_deployment_measurement_plan"
        in report["future_experiment_pre_registration"]["items"]
    )
    assert report["future_natural_experiment_candidates"][0]["allowed_use"] == "future_shadow_instrument_only"
    assert report["future_natural_experiment_candidates"][0]["promotion_requirement"] == (
        "credible_exclusion_restriction_and_reported_first_stage"
    )
    assert report["capacity_shadow_next_steps"][0]["step"] == "log_assigned_vs_realized_daily_deployment"
    assert all(item["live_weight_change_allowed"] is False for item in report["capacity_shadow_next_steps"])
    assert report["current_artifact_summary"]["erosion_persistence_status"] == "proxy_available_not_calibrated_kernel"
    assert report["current_artifact_summary"]["erosion_persistence_kernel_calibrated"] is False
    assert report["current_artifact_summary"]["instrument_readiness_status"] == "blocked_shadow_only"
    assert report["current_artifact_summary"]["instrument_promotable"] is False
    assert "natural_experiment_instrument_not_promotable" in report["blocking_reasons"]
    assert report["current_artifact_summary"]["ramp_path_dependence_status"] == "blocked_shadow_only"
    assert report["current_artifact_summary"]["ramp_path_dependence_claim_allowed"] is False
    assert "ramp_path_dependence_not_identified" in report["blocking_reasons"]


def test_capacity_crowding_report_flags_stale_plan_and_blocked_impact(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    impact = tmp_path / "impact.json"
    liquidity = tmp_path / "liquidity.json"
    capacity_grid = tmp_path / "capacity_grid.json"
    erosion = tmp_path / "erosion.json"
    instrument = tmp_path / "instrument.json"
    ramp = tmp_path / "ramp.json"
    _write_json(
        live,
        {
            "actual_data_date": "2026-09-03",
            "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
        },
    )
    _write_json(plan, {"actual_data_date": "2026-08-31", "target_shares": {"0050.TW": 1}})
    _write_json(impact, {"status": "blocked", "computed": {"trade_rows": []}})
    _write_json(liquidity, {})
    _write_json(capacity_grid, {})
    _write_json(erosion, {})
    _write_json(instrument, {})
    _write_json(ramp, {})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        market_impact_path=impact,
        liquidity_feedback_path=liquidity,
        capacity_grid_path=capacity_grid,
        erosion_persistence_path=erosion,
        instrument_readiness_path=instrument,
        ramp_path_dependence_path=ramp,
        capital=1_000_000.0,
        persistence=0.9177,
        hold_periods=(20,),
    )

    assert "market_impact_readiness_blocked" in report["blocking_reasons"]
    assert "execution_plan_stale_vs_live_signal" in report["blocking_reasons"]
    assert "missing_letf_liquidity_feedback_watch" in report["blocking_reasons"]
    assert "natural_experiment_instrument_readiness_missing" in report["blocking_reasons"]
    assert "ramp_path_dependence_shadow_missing" in report["blocking_reasons"]
    assert report["assigned_vs_realized_deployment"]["realized_fill_or_broker_execution_logged"] is False
    assert "outcome_adjustment" in report["paper_method_mapping"]


def test_markdown_includes_future_capacity_sections(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    impact = tmp_path / "impact.json"
    liquidity = tmp_path / "liquidity.json"
    capacity_grid = tmp_path / "capacity_grid.json"
    erosion = tmp_path / "erosion.json"
    instrument = tmp_path / "instrument.json"
    ramp = tmp_path / "ramp.json"
    _write_json(live, {"target_weights": {"0050.TW": 0.7, "cash": 0.3}})
    _write_json(plan, {})
    _write_json(impact, {})
    _write_json(liquidity, {})
    _write_json(capacity_grid, {})
    _write_json(erosion, {})
    _write_json(instrument, {})
    _write_json(ramp, {})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        market_impact_path=impact,
        liquidity_feedback_path=liquidity,
        capacity_grid_path=capacity_grid,
        erosion_persistence_path=erosion,
        instrument_readiness_path=instrument,
        ramp_path_dependence_path=ramp,
        capital=1_000_000.0,
        persistence=0.9177,
        hold_periods=(20,),
    )
    markdown = module._markdown(report)

    assert "## Future Experiment Pre-Registration" in markdown
    assert "## Current Artifact Summary" in markdown
    assert "## Future Natural Experiment Candidates" in markdown
    assert "## Shadow Next Steps" in markdown
    assert "build_shadow_capacity_grid_report" in markdown
