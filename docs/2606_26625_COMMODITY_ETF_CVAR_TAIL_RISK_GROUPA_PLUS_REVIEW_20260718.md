# 2606.26625 Commodity ETF CVaR Tail-Risk GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\2606.26625.pdf`
- Title: `Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns`
- Authors: Nicholas Appiah, Ali Jaffri, Dilmi C.W. Hettiachchi-Halpe-Kankanamalage, Svetlozar T. Rachev
- arXiv: `2606.26625v1`
- Paper date in PDF: 2026-06-25
- Review target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 execution context

## Paper Summary

The paper studies portfolio optimization for 30 U.S.-listed commodity ETFs from
2018-12-12 to 2024-12-16 under heavy-tailed returns. It compares passive
buy-and-hold with rolling-window optimized portfolios using:

- mean-variance objectives;
- CVaR 95% / 99% objectives;
- long-only and restricted long-short constraints;
- 504-trading-day rolling windows;
- turnover constraints and transaction-cost robustness;
- EVT / Hill tail-index diagnostics;
- dynamic ARMA-GARCH marginal models with Student-t copula predictive scenarios.

Main result:

- conservative minimum-risk and CVaR-aware portfolios were more stable than
  tangent portfolios;
- dynamic mean-variance tangent portfolios were unreliable due to expected-return
  estimation error;
- improved risk-adjusted performance did not eliminate heavy downside tails;
- implementation value depended heavily on turnover control and transaction-cost
  robustness.

## Useful Ideas For GroupA+

### 1. CVaR Before Return-Seeking Tangency

The strongest import is the governance preference for downside-risk-aware
objectives over return-seeking tangent portfolios in heavy-tailed markets.

For GroupA+ this supports:

- treating `00631L` add decisions as downside-risk constrained decisions;
- avoiding optimizer claims based mainly on expected return;
- requiring CVaR / drawdown / STARR-style checks before any optimizer promotion;
- keeping current no-auto-rebalance posture when tail diagnostics are elevated.

Import decision: useful as research/governance only. Do not promote a CVaR
optimizer to live allocation from this paper alone.

### 2. EVT / Hill Tail Diagnostics After Optimization

The paper stresses that optimized portfolios can still retain heavy downside
tails. This maps directly to GroupA+:

- a lower daily VaR / CVaR estimate is not enough;
- tail thickness should be checked separately;
- 00631L exposure must remain blocked when tail diagnostics remain elevated;
- reward-to-risk improvement should not be confused with tail-risk elimination.

GroupA+ already has related artifacts:

- `cvar_tail_risk_diagnostic.json`
- `density_head_tail_risk_advisory.json`
- `trigate_vol_memory_shadow.json`
- `systemic_bubble_time_at_risk_review.json`
- `hmm_wj_synthetic_scenario_readiness_review.json`

The paper supports continuing these as blockers / manual-review diagnostics.

### 3. Turnover And Transaction-Cost Robustness

The paper's dynamic optimization results show that high-turnover strategies can
lose practical value under costs. This reinforces existing GroupA+ governance:

- `market_impact_readiness_review`;
- `rebalance_review`;
- deployment consistency / execution guard review;
- no automatic optimizer promotion without turnover and cost diagnostics.

Import decision: useful as a pre-trade robustness checklist. No direct weight
change.

### 4. Dynamic ARMA-GARCH Student-t Copula Scenario Concept

The dynamic extension uses ARMA-GARCH marginals and Student-t copula dependence
to generate one-step-ahead scenarios. This is conceptually related to:

- FinStressTS readiness;
- HMM-WJ synthetic scenario readiness;
- systemic bubble ETF-coupling review.

Potential future GroupA+ research:

- a `dynamic_cvar_tail_cost_readiness_review`;
- scenario validation before optimizer use;
- compare simple historical CVaR, HMM-WJ readiness, and ARMA-GARCH copula
  readiness.

This remains research-only until Taiwan ETF walk-forward validation exists.

## Not Imported

The following are not suitable for live GroupA+ import now:

- commodity ETF allocation;
- commodity sector conclusions such as energy / metals / agriculture weights;
- ARMA-GARCH Student-t copula optimizer as live strategy;
- mean-variance or CVaR tangent portfolio as live allocation;
- long-short commodity ETF assumptions;
- Bloomberg commodity ETF parameters;
- automatic `00631L` add, `00632R` hedge, or Golden1_0531 change.

Reasons:

- The paper studies U.S. commodity ETFs, not Taiwan equity / LETF instruments.
- Commodity futures roll yield, storage, hedging pressure, and term-structure
  effects do not map directly to `0050`, `00631L`, or `00632R`.
- The paper itself shows optimized portfolios remain heavy-tailed.
- Dynamic strategies can be highly turnover-sensitive.

