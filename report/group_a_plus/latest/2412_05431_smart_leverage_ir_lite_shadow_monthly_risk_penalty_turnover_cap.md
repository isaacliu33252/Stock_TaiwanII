# 2412.05431 Smart Leverage IR-lite Shadow

- Generated: `2026-08-21T16:07:25`
- Policy: `research_only_no_groupa_plus_live_change`
- Decision: `do_not_promote_keep_shadow`
- Promotion ready: `False`
- Params: `{'lookback_days': 252, 'rebalance_frequency': 'monthly', 'max_00631l_weight': 0.3, 'max_effective_beta': 1.1, 'grid_step': 0.1, 'drawdown_penalty': 12.0, 'worst_20d_penalty': 8.0, 'max_rebalance_turnover': 0.3, 'no_trade_band': 0.05, 'candidate_count': 187, 'benchmark_weights': {'0050.TW': 0.7, '00631L.TW': 0.0, '00632R.TW': 0.0, '00679B.TWO': 0.3, 'cash': 0.0}}`

## Summary

| Bucket | Windows | Pass | Delta Final vs Benchmark | Delta Final vs Latest A21.18 | Avg 00631L Weight |
|---|---:|---:|---:|---:|---:|
| all | 7 | 0/7 | 199419.49 | 2113275.17 | 0.0957 |
| holdout | 3 | 0/3 | 76024.02 | 296242.57 | 0.1259 |
| recent | 2 | 0/2 | 52602.73 | 1577990.11 | 0.0152 |
| stress | 2 | 0/2 | 70792.73 | 239042.49 | 0.1311 |

## Window Details

| Window | Bucket | IR Final | Benchmark Final | Latest A21.18 Final | dFinal vs Benchmark | dSharpe vs Benchmark | dMDD vs Benchmark | dFinal vs Latest | Avg 00631L | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| live_2024_2026 | recent | 2603741.32 | 2590999.74 | 1558183.92 | 12741.58 | -0.0453 | -0.0239 | 1045557.40 | 0.0303 | False |
| active_2025_2026 | recent | 1892924.09 | 1853062.94 | 1360491.38 | 39861.15 | -0.0459 | -0.0266 | 532432.71 | 0.0000 | False |
| holdout_2022_full | holdout | 798487.68 | 778570.85 | 913419.49 | 19916.83 | -0.1390 | 0.0440 | -114931.81 | 0.1598 | False |
| holdout_2023 | holdout | 1192775.43 | 1195178.57 | 1079671.82 | -2403.14 | 0.0453 | 0.0004 | 113103.61 | 0.2179 | False |
| holdout_2026 | holdout | 1461147.68 | 1402637.35 | 1163076.91 | 58510.33 | 0.0422 | -0.0102 | 298070.77 | 0.0000 | False |
| backfill_2020_covid | stress | 1271837.56 | 1235186.80 | 1095952.97 | 36650.76 | -0.0124 | -0.0357 | 175884.59 | 0.1394 | False |
| backfill_2021_may_correction | stress | 1152187.98 | 1118046.01 | 1089030.09 | 34141.98 | 0.1073 | -0.0110 | 63157.90 | 0.1228 | False |

## Decision

- Research-only. No latest strategy, golden1_0531, target weights, execution plan, or order file was changed.
- Promotion requires holdout pass plus separate governance, lot-rounding, turnover, and incident replay review.
