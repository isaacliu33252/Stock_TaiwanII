# Group A + 00679B Rebalance/Fee Shadow

Date: 2026-06-04
Status: Shadow research only

## Purpose

Extend the first `00679B` overlay check with a more realistic rebalance rule and transaction costs.

## Inputs

- Group A source:
  - `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- 00679B cache:
  - `FinRL/data/portfolio_cache/00679B_TWO_20200101_20260602_1d_raw_v1.parquet`

## Method

- Window: `2025-01-02` to `2026-05-25`
- Group A daily returns exclude external DCA cash contributions.
- 00679B returns use adjusted close.
- Rebalance on:
  - first trading day of each month, or
  - absolute target-weight drift >= `5` percentage points
- Cost assumptions:
  - commission on buys and sells: `0.1425%`
  - ETF tax on sells: `0.1%`

## Results

| Variant | Total return | Annual return | Volatility | Sharpe | Sortino | Max drawdown | Rebalances | Total cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `100% Group A` | `91.17%` | `63.29%` | `24.06%` | `2.631` | `3.562` | `-25.99%` | `1` | `0` |
| `90% Group A / 10% 00679B` | `79.86%` | `55.93%` | `21.67%` | `2.581` | `3.543` | `-23.61%` | `17` | `472.93` |
| `80% Group A / 20% 00679B` | `69.04%` | `48.78%` | `19.40%` | `2.515` | `3.477` | `-21.17%` | `17` | `828.13` |
| `70% Group A / 30% 00679B` | `58.70%` | `41.84%` | `17.28%` | `2.420` | `3.357` | `-18.67%` | `17` | `1,070.53` |

## Interpretation

The monthly/drift rebalance version is close to the idealized daily-rebalanced result. Transaction costs are not the main issue; the main tradeoff remains return versus drawdown reduction.

- `10% 00679B` reduces max drawdown by about `2.38` percentage points.
- `20% 00679B` reduces max drawdown by about `4.82` percentage points.
- `30% 00679B` reduces max drawdown by about `7.32` percentage points.

The best practical shadow candidate remains `80% Group A / 20% 00679B`.

## Outputs

- Summary JSON: `results/group_a_679b_overlay_rebalance_fee_20260604.json`
- Summary CSV: `results/group_a_679b_overlay_rebalance_fee_20260604.csv`
- Daily curve CSV: `results/group_a_679b_overlay_rebalance_fee_curve_20260604.csv`

## Recommendation

Use `80% Group A / 20% 00679B` as the first realistic shadow overlay. Keep `Golden1_0531` unchanged and do not retrain Group A yet.
