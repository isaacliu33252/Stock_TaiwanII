# GroupA+ TSI No-Add Sweep

- status: `research_only`
- production_effect: `none`
- promotion_allowed: `False`
- best_by_final_value: `tsi_only` @ `0.8`, add_fraction `0.5`
- best_by_drawdown: `tsi_only` @ `0.75`, add_fraction `0.0`

| threshold | alert_mode | add_fraction | tsi_alert_days | event_days | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.75 | tsi_only | 0.00 | 463 | 177 | -11,610 | -0.0400 | 0.10% |
| 0.80 | tsi_only | 0.00 | 376 | 140 | -13,837 | -0.0435 | 0.09% |
| 0.75 | tsi_only | 0.25 | 463 | 156 | -1,602 | 0.0049 | -0.00% |
| 0.80 | tsi_only | 0.25 | 376 | 121 | -1,102 | 0.0106 | 0.02% |
| 0.75 | tsi_only | 0.50 | 463 | 132 | 2,375 | 0.0249 | -0.00% |
| 0.80 | tsi_only | 0.50 | 376 | 104 | 2,737 | 0.0292 | 0.01% |

## Governance

All variants remain shadow-only. None may change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
