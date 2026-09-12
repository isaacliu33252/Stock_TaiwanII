# 2510.14985v1 DeepAries-Lite Interval Shadow

- Generated: `2026-08-14T15:56:28`
- Policy: `research_only_no_groupa_plus_live_change`
- Action space tested: `[1, 5, 20]`
- Interval params: `{'crash_dd_buffer': 0.05, 'tail_risk_score_min': 4.0, 'total_risk_score_min': 6.0, 'near_ma_gap_buffer': 0.02, 'near_dd_buffer': 0.07, 'defensive_interval': 5, 'stable_golden_interval': 20}`
- Strict nontrivial gate: `{'min_total_cost_saving': 1000.0, 'min_total_turnover_reduction': 100000.0, 'min_nonzero_delta_windows': 2}`

## Summary By Method

| Method | Pass Windows | Nonzero Windows | Strict Ready | Total Final Delta | Total Cost Delta | Total Turnover Delta |
|---|---:|---:|---:|---:|---:|---:|
| deeparies_lite_adaptive_1_5_20 | 6/6 | 2/6 | `True` | 38234.30 | -8235.50 | -3763780.72 |
| deeparies_lite_adaptive_choppy_1_5_20 | 6/6 | 2/6 | `True` | 33110.21 | -5004.82 | -2302076.80 |
| fixed_20d | 2/6 | 5/6 | `False` | -126577.90 | -24840.81 | -11138097.16 |
| fixed_5d | 2/6 | 5/6 | `False` | -93579.29 | -7280.49 | -3014791.81 |

## Window Details

| Window | Method | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Reviews | Usage | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| live_2024_2026 | fixed_5d | -20368.42 | -0.0176 | 0.0000 | -3443.71 | -1425704.32 | 123 | `{'5': 123}` | False |
| live_2024_2026 | fixed_20d | -120993.72 | -0.1097 | 0.0000 | -5814.55 | -2624881.19 | 31 | `{'20': 31}` | False |
| live_2024_2026 | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 195 | `{'20': 22, '1': 173}` | True |
| live_2024_2026 | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 214 | `{'20': 21, '1': 193}` | True |
| active_2025_2026 | fixed_5d | -51224.45 | -0.1171 | -0.0135 | -2014.29 | -841024.43 | 77 | `{'5': 77}` | False |
| active_2025_2026 | fixed_20d | 39506.63 | -0.0205 | -0.0160 | -6227.24 | -2722437.56 | 20 | `{'20': 20}` | False |
| active_2025_2026 | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 134 | `{'1': 121, '20': 13}` | True |
| active_2025_2026 | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 153 | `{'1': 141, '20': 12}` | True |
| backfill_2020_covid | fixed_5d | -39621.20 | -0.2406 | -0.0083 | -1017.48 | -426945.21 | 49 | `{'5': 49}` | False |
| backfill_2020_covid | fixed_20d | -79596.97 | -0.5199 | -0.0405 | -3220.27 | -1464522.31 | 13 | `{'20': 13}` | False |
| backfill_2020_covid | deeparies_lite_adaptive_1_5_20 | 17469.20 | 0.0954 | 0.0076 | -1983.78 | -934025.26 | 100 | `{'20': 8, '1': 92}` | True |
| backfill_2020_covid | deeparies_lite_adaptive_choppy_1_5_20 | 17469.20 | 0.0954 | 0.0076 | -1983.78 | -934025.26 | 106 | `{'20': 8, '1': 98}` | True |
| backfill_2021_may_correction | fixed_5d | 13335.35 | 0.0921 | 0.0080 | -820.73 | -327178.73 | 49 | `{'5': 49}` | True |
| backfill_2021_may_correction | fixed_20d | 36673.46 | 0.2671 | 0.0080 | -9554.13 | -4316757.27 | 13 | `{'20': 13}` | True |
| backfill_2021_may_correction | deeparies_lite_adaptive_1_5_20 | 20765.10 | 0.1250 | 0.0018 | -6251.72 | -2829755.47 | 106 | `{'20': 8, '1': 98}` | True |
| backfill_2021_may_correction | deeparies_lite_adaptive_choppy_1_5_20 | 15641.01 | 0.0946 | 0.0018 | -3021.03 | -1368051.54 | 151 | `{'20': 5, '1': 146}` | True |
| backfill_2022_rate_hike | fixed_5d | 4299.44 | 0.0551 | 0.0041 | 15.71 | 6060.87 | 41 | `{'5': 41}` | False |
| backfill_2022_rate_hike | fixed_20d | -2167.30 | 0.1112 | -0.0021 | -24.63 | -9498.83 | 11 | `{'20': 11}` | False |
| backfill_2022_rate_hike | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 183 | `{'20': 1, '1': 182}` | True |
| backfill_2022_rate_hike | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 183 | `{'20': 1, '1': 182}` | True |
| backfill_2024_aug_unwind | fixed_5d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 47 | `{'5': 47}` | True |
| backfill_2024_aug_unwind | fixed_20d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 12 | `{'20': 12}` | True |
| backfill_2024_aug_unwind | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 67 | `{'20': 9, '1': 58}` | True |
| backfill_2024_aug_unwind | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 67 | `{'20': 9, '1': 58}` | True |

## Decision

- Legacy all-window no-worse gate: `True`
- Promotion ready: `True`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
