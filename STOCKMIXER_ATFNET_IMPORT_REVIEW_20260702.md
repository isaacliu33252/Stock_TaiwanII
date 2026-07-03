# StockMixer + ATFNet Import Review / Group A+ Strategy Decision
**Date:** 2026-07-02
**Source reviewed:** `C:\Users\isaac\Downloads\s41598-025-14872-6.pdf` (Sun et al. 2025, Scientific Reports,
"Research on deep learning model for stock prediction by integrating frequency domain and time series features")
**Target system:** Group A+ 0050 constituent universe (new experiment, not 00631L/00632R)

---

## 1. Executive Summary

The paper proposes StockMixer+ATFNet: MultTime2dMixer (dual-path MLP time/stock mixing),
NoGraphMixer (learnable implicit N×N stock-correlation matrix, no explicit graph), and ATFNet
(FFT-based frequency-domain linear attention), fused by weighted average. Reported results on
NASDAQ (N=1026) / NYSE beat 7-8 baselines (LSTM, GCN, GAT, HGTAN, etc.) with IC=0.041/0.028,
Sharpe=1.33/1.23.

**Decision: research_only. Do not add to active Group A+ allocation logic.** A simplified
reproduction on 0050's top-15 holdings by weight shows **no improvement over a trivial per-stock
logistic-regression baseline**, and near-chance direction accuracy. Consistent with every other
external deep-learning shadow benchmark reviewed this project ([[STOCK_RNN_IMPORT_REVIEW_20260630]],
[[STOCK_PREDICTION_MODELS_IMPORT_REVIEW_20260630]]).

---

## 2. What was tested

`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py` (new, research-only, no production imports).

- **Universe:** 0050's top-15 holdings by weight (2330/2454/2308/2317/3711/2303/2327/2383/3037/
  2345/2891/2881/2382/1303/2882.TW) — individual TWSE stocks fetched via yfinance, 2019-01-01 to
  2026-07-01 (1815 trading days), cached at
  `results/stockmixer_atfnet_0050top15_ohlcv_cache.parquet`.
- **Input:** each stock's own daily log return only (single channel, no OHLCV/volume/external
  features — a deliberate simplification vs. the paper's 5-8 feature channels).
- **Architecture:** faithful-in-spirit but simplified PyTorch reimplementation of the three core
  modules (MultTime2dMixer / NoGraphMixer / ATFNet), lookback=16 matching the paper, fusion
  weight α=0.5.
- **Task:** joint next-day up/down direction prediction across all 15 stocks.
- **Split:** 60/20/20 train/val/test by date (no shuffling).
- **Baselines:** (a) persistence (yesterday's sign), (b) per-stock logistic regression using only
  that stock's own lagged returns (no cross-stock information at all).

## 3. Results (test period, `results/stockmixer_atfnet_shadow_latest_20260702.json`)

| Model | Accuracy | IC | RIC | Prec@3 |
|---|---|---|---|---|
| StockMixer+ATFNet (lite) | 49.65% | 0.0151 | 0.0134 | 0.520 |
| Own-history logistic (no cross-stock) | 49.35% | **0.0295** | 0.0143 | 0.525 |
| Persistence (naive momentum) | 49.78% | -0.0140 | -0.0184 | 0.499 |

**The custom architecture does not beat the trivial single-stock logistic baseline on IC**, and all
three models are at or below chance-level accuracy (~50%) — none clears the paper's own IC>0.1
"significant predictive effectiveness" threshold, and the paper's reported NASDAQ IC (0.041) was
achieved at N=1026, not N=15.

## 4. Why it likely underperforms here (not necessarily wrong idea, wrong scale)

1. **Universe size mismatch.** `NoGraphMixer`'s learnable N×N correlation matrix and `ATFNet`'s
   per-frequency-bin linear layers need enough cross-sectional diversity to fit reliably. The paper
   validated at N=1026; N=15 gives the model far fewer degrees of freedom to learn from while adding
   real parameters, an easy path to overfitting/noise-fitting rather than genuine signal.
2. **Single-feature input.** Using only log-return (vs. the paper's OHLCV + volume) strips out
   information NoGraphMixer/ATFNet might otherwise exploit — this was a deliberate "simplified
   version" scope choice, not a faithfulness bug, but it caps the ceiling.
3. **Individual TWSE daily direction is a genuinely hard target.** This matches every other
   sequence-model shadow test already run against this project's own data (relative-window
   normalization, OHLCV combined shadow, etc.) — raw daily direction on individual names has close
   to zero linearly-recoverable signal at this data scale, regardless of architecture.

## 5. What this does NOT tell us

- This does **not** invalidate the paper's own NASDAQ/NYSE results (different scale, different
  market, full feature set, official hyperparameter tuning).
- This does **not** test the "weight-aggregation" idea discussed with the user (using 0050's actual
  ETF weights to combine per-stock predictions into an index-level signal) — the per-stock signal
  itself needs to clear a much higher bar before that aggregation step would be worth building.
- Not tested: full 50-stock universe (only top 15 by weight), OHLCV+volume as multi-channel input,
  longer training/more epochs, tuned α, walk-forward validation across regimes.

## 6. Decision

- **active_allocation_impact: none.** Group A+ live signal, a2118 params, and NCF models are
  untouched.
- Recorded as `research_only` in `results/stockmixer_atfnet_shadow_latest_20260702.json`.
- Nothing committed to git. New files this session (`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`,
  `results/stockmixer_atfnet_0050top15_ohlcv_cache.parquet`,
  `results/stockmixer_atfnet_shadow_latest_20260702.json`, this review doc) are all untracked,
  self-contained, and don't touch any existing pipeline file.

### 6.1 Open question (2026-07-02, not yet decided): would N=15→50 help?

User asked whether expanding to the full 50 constituents would improve results. **No clean
theoretical answer — two opposing effects, and it's cheap enough to just test empirically instead
of reasoning it out:**

- **Could help:** `MultTime2dMixer`'s time-mixing path shares weights across stocks, so more names
  = more effective training signal for those shared parameters (same mechanism that lets MLP-Mixer
  scale with more image patches).
- **Could hurt:** `NoGraphMixer`'s Ws and `ATFNet`'s w_real/w_imag are all N×N — going 15→50 grows
  those from 225 to 2500 params (11x) while the number of trading days (the actual supervisory
  signal for the correlation structure) stays the same (~1815 days total). This is plausibly *why*
  the N=15 run already lost to the trivial single-stock logistic baseline (see section 3) — more N
  without proportionally more days could make this worse, not better.

**Next step if picked back up:** extend `TICKERS` in `evaluate_stockmixer_atfnet_shadow.py` to the
full 50 (need to fetch the remaining ~35 names via yfinance first — the DuckDB `ohlcv` table only
has 11 ETF tickers, no individual TWSE stocks, so this always requires a fresh yfinance pull, not
a DB query). Script and harness already support arbitrary N with no code changes beyond the
ticker list. Expected runtime: a few minutes (fetch + train), same order as the N=15 run.

---
*Generated by Claude Code — 2026-07-02*
