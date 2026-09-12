# Review: 2510.03236 Regime-Switching Volatility Forecast for Group A+

## Scope

- Paper: `Improving S&P 500 Volatility Forecasting through Regime-Switching Methods`
- Source file: `C:/Users/isaac/Downloads/2510.03236.pdf`
- arXiv: `2510.03236v1`
- PDF date: 2025-10-07
- Review date: 2026-08-08
- Group A+ rule: `golden1_0531` is fixed and must not be modified. Any import
  can only be research/shadow first, then latest-strategy candidate after
  separate backtest, OOS, trade replay, and approval.

## Paper Summary

The paper improves S&P 500 realized-volatility forecasting with
regime-switching HAR extensions. It uses eleven years of SPX 5-minute data to
compute daily realized volatility, then compares:

- baseline HAR;
- feature-engineered HAR with VIX, realized kurtosis, and jump variation;
- soft Markov regime-switching HAR;
- distributional clustering with Mood-test segments, Wasserstein distance,
  spectral clustering, and XGBoost regime assignment;
- coefficient-based soft clustering using segment-level HAR coefficients,
  PCA, Bayesian Gaussian mixture probabilities, and XGBoost soft regime
  prediction.

The best result is the coefficient-based soft clustering method. It lowered MSE
versus standard HAR in pre-COVID, COVID, and post-COVID periods. The paper also
shows that dual-recursive RV/VIX forecasting improves multi-horizon forecasts in
many windows, while distributional clustering is more robust during crisis-like
structural breaks.

## Useful Ideas For Group A+

Useful and transferable:

- soft volatility-regime probabilities instead of hard high/low-vol labels;
- coefficient-based regime clustering, because it clusters by the relationship
  between features and future volatility rather than raw volatility level only;
- VIX or VIX-like forward-looking volatility input;
- realized kurtosis and jump variation as tail/shock features;
- Mood-test variance-shift segmentation as a structural-break detector;
- separate evaluation for normal and crisis/stress windows;
- recursive multi-horizon forecast discipline that avoids look-ahead by using
  forecasted VIX/RV values inside future steps.

Potential Group A+ use:

- improve the existing HAR-RV forecast module;
- create a research-only regime-switching volatility forecast shadow;
- add an advisory signal to the volatility pre-trade guard;
- make `00631L.TW` add-blocking more state-aware;
- improve `00632R.TW` hedge review timing by detecting jump/stress regimes;
- enrich LLM state/reward feature catalog with `soft_vol_regime_prob`,
  `coefficient_regime_id`, `jump_variation`, and `realized_kurtosis`.

## Not Suitable For Direct Import

Do not directly import:

- SPX paper performance as Taiwan ETF evidence;
- a live XGBoost/HMM allocator;
- automatic `00631L.TW` reduction or addition;
- automatic `00632R.TW` hedge opening;
- intraday 5-minute realized-volatility dependency as mandatory live input;
- coefficient-clustering thresholds tuned on the full sample.

Reasons:

- Group A+ trades Taiwan ETFs, not SPX directly;
- local data currently appears daily/OHLC based for most production paths;
- `0050.TW`, `00631L.TW`, and `00632R.TW` have leverage and path-dependency
  mechanics that are not covered by the paper;
- live decisions require transaction-cost, turnover, OOS, and execution replay
  checks;
- `golden1_0531` is fixed by user instruction.

## Existing Local Overlap

The paper overlaps with current Group A+ modules:

- `group_a_plus/integrations/volatility_forecast.py`
  - existing HAR-RV forecast using Garman-Klass variance;
  - h=5/10/20 direct multi-horizon forecasts;
  - no target-weight mutation.
- `group_a_plus/integrations/garch_regime_shadow.py`
  - existing GARCH-proxy volatility regime shadow;
  - advisory-only `high_vol_defensive`, `neutral_vol`, and
    `low_vol_participation` metadata.
- `scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py`
  - existing research-only no-add audit for `00631L.TW`.
- `group_a_plus/integrations/network_volatility_forecast_shadow.py`
  - existing network/HAR volatility shadow work.

So the paper does not introduce a brand-new trading strategy. Its value is an
upgrade path for the existing volatility forecast and volatility gate.

## Recommended Import Plan

### Phase 1: Shadow Feature Prototype

Create a research-only module, for example:

- `group_a_plus/integrations/regime_switching_volatility_shadow.py`

Suggested outputs:

- `baseline_har_forecast_h5/h10`;
- `feature_har_forecast_h5/h10`;
- `soft_markov_regime_prob_low/mid/high`;
- `coefficient_cluster_regime_prob_0/1/2`;
- `realized_kurtosis`;
- `jump_variation`;
- `vol_regime_confidence`;
- `policy = shadow_only_no_weight_change`.

Minimum rule:

- output must not include target weights;
- output must not modify execution regime;
- output must not create broker orders;
- output must preserve `golden1_0531`.

### Phase 2: Forecast Quality Backtest

Compare against the current local HAR-RV forecast and naive persistence:

- QLIKE loss;
- MSE / MAE;
- directional high-vol hit rate;
- crisis-window false-negative rate;
- no-lookahead truncation test;
- walk-forward split, not full-sample tuning.

