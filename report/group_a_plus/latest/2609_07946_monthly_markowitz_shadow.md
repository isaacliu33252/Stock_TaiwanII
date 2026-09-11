# 2609.07946 Monthly Markowitz Shadow

- generated_at: `2026-09-12T07:45:03`
- policy: `shadow_only_no_orders_no_live_weight_change`
- robust_combo_count: `0`
- promotion_ready: `False`

| risk_aversion | trust_region | turnover_penalty | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.06 | 0.0005 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.10 | 0.0005 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.14 | 0.0005 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.06 | 0.0000 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.10 | 0.0000 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.14 | 0.0000 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.06 | 0.0010 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |
| 0.50 | 0.10 | 0.0010 | 3/5 | 0.3415% | 0.0105 | 0.1283% | 0.162 |

## Notes

- 00635U.TW is a Taiwan gold-futures ETF in DB but not in current GroupA++ tradable core/watchlist.
- Monthly optimizer is bounded around latest GroupA++ baseline and remains shadow-only.

## Decision

- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
