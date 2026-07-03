# Stock-Prediction-Models Import Review / Group A+ Strategy Decision
**Date:** 2026-06-30  
**Source reviewed:** `C:\Users\isaac\Downloads\Stock-Prediction-Models-master\Stock-Prediction-Models-master`  
**Target system:** Group A+ / A2118 / latest strategy manifest

---

## 1. Executive Summary

The `Stock-Prediction-Models-master` repository was reviewed as an external model/reference library.

Decision:

- Do not add it directly to active Group A+ allocation logic.
- Record it as a reviewed research source in the latest strategy manifest.
- Reuse only selected ideas through future leakage-safe walk-forward experiments.

Reason:

- The repository is a broad stock forecasting example library, not a Taiwan ETF production pipeline.
- Its datasets are mainly US stocks / generic examples, not `0050.TW`, `00631L.TW`, `00632R.TW`, or Taiwan derivative/chip data.
- Its reported high forecasting accuracies are README/notebook demonstration results and are not comparable to Group A+ walk-forward AUC, Sharpe, drawdown, or execution-risk metrics.
- No directly consumable Group A+ signal JSON, NCF panel, or Taiwan ETF backtest output was found.

---

## 2. Source Repository Findings

The source contains:

- Deep-learning notebook examples: LSTM, GRU, seq2seq, attention, CNN seq2seq, dilated CNN seq2seq.
- Agent examples: turtle, moving average, signal rolling, Q-learning variants, actor-critic variants, evolution strategy, neuro-evolution, ABCD strategy.
- Simulation notebooks: Monte Carlo, dynamic volatility Monte Carlo, portfolio optimization.
- Stacking examples: autoencoder + recurrent model + ARIMA + XGBoost, and tree ensemble stacking.
- TensorFlow JS browser demo for LSTM forecasting and simple trading simulation.
- Realtime evolution-strategy Flask example with a pretrained `model.pkl` for US stock examples.

The repository includes static image outputs and example datasets, but not an auditable Taiwan ETF research result suitable for promotion into Group A+.

---

## 3. Mapping to Current Group A+

| Source idea | Current Group A+ status | Decision |
|---|---|---|
| LSTM/GRU/seq2seq forecasting | NCF already uses stronger Taiwan-specific feature panels and walk-forward validation | Research only |
| Attention/CNN/dilated CNN | Potential future sequence model family | Research only |
| Stacking with ARIMA/XGB/RNN | Existing NCF ensemble and TabNet/tree pipeline already cover the practical path | Research only |
| RL/evolution trading agents | Group A+ uses interpretable regime/overlay logic with transaction-cost backtests | Do not import directly |
| Monte Carlo simulations | Current strategy already tracks tail risk, MDD probability, execution risk | Optional future stress-test tooling |
| Portfolio optimization | Current weights are policy-constrained and regime-driven | Optional research only |
| Realtime agent Flask API | Not aligned with current batch daily signal architecture | Do not import |

---

## 4. Why It Should Not Change Active Weights

The active strategy is currently:

```text
a2118_a2111_ncf_late_bull_deleverage
```

This strategy is tied to:

- Taiwan ETF price data.
- Taiwan index/derivative/chip features.
- NCF 00631L/00632R horizons.
- Walk-forward validation and live freshness checks.
- Daily signal overlays, including the latest high-risk bearish trim.

The reviewed external repository does not provide validated evidence that it improves these specific decision points.

Directly adding its models would create avoidable risk:

- Domain mismatch between US stock examples and Taiwan leveraged/inverse ETF behavior.
- Old TensorFlow 1 style code and notebook-oriented workflows.
- Unclear leakage controls in demo notebooks.
- No transaction-cost-compatible Group A+ backtest.
- No 2025 to 2026-06-30 Taiwan ETF validation.

---

## 5. Recommended Future Use

These are candidates only. They require strict walk-forward ablation before use.

### 5.1 Sequence Model Shadow Benchmark

Build a small shadow benchmark comparing:

- Current NCF tree/TabNet ensemble.
- Lightweight GRU/LSTM sequence model.
- Dilated CNN sequence model.

Use the same Group A+ panel, same horizon labels, and no future leakage.

### 5.2 Stacking Residual Feature

