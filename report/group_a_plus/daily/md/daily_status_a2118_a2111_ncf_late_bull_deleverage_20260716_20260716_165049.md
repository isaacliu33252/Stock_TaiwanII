# GroupA+ Daily Status

Generated: `2026-07-16T16:50:49`
Check date: `2026-07-16`
Overall: `warn`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `ok` | allowed |
| data_freshness | `ok` | 0 business days stale, 0 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `ok` | all required sources ok |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=300,106 |
| execution_plan_pre_trade_guard | `warn` | execution plan has no aligned pre_trade_guard |
| dfl_advisory_frozen_input_staleness | `ok` | frozen backtest last covers 2026-07-13 (3 calendar days behind check_date); matched_decision_count is structurally 0 until this is re-run |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-16`
- Business stale days: `0`
- Calendar stale days: `0`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `300,106`

## A21.18 DFL Shadow Ensemble

- Level: `none`
- Manual review: `False`
- Policy: `shadow_only_no_auto_weight_change`
- `base` action `KEEP` active `False` reliability `None`
- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## 00631L Compounding Regime

- Regime: `MEAN_REVERTING`
- Policy: `prohibit_new_leverage_or_reduce_rebalance_frequency`
- Trend score: `1`
- Mean-reversion score: `3`
- AR1 5d / 20d: `-0.4657972613531006` / `0.03409666613259`
- Variance ratio: `0.9138730393558065`
- 00631L vs 0050 relative momentum: `-0.012304649931065281`

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
