# NCF TSM-ADR Dynamic Lag Walk-Forward Comparison

- Status: `diagnostic_available`
- Horizon: `5`d, windows: `6`

| variant | model | avg AUC | avg accuracy | windows |
|---|---|---:|---:|---:|
| baseline_fixed_lag1 | rf | 0.5393 | 0.4985 | 6 |
| baseline_fixed_lag1 | et | 0.5426 | 0.5038 | 6 |
| baseline_fixed_lag1 | hgb | 0.5524 | 0.5122 | 6 |
| baseline_fixed_lag1 | gb | 0.5475 | 0.5198 | 6 |
| baseline_fixed_lag1 | ensemble | 0.5966 | 0.5586 | 6 |
| dynamic_lag | rf | 0.5449 | 0.5167 | 6 |
| dynamic_lag | et | 0.5443 | 0.5137 | 6 |
| dynamic_lag | hgb | 0.5529 | 0.5251 | 6 |
| dynamic_lag | gb | 0.5524 | 0.5228 | 6 |
| dynamic_lag | ensemble | 0.5892 | 0.5487 | 6 |

## Boundary

- Research-only full-model walk-forward comparison.
- Does not modify scripts/misc/ncf_0050.py or retrain the production NCF model artifact.
- Does not change target weights, orders, or the daily pipeline.
