# StockMixer + ATFNet 0050 Weighted Shadow Handoff

**Date:** 2026-07-02 (bugfixes + rerun same day, see section 13)  
**Source PDF:** `C:\Users\isaac\Downloads\s41598-025-14872-6.pdf`  
**Paper:** Sun et al. 2025, Scientific Reports, "Research on deep learning model for stock prediction by integrating frequency domain and time series features"  
**Status:** research-only shadow. Do not wire into live GroupA+ allocation.

> **2026-07-02 update:** a Fable 5 code review (same day, after this doc was
> first written) found three real bugs in
> `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py` and confirmed the
> original weighted-metrics decision evidence (section 9's `long_short_sharpe`
> around -2.0) was a **mechanical artifact**, not a signal from the model.
> All three bugs are fixed and every universe was rerun. See section 13 for
> the corrected numbers and the (unchanged) decision. Sections 1-12 below are
> preserved as-is for history; do not treat their weighted-metrics numbers as
> current.

## 1. Objective

User asked whether the paper's StockMixer + ATFNet approach can use 0050 constituent stocks to
predict with high accuracy, then asked to try 50, 75, and finally 0050 holding-weighted versions.

The experiment was intentionally kept outside live GroupA+ logic. It does not change:

- `golden1_0531`
- latest GroupA+ target weights
- NCF 00631L/00632R production overlay
- execution plan target weights

## 2. Paper Summary

The paper combines:

- `MultTime2dMixer`: time/channel MLP mixing
- `NoGraphMixer`: learnable stock relation matrix, no predefined graph
- `ATFNet`: FFT/frequency-domain attention-like branch

Paper data:

- NASDAQ / NYSE
- 2013-01 to 2017-08
- OHLCV features
- lookback 16 days

Paper reported direction metrics were not high in absolute terms:

| Market | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| NASDAQ | 41.23% | 41.27% | 40.79% | 40.65% |
| NYSE | 49.67% | 43.77% | 41.34% | 43.22% |

The more relevant paper metrics were ranking/strategy metrics:

| Market | IC | RIC | Prec@N | SR |
|---|---:|---:|---:|---:|
| NASDAQ | 0.041 | 0.473 | 0.577 | 1.333 |
| NYSE | 0.028 | 0.347 | 0.557 | 1.233 |

## 3. Code Changed

Main script:

- `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`

Important additions made in this session:

- `--universe top15 | full50_202606 | top75_candidate_202606`
- `--download-cache`
- `--download-start`
- `--download-end`
- `--min-history-days`
- static `FULL50_TICKERS_202606`
- static `TOP75_CANDIDATE_TICKERS_202606`
- `download_cache()` using yfinance
- `build_universe_weights()`
- `weighted_index_metrics()`
- `PARTIAL_0050_PROXY_WEIGHTS`
- output field `weighted_0050_proxy_results`
- output field `universe_weights`
- output field `universe_weights_method`

The script is still untracked in git in this workspace. Check before committing because this repo
already has many unrelated WIP files.

## 4. Data Files Produced

Caches:

- `results/stockmixer_atfnet_0050top15_ohlcv_cache.parquet`
- `results/stockmixer_atfnet_full50_202606_ohlcv_cache.parquet`
- `results/stockmixer_atfnet_top75_candidate_202606_ohlcv_cache.parquet`

Result JSONs:

- `results/stockmixer_atfnet_shadow_latest_20260702.json`
- `results/stockmixer_atfnet_full50_shadow_20260702.json`
- `results/stockmixer_atfnet_full50_min1200_shadow_20260702.json`
- `results/stockmixer_atfnet_top75_candidate_min1200_shadow_20260702.json`
- `results/stockmixer_atfnet_full50_min1200_weighted_shadow_20260702.json`
- `results/stockmixer_atfnet_top75_candidate_min1200_weighted_shadow_20260702.json`

## 5. Universe Notes

### top15

Static 0050 top-15 proxy:

`2330, 2454, 2308, 2317, 3711, 2303, 2327, 2383, 3037, 2345, 2891, 2881, 2382, 1303, 2882`

### full50_202606

Static Taiwan 50 constituent proxy after 2026-06 rebalance.

Problem found:

- `7769.TW` only has data from 2024-11-01 in Yahoo.
- If requiring all 50 names jointly, sample shrinks to 385 windows.
- Therefore, the better comparison uses `--min-history-days 1200`, which drops `7769.TW` and runs 49 names.

