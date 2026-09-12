# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:55:58`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2025-01-02', 'end': '2026-08-13', 'rows': 391}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | 15108.02 | 0.0448 | 0.0176 | 1429784.19 | 1414676.17 | 4 | True |
| monthly | 0.20 | 29901.92 | 0.0653 | 0.0290 | 1444578.09 | 1414676.17 | 4 | True |
| monthly | 0.35 | 52709.73 | 0.0633 | 0.0309 | 1467385.90 | 1414676.17 | 4 | True |
| quarterly | 0.10 | -3558.87 | 0.0088 | 0.0182 | 1466850.02 | 1470408.90 | 4 | False |
| quarterly | 0.20 | -7461.21 | 0.0022 | 0.0307 | 1462947.68 | 1470408.90 | 4 | False |
| quarterly | 0.35 | -6375.82 | -0.0200 | 0.0358 | 1464033.07 | 1470408.90 | 4 | False |
| semiannual | 0.10 | 8197.58 | -0.0018 | 0.0054 | 1562275.82 | 1554078.24 | 4 | False |
| semiannual | 0.20 | 15972.65 | -0.0081 | 0.0104 | 1570050.90 | 1554078.24 | 4 | False |
| semiannual | 0.35 | 21260.61 | -0.0235 | 0.0180 | 1575338.85 | 1554078.24 | 4 | False |

## Decision

- Promotion ready: `True`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
