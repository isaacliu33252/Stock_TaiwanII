# GroupA+ Daily Status

Generated: `2026-07-18T21:30:42`
Check date: `2026-07-20`
Overall: `warn`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `ok` | allowed |
| data_freshness | `warn` | 1 business days stale, 3 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `ok` | all required sources ok |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=300,533 |
| execution_plan_pre_trade_guard | `ok` | pre_trade_guards=blocked,blocked |
| dfl_advisory_frozen_input_staleness | `ok` | frozen backtest last covers 2026-07-13 (7 calendar days behind check_date); matched_decision_count is structurally 0 until this is re-run |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-17`
- Business stale days: `1`
- Calendar stale days: `3`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `300,533`

## Pre-Trade Guard

- Status: `blocked`
- 00631L add: `blocked`
- Policy: `advisory_no_auto_weight_change`
- Blocked: `00631L.TW` `buy` current `0` requested `668` guarded `0`

## A21.18 DFL Shadow Ensemble

- Level: `none`
- Manual review: `False`
- Policy: `shadow_only_no_auto_weight_change`
- `base` action `KEEP` active `False` reliability `None`
- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## 00631L Compounding Guard

- Status: `blocked`
- 00631L add: `blocked`
- Regime: `MEAN_REVERTING`
- Policy: `prohibit_new_leverage_or_reduce_rebalance_frequency`

## 00631L Compounding Regime

- Regime: `MEAN_REVERTING`
- Policy: `prohibit_new_leverage_or_reduce_rebalance_frequency`
- Trend score: `1`
- Mean-reversion score: `3`
- AR1 5d / 20d: `-0.18140049089369714` / `-0.05761683301835627`
- Variance ratio: `0.5215570331390492`
- 00631L vs 0050 relative momentum: `-0.09407410134461369`

## A21.18 DFL Advisory

- Action: `KEEP`
- Active: `False`
- Policy: `advisory_only_no_auto_weight_change`

### Selective Variants

- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## A21.18 DFL Active-Date Audit

- Conclusion: `passes_replay_audit_with_warnings_shadow_only`
- Active days: `7`
- Hard checks pass: `True`
- Warning days: `3`
- Existing guard overlap days: `0`
- Total estimated cost bps / 1M: `8.074904151886141`
- Policy: `shadow_only_no_auto_weight_change`

## FinStressTS Shadow Snapshot

- Status: `blocked`
- 00631L add: `blocked`
- Blocked mechanisms: `['heavy_tailed_shocks', 'self_exciting_jumps', 'zero_inflated_sparse_jumps', 'execution_under_stress']`
- Reference loses to no-00631L: `5`
- Reference tail failures: `4`
- Best shadow candidate: `combined_vol_trend_gate`
- Policy: `research_only_summary_no_weight_change`

## Tri-Gate Volatility Memory Shadow

- State: `blocked_for_leverage_add`
- 00631L add: `blocked`
- Stress gate count: `3`
- Level / shape / tempo active: `True` / `True` / `True`
- Vol level percentile: `0.9325396825396826`
- Shape percentile: `0.9761904761904762`
- Tempo percentile: `1.0`
- Policy: `research_only_vol_memory_decomposition_no_weight_change`

## Systemic Bubble Time-At-Risk Review

- State: `blocked_for_leverage_add`
- 00631L add: `blocked`
- Systemic score: `2`
- Time-at-risk / ETF coupling / reflexivity: `elevated` / `watch` / `elevated`
- 2330/0050 corr 60d: `0.8733215293681316`
- ETF coupling score: `0.9439529638992444`
- Policy: `research_only_systemic_bubble_time_at_risk_no_weight_change`

## HMM-WJ Synthetic Scenario Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Data ready: `True`
- Can generate scenarios for decision: `False`
- Generator implemented: `False`
- Taiwan ETF walk-forward validated: `False`
- Blocking reasons: `['finstressts_snapshot_blocked', 'trigate_vol_memory_blocks_leverage_add', 'systemic_bubble_time_at_risk_blocks_leverage_add', 'hmm_wj_generator_not_implemented', 'taiwan_etf_walkforward_validation_missing']`
- Policy: `research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change`

## Dynamic CVaR Tail/Cost Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Tail/cost ready: `False`
- Dynamic optimizer ready: `False`
- 00631L Hill xi 95: `0.36369464063958445`
- 00631L POT-GPD xi 95: `-0.06744554391369038`
- Turnover: `0.5006477801878955`
- Blocking reasons: `['cvar_tail_risk_diagnostic_research_only', '00631l_hill_tail_index_positive_heavy_tail', 'density_tail_model_unstable_research_only', 'market_impact_readiness_blocked', 'market_impact_disallows_auto_rebalance', 'rebalance_review_disallows_auto_rebalance', 'rebalance_review_disallows_target_weight_change', 'systemic_bubble_time_at_risk_blocks_leverage_add', 'systemic_bubble_disallows_00631l_add', 'hmm_wj_scenario_readiness_blocked', 'scenario_generator_not_decision_ready', 'dynamic_cvar_optimizer_not_implemented', 'taiwan_etf_walkforward_validation_missing']`
- Policy: `research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change`

## Synthetic Augmentation Validation Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Synthetic validation ready: `False`
- Directional synthetic alpha: `blocked`
- Generator promotion: `blocked`
- Size-matched null: `True`
- Block permutation test: `True`
- Blocking reasons: `['directional_synthetic_alpha_default_blocked', 'finstressts_snapshot_blocked', 'hmm_wj_scenario_readiness_blocked', 'scenario_generator_not_decision_ready', 'dynamic_cvar_tail_cost_readiness_blocked', 'tail_cost_readiness_not_ready', 'density_tail_model_unstable_research_only']`
- Policy: `research_only_synthetic_augmentation_validation_no_synthetic_alpha_no_weight_change`

## Research Shadow Decision Snapshot

- Status: `blocked`
- 00631L add: `blocked`
- FinStressTS status: `blocked`
- Tri-gate state: `blocked_for_leverage_add`
- Tri-gate stress count: `3`
- Dynamic CVaR status: `blocked`
- Dynamic CVaR tail/cost ready: `False`
- Dynamic CVaR optimizer ready: `False`
- Synthetic augmentation status: `blocked`
- Synthetic validation ready: `False`
- Directional synthetic alpha: `False`
- Policy: `research_shadow_summary_no_weight_change`
