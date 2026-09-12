# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:55:56`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2020-01-02', 'end': '2020-12-31', 'rows': 245}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -167418.08 | -1.5564 | 0.1214 | 1000000.00 | 1167418.08 | 0 | False |
| monthly | 0.20 | -167418.08 | -1.5564 | 0.1214 | 1000000.00 | 1167418.08 | 0 | False |
| monthly | 0.35 | -167418.08 | -1.5564 | 0.1214 | 1000000.00 | 1167418.08 | 0 | False |
| quarterly | 0.10 | -230023.76 | -2.0077 | 0.1046 | 1000000.00 | 1230023.76 | 0 | False |
| quarterly | 0.20 | -230023.76 | -2.0077 | 0.1046 | 1000000.00 | 1230023.76 | 0 | False |
| quarterly | 0.35 | -230023.76 | -2.0077 | 0.1046 | 1000000.00 | 1230023.76 | 0 | False |
| semiannual | 0.10 | -184481.18 | -1.7406 | 0.1046 | 1000000.00 | 1184481.18 | 0 | False |
| semiannual | 0.20 | -184481.18 | -1.7406 | 0.1046 | 1000000.00 | 1184481.18 | 0 | False |
| semiannual | 0.35 | -184481.18 | -1.7406 | 0.1046 | 1000000.00 | 1184481.18 | 0 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
