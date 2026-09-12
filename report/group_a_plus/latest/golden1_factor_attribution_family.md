# Golden1_0531 Family Factor Attribution (research diagnostic)

- Source paper: `arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)`
- Curve: `results/group_a_plus_switch_policy_compare_golden1_20250102_20260703.json_curve.csv`
- Caveat: Single ~1.5-year, broadly bullish window; descriptive attribution, not an OOS predictive test.

Sorted by full-model alpha p-value (most significant residual alpha first).

| strategy | n | corr(MKT) | beta-only R² | full R² | MKT beta | alpha (ann.) | alpha p |
|---|---|---|---|---|---|---|---|
| switch_ma60_dd10_hold10 | 360 | 0.989 | 0.985 | 0.993 | 0.984 | -1.20% | 0.526 |
| switch_chip_ma60_dd8_score1_hold10 | 360 | 0.992 | 0.988 | 0.994 | 0.961 | -0.86% | 0.554 |
| switch_chip_ma20_dd5_score1_hold5 | 360 | 0.994 | 0.991 | 0.996 | 0.937 | -0.69% | 0.582 |
| switch_chip_ma20_dd5_score2_hold5 | 360 | 0.994 | 0.991 | 0.996 | 0.937 | -0.69% | 0.582 |
| switch_ma60_dd8_hold10 | 360 | 0.992 | 0.988 | 0.994 | 0.961 | -0.81% | 0.586 |
| golden1_0531_1m | 360 | 0.991 | 0.989 | 0.993 | 1.046 | -0.93% | 0.594 |
| group_a_plus_defensive_1m | 360 | 0.995 | 0.992 | 0.995 | 0.940 | -0.65% | 0.620 |
| switch_risk_ma75_dd11_total6_hold5_eg0175_xg020 | 360 | 0.985 | 0.976 | 0.987 | 1.032 | 1.26% | 0.630 |
| switch_risk_ma80_dd11_total6_hold5_eg015_xg015 | 360 | 0.985 | 0.976 | 0.987 | 1.031 | 1.23% | 0.637 |
| switch_ma20_dd7_hold5 | 360 | 0.993 | 0.989 | 0.996 | 0.959 | -0.66% | 0.654 |
| switch_ma90_dd12_hold5_eg020_xg010 | 360 | 0.985 | 0.977 | 0.987 | 1.031 | 1.12% | 0.667 |
| switch_risk_ma90_dd12_total6_hold5 | 360 | 0.985 | 0.977 | 0.987 | 1.031 | 1.12% | 0.667 |
| switch_ma20_dd5_hold5 | 360 | 0.993 | 0.990 | 0.995 | 0.940 | -0.40% | 0.752 |
| switch_risk_ma20_dd5_total2_hold5 | 360 | 0.993 | 0.990 | 0.995 | 0.939 | -0.38% | 0.769 |
| switch_ma120_dd12_hold15 | 360 | 0.986 | 0.978 | 0.988 | 1.032 | 0.65% | 0.795 |
| switch_deriv_ma20_dd5_score1_hold5 | 360 | 0.993 | 0.990 | 0.996 | 0.946 | -0.28% | 0.827 |
| switch_deriv_ma60_dd8_score1_hold10 | 360 | 0.990 | 0.985 | 0.992 | 0.971 | -0.44% | 0.828 |
| switch_risk_ma90_dd12_total6_tail1_hold5 | 360 | 0.987 | 0.981 | 0.989 | 1.046 | 0.13% | 0.957 |

** p<0.05, * p<0.10 on the full-model alpha (const term).
If no row's alpha is significant, none of the switch-policy variants in this family show residual return beyond MKT/LETF_XS/TSMOM/REV1 exposure in this sample -- the whole family's reported Sharpe is beta-explained here, not signal-specific to golden1_0531.

