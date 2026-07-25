# 1610.09404 LETF Tracking Error GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\1610.09404.pdf`
- Title: `Understanding the Tracking Errors of Commodity Leveraged ETFs`
- Authors: Kevin Guo and Tim Leung
- arXiv: `1610.09404v1`
- Date: October 28, 2016

## Paper Summary

The paper studies commodity leveraged ETFs and their tracking errors over
different holding horizons. It emphasizes that leveraged ETF returns can track
their daily target over short horizons but diverge materially over longer
horizons due to:

- volatility decay;
- holding-horizon effects;
- expense fees;
- reference liquidity and replication method;
- OTC swap / futures replication frictions;
- realized tracking error variance.

The paper introduces a benchmark process that includes realized variance:

- LETF return is linked to reference return by leverage `beta`;
- realized variance contributes a drag term;
- expense fee further reduces return.

It also introduces `realized effective fee` as a way to measure how much an LETF
underperforms a variance-adjusted benchmark beyond stated fees.

The paper also studies a double-short strategy on long/inverse LETF pairs. The
strategy can be long realized variance and profitable on average in some
commodity pairs, but it has large tail risk, loses neutrality when the reference
moves sharply, and is sensitive to tracking errors.

## GroupA+ Relevance

This paper is directly relevant to GroupA+ because the strategy uses Taiwan LETFs:

- `00631L.TW`: Taiwan 50 2x long ETF;
- `00632R.TW`: Taiwan 50 inverse ETF.

Useful ideas:

- LETF holding horizon should be an explicit risk variable.
- Realized variance should be used to estimate leveraged ETF decay pressure.
- Tracking error should be measured against a variance-adjusted benchmark, not
  just against simple `beta * reference return`.
- Inverse LETFs can have different and often worse horizon penalties than long
  LETFs.
- A long/inverse pair or hedge should not be assumed neutral unless tracking
  error, realized variance, and large underlying moves are explicitly modeled.
- Any `00632R` hedge should require a tracking-error and horizon-risk gate.

## Potential Import

Import as research-only governance:

1. LETF tracking-error readiness review
   - Compute `00631L` and `00632R` tracking error versus `0050`.
   - Evaluate 1, 5, 10, 20, and 30-day horizons.
   - Track mean tracking error, dispersion, and left-tail tracking error.

2. Realized effective fee proxy
   - Approximate the variance-adjusted theoretical LETF return.
   - Compare actual `00631L` / `00632R` log return against the benchmark.
   - Use the residual as an effective drag / slippage proxy.

3. Holding horizon guard
   - Treat `00631L` as a horizon-sensitive instrument.
   - Penalize holding or adding leverage when realized variance is high and
     trend persistence is weak.
   - Keep current compounding-regime guard aligned with this paper.

4. Hedge neutrality guard
   - Do not assume `00632R` is a clean hedge for `0050` or `00631L`.
   - Require realized tracking-quality review before opening `00632R`.

## Not Imported

Do not import:

- commodity ETF parameters;
- US LETF fee estimates;
- commodity pair trading signals;
- double-short LETF strategy;
- shorting leveraged ETF pairs;
- assumption that `00632R` hedge is delta-neutral;
- automatic `00631L` add or `00632R` open rule.

## Latest Strategy Impact

No live GroupA+ strategy change.

For the current 2026-07-20 decision context:

- do not auto rebalance;
- do not add `00631L`;
- do not open `00632R`;
- keep `Golden1_0531` unchanged;
- keep all LETF tracking-error ideas research-only.

Reason:

- Current daily status is still `warn`.
- Pre-trade guards remain blocked.
- Dynamic CVaR tail/cost readiness is blocked.
- Research shadow decision snapshot is blocked.
- Broker holdings reconciliation is blocked and cannot generate live orders.
- `00631L` already has compounding-regime and volatility-memory concerns.

## Implemented Artifact

Added a research-only review:

- `letf_tracking_error_effective_fee_readiness_review`

Implemented files:

- `scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
- `report/group_a_plus/letf_tracking_error_effective_fee_readiness/history/letf_tracking_error_effective_fee_readiness_20260720.json`

Inputs:

- `FinRL` OHLCV data for `0050.TW`, `00631L.TW`, `00632R.TW`
- `report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json`

Implemented outputs:

- 1/5/10/20/30-day tracking error summary;
- realized variance decay proxy;
- effective drag proxy for `00631L` and `00632R`;
- hedge-neutrality warning for `00632R`;
- `allow_00631l_add = false`;
- `allow_00632r_open = false`;
- `auto_rebalance_allowed = false`.

Current 2026-07-20 run:

- `blocked`
- actual data end: `2026-07-17`
- `00631L` 30d mean/latest tracking error: `-0.004888744513726964` / `-0.05898968415234139`
- `00632R` 60d hedge beta/correlation: `-0.9943236718895596` / `-0.9779260056912819`
- `00632R` full-sample 30d tracking-error p05: `-0.04194782042073657`
- `00632R` recent-60 30d tracking-error p05: `-0.010876108225421257`
- `00632R` latest 30d tracking error: `0.0081190680562589`
- `00632R` tail tracking-error gate split recommended: `true`
- blocking reasons include `research_only_letf_tracking_error_review`,
  `realized_effective_fee_proxy_not_validated`,
  `00632r_hedge_neutrality_not_promoted`,
  `letf_pair_strategy_not_imported`,
  `intervention_fatigue_risk_budget_readiness_blocked`.

Additional 00632R tail-gate review:

- `report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json`
- `status = blocked`
- full-sample auto-trade tail gate passed: `false`
- manual recent tail gate passed: `true`
- gate split recommended: `true`
- no live permission:
  - `manual_hedge_discussion_allowed = false`
  - `allow_00632r_open = false`

Interpretation: the full-sample p05 gate remains a valid conservative blocker
for automatic trading. Recent tail behavior can be monitored separately for
manual review, but it does not override effective-fee, live hedge policy,
market-impact, or research-shadow blockers.

Additional effective-fee proxy validation:

- `report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json`
- `status = blocked`
- proxy validated for manual review: `false`
- failed horizons: `20:tail_overlap`, `30:tail_overlap`
- 5d / 10d tail overlap: `0.8625` / `0.8354430379746836`
- 20d / 30d tail overlap: `0.759493670886076` /
  `0.717948717948718`
- no live permission:
  - `manual_hedge_discussion_allowed = false`
  - `allow_00632r_open = false`

Interpretation: effective drag is highly correlated with realized tracking
error, but the proxy does not reliably capture the 20d and 30d left-tail
overlap. Keep `realized_effective_fee_proxy_not_validated` as a blocker.

Additional live hedge policy review:

- `report/group_a_plus/latest/live_hedge_policy_review.json`
- `status = blocked`
- policy defined: `true`
- live hedge policy validated: `false`
- manual hedge discussion allowed: `false`
- hard prohibitions include no LLM order, no RL allocator order, no generated
  target weight, no auto rebalance, and no position open without manual broker
  action.

Interpretation: policy boundaries are now explicit, but they do not validate a
live hedge policy for action. Keep `live_hedge_policy_not_validated` active.

Pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py` runs the review as best-effort.
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  imports the review and adds
  `letf_tracking_error_effective_fee_readiness_blocked`.
- `scripts/misc/check_group_a_plus_daily_status.py` displays the LETF review
  in daily status.

## Decision

Useful and relevant, but only as a governance layer.

The paper strengthens the current conservative GroupA+ decision: leverage and
inverse ETF exposure should require explicit holding-horizon, realized-variance,
and tracking-error checks before any live action.
