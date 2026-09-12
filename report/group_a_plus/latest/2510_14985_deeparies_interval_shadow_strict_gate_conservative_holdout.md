# 2510.14985v1 DeepAries-Lite Interval Shadow

- Generated: `2026-08-14T15:56:20`
- Policy: `research_only_no_groupa_plus_live_change`
- Action space tested: `[1, 5, 20]`
- Interval params: `{'crash_dd_buffer': 0.05, 'tail_risk_score_min': 4.0, 'total_risk_score_min': 6.0, 'near_ma_gap_buffer': 0.02, 'near_dd_buffer': 0.07, 'defensive_interval': 5, 'stable_golden_interval': 20}`
- Strict nontrivial gate: `{'min_total_cost_saving': 1000.0, 'min_total_turnover_reduction': 100000.0, 'min_nonzero_delta_windows': 2}`

## Summary By Method

| Method | Pass Windows | Nonzero Windows | Strict Ready | Total Final Delta | Total Cost Delta | Total Turnover Delta |
|---|---:|---:|---:|---:|---:|---:|
| deeparies_lite_adaptive_1_5_20 | 3/3 | 0/3 | `False` | 0.00 | 0.00 | 0.00 |
| deeparies_lite_adaptive_choppy_1_5_20 | 3/3 | 0/3 | `False` | 0.00 | 0.00 | 0.00 |
| fixed_20d | 1/3 | 2/3 | `False` | 39545.76 | -4415.15 | -1953104.19 |
| fixed_5d | 2/3 | 2/3 | `False` | 13766.96 | -1226.49 | -505993.88 |

## Window Details

| Window | Method | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Reviews | Usage | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| holdout_2023 | fixed_5d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 48 | `{'5': 48}` | True |
| holdout_2023 | fixed_20d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 12 | `{'20': 12}` | True |
| holdout_2023 | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 94 | `{'1': 86, '20': 8}` | True |
| holdout_2023 | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 94 | `{'1': 86, '20': 8}` | True |
| holdout_2026 | fixed_5d | 9501.35 | 0.0495 | 0.0000 | -1253.09 | -517711.69 | 29 | `{'5': 29}` | True |
| holdout_2026 | fixed_20d | 47533.64 | 0.0905 | -0.0080 | -4392.91 | -1944840.88 | 8 | `{'20': 8}` | False |
| holdout_2026 | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 29 | `{'20': 6, '1': 23}` | True |
| holdout_2026 | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 29 | `{'20': 6, '1': 23}` | True |
| holdout_2022_full | fixed_5d | 4265.61 | 0.0426 | 0.0041 | 26.60 | 11717.81 | 50 | `{'5': 50}` | False |
| holdout_2022_full | fixed_20d | -7987.88 | -0.0681 | -0.0021 | -22.25 | -8263.31 | 13 | `{'20': 13}` | False |
| holdout_2022_full | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 208 | `{'20': 2, '1': 206}` | True |
| holdout_2022_full | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 208 | `{'20': 2, '1': 206}` | True |

## Decision

- Legacy all-window no-worse gate: `True`
- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
