# GroupA+ 00631L ML Crash-Risk De-risk Shadow - 2026-07-12

## One-line conclusion

Imported the "forecast crash risk directly with ML, not ordinary up/down
direction" idea as a research-only shadow script. The implementation works,
but the first validation run does **not** justify live de-risk promotion:
both crash labels lose money in most tuning windows and fail the 2017-2019
out-of-sample check, especially 2018.

## Motivation

The user pointed to two downloaded ScienceDirect PDFs:

- `C:\Users\isaac\Downloads\ScienceDirect_articles_12Jul2026_04-16-31.841\Bayesian-forecasting-of-short-term-crash-risk-with-condi_2025_Analytic-Metho.pdf`
- `C:\Users\isaac\Downloads\ScienceDirect_articles_12Jul2026_04-16-31.841\Editorial-Board_2025_Analytic-Methods-in-Accident-Research.pdf`

and explicitly reframed the next attempt as:

> ML should forecast crash risk directly; extreme crash risk -> de-risk.

That is different from the existing ordinary return-direction work and also
different from the previous 00631L race classifier, which asked whether
00631L touches -8% before +12%. This handoff records the direct crash-event
probability version.

## New file

`scripts/evaluate/evaluate_00631l_ml_crash_risk_derisk.py`

Research-only. It does not touch live signal generation, target weights, or
daily execution.

Core design:

- Target is a tail/crash event, not ordinary up/down:
  - `10d_mdd_lt_5pct`: future 10-trading-day 00631L max drawdown < -5%.
  - `20d_mdd_lt_8pct`: future 20-trading-day 00631L max drawdown < -8%.
- Reuses the existing 00631L downside feature set from
  `evaluate_group_a_plus_00631l_downside_race_classifier.py`.
- Reuses the existing no-look-ahead walk-forward classifier discipline:
  504-day train window, 21-day refit cadence, `train_end = i - horizon`.
- Default trigger is sparse: rolling top 5% predicted crash probability
  (`--trigger-mode rolling_quantile --rolling-quantile-level 0.95`).
- When triggered inside golden1, shifts the 00631L.TW weight into 0050.TW.
- Reports forecast quality separately from trading PnL:
  - AUC
  - average precision
  - event rate in top predicted-risk bucket
  - lift vs base event rate
  - backtest delta vs a2118 baseline

## Result artifacts

- `results/00631l_ml_crash_risk_derisk_10d_20260712.json`
- `results/00631l_ml_crash_risk_derisk_20d_20260712.json`

Note: this repo's `.gitignore` excludes `/results/`, so these JSON files are
local run artifacts unless explicitly force-added. The key numbers are copied
into this handoff for portability.

Reproduce with:

```bash
python3 scripts/evaluate/evaluate_00631l_ml_crash_risk_derisk.py --label 10d_mdd_lt_5pct --output results/00631l_ml_crash_risk_derisk_10d_20260712.json
python3 scripts/evaluate/evaluate_00631l_ml_crash_risk_derisk.py --label 20d_mdd_lt_8pct --output results/00631l_ml_crash_risk_derisk_20d_20260712.json
```

## Key validation results

### 10d max drawdown < -5%

Tuning windows:

| Window | AUC | AP | De-risk days | Delta final | Delta Sharpe |
|---|---:|---:|---:|---:|---:|
| covid_2020 | 0.545 | 0.334 | 4/169 | -29,029 | -0.1297 |
| inflation_2022 | 0.594 | 0.581 | 4/67 | -1,411 | -0.0184 |
| live_2024_2026 | 0.540 | 0.328 | 41/539 | -235,451 | +0.0013 |
| active_2025_2026 | 0.565 | 0.357 | 29/297 | -148,234 | -0.0179 |

OOS windows:

| Window | AUC | AP | De-risk days | Delta final | Delta Sharpe |
|---|---:|---:|---:|---:|---:|
| 2017_bull | 0.435 | 0.121 | 0/199 | 0 | 0.0000 |
| 2018_correction | 0.406 | 0.253 | 19/245 | -22,065 | -0.1799 |
| 2019_recovery | 0.558 | 0.136 | 12/241 | -25,831 | -0.1063 |

