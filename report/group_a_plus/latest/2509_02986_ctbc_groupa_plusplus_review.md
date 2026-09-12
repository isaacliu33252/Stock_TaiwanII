# 2509.02986 CTBC GroupA++ Review

- Policy: `research_only_no_weight_change`
- Decision: `research_only_no_weight_change`
- Promotion allowed now: `False`
- Latest strategy weight change allowed: `False`
- Golden1 unchanged: `True`
- Golden2 unchanged: `True`

## Paper Identity

- Title: CTBC: Contact-Triggered Blind Climbing for Wheeled Bipedal Robots with Instruction Learning and Reinforcement Learning
- Domain: `robotics_control_reinforcement_learning`
- Path: `/mnt/c/Users/isaac/Downloads/2509.02986.pdf`

## Current Context

- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- NCF00631L panel: `results/ncf_00631l_panel_latest_20260716.csv`
- NCF00713 path: `results/ncf_00713_latest_20260909.json`

## Implemented Shadow

- CTBC debounce shadow: `report/group_a_plus/latest/2509_02986_ctbc_debounce_shadow.json`
- Debounce decision: `do_not_promote_keep_shadow`
- Debounce best candidate: `realized_var_20_top25_raw`
- Debounce strict passed: `False`
- 00713 debounce shadow: `report/group_a_plus/latest/2509_02986_ctbc_00713_debounce_shadow.json`
- 00713 debounce decision: `do_not_promote_keep_shadow`
- 00713 debounce best variant: `raw_gate`
- 00713 debounce strict passed: `False`
- 00713 domain randomization: `report/group_a_plus/latest/2509_02986_ctbc_00713_domain_randomization.json`
- 00713 domain randomization decision: `robustness_test_complete_do_not_promote`
- 00713 domain randomization strict passed: `False`
- Promotion readiness gate: `report/group_a_plus/latest/2509_02986_ctbc_promotion_readiness_gate.json`
- Promotion readiness decision: `do_not_promote_import_governance_requirements_only`
- Promotion readiness allowed: `False`

## Transfer Candidates

| idea | status | latest strategy change | use |
|---|---|---:|---|
| `contact_triggered_event_controller` | `candidate_shadow` | `False` | Use event-triggered shadow controllers for actual market contact events such as realized drawdown, gap-down, liquidity stress, stale-data contact, or broker-fill friction. Do not let the controller fire from a pure forecast without an observed contact condition. |
| `sliding_window_trigger_debounce` | `tested_do_not_promote` | `False` | Test 2-of-3 or 3-of-3 confirmation for slow actions such as no-add, re-entry, and 00713 sleeve disablement. Do not apply it blindly to emergency de-risking because confirmation can delay protection. |
| `feedforward_instruction_warm_start` | `training_governance_candidate` | `False` | For future RL or learned micro-tilt agents, initialize behavior near the current latest strategy or Golden1 policy and anneal the imitation weight during shadow training. |
| `asymmetric_actor_critic_privileged_training` | `research_only_design_pattern` | `False` | Allow shadow critics to use ex-post labels, realized future drawdown diagnostics, and full-cost attribution for training diagnostics, while live actors/signals remain limited to point-in-time features. |
| `domain_randomization_for_strategy_robustness` | `can_import_as_validation_requirement` | `False` | Add robustness sweeps for transaction costs, execution delay, price slippage, missing chip/news data, stale TDCC rows, NCF probability perturbation, and capital-size scaling before any new overlay is promoted. |
| `component_ablation_and_seed_stability` | `can_import_as_research_checklist` | `False` | Any paper-inspired GroupA++ candidate should report full, no-trigger, no-guidance, and baseline variants with at least three seed or window slices before promotion review. |

## Blocked Or Deferred

| idea | reason |
|---|---|
| `direct_rl_policy_import` | The paper controls robot joints in a physics simulator; it does not model market returns, ETF flows, portfolio PnL, or transaction costs. |
| `contact_force_threshold_as_market_signal` | Robot contact force has no direct market analogue. Trading triggers must be rebuilt from observed market/account states. |
| `blind_policy_as_no_news_rule` | Blind locomotion means no vision sensor; it does not imply financial news/chip/external features should be removed. |
| `zero_shot_transfer_to_live_strategy` | The paper validates sim-to-real hardware transfer; groupA++ requires purged walk-forward, cost, capital, and multi-window portfolio validation. |

## Checks

| check | pass |
|---|---:|
| `paper_is_finance_or_trading` | `False` |
| `direct_alpha_claim_available` | `False` |
| `portfolio_pnl_evidence_available` | `False` |
| `transferable_control_patterns_available` | `True` |
| `latest_strategy_change_allowed` | `False` |
| `golden_change_allowed` | `False` |
| `shadow_only_review_complete` | `True` |

## Final Decision

- Recommended import now: `domain_randomization_for_strategy_robustness_as_validation_requirement, component_ablation_and_seed_stability_as_research_checklist`
- Recommended shadow experiments: `feedforward_warm_start_for_future_rl_micro_tilt_shadow`
- Reason: The paper is useful as a control/governance analogy, but it provides no direct financial alpha, no ETF allocation result, and no evidence that live groupA++ weights should change.

This report is research-only. It does not emit trades, target weights, NCF gates, or order-generation changes.
