# GroupA+ 00632R Discipline Guard

- status: blocked_for_inverse_adds
- as_of: 2026-09-09
- policy: latest_strategy_00632r_zero_default_no_dca_no_averaging_down
- strategy_id: a2118_a2111_ncf_late_bull_deleverage
- target_weight_00632r: 0.0
- target_weight_cash: 0.18000000000000005
- allow_00632r_open: False
- allow_00632r_dca: False
- default_defense_asset: cash

## Rules
- default_target_weight: 0.0
- dca_allowed: False
- averaging_down_allowed: False
- discretionary_buy_allowed: False
- prefer_cash_floor_for_default_defense: True
- manual_exception_max_weight: 0.05
- manual_exception_requires_all_hedge_gates: True
- must_have_exit_rule_before_open: True

## Blocking Reasons
- dedicated_hedge_gates_do_not_allow_00632r_open
- recent_trade_review_found_00632r_buy_or_dca_records
- 00632r_dca_prohibited
- 00632r_averaging_down_prohibited
- cash_floor_preferred_over_inverse_etf_for_default_defense

## Decision
Keep 00632R at zero by default in the latest strategy. Do not DCA, average down, or buy it discretionarily; use cash as the default defensive sleeve unless all dedicated hedge gates explicitly pass.
