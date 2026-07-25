# Data Freshness Audit（2026-07-18）

Detailed follow-up handoff:
`docs/HANDOFF_GROUPA_PLUS_20260718_REFRESH_SIGNAL_0720_ESTIMATE.md`

## Context

- Audit date: `2026-07-18`
- Weekday: Saturday
- Expected latest Taiwan trading date for local daily market data: `2026-07-17`
- Scope: local downloaded data in `FinRL/data/stock_data.db`, latest GroupA+
  reports, and freshness reports.

## Post-refresh Conclusion

Refresh completed on `2026-07-18`.

The core Taiwan ETF OHLCV data, GroupA+ chip tables, lending/short/day-trading
tables, dealer futures/options tables, external options IV, and key external
market OHLCV caches were refreshed. The active freshness gate improved from
`error` to `warning`.

Remaining warnings are not stale DB dates:

- Taiwan ETF DB OHLCV is at `2026-07-17`, but several raw parquet caches have
  `raw_target_close_invalid` on the target date while OHLCV fields are present.
- TAIFEX futures/options tables are at `2026-07-16`; no `2026-07-17` rows were
  available from the current refresh source in this run.
- TDCC shareholding distribution remains at `2026-07-09`, consistent with the
  lower-frequency release cadence.

## Fresh / Acceptable

Main Taiwan ETF OHLCV:

| Ticker | Max date | Status |
| --- | --- | --- |
| `0050.TW` | `2026-07-17` | ok |
| `0056.TW` | `2026-07-17` | ok |
| `00631L.TW` | `2026-07-17` | ok |
| `00632R.TW` | `2026-07-17` | ok |
| `00679B.TWO` | `2026-07-17` | ok |
| `00751B.TWO` | `2026-07-17` | ok |
| `00878.TW` | `2026-07-17` | ok |

Other tables refreshed to max date `2026-07-17`:

- `ohlcv`
- `derivative_institutional_data`
- `dealer_futures_data`
- `dealer_options_data`
- `institutional_data`
- `margin_data`
- `market_margin_data`
- `securities_lending_data`
- `foreign_shareholding_data`
- `short_sale_balance_data`
- `day_trading_data`
- `external_options_iv`

## Post-refresh Table Status

Important GroupA+ target ticker sources:

| Source | Examples | Max date | Status |
| --- | --- | ---: | --- |
| `institutional_data` | target ETFs | `2026-07-17` | refreshed |
| `margin_data` | target ETFs | `2026-07-17` | refreshed |
| `market_margin_data` | market aggregate | `2026-07-17` | refreshed |
| `securities_lending_data` | target ETFs | `2026-07-17` | refreshed |
| `foreign_shareholding_data` | target ETFs | `2026-07-17` | refreshed |
| `short_sale_balance_data` | target ETFs | `2026-07-17` | refreshed |
| `day_trading_data` | target ETFs | `2026-07-17` | refreshed |
| `shareholding_distribution` | table max | `2026-07-09` | latest available / lower frequency |

Derivative / options sources:

| Source | Max date | Status |
| --- | ---: | --- |
| `derivative_institutional_data` | `2026-07-17` | refreshed |
| `dealer_futures_data` | `2026-07-17` | refreshed |
| `dealer_options_data` | `2026-07-17` | refreshed |
| `taifex_futures_daily` | `2026-07-16` | latest fetched; source did not provide `2026-07-17` in this run |
| `taifex_futures_institutional` | `2026-07-16` | latest fetched |
| `taifex_options_daily` | `2026-07-16` | latest fetched |
| `external_options_iv` | `2026-07-17` | refreshed |

External market sources:

- `^GSPC`, `^IXIC`, `^IRX`, `^TNX`, `GC=F`, `2330.TW`: `2026-07-17`
- `TSM`, `^VIX`, `QQQ`, `SOXX`, `TWD=X`: `2026-07-17`
- `^TWII`: `2026-07-16`, acceptable with one-day lag in freshness policy

## Existing Freshness Report

`results/ohlcv_freshness_20260718.json` after refresh:

- `target_date = 2026-07-17`
- Taiwan ETF DB OHLCV: latest at `2026-07-17`
- `overall_status = warning`
- `error_tickers = []`
- `external_error_tickers = []`
- warning tickers: `0050.TW`, `0056.TW`, `00631L.TW`, `00632R.TW`,
  `00646.TW`, `00713.TW`, `00878.TW`
- warning reason: raw cache target-date `close` is invalid while DB OHLCV is
  current

## GroupA+ Current Implication

Data freshness no longer has external-market hard errors after the final
external refresh. `report/group_a_plus/latest/ops_health.json` now reports:

- `status = warning`
- `errors = []`
- warnings: `system_resources`, `artifact_health`, `external_data_freshness`

Decision:

- mark the 2026-07-18 download refresh as completed
- do not auto-rebalance from data refresh alone
- do not add `00631L` from data refresh alone
- keep GroupA+ latest strategy unchanged
- keep `Golden1_0531` unchanged

## Commands Run

