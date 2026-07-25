# GroupA+ 2026-07-20 Full Pipeline Final Decision Record

## Scope

This record summarizes the full 2026-07-20 GroupA+ pipeline run completed on
2026-07-18 after refreshing data through the 2026-07-17 market date.

Run command:

- `.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --date-stamp 20260720 --refresh-target-date 2026-07-17 --chip-end 2026-07-17 --per-start 2023-07-17 --val-end latest --checklist-external-end 2026-07-18`

Pipeline result:

- completed `52 / 52` steps
- manifest: `results/ncf_daily_pipeline_20260720.json`
- live signal: `results/group_a_plus_live_signal_v2_20260720.json`
- daily status: `results/group_a_plus_daily_status_20260720.json`
- dynamic CVaR readiness: `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- research shadow snapshot: `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- deployment consistency: `report/group_a_plus/latest/deployment_consistency_review.json`
- promotion gate: `results/group_a_plus_promotion_gate_20260720.json`

## Important Change Versus Earlier 7/20 Estimate

The earlier 7/20 estimate was blocked at the live-signal/data layer because:

- `institutional_0050` was stale or missing;
- NCF live overlay panel dates did not match the actual data date.

After the full refresh:

- `execution_allowed = true`
- `source_freshness = ok`
- `execution_guard_reasons = []`
- daily status changed from `block` to `warn`

This only means the live signal is now data-current enough for review. It does
not authorize automatic trading.

## Fresh NCF Signals

`00631L.TW`:

- data date: `2026-07-17`
- freshness: `ok`
- direction: `DOWN`
- `probability_up = 0.4912`
- `calibrated_probability_up = 0.4953`
- `confidence = 0.3332`
- `weighted_return = -0.00619`

`00632R.TW`:

- data date: `2026-07-17`
- freshness: `ok`
- direction: `UP`
- `probability_up = 0.5207`
- `calibrated_probability_up = 0.5124`
- `confidence = 0.4279`
- `weighted_return = 0.020023`

`2330.TW`:

- data date: `2026-07-17`
- direction: `UP`
- `probability_up = 0.531`
- `calibrated_probability_up = 0.5156`
- `confidence = 0.2914`
- freshness: `degraded_missing` for local `ohlcv`, `institutional`, and
  `margin`; external 2330 OHLCV is current.

## Fresh Live Signal

From `results/group_a_plus_live_signal_v2_20260720.json`:

- requested as-of date: `2026-07-20`
- actual data date: `2026-07-17`
- execution regime: `golden1`
- action: `hold_or_align_to_target`
- `execution_allowed = true`
- `execution_guard_reasons = []`
- `execution_warning_reasons = []`

Fresh reference target weights:

| asset | weight |
| --- | ---: |
| `0050.TW` | `0.5` |
| `00631L.TW` | `0.19954000000000002` |
| `00632R.TW` | `0.0` |
| `00679B.TWO` | `0.0` |
| cash | `0.30046000000000006` |

The small deviation from the old 20% / 30% split is a fresh live-signal
reference value, not permission to auto-trade.

## Daily Status

From `results/group_a_plus_daily_status_20260720.json`:

- `overall_status = warn`
- `execution_allowed = ok`
- `source_freshness = ok`
- `data_freshness = warn`
- cash constraint: `ok`
- execution-plan pre-trade guard: `ok`, detail `pre_trade_guards=blocked,blocked`

Interpretation:

- the stale source blocker is resolved;
- the check date is still 2026-07-20 while the latest market data is
  2026-07-17, so data freshness is a warning;
- pre-trade guards remain blocked for leverage adds.

## Governance Blocks Still Active

Dynamic CVaR tail/cost readiness:

- `status = blocked`
- `dynamic_optimizer_ready = false`
- `tail_cost_readiness_ready = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Fresh dynamic CVaR blockers:

- `cvar_tail_risk_diagnostic_research_only`
- `00631l_hill_tail_index_positive_heavy_tail`
- `density_tail_model_unstable_research_only`
- `market_impact_readiness_blocked`
- `market_impact_disallows_auto_rebalance`
- `rebalance_review_disallows_auto_rebalance`
- `rebalance_review_disallows_target_weight_change`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `systemic_bubble_disallows_00631l_add`
- `hmm_wj_scenario_readiness_blocked`
- `scenario_generator_not_decision_ready`
- `dynamic_cvar_optimizer_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

Research shadow decision snapshot:

- `status = blocked`
- `dynamic_cvar_status = blocked`
- `dynamic_cvar_tail_cost_ready = false`
- `dynamic_cvar_optimizer_ready = false`
- `allow_00631l_add = false`

Deployment consistency:

- `status = manual_review_required`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `broker_actionable = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Promotion gate:

- `decision = blocked_multi_window`

## Final Decision

For 2026-07-20:

- do not auto-rebalance;
- do not add `00631L`;
- do not open a direct `00632R` hedge;
- do not change Golden1_0531;
- keep GroupA+ latest strategy unchanged;
- treat the refreshed target weights as reference only;
- require manual review before any broker-actionable change.

The reason is not stale data anymore. The reason is that research/governance
layers still block leverage add, auto rebalance, target-weight changes,
deployment actionability, and promotion.
