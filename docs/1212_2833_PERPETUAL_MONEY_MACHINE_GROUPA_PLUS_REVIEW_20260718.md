# 1212.2833 Perpetual Money Machine GroupA+ Review（2026-07-18）

## Source

- File: `C:\Users\isaac\Downloads\1212.2833.pdf`
- Title: `The Illusion of the Perpetual Money Machine`
- Authors: Didier Sornette and Peter Cauwels
- Date in paper: 2012-10-27
- Review target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 execution context

## Paper Summary

This white paper argues that the post-1980s financial system shifted from
productivity-led growth toward debt-led and finance-led growth. The authors
connect this shift to repeated bubbles and crashes, then highlight three future
sources of instability:

- ETF financialization and stronger cross-asset coupling.
- Algorithmic / high-frequency trading and rising market endogeneity.
- Public-debt trajectories and macro fragility.

The investment section recommends scenario thinking, capital preservation, and
a `time-at-risk` approach that monitors bubbles and unstable regimes instead of
assuming stationary market risk.

## Useful Ideas For GroupA+

### 1. Time-At-Risk Governance

The most relevant idea is not a new alpha model. It is a regime-governance layer:

- track how long the market stays in a fragile / bubble-like state;
- reduce confidence in leveraged exposure when instability persists;
- evaluate scenarios and ex-post forecast quality rather than relying on one
  point forecast.

GroupA+ already has partial equivalents:

- crash-window review;
- volatility gate;
- compounding regime;
- cross-market shock diagnostics;
- deployment consistency review;
- FinStressTS counterfactual stress harness.

Import decision: useful as a research-only umbrella concept, not as a live
weight-change trigger.

### 2. ETF Coupling / Network Fragility Check

The ETF section is directly relevant because GroupA+ uses leveraged and inverse
ETF instruments:

- `00631L.TW`
- `00632R.TW`

The paper's useful warning is that ETFs can increase cross-asset coupling and
make diversification weaker during stress. For GroupA+, this supports stricter
checks before adding `00631L`:

- rolling correlation spike between `0050`, `00631L`, `00632R`;
- SOXX / QQQ / TSM / TWII / 2330 coupling;
- VIX and USD/TWD shock state;
- volume z-score and volatility clustering;
- margin / chip-pressure state when data is available.

Import decision: can be added as a shadow `ETF coupling / systemic fragility`
diagnostic. Do not use it alone for trade execution.

### 3. Reflexivity / Endogenous-Risk Proxy

The paper notes that machine-driven and self-excited trading can amplify
short-horizon crashes. GroupA+ does not currently have quote-level or intraday
order-book data, so a true reflexivity estimator is not available.

Practical proxy candidates using current daily data:

- abnormal turnover / volume z-score;
- realized volatility clustering;
- same-direction cross-asset moves;
- sudden gap between US semiconductors and Taiwan ETFs;
- intraday crash-window flags if intraday data is later added.

Import decision: keep as a diagnostic proxy only. Do not claim full HFT /
reflexivity detection without intraday or order-book data.

### 4. Scenario Discipline And Ex-Post Review

The paper supports the existing direction of GroupA+:

- avoid one-model auto-execution;
- require scenario stress checks;
- preserve capital when signals diverge;
- record rejected actions and review forecast quality after the event.

This aligns with the current `manual_review_required` posture.

## Not Imported

The following are not suitable for live GroupA+ import now:

- full LPPL / bubble model as a trading signal;
- macro-debt discretionary market timing;
- commodity / real-asset allocation changes outside the GroupA+ ETF universe;
- direct `00631L` add or `00632R` hedge from this paper;
- any parameter copied from a 2012 global macro white paper into Taiwan ETFs.

Reason: the paper is conceptual and macro/systemic. It does not provide a
validated Taiwan ETF allocation rule, transaction-cost model, or 2026 local
market calibration.

## Latest Strategy Decision

Live strategy remains unchanged:

- Strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Runner: `group_a_plus.runners.a2118`
- Reference target:
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - `00632R.TW = 0%`
  - `00679B.TWO = 0%`
  - cash = `30%`

For the 2026-07-20 estimate / execution context:

- no auto-rebalance;
- no new `00631L` add;
- keep Golden1_0531 unchanged;
- keep existing guards active:
  - volatility gate;
  - compounding regime;
  - deployment consistency review;
  - manual confirmation requirement.

## Recommended Next Step

Add a research-only `systemic_bubble_time_at_risk_review` artifact if we want to
operationalize the useful parts:

- inputs:
  - `0050`, `00631L`, `00632R`, `2330`, TWII;
  - SOXX / QQQ / TSM;
  - VIX and USD/TWD;
  - volume, realized volatility, rolling correlation;
  - margin / chip data when available.
- outputs:
  - `time_at_risk_state`;
  - `etf_coupling_state`;
  - `reflexivity_proxy_state`;
  - `allow_00631l_add`;
  - `manual_review_reasons`.
- current implementation note:
  - 2026-07-18 update: `2330.TW` is read from `external_market_ohlcv`
    (`provider = yfinance`) when it is not present in the main `ohlcv` table,
    so `2330_0050_corr_60d` is now populated in the daily diagnostic.
- promotion rule:
  - research-only until it has enough out-of-sample history and improves
    crash-window / rebalance decisions versus current guards.

## Conclusion

There are useful governance ideas to import, mainly `time-at-risk`, ETF-coupling
fragility, reflexivity proxy, and scenario discipline.

There is no direct live trading edge to import into GroupA+ now. The latest
strategy and Golden1_0531 should remain unchanged for 2026-07-20.
