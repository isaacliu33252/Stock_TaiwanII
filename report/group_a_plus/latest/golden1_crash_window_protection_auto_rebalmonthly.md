# Golden1_0531 / Switch-Policy Crash-Window Protection (research diagnostic)

- Curve: `results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810_curve.csv`
- Caveat: 12 crash window(s); descriptive comparison, not a formal significance test. Fixed weights/rules replayed in-sample, not walk-forward retrained.

## 2018_drawdown_20180123_20180503 (2018-01-23 to 2018-05-03)
- 0050 (MKT) return: `-11.04%`, max drawdown: `-11.04%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -9.52% | -9.52% | +1.52% | +1.52% |
| group_a_plus_defensive_1m | -9.22% | -9.22% | +1.82% | +1.82% |
| switch_ma20_dd5_hold5 | -9.34% | -9.34% | +1.70% | +1.70% |
| switch_ma20_dd7_hold5 | -9.91% | -9.91% | +1.13% | +1.13% |
| switch_ma60_dd8_hold10 | -9.89% | -9.89% | +1.15% | +1.15% |
| switch_ma60_dd10_hold10 | -9.96% | -9.96% | +1.08% | +1.08% |
| switch_ma90_dd12_hold5_eg020_xg010 | -9.91% | -9.91% | +1.13% | +1.13% |
| switch_ma120_dd12_hold15 | -9.98% | -9.98% | +1.06% | +1.06% |

## 2019_drawdown_20180123_20190104 (2018-01-23 to 2019-01-04)
- 0050 (MKT) return: `-18.23%`, max drawdown: `-18.23%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -16.04% | -16.41% | +2.20% | +1.82% |
| group_a_plus_defensive_1m | -15.35% | -15.35% | +2.88% | +2.88% |
| switch_ma20_dd5_hold5 | -15.91% | -16.17% | +2.32% | +2.06% |
| switch_ma20_dd7_hold5 | -16.56% | -16.56% | +1.67% | +1.67% |
| switch_ma60_dd8_hold10 | -16.10% | -16.10% | +2.13% | +2.13% |
| switch_ma60_dd10_hold10 | -17.04% | -17.04% | +1.19% | +1.19% |
| switch_ma90_dd12_hold5_eg020_xg010 | -17.00% | -17.00% | +1.23% | +1.23% |
| switch_ma120_dd12_hold15 | -17.01% | -17.01% | +1.23% | +1.23% |

## 2020_drawdown_20200114_20200319 (2020-01-14 to 2020-03-19)
- 0050 (MKT) return: `-30.48%`, max drawdown: `-30.48%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -29.07% | -29.07% | +1.40% | +1.40% |
| group_a_plus_defensive_1m | -26.93% | -26.93% | +3.55% | +3.55% |
| switch_ma20_dd5_hold5 | -27.62% | -27.62% | +2.86% | +2.86% |
| switch_ma20_dd7_hold5 | -27.62% | -27.62% | +2.86% | +2.86% |
| switch_ma60_dd8_hold10 | -27.60% | -27.60% | +2.87% | +2.87% |
| switch_ma60_dd10_hold10 | -27.34% | -27.34% | +3.14% | +3.14% |
| switch_ma90_dd12_hold5_eg020_xg010 | -27.32% | -27.32% | +3.16% | +3.16% |
| switch_ma120_dd12_hold15 | -27.62% | -27.62% | +2.86% | +2.86% |

## 2021_drawdown_20210121_20210517 (2021-01-21 to 2021-05-17)
- 0050 (MKT) return: `-11.54%`, max drawdown: `-11.54%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -8.96% | -11.21% | +2.58% | +0.33% |
| group_a_plus_defensive_1m | -9.15% | -9.85% | +2.39% | +1.69% |
| switch_ma20_dd5_hold5 | -8.67% | -10.39% | +2.86% | +1.14% |
| switch_ma20_dd7_hold5 | -8.53% | -10.44% | +3.01% | +1.10% |
| switch_ma60_dd8_hold10 | -9.47% | -10.53% | +2.07% | +1.01% |
| switch_ma60_dd10_hold10 | -9.35% | -10.90% | +2.19% | +0.64% |
| switch_ma90_dd12_hold5_eg020_xg010 | -8.63% | -11.01% | +2.91% | +0.53% |
| switch_ma120_dd12_hold15 | -8.98% | -11.30% | +2.56% | +0.24% |

