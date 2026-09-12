# 2607.27461 OMD-Portfolio Review for GroupA+ - 2026-08-21

## Paper

Local file: `C:\Users\isaac\Downloads\2607.27461.pdf`

Title: `Are Three Matrices All You Need To Beat the Market? Observable Matrix Dynamics for Portfolio Optimization`

Author/date from PDF: Igor Halperin, July 31, 2026.

## Executive Decision

The paper has useful ideas for GroupA+, but the full OMD-Portfolio strategy should not be
directly promoted into the latest strategy.

Recommended action:

- Do not wire into `group_a_plus/operations/daily_signal.py`.
- Do not change target weights.
- Do not add automatic `00631L.TW` or `00632R.TW` exposure from this paper.
- Keep as research/shadow candidate only.
- Best first candidate: a residual-distance / crowding / concentration shadow diagnostic for the current ETF basket and broader Taiwan proxy pool.

Reason:

- The paper is built for a large S&P 500 single-stock universe, not a 4-ETF GroupA+ universe.
- Its strongest performance mechanism is cross-sectional stock selection; GroupA+ has too few live assets for a ten-decile Markov ranking chain.
- The author's own ablations show return rank is close to unforecastable, daily rebalancing hurts, validation Sharpe optimization overfits, and volume signals are real but too fast to monetize after costs.
- Several ideas are still useful as discipline: rank-bucketing, no-trade hysteresis, volatility-rank diagnostics, residual-distance diversification, and transfer-entropy leader/crowding analysis.

## Paper Summary

The paper proposes OMD-Portfolio, a dynamic portfolio framework using only market data:

- daily prices
- trading volumes
- market capitalizations

The state representation is built from three fixed-size matrices:

1. Geodesic distance matrix from return correlations: `M = arccos(C)`.
2. Markov transition matrix of monthly trailing-return ranks.
3. Markov transition matrix of monthly trailing-volatility ranks.

The paper extends prior OMD-Stocks by conditioning the return-rank and volatility-rank Markov chains on cross-sectionally ranked covariates:

- size
- beta
- Amihud illiquidity
- momentum
- realized volatility over multiple windows
- distance-matrix features such as market loading, centrality, and transfer-entropy lead-lag score

Reported S&P 500 results:

- Volatility rank is forecastable out of sample; return rank is near unforecastable.
- Monthly rebalancing beats daily rebalancing because daily updates mostly add turnover.
- A market-neutral momentum long-short sleeve becomes useful only after a no-trade band cuts turnover.
- A long-only sleeve plus defensive timing and a market-neutral sleeve beats the market over 2022-2024.
- A second clean test over January 2025 to July 2026 reports Sharpe `1.32` versus market `1.14`; residual-distance diversification raises it to `1.44`.
- Residual-distance diversification of the long-only sleeve improves Sharpe, but too much tilt over-selects peripheral clusters.
- A transfer-entropy hub overlay improves convexity/drawdown but does not add return.

Important caveats from the paper itself:

- Hyperparameter optimization on validation Sharpe overfits.
- Return-rank forecastability is weak.
- The strongest edge is in a large stock cross-section, not in a small ETF universe.
- Volume/turnover signal forecasts next-day rank but is not tradeable net of cost.
- Sharpe difference versus the market is not statistically significant over the short clean test; excess return is stronger than risk-adjusted significance.

## Relevance To Current GroupA+

