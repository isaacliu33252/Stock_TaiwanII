# Group A + 00679B Shadow Overlay

Date: 2026-06-04
Status: Shadow research only

## Purpose

Evaluate whether adding `00679B` as an external stabilizer to Group A improves stability before any model retraining or production change.

## Inputs

- Group A source:
  - `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- 00679B cache:
  - `FinRL/data/portfolio_cache/00679B_TWO_20200101_20260602_1d_raw_v1.parquet`

## Method

- Window: `2025-01-02` to `2026-05-25`
- Use idealized daily-rebalanced static overlays.
- Group A daily returns exclude external DCA cash contributions.
- 00679B returns use adjusted close.
- Tested:
  - `90% Group A / 10% 00679B`
  - `80% Group A / 20% 00679B`
  - `70% Group A / 30% 00679B`

## Results

| Variant | Total return | Annual return | Volatility | Sharpe | Sortino | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `100% Group A` | `91.17%` | `63.29%` | `24.06%` | `2.631` | `3.562` | `-25.99%` |
| `90% Group A / 10% 00679B` | `79.82%` | `55.90%` | `21.63%` | `2.584` | `3.541` | `-23.56%` |
| `80% Group A / 20% 00679B` | `68.97%` | `48.73%` | `19.33%` | `2.520` | `3.474` | `-21.07%` |
| `70% Group A / 30% 00679B` | `58.59%` | `41.76%` | `17.20%` | `2.427` | `3.344` | `-18.56%` |

## Interpretation

00679B improves stability as expected, but the cost is lower return:

- `10% 00679B` reduces max drawdown by about `2.43` percentage points.
- `20% 00679B` reduces max drawdown by about `4.92` percentage points.
- `30% 00679B` reduces max drawdown by about `7.43` percentage points.

The best starting candidate is `80% Group A / 20% 00679B`: it meaningfully reduces volatility and drawdown while keeping most of Group A's return profile.

## Outputs

- Summary JSON: `results/group_a_679b_overlay_shadow_20260604.json`
- Summary CSV: `results/group_a_679b_overlay_shadow_20260604.csv`
- Daily curve CSV: `results/group_a_679b_overlay_shadow_curve_20260604.csv`

## Recommendation

Keep `Golden1_0531` unchanged. Run `80% Group A / 20% 00679B` as the first shadow overlay candidate. Do not retrain Group A until the overlay proves useful under a realistic rebalance schedule and fee model.
