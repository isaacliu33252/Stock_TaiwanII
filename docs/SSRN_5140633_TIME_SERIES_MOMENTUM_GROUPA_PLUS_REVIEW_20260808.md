# SSRN-5140633 / Time-Series Momentum Return-Timing Review - 2026-08-08

**Status: closed, null result. Research-only, never wired to production.**

This doc was written 2026-08-08 during a full-repo paper-audit action-items
follow-up. The test script and its result JSONs existed since 2026-07-12 with
no accompanying write-up -- this fills that gap using the actual saved
results, not a re-run.

## Reference

Discussion followed AQR's time-series momentum / managed-futures literature:
Hurst, Ooi, and Pedersen (2017), "A Century of Evidence on Trend-Following
Investing"; Baltas and Kosowski (2013); Hutchinson and O'Brien (2014).

Time-series momentum asks whether an asset's OWN sign of trailing return
predicts its OWN future return -- distinct from every other predictability
test in this project (which test volatility asymmetry, tail risk, or
chip/options positioning, never plain own-asset return continuation).

## Script

`scripts/evaluate/evaluate_time_series_momentum_return_timing.py`

Method: same Newey-West/Bartlett-HAC OLS slope test used throughout this
project's return-timing research (`_hac_ols_slope_tstat`, reused from
`evaluate_downside_vol_return_timing.py`). Predictor: trailing L-day return
(L=21/63/252, approximating 1/3/12-month lookbacks). Target: forward h-day
return (h=5/10/20). Positive significant slope -> continuation; negative
significant slope -> mean-reversion; null -> no timing value.

Two caveats noted at the time (still hold):

1. The literature's main diversification story (low cross-correlation across
   67 markets/4 asset classes) does not apply here -- 0050/00631L/00632R are
   direct/leveraged/inverse variants of the same TAIEX-50 underlying, already
   highly correlated. Only the pure return-predictability claim is testable
   with this project's universe, not the diversification claim.
2. Group A+ already implicitly relies on a trend/momentum premise via
   `ma_gap` (price vs moving average) regime classification (golden1 vs
   defensive), but that threshold was set by backtest optimization, not a
   formal significance test. This script was the first formal test of "does
   trailing return predict forward return" for this project.

## Result

Saved outputs (2026-07-12, `--start 2013-01-01 --end 2026-07-09`):

- `results/time_series_momentum_0050_latest.json`
- `results/time_series_momentum_00631l_latest.json`

0050.TW, all 9 lookback x horizon combinations (n=2527-2773):

| Lookback | h=5 | h=10 | h=20 |
|---|---|---|---|
| 1m | p=0.571 | p=0.594 | p=0.692 |
| 3m | p=0.264 | p=0.186 | p=0.145 |
| 12m | p=0.299 | p=0.294 | p=0.300 |

00631L.TW, all 9 combinations (n=2531-2777):

| Lookback | h=5 | h=10 | h=20 |
|---|---|---|---|
| 1m | p=0.757 | p=0.646 | p=0.624 |
| 3m | p=0.752 | p=0.637 | p=0.522 |
| 12m | p=0.646 | p=0.648 | p=0.738 |

Every single p-value is far above 0.05 (smallest is 0.145, on 0050 3m/h=20,
still not close to significant). Signs are mixed (0050 all positive; 00631L
mixed sign at 1m, positive at 3m/12m) with no consistent direction, which is
itself evidence against a real effect rather than for one.

## Interpretation

Null result on both tickers, all lookbacks, all horizons. Own-asset trailing
return does not predict own-asset forward return on 0050.TW or 00631L.TW at
any tested lag. This matches this project's broader, repeatedly-confirmed
pattern that simple return-predictability signals are weak-to-absent on
these specific tickers (see the closed GJR-GARCH, downside-volatility, and
good/bad-volatility return-timing lines in memory).

## Production Decision

No production change. Never wired into any model, gate, or signal. Confirms
(does not newly justify) that `ma_gap`'s golden1/defensive regime threshold
should continue to be validated by backtest/OOS performance rather than
treated as resting on a proven return-continuation effect -- the formal test
run here does not support that premise on a pure own-asset-momentum basis.

Closed. No follow-up planned.
