# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:55:29`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2020-01-02', 'end': '2026-08-13', 'rows': 1606}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -887662.99 | -0.0330 | 0.0114 | 3789295.29 | 4676958.28 | 0 | False |
| monthly | 0.20 | -1014042.70 | -0.0172 | 0.0227 | 3662915.57 | 4676958.28 | 0 | False |
| monthly | 0.35 | -1186733.49 | 0.0145 | 0.0278 | 3490224.79 | 4676958.28 | 0 | False |
| quarterly | 0.10 | -1303618.27 | -0.0577 | 0.0035 | 3880179.26 | 5183797.53 | 0 | False |
| quarterly | 0.20 | -1479881.19 | -0.0499 | 0.0069 | 3703916.34 | 5183797.53 | 0 | False |
| quarterly | 0.35 | -1684275.06 | -0.0308 | 0.0045 | 3499522.47 | 5183797.53 | 0 | False |
| semiannual | 0.10 | -1454502.60 | -0.0529 | -0.0011 | 4080430.95 | 5534933.55 | 0 | False |
| semiannual | 0.20 | -1717479.74 | -0.0411 | -0.0024 | 3817453.81 | 5534933.55 | 0 | False |
| semiannual | 0.35 | -2036895.97 | -0.0165 | -0.0116 | 3498037.58 | 5534933.55 | 0 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
