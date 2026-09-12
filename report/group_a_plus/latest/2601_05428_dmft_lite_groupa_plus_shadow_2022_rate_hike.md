# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T13:55:25`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2022-01-03', 'end': '2022-12-30', 'rows': 246}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | 616.46 | -0.1725 | 0.0114 | 832682.94 | 832066.47 | 4 | False |
| monthly | 0.20 | 790.48 | -0.3606 | 0.0227 | 832856.96 | 832066.47 | 4 | False |
| monthly | 0.35 | 2291.89 | -0.4157 | 0.0278 | 834358.36 | 832066.47 | 4 | False |
| quarterly | 0.10 | -5697.74 | -0.2223 | 0.0035 | 816759.21 | 822456.95 | 4 | False |
| quarterly | 0.20 | -11488.84 | -0.4528 | 0.0069 | 810968.12 | 822456.95 | 4 | False |
| quarterly | 0.35 | -17211.26 | -0.5253 | 0.0045 | 805245.69 | 822456.95 | 4 | False |
| semiannual | 0.10 | -9685.12 | -0.2532 | -0.0011 | 815267.21 | 824952.32 | 4 | False |
| semiannual | 0.20 | -19379.84 | -0.5021 | -0.0024 | 805572.49 | 824952.32 | 4 | False |
| semiannual | 0.35 | -32879.81 | -0.6358 | -0.0116 | 792072.52 | 824952.32 | 4 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
