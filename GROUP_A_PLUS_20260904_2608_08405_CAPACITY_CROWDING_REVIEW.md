# GroupA+ 2608.08405 Capacity/Crowding Review

Date: 2026-09-04

Paper: `C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf`

Title: `Robustness or Crowding: Experimental Design for Trading Strategy Capacity`

## Conclusion

This paper has useful governance ideas for GroupA+, but it does not provide a new alpha,
forecasting feature, optimizer, or weight formula. The safe import is a research-only
capacity/crowding readiness gate. It must not change `golden1_0531`, `golden2_0830`,
the latest strategy weights, or live execution permission.

For the current 1,000,000 TWD 2026-09-04 prediction context, the latest signal remains:

- `0050.TW`: 0.529328223921051
- `00631L.TW`: 0.170671776078949
- `00632R.TW`: 0.0
- `00679B.TWO`: 0.0
- `cash`: 0.30

The paper import blocks capacity scaling because GroupA+ does not have randomized
parallel sleeves, a finite-grid capacity interval, a GroupA+-calibrated steady-state
crowding kernel, or same-run realized deployment/fill records.

## What The Paper Adds

The paper reframes strategy capacity as a causal estimand: how much deployed capital
can be added before edge erodes below a hurdle. Its key point is that normal backtests,
execution-cost models, and same-date sleeve comparisons can each answer a narrower
question, but they do not prove aggregate strategy capacity.

The most relevant points for GroupA+ are:

- Capacity is not just a backtest return or Sharpe metric.
- Same-date sleeve contrasts control market-wide shocks but also absorb common crowding.
- A short fixed-hold study understates steady-state erosion because crowding accumulates.
- An impact model bounds capacity from one side only; it cannot rule out lost alpha from
  crowded positioning.
- A finite deployment grid should report a capacity interval, not a single capacity point.
- Assigned deployment and realized deployment must be logged separately.
- Path dependence requires a separate ramp-up/ramp-down study, not the same capacity test.
- Any capacity experiment must be pre-registered: estimand, arms, hold length, outcome
  adjustment convention, assigned-vs-realized measurement, reporting rule, and detectable
  gap/power budget must be fixed before the test starts.
- Natural experiments such as securities-lending supply shifts or index reconstitution events
  are only future shadow instruments unless they have a credible exclusion restriction and a
  reported first stage.

## Imported Into GroupA+

Added:

- `scripts/evaluate/build_group_a_plus_2608_08405_capacity_crowding_readiness.py`
- `tests/test_build_group_a_plus_2608_08405_capacity_crowding_readiness.py`

Connected to:

- `scripts/run/run_ncf_daily_pipeline.py`

Latest generated outputs:

- `report/group_a_plus/latest/2608_08405_capacity_crowding_readiness.json`
- `report/group_a_plus/latest/2608_08405_capacity_crowding_readiness.md`
- `report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json`
- `report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.md`
- `report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json`
- `report/group_a_plus/latest/2608_08405_capacity_grid_shadow.md`
- `report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json`
- `report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.md`
- `report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json`
- `report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.md`
- `report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json`
- `report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.md`
- history snapshots under `report/group_a_plus/2608_08405_capacity_crowding_readiness/history/`

The pipeline now runs the 2608.08405 checks as:

- `assigned_realized_deployment_shadow_2608_08405`
- `capacity_grid_shadow_2608_08405`
- `erosion_persistence_shadow_2608_08405`
- `instrument_readiness_shadow_2608_08405`
- `capacity_crowding_readiness_2608_08405`

The total readiness step intentionally runs after the assigned/realized and capacity-grid
shadow reports, because the paper explicitly says market-impact evidence should not be
treated as full capacity evidence.

2026-09-04 follow-up import:

- Added `future_experiment_pre_registration` to the readiness JSON.
- Added `future_natural_experiment_candidates` to keep securities-lending/index-event ideas
  as shadow-only instrument candidates.
- Added `outcome_adjustment` mapping so future capacity claims cannot condition on
  treatment-moved quantities without predeclaring the estimand.
- Added tests covering the new report fields.

2026-09-04 continuation import:

- Added `scripts/evaluate/build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`.
- Added `tests/test_build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`.
- Added the pipeline step `assigned_realized_deployment_shadow_2608_08405` after
  `broker_holdings_reconciliation_review`, before intervention-fatigue governance.
- Added manifest outputs for:
  - `report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json`
  - `report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.md`
- Current status is blocked because the latest live signal is fresher than the execution
  plan, broker positions are transaction-derived rather than authoritative, broker holdings
  are not reconciled, and no same-run realized fill/deployment series exists.

2026-09-05 audit correction / continuation:

- Added `scripts/evaluate/build_group_a_plus_2608_08405_capacity_grid_shadow.py`.
- Added `tests/test_build_group_a_plus_2608_08405_capacity_grid_shadow.py`.
- Added the pipeline step `capacity_grid_shadow_2608_08405` after
  `assigned_realized_deployment_shadow_2608_08405`.
