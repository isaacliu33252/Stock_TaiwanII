# 2604.08356 MRP Strategy-Decay Diagnostic

- Status: `diagnostic_available`
- As of: `2026-08-18`
- Policy: `research_only_mrp_strategy_decay_monitor_no_weight_change`

| strategy | full-sample Sharpe | MRP1 (d=1y) | MRP1 (d=2y) | MRP/Sharpe (d=2y) | worst-regime split (d=2y) |
|---|---:|---:|---:|---:|---|
| switch_ma80_dd11_production | 1.1590 | 0.3074 | 0.3074 | 0.2652 | 2022-10-26 |
| golden1_0531_baseline | 1.1152 | 0.2174 | 0.2174 | 0.1949 | 2022-10-26 |
| defensive_baseline | 1.1122 | 0.1551 | 0.1551 | 0.1395 | 2022-10-26 |

## Boundary

- Diagnostic only, computed from an existing backtest equity curve.
- Not a switch-decision input.
- No target-weight change, no orders, no automatic rebalance.
