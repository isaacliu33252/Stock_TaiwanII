# 2609.08106 Cross-Asset Complementarity Shadow

- generated_at: `2026-09-12T07:27:23`
- as_of: `2026-09-09`
- actual_data_end: `2026-09-09`
- policy: `shadow_only_no_orders_no_weight_change`
- shadow_available: `True`

| ticker | close | corr0050 | corr00631L | ann_vol | mom5 | mom20 | score |
|---|---:|---:|---:|---:|---:|---:|---:|
| 00679B.TWO | 25.5800 | 0.0191 | 0.0289 | 0.1112 | -0.0027 | -0.0307 | 0.9909 |
| 00751B.TWO | 30.0600 | 0.1783 | 0.1889 | 0.0870 | -0.0050 | -0.0221 | 0.6929 |
| 00713.TW | 63.6500 | 0.6538 | 0.6689 | 0.0868 | 0.0135 | 0.0400 | -0.1306 |
| 00878.TW | 34.1300 | 0.8820 | 0.8661 | 0.2556 | 0.0143 | 0.0182 | -0.6992 |
| 00631L.TW | 37.5400 | 0.9892 | 1.0000 | 0.7491 | 0.0448 | 0.0590 | -1.1106 |
| 00632R.TW | 9.7000 | -0.9856 | -0.9965 | 0.3787 | -0.0212 | -0.0358 | -1.1683 |

## Decision

- sleeve_reference: `defensive_complement_available`
- No live weight change. No order generation.
- Do not add graph/top-K sparse masks from this paper.
- Next step: Backtest this complementarity score as a no-add/resize diagnostic before any live integration.
