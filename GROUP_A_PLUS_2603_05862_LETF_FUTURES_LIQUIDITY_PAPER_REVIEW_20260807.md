# GroupA+ Paper Review - arXiv 2603.05862 LETF/Futures Liquidity - 2026-08-07

## Source

- File: `C:\Users\isaac\Downloads\2603.05862.pdf`
- Title: `Impact of arbitrage between leveraged ETF and futures on market liquidity during market crash`
- Authors: Ryuki Hayase, Takanobu Mizuta, Isao Yagi
- arXiv: `2603.05862`

## Paper Summary

The paper studies leveraged ETF and futures markets with an artificial-market
simulation. It asks what happens to liquidity when erroneous market-sell orders
cause a crash in either:

- the leveraged ETF market, or
- the futures market.

The model has:

- normal agents,
- one arbitrage agent trading both the leveraged ETF and futures,
- one leveraged ETF agent that rebalances futures exposure to maintain leverage.

Liquidity is measured with:

- `Volume`: executed trades,
- `SellDepth`: sell book depth around best ask,
- `BuyDepth`: buy book depth around best bid,
- `Tightness`: bid-ask spread.

Main conclusion:

- If the leveraged ETF market crashes, arbitrage can supply liquidity from
  futures to the leveraged ETF market in terms of sell depth and spread.
- If the futures market crashes, arbitrage can supply liquidity from the
  leveraged ETF market to futures in terms of sell depth and spread, and from
  futures to the leveraged ETF market in terms of volume.
- When the leveraged ETF becomes too large, rebalancing sell pressure can create
  a feedback loop: futures fall, the leveraged ETF sells futures to rebalance,
  futures fall further, and more rebalancing is required.

Important limitation:

- The model does not include trading-day boundaries or end-of-day rebalancing
  concentration.
- It is an artificial-market simulation, not Taiwan ETF empirical evidence.
- It models leveraged ETF and futures interaction, not direct stock/ETF
  portfolio allocation.

## Useful Ideas For GroupA+

### 1. Hidden Liquidity Diagnostic

Useful and safe to adapt as a shadow report.

The paper's strongest concept is that a leveraged ETF's apparent liquidity may
depend on another market's order book. In GroupA+, `00631L.TW` and `00632R.TW`
should not be judged only from their own volume.

Recommended GroupA+ adaptation:

- Build a shadow `letf_hidden_liquidity_stress_shadow`.
- Compare `00631L.TW` and `00632R.TW` liquidity against proxies for the
  underlying/liquidity source:
  - `0050.TW`,
  - Taiwan index futures/TAIFEX data if available,
  - broad market turnover or cross-market stress proxies.
- Output only a liquidity-risk state, not target weights.

Suggested states:

- `normal_liquidity_linkage`
- `letf_liquidity_depends_on_underlying`
- `underlying_liquidity_stress_may_feed_letf`
- `letf_rebalancing_feedback_watch`
- `liquidity_linkage_unavailable`

### 2. Crash-Period Depth/Tightness Monitor

Useful, but needs Taiwan intraday/order-book data to do fully.

The paper emphasizes depth and spread rather than just volume. GroupA+ currently
has market-impact readiness and participation-of-volume checks, but these do not
fully capture bid-ask spread or order-book depth.

Recommended GroupA+ adaptation:

- If intraday or quote data becomes available, track:
  - quoted spread,
  - spread percentile,
  - top-of-book or near-book depth,
  - ETF volume versus underlying/futures volume.
- If only daily data is available, use a conservative proxy:
  - abnormal turnover,
  - large true range,
  - close-to-low pressure,
  - Amihud illiquidity,
  - 00631L/0050 and 00632R/0050 tracking dislocation.

### 3. LETF Rebalancing Feedback Loop Watch

Highly relevant to `00631L.TW`.

The appendix describes the dangerous loop:

- underlying/futures price falls,
- LETF needs to sell futures to rebalance,
- the sale causes further price decline,
- additional rebalancing is required.

Recommended GroupA+ adaptation:

- Build a shadow `letf_rebalancing_feedback_watch`.
- Trigger warnings when all are true:
  - large target `00631L.TW` exposure or large proposed add,
  - sharp underlying decline or high intraday range,
  - elevated turnover/illiquidity,
  - high realized volatility or negative compounding regime,
  - execution guard or source freshness is not clean.
- Output:
  - `feedback_loop_watch=false/true`,
  - `allow_new_00631l_add=false` as review-only until validated.

This should initially be advisory-only. It must not automatically alter
Golden1_0531 or latest strategy weights.