Current GroupA+ live universe is small:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`

This creates a structural mismatch:

- The paper's decile rank chains require hundreds of names.
- GroupA+ has no meaningful 10-bucket cross-sectional rank process at the live allocation level.
- Leveraged/inverse ETFs are not ordinary single stocks; covariance/diversification optimizers can produce mechanically bad allocations in this universe.
- Existing project history already contains negative evidence against naive dynamic-correlation-driven allocation for leveraged/inverse ETF baskets.

Therefore the direct OMD portfolio cannot be copied into GroupA+ as a live allocation strategy.

The useful path is to adapt the diagnostics, not the full optimizer.

## Ideas Worth Importing

### 1. Residual-distance diversification / crowding shadow

This is the best candidate.

Paper idea:

- Remove the broad market mode from returns.
- Compute residual correlation and residual arccos distance.
- Prefer a long book whose holdings are not crowded in residual space.

GroupA+ adaptation:

- Compute rolling residual-distance diagnostics for the ETF basket and optional broader proxy pool.
- Treat it as a crowding/concentration warning, not a weight optimizer.
- Report whether current holdings are effectively one crowded equity-beta bet despite appearing diversified.

Possible output fields:

- `mean_pairwise_residual_distance`
- `distance_to_0050`
- `00631l_redundancy_to_0050`
- `00679b_hedge_distance`
- `00632r_inverse_distance`
- `crowding_status`
- `target_weight_change_allowed=false`

Why useful:

- GroupA+ already cares about whether `00631L.TW` is just amplified `0050.TW`.
- Existing docs repeatedly warn that `00679B.TWO` hedge behavior is regime-dependent.
- Residual distance can give a compact daily diagnostic for whether the current basket is genuinely diversified or just levered equity exposure.

Promotion status:

- Shadow-only candidate.
- Do not use to optimize weights until validated against GroupA+ windows and transaction-cost constraints.

### 2. No-trade hysteresis as a hard anti-turnover principle

Paper idea:

- Monthly score changes caused high turnover.
- A no-trade band reduced turnover from roughly `2.4` to about `0.9` and improved net Sharpe.
- Daily rebalancing did not help.

GroupA+ relevance:

- This project already uses turnover caps and execution guards.
- The paper reinforces the existing rule: small signal-score differences should not trigger trades.

Recommended policy:

- Preserve existing turnover cap discipline.
- If any OMD-like rank/crowding shadow later proposes a change, it must pass a no-trade band / hysteresis replay.
- Do not create a daily OMD rebalance signal.

### 3. Volatility-rank diagnostics, not return-rank alpha

Paper idea:

- Volatility rank is forecastable.
- Return rank is close to unforecastable.
- Volatility information helps measure risk more than it helps select return winners.

GroupA+ adaptation:

- Use OMD-style rank-bucket diagnostics only for risk state:
  - realized-volatility rank
  - drawdown rank
  - beta/correlation concentration rank
  - ETF crowding rank
- Do not treat return-rank forecast as a primary alpha signal.

Fit with existing system:

- This complements existing RG-ResMoE, GARCH, tail-conformal, and drawdown forecast shadows.
- It should be compared against those diagnostics, not immediately added beside them.

### 4. Transfer-entropy leader overlay as research only

Paper idea:

- Transfer-entropy leader/hub scores did not improve rank forecasting, but helped hedge/convexity.

GroupA+ adaptation:

- Possible research diagnostic across:
  - `2330.TW`
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
  - `00679B.TWO`
  - external proxies such as SOXX, QQQ/SPY, TWD/USD, TW futures/options if locally available

Use:

- Detect whether Taiwan equity risk is being led by semis/US tech/futures rather than local ETF prices.
- Keep as advisory only.

Blocker:

- Transfer entropy is sample-hungry and unstable on a tiny asset set.
- Needs strict out-of-sample and null/surrogate tests before any decision use.

### 5. Rank-bucketing as a robust feature transform

Paper idea:

- Convert heterogeneous features to cross-sectional deciles.
- This gives outlier resistance and monotone-transform invariance.

GroupA+ adaptation:

- For a broad proxy universe, use quantile/rank buckets instead of raw levels.
- For the live 4-ETF basket, deciles do not make sense; use rolling historical percentile ranks instead.

Potential feature transforms:

- rolling volatility percentile
- rolling drawdown percentile
- rolling correlation percentile
- spread/discount percentile if available
- turnover/liquidity percentile

## Ideas Not Ready For GroupA+

### 1. Full Markov-chain portfolio optimizer

Do not implement as live strategy.

Reasons:

- Requires large cross-section.
- GroupA+ ETF basket has too few assets.
- Leveraged/inverse ETFs violate the paper's ordinary-stock assumptions.
- Existing project history already shows dynamic covariance allocation can fail badly on this ETF set.

### 2. Return-rank selection alpha

Do not promote.

Reasons:

- The paper itself says return rank is close to unforecastable.
- GroupA+ does not have enough names to extract the paper's cross-sectional momentum structure.
- Any return-rank alpha on four ETFs would likely reduce to already-known 0050/00631L momentum and inverse/bond switching rules.

### 3. Daily volume/turnover signal

Do not promote.

Reasons:

- Paper finds the signal real but too fast to trade net of cost.
- GroupA+ execution already needs turnover discipline.
- For Taiwan ETFs, liquidity/volume should remain risk context, not day-trading alpha.

### 4. Covariance or minimum-variance optimizer

Do not reattempt without a new objective.

Reason:

- The paper itself argues classical covariance inversion is fragile.
- GroupA+ history already records that GMV-style allocation on `0050/00631L/00632R/00679B` can overweight leveraged/inverse legs for the wrong reason.

## Recommended Implementation Path

### Phase 1: Documentation only

Status: done by this review.

Keep the paper as:

- useful design reference
- no live strategy change
- residual-distance/crowding shadow candidate

### Phase 2: Build residual-distance crowding shadow

Candidate file:

- `group_a_plus/integrations/omd_residual_distance_shadow.py`

Candidate runner:

- `scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py`

Candidate latest artifact:

- `report/group_a_plus/latest/omd_residual_distance_shadow.json`

Candidate log:

- `results/omd_residual_distance_shadow_log.jsonl`

Minimum first version:

- load daily returns for GroupA+ tickers
- rolling window `126` or `252` trading days
- compute equal-weight market proxy
- regress out market proxy from each asset return
- compute residual correlation
- compute `arccos(clipped_corr)`
- report pairwise distances and current-basket mean residual distance
- mark `target_weight_change_allowed=false`

Important:

- First version should be diagnostic only.
- No optimizer.
- No target-weight output.

Status: implemented as first shadow version on 2026-08-21.

Implemented files:

- `group_a_plus/integrations/omd_residual_distance_shadow.py`
- `scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py`

Generated artifacts:

- `report/group_a_plus/latest/omd_residual_distance_shadow.json`
- `report/group_a_plus/omd_residual_distance_shadow/history/omd_residual_distance_shadow_20260820.json`
- `results/omd_residual_distance_shadow_log.jsonl`

Command run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py --as-of 2026-08-20
```

