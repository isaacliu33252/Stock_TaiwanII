# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:02`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2024-01-02', 'end': '2026-08-13', 'rows': 633}`
- Tickers: `0050.TW, 0056.TW, 00631L.TW, 00632R.TW, 00646.TW, 00679B.TWO, 00713.TW, 00751B.TWO, 00878.TW`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -100002.49 | 0.0488 | 0.0091 | 2301784.64 | 2401787.14 | 9 | False |
| monthly | 0.20 | -203753.08 | 0.1087 | 0.0170 | 2198034.05 | 2401787.14 | 9 | False |
| monthly | 0.35 | -268763.13 | 0.1254 | 0.0182 | 2133024.01 | 2401787.14 | 9 | False |
| quarterly | 0.10 | -115977.59 | 0.0423 | 0.0104 | 2353136.46 | 2469114.04 | 9 | False |
| quarterly | 0.20 | -232105.13 | 0.0942 | 0.0193 | 2237008.92 | 2469114.04 | 9 | False |
| quarterly | 0.35 | -304802.71 | 0.1157 | 0.0209 | 2164311.34 | 2469114.04 | 9 | False |
| semiannual | 0.10 | -151117.07 | 0.0635 | 0.0037 | 2427907.09 | 2579024.16 | 9 | False |
| semiannual | 0.20 | -279803.84 | 0.1314 | 0.0069 | 2299220.32 | 2579024.16 | 9 | False |
| semiannual | 0.35 | -297464.14 | 0.1439 | 0.0119 | 2281560.02 | 2579024.16 | 9 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
