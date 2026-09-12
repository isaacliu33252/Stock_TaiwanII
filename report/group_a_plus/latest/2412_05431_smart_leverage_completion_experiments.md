# 2412.05431 Smart Leverage Completion Experiments

- Generated: `2026-08-21T16:28:30`
- Policy: `research_only_no_groupa_plus_live_change`
- Decision: `do_not_promote_keep_shadow`
- Promotion ready: `False`

## Variant Summary

| Variant | Pass | Holdout Pass | Incident Pass | dFinal vs Benchmark | dFinal vs Latest | Avg 00631L | Lot dFinal | Top Blockers |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| quarterly_default_risk_penalty | 0/11 | 0/3 | 0/4 | 236829.29 | 2191579.75 | 0.1025 |  | latest_a2118_drawdown:11, benchmark_sharpe:6, benchmark_drawdown:5, benchmark_final_value:3 |
| monthly_default_risk_penalty | 0/11 | 0/3 | 0/4 | 305060.10 | 2259810.55 | 0.1034 |  | latest_a2118_drawdown:11, benchmark_sharpe:6, benchmark_drawdown:5, benchmark_final_value:3 |
| monthly_risk_turnover_cap | 0/11 | 0/3 | 0/4 | 260229.74 | 2214980.20 | 0.0978 |  | latest_a2118_drawdown:11, benchmark_drawdown:5, benchmark_sharpe:5, benchmark_final_value:2 |
| monthly_low_beta | 0/11 | 0/3 | 0/4 | 36565.31 | 1991315.76 | 0.0527 |  | latest_a2118_drawdown:11, benchmark_sharpe:5, benchmark_final_value:4, benchmark_drawdown:1 |
| monthly_no_00631l_control | 0/11 | 0/3 | 0/4 | -7169.97 | 1947580.48 | 0.0000 |  | latest_a2118_drawdown:11, benchmark_final_value:6, benchmark_sharpe:6, benchmark_drawdown:1 |
| monthly_risk_turnover_cap_lot1000 | 0/11 | 0/3 | 0/4 | 260229.74 | 2214980.20 | 0.0978 | -159070.28 | latest_a2118_drawdown:11, lot_rounding_final_value:6, benchmark_drawdown:5, benchmark_sharpe:5 |

## Decision

- No variant passed both standard holdout and incident windows.
- Main blockers are benchmark-relative Sharpe/final-value instability and drawdown versus latest A21.18.
- Lot-size 1000 is reported as a stress diagnostic only; it does not create any live order permission.
- Latest strategy, golden1_0531, target weights, execution plans, and order files were not changed.
