# Golden1_0531 / Switch-Policy Crash-Window Protection (research diagnostic)

- Curve: `results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810_curve.csv`
- Caveat: 12 crash window(s); descriptive comparison, not a formal significance test. Fixed weights/rules replayed in-sample, not walk-forward retrained.

## 2018_drawdown_20180123_20180503 (2018-01-23 to 2018-05-03)
- 0050 (MKT) return: `-11.04%`, max drawdown: `-11.04%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -10.05% | -10.05% | +0.99% | +0.99% |
| group_a_plus_defensive_1m | -9.63% | -9.63% | +1.41% | +1.41% |
| switch_ma20_dd5_hold5 | -9.38% | -9.38% | +1.66% | +1.66% |
| switch_ma20_dd7_hold5 | -10.05% | -10.05% | +0.99% | +0.99% |
| switch_ma60_dd8_hold10 | -9.89% | -9.89% | +1.15% | +1.15% |
| switch_ma60_dd10_hold10 | -9.95% | -9.95% | +1.10% | +1.10% |
| switch_ma90_dd12_hold5_eg020_xg010 | -9.90% | -9.90% | +1.14% | +1.14% |
| switch_ma120_dd12_hold15 | -10.50% | -10.50% | +0.55% | +0.55% |

## 2019_drawdown_20180123_20190104 (2018-01-23 to 2019-01-04)
- 0050 (MKT) return: `-18.23%`, max drawdown: `-18.23%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -17.23% | -17.63% | +1.00% | +0.60% |
| group_a_plus_defensive_1m | -16.24% | -16.24% | +2.00% | +2.00% |
| switch_ma20_dd5_hold5 | -16.05% | -16.27% | +2.18% | +1.96% |
| switch_ma20_dd7_hold5 | -16.73% | -16.73% | +1.50% | +1.50% |
| switch_ma60_dd8_hold10 | -16.02% | -16.02% | +2.21% | +2.21% |
| switch_ma60_dd10_hold10 | -17.13% | -17.13% | +1.10% | +1.10% |
| switch_ma90_dd12_hold5_eg020_xg010 | -17.10% | -17.10% | +1.13% | +1.13% |
| switch_ma120_dd12_hold15 | -17.54% | -17.54% | +0.69% | +0.69% |

## 2020_drawdown_20200114_20200319 (2020-01-14 to 2020-03-19)
- 0050 (MKT) return: `-30.48%`, max drawdown: `-30.48%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -32.74% | -32.74% | -2.26% | -2.26% |
| group_a_plus_defensive_1m | -29.55% | -29.55% | +0.92% | +0.92% |
| switch_ma20_dd5_hold5 | -27.80% | -27.80% | +2.68% | +2.68% |
| switch_ma20_dd7_hold5 | -27.80% | -27.80% | +2.68% | +2.68% |
| switch_ma60_dd8_hold10 | -27.82% | -27.82% | +2.65% | +2.65% |
| switch_ma60_dd10_hold10 | -27.53% | -27.53% | +2.94% | +2.94% |
| switch_ma90_dd12_hold5_eg020_xg010 | -27.76% | -27.76% | +2.72% | +2.72% |
| switch_ma120_dd12_hold15 | -28.01% | -28.01% | +2.46% | +2.46% |

## 2021_drawdown_20210121_20210517 (2021-01-21 to 2021-05-17)
- 0050 (MKT) return: `-11.54%`, max drawdown: `-11.54%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -10.25% | -15.42% | +1.29% | -3.88% |
| group_a_plus_defensive_1m | -10.24% | -12.91% | +1.29% | -1.37% |
| switch_ma20_dd5_hold5 | -8.78% | -10.40% | +2.76% | +1.13% |
| switch_ma20_dd7_hold5 | -9.07% | -10.59% | +2.47% | +0.95% |
| switch_ma60_dd8_hold10 | -10.12% | -10.53% | +1.42% | +1.01% |
| switch_ma60_dd10_hold10 | -10.48% | -11.17% | +1.06% | +0.37% |
| switch_ma90_dd12_hold5_eg020_xg010 | -9.21% | -12.88% | +2.33% | -1.34% |
| switch_ma120_dd12_hold15 | -9.91% | -13.47% | +1.63% | -1.94% |

