# GroupA+ Daily Status

Generated: `2026-07-13T18:41:07`
Check date: `2026-07-13`
Overall: `warn`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `ok` | allowed |
| data_freshness | `warn` | 2 business days stale, 4 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `warn` | NCF live overlay skipped: date mismatch {'00631L.TW': '2026-07-10', '00632R.TW': '2026-07-10'}, actual 2026-07-09 |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=300,123 |
| execution_plan_pre_trade_guard | `warn` | execution plan has no aligned pre_trade_guard |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-09`
- Business stale days: `2`
- Calendar stale days: `4`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `300,123`

## 00631L Compounding Regime

- Regime: `MEAN_REVERTING`
- Policy: `prohibit_new_leverage_or_reduce_rebalance_frequency`
- Trend score: `3`
- Mean-reversion score: `3`
- AR1 5d / 20d: `-0.15891126254568375` / `0.0872425443275918`
- Variance ratio: `0.9567617503213399`
- 00631L vs 0050 relative momentum: `0.018557664489911918`
