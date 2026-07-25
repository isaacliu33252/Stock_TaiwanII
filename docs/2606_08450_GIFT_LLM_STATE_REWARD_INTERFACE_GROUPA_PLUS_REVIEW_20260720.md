# 2606.08450 GIFT LLM State-Reward Interface GroupA+ Review（2026-07-20）

## Source

- File: `C:\Users\isaac\Downloads\2606.08450.pdf`
- Title: `GIFT: LLM-Guided State-Reward Interface for Financial Reinforcement Learning`
- arXiv: `2606.08450v1`
- Date in PDF: `2026-06-07`

## Paper Summary

The paper proposes `GIFT`, an LLM-guided framework for financial RL interface
design.

The important distinction is that the LLM is not the trading agent. The paper
uses the LLM only to design the learning interface around a PPO portfolio
learner:

- `FSE`: Factor-guided State Enhancement. The LLM selects and composes bounded
  factor primitives such as momentum, volatility, downside risk, liquidity,
  mean reversion, and trend strength.
- `RRS`: Risk-rule-guided Reward Shaping. The LLM configures reward terms for
  concentration, diversification, turnover, drawdown, volatility, regime
  defense, and momentum alignment.
- `DGR`: Diagnostic-guided Refinement. PPO rollout diagnostics are fed back to
  revise candidate state/reward interfaces.

After offline refinement, the selected state-reward interface is frozen before
out-of-sample evaluation. The paper explicitly avoids LLM queries, prompt
updates, feedback writes, or interface changes at test time.

## Useful Ideas For GroupA+

There are useful governance ideas, but not a live strategy import.

Useful imports:

- keep LLM use constrained to feature/reward proposal, not trading action;
- require an allowlisted feature primitive library before any LLM-generated
  factor can enter research;
- map reward shaping only to existing risk objectives: drawdown, tail cost,
  turnover, market impact, concentration, cash defense, and LETF decay;
- require executable-code validation, finite values, bounded parameters, and
  human review for generated feature/reward logic;
- use diagnostic-guided refinement as research-only tuning evidence;
- freeze any selected interface before walk-forward / OOS evaluation;
- forbid test-time LLM updates.

These ideas fit the current GroupA+ research governance stack, especially:

- `rl_governance_readiness_review.json`;
- `market_impact_readiness_review.json`;
- `dynamic_cvar_tail_cost_readiness_review.json`;
- `synthetic_augmentation_validation_readiness_review.json`;
- `deployment_consistency_review.json`;
- `research_shadow_decision_snapshot.json`.

## Not Imported

Do not import:

- LLM as a direct trading agent;
- PPO as a live allocator;
- generated code without review;
- test-time LLM queries or prompt updates;
- automatic target-weight change;
- automatic rebalance;
- any direct `00631L` add rule;
- any direct `00632R` open rule.

Reasons:

- the paper is daily OHLCV rolling-window research, not Taiwan ETF broker-ready
  execution validation;
- it does not fully model liquidity, execution delay, market impact, taxes, or
  time-varying costs;
- current GroupA+ RL governance is blocked;
- current market-impact, synthetic validation, tail-cost, and deployment gates
  are not ready for live promotion;
- GroupA+ already has a live strategy and manual risk controls for 2026-07-20.

## Implemented GroupA+ Import

Implemented as a research-only readiness artifact:

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

Also integrated into:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Current readiness result:

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

Key blockers:

- `rl_governance_blocked`
- `rl_component_not_promotable_for_llm_interface`
- `market_impact_blocked`
- `market_impact_not_ready_for_reward_shaping`
- `synthetic_augmentation_validation_blocked`
- `synthetic_validation_not_ready_for_interface_search`
- `dynamic_cvar_tail_cost_blocked`
- `tail_cost_not_ready_for_reward_shaping`
- `deployment_not_broker_actionable`
- `research_shadow_snapshot_blocked`

## Research Catalog

The GIFT catalog is available for research review only:

- feature families: momentum, volatility, downside risk, liquidity, mean
  reversion, trend strength;
- reward terms: drawdown penalty, turnover penalty, concentration penalty,
  volatility scaling, cash defense bonus, LETF tail/decay cost;
- required checks: preserve raw market input, append features only, finite
  numeric values, bounded parameters, human review note, walk-forward plan, and
  frozen OOS interface;
