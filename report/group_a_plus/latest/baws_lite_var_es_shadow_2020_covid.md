# GroupA+ BAWS-lite VaR/ES Shadow

- Generated: `2026-08-13T23:38:38`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`
- Average BAWS minus best fixed score: `0.0002837931194114619`

## Ticker Results

| Ticker | Best fixed | BAWS-best score delta | BAWS breach rate | Selected windows |
|---|---:|---:|---:|---|
| 0050.TW | fixed_40 | 0.00031463 | 0.073469 | {"126": 245} |
| 00631L.TW | fixed_40 | 0.00076385 | 0.093878 | {"126": 245} |
| 00632R.TW | fixed_63 | 0.00005669 | 0.069388 | {"20": 1, "126": 244} |
| 00679B.TWO | fixed_126 | 0.00000000 | 0.048980 | {"126": 245} |

## Latest Snapshot

| Ticker | Date | Window | VaR loss | ES loss | Latest realized loss | Breach |
|---|---:|---:|---:|---:|---:|---:|
| 00631L.TW | 2020-12-31 | 126 | 0.02415460 | 0.03850042 | -0.00614871 | False |
| 0050.TW | 2020-12-31 | 126 | 0.01200249 | 0.01897930 | -0.00534541 | False |
| 00632R.TW | 2020-12-31 | 126 | 0.01704957 | 0.02125923 | 0.00854700 | False |
| 00679B.TWO | 2020-12-31 | 126 | 0.01483317 | 0.01794945 | -0.00111233 | False |

Codex 2026-08-13: research-only output; no active strategy, golden1_0531 artifact, live signal, execution plan, or order file is changed.
