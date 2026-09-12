# GroupA+ TSI Compounding Ensemble Cost Sensitivity

- status: `research_only`
- production_effect: `none`
- cost_sensitivity_passed: `False`
- promotion_allowed: `False`

## Summary

| cost_bps | best_threshold | best_cap | best_delta_final_value | best_delta_sharpe | best_delta_max_drawdown | positive_windows | non_worse_mdd_windows | temporal_oos_passed |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 0.75 | 0.00 | 3,584 | 0.0300 | 0.00% | 2 | 8 | False |
| 5.0 | 0.75 | 0.00 | 3,654 | 0.0304 | 0.00% | 2 | 6 | False |
| 10.0 | 0.75 | 0.00 | 3,723 | 0.0307 | 0.00% | 2 | 6 | False |

## Blocking Reasons

```json
[
  "research_only_no_live_weight_change",
  "cost_sensitivity_not_promoted",
  "temporal_oos_not_passed_under_all_costs"
]
```

## Governance

This cost sensitivity is research-only. It does not change Golden1_0531,
target weights, execution regimes, or live 00631L permission.
