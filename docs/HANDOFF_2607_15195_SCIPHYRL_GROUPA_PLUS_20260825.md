# Handoff: 2607.15195 SciPhyRL for GroupA+

Date: 2026-08-25  
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`  
Paper: `C:/Users/isaac/Downloads/2607.15195.pdf`  
Title: `SciPhy Reinforcement Learning for Portfolio Optimization`  
Scope: GroupA+ / A21.18 import review and shadow experiments.

## Final Decision

Do not change live weights.

Keep the imported ideas as shadow/governance only:

- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `replace_a2118 = false`
- `allow_sciphyrl_optimizer_research = false`
- `train_reward_model_now = false`
- `train_sciphyrl_or_pinn_optimizer_now = false`

The latest active strategy remains:

- `a2118_a2111_ncf_late_bull_deleverage`

Latest local strategy snapshot:

- as_of: `2026-08-24`
- guarded live target: `0050.TW 0.30`, `00631L.TW 0.00`, `00632R.TW 0.00`, `00679B.TWO 0.00`, `cash 0.70`
- raw A21.18 seed ensemble target for action: `0050.TW 0.70`, `00631L.TW 0.30`, `00632R.TW 0.00`, `00679B.TWO 0.00`

## Why the Paper Was Not Promoted

The paper's high-level optimizer is not directly usable as promotion evidence because its experiments rely on an engineered oracle signal. The paper reports the oracle signal has OOS `R2 ~= 0.115`, but the portfolio results are a mechanism demonstration, not an attainable GroupA+ live track record.

Therefore the review imported only the pieces that can be tested without trusting the oracle:

- target-holding execution cost
- real signal quality gate
- quadratic turnover / impact gate
- soft budget / cash accounting
- expectile-style asymmetric downside utility

## Oracle Signal Clarification

In this handoff, `oracle signal` means a paper-side idealized signal that is allowed to know, approximate, or be engineered from information that is not available to a live trading system at decision time.

Practical distinction:

- oracle signal: a research signal used to demonstrate that an optimizer can exploit a strong predictive input
- real signal: a signal GroupA+ can compute using only data available up to the decision date

For GroupA+, real signals include the existing NCF probabilities, PPO/A21.18 state, price/volume history, chip data, cross-market inputs, and other already materialized local features. They do not include future returns, future labels, or engineered hindsight information.

The paper's optimizer should only be considered after the real signal gate proves that GroupA+ has enough OOS predictive value and enough economic trigger events. This did not happen in the 2026-08-25 review.

## Current Monitoring / Review Flow Placement

These 2607.15195 outputs are not a replacement for A21.18. They are review artifacts inside the existing shadow/governance flow:

1. Latest strategy and target snapshot:
   - `report/group_a_plus/latest/strategy.json`
   - `report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json`
   - `report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json`
2. Promotion gate:
   - `report/group_a_plus/latest/a2118_seed_averaging_promotion_gate.json`
3. Execution and turnover governance:
   - `report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json`
   - `report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json`
   - `report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json`
4. Signal-quality governance:
   - `report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json`
5. Reward / asymmetric downside utility review:
   - `report/group_a_plus/latest/2607_15195_expectile_utility_shadow.json`

The correct interpretation is:

- these reports may block an unsafe target
- these reports may recommend further shadow monitoring
- these reports may not independently change live weights
- these reports may not promote SciPhyRL/PINN/HJB optimizer training without upstream gate approval

## Files Added

Cost-aware target holding:

- `scripts/evaluate/build_group_a_plus_2607_15195_cost_aware_target_holding_shadow.py`
- `tests/test_build_group_a_plus_2607_15195_cost_aware_target_holding_shadow.py`
- `report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json`

Real signal quality gate:

- `scripts/evaluate/build_group_a_plus_2607_15195_real_signal_quality_gate.py`
- `tests/test_build_group_a_plus_2607_15195_real_signal_quality_gate.py`
- `report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json`

Quadratic impact / turnover gate:

- `scripts/evaluate/build_group_a_plus_2607_15195_quadratic_impact_turnover_gate.py`
- `tests/test_build_group_a_plus_2607_15195_quadratic_impact_turnover_gate.py`
- `report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json`

Soft budget / cash accounting:

- `scripts/evaluate/build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow.py`
- `tests/test_build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow.py`
- `report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json`

Expectile / asymmetric utility:

- `scripts/evaluate/build_group_a_plus_2607_15195_expectile_utility_shadow.py`
- `tests/test_build_group_a_plus_2607_15195_expectile_utility_shadow.py`
- `report/group_a_plus/latest/2607_15195_expectile_utility_shadow.json`

## Experiment 1: Cost-Aware Target Holding

Report:

- `report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json`

Status:

- `available_for_shadow_monitoring`
- as_of: `2026-08-24`

Decision:

- preferred target for execution review: `guarded_live_target`
- cost-aware execution state: `EXECUTION_LOW_COST`
- raw A21.18 target allowed to override guarded target: `false`
- target weight change allowed: `false`

Key result:

- guarded target turnover: `0.02553`
- guarded estimated cost bps of assets: `0.127649`
- raw A21.18 turnover: `0.674448`
- raw estimated cost bps of assets: `3.37224`
- raw target trade notional: `1002537.654572`
- guarded target trade notional: `37948.800888`

Interpretation:

The paper's target-holding cost view is useful. It confirms the guarded target is execution-light while the raw `0050 70% / 00631L 30%` action is materially more expensive and should not override the guarded target.

## Experiment 2: Real Signal Quality Gate

Report:

- `report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json`

Status:

- `blocked`
- as_of: `2026-06-17`

Decision:

- real signal quality sufficient for SciPhyRL optimizer research: `false`
- allow oracle signal assumption: `false`
- train SciPhyRL or PINN optimizer now: `false`
- target weight change allowed: `false`

Key result:

- evaluation rows: `351`
- primary signal: `prob_up_h20`
- Rank IC: `0.228799`
- Pearson: `0.302487`
- direction accuracy: `0.655271`
- top 30% future return: `0.108309`
- bottom 30% future return: `0.027254`
- A21.18 bad-signal trigger event count: `0`
- minimum required events: `10`

Blocking reason:

- `a2118_bad_signal_trigger_economic_sample_insufficient`

Interpretation:

The NCF `h20` signal has statistical information, but there are not enough economic bad-signal trigger events to justify optimizer research. This blocks importing the paper's RL/PINN optimizer.

## Experiment 3: Quadratic Impact / Turnover Gate

Report:

- `report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json`

Status:

- `blocked`
- as_of: `2026-08-24`

Decision:

- quadratic impact turnover gate passed: `false`
- allow raw A21.18 target to override guarded target: `false`
- allow SciPhyRL optimizer research: `false`
- target weight change allowed: `false`

Key result:

- raw vs guarded turnover ratio: `26.417861`
- guarded target passes cost gate
- raw A21.18 target fails cost gate

Blocking reasons:

- `market_impact_disallows_auto_rebalance`
- `market_impact_readiness_blocked`
- `real_signal_quality_gate_not_passed`
- `real_signal_quality_insufficient_for_optimizer_research`

Interpretation:

The quadratic impact idea is useful as governance, but it blocks rather than promotes the raw target.

## Experiment 4: Soft Budget / Cash Accounting

Report:

- `report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json`

Status:

- `available_for_shadow_monitoring`
- as_of: `2026-08-24`

Decision:

- guarded target best shadow fraction: `0.25`
- guarded target best shadow state: `PARTIAL_ALIGNMENT_PREFERRED_BY_SOFT_BUDGET`
- raw A21.18 best shadow fraction: `0.75`
- raw A21.18 can override guarded target: `false`
- target weight change allowed: `false`

Key result:

Guarded ladder:

- `0.00`: objective `0.008917` bps
- `0.25`: objective `0.005016` bps, best
- `0.50`: objective `0.065879` bps
- `0.75`: objective `0.096206` bps
- `1.00`: objective `0.127649` bps

Raw A21.18 ladder:

- `0.00`: objective `5.459055` bps
- `0.25`: objective `3.913662` bps
- `0.50`: objective `3.051116` bps
- `0.75`: objective `2.870487` bps, best
- `1.00`: objective `3.37224` bps

Interpretation:

Soft budget accounting supports partial alignment and argues against hard full rebalancing. It does not create live permission to change target weights.

## Experiment 5: Expectile / Asymmetric Utility

Report:

- `report/group_a_plus/latest/2607_15195_expectile_utility_shadow.json`

Status:

- `available_for_reward_review`
- as_of: `2026-08-24`

Decision:

- best target by expectile shadow: `guarded_live_target`
- best target by symmetric quadratic shadow: `guarded_live_target`
- expectile utility adds target ranking information: `false`
- train reward model now: `false`
- allow SciPhyRL optimizer research: `false`
- target weight change allowed: `false`

Parameters:

- start: `2020-01-01`
- end: `2026-08-24`
- horizon: `20` trading days
- target 20d return: `0.0`
- expectile tau: `0.90`
- observations per target: `1593`

Expectile ranking, lower is better:

- rank 1: `guarded_live_target`, loss `0.0001396517`
- rank 2: `soft_budget_best_guarded_partial`, loss `0.0001668736`
- rank 3: `current_live_weights`, loss `0.0001764955`
- rank 4: `soft_budget_best_raw_partial`, loss `0.0016578608`
- rank 5: `raw_a2118_seed_ensemble_target`, loss `0.0024835437`

Selected target detail:

- guarded target mean forward 20d return: `0.00617`
- guarded target p05 forward 20d return: `-0.024366`
- guarded target shortfall rate: `0.357815`
- raw A21.18 mean forward 20d return: `0.027032`
- raw A21.18 p05 forward 20d return: `-0.102481`
- raw A21.18 shortfall rate: `0.35656`

Interpretation:

Asymmetric utility clearly penalizes the raw `0050 70% / 00631L 30%` target's tail risk, but it does not add a new ranking beyond symmetric quadratic loss. It validates the guarded target; it does not justify reward-model training.

## Test Verification

Full rebuild commands:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2607_15195_cost_aware_target_holding_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2607_15195_real_signal_quality_gate.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2607_15195_quadratic_impact_turnover_gate.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2607_15195_expectile_utility_shadow.py
```