Test whether an ARIMA or simple sequence forecast residual adds incremental value to:

- `00631L.TW` H5/H20 probability.
- late-bull de-leverage trigger confidence.
- signal-alignment bearish divergence.

Use it only if walk-forward AUC/Brier and strategy metrics improve after costs.

### 5.3 Monte Carlo Stress-Test Report

The simulation notebooks can inspire a separate risk report:

- Current portfolio weight stress testing.
- Volatility-regime conditional return simulation.
- Drawdown path probability.

This should be reporting-only first, not an allocation rule.

---

## 6. Final Import Decision

Add to latest strategy as:

```text
review_status = completed
active_allocation_impact = none
classification = external_research_reference
```

Do not change:

- `active_strategy.id`
- runner parameters
- NCF panel path
- live 7/1 target weights
- A2118 hard hedge thresholds
- high-risk bearish trim logic

---

## 7. Work Completed in This Repository

### 7.1 Strategy manifest integration

The latest strategy manifest was updated:

```text
report/group_a_plus/latest/strategy.json
```

Added under:

```text
active_strategy.improvements.external_research_review_20260630.stock_prediction_models_master
```

Recorded status:

```text
status = review_completed
classification = external_research_reference
active_allocation_impact = none
```

This means the source is now traceable from the active strategy manifest, but it does not control live weights.

### 7.2 Monte Carlo stress-test report

Implemented:

```text
scripts/evaluate/evaluate_group_a_plus_monte_carlo_stress.py
tests/test_evaluate_group_a_plus_monte_carlo_stress.py
```

Latest output:

```text
results/group_a_plus_monte_carlo_stress_latest_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_group_a_plus_monte_carlo_stress.py \
  --start 2025-01-02 \
  --end 2026-06-30 \
  --horizon-days 20 \
  --n-paths 20000 \
  --seed 2118 \
  --output results/group_a_plus_monte_carlo_stress_latest_20260630.json
```

Inputs:

- Live signal: `report/group_a_plus/latest/live_signal.json`
- Historical prices: `FinRL/data/stock_data.db`
- Historical window: `2025-01-02` to `2026-06-30`
- Price rows: `359`
- Return rows: `358`
- Current target weights:

| Asset | Weight |
|---|---:|
| `0050.TW` | 0.6947 |
| `00631L.TW` | 0.0744 |
| `00632R.TW` | 0.0000 |
| `00679B.TWO` | 0.0000 |
| cash | 0.2308 |

20-trading-day bootstrap Monte Carlo results:

| Metric | Value |
|---|---:|
| Terminal value mean | 1,039,390.99 |
| Terminal value median | 1,037,848.24 |
| Path return mean | 3.94% |
| Path return median | 3.78% |
| Path return p05 | -6.61% |
| Path return p01 | -11.32% |
| Probability of loss | 27.59% |
| Probability of loss > 5% | 8.17% |
| Probability of gain > 5% | 42.51% |
| Mean max drawdown | -4.46% |
| Median max drawdown | -3.79% |
| Probability of drawdown > 5% | 31.80% |
| Probability of drawdown > 10% | 5.00% |

Decision:

```text
status = reporting_only
active_allocation_impact = none
```

Reason:

- This is useful for risk visibility.
- It is not a validated allocation rule.
- It samples historical daily portfolio returns with current weights; it does not model regime changes, transaction costs, or future structural breaks.

### 7.3 Sequence shadow benchmark

Implemented:

```text
scripts/evaluate/evaluate_group_a_plus_sequence_shadow.py
tests/test_evaluate_group_a_plus_sequence_shadow.py
```

Latest output:

```text
results/group_a_plus_sequence_shadow_latest_20260630.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_group_a_plus_sequence_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --n-splits 4 \
  --gap 5 \
  --output results/group_a_plus_sequence_shadow_latest_20260630.json
```

Purpose:

- Test whether lagged and rolling NCF signal outputs add H20 direction-ranking value.
- This is a lightweight proxy for the source repository's LSTM/GRU/sequence-model idea.
- It uses the existing Group A+ NCF signal panel instead of importing the external notebook code.

Inputs:

