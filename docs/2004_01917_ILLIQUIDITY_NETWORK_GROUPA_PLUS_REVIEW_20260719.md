# 2004.01917 Illiquidity Network GroupA+ Review（2026-07-19）

## Source

- File: `C:\Users\isaac\Downloads\2004.01917.pdf`
- Title: `The illiquidity network of stocks in China's market crash`
- Authors: Xiaoling Tan, Jichang Zhao
- arXiv: `2004.01917v3`
- Date shown in PDF: 2021-11-15 preprint, arXiv update 2021-11-12

## Paper Summary

The paper studies China's 2015 stock-market crash through high-frequency
illiquidity networks. It builds stock-to-stock links from comovement in
minute-level illiquidity, where illiquidity is derived from weighted bid-ask
spreads using order-book quote levels.

Main findings:

- Crash days show denser and more homogeneous illiquidity dependencies.
- Illiquidity is associated with investor fear and panic-selling behavior.
- Finance-sector and large-value stocks occupy important positions in the
  illiquidity network.
- Crash propagation can move from peripheral / low-degree stocks to the network
  core and then back to the periphery.
- A five-day count of systemic liquidity-failure days can warn more than half of
  the crash days in the 2015 China sample.

## GroupA+ Relevance

The paper is relevant to GroupA+ because it targets systemic crash warning and
liquidity contagion, which overlap with current GroupA+ research gates:

- SRR-lite crash watch;
- crash-risk alert;
- market-impact readiness;
- systemic bubble time-at-risk;
- LETF tracking / hedge-readiness gates.

Potentially useful concepts:

- liquidity stress should be monitored as a network effect, not just as volume
  or price volatility;
- crash warning should inspect whether many assets lose liquidity together;
- finance-heavy or core-market instruments may transmit liquidity stress;
- an early warning should remain manual-review unless independently validated
  across Taiwan crash windows.

## Not Directly Portable

Do not directly import:

- China 2015 crash thresholds;
- `Nwd=0 = 0` as a live Taiwan crash trigger;
- 0.01 normalized mutual-information threshold;
- China finance-sector conclusions as Taiwan trading rules;
- high-frequency order-book formulas without matching Taiwan bid/ask data;
- any rule that automatically reduces risk, opens `00632R`, or changes target
  weights.

Reasons:

- The paper depends on high-frequency bid/ask order-book data.
- It needs full-market stock universe coverage.
- It needs limit-down / no-bid / no-quote failure timing.
- The authors explicitly note uncertainty about extending the method to other
  markets.
- GroupA+ currently does not have validated Taiwan illiquidity-network
  backtests.

## Implemented Artifact

Implemented as research-only readiness review:

- `illiquidity_network_readiness_review`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py`
- `tests/test_build_group_a_plus_illiquidity_network_readiness_review.py`
- `report/group_a_plus/latest/illiquidity_network_readiness_review.json`
- `report/group_a_plus/illiquidity_network_readiness/history/illiquidity_network_readiness_20260720.json`

The artifact checks whether GroupA+ has the minimum data needed to even build
the paper's signal:

- high-frequency bid/ask quotes;
- intraday minute-level liquidity or illiquidity;
- market-wide limit-down / no-bid / no-quote failure events;
- sector / style metadata for critical-node inspection.

Pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py` runs
  `illiquidity_network_readiness_review` as a best-effort diagnostic.
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  imports the review and adds `illiquidity_network_readiness_blocked`.
- `scripts/misc/check_group_a_plus_daily_status.py` displays the review in
  daily status.

## Current 2026-07-20 Result

Status:

- `blocked`

Actual data end:

- `2026-07-17`

Blocking reasons:

- `missing_high_frequency_bid_ask`
- `missing_intraday_minute_liquidity`
- `missing_market_wide_failure_events`
- `missing_stock_sector_style_mapping`
- `nmi_illiquidity_network_not_implemented`
- `five_day_systemic_failure_signal_not_validated_for_taiwan`
- `china_2015_parameters_not_portable_to_group_a_plus`
- `crash_warning_not_allowed_to_change_live_weights`

Research shadow impact:

- `report/group_a_plus/latest/research_shadow_decision_snapshot.json` now
  includes `illiquidity_network_readiness_blocked`.

