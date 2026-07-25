# 2603.29086 GroupA+ Review

Source:

- `C:/Users/isaac/Downloads/2603.29086.pdf`
- Title: `Realistic Market Impact Modeling for Reinforcement Learning Trading Environments`

## Paper Summary

The paper argues that flat transaction-cost assumptions can materially distort
RL trading results. It introduces Gymnasium-compatible FinRL-style environments
with Almgren-Chriss and square-root market-impact models, permanent impact
decay, participation-of-volume monitoring, and trade-level logging. Its
experiments show that cost model choice changes both performance and algorithm
ranking, and that hyperparameter optimization is necessary to control
pathological turnover / POV growth.

## GroupA+ Decision

Do not import the RL environments or DRL agents.

Import only pre-trade market-impact governance:

- flat bps cost assumptions are insufficient for strategy promotion;
- rebalance proposals must report turnover and participation-of-volume;
- impact/capacity checks should be evaluated before any optimizer-driven trade;
- HPO or parameter tuning is not acceptable unless it also controls execution
  behavior, not only Sharpe.

## Implemented Artifact

- `scripts/evaluate/build_group_a_plus_market_impact_readiness_review.py`
- `report/group_a_plus/latest/market_impact_readiness_review_20260720.json`
- `report/group_a_plus/latest/market_impact_readiness_review.json`
- `report/group_a_plus/market_impact_readiness/history/20260720.json`
- `tests/test_build_group_a_plus_market_impact_readiness_review.py`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `market_impact_readiness_review` as a best-effort daily diagnostic.

Daily history:

- The readiness script writes both latest and dated history snapshots by
  default.
- History can be disabled with `--no-history` for one-off experiments.

Current result:

- status: `blocked`
- turnover: `0.5915811038461518`
- max participation of volume: `0.00022187708009762592`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `live_signal_execution_not_allowed`
- `execution_plan_stale_vs_live_signal`
- `rebalance_review_disallows_auto_rebalance`
- `turnover_exceeds_limit`

## Not Imported

- Gymnasium DRL environment;
- A2C / PPO / DDPG / SAC / TD3 agents;
- NASDAQ 100 experiment results;
- automatic rebalance execution.

## Future Shadow Work

If continued, the safe next step is to connect this readiness check to daily
pipeline and then calibrate Taiwan ETF-specific impact limits:

- ADV / volatility / spread by ticker;
- per-trade POV caps;
- turnover cap by regime;
- square-root cost stress for large rebalance proposals;
- trade-level log for every proposed rebalance.

No live strategy change is justified by this paper.
