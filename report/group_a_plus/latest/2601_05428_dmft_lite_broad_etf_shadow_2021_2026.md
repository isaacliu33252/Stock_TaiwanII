# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:02`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2021-01-04', 'end': '2026-08-13', 'rows': 1361}`
- Tickers: `0050.TW, 0056.TW, 00631L.TW, 00632R.TW, 00646.TW, 00679B.TWO, 00713.TW, 00751B.TWO, 00878.TW`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -342006.77 | -0.0245 | 0.0052 | 2334486.11 | 2676492.89 | 0 | False |
| monthly | 0.20 | -456996.90 | 0.0087 | 0.0075 | 2219495.99 | 2676492.89 | 0 | False |
| monthly | 0.35 | -527806.39 | 0.0156 | 0.0080 | 2148686.49 | 2676492.89 | 0 | False |
| quarterly | 0.10 | -305863.76 | -0.0115 | 0.0011 | 2450640.24 | 2756503.99 | 0 | False |
| quarterly | 0.20 | -436086.75 | 0.0193 | 0.0004 | 2320417.25 | 2756503.99 | 0 | False |
| quarterly | 0.35 | -521139.74 | 0.0285 | -0.0040 | 2235364.25 | 2756503.99 | 0 | False |
| semiannual | 0.10 | -481292.36 | -0.0315 | 0.0005 | 2415677.98 | 2896970.34 | 0 | False |
| semiannual | 0.20 | -631552.36 | 0.0002 | -0.0011 | 2265417.98 | 2896970.34 | 0 | False |
| semiannual | 0.35 | -661472.29 | 0.0023 | -0.0043 | 2235498.05 | 2896970.34 | 0 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