- explicit rejects: LLM direct trade signal, LLM target-weight output, PPO live
  allocator, test-time prompt update, high-frequency dependency, unbounded
  reward term, synthetic alpha without validation, and market-impact-blind
  turnover reward.

Current catalog result:

- `status = research_catalog_available_live_blocked`
- `feature_family_count = 6`
- `reward_term_count = 6`
- `promote_to_live = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

## Proposal Validation

The proposal validator is implemented for research-only review:

- accepts proposals only if feature families, feature primitives, and reward
  terms are in the catalog allowlists;
- rejects proposals that output actions, target weights, test-time LLM queries,
  live generated-code execution, high-frequency dependencies, or live effects;
- keeps all accepted proposals offline-only.

Current validation result:

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

## Offline Smoke Review

The accepted proposal `gift_research_momentum_vol_drawdown_turnover_v1` was
checked with a minimal offline smoke test.

Scope:

- data source: `FinRL/data/stock_data.db`, table `ohlcv`, ticker `0050.TW`;
- fallback data source: `data/cache/0050_TW_2016-01-01_2026-05-05_1d.parquet.bak`;
- rows: `2560`;
- date range: `2016-01-04` to `2026-07-17`;
- features: `relative_momentum`, `realized_volatility`;
- reward proxies: `drawdown_penalty`, `turnover_penalty`, bounded
  `reward_proxy`;
- no model training;
- no PPO training;
- no action output;
- no target-weight output.

Current smoke result:

- `status = available_for_manual_offline_review`
- `blocking_reasons = []`
- `relative_momentum` finite ratio: `0.9921875`
- `realized_volatility` finite ratio: `0.9921875`
- reward proxy bounded range: `[-0.25, 0.0]`
- `warning_reasons = []`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

## Multi-Ticker Coverage Smoke

The same feature/reward smoke was extended to the current ETF universe using
DuckDB `ohlcv`.

Tickers:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `0056.TW`
- `00713.TW`
- `00878.TW`
- `00679B.TWO`
- `00751B.TWO`

Current multi-ticker result:

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
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Ticker data ranges:

- `0050.TW`: `2016-01-04` to `2026-07-17`, rows `2560`
- `00631L.TW`: `2016-01-04` to `2026-07-17`, rows `2564`
- `00632R.TW`: `2016-01-04` to `2026-07-17`, rows `2564`
- `0056.TW`: `2020-01-02` to `2026-07-17`, rows `1587`
- `00713.TW`: `2020-01-02` to `2026-07-17`, rows `1587`
- `00878.TW`: `2020-07-10` to `2026-07-17`, rows `1464`
- `00679B.TWO`: `2017-01-11` to `2026-07-17`, rows `2309`
- `00751B.TWO`: `2020-01-02` to `2026-07-17`, rows `1587`

## Feature Stability Review

The multi-ticker feature/reward proxies were checked for cross-ETF stability.

Current feature-stability result:

- `status = available_for_manual_offline_review`
- `ticker_count = 8`
- `available_ticker_count = 8`
- `missing_tickers = []`
- `blocking_reasons = []`
- `tickers_with_stability_warnings = [0050.TW]`
- warning: `0050.TW:latest_zscore_extreme:drawdown_penalty:3.1250`
- warning: `0050.TW:latest_zscore_extreme:reward_proxy:-3.1250`
- warning: `00631L.TW:high_positive_benchmark_correlation`
- `00631L.TW` return correlation to `0050.TW`: `0.9641117355384909`
- `00631L.TW` return beta to `0050.TW`: `1.8549426919994487`
- `00632R.TW` return correlation to `0050.TW`: `-0.06175848479875322`
- `00632R.TW` return beta to `0050.TW`: `-0.5751915925033152`
- max absolute return correlation across pairs: `0.9641117355384909`
- max absolute relative-momentum correlation across pairs: `0.973872116171167`
- max absolute realized-volatility correlation across pairs: `0.9717136226136651`
- max absolute reward-proxy correlation across pairs: `0.8883253236285474`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Interpretation:

- `00631L.TW` behaves like amplified `0050.TW` exposure, not diversification.
- `00632R.TW` does not show stable high negative correlation to `0050.TW` in
  this full daily sample, so it cannot be auto-opened as a hedge from this
  review.
- The `0050.TW` latest drawdown/reward z-score warning is manual-review
  evidence only; it is not a rebalance or sell signal.

## Windowed Stability / Stress Review

The core `0050.TW`, `00631L.TW`, and `00632R.TW` relationships were checked
with rolling 63 / 126 / 252 trading-day windows and stress windows.

Current windowed result:

- `status = available_for_manual_offline_review`
- `ticker_count = 3`
- `available_ticker_count = 3`
- `missing_tickers = []`
- `blocking_reasons = []`
- recent `0050.TW` drawdown extreme z-score days: `1`
- recent `0050.TW` reward-proxy extreme z-score days: `1`
- `model_training_allowed = false`
- `ppo_training_allowed = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Latest rolling relationships as of `2026-07-17`:

