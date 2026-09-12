# HANDOFF - 2026-08-14 GroupA+ prediction safety audit

Date: 2026-08-13  
Owner note: Codex 2026-08-13

## Scope

User selected next step 2: check whether the 2026-08-14 GroupA+ prediction/execution plan uses current data, current golden1 signal, and the supplied 2026-08-13 holdings workbook assumption.

This audit is about safety and freshness. It does not place orders.

## Production golden1 pointer refreshed

Command run:

```bash
.venv/bin/python scripts/run/run_group_a_combined_signal.py --as-of-date 2026-08-13
```

Result:

- Stable JSON: `results/group_a_combined_live_latest.json`
- Stable CSV: `results/group_a_combined_live_latest.csv`
- Bundle: `results/group_a_combined_bundle_latest.json`
- New dated signal: `results/signal_group_a_20260813_235014.json`

Verified:

- `results/group_a_combined_live_latest.json`
  - `requested_as_of_date`: `2026-08-13`
  - `actual_data_date`: `2026-08-13`
  - `override_holdings_source`: `null`
  - sha256: `4623b0fcb344586a6d2706e9bc98bce3960674f4a2ea982e62a0a48e15ec11e0`

`group_a_plus.runners.a2111._resolve_golden_signal_path()` resolves to:

```text
/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/group_a_combined_live_latest.json
```

Codex 2026-08-13: this confirms the stale mtime-based golden1 issue is not active for the production golden1 pointer after this refresh.

## Production live signal refreshed

Command run:

```bash
.venv/bin/python group_a_plus/operations/daily_signal.py --as-of 2026-08-14 --portfolio-value 1000000 --output results/group_a_plus_live_signal_v2_20260814_after_20260813_refresh.json
```

Result:

- `report/group_a_plus/latest/live_signal.json`
- `results/group_a_plus_live_signal_v2_20260814_after_20260813_refresh.json`
- Point-in-time snapshot: `results/ncf_snapshots/2026/08/13/a2118_a2111_ncf_late_bull_deleverage_20260813T235113_ec447db0710f.json`

Verified live signal:

- `requested_as_of_date`: `2026-08-14`
- `actual_data_date`: `2026-08-13`
- `business_stale_days`: `1`
- `calendar_stale_days`: `1`
- `execution_allowed`: `true`
- `execution_guard_reasons`: `[]`
- `execution_warning_reasons`: `[]`
- `base_regime`: `golden1`
- `execution_regime`: `golden1`
- golden signal path: `results/group_a_combined_live_latest.json`
- golden signal sha256: `4623b0fcb344586a6d2706e9bc98bce3960674f4a2ea982e62a0a48e15ec11e0`

Live target weights for `portfolio_value=1000000`:

| Asset | Weight |
|---|---:|
| 0050.TW | 0.530000 |
| 00631L.TW | 0.073778 |
| 00632R.TW | 0.000000 |
| 00679B.TWO | 0.000000 |
| cash | 0.396222 |

## Data freshness

Database latest dates checked after the 2026-08-13 data refresh:

| Source | Latest date | Notes |
|---|---:|---|
| ohlcv | 2026-08-13 | ok |
| institutional_data | 2026-08-13 | ok |
| margin_data | 2026-08-13 | ok |
| market_margin_data | 2026-08-13 | ok |
| shareholding_distribution | 2026-08-07 | ok within configured TDCC tolerance |
| dealer_futures_data | 2026-08-13 | ok |
| dealer_options_data | 2026-08-13 | ok |
| derivative_institutional_data | 2026-08-13 | ok |
| foreign_shareholding_data | 2026-08-13 | ok |
| short_sale_balance_data | 2026-08-13 | ok |
| securities_lending_data | 2026-08-12 | ok within configured tolerance |
| day_trading_data | 2026-08-13 | ok |
| external_market_ohlcv | 2026-08-12 | expected one-day lag for external markets |

Live signal `data_freshness.optional_sources` reports all hard sources as `ok`.

## 2026-08-14 scratch execution plan with workbook holdings

Correct plan:

- `results/scratch_predict_20260814/latest_strategy_execution_plan_workbook_20260813_1m_20260814.json`

Correct golden1 what-if basis:

- `results/whatif_signal_group_a_20260813_223018.json`

Correct holdings source:

- `results/scratch_predict_20260814/group_a_holdings_flat_from_taiwan_stock_20260813.json`

Parsed holdings:

| Asset | Shares |
|---|---:|
| 0050.TW | 3994 |
| 00631L.TW | 0 |
| 00632R.TW | 0 |
| 00679B.TWO | 100 |

Cash input:

- `1000000`

Plan freshness:

- `requested_as_of_date`: `2026-08-14`
- `actual_data_date`: `2026-08-13`
- `business_stale_days`: `1`
- `calendar_stale_days`: `1`
- `execution_allowed`: `true`
- `planning_status`: `ready`
- `manual_confirmation_required`: `false`
- source golden signal path: `results/whatif_signal_group_a_20260813_223018.json`

Current total assets:

- `1,428,794.79`

Target weights in the scratch plan:

| Asset | Weight |
|---|---:|
| 0050.TW | 0.626077 |
| 00631L.TW | 0.073778 |
| 00632R.TW | 0.000000 |
| 00679B.TWO | 0.000000 |
| cash | 0.300144 |

Planned staged target shares:

