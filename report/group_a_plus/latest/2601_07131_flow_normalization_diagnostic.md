# 2601.07131 Institutional-Flow Normalization Diagnostic (h=5)

- Status: `diagnostic_available`
- As of: `2026-08-31`

| variant | IC (full) | IC (pre-2024) | IC (post-2024) | AUC (full) | AUC (pre-2024) | AUC (post-2024) |
|---|---:|---:|---:|---:|---:|---:|
| raw_foreign_net_buy | 0.0240 | 0.0124 | 0.0708 | 0.4847 | 0.4523 | 0.5324 |
| price_scaled_foreign_net_buy | 0.0214 | 0.0108 | 0.0659 | 0.4838 | 0.4520 | 0.5283 |
| volume_normalized_foreign_net_buy | 0.0299 | 0.0193 | 0.0844 | 0.4889 | 0.4561 | 0.5390 |
| expanding_zscore_foreign_net_buy | 0.0314 | 0.0185 | 0.0717 | 0.5115 | 0.5072 | 0.5301 |
| raw_inst_total_net_buy | 0.0098 | 0.0053 | 0.0349 | 0.4777 | 0.4455 | 0.5154 |
| price_scaled_inst_total_net_buy | 0.0090 | 0.0041 | 0.0338 | 0.4771 | 0.4452 | 0.5136 |
| volume_normalized_inst_total_net_buy | 0.0182 | 0.0150 | 0.0451 | 0.4823 | 0.4501 | 0.5206 |
| expanding_zscore_inst_total_net_buy | 0.0259 | 0.0266 | 0.0430 | 0.5108 | 0.5117 | 0.5172 |

## Boundary

- Single-feature diagnostic only (Spearman IC / rank AUC vs forward 0050.TW return).
- Does not retrain or modify the production NCF model.
- Does not change target weights, orders, or the switch policy.
