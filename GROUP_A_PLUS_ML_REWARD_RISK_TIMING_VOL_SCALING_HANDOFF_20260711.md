# Group A+ ML Reward-Risk Timing / Continuous Vol-Scaling — Handoff 2026-07-11

## Context

User provided Pinelis & Ruppert (2020, arXiv:2003.00656), "Machine Learning
Portfolio Allocation", and asked what could be imported into Group A+.
Same-day follow-on to the extensive downside/asymmetric-volatility research
already run (`GROUP_A_PLUS_GOOD_BAD_VOLATILITY_AND_CHIP_TRIGGERS_HANDOFF_20260711.md`,
`GROUP_A_PLUS_00631L_CED_DRAWDOWN_SERIAL_CORRELATION_HANDOFF_20260711.md`).
**Research-only; no production weight, alert, or rule changed.**

## What the paper does

Random Forest models forecast, monthly, both (1) expected excess market
return ("reward") and (2) prevailing volatility ("risk") using standard
Goyal-Welch macro predictors plus a payout-yield variant. Portfolio weight
on the market index follows the classic Merton myopic-optimal formula:

```
w*_t = E[excess return | F_t-1] / (gamma_bar * Var[return | F_t-1])
```

On 1989-2019 US holdout data: Sharpe ratio improves from 0.57 (buy-and-hold)
to 0.73 (RF reward-risk timing), annualized alpha 3.37%, survives realistic
transaction costs and a 150% leverage cap.

## Key observation before testing anything: the paper's own numbers already match this session's pattern

| Task | Paper's best out-of-sample R^2 |
|---|---:|
| Excess return forecasting (Random Forest) | 0.52% (only positive model; essentially noise) |
| Volatility forecasting (Linear Model) | 54.69% |

The paper's own results show return forecasting barely works even with ML
and 11 macro predictors on 90+ years of US data, while volatility
forecasting works well — the exact same asymmetry found repeatedly this
session on 0050.TW/00631L.TW (Wang & Yan downside-vol, GNHAR, RSJ proxy, TXO
positioning: all null on return predictability). This meant the paper's
ML-forecasting machinery itself was not worth transplanting (weak
return-forecast signal, and this project already has a better-validated
volatility forecaster than the paper's simple linear/RF model — the HAR-RV
model in `group_a_plus/integrations/volatility_forecast.py` from
2026-07-10, QLIKE-tested against a naive baseline).

## The one genuinely different, testable idea: continuous inverse-vol position sizing