Latest run summary:

- status: `available_for_shadow_review`
- actual data end: `2026-08-20`
- state: `normal`
- usable tickers: `4`
- return observations: `504`
- rolling snapshots: `379`
- window: `126` trading days
- mean pairwise raw distance: `1.791734`
- mean pairwise residual distance: `1.950008`
- low-distance risk percentile: `0.588391`
- manual review required: `false`
- target weight change allowed: `false`

Latest pair highlights:

- `0050.TW|00631L.TW` raw correlation: `0.977614`
- `0050.TW|00631L.TW` raw distance: `0.211989`
- `0050.TW|00631L.TW` residual correlation: `0.381424`
- `0050.TW|00631L.TW` residual distance: `1.17946`
- `0050.TW|00632R.TW` raw correlation: `-0.982179`
- `0050.TW|00679B.TWO` raw correlation: `0.110448`

Interpretation:

- `00631L.TW` remains highly redundant with `0050.TW` in raw return space, as expected for a leveraged equity ETF.
- After equal-weight market proxy residualization, the latest basket-level residual-distance state is not elevated.
- This is a crowding/concentration diagnostic only; it does not justify adding or reducing any position.

Validation run:

```bash
.venv/bin/python -m py_compile \
  group_a_plus/integrations/omd_residual_distance_shadow.py \
  scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py
```