| Asset | Current | Staged target | Delta |
|---|---:|---:|---:|
| 00679B.TWO | 100 | 0 | -100 |
| 0050.TW | 3994 | 5749 | +1755 |
| 00631L.TW | 0 | 1161 | +1161 |
| 00632R.TW | 0 | 0 | 0 |

Estimated execution:

- buy notional: `229,391.19`
- sell notional: `2,635.00`
- estimated total cost: `446.65`
- turnover ratio: `16.24%`
- estimated cash after execution: `772,797.16`

## Important advisory warnings

The 2026-08-14 live signal and scratch plan both show tail risk for new 00631L additions:

- `tail_conformal.state`: `TAIL_RISK_HIGH`
- `recommended_action`: `pause_new_00631l_adds_and_monitor_trough`
- `allow_00631l_add`: `false`
- high-tail reason: `h10_lower_bound_le_8pct`

In the scratch execution plan:

- `pre_trade_guard.status`: `flagged_advisory_only`
- `advisory_pre_trade_guards_enforced`: `false`
- `blocked_trades`: `[]`

Interpretation: the system kept the +1161 share 00631L staged buy because the guard is advisory-only, but the risk diagnostic explicitly says new 00631L additions should be paused and manually reviewed.

## Wrong artifact to avoid

Do not use:

- `results/whatif_signal_group_a_20260813_222902.json`

Reason:

- It used nested holdings JSON directly.
- `current_shares` were read as all zero.
- Corrected by rerunning with flat holdings JSON:
  - `results/whatif_signal_group_a_20260813_223018.json`

## Production execution plan status

`report/group_a_plus/latest/execution_plan.json` was intentionally not overwritten in this audit.

Reason:

- `group_a_plus/operations/execution_plan.py` writes the latest pointer unconditionally.
- The 2026-08-14 workbook/1,000,000-cash run is a user-specified scratch assumption.
- Writing it to latest would make that scratch assumption look like the official production execution plan.

Current production live signal is updated to 2026-08-14/2026-08-13. Current workbook-specific execution plan remains in `results/scratch_predict_20260814/`.

## Final decision

Freshness issue:

- Fixed for production golden1 pointer.
- Fixed for production live signal.
- Scratch 2026-08-14 execution plan uses correct 2026-08-13 data and correct flat holdings.

Trading caution:

- The staged +1161 00631L buy is only allowed because advisory guards are not enforced.
- Tail conformal says pause new 00631L additions.
- If acting manually, review whether to skip or reduce the 00631L buy while keeping 0050 alignment.

## Latest strategy backtests after refresh

User asked whether everything was backtested. Codex 2026-08-13 ran the core latest-strategy backtest set after refreshing the production golden1 pointer and live signal. Scope: active GroupA+ latest strategy, not every historical research-only shadow script in the repository.

Commands:

```bash
.venv/bin/python -m group_a_plus.runners.latest --start 2020-01-02 --end 2020-12-31 --initial-value 1000000 --output results/group_a_plus_latest_backtest_2020_covid_after_20260813_refresh.json --frame-output results/group_a_plus_latest_backtest_2020_covid_after_20260813_refresh_frame.csv

.venv/bin/python -m group_a_plus.runners.latest --start 2022-01-03 --end 2022-12-30 --initial-value 1000000 --output results/group_a_plus_latest_backtest_2022_rate_hike_after_20260813_refresh.json --frame-output results/group_a_plus_latest_backtest_2022_rate_hike_after_20260813_refresh_frame.csv

.venv/bin/python -m group_a_plus.runners.latest --start 2024-01-02 --end 2026-08-13 --initial-value 1000000 --output results/group_a_plus_latest_backtest_2024_2026_after_20260813_refresh.json --frame-output results/group_a_plus_latest_backtest_2024_2026_after_20260813_refresh_frame.csv

.venv/bin/python -m group_a_plus.runners.latest --start 2025-01-02 --end 2026-08-13 --initial-value 1000000 --output results/group_a_plus_latest_backtest_2025_2026_after_20260813_refresh.json --frame-output results/group_a_plus_latest_backtest_2025_2026_after_20260813_refresh_frame.csv
```

Results:

| Scenario | Success | Final value | Total return | Annual return | Sharpe | Sortino | Max drawdown | VaR breach ratio 5% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 COVID | true | 1,245,754.34 | 24.58% | 24.67% | 1.7461 | 1.6095 | -13.93% | 5.35% |
| 2022 rate hike | true | 846,876.29 | -15.31% | -15.48% | -1.5541 | -1.5007 | -21.73% | 5.31% |
| 2024-2026 recent long | true | 2,299,183.52 | 129.92% | 37.54% | 1.8148 | 1.8060 | -16.70% | 5.07% |
| 2025-2026 latest | true | 1,772,296.99 | 77.23% | 42.69% | 1.9444 | 2.0365 | -13.80% | 5.00% |

Interpretation:

- Core latest strategy backtests run successfully after the 2026-08-13 refresh.
- 2022 remains the weak stress window: final value below initial capital and max drawdown about -21.73%.
- 2024-2026 and 2025-2026 remain profitable in this replay.
- These backtests use the active latest manifest and current golden1 pointer; they are not a substitute for rerunning every independent research shadow in `scripts/evaluate/`.

Validation tests:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_latest_strategy.py tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_execution_plan_v2.py tests/test_group_a_plus_daily_signal_v2.py -q
```

Result:

```text
122 passed in 46.21s
```
