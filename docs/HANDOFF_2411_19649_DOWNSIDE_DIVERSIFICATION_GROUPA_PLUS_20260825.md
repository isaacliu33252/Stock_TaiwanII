# Handoff: 2411.19649 Downside Diversification Forecast for GroupA+

Date: 2026-08-25  
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`  
Scope: A21.18 / GroupA+ downside-diversification diagnostics and OOS forecast shadows.

## Final Decision

Do not change live weights.

Keep all work as shadow/research only:

- `target_weight_change_allowed = false`
- `replace_a2118 = false`
- `promote_to_live_weights = false`
- Transformer / Autoformer training is blocked for now.

The best operational baseline is still the simple semi-covariance family, especially `EWMA window=120`, not DCC or Transformer.

## User Intent Captured

The user explicitly wanted:

- Stage 1: compare current A21.18, historical covariance, historical semi-covariance, EWMA semi-covariance.
- Do not let an optimizer freely control A21.18.
- Do not allow meaningless simultaneous long leveraged ETF and inverse ETF offsets such as `00631L + 00632R`.
- Use regime constraints:
  - `golden1`: allowed `0050`, `00631L`; forbid `00632R`.
  - `defensive`: allowed `0050`, `00679B`, cash; forbid `00631L`, `00632R`.
  - `bear / inverse eligible`: allow `00632R` only when existing A21.18 permits.
- Stage 2: forecast the target that matters, not the full covariance matrix:
  - future 20d downside correlation
  - future 20d downside semi-covariance
  - downside-diversification failure event
- Stage 2 models:
  - rolling historical semi-covariance
  - EWMA semi-covariance
  - shrinkage semi-covariance
- Stage 3: only if simple models have OOS value, test Downside-DCC / asymmetric DCC before any deep model.
- Stage 4: only consider Transformer / Autoformer if simple models and DCC show both statistical and economic value.

## Files Added

Stage 1:

- `scripts/evaluate/build_group_a_plus_2411_19649_semicovariance_review.py`
- `tests/test_build_group_a_plus_2411_19649_semicovariance_review.py`
- `report/group_a_plus/latest/2411_19649_semicovariance_review.json`

Stage 2:

- `scripts/evaluate/build_group_a_plus_a2118_downside_diversification_forecast_shadow.py`
- `tests/test_build_group_a_plus_a2118_downside_diversification_forecast_shadow.py`
- `report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json`

Stage 3:

- `scripts/evaluate/build_group_a_plus_a2118_downside_dcc_forecast_shadow.py`
- `tests/test_build_group_a_plus_a2118_downside_dcc_forecast_shadow.py`
- `report/group_a_plus/latest/a2118_downside_dcc_forecast_shadow.json`

Stage 4:

- `scripts/evaluate/build_group_a_plus_a2118_transformer_admission_gate.py`
- `tests/test_build_group_a_plus_a2118_transformer_admission_gate.py`
- `report/group_a_plus/latest/a2118_transformer_admission_gate.json`

## Stage 1 Result: Semi-Covariance Information Test

Report:

- `report/group_a_plus/latest/2411_19649_semicovariance_review.json`

Coverage:

- as_of: `2026-08-24`
- observations: `756`
- tickers: `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`, `0056.TW`, `00713.TW`, `00878.TW`, `00646.TW`

Decision:

- `semi_covariance_adds_information_vs_ordinary_covariance = true`
- `use_as_fifth_asset_filter = true`
- `target_weight_change_allowed = false`
- `replace_a2118_optimizer = false`

Key finding:

- Defensive pair `0050.TW` vs `00679B.TWO`:
  - ordinary corr: `-0.010750`
  - historical semi-corr: `0.248793`
  - EWMA semi-corr: `0.207276`

Interpretation:

Ordinary correlation says `0050` and `00679B` are almost uncorrelated, but downside semi-correlation says they still share some downside co-movement. That is real incremental information, but not enough to change live allocation.

Fifth-asset candidates:

- `0056.TW`: ordinary corr `0.788413`, max conditional downside corr `0.846964`
- `00713.TW`: ordinary corr `0.620776`, max conditional downside corr `0.790884`
- `00878.TW`: ordinary corr `0.790683`, max conditional downside corr `0.837202`
- `00646.TW`: ordinary corr `0.609796`, max conditional downside corr `0.705482`

Interpretation:

No fifth-asset candidate looked like a hidden diversifier. They were already materially correlated with `0050`; stress correlation mostly confirmed that.

Known limitation:

- `rolling_risk_free_rate_unavailable_using_proxy`
- Local database did not have a real rolling risk-free rate series, so risk-free MAR was proxied.

## Stage 2 Result: A2118 Downside-Diversification Forecast Shadow

Report:

- `report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json`

Target:

- future `t+1` to `t+20` downside semi-corr
- future `t+1` to `t+20` downside semi-cov
- binary failure:
  - future 20d `0050` MDD `<= -5%`
  - and candidate future 20d return `< 0`

Models:

- `historical`
- `ewma`
- `shrinkage`

Windows:

- `20`, `60`, `120`

Coverage:

- as_of: `2026-08-24`
- OOS lookback: `252` days
- prediction rows: `11340`
- pairs:
  - `0050.TW_00679B.TWO`
  - `0050.TW_0056.TW`
  - `0050.TW_00713.TW`
  - `0050.TW_00878.TW`
  - `0050.TW_00646.TW`

Decision:

- `simple_models_have_oos_bucket_value = true`
- `advance_to_downside_dcc_research = true`
- `advance_to_transformer_research = false`
- `target_weight_change_allowed = false`

Best simple model:

- model: `ewma`
- window: `120`
- Rank IC: `0.600397`
- high-risk bucket realized semi-corr: `0.687405`
- low-risk bucket realized semi-corr: `0.436835`
- MAE semi-corr: `0.205821`
- QLIKE-like semi-cov loss: `1.173850`

Defensive pair latest signal:

- latest signal date: `2026-07-27`
- reason latest date is earlier than as_of: realized target needs future 20 trading days through `2026-08-24`.
- `0050.TW_00679B.TWO`:
  - mostly `DIVERSIFICATION_GOOD`
  - historical 120 was `DIVERSIFICATION_WEAK`

Economic filter:

- `0050.TW_00679B.TWO`
  - historical 20:
    - failed signal count: `13`
    - net_filter_value: `+0.019303`
  - EWMA 20:
    - failed signal count: `15`
    - net_filter_value: `+0.014698`

Interpretation:

Simple semi-covariance models have useful OOS ranking signal. The economic filter is promising specifically for defensive `00679B` vs cash during failure states, but not robust enough across all fifth-asset candidates.

## Stage 3 Result: Downside-DCC Forecast Shadow

Report:

- `report/group_a_plus/latest/a2118_downside_dcc_forecast_shadow.json`

Method:

- fixed-parameter downside-DCC proxy
- `alpha = 0.03`
- `beta = 0.94`
- no parameter sweep
- no live effect

Coverage:

- as_of: `2026-08-24`
- OOS lookback: `252`
- prediction rows: `3780`
- same five pairs as Stage 2

Decision from Stage 3 alone:

- `downside_dcc_has_oos_bucket_value = true`
- `downside_dcc_improves_best_simple_rank_ic = true`
- `downside_dcc_has_positive_economic_filter_value = true`
- `target_weight_change_allowed = false`

Best DCC model:

- model: `downside_dcc`
- window: `60`
- Rank IC: `0.604762`
- high-risk bucket realized semi-corr: `0.686006`
- low-risk bucket realized semi-corr: `0.384764`
- MAE semi-corr: `0.216484`
- QLIKE-like semi-cov loss: `3273.876677`

Comparison vs Stage 2 best simple:

- best simple Rank IC: `0.600397`
- best DCC Rank IC: `0.604762`
- improvement: `+0.004365`

Interpretation:

DCC technically improves Rank IC, but the improvement is tiny. It is less than `0.01`, and only around 44% of a 0.01 Rank IC increment. It should not be treated as robust enough to justify deep models by itself.

Defensive latest DCC signals:

- `0050.TW_00679B.TWO`, latest signal date `2026-07-27`:
  - window 20: `DIVERSIFICATION_GOOD`, predicted semi-corr `-0.030346`
  - window 60: `DIVERSIFICATION_GOOD`, predicted semi-corr `0.047653`
  - window 120: `DIVERSIFICATION_GOOD`, predicted semi-corr `0.095530`

Economic filter:

- `0050.TW_00679B.TWO`, DCC window 20:
  - failed signal count: `6`
  - net_filter_value: `+0.025546`
  - avoided downside: `+0.025546`
  - opportunity cost: `0`

Important caveat:

The positive DCC economic result uses only 6 failed signals. That is too few to justify promotion or deep-model escalation.

## Stage 4 Result: Transformer Admission Gate

Report:

- `report/group_a_plus/latest/a2118_transformer_admission_gate.json`

Status:

- `blocked`

Decision:

- `admit_transformer_research = false`
- `admit_autoformer_research = false`
- `train_deep_model_now = false`
- `target_weight_change_allowed = false`

Blocking reasons:

- `dcc_rank_ic_improvement_not_material`
- `dcc_qlike_like_loss_worse_than_best_simple`
- `dcc_positive_filter_signal_count_too_small`

Gate thresholds:

- minimum DCC Rank IC improvement over simple: `0.02`
- minimum positive net filter value: `0.005`
- minimum positive failed signal count: `20`
- require DCC QLIKE-like loss not worse than simple: `true`

Evidence:

- Rank IC improvement:
  - DCC `0.604762`
  - simple `0.600397`
  - diff `+0.004365`
  - below `+0.02` materiality threshold
- QLIKE-like:
  - simple `1.173850`
  - DCC `3273.876677`
  - DCC much worse
- DCC positive economic filter:
  - net_filter_value `+0.025546`
  - signal count `6`
  - below minimum `20`

Interpretation:

The earlier Stage 3 field `advance_to_transformer_research = true` was too permissive because it only checked direction of improvement. The Stage 4 admission gate is the governing decision and blocks Transformer / Autoformer.

## Practical Meaning for 1,000,000 TWD Capital

The apparent DCC economic improvement versus simple in the best positive case:

- DCC net filter value: `+0.025546`
- simple net filter value: `+0.019303`
- difference: `+0.006243`

On 1,000,000 TWD:

- `1,000,000 * 0.006243 = 6,243 TWD` per obeyed 20d failed-signal event

But this is not a reliable expected profit estimate because:

- DCC positive case has only 6 signals.
- DCC Rank IC improvement is only `+0.004365`.
- DCC QLIKE-like loss is much worse than simple.

Conclusion:

There is no sufficient evidence that DCC adds stable real-money profit beyond simple semi-covariance filters.

## Current Preferred Operational Interpretation

Use these outputs as monitoring only:

- Stage 1 semi-covariance review: good diagnostic.
- Stage 2 EWMA/historical semi-covariance forecast: preferred shadow baseline.
- Stage 3 DCC: keep for observation, not promotion.
- Stage 4 Transformer gate: blocks deep model.

Current best candidate for continued monitoring:

- `EWMA window=120` for downside-diversification ranking.

Do not:

- add live weight changes
- let any optimizer replace A21.18
- use unconstrained semi-covariance minimization
- allow `00631L` and `00632R` offset positions as a mathematical variance trick
- train Transformer/Autoformer yet

## Commands Run

Stage 1:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2411_19649_semicovariance_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2411_19649_semicovariance_review.py -q
```