## 2021_drawdown_20210121_20210820 (2021-01-21 to 2021-08-20)
- 0050 (MKT) return: `-8.57%`, max drawdown: `-11.54%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -4.31% | -11.21% | +4.26% | +0.33% |
| group_a_plus_defensive_1m | -5.59% | -9.85% | +2.98% | +1.69% |
| switch_ma20_dd5_hold5 | -4.64% | -10.39% | +3.92% | +1.14% |
| switch_ma20_dd7_hold5 | -4.90% | -10.44% | +3.67% | +1.10% |
| switch_ma60_dd8_hold10 | -5.83% | -10.53% | +2.74% | +1.01% |
| switch_ma60_dd10_hold10 | -5.75% | -10.90% | +2.81% | +0.64% |
| switch_ma90_dd12_hold5_eg020_xg010 | -4.94% | -11.01% | +3.63% | +0.53% |
| switch_ma120_dd12_hold15 | -4.38% | -11.30% | +4.19% | +0.24% |

## 2022_drawdown_20220117_20221025 (2022-01-17 to 2022-10-25)
- 0050 (MKT) return: `-36.38%`, max drawdown: `-36.38%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -33.55% | -33.55% | +2.83% | +2.83% |
| group_a_plus_defensive_1m | -31.91% | -31.91% | +4.47% | +4.47% |
| switch_ma20_dd5_hold5 | -32.32% | -32.32% | +4.06% | +4.06% |
| switch_ma20_dd7_hold5 | -32.70% | -32.70% | +3.69% | +3.69% |
| switch_ma60_dd8_hold10 | -31.98% | -31.98% | +4.40% | +4.40% |
| switch_ma60_dd10_hold10 | -32.34% | -32.34% | +4.04% | +4.04% |
| switch_ma90_dd12_hold5_eg020_xg010 | -32.00% | -32.00% | +4.38% | +4.38% |
| switch_ma120_dd12_hold15 | -32.08% | -32.08% | +4.30% | +4.30% |

## 2023_drawdown_20230714_20231031 (2023-07-14 to 2023-10-31)
- 0050 (MKT) return: `-8.39%`, max drawdown: `-8.39%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -8.02% | -8.02% | +0.38% | +0.38% |
| group_a_plus_defensive_1m | -7.41% | -7.41% | +0.98% | +0.98% |
| switch_ma20_dd5_hold5 | -8.37% | -8.37% | +0.03% | +0.03% |
| switch_ma20_dd7_hold5 | -8.14% | -8.14% | +0.26% | +0.26% |
| switch_ma60_dd8_hold10 | -8.22% | -8.22% | +0.18% | +0.18% |
| switch_ma60_dd10_hold10 | -7.69% | -7.69% | +0.70% | +0.70% |
| switch_ma90_dd12_hold5_eg020_xg010 | -7.77% | -7.77% | +0.62% | +0.62% |
| switch_ma120_dd12_hold15 | -7.96% | -7.96% | +0.43% | +0.43% |

## 2024_drawdown_20240711_20240805 (2024-07-11 to 2024-08-05)
- 0050 (MKT) return: `-21.70%`, max drawdown: `-21.70%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -20.84% | -20.84% | +0.86% | +0.86% |
| group_a_plus_defensive_1m | -19.27% | -19.27% | +2.43% | +2.43% |
| switch_ma20_dd5_hold5 | -19.37% | -19.37% | +2.33% | +2.33% |
| switch_ma20_dd7_hold5 | -19.60% | -19.60% | +2.11% | +2.11% |
| switch_ma60_dd8_hold10 | -19.69% | -19.69% | +2.01% | +2.01% |
| switch_ma60_dd10_hold10 | -19.91% | -19.91% | +1.79% | +1.79% |
| switch_ma90_dd12_hold5_eg020_xg010 | -20.27% | -20.27% | +1.44% | +1.44% |
| switch_ma120_dd12_hold15 | -20.19% | -20.19% | +1.51% | +1.51% |