- `.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --date-stamp 20260718 --refresh-target-date auto --force-refresh --strict-refresh --refresh-external-cache --only-refresh`
- `.venv/bin/python refresh_group_data.py --group both --summary-path results/data_refresh_20260718.json --force`
- `.venv/bin/python scripts/fetch/fetch_cross_market_ohlcv.py --tickers '^GSPC,^IXIC,^IRX,^TNX,GC=F,^TWII,2330.TW' --start 2023-07-19 --end 2026-07-19 --output results/cross_market_ohlcv_stale_external_20260718.json`
- `.venv/bin/python scripts/misc/check_ohlcv_freshness.py --target-date auto --max-db-lag-days 3 --output results/ohlcv_freshness_20260718.json`
- `.venv/bin/python -m scripts.run.check_ops_health --output report/group_a_plus/latest/ops_health.json`

## Next Recommended Step

Rebuild the live signal / NCF panels using the refreshed data before making any
rebalance decision. The data refresh itself should not change live allocation
without a rebuilt signal and execution-plan review.

## Follow-up Signal Rebuild（2026-07-18）

After the data refresh, the NCF/live-signal stack was rebuilt against data
through `2026-07-17`.

Generated / updated:

- `results/ncf_00631l_latest_20260718.json`
- `results/ncf_00631l_panel_latest_20260718.csv`
- `results/ncf_00632r_latest_20260718.json`
- `results/ncf_00632r_panel_latest_20260718.csv`
- `results/ncf_2330_latest_20260718.json`
- `results/ncf_2330_panel_latest_20260718.csv`
- `results/ncf_panel_manifest_20260718.json`
- `results/ncf_panel_coverage_20260718.json`
- `results/ncf_advisory_panel_latest_20260718.csv`
- `results/group_a_plus_live_signal_v2_20260718.json`
- `results/group_a_plus_daily_status_20260718.json`
- `report/group_a_plus/latest/live_signal.json`
- `report/group_a_plus/latest/daily_status.json`
- `report/group_a_plus/latest/signal_alignment.json`
- `report/group_a_plus/latest/crash_risk_alert.json`
- `report/group_a_plus/latest/alert_state.json`

Panel coverage:

- `00631L.TW`: pass, panel end `2026-07-17`, gap `0` business days
- `00632R.TW`: pass, panel end `2026-07-17`, gap `0` business days
- `2330.TW`: pass, panel end `2026-07-17`, gap `0` business days

NCF latest summary:

| Model | Date | Direction | Prob up | Calibrated prob up | Confidence | Weighted return |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `00631L` | `2026-07-17` | `UP` | `0.5101` | `0.5055` | `0.3485` | `-0.6190%` |
| `00632R` | `2026-07-17` | `UP` | `0.5204` | `0.5122` | `0.4278` | `+2.0023%` |
| `2330` | `2026-07-17` | `UP` | `0.5321` | `0.5162` | `0.2923` | `-0.3351%` |

Daily status:

- `overall_status = warn`
- `execution_allowed = ok`
- `source_freshness = ok`
- `data_freshness = warn` because `2026-07-18` is Saturday and latest market
  data is `2026-07-17`
- `execution_plan_pre_trade_guard = warn`

Risk / overlay diagnostics:

- Compounding regime: `MEAN_REVERTING`
- Compounding policy: `prohibit_new_leverage_or_reduce_rebalance_frequency`
- Signal alignment: `wide_divergence`
- Leverage suitability: tier `1`, `只適合 0050`, action `0050_only`
- Crash-risk alert: `watch`, `alert_active = false`, manual action
  `watch_only_no_action`
- DFL advisory: `KEEP`

Follow-up decision:

- Data and NCF panels are current enough to evaluate the strategy.
- Do not add new `00631L` exposure from this rebuild alone.
- Do not treat the low-confidence NCF `UP` labels as a strong rebalance trigger.
- Before any live trade, regenerate or review the execution plan pre-trade guard
  because daily status still warns that the execution plan has no aligned
  pre-trade guard.

## Execution Plan Guard Check（2026-07-18）

The execution plan was rebuilt after the live-signal refresh.

Important caveat:

- Workbook: `taiwan_stock_20260619.xlsx`
- Parsed holdings: `0050.TW=1342`, `00631L.TW=0`, `00632R.TW=0`,
  `00679B.TWO=5000`
- Cash input: `0`
- This is a conservative guard-check because the workbook has no cash field.
  It should not be treated as a cash-accurate broker order plan without a
  current cash balance.

Generated / updated:

- `results/group_a_plus_execution_plan_v2_20260718_cash0_guard_check.json`
- `report/group_a_plus/latest/execution_plan.json`
- `results/group_a_plus_daily_status_20260718.json`
- `report/group_a_plus/latest/daily_status.json`

Execution-plan result:

- `requested_as_of_date = 2026-07-18`
- `actual_data_date = 2026-07-17`
- `planning_status = manual_review_required`
- `execution_allowed = false`
- guard reason: turnover ratio `50.06%` exceeds automatic limit `50.00%`

Pre-trade guard result:

- `volatility_gate_no_00631l_add`: `blocked`
- `compounding_regime_no_00631l_add`: `blocked`
- blocked `00631L` buy: `668` shares, estimated notional `21,489.56`
- final target after guards: `00631L.TW = 0`

Daily status after rebuilding the plan:

- `overall_status = warn`
- `execution_allowed = ok` at live-signal level
- `source_freshness = ok`
- `execution_plan_pre_trade_guard = ok`
- detail: `pre_trade_guards=blocked,blocked`

Execution conclusion:

- Do not rebalance automatically.
- Do not buy `00631L`.
- If execution is considered manually, first provide or update the real cash
  balance; otherwise this plan only validates guard behavior, not exact order
  sizing.
