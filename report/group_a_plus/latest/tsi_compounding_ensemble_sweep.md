# GroupA+ TSI Compounding Ensemble Sweep

- status: `research_only`
- production_effect: `none`
- promotion_allowed: `False`

## Summary

| threshold | trend_cap | tsi_alert_days | trend_alert_days | delta_final_value_vs_compounding | delta_sharpe | delta_max_drawdown | positive_windows | non_worse_mdd_windows |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.75 | 0.00 | 463 | 58 | 3,584 | 0.0300 | 0.00% | 2 | 8 |
| 0.75 | 0.25 | 463 | 58 | 3,100 | 0.0254 | 0.00% | 2 | 8 |
| 0.75 | 0.50 | 463 | 58 | 2,619 | 0.0205 | 0.00% | 2 | 7 |
| 0.75 | 0.75 | 463 | 58 | 2,123 | 0.0155 | 0.00% | 2 | 7 |
| 0.80 | 0.00 | 376 | 47 | 2,809 | 0.0278 | 0.00% | 2 | 8 |
| 0.80 | 0.25 | 376 | 47 | 2,555 | 0.0238 | 0.00% | 2 | 8 |
| 0.80 | 0.50 | 376 | 47 | 2,280 | 0.0196 | 0.00% | 2 | 7 |
| 0.80 | 0.75 | 376 | 47 | 1,966 | 0.0151 | 0.00% | 2 | 7 |
| 0.85 | 0.00 | 258 | 41 | 2,821 | 0.0279 | 0.00% | 2 | 7 |
| 0.85 | 0.25 | 258 | 41 | 2,562 | 0.0238 | 0.00% | 2 | 8 |
| 0.85 | 0.50 | 258 | 41 | 2,284 | 0.0196 | 0.00% | 2 | 8 |
| 0.85 | 0.75 | 258 | 41 | 1,967 | 0.0151 | 0.00% | 2 | 7 |
| 0.90 | 0.00 | 171 | 26 | 2,798 | 0.0276 | 0.00% | 2 | 8 |
| 0.90 | 0.25 | 171 | 26 | 2,544 | 0.0236 | -0.00% | 2 | 7 |
| 0.90 | 0.50 | 171 | 26 | 2,272 | 0.0195 | 0.00% | 2 | 8 |
| 0.90 | 0.75 | 171 | 26 | 1,961 | 0.0150 | 0.00% | 2 | 8 |
| 0.95 | 0.00 | 109 | 20 | -105 | -0.0005 | 0.00% | 0 | 8 |
| 0.95 | 0.25 | 109 | 20 | -59 | -0.0003 | -0.00% | 0 | 7 |
| 0.95 | 0.50 | 109 | 20 | -32 | -0.0001 | 0.00% | 0 | 8 |
| 0.95 | 0.75 | 109 | 20 | -13 | -0.0001 | 0.00% | 0 | 8 |

## Best By Final Value

```json
{
  "threshold": 0.75,
  "tsi_trend_cap": 0.0,
  "tsi_alert_days": 463,
  "trend_persistent_tsi_alert_days": 58,
  "ensemble_minus_compounding_final_value_sum": 3584.048424748704,
  "ensemble_minus_compounding_sharpe_sum": 0.030047236801148736,
  "ensemble_minus_compounding_max_drawdown_sum": 1.56989917128314e-05,
  "ensemble_positive_vs_compounding_windows": 2,
  "ensemble_non_worse_drawdown_vs_compounding_windows": 8
}
```

## Best By Drawdown

```json
{
  "threshold": 0.75,
  "tsi_trend_cap": 0.0,
  "tsi_alert_days": 463,
  "trend_persistent_tsi_alert_days": 58,
  "ensemble_minus_compounding_final_value_sum": 3584.048424748704,
  "ensemble_minus_compounding_sharpe_sum": 0.030047236801148736,
  "ensemble_minus_compounding_max_drawdown_sum": 1.56989917128314e-05,
  "ensemble_positive_vs_compounding_windows": 2,
  "ensemble_non_worse_drawdown_vs_compounding_windows": 8
}
```

## Best By Window Coverage

```json
{
  "threshold": 0.75,
  "tsi_trend_cap": 0.0,
  "tsi_alert_days": 463,
  "trend_persistent_tsi_alert_days": 58,
  "ensemble_minus_compounding_final_value_sum": 3584.048424748704,
  "ensemble_minus_compounding_sharpe_sum": 0.030047236801148736,
  "ensemble_minus_compounding_max_drawdown_sum": 1.56989917128314e-05,
  "ensemble_positive_vs_compounding_windows": 2,
  "ensemble_non_worse_drawdown_vs_compounding_windows": 8
}
```

## Governance

This is a sweep-only shadow. It does not change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
