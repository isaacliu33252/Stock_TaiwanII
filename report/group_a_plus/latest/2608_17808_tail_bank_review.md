# 2608.17808 Tail Bank Review

- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Best stability candidate: `cap631_tail2_dd10_vol125_beta05`
- No target-weight change: `True`
- No further auto tuning recommended: `True`

## Candidate Summary

| candidate | cap days | FV+ | Sharpe+ | MDD+ | tail nonneg | worst FV | worst Sharpe | worst MDD | pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| cap631_tail2_dd10_vol125_beta05 | 10 | 1/6 | 1/6 | 1/6 | 5/6 | -45.01 | -0.000712 | -0.000028 | False |
| cap631_tail2_dd10_vol125_beta10 | 10 | 1/6 | 1/6 | 1/6 | 5/6 | -60.01 | -0.000949 | -0.000038 | False |
| cap631_tail_drawdown_vol_beta05 | 72 | 2/6 | 2/6 | 4/6 | 4/6 | -12369.52 | -0.016992 | -0.003314 | False |
| both_tail_drawdown_vol_beta05 | 82 | 2/6 | 2/6 | 2/6 | 1/6 | -29760.99 | -0.625353 | -0.011384 | False |

## Window Details

### cap631_tail2_dd10_vol125_beta05

| window | kind | cap days | dFV | dSharpe | dMDD | dWorst20D |
|---|---|---:|---:|---:|---:|---:|
| covid_2020 | out_of_sample | 2 | -25.35 | -0.000198 | 0.000000 | 0.000000 |
| rate_hike_2022 | out_of_sample | 1 | -2.61 | -0.000051 | -0.000003 | 0.000000 |
| full_2024 | out_of_sample | 3 | 896.92 | 0.000493 | 0.006713 | 0.006886 |
| active_2025_2026 | tuning_window | 2 | -45.01 | -0.000120 | 0.000000 | 0.000000 |
| taiwan_2026_q1q2_stress | stress_window | 2 | -33.78 | -0.000712 | -0.000028 | -0.000029 |
| taiwan_2026_recent | recent_window | 0 | 0.00 | 0.000000 | 0.000000 | 0.000000 |

### cap631_tail2_dd10_vol125_beta10

| window | kind | cap days | dFV | dSharpe | dMDD | dWorst20D |
|---|---|---:|---:|---:|---:|---:|
| covid_2020 | out_of_sample | 2 | -33.79 | -0.000263 | 0.000000 | 0.000000 |
| rate_hike_2022 | out_of_sample | 1 | -3.48 | -0.000068 | -0.000003 | 0.000000 |
| full_2024 | out_of_sample | 3 | 1092.33 | 0.000606 | 0.008937 | 0.009167 |
| active_2025_2026 | tuning_window | 2 | -60.01 | -0.000160 | 0.000000 | 0.000000 |
| taiwan_2026_q1q2_stress | stress_window | 2 | -45.04 | -0.000949 | -0.000038 | -0.000038 |
| taiwan_2026_recent | recent_window | 0 | 0.00 | 0.000000 | 0.000000 | 0.000000 |

### cap631_tail_drawdown_vol_beta05

| window | kind | cap days | dFV | dSharpe | dMDD | dWorst20D |
|---|---|---:|---:|---:|---:|---:|
| covid_2020 | out_of_sample | 8 | -613.93 | -0.005100 | 0.000000 | 0.000000 |
| rate_hike_2022 | out_of_sample | 6 | 2.45 | -0.000053 | 0.000002 | -0.000000 |
| full_2024 | out_of_sample | 17 | -12369.52 | -0.005429 | 0.011047 | 0.011331 |
| active_2025_2026 | tuning_window | 24 | -10752.89 | -0.016992 | -0.003314 | 0.000000 |
| taiwan_2026_q1q2_stress | stress_window | 16 | -2501.31 | 0.089272 | 0.000094 | -0.001326 |
| taiwan_2026_recent | recent_window | 1 | 1.22 | 0.000024 | 0.000001 | 0.000001 |

### both_tail_drawdown_vol_beta05

| window | kind | cap days | dFV | dSharpe | dMDD | dWorst20D |
|---|---|---:|---:|---:|---:|---:|
| covid_2020 | out_of_sample | 9 | 12120.96 | 0.096568 | 0.000821 | -0.000000 |
| rate_hike_2022 | out_of_sample | 11 | 988.29 | 0.046063 | 0.000961 | -0.000000 |
| full_2024 | out_of_sample | 21 | -29760.99 | -0.013504 | -0.008100 | -0.008309 |
| active_2025_2026 | tuning_window | 24 | -26418.92 | -0.113611 | -0.003084 | 0.000000 |
| taiwan_2026_q1q2_stress | stress_window | 16 | -14313.48 | -0.625353 | -0.011384 | -0.013314 |
| taiwan_2026_recent | recent_window | 1 | -1095.46 | -0.021244 | -0.000966 | -0.000973 |

No target-weight change. This review is a research-only diagnostic gate.