Daily status impact:

- `results/group_a_plus_daily_status_20260720.md` now includes
  `Illiquidity Network Readiness`.

## Data Backfill Plan

The latest artifact now includes `data_backfill_plan`.

Minimum viable tables:

- `intraday_bid_ask_quotes`
  - `ticker`
  - `dt`
  - `timestamp`
  - `best_bid_price`
  - `best_bid_volume`
  - `best_ask_price`
  - `best_ask_volume`
  - preferred: bid/ask level 1-5 prices and volumes
  - minimum frequency: `1min_or_better`
  - required universe: broad Taiwan listed stocks, not only GroupA+ ETFs
- `intraday_minute_illiquidity`
  - derived minute-level spread or weighted-spread illiquidity
  - depends on `intraday_bid_ask_quotes`
- `stock_failure_events`
  - limit-down touch / lock
  - no-bid
  - no-quote
  - intraday event timestamp
- `ticker_metadata`
  - sector
  - industry
  - market-cap bucket
  - financial-sector flag

Validation requirements:

- shadow-only signal first;
- validate on Taiwan 2015, 2020, 2022, and 2026 stress windows;
- measure one-day-ahead hit rate and false-positive rate;
- compare overlap with SRR-lite crash watch;
- run randomization / null tests before trusting network links.

Allowed current proxies:

- Daily OHLCV volume proxy can be used only for coarse monitoring.
- ETF-only universe can be used only for sanity-check dashboards.
- Neither is paper-equivalent because they cannot identify no-bid/no-quote
  timing or full-market intraday systemic failures.

## Daily OHLCV Proxy

Implemented in the latest artifact:

- `daily_ohlcv_liquidity_stress_proxy`

Inputs:

- daily `ohlcv` table only.

Components:

- `volume_drought`: latest volume less than 50% of trailing 20-day median;
- `range_spike`: daily range above trailing 252-day 95th percentile;
- `negative_return`: daily return less than or equal to `-3%`;
- `limit_down_proxy`: daily return less than or equal to `-9.5%` or low near
  10% down-limit proxy.

Current 2026-07-20 run:

- proxy status: `available_research_proxy`
- paper equivalent: `false`
- actual data end: `2026-07-17`
- coverage tickers: `9`
- stress score: `0.21666666666666667`
- stress state: `elevated`
- manual review required: `true`
- state thresholds:
  - normal: `< 0.10`
  - watch: `>= 0.10`
  - elevated: `>= 0.20`
  - stress: `>= 0.35`
- state reasons:
  - `range_spike_count:3`
  - `negative_return_count:4`
  - `limit_down_proxy_count:1`
- component counts:
  - volume drought: `0`
  - range spike: `3`
  - negative return: `4`
  - limit-down proxy: `1`

Use:

- research dashboard only;
- no crash guard;
- no live target-weight effect;
- no `00631L` add / `00632R` open unlock.

Decision:

- `illiquidity_network_ready = false`
- `high_frequency_liquidity_data_ready = false`
- `systemic_failure_signal_ready = false`
- `promote_to_live = false`
- `crash_guard_allowed = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

## Daily Proxy Crash-Window Backtest

Implemented:

- `illiquidity_daily_proxy_backtest`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_daily_proxy_backtest.py`
- `tests/test_build_group_a_plus_illiquidity_daily_proxy_backtest.py`
- `report/group_a_plus/latest/illiquidity_daily_proxy_backtest.json`
- `report/group_a_plus/illiquidity_daily_proxy_backtest/history/illiquidity_daily_proxy_backtest_20260720.json`

Backtest context:

- as-of: `2026-07-20`
- actual data start: `2009-01-02`
- actual data end: `2026-07-17`
- total scored days: `3474`
- stress-window days: `359`
- non-window days: `3115`

Aggregate result:

- stress-window elevated-or-worse rate: `0.08635097493036212`
- non-window elevated-or-worse rate: `0.06645264847512039`
- non-window stress rate: `0.006099518459069021`
- all-day state counts:
  - normal: `2927`
  - watch: `309`
  - elevated: `216`
  - stress: `22`

Window results:

