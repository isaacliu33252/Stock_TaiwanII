# 2609.04917 Selection Ledger

- status: available_for_confirmatory_review
- active_shadow_candidates: staged_reentry, a2118_seed_averaging
- artifact_count: 80
- frozen_confirmatory_specification_available: True
- blocking_reasons: none

| artifact | suffix | mtime |
| --- | --- | --- |
| moira_policy_critic_validation_shadow.json | .json | 2026-09-09T12:25:11 |
| promotion_blocked_diagnostic.md | .md | 2026-09-09T12:25:07 |
| promotion_blocked_diagnostic.json | .json | 2026-09-09T12:25:07 |
| golden2_promotion_candidate_review.md | .md | 2026-09-09T12:25:07 |
| golden2_promotion_candidate_review.json | .json | 2026-09-09T12:25:07 |
| golden2_same_window_candidate_backtests.md | .md | 2026-09-09T12:25:05 |
| golden2_same_window_candidate_backtests.json | .json | 2026-09-09T12:25:05 |
| group_a_plus_promotion_gate_20260909.json | .json | 2026-09-09T12:24:41 |
| tsi_stress_oos.md | .md | 2026-09-09T12:22:58 |
| tsi_stress_oos.json | .json | 2026-09-09T12:22:58 |
| staged_reentry_promotion_review.json | .json | 2026-09-09T12:21:31 |
| relative_reentry_promotion_gate.md | .md | 2026-09-09T12:21:27 |
| relative_reentry_promotion_gate.json | .json | 2026-09-09T12:21:27 |
| relative_reentry_candidate_review.md | .md | 2026-09-09T12:21:26 |
| relative_reentry_candidate_review.json | .json | 2026-09-09T12:21:26 |
| a2118_seed_averaging_promotion_gate.md | .md | 2026-09-09T12:19:38 |
| a2118_seed_averaging_promotion_gate.json | .json | 2026-09-09T12:19:38 |
| a2118_seed_averaging_forward_shadow_monitor.md | .md | 2026-09-09T12:19:38 |
| a2118_seed_averaging_forward_shadow_monitor.json | .json | 2026-09-09T12:19:38 |
| a2118_seed_averaging_live_inference_snapshot.json | .json | 2026-09-09T12:19:36 |
| defensive_cash_floor_guarded_candidate.json | .json | 2026-09-09T12:12:53 |
| defensive_cash_floor_signed_approval_validation.json | .json | 2026-09-09T12:12:53 |
| llm_state_reward_human_exception_signed_approval_validation.json | .json | 2026-09-09T12:12:44 |
| synthetic_augmentation_validation_readiness_review.json | .json | 2026-09-09T12:12:13 |
| synthetic_augmentation_validation_audit.json | .json | 2026-09-09T12:12:12 |
| 2608_20179_dynamic_cvar_forward_validation.md | .md | 2026-09-09T12:12:10 |
| 2608_20179_dynamic_cvar_forward_validation.json | .json | 2026-09-09T12:12:10 |
| 2602_24037_scr_readiness_robustness.md | .md | 2026-09-09T12:10:50 |
| 2602_24037_scr_readiness_robustness.json | .json | 2026-09-09T12:10:50 |
| 2607_16450_bootstrap_promotion_gate.json | .json | 2026-09-09T12:08:51 |
| 2607_16450_candidate_tail_review.json | .json | 2026-09-09T12:08:04 |
| 2607_16450_turnover_cost_robustness.json | .json | 2026-09-09T12:08:04 |
| recovery_boost_spillover_gate_shadow.json | .json | 2026-09-09T12:06:29 |
| 2608_15841_candidate_auxiliary_bank_blueprint.md | .md | 2026-09-09T12:04:34 |
| 2608_15841_candidate_auxiliary_bank_blueprint.json | .json | 2026-09-09T12:04:34 |
| 2509_02986_ctbc_promotion_readiness_gate.md | .md | 2026-09-09T12:04:15 |
| 2509_02986_ctbc_promotion_readiness_gate.json | .json | 2026-09-09T12:04:15 |
| ncf_data_validation_20260909.json | .json | 2026-09-09T11:10:50 |
| a2118_independent_ppo_v1_80k_integration_new_model_80k_cap20_seed123_20260908.json | .json | 2026-09-08T22:50:54 |
| a2118_independent_ppo_v1_80k_integration_new_model_80k_cap20_seed7_20260908.json | .json | 2026-09-08T22:50:39 |

## Recommended Next Actions

- choose exactly one active shadow candidate for confirmatory validation
- write a frozen specification with candidate name, parameters, windows, costs, and pass/fail rule
- treat later parameter changes as a new exploratory run, not as the confirmatory result
- keep the full attempted-artifact ledger attached to promotion review