### 20d max drawdown < -8%

Tuning windows:

| Window | AUC | AP | De-risk days | Delta final | Delta Sharpe |
|---|---:|---:|---:|---:|---:|
| covid_2020 | 0.601 | 0.296 | 4/169 | -19,044 | -0.0817 |
| inflation_2022 | 0.540 | 0.548 | 9/67 | -451 | -0.0166 |
| live_2024_2026 | 0.491 | 0.254 | 39/539 | -300,335 | -0.0183 |
| active_2025_2026 | 0.536 | 0.274 | 27/297 | -211,677 | -0.0878 |

OOS windows:

| Window | AUC | AP | De-risk days | Delta final | Delta Sharpe |
|---|---:|---:|---:|---:|---:|
| 2017_bull | 0.249 | 0.091 | 0/199 | 0 | 0.0000 |
| 2018_correction | 0.420 | 0.225 | 57/245 | -48,737 | -0.4180 |
| 2019_recovery | 0.369 | 0.104 | 32/241 | -24,459 | -0.0468 |

## Interpretation

This is the same qualitative pattern as the 2026-07-10 and 2026-07-11
00631L downside-risk work:

1. The oracle ceiling for downside/crash labels is real.
2. A real no-look-ahead model still does not capture that ceiling well
   enough to trade.
3. The sparse "extreme crash risk -> de-risk" rule avoids continuous daily
   scaling, but it still pays opportunity cost on too many false positives.
4. The OOS check is decisive: 2018 correction is exactly the kind of window
   this should protect, yet both labels degrade final value and Sharpe.

## Promotion decision

Do not promote.

The script is useful as a repeatable research harness for future crash-risk
features or model families, but the current GradientBoosting + existing
feature set is not a live de-risk signal.

Future work should only continue if there is a genuinely new information
source or model family, not another small threshold sweep on these same
features and windows.

## Review note - 2026-07-12

Post-write review fixed one label-handling bug in the research script:
future max-drawdown labels with unavailable future horizon data are now kept
as `NaN` instead of being converted to non-crash (`0`). This slightly changes
some forecast-quality metrics in the live/active windows, but does not
change the de-risk trading deltas or the no-promotion conclusion above.

## Major-crash detection check - 2026-07-12

Additional date-level diagnostic checked whether the rolling-top-5% ML
crash-risk trigger fired in golden1 around major stress windows. This check
is stricter than AUC because it asks whether the signal actually appears
near useful dates.

Result: do **not** claim it correctly detects major crashes.

- 2020 COVID:
  - `10d_mdd_lt_5pct`: only 1 golden1 trigger (`2020-01-30`), and that day
    was not itself a positive crash label. It missed most labeled events.
  - `20d_mdd_lt_8pct`: 2 early triggers (`2020-01-06`, `2020-01-07`) were
    positive labels, but the broader crash-period protection was still weak
    and the full-window trading delta remained negative.
- 2022 inflation/bear window:
  - `10d_mdd_lt_5pct`: 4 golden1 triggers (`2022-01-21` to `2022-01-26`),
    all non-event on the trigger day; only 2 of 128 event dates had a trigger
    in the prior 5 trading days.
  - `20d_mdd_lt_8pct`: 9 golden1 triggers, mostly in December; only 3 of
    133 event dates had prior-5-day coverage. This misses most of the year.
- 2018 OOS correction:
  - `10d_mdd_lt_5pct`: 19 golden1 triggers, 20 of 71 event dates covered in
    prior 5 trading days, but many trigger days were non-events and trading
    delta was still negative.
  - `20d_mdd_lt_8pct`: 57 golden1 triggers, 35 of 61 event dates covered,
    but this was too noisy/expensive; OOS Sharpe delta was -0.4180.

Interpretation: the model sometimes recognizes stress after risk has already
risen, but it is not a reliable early crash detector and not an actionable
de-risk signal in its current form.
