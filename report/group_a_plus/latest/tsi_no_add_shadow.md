# GroupA+ TSI No-Add Shadow

- status: `research_only`
- policy: `slow_or_block_incremental_00631l_add_only_when_tsi_stress_alert_active`
- threshold: `0.9`
- alert_mode: `tsi_only`
- guard_add_fraction: `0.0`
- production_effect: `none`
- promotion_allowed: `False`
- target_weight_change_allowed: `False`

## Detector Coverage

- TSI active days: `25`
- TSI days active while no blocking guard active: `14`
- TSI days active while no existing alert/blocking active: `0`
- overlap window: `2025-01-02` to `2026-07-02`

## No-Add Counterfactual

| window | kind | tsi_alert_days | blocked_days | delta_final_value | delta_sharpe | delta_max_drawdown |
|---|---|---:|---:|---:|---:|---:|
| live_2024_2026 | tuning_window | 106 | 53 | -40,200 | -0.0206 | -0.00% |
| active_2025_2026 | tuning_window | 32 | 4 | -6,335 | -0.0013 | 0.00% |
| taiwan_2026_q1q2_stress | stress_window | 0 | 0 | 0 | 0.0000 | 0.00% |
| taiwan_2026_recent | recent_window | 10 | 6 | -3,064 | -0.0208 | 0.03% |

## Totals

```json
{
  "tsi_alert_days": 148,
  "blocked_days": 63,
  "event_days": 63,
  "delta_final_value_sum": -49598.98973896587,
  "delta_sharpe_sum": -0.04270177561603372,
  "delta_max_drawdown_sum": 0.000300491617517884,
  "positive_final_value_windows": 0,
  "non_worse_drawdown_windows": 3
}
```

## Governance

TSI remains shadow-only. It does not output target weights, execution regimes,
orders, or live permission to add 00631L. Golden1_0531 remains unchanged.