### Phase 3: Broader proxy-pool experiment

If Phase 2 is stable, extend to a broader local proxy pool:

- GroupA+ ETFs
- `2330.TW`
- major 0050 constituents if available
- US tech/semiconductor proxies if already stored
- futures/options-derived market state if available

Goal:

- Test whether residual-distance/crowding diagnostics improve drawdown or re-entry decisions beyond existing vol/tail shadows.

Promotion bar:

- Must beat existing GroupA+ diagnostics on 2020 Covid, 2022 rate-hike, 2024-2026, and 2025-2026 windows.
- Must include transaction-cost and turnover replay if it ever proposes trades.
- Must survive a no-trade band.
- Must not duplicate existing 0050/00631L correlation warnings.

### Phase 2b: Historical validation of residual-distance shadow

Status: implemented and run on 2026-08-21.

Implemented file:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py`

Generated artifacts:

- `report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.json`
- `report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.md`
- `report/group_a_plus/omd_residual_distance_shadow_evaluation/history/omd_residual_distance_shadow_evaluation_20260820.json`
- `report/group_a_plus/omd_residual_distance_shadow_evaluation/history/omd_residual_distance_shadow_evaluation_20260820.md`

Command run:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py --as-of 2026-08-20
```

Validation result:

- status: `research_complete_do_not_promote`
- actual data: `2009-07-14` to `2026-08-20`
- total days: `4195`
- stress-window days: `1245`
- non-stress days: `2950`
- stress manual-review rate: `0.297992`
- non-stress manual-review rate: `0.750508`
- high-risk days with risk percentile >= 0.75: `2490`
- high-risk rate: `0.593564`
- blockers:
  - `manual_review_rate_not_higher_in_stress_windows`
  - `not_promoted_shadow_only`

H20 forward drawdown check:

- high-risk mean H20 forward max drawdown: `-0.033137`
- normal mean H20 forward max drawdown: `-0.028804`
- high-risk mean H20 forward return: `0.00575`
- normal mean H20 forward return: `0.011413`

Stress-window coverage:

| window | days | manual-review rate | max risk percentile | mean H20 forward max drawdown |
| --- | ---: | ---: | ---: | ---: |
| `2018_correction` | `245` | `0.212245` | `0.948413` | `-0.033821` |
| `2020_covid` | `116` | `0.12069` | `0.607143` | `-0.056749` |
| `2022_rate_hike` | `246` | `0.211382` | `0.97619` | `-0.052932` |
| `2024_2026_live` | `638` | `0.396552` | `1.0` | `-0.032366` |
| `2025_2026_active` | `396` | `0.520202` | `1.0` | `-0.03379` |

Interpretation:

- Residual-distance high-risk buckets have slightly worse average H20 forward drawdown than normal days, but the effect is not clean enough.
- Trigger coverage is poor in the key 2020 Covid window.
- Non-stress manual-review rate is higher than stress-window rate, so the signal is too broad/structural to serve as a stress gate.
- This should remain a descriptive crowding/concentration diagnostic only.
- Do not promote into `daily_signal.py`, target weights, `00631L` add, or `00632R` open logic.

Current verdict after validation:

- Keep latest `omd_residual_distance_shadow.json` as research context if desired.
- Do not treat it as a standalone risk-off or re-entry signal.
- The next meaningful experiment would need a broader proxy pool, not more tuning on the same 4-ETF basket.

### Phase 2c: Incremental value versus simple vol/drawdown baselines

Status: implemented and run on 2026-08-21.

Reason for this test:

- User asked for next step after the residual-distance validation.
- The most pragmatic question is whether OMD residual distance adds anything beyond simple, already-available risk state features.

Implemented file:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py`

Generated artifacts:

- `report/group_a_plus/latest/omd_residual_distance_incremental_review.json`
- `report/group_a_plus/latest/omd_residual_distance_incremental_review.md`
- `report/group_a_plus/omd_residual_distance_incremental_review/history/omd_residual_distance_incremental_review_20260820.json`
- `report/group_a_plus/omd_residual_distance_incremental_review/history/omd_residual_distance_incremental_review_20260820.md`

Command run:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py --as-of 2026-08-20
```

