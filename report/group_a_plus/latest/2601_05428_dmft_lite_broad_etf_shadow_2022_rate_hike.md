# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:00`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2022-01-03', 'end': '2022-12-30', 'rows': 246}`
- Tickers: `0050.TW, 0056.TW, 00631L.TW, 00632R.TW, 00646.TW, 00679B.TWO, 00713.TW, 00751B.TWO, 00878.TW`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -2334.91 | -0.1143 | 0.0051 | 829323.82 | 831658.73 | 9 | False |
| monthly | 0.20 | -4872.89 | -0.2058 | 0.0073 | 826785.84 | 831658.73 | 9 | False |
| monthly | 0.35 | -5952.78 | -0.2239 | 0.0079 | 825705.95 | 831658.73 | 9 | False |
| quarterly | 0.10 | -5305.85 | -0.1305 | 0.0011 | 820804.08 | 826109.93 | 9 | False |
| quarterly | 0.20 | -9705.07 | -0.2215 | 0.0003 | 816404.86 | 826109.93 | 9 | False |
| quarterly | 0.35 | -15637.08 | -0.2623 | -0.0041 | 810472.86 | 826109.93 | 9 | False |
| semiannual | 0.10 | -5466.69 | -0.1210 | -0.0006 | 821238.20 | 826704.89 | 9 | False |
| semiannual | 0.20 | -10823.54 | -0.2224 | -0.0021 | 815881.35 | 826704.89 | 9 | False |
| semiannual | 0.35 | -14720.28 | -0.2434 | -0.0053 | 811984.60 | 826704.89 | 9 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
