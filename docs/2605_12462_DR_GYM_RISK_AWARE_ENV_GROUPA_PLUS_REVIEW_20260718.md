# 2605.12462 DR-Gym Risk-Aware Environment GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\2605.12462.pdf`
- Title: `Towards Affordable Energy: A Gymnasium Environment for Electric Utility Demand-Response Programs`
- Authors: Jose E. Aguilar Escamilla, Lingdong Zhou, Xiangqi Zhu, Huazheng Wang
- Date: May 13, 2026
- arXiv: `2605.12462v1`

## Paper Summary

The paper introduces `DR-Gym`, a Gymnasium-compatible reinforcement-learning
environment for electric utility demand-response programs. The agent chooses
hourly bill credits to reduce demand during high-price periods while balancing
utility revenue, consumer cost, grid stress, and optional tail-risk penalties.

The environment combines:

- modular simulator components that can be swapped independently;
- Markov regime-switching price spikes calibrated to extreme events;
- physics-based building demand profiles;
- heterogeneous customer response archetypes;
- fatigue after repeated interventions;
- budget roll-over and budget exhaustion effects;
- configurable multi-objective reward;
- optional CVaR penalty on running consumer bills.

The experiments show PPO can outperform rule-based baselines in this simulator,
including lower CVaR of consumer bills. The authors do not claim state-of-the-art
trading or forecasting performance; the contribution is mainly a realistic,
risk-aware, interactive RL testbed.

## GroupA+ Relevance

This is not a financial trading paper, and the electricity-market simulator
should not be imported directly into GroupA+.

The useful ideas are governance patterns:

- treat strategy changes as interventions that can have fatigue and pacing costs;
- separate policy environment, agent, reward, simulator, and stress calculator;
- include explicit risk-budget state in observations;
- evaluate policies against simple baselines, not only against raw returns;
- use CVaR as a first-class penalty in sequential decisions;
- model clustered spike/stress episodes with regime switching;
- penalize repeated actions that consume future flexibility.

These map naturally to GroupA+ because the current strategy already has several
research-only gates:

- `trigate_vol_memory_shadow`
- `systemic_bubble_time_at_risk_review`
- `hmm_wj_synthetic_scenario_readiness_review`
- `dynamic_cvar_tail_cost_readiness_review`
- `synthetic_augmentation_validation_readiness_review`
- `research_shadow_decision_snapshot`

## Potential Import

Import as research-only governance:

1. Intervention fatigue / cooldown guard
   - Track repeated recent attempts to add, reduce, hedge, or rebalance.
   - Penalize too many position changes in a short window.
   - Keep `00631L` additions blocked when recent leverage changes are clustered.

2. Risk-budget pacing
   - Treat leverage budget and hedge budget like finite daily/weekly budgets.
   - Avoid spending all risk budget in the first signal.
   - Preserve optionality for crash or recovery windows.

3. Multi-objective reward audit
   - Score candidate actions by expected return, CVaR, drawdown, turnover cost,
     cash buffer, and guard consistency.
   - Do this as an audit, not as an RL policy.

4. Stress-regime scenario interface
   - Use the paper's modular environment idea to make a future GroupA+
     simulator shell.
   - Plug in existing modules instead of creating a new live engine:
     NCF signal, tri-gate volatility memory, systemic bubble, HMM-WJ,
     dynamic CVaR, market impact, and rebalance review.

## Not Imported

Do not import:

- electricity demand data;
- CAISO/ERCOT calibration;
- customer archetype parameters;
- PPO policy or Stable-Baselines3 training recipe;
- hourly electricity price spike model as a financial price model;
- automatic RL-driven target weights;
- automatic rebalance or hedge execution.

## Latest Strategy Impact

No live GroupA+ strategy change.

For the current 2026-07-20 decision context:

- do not auto rebalance;
- do not add `00631L`;
- do not open `00632R`;
- keep `Golden1_0531` unchanged;
- keep all RL/environment ideas research-only.

Reason:

- the paper validates the value of an interactive risk-aware environment, but
  GroupA+ does not yet have a validated broker-action simulator with transaction
  costs, slippage, holdings, leverage fatigue, and crash-window behavior;
- current research shadow remains blocked by FinStressTS, HMM-WJ, dynamic CVaR,
  and density/GMM stability blockers;
- a Gym/RL layer would add model risk if promoted before those gates are cleared.

## Implemented Artifact

Added a research-only review:

- `intervention_fatigue_risk_budget_readiness_review`

Inputs:

- `report/group_a_plus/latest/execution_plan.json`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `report/group_a_plus/latest/market_impact_readiness_review.json`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Outputs:

- recent intervention count;
- recent leverage-change count;
- recent hedge-change count;
- risk-budget consumption estimate;
- cooldown state;
- action pacing recommendation;
- `allow_00631l_add = false`;
- `allow_00632r_open = false`;
- `auto_rebalance_allowed = false`;
- `target_weight_change_allowed = false`.

Current 2026-07-20 output:

- `status = blocked`
- `intervention_fatigue_ready = false`
- `risk_budget_pacing_ready = false`
- `trade_count_nonzero = 1`
- `leverage_change_count = 0`
- `hedge_change_count = 0`
- `turnover = 0.5006477801878955`
- `keep_golden1_0531_unchanged = true`

Implemented files:

- `scripts/evaluate/build_group_a_plus_intervention_history_from_daily_status.py`
- `scripts/evaluate/build_group_a_plus_broker_holdings_time_series_sample.py`
- `scripts/evaluate/build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py`
- `tests/test_build_group_a_plus_intervention_history_from_daily_status.py`
- `tests/test_build_group_a_plus_broker_holdings_time_series_sample.py`
- `tests/test_build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py`
- `report/group_a_plus/latest/intervention_history.json`
- `report/group_a_plus/intervention_history/history/20260720.json`
- `report/group_a_plus/latest/broker_holdings_time_series_sample.json`
- `report/group_a_plus/broker_holdings_time_series_sample/history/20260717.json`
- `report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json`
- `report/group_a_plus/intervention_fatigue_risk_budget_readiness/history/20260720.json`

Normalized intervention history:

- `status = available`
- `source_file_count = 24`
- `entry_count = 40`
- `blocked_entry_count = 21`
- `leverage_intervention_count = 31`
- `hedge_intervention_count = 0`
- coverage: `2026-07-06` to `2026-07-20`
- limitation: system-observed daily-status history, not broker fills

Broker holdings sample:

- `status = sample_available`
- `transaction_count = 146`
- `snapshot_count = 116`
- coverage: `2022-09-14` to `2026-07-17`
- `negative_position_count = 4`
- limitation: transaction-derived sample only, not authoritative broker export

Pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/misc/check_group_a_plus_daily_status.py`

## Decision

Useful, but only as a governance template.

The import should improve GroupA+ review discipline by adding action pacing and
intervention fatigue checks. It should not change live allocation or unlock any
RL optimizer.
