# 2604.14498 Synthetic Augmentation Validation GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\2604.14498.pdf`
- Title: `Improving Machine Learning Performance with Synthetic Augmentation`
- Authors: Charles Dezons, Sami Sellami, Oscar Ninou, Axel Pincon, Mel Sohm
- arXiv: `2604.14498v1`
- Paper date in PDF: 2026-02
- Review target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 final decision context

## Paper Summary

The paper studies when synthetic data augmentation helps financial machine
learning. Its main point is structural:

- synthetic augmentation changes the effective training distribution;
- extra samples may reduce variance, but can also introduce persistent
  distributional bias;
- performance must be tested against a size-matched null augmentation, not only
  against a real-only baseline;
- financial time-series evaluation should use block permutation tests to respect
  temporal dependence;
- synthetic data helps mainly in variance-dominant tasks such as persistent
  volatility forecasting;
- synthetic data is weak, neutral, or harmful in bias-dominant tasks such as
  near-efficient directional prediction;
- rare-regime targeting can improve domain metrics such as AP/F1, but may
  conflict with unconditional permutation p-values.

## Useful Ideas For GroupA+

### 1. Size-Matched Null Augmentation Gate

The strongest import is the null-control idea:

- compare synthetic augmentation against a same-size null augmentation;
- preserve low-level distributional properties;
- destroy predictive alignment;
- accept synthetic data only if it beats this null control out-of-sample.

GroupA+ mapping:

- FinStressTS synthetic scenarios should not be promoted just because they add
  rows.
- HMM-WJ paths should not be accepted because they look plausible.
- Dynamic CVaR / tail-cost scenario generators should be required to show
  incremental information beyond a null augmentation.

Import decision: useful as research/governance.

### 2. Block Permutation Test For Time Dependence

The paper's block permutation test is directly useful for GroupA+ because NCF,
volatility, crash-risk, and scenario diagnostics are temporally dependent.

GroupA+ mapping:

- evaluate loss differences by block, not independent row shuffling;
- report fold-level significance and rejection rate;
- require out-of-sample evidence, not training loss improvement.

Import decision: useful as validation method.

### 3. Task-Type Restriction

The paper's most important warning:

- synthetic augmentation is poor for near-efficient directional prediction;
- synthetic augmentation is more credible for volatility forecasting,
  tail-risk, or rare-regime diagnostics.

GroupA+ mapping:

- do not use synthetic data to directly improve `00631L` / `00632R` direction
  forecasts without strong validation;
- use synthetic data only for stress coverage, volatility readiness, crash-risk
  review, and scenario robustness;
- keep synthetic alpha blocked until directional OOS evidence beats the null.

Import decision: restrict synthetic data to governance/stress tasks.

### 4. Rare-Regime Metric Alignment

For rare events, the paper shows p-values alone can mislead. Domain metrics such
as AP/F1 must match the economic objective.

GroupA+ mapping:

- crash-window tasks should use AP/F1/recall at constrained false-positive rate;
- tail-risk tasks should use expected shortfall / drawdown / STARR / AP for
  crash labels;
- a globally significant p-value is not enough if the rare-regime metric does
  not improve.

Import decision: useful for future crash-window and synthetic-stress validation.

## Not Imported

Do not import:

- SPY option tick-tape models;
- U.S. daily equity panel parameters;
- bootstrap / copula / VAE / diffusion / TimeGAN outputs as live signals;
- synthetic data as direct alpha;
- random-forest tick-tape conclusions as Taiwan ETF trading rules;
- any automatic `00631L`, `00632R`, or Golden1_0531 change.

Reasons:

- The paper is an evaluation framework, not a Taiwan ETF strategy.
- Its own conclusion says synthetic data is not a universal source of
  predictive power.
- Directional prediction is the setting where synthetic augmentation is most
  likely to be neutral or harmful.
- GroupA+ latest governance already blocks synthetic scenario promotion.

## Fit With Existing GroupA+

This paper reinforces existing GroupA+ artifacts:

- `report/group_a_plus/latest/finstressts_decision_snapshot.json`
- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`

Current 2026-07-20 refreshed state:

- full pipeline completed `52 / 52`;
- `execution_allowed = true`;
- `source_freshness = ok`;
- daily status remains `warn`;
- dynamic CVaR readiness remains `blocked`;
- research shadow snapshot remains `blocked`;
- deployment consistency remains `manual_review_required`;
- promotion gate remains `blocked_multi_window`.

## Recommended GroupA+ Import

Implemented a research-only artifact:

- `synthetic_augmentation_validation_readiness_review`

Current implementation:

- Validation audit builder: `scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_audit.py`
- Validation audit JSON: `report/group_a_plus/latest/synthetic_augmentation_validation_audit.json`
- Builder: `scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py`
- Latest JSON: `report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json`
- History JSON: `report/group_a_plus/synthetic_augmentation_validation_readiness/history/20260720.json`
- Pipeline step: `synthetic_augmentation_validation_readiness_review`
- Research snapshot blocker: `synthetic_augmentation_validation_readiness_blocked`
- Daily status display: `Synthetic Augmentation Validation Readiness`

Current status for 2026-07-20 after NCF panel regeneration:

- validation audit: `passed`
- NCF 00631L panel now exports `actual_up_h1`, `actual_up_h5`, `actual_up_h20`
- directional audit: `passed`
- `directional_up_ensemble` AP `0.8500`, null p95 `0.8411`, p-value `0.02595`
- rare-regime validation audit: `passed`
- `rare_gain_h20` AP `0.8697`, null p95 `0.8598`, p-value `0.02794`
- `rare_mdd_h20` AP `0.6013`, null p95 `0.4806`, p-value `0.001996`
- `status = blocked`
- `size_matched_null_augmentation_implemented = true`
- `block_permutation_test_implemented = true`
- `walk_forward_oos_synthetic_validation_passed = true`
- `synthetic_validation_ready = false`
- `directional_synthetic_alpha_allowed = false`
- `synthetic_generator_promotion_allowed = false`
- `allow_00631l_add = false`
- `auto_rebalance_allowed = false`

## Latest Strategy Decision

No live strategy change.

For 2026-07-20:

- no auto rebalance;
- no new `00631L` add;
- no direct `00632R` hedge;
- no Golden1_0531 change;
- keep GroupA+ latest strategy unchanged;
- synthetic augmentation remains validation-only / research-only.

## Conclusion

There are useful ideas to import into GroupA+ governance:

- require size-matched null augmentation before accepting synthetic data;
- use block permutation tests for temporally dependent OOS losses;
- restrict synthetic augmentation to volatility, tail-risk, and rare-regime
  diagnostics unless directional evidence is strong;
- evaluate rare regimes with economic metrics, not p-values alone.

There is no direct live trading advantage to import now. This paper supports
keeping FinStressTS, HMM-WJ, and dynamic CVaR scenario ideas blocked from live
execution until they pass a rigorous synthetic-augmentation validation gate.