- `00631L.TW` 63d correlation / beta to `0050.TW`:
  `0.9804545943921081` / `1.9004889933924094`
- `00631L.TW` 126d correlation / beta to `0050.TW`:
  `0.9710141700279369` / `1.9374371393631045`
- `00631L.TW` 252d correlation / beta to `0050.TW`:
  `0.9709061213727571` / `1.9068014182501556`
- `00632R.TW` 63d correlation / beta to `0050.TW`:
  `-0.9779370370774443` / `-0.9951325582163222`
- `00632R.TW` 126d correlation / beta to `0050.TW`:
  `-0.9785023640596672` / `-1.0141874201460217`
- `00632R.TW` 252d correlation / beta to `0050.TW`:
  `-0.975772171326609` / `-0.9832319101817458`

Stress-window findings:

- `2018` trade-war correction:
  - `00631L.TW` correlation / beta: `0.9691216405312906` /
    `1.9246892104645954`
  - `00632R.TW` correlation / beta: `-0.9581997284313736` /
    `-0.9307819247740824`
- `2020` COVID crash:
  - `00631L.TW` correlation / beta: `0.9729101860724241` /
    `1.9951972028222642`
  - `00632R.TW` correlation / beta: `-0.969374791130877` /
    `-1.0059258889687406`
- `2022` rate-hike stress:
  - `00631L.TW` correlation / beta: `0.9618460847853261` /
    `1.8214492694677702`
  - `00632R.TW` correlation / beta: `-0.9584372527444128` /
    `-0.8961098200544976`
- `2026` recent:
  - `00631L.TW` correlation / beta: `0.985022304645767` /
    `1.967670773865783`
  - `00632R.TW` correlation / beta: `-0.9803311350577403` /
    `-1.0230849199964227`

Interpretation:

- `00631L.TW` is consistently amplified `0050.TW` exposure across rolling and
  stress windows, so adding it would increase equity beta.
- `00632R.TW` is hedge-like in recent rolling windows and several stress
  windows, but the review is still research-only and cannot authorize an
  automatic hedge open.
- The recent `0050.TW` z-score warning appeared for `1` day, so it should be
  monitored manually rather than treated as a rebalance instruction.

## Manual Hedge Eligibility Checklist

The windowed `00632R.TW` hedge-like evidence was converted into a manual hedge
eligibility checklist. The checklist separates evidence from permission.

Current manual hedge eligibility result:

- `status = blocked`
- `hedge_evidence_available = true`
- `manual_hedge_discussion_allowed = false`
- `failed_manual_gate_count = 6`
- latest `00632R.TW` rolling correlations to `0050.TW`:
  - 63d: `-0.9779370370774443`
  - 126d: `-0.9785023640596672`
  - 252d: `-0.975772171326609`
- latest `00632R.TW` rolling betas to `0050.TW`:
  - 63d: `-0.9951325582163222`
  - 126d: `-1.0141874201460217`
  - 252d: `-0.9832319101817458`
- recent stress relationship:
  - correlation: `-0.9803311350577403`
  - beta: `-1.0230849199964227`
  - relationship: `high_negative_benchmark_correlation`

Blocking reasons:

- `00632r_tail_tracking_error_gate_failed`
- `effective_fee_proxy_not_validated`
- `live_hedge_policy_not_validated`
- `letf_readiness_blocks_00632r_open`
- `market_impact_blocks_trade_or_weight_change`
- `research_shadow_blocks_00632r_open`

Decision:

- `manual_hedge_discussion_blocked = true`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Interpretation:

- `00632R.TW` has hedge-like evidence, but evidence is not authorization.
- Tail tracking error, effective-fee validation, live hedge policy, market
  impact, and research-shadow gates still block even manual hedge eligibility.
- No target weight, rebalance, or hedge order should be produced from this
  research chain.

## 00632R Tail Tracking-Error Gate Review

The failed `00632r_30d_p05_tracking_error_floor` gate was reviewed separately.

Current tail-gate result:

- `status = blocked`
- full-sample 30d tracking-error p05: `-0.04194782042073657`
- full-sample auto-trade floor: `-0.03`
- full-sample tail gate passed: `false`
- recent-60 30d tracking-error p05: `-0.010876108225421257`
- manual recent p05 floor: `-0.02`
- latest 30d tracking error: `0.0081190680562589`
- manual recent tail gate passed: `true`
- `gate_split_recommended = true`

Blocking reasons:

- `full_sample_00632r_tail_tracking_error_gate_failed`
- `manual_hedge_eligibility_still_blocked`
- `letf_readiness_still_blocks_00632r_open`

Interpretation:

- The original full-sample p05 gate should remain a conservative blocker for
  automatic 00632R trading.
- Recent tail behavior is better than the full-sample auto gate, so it is
  reasonable to split the check into an auto-trade blocker and a manual
  monitoring tier.
- This split does not unlock manual hedge discussion because other gates remain
  blocked.

## 00632R Effective-Fee Proxy Validation

The effective-drag / effective-fee proxy was independently recomputed from
daily OHLCV and compared against realized tracking error.

Current validation result:

- `status = blocked`
- `proxy_validated_for_manual_review = false`
- failed horizons: `20:tail_overlap`, `30:tail_overlap`
- correlation threshold: `0.95`
- sign-agreement threshold: `0.85`
- tail-overlap threshold: `0.80`

Validation metrics:

- 5d tracking-vs-drag correlation / sign agreement / tail overlap:
  `0.99987025107381` / `0.9595448798988622` / `0.8625`
- 10d tracking-vs-drag correlation / sign agreement / tail overlap:
  `0.9998335441804744` / `0.9302473050095117` /
  `0.8354430379746836`
- 20d tracking-vs-drag correlation / sign agreement / tail overlap:
  `0.999800905765244` / `0.9010848755583918` /
  `0.759493670886076`
- 30d tracking-vs-drag correlation / sign agreement / tail overlap:
  `0.999782278198798` / `0.8946692357096981` /
  `0.717948717948718`

Interpretation:

- Effective drag is highly correlated with realized tracking error.
- It does not reliably capture the left-tail overlap at 20d and 30d horizons.
- Therefore `effective_fee_proxy_not_validated` remains a valid blocker for
  hedge eligibility.

## Live Hedge Policy Review

The live hedge policy boundary was defined explicitly.

Current policy result:

- `status = blocked`
- `policy_defined = true`
- `policy_validated_for_manual_discussion = false`
- `live_hedge_policy_validated = false`
- `manual_hedge_discussion_allowed = false`
- `allow_00632r_open = false`

Policy hard prohibitions:

- no LLM-generated order;
- no PPO / RL allocator order;
- no script-generated target weight;
- no auto rebalance;
- no market order instruction;
- no position open without manual broker action.

Blocking reasons:

- `manual_hedge_eligibility_blocks_discussion`
- `effective_fee_proxy_not_validated_for_manual_review`
- `live_hedge_policy_not_validated_for_live_action`

Interpretation:

- The policy ambiguity is reduced: even if future evidence improves, this chain
  cannot create an automatic 00632R order.
- Because current manual hedge eligibility and effective-fee proxy validation
  still fail, the live hedge policy remains unvalidated for action.

## Latest Strategy Impact

No live GroupA+ strategy change.

For 2026-07-20:

- keep `a2118_a2111_ncf_late_bull_deleverage`;
- keep `Golden1_0531` unchanged;
- do not auto-rebalance;
- do not add `00631L`;
- do not open `00632R`;
- no PPO allocator;
- no LLM trading policy.

## Conclusion

`2606.08450` has importable value for GroupA+ only at the research governance
layer. The best import is a constrained feature/reward proposal framework with
strict validation and frozen OOS evaluation. It can improve future research
discipline, but it does not justify any live allocation, rebalance, leverage
increase, or inverse ETF hedge today.
