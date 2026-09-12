# Golden1_0531 Family Factor Attribution (research diagnostic)

- Source paper: `arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)`
- Curve: `results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810_curve.csv`
- Caveat: 9.6-year window (2017-01-12 to 2026-08-10), spanning multiple regimes; still a descriptive in-sample attribution (weights/rules are fixed, not walk-forward retrained), not an OOS predictive test.

Sorted by full-model alpha p-value (most significant residual alpha first).

| strategy | n | corr(MKT) | beta-only R² | full R² | MKT beta | alpha (ann.) | alpha p |
|---|---|---|---|---|---|---|---|
| golden1_0531_1m | 2324 | 0.979 | 0.983 | 0.983 | 1.337 | -1.63% | 0.188 |
| group_a_plus_defensive_1m | 2324 | 0.986 | 0.985 | 0.985 | 1.161 | -1.29% | 0.200 |
| switch_ma60_dd10_hold10 | 2324 | 0.991 | 0.990 | 0.994 | 0.971 | -0.50% | 0.372 |
| switch_ma120_dd12_hold15 | 2324 | 0.987 | 0.984 | 0.988 | 1.008 | -0.64% | 0.415 |
| switch_ma60_dd8_hold10 | 2324 | 0.993 | 0.991 | 0.995 | 0.956 | -0.34% | 0.480 |
| switch_ma90_dd12_hold5_eg020_xg010 | 2324 | 0.988 | 0.984 | 0.988 | 1.001 | -0.48% | 0.526 |
| switch_ma20_dd5_hold5 | 2324 | 0.994 | 0.993 | 0.996 | 0.945 | 0.13% | 0.746 |
| switch_ma20_dd7_hold5 | 2324 | 0.993 | 0.992 | 0.996 | 0.964 | 0.09% | 0.844 |

** p<0.05, * p<0.10 on the full-model alpha (const term).
If no row's alpha is significant, none of the switch-policy variants in this family show residual return beyond MKT/LETF_XS/TSMOM/REV1 exposure in this sample -- the whole family's reported Sharpe is beta-explained here, not signal-specific to golden1_0531.

