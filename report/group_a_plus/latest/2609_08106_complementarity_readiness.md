# 2609.08106 Complementarity Readiness

- generated_at: `2026-09-10T13:21:55`
- candidate: `complementarity_sleeve_window42_threshold2_shift3pct`
- policy: `readiness_summary_only_no_orders_no_weight_change`
- promotion_ready: `False`

| start | end | window | events | d_return | d_sharpe | d_mdd | turnover | pass |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 2018-01-02 | 2018-12-28 | 42 | 151 | 1.8785% | 0.1076 | 1.1186% | 2.220 | True |
| 2020-01-02 | 2020-06-30 | 42 | 51 | 0.0292% | 0.0082 | 0.6145% | 0.720 | True |
| 2022-01-03 | 2022-10-31 | 42 | 167 | 1.1018% | -0.0285 | 1.0576% | 1.260 | False |
| 2024-01-02 | 2024-12-31 | 42 | 128 | 0.8841% | 0.1245 | 1.0801% | 1.740 | True |
| 2025-01-02 | 2026-09-09 | 42 | 224 | 1.4721% | 0.1228 | 1.2086% | 4.680 | True |
| 2025-01-02 | 2026-09-09 | 63 | 218 | 1.1591% | 0.1149 | 0.9533% | 4.020 | True |

## Aggregate

- positive_return_windows: `6/6`
- positive_sharpe_windows: `5/6`
- non_worse_drawdown_windows: `6/6`
- blockers: `['not_all_windows_positive_sharpe', 'not_all_windows_pass_single_window_gate']`

## Decision

- Keep as forward shadow candidate.
- Do not change latest GroupA++ target weights, Golden1, or Golden2.
- Next step: Run OOS-forward logging and parameter robustness; investigate 2022 Sharpe failure before promotion.
