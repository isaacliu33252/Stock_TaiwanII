# 2604.02126 Robust Hedge Review for GroupA+

Date: 2026-08-29  
Paper: `C:\Users\isaac\Downloads\2604.02126.pdf`  
Title: `Hedging market risk and uncertainty via a robust portfolio approach`  
arXiv: `2604.02126v2`, paper date `2026-07-08`

## Decision

Do not change GroupA+ live target weights.

Do not open or increase `00632R.TW`.

Keep `Golden1_0531` unchanged.

Keep the paper import as research-only shadow diagnostics.

Final archive decision after user review:

- The paper's core question was explicitly considered: when
  volatility/covariance forecasts are uncertain, shrink the `00632R.TW`
  hedge ratio rather than simply cutting upside exposure.
- This was implemented as `standard_hedge_ratio` versus
  `robust_uncertainty_adjusted_hedge_ratio` diagnostics.
- The concept is appropriate for A21.18/A21.19-style hedge sizing, but the
  current GroupA+ gates do not show live inverse eligibility:
  `allow_00632r_open = false`, `target_weight_change_allowed = false`, and
  `auto_rebalance_allowed = false`.
- Therefore the final action is: preserve as shadow/cap diagnostic only; do
  not use it to buy, open, or increase `00632R.TW`; do not use it to unlock
  `00631L.TW`; keep `Golden1_0531` unchanged.

## What Was Imported

The useful paper idea is a robust dynamic minimum-variance hedge ratio:

`h*=sgn(cov_sf)*(abs(cov_sf)-theta_cov)^+/(var_f+theta_var)`

The practical subcase is:

`h*=cov_sf/(var_f+theta_var)`

For GroupA+ this was mapped as:

- hedged asset: `0050.TW`
- hedge instrument: `00632R.TW`
- return definition: daily log return from close
- covariance/variance proxy: rolling realized daily covariance and variance
- uncertainty proxy: rolling forecast residual volatility
- output role: advisory/cap-only diagnostic, not a live target-weight input

## Artifact

Implemented:

- `scripts/evaluate/build_group_a_plus_2604_02126_robust_hedge_review.py`
- `scripts/evaluate/sweep_group_a_plus_2604_02126_robust_hedge.py`
- `scripts/evaluate/validate_group_a_plus_2604_02126_robust_hedge_temporal_oos.py`
- `scripts/evaluate/evaluate_group_a_plus_2604_02126_forecast_variants.py`
- `scripts/evaluate/evaluate_group_a_plus_2604_02126_cost_stress.py`
- `tests/test_build_group_a_plus_2604_02126_robust_hedge_review.py`
- `tests/test_sweep_group_a_plus_2604_02126_robust_hedge.py`
- `tests/test_validate_group_a_plus_2604_02126_robust_hedge_temporal_oos.py`
- `tests/test_evaluate_group_a_plus_2604_02126_forecast_variants.py`
- `tests/test_evaluate_group_a_plus_2604_02126_cost_stress.py`
- `report/group_a_plus/latest/2604_02126_robust_hedge_review.json`
- `report/group_a_plus/2604_02126_robust_hedge/history/2604_02126_robust_hedge_review_20260828.json`
- `report/group_a_plus/latest/2604_02126_robust_hedge_sweep.json`
- `report/group_a_plus/latest/2604_02126_robust_hedge_sweep.md`
- `report/group_a_plus/2604_02126_robust_hedge_sweep/history/2604_02126_robust_hedge_sweep_20260828.json`
- `report/group_a_plus/latest/2604_02126_robust_hedge_temporal_oos.json`
- `report/group_a_plus/latest/2604_02126_robust_hedge_temporal_oos.md`
- `report/group_a_plus/2604_02126_robust_hedge_temporal_oos/history/2604_02126_robust_hedge_temporal_oos_20260829.json`
- `report/group_a_plus/latest/2604_02126_forecast_variants.json`
- `report/group_a_plus/latest/2604_02126_forecast_variants.md`
- `report/group_a_plus/2604_02126_forecast_variants/history/2604_02126_forecast_variants_20260828.json`
- `report/group_a_plus/latest/2604_02126_cost_stress.json`
- `report/group_a_plus/latest/2604_02126_cost_stress.md`
- `report/group_a_plus/2604_02126_cost_stress/history/2604_02126_cost_stress_20260828.json`

