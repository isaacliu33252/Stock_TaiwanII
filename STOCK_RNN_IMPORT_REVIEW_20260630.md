# stock-rnn Import Review / Group A+ Stepwise Integration
**Date:** 2026-06-30  
**Source reviewed:** `C:\Users\isaac\Downloads\stock-rnn-master\stock-rnn-master`  
**Target system:** Group A+ / A2118 / NCF 00631L

---

## 1. Source Summary

`stock-rnn-master` is a compact TensorFlow 1 / Python 2 educational RNN project for stock price prediction.

Core ideas:

- Use a fixed lookback window, default `num_steps=30`.
- Normalize each sequence relative to the window's own starting or prior close price.
- Train an LSTM to predict the next normalized close.
- Optionally train across multiple S&P 500 stocks with stock-symbol embeddings.
- Track training with TensorBoard and prediction-vs-truth plots.

The repository is useful as a modeling reference, but not directly production-ready for Group A+.

Limitations:

- Python 2.7 code.
- TensorFlow 1.2 and `tf.contrib`.
- Google Finance fetcher is obsolete.
- Uses S&P 500 examples, not Taiwan ETFs.
- Optimizes MSE price prediction, not H20 directional AUC, Sharpe, drawdown, or transaction-cost-aware strategy performance.
- No local Taiwan ETF validation, no Group A+ signal JSON, and no executable strategy result.

---

## 2. Candidate Ideas for Group A+

| Idea | Decision |
|---|---|
| 30-day relative-window normalization | Tested first as research-only shadow benchmark |
| Raw OHLCV sequence model | Research only; needs stronger evidence |
| Multi-symbol embedding | Future research only; current ETF universe is small |
| TensorBoard / prediction plots | Optional governance/diagnostic tooling |
| Direct TensorFlow model import | Rejected |

---

## 3. Step 1 Implemented: Relative Window Shadow Benchmark

Implemented:

```text
scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py
tests/test_evaluate_stock_rnn_relative_window_shadow.py
```

Latest output:

```text
results/stock_rnn_relative_window_shadow_latest_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-06-30 \
  --lookback 30 \
  --n-splits 4 \
  --gap 5 \
  --output results/stock_rnn_relative_window_shadow_latest_20260630.json
```

Design:

- Source idea imported: relative lookback-window normalization.
- Each ETF close-price window is normalized as:

```text
window_close / window_start_close - 1
```

- Tickers used:

```text
0050.TW
00631L.TW
00632R.TW
00679B.TWO
```

- Lookback: `30` trading days.
- Target: `forward_gain_h20 > 0`.
- Baseline: current NCF `prob_up_h20`.
- Validation: `TimeSeriesSplit(n_splits=4, gap=5)`.
- Models:

```text
relative_window_logistic
relative_window_hgb
```

Input coverage:

| Item | Value |
|---|---:|
| Price window | 2025-01-02 to 2026-06-30 |
| Price rows | 359 |
| Feature rows | 310 |
| Feature count | 141 |

Aggregate result:

| Model | AUC | Brier | AUC delta vs baseline | Brier delta vs baseline |
|---|---:|---:|---:|---:|
| Raw `prob_up_h20` baseline | 0.9004 | 0.2614 | 0.0000 | 0.0000 |
| Relative-window logistic | 0.5596 | 0.2503 | -0.3408 | -0.0111 |
| Relative-window HGB | 0.5782 | 0.1163 | -0.3222 | -0.1451 |

Interpretation:

- The stock-rnn-style relative window improves Brier in this sample, especially with HGB.
- It badly underperforms `prob_up_h20` for directional ranking.
- A21.18 depends on directional ranking and threshold behavior, so this result is not strong enough for promotion.

Decision:

```text
status = research_only
active_allocation_impact = none
promotion_decision = research_only
```

---

## 4. What Was Not Imported

The following were intentionally not imported:

| Source item | Reason |
|---|---|
| TensorFlow 1 LSTM graph | Old framework, no Taiwan ETF validation |
| Python 2 training pipeline | Incompatible with current Python 3 project |
| Google Finance data fetcher | Obsolete API and irrelevant data source |
| S&P 500 symbol embedding | Domain mismatch; needs separate Taiwan multi-asset design |
| MSE next-price objective | Does not match Group A+ H20 direction/risk objective |
| Plotting/checkpoint code | Useful only as optional diagnostics |

---

## 5. Current Strategy Impact

No active strategy change was made.

Active strategy remains:

```text
a2118_a2111_ncf_late_bull_deleverage
```

Active allocation impact:

```text
none
```

Reason:

```text
relative-window HGB AUC = 0.5782
baseline prob_up_h20 AUC = 0.9004
```

The imported idea is retained as a research benchmark only.

---

## 6. Step 2 Implemented: OHLCV Relative Window Benchmark

After the close-only test, the same tool was expanded to support:

```text
--feature-set ohlcv
```

Implemented in:

```text
scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py
tests/test_evaluate_stock_rnn_relative_window_shadow.py
```

Latest output:

```text
results/stock_rnn_ohlcv_relative_window_shadow_latest_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-06-30 \
  --lookback 30 \
  --feature-set ohlcv \
  --n-splits 4 \
  --gap 5 \
  --output results/stock_rnn_ohlcv_relative_window_shadow_latest_20260630.json
```

Additional features added:

- Relative close sequence.
- Intraday range sequence: `(high - low) / close`.
- Relative volume sequence.
- Window return, return mean, return volatility, return min/max.
- Range mean/max.
- Open gap summary.
- Final relative volume.

Input coverage:

| Item | Value |
|---|---:|
| Price window | 2025-01-02 to 2026-06-30 |
| Price rows | 359 |
| Feature rows | 310 |
| Feature count | 401 |

Aggregate result:

| Model | AUC | Brier | AUC delta vs baseline | Brier delta vs baseline |
|---|---:|---:|---:|---:|
| Raw `prob_up_h20` baseline | 0.9004 | 0.2614 | 0.0000 | 0.0000 |
| OHLCV relative-window logistic | 0.4031 | 0.2383 | -0.4973 | -0.0231 |
| OHLCV relative-window HGB | 0.5910 | 0.0824 | -0.3094 | -0.1790 |

Comparison with Step 1 close-only HGB:

| Feature set | HGB AUC | HGB Brier |
|---|---:|---:|
| Close-only relative window | 0.5782 | 0.1163 |
| OHLCV relative window | 0.5910 | 0.0824 |

Interpretation:

- OHLCV features improved Brier versus close-only.
- OHLCV features slightly improved AUC versus close-only.
- However, OHLCV AUC remains far below the raw `prob_up_h20` baseline.
- This is not suitable for active hedge trigger or live allocation.

Decision:

```text
status = research_only
active_allocation_impact = none
promotion_decision = research_only
```

Potential future use:

- The OHLCV relative-window model might be useful as a calibration/risk feature if the Brier improvement remains stable.
- It should not be used as a direction-ranking feature unless AUC improves materially in a combined model or longer validation.

---

## 7. Step 3 Implemented: Combined NCF + OHLCV Relative Window

The tool was expanded to support:

```text
--include-baseline-feature
```

This tests whether the OHLCV relative-window features can improve a model that also sees the current NCF `prob_up_h20` baseline.

Latest output:

```text
results/stock_rnn_ohlcv_combined_shadow_latest_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-06-30 \
  --lookback 30 \
  --feature-set ohlcv \
  --include-baseline-feature \
  --n-splits 4 \
  --gap 5 \
  --output results/stock_rnn_ohlcv_combined_shadow_latest_20260630.json
```

Aggregate result:

| Model | AUC | Brier | AUC delta vs baseline | Brier delta vs baseline |
|---|---:|---:|---:|---:|
| Raw `prob_up_h20` baseline | 0.9004 | 0.2614 | 0.0000 | 0.0000 |
| Combined logistic | 0.4155 | 0.2398 | -0.4849 | -0.0217 |
| Combined HGB | 0.5702 | 0.0812 | -0.3302 | -0.1803 |

Interpretation:

- Adding `prob_up_h20` into the OHLCV relative-window model did not recover baseline directional ranking.
- Brier remains much better than baseline, but AUC remains far worse.
- This reinforces the same conclusion: useful as a possible calibration/risk research feature, not as a direction trigger.

Decision:

```text
status = research_only
active_allocation_impact = none
promotion_decision = research_only
```

---

## 8. Step 4 Implemented: Fast Parameter Sweep

A full 270-combination sweep was started first, but it was too slow for an interactive run and was stopped. A smaller fast sweep was then added and executed.

Implemented:

```text
scripts/evaluate/sweep_stock_rnn_relative_window_shadow.py
tests/test_sweep_stock_rnn_relative_window_shadow.py
```

Latest output:

```text
results/stock_rnn_relative_window_sweep_fast_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/sweep_stock_rnn_relative_window_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-06-30 \
  --lookbacks 10,20,30,45,60 \
  --feature-sets ohlcv \
  --n-splits 4 \
  --gap 5 \
  --fast \
  --output results/stock_rnn_relative_window_sweep_fast_20260630.json
```

Sweep design:

- Lookbacks: `10`, `20`, `30`, `45`, `60`.
- Feature set: `ohlcv`.
- Include baseline options: `false`, `true`.
- HGB parameter profiles:
  - conservative: `max_leaf_nodes=7`, `learning_rate=0.02`, `l2_regularization=0.20`
  - middle: `max_leaf_nodes=15`, `learning_rate=0.035`, `l2_regularization=0.08`
  - aggressive: `max_leaf_nodes=31`, `learning_rate=0.05`, `l2_regularization=0.02`
- Total combinations: `30`.

Best AUC combo:

| Parameter | Value |
|---|---:|
| lookback | 45 |
| feature_set | ohlcv |
| include_baseline_feature | true |
| max_leaf_nodes | 7 |
| learning_rate | 0.02 |
| l2_regularization | 0.20 |
| feature_rows | 295 |
| feature_count | 581 |

Best AUC result:

| Metric | Value |
|---|---:|
| Baseline AUC | 0.9127 |
| Model AUC | 0.7074 |
| AUC delta vs baseline | -0.2052 |
| Baseline Brier | 0.2517 |
| Model Brier | 0.0316 |
| Brier delta vs baseline | -0.2201 |

Interpretation:

- Tuning helps: best AUC improved from the earlier OHLCV HGB result of `0.5910` to `0.7074`.
- The model still substantially underperforms the raw `prob_up_h20` baseline for directional ranking.
- Brier/calibration remains very strong, but this alone is not enough to control A21.18 hard hedge or live exposure.

Decision:

```text
promotion_decision = research_only
active_allocation_impact = none
```

Conclusion after parameter sweep:

```text
Do not use stock-rnn relative-window features as a direction trigger.
Potentially revisit only as a calibration/risk feature after longer-window validation.
```

---

## 9. Next Step Candidates

Only proceed if requested:

1. Test the same relative-window representation on a longer 2020-2026 window.
2. Test a modern lightweight PyTorch/Sklearn sequence proxy, not TensorFlow 1.
3. Use relative-window model only as a calibration/risk feature if Brier improvement remains stable.
4. Require a full Group A+ backtest before any live use.

Promotion criteria:

- AUC improves versus `prob_up_h20`, or contributes positive incremental value in a combined model.
- Brier improvement remains stable across folds.
- Group A+ backtest metrics improve after costs.
- Tests and latest strategy manifest entries exist.
