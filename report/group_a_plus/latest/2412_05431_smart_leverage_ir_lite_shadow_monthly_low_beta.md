# 2412.05431 Smart Leverage IR-lite Shadow

- Generated: `2026-08-21T16:08:37`
- Policy: `research_only_no_groupa_plus_live_change`
- Decision: `do_not_promote_keep_shadow`
- Promotion ready: `False`
- Params: `{'lookback_days': 252, 'rebalance_frequency': 'monthly', 'max_00631l_weight': 0.1, 'max_effective_beta': 0.8, 'grid_step': 0.1, 'drawdown_penalty': 20.0, 'worst_20d_penalty': 12.0, 'max_rebalance_turnover': 0.2, 'no_trade_band': 0.05, 'candidate_count': 101, 'benchmark_weights': {'0050.TW': 0.7, '00631L.TW': 0.0, '00632R.TW': 0.0, '00679B.TWO': 0.3, 'cash': 0.0}}`

## Summary

| Bucket | Windows | Pass | Delta Final vs Benchmark | Delta Final vs Latest A21.18 | Avg 00631L Weight |
|---|---:|---:|---:|---:|---:|
| all | 7 | 0/7 | -5471.08 | 1908384.60 | 0.0556 |
| holdout | 3 | 0/3 | 74290.84 | 294509.39 | 0.0642 |
| recent | 2 | 0/2 | -132001.65 | 1393385.73 | 0.0068 |
| stress | 2 | 0/2 | 52239.73 | 220489.48 | 0.0915 |

## Window Details

| Window | Bucket | IR Final | Benchmark Final | Latest A21.18 Final | dFinal vs Benchmark | dSharpe vs Benchmark | dMDD vs Benchmark | dFinal vs Latest | Avg 00631L | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| live_2024_2026 | recent | 2473505.34 | 2590999.74 | 1558183.92 | -117494.40 | -0.0867 | 0.0007 | 915321.43 | 0.0136 | False |
| active_2025_2026 | recent | 1838555.68 | 1853062.94 | 1360491.38 | -14507.26 | -0.1020 | -0.0192 | 478064.30 | 0.0000 | False |
| holdout_2022_full | holdout | 793551.43 | 778570.85 | 913419.49 | 14980.57 | -0.0610 | 0.0230 | -119868.06 | 0.1000 | False |
| holdout_2023 | holdout | 1195978.51 | 1195178.57 | 1079671.82 | 799.93 | 0.0643 | 0.0020 | 116306.68 | 0.0925 | False |
| holdout_2026 | holdout | 1461147.68 | 1402637.35 | 1163076.91 | 58510.33 | 0.0422 | -0.0102 | 298070.77 | 0.0000 | False |
| backfill_2020_covid | stress | 1267432.55 | 1235186.80 | 1095952.97 | 32245.75 | 0.0393 | -0.0169 | 171479.58 | 0.0918 | False |
| backfill_2021_may_correction | stress | 1138039.99 | 1118046.01 | 1089030.09 | 19993.98 | 0.0582 | -0.0014 | 49009.90 | 0.0912 | False |

## Decision

- Research-only. No latest strategy, golden1_0531, target weights, execution plan, or order file was changed.
- Promotion requires holdout pass plus separate governance, lot-rounding, turnover, and incident replay review.