The paper's **"Base" strategy** — no ML at all, just `w_t = c / sigma_t^2`
using historical mean return and lagged realized volatility — *already*
beats buy-and-hold (Sharpe 0.57 -> 0.67) using volatility-timing alone, with
**no return-forecasting skill required**. This is a different, weaker, and
more testable claim than everything tested this session so far: not "does
volatility predict returns" (tested repeatedly, null), but "does
continuously scaling position size inversely to (well-forecastable, per
this project's own HAR-RV work) volatility improve realized Sharpe,
regardless of return predictability."

Mechanically the same idea as Moreira & Muir (2017) volatility-managed
portfolios and `garch_regime_shadow.py`'s `volatility_gate_reference` — but
that gate is discrete/bucket-based (shadow-only, never continuous), and
every prior downside-vol test in this project asked the return-timing
question, never this pure risk-timing question.

## Test built and run

`scripts/evaluate/evaluate_0050_continuous_vol_scaled_weight.py`:
`w_t = clip(c / sigma_t^2, 0, 1.5)`, `sigma_t` = trailing 21-trading-day
realized volatility (annualized), `c` calibrated so mean weight over the
sample = 1.0 (matches buy-and-hold's average exposure, same logic as the
paper's own c-calibration). Compared against plain buy-and-hold, gross and
net of this project's standard commission/slippage/tax assumptions.

**First pass (daily rebalance) was a methodology mistake, caught and
fixed**: rebalancing every day off a continuously-updating realized-vol
estimate generated enormous turnover -- $375,269 in transaction costs on a
$1M initial position over 13 years (37.5% of principal), because the daily
vol estimate is noisy and the weight chases that noise. This does not match
the paper's actual design (monthly rebalance, vol estimated once per
month). Rebuilt with `--monthly-rebalance` (now the default): weight is
set once per calendar month from that month's first trading day's trailing
vol estimate and held fixed intra-month, matching the paper's methodology.
Transaction cost dropped to a reasonable $166,330 (0050) / $238,737
(00631L) over the same horizon.

## Result: negative on both tickers, gross and net of costs

| Ticker | Strategy | Sharpe (gross) | Sharpe (net) | Max DD | Final value |
|---|---|---:|---:|---:|---:|
| 0050.TW (2013-2026) | buy-and-hold | 0.964 | 0.963 | -36.4% | 6,520,801 |
| 0050.TW (2013-2026) | vol-scaled | 0.787 | 0.717 | -25.8% | 3,438,965 |
| 00631L.TW (2015-2026) | buy-and-hold | 1.067 | 1.067 | -55.1% | 41,431,515 |
| 00631L.TW (2015-2026) | vol-scaled | 0.804 | 0.770 | -50.5% | 8,711,499 |

Vol-scaling clearly reduces max drawdown on both tickers (0050:
-36.4%->-25.8%, 00631L: -55.1%->-50.5%), but Sharpe and total return are
both meaningfully worse, gross and net of costs, on both tickers. Not a
marginal or mixed result -- four independent comparisons (2 tickers x
gross/net) all point the same direction.

## Interpretation

Same structural cause already identified multiple times in this project
(`garch_regime_shadow.py`'s own code comment: "high vol is not equivalent
to downside risk, especially inside an already-good trend";
`GARCH_SPECIALIST_ROUTING` line; A22's OOS failure): 0050.TW (2013-2026) and
00631L.TW (2015-2026) spent most of their sample in a strong, fast-recovering
bull regime. Volatility-based de-risking necessarily cuts exposure during
the sharpest drawdowns -- which in this specific sample were consistently
followed by strong rebounds -- so the opportunity cost of missing the
recovery exceeds the value of the drawdown protection. This is the same
mechanism, not a coincidence, as why every de-risking/regime-gate mechanism
tested in this project (A22_bad_vol_overlay, GARCH specialist routing,
today's oracle/serial-correlation tests) struggles the same way on these
same two tickers over this same broad period.

**Decision: this specific mechanism (continuous inverse-vol position sizing
on 0050/00631L, matching the paper's own "Base" strategy design) does not
work on this data and should not be built into any overlay.**

## Files touched this session

**New script:**
- `scripts/evaluate/evaluate_0050_continuous_vol_scaled_weight.py`

**New result artifacts:**
- `results/0050_continuous_vol_scaled_weight_latest.json` (first-pass daily-rebalance run, kept for the record of the methodology mistake)
- `results/0050_continuous_vol_scaled_weight_monthly_latest.json` (corrected monthly-rebalance run, 0050.TW)
- `results/00631l_continuous_vol_scaled_weight_monthly_latest.json` (corrected monthly-rebalance run, 00631L.TW)

**Production impact: none.** Purely a standalone research script; not wired
into any live signal, gate, or the golden1/a2118 pipeline.

## What's open for the future

1. This closes the "continuous vol-scaling for realized Sharpe improvement"
   question on 0050/00631L specifically, using the paper's own base-case
   design (21d trailing realized vol, monthly rebalance, weight capped
   [0, 1.5]). A materially different vol estimator (e.g. the already-
   validated HAR-RV forecast instead of trailing realized vol) or a
   different cap/rebalance frequency was not tried and could in principle
   give a different answer, but there is no specific reason yet to expect
   one given how consistently this project's de-risking mechanisms fail on
   these same tickers for the same underlying reason (strong, fast-
   recovering bull regime dominates the sample).
2. The paper's ML return-forecasting machinery (Random Forest on Goyal-
   Welch macro variables) was assessed but not tested -- its own R^2 of
   0.52% out-of-sample was judged not worth transplanting given this
   session's repeated confirmation that return-timing is essentially
   unforecastable on these tickers with the methods tried so far. If
   revisited, it would need Taiwan-specific macro predictors (no direct
   analog surfaced for Goyal-Welch's US variables like net equity
   expansion or the corporate bond rate) and a specific reason to expect
   better luck than the ~8 other return-predictability angles already
   closed this project (Wang & Yan, GNHAR, RSJ proxy, TXO positioning,
   NCF's own return-timing signal, etc.).

Related: `GROUP_A_PLUS_GOOD_BAD_VOLATILITY_AND_CHIP_TRIGGERS_HANDOFF_20260711.md`,
`GROUP_A_PLUS_00631L_CED_DRAWDOWN_SERIAL_CORRELATION_HANDOFF_20260711.md`,
`project_garch_specialist_routing_2008_20260705.md`,
`feedback_strategy_promotion_caution.md`.
