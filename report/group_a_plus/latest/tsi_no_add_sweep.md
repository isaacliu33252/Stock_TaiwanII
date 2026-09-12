# GroupA+ TSI No-Add Sweep

- status: `research_only`
- production_effect: `none`
- promotion_allowed: `False`
- best_by_final_value: `tsi_and_existing_any` @ `0.8`
- best_by_drawdown: `tsi_only` @ `0.8`

| threshold | alert_mode | tsi_alert_days | blocked_days | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum |
|---:|---|---:|---:|---:|---:|---:|
| 0.80 | tsi_only | 310 | 167 | -12,092 | 0.0223 | 0.10% |
| 0.85 | tsi_only | 224 | 108 | -19,658 | -0.0771 | 0.03% |
| 0.90 | tsi_only | 148 | 63 | -12,485 | 0.0100 | 0.02% |
| 0.95 | tsi_only | 80 | 30 | -4,230 | -0.0029 | 0.00% |
| 0.80 | tsi_and_existing_any | 93 | 12 | 1,437 | 0.0149 | 0.04% |
| 0.85 | tsi_and_existing_any | 70 | 2 | -38 | -0.0003 | 0.00% |
| 0.90 | tsi_and_existing_any | 53 | 0 | 0 | 0.0000 | 0.00% |
| 0.95 | tsi_and_existing_any | 42 | 0 | 0 | 0.0000 | 0.00% |

## Governance

All variants remain shadow-only. None may change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
