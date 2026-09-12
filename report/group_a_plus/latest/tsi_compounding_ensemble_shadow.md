# GroupA+ TSI Compounding Ensemble Shadow

- status: `research_only`
- policy: `compounding_staged_with_tsi_trend_persistent_add_cap_shadow`
- tsi_threshold: `0.8`
- tsi_trend_cap: `0.5`
- promotion_allowed: `False`

## Ensemble Vs Compounding Staged

| window | tsi_alert_days | trend_persistent_tsi_alert_days | delta_final_value | delta_sharpe | delta_max_drawdown |
|---|---:|---:|---:|---:|---:|
| covid_2020 | 55 | 7 | 0 | 0.0000 | 0.00% |
| recovery_2021 | 22 | 1 | 0 | 0.0000 | 0.00% |
| rate_hike_2022 | 70 | 11 | 0 | 0.0000 | 0.00% |
| rebound_2023 | 18 | 12 | -7 | -0.0001 | -0.00% |
| full_2024 | 79 | 10 | -40 | -0.0002 | 0.00% |
| active_2025_2026 | 78 | 4 | 1,442 | 0.0049 | 0.00% |
| taiwan_2026_q1q2_stress | 21 | 0 | 0 | 0.0000 | 0.00% |
| taiwan_2026_recent | 33 | 2 | 885 | 0.0149 | 0.00% |

## Totals

```json
{
  "tsi_alert_days": 376,
  "trend_persistent_tsi_alert_days": 47,
  "compounding_delta_final_value_sum": 1300.8447941986378,
  "ensemble_delta_final_value_sum": 3581.2126280390657,
  "ensemble_minus_compounding_final_value_sum": 2280.367833840428,
  "ensemble_minus_compounding_sharpe_sum": 0.01955884984725087,
  "ensemble_minus_compounding_max_drawdown_sum": 7.849495856526723e-06,
  "ensemble_positive_vs_compounding_windows": 2,
  "ensemble_non_worse_drawdown_vs_compounding_windows": 7
}
```

## Governance

This is an ensemble shadow only. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L permission.
