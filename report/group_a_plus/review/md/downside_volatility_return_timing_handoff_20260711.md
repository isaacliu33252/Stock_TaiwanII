# Downside Volatility Return-Timing Test Handoff

Date: 2026-07-11

Paper: Wang & Yan (2021, Journal of Banking and Finance), "Downside risk and
the performance of volatility-managed portfolios"

## What the paper claims

Volatility-managed portfolios (position size ~ 1/lagged volatility) scaled by
**downside volatility** (semivariance from negative-return days only)
significantly outperform those scaled by **total volatility**, across
spanning regressions, real-time (out-of-sample) trading strategies, and
direct Sharpe-ratio comparisons, for 9 equity factors and 94 anomalies
(1926-2018 US data). Decomposing the alpha into volatility-timing
(persistence) and return-timing (does lagged vol predict future returns)
components: total volatility has near-zero/ambiguous return-timing power
(positive in only 42/94 anomalies), while downside volatility reliably,
negatively predicts future returns (positive return-timing component in
71/94 anomalies) -- that asymmetry is what drives the outperformance. A
second, independent lesson: real-time combination strategies with **fixed**
weights (e.g. 50/50) beat strategies that estimate "optimal" weights in real
time, because of parameter instability/estimation risk -- the same lesson
already reflected in this project's `ncf.py` blend_live_auc constant-weight
design and `garch_regime_shadow.py`'s discrete fixed reference-scale buckets.

## What was tested

