# 2604.27287v1 Leveraged ETF Anomaly - GroupA+ Review

Date: 2026-08-21

Source PDF: `C:\Users\isaac\Downloads\2604.27287v1.pdf`

Paper: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`

## Decision

Useful for GroupA+, but only as a shadow diagnostic. Do not change latest
strategy, golden1_0531, daily signals, execution plans, or orders from this
paper alone.

## Paper Takeaway

The paper decomposes long-horizon levered ETF performance into:

- underlying arithmetic return;
- underlying volatility and compounding drag;
- target leverage;
- covariance between realized effective return ratio and underlying return.

The last item is the main importable idea. A levered ETF may have an average
daily return ratio near its target, but if that ratio is higher on underlying
down days and lower on underlying up days, long-horizon performance can be worse
than a constant-leverage estimate.

## GroupA+ Relevance

GroupA+ already has 00631L compounding, volatility, GARCH, BAWS, crash-risk, and
no-add diagnostics. Those cover volatility, path dependency, and downside
states. This paper adds a more specific realized-leverage timing diagnostic:

- realized effective leverage: `ETF daily return / 0050 daily return`;
- winsorized ratio handling for tiny 0050 moves;
- annualized covariance between effective leverage and 0050 return;
- gap between observed ETF arithmetic return and constant-leverage arithmetic
  estimate;
- geometric approximation with volatility drag.

This can support manual review before adding 00631L or 00632R, but it is not an
alpha model and has no forward prediction proof in Taiwan ETF data yet.

## Implemented

- `group_a_plus/integrations/leveraged_etf_timing_anomaly.py`
- `scripts/evaluate/evaluate_group_a_plus_leveraged_etf_timing_anomaly.py`
- `tests/test_leveraged_etf_timing_anomaly.py`

Expected output paths when the evaluator is run:

- `results/group_a_plus_leveraged_etf_timing_anomaly_2604_27287.json`
- `results/group_a_plus_leveraged_etf_timing_anomaly_2604_27287.csv`
- `report/group_a_plus/latest/leveraged_etf_timing_anomaly_2604_27287.md`

## 2026-08-21 Run Result

Window: 2015-01-05 through 2026-08-20, 2,828 aligned rows, 252-day rolling
window.

00631L.TW:

- full-sample average effective leverage: 1.671 vs target 2.0;
- full-sample ratio-return covariance: +9.16% annualized;
- latest 252-day ratio-return covariance: -21.41% annualized;
- latest rolling warnings: negative ratio-return covariance and large volatility
  drag;
- decision: shadow warning for manual 00631L/00632R review, no automatic weight
  change.

00632R.TW:

- full-sample average effective leverage: -0.736 vs target -1.0;
- full-sample ratio-return covariance: -8.47% annualized;
- latest 252-day ratio-return covariance: +10.05% annualized;
- full-sample warnings: negative ratio-return covariance, average effective
  leverage away from target, and large volatility drag;
- decision: shadow warning for manual 00631L/00632R review, no automatic weight
  change.

Validation:

- `.venv/bin/python -m pytest tests/test_leveraged_etf_timing_anomaly.py -q`
  passed, 4 tests.

## Promotion Boundary

Keep shadow unless a separate multi-window promotion backtest proves that the
timing-anomaly warning improves after-cost final value, Sharpe, and max drawdown
for GroupA+ latest strategy. A signed promotion review is required before any
target-weight or execution-guard wiring.

## Next-Step Backtest Added

Added a research-only promotion backtest:

- `scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py`
- `tests/test_leveraged_etf_timing_guard_backtest.py`

The backtest uses previous-day warnings only, then replays latest strategy with
three variants:

- `00631l_only`: move guarded 00631L weight into 0050;
- `00632r_only`: move guarded 00632R weight into cash;
- `combined`: apply both rules.

Promotion requires every tested window to improve after-cost final value,
Sharpe, Sortino, and not worsen max drawdown. Passing this script still does
not auto-promote; it only allows manual review.

## Backtest Result

Run output:

- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.json`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.csv`
- `report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287.md`

Decision: `do_not_promote_keep_shadow`.

Variant summary:

- `00631l_only`: promotion-ready in 1 of 4 windows; average delta final value
  -16,479.54; average delta Sharpe +0.0028.
- `00632r_only`: promotion-ready in 0 of 4 windows; average delta final value
  -55,429.51; average delta Sharpe -0.0134.
- `combined`: promotion-ready in 0 of 4 windows; average delta final value
  -68,331.38; average delta Sharpe -0.0064.

Window highlights:

- 2016-2026 full window: all variants reduce final value.
- 2022-2023 rate-hike window: all variants reduce final value and Sharpe.
- 2024-2026 live window: `00631l_only` improves final value by +3,293.52 and
  passes that single window.
- 2025-2026 active window: `00631l_only` reduces final value by -39,755.34 even
  though Sharpe/Sortino rise.

Conclusion: the paper's timing-anomaly idea is useful as a diagnostic and manual
warning, but the tested guard is not robust enough for latest strategy
promotion.

Validation:

- `.venv/bin/python -m pytest tests/test_leveraged_etf_timing_anomaly.py tests/test_leveraged_etf_timing_guard_backtest.py -q`
  passed, 6 tests.

## Refinement Sweep

After the first backtest failed, the warning logic was parameterized:

- `any_warning`: original behavior;
- `negative_covariance`: only trigger when rolling effective-leverage/0050
  return covariance is below threshold;
- `negative_covariance_and_large_drag`: require negative covariance and large
  volatility drag;
- `persistence_days`: require N consecutive warning days.

Two stricter runs were tested:

1. `negative_covariance`, persistence 1:
   - output:
     `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov.json`;
   - decision: `do_not_promote_keep_shadow`;
   - best average-final-value mode: `00632r_only`, but average delta final value
     still -21,600.62;
   - `00631l_only` still only passes 2024-2026 and loses -39,755.34 in
     2025-2026.

2. `negative_covariance_and_large_drag`, persistence 3:
   - output:
     `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.json`;
   - decision: `do_not_promote_keep_shadow`;
   - `00632R` warning count is much lower, but `00632r_only` average delta final
     value remains -5,632.43 and worsens worst max drawdown by -0.31%;
   - `00631l_only` improves 2024-2026 by +3,985.44 but still loses -39,493.19 in
     2025-2026 and -91,863.54 in 2016-2026.

Refined conclusion: stricter triggers improve noise control but still do not
solve the core robustness problem. Stop promotion work for this paper unless a
new hypothesis uses a different action than full 00631L-to-0050 or
00632R-to-cash shifting.

Validation after refinement:

- `.venv/bin/python -m pytest tests/test_leveraged_etf_timing_anomaly.py tests/test_leveraged_etf_timing_guard_backtest.py -q`
  passed, 7 tests.