### 4. 00632R Hedge Liquidity Warning

Relevant, but weaker than the `00631L` application.

The paper is about leveraged ETFs and futures, but the inverse ETF leg may have
similar stress-time liquidity and tracking issues. For GroupA+, the current latest
strategy sometimes proposes large `00632R.TW` hedge exposure. The useful import is
not "buy inverse hedge"; it is "large inverse hedge adds should be staged and
checked against liquidity linkage."

Recommended GroupA+ adaptation:

- Extend event-aware execution quality with a liquidity-linkage warning for
  large `00632R.TW` adds.
- Keep `00632R.TW` as short-term hedge review only.
- Require staging when the buy is large relative to current holdings or recent
  turnover.

### 5. Strengthen Existing Market-Impact Readiness

Useful as an enhancement to existing code.

Current GroupA+ already has:

- `market_impact_readiness_review`,
- `letf_tracking_error_effective_fee_readiness_review`,
- `00631l_compounding_regime` diagnostics,
- Moira event-aware execution quality and execution-guard backtests.

This paper suggests the next market-impact readiness improvement:

- add a specific `LETF liquidity linkage` section,
- distinguish standalone ETF participation-of-volume from linked-market stress,
- flag situations where futures/underlying liquidity may be the real liquidity
  source during crash periods.

## What Should Not Be Directly Imported

- Do not import the artificial-market parameters directly.
- Do not treat Japanese Nikkei LETF/futures simulation results as Taiwan ETF
  live evidence.
- Do not create live target weights from Volume, SellDepth, BuyDepth, or
  Tightness alone.
- Do not automatically block or force `00631L.TW`/`00632R.TW` trades without
  Taiwan historical validation.
- Do not assume arbitrage always improves liquidity. It can transfer liquidity
  but can also transmit shocks.

## Recommended Integration Priority

1. `letf_rebalancing_feedback_watch_shadow`
   - Highest value for GroupA+.
   - Directly maps to `00631L.TW` add/re-entry risk.
   - Review-only; no target-weight changes.

2. Add `liquidity_linkage` section to `market_impact_readiness_review`
   - Uses available daily volume/range/Amihud proxies now.
   - Can later upgrade to quote/order-book metrics if data is available.

3. Add `large_inverse_hedge_liquidity_warning` to
   `event_aware_execution_quality_shadow`
   - Relevant when latest strategy proposes large `00632R.TW` adds.
   - Should warn and stage, not auto-trade.

4. Optional future empirical backtest
   - Replay historical GroupA+ days and label whether high liquidity-linkage
     stress predicts worse next-day or next-week `00631L.TW`/`00632R.TW`
     execution outcomes.

## Current 2026-08-10 GroupA+ Relevance

The latest 2026-08-10 preview from the 2026-08-07 workbook has:

- `execution_allowed=false`,
- blocker: `required strategy sources are stale or missing: ['institutional_0050']`,
- market state: `choppy_range_low_risk`,
- signal alignment: `bullish_alignment`,
- target weights:
  - `0050.TW`: `30.00%`,
  - `00631L.TW`: `0.00%`,
  - `00632R.TW`: `27.0787%`,
  - cash: `42.9213%`.

The paper reinforces the existing caution:

- do not add `00631L.TW` while execution guard is blocked,
- large `00632R.TW` hedge adds should remain staged/manual-review,
- liquidity/impact checks should look beyond ETF volume alone.

## Decision

- `promotion_decision`: `research_shadow_candidate`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`
- `keep_golden1_0531_unchanged`: `true`

## Shadow Backtest - 2026-08-07

Implemented first-pass `letf_liquidity_feedback_watch_shadow_backtest`.

Added files:

- `group_a_plus/integrations/letf_liquidity_feedback.py`
- `scripts/evaluate/backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py`
- `tests/test_group_a_plus_letf_liquidity_feedback.py`
- `tests/test_backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py`

Generated artifacts:

- `report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json`
- `report/group_a_plus/letf_liquidity_feedback_watch_shadow/history/letf_liquidity_feedback_watch_shadow_backtest_20260807.json`

Updated pipeline wiring:

- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `group_a_plus/integrations/event_aware_execution_quality.py`
- `scripts/evaluate/build_group_a_plus_event_aware_execution_quality_shadow.py`
- `tests/test_group_a_plus_event_aware_execution_quality.py`

Daily pipeline step:

- `letf_liquidity_feedback_watch_shadow_backtest`
- placement: after `letf_tracking_error_effective_fee_readiness_review`, before
  `asian_etf_tail_analytics_readiness_review`
- step number in 2026-08-07 dry-run: `56`
- all outputs are best-effort diagnostics only
- no target weights, orders, code mutations, or guarded candidates are produced

Test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_letf_liquidity_feedback.py \
  tests/test_backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py \
  tests/test_run_ncf_daily_pipeline.py
```

