# NCF Institutional-Flow Z-Score Walk-Forward Comparison

- Status: `diagnostic_available`
- Horizon: `5`d, windows: `6`

| variant | model | avg AUC | avg accuracy | windows |
|---|---|---:|---:|---:|
| baseline_price_scaled | rf | 0.5828 | 0.5278 | 6 |
| baseline_price_scaled | et | 0.5965 | 0.5003 | 6 |
| baseline_price_scaled | hgb | 0.5244 | 0.5296 | 6 |
| baseline_price_scaled | gb | 0.5575 | 0.5393 | 6 |
| baseline_price_scaled | ensemble | 0.6430 | 0.6185 | 6 |
| expanding_zscore | rf | 0.5890 | 0.5219 | 6 |
| expanding_zscore | et | 0.5982 | 0.5051 | 6 |
| expanding_zscore | hgb | 0.5305 | 0.5537 | 6 |
| expanding_zscore | gb | 0.5777 | 0.5667 | 6 |
| expanding_zscore | ensemble | 0.6404 | 0.6173 | 6 |

## Boundary

- Research-only full-model walk-forward comparison.
- Does not modify scripts/misc/ncf_0050.py or retrain the production NCF model artifact.
- Does not change target weights, orders, or the daily pipeline.