## Fit With Existing GroupA+

Existing GroupA+ already has several compatible pieces:

- `rebalance_review_20260720.json`
- `market_impact_readiness_review.json`
- `cvar_tail_risk_diagnostic.json`
- `density_head_tail_risk_advisory.json`
- `finstressts_decision_snapshot.json`
- `hmm_wj_synthetic_scenario_readiness_review.json`
- `systemic_bubble_time_at_risk_review.json`

This paper supports a future consolidated readiness artifact:

- `dynamic_cvar_tail_cost_readiness_review`

Suggested checks:

- CVaR 95 / 99 comparison versus current allocation;
- Hill tail-index / EVT tail-thickness diagnostic;
- maximum drawdown and Calmar / STARR style score;
- turnover and transaction-cost stress;
- expected-return sensitivity warning for tangent-style optimizers;
- explicit rule that improved risk-adjusted metrics do not unlock leverage if
  tail thickness remains elevated.

## Latest Strategy Decision

Live strategy remains unchanged:

- Strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Runner: `group_a_plus.runners.a2118`
- Reference target:
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - `00632R.TW = 0%`
  - `00679B.TWO = 0%`
  - cash = `30%`

For the 2026-07-20 context:

- no auto-rebalance;
- no new `00631L` add;
- no direct `00632R` hedge;
- keep Golden1_0531 unchanged;
- keep existing blockers:
  - FinStressTS blocked;
  - tri-gate volatility memory blocks leverage add;
  - systemic bubble time-at-risk blocks leverage add;
  - HMM-WJ scenario readiness blocked;
  - deployment consistency requires manual review.

## Conclusion

There are useful ideas to import into GroupA+ governance:

- prefer downside-risk-aware checks over return-seeking tangent optimization;
- use CVaR plus EVT / Hill diagnostics instead of CVaR alone;
- require turnover and transaction-cost robustness before any dynamic optimizer
  is trusted;
- keep scenario-based optimizer ideas research-only until Taiwan ETF
  walk-forward validation exists.

There is no direct live trading advantage to import into GroupA+ now. Do not
change latest strategy or Golden1_0531 for 2026-07-20.

## Implementation Record（2026-07-18）

Added a research-only readiness artifact based on this paper:

- Builder: `scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
- Test: `tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
- Latest output: `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- History output: `report/group_a_plus/dynamic_cvar_tail_cost_readiness/history/20260720.json`

Integrated into:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_check_group_a_plus_daily_status.py`

Latest dynamic CVaR / tail / cost readiness result:

- `status = blocked`
- `dynamic_optimizer_ready = false`
- `tail_cost_readiness_ready = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Key blockers:

- `cvar_tail_risk_diagnostic_research_only`
- `00631l_hill_tail_index_positive_heavy_tail`
- `00631l_pot_gpd_shape_positive_heavy_tail`
- `density_tail_model_unstable_research_only`
- `market_impact_readiness_blocked`
- `market_impact_disallows_auto_rebalance`
- `rebalance_review_disallows_auto_rebalance`
- `rebalance_review_disallows_target_weight_change`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `systemic_bubble_disallows_00631l_add`
- `hmm_wj_scenario_readiness_blocked`
- `scenario_generator_not_decision_ready`
- `dynamic_cvar_optimizer_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

The consolidated research shadow snapshot now includes:

- `dynamic_cvar_status = blocked`
- `dynamic_cvar_tail_cost_ready = false`
- `dynamic_cvar_optimizer_ready = false`
- `dynamic_cvar_allow_00631l_add = false`
- blocker: `dynamic_cvar_tail_cost_readiness_blocked`

Daily status visibility added:

- CLI input: `--dynamic-cvar-tail-cost-readiness-review`
- JSON key: `group_a_plus.dynamic_cvar_tail_cost_readiness_review`
- Markdown section: `Dynamic CVaR Tail/Cost Readiness`
- Pipeline wiring: daily status now receives
  `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`

Validation daily-status output:

- `results/group_a_plus_daily_status_20260720_dynamic_cvar.json`
- `results/group_a_plus_daily_status_20260720_dynamic_cvar.md`
- Overall status remained `block` due to execution/data freshness blockers; the
  dynamic CVaR section is display/governance only and did not add a live
  execution gate.

Verification:

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py`
  - `19 passed`
- `.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py`
  - `30 passed`
- `.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py scripts/run/run_ncf_daily_pipeline.py`
- `.venv/bin/python -m py_compile scripts/misc/check_group_a_plus_daily_status.py scripts/run/run_ncf_daily_pipeline.py`

Operational decision remains unchanged for 2026-07-20:

- no auto rebalance;
- no new `00631L` add;
- no `00632R` hedge;
- no Golden1_0531 change;
- dynamic CVaR optimizer remains research-only and blocked from live execution.