## 2021_drawdown_20210121_20210820 (2021-01-21 to 2021-08-20)
- 0050 (MKT) return: `-8.57%`, max drawdown: `-11.54%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -2.99% | -15.42% | +5.58% | -3.88% |
| group_a_plus_defensive_1m | -4.94% | -12.91% | +3.62% | -1.37% |
| switch_ma20_dd5_hold5 | -4.82% | -10.40% | +3.75% | +1.13% |
| switch_ma20_dd7_hold5 | -5.56% | -10.59% | +3.00% | +0.95% |
| switch_ma60_dd8_hold10 | -6.58% | -10.53% | +1.99% | +1.01% |
| switch_ma60_dd10_hold10 | -7.02% | -11.17% | +1.55% | +0.37% |
| switch_ma90_dd12_hold5_eg020_xg010 | -5.64% | -12.88% | +2.93% | -1.34% |
| switch_ma120_dd12_hold15 | -4.05% | -13.47% | +4.52% | -1.94% |

## 2022_drawdown_20220117_20221025 (2022-01-17 to 2022-10-25)
- 0050 (MKT) return: `-36.38%`, max drawdown: `-36.38%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -40.34% | -40.34% | -3.96% | -3.96% |
| group_a_plus_defensive_1m | -37.22% | -37.22% | -0.84% | -0.84% |
| switch_ma20_dd5_hold5 | -32.42% | -32.42% | +3.96% | +3.96% |
| switch_ma20_dd7_hold5 | -32.71% | -32.71% | +3.67% | +3.67% |
| switch_ma60_dd8_hold10 | -32.00% | -32.00% | +4.38% | +4.38% |
| switch_ma60_dd10_hold10 | -32.49% | -32.49% | +3.90% | +3.90% |
| switch_ma90_dd12_hold5_eg020_xg010 | -31.37% | -31.37% | +5.01% | +5.01% |
| switch_ma120_dd12_hold15 | -31.68% | -31.68% | +4.70% | +4.70% |

## 2023_drawdown_20230714_20231031 (2023-07-14 to 2023-10-31)
- 0050 (MKT) return: `-8.39%`, max drawdown: `-8.39%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -10.51% | -10.51% | -2.12% | -2.12% |
| group_a_plus_defensive_1m | -9.29% | -9.29% | -0.89% | -0.89% |
| switch_ma20_dd5_hold5 | -8.54% | -8.54% | -0.14% | -0.14% |
| switch_ma20_dd7_hold5 | -8.29% | -8.29% | +0.11% | +0.11% |
| switch_ma60_dd8_hold10 | -8.38% | -8.38% | +0.01% | +0.01% |
| switch_ma60_dd10_hold10 | -7.85% | -7.85% | +0.55% | +0.55% |
| switch_ma90_dd12_hold5_eg020_xg010 | -8.12% | -8.12% | +0.28% | +0.28% |
| switch_ma120_dd12_hold15 | -8.43% | -8.43% | -0.03% | -0.03% |

## 2024_drawdown_20240711_20240805 (2024-07-11 to 2024-08-05)
- 0050 (MKT) return: `-21.70%`, max drawdown: `-21.70%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -29.04% | -29.04% | -7.34% | -7.34% |
| group_a_plus_defensive_1m | -25.78% | -25.78% | -4.08% | -4.08% |
| switch_ma20_dd5_hold5 | -19.60% | -19.60% | +2.11% | +2.11% |
| switch_ma20_dd7_hold5 | -19.92% | -19.92% | +1.78% | +1.78% |
| switch_ma60_dd8_hold10 | -20.16% | -20.16% | +1.54% | +1.54% |
| switch_ma60_dd10_hold10 | -20.75% | -20.75% | +0.95% | +0.95% |
| switch_ma90_dd12_hold5_eg020_xg010 | -21.47% | -21.47% | +0.23% | +0.23% |
| switch_ma120_dd12_hold15 | -21.41% | -21.41% | +0.29% | +0.29% |

