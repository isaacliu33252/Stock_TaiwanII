# NCF Institutional-Flow Z-Score Walk-Forward Comparison

- Status: `diagnostic_available`
- Horizon: `5`d, windows: `6`

| variant | model | avg AUC | avg accuracy | windows |
|---|---|---:|---:|---:|
| baseline_price_scaled | rf | 0.5393 | 0.4985 | 6 |
| baseline_price_scaled | et | 0.5426 | 0.5038 | 6 |
| baseline_price_scaled | hgb | 0.5524 | 0.5122 | 6 |
| baseline_price_scaled | gb | 0.5475 | 0.5198 | 6 |
| baseline_price_scaled | ensemble | 0.5966 | 0.5586 | 6 |
| expanding_zscore | rf | 0.5474 | 0.5198 | 6 |
| expanding_zscore | et | 0.5486 | 0.5152 | 6 |
| expanding_zscore | hgb | 0.5420 | 0.5107 | 6 |
| expanding_zscore | gb | 0.5523 | 0.5236 | 6 |
| expanding_zscore | ensemble | 0.5975 | 0.5540 | 6 |

## Boundary

- Research-only full-model walk-forward comparison.
- Does not modify scripts/misc/ncf_0050.py or retrain the production NCF model artifact.
- Does not change target weights, orders, or the daily pipeline.