- Panel: `results/ncf_00631l_panel_latest_20260630.csv`
- Rows after live-row filtering: `339`
- Feature rows after lag/rolling feature construction: `334`
- Feature count: `76`
- Target: `forward_gain_h20 > 0`
- Split method: `TimeSeriesSplit(n_splits=4, gap=5)`

Aggregate results:

| Model | AUC | Brier | AUC delta vs baseline | Decision |
|---|---:|---:|---:|---|
| Raw `prob_up_h20` baseline | 0.8694 | 0.2474 | 0.0000 | Keep |
| Lagged logistic | 0.3141 | 0.1597 | -0.5553 | Reject |
| Lagged HGB | 0.5731 | 0.0387 | -0.2963 | Research only |

Important interpretation:

- Some folds have all-positive test labels, so per-fold AUC is undefined and recorded as `null`.
- Aggregate AUC remains computable across pooled out-of-sample predictions.
- The sequence-lag models improve Brier in this sample, but lose directional ranking badly.
- Since A21.18 trigger logic depends on directional probability ranking and thresholds, this is not acceptable for promotion.

Decision:

```text
status = research_only
active_allocation_impact = none
promotion_decision = research_only
```

Reason:

- Raw `prob_up_h20` remains much stronger for directional ranking.
- The lagged model result is not robust enough to affect hard hedge, live trim, or target weights.

---

## 8. Explicitly Not Imported

The following source-repository elements were intentionally not imported into active logic:

| Source component | Reason |
|---|---|
| TensorFlow 1 LSTM/GRU notebooks | Notebook/demo code, old API style, no Taiwan ETF validation |
| Attention/CNN/dilated CNN notebooks | Requires a full leakage-safe raw feature panel and ablation study |
| Reinforcement learning / evolution strategy agents | Action space is one-unit demo trading, not Group A+ portfolio allocation |
| Realtime Flask `model.pkl` | Trained on US stock examples; incompatible with current daily batch signal pipeline |
| TensorFlow JS browser demo | UI/demo artifact, not research-grade strategy logic |
| Portfolio optimization notebook | Group A+ weights are policy-constrained, regime-aware, and transaction-cost tested |
| Static PNG outputs | Presentation artifacts, no executable signal or reproducible Taiwan ETF metrics |

---

## 9. Current Active Strategy After Review

Active strategy remains:

```text
a2118_a2111_ncf_late_bull_deleverage
```

Active runner remains:

```text
group_a_plus.runners.a2118
```

Active NCF panel remains:

```text
results/ncf_00631l_panel_latest_20260630.csv
```

Active parameters remain:

```text
h20_max = 0.33
conf_min = 0.55
h5_reentry_min = 0.55
```

Latest live execution behavior remains:

```text
execution_regime = golden1
hard_hedge_active = false
high-risk bearish trim = enabled in live signal when total_risk_score>=9 and alignment is bearish/wide_divergence
```

No target-weight change was made because of `Stock-Prediction-Models-master`.

---

## 10. Validation Performed

Commands run:

```bash
python3 -m json.tool report/group_a_plus/latest/strategy.json
```

```bash
.venv/bin/python -m pytest \
  tests/test_evaluate_group_a_plus_sequence_shadow.py \
  tests/test_evaluate_group_a_plus_monte_carlo_stress.py \
  tests/test_group_a_plus_latest_strategy.py \
  tests/test_group_a_plus_daily_signal_v2.py
```

Latest result:

```text
42 passed
```

Earlier focused validations also passed:

```text
36 passed
39 passed
```

---

## 11. Promotion Criteria for Any Future Import

No remaining idea from `Stock-Prediction-Models-master` should enter active allocation unless it satisfies all of the following:

1. Uses Taiwan ETF / Taiwan market feature data, not US demo CSVs.
2. Uses leakage-safe time-series validation.
3. Improves H20 directional AUC or the relevant trigger metric versus the current baseline.
4. Does not worsen Brier/calibration materially.
5. Improves or preserves Group A+ backtest Sharpe, Sortino, max drawdown, turnover, and transaction-cost-adjusted return.
6. Produces a reproducible output file under `results/`.
7. Has tests under `tests/`.
8. Is recorded in `report/group_a_plus/latest/strategy.json`.

Until those conditions are met, the correct classification remains:

```text
external_research_reference
research_only / reporting_only
active_allocation_impact = none
```
