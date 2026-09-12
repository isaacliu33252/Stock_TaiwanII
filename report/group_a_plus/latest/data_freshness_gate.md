# GroupA++ Data Freshness Gate

- Generated at: `2026-09-09T12:24:35`
- As of: `2026-09-09`
- Status: `blocked`
- Policy: `freshness_gate_only_no_weight_change_no_orders`
- Live signal actual data date: `2026-09-07`
- Live signal business stale days: `2`
- OHLCV freshness status: `warning`
- OHLCV target date: `2026-09-09`
- Latest strategy target-weight window end: `2026-08-07`

## Decision

- Data fresh enough for unqualified execution: `False`
- Creates orders: `False`
- Changes latest/golden: `False`
- Promotion allowed: `False`

## Blockers

- `latest_strategy_explain_target_weight_window_lags_live_signal`

## Warnings

- `latest_strategy_explain_snapshot_has_warnings`
- `live_signal_actual_date_lags_ohlcv_freshness_target`
- `ohlcv_freshness_report_warning`
