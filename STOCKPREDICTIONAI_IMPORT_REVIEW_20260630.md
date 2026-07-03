# stockpredictionai Import Review / Group A+ NCF Follow-up
**Date:** 2026-06-30  
**Local time:** 2026-06-30 14:22 CST  
**Source reviewed:** `C:\Users\isaac\Downloads\stockpredictionai-master\stockpredictionai-master`  
**Target system:** Group A+ / A2118 / NCF 00631L

---

## 1. Executive Summary

The `stockpredictionai-master` repository was reviewed after the Bollinger Band feature import work. The source is primarily a README/notebook-derived static site and conceptual write-up, not a maintained executable research pipeline for Taiwan ETFs.

Conclusion:

- No additional low-risk, clearly superior feature or model component remains for direct import into the active Group A+ strategy.
- The most useful idea from the source, Bollinger Band-derived features, has already been imported into `scripts/misc/ncf_00631l.py`.
- The remaining ideas are mostly high-cost research candidates: Fourier trend features, ARIMA residual features, autoencoder latent features, and option anomaly detection.
- These should not be added directly to active strategy logic without strict walk-forward ablation and leakage checks.

---

## 2. Source Repository Findings

### 2.1 Repository nature

The reviewed folder contains:

- `readme.md` and `readme2.md`, both large notebook-style descriptions.
- Static website files under `src/components/`.
- Image outputs such as `output_*.png`.
- No directly reusable, production-grade research pipeline matching our current Taiwan ETF framework.

The website components market several model families, including GAN, VAE, CNN, MHGAN, InfoGAN, and Bayesian networks. These are presented as product/marketing claims and are not backed by a local reproducible Taiwan ETF backtest in that repository.

### 2.2 Key ideas listed in the source

The source proposes:

1. Correlated assets.
2. Technical indicators: MA, EMA, momentum, Bollinger Bands, MACD.
3. News/BERT sentiment.
4. Fourier transforms for denoised trend approximations.
5. ARIMA as a feature.
6. Stacked autoencoders / VAE latent features.
7. PCA/eigen portfolio compression.
8. Option pricing anomaly detection.
9. GAN/LSTM/CNN-style prediction architecture.

---

## 3. Mapping to Current Group A+ System

### 3.1 Already covered or superseded

| Source idea | Current status in Group A+ / NCF | Assessment |
|---|---|---|
| Correlated assets | TWII, SOXX, VIX, USDTWD, external market features, TX/TXO, institutional/margin/chip data | Already stronger and Taiwan-specific |
| MA/MACD/technical indicators | Existing technical features and regime gates | Already covered |
| Bollinger Bands | Imported as 0050 BB external features and BB/VIX interaction | Already imported |
| BERT/news sentiment | FinBERT and LLM/news feature pipeline exists | Already stronger and localized |
| Feature importance | Factor lens, Alphalens, Optuna, AUC/Brier checks | Already more rigorous |
| Risk/uncertainty | Tail MDD probability, gain probability, execution risk, freshness guard | Already stronger |

### 3.2 Not recommended for direct active import

| Source idea | Reason not directly imported |
|---|---|
| GAN / MHGAN / InfoGAN | High complexity, small sample size, high overfitting risk, no source-side reproducible Taiwan ETF result |
| CNN chart/pattern model | Would require image/tensor pipeline and strict ablation; current tabular feature stack is easier to audit |
| VAE/autoencoder latent features | Source itself notes PCA still required too many components; leakage-safe walk-forward implementation required |
| ARIMA price feature | Likely lagging for 00631L; could be tested as residual/noise feature only |
| Option anomaly detection | Conceptually useful, but current TXO PCR/dealer/foreign OI features are more Taiwan-relevant |
| Bayesian networks | Useful conceptually for uncertainty, but current execution risk and tail probability framework is already operational |

---

## 4. Imported Work Already Completed

### 4.1 Bollinger Band external features

Implemented in `scripts/misc/ncf_00631l.py`:

```python
eti0050_bb_pct
eti0050_bb_width
bb0050_x_vix
```

Economic interpretation:

