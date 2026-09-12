# GroupA+ 2607.27461 OMD-Portfolio Final Handoff - 2026-08-21

## Paper

Local file:

- `C:\Users\isaac\Downloads\2607.27461.pdf`

Title:

- `Are Three Matrices All You Need To Beat the Market? Observable Matrix Dynamics for Portfolio Optimization`

Main idea:

- Build portfolio decisions from three matrices:
  - arccos correlation-distance matrix
  - trailing-return rank Markov chain
  - trailing-volatility rank Markov chain
- Use rank-bucketed market covariates, residual-distance diversification, no-trade bands, and transfer-entropy leader/crowding diagnostics.

## Final Decision

For current GroupA+, this paper is experimentally exhausted.

Do not promote.

Final strategy impact:

- No `daily_signal.py` wiring.
- No target-weight change.
- No auto rebalance.
- No `00631L.TW` add rule.
- No `00632R.TW` open rule.
- No risk-off or re-entry gate from OMD residual distance.
- Do not keep tuning OMD residual-distance thresholds on the current data.

Reason:

- The paper's full OMD-Portfolio is designed for a large S&P 500 single-stock cross-section.
- GroupA+ live allocation is a small ETF basket, so the ten-decile rank-chain machinery is structurally mismatched.
- The tested residual-distance adaptation did not beat simple volatility/drawdown baselines.
- Broad proxy-pool expansion also failed to produce incremental value.

## Files Created Or Updated

Main review:

- `docs/HANDOFF_2607_27461_OMD_PORTFOLIO_GROUPA_PLUS_REVIEW_20260821.md`

Shadow implementation:

- `group_a_plus/integrations/omd_residual_distance_shadow.py`
- `scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py`

Validation scripts:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py`

Latest artifacts:

- `report/group_a_plus/latest/omd_residual_distance_shadow.json`
- `report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.json`
- `report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.md`
- `report/group_a_plus/latest/omd_residual_distance_incremental_review.json`
- `report/group_a_plus/latest/omd_residual_distance_incremental_review.md`
- `report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.json`
- `report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.md`

History/log artifacts:

- `report/group_a_plus/omd_residual_distance_shadow/history/omd_residual_distance_shadow_20260820.json`
- `report/group_a_plus/omd_residual_distance_shadow_evaluation/history/omd_residual_distance_shadow_evaluation_20260820.json`
- `report/group_a_plus/omd_residual_distance_shadow_evaluation/history/omd_residual_distance_shadow_evaluation_20260820.md`
- `report/group_a_plus/omd_residual_distance_incremental_review/history/omd_residual_distance_incremental_review_20260820.json`
- `report/group_a_plus/omd_residual_distance_incremental_review/history/omd_residual_distance_incremental_review_20260820.md`
- `report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history/omd_residual_distance_incremental_review_20260820.json`
- `report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history/omd_residual_distance_incremental_review_20260820.md`
- `results/omd_residual_distance_shadow_log.jsonl`

## Commands Run

Build latest 4-ETF residual-distance shadow:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py --as-of 2026-08-20
```

Evaluate 4-ETF residual-distance shadow on historical stress / forward-drawdown windows:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py --as-of 2026-08-20
```

Evaluate 4-ETF residual-distance incremental value versus simple vol/drawdown baselines:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py --as-of 2026-08-20
```

Evaluate broad proxy-pool residual-distance incremental value:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py \
  --as-of 2026-08-20 \
  --broad-proxy-pool \
  --start 2019-01-02 \
  --output report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.json \
  --markdown report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.md \
  --history-dir report/group_a_plus/omd_residual_distance_broad_proxy_incremental_review/history
```

Compile checks passed:

```bash
.venv/bin/python -m py_compile \
  group_a_plus/integrations/omd_residual_distance_shadow.py \
  scripts/evaluate/build_group_a_plus_omd_residual_distance_shadow.py \
  scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py \
  scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py
