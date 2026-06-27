# Group A + Group B No-2884 Backtest

Date: 2026-06-05 request, using available market data through 2026-06-04
Status: Backtest complete

## Scope

Run the latest Group A + Group B strategies from `2024-01-01` to `2026-06-05`, excluding 玉山金 (`2884.TW`).

The local database has aligned market data through `2026-06-04`, so the actual backtest window is:

- `2024-01-02` to `2026-06-04`
- `584` trading rows

## Strategy Inputs

Group A:

- Strategy: `Golden1_0531_tdcc_v1_latest`
- Source: `results/group_a_tdcc_latest_backtest_20240101_20260605.json`

Group B:

- Strategy/model: `group_b_opt_balanced_cash20_llm_pva`
- Source: `results/group_b_latest_no2884_backtest_20240101_20260605.json`
- Tickers: `0056.TW`, `00646.TW`, `00679B.TWO`, `00713.TW`, `00751B.TWO`, `00878.TW`
- `2884.TW` is not present in the latest Group B payload, so no runtime removal was needed.

Combined portfolio:

- Group A initial capital: `1,000,000`
- Group B initial capital: `1,000,000`
- Initial total: `2,000,000`
- This is equivalent to the existing dual-group 50/50 initial-capital convention.

## Results

Main combined metrics use geometric annual return from the combined daily curve.

| Strategy | Final value | Annual return | Sharpe | MDD | Volatility |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Group A + Group B 50/50` | `5,302,898` | `49.61%` | `2.5736` | `-18.48%` | `16.95%` |
| `Group A latest` | `3,104,211` | `59.68%` | `2.1641` | `-26.43%` | `23.98%` |
| `Group B latest no-2884` | `2,198,687` | `38.48%` | `2.6347` | `-13.69%` | `13.27%` |

## Interpretation

The 50/50 Group A + Group B portfolio materially improves risk-adjusted behavior versus standalone Group A:

- MDD improves from `-26.43%` to `-18.48%`
- Volatility falls from `23.98%` to `16.95%`
- Sharpe improves from `2.1641` to `2.5736`

The tradeoff is lower return than pure Group A, but the combined curve is much smoother.

## Outputs

- `results/group_ab_latest_no2884_backtest_20240101_20260605.json`
- `results/group_ab_latest_no2884_backtest_20240101_20260605.csv`
- `results/group_ab_latest_no2884_backtest_20240101_20260605_curve.csv`
- `results/group_a_tdcc_latest_backtest_20240101_20260605.json`
- `results/group_b_latest_no2884_backtest_20240101_20260605.json`
