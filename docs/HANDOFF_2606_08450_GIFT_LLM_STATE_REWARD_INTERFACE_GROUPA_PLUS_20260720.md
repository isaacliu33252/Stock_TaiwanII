# Handoff: 2606.08450 GIFT LLM State-Reward Interface for GroupA+（2026-07-20）

## Bottom Line

`C:\Users\isaac\Downloads\2606.08450.pdf` is useful, but only as research
governance.

Do not import a live LLM trading agent or PPO allocator.

Keep current GroupA+ latest strategy unchanged:

- `a2118_a2111_ncf_late_bull_deleverage`
- `Golden1_0531`
- no auto rebalance
- no `00631L` add
- no `00632R` open

## What Was Imported

Imported from GIFT:

- constrained LLM feature proposal from approved financial primitives;
- risk-rule-guided reward shaping as an audit framework;
- diagnostic-guided refinement using PPO/rollout style metrics;
- frozen interface before OOS evaluation;
- no test-time LLM query or update.

Not imported:

- LLM trading actions;
- PPO live allocation;
- generated code without human review;
- test-time LLM interface updates;
- automatic target-weight changes;
- automatic rebalance.

## Files Created Or Updated

Created:

- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_readiness_review.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_catalog.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py`
- `scripts/evaluate/validate_group_a_plus_llm_state_reward_interface_proposals.py`
- `tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py`
- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py`
- `scripts/evaluate/build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `scripts/evaluate/build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `tests/test_build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `scripts/evaluate/build_group_a_plus_live_hedge_policy_review.py`
- `tests/test_build_group_a_plus_live_hedge_policy_review.py`
- `docs/2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_REVIEW_20260720.md`
- `docs/HANDOFF_2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_20260720.md`

Updated:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

Generated:

- `report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json`
- `report/group_a_plus/llm_state_reward_interface/history/llm_state_reward_interface_readiness_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_catalog.json`
- `report/group_a_plus/llm_state_reward_interface_catalog/history/llm_state_reward_interface_catalog_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_sample_proposals.json`
- `report/group_a_plus/latest/llm_state_reward_interface_proposal_validation_review.json`
- `report/group_a_plus/llm_state_reward_interface_proposal_validation/history/llm_state_reward_interface_proposal_validation_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_offline_smoke_review.json`
- `report/group_a_plus/llm_state_reward_interface_offline_smoke/history/llm_state_reward_interface_offline_smoke_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_multi_ticker_smoke_review.json`
- `report/group_a_plus/llm_state_reward_interface_multi_ticker_smoke/history/llm_state_reward_interface_multi_ticker_smoke_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_feature_stability_review.json`
- `report/group_a_plus/llm_state_reward_interface_feature_stability/history/llm_state_reward_interface_feature_stability_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_windowed_stability_review.json`
- `report/group_a_plus/llm_state_reward_interface_windowed_stability/history/llm_state_reward_interface_windowed_stability_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json`
- `report/group_a_plus/llm_state_reward_interface_manual_hedge_eligibility/history/llm_state_reward_interface_manual_hedge_eligibility_20260720.json`
- `report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json`
- `report/group_a_plus/00632r_tail_tracking_error_gate/history/00632r_tail_tracking_error_gate_20260720.json`
- `report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json`
- `report/group_a_plus/00632r_effective_fee_proxy_validation/history/00632r_effective_fee_proxy_validation_20260720.json`
- `report/group_a_plus/latest/live_hedge_policy_review.json`
- `report/group_a_plus/live_hedge_policy/history/live_hedge_policy_20260720.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

## Current JSON Results

`llm_state_reward_interface_readiness_review.json`:

