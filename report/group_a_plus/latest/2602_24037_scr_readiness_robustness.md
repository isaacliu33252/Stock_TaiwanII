# 2602.24037 SCR Readiness Robustness

Generated: `2026-09-12T08:40:39`
Status: `available_for_shadow_review`

## Summary

- Total runs: `18`
- Valid runs: `18`
- Gap gate pass runs: `6`
- Beta moderate runs: `18`
- Mean gap range: `0.008913` to `0.010976`
- Beta cf range: `0.632979` to `0.666534`
- Gap readiness robust: `False`
- Beta cf moderate robust: `True`

## Rows

| Eval start | Min history | K | OOS days | Mean gap | P90 gap | Beta cf | Gap pass | Beta moderate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2023-01-03 | 252 | 15 | 891 | 0.009097 | 0.019349 | 0.6396 | True | True |
| 2023-01-03 | 252 | 30 | 891 | 0.008957 | 0.019358 | 0.634014 | True | True |
| 2023-01-03 | 252 | 60 | 891 | 0.008913 | 0.019192 | 0.632979 | True | True |
| 2023-01-03 | 504 | 15 | 891 | 0.009097 | 0.019349 | 0.6396 | True | True |
| 2023-01-03 | 504 | 30 | 891 | 0.008957 | 0.019358 | 0.634014 | True | True |
| 2023-01-03 | 504 | 60 | 891 | 0.008913 | 0.019192 | 0.632979 | True | True |
| 2024-01-02 | 252 | 15 | 652 | 0.010309 | 0.021572 | 0.662586 | False | True |
| 2024-01-02 | 252 | 30 | 652 | 0.010158 | 0.021949 | 0.661068 | False | True |
| 2024-01-02 | 252 | 60 | 652 | 0.010092 | 0.022517 | 0.661238 | False | True |
| 2024-01-02 | 504 | 15 | 652 | 0.010309 | 0.021572 | 0.662586 | False | True |
| 2024-01-02 | 504 | 30 | 652 | 0.010158 | 0.021949 | 0.661068 | False | True |
| 2024-01-02 | 504 | 60 | 652 | 0.010092 | 0.022517 | 0.661238 | False | True |
| 2025-01-02 | 252 | 15 | 410 | 0.010976 | 0.02276 | 0.666534 | False | True |
| 2025-01-02 | 252 | 30 | 410 | 0.010837 | 0.022787 | 0.664324 | False | True |
| 2025-01-02 | 252 | 60 | 410 | 0.010734 | 0.023435 | 0.664856 | False | True |
| 2025-01-02 | 504 | 15 | 410 | 0.010976 | 0.02276 | 0.666534 | False | True |
| 2025-01-02 | 504 | 30 | 410 | 0.010837 | 0.022787 | 0.664324 | False | True |
| 2025-01-02 | 504 | 60 | 410 | 0.010734 | 0.023435 | 0.664856 | False | True |

## Decision

- Keep as shadow readiness guard only.
- Do not train SCR-PPO from this sweep.
- Do not change target weights or rebalance.
- Keep `Golden1_0531` unchanged.