Stage 2:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_a2118_downside_diversification_forecast_shadow.py --oos-lookback-days 252
.venv/bin/python -m pytest tests/test_build_group_a_plus_a2118_downside_diversification_forecast_shadow.py -q
```

Stage 3:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_a2118_downside_dcc_forecast_shadow.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_a2118_downside_dcc_forecast_shadow.py -q
```

Stage 4:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_a2118_transformer_admission_gate.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_a2118_transformer_admission_gate.py -q
```

Combined tests after Stage 2:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_a2118_downside_diversification_forecast_shadow.py tests/test_build_group_a_plus_2411_19649_semicovariance_review.py -q
```

Observed test results:

- Stage 1 tests: `3 passed`
- Stage 2 tests: `3 passed`
- Stage 1 + Stage 2 combined: `6 passed`
- Stage 3 tests: `3 passed`
- Stage 4 tests: `3 passed`

Some tests emit pandas/numpy constant-input warnings in synthetic data. These warnings are expected from deterministic synthetic samples and did not block outputs.

## Known Implementation Notes

1. Stage 2 and Stage 3 are intentionally shadow-only.
2. Stage 2 includes shrinkage semi-covariance as a fixed shrink-to-zero proxy using `shrinkage_alpha = 0.25`.
3. Stage 3 DCC is a fixed-parameter proxy, not a fully estimated maximum-likelihood DCC model.
4. Stage 4 is the stricter governing decision for deep model admission. It supersedes the permissive Stage 3 `advance_to_transformer_research` field.
5. Default fifth candidates exclude `00751B`, consistent with the user's earlier note that `00751B` is not in GroupA+.
6. Reports are not yet wired into the daily pipeline. This was intentionally left standalone because Transformer was blocked and live weights must not change.

## Suggested Next Steps

1. Keep Stage 2 `EWMA window=120` as the primary shadow dashboard metric.
2. Monitor whether DCC window 60 continues to beat EWMA 120 by a material margin over more forward data.
3. Require at least 20 DCC positive economic failed signals before reconsidering deep models.
4. Consider adding a compact daily summary markdown for:
   - latest `0050_00679B` state
   - best simple vs DCC Rank IC
   - admission gate status
5. Do not integrate any of these outputs into live execution until a separate promotion gate is designed and passes.
