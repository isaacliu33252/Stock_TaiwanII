# 2607.15195 GroupA+ Review

Source:

- `C:/Users/isaac/Downloads/2607.15195.pdf`
- Title: `SciPhy Reinforcement Learning for Portfolio Optimization`
- arXiv version date in PDF: `2026-07-16`

## Paper Summary

The paper proposes SciPhyRL, an offline continuous-time portfolio optimization
framework. It formulates the state as holdings, prices, and cumulative cost,
uses entropy-regularized distributional RL, reduces the HJB problem to a
pathwise Hamilton-Jacobi equation along observed trajectories, and trains a
PINN in a single offline sweep. A practical modification recasts the control
from trading rate to target holding, allowing the optimizer to reach the desired
position immediately while still charging transaction and price-impact costs.

The experiments use 14 US ETFs from 2019-2025 and an engineered oracle signal.
The paper explicitly states that the reported Sharpe ratios demonstrate a
mechanism, not an attainable live track record.

## GroupA+ Decision

Do not import the SciPhyRL/PINN/Gibbs optimizer into live GroupA+.

Import only governance ideas:

- target-holding control is a better review abstraction than slow trading-rate
  control for short-horizon ETF allocation;
- cumulative cost, turnover, and price impact must be explicit state/checklist
  items before any optimizer-driven rebalance;
- signal quality must be measured out-of-sample before optimizer results can be
  trusted;
- live target-weight changes must remain blocked unless source freshness,
  option-state, adversarial-integrity, and rebalance governance gates pass.

## Implemented Artifact

- `scripts/evaluate/build_group_a_plus_sciphyrl_readiness_review.py`
- `report/group_a_plus/latest/sciphyrl_readiness_review_20260720.json`
- `report/group_a_plus/latest/sciphyrl_readiness_review.json`
- `report/group_a_plus/sciphyrl_readiness/history/20260720.json`
- `tests/test_build_group_a_plus_sciphyrl_readiness_review.py`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `sciphyrl_readiness_review` as a best-effort daily diagnostic.

Daily history:

- The readiness script writes both latest and dated history snapshots by
  default.
- History can be disabled with `--no-history` for one-off experiments.

Current result:

- status: `blocked`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `live_signal_execution_not_allowed`
- `rebalance_review_disallows_target_weight_change`
- `option_state_gate_not_passed`
- `adversarial_market_integrity_not_passed`
- `leverage_suitability_disallows_00631l_add`

Warnings:

- `high_total_risk_score_for_optimizer`
- `signal_alignment_wide_divergence`

## Not Imported

- PINN/HJB optimizer;
- engineered-oracle signal experiment;
- Gibbs policy live execution;
- automatic target-weight change;
- any `00631L` auto-add override.

## Future Shadow Work

If this line is continued, the next safe step is not RL training. It is a
transparent target-holding planning shadow:

- compare current target, target-holding proposal, and no-trade plan;
- charge explicit transaction cost and turnover;
- require option-state and adversarial-integrity gates;
- evaluate on 2018, 2020, 2022, and 2025-2026 windows;
- require improvement versus both no-add and Golden1 proxy after costs.

No live strategy change is justified by this paper.