- Added manifest outputs for:
  - `report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json`
  - `report/group_a_plus/latest/2608_08405_capacity_grid_shadow.md`
- Current capacity-grid status is `not_identified_shadow_only`, not a capacity estimate.
  It specifies finite deployment arms and one-sided impact proxies, but it does not report
  a capacity interval because randomized sleeve observations, observed edge erosion by arm,
  realized deployment evidence, and simultaneous bands are missing.

2026-09-05 continuation import #2:

- Added `scripts/evaluate/build_group_a_plus_2608_08405_erosion_persistence_shadow.py`.
- Added `tests/test_build_group_a_plus_2608_08405_erosion_persistence_shadow.py`.
- Added the pipeline step `erosion_persistence_shadow_2608_08405` after
  `capacity_grid_shadow_2608_08405`, before total capacity/crowding readiness.
- Added manifest outputs for:
  - `report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json`
  - `report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.md`
- Current erosion-persistence status is `proxy_available_not_calibrated_kernel`.
  The report estimates an OHLCV proxy `abs(log_return) * log1p(volume)` for Taiwan ETFs,
  but explicitly blocks capacity deattenuation because this is not a randomized deployment
  erosion kernel and does not use same-run realized deployment.

2026-09-05 continuation import #3:

- Added `scripts/evaluate/build_group_a_plus_2608_08405_instrument_readiness_shadow.py`.
- Added `tests/test_build_group_a_plus_2608_08405_instrument_readiness_shadow.py`.
- Added the pipeline step `instrument_readiness_shadow_2608_08405` after
  `erosion_persistence_shadow_2608_08405`, before total capacity/crowding readiness.
- Added manifest outputs for:
  - `report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json`
  - `report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.md`
- Wired total capacity/crowding readiness to read
  `report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json`.
- Current instrument-readiness status is `blocked_shadow_only`.
  Securities-lending supply shifts and index reconstitution/index-weight events remain
  future shadow instruments only. The current artifacts do not report first-stage
  strength, a pre-registered exclusion restriction, an index-event panel, or same-run
  realized deployment evidence.

2026-09-05 continuation import #4:

- Added `scripts/evaluate/build_group_a_plus_2608_08405_ramp_path_dependence_shadow.py`.
- Added `tests/test_build_group_a_plus_2608_08405_ramp_path_dependence_shadow.py`.
- Added the pipeline step `ramp_path_dependence_shadow_2608_08405` after
  `instrument_readiness_shadow_2608_08405`, before total capacity/crowding readiness.
- Added manifest outputs for:
  - `report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json`
  - `report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.md`
- Wired total capacity/crowding readiness to read
  `report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json`.
- Current ramp-path-dependence status is `blocked_shadow_only`.
  GroupA+ has two-sided target-change paths for 0050/00631L/00632R/00679B, but these
  are daily-status target deltas rather than authoritative realized fills. No
  pre-registered ramp-up/ramp-down protocol or path-dependent outcome window exists.

## Current Gate Result

Status: `blocked`

Decision:

- `promotion_allowed`: false
- `target_weight_change_allowed`: false
- `golden1_0531_change_allowed`: false
- `golden2_0830_change_allowed`: false
- `latest_strategy_change_allowed`: false
- `capacity_scaling_allowed`: false

Current blockers:

- `no_randomized_parallel_sleeves`
- `aggregate_crowding_not_identified_by_same_date_contrast`
- `finite_grid_capacity_interval_not_identified`
- `steady_state_kernel_not_calibrated_to_group_a_plus`
- `impact_model_upper_bound_only`
- `realized_deployment_series_missing`
- `market_impact_readiness_blocked`
- `natural_experiment_instrument_not_promotable`
- `ramp_path_dependence_not_identified`
- `execution_plan_stale_vs_live_signal`

## Not Imported

Not imported into production:

- Randomized live sleeve experiment.
- Automatic capacity-based scaling.
- Steady-state deattenuated point estimate.
- Any direct modification to 0050, 00631L, 00632R, 00679B, or cash weights.

Reason: the paper itself says the proper experiment is expensive and requires many
simultaneous sleeves. GroupA+ is currently a single-account daily strategy workflow,
so implementing the experiment as live randomized trades would be an unjustified
execution change.

## Validation

Focused tests passed:

`36 passed in 60.53s`

Command:

`./.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_08405_ramp_path_dependence_shadow.py tests/test_build_group_a_plus_2608_08405_instrument_readiness_shadow.py tests/test_build_group_a_plus_2608_08405_erosion_persistence_shadow.py tests/test_build_group_a_plus_2608_08405_capacity_grid_shadow.py tests/test_build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py tests/test_build_group_a_plus_2608_08405_capacity_crowding_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
