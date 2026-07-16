# GroupA+ Daily Status

Generated: `2026-07-11T23:27:38`
Check date: `2026-07-11`
Overall: `block`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `block` | required strategy sources are stale or missing: ['day_trading_0050', 'dealer_tx', 'dealer_txo', 'foreign_shareholding_0050', 'institutional_0050', 'short_balance_0050'] |
| data_freshness | `warn` | 0 business days stale, 1 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `block` | required strategy sources are stale or missing: ['day_trading_0050', 'dealer_tx', 'dealer_txo', 'foreign_shareholding_0050', 'institutional_0050', 'short_balance_0050']; soft strategy sources are stale or missing: ['securities_lending_0050']; institutional_0050; foreign_shareholding_0050; short_balance_0050; day_trading_0050; dealer_tx; dealer_txo; securities_lending_0050 |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=200,069 |
| execution_plan_pre_trade_guard | `warn` | execution plan has no aligned pre_trade_guard |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-10`
- Business stale days: `0`
- Calendar stale days: `1`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `200,069`
