# 2509.02986 CTBC Promotion Readiness Gate

- Policy: `research_governance_only_no_weight_change`
- Decision: `do_not_promote_import_governance_requirements_only`
- Promotion allowed: `False`
- Latest strategy weight change allowed: `False`

## Checks

| check | pass |
|---|---:|
| `source_is_financial_strategy_paper` | `False` |
| `direct_alpha_or_portfolio_claim_available` | `False` |
| `review_artifact_available` | `True` |
| `component_ablation_available` | `True` |
| `raw_vs_debounced_trigger_tested` | `True` |
| `window_stability_tested` | `True` |
| `strict_00631l_debounce_passed` | `False` |
| `strict_00713_debounce_passed` | `False` |
| `domain_randomization_stress_completed` | `True` |
| `strict_domain_randomization_passed` | `False` |
| `pit_actor_input_separation_documented` | `True` |
| `no_latest_strategy_change_requested_by_gate` | `True` |
| `no_golden_change_requested_by_gate` | `True` |

## Evidence

- 00631L best candidate: `realized_var_20_top25_raw`
- 00631L pass fraction: `0.0`
- 00631L strict passed: `False`
- 00713 best variant: `raw_gate`
- 00713 average dFV: `-3747.4039138995577`
- 00713 strict passed: `False`
- Domain randomization best variant: `debounce_3of3`
- Domain randomization scenario count: `7`
- Domain randomization strict passed: `False`

## Governance Imports

| requirement | status | minimum |
|---|---|---|
| `component_ablation` | `implemented_as_readiness_requirement` | full/raw, no-trigger/debounced, and baseline/fixed variants must be reported. |
| `window_or_seed_stability` | `implemented_as_readiness_requirement` | A candidate must pass all required windows/folds before promotion review. |
| `domain_randomization_stress` | `added_as_future_required_blocker` | Cost, delay, slippage, stale data, missing feature, probability perturbation, and capital-size sweeps. |
| `pit_actor_privileged_critic_separation` | `implemented_as_documented_boundary` | Training diagnostics may use ex-post labels; live actor/signal inputs must remain point-in-time only. |

## Conclusion

CTBC 的可導入價值是治理檢查，不是交易訊號。此 gate 明確阻擋策略升級，只保留未來候選策略的驗證要求。
