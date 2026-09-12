# 2604.02126 Forecast Variant Review

Generated: `2026-08-29T23:07:52`
As of: `2026-08-28`
Status: `blocked_for_live_promotion`

## Decision

- Do not change live target weights.
- Do not open or increase `00632R.TW`.
- Keep `Golden1_0531` unchanged.

## Variants

| model | obs | robust latest | turnover delta | std delta | robust CHE | standard CHE | pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| rolling_mean | 1364 | 0.300000 | -1.513147 | -0.322986 | 0.363117 | 0.370706 | False |
| ar1 | 1358 | 0.300000 | -6.274324 | -0.360688 | 0.339119 | 0.373962 | False |
| har_lite | 1323 | 0.240273 | -17.005848 | -0.592123 | 0.311572 | -2122.478116 | False |

## Blockers

- `daily_close_proxy_not_high_frequency_realized_covariance`
- `letf_readiness_blocks_00632r_open`
- `live_hedge_policy_not_validated_for_robust_ratio`
- `no_forecast_variant_passed_shadow_filter`
- `research_only_forecast_variant_review`
- `transaction_cost_and_execution_slippage_not_revalidated`