## 2025_drawdown_20250107_20250409 (2025-01-07 to 2025-04-09)
- 0050 (MKT) return: `-28.47%`, max drawdown: `-28.47%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -38.16% | -38.16% | -9.69% | -9.69% |
| group_a_plus_defensive_1m | -33.70% | -33.70% | -5.23% | -5.23% |
| switch_ma20_dd5_hold5 | -26.05% | -26.05% | +2.42% | +2.42% |
| switch_ma20_dd7_hold5 | -25.65% | -25.65% | +2.83% | +2.83% |
| switch_ma60_dd8_hold10 | -25.57% | -25.57% | +2.90% | +2.90% |
| switch_ma60_dd10_hold10 | -25.59% | -25.59% | +2.88% | +2.88% |
| switch_ma90_dd12_hold5_eg020_xg010 | -25.64% | -25.64% | +2.84% | +2.84% |
| switch_ma120_dd12_hold15 | -25.74% | -25.74% | +2.74% | +2.74% |

## 2025_drawdown_20251031_20251124 (2025-10-31 to 2025-11-24)
- 0050 (MKT) return: `-8.03%`, max drawdown: `-8.03%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -10.54% | -10.54% | -2.51% | -2.51% |
| group_a_plus_defensive_1m | -9.46% | -9.46% | -1.43% | -1.43% |
| switch_ma20_dd5_hold5 | -7.81% | -7.81% | +0.22% | +0.22% |
| switch_ma20_dd7_hold5 | -8.23% | -8.23% | -0.20% | -0.20% |
| switch_ma60_dd8_hold10 | -8.23% | -8.23% | -0.20% | -0.20% |
| switch_ma60_dd10_hold10 | -8.21% | -8.21% | -0.18% | -0.18% |
| switch_ma90_dd12_hold5_eg020_xg010 | -8.21% | -8.21% | -0.18% | -0.18% |
| switch_ma120_dd12_hold15 | -8.16% | -8.16% | -0.13% | -0.13% |

## 2026_drawdown_20260226_20260331 (2026-02-26 to 2026-03-31)
- 0050 (MKT) return: `-10.84%`, max drawdown: `-10.84%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -16.70% | -16.70% | -5.85% | -5.85% |
| group_a_plus_defensive_1m | -14.56% | -14.56% | -3.72% | -3.72% |
| switch_ma20_dd5_hold5 | -11.36% | -11.36% | -0.52% | -0.52% |
| switch_ma20_dd7_hold5 | -11.68% | -11.68% | -0.84% | -0.84% |
| switch_ma60_dd8_hold10 | -11.68% | -11.68% | -0.84% | -0.84% |
| switch_ma60_dd10_hold10 | -12.75% | -12.75% | -1.91% | -1.91% |
| switch_ma90_dd12_hold5_eg020_xg010 | -12.75% | -12.75% | -1.91% | -1.91% |
| switch_ma120_dd12_hold15 | -12.69% | -12.69% | -1.84% | -1.84% |

## 2026_drawdown_20260622_20260730 (2026-06-22 to 2026-07-30)
- 0050 (MKT) return: `-15.88%`, max drawdown: `-15.88%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -25.59% | -25.59% | -9.71% | -9.71% |
| group_a_plus_defensive_1m | -22.46% | -22.46% | -6.58% | -6.58% |
| switch_ma20_dd5_hold5 | -15.54% | -15.54% | +0.34% | +0.34% |
| switch_ma20_dd7_hold5 | -16.07% | -16.07% | -0.19% | -0.19% |
| switch_ma60_dd8_hold10 | -16.79% | -16.79% | -0.92% | -0.92% |
| switch_ma60_dd10_hold10 | -16.57% | -16.57% | -0.69% | -0.69% |
| switch_ma90_dd12_hold5_eg020_xg010 | -19.18% | -19.18% | -3.30% | -3.30% |
| switch_ma120_dd12_hold15 | -19.11% | -19.11% | -3.23% | -3.23% |

## Aggregate Across Windows

| strategy | n windows | mean excess return vs MKT | positive-excess hit rate | mean drawdown relief vs MKT | positive-relief hit rate |
|---|---|---|---|---|---|
| switch_ma20_dd5_hold5 | 12 | +1.79% | 10/12 | +1.41% | 10/12 |
| switch_ma60_dd8_hold10 | 12 | +1.36% | 9/12 | +1.24% | 9/12 |
| switch_ma20_dd7_hold5 | 12 | +1.48% | 9/12 | +1.19% | 9/12 |
| switch_ma60_dd10_hold10 | 12 | +1.10% | 9/12 | +0.95% | 9/12 |
| switch_ma90_dd12_hold5_eg020_xg010 | 12 | +1.10% | 9/12 | +0.44% | 7/12 |
| switch_ma120_dd12_hold15 | 12 | +1.03% | 8/12 | +0.19% | 6/12 |
| group_a_plus_defensive_1m | 12 | -1.13% | 5/12 | -1.76% | 3/12 |
| golden1_0531_1m | 12 | -2.88% | 4/12 | -4.13% | 2/12 |

Positive "drawdown relief" means the strategy's max drawdown in that window was shallower (less negative) than simply holding 0050; positive "excess return" means it lost less (or gained more) than 0050 over the window.