Method:

- Target: `0050.TW`
- OMD high risk: `low_distance_risk_percentile >= 0.75`
- Baseline high risk: `20d realized-vol percentile >= 0.75 OR drawdown-depth percentile >= 0.75`
- Outcome: H20 forward max drawdown <= `-5%`
- Rows: `4195`
- Rows with H20 outcome: `4169`

Classifier result for H20 severe drawdown:

| signal | signal rate | precision | recall | false positive rate | precision lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.591749` | `0.187272` | `0.578947` | `0.594779` | `0.978367` |
| `vol_high` | `0.28616` | `0.236379` | `0.353383` | `0.270246` | `1.234917` |
| `drawdown_high` | `0.277525` | `0.259291` | `0.37594` | `0.254227` | `1.354618` |
| `baseline_high` | `0.411609` | `0.244172` | `0.525063` | `0.384752` | `1.275633` |
| `omd_only` | `0.362437` | `0.176042` | `0.333333` | `0.369327` | `0.9197` |
| `both_high` | `0.229312` | `0.205021` | `0.245614` | `0.225452` | `1.071093` |

Bucket H20 outcomes:

| bucket | days | H20 mean forward max drawdown | H20 mean forward return |
| --- | ---: | ---: | ---: |
| `omd_only` | `1515` | `-0.035412` | `-0.003349` |
| `baseline_only` | `761` | `-0.039221` | `0.0046` |
| `both_high` | `975` | `-0.029541` | `0.020131` |
| `neither_high` | `944` | `-0.020399` | `0.016911` |
| `omd_high` | `2490` | `-0.033137` | `0.00575` |
| `baseline_high` | `1736` | `-0.033828` | `0.013252` |

Incremental review blockers:

- `omd_precision_lift_not_above_vol_drawdown_baseline`
- `omd_only_days_do_not_improve_severe_drawdown_precision`
- `not_promoted_shadow_only`

Interpretation:

- OMD residual-distance high-risk days do not beat simple vol/drawdown baselines for H20 severe-drawdown precision.
- `omd_only` days are worse than the unconditional base rate for severe drawdown precision, so the signal has no usable independent edge.
- The existing simple drawdown-depth percentile is stronger than OMD residual distance in this test.
- This confirms that the 4-ETF residual-distance adaptation should stay descriptive/research-only.

Current verdict after incremental test:

- Do not keep tuning the 4-ETF version.
- Do not wire it into daily signal, execution guard, `00631L` add, or `00632R` open logic.
- If revisited, use a broader proxy pool; otherwise this paper can be considered experimentally exhausted for the current GroupA+ ETF basket.

### Phase 3: Broad proxy-pool incremental test

Status: implemented and run on 2026-08-21.

Reason for this test:

- The 4-ETF residual-distance adaptation was too narrow and had no incremental edge.
- The paper's original OMD idea is cross-sectional, so the only remaining fair test was to expand the proxy universe rather than keep tuning the 4-ETF basket.

Implementation note:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py` was extended to:
  - load both `ohlcv` and `external_market_ohlcv`
  - prefer fresher `external_market_ohlcv` rows when a ticker exists in both tables
  - support `--broad-proxy-pool`
  - support `--start`

Broad proxy pool used:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`
- `2330.TW`
- `2317.TW`
- `2454.TW`
- `2308.TW`
- `2382.TW`
- `^TWII`
- `SOXX`
- `TSM`
- `QQQ`
- `^IXIC`
- `^GSPC`
- `^VIX`
- `TWD=X`
- `HYG`
- `SHY`
- `^N225`
- `^KS11`
- `^HSI`

Command run:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py \
  --as-of 2026-08-20 \
  --broad-proxy-pool \
  --start 2019-01-02 \
  --output report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.json \
  --markdown report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.md \
  --history-dir report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history
```

