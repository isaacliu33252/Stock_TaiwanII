# 2609.07946 Adoption Matrix

- generated_at: `2026-09-12T07:45:57`
- policy: `research_summary_no_orders_no_live_weight_change`
- adopt_into_latest_strategy_now: `False`
- promotion_gate_ready: `False`

| candidate | verdict | import_now | reason |
|---|---|---:|---|
| short_window_volatility_control_cash_scaler_monthly | reject | `False` | No robust pass; return drag is not compensated enough by drawdown improvement. |
| short_window_volatility_control_cash_scaler_daily | reject | `False` | No robust pass; daily scaling increases operational churn without stable net benefit. |
| stock_bond_gold_complementarity_sleeve | forward_shadow_continue | `False` | Backtest is robust, but 00635U is a futures ETF outside current watchlist/tradable core; latest 2026-09-10 signal is not triggered. |
| bond_only_complementarity_sleeve | forward_shadow_continue | `False` | Uses existing pipeline tickers and has robust historical evidence, but latest 2026-09-10 signal is not triggered and no forward live log exists yet. |
| monthly_constrained_markowitz | reject | `False` | Best screened combo only passes 3/5 windows; improvement is too small for optimizer complexity. |

## Decision

- Do not change latest GroupA++ target weights, execution plans, or orders.
- Continue forward shadow for complementarity sleeves.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
