# GroupA+ Daily Status

Generated: `2026-07-10T10:34:55`
Check date: `2026-07-10`
Overall: `block`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `block` | required strategy sources are stale or missing: ['day_trading_0050', 'dealer_tx', 'dealer_txo'] |
| data_freshness | `ok` | 1 business days stale, 1 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `block` | required strategy sources are stale or missing: ['day_trading_0050', 'dealer_tx', 'dealer_txo']; day_trading_0050; dealer_tx; dealer_txo |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=200,069 |
| execution_plan_pre_trade_guard | `warn` | execution plan has no aligned pre_trade_guard |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-09`
- Business stale days: `1`
- Calendar stale days: `1`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `200,069`
