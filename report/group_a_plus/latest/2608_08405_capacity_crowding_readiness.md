# 2608.08405 Capacity/Crowding Readiness

- status: blocked
- as_of: 2026-09-09
- policy: research_only_capacity_crowding_readiness_no_weight_change
- promotion_allowed: False
- target_weight_change_allowed: False
- capital: 1000000.00
- leveraged_or_inverse_weight: 0.173439
- cash_weight: 0.180000

## Imported Ideas
- capacity_is_a_causal_estimand_not_a_backtest_metric
- same_date_sleeve_contrasts_remove_calendar_shocks_but_do_not_identify_aggregate_crowding
- finite_hold_trials_attenuate_steady_state_erosion
- impact_models_bound_capacity_from_one_side_only
- finite_arm_grids_should_report_capacity_intervals_not_point_estimates
- assigned_and_realized_deployment_must_be_separated
- path_dependence_requires_a_separate_ramp_experiment
- capacity_experiment_requires_pre_registration
- natural_experiments_require_exclusion_restriction_and_first_stage
- outcome_adjustment_must_not_condition_on_treatment_moved_quantities

## Blocking Reasons
- no_randomized_parallel_sleeves
- aggregate_crowding_not_identified_by_same_date_contrast
- steady_state_kernel_not_calibrated_to_group_a_plus
- impact_model_upper_bound_only
- realized_deployment_series_missing
- finite_grid_capacity_interval_not_identified
- market_impact_readiness_blocked
- natural_experiment_instrument_not_promotable
- ramp_path_dependence_not_identified
- execution_plan_stale_vs_live_signal

## Current Artifact Summary
- market_impact_status: blocked
- capacity_grid_status: not_identified_shadow_only
- capacity_grid_interval_reported: False
- erosion_persistence_status: proxy_available_not_calibrated_kernel
- erosion_persistence_proxy_available_count: 4
- erosion_persistence_kernel_calibrated: False
- instrument_readiness_status: blocked_shadow_only
- instrument_promotable: False
- instrument_first_stage_reported: False
- instrument_exclusion_restriction_pre_registered: False
- ramp_path_dependence_status: blocked_shadow_only
- ramp_path_dependence_claim_allowed: False
- ramp_realized_two_sided_path_ticker_count: 0

## Future Experiment Pre-Registration
- required_before_any_capacity_experiment: True
- estimand_capacity_curve_or_capacity_crossing
- deployment_arms_allocation_and_hold_length
- hold_length_justified_by_dissipation_half_life
- outcome_timestamp_and_adjustment_convention
- assigned_and_realized_deployment_measurement_plan
- within_block_trajectory_recording_plan
- model_free_bound_and_deattenuated_point_reporting_rule
- path_dependence_alternative_class_if_ramp_tested
- pooled_scale_and_detectable_gap_power_budget

## Future Natural Experiment Candidates
- securities_lending_supply_shifts: future_shadow_instrument_only; requirement=credible_exclusion_restriction_and_reported_first_stage
- index_reconstitution_or_index_weight_events: future_shadow_instrument_only; requirement=credible_exclusion_restriction_and_reported_first_stage

## Shadow Next Steps
- log_assigned_vs_realized_daily_deployment: separate intended target exposure from realized fill/deployment before any capacity claim; live_weight_change_allowed=False
- build_shadow_capacity_grid_report: report a finite-grid capacity interval and simultaneous band instead of a point estimate; live_weight_change_allowed=False
- calibrate_taiwan_etf_erosion_persistence: replace the illustrative persistence bridge with GroupA+-specific evidence; live_weight_change_allowed=False
- evaluate_lending_or_index_event_instruments: test first-stage strength and exclusion plausibility before using natural experiments; live_weight_change_allowed=False
- build_ramp_path_dependence_shadow: keep ramp-up/ramp-down path dependence separate from capacity-level grid evidence; live_weight_change_allowed=False

## Decision
Import the paper as capacity/crowding governance only. It adds a mandatory research-only review before scaling capital, but it does not justify changing golden1_0531, golden2_0830, or the latest strategy weights.
