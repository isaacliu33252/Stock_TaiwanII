# Group A+ 00631L CED Drawdown / Serial Correlation — Handoff 2026-07-11

## Context

User referenced Goldberg & Mahmoud, "Drawdown: From Practice to Theory and
Back Again", which formalizes drawdown risk as **Conditional Expected
Drawdown (CED)** -- the average severity of drawdowns that breach a
threshold -- and notes CED is sensitive to **serial correlation** in returns
in a way plain volatility is not (a sequence of losses that trend together
compounds into a deeper drawdown than the same total variance spread across
uncorrelated up/down days). User asked three concrete questions about
00631L.TW:

1. Is future 10-trading-day max drawdown < -5%?
2. Is future 20-trading-day max drawdown < -8%?
3. Does an N-day sustained/serial-decline-type drawdown occur?

This session's prior work (Parts 1-6 of
`GROUP_A_PLUS_GOOD_BAD_VOLATILITY_AND_CHIP_TRIGGERS_HANDOFF_20260711.md`,
plus the 2026-07-10 downside-risk research in
`GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md`) was
directly relevant background, so both tests here were framed against that
existing history rather than starting cold. **Research-only; no production
weight, alert, or rule changed.**

## Relevant prior context (not re-derived, just applied)

The 2026-07-10 research line already tested a near-identical label
("future 10d 00631L max drawdown < -10%", called "Label A") as one of three
oracle-tested labels, alongside a race/first-touch label and a downside-
semivariance label. That was **the first time in this project's whole
volatility/regime-routing research history that an oracle ceiling came back
positive across all tested windows and labels**. However, every *real*
(non-oracle) classifier and rule subsequently built on similar labels --
the GradientBoosting race classifier (7 stages) and the A22_bad_vol_overlay
rule (9 more stages, later found to fail true out-of-sample validation on a
backfilled 2017-2019 panel) -- failed to translate that oracle ceiling into
actual trading edge. This gap (oracle attractive, every real model built so
far fails to capture it) was the standing, unresolved problem going into
today's questions.

## Test 1: Oracle ceiling for the user's specific new thresholds

Built `scripts/evaluate/evaluate_group_a_plus_00631l_ced_drawdown_oracle.py`,
reusing the exact oracle-simulation harness from
`evaluate_group_a_plus_00631l_downside_oracle_ceiling.py`
(`_label_max_drawdown`, `_weights_de_risked`, `_simulate_oracle_curve` --
imported, not reimplemented) with two new label definitions instead of the
original single (-10%, 10d):

- A: future 10-trading-day 00631L max drawdown < -5%
- B: future 20-trading-day 00631L max drawdown < -8%

Same perfect-foresight oracle framing as the original script: not a real
forecast, only answers "is there even a theoretical edge worth chasing."

**Result across the 4 standard windows (covid_2020/inflation_2022/
live_2024_2026/active_2025_2026):**

| Window | A (10d<-5%) ΔSharpe | B (20d<-8%) ΔSharpe |
|---|---:|---:|
| covid_2020 | +0.101 | +0.082 |
| inflation_2022 | +0.045 | -0.021 |
| live_2024_2026 | +0.288 | +0.222 |
| active_2025_2026 | +0.268 | +0.179 |

**7/8 combinations Sharpe-positive** (only inflation_2022's 20d/-8% label is
slightly negative). Label A (10d/-5%) is positive in all 4 windows, and the
magnitude is *larger* than the original -10%/10d label tested 2026-07-10 --
i.e. the tighter, more sensitive threshold the user proposed has an even
higher theoretical ceiling. Final-value deltas are mixed (active_2025_2026
shows negative Δfinal_value for both labels despite positive Sharpe --
oracle de-risking smooths volatility/drawdown in that window but at some
cost to total dollar return, a pattern already seen in prior oracle/rule
tests this project has run).

**This reconfirms, not newly discovers**, the 2026-07-10 finding: the
oracle ceiling for downside-specific 00631L de-risking is real and
attractive. It does not by itself address the standing problem (no real
model has captured it yet).

## Test 2: Serial correlation predictability — the paper's genuinely new angle