Command:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_2607_15195_cost_aware_target_holding_shadow.py \
  tests/test_build_group_a_plus_2607_15195_real_signal_quality_gate.py \
  tests/test_build_group_a_plus_2607_15195_quadratic_impact_turnover_gate.py \
  tests/test_build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow.py \
  tests/test_build_group_a_plus_2607_15195_expectile_utility_shadow.py -q
```

Result:

- `15 passed in 58.42s`

## Reproduction Inputs

Primary local inputs used by the 2026-08-25 run:

- stock database: `FinRL/data/stock_data.db`
- live snapshot: `report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json`
- forward monitor: `report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json`
- soft-budget shadow input to expectile review: `report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json`
- NCF 00631L panel default used by signal gate: `results/ncf_00631l_panel_latest_20260716.csv`

Important local dates:

- latest strategy snapshot date: `2026-08-24`
- real signal gate as_of: `2026-06-17`
- expectile sample: `2020-01-01` through `2026-08-24`

## What Counts as a Good Future Result

The current work should only be revisited for live upgrade if future data changes the gate results materially.

Minimum future evidence:

- `2607_15195_real_signal_quality_gate.json` is no longer `blocked`
- A21.18 bad-signal trigger has enough economic events, not just high Rank IC
- `2607_15195_quadratic_impact_turnover_gate.json` passes
- raw or proposed target does not require excessive turnover versus guarded target
- expectile/asymmetric utility adds useful target ranking information, not just confirmation of the guarded target
- any proposed optimizer respects regime constraints and cannot choose simultaneous large long-leveraged and inverse ETF exposure

Examples of insufficient future evidence:

- higher paper-reported Sharpe from the oracle-signal setup
- lower forecast loss without higher economic filter value
- a model that improves average return but worsens 5th percentile or expectile loss
- a target that looks mathematically hedged by holding both `00631L` and `00632R`

## Promotion Gate for Future Work

Do not start SciPhyRL / PINN / HJB optimizer work unless all conditions below are met:

- real signal gate passes with enough economic bad-signal events
- turnover / quadratic impact gate passes
- expectile or another asymmetric reward adds ranking information beyond the existing guarded target
- any proposed target remains constrained by A21.18 regime permissions
- no optimizer is allowed to freely create economically meaningless hedges such as simultaneous large `00631L` and `00632R`

If these conditions are not met, the correct action is to keep the 2607.15195 imports as shadow diagnostics only.
