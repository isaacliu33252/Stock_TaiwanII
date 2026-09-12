# 2412.05431 Smart Leverage IR-lite Shadow

- Generated: `2026-08-21T15:48:10`
- Policy: `research_only_no_groupa_plus_live_change`
- Decision: `do_not_promote_keep_shadow`
- Promotion ready: `False`
- Params: `{'lookback_days': 252, 'rebalance_frequency': 'monthly', 'max_00631l_weight': 0.3, 'max_effective_beta': 1.1, 'grid_step': 0.1, 'candidate_count': 187, 'benchmark_weights': {'0050.TW': 0.7, '00631L.TW': 0.0, '00632R.TW': 0.0, '00679B.TWO': 0.3, 'cash': 0.0}}`

## Summary

| Bucket | Windows | Pass | Delta Final vs Benchmark | Delta Final vs Latest A21.18 | Avg 00631L Weight |
|---|---:|---:|---:|---:|---:|
| all | 7 | 0/7 | 367864.63 | 2281720.32 | 0.1357 |
| holdout | 3 | 0/3 | 74961.71 | 295180.26 | 0.1684 |
| recent | 2 | 0/2 | 196163.19 | 1721550.56 | 0.0360 |
| stress | 2 | 0/2 | 96739.74 | 264989.49 | 0.1862 |

## Window Details

| Window | Bucket | IR Final | Benchmark Final | Latest A21.18 Final | dFinal vs Benchmark | dSharpe vs Benchmark | dMDD vs Benchmark | dFinal vs Latest | Avg 00631L | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| live_2024_2026 | recent | 2699918.97 | 2590999.74 | 1558183.92 | 108919.23 | -0.0979 | -0.0263 | 1141735.06 | 0.0559 | False |
| active_2025_2026 | recent | 1940306.89 | 1853062.94 | 1360491.38 | 87243.95 | -0.0826 | -0.0266 | 579815.51 | 0.0162 | False |
| holdout_2022_full | holdout | 799224.80 | 778570.85 | 913419.49 | 20653.95 | -0.1388 | 0.0485 | -114194.69 | 0.2305 | False |
| holdout_2023 | holdout | 1173241.33 | 1195178.57 | 1079671.82 | -21937.24 | -0.1368 | -0.0049 | 93569.51 | 0.2326 | False |
| holdout_2026 | holdout | 1478882.36 | 1402637.35 | 1163076.91 | 76245.01 | -0.1119 | -0.0334 | 315805.44 | 0.0421 | False |
| backfill_2020_covid | stress | 1293701.89 | 1235186.80 | 1095952.97 | 58515.09 | 0.0636 | -0.0357 | 197748.92 | 0.1612 | False |
| backfill_2021_may_correction | stress | 1156270.65 | 1118046.01 | 1089030.09 | 38224.65 | 0.0164 | -0.0330 | 67240.57 | 0.2111 | False |

## Decision

- Research-only. No latest strategy, golden1_0531, target weights, execution plan, or order file was changed.
- Promotion requires holdout pass plus separate governance, lot-rounding, turnover, and incident replay review.
