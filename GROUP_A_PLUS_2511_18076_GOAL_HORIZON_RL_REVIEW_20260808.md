# Group A+ review: 2511.18076 goal/horizon RL portfolio optimization

## Source

- File: `C:/Users/isaac/Downloads/2511.18076.pdf`
- Title: `Reinforcement Learning for Portfolio Optimization with a Financial Goal and Defined Time Horizons`
- arXiv: `2511.18076v1`
- Date in PDF: 2025-11-22

## Paper takeaway

The paper applies G-Learning and GIRL to goal-based portfolio optimization.
The useful idea is not the reported Sharpe ratio or the simulated allocator.
The useful idea is the reward framing:

- define a target wealth and target date;
- penalize periodic contributions;
- penalize falling short of a target/benchmark path;
- penalize transaction/rebalance size;
- keep reward parameters explicit.

The paper reports a Sharpe ratio around 0.483 in a simulated high-volatility
market and finds GIRL parameter learning gives only marginal improvement over
direct G-Learning parameters.

## Fit with Group A+

Group A+ currently asks practical questions such as: with TWD 1,000,000 and a
given current holding file, what should the latest strategy do on the next date?
That is close to goal-based wealth management, but the current strategy
contract does not yet explicitly define:

- target portfolio value;
- target date;
- periodic contribution plan;
- benchmark wealth path;
- reward penalty weights for contribution shortfall, underachievement, and
  transaction cost.

Without those fields, importing a G-Learning or GIRL allocator would be
ill-posed and easy to overfit.

## Imported

Implemented a research-only readiness review:

- `scripts/evaluate/build_group_a_plus_goal_horizon_reward_readiness_review.py`
- `tests/test_build_group_a_plus_goal_horizon_reward_readiness_review.py`
- `report/group_a_plus/latest/goal_horizon_reward_readiness_review.json`
- `report/group_a_plus/goal_horizon_reward_readiness/history/`

The report checks whether the latest live signal / execution plan has enough
goal-horizon information to support a reward overlay.

Current result: `blocked`.

Blocking reasons:

- `missing_explicit_financial_goal_target_value`;
- `missing_explicit_goal_target_date`;
- `missing_periodic_contribution_plan`.

## Not Imported

Do not import the paper's G-Learning allocator into live Group A+.

Reasons:

- the paper uses simulated market/asset dynamics, not Taiwan ETF data;
- the reported Sharpe result is not evidence for `0050/00631L/00632R`;
- GIRL improves parameters only marginally in the paper's own results;
- Group A+ already has many live/shadow gates, and adding a new RL allocator
  without a frozen goal contract would create governance risk.

## Recommendation

Use this paper to improve the strategy contract, not the live allocator.

Before any goal-based reward overlay is considered, Group A+ should require:

- `financial_goal_target_value`;
- `financial_goal_target_date`;
- `planned_periodic_contribution`;
- benchmark/goal path definition;
- transaction-cost penalty definition;
- walk-forward trade-level validation.

Until those exist, keep `golden1_0531` and latest strategy unchanged.
