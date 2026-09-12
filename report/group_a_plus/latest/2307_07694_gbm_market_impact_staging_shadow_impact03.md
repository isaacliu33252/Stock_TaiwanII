# 2307.07694 GBM Market-Impact Staging Shadow

- Generated: `2026-08-14T16:26:34`
- Policy: `research_only_gbm_stress_no_live_weight_change`
- Execution plan: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/execution_plan.json`
- Settings: `{'paths': 2000, 'horizon_days': 20, 'defer_days': 5, 'impact_scale': 0.3, 'commission_rate': 0.001425, 'slippage_rate': 0.0005, 'equity_etf_sell_tax': 0.001, 'seed': 230707694}`

## Scenario Summary

| Scenario | Mean Final Delta | P05 Final Delta | Cost Delta Mean | Cost Save Rate | Staged Win Rate |
|---|---:|---:|---:|---:|---:|
| neutral | 3208.45 | -9110.99 | -3954.99 | 1.000 | 0.672 |
| bull | 3152.08 | -9516.25 | -3954.88 | 1.000 | 0.666 |
| bear | 5077.87 | -9381.91 | -3975.97 | 1.000 | 0.719 |
| high_vol_flat | 3314.64 | -21240.50 | -3953.84 | 1.000 | 0.597 |

## Decision

- Recommended use: `shadow_stress_test_only`
- Promote to live: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- No latest strategy, live signal, execution plan, or order file was changed.
