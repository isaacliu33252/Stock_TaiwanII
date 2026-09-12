# GroupA+ TSI Compounding Ensemble Temporal OOS

- status: `research_only`
- production_effect: `none`
- temporal_oos_passed: `False`
- promotion_allowed: `False`

## Folds

| fold | selected_threshold | selected_cap | holdout_delta_final_value | holdout_delta_sharpe | holdout_delta_max_drawdown | positive_windows | non_worse_mdd_windows | passed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| train_2020_2023__holdout_2024_2026 | 0.90 | 0.00 | 2,798 | 0.0276 | 0.00% | 2/4 | 4/4 | False |
| train_2020_2024__holdout_2025_2026 | 0.90 | 0.75 | 1,974 | 0.0151 | 0.00% | 2/3 | 3/3 | False |

## Blocking Reasons

```json
[
  "research_only_no_live_weight_change",
  "temporal_oos_fold_failed:train_2020_2023__holdout_2024_2026",
  "temporal_oos_fold_failed:train_2020_2024__holdout_2025_2026"
]
```

## Governance

This validation is research-only. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L permission.
