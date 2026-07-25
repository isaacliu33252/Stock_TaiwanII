# Handoff: 2004.01917 Illiquidity Network for GroupA+（2026-07-19）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\2004.01917.pdf`
- Paper: `The illiquidity network of stocks in China's market crash`
- Target: GroupA+ latest strategy, `Golden1_0531`, 2026-07-20 context
- Import type: liquidity-network data-readiness governance only
- Detailed final handoff:
  `docs/DETAILED_HANDOFF_2004_01917_SRR_ILLIQUIDITY_GROUPA_PLUS_20260719.md`

## Final Decision

No live strategy change.

- No auto rebalance.
- No new `00631L` add.
- No `00632R` hedge.
- Keep `Golden1_0531` unchanged.
- Do not import China 2015 crash-warning parameters.
- Do not use this as a live crash detector.

## Useful Import

Imported concepts for research-only governance:

- illiquidity contagion can be networked across stocks;
- crash days may show denser, more homogeneous liquidity-stress dependencies;
- liquidity-failure clustering over the past five days can be a crash-warning
  candidate;
- finance / core-market instruments deserve inspection during liquidity stress;
- low-degree or peripheral failures may trigger core failure waves.

## Implemented Artifact

Research-only:

- `illiquidity_network_readiness_review`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py`
- `tests/test_build_group_a_plus_illiquidity_network_readiness_review.py`
- `report/group_a_plus/latest/illiquidity_network_readiness_review.json`
- `report/group_a_plus/illiquidity_network_readiness/history/illiquidity_network_readiness_20260720.json`
- `docs/2004_01917_ILLIQUIDITY_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`

Pipeline wiring:

- `run_ncf_daily_pipeline.py`: best-effort step
  `illiquidity_network_readiness_review`
- `build_group_a_plus_research_shadow_decision_snapshot.py`: adds
  `illiquidity_network_readiness_blocked`
- `check_group_a_plus_daily_status.py`: renders
  `Illiquidity Network Readiness`

## Current Output

- `status = blocked`
- `actual_data_end = 2026-07-17`
- `illiquidity_network_ready = false`
- `high_frequency_liquidity_data_ready = false`
- `systemic_failure_signal_ready = false`
- `crash_guard_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `missing_high_frequency_bid_ask`
- `missing_intraday_minute_liquidity`
- `missing_market_wide_failure_events`
- `missing_stock_sector_style_mapping`
- `nmi_illiquidity_network_not_implemented`
- `five_day_systemic_failure_signal_not_validated_for_taiwan`
- `china_2015_parameters_not_portable_to_group_a_plus`
- `crash_warning_not_allowed_to_change_live_weights`

## Practical Impact

The paper supports the existing conservative stance:

- `00631L` add remains blocked;
- `00632R` open remains blocked;
- no auto rebalance;
- no target-weight change.

The artifact is useful because it prevents accidental promotion of a China
high-frequency liquidity-network signal when the required Taiwan data does not
exist in the current database.

## Data Backfill Plan

The latest artifact includes `data_backfill_plan`.

Priority:

1. `high_frequency_bid_ask`
2. `market_wide_failure_events`
3. `intraday_minute_liquidity`
4. `stock_sector_style_mapping`

Minimum tables needed before implementation:

- `intraday_bid_ask_quotes`
- `intraday_minute_illiquidity`
- `stock_failure_events`
- `ticker_metadata`

Important caveat:

- Current daily OHLCV volume can only be a coarse proxy.
- ETF-only data is not enough.
- Neither can reproduce the paper's high-frequency illiquidity network.

## Daily OHLCV Proxy

Implemented:

- `daily_ohlcv_liquidity_stress_proxy`

Current 2026-07-20 run:

- status: `available_research_proxy`
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

Decision:

- proxy can be monitored as research dashboard only;
- proxy cannot become a crash guard;
- proxy cannot change target weights;
- proxy cannot unlock `00631L` add or `00632R` open.

Integration status:

- `research_shadow_decision_snapshot.json` includes:
  - `illiquidity_daily_proxy_status`
  - `illiquidity_daily_proxy_stress_score`
  - `illiquidity_daily_proxy_stress_state`
  - `illiquidity_daily_proxy_manual_review_required`
  - `illiquidity_daily_proxy_coverage_tickers`