Result:

- `25 passed`

Backtest command:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py \
  --db FinRL/data/stock_data.db \
  --as-of 2026-08-07 \
  --start 2015-01-01 \
  --range-threshold 0.035 \
  --volume-z-min 1.5 \
  --dislocation-z-min 1.5 \
  --min-trigger-count 20 \
  --output report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json \
  --history-dir report/group_a_plus/letf_liquidity_feedback_watch_shadow/history
```

Current result:

- date range: `2015-01-05` to `2026-08-07`
- rows: `2826`
- trigger count: `313`
- minimum trigger count: `20`
- recommendation: `manual_review_shadow_candidate`
- target weight change allowed: `false`
- guarded candidate allowed: `false`
- promote to live: `false`

Pipeline validation:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260807 \
  --skip-refresh \
  --dry-run
```

Result:

- dry-run completed
- command count: `97`
- LETF-related step order:
  - `37` `market_impact_readiness_review`
  - `55` `letf_tracking_error_effective_fee_readiness_review`
  - `56` `letf_liquidity_feedback_watch_shadow_backtest`
  - `57` `asian_etf_tail_analytics_readiness_review`

Event-aware execution-quality integration:

- `moira_event_aware_execution_quality_shadow` now accepts
  `--liquidity-feedback`.
- The daily pipeline passes
  `report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json`
  into the event-aware execution-quality checklist.
- Added warning:
  `large_00632r_add_respects_liquidity_feedback_watch`
- Trigger condition:
  - current target adds `00632R.TW` to at least `20%`,
  - liquidity feedback backtest is ready for manual review,
  - historical `00632R.TW` 20d negative-return rate after trigger is at least
    `70%`.
- This warning is advisory-only and cannot change target weights or orders.

Current 2026-08-10 workbook-20260807 event-aware result:

- output:
  `report/group_a_plus/latest/event_aware_execution_quality_20260810_workbook_20260807_liquidity_feedback_shadow.json`
- status: `blocked_review_only`
- quality score: `0.74`
- blocker:
  - `execution_guard_satisfied`
- warning:
  - `large_00632r_add_respects_liquidity_feedback_watch`
- liquidity input:
  - `liquidity_feedback_backtest_ready`: `true`
  - `liquidity_feedback_00632r_20d_negative_rate`: `74.242424%`
- decision:
  - target weight change allowed: `false`
  - auto rebalance allowed: `false`
  - allow `00631L` add: `false`
  - allow `00632R` open: `false`

Selected event metrics:

- `00631L.TW` after trigger:
  - 1d forward return mean: `+0.247955%`
  - 5d forward return mean: `+1.081891%`
  - 10d forward return mean: `+1.879566%`
  - 20d forward return mean: `+4.803432%`
  - 20d forward MDD mean: `-7.534967%`
  - 20d forward MDD p05: `-34.654358%`
- `00632R.TW` after trigger:
  - 1d forward return mean: `-0.037112%`
  - 5d forward return mean: `-0.279752%`
  - 10d forward return mean: `-1.009674%`
  - 20d forward return mean: `-2.572604%`
  - 20d negative forward return rate: `74.242424%`
  - 20d forward MDD mean: `-5.528711%`

Interpretation:

- The first-pass proxy has enough observations for manual review.
- It does not prove a profitable live rule.
- For `00631L.TW`, trigger days are not simply bearish; average forward returns
  are positive, but forward drawdowns are large. This supports using the signal
  as a staging/risk warning, not as an automatic no-add rule.
- For `00632R.TW`, trigger days have poor average 5/10/20-day forward returns.
  This supports the current manual-review stance for large inverse-hedge adds.
- The module is shadow-only and cannot change target weights, create orders, or
  promote a guarded candidate.

## Bottom Line

The paper has useful ideas for GroupA+, but they should be imported as
execution-risk diagnostics, not as a new return model or allocation rule.

Best next implementation after this first backtest:

- add a daily `letf_liquidity_feedback_watch_shadow_backtest` best-effort step
  after market-impact and compounding diagnostics;
- use the backtest output to flag large `00631L.TW` add/re-entry and large
  `00632R.TW` hedge add risk during liquidity stress;
- keep all outputs review-only until Taiwan historical validation exists.