Command run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2604_02126_robust_hedge_review.py --as-of 2026-08-28
.venv/bin/python scripts/evaluate/sweep_group_a_plus_2604_02126_robust_hedge.py --as-of 2026-08-28
.venv/bin/python scripts/evaluate/validate_group_a_plus_2604_02126_robust_hedge_temporal_oos.py
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2604_02126_forecast_variants.py --as-of 2026-08-28
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2604_02126_cost_stress.py --as-of 2026-08-28
```

Test run:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2604_02126_robust_hedge_review.py
.venv/bin/python -m pytest tests/test_sweep_group_a_plus_2604_02126_robust_hedge.py
.venv/bin/python -m pytest tests/test_validate_group_a_plus_2604_02126_robust_hedge_temporal_oos.py
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2604_02126_forecast_variants.py
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2604_02126_cost_stress.py
```

Combined result: `17 passed`.

## 2026-08-28 Results

Data window after warmup:

- start: `2021-01-14`
- end: `2026-08-28`
- observations: `1364`

Latest strategy context:

- latest preview `00632R.TW` target weight: `0.1647819322`
- robust variance-only advisory exposure after 30% cap: `0.3000000000`
- advisory minus latest preview: `+0.1352180678`

Method comparison:

| Method | Latest raw hedge ratio | Latest long inverse exposure | Mean abs daily turnover | HE | Conditional HE | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Standard MV | `-0.950649354` | `0.300000000` | `0.000402955` | `-14.690435358` | `0.370705754` | diagnostic only |
| Robust variance-only | `-0.313308982` | `0.300000000` | `0.001012685` | `-0.570441619` | `0.363116508` | best shadow candidate, not live |
| Robust full-box | `-0.000000000` | `0.000000000` | `0.000000000` | `0.000000000` | `0.000000000` | too conservative |

Interpretation:

- The paper's variance-uncertainty shrinkage is useful as a hedge-sizing diagnostic.
- In the current GroupA+ daily-close proxy, robust variance-only does not prove a live improvement: capped exposure still reaches 30%, and turnover is higher than the capped standard hedge.
- Full box uncertainty collapses the hedge to zero, matching the paper's warning that covariance uncertainty can become too conservative.
- Conditional hedge effectiveness is similar between standard and robust variance-only, but the robust version has much better total variance behavior than standard in this proxy test.

## Parameter Sweep

Sweep grid:

- rolling window: `63`, `126`, `252`
- uncertainty window: `63`, `126`, `252`
- max `00632R.TW` diagnostic cap: `10%`, `20%`, `30%`
- total parameter sets: `27`

Selection filter:

- robust turnover reduction versus standard must be non-negative;
- robust exposure standard-deviation reduction versus standard must be non-negative;
- robust conditional hedge effectiveness must be at least standard conditional hedge effectiveness.

Sweep result:

- eligible parameter count: `0`
- no parameter set passed the shadow stability filter;
- top-scored rows improved the very poor standard total-variance HE, but still failed turnover, exposure stability, or conditional hedge effectiveness;
- full-box zero/near-zero exposure rate was high in top rows, ranging from about `88.7%` to `100%`.

Top row:

- window: `252`
- uncertainty window: `126`
- cap: `10%`
- robust latest exposure: `10%`
- robust turnover reduction versus standard: `-0.912342`
- robust exposure std reduction versus standard: `-0.098377`
- robust conditional HE: `0.237638`
- standard conditional HE: `0.309686`
- pass: `False`

Conclusion after sweep:

- The negative live decision is not a single-parameter artifact.
- Under current daily-close proxies, the robust variance-only hedge is still useful only as a research diagnostic.
- It should not replace the existing LETF readiness gates and should not increase `00632R.TW`.

## Temporal OOS Validation

Temporal windows:

- `early_2020_2022`: `2020-01-01` to `2022-12-31`
- `mid_2023_2024`: `2023-01-01` to `2024-12-31`
- `recent_2025_2026`: `2025-01-01` to `2026-08-28`

Implementation note:

- volatility/covariance warmup starts at `2020-01-01`;
- each OOS window is evaluated only from its own start date;
- this avoids treating missing warmup observations as failed OOS evidence.

Temporal OOS result:

- parameter count: `27`
- eligible parameter count: `0`
- temporal OOS passed: `False`

