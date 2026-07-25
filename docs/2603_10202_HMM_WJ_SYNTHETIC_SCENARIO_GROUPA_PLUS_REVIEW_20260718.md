# 2603.10202 HMM-WJ Synthetic Scenario GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\2603.10202.pdf`
- Title: `Hybrid Hidden Markov Model for Modeling Equity Excess Growth Rate Dynamics: A Discrete-State Approach with Jump-Diffusion`
- Authors: Abdulrahman Alswaidan and Jeffrey Varner
- arXiv: `2603.10202v2`
- Paper date in PDF: 2026-04-02
- Review target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 execution context

## Paper Summary

The paper proposes a hybrid HMM with jump-duration dynamics for synthetic
financial time-series generation. The goal is not point forecasting or trade
execution. The goal is to generate synthetic return paths that better preserve
three stylized facts:

- heavy-tailed return distributions;
- near-zero linear autocorrelation in raw returns;
- persistent volatility clustering.

Main design:

- discretize excess growth rates into Laplace quantile-defined states;
- estimate transitions by direct counting instead of Baum-Welch EM;
- use state-conditional Student-t emissions;
- add a Poisson jump-duration mechanism so tail states can persist for
  empirically realistic durations;
- validate generated paths using KS, AD, Wasserstein-1, Hellinger, and ACF-MAE;
- for multi-asset scenarios, use copulas to preserve per-asset HMM marginals
  while injecting cross-asset dependence.

The paper reports that no model dominates every metric. GARCH better captures
volatility clustering but fails distributional tests; standard HMM has better
distributional fit but weak volatility persistence; HMM-WJ is the most balanced
among the tested generators.

## Useful Ideas For GroupA+

### 1. Synthetic Scenario Quality Gate

The most useful import is not the model itself. It is the quality-control
standard for any future synthetic scenario engine:

- distributional fidelity: KS / AD pass rates;
- tail distance: Wasserstein-1 / Hellinger;
- temporal fidelity: ACF-MAE on absolute returns;
- explicit tradeoff between tail distribution and volatility persistence.

This can strengthen the existing FinStressTS / counterfactual stress harness by
requiring any generated Taiwan ETF scenarios to pass stylized-fact checks before
they are allowed to influence manual review.

### 2. Jump-Duration Stress Episodes

The Poisson jump-duration idea is relevant to `00631L` because leveraged ETFs
are highly sensitive to multi-day high-volatility episodes. A one-day shock is
not enough to model LETF compounding damage.

Potential GroupA+ use:

- model multi-day tail-state dwell periods;
- evaluate whether `00631L` add decisions survive clustered volatility;
- stress `0050 / 00631L / 00632R` paths under persistent negative-tail states;
- compare against current crash-window and tri-gate volatility-memory blockers.

Import decision: useful as a future research-only scenario generator concept.
Do not use it as a live signal.

### 3. Direct Counting / Interpretability

Direct transition counting over quantile states is attractive for governance:

- no EM initialization instability;
- states can be labeled as crash / bear / neutral / bull / rally;
- parameters are more inspectable than a black-box deep generator;
- daily or weekly refresh is computationally feasible.

This is aligned with GroupA+ preference for transparent diagnostics before any
promotion.

### 4. Student-t Copula Dependence

The paper's multi-asset result is relevant because GroupA+ cares about
cross-asset coupling:

- `0050`
- `00631L`
- `00632R`
- `2330`
- SOXX / QQQ / TSM / VIX / USD/TWD if extended

The useful concept is to preserve each asset's marginal synthetic dynamics while
using a Student-t copula or rank reordering to synchronize crashes and rallies.

This can complement the current `systemic_bubble_time_at_risk_review`, which
already tracks ETF coupling and `2330/0050` correlation.

## Not Imported

The following are not suitable for live GroupA+ import now:

- full HMM-WJ generator as a live trading signal;
- synthetic scenarios as direct alpha;
- SPY / S&P 500 calibration copied into Taiwan ETFs;
- paper hyperparameters such as `N = 100`, `nu = 5`, or its jump grid as fixed
  GroupA+ parameters;
- Student-t copula allocation optimizer;
- automatic `00631L` add or de-risk decision.

Reasons:

- The paper validates mainly US equities and SPY-style data, not Taiwan ETFs.
- Out-of-sample validation covers only one 249-trading-day 2025 window.
- The paper itself flags stationarity and structural-break limitations.
- Synthetic paths require a separate Taiwan ETF walk-forward validation before
  they can affect even manual advisory decisions.

## Fit With Existing GroupA+

Existing GroupA+ already has related pieces:

- `finstressts_decision_snapshot`
- `finstressts_counterfactual_shadow`
- `trigate_vol_memory_shadow`
- `systemic_bubble_time_at_risk_review`
- `density_head_tail_risk_advisory`
- crash-window and compounding-regime guards

This paper supports a future `hmm_wj_synthetic_scenario_readiness_review`, not a
replacement for current guards.

Recommended future artifact:

- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`

Suggested readiness checks:

- has enough local `0050 / 00631L / 00632R / 2330` history;
- can fit quantile-state transitions without sparse tail-state failure;
- simulated paths pass KS / AD / Wasserstein / Hellinger thresholds;
- simulated absolute-return ACF-MAE is not worse than current simple baselines;
- jump-duration scenarios increase, rather than dilute, useful crash-window
  coverage;
- Student-t copula or simpler dependence proxy improves crash co-movement versus
  independent marginals;
- output remains research-only and cannot unlock execution.

Implemented on 2026-07-18:

- `scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/hmm_wj_synthetic_scenario_readiness/history/20260717.json`

Latest readiness result:

- `status = blocked`
- `all_required_tickers_ready = true`
- `can_generate_scenarios_for_decision = false`
- `allow_00631l_add = false`
- data coverage is sufficient for future research, but generator and Taiwan ETF
  walk-forward validation are not implemented.

Current blocking reasons:

- `finstressts_snapshot_blocked`
- `trigate_vol_memory_blocks_leverage_add`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `hmm_wj_generator_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

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
- keep Golden1_0531 unchanged;
- keep existing blockers:
  - FinStressTS blocked;
  - tri-gate volatility memory blocks leverage add;
  - systemic bubble time-at-risk blocks leverage add;
  - deployment consistency requires manual review.

## Conclusion

There are useful ideas to import, but only into the research and stress-testing
layer:

- synthetic scenario quality gate;
- jump-duration multi-day stress episode design;
- interpretable quantile-state transition counting;
- Student-t copula dependence idea for future multi-asset scenarios.

There is no direct live trading advantage to import into GroupA+ now. Do not
change latest strategy or Golden1_0531 for 2026-07-20.