Required windows:

- 2020 COVID-style shock window if local Taiwan data is available;
- 2022 bear/stress window;
- 2024-2026 recent live-like window;
- a latest holdout window not used for parameter selection.

### Phase 3: Guard-Only Evaluation

If forecast quality passes, test only as a pre-trade guard:

- block new `00631L.TW` adds in high predicted-vol / high jump regime;
- do not force sell existing `00631L.TW`;
- optionally require manual review before large `00632R.TW` hedge opens;
- compare against current volatility gate and no-add guard.

Promotion metric should be risk-first:

- reduce worst 5/10/20-day forward drawdown;
- avoid materially lowering total return;
- avoid excessive blocked-add events;
- no increase in max drawdown;
- transaction-cost and turnover included.

### Phase 4: Latest Strategy Candidate

Only after Phase 1-3 pass:

- add as latest-strategy guarded candidate, not golden;
- require signed/manual approval package;
- keep live default disabled until monitored trigger evidence accumulates.

## Current Decision

Status: `research_shadow_imported_forecast_quality_blocked`.

Import conclusion:

- Yes, the paper has useful ideas for Group A+.
- The useful import is a regime-switching volatility forecast shadow and
  stronger volatility pre-trade guard evidence.
- The first daily-OHLC coefficient-clustering implementation does not pass
  forecast-quality validation on `0050.TW`.
- No direct live strategy, guard activation, or weight change should be made
  now.
- No change to `golden1_0531`.
- No change to latest strategy at this review step.

## Implemented Shadow Artifacts

Implemented after the initial review:

- `group_a_plus/integrations/regime_switching_volatility_shadow.py`
- `tests/test_group_a_plus_regime_switching_volatility_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py`
- `tests/test_evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime1.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime3.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime1.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime3.json`

The module is research-only and exports:

- `policy = shadow_only_no_weight_change`;
- soft volatility-regime probabilities;
- coefficient-clustered volatility forecasts;
- realized kurtosis and jump-variation proxies;
- no target weights;
- no target shares;
- no execution regime;
- no broker-order output.

Second-pass data augmentation was added to the evaluation script:

- `^VIX` level/change from `external_market_ohlcv`;
- TXO put/call volume ratio z-score;
- TXO put/call open-interest ratio z-score;
- TXO put/call premium ratio z-score;
- TX front-month futures percent-change z-score;
- TX front-month futures volume z-score;
- TX front-month futures open-interest change z-score.

All augmented features are shifted by one trading day before use to avoid
same-day look-ahead.

## Forecast Quality Result

Validation command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json --rolling-window 504 --n-regimes 2
```

Result versus the existing local HAR-RV forecast:

| Horizon | Rows | QLIKE improvement vs HAR-RV | Win rate vs HAR-RV |
| --- | ---: | ---: | ---: |
| 5 | 1,928 | -182.07% | 0.295 |
| 10 | 1,918 | -140.62% | 0.285 |
| 20 | 1,898 | -65.18% | 0.354 |

Parameter checks:

- `n_regimes=1`: still failed versus HAR-RV at all horizons;
- `n_regimes=3`: still failed versus HAR-RV at all horizons;
- 1%/99% training-window forecast clipping reduced extreme overfit but did not
  create usable edge.

Augmented-feature validation command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json --rolling-window 504 --n-regimes 2 --use-augmented-features
```

Augmented-feature result versus HAR-RV:

| Variant | h=5 QLIKE vs HAR-RV | h=10 QLIKE vs HAR-RV | h=20 QLIKE vs HAR-RV |
| --- | ---: | ---: | ---: |
| `n_regimes=1` | -169.98% | -65.19% | -41.97% |
| `n_regimes=2` | -257.84% | -107.86% | -60.54% |
| `n_regimes=3` | -246.85% | -78.26% | -45.25% |

Interpretation of augmentation:

- Existing TAIFEX/VIX data can be connected, but it does not rescue the
  coefficient-clustering forecast.
- The best augmented setting (`n_regimes=1`) is still worse than the existing
  HAR-RV forecast at all horizons.
- Do not connect augmented regime-switching output to the pre-trade guard.

Interpretation:

- The framework is useful as a research harness.
- The first daily-OHLC proxy implementation is not useful enough for guard or
  latest-strategy promotion.
- The likely gap is paper-data mismatch: the paper uses SPX 5-minute realized
  volatility and VIX, while this first Group A+ implementation uses daily OHLC
  and no true Taiwan implied-volatility input.

Verification:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_regime_switching_volatility_shadow.py tests/test_evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py tests/test_group_a_plus_volatility_forecast.py
# 15 passed

.venv/bin/python -m py_compile group_a_plus/integrations/regime_switching_volatility_shadow.py scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py
# passed
```

## Next Step

Recommended next engineering step if continuing this paper:

1. Do not connect this shadow to the current pre-trade guard.
2. Try a second pass only if better inputs are available:
   Taiwan intraday realized volatility, Taiwan implied-volatility proxy, or
   option/TAIFEX volatility features.
3. If no better inputs are available, leave this paper as a blocked research
   artifact and keep using the existing HAR-RV / GARCH-proxy guard stack.
