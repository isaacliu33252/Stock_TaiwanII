# GroupA+ Paper Review: 2026-09-04 -- 2608.15841 QUESTrader / Self-Supervised Auxiliary Task Discovery

- Paper:
  `C:\Users\isaac\Downloads\2608.15841_self_supervised_auxiliary_task_discovery_stable_rl_stock_trading.pdf`
- Repository copy:
  `research/papers/2608.15841_self_supervised_auxiliary_task_discovery_stable_rl_stock_trading.pdf`
- Extracted text: 36 pages, 75,221 characters via `pypdf`
- Scope: decide whether this paper has advantages that should be imported into
  GroupA+ and the current latest strategy.
- Decision: useful as a research/shadow validation direction, not enough for a
  direct latest-strategy production change.

## Executive Verdict

Do not change GroupA+ latest strategy weights from this paper now.

The paper's core idea is valuable:

- Automatically discover auxiliary tasks instead of hard-coding them.
- Express auxiliary tasks as GVFs, defined by learned cumulants and
  state-dependent discounts.
- Use non-myopic meta-gradients so auxiliary tasks are credited by their delayed
  impact on PPO trading performance.
- In experiments, this improves return and risk-adjusted metrics across DJI,
  FTSE, Sensex, and TAIEX.

But the production transfer is blocked:

- The paper trains a fresh PPO-style multi-stock trading agent.
- GroupA+ latest strategy is an existing ETF strategy with many governance,
  NCF, risk, and execution layers.
- The paper's TAIEX test is top 30 Taiwan stocks, not GroupA+ ETFs
  `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`.
- It assumes 0.1% transaction fee, zero slippage, negligible market impact, and
  close-price execution. That is too light for leveraged/inverse ETF live rules.
- It does not provide a drop-in auxiliary-task selection rule that can safely
  change current target weights.

Therefore: import the concept only as a shadow/research gate for NCF auxiliary
heads; do not import it into latest target weights or live execution.

## Paper Summary

The paper proposes QUESTrader, a PPO-based stock trading framework with two
networks:

1. Main/Answer network:
   - Learns the PPO policy.
   - Learns the value function.
   - Learns answers to auxiliary GVF questions.

2. Question network:
   - Receives a short future-state slice.
   - Emits cumulants and discount factors.
   - These cumulants/discounts define auxiliary GVF tasks.
   - It is trained through meta-gradients to make the downstream PPO objective
     better, not to fit a fixed supervised label.

The auxiliary prediction target is a General Value Function:

- It predicts expected discounted sums of arbitrary cumulant signals.
- The cumulant and discount are learned rather than manually specified.
- The point is to improve representation quality and stabilize PPO learning.

The method uses a non-myopic inner unroll:

- The main network is updated for `K` inner PPO steps.
- The question network receives credit through those updates.
- This addresses the fact that auxiliary tasks may help trading only after
  several learner updates, not immediately.

## Experiment Setup

Markets:

- DJI
- FTSE
- Sensex
- TAIEX

Data:

- Daily close data from Yahoo Finance.
- 2010-01-01 to 2025-03-31.
- Train/validation: 2010-01-01 to 2023-12-31.
- Out-of-sample test: 2024-01-01 to 2025-03-31.

Universe:

- DJI: 30 stocks.
- Sensex: 30 stocks.
- FTSE: top 30 stocks.
- TAIEX: top 30 stocks.

State:

- Balance.
- Shares held.
- Close price.
- Eight technical indicators per stock:
  SMA 30/60, MACD, Bollinger upper/lower, RSI, CCI, ADX.

Action:

- Buy/sell/hold for each stock.
- The action is an `n`-dimensional vector of share changes.

Reward:

- Immediate P/L minus transaction cost.
- Uses fixed transaction cost.

Assumptions:

- Zero slippage.
- Negligible market impact.
- Immediate settlement.
- End-of-period execution.

These assumptions are acceptable for an academic comparison, but too weak for
direct GroupA+ production transfer.

## Reported Results

The paper reports QUESTrader as best overall on annual return, cumulative
return, Sharpe, Calmar, and Sortino across the four tested markets.

TAIEX table, most relevant but still not directly GroupA+:

| model | annual return | cumulative return | Sharpe | max drawdown | Calmar | Sortino |
|---|---:|---:|---:|---:|---:|---:|
| TWII index | 17.554% | 20.991% | 0.893 | 18.692% | 0.939 | 1.173 |
| MVO | 18.007% | 21.468% | 1.738 | 8.065% | 2.173 | 2.171 |
| PPO | 21.513% | 25.718% | 1.001 | 19.525% | 1.102 | 1.490 |
| DeepScalper | 26.833% | 32.740% | 1.236 | 16.231% | 1.653 | 1.860 |
| QUESTrader | 30.279% | 38.603% | 1.803 | 13.632% | 2.559 | 2.310 |

The strongest point is not just return; QUESTrader also improves
risk-adjusted metrics materially versus PPO and other DRL baselines.

## Ablation Findings

The paper's ablation is useful for future GroupA+ experiments:

