# 2608.15841 Candidate Auxiliary Bank Blueprint

- Policy: `research_only_no_weight_change`
- Training allowed: `False`
- Promotion allowed: `False`
- Decision: `blocked_until_readiness_gates_pass`
- Blockers: `live_feature_freshness_ok, quest_trader_retrained_for_group_a_plus, downstream_policy_lift_validated, multi_window_cost_turnover_passed, temporal_regime_stability_passed, auxiliary_head_lifecycle_passed, delayed_credit_alignment_passed`

## Candidate Grid

| bank | questions | K | role |
|---|---:|---:|---|
| `gvf_bank_16_k10` | 16 | 10 | `minimum_viable_candidate` |
| `gvf_bank_32_k10` | 32 | 10 | `balanced_default_candidate` |
| `gvf_bank_32_k20` | 32 | 20 | `delayed_credit_candidate` |
| `gvf_bank_64_k20` | 64 | 20 | `upper_complexity_candidate` |

## Admission Tests

- `point_in_time_feature_build_no_forward_label_leakage`
- `purged_walk_forward_policy_impact_passed`
- `full_window_delta_final_value_nonnegative_after_costs`
- `delta_sharpe_ratio_nonnegative`
- `delta_max_drawdown_nonnegative`
- `turnover_to_initial_below_cap`
- `temporal_regime_stability_passed`
- `live_feature_freshness_ok`
- `seed_sensitivity_small_enough`

This blueprint is research-only and does not train a model or change weights.
