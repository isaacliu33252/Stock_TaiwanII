# 2609.07946 Stock/Bond/Gold Complementarity Shadow

- generated_at: `2026-09-12T07:44:09`
- policy: `shadow_only_no_orders_no_live_weight_change`
- robust_combo_count: `20`
- promotion_ready: `False`

| universe | threshold | shift | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| bond_plus_00635u | 1.80 | 4.00% | 5/5 | 5.1965% | 0.2144 | 1.8690% | 5.184 |
| bond_plus_gold_proxy | 1.80 | 4.00% | 5/5 | 5.1885% | 0.2075 | 1.7884% | 4.912 |
| bond_plus_00635u | 2.00 | 4.00% | 5/5 | 4.9476% | 0.2073 | 1.8617% | 4.912 |
| bond_plus_gold_proxy | 2.00 | 4.00% | 5/5 | 4.6787% | 0.1870 | 1.7087% | 4.080 |
| bond_only | 1.80 | 4.00% | 5/5 | 4.1589% | 0.1728 | 1.4920% | 4.176 |
| bond_plus_00635u | 1.80 | 3.00% | 5/5 | 3.8774% | 0.1584 | 1.3975% | 3.888 |
| bond_plus_gold_proxy | 1.80 | 3.00% | 5/5 | 3.8696% | 0.1534 | 1.3367% | 3.684 |
| bond_plus_00635u | 2.00 | 3.00% | 5/5 | 3.6930% | 0.1533 | 1.3919% | 3.684 |

## Notes

- GC=F is data-only and not a directly executable GroupA++ instrument.
- 00635U.TW is a Taiwan gold-futures ETF in DB but not in current GroupA++ tradable core/watchlist.

## Decision

- Keep as shadow-only research.
- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.
- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.