```

## Experiment 1: Latest 4-ETF Residual-Distance Shadow

Universe:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`

Method:

- Compute daily returns.
- Use 126-trading-day rolling window.
- Build equal-weight GroupA+ market proxy.
- OLS-residualize each asset against the equal-weight proxy.
- Compute residual correlation.
- Convert correlation to arccos distance.
- Report pairwise raw/residual distances and basket crowding state.

Latest run:

- as_of: `2026-08-20`
- status: `available_for_shadow_review`
- state: `normal`
- usable tickers: `4`
- return observations: `504`
- rolling snapshots: `379`
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

- The diagnostic correctly shows `00631L.TW` is highly redundant with `0050.TW` in raw return space.
- Latest residual-distance state is not elevated.
- This is descriptive only and does not justify adding/reducing any position.

## Experiment 2: Historical Residual-Distance Validation

Script:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_shadow.py`

Output:

- `report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.md`

Result:

- status: `research_complete_do_not_promote`
- actual data: `2009-07-14` to `2026-08-20`
- total days: `4195`
- stress-window days: `1245`
- non-stress days: `2950`
- stress manual-review rate: `0.297992`
- non-stress manual-review rate: `0.750508`
- high-risk days with risk percentile >= 0.75: `2490`
- high-risk rate: `0.593564`

Blockers:

- `manual_review_rate_not_higher_in_stress_windows`
- `not_promoted_shadow_only`

H20 forward drawdown:

- high-risk mean H20 forward max drawdown: `-0.033137`
- normal mean H20 forward max drawdown: `-0.028804`
- high-risk mean H20 forward return: `0.00575`
- normal mean H20 forward return: `0.011413`

Stress-window coverage:

| Window | Days | Manual-review rate | Max risk pct | Mean H20 forward max DD |
| --- | ---: | ---: | ---: | ---: |
| `2018_correction` | `245` | `0.212245` | `0.948413` | `-0.033821` |
| `2020_covid` | `116` | `0.12069` | `0.607143` | `-0.056749` |
| `2022_rate_hike` | `246` | `0.211382` | `0.97619` | `-0.052932` |
| `2024_2026_live` | `638` | `0.396552` | `1.0` | `-0.032366` |
| `2025_2026_active` | `396` | `0.520202` | `1.0` | `-0.03379` |

Interpretation:

- High-risk buckets have slightly worse H20 drawdown, but the signal is too broad.
- 2020 Covid coverage is poor.
- Non-stress periods trigger more often than stress windows.
- Not suitable as a risk-off gate.

## Experiment 3: 4-ETF Incremental Review Versus Simple Baselines

Script:

- `scripts/evaluate/evaluate_group_a_plus_omd_residual_distance_incremental.py`

Output:

- `report/group_a_plus/latest/omd_residual_distance_incremental_review.md`

Method:

- Target: `0050.TW`
- OMD high risk: `low_distance_risk_percentile >= 0.75`
- Baseline high risk: `20d realized-vol percentile >= 0.75 OR drawdown-depth percentile >= 0.75`
- Outcome: H20 forward max drawdown <= `-5%`
- Rows: `4195`
- Rows with H20 outcome: `4169`

Classifier result:

| Signal | Signal rate | Precision | Recall | FPR | Precision lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.591749` | `0.187272` | `0.578947` | `0.594779` | `0.978367` |
| `vol_high` | `0.28616` | `0.236379` | `0.353383` | `0.270246` | `1.234917` |
| `drawdown_high` | `0.277525` | `0.259291` | `0.37594` | `0.254227` | `1.354618` |
| `baseline_high` | `0.411609` | `0.244172` | `0.525063` | `0.384752` | `1.275633` |
| `omd_only` | `0.362437` | `0.176042` | `0.333333` | `0.369327` | `0.9197` |
| `both_high` | `0.229312` | `0.205021` | `0.245614` | `0.225452` | `1.071093` |

Interpretation:

- OMD high-risk precision lift is below 1.0.
- Simple vol/drawdown baseline is stronger.
- Drawdown-depth alone is stronger than OMD.
- `omd_only` is worse than the unconditional base rate.
- No independent incremental edge.

## Experiment 4: Broad Proxy-Pool Incremental Review

Reason:

- The 4-ETF basket may be too small for OMD.
- A broader Taiwan/US/FX/credit pool is closer to the paper's cross-sectional spirit.

Broad proxy pool:

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

Output:

- `report/group_a_plus/latest/omd_residual_distance_broad_proxy_incremental_review.md`

Result:

- status: `research_complete_do_not_promote`
- actual data: `2019-06-27` to `2026-08-20`
- rows: `1864`
- rows with H20 outcome: `1718`
- outcome: H20 forward max drawdown <= `-5%`

Classifier result:

| Signal | Signal rate | Precision | Recall | FPR | Precision lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.37078` | `0.175824` | `0.287918` | `0.395034` | `0.776519` |
| `vol_high` | `0.347497` | `0.318258` | `0.488432` | `0.306245` | `1.405571` |
| `drawdown_high` | `0.294529` | `0.395257` | `0.514139` | `0.230248` | `1.745633` |
| `baseline_high` | `0.470896` | `0.346106` | `0.719794` | `0.398044` | `1.528562` |
| `omd_only` | `0.231665` | `0.170854` | `0.174807` | `0.248307` | `0.75457` |
| `both_high` | `0.139115` | `0.1841` | `0.113111` | `0.146727` | `0.813071` |

Bucket H20 outcomes:

| Bucket | Days | H20 mean forward max DD | H20 mean forward return |
| --- | ---: | ---: | ---: |
| `omd_only` | `445` | `-0.027975` | `0.000957` |
| `baseline_only` | `590` | `-0.051604` | `0.004415` |
| `both_high` | `239` | `-0.023009` | `0.049205` |
| `neither_high` | `590` | `-0.015559` | `0.041647` |
| `omd_high` | `684` | `-0.026112` | `0.019059` |
| `baseline_high` | `829` | `-0.043156` | `0.017647` |

Interpretation:

- Broad proxy pool did not rescue the OMD residual-distance signal.
- OMD precision lift got worse than the 4-ETF version.
- Simple drawdown-depth percentile remained much stronger.
- `omd_only` again had precision below base rate.
- This closes the main "maybe the universe was too small" objection for a first-pass GroupA+ adaptation.

## What Is Still Useful From The Paper

Conceptual lessons worth retaining:

- No-trade hysteresis is important; small score changes should not force trades.
- Volatility/risk ranking is more reliable than return-rank alpha.
- Large matrix/covariance optimizers are fragile and can overfit.
- Residual/crowding diagnostics can be descriptive, but must beat simple baselines before becoming gates.
- Daily rebalancing from slow cross-sectional features is likely turnover waste.

## What Not To Do

Do not:

- Promote OMD residual distance.
- Tune OMD thresholds further on this dataset.
- Wire OMD into `daily_signal.py`.
- Use OMD for target weights.
- Use OMD for `00631L.TW` add.
- Use OMD for `00632R.TW` open.
- Use OMD as risk-off or re-entry signal.
- Build a minimum-variance / max-diversification optimizer for the current ETF set.
- Treat four ETF ranks as a substitute for S&P 500 decile ranks.
- Treat transfer entropy as live overlay without surrogate/null tests.

## Final Status

`2607.27461` is complete for GroupA+ current strategy research.

Final verdict:

- Full OMD-Portfolio: not applicable to current GroupA+.
- 4-ETF residual-distance shadow: implemented, validated, not promotable.
- 4-ETF incremental test: negative.
- Broad proxy-pool incremental test: negative.
- Latest strategy: unchanged.
- Production wiring: none.
- Further work: only revisit with a genuinely different objective or a much richer Taiwan equity universe; do not keep tuning the tested residual-distance gate.