`group_a_plus/integrations/garch_regime_shadow.py`'s `volatility_gate_reference`
(shadow-only, "must not be consumed by live allocation until it passes
separate walk-forward promotion") is gated by a **symmetric** GARCH(1,1)-proxy
volatility measure (`_garch_proxy_vol` in
`scripts/backtest/backtest_group_a_plus_financial_econometrics.py`) --
exactly the "total volatility" the paper contrasts against downside
volatility. Before investing in the heavier walk-forward trading-curve
machinery (`garch_specialist_routing_walkforward_20260705.py`) to test a
downside-vol-based regime gate, this session ran a cheap, direct test of the
paper's actual mechanism first: does downside volatility have more
return-timing power than total volatility for 0050.TW?

Built:
- `_garch_proxy_vol_downside` added alongside `_garch_proxy_vol` in
  `scripts/backtest/backtest_group_a_plus_financial_econometrics.py` --
  same GARCH(1,1)-style recursion, but the shock term only fires on
  negative-return days (asymmetric/GJR-style), following the paper's Section
  3.5.4 daily exponential-smoothing downside estimator. `_garch_features`
  extended with three new columns (`garch_proxy_vol_downside_0050/_ratio/_percentile`),
  purely additive -- no existing column or caller changed.
- `tests/test_backtest_group_a_plus_financial_econometrics_downside.py` --
  3 tests (decays toward baseline on all-up-day series; matches the
  symmetric proxy exactly on all-down-day series; positive and index-aligned).
- `scripts/evaluate/evaluate_downside_vol_return_timing.py` -- regresses
  forward h-day return on the lagged, causal 252d rolling percentile of each
  vol proxy (total vs downside), h = 5/10/20, with a Newey-West (Bartlett
  kernel, lag=h-1) HAC t-statistic -- same style as `diebold_mariano_test`
  added earlier this session, applied to a return-predictability regression
  instead of a loss differential.

## Result (0050.TW, 2013-01-01 to 2026-07-09)

| h | total_vol slope | t | p | downside_vol slope | t | p |
|---|---|---|---|---|---|---|
| 5 | +0.0018 | +0.59 | 0.557 | +0.0010 | +0.34 | 0.736 |
| 10 | +0.0028 | +0.45 | 0.650 | +0.0023 | +0.39 | 0.694 |
| 20 | +0.0062 | +0.51 | 0.609 | +0.0050 | +0.40 | 0.688 |

**No significant return-timing effect for either measure at any horizon (all
p > 0.55), and downside volatility does not show the paper's expected
asymmetric edge over total volatility here** -- both slopes are weakly
*positive* (the opposite sign from what would make vol-scaling profitable),
and downside's slope is not more negative than total's at any horizon.

## Follow-up: 00631L.TW (same day)

Tested the one specific alternative flagged above (leveraged product, more
volatility-sensitive) rather than searching across tickers. Same script,
`--ticker 00631L.TW --start 2015-01-05` (full available history):

| h | total_vol slope | t | p | downside_vol slope | t | p |
|---|---|---|---|---|---|---|
| 5 | +0.0066 | +1.12 | 0.262 | +0.0047 | +0.79 | 0.430 |
| 10 | +0.0130 | +1.13 | 0.258 | +0.0103 | +0.90 | 0.366 |
| 20 | +0.0202 | +0.89 | 0.373 | +0.0192 | +0.85 | 0.395 |

Same null pattern: no significance at any horizon (all p>0.25), both slopes
still weakly positive (wrong sign), downside still not more negative than
total. t-statistics are somewhat larger than 0050's (~0.8-1.1 vs ~0.3-0.6)
but nowhere near the ~2.0 threshold for even 10% significance. This confirms
the null result is not specific to 0050 -- it replicates on the one other
ticker that had an a-priori reason (leverage/volatility-sensitivity) to show
a stronger effect if the mechanism were present. Saved to
`results/downside_vol_return_timing_00631l_latest.json`.

This closes the "try a different ticker" branch too: both the market-tracking
ETF and its leveraged variant show the same null. Do not test further
tickers without a new, specific reason to expect a different result --
otherwise this becomes exactly the unprincipled multi-try search this
project's memory already warns against.

## Interpretation

- Not a contradiction of the paper, just underpowered / consistent with a
  small true effect. The paper's own MKT-factor (closest analog to a
  broad-market ETF like 0050) return-timing component was already the
  *smallest* and *least distinctly-improved* of the nine factors (Table 5:
  total 0.09%/yr vs downside 0.79%/yr, both tiny next to MOM's 2.88%/1.34% or
  BAB's 0.51%/2.33%), estimated over ~90 years of monthly US data. 0050.TW
  only has ~13 years of daily history since inception -- far too little power
  to detect an effect that was already marginal for the closest-matching
  factor in a dataset 7x longer.
- Do not chase this by trying other tickers/horizons/percentile windows until
  something turns significant -- that is exactly the multi-round,
  no-correction search this project has been burned by before (see
  `feedback_overfitting_fixed_window_tuning`). This was one pre-registered
  test of the paper's actual mechanism; it came back null.

## Decision

Do not build the downside-vol regime gate or invest in the walk-forward
trading-curve evaluation. The premise (downside vol predicts 0050's future
returns better than total vol) did not hold up in the cheap direct test that
was supposed to justify that investment.

- Yes: `_garch_proxy_vol_downside` and its features/tests are kept (harmless,
  additive, tested). Both 0050.TW and 00631L.TW tested null; no further
  ticker to try without a new specific reason.
- No: any change to `garch_regime_shadow.py`'s gate, `_garch_selector_regime`,
  `_garch_guard_regime`, or any production weight.
- The "fixed weight beats optimized weight in real time" lesson from this
  paper needs no new action -- it's already the design pattern used by
  `ncf.py`'s `blend_live_auc` and `garch_regime_shadow.py`'s discrete
  reference-scale buckets.

## Verification

- `.venv/bin/python -m pytest tests/test_backtest_group_a_plus_financial_econometrics_downside.py tests/test_group_a_plus_garch_regime_shadow.py` -- 13 passed (10 pre-existing + 3 new), confirming the additive change to `_garch_features` did not break the existing shadow module.
- `.venv/bin/python -m py_compile scripts/backtest/backtest_group_a_plus_financial_econometrics.py scripts/evaluate/evaluate_downside_vol_return_timing.py` -- passed.
- `.venv/bin/python scripts/evaluate/evaluate_downside_vol_return_timing.py` -- results above, saved to `results/downside_vol_return_timing_latest.json`.
