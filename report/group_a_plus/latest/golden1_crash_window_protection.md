# Golden1_0531 / Switch-Policy Crash-Window Protection (research diagnostic)

- Curve: `results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810_curve.csv`
- Caveat: 3 crash window(s); descriptive comparison, not a formal significance test. Fixed weights/rules replayed in-sample, not walk-forward retrained.

## 2018Q4_correction (2018-10-01 to 2018-12-31)
- 0050 (MKT) return: `-13.57%`, max drawdown: `-15.80%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -14.03% | -16.19% | -0.46% | -0.40% |
| group_a_plus_defensive_1m | -12.72% | -14.74% | +0.84% | +1.06% |
| switch_ma20_dd5_hold5 | -12.88% | -14.85% | +0.68% | +0.95% |
| switch_ma20_dd7_hold5 | -12.90% | -14.98% | +0.67% | +0.82% |
| switch_ma60_dd8_hold10 | -12.41% | -14.33% | +1.15% | +1.47% |
| switch_ma60_dd10_hold10 | -13.19% | -15.13% | +0.38% | +0.66% |
| switch_ma90_dd12_hold5_eg020_xg010 | -13.19% | -15.13% | +0.38% | +0.66% |
| switch_ma120_dd12_hold15 | -13.18% | -15.12% | +0.39% | +0.67% |

## 2020_covid_crash (2020-01-15 to 2020-03-23)
- 0050 (MKT) return: `-27.46%`, max drawdown: `-29.84%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -29.72% | -32.18% | -2.26% | -2.35% |
| group_a_plus_defensive_1m | -26.73% | -28.99% | +0.73% | +0.85% |
| switch_ma20_dd5_hold5 | -25.12% | -27.23% | +2.34% | +2.60% |
| switch_ma20_dd7_hold5 | -25.12% | -27.23% | +2.34% | +2.60% |
| switch_ma60_dd8_hold10 | -25.14% | -27.25% | +2.32% | +2.58% |
| switch_ma60_dd10_hold10 | -24.84% | -26.96% | +2.62% | +2.87% |
| switch_ma90_dd12_hold5_eg020_xg010 | -25.06% | -27.19% | +2.40% | +2.65% |
| switch_ma120_dd12_hold15 | -25.31% | -27.44% | +2.15% | +2.39% |

## 2022_bear_market (2022-01-01 to 2022-10-31)
- 0050 (MKT) return: `-32.34%`, max drawdown: `-36.38%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -36.62% | -40.34% | -4.27% | -3.96% |
| group_a_plus_defensive_1m | -33.49% | -37.22% | -1.15% | -0.84% |
| switch_ma20_dd5_hold5 | -28.95% | -32.42% | +3.40% | +3.96% |
| switch_ma20_dd7_hold5 | -29.25% | -32.71% | +3.10% | +3.67% |
| switch_ma60_dd8_hold10 | -28.52% | -32.00% | +3.82% | +4.38% |
| switch_ma60_dd10_hold10 | -29.01% | -32.49% | +3.33% | +3.90% |
| switch_ma90_dd12_hold5_eg020_xg010 | -27.93% | -31.37% | +4.41% | +5.01% |
| switch_ma120_dd12_hold15 | -28.24% | -31.68% | +4.10% | +4.70% |

## Aggregate Across Windows

| strategy | n windows | mean excess return vs MKT | positive-excess hit rate | mean drawdown relief vs MKT | positive-relief hit rate |
|---|---|---|---|---|---|
| switch_ma60_dd8_hold10 | 3 | +2.43% | 3/3 | +2.81% | 3/3 |
| switch_ma90_dd12_hold5_eg020_xg010 | 3 | +2.40% | 3/3 | +2.77% | 3/3 |
| switch_ma120_dd12_hold15 | 3 | +2.21% | 3/3 | +2.59% | 3/3 |
| switch_ma20_dd5_hold5 | 3 | +2.14% | 3/3 | +2.51% | 3/3 |
| switch_ma60_dd10_hold10 | 3 | +2.11% | 3/3 | +2.48% | 3/3 |
| switch_ma20_dd7_hold5 | 3 | +2.04% | 3/3 | +2.37% | 3/3 |
| group_a_plus_defensive_1m | 3 | +0.14% | 2/3 | +0.36% | 2/3 |
| golden1_0531_1m | 3 | -2.33% | 0/3 | -2.24% | 0/3 |

Positive "drawdown relief" means the strategy's max drawdown in that window was shallower (less negative) than simply holding 0050; positive "excess return" means it lost less (or gained more) than 0050 over the window.

