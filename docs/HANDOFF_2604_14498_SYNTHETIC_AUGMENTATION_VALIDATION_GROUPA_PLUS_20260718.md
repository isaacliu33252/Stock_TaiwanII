# Handoff: 2604.14498 Synthetic Augmentation Validation for GroupA+（2026-07-18）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\2604.14498.pdf`
- Paper: `Improving Machine Learning Performance with Synthetic Augmentation`
- Target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 final decision context
- Import type: validation governance only

## Final Decision

No live strategy change.

- No auto rebalance.
- No new `00631L` add.
- No direct `00632R` hedge.
- Keep Golden1_0531 unchanged.
- Do not use synthetic augmentation as direct alpha.

## Useful Import

The paper is useful as a validation gate for synthetic data and scenario
generators.

Imported governance concepts:

- size-matched null augmentation;
- block permutation test for weak temporal dependence;
- bias/variance framing for synthetic augmentation;
- task-type restriction:
  - directional prediction: default blocked unless strong OOS evidence;
  - volatility / tail-risk / rare-regime diagnostics: research-only candidate;
- rare-regime metrics must match the economic objective, not p-values alone.

## Why It Matters For Existing GroupA+

This paper directly affects how to judge:

- `FinStressTS`;
- `HMM-WJ synthetic scenario readiness`;
- `dynamic CVaR tail/cost readiness`;
- density-head / GMM tail-risk research;
- any future TimeGAN / diffusion / copula / bootstrap augmentation.

Current state remains restrictive:

- `report/group_a_plus/latest/finstressts_decision_snapshot.json`
  - `status = blocked`
- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
  - `status = blocked`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
  - `status = blocked`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
  - `status = blocked`
- `results/group_a_plus_promotion_gate_20260720.json`
  - `decision = blocked_multi_window`

## Not Imported

Do not import:

- SPY options tick-tape model results;
- U.S. daily equity panel parameters;
- bootstrap / copula / VAE / diffusion / TimeGAN outputs as trading signals;
- synthetic directional alpha for `00631L` or `00632R`;
- any automatic target-weight change.

## Implemented Artifact

Implemented first research-only version:

- `synthetic_augmentation_validation_readiness_review`

Files:

- Validation audit builder:
  `scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_audit.py`
- Validation audit test:
  `tests/test_build_group_a_plus_synthetic_augmentation_validation_audit.py`
- Validation audit latest JSON:
  `report/group_a_plus/latest/synthetic_augmentation_validation_audit.json`
- Validation audit history JSON:
  `report/group_a_plus/synthetic_augmentation_validation_audit/history/20260720.json`
- Builder:
  `scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py`
- Unit test:
  `tests/test_build_group_a_plus_synthetic_augmentation_validation_readiness_review.py`
- Latest JSON:
  `report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json`
- History JSON:
  `report/group_a_plus/synthetic_augmentation_validation_readiness/history/20260720.json`

Pipeline/status integration:

- `scripts/run/run_ncf_daily_pipeline.py`
  - adds best-effort step `synthetic_augmentation_validation_audit`;
  - adds best-effort step `synthetic_augmentation_validation_readiness_review`;
  - runs both before `research_shadow_decision_snapshot`;
  - does not depend on same-run promotion gate.
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  - consumes the new readiness artifact;
  - adds blocker `synthetic_augmentation_validation_readiness_blocked`.
- `scripts/misc/check_group_a_plus_daily_status.py`
  - displays the synthetic validation readiness block in daily markdown/json.

Current 2026-07-20 output after NCF panel regeneration:

- Audit `status = passed` overall.
- NCF 00631L panel now exports:
  - `actual_up_h1`;
  - `actual_up_h5`;
  - `actual_up_h20`.
- Directional and rare-regime panel tests pass:
  - panel coverage: `2025-01-02` to `2026-06-18`, `352` rows;
  - `directional_up_ensemble`: AP `0.8500`, null p95 `0.8411`, block permutation p-value `0.02595`;
  - `rare_gain_h20`: AP `0.8697`, null p95 `0.8598`, block permutation p-value `0.02794`;
  - `rare_mdd_h20`: AP `0.6013`, null p95 `0.4806`, block permutation p-value `0.001996`.
- `status = blocked`
- `as_of = 2026-07-20`
- `size_matched_null_augmentation_implemented = true`
- `block_permutation_test_implemented = true`
- `walk_forward_oos_synthetic_validation_passed = true`
- `directional_audit_tested = true`
- `directional_audit_passed = true`
- `rare_regime_audit_passed = true`
- `synthetic_validation_ready = false`
- `directional_synthetic_alpha_allowed = false`
- `synthetic_generator_promotion_allowed = false`
- `allow_00631l_add = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`

Key blockers:

- `finstressts_snapshot_blocked`
- `hmm_wj_scenario_readiness_blocked`
- `scenario_generator_not_decision_ready`
- `dynamic_cvar_tail_cost_readiness_blocked`
- `tail_cost_readiness_not_ready`
- `density_tail_model_unstable_research_only`

Optional warning:

- `promotion_gate_unavailable_optional`
  - promotion gate is not a hard dependency because the daily pipeline produces
    promotion gate after daily status.

## Practical 2026-07-20 Impact

None on live allocation.

The paper reinforces the current 2026-07-20 final decision:

- `execution_allowed = true` and `source_freshness = ok` after full refresh,
  but governance still blocks automatic trading;
- dynamic CVaR remains `blocked`;
- research shadow remains `blocked`;
- deployment consistency remains `manual_review_required`;
- promotion gate remains `blocked_multi_window`.

Final action:

- hold / freeze risk additions;
- do not add `00631L`;
- do not open `00632R`;
- keep Golden1_0531 unchanged.

## Verification

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_synthetic_augmentation_validation_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py`
  - `35 passed`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_synthetic_augmentation_validation_audit.py tests/test_build_group_a_plus_synthetic_augmentation_validation_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py`
  - `37 passed`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_synthetic_augmentation_validation_audit.py tests/test_build_group_a_plus_synthetic_augmentation_validation_readiness_review.py tests/test_run_ncf_daily_pipeline.py`
  - `20 passed`
- `.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py scripts/run/run_ncf_daily_pipeline.py scripts/misc/check_group_a_plus_daily_status.py`
  - passed
- `.venv/bin/python -m py_compile scripts/misc/ncf_00631l.py scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_audit.py scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py scripts/run/run_ncf_daily_pipeline.py`
  - passed

## Next Step

Do not tune trading weights from this paper. The next legitimate improvement
is to validate an actual synthetic generator, not just the existing NCF panel:

- generate HMM-WJ or FinStressTS synthetic scenarios with a frozen spec;
- compare real-only vs synthetic-augmented training under the same walk-forward
  folds;
- require synthetic-augmented results to beat the size-matched null and pass
  block permutation before generator promotion.
