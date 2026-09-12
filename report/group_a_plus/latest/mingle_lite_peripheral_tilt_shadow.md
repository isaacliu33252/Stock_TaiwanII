# GroupA+ MINGLE-lite Peripheral Tilt Shadow

- status: `research_only`
- paper: `2608.06618`
- production_effect: `none`
- promotion_allowed: `False`
- allow_00632r_open: `False`

## Summary

| tilt_fraction | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum | positive_windows | non_worse_mdd_windows |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 0 | 0.0000 | 0.00% | 0 | 8 |
| 0.05 | -147,617 | 0.2265 | 3.35% | 2 | 6 |
| 0.10 | -149,741 | 0.2079 | 3.29% | 2 | 6 |
| 0.20 | -153,965 | 0.1689 | 3.17% | 2 | 6 |

## Best By Final Value

```json
{
  "tilt_fraction": 0.0,
  "delta_final_value_sum": 0.0,
  "delta_sharpe_sum": 0.0,
  "delta_max_drawdown_sum": 0.0,
  "positive_final_value_windows": 0,
  "non_worse_drawdown_windows": 8
}
```

## Blocking Reasons

```json
[
  "research_only_no_live_weight_change",
  "mingle_lite_peripheral_tilt_not_promoted",
  "best_tilt_not_positive_in_all_windows",
  "best_tilt_does_not_improve_total_final_value"
]
```

## Governance

This is a shadow-only peripheral tilt. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L/00632R permissions.
