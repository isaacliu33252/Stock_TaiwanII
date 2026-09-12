# Handoff: 2510.03236 Regime-Switching Volatility Forecast for Group A+

## Bottom Line

`C:/Users/isaac/Downloads/2510.03236.pdf` has useful research ideas, but the
first Group A+ implementation does not pass forecast-quality validation.

Keep:

- `golden1_0531` unchanged;
- latest strategy unchanged;
- no automatic rebalance;
- no automatic `00631L.TW` add/reduce;
- no automatic `00632R.TW` hedge open.

Current status:

- `research_shadow_imported_forecast_quality_blocked`
- second-pass TAIFEX/VIX data augmentation also failed versus existing HAR-RV.

## Final Session Summary

This session answered the question: can missing data be supplemented enough to
make the paper usable for Group A+?

Answer: data can be supplemented technically, but the supplemented model still
does not beat the existing HAR-RV forecast. Therefore the paper remains
blocked for latest-strategy import.

Important distinction:

- The research framework is retained.
- The forecast output is rejected for guard/promotion use.
- No strategy weight, target-share, execution-regime, or broker-order path was
  connected.

## Paper Advantage Imported

Imported as research-only shadow:

- coefficient-based volatility-regime clustering;
- soft volatility-regime probabilities;
- Mood-test-style variance-shift segmentation proxy;
- realized kurtosis proxy;
- jump-variation proxy;
- walk-forward no-lookahead forecast quality evaluation.

Second pass imported only as evaluation features:

- TAIFEX TXO put/call volume pressure;
- TAIFEX TXO put/call open-interest pressure;
- TAIFEX TXO put/call premium pressure;
- TAIFEX TX front-month futures return / volume / OI pressure;
- `^VIX` level and 5-day change pressure.

These are not live signals. They are only offline forecast-quality inputs.

Not imported:

- SPX paper performance as Group A+ evidence;
- HMM/XGBoost live allocator;
- target-weight output;
- execution-regime output;
- broker-order output;
- live guard activation.

## Files Created Or Updated

Created:

- `group_a_plus/integrations/regime_switching_volatility_shadow.py`
- `tests/test_group_a_plus_regime_switching_volatility_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py`
- `tests/test_evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py`
- `docs/REVIEW_2510_03236_REGIME_SWITCHING_VOL_FORECAST_GROUPA_PLUS_20260808.md`
- `docs/HANDOFF_2510_03236_REGIME_SWITCHING_VOL_FORECAST_GROUPA_PLUS_20260808.md`

Generated:

- `results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime1.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime3.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime1.json`
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime3.json`

Updated:

- `group_a_plus/integrations/regime_switching_volatility_shadow.py`
  - added `extra_features`;
  - added external feature passthrough with `extra_` prefix;
  - kept `policy = shadow_only_no_weight_change`;
  - kept snapshot contract with `outputs_target_weights = false` and
    `outputs_execution_regime = false`.
- `scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py`
  - added `--use-augmented-features`;
  - added TAIFEX/VIX feature loader;
  - all added features are shifted by one trading day.
- `tests/test_group_a_plus_regime_switching_volatility_shadow.py`
  - added extra-feature coverage.
- `docs/REVIEW_2510_03236_REGIME_SWITCHING_VOL_FORECAST_GROUPA_PLUS_20260808.md`
  - updated from initial review to final blocked result after data
    augmentation.

## Validation Results

Main command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json --rolling-window 504 --n-regimes 2
```

Main result versus existing HAR-RV:

| Horizon | Rows | QLIKE improvement vs HAR-RV | Win rate vs HAR-RV |
| --- | ---: | ---: | ---: |
| 5 | 1,928 | -182.07% | 0.295 |
| 10 | 1,918 | -140.62% | 0.285 |
| 20 | 1,898 | -65.18% | 0.354 |

Plain-feature result files:

- `results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json`
  - `n_regimes=2`;
  - failed versus HAR-RV at h=5/10/20.
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime1.json`
  - `n_regimes=1`;
  - still failed versus HAR-RV at h=5/10/20.
- `results/group_a_plus_regime_switching_volatility_forecast_quality_regime3.json`
  - `n_regimes=3`;
  - still failed versus HAR-RV at h=5/10/20.

Parameter checks:

- `n_regimes=1`: failed versus HAR-RV at all horizons.
- `n_regimes=2`: failed versus HAR-RV at all horizons.
- `n_regimes=3`: failed versus HAR-RV at all horizons.
- Forecast clipping at the training-window 1%/99% target quantiles reduced
  extreme extrapolation but did not make the signal useful.

Second-pass augmented features:

- `txo_pcr_volume_z20`;
- `txo_pcr_oi_z20`;
- `txo_put_call_premium_z20`;
- `tx_front_pct_change_z20`;
- `tx_front_volume_z20`;
- `tx_front_oi_chg_z20`;
- `vix_level_z60`;
- `vix_chg5_z60`.

All augmented features are shifted one trading day to avoid look-ahead.

Data source status checked before augmentation:

- `ohlcv`
  - `0050.TW`: 2009-01-02 to 2026-08-07;
  - `00631L.TW`: 2014-10-23 to 2026-08-07;
  - `00632R.TW`: 2014-10-23 to 2026-08-07.
- `external_market_ohlcv`
  - `^VIX`: 1990-01-02 to 2026-08-06;
  - `SOXX`, `QQQ`, `TSM`, `TWD=X`, `^TWII`: available through 2026-08-06
    or nearby dates depending on market calendar.
- `taifex_options_daily`
  - 2020-01-02 to 2026-08-06;
  - about 3,091,462 rows at the time checked;
  - no direct implied-volatility column, so only option pressure proxies were
    used.
- `taifex_futures_daily`
  - 1998-07-21 to 2026-08-06.
- `external_options_iv`
  - SOXX only, 2026-07-10 to 2026-08-06;
  - too short for the long 2018-2026 forecast-quality backtest.

Augmented command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json --rolling-window 504 --n-regimes 2 --use-augmented-features
```

Augmented result versus HAR-RV:

| Variant | h=5 QLIKE vs HAR-RV | h=10 QLIKE vs HAR-RV | h=20 QLIKE vs HAR-RV |
| --- | ---: | ---: | ---: |
| `n_regimes=1` | -169.98% | -65.19% | -41.97% |
| `n_regimes=2` | -257.84% | -107.86% | -60.54% |
| `n_regimes=3` | -246.85% | -78.26% | -45.25% |

Augmented result files:

- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json`
  - `n_regimes=2`;
  - h=5/10/20 all failed versus HAR-RV.
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime1.json`
  - `n_regimes=1`;
  - best augmented variant, but still failed versus HAR-RV at all horizons.
- `results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime3.json`
  - `n_regimes=3`;
  - failed versus HAR-RV at all horizons.

Conclusion after augmentation:

- TAIFEX/VIX data can be added technically.
- It did not improve enough to beat HAR-RV.
- Keep blocked; do not wire to any guard.

## Commands Run

Core tests:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_regime_switching_volatility_shadow.py tests/test_evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py
# 9 passed
```

Compile check:

```bash
.venv/bin/python -m py_compile group_a_plus/integrations/regime_switching_volatility_shadow.py scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py
# passed
```

Plain-feature validation:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json --rolling-window 504 --n-regimes 2

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_regime1.json --rolling-window 504 --n-regimes 1

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_regime3.json --rolling-window 504 --n-regimes 3
```

Augmented-feature validation:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_latest.json --rolling-window 504 --n-regimes 2 --use-augmented-features

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime1.json --rolling-window 504 --n-regimes 1 --use-augmented-features

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py --ticker 0050.TW --start 2018-01-02 --end 2026-08-07 --output results/group_a_plus_regime_switching_volatility_forecast_quality_augmented_regime3.json --rolling-window 504 --n-regimes 3 --use-augmented-features
```

## Tests

Passed:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_regime_switching_volatility_shadow.py tests/test_evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py tests/test_group_a_plus_volatility_forecast.py
# 15 passed

.venv/bin/python -m py_compile group_a_plus/integrations/regime_switching_volatility_shadow.py scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py
# passed
```

## Why Blocked

The paper uses SPX 5-minute realized volatility and VIX-style forward-looking
volatility inputs. The first Group A+ implementation used daily OHLC proxies
for `0050.TW`; the second pass added TAIFEX option/futures and `^VIX` proxy
features. Both failed versus existing HAR-RV. The remaining likely gap is that
the paper's intraday realized-volatility and true implied-volatility setup is
not replicated by the current local daily data.

The shadow is therefore useful for governance and future experiments, but not
useful enough to improve the current HAR-RV / GARCH-proxy guard stack.

## Do Not Do

- Do not wire this into `apply_group_a_plus_execution_gate.py`.
- Do not use it to block or force sell current `00631L.TW`.
- Do not open `00632R.TW` from this signal.
- Do not modify `golden1_0531`.
- Do not modify latest strategy weights from this result.
- Do not treat TAIFEX/VIX augmentation as passed validation.
- Do not promote `n_regimes=1` merely because it is the least bad variant.
- Do not use `external_options_iv` SOXX history for long OOS validation yet;
  it only covers a short recent window.

## Next Step

Only continue this paper if materially better inputs are available:

- Taiwan ETF intraday realized volatility;
- Taiwan implied-volatility proxy;
- TAIFEX option/futures volatility features;
- robust OOS evidence that beats existing HAR-RV.

Without those inputs, leave this as a blocked research artifact and continue
using the existing volatility stack.
