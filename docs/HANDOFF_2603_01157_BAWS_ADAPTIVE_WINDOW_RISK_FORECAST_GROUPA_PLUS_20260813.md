# 2603.01157v2 BAWS Adaptive Window Risk Forecasting — GroupA+ Review

Date: 2026-08-13  
Author note: Codex 2026-08-13

## Status

Reviewed.  No code was changed in this review.

Decision: **worth a research-only shadow diagnostic**, not suitable for direct
promotion into GroupA+ active allocation.

## Source

Source PDF:

`C:\Users\isaac\Downloads\2603.01157v2.pdf`

Extracted locally with `pypdf` to:

`/tmp/2603.01157v2.txt`

Paper title:

`Adaptive Window Selection for Financial Risk Forecasting`

Authors:

Yinhuan Li, Chenxin Lyu, Ruodu Wang

arXiv:

`2603.01157v2 [q-fin.RM]`, dated 2026-05-29.

## Paper Summary

The paper proposes **BAWS**: bootstrap-based adaptive window selection.

Problem:

- VaR/ES risk forecasts depend heavily on the lookback window.
- Fixed rolling windows are brittle:
  - long windows adapt too slowly after structural breaks;
  - short windows adapt faster but have higher variance.
- Financial losses are nonstationary and often contain unknown structural breaks.

Core idea:

- At each time `t`, compare candidate lookback windows using realized scoring
  losses.
- Use a bootstrap threshold to decide whether a longer window is still
  admissible.
- Select the largest admissible window.

Important method details:

- For iid-like data, use empirical bootstrap.
- For dependent time series, use moving block bootstrap.
- The paper specifically covers nonsmooth scores:
  - VaR check loss;
  - joint VaR-ES Fissler-Ziegel score.
- Candidate windows are sparse/increasing for computation efficiency.
- Typical threshold confidence level is beta around `0.9`.
- Empirical study uses moving block bootstrap with `B=1000`, block length
  roughly `ceil(i^(1/3))`, and maximum window capped at `1000`.

## Evidence From Paper

Simulation findings:

- In discrete structural-break simulations, BAWS achieves the lowest VaR MSE,
  cumulative risk, and cumulative forecast loss across the tested settings.
- In GARCH/time-varying volatility simulation, BAWS achieves the lowest MSE,
  cumulative risk, and cumulative forecast loss among compared methods.
- BAWS reacts faster after structural breaks because it stops mixing pre-break
  observations into post-break forecasts.

Empirical findings:

- Data: S&P 500 daily losses, 2005-01-04 to 2025-10-30.
- Forecast period: 2006-12-28 to 2025-10-30.
- BAWS is compared with:
  - SAWS;
  - fixed rolling windows 250/500/750;
  - full window.
- BAWS attains the lowest average VaR-ES joint forecast loss over the full
  evaluation period and remains competitive in stress subperiods including GFC,
  COVID, and 2025 tariff episode.

## Fit With Current GroupA+

Current active strategy:

`a2118_a2111_ncf_late_bull_deleverage`

Current active knobs include:

- NCF late-bull hedge trigger;
- `risk_score_lookback_days=5`;
- fixed rolling VaR/tail features in `backtest_group_a_plus_switch_policy.py`;
- tail conformal diagnostics;
- regime-weighted conformal shadow diagnostics;
- CVaR/tail-risk diagnostics.

Relevant existing files:

- `backtest_group_a_plus_switch_policy.py`
- `group_a_plus/integrations/regime_weighted_tail_conformal.py`
- `scripts/evaluate/evaluate_group_a_plus_regime_weighted_tail_conformal_walk_forward.py`
- `scripts/run/run_ncf_daily_pipeline.py`

The paper does **not** propose a trading allocator or portfolio weighting
strategy.  It is a method for choosing risk-forecast lookback windows.

Therefore, it should not directly modify:

- golden1 target weights;
- a2118 allocation weights;
- execution plans;
- production live pointers.

## What Can Be Imported

The strongest transferable idea is:

**Adaptive risk-forecast lookback selection for GroupA+ tail-risk guards.**

Practical GroupA+ candidates:

1. **BAWS-style VaR/ES shadow for 0050 and 00631L**
   - Forecast 1d/5d loss VaR and ES.
   - Candidate windows: e.g. 63, 126, 252, 504, 756.
   - Use check loss for VaR and optionally FZ score for VaR-ES.
   - Output selected window, VaR, ES, realized breach, and forecast score.

2. **Adaptive lookback for `tail_var_breach_risk`**
   - Current tail features use fixed windows such as 20d historical VaR.
   - BAWS could select between short/medium/long calibration windows during
     regime shifts.
   - This should first be shadow-only and compared against the existing fixed
     VaR breach feature.

3. **Adaptive calibration window for conformal tail diagnostics**
   - Existing conformal / regime-weighted conformal diagnostics depend on
     calibration windows.
   - BAWS could choose calibration length when structural breaks are detected.
   - This is promising because it directly addresses a known nonstationarity
     problem.

4. **Risk-source health/advisory**
   - Daily report can show whether BAWS selects a very short window.
   - A sudden window contraction is a structural-break warning.
   - Use as warning/advisory, not automatic trading.

## What Should Not Be Imported

Do not directly wire BAWS into active trading decisions yet.

Do not:

- change `a2118.py` active weights;
- change `golden1_0531`;
- replace existing NCF late-bull trigger;
- block trades solely because BAWS selects a short window;
- use full bootstrap daily in production without runtime controls.

Reason:

- The paper validates risk forecast loss, not GroupA+ portfolio P&L.
- VaR/ES forecast improvement does not automatically imply better trading
  performance.
- Moving block bootstrap can be computationally expensive.
- GroupA+ already has multiple risk overlays; another guard may add redundant
  conservatism unless validated.

## Recommended Next Step

Implement **research-only BAWS-lite VaR/ES window shadow**.

Scope:

- No active strategy changes.
- No execution changes.
- Output JSON/MD report only.

Suggested first version:

- tickers: `0050.TW`, `00631L.TW`;
- losses: negative daily log returns;
- risk levels: 95% VaR and ES;
- candidate windows: `[63, 126, 252, 504, 756]`;
- bootstrap:
  - start with smaller `B=200` for speed;
  - optionally add moving block bootstrap with block length `ceil(k^(1/3))`;
- compare against fixed windows:
  - 63, 126, 252;
  - current fixed tail feature.

Evaluation:

- rolling walk-forward from 2020-01-01 to latest;
- metrics:
  - VaR check loss;
  - VaR breach rate;
  - ES/FZ loss if implemented;
  - severe 5d/10d drawdown hit rate;
  - whether selected window contraction leads risk events.

Promotion condition:

- This should only become a production advisory if it improves risk forecast
  quality without creating excessive false alarms.
- It should not become a hard execution blocker unless a separate portfolio
  backtest shows improved P&L / drawdown tradeoff.

## Verdict

This paper has a real, relevant advantage for GroupA+:

**adaptive lookback selection for tail-risk forecasting under structural
breaks.**

Best use:

- research-only risk diagnostic;
- future promotion-gate input for tail-risk/conformal calibration;
- possible daily warning when selected windows shrink sharply.

Not appropriate as:

- direct allocation logic;
- direct latest-strategy replacement;
- direct trading guard without shadow validation.

Final decision:

Proceed only with a BAWS-lite shadow evaluator if requested.  Do not change
GroupA+ latest strategy now.
