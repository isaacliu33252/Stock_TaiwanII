# GroupA+ TSI Compounding Ensemble Parameter Robustness

- status: `research_only`
- production_effect: `none`
- parameter_robustness_passed: `False`
- promotion_allowed: `False`

## Summary

| variant | window | alpha_up | alpha_down | best_threshold | best_cap | best_delta_final_value | best_delta_sharpe | best_delta_max_drawdown | positive_windows | non_worse_mdd_windows | temporal_oos_passed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| default | 20 | 0.60 | 0.08 | 0.75 | 0.00 | 3,584 | 0.0300 | 0.00% | 2 | 8 | False |
| short_window | 15 | 0.60 | 0.08 | 0.85 | 0.00 | 2,860 | 0.0282 | 0.00% | 3 | 8 | False |
| long_window | 30 | 0.60 | 0.08 | 0.85 | 0.00 | 2,690 | 0.0272 | -0.00% | 2 | 7 | False |
| fast_memory | 20 | 0.80 | 0.15 | 0.75 | 0.00 | 3,592 | 0.0302 | 0.00% | 2 | 8 | False |
| slow_memory | 20 | 0.40 | 0.04 | 0.80 | 0.00 | 2,809 | 0.0278 | 0.00% | 2 | 8 | False |

## Blocking Reasons

```json
[
  "research_only_no_live_weight_change",
  "parameter_robustness_not_promoted",
  "temporal_oos_not_passed_under_all_tsi_parameter_variants"
]
```

## Governance

This parameter robustness check is research-only. It does not change
Golden1_0531, target weights, execution regimes, or live 00631L permission.
