# 2609.08106 Complementarity Readiness

- generated_at: `2026-09-12T07:28:06`
- candidate: `complementarity_sleeve_window42_threshold2_shift3%_momentum5_weak`
- policy: `readiness_summary_only_no_orders_no_weight_change`
- promotion_ready: `False`

| start | end | window | events | d_return | d_sharpe | d_mdd | turnover | pass |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 2018-01-02 | 2018-12-28 | 42 | 100 | 2.1300% | 0.1270 | 1.0963% | 2.520 | True |
| 2020-01-02 | 2020-12-31 | 42 | 52 | 1.7295% | 0.1174 | 0.6145% | 2.280 | True |
| 2022-01-03 | 2022-10-31 | 42 | 107 | 2.0957% | 0.0582 | 1.8922% | 3.240 | True |
| 2024-01-02 | 2024-12-31 | 42 | 76 | 2.6526% | 0.2012 | 1.0801% | 2.100 | True |
| 2025-01-02 | 2026-09-09 | 42 | 127 | 6.9682% | 0.1972 | 1.2784% | 4.560 | True |

## Aggregate

- positive_return_windows: `5/5`
- positive_sharpe_windows: `5/5`
- non_worse_drawdown_windows: `5/5`
- blockers: `[]`

## Decision

- Keep as forward shadow candidate.
- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.
- Do not change latest GroupA++ target weights.
- Next step: Continue daily forward shadow logging with realized after-cost attribution; do not promote without enough live-period observations.
