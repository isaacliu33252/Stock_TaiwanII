# 2604.02126 Robust Hedge Parameter Sweep

Generated: `2026-08-29T23:01:05`
As of: `2026-08-28`
Status: `blocked_for_live_promotion`

## Decision

- Do not change live target weights.
- Do not open or increase `00632R.TW`.
- Keep `Golden1_0531` unchanged.
- Keep robust hedge ratio as shadow/cap diagnostics only.

## Sweep Summary

- parameter count: `27`
- eligible parameter count: `0`

## Top Rows

| window | uncertainty | cap | score | robust latest | turnover delta | std delta | robust CHE | standard CHE | pass |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 252 | 126 | 0.10 | 14.537675 | 0.100000 | -0.912342 | -0.098377 | 0.237638 | 0.309686 | False |
| 252 | 252 | 0.10 | 14.179032 | 0.043243 | -0.731724 | -0.156762 | 0.220026 | 0.309686 | False |
| 252 | 126 | 0.20 | 14.152625 | 0.200000 | -1.270058 | -0.125712 | 0.237638 | 0.309686 | False |
| 252 | 252 | 0.20 | 14.115251 | 0.043243 | -0.763219 | -0.189049 | 0.220026 | 0.309686 | False |
| 252 | 252 | 0.30 | 14.107030 | 0.043243 | -0.786000 | -0.174488 | 0.220026 | 0.309686 | False |
| 252 | 126 | 0.30 | 13.820670 | 0.232102 | -1.617791 | -0.109934 | 0.237638 | 0.309686 | False |
| 252 | 63 | 0.10 | 13.144096 | 0.100000 | -0.727592 | -0.048137 | 0.256869 | 0.309686 | False |
| 126 | 126 | 0.10 | 12.736195 | 0.100000 | -1.123133 | -0.253077 | 0.363117 | 0.370706 | False |
| 126 | 126 | 0.20 | 12.641587 | 0.200000 | -1.154010 | -0.316808 | 0.363117 | 0.370706 | False |
| 126 | 252 | 0.10 | 12.511354 | 0.100000 | -0.227262 | -0.553270 | 0.330893 | 0.370706 | False |

## Blockers

- `daily_close_proxy_not_high_frequency_realized_covariance`
- `letf_readiness_blocks_00632r_open`
- `live_hedge_policy_not_validated_for_robust_ratio`
- `no_parameter_set_passed_shadow_stability_filter`
- `research_only_parameter_sweep`
- `transaction_cost_and_execution_slippage_not_revalidated`

