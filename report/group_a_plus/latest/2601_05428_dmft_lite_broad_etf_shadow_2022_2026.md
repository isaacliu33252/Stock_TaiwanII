# 2601.05428v1 DMFT-lite GroupA+ Shadow

- Generated: `2026-08-14T14:29:34`
- Policy: `research_only_no_groupa_plus_live_change`
- Window: `{'start': '2022-01-03', 'end': '2026-08-13', 'rows': 1118}`
- Tickers: `0050.TW, 0056.TW, 00631L.TW, 00632R.TW, 00646.TW, 00679B.TWO, 00713.TW, 00751B.TWO, 00878.TW`

## Variant Results

| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| monthly | 0.10 | -108709.70 | 0.0313 | 0.0051 | 2308205.16 | 2416914.86 | 9 | False |
| monthly | 0.20 | -219752.41 | 0.0686 | 0.0073 | 2197162.46 | 2416914.86 | 9 | False |
| monthly | 0.35 | -286384.59 | 0.0775 | 0.0079 | 2130530.27 | 2416914.86 | 9 | False |
| quarterly | 0.10 | -131268.91 | 0.0238 | 0.0011 | 2342177.79 | 2473446.70 | 9 | False |
| quarterly | 0.20 | -256736.23 | 0.0534 | 0.0003 | 2216710.47 | 2473446.70 | 9 | False |
| quarterly | 0.35 | -333304.91 | 0.0630 | -0.0041 | 2140141.79 | 2473446.70 | 9 | False |
| semiannual | 0.10 | -179806.80 | 0.0349 | -0.0006 | 2415677.98 | 2595484.79 | 9 | False |
| semiannual | 0.20 | -330066.81 | 0.0700 | -0.0021 | 2265417.98 | 2595484.79 | 9 | False |
| semiannual | 0.35 | -359986.74 | 0.0723 | -0.0053 | 2235498.05 | 2595484.79 | 9 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.

## Interpretation

Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small.