- `status = blocked`
- `llm_state_reward_interface_ready = false`
- `feature_proposal_governance_imported = true`
- `reward_shaping_governance_imported = true`
- `diagnostic_refinement_governance_imported = true`
- `live_llm_trading_allowed = false`
- `live_ppo_allocator_allowed = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

`llm_state_reward_interface_multi_ticker_smoke_review.json`:

- `status = available_for_manual_offline_review`
- `ticker_count = 8`
- `available_for_manual_offline_review_count = 8`
- `blocked_tickers = []`
- `earliest_end = 2026-07-17`
- `latest_end = 2026-07-17`
- `blocking_reasons = []`
- `warning_reasons = []`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `outputs_actions = false`
- `outputs_target_weights = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Ticker coverage:

- `0050.TW`: `2016-01-04` to `2026-07-17`, rows `2560`
- `00631L.TW`: `2016-01-04` to `2026-07-17`, rows `2564`
- `00632R.TW`: `2016-01-04` to `2026-07-17`, rows `2564`
- `0056.TW`: `2020-01-02` to `2026-07-17`, rows `1587`
- `00713.TW`: `2020-01-02` to `2026-07-17`, rows `1587`
- `00878.TW`: `2020-07-10` to `2026-07-17`, rows `1464`
- `00679B.TWO`: `2017-01-11` to `2026-07-17`, rows `2309`
- `00751B.TWO`: `2020-01-02` to `2026-07-17`, rows `1587`

`research_shadow_decision_snapshot.json` now includes:

- `llm_state_reward_interface_status = blocked`
- `llm_state_reward_interface_ready = false`
- `feature_proposal_governance_imported = true`
- `reward_shaping_governance_imported = true`
- `live_llm_trading_allowed = false`
- `live_ppo_allocator_allowed = false`
- `llm_state_reward_interface_allow_00631l_add = false`

`llm_state_reward_interface_catalog.json`:

- `status = research_catalog_available_live_blocked`
- `feature_family_count = 6`
- `reward_term_count = 6`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Allowed feature families:

- momentum;
- volatility;
- downside risk;
- liquidity;
- mean reversion;
- trend strength.

Allowed reward terms:

- drawdown penalty;
- turnover penalty;
- concentration penalty;
- volatility scaling;
- cash defense bonus;
- LETF tail/decay cost.

`llm_state_reward_interface_proposal_validation_review.json`:

- `status = available_for_manual_offline_review`
- `proposal_count = 2`
- `accepted_for_offline_review_count = 1`
- `rejected_count = 1`
- accepted: `gift_research_momentum_vol_drawdown_turnover_v1`
- rejected: `gift_reject_live_00631l_target_weight_v1`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

The rejected proposal was blocked because it attempted action / target-weight
output, test-time LLM use, live generated-code execution, auto rebalance, and
`00631L` live add permission.

`llm_state_reward_interface_offline_smoke_review.json`:

- accepted proposal: `gift_research_momentum_vol_drawdown_turnover_v1`
- `status = available_for_manual_offline_review`
- data: `FinRL/data/stock_data.db`, table `ohlcv`, ticker `0050.TW`
- range: `2016-01-04` to `2026-07-17`
- rows: `2560`
- feature checks: `relative_momentum`, `realized_volatility`
- reward proxy checks: `drawdown_penalty`, `turnover_penalty`, bounded
  `reward_proxy`
- `blocking_reasons = []`
- `warning_reasons = []`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `outputs_actions = false`
- `outputs_target_weights = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

`llm_state_reward_interface_feature_stability_review.json`:

- `status = available_for_manual_offline_review`
- `ticker_count = 8`
- `available_ticker_count = 8`
- `missing_tickers = []`
- `blocking_reasons = []`
- `tickers_with_stability_warnings = [0050.TW]`
- warnings:
  - `0050.TW:latest_zscore_extreme:drawdown_penalty:3.1250`
  - `0050.TW:latest_zscore_extreme:reward_proxy:-3.1250`
  - `00631L.TW:high_positive_benchmark_correlation`
- `00631L.TW` return correlation to `0050.TW`: `0.9641117355384909`
- `00631L.TW` return beta to `0050.TW`: `1.8549426919994487`
- `00632R.TW` return correlation to `0050.TW`: `-0.06175848479875322`
- `00632R.TW` return beta to `0050.TW`: `-0.5751915925033152`
- cross-pair max absolute correlations:
  - return: `0.9641117355384909`
  - relative momentum: `0.973872116171167`
  - realized volatility: `0.9717136226136651`
  - reward proxy: `0.8883253236285474`
- `feature_stability_ready_for_research_review = true`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `outputs_actions = false`
- `outputs_target_weights = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Interpretation:

