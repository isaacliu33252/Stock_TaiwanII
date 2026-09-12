# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:55:29`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2024-01-02', 'end': '2026-08-13', 'rows': 633}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -108065.64 | 0.0243 | 0.0165 | 3852081.50 | 3960147.14 | 4 | False |
| monthly | 0.20 | -223828.04 | 0.0526 | 0.0267 | 3736319.10 | 3960147.14 | 4 | False |
| monthly | 0.35 | -410088.57 | 0.1049 | 0.0276 | 3550058.57 | 3960147.14 | 4 | False |
| quarterly | 0.10 | -131197.58 | 0.0177 | 0.0182 | 4010115.06 | 4141312.64 | 4 | False |
| quarterly | 0.20 | -266102.40 | 0.0376 | 0.0307 | 3875210.24 | 4141312.64 | 4 | False |
| quarterly | 0.35 | -455807.80 | 0.0755 | 0.0357 | 3685504.84 | 4141312.64 | 4 | False |
| semiannual | 0.10 | -168361.01 | 0.0295 | 0.0054 | 4343518.94 | 4511879.95 | 4 | False |
| semiannual | 0.20 | -345127.84 | 0.0642 | 0.0104 | 4166752.11 | 4511879.95 | 4 | False |
| semiannual | 0.35 | -616964.29 | 0.1240 | 0.0180 | 3894915.66 | 4511879.95 | 4 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