- Too few auxiliary questions underfit market structure.
- Too many auxiliary questions add redundancy/noise.
- A moderate question bank is best.
- Reported practical range:
  - `dq` around 16-64 questions.
  - inner unroll `K` around 10-20.
- Very long unrolls increase variance and memory load.

This suggests that if GroupA+ tests automatic auxiliary discovery later, it
should start small and controlled. It should not train a huge unrestricted
auxiliary bank.

## Fit Against GroupA+

### Good Fit

GroupA+ already has auxiliary-style NCF signals:

- `prob_fwd_mdd_gt5_h20`
- `prob_fwd_gain_gt5_h20`
- `tail_reward_risk_score`
- downside/upside NCF composite signals
- multiple horizons: 1d, 5d, 20d
- direction + return + tail heads

Relevant local code:

- `group_a_plus/integrations/ncf.py`
- `scripts/misc/ncf_00631l.py`
- `scripts/misc/ncf_0050.py`
- `group_a_plus/operations/daily_signal.py`

This means GroupA+ does not need to import the whole QUESTrader agent to use
the paper's lesson. The practical import is to audit whether existing auxiliary
heads truly improve downstream live-policy decisions.

### Poor Fit

Direct production adoption is not justified because:

- QUESTrader is a full PPO architecture, not a lightweight scoring layer.
- It requires retraining the policy with meta-gradient auxiliary discovery.
- It is evaluated on stock baskets, not leveraged/inverse ETFs.
- It does not address GroupA+'s known live constraints:
  stale external features, ETF-specific tracking error, securities lending
  warnings, TAIFEX timing, odd-lot/rounding, high correlation between 0050 and
  00631L, inverse ETF behavior, and existing signed-review governance.
- It does not provide a walk-forward ablation against GroupA+'s current
  `a2118_a2111_ncf_late_bull_deleverage` strategy.

## Import Decision

### Do Not Import Into Latest Strategy Now

No change should be made to:

- `report/group_a_plus/latest/strategy.json`
- `golden1_0531`
- `golden2_0830`
- target weights
- execution permissions
- order generation
- NCF live thresholds

Reason:

The paper's empirical edge has not been reproduced inside GroupA+'s actual ETF
environment, and direct adoption would require a new PPO training architecture.

### Importable Advantage

The useful import is a research-only auxiliary-task discovery/readiness review:

1. Treat GroupA+'s existing NCF tail/drawdown/upside heads as auxiliary tasks.
2. Measure whether each auxiliary head improves downstream policy quality, not
   only standalone AUC.
3. Compare current fixed auxiliary heads against a small candidate bank of
   discovered/derived auxiliary labels.
4. Require purged walk-forward validation with no unresolved forward-label
   leakage.
5. Keep all results shadow-only until they pass multi-window policy impact
   tests.

This is aligned with the paper's true lesson: auxiliary tasks should be judged
by their effect on the trading objective, not by whether they are intuitively
appealing.

## Recommended Shadow Design

Suggested artifact:

- `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json`
- optional markdown:
  `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.md`

Suggested checks:

| check | purpose |
|---|---|
| `existing_aux_heads_available` | Confirm NCF has tail/gain/drawdown heads. |
| `aux_head_policy_lift_positive` | Check policy-level improvement, not only AUC. |
| `purged_walk_forward_passed` | Avoid forward-label leakage. |
| `multi_window_consistency_passed` | Avoid one-window overfit. |
| `tail_event_sample_size_passed` | Ensure enough drawdown/gain events. |
| `turnover_and_cost_not_worse` | Prevent noisy auxiliary heads from increasing churn. |
| `live_feature_freshness_ok` | Avoid promoting heads that rely on stale external sources. |
| `latest_strategy_change_allowed` | Must stay false until all above pass. |

Initial decision should be:

```json
{
  "policy": "research_only_no_weight_change",
  "decision": {
    "promotion_allowed": false,
    "decision": "shadow_readiness_only"
  }
}
```

## Why This Is Not a Strategy Upgrade Yet

The paper compares trained algorithms on a benchmark setup. GroupA+ needs a
different proof:

- Does an auxiliary task improve the actual GroupA+ action path?
- Does it reduce bad 00631L exposure before crashes?
- Does it avoid false hedges in bull trends?
- Does it improve Sharpe and max drawdown after realistic costs?
- Does it survive 2020, 2022, 2024-2026, and recent/live windows?
- Does it stay stable when external-market OHLCV is stale or missing?

None of those are answered by the paper directly.

## Final Recommendation

Useful point found: yes.

Direct latest-strategy import: no.

Best next step:

Create a shadow/readiness gate for GroupA+ NCF auxiliary heads inspired by
QUESTrader. It should test auxiliary tasks by downstream policy impact under
purged walk-forward and multi-window stress validation. It should not alter
latest target weights until it passes those checks.

Production status after this review:

- `golden1_0531`: unchanged
- `golden2_0830`: unchanged
- latest strategy: unchanged
- live weights: unchanged
- execution permissions: unchanged
