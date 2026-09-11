# 2609.08106 Mom5 Gate Robustness

- generated_at: `2026-09-12T07:28:31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- robust_combo_count: `18`
- promotion_ready: `False`

| threshold | shift | cost_bps | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.80 | 4.00% | 10.0 | 5/5 | 4.5924% | 0.1995 | 1.6918% | 4.480 |
| 2.00 | 4.00% | 10.0 | 5/5 | 4.1685% | 0.1896 | 1.5935% | 3.920 |
| 1.80 | 4.00% | 20.0 | 5/5 | 3.9662% | 0.1750 | 1.5856% | 4.480 |
| 2.00 | 4.00% | 20.0 | 5/5 | 3.6258% | 0.1685 | 1.4937% | 3.920 |
| 2.20 | 4.00% | 10.0 | 5/5 | 3.4923% | 0.1579 | 1.4102% | 2.640 |

## Decision

- Keep as shadow-only candidate.
- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.
- No GroupA++ live target-weight changes.
- Next gate: daily forward shadow log with realized after-cost attribution.