- `eti0050_bb_pct`: 0050 location inside/around Bollinger channel.
- `eti0050_bb_width`: 0050 volatility/channel width proxy.
- `bb0050_x_vix`: overheated 0050 condition multiplied by VIX relative stress.

This is the most concrete useful idea from `stockpredictionai-master`, and it has already been brought into the NCF feature stack.

---

## 5. Issues Found and Fixed During This Review

### 5.1 A2118 live date mismatch

Problem:

- `group_a_plus.runners.a2118` previously mixed the latest NCF JSON date with the runner frame's final date.
- Example: NCF file date `2026-06-29` could be evaluated against frame date `2026-06-18`.

Fix:

- Added live date guard in `group_a_plus/runners/a2118.py`.
- If NCF date does not match frame date, output:

```text
status = stale
reason = ncf_date_mismatch
late_bull_triggered = false
```

### 5.2 Daily signal A2118 hard overlay guard

Problem:

- Daily signal could consume stale A2118 live signal metadata if not guarded.

Fix:

- Added `_a2118_live_signal_is_current(...)`.
- Hard overlay only uses A2118 live signal if `status=ok` and `signal_date == actual_data_date`.

### 5.3 A2118 H5 hold / reentry persistence

Problem:

- Historical A2118 supports H5 hold until `prob_up_h5 >= h5_reentry_min`.
- Live daily signal previously only checked same-day trigger.

Fix:

- Added previous live signal pointer read from `report/group_a_plus/latest/live_signal.json`.
- If prior day hard hedge was active and today's H5 is still below reentry threshold, daily signal can continue the hedge.
- Current 2026-06-29 signal is not a hold continuation; it is a fresh/panel trigger.

### 5.4 Panel / JSON latest row inconsistency

Problem:

- `results/ncf_00631l_v5_tabnet_panel.csv` live tail row did not match `results/ncf_00631l_20260630.json`.
- Example observed before fix:

```text
panel 2026-06-29 h20_prob_up = 0.4159
JSON  2026-06-29 h20_prob_up = 0.2703
```

Fix:

- Added `reconcile_latest_panel_row(...)` in `scripts/misc/ncf_00631l.py`.
- The latest panel row is reconciled to the JSON horizon payload for:
  - `prob_up_h1`
  - `prob_up_h5`
  - `prob_up_h20`
  - `h20_prob_up`
  - `h20_direction`
  - `ensemble_prob_up`
  - `prob_magnitude`
  - `direction`
  - `confidence`

---

## 6. Optuna / NCF Re-run Results

### 6.1 Optuna command

```bash
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py --trials 75 --horizon 20
```

Output:

```text
results/ncf_optuna_best_params.json
```

Feature count:

```text
n_features = 115
```

H20 time-series CV AUC:

| Model | Best CV AUC |
|---|---:|
| LGB | 0.5016 |
| XGB | 0.5057 |
| HGB | 0.5120 |
| RF | 0.4895 |
| ET | 0.5109 |

Interpretation:

- Optuna did not provide strong evidence of better H20 generalization.
- Best CV AUC is only about `0.512`.
- This should be treated as an experiment, not a proven model upgrade.

### 6.2 NCF retraining command

```bash
PYTHONPATH=. MPLCONFIGDIR=/tmp/matplotlib-ncf .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2020-01-01 \
  --val-start 2025-01-02 \
  --full-panel \
  --val-predictions-output results/ncf_00631l_v5_tabnet_panel.csv \
  --optuna-params results/ncf_optuna_best_params.json
```

Outputs:

```text
results/ncf_00631l_20260630.json
results/ncf_00631l_v5_tabnet_panel.csv
```

### 6.3 New NCF live prediction

Data date:

```text
2026-06-29
```

Key values:

| Field | Value |
|---|---:|
| H1 probability up | 0.4669 |
| H5 probability up | 0.3576 |
| H20 probability up | 0.2703 |
| Horizon ensemble calibrated probability up | 0.3793 |
| Horizon ensemble confidence | 0.6621 |
| Forward MDD > 5% probability | 0.542191 |
| Forward gain > 5% probability | 0.374325 |
| Tail reward-risk score | -0.167866 |

### 6.4 Model validation AUC from retrain

