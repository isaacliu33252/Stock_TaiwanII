# 2609.07989 Order-Flow Regime Review

- generated_at: `2026-09-12T15:31:33`
- paper: `Regimes in the Order Flow`
- subtitle: `Duration-Aware and Multivariate Bayesian Online Changepoint Detection for High-Frequency Markets`
- pdf: `/mnt/c/Users/isaac/Downloads/2609.07989_regimes_in_the_order_flow.pdf`
- decision: `execution_advisory_shadow_only`
- changes_latest_strategy: `False`
- changes_golden1_0531: `False`
- changes_golden2_0830: `False`

## Paper Takeaways

- The tested data are signed high-frequency order-flow series for AAPL and MSFT from LOBSTER.
- The modeled quantity is aggregated signed volume in volume-clock or one-minute buckets, not daily returns.
- Duration-aware BOCPD/BOSD with a log-normal duration law outperformed constant-hazard BOCPD in the univariate order-flow tests.
- The log-normal duration law dominated the geometric and Pareto alternatives across assets, months, and calibration criteria.
- The multivariate BOCPDMS/BVAR extension was negative on the bivariate order-flow test, underperforming two independent univariate filters.
- Heavy-tailed innovations and short regimes made adaptive multivariate coefficients overreact to spikes.
- The paper reports no trading strategy, no transaction-cost-adjusted Sharpe, and no ETF allocation test.

## GroupA++ Fit

- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Time scale: `daily allocation with execution/advisory shadows`
- Data gap: The repository has daily OHLCV and some intraday bars, but this paper's core input is signed transaction/order-flow data. Without reliable trade signs, direct import would create a proxy risk.
- Mismatch: The paper studies high-frequency microstructure regime detection; GroupA++ latest strategy is a small ETF allocation system. The fit is strongest for execution-risk advisory, not for changing strategic target weights.

## Adoption Candidates

| candidate | status | live change | expected advantage |
|---|---|---:|---|
| `duration_aware_intraday_order_flow_changepoint_shadow` | `conditional_shadow` | `False` | Could flag execution-time flow breaks earlier than daily OHLCV indicators, especially before adding leveraged 00631L exposure or resizing the 00713/cash sleeve. |
| `lognormal_duration_prior_for_regime_monitors` | `recommended_research_only` | `False` | The paper's strongest positive result is that order-flow regimes have no single characteristic timescale; a log-normal duration prior may reduce over-fragmentation of stable periods. |
| `daily_ohlcv_proxy_order_flow_regime_gate` | `do_not_adopt` | `False` | None with current evidence; the paper's signal is defined on signed high-frequency transactions. |
| `multivariate_bocpdms_bvar_live_gate` | `reject_for_now` | `False` | Not supported by this paper: the bivariate BOCPDMS experiment underperformed two independent univariate filters, and pairwise DM tests did not establish superiority. |

## Recommendation

- Do not change latest strategy weights. If reliable Taiwan signed intraday flow becomes available, build a duration-aware univariate order-flow changepoint shadow for execution timing only.
- Keep this paper out of live target-weight logic unless Taiwan signed-flow evidence passes a separate forward-validation gate.
- Prefer the paper's positive univariate duration-aware result over its negative multivariate BOCPDMS result for any future shadow.
