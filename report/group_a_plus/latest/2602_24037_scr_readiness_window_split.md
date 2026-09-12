# 2602.24037 SCR Readiness Window Split

Generated: `2026-09-12T08:39:37`
Status: `available_for_shadow_review`

## Summary

- Valid windows: `5`
- Gap gate pass windows: `2`
- Beta moderate windows: `5`
- Mean gap range: `0.008943` to `0.011228`
- Beta cf range: `0.583296` to `0.689016`
- Stress gap readiness passed: `False`
- Stress beta cf moderate passed: `True`

## Rows

| Window | OOS days | Mean gap | P90 gap | Beta cf | Gap pass | Beta moderate |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| covid_2020 | 101 | 0.011228 | 0.024054 | 0.689016 | False | True |
| rate_hike_2022 | 246 | 0.009329 | 0.019363 | 0.583296 | True | True |
| post_2023 | 883 | 0.008943 | 0.019644 | 0.63433 | True | True |
| recent_2024_2026 | 644 | 0.010154 | 0.022132 | 0.661658 | False | True |
| active_2025_2026 | 402 | 0.010844 | 0.022903 | 0.665215 | False | True |

## Decision

- Keep as shadow readiness guard only.
- Do not train SCR-PPO from this window split.
- Do not change target weights or rebalance.
- Keep `Golden1_0531` unchanged.