- `00631L.TW` is amplified `0050.TW` exposure, not diversification.
- `00632R.TW` is not a stable high-negative-correlation hedge in this full
  daily sample.
- The `0050.TW` drawdown/reward z-score warning is a manual-review flag only,
  not a sell or rebalance trigger.

`llm_state_reward_interface_windowed_stability_review.json`:

- `status = available_for_manual_offline_review`
- `ticker_count = 3`
- `available_ticker_count = 3`
- `missing_tickers = []`
- `blocking_reasons = []`
- recent `0050.TW` drawdown extreme z-score days: `1`
- recent `0050.TW` reward-proxy extreme z-score days: `1`
- latest rolling `00631L.TW` correlation / beta to `0050.TW`:
  - 63d: `0.9804545943921081` / `1.9004889933924094`
  - 126d: `0.9710141700279369` / `1.9374371393631045`
  - 252d: `0.9709061213727571` / `1.9068014182501556`
- latest rolling `00632R.TW` correlation / beta to `0050.TW`:
  - 63d: `-0.9779370370774443` / `-0.9951325582163222`
  - 126d: `-0.9785023640596672` / `-1.0141874201460217`
  - 252d: `-0.975772171326609` / `-0.9832319101817458`
- stress-window findings:
  - 2018 trade-war correction:
    - `00631L.TW`: `0.9691216405312906` / `1.9246892104645954`
    - `00632R.TW`: `-0.9581997284313736` / `-0.9307819247740824`
  - 2020 COVID crash:
    - `00631L.TW`: `0.9729101860724241` / `1.9951972028222642`
    - `00632R.TW`: `-0.969374791130877` / `-1.0059258889687406`
  - 2022 rate-hike stress:
    - `00631L.TW`: `0.9618460847853261` / `1.8214492694677702`
    - `00632R.TW`: `-0.9584372527444128` / `-0.8961098200544976`
  - 2026 recent:
    - `00631L.TW`: `0.985022304645767` / `1.967670773865783`
    - `00632R.TW`: `-0.9803311350577403` / `-1.0230849199964227`
- `windowed_stability_ready_for_research_review = true`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `outputs_actions = false`
- `outputs_target_weights = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Interpretation:

- `00631L.TW` is consistently amplified `0050.TW` exposure in rolling and
  stress windows.
- `00632R.TW` is hedge-like in recent rolling windows and several stress
  windows, but this is not live authorization.
- The recent `0050.TW` drawdown/reward z-score warning appeared for `1` day and
  remains manual-review evidence only.

`llm_state_reward_interface_manual_hedge_eligibility_review.json`:

- `status = blocked`
- `hedge_evidence_available = true`
- `manual_hedge_discussion_allowed = false`
- `failed_manual_gate_count = 6`
- latest rolling `00632R.TW` correlations to `0050.TW`:
  - 63d: `-0.9779370370774443`
  - 126d: `-0.9785023640596672`
  - 252d: `-0.975772171326609`
- latest rolling `00632R.TW` betas to `0050.TW`:
  - 63d: `-0.9951325582163222`
  - 126d: `-1.0141874201460217`
  - 252d: `-0.9832319101817458`
- recent stress relationship:
  - correlation: `-0.9803311350577403`
  - beta: `-1.0230849199964227`
  - relationship: `high_negative_benchmark_correlation`
- blocking reasons:
  - `00632r_tail_tracking_error_gate_failed`
  - `effective_fee_proxy_not_validated`
  - `live_hedge_policy_not_validated`
  - `letf_readiness_blocks_00632r_open`
  - `market_impact_blocks_trade_or_weight_change`
  - `research_shadow_blocks_00632r_open`
- `manual_hedge_discussion_blocked = true`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `outputs_actions = false`
- `outputs_target_weights = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Interpretation:

