# GroupA+ TSI Stress Shadow

- date: `2026-09-09`
- status: `available`
- policy: `shadow_only_no_weight_change`
- production_effect: `none`
- recommended_use: `monitor_only`
- alarm_active: `False`
- scope: Coincident correlation-network stress index; not a directional forecast.

## Latest

- tsi: `0.2178403273997756`
- tsi_memory: `0.29204630895318545`
- tsi_percentile: `0.5985620131815458`
- tsi_memory_percentile: `0.5446375074895147`
- tsi_memory_zscore: `-0.2570123349435294`
- effective_rank: `6.353024942270866`
- n_assets: `18`
- observations: `20`

## Top Attribution

| ticker | triangle_share | degree_share | degree |
|---|---:|---:|---:|
| 00632R.TW | 11.49% | 8.12% | 8.8069 |
| 00631L.TW | 11.40% | 8.04% | 8.7203 |
| ^TWII | 11.31% | 7.99% | 8.6686 |
| 0050.TW | 11.22% | 7.97% | 8.6505 |
| 2330.TW | 8.11% | 6.44% | 6.9869 |
| 2308.TW | 6.98% | 6.21% | 6.7346 |
| 2317.TW | 5.91% | 5.80% | 6.2915 |
| 2454.TW | 5.65% | 5.56% | 6.0315 |

## Governance

This report is research-only. It does not output target weights, target shares,
execution regime, or orders. The source paper frames TSI as a coincident state
index, not a forecast; any live use must pass out-of-sample GroupA+ validation
and promotion governance first.