### top75_candidate_202606

Research-only approximate top-75 candidate universe:

- Full50 static list plus 25 large-cap Taiwan candidates.
- `6488.TW` failed in Yahoo (`Quote not found`) and was missing.
- `7769.TW` was dropped by `--min-history-days 1200`.
- Final run used 73 names.

This is not an official FTSE/Yuanta top-75 universe.

## 6. Commands Run

Top 50, all names:

```bash
.venv/bin/python scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py \
  --universe full50_202606 \
  --download-cache \
  --epochs 60 \
  --top-n 10 \
  --output results/stockmixer_atfnet_full50_shadow_20260702.json
```

Top 50 with long-history filter:

```bash
.venv/bin/python scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py \
  --universe full50_202606 \
  --min-history-days 1200 \
  --epochs 60 \
  --top-n 10 \
  --output results/stockmixer_atfnet_full50_min1200_shadow_20260702.json
```

Top 75 candidate with long-history filter:

```bash
.venv/bin/python scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py \
  --universe top75_candidate_202606 \
  --download-cache \
  --min-history-days 1200 \
  --epochs 60 \
  --top-n 15 \
  --output results/stockmixer_atfnet_top75_candidate_min1200_shadow_20260702.json
```

Weighted 49-name version:

```bash
.venv/bin/python scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py \
  --universe full50_202606 \
  --min-history-days 1200 \
  --epochs 60 \
  --top-n 10 \
  --output results/stockmixer_atfnet_full50_min1200_weighted_shadow_20260702.json
```

Weighted 73-name version:

```bash
.venv/bin/python scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py \
  --universe top75_candidate_202606 \
  --min-history-days 1200 \
  --epochs 60 \
  --top-n 15 \
  --output results/stockmixer_atfnet_top75_candidate_min1200_weighted_shadow_20260702.json
```

