# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:56:49`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2021-01-04', 'end': '2026-08-13', 'rows': 1361}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -170075.27 | 0.0110 | 0.0114 | 3789295.29 | 3959370.56 | 0 | False |
| monthly | 0.20 | -296454.99 | 0.0282 | 0.0227 | 3662915.57 | 3959370.56 | 0 | False |
| monthly | 0.35 | -469145.77 | 0.0626 | 0.0278 | 3490224.79 | 3959370.56 | 0 | False |
| quarterly | 0.10 | -277043.32 | 0.0003 | 0.0035 | 3880179.26 | 4157222.58 | 0 | False |
| quarterly | 0.20 | -453306.24 | 0.0088 | 0.0069 | 3703916.34 | 4157222.58 | 0 | False |
| quarterly | 0.35 | -657700.11 | 0.0295 | 0.0045 | 3499522.47 | 4157222.58 | 0 | False |
| semiannual | 0.10 | -520604.53 | -0.0054 | -0.0011 | 4080430.95 | 4601035.48 | 0 | False |
| semiannual | 0.20 | -783581.67 | 0.0073 | -0.0024 | 3817453.81 | 4601035.48 | 0 | False |
| semiannual | 0.35 | -1102997.90 | 0.0341 | -0.0116 | 3498037.58 | 4601035.48 | 0 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
