# GroupA+ Daily Status

Generated: `2026-07-22T20:12:21`
Check date: `2026-07-22`
Overall: `warn`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `ok` | allowed |
| data_freshness | `ok` | 0 business days stale, 0 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `warn` | soft strategy sources are stale or missing: ['securities_lending_0050']; securities_lending_0050 |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=301,428 |
| execution_plan_pre_trade_guard | `ok` | pre_trade_guards=blocked,blocked |
| dfl_advisory_frozen_input_staleness | `ok` | frozen backtest last covers 2026-07-13 (9 calendar days behind check_date); matched_decision_count is structurally 0 until this is re-run |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-22`
- Business stale days: `0`
- Calendar stale days: `0`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `301,428`

## Pre-Trade Guard

- Status: `blocked`
- 00631L add: `blocked`
- Policy: `advisory_no_auto_weight_change`
- Blocked: `00631L.TW` `buy` current `0` requested `2908` guarded `0`

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
- AR1 5d / 20d: `-0.010102912243728992` / `0.006098327675767404`
- Variance ratio: `0.37958639093078145`
- 00631L vs 0050 relative momentum: `-0.05533654291323964`

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

- State: `research_watch`
- 00631L add: `blocked`
- Systemic score: `1`
- Time-at-risk / ETF coupling / reflexivity: `elevated` / `watch` / `watch`
- 2330/0050 corr 60d: `0.8688580320606354`
- ETF coupling score: `0.9429569609696794`
- Policy: `research_only_systemic_bubble_time_at_risk_no_weight_change`

## Illiquidity Network Readiness

- Status: `blocked`
- Actual data end: `2026-07-21`
- Illiquidity network ready: `False`
- Crash guard allowed: `False`
- Daily OHLCV proxy: `available_research_proxy` paper-equivalent `False`
- Daily OHLCV proxy state: `normal` manual-review `False`
- Daily OHLCV proxy score: `0.027777777777777776` coverage `9`
- Proxy components volume/range/negative/limit: `0` / `0` / `1` / `0`
- 00631L add: `blocked`
- 00632R open: `blocked`
- OHLCV tickers / rows: `15` / `29659`
- Blocking reasons: `['china_2015_parameters_not_portable_to_group_a_plus', 'crash_warning_not_allowed_to_change_live_weights', 'five_day_systemic_failure_signal_not_validated_for_taiwan', 'missing_high_frequency_bid_ask', 'missing_intraday_minute_liquidity', 'missing_market_wide_failure_events', 'nmi_illiquidity_network_not_implemented']`
- Policy: `research_only_illiquidity_network_readiness_no_crash_guard_no_weight_change`

## Speculative Influence Network Readiness

- Status: `blocked`
- Actual data end: `2026-07-21`
- SIN ready: `False`
- HMM bubble state ready: `False`
- Transfer entropy network ready: `False`
- Max-loss validation ready: `False`
- 00631L add: `blocked`
- 00632R open: `blocked`
- OHLCV tickers / minimum: `15` / `50`
- Broad universe ready: `False`
- Blocking reasons: `['broad_stock_universe_insufficient_for_sin', 'china_2006_2008_parameters_not_portable_to_group_a_plus', 'missing_crash_maxloss_validation', 'missing_hmm_bubble_state_probabilities', 'missing_sector_index_history', 'missing_transfer_entropy_network', 'nsii_maxloss_validation_missing_for_taiwan', 'sornette_andersen_hmm_not_implemented', 'speculative_influence_signal_not_allowed_to_change_live_weights', 'transfer_entropy_sin_not_implemented']`
- Policy: `research_only_speculative_influence_network_readiness_no_weight_change`

## SIN-Lite Proxy

- Status: `blocked`
- Actual data end: `2026-07-21`
- State: `normal`
- SIN-lite score: `0.383788`
- Manual review required: `False`
- Usable tickers: `14`
- Components corr/edge/downside/concentration/TSMC: `0.675155` / `0.0` / `0.66792` / `None` / `0.192076`
- 00631L add: `blocked`
- 00632R open: `blocked`
- Blocking reasons: `['sin_lite_proxy_not_validated_for_live_weight_change']`
- Policy: `research_only_sin_lite_proxy_no_weight_change`

## HMM-WJ Synthetic Scenario Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Data ready: `True`
- Can generate scenarios for decision: `False`
- Generator implemented: `False`
- Taiwan ETF walk-forward validated: `False`
- Blocking reasons: `['finstressts_snapshot_blocked', 'trigate_vol_memory_blocks_leverage_add', 'hmm_wj_generator_not_implemented', 'taiwan_etf_walkforward_validation_missing']`
- Policy: `research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change`

## Dynamic CVaR Tail/Cost Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Tail/cost ready: `False`
- Dynamic optimizer ready: `False`
- 00631L Hill xi 95: `0.365186858046869`
- 00631L POT-GPD xi 95: `-0.07162970315917858`
- Turnover: `0.5006477801878955`
- Blocking reasons: `['cvar_tail_risk_diagnostic_research_only', '00631l_hill_tail_index_positive_heavy_tail', 'density_tail_model_unstable_research_only', 'market_impact_readiness_blocked', 'market_impact_disallows_auto_rebalance', 'rebalance_review_disallows_auto_rebalance', 'rebalance_review_disallows_target_weight_change', 'systemic_bubble_disallows_00631l_add', 'hmm_wj_scenario_readiness_blocked', 'scenario_generator_not_decision_ready', 'dynamic_cvar_optimizer_not_implemented', 'taiwan_etf_walkforward_validation_missing']`
- Policy: `research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change`

## Synthetic Augmentation Validation Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Synthetic validation ready: `False`
- Directional synthetic alpha: `blocked`
- Generator promotion: `blocked`
- Size-matched null: `True`
- Block permutation test: `True`
- Directional audit passed: `True`
- Rare-regime audit passed: `True`
- Blocking reasons: `['finstressts_snapshot_blocked', 'hmm_wj_scenario_readiness_blocked', 'scenario_generator_not_decision_ready', 'dynamic_cvar_tail_cost_readiness_blocked', 'tail_cost_readiness_not_ready', 'density_tail_model_unstable_research_only']`
- Policy: `research_only_synthetic_augmentation_validation_no_synthetic_alpha_no_weight_change`

## Intervention Fatigue / Risk-Budget Readiness

- Status: `blocked`
- 00631L add: `blocked`
- 00632R open: `blocked`
- Intervention fatigue ready: `False`
- Risk-budget pacing ready: `False`
- Nonzero trade count: `1`
- Leverage / hedge change count: `0` / `0`
- Normalized history available: `True`
- History entries / blocked: `76` / `55`
- History leverage / hedge interventions: `67` / `0`
- Broker holdings status: `sample_available` authoritative `False`
- Broker transactions / snapshots: `146` / `116`
- Broker negative positions: `4`
- Broker reconciliation status: `blocked`
- Confirmed matched / mismatched: `1` / `1`
- Can generate live orders: `False`
- Turnover: `0.5006477801878955`
- Blocking reasons: `['risk_budget_policy_not_promoted', 'rl_environment_not_validated', 'broker_holdings_time_series_sample_only', 'broker_holdings_time_series_has_negative_positions', 'broker_holdings_reconciliation_blocked', 'broker_holdings_not_order_authoritative', 'market_impact_readiness_blocked', 'dynamic_cvar_tail_cost_readiness_blocked', 'research_shadow_decision_snapshot_blocked', 'rebalance_review_disallows_auto_rebalance', 'rebalance_review_disallows_target_weight_change', 'market_impact_disallows_00631l_add', 'tail_cost_readiness_not_ready', 'research_shadow_disallows_00631l_add', 'turnover_at_or_above_pacing_limit']`
- Policy: `research_only_intervention_fatigue_risk_budget_pacing_no_weight_change`

## LETF Tracking Error / Effective Fee Readiness

- Status: `blocked`
- Actual data end: `2026-07-21`
- 00631L add: `blocked`
- 00632R open: `blocked`
- Tracking-error readiness: `False`
- Effective-fee proxy ready: `False`
- Hedge-neutrality ready: `False`
- 00631L 30d mean/latest tracking error: `-0.004915562181173291` / `-0.014624888104038298`
- 00632R 30d mean/latest tracking error: `0.02909703342204928` / `-0.01205841440872513`
- 00632R hedge beta/corr: `-1.0047353417380487` / `-0.9792603311136588`
- Blocking reasons: `['00631l_tw_mean_30d_tracking_error_drag_present', '00632r_hedge_neutrality_not_promoted', 'intervention_fatigue_risk_budget_readiness_blocked', 'letf_pair_strategy_not_imported', 'realized_effective_fee_proxy_not_validated', 'research_only_letf_tracking_error_review']`
- Policy: `research_only_letf_tracking_error_effective_fee_no_pair_trade_no_weight_change`

## Asian ETF Tail Analytics Readiness

- Status: `blocked`
- 00631L add: `blocked`
- Tail analytics ready: `False`
- Optimizer ready: `False`
- Paper ETF coverage: `1` / `29`
- Available paper ETFs: `['EWT']`
- Golden1 STARR 95: `15.208210413984315`
- Golden1 Rachev 95/95: `1.042372888137112`
- 00631L Rachev 95/95: `0.9604260807450556`
- Tail reward/risk tier: `defensive_preference`
- 00631L Hill xi 95: `0.365186858046869`
- Blocking reasons: `['asian_29_etf_universe_not_available', 'asian_etf_walkforward_validation_missing', 'cvar_tail_risk_diagnostic_research_only', 'letf_tracking_error_review_disallows_00631l_add', 'leverage_10_20_30_percent_not_portable_to_group_a_plus', 'long_short_etf_strategy_not_allowed', 'market_impact_disallows_auto_rebalance', 'market_impact_readiness_blocked', 'rachev_starr_hill_optimizer_not_implemented', 'rebalance_review_disallows_auto_rebalance', 'rebalance_review_disallows_target_weight_change', 'transaction_borrow_financing_costs_missing']`
- Policy: `research_only_asian_etf_tail_analytics_no_optimizer_no_weight_change`

## Research Shadow Decision Snapshot

- Status: `blocked`
- 00631L add: `blocked`
- FinStressTS status: `blocked`
- Tri-gate state: `blocked_for_leverage_add`
- Tri-gate stress count: `3`
- Illiquidity network status: `blocked`
- Illiquidity crash guard allowed: `False`
- Illiquidity daily proxy score: `0.027777777777777776`
- Illiquidity daily proxy state: `normal`
- Speculative influence status: `blocked`
- Speculative influence ready: `False`
- SIN-lite state: `normal`
- SIN-lite score: `0.383788`
- Dynamic CVaR status: `blocked`
- Dynamic CVaR tail/cost ready: `False`
- Dynamic CVaR optimizer ready: `False`
- Synthetic augmentation status: `blocked`
- Synthetic validation ready: `False`
- Directional synthetic alpha: `False`
- Intervention fatigue status: `blocked`
- Risk-budget pacing ready: `False`
- LETF tracking status: `blocked`
- LETF hedge neutrality ready: `False`
- Asian ETF tail analytics status: `blocked`
- Asian ETF tail analytics ready: `False`
- GIFT signed approval validation: `blocked`
- GIFT signed approval record valid: `False`
- GIFT human exception approved: `False`
- GIFT non-PPO shadow queue review allowed: `False`
- GIFT manual approval queue allowed: `False`
- GIFT training queue blockers: `['signed_human_exception_approval_record_missing_or_invalid']`
- GIFT checklist status: `manual_completion_pending`
- GIFT validator smoke status: `passed`
- Policy: `research_shadow_summary_no_weight_change`

## GIFT Signed Approval Governance

- Validation status: `blocked`
- Signed approval record valid: `False`
- Human exception approved: `False`
- Non-PPO shadow queue review allowed: `False`
- Manual approval queue allowed: `False`
- Training queue allowed: `False`
- Model training allowed: `False`
- PPO training allowed: `False`
- Promote to live: `False`
- Queue blockers: `['signed_human_exception_approval_record_missing_or_invalid']`
- Signed approval warnings: `['llm_state_reward_signed_approval_validation_blocked', 'llm_state_reward_signed_approval_validation_status:blocked', 'llm_state_reward_signed_approval_validation:missing_signed_human_exception_approval_record']`
- Checklist status: `manual_completion_pending`
- Checklist manual completion ready: `True`
- Checklist manual completion pending: `True`
- Checklist signed record exists: `False`
- Validator smoke status: `passed`
- Validator smoke passed: `True`
- Validator blocks 00631L add: `True`
- Validator blocks model training: `True`
- Smoke wrote formal signed record: `False`
- Policy: `research_only_signed_approval_governance_no_training_no_live_action`