Best temporal row:

- window: `126`
- uncertainty window: `126`
- cap: `30%`
- valid windows: `3`
- passed windows: `0`
- mean robust turnover reduction versus standard: `-0.881545`
- mean robust conditional HE delta versus standard: `-0.037649`
- all windows passed: `False`

Conclusion after temporal OOS:

- The robust hedge ratio does not show stable cross-period superiority under current GroupA+ inputs.
- No tested parameter set can justify live `00632R.TW` opening or increase.
- The only defensible import is a research-only diagnostic/cap monitor.

## Forecast Variant Review

Forecast models tested:

- `rolling_mean`
- `AR(1)`
- `HAR-lite`

This addresses whether the first proxy was too far from the paper's
AR/HAR-style realized-volatility forecast setup.

Result as of `2026-08-28`:

| Forecast model | Observations | Robust latest exposure | Turnover delta vs standard | Exposure std delta vs standard | Robust conditional HE | Standard conditional HE | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| rolling mean | `1364` | `0.300000` | `-1.513147` | `-0.322986` | `0.363117` | `0.370706` | `False` |
| AR(1) | `1358` | `0.300000` | `-6.274324` | `-0.360688` | `0.339119` | `0.373962` | `False` |
| HAR-lite | `1323` | `0.240273` | `-17.005848` | `-0.592123` | `0.311572` | `-2122.478116` | `False` |

Forecast-variant conclusion:

- No forecast variant passed the shadow filter.
- AR(1) and HAR-lite did not rescue the live case.
- HAR-lite produced unstable standard-hedge tail behavior; robust shrinkage
  reduced the damage but still failed turnover and exposure-stability checks.
- The remaining paper-replication gap is now mainly high-frequency realized
  covariance and the paper's ETF universe, not the GroupA+ live decision.

## Transaction Cost Stress

Cost scenarios:

- forecast models: `rolling_mean`, `AR(1)`, `HAR-lite`
- cost bps: `0`, `5`, `10`, `20`, `50`
- total scenarios: `15`
- eligible scenarios: `0`

Result:

| Forecast model | Cost bps | Robust minus standard return | Robust minus standard Sharpe | Robust minus standard max drawdown | Pass |
| --- | ---: | ---: | ---: | ---: | --- |
| rolling mean | `0` | `-0.212627` | `-0.029140` | `0.001569` | `False` |
| rolling mean | `50` | `-0.216528` | `-0.031778` | `0.000702` | `False` |
| AR(1) | `0` | `-0.568893` | `-0.016449` | `-0.025802` | `False` |
| AR(1) | `50` | `-0.629113` | `-0.071662` | `-0.042015` | `False` |
| HAR-lite | `0` | `-0.580009` | `-0.034752` | `-0.030254` | `False` |
| HAR-lite | `50` | `-0.677973` | `-0.122034` | `-0.052550` | `False` |

Cost-stress conclusion:

- The paper's transaction-cost advantage does not appear in the GroupA+
  `0050.TW`/`00632R.TW` daily-close proxy.
- Robust variance-only is not net-superior to standard under any tested cost
  scenario.
- This removes the transaction-cost blocker only as an evaluated item; it does
  not support promotion.

## Live Blockers

The review is intentionally blocked for live promotion:

- `daily_close_proxy_not_high_frequency_realized_covariance`
- `forecast_uncertainty_proxy_not_paper_exact_ar_har_realized_covariance`
- `full_box_covariance_uncertainty_too_conservative`
- `letf_readiness_blocks_00632r_open`
- `live_hedge_policy_not_validated_for_robust_ratio`
- `research_only_robust_hedge_review`
- `transaction_cost_and_execution_slippage_not_revalidated`
- `no_parameter_set_passed_shadow_stability_filter`
- `no_parameter_set_passed_all_temporal_windows`
- `no_forecast_variant_passed_shadow_filter`
- `no_cost_scenario_passed_robust_vs_standard_filter`

## Next Step

Only worth continuing if we want a second-stage shadow experiment:

- use intraday realized covariance if available;
- add HAR/AR realized volatility forecasts closer to the paper;
- evaluate robust hedge as a cap on existing `00632R.TW`, not as permission to increase it;
- run OOS cost/slippage validation against current GroupA+ latest strategy before any promotion discussion.
