# GroupA+ TSI No-Add Sweep

- status: `research_only`
- production_effect: `none`
- promotion_allowed: `False`
- best_by_final_value: `tsi_and_existing_any` @ `0.8`, add_fraction `0.0`
- best_by_drawdown: `tsi_and_existing_any` @ `0.8`, add_fraction `0.0`

| threshold | alert_mode | add_fraction | tsi_alert_days | event_days | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.75 | tsi_and_existing_any | 0.00 | 60 | 13 | 454 | 0.0050 | -0.00% |
| 0.80 | tsi_and_existing_any | 0.00 | 47 | 7 | 496 | 0.0136 | 0.04% |
| 0.75 | tsi_and_existing_any | 0.25 | 60 | 13 | 329 | 0.0037 | -0.00% |
| 0.80 | tsi_and_existing_any | 0.25 | 47 | 7 | 347 | 0.0096 | 0.03% |
| 0.75 | tsi_and_existing_any | 0.50 | 60 | 13 | 209 | 0.0024 | 0.00% |
| 0.80 | tsi_and_existing_any | 0.50 | 47 | 7 | 215 | 0.0059 | 0.02% |

## Governance

All variants remain shadow-only. None may change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
