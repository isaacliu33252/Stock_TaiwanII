# 2606.03828 GNHAR-RV Forecast Prototype Handoff

Date: 2026-07-11

Paper: Network Time Series Models for Multivariate Volatility Forecasting (arXiv:2606.03828v1)

Follow-up to: `2606_03828_network_vol_spillover_shadow_handoff_20260711.md`, which only
built a lagged-correlation risk-alert network, not a real GNHAR forecast model.
This step builds the actual forecasting model the paper proposes and tests
whether it beats the existing univariate HAR-RV forecast for 0050.TW.

## What was built

- `group_a_plus/integrations/network_volatility_forecast_shadow.py` -- pooled
  GNHAR-RV: global-alpha (shared daily/weekly/monthly AR + network
  coefficients across all tickers, node-specific intercept only), fully-connected
  unweighted 1-stage neighbour graph, network order configurable (default (1,0,1):
  daily + monthly network terms, matching the paper's most robust global-alpha
  configuration across all five graph types it tested).
- `scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py`
  -- QLIKE comparison against the existing univariate HAR-RV forecast
  (`volatility_forecast.py`, already in production evaluation) and naive
  persistence, at h=5/10/20, walk-forward with no lookahead.
- `tests/test_group_a_plus_network_volatility_forecast_shadow.py` -- 9 tests
  (shape, no-lookahead, warmup, error handling). All pass.

Default network tickers (same panel as the spillover shadow module):
0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO, 00646.TW, 00713.TW, 00878.TW.

## Result (2018-01-02 to 2026-07-09, target 0050.TW)

Added `diebold_mariano_test` to `risk_sensitive_loss.py` (Harvey et al. 1997
small-sample-corrected DM test, Bartlett-kernel HAC variance with truncation
lag h-1 -- the same test the paper uses in Section 5.4) and wired it into the
evaluation script, to check whether any QLIKE gap is real or noise.

Network order (1,0,1) -- daily + monthly network terms:

| h | GNHAR QLIKE | HAR-RV QLIKE | GNHAR vs HAR | win rate | DM p-value |
|---|---|---|---|---|---|
| 5 | 0.3077 | 0.2861 | -7.56% (worse) | 0.517 | 0.29 |
| 10 | 0.2348 | 0.2435 | +3.58% (better) | 0.541 | 0.57 |
| 20 | 0.2045 | 0.2218 | +7.81% (better) | 0.546 | 0.38 |

Network order (1,1,0) -- daily + weekly network terms (paper's alternative
short-horizon configuration, tested to check whether (1,0,1) simply had the
wrong order for h=5):

| h | GNHAR QLIKE | HAR-RV QLIKE | GNHAR vs HAR | win rate | DM p-value |
|---|---|---|---|---|---|
| 5 | 0.3013 | 0.2842 | -6.02% (worse) | 0.517 | 0.42 |
| 10 | 0.2436 | 0.2416 | -0.83% (worse) | 0.530 | 0.90 |
| 20 | 0.2081 | 0.2196 | +5.27% (better) | 0.527 | 0.60 |

**None of the six horizon/order combinations are significant at 5%.** The
largest apparent edge (+7.81% at h=20, order (1,0,1)) has p=0.38 -- not
distinguishable from noise given the sample's autocorrelation from overlapping
forecast windows.

## Interpretation

- The paper's qualitative pattern (network models widen the gap over
  univariate HAR as horizon grows) partially replicates in the point estimates
  (h=20 > h=10 > h=5 in relative terms), but none of it clears statistical
  significance here -- unlike the paper, where the same order (1,0,1) was
  consistently retained by a formal Model Confidence Set across all five graph
  types on 10 diverse global indices (2013-2022).
- Likely cause of the gap: the paper's network used 10 largely independent
  country indices; this project's 7-ticker panel is mostly derivatives of the
  same underlying index (0050/00631L/00632R are index/leveraged/inverse
  variants of the same TAIEX-50 basket), so "neighbour" volatility is close to
  duplicate information rather than an independent spillover source, and the
  panel likely also has less usable history than the paper's 2013-2022, ~2200
  trading-day window. A genuinely informative network here would need tickers
  with less structural overlap (e.g. sector ETFs, single-name stocks, or a
  non-Taiwan risk-off proxy) -- not tested in this pass.
- h=5 consistently loses to the univariate HAR-RV under both orders tested
  (though not significantly). Do not use GNHAR for short-horizon forecasting
  with this ticker panel.

## Decision

Do not promote to production. Keep as a research module only -- and treat this
specific 7-ETF panel + GNHAR(1,0,1)/(1,1,0) combination as **closed, not just
paused**: the DM test found no significant edge at any tested horizon, so
re-running the same panel/order combination again would not produce a
different answer.

- Yes: module + evaluation script + DM significance test exist, tests pass,
  results saved.
- No: wiring into `volatility_forecast.py`'s multi-horizon output.
- No: wiring into any alert or target-weight logic.
- Open question for a future session, if revisited: does a less-redundant
  ticker panel (e.g. swap 00631L/00632R for genuinely different-sector ETFs
  or single-name stocks) produce a significant DM result where this one did
  not? Untested; would need a new panel, not a re-run of this one.

## Verification

Commands run:

- `.venv/bin/python -m pytest tests/test_group_a_plus_network_volatility_forecast_shadow.py tests/test_group_a_plus_volatility_forecast.py tests/test_group_a_plus_network_volatility_spillover_shadow.py tests/test_group_a_plus_risk_sensitive_loss.py` -- 27 passed.
- `.venv/bin/python -m py_compile group_a_plus/integrations/network_volatility_forecast_shadow.py group_a_plus/integrations/risk_sensitive_loss.py scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py` -- passed.
- `.venv/bin/python scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py` (order (1,0,1) default, and again with `--network-order 1 1 0`) -- results above, saved to `results/group_a_plus_network_volatility_forecast_quality_latest.json` and `results/group_a_plus_network_volatility_forecast_quality_order110.json`.