## 2025_drawdown_20250107_20250409 (2025-01-07 to 2025-04-09)
- 0050 (MKT) return: `-28.47%`, max drawdown: `-28.47%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -27.84% | -27.84% | +0.64% | +0.64% |
| group_a_plus_defensive_1m | -25.59% | -25.59% | +2.88% | +2.88% |
| switch_ma20_dd5_hold5 | -26.09% | -26.09% | +2.38% | +2.38% |
| switch_ma20_dd7_hold5 | -25.87% | -25.87% | +2.60% | +2.60% |
| switch_ma60_dd8_hold10 | -25.87% | -25.87% | +2.60% | +2.60% |
| switch_ma60_dd10_hold10 | -25.89% | -25.89% | +2.59% | +2.59% |
| switch_ma90_dd12_hold5_eg020_xg010 | -25.87% | -25.87% | +2.61% | +2.61% |
| switch_ma120_dd12_hold15 | -25.71% | -25.71% | +2.76% | +2.76% |

## 2025_drawdown_20251031_20251124 (2025-10-31 to 2025-11-24)
- 0050 (MKT) return: `-8.03%`, max drawdown: `-8.03%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -7.49% | -7.49% | +0.54% | +0.54% |
| group_a_plus_defensive_1m | -6.98% | -6.98% | +1.05% | +1.05% |
| switch_ma20_dd5_hold5 | -7.33% | -7.33% | +0.70% | +0.70% |
| switch_ma20_dd7_hold5 | -7.50% | -7.50% | +0.53% | +0.53% |
| switch_ma60_dd8_hold10 | -7.55% | -7.55% | +0.48% | +0.48% |
| switch_ma60_dd10_hold10 | -7.53% | -7.53% | +0.51% | +0.51% |
| switch_ma90_dd12_hold5_eg020_xg010 | -7.60% | -7.60% | +0.43% | +0.43% |
| switch_ma120_dd12_hold15 | -7.57% | -7.57% | +0.46% | +0.46% |

## 2026_drawdown_20260226_20260331 (2026-02-26 to 2026-03-31)
- 0050 (MKT) return: `-10.84%`, max drawdown: `-10.84%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -11.06% | -11.06% | -0.22% | -0.22% |
| group_a_plus_defensive_1m | -9.97% | -9.97% | +0.87% | +0.87% |
| switch_ma20_dd5_hold5 | -10.95% | -10.95% | -0.10% | -0.10% |
| switch_ma20_dd7_hold5 | -11.13% | -11.13% | -0.28% | -0.28% |
| switch_ma60_dd8_hold10 | -11.13% | -11.13% | -0.29% | -0.29% |
| switch_ma60_dd10_hold10 | -11.16% | -11.16% | -0.32% | -0.32% |
| switch_ma90_dd12_hold5_eg020_xg010 | -10.83% | -10.83% | +0.01% | +0.01% |
| switch_ma120_dd12_hold15 | -10.99% | -10.99% | -0.15% | -0.15% |

## 2026_drawdown_20260622_20260730 (2026-06-22 to 2026-07-30)
- 0050 (MKT) return: `-15.88%`, max drawdown: `-15.88%`

| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |
|---|---|---|---|---|
| golden1_0531_1m | -16.25% | -16.25% | -0.37% | -0.37% |
| group_a_plus_defensive_1m | -14.63% | -14.63% | +1.25% | +1.25% |
| switch_ma20_dd5_hold5 | -15.54% | -15.54% | +0.34% | +0.34% |
| switch_ma20_dd7_hold5 | -16.07% | -16.07% | -0.19% | -0.19% |
| switch_ma60_dd8_hold10 | -15.94% | -15.94% | -0.06% | -0.06% |
| switch_ma60_dd10_hold10 | -15.76% | -15.76% | +0.12% | +0.12% |
| switch_ma90_dd12_hold5_eg020_xg010 | -15.96% | -15.96% | -0.08% | -0.08% |
| switch_ma120_dd12_hold15 | -16.06% | -16.06% | -0.18% | -0.18% |

## Aggregate Across Windows

| strategy | n windows | mean excess return vs MKT | positive-excess hit rate | mean drawdown relief vs MKT | positive-relief hit rate |
|---|---|---|---|---|---|
| group_a_plus_defensive_1m | 12 | +2.30% | 12/12 | +2.13% | 12/12 |
| switch_ma20_dd5_hold5 | 12 | +1.95% | 11/12 | +1.55% | 11/12 |
| switch_ma60_dd8_hold10 | 12 | +1.69% | 10/12 | +1.46% | 10/12 |
| switch_ma20_dd7_hold5 | 12 | +1.75% | 10/12 | +1.38% | 10/12 |
| switch_ma60_dd10_hold10 | 12 | +1.65% | 11/12 | +1.34% | 11/12 |
| switch_ma90_dd12_hold5_eg020_xg010 | 12 | +1.79% | 11/12 | +1.33% | 11/12 |
| switch_ma120_dd12_hold15 | 12 | +1.75% | 10/12 | +1.23% | 10/12 |
| golden1_0531_1m | 12 | +1.38% | 10/12 | +0.84% | 10/12 |

Positive "drawdown relief" means the strategy's max drawdown in that window was shallower (less negative) than simply holding 0050; positive "excess return" means it lost less (or gained more) than 0050 over the window.

