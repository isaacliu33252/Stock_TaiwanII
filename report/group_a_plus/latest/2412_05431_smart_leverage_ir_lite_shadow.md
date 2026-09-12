# 2412.05431 Smart Leverage IR-lite Shadow

- Generated: `2026-08-21T16:11:09`
- Policy: `research_only_no_groupa_plus_live_change`
- Decision: `do_not_promote_keep_shadow`
- Promotion ready: `False`
- Params: `{'lookback_days': 252, 'rebalance_frequency': 'quarterly', 'max_00631l_weight': 0.3, 'max_effective_beta': 1.1, 'grid_step': 0.05, 'drawdown_penalty': 5.0, 'worst_20d_penalty': 3.0, 'max_rebalance_turnover': None, 'no_trade_band': 0.0, 'candidate_count': 1170, 'benchmark_weights': {'0050.TW': 0.7, '00631L.TW': 0.0, '00632R.TW': 0.0, '00679B.TWO': 0.3, 'cash': 0.0}}`

## Summary

| Bucket | Windows | Pass | Delta Final vs Benchmark | Delta Final vs Latest A21.18 | Avg 00631L Weight |
|---|---:|---:|---:|---:|---:|
| all | 7 | 0/7 | -2816.30 | 1911039.38 | 0.0687 |
| holdout | 3 | 0/3 | 8149.68 | 228368.23 | 0.0925 |
| recent | 2 | 0/2 | -87054.39 | 1438332.99 | 0.0152 |
| stress | 2 | 0/2 | 76088.41 | 244338.16 | 0.0867 |

## Window Details

| Window | Bucket | IR Final | Benchmark Final | Latest A21.18 Final | dFinal vs Benchmark | dSharpe vs Benchmark | dMDD vs Benchmark | dFinal vs Latest | Avg 00631L | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| live_2024_2026 | recent | 2500910.85 | 2590999.74 | 1558183.92 | -90088.89 | -0.0327 | -0.0041 | 942726.93 | 0.0257 | False |
| active_2025_2026 | recent | 1856097.44 | 1853062.94 | 1360491.38 | 3034.51 | -0.0070 | -0.0134 | 495606.06 | 0.0046 | False |
| holdout_2022_full | holdout | 793719.80 | 778570.85 | 913419.49 | 15148.95 | -0.0542 | 0.0305 | -119699.69 | 0.1514 | False |
| holdout_2023 | holdout | 1163965.80 | 1195178.57 | 1079671.82 | -31212.77 | -0.1554 | -0.0054 | 84293.98 | 0.1142 | False |
| holdout_2026 | holdout | 1426850.85 | 1402637.35 | 1163076.91 | 24213.50 | 0.0334 | -0.0033 | 263773.94 | 0.0118 | False |
| backfill_2020_covid | stress | 1280396.85 | 1235186.80 | 1095952.97 | 45210.05 | 0.0783 | -0.0222 | 184443.88 | 0.0863 | False |
| backfill_2021_may_correction | stress | 1148924.37 | 1118046.01 | 1089030.09 | 30878.36 | 0.0988 | -0.0135 | 59894.28 | 0.0870 | False |

## Decision

- Research-only. No latest strategy, golden1_0531, target weights, execution plan, or order file was changed.
- Promotion requires holdout pass plus separate governance, lot-rounding, turnover, and incident replay review.