Verification:

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py
.venv/bin/python -m pytest tests/test_fourier_features.py tests/test_evaluate_stock_ranking_walkforward.py
```

Latest verification result:

- `24 passed`

## 7. Equal-Weight Cross-Sectional Results

### top15

Output: `results/stockmixer_atfnet_shadow_latest_20260702.json`

Test period: 2024-12-31 to 2026-07-01

| Model | Accuracy | IC | RIC | Prec@3 |
|---|---:|---:|---:|---:|
| StockMixer+ATFNet lite | 49.65% | 0.0151 | 0.0134 | 0.520 |
| Own-history logistic | 49.35% | 0.0295 | 0.0143 | 0.525 |
| Persistence | 49.78% | -0.0140 | -0.0184 | 0.499 |

Decision: no improvement over trivial logistic baseline.

### full50_202606, all names

Output: `results/stockmixer_atfnet_full50_shadow_20260702.json`

Final universe: 50 names  
Test period: 2026-03-12 to 2026-07-02  
Issue: test too short because `7769.TW` starts late.

| Model | Accuracy | IC | RIC | Prec@10 |
|---|---:|---:|---:|---:|
| StockMixer+ATFNet lite | 50.36% | 0.0159 | 0.0116 | 0.5117 |
| Own-history logistic | 50.42% | 0.0187 | 0.0137 | 0.5169 |
| Persistence | 51.12% | 0.0076 | -0.0029 | 0.5329 |

Decision: not useful; test window too short and model does not beat baselines.

### full50_202606, min-history 1200

Output: `results/stockmixer_atfnet_full50_min1200_shadow_20260702.json`

Final universe: 49 names  
Dropped: `7769.TW`  
Test period: 2025-01-02 to 2026-07-02

| Model | Accuracy | IC | RIC | Prec@10 |
|---|---:|---:|---:|---:|
| StockMixer+ATFNet lite | 50.62% | 0.0258 | 0.0127 | 0.5053 |
| Own-history logistic | 50.63% | 0.0212 | 0.0097 | 0.4992 |
| Persistence | 50.36% | -0.0009 | -0.0038 | 0.5143 |

Decision: slightly better IC than logistic, but not strong enough for live use.

### top75_candidate_202606, min-history 1200

Output: `results/stockmixer_atfnet_top75_candidate_min1200_shadow_20260702.json`

Final universe: 73 names  
Missing: `6488.TW`  
Dropped: `7769.TW`  
Test period: 2025-01-02 to 2026-07-02

| Model | Accuracy | IC | RIC | Prec@15 |
|---|---:|---:|---:|---:|
| StockMixer+ATFNet lite | 51.88% | 0.0231 | 0.0131 | 0.4994 |
| Own-history logistic | 51.74% | 0.0179 | 0.0073 | 0.4952 |
| Persistence | 50.43% | -0.0002 | -0.0033 | 0.5015 |

Decision: higher accuracy than 49 names, but IC lower than 49-name version and Prec@15 does not beat persistence.

## 8. 0050 Proxy Weight Method

User asked to use actual stock holding weights where numbers are available and equally distribute the residual among missing names.

Implemented as:

- `PARTIAL_0050_PROXY_WEIGHTS`
- `build_universe_weights(tickers, partial_weights)`

Known weights are fixed. Missing universe members split `1 - sum(known_weights)` equally.

Important: these are proxy weights, not official Yuanta holdings. The output explicitly says:

`partial_0050_proxy_weights_else_equal_residual; research-only proxy, not official Yuanta holdings`

Top proxy weights used:

| Ticker | Weight |
|---|---:|
| 2330.TW | 54.50% |
| 2317.TW | 4.83% |
| 2454.TW | 3.96% |
| 2308.TW | 2.61% |
| 2382.TW | 1.35% |
| 2881.TW | 1.31% |
| 2882.TW | 1.30% |
| 2303.TW | 1.11% |
| 2412.TW | 0.95% |
| 2886.TW | 0.93% |

## 9. Weighted 0050 Proxy Results

### 49-name weighted proxy

Output: `results/stockmixer_atfnet_full50_min1200_weighted_shadow_20260702.json`

| Model | Weighted Direction Accuracy | Weighted Return Corr | Long-short Sharpe |
|---|---:|---:|---:|
| StockMixer+ATFNet lite | 43.89% | -0.0996 | -2.059 |
| Own-history logistic | 43.89% | -0.0203 | -2.059 |
| Persistence | 49.17% | -0.0339 | -0.500 |

StockMixer weighted probability:

- mean: 0.4805
- latest: 0.4804
- actual weighted up-rate: 56.11%

Interpretation: model is persistently biased below 0.5, while the actual weighted basket rose more often than it fell.

### 73-name weighted proxy

Output: `results/stockmixer_atfnet_top75_candidate_min1200_weighted_shadow_20260702.json`

| Model | Weighted Direction Accuracy | Weighted Return Corr | Long-short Sharpe |
|---|---:|---:|---:|
| StockMixer+ATFNet lite | 44.44% | 0.0679 | -1.888 |
| Own-history logistic | 44.44% | -0.0150 | -1.888 |
| Persistence | 48.61% | -0.0289 | -0.468 |

StockMixer weighted probability:

- mean: 0.4776
- latest: 0.4776
- actual weighted up-rate: 55.56%

Interpretation: weighted return correlation turns positive in 73-name universe, but direction and simple long-short behavior remain bad.

## 10. Decision

Do not导入正式策略權重.

Reasons:

1. Equal-weight cross-sectional results are only mildly positive.
2. 0050 proxy-weighted results are not tradable:
   - weighted direction accuracy around 44%
   - long-short Sharpe strongly negative
   - model weighted probability is biased below 0.5
3. 75-candidate universe does not improve the most important IC vs the 49-name version.
4. The current model uses only each stock's own daily log return, not full OHLCV/volume or official constituent weights.

Current live GroupA+ weights should remain unchanged:

- 0050 about 69.49%
- 00631L about 10.31%
- cash about 20.19%

The previous execution recommendation also remains unchanged:

- Do not fill all 771 missing 00631L shares at once.
- First staged buy around 300 shares is still the preferred conservative execution plan.

## 11. Criteria Before Any Future導入

Minimum gates before this can affect live weights:

- Use official reproducible Yuanta/FTSE holdings weights.
- Use real historical constituent membership or explicitly accept survivorship bias.
- Weighted 0050 proxy direction accuracy must exceed 52% over multiple walk-forward windows.
- Weighted return correlation should be positive and stable.
- StockMixer must beat logistic and persistence on:
  - weighted direction accuracy
  - weighted return correlation
  - long-flat or long-short Sharpe
- When applied as a 00631L add/reduce overlay, it must improve:
  - Sharpe
  - max drawdown
  - turnover-adjusted return

Suggested live effect cap even if it passes:

- Start as `shadow_only`.
- Then allow at most +/-0.5% to +/-1.0% adjustment to 00631L.
- Never override stale-data guards or NCF downside gates.

## 12. Recommended Next Technical Steps

If continuing this line of research:

1. Replace proxy weights with official holdings download.
2. Add OHLCV multi-channel input instead of returns only.
3. Add weighted BCE loss using 0050 weights.
4. Add calibration so weighted probability is not stuck around 0.48.
5. Evaluate horizon 5/20 days, not only next-day.
6. Evaluate only as an overlay on 00631L staging, not as a standalone stock picker.
7. Add walk-forward windows instead of one 60/20/20 split.

Recommended first next patch:

- Add `--loss-weighting 0050_proxy|equal`
- Add `--target-horizon 1|5|20`
- Report weighted metrics by horizon.

## 13. 2026-07-02 Bugfixes and Rerun

A Fable 5 review of `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`
found three bugs and confirmed the section 9 weighted-metrics decision
evidence was misleading. All three are fixed; every universe was rerun on
the existing caches (no re-download needed).

### 13.1 Bugs fixed

1. **`make_windows()` / `own_history_logistic_baseline()` off-by-one gap.**
   The input window ended at `t-1` while the label was `values[t+1]`, so day
   `t`'s return was never seen by any model (including the persistence
   baseline). Fixed: window now ends at `t` inclusive
   (`values[t-lookback+1:t+1, :]`), matching the module's own "predict
   next-day direction" docstring.
2. **`load_returns()` used raw `Close`, not dividend/split-adjusted
   `Adj Close`.** High-yield constituents (2454, 2882, 2881, 2891, 2317) saw
   single-day *raw*-price drops up to ~10% on ex-dividend dates that are not
   real price moves, mislabeling those days "down". Fixed: `load_returns()`
   now prefers `Adj Close` when present in the cache (it already is, in all
   three cached parquet files).
3. **`build_universe_weights()` silently dropped missing tickers when known
   weights already summed above 1.0**, which would have raised `KeyError` at
   the `weight_arr` lookup the moment `PARTIAL_0050_PROXY_WEIGHTS` gets
   updated closer to full coverage. Fixed: missing tickers now get an
   explicit 0.0 weight instead of being omitted from the dict.
4. **(Not a code bug, but the real root cause of section 9's numbers.)**
   `weighted_index_metrics()` thresholded `weighted_prob` at a hard 0.5. Each
   stock's own probability is calibrated to *that stock's* ~50% base rate,
   but the market-cap-weighted 0050 index base rate over the test window is
   ~56% (2330 alone is >50% of the proxy weight). A hard 0.5 cutoff therefore
   predicted "down" on **every single test day** for every model —
   `long_short_sharpe` was just the negative of the always-up-trending
   index's own Sharpe, and the old `weighted_direction_accuracy` (~44%) was
   exactly `1 - actual_up_rate`. This was true for StockMixer+ATFNet *and*
   the logistic baseline identically (`-2.059` for both, bit-for-bit), which
   is what first exposed the artifact. Fixed: `weighted_index_metrics()` now
   accepts a `threshold` parameter, and `main()` calibrates it per-model as
   the median weighted probability on the *validation* period before scoring
   the test period. `weighted_return_corr` (threshold-independent) was
   already being reported and remains the metric to trust most.

### 13.2 Corrected cross-sectional results (unweighted, per-stock)

| Universe | Model | Accuracy | IC | RIC |
|---|---|---:|---:|---:|
| top15 | StockMixer+ATFNet | 49.65% | 0.0143 | 0.0127 |
| top15 | Own-history logistic | 49.78% | 0.0244 | 0.0117 |
| top15 | Persistence | 49.93% | 0.0126 | -0.0030 |
| full50 (49 names) | StockMixer+ATFNet | 50.52% | 0.0261 | 0.0123 |
| full50 (49 names) | Own-history logistic | 50.55% | 0.0188 | 0.0089 |
| full50 (49 names) | Persistence | 49.24% | 0.0053 | -0.0077 |
| top75 (73 names) | StockMixer+ATFNet | 51.71% | 0.0240 | 0.0128 |
| top75 (73 names) | Own-history logistic | 51.68% | 0.0166 | 0.0069 |
| top75 (73 names) | Persistence | 49.42% | 0.0067 | -0.0102 |

Barely moved vs. the pre-fix numbers in sections 7/2026-07-02 originals — the
off-by-one gap and dividend mislabeling were real bugs but small in
magnitude at this scale, consistent with the Fable 5 review's own estimate
(lag-1 vs lag-2 sign-persistence accuracy differs by ~1pp on this universe).
StockMixer+ATFNet still does not clearly and consistently beat the trivial
own-history logistic baseline on IC.

### 13.3 Corrected weighted (0050 proxy) results — now with calibrated threshold

| Universe | Model | Threshold | Weighted Acc | Weighted Return Corr | Long-short Sharpe |
|---|---|---:|---:|---:|---:|
| top15 | StockMixer+ATFNet | 0.4997 | 50.28% | -0.0193 | -0.307 |
| top15 | Own-history logistic | 0.4884 | 53.33% | 0.0439 | (positive, see JSON) |
| full50 (49 names) | StockMixer+ATFNet | 0.4841 | 45.83% | -0.0409 | -1.849 |
| full50 (49 names) | Own-history logistic | 0.4833 | 50.83% | -0.0181 | 0.181 |
| full50 (49 names) | Persistence | 0.6329 | 48.06% | -0.0186 | -0.160 |
| top75 (73 names) | StockMixer+ATFNet | 0.4808 | 51.11% | **0.0844** | **0.713** |
| top75 (73 names) | Own-history logistic | 0.4825 | 50.28% | -0.0151 | -0.004 |
| top75 (73 names) | Persistence | 0.6278 | 49.17% | -0.0257 | 0.115 |

The mechanical "every model always shorts" artifact is gone — thresholds
now sit near each model's own validation-period median (~0.48-0.63) instead
of the uninformative 0.5, and `weighted_pred_up_rate` is no longer 0 for any
model. The 73-name StockMixer+ATFNet result (`corr=+0.084`,
`long_short_sharpe=+0.71`) is the first *positive* result seen anywhere in
this experiment, but it is a single split on a single universe/seed and is
still far below the section 11 gates (52%+ weighted accuracy across multiple
walk-forward windows, positive *and stable* return correlation). The 49-name
StockMixer+ATFNet result is still clearly negative. Results are noisy across
universe size and not monotonic, consistent with the Fable 5 review's point
that a single 60/20/20 split with one seed cannot support a "bigger universe
is better" narrative here.

### 13.4 Decision (unchanged)

**Still do not integrate into live GroupA+ allocation.** The corrected
evidence is not stronger than before — if anything it's more honest about
being noisy/inconclusive rather than falsely conclusive (the old -2.06
Sharpe *looked* like strong evidence against the idea; the corrected numbers
show a mix of small positive and negative results depending on universe,
which is a weaker basis for a decision either way, not a reason to reverse
it). Section 11's gates (multi-window walk-forward, official holdings
weights, consistent beat of both baselines) are unmet either way.

New files this session, all untracked in git:

- `results/stockmixer_atfnet_shadow_latest_20260702_fixed.json`
- `results/stockmixer_atfnet_full50_min1200_fixed_20260702.json`
- `results/stockmixer_atfnet_top75_candidate_min1200_fixed_20260702.json`

Modified: `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py` (also
untracked). `tests/test_fourier_features.py` and
`tests/test_evaluate_stock_ranking_walkforward.py` still pass (24 passed) —
neither of those two files touches this script, so this is a smoke check on
the shared repo state, not a regression test for the fixes above.

### 13.5 Still open (not done in this pass)

The Fable 5 review's remaining suggestions were left for a future session if
this line of research is picked back up again — none of them change the
section 13.4 decision:

- Multi-seed / walk-forward evaluation (section 5 of the review) to get a
  statistically meaningful universe-size comparison.
- Truncation-invariance tests for `group_a_plus/integrations/fourier_features.py`
  and `cross_asset_relation.py` (these *are* wired into the live NCF
  pipeline via `ncf_00632r.py` and `ncf_00631l.py`, unlike this shadow
  script — the review found no lookahead bug there, just a test-coverage
  gap worth closing before the live-pipeline exposure grows).
- Sections 12's other items (official holdings weights, OHLCV multi-channel
  input, weighted BCE loss, multi-horizon evaluation) remain undone.

