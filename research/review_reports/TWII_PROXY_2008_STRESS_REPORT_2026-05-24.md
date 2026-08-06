# TWII Proxy 2008 Stress Report

Date: 2026-05-24

## Scope

This report summarizes two proxy stress tests run over the Taiwan crisis window `2007-07-02` to `2010-12-31`:

- `0050` single-asset proxy backtest:
  `results/backtest_0050_twii_proxy_20070701_20101231_20260524_170331.json`
- `Group A` synthetic triplet proxy stress test:
  `results/group_a_twii_proxy_2008_20070701_20101231_20260524_165946.json`

The real ETF history in this workspace does not cover `2008`, so the tests use `TWII` as the market proxy:

- `0050.TW` proxy = `1x TWII` daily returns
- `00631L.TW` proxy = `2x TWII` daily returns
- `00632R.TW` proxy = `-1x TWII` daily returns

Scripts used:

- `twii_proxy_utils.py`
- `backtest_0050_twii_proxy_2008.py`
- `backtest_group_a_twii_proxy_2008.py`

## Headline Findings

- `Group A` held up better than the simple `0050` proxy tests and materially better than static `50/50 0050+00631L`.
- `Group A` still experienced a severe crisis drawdown at `-54.18%`, but it recovered its prior peak by `2009-09-18`.
- The `0050` no-DCA proxy runs did not fully recover to their pre-crisis peak by `2010-12-31`.
- Because `Group A` includes `0050` monthly DCA, the fairest baseline is not the no-DCA `0050` hold curve. Under the same `1.21M` total contributions, `Group A` finished at `1.4396M` versus `1.2707M` for `0050 hold + same DCA schedule`.

## Method Notes

- `Group A` used the current canonical payload:
  `results/group_a_runtime_payload_opt_20260524.json`
- The proxy run preserved current runtime logic, including:
  `PVA`, `DCA day = 20`, inverse hedge logic, and the current exposure caps.
- Historical `LLM sentiment` inputs were unavailable for `2008`, so the shared LLM columns were zero-filled. In practice this means the sentiment gate stayed neutral and this test mainly reflects price-regime logic rather than news sentiment.
- `Group A` result metrics based on `initial_cash = 1,000,000` are not directly comparable to no-DCA benchmarks because the strategy also added `210,000` of DCA capital over the test.

## Summary Table

| Strategy | Cash Flow Basis | Final Value | Net Profit | Contribution Return | Sharpe | Max DD | Trough Date | Recovery Date |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Group A RL | `1,000,000 + 210,000` DCA | `1,439,564.66` | `229,564.66` | `18.97%` | `0.454` | `-54.18%` | `2008-11-20` | `2009-09-18` |
| 0050 Hold + same DCA | `1,000,000 + 210,000` DCA | `1,270,714.37` | `60,714.37` | `5.02%` | `0.319` | `-54.94%` | `2008-11-20` | `2010-01-15` |
| 0050 RL | `1,000,000` only | `1,016,593.26` | `16,593.26` | `1.66%` | `0.067` | `-57.00%` | `2008-11-20` | not recovered by `2010-12-31` |
| 0050 Hold | `1,000,000` only | `1,003,692.60` | `3,692.60` | `0.37%` | `0.058` | `-58.31%` | `2008-11-20` | not recovered by `2010-12-31` |
| Group A static `50/50` | `1,000,000` only | `899,192.04` | `-100,807.96` | `-10.08%` | `0.044` | `-71.88%` | `2008-11-20` | not recovered by `2010-12-31` |
| Group A equal-weight | `1,000,000` only | `861,996.57` | `-138,003.43` | `-13.80%` | `-0.529` | `-28.60%` | `2009-06-18` | not recovered by `2010-12-31` |

Notes:

- `Contribution Return` is shown on total invested capital and is the fairest comparison for `Group A` because of DCA.
- `0050 hold + same DCA` was reconstructed from the actual `Group A` DCA purchase history so the cash-flow comparison uses the same contribution timing.

## Crisis Window Comparison

### Lehman to `2009-03-31`

This isolates the sharpest part of the global crisis:

| Strategy | Return |
| --- | ---: |
| Group A RL | `-2.11%` |
| 0050 Hold + same DCA | `-8.67%` |
| 0050 RL | `-13.77%` |
| 0050 Hold | `-13.91%` |
| Group A static `50/50` | `-20.44%` |
| 00631L hold | `-31.06%` |
| 00632R hold | `+8.13%` |

Interpretation:

- `Group A` was not crash-proof, but it clearly reduced the deep crisis loss path relative to pure `0050` exposure and especially relative to the leveraged blend.
- The inverse-only proxy helped in the core crash window, but it was not a good full-period holding strategy.

### Calendar Year View

| Strategy | 2008 Return | 2009 Return |
| --- | ---: | ---: |
| Group A RL | `-42.95%` | `+117.95%` |
| 0050 Hold + same DCA | `-41.78%` | `+92.28%` |
| 0050 RL | `-45.13%` | `+77.36%` |
| 0050 Hold | `-46.03%` | `+78.34%` |
| Group A static `50/50` | `-59.45%` | `+115.46%` |
| Group A equal-weight | `-14.82%` | `+2.52%` |

Interpretation:

- `Group A` still lost heavily in `2008`, but it recovered faster than the plain `0050` proxy and converted the `2009` rebound more efficiently.
- The static `50/50` mix had strong upside in `2009` but paid for it with much worse crash damage in `2008`.

## Group A Internal Behavior

From the stored stress-test result:

- Trades: `147`
- Estimated fees: `57,624.65`
- DCA purchases: `42`
- DCA total contributions: `210,000`
- PVA overlay activations: `90`
- S/J/M counts: `S=659`, `J=120`, `M=93`
- Final weights on `2010-12-31`: `0050 74.6%`, `00631L 25.4%`, `00632R 0.0%`
- Total dividend credited: `0.0` in proxy mode

Interpretation:

- The strategy spent most of the path in `S` state, which is consistent with a prolonged stressed regime.
- It did not end the window in a defensive inverse posture; by the end of `2010`, the proxy run had re-risked into `0050 + 00631L`.

## What This Means

- If the goal is `2008-style downside rehearsal`, current `Group A` logic is directionally useful. It did better than simple `0050` exposure and much better than a static leveraged blend.
- If the goal is `capital preservation`, the result is still harsh. A `-54%` drawdown is not a defensive outcome in absolute terms.
- The most honest read is:
  current `Group A` improved crisis navigation, but it did not solve crash risk.

## Limits

- This is not real `0050 / 00631L / 00632R` historical execution data.
- Leveraged and inverse ETF behavior is approximated from daily `TWII` returns and does not include real tracking error, financing drag, or fund-specific path decay.
- `LLM sentiment` was effectively neutralized because `2008` daily sentiment features were not available.
- Stored static benchmarks in the raw JSON are no-DCA. This report adds a separate `0050 hold + same DCA schedule` baseline to make the main comparison fairer.

## Recommendation

- Keep this report as a `stress-test appendix`, not as a production performance claim.
- If you want a stronger crisis study next, the most useful extension is:
  build a `same-cash-flow benchmark pack` for `0050`, `blend50`, and `equal-weight`, then compare all of them against `Group A` under identical DCA rules.