- 2015 China-devaluation Taiwan stress:
  - available days: `32`
  - elevated-or-worse rate: `0.375`
  - max score: `0.4875`
  - top day: `2015-08-24`, state `stress`
- 2020 COVID crash:
  - available days: `51`
  - elevated-or-worse rate: `0.17647058823529413`
  - max score: `0.4346153846153846`
  - top day: `2020-03-19`, state `stress`
- 2022 inflation / rate stress:
  - available days: `202`
  - elevated-or-worse rate: `0.01485148514851485`
  - max score: `0.26785714285714285`
  - top day: `2022-07-01`, state `elevated`
- 2026 recent GroupA+ stress:
  - available days: `74`
  - elevated-or-worse rate: `0.0945945945945946`
  - max score: `0.3423076923076923`
  - top days: `2026-06-08` and `2026-06-26`, state `elevated`
  - latest elevated day: `2026-07-17`, score `0.21666666666666667`

Backtest decision:

- `promotion_allowed = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Reason:

- stress-window elevated-or-worse rate is only slightly higher than non-window
  elevated-or-worse rate;
- 2022 stress window is weak;
- daily OHLCV is still not paper-equivalent;
- high-frequency bid/ask and market-wide failure events remain missing.

## Daily Proxy Overlap With SRR-Lite

Implemented:

- `illiquidity_daily_proxy_overlap`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_daily_proxy_overlap.py`
- `tests/test_build_group_a_plus_illiquidity_daily_proxy_overlap.py`
- `report/group_a_plus/latest/illiquidity_daily_proxy_overlap.json`
- `report/group_a_plus/latest/illiquidity_daily_proxy_overlap_frame.csv`
- `report/group_a_plus/illiquidity_daily_proxy_overlap/history/illiquidity_daily_proxy_overlap_20260720.json`

Overlap context:

- as-of: `2026-07-20`
- overlap start: `2025-01-02`
- overlap end: `2026-07-16`
- rows: `371`
- SRR input:
  `results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv`
- crash-risk alert:
  `report/group_a_plus/latest/crash_risk_alert.json`
  - latest snapshot only, not historical overlap series

Key overlap results:

- illiquidity elevated-or-worse active days: `18`
- SRR no-add active days: `8`
- both active days: `1`
- Jaccard, illiquidity elevated vs SRR no-add: `0.04`
- illiquidity elevated without SRR no-add: `17` days
- SRR no-add without illiquidity elevated: `7` days

Forward-label comparison using SRR labels:

- illiquidity elevated h10 precision: `0.3888888888888889`
- SRR no-add h10 precision: `0.5`
- union h10 precision: `0.4`
- SRR no-add h10 false-positive rate: `0.01646090534979424`
- union h10 false-positive rate: `0.06172839506172839`

Latest alignment:

- overlap latest date: `2026-07-16`
  - illiquidity state: `normal`
  - SRR no-add: `false`
  - SRR crash watch: `false`
- crash-risk latest snapshot: `2026-07-17`
  - watch level: `watch`
  - alert active: `false`
  - category score: `1`

Overlap decision:

- `incremental_signal_promotable = false`
- `promotion_allowed = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`

Reason:

- illiquidity elevated is not just a duplicate of SRR-lite, but its standalone
  h10 precision is worse than SRR no-add;
- adding it to SRR increases false positives;
- latest crash-risk alert is only a single-day snapshot, so it cannot validate
  historical overlap;
- keep it as research-only context.

## Latest Strategy Impact

No live GroupA+ strategy change.

For the 2026-07-20 context:

- do not auto rebalance;
- do not add `00631L`;
- do not open `00632R`;
- keep `Golden1_0531` unchanged;
- treat this paper as future liquidity-network data-readiness evidence only.

Verification:

- Focused integration tests passed:
  `38 passed`

## Recommendation

This paper has a useful idea, but GroupA+ can only import it as a readiness gate
for now.

Next possible research step:

- if Taiwan intraday bid/ask or reliable spread data becomes available, build a
  shadow-only liquidity contagion score;
- validate it across Taiwan 2015, 2020, 2022, and 2026 crash/stress windows;
- require false-positive control before it can even become a manual crash watch;
- do not let it directly alter target weights.
