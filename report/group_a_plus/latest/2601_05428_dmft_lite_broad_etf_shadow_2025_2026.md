# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:02`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2025-01-02', 'end': '2026-08-13', 'rows': 391}`
- Tickers: `0050.TW, 0056.TW, 00631L.TW, 00632R.TW, 00646.TW, 00679B.TWO, 00713.TW, 00751B.TWO, 00878.TW`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | 6025.77 | 0.0316 | 0.0091 | 1333904.21 | 1327878.44 | 9 | True |
| monthly | 0.20 | 11739.75 | 0.0546 | 0.0170 | 1339618.18 | 1327878.44 | 9 | True |
| monthly | 0.35 | 733.39 | 0.0266 | 0.0180 | 1328611.83 | 1327878.44 | 9 | True |
| quarterly | 0.10 | -4309.79 | 0.0098 | 0.0104 | 1349544.97 | 1353854.76 | 9 | False |
| quarterly | 0.20 | -8183.11 | 0.0138 | 0.0195 | 1345671.65 | 1353854.76 | 9 | False |
| quarterly | 0.35 | -20333.55 | -0.0075 | 0.0225 | 1333521.21 | 1353854.76 | 9 | False |
| semiannual | 0.10 | 2486.80 | -0.0004 | 0.0037 | 1394576.41 | 1392089.62 | 9 | False |
| semiannual | 0.20 | 3736.22 | -0.0040 | 0.0075 | 1395825.83 | 1392089.62 | 9 | False |
| semiannual | 0.35 | -2162.92 | -0.0015 | 0.0131 | 1389926.69 | 1392089.62 | 9 | False |

## Decision

- Promotion ready: `True`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
