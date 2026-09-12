# Golden1_0531 Family Factor Attribution (research diagnostic)

- Source paper: `arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)`
- Curve: `results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810_curve.csv`
- Caveat: 9.6-year window (2017-01-12 to 2026-08-10), spanning multiple regimes; still a descriptive in-sample attribution (weights/rules are fixed, not walk-forward retrained), not an OOS predictive test.

Sorted by full-model alpha p-value (most significant residual alpha first).

| strategy | n | corr(MKT) | beta-only R² | full R² | MKT beta | alpha (ann.) | alpha p |
|---|---|---|---|---|---|---|---|
| switch_ma60_dd10_hold10 | 2324 | 0.994 | 0.995 | 0.997 | 0.950 | -0.32% | 0.385 |
| switch_ma20_dd5_hold5 | 2324 | 0.995 | 0.995 | 0.998 | 0.939 | 0.31% | 0.386 |
| golden1_0531_1m | 2324 | 0.995 | 0.999 | 0.999 | 0.993 | 0.18% | 0.458 |
| group_a_plus_defensive_1m | 2324 | 0.998 | 0.999 | 0.999 | 0.898 | 0.10% | 0.575 |
| switch_ma60_dd8_hold10 | 2324 | 0.995 | 0.995 | 0.997 | 0.943 | -0.16% | 0.646 |
| switch_ma20_dd7_hold5 | 2324 | 0.995 | 0.995 | 0.997 | 0.949 | 0.04% | 0.905 |
| switch_ma120_dd12_hold15 | 2324 | 0.994 | 0.995 | 0.997 | 0.956 | 0.01% | 0.974 |
| switch_ma90_dd12_hold5_eg020_xg010 | 2324 | 0.995 | 0.996 | 0.997 | 0.953 | 0.01% | 0.976 |

** p<0.05, * p<0.10 on the full-model alpha (const term).
If no row's alpha is significant, none of the switch-policy variants in this family show residual return beyond MKT/LETF_XS/TSMOM/REV1 exposure in this sample -- the whole family's reported Sharpe is beta-explained here, not signal-specific to golden1_0531.

