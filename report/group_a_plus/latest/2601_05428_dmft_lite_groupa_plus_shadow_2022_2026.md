# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:34`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2022-01-03', 'end': '2026-08-13', 'rows': 1118}`
- Tickers: `0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -127060.65 | 0.0137 | 0.0114 | 3563987.48 | 3691048.13 | 4 | False |
| monthly | 0.20 | -262210.98 | 0.0294 | 0.0227 | 3428837.15 | 3691048.13 | 4 | False |
| monthly | 0.35 | -447766.95 | 0.0613 | 0.0278 | 3243281.18 | 3691048.13 | 4 | False |
| quarterly | 0.10 | -176555.07 | 0.0063 | 0.0035 | 3653028.32 | 3829583.39 | 4 | False |
| quarterly | 0.20 | -353615.67 | 0.0132 | 0.0069 | 3475967.72 | 3829583.39 | 4 | False |
| quarterly | 0.35 | -559927.93 | 0.0319 | 0.0045 | 3269655.46 | 3829583.39 | 4 | False |
| semiannual | 0.10 | -267717.78 | 0.0105 | -0.0011 | 3953103.48 | 4220821.26 | 4 | False |
| semiannual | 0.20 | -533333.61 | 0.0225 | -0.0024 | 3687487.65 | 4220821.26 | 4 | False |
| semiannual | 0.35 | -856673.25 | 0.0484 | -0.0116 | 3364148.01 | 4220821.26 | 4 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
