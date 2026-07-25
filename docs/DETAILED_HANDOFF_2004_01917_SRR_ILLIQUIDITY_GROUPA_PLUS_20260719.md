# Detailed Handoff: 2004.01917 / SRR / Illiquidity Proxy for GroupA+（2026-07-19）

## Scope

This handoff closes the `2004.01917` review thread and the follow-up question
about whether SRR-lite is useful.

Context:

- Source PDF: `C:\Users\isaac\Downloads\2004.01917.pdf`
- Paper: `The illiquidity network of stocks in China's market crash`
- Target strategy: GroupA+ latest strategy
- Current strategy anchor: `Golden1_0531`
- Decision date context: `2026-07-20`
- Actual latest OHLCV data used by artifacts: `2026-07-17`

## Final Decision

No live strategy change.

- Do not auto rebalance.
- Do not add `00631L`.
- Do not open `00632R`.
- Do not reduce `0050` from this research thread.
- Do not use the China 2015 paper parameters as Taiwan live thresholds.
- Do not use the daily OHLCV illiquidity proxy as a live crash detector.
- Do not use the daily OHLCV illiquidity proxy to modify SRR-lite thresholds.
- Keep `Golden1_0531` unchanged.

## Why Nothing Was Promoted

Three checks failed promotion:

1. Data readiness failed.
   - Missing high-frequency bid/ask data.
   - Missing intraday minute-level liquidity / illiquidity.
   - Missing market-wide limit-down / no-bid / no-quote failure events.
   - Missing sector/style metadata for full network inspection.

2. Daily proxy crash-window backtest was weak.
   - Stress-window elevated-or-worse rate: `0.08635097493036212`
   - Non-window elevated-or-worse rate: `0.06645264847512039`
   - Difference is too small.
   - 2022 and 2026 windows were weak.

3. SRR overlap did not justify adding the proxy.
   - Illiquidity elevated h10 precision: `0.3888888888888889`
   - SRR no-add h10 precision: `0.5`
   - Union h10 false-positive rate rose from `0.01646090534979424` to
     `0.06172839506172839`.

## Paper Takeaway

Useful ideas from `2004.01917`:

- Illiquidity contagion can be networked across stocks.
- Crash windows may show denser and more homogeneous liquidity-stress links.
- Multi-day clustering of systemic liquidity failure can be an early-warning
  candidate.
- Finance/core-market instruments should be inspected during liquidity stress.
- Peripheral failures may precede core stress.

Not portable now:

- China 2015 thresholds.
- NMI network threshold.
- Five-day systemic liquidity-failure trigger.
- Finance-sector conclusions as direct Taiwan rules.
- Any automatic risk reduction or hedge.

## Implemented Artifacts

### 1. Illiquidity Network Readiness

Artifact:

- `illiquidity_network_readiness_review`

Files:

- `scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py`
- `tests/test_build_group_a_plus_illiquidity_network_readiness_review.py`
- `report/group_a_plus/latest/illiquidity_network_readiness_review.json`
- `report/group_a_plus/illiquidity_network_readiness/history/illiquidity_network_readiness_20260720.json`

Current output:

- status: `blocked`
- actual data end: `2026-07-17`
- illiquidity network ready: `false`
- crash guard allowed: `false`
- allow `00631L` add: `false`
- allow `00632R` open: `false`

Blocking reasons:

- `missing_high_frequency_bid_ask`
- `missing_intraday_minute_liquidity`
- `missing_market_wide_failure_events`
- `missing_stock_sector_style_mapping`
- `nmi_illiquidity_network_not_implemented`
- `five_day_systemic_failure_signal_not_validated_for_taiwan`
- `china_2015_parameters_not_portable_to_group_a_plus`
- `crash_warning_not_allowed_to_change_live_weights`

### 2. Daily OHLCV Illiquidity Proxy

Artifact:

- `daily_ohlcv_liquidity_stress_proxy`

Current 2026-07-20 run:

- status: `available_research_proxy`
- paper equivalent: `false`
- actual data end: `2026-07-17`
- coverage tickers: `9`
- stress score: `0.21666666666666667`
- stress state: `elevated`
- manual review required: `true`

State thresholds:

- normal: `< 0.10`
- watch: `>= 0.10`
- elevated: `>= 0.20`
- stress: `>= 0.35`

State reasons:

- `range_spike_count:3`
- `negative_return_count:4`
- `limit_down_proxy_count:1`

Use:

- research dashboard only;
- no crash guard;
- no target-weight effect;
- no `00631L` add unlock;
- no `00632R` hedge/open unlock.

### 3. Daily Proxy Crash-Window Backtest

Artifact:

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

- 2015 stress:
  - elevated-or-worse: `0.375`
  - max score: `0.4875`
- 2020 COVID crash:
  - elevated-or-worse: `0.17647058823529413`
  - max score: `0.4346153846153846`
- 2022 rate/inflation stress:
  - elevated-or-worse: `0.01485148514851485`
  - max score: `0.26785714285714285`
- 2026 recent stress:
  - elevated-or-worse: `0.0945945945945946`
  - max score: `0.3423076923076923`

Decision:

- Do not promote.
- 2015 / 2020 have partial signal.
- 2022 / 2026 are too weak.
- Stress-window rate is too close to non-window rate.

### 4. Daily Proxy / SRR-Lite Overlap

Artifact:

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

- The proxy is not just duplicating SRR-lite.
- The added dates are not good enough.
- Union with SRR-lite raises false positives.
- Keep it research-only.

## SRR-Lite Decision

SRR-lite is useful, but only as a conservative shadow / manual no-add
diagnostic.

Evidence:

- SRR no-add h10 precision: `0.5`
- SRR no-add h10 false-positive rate: `0.01646090534979424`
- Daily illiquidity elevated h10 precision: `0.3888888888888889`
- Union with illiquidity proxy increases h10 false positives to
  `0.06172839506172839`

Keep:

- SRR no-add as conservative shadow no-add diagnostic.
- SRR crash-watch as low-level manual crash watch.

Do not:

- do not use SRR-lite for automatic sell/deleverage;
- do not use SRR-lite for automatic rebalance;
- do not let SRR crash-watch override no-add;
- do not modify SRR thresholds using the daily illiquidity proxy;
- do not open `00632R` from SRR-lite;
- do not unlock `00631L` add from SRR-lite.

Dedicated decision record:

- `docs/SRR_LITE_VS_ILLIQUIDITY_PROXY_DECISION_20260719.md`

Existing SRR handoff:

- `docs/FINAL_HANDOFF_SRR_LITE_CROSS_MARKET_20260717.md`

## Pipeline / Report Integration

Readiness review is wired into:

- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/misc/check_group_a_plus_daily_status.py`

Latest daily status:

- `results/group_a_plus_daily_status_20260720.md`
- `results/group_a_plus_daily_status_20260720.json`
- `report/group_a_plus/latest/daily_status.json`

Research shadow:

- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Relevant fields:

- `illiquidity_network_status = blocked`
- `illiquidity_network_ready = false`
- `illiquidity_daily_proxy_status = available_research_proxy`
- `illiquidity_daily_proxy_stress_score = 0.21666666666666667`
- `illiquidity_daily_proxy_stress_state = elevated`
- `illiquidity_daily_proxy_manual_review_required = true`

## Verification

Most recent focused verification:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_illiquidity_daily_proxy_overlap.py tests/test_build_group_a_plus_illiquidity_daily_proxy_backtest.py tests/test_build_group_a_plus_illiquidity_network_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `42 passed`

Earlier focused runs:

- readiness / shadow / daily status / pipeline: `38 passed`
- proxy backtest + readiness: `4 passed`
- overlap only: `2 passed`

## Future Work Conditions

Only revisit live promotion if all of the following are available:

- broad Taiwan stock universe coverage;
- high-frequency bid/ask or reliable intraday spread data;
- market-wide limit-down / no-bid / no-quote failure events;
- sector/style metadata;
- Taiwan-calibrated thresholds;
- walk-forward validation on 2015, 2018, 2020, 2022, 2026, and later OOS;
- false-positive rate stays low versus SRR-lite;
- any new signal improves SRR-lite without raising false positives materially.

Until then:

- daily illiquidity proxy remains a research context;
- SRR-lite remains the stronger shadow no-add diagnostic;
- live GroupA+ strategy remains unchanged.
