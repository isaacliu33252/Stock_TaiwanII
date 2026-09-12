# 2604.02126 Cost Stress

Generated: `2026-08-29T23:26:31`
As of: `2026-08-28`
Status: `blocked_for_live_promotion`

## Decision

- Do not change live target weights.
- Do not open or increase `00632R.TW`.
- Keep `Golden1_0531` unchanged.

## Rows

| model | cost bps | robust-standard return | robust-standard sharpe | robust-standard mdd | pass |
| --- | ---: | ---: | ---: | ---: | --- |
| rolling_mean | 0.0 | -0.212627 | -0.029140 | 0.001569 | False |
| rolling_mean | 5.0 | -0.213017 | -0.029403 | 0.001482 | False |
| rolling_mean | 10.0 | -0.213407 | -0.029667 | 0.001395 | False |
| rolling_mean | 20.0 | -0.214188 | -0.030195 | 0.001222 | False |
| rolling_mean | 50.0 | -0.216528 | -0.031778 | 0.000702 | False |
| ar1 | 0.0 | -0.568893 | -0.016449 | -0.025802 | False |
| ar1 | 5.0 | -0.574915 | -0.021966 | -0.027446 | False |
| ar1 | 10.0 | -0.580937 | -0.027484 | -0.029084 | False |
| ar1 | 20.0 | -0.592981 | -0.038523 | -0.032347 | False |
| ar1 | 50.0 | -0.629113 | -0.071662 | -0.042015 | False |
| har_lite | 0.0 | -0.580009 | -0.034752 | -0.030254 | False |
| har_lite | 5.0 | -0.589805 | -0.043479 | -0.032524 | False |
| har_lite | 10.0 | -0.599602 | -0.052206 | -0.034785 | False |
| har_lite | 20.0 | -0.619194 | -0.069661 | -0.039280 | False |
| har_lite | 50.0 | -0.677973 | -0.122034 | -0.052550 | False |

## Blockers

- `daily_close_proxy_not_high_frequency_realized_covariance`
- `letf_readiness_blocks_00632r_open`
- `live_hedge_policy_not_validated_for_robust_ratio`
- `no_cost_scenario_passed_robust_vs_standard_filter`
- `research_only_transaction_cost_stress`

