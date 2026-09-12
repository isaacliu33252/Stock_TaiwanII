# 2608.08405 Ramp Path Dependence Shadow

- status: blocked_shadow_only
- as_of: 2026-09-07
- policy: ramp_path_dependence_shadow_no_weight_change
- history_type: system_observed_daily_status_not_broker_fills
- entry_count: 149
- two_sided_target_path_ticker_count: 4
- realized_two_sided_path_ticker_count: 0
- ramp_path_dependence_claim_allowed: False

## Blocking Reasons
- intervention_history_is_target_status_not_realized_fills
- realized_deployment_series_missing
- realized_two_sided_ramp_paths_missing
- ramp_up_down_protocol_not_pre_registered
- path_dependent_outcome_window_not_estimated
- capacity_level_grid_cannot_substitute_for_ramp_experiment

## Ticker Sequences
- 0050.TW: entries=31, positive=15, negative=16, filled=0
- 00631L.TW: entries=103, positive=15, negative=15, filled=0
- 00632R.TW: entries=13, positive=7, negative=6, filled=0
- 00679B.TWO: entries=2, positive=1, negative=1, filled=0

## Decision
GroupA+ has target-change history, but not a pre-registered realized ramp-up/ramp-down experiment. Path dependence remains a separate shadow question and cannot support capacity scaling or strategy changes.
