# Group A+ 2511.18076 Paper Review Handoff -- 2026-08-08

## User Request

User asked:

`C:\Users\isaac\Downloads\2511.18076.pdf 分析, 是否有優點可以導入groupA+，最新策略？`

Then asked:

`留下詳細交接記錄.`

## Environment

- Working directory: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`
- Current date: 2026-08-08 Asia/Taipei
- PDF path read: `/mnt/c/Users/isaac/Downloads/2511.18076.pdf`
- Extracted text path: `/tmp/2511_18076.txt`
- PDF metadata:
  - Title: `Reinforcement Learning for Portfolio Optimization with a Financial Goal and Defined Time Horizons`
  - arXiv: `2511.18076v1`
  - Date in PDF: 2025-11-22
  - Authors: Fermat Leukam, Rock Stephane Koffi, Prudence Djagba
  - Pages: 28

## Paper Summary

The paper applies G-Learning and GIRL to goal-based portfolio optimization.
The core objective is to maximize terminal portfolio value by a target date
while minimizing periodic investor contributions.

Important reward terms:

- contribution cost: penalize required cash injections;
- underachievement penalty: penalize falling below a target/benchmark wealth
  path;
- transaction/rebalance cost: penalize position changes;
- explicit reward parameters: `lambda`, `eta`, `rho`, `Omega`;
- defined investment horizon and target date.

The paper reports Sharpe around 0.483 in a simulated high-volatility setting.
GIRL learns reward parameters, but the paper itself says the improvement over
direct G-Learning is marginal.

## Group A+ Interpretation

This paper is not strong evidence for replacing Group A+ latest strategy with
a new live RL allocator.

Useful import:

- goal/horizon reward contract readiness;
- explicit target wealth and target date;
- periodic contribution plan;
- reward penalty terms for contribution, underachievement, and transaction
  cost;
- governance check before any reward overlay.

Not imported:

- G-Learning live allocator;
- GIRL inverse-RL live parameter fitting;
- GBM simulation result as Taiwan ETF evidence;
- Sharpe `0.483` as Group A+ promotion evidence;
- automatic target-weight changes;
- automatic rebalance.

## Files Added

Review / handoff:

- `GROUP_A_PLUS_2511_18076_GOAL_HORIZON_RL_REVIEW_20260808.md`
- `GROUP_A_PLUS_20260808_PAPER_2511_18076_HANDOFF.md`

Implementation:

- `scripts/evaluate/build_group_a_plus_goal_horizon_reward_readiness_review.py`

Tests:

- `tests/test_build_group_a_plus_goal_horizon_reward_readiness_review.py`

Reports:

- `report/group_a_plus/latest/goal_horizon_reward_readiness_review.json`
- `report/group_a_plus/goal_horizon_reward_readiness/history/goal_horizon_reward_readiness_20260808.json`

## Current Report Result

Latest generated report:

`report/group_a_plus/latest/goal_horizon_reward_readiness_review.json`

Status:

`blocked`

Blocking reasons:

- `missing_explicit_financial_goal_target_value`
- `missing_explicit_goal_target_date`
- `missing_periodic_contribution_plan`

Warning:

- `missing_explicit_transaction_cost_summary_for_reward_penalty`

The latest strategy preview has target weights, but it does not have the
goal/horizon/contribution contract needed to define the paper's reward
objective.

Observed target-weight summary from the latest preview:

- `cash`: 0.42921266083869036
- `risky_weight`: 0.5707873391613096
- `00631L.TW`: 0.0
- `00632R.TW`: 0.2707873391613097

## Decision

The goal/horizon reward layer was imported only as a research readiness review.

Current decision fields:

- `goal_horizon_reward_layer_imported_as_review`: true
- `ready_for_reward_overlay_backtest`: false
- `live_rl_allocator_allowed`: false
- `girl_parameter_learning_allowed_live`: false
- `target_weight_change_allowed`: false
- `auto_rebalance_allowed`: false
- `creates_orders`: false
- `keep_golden1_0531_unchanged`: true
- `promotion_ready`: false

## Verification

Commands run and passed:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_goal_horizon_reward_readiness_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_goal_horizon_reward_readiness_review.py tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py
```

Result:

`5 passed`

## Related Prior Paper Context

Immediately before this, `2602.03903` was completed:

- file: `GROUP_A_PLUS_2602_03903_REGIME_WEIGHTED_CONFORMAL_VAR_REVIEW_20260807.md`
- introduced RWC/TWC tail-conformal shadow diagnostics;
- full replay over 1,355 dates found RWC improved VaR calibration;
- no-add trade-level shadow found RWC `tail_high` would miss too many profitable
  00631L add windows;
- final decision: keep RWC as shadow VaR calibration diagnostic, do not promote
  to live no-add guard.

This matters because both papers involve reward/risk overlays, but neither is
approved for live target-weight changes.

## Next Recommended Steps

Do not change live Group A+ strategy yet.

If continuing this research line, next concrete step is to add a goal-contract
input format, not a live RL model. Required fields:

- `financial_goal_target_value`
- `financial_goal_target_date`
- `planned_periodic_contribution`
- benchmark/goal path definition
- transaction-cost penalty definition
- allowable contribution/rebalance frequency

After those fields exist, the next validation should be:

1. Build a goal-path backtest using saved Group A+ live signals.
2. Compare raw latest strategy vs goal-aware reward overlay.
3. Measure terminal wealth shortfall, contribution burden, turnover cost, max
   drawdown, and missed upside.
4. Keep output shadow-only until walk-forward trade-level validation is positive.

## Important Guardrail

Do not promote G-Learning or GIRL into live Group A+ from this paper. The paper's
evidence is simulated and not Taiwan ETF-specific. `golden1_0531` and latest
strategy weights remain unchanged.