- `00632R.TW` hedge-like evidence exists, but evidence is not authorization.
- Manual hedge discussion is still blocked by tail tracking error,
  effective-fee validation, live hedge policy, market impact, and research
  shadow gates.
- This chain must not produce a hedge order, target weight, or rebalance.

`00632r_tail_tracking_error_gate_review.json`:

- `status = blocked`
- full-sample 30d tracking-error p05: `-0.04194782042073657`
- full-sample auto-trade floor: `-0.03`
- full-sample tail gate passed: `false`
- recent-60 30d tracking-error p05: `-0.010876108225421257`
- manual recent p05 floor: `-0.02`
- latest 30d tracking error: `0.0081190680562589`
- manual recent tail gate passed: `true`
- gate split recommended: `true`
- blocking reasons:
  - `full_sample_00632r_tail_tracking_error_gate_failed`
  - `manual_hedge_eligibility_still_blocked`
  - `letf_readiness_still_blocks_00632r_open`
- `manual_hedge_discussion_allowed = false`
- `allow_00632r_open = false`

Interpretation:

- Keep the full-sample p05 gate as an automatic-trading blocker.
- Add a separate recent-tail monitoring tier for manual-review evidence.
- The split does not unlock manual hedge discussion or live action.

`00632r_effective_fee_proxy_validation_review.json`:

- `status = blocked`
- proxy validated for manual review: `false`
- failed horizons: `20:tail_overlap`, `30:tail_overlap`
- thresholds:
  - correlation floor: `0.95`
  - sign agreement floor: `0.85`
  - tail overlap floor: `0.80`
- 5d validation:
  - tracking-vs-drag correlation: `0.99987025107381`
  - sign agreement: `0.9595448798988622`
  - tail overlap: `0.8625`
- 10d validation:
  - tracking-vs-drag correlation: `0.9998335441804744`
  - sign agreement: `0.9302473050095117`
  - tail overlap: `0.8354430379746836`
- 20d validation:
  - tracking-vs-drag correlation: `0.999800905765244`
  - sign agreement: `0.9010848755583918`
  - tail overlap: `0.759493670886076`
- 30d validation:
  - tracking-vs-drag correlation: `0.999782278198798`
  - sign agreement: `0.8946692357096981`
  - tail overlap: `0.717948717948718`
- `manual_hedge_discussion_allowed = false`
- `allow_00632r_open = false`

Interpretation:

- Effective drag tracks broad tracking-error movement very closely.
- It fails the 20d and 30d tail-overlap requirement, so it is not reliable
  enough to remove the effective-fee blocker.
- This keeps `effective_fee_proxy_not_validated` active.

`live_hedge_policy_review.json`:

- `status = blocked`
- `policy_defined = true`
- `policy_validated_for_manual_discussion = false`
- `live_hedge_policy_validated = false`
- `manual_hedge_discussion_allowed = false`
- `allow_00632r_open = false`
- blocking reasons:
  - `manual_hedge_eligibility_blocks_discussion`
  - `effective_fee_proxy_not_validated_for_manual_review`
  - `live_hedge_policy_not_validated_for_live_action`
- hard prohibitions:
  - no LLM-generated order
  - no PPO / RL allocator order
  - no script-generated target weight
  - no auto rebalance
  - no market order instruction
  - no position open without manual broker action

Interpretation:

- The policy boundary is explicit and forbids automatic hedge actions.
- The live hedge policy remains unvalidated for action because evidence gates
  are still blocked.

## Blocking Reasons

The GIFT import is blocked from live promotion because:

- RL governance is blocked;
- RL component is not promotable;
- market-impact readiness is blocked;
- reward shaping cannot be promoted without market-impact readiness;
- synthetic validation is blocked;
- tail-cost readiness is blocked;
- deployment is not broker-actionable;
- research shadow snapshot is blocked.

