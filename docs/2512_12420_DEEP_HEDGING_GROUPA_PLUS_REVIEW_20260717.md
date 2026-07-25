# 2512.12420 Deep Hedging GroupA+ Review（2026-07-17）

## Source

- PDF: `C:\Users\isaac\Downloads\2512.12420.pdf`
- Title: `Deep Hedging with Reinforcement Learning: A Practical Framework for Option Risk Management`
- Date in paper: November 2025

## Paper Summary

The paper proposes a practical deep-hedging stack for SPX/SPY option-risk
management. It trains a compact stochastic actor-critic policy on daily
end-of-day option surface, realized-volatility, and macro-rate features.

Important implementation ideas:

- leak-free simulator;
- cost-aware reward;
- bounded position size;
- explicit rebalance cadence;
- transaction cost and slippage stress;
- deterministic replay;
- monitoring of turnover, rolling Sharpe, realized cost, and policy drift.

The paper's final reported configuration uses:

- transaction cost: `10 bps` per unit of absolute position change;
- slippage: `8 bps`;
- position limit: `2.0`;
- rebalance cadence: every `25` steps;
- standalone GAE test Sharpe: about `0.50`;
- 50/50 GAE + long SPY test Sharpe: about `0.65`.

The authors explicitly stop short of claiming formal dominance over long SPY:
the GAE overlay has positive test Sharpe, but confidence intervals overlap the
long-SPY benchmark.

## GroupA+ Fit

This paper is relevant to GroupA+ as an overlay governance framework, not as a
direct model replacement.

Useful concepts to import:

- cost-aware overlay review before adding leveraged ETF exposure;
- hard cap on gross overlay notional;
- rebalance cadence and turnover review;
- option / macro / realized-volatility state coverage check;
- deterministic replay and nightly monitoring;
- overlay treated as risk-management sleeve, not alpha engine.

Not imported:

- SPX/SPY trained actor-critic policy;
- automatic hedge execution;
- direct replacement of `a2118_a2111_ncf_late_bull_deleverage`;
- any change to `Golden1_0531`.

## Current GroupA+ 7/20 Read

Inputs:

- `report/group_a_plus/latest/live_signal_20260720_estimate.json`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`
- `report/group_a_plus/latest/cvar_tail_risk_diagnostic.json`
- `report/group_a_plus/latest/density_head_tail_risk_promotion_review.json`

Current constraints:

- live execution is not allowed because required source data is stale/missing;
- NCF live overlay has date mismatch;
- option state is incomplete (`txo_pcr_*`, SOXX option skew/ratio fields are
  missing);
- market state is `medium_high` risk;
- heterogeneous volatility advisory is high;
- rebalance review disallows auto-add of `00631L`;
- density-head GMM is not promoted.

## Produced Artifact

- `scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py`
- `report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json`
- `scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py`
- `results/deep_hedging_lite_overlay_shadow_20260717.json`

Review output:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- `manual_review_required = true`
- `keep_golden1_0531_unchanged = true`

## Decision

Do not import the RL actor.

Do not change GroupA+ latest strategy.

Do not change `Golden1_0531`.

Do not auto-rebalance or auto-add `00631L` for 2026-07-20.

Keep only the governance ideas:

- cost-aware overlay review;
- position cap;
- rebalance cadence;
- state coverage gate;
- deterministic replay / monitoring requirements.

## Deep-Hedging-Lite Shadow

To avoid jumping directly to RL, a transparent Taiwan-specific baseline was
tested first:

- max `00631L` overlay: `20%`
- rebalance cadence: `20` trading days
- cost stress: `18 bps` per absolute `00631L` weight change
- rule inputs: `0050` drawdown, 5-day momentum, realized-volatility ratio,
  `0050` MA trend
- compared against:
  - `no_add_0050_only`
  - `golden1_frozen_50_20_30_proxy`

Result:

- windows tested: `4`
- deep-hedging-lite beats golden1 proxy by STARR95: `1 / 4`
- deep-hedging-lite beats no-add by STARR95: `2 / 4`
- promotion decision: `false`

Window read:

- 2018 correction: fails versus both no-add and golden1 proxy.
- 2020 COVID: beats no-add, fails versus golden1 proxy.
- 2022 rate-hike: beats no-add, fails versus golden1 proxy.
- 2025-2026: beats golden1 proxy, fails versus no-add.

Interpretation:

- The cost-aware/cadence/position-cap framework is useful.
- The simple rule is not robust enough for promotion.
- A future RL or hybrid overlay must beat both no-add and frozen golden1 across
  the same windows after costs before it can be considered.

## Next Research Step

If continuing this line of work, build a Taiwan-specific rule baseline before
any RL:

- state: TXO PCR, foreign TX futures/options positioning, realized vol, 0050 /
  00631L drawdown, USD/TWD, SOXX/TSM;
- action: bounded `00631L` overlay change, not raw portfolio replacement;
- costs: at least `10 bps` plus slippage stress;
- cadence: weekly/monthly candidate windows, not daily churning;
- promotion: must beat no-add / current golden1 proxy after costs on 2018,
  2020, 2022, and 2025-2026 windows.
