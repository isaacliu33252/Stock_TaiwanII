# GroupA+ BAWS-lite VaR/ES Shadow

- Generated: `2026-08-13T23:22:15`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`
- Average BAWS minus best fixed score: `3.646363478175763e-05`

## Ticker Results

| Ticker | Best fixed | BAWS-best score delta | BAWS breach rate | Selected windows |
|---|---:|---:|---:|---|
| 0050.TW | fixed_504 | 0.00000000 | 0.063939 | {"504": 391} |
| 00631L.TW | fixed_252 | 0.00000083 | 0.081841 | {"504": 391} |
| 00632R.TW | fixed_63 | 0.00014068 | 0.107417 | {"504": 391} |
| 00679B.TWO | fixed_252 | 0.00000433 | 0.035806 | {"252": 1, "504": 390} |

## Latest Snapshot

| Ticker | Date | Window | VaR loss | ES loss | Latest realized loss | Breach |
|---|---:|---:|---:|---:|---:|---:|
| 00631L.TW | 2026-08-13 | 504 | 0.04740771 | 0.08475859 | -0.02369535 | False |
| 0050.TW | 2026-08-13 | 504 | 0.02313337 | 0.04022806 | -0.01425856 | False |
| 00632R.TW | 2026-08-13 | 504 | 0.02771580 | 0.04105309 | 0.01093445 | False |
| 00679B.TWO | 2026-08-13 | 504 | 0.01220124 | 0.02079279 | 0.00151569 | False |

Codex 2026-08-13: research-only output; no active strategy, golden1_0531 artifact, live signal, execution plan, or order file is changed.
