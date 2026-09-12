# 2609.07989 Order-Flow Regime Shadow

- generated_at: `2026-09-12T07:38:43.313510+00:00`
- status: `unavailable`
- policy: `execution_advisory_shadow_only`
- advisory_state: `n/a`
- as_of: `None`
- input: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/intraday_signed_order_flow_latest.csv`
- reason: `missing_signed_flow_csv`

## Decision

- auto_rebalance_allowed: `False`
- creates_orders: `False`
- golden2_0830_change_allowed: `False`
- latest_strategy_change_allowed: `False`
- live_weight_change_allowed: `False`
- target_weight_change_allowed: `False`

## Stress Tickers

- none

## Ticker Details

| ticker | status | latest direction | z | change proxy | break |
|---|---|---|---:|---:|---:|

## Notes

- This shadow requires signed intraday transaction/order-flow data.
- Daily OHLCV proxies are intentionally rejected for this paper.
- This report is advisory only and cannot change latest strategy target weights or orders.
