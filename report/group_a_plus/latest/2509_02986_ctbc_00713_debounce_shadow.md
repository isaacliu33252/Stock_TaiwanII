# 2509.02986 CTBC 00713 Debounce Shadow

- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Best variant: `raw_gate`
- Strict debounce gate passed: `False`

## Summary

| variant | FV wins | Sharpe wins | non-worse MDD | avg dFV | avg dSharpe | worst dFV |
|---|---:|---:|---:|---:|---:|---:|
| `raw_gate` | 1 | 1 | 2 | -3747.40 | -0.0066 | -7497.32 |
| `debounce_2of3` | 0 | 0 | 2 | -1823.95 | -0.0036 | -3647.90 |
| `debounce_3of3` | 0 | 0 | 2 | -1583.80 | -0.0039 | -3167.60 |

## Windows

### ncf_panel_2025_2026

- `raw_gate` dFV=`-7497.32` dSharpe=`-0.0132` dMDD=`0.0000`
- `debounce_2of3` dFV=`-3647.90` dSharpe=`-0.0072` dMDD=`0.0000`
- `debounce_3of3` dFV=`-3167.60` dSharpe=`-0.0078` dMDD=`0.0000`

### trade_record_period_20260501_20260904

- `raw_gate` dFV=`2.51` dSharpe=`0.0000` dMDD=`0.0000`
- `debounce_2of3` dFV=`0.00` dSharpe=`0.0000` dMDD=`0.0000`
- `debounce_3of3` dFV=`0.00` dSharpe=`0.0000` dMDD=`0.0000`

## Conclusion

CTBC 00713 debounce remains shadow-only and does not change the current fixed 10% sleeve policy.
