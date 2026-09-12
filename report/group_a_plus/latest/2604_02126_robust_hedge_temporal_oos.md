# 2604.02126 Robust Hedge Temporal OOS

Generated: `2026-08-29T23:01:26`
Status: `blocked_for_live_promotion`

## Decision

- Do not change live target weights.
- Do not open or increase `00632R.TW`.
- Keep `Golden1_0531` unchanged.

## Summary

- parameter count: `27`
- eligible parameter count: `0`

## Best Rows

| window | uncertainty | cap | valid | pass | mean turnover delta | mean CHE delta | all pass |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 126 | 126 | 0.30 | 3 | 0 | -0.881545 | -0.037649 | False |
| 126 | 126 | 0.10 | 3 | 0 | -0.943472 | -0.037649 | False |
| 126 | 126 | 0.20 | 3 | 0 | -0.971736 | -0.037649 | False |
| 126 | 252 | 0.20 | 3 | 0 | -0.009779 | -0.041046 | False |
| 126 | 252 | 0.10 | 3 | 0 | -0.019559 | -0.041046 | False |
| 126 | 252 | 0.30 | 3 | 0 | -0.548996 | -0.041046 | False |
| 126 | 63 | 0.20 | 3 | 0 | -0.727326 | -0.041058 | False |
| 126 | 63 | 0.10 | 3 | 0 | -0.786921 | -0.041058 | False |
| 126 | 63 | 0.30 | 3 | 0 | -1.195026 | -0.041058 | False |
| 252 | 63 | 0.10 | 3 | 0 | -0.593723 | -0.080852 | False |

## Blockers

- `daily_close_proxy_not_high_frequency_realized_covariance`
- `letf_readiness_blocks_00632r_open`
- `live_hedge_policy_not_validated_for_robust_ratio`
- `no_parameter_set_passed_all_temporal_windows`
- `research_only_temporal_oos`
- `transaction_cost_and_execution_slippage_not_revalidated`

