# 2609.07946 Stock/Bond/Gold Review

- generated_at: `2026-09-12T07:43:25`
- paper: `Simple Dynamic Stock/Bond/Gold Portfolios`
- pdf: `/mnt/c/Users/isaac/Downloads/2609.07946_simple_dynamic_stock_bond_gold_portfolios.pdf`
- decision: `shadow_only`
- changes_latest_strategy: `False`
- golden1_0531_lockdown: `True`
- golden2_0830_lockdown: `True`

## Paper Takeaways

- The paper studies long-only portfolios of SPY, AGG, GLD, and cash with monthly rebalancing and public data.
- Volatility control scales fixed portfolios toward cash when estimated risk exceeds a target; it does not lever up in calm regimes.
- The reported volatility estimate is an 11-trading-day trailing realized volatility annualized by sqrt(252).
- The 50/30/20 volatility-controlled portfolio reports return 7.8%, volatility 7.3%, Sharpe 0.82, max drawdown 15.9%, turnover 79.0%.
- The Markowitz portfolio reports return 11.6%, volatility 9.0%, Sharpe 1.08, max drawdown 18.1%, turnover 284.4%.
- The fixed 60/40 benchmark reports Sharpe 0.56 and max drawdown 33.7%.
- The paper includes trading costs and shows rankings persist at 10 and 20 basis point cost assumptions.
- The authors caution via robustness/statistical sections that Sharpe advantages have uncertainty and require careful validation.

## GroupA++ Fit

- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Tradable core: `['0050.TW', '00631L.TW', '00632R.TW', '00679B.TWO', '00713.TW', 'cash']`
- Bond candidates: `['00679B.TWO', '00751B.TWO']`
- Gold status: `not_in_current_tradable_watchlist`; proxy: `GC=F in external_market_ohlcv`
- Mismatch: The paper is monthly, U.S.-ETF, unlevered, and includes GLD. GroupA++ is Taiwan ETF based and uses 00631L leverage, so only shadow translation is justified.

## Adoption Candidates

| candidate | status | live change | expected advantage | main risk |
|---|---|---:|---|---|
| `short_window_volatility_control_cash_scaler` | `recommended_shadow` | `False` | May reduce 00631L drawdown spikes while preserving the existing latest strategy's relative asset signal. | GroupA++ already has defensive and execution guards; a second volatility scaler can double-count risk and suppress profitable rebounds. |
| `stock_bond_gold_complementarity_shadow` | `conditional_shadow` | `False` | Adds a third defensive driver when stock/bond correlation is unfavorable; can complement the 2609.08106 bond-only sleeve. | Gold proxy may not map cleanly to executable Taiwan ETF liquidity, tax, spread, and currency exposure. |
| `monthly_constrained_markowitz_shadow` | `conditional_shadow` | `False` | Gives a transparent optimizer for risk-budget and cash-sleeve sizing, using cost-aware objective instead of ad hoc thresholds. | Return forecasts are fragile; paper uses U.S. SPY/AGG/GLD 2006-2026 and monthly cadence, not Taiwan leveraged ETF dynamics. |
| `direct_live_replacement` | `do_not_adopt` | `False` | None without Taiwan-specific evidence and executable gold sleeve. | Would violate lockdown/governance and create asset-universe mismatch. |

## Recommendation

- Backtest the short_window_volatility_control_cash_scaler against latest GroupA++ first; evaluate gold only as a data proxy until a tradable Taiwan gold instrument passes review.
- Do not modify or overwrite lockdown `golden1_0531` / `golden2_0830`.
- Do not promote to live until Taiwan-specific, cost-aware, multi-window validation passes.
