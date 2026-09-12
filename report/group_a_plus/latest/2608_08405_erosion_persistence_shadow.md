# 2608.08405 Erosion Persistence Shadow

- status: proxy_available_not_calibrated_kernel
- as_of: 2026-09-09
- policy: research_only_erosion_persistence_proxy_no_weight_change
- proxy_available_count: 4
- median_ar1_persistence_proxy: 0.24069437323306775
- median_half_life_days_proxy: 0.48668297197722094
- steady_state_kernel_calibrated_to_group_a_plus: False
- capacity_deattenuation_allowed: False

## Blocking Reasons
- randomized_deployment_erosion_kernel_missing
- proxy_not_causal_capacity_evidence
- same_run_realized_deployment_not_used

## Ticker Estimates
- 0050.TW: status=proxy_available_not_causal_kernel, ar1=0.2398058927466925, half_life_days=0.48542252272358594
- 00631L.TW: status=proxy_available_not_causal_kernel, ar1=0.24158285371944302, half_life_days=0.48794530359010974
- 00632R.TW: status=proxy_available_not_causal_kernel, ar1=0.005818212088516967, half_life_days=0.13467635472043873
- 00679B.TWO: status=proxy_available_not_causal_kernel, ar1=0.26724524625130447, half_life_days=0.5252752442841714

## Decision
OHLCV persistence proxies are available for monitoring, but they are not the causal deployment-erosion kernel required by the paper. Do not deattenuate capacity or scale capital from this proxy.