Generated artifacts:

- `report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.json`
- `report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.md`
- `report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history/omd_residual_distance_incremental_review_20260820.json`
- `report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history/omd_residual_distance_incremental_review_20260820.md`

Broad proxy result:

- status: `research_complete_do_not_promote`
- actual data: `2019-06-27` to `2026-08-20`
- rows: `1864`
- rows with H20 outcome: `1718`
- outcome: H20 forward max drawdown <= `-5%`
- blockers:
  - `omd_precision_lift_not_above_vol_drawdown_baseline`
  - `omd_only_days_do_not_improve_severe_drawdown_precision`
  - `not_promoted_shadow_only`

Broad proxy H20 severe drawdown classifier:

| signal | signal rate | precision | recall | false positive rate | precision lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.37078` | `0.175824` | `0.287918` | `0.395034` | `0.776519` |
| `vol_high` | `0.347497` | `0.318258` | `0.488432` | `0.306245` | `1.405571` |
| `drawdown_high` | `0.294529` | `0.395257` | `0.514139` | `0.230248` | `1.745633` |
| `baseline_high` | `0.470896` | `0.346106` | `0.719794` | `0.398044` | `1.528562` |
| `omd_only` | `0.231665` | `0.170854` | `0.174807` | `0.248307` | `0.75457` |
| `both_high` | `0.139115` | `0.1841` | `0.113111` | `0.146727` | `0.813071` |

Broad proxy bucket H20 outcomes:

| bucket | days | H20 mean forward max drawdown | H20 mean forward return |
| --- | ---: | ---: | ---: |
| `omd_only` | `445` | `-0.027975` | `0.000957` |
| `baseline_only` | `590` | `-0.051604` | `0.004415` |
| `both_high` | `239` | `-0.023009` | `0.049205` |
| `neither_high` | `590` | `-0.015559` | `0.041647` |
| `omd_high` | `684` | `-0.026112` | `0.019059` |
| `baseline_high` | `829` | `-0.043156` | `0.017647` |

Interpretation:

- Expanding to a broader Taiwan/US/FX/credit proxy pool did not rescue the OMD residual-distance signal.
- OMD precision lift got worse versus the 4-ETF test.
- Simple drawdown-depth percentile remained much stronger than OMD residual distance.
- `omd_only` again had precision below the unconditional base rate.
- This closes the main remaining "maybe the universe is too small" objection for a first-pass GroupA+ adaptation.

Final verdict after broad proxy test:

- Do not promote.
- Do not keep tuning thresholds on OMD residual distance.
- Do not add to `daily_signal.py`.
- Do not use for `00631L` add, `00632R` open, risk-off, or re-entry.
- The paper's useful contribution for GroupA+ remains conceptual: rank/volatility discipline, no-trade hysteresis, and skepticism of fragile optimizers.
- The actual OMD residual-distance adaptation is experimentally negative for current GroupA+ data.

## Do Not Do

Do not:

- Wire OMD score into `daily_signal.py`.
- Use OMD to automatically add `00631L.TW`.
- Use OMD to automatically open `00632R.TW`.
- Build a minimum-variance or max-diversification live optimizer for the current ETF set.
- Treat four ETF ranks as a valid substitute for S&P 500 decile ranks.
- Tune hyperparameters on the current latest window until Sharpe improves.
- Daily rebalance from OMD-like scores.
- Promote transfer entropy without surrogate/null tests.
- Treat residual distance as a trade signal before it proves incremental value over existing correlation and vol shadows.

## Current Conclusion

This paper is useful, but mainly as a design warning and shadow-diagnostic source.

Best import:

- residual-distance/crowding diagnostic
- no-trade hysteresis discipline
- volatility-rank/risk-state framing

Not ready:

- full OMD optimizer
- return-rank alpha
- transfer-entropy live overlay
- covariance optimizer

Final current strategy impact:

- No latest-strategy target-weight change.
- No production wiring.
- Keep as research/shadow candidate.