## Tests Run

Command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py
```

Result:

- `4 passed`

Additional command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `8 passed`

Proposal validation command:

```bash
.venv/bin/python -m pytest tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `12 passed`

Offline smoke command:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `15 passed`

Multi-ticker smoke command:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `19 passed`

Feature-stability command:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `22 passed`

Windowed-stability command:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `25 passed`

Manual hedge eligibility command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py
```

Result:

- `28 passed`

00632R tail tracking-error gate command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py
```

Result:

- `33 passed`

00632R effective-fee proxy validation command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_00632r_effective_fee_proxy_validation_review.py tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py
```

Result:

- `36 passed`

Live hedge policy command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_live_hedge_policy_review.py tests/test_build_group_a_plus_00632r_effective_fee_proxy_validation_review.py tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_build_group_a_plus_rl_governance_readiness_review.py tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py
```

Result:

- `39 passed`

Live hedge policy generation command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_live_hedge_policy_review.py --as-of 2026-07-20
```

Result:

- status: `blocked`;
- policy defined: `true`;
- live hedge policy validated: `false`;
- manual hedge discussion allowed: `false`;
- live locks remain false.

00632R effective-fee proxy validation generation command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_00632r_effective_fee_proxy_validation_review.py --as-of 2026-07-20
```

Result:

- status: `blocked`;
- proxy validated for manual review: `false`;
- failed horizons: `20:tail_overlap`, `30:tail_overlap`;
- live locks remain false.

00632R tail tracking-error gate generation command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_00632r_tail_tracking_error_gate_review.py --as-of 2026-07-20
```

Result:

- status: `blocked`;
- gate split recommended: `true`;
- full-sample auto gate passed: `false`;
- recent manual tail gate passed: `true`;
- live locks remain false.

Manual hedge eligibility generation command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py --as-of 2026-07-20
```

Result:

- status: `blocked`;
- hedge evidence: `true`;
- manual hedge discussion allowed: `false`;
- failed manual gates: `6`;
- live locks remain false.

Windowed-stability generation command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py --as-of 2026-07-20
```

Result:

- status: `available_for_manual_offline_review`;
- ticker coverage: `3/3`;
- recent `0050.TW` extreme z-score days: `1`;
- live locks remain false.

Feature-stability generation command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py --as-of 2026-07-20
```

Result:

- status: `available_for_manual_offline_review`;
- ticker coverage: `8/8`;
- blockers: none;
- live locks remain false.

Data backfill / DB-first command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py --as-of 2026-07-20
```

Result:

- data source changed from old parquet fallback to DuckDB `ohlcv`;
- date range expanded from `2026-05-04` to `2026-07-17`;
- rows increased from `2507` to `2560`;
- `16 passed` after DB-first test update.

## Next Step

The allowlisted feature/reward proposal catalog, validator, DB-first data
backfill, single-ticker smoke, multi-ticker coverage smoke, feature stability
review, windowed / stress-window stability review, and manual hedge eligibility
checklist are complete for the current research-only scope. The 00632R tail
tracking-error gate review and effective-fee proxy validation are also complete.
The live hedge policy boundary is defined but remains unvalidated for action.

If continuing this line of work, the next useful step is not more model work.
It is to decide whether to improve the blockers that prevented manual hedge
eligibility:

- validate the effective-fee proxy independently;
- keep `effective_fee_proxy_not_validated` active unless a better tail proxy
  improves 20d/30d tail overlap;
- define a live hedge policy that still forbids automatic orders;
- do not treat the policy definition as validation; it only documents the
  boundary;
- keep the full-sample `00632R.TW` 30d p05 tail gate as an auto-trading blocker
  and track the recent-tail manual tier separately;
- resolve market-impact and research-shadow blockers before any manual hedge
  discussion;
- keep accepted proposal as manual-review evidence only;
- do not train or deploy a live PPO allocator;
- keep `00631L` add and `00632R` open blocked unless existing live gates change.
