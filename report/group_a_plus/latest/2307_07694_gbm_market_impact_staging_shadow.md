# 2307.07694 GBM Market-Impact Staging Shadow

- Generated: `2026-08-14T16:26:10`
- Policy: `research_only_gbm_stress_no_live_weight_change`
- Execution plan: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/execution_plan.json`
- Settings: `{'paths': 2000, 'horizon_days': 20, 'defer_days': 5, 'impact_scale': 3.0, 'commission_rate': 0.001425, 'slippage_rate': 0.0005, 'equity_etf_sell_tax': 0.001, 'seed': 230707694}`

## Scenario Summary

| Scenario | Mean Final Delta | P05 Final Delta | Cost Delta Mean | Cost Save Rate | Staged Win Rate |
|---|---:|---:|---:|---:|---:|
| neutral | 38762.90 | 25458.50 | -39509.43 | 1.000 | 1.000 |
| bull | 38706.53 | 25107.66 | -39509.34 | 1.000 | 1.000 |
| bear | 40789.82 | 25210.09 | -39687.92 | 1.000 | 1.000 |
| high_vol_flat | 38856.95 | 12442.98 | -39496.15 | 1.000 | 0.988 |

## Decision

- Recommended use: `shadow_stress_test_only`
- Promote to live: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- No latest strategy, live signal, execution plan, or order file was changed.