- `results/group_a_plus_daily_status_20260720.md` displays:
  - proxy status;
  - proxy stress state;
  - proxy stress score;
  - component counts.

Latest research shadow impact:

- `status = blocked`
- includes `illiquidity_network_readiness_blocked`

Latest daily status impact:

- `results/group_a_plus_daily_status_20260720.md` includes
  `Illiquidity Network Readiness`

## Daily Proxy Backtest

Implemented:

- `illiquidity_daily_proxy_backtest`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_daily_proxy_backtest.py`
- `tests/test_build_group_a_plus_illiquidity_daily_proxy_backtest.py`
- `report/group_a_plus/latest/illiquidity_daily_proxy_backtest.json`
- `report/group_a_plus/illiquidity_daily_proxy_backtest/history/illiquidity_daily_proxy_backtest_20260720.json`

Current 2026-07-20 run:

- status: `blocked`
- actual data start: `2009-01-02`
- actual data end: `2026-07-17`
- total scored days: `3474`
- stress-window days: `359`
- non-window days: `3115`
- stress-window elevated-or-worse rate: `0.08635097493036212`
- non-window elevated-or-worse rate: `0.06645264847512039`
- non-window stress rate: `0.006099518459069021`

Window results:

- 2015 stress: elevated-or-worse `0.375`, max score `0.4875`
- 2020 COVID crash: elevated-or-worse `0.17647058823529413`, max score
  `0.4346153846153846`
- 2022 stress: elevated-or-worse `0.01485148514851485`, max score
  `0.26785714285714285`
- 2026 recent: elevated-or-worse `0.0945945945945946`, max score
  `0.3423076923076923`

Decision:

- backtest does not justify promotion;
- 2015 / 2020 have partial signal;
- 2022 and 2026 are too weak;
- stress-window rate is too close to non-window rate;
- keep proxy as research dashboard only.

Live impact:

- no target-weight change;
- no auto rebalance;
- no `00631L` add;
- no `00632R` open;
- keep `Golden1_0531` unchanged.

## Daily Proxy / SRR-Lite Overlap

Implemented:

- `illiquidity_daily_proxy_overlap`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_daily_proxy_overlap.py`
- `tests/test_build_group_a_plus_illiquidity_daily_proxy_overlap.py`
- `report/group_a_plus/latest/illiquidity_daily_proxy_overlap.json`
- `report/group_a_plus/latest/illiquidity_daily_proxy_overlap_frame.csv`
- `report/group_a_plus/illiquidity_daily_proxy_overlap/history/illiquidity_daily_proxy_overlap_20260720.json`

Current 2026-07-20 run:

- status: `blocked`
- overlap start: `2025-01-02`
- overlap end: `2026-07-16`
- rows: `371`
- illiquidity elevated-or-worse active days: `18`
- SRR no-add active days: `8`
- both active days: `1`
- Jaccard, illiquidity elevated vs SRR no-add: `0.04`

Forward-label comparison:

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
- crash-risk snapshot date: `2026-07-17`
  - watch level: `watch`
  - alert active: `false`
  - category score: `1`

Decision:

- proxy is not just duplicating SRR-lite, but the added dates are not strong
  enough;
- union with SRR-lite raises h10 false positives;
- do not use this as an incremental live gate;
- keep proxy as research-only context.

SRR-lite conclusion:

- SRR-lite remains useful as a conservative shadow no-add diagnostic.
- SRR no-add is stronger than daily illiquidity elevated:
  - SRR no-add h10 precision: `0.5`
  - illiquidity elevated h10 precision: `0.3888888888888889`
- Do not use the daily illiquidity proxy to change SRR thresholds.
- Do not interpret "SRR useful" as permission for auto deleverage or
  rebalance.
- Decision record:
  `docs/SRR_LITE_VS_ILLIQUIDITY_PROXY_DECISION_20260719.md`

Live impact:

- no target-weight change;
- no auto rebalance;
- no `00631L` add;
- no `00632R` open;
- keep `Golden1_0531` unchanged.

## Verification

Focused integration tests:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_illiquidity_network_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `38 passed`

Additional daily proxy backtest tests:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_illiquidity_daily_proxy_backtest.py tests/test_build_group_a_plus_illiquidity_network_readiness_review.py
```

Result:

- `4 passed`

Additional overlap tests:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_illiquidity_daily_proxy_overlap.py
```

Result:

- `2 passed`