Built
`scripts/evaluate/evaluate_00631l_serial_correlation_drawdown_predictability.py`.
None of the existing 00631L downside-risk features (race classifier's
price-based set: ma_gap/drawdown/multi-period returns/realized_vol_ratio/
downside_semivar/up-day fraction, later + 19 chip features + HAR-RV h10)
explicitly measure serial correlation -- this is the one piece of the CED
paper's argument not already covered by prior work, so it was tested
standalone (same Newey-West/Bartlett-HAC regression style used throughout
this session) before considering whether to feed it into the existing
(already-paused) classifier.

Two backward-looking, no-look-ahead features on 00631L.TW daily returns:
- `autocorr_20d`: rolling 20-day lag-1 autocorrelation of daily returns.
- `down_streak`: current consecutive-negative-return-day run length.

Each regressed (linear probability model -- valid OLS-based significance
test even for a 0/1 dependent variable) against the same two CED labels
from Test 1, lag = horizon-1 for the HAC kernel, full history 2015-01-05 to
2026-07-09 (n=2784 for both labels).

**Result: null, all 4 combinations p>0.18:**

| Label | autocorr_20d p | down_streak p |
|---|---:|---:|
| A (10d<-5%) | 0.341 | 0.187 |
| B (20d<-8%) | 0.872 | 0.972 |

Neither serial-correlation feature has standalone predictive power for
either drawdown-breach label on 00631L.

## Combined interpretation

This session's two tests reproduce the exact pattern established
2026-07-10: **the oracle ceiling is real and, with these tighter
thresholds, even larger than before -- but the specific new predictive
angle tested (serial correlation, the CED paper's stated distinguishing
feature over plain volatility) does not close the gap between that ceiling
and any real forecast.** This is not "haven't found the right feature yet"
in a vague sense -- it is now the *second* substantively different
candidate signal family (after the extensive price/vol/chip feature set
from the 07-10 race classifier) to fail to capture a ceiling that is
demonstrably there. The user explicitly chose to pause here rather than
proceed to building a classifier/rule on these labels, consistent with this
project's standing caution against continuing to iterate without a
qualitatively new reason to expect a different outcome
(`feedback_overfitting_fixed_window_tuning`, `feedback_strategy_promotion_caution`).

## Files touched this session

**New scripts:**
- `scripts/evaluate/evaluate_group_a_plus_00631l_ced_drawdown_oracle.py`
- `scripts/evaluate/evaluate_00631l_serial_correlation_drawdown_predictability.py`

**New result artifacts:**
- `results/group_a_plus_00631l_ced_drawdown_oracle_latest.json`
- `results/00631l_serial_correlation_drawdown_predictability_latest.json`

**Production impact: none.** Both scripts are research-only; neither is
wired into any live signal, gate, or the A22/race-classifier lines (which
remain paused per their own prior conclusions).

## What's open for the future

1. **Do not** re-run the oracle ceiling test with yet another threshold
   combination expecting a different qualitative answer -- the ceiling
   being positive and non-trivial is now established across two independent
   threshold sets (original -10%/10d from 07-10, and this session's
   -5%/10d and -8%/20d). That part of the question is answered.
2. **Do not** assume serial correlation is a dead end for *all* possible
   operationalizations -- only `autocorr_20d` (20-day lag-1) and
   `down_streak` (current streak length) were tested. Different window
   lengths, higher-order autocorrelation, or a genuinely CED-style
   *realized conditional expected drawdown itself* (rather than a
   correlation proxy for it) as a rolling feature were not tried. Any
   future attempt should have a specific, articulable reason to expect a
   different result from these two, not just "try a different window."
3. The core standing problem from 2026-07-10 remains unresolved: two
   different feature families (price/vol/chip; serial correlation) have now
   both failed to capture a real, demonstrable oracle ceiling for 00631L
   downside-specific de-risking. Whether this reflects a fundamental limit
   (the label's true drivers are not observable ex-ante with the data this
   project has) or simply more feature/model exploration needed is an open
   question this session did not resolve.

Related: `project_00631l_downside_risk_forecast_20260710.md` (origin of the
oracle-ceiling methodology and the race-classifier/A22 history),
`project_good_bad_volatility_and_chip_triggers_20260711.md` (same-day prior
work this session built on), `feedback_overfitting_fixed_window_tuning.md`,
`feedback_strategy_promotion_caution.md`.
