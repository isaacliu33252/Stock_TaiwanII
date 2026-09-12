# 2510.14985v1 DeepAries-Lite Interval Shadow

- Generated: `2026-08-14T15:45:29`
- Policy: `research_only_no_groupa_plus_live_change`
- Action space tested: `[1, 5, 20]`
- Interval params: `{'crash_dd_buffer': 0.03, 'tail_risk_score_min': 5.0, 'total_risk_score_min': 8.0, 'near_ma_gap_buffer': 0.015, 'near_dd_buffer': 0.05, 'defensive_interval': 5, 'stable_golden_interval': 20}`

## Summary By Method

| Method | Pass Windows | Total Final Delta | Total Cost Delta | Total Turnover Delta |
|---|---:|---:|---:|---:|
| deeparies_lite_adaptive_1_5_20 | 4/6 | 189913.08 | -20444.06 | -9135817.12 |
| deeparies_lite_adaptive_choppy_1_5_20 | 3/6 | -27272.53 | -2395.85 | -1111863.37 |
| fixed_20d | 2/6 | -126577.90 | -24840.81 | -11138097.16 |
| fixed_5d | 2/6 | -93579.29 | -7280.49 | -3014791.81 |

## Window Details

| Window | Method | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Reviews | Usage | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| live_2024_2026 | fixed_5d | -20368.42 | -0.0176 | 0.0000 | -3443.71 | -1425704.32 | 123 | `{'5': 123}` | False |
| live_2024_2026 | fixed_20d | -120993.72 | -0.1097 | 0.0000 | -5814.55 | -2624881.19 | 31 | `{'20': 31}` | False |
| live_2024_2026 | deeparies_lite_adaptive_1_5_20 | 104145.64 | 0.0298 | 0.0000 | -7893.01 | -3444570.20 | 155 | `{'20': 25, '1': 130}` | True |
| live_2024_2026 | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 176 | `{'20': 23, '1': 153}` | True |
| active_2025_2026 | fixed_5d | -51224.45 | -0.1171 | -0.0135 | -2014.29 | -841024.43 | 77 | `{'5': 77}` | False |
| active_2025_2026 | fixed_20d | 39506.63 | -0.0205 | -0.0160 | -6227.24 | -2722437.56 | 20 | `{'20': 20}` | False |
| active_2025_2026 | deeparies_lite_adaptive_1_5_20 | 39580.95 | -0.0350 | -0.0160 | -6270.32 | -2737163.65 | 94 | `{'20': 16, '1': 78}` | False |
| active_2025_2026 | deeparies_lite_adaptive_choppy_1_5_20 | -38923.80 | -0.0825 | -0.0160 | -320.58 | -140654.19 | 115 | `{'20': 14, '1': 101}` | False |
| backfill_2020_covid | fixed_5d | -39621.20 | -0.2406 | -0.0083 | -1017.48 | -426945.21 | 49 | `{'5': 49}` | False |
| backfill_2020_covid | fixed_20d | -79596.97 | -0.5199 | -0.0405 | -3220.27 | -1464522.31 | 13 | `{'20': 13}` | False |
| backfill_2020_covid | deeparies_lite_adaptive_1_5_20 | 17469.20 | 0.0954 | 0.0076 | -1983.78 | -934025.26 | 100 | `{'20': 8, '1': 92}` | True |
| backfill_2020_covid | deeparies_lite_adaptive_choppy_1_5_20 | 17469.20 | 0.0954 | 0.0076 | -1983.78 | -934025.26 | 105 | `{'20': 8, '1': 97}` | True |
| backfill_2021_may_correction | fixed_5d | 13335.35 | 0.0921 | 0.0080 | -820.73 | -327178.73 | 49 | `{'5': 49}` | True |
| backfill_2021_may_correction | fixed_20d | 36673.46 | 0.2671 | 0.0080 | -9554.13 | -4316757.27 | 13 | `{'20': 13}` | True |
| backfill_2021_may_correction | deeparies_lite_adaptive_1_5_20 | 33199.45 | 0.2673 | 0.0067 | -4251.59 | -2002564.90 | 77 | `{'20': 9, '1': 67, '5': 1}` | True |
| backfill_2021_may_correction | deeparies_lite_adaptive_choppy_1_5_20 | -1335.78 | -0.0111 | -0.0011 | -46.14 | -19690.81 | 144 | `{'20': 6, '1': 137, '5': 1}` | False |
| backfill_2022_rate_hike | fixed_5d | 4299.44 | 0.0551 | 0.0041 | 15.71 | 6060.87 | 41 | `{'5': 41}` | False |
| backfill_2022_rate_hike | fixed_20d | -2167.30 | 0.1112 | -0.0021 | -24.63 | -9498.83 | 11 | `{'20': 11}` | False |
| backfill_2022_rate_hike | deeparies_lite_adaptive_1_5_20 | -4482.15 | 0.0999 | -0.0044 | -45.35 | -17493.11 | 164 | `{'20': 2, '1': 162}` | False |
| backfill_2022_rate_hike | deeparies_lite_adaptive_choppy_1_5_20 | -4482.15 | 0.0999 | -0.0044 | -45.35 | -17493.11 | 164 | `{'20': 2, '1': 162}` | False |
| backfill_2024_aug_unwind | fixed_5d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 47 | `{'5': 47}` | True |
| backfill_2024_aug_unwind | fixed_20d | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 12 | `{'20': 12}` | True |
| backfill_2024_aug_unwind | deeparies_lite_adaptive_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 50 | `{'20': 10, '1': 40}` | True |
| backfill_2024_aug_unwind | deeparies_lite_adaptive_choppy_1_5_20 | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 50 | `{'20': 10, '1': 40}` | True |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