| Horizon | AUC |
|---|---:|
| H1 | 0.5710 |
| H5 | 0.6800 |
| H20 | 0.6634 |

H20 late-bull sub-regime:

```text
H20 late-bull AUC = 0.8412
```

Interpretation:

- Overall H20 AUC is lower than the earlier handoff value of `0.7078`.
- Late-bull H20 AUC remains strong.
- Since A2118 specifically uses late-bull conditions, the active trigger remains defensible, but the Optuna run should not be described as an overall model improvement.

---

## 7. A2118 / Daily Signal Status After Re-run

Files regenerated:

```text
results/group_a_plus_runner_latest_20260620.json
results/group_a_plus_live_signal_v2.json
report/group_a_plus/latest/live_signal.json
```

Current daily signal:

```text
actual_data_date = 2026-06-29
execution_allowed = true
execution_regime = ncf_late_bull_hedge
a2118_late_bull_overlay_reason = panel_trigger
a2118_h20_prob = 0.2703
a2118_h5_prob = 0.3576
a2118_confidence = 0.6621
```

Target weights:

| Ticker | Weight |
|---|---:|
| 0050.TW | 0.7473586978 |
| 00631L.TW | 0.0526413022 |
| 00632R.TW | 0.0 |
| 00679B.TWO | 0.0 |
| cash | 0.20 |

Important note:

- `execution_regime = ncf_late_bull_hedge` is now coming directly from the reconciled panel-trigger path.
- Daily signal correctly records the reason as `panel_trigger`.
- This is not an H5 hold continuation today.

---

## 8. Validation

Tests run:

```text
92 passed, 1 warning
33 passed, 1 warning
```

Key consistency checks:

```text
panel_h20 = 0.2703
json_h20  = 0.2703
panel_conf = 0.6621
json_conf  = 0.6621
tail_conf_na = 0
```

Runner stale guard check:

```text
runner frame_data_date = 2026-06-18
NCF signal_date        = 2026-06-29
status                 = stale
reason                 = ncf_date_mismatch
late_bull_triggered    = false
```

This is expected for the default latest runner window and prevents date-mixed live interpretation.

---

## 9. Final Import Decision

No further direct import from `stockpredictionai-master` is recommended at this time.

Reasons:

1. The source repository is conceptual/static, not a reproducible Taiwan ETF research pipeline.
2. The strongest concrete idea, Bollinger Band features, is already imported.
3. Existing Group A+ already has more relevant Taiwan-specific external, sentiment, derivative, and execution-risk features.
4. Remaining ideas are research candidates with high leakage/overfit risk.
5. The latest Optuna run does not prove model improvement.

---

## 10. Future Research Candidates

These are not active-strategy recommendations. They require walk-forward ablation before use.

### 10.1 Fourier trend features

Candidate:

- Multi-period denoised trend approximation for `0050.TW` and `00631L.TW`.

Use only as shadow features first.

### 10.2 ARIMA residual / forecast gap

Candidate:

- Do not use ARIMA price forecast directly.
- Test residual, forecast gap, or residual z-score as a noise/regime feature.

Priority: low.

### 10.3 Autoencoder latent features

Candidate:

- Build leakage-safe walk-forward latent features from technical/external panels.
- Compare against existing TabNet/tree ensemble before using.

Priority: low to medium research only.

### 10.4 Options anomaly feature

Candidate:

- Build anomaly score from Taiwan option market features already present:
  - TXO PCR
  - dealer options
  - foreign option OI
  - cross-market futures/options pressure

Priority: medium only if existing TXO features show unstable but non-zero IC.

---

## 11. Operational Recommendation

Keep active strategy as:

```text
active_strategy = a2118_a2111_ncf_late_bull_deleverage
```

Current live stance:

```text
00631L reduced to hard hedge weight because A2118 late-bull conditions are met.
```

Do not label the latest Optuna result as a model upgrade. Treat it as:

```text
data-chain cleanup + feature consistency fix + experimental H20 tuning result
```

The main improvement from this work is not higher Optuna AUC. The main improvement is that:

- JSON, panel, latest runner, and daily signal are now date-consistent.
- A2118 H5 hold/reentry behavior is represented in live logic.
- The latest panel row is reconciled to the executable JSON signal.

