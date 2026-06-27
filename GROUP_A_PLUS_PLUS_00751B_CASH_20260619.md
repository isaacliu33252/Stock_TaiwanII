# GroupA++ 00751B vs Cash Evaluation - 2026-06-19

## Input

- Workbook: `taiwan_stock_20260619.xlsx`
- Detected Group A++ holdings:
  - `0050.TW`: 1342 shares
  - `00679B.TWO`: 5000 shares
  - `00751B.TWO`: 4000 shares
- Latest local price date: 2026-06-18

## Current GroupA++ market value

| ticker | shares | latest close | value | weight |
| --- | ---: | ---: | ---: | ---: |
| `0050.TW` | 1342 | 107.30 | 143996.60 | 35.27% |
| `00679B.TWO` | 5000 | 27.04 | 135200.00 | 33.12% |
| `00751B.TWO` | 4000 | 32.26 | 129039.99 | 31.61% |

## Method

Compared four static curves:

- GroupA++ with current `00751B`.
- GroupA++ replacing `00751B` with zero-yield cash.
- `00751B` only.
- zero-yield cash replacing the `00751B` position.

Cash replacement uses the `00751B` position value on the first backtest date. Local OHLCV close data is price-only unless distributions are already reflected in the stored close series.

## Results

### 2020-01-02 ~ 2026-06-18

| scenario | final | total return | Sharpe | MDD |
| --- | ---: | ---: | ---: | ---: |
| GroupA++ with `00751B` | 408237 | -4.85% | 0.003 | -41.03% |
| GroupA++ with `00751B` as cash | 465437 | 8.48% | 0.214 | -25.06% |
| `00751B` only | 129040 | -30.71% | -0.335 | -44.40% |
| cash replacing `00751B` | 186240 | 0.00% | 0.000 | 0.00% |

`00751B` vs cash impact:

- `00751B` final value minus cash: -57200
- Portfolio total return drag: -13.33 percentage points

### 2025-01-02 ~ 2026-06-18

| scenario | final | total return | Sharpe | MDD |
| --- | ---: | ---: | ---: | ---: |
| GroupA++ with `00751B` | 408237 | 19.57% | 1.035 | -14.68% |
| GroupA++ with `00751B` as cash | 413517 | 21.12% | 1.615 | -8.41% |
| `00751B` only | 129040 | -3.93% | -0.141 | -16.38% |
| cash replacing `00751B` | 134320 | 0.00% | 0.000 | 0.00% |

`00751B` vs cash impact:

- `00751B` final value minus cash: -5280
- Portfolio total return drag: -1.55 percentage points

## Judgment

- Based on local close-only data, `00751B` is not better than cash for the current GroupA++ position.
- Replacing `00751B` with cash improves both recent and long-term portfolio MDD.
- The result is particularly clear over 2020~2026, where `00751B` price-only return is materially negative.
- Caveat: this test does not add cash distributions from `00751B`. If a total-return result is required, the next step is to import ETF distribution history and rerun a total-return version.

## Outputs

- `results/group_a_plus_plus_00751b_cash_2020_2026_20260619.json`
- `results/group_a_plus_plus_00751b_cash_2020_2026_20260619_curve.csv`
- `results/group_a_plus_plus_00751b_cash_2025_2026_20260619.json`
- `results/group_a_plus_plus_00751b_cash_2025_2026_20260619_curve.csv`
- `taiwan_stock_20260619_groupA++_00751B_eval.xlsx`
- `taiwan_stock_20260619_groupA++_00751B_eval_2025_2026.xlsx`
