# GroupA+ Signal/Overlay Validation Checklist - 2026-07-23

## Status

**Adopted as a standing convention, effective today.** Not a strategy
change -- this is a process checklist for how future shadow-candidate
signals and overlays should be validated before a promotion decision is
made. No existing script, test, or production file was modified to
enforce this; it is a documented practice for whoever runs the next
evaluation.

## Origin

Distilled from reading arXiv:2605.20636v2 ("Continuous Timing Signals for
Growth-Defensive Style Allocation") during the same 2026-07-23 session as
`GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md` (see that
file's final subsection for the full paper review -- most of the paper's
actual strategy logic was rejected as not applicable; this checklist is
the one piece judged worth adopting). The paper's own validation design
was more systematic than what most `scripts/evaluate/*.py` files in this
repo currently do on an ad hoc, per-script basis.

## The checklist

When evaluating a new shadow candidate (new signal, new overlay, new
threshold, new parameter set) before writing a promotion/rejection
decision, report all four of the following -- not just one aligned
backtest window:

1. **Walk-forward expanding.** Initial training window, then re-evaluate
   on successive out-of-sample test blocks using all history available
   before each block. This project already has NCF panels split into
   tuning windows (e.g. `live_2024_2026`, `active_2025_2026`) and a
   genuine out-of-sample panel (`results/ncf_00631l_panel_backfill_
   2017_2019_20260710.csv`, tagged `out_of_sample` in ~16 existing
   evaluate scripts) -- use the latter as the walk-forward test bed, not
   just a second look at the same 2025-2026 window the candidate was
   tuned on.
2. **Walk-forward rolling** (fixed-length lookback, not all history) as a
   second OOS variant -- catches cases where a candidate only works
   because of accumulated history, not genuine recent-regime robustness.
3. **A crisis-independence check**, not just a generic OOS split.
   Specifically: if any part of the candidate's edge comes from a single
   historical stress episode, re-run validation with that episode
   excluded (or isolated) and confirm the conclusion doesn't flip. This
   project already has real crisis-fold infrastructure for exactly this
   purpose -- the 2008/2011/2015/2018/2020 five-crisis backtest data
   (see `GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md`'s
   `prepare_2015_china_crash_data_20260706.py` /
   `prepare_2018_trade_war_twii_proxy_data_20260706.py` and the existing
   2008 TWII proxy) -- use it as the "post-crisis" analogue instead of
   building a new one from scratch each time.
4. **A transaction-cost / parameter-assumption sensitivity sweep**, not a
   single fixed assumption. At minimum, re-run the candidate's headline
   metrics at a couple of different cost/discount levels bracketing the
   plausible real range. Precedent from this same session: Fable
   direction 7 (`project_a2118_remaining_fable_directions_5_8_10_
   20260723` memory) swept `commission_discount` from 1.0 to 0.10 and
   found <0.4% final-value impact for a2118 specifically (low turnover)
   -- but that finding is specific to a2118's turnover profile and
   should not be assumed to generalize to every future candidate,
   especially higher-turnover ones (e.g. anything resembling the live
   NCF continuous overlay from Finding 2 of the sibling handoff, which
   rebalances far more often).

5. **Backtest/live weight-interface consistency**, added 2026-07-24 from
   arXiv:2603.21330 ("FinRL-X"): before citing a2118's headline Sharpe /
   annual-return numbers as justification for any promotion, revert, or
   "keep as-is" decision, also run
   `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py` and
   report the overlay-inclusive numbers alongside the plain `run_a2118()`
   numbers. This is the standing fix for the exact gap Finding 2 of the
   sibling Fable-audit handoff found: `a2118.py`'s backtest never called
   the same NCF-overlay function `daily_signal.py`'s live path calls, so
   its headline numbers were never actually produced by the code that
   runs live. The script already reuses the real production functions
   (not a reimplementation) -- see its own docstring for exactly which
   overlay layers it includes (live NCF continuous downside overlay; the
   TSMC weakness trim only with `--include-tsmc-trim`, since that one is
   confirmed dead code, not live) and which it deliberately excludes
   (`_apply_bearish_high_risk_trim`, which a2118.py's own
   `backtest_live_discrepancy` field already documents as not
   historically reconstructable). This does not require refactoring
   `run_a2118()` itself -- that was scoped as a larger, separate
   architectural task and deliberately not started (see the sibling
   handoff's FinRL-X subsection for why: `run_a2118()` has too many
   existing callers/tests to safely restructure its simulation engine
   without a dedicated session for it).

6. **Incremental-OOS-admission for any new signal/interaction term**, added
   2026-07-25 from arXiv:2607.06117v1 ("Relief-Gated Relative Rotation for
   QQQ-DIA Allocation", see
   `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`). A new
   candidate signal clearing its own standalone statistical/IC screen
   (correct sign, real Spearman IC vs. forward return/drawdown) is
   **necessary but not sufficient** for adding it to a live blended
   signal. Before adding any new term's weight above zero in a shadow
   candidate's default config, also show that blending it into the
   existing (simpler) base configuration improves backtest Sharpe/return
   across at least two of the multi-window checks already required by
   items 1-4 above -- not just that the term is statistically real in
   isolation. This is not a hypothetical concern: `GROUP_A_PLUS_A2119_
   CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`'s 2026-07-25
   addendum #7 found exactly this failure mode by hand a few hours before
   this rule was written down -- `growth_crowding` had a correctly-signed,
   statistically real standalone IC, unlike this project's own earlier-
   rejected `rate_stress`/`tsmc_crowding`, yet blending it into the tilt
   made backtest Sharpe/return worse in every window that mattered once
   the simpler VIX-only base was already present. RGRR's paper shows the
   same pattern at scale (many interaction terms with HAC |t| > 5-7 but
   negative incremental OOS Sharpe once a simpler base is already
   present) and formalizes the fix as a second admission gate specifically
   for higher-order/interaction terms. Applies to any new component added
   to an existing shadow candidate's signal mix, not just brand-new
   candidates from scratch.

7. **A worst-case-perturbation robustness check for any hard threshold gate**,
   added 2026-07-26 from arXiv:2601.04062v3 ("Smart Predict-then-Optimize
   Paradigm for Portfolio Optimization in Real Markets"). That paper's
   RobustSPO variant trains decisions to survive worst-case perturbations of
   the predicted signal rather than trusting a point estimate, and shows this
   materially improves crisis-period decision quality -- its literal
   SPO+/PyEPO gradient method does not transfer here (this project has no
   differentiable optimization layer), but the diagnostic idea does: any gate
   built on a hard integer threshold against a composite score assembled from
   independent sub-indicators (e.g. `total_risk_score` = 12 chip + 2
   derivative binary sub-indicators, see `_regime_features` in
   `backtest_group_a_plus_switch_policy.py`) has a natural discrete
   perturbation set -- one sub-indicator flipping moves the score by exactly
   1. Before trusting a new/changed threshold's historical trigger count as
   evidence of a working gate, run
   `scripts/evaluate/evaluate_total_risk_score_gate_robustness.py` (or the
   same margin-to-boundary / Monte-Carlo-flip-rate / forward-return-regret-
   proxy pattern applied to the relevant score) and report: what fraction of
   historical fires sat at the exact threshold (one flip from not firing),
   the resulting decision-flip probability under plausible sub-indicator
   noise, and whether marginal fires actually carry a different forward-
   return signal than non-fires. **Also check the sub-indicators' own data-
   coverage history first** (the script's `_yearly_score_ceiling_report`) --
   `total_risk_score`'s 14 sub-indicators were onboarded in phases as their
   source tables came online (several, including dealer_futures_data/
   dealer_options_data/day_trading_data/securities_lending_data/foreign_
   shareholding_data, only exist from 2025-01 onward), so the score's
   practical ceiling rose over time; a naive "N years of history, M fires"
   framing can badly overstate the usable sample if the threshold was
   structurally unreachable before some sub-indicators existed. First run
   (2026-07-26) on the existing `total_risk_score >= 9` gate in
   `_apply_bearish_high_risk_trim`, corrected after this exact mistake was
   caught mid-session: with 0050.TW price data extended back to its full
   2009-01-02 history, the yearly max/mean table shows the score never
   exceeded 2 before 2020 and only reached 7-8 by 2021-2022 -- all 21
   historical fires (13 episodes) of the >=9 threshold fall in 2025-2026,
   the only window with all 14 sub-indicators live, not spread over "10
   years" as first (incorrectly) reported. Within that genuinely-usable
   ~1.5-year window, 81% of the 13 episodes sat exactly at the threshold
   with a 51% simulated decision-flip rate, and no clear forward-return
   separation between marginal fires and non-fires -- flagged as a red flag
   worth tracking, not acted on, since only 17 marginal-fire days exist
   (too few to distinguish a real effect from noise either way, and now
   an even shorter usable window than first thought makes that more true,
   not less). A follow-up test of requiring 2-3 consecutive days above
   threshold before firing reduced the flip rate away from the boundary but
   cut the already-rare episode count further (13 -> 5 -> 3) without
   resolving the forward-return ambiguity -- concluded not worth adopting on
   this evidence; recorded as a finding, not a threshold change.

   2026-07-26 follow-up: ran the same check against the other three
   production `total_risk_score` thresholds (6, 7, 8) for a complete
   picture. All four show substantial same-day decision-flip risk at the
   boundary (27-51%), so fragility at margin=0 is not unique to the >=9
   gate. But the forward-return regret proxy splits cleanly by direction:
   `trough_nowcast`'s >=8 threshold (a bottom-detection/bullish-reversal
   gate) shows a real, large signal even at its marginal fires (fwd_20d
   +6.0% vs. +1.3% baseline) -- this one looks genuinely validated, not
   fragile in the way that matters. The three defensive/bearish-oriented
   thresholds (6, 7, 9) all show the opposite pattern: marginal fires carry
   no meaningfully worse forward return than non-fires. This is one pattern
   confirmed three independent times, not three isolated findings -- still
   not acted on (small samples, and this diagnostic tests `total_risk_score`
   in isolation without the other co-conditions -- drawdown, ma_gap,
   signal_alignment direction -- production actually combines it with), but
   raises the flag from "one gate's marginal fires look weak" to "the
   defensive-direction gates on this score generally do, while the
   reversal-direction one doesn't." Worth revisiting once more real crisis
   events accumulate data, not worth further code-side investigation right
   now.

8. **A base-rate/mean-bias check via conditional breakdown by realized
   winning side**, added 2026-08-09. Whenever a new candidate's evidence
   includes any directional-accuracy/hit-rate/win-rate style metric (not a
   continuous R²/Sharpe/return metric), also split that same metric by
   which side actually won that day/period and report both halves
   separately. In a persistently-trending sample (this project's
   2019-2026 Taiwan bull-market backtest window), an aggregate hit rate
   that looks statistically significant can be almost entirely a base-rate
   artifact -- the signal is reading off the sample's own class imbalance
   (predicting the majority-trend side most of the time) rather than
   showing genuine bidirectional predictive skill, and this is invisible
   in the aggregate number alone. Not hypothetical: this exact check had
   to be independently rediscovered twice in the same 2026-08-09 session
   before being written down here. `scripts/evaluate/evaluate_cross_market_lead_lag_relative_return_shadow.py`
   found a surface "53% directional accuracy" was actually 84% accurate
   when the historically-favored side won vs. only 13% when the other side
   won (`docs/CROSS_MARKET_LEAD_LAG_RELATIVE_RETURN_GROUPA_PLUS_20260809.md`).
   Independently, `scripts/evaluate/evaluate_adaptive_window_hit_rate_comparison.py`
   found a 252-day window's "statistically significant" 56.4% hit rate
   (z=5.0) was actually 88.1% vs. 13.4% once split by realized winner,
   because that window's signal was positive (predicting the same side) on
   87.4% of all days in the sample -- reading off the multi-year uptrend,
   not forecasting anything
   (`docs/ADAPTIVE_LOOKBACK_NARROW_LEAD_GROUPA_PLUS_20260809.md`). Applies
   to any candidate reporting a hit-rate/directional-accuracy style metric
   as evidence, in addition to (not instead of) items 1-4's walk-forward/
   crisis-independence/cost-sensitivity checks -- a signal can pass this
   check and still fail those, or vice versa.

9. **A crash-window conditional check, separate from the mean-alpha
   regression**, added 2026-08-11 from arXiv:2607.18001 ("AlphaZeroBeta:
   Deep Reinforcement Learning for Market-Neutral Portfolios"), whose
   factor-attribution methodology (regress realized returns on
   market/size/momentum/reversal-style factors to test whether a
   reported Sharpe ratio is genuine alpha or disguised beta) was adapted
   -- not its RL architecture, which does not fit this project's
   single-index/LETF switching setup -- and run against golden1_0531 and
   the `switch_ma*` family
   (`scripts/evaluate/build_group_a_plus_golden1_factor_attribution_review.py`).
   A full-sample regression answers "does this candidate have a
   statistically distinguishable mean excess return beyond simple market
   beta" -- for any switching/timing candidate, that is necessary but not
   sufficient evidence, because a switching rule's actual value
   proposition is often drawdown protection during crashes, which a
   linear regression on average daily returns does not directly measure
   (a rule can show zero unconditional alpha and still meaningfully cut
   losses in the states it was designed for, or vice versa -- show
   positive average alpha while doing nothing useful in an actual
   crash). Run
   `scripts/evaluate/build_group_a_plus_golden1_crash_window_protection_review.py
   --auto-detect` (objectively detects drawdown episodes from a trailing
   1-year rolling peak, rather than hand-picking "famous" crash dates,
   which this project's own first pass at this check did and which
   overstated consistency: 3 hand-picked windows showed 18/18
   perfectly-signed results across 6 rules, while the unbiased 12-episode
   auto-detected sample showed a real but more modest 67-83% hit rate per
   rule) and report both the mean excess-return/drawdown-relief-vs-MKT
   and the positive-hit-rate fraction, not just the mean (a strategy can
   have a positive mean driven by a few large episodes while losing more
   often than it wins). First run (2026-08-10/11) found golden1_0531
   itself -- the frozen static buy-and-hold weight snapshot
   (0050:0.6/00631L:0.2/cash:0.2), not a switching rule -- underperformed
   simply holding 0050 in 8 of 12 auto-detected drawdown episodes (mean
   excess return -2.88%, mean drawdown relief -4.13%), with the
   underperformance markedly worse in the most recent 2024-2026 episodes
   (-7% to -10% excess return) than in 2018-2019 (roughly flat to
   slightly positive) -- consistent with 00631L's leveraged-tracking
   decay amplifying losses in an unhedged static allocation, and getting
   worse recently rather than staying constant, which is itself worth a
   closer look before treating golden1_0531 as a safe reference/fallback
   allocation. Applies to any candidate whose claimed value is
   switching/timing/defensive-tilt behavior (not every candidate --
   e.g. a pure stock-selection or blend-weight candidate with no
   regime-conditional behavior doesn't need this), in addition to (not
   instead of) the mean-return checks in items 1-4 and the factor
   regression above -- a candidate can pass one and fail the other.

10. **A simultaneous-coverage significance check for any candidate selected
    via multi-round/grid search**, added 2026-09-05 from arXiv:2608.08405
    ("Robustness or Crowding: Experimental Design for Trading Strategy
    Capacity" -- desk review: closed_negative overall for its main
    capacity-experiment framework, see project memory
    `project_2608_08405_capacity_experiment_design_desk_review_20260904`,
    but Prop 3.12/Table 8 is a general statistical design point worth
    importing on its own). Whenever a candidate's promotion evidence
    includes a Sharpe/return comparison against baseline that was selected
    by picking the best-looking result out of a multi-round parameter
    search (grid search, coordinate descent, threshold sweep) on the same
    fixed window(s), report the significance of that comparison using
    `group_a_plus/governance/significance.py`'s
    `bonferroni_grid_significance()` with `candidate_grid_size` set to the
    actual count of distinct configurations evaluated across the whole
    search (not just the winning round) -- not the uncorrected
    per-candidate JK-Memmel p-value or bootstrap CI computed only for the
    reported winner, which overstates confidence because the candidate was
    selected *for* looking good. `jobson_korkie_memmel_test()` is two-sided,
    so read `bonferroni_grid_significance()`'s `significant_improvement`
    field (added 2026-09-05 after this exact gap was caught reviewing the
    A22 validation below), not the raw `significant` field, when deciding
    whether to promote -- `significant` alone is also True for a candidate
    that is significantly *worse* than baseline, and a promotion check that
    reads it directly would treat a confirmed regression as confirmed
    evidence. Retroactively validated 2026-09-05
    (`scripts/misc/significance_check_a22_bad_vol_overlay_grid_20260905.py`)
    against the one historical case in this repo where this exact failure
    mode was later proven real by actual out-of-sample data:
    A22_bad_vol_overlay's 6-round-plus coordinate-descent champion (see
    `feedback_overfitting_fixed_window_tuning`), whose apparent in-sample
    sum-Sharpe improvement (+0.045 across 4 windows) did not survive
    correction for its actual 33-candidate search grid in any of the 4
    tuning windows individually (nothing even cleared the *uncorrected* 5%
    level in the champion's favor). The 4 per-window checks are themselves
    only an approximation, though, since the actual historical selection
    criterion was the SUM of Sharpe deltas across all 4 windows -- a single
    joint statistic, not 4 independent ones; a Stouffer combined-z test
    across the 4 window z-statistics is the more faithful reconstruction of
    that selection criterion, and it makes the null result far starker: the
    4 windows' effects (2 negative, 2 positive, similar magnitude) largely
    cancel, giving a combined z of 0.076 (p=0.94) -- consistent with each
    window separately fitting its own noise rather than any shared signal,
    matching what the far more expensive later OOS test found the hard way
    (3-year aggregate delta Sharpe -0.058). When applying this check to a
    candidate selected on a summed/pooled multi-window criterion, prefer the
    combined-z reconstruction over 4 marginal per-window Bonferroni checks
    for the same reason. This is a companion check to
    `feedback_overfitting_fixed_window_tuning`'s
    existing "more than 2-3 rounds on the same window needs OOS" rule, not
    a replacement -- this one can be run immediately with only the
    in-sample data already in hand, as an early-warning gate before
    committing to (or in cases where data gaps block) an OOS validation.

11. **A manager-scaling-endogeneity caution for observational
    turnover/position-size analyses**, added 2026-09-05, also from
    arXiv:2608.08405 (Assumption 3.2 / Theorem 3.3 discussion). Regressing
    realized returns on realized turnover, or more generally reading
    "we sized up after X looked good, and it kept performing well/poorly"
    as evidence about whether sizing up helped, estimates a mixture of any
    true edge-decay/capacity slope and the decision-maker's own scaling
    rule -- because real allocation decisions are typically made *after*
    observing recent performance, assignment is a function of the outcome,
    not independent of it. Before citing any backtest/live-history
    turnover-vs-return or position-size-vs-subsequent-performance analysis
    as evidence for or against a rule, confirm whether the sizing decision
    itself was triggered by the same recent-performance signal being
    evaluated; if so, the correlation has no causal read on whether sizing
    up helped, only on whether the trigger itself was already informative.
    Generalizes `feedback_lookahead_bug_same_day_signal_decision`'s
    same-day-drawdown-decides-same-day-position finding to any deliberate
    allocation-after-signal decision, not just same-day mechanical rules.

12. **A same-complexity-class naive-baseline requirement for any RL or
    optimizer-based candidate**, added 2026-09-05 from arXiv:2603.22880
    ("Portfolio Optimization under Recursive Utility via Reinforcement
    Learning" -- desk review: closed_negative overall, see project memory
    `project_2603_22880_recursive_utility_rl_desk_review_20260905`; the
    paper's main recursive-utility-in-RL-value-target mechanism and its
    Campbell-Viceira closed-form allocation rule both fail for GroupA+'s
    tiny, highly-correlated core universe -- 0050 long, 00631L 2x long,
    00632R inverse, 00679B bonds, cash -- for the same reason: the
    "hedging demand" / diversification value both mechanisms rely on needs
    genuinely independent cross-asset risk exposures that this universe
    does not have). The paper's own most credible result is not about
    recursive utility at all: a trivial equal-weight (1/N) benchmark (SR
    2.3-2.7) beats every RL variant tested, including the paper's own
    headline recursive-utility PPO result (SR 2.07) -- the entire RL
    framework never actually clears the bar of a benchmark with zero
    training and zero overfitting surface. Before crediting any future
    RL-policy or formal-optimizer candidate for GroupA+ with an
    improvement, compare it against a naive baseline of the *same
    complexity class* (equal-weight across the candidate's own asset set,
    or the existing rule-based golden strategy itself) -- not just against
    a weaker variant of the same RL/optimizer framework. Beating a worse
    RL variant is not evidence the RL approach itself adds value.
    Consistent with this project's existing skepticism toward formal
    optimizers (`project_2606_26625_commodity_etf_cvar_tail_cost_20260831`
    found a claimed "optimizer wins 5/5" result was an in-sample
    overfitting artifact) and with `feedback_strategy_promotion_caution`.

13. **A hyperparameter-sensitivity-sweep requirement before crediting any
    RL-based result**, added 2026-09-05, also from arXiv:2603.22880's
    Appendix D.3 ablation study. On the identical training window, the
    paper's own recursive-utility PPO swings from SR=4.00 (K=1 Monte
    Carlo samples for the certainty equivalent) to SR=0.08 (K=5) to
    SR=1.52 (K=10) -- a non-monotone, order-of-magnitude swing from one
    hyperparameter change alone, with only one trial per split (no seed
    averaging, no confidence interval). A result reported at a single
    hyperparameter setting under these conditions is not evidence of a
    real effect, only a sample from a highly unstable distribution of
    outcomes. Before crediting any future RL-based candidate's headline
    metric for GroupA+, require a sensitivity sweep over its 2-3 most
    consequential hyperparameters (learning rate, key architecture
    choices, any Monte-Carlo sample count, training window/episode
    length) and report the range, not just the best-looking point --
    treat a single-setting RL result with the same skepticism this
    project already applies to a single-window backtest result under
    `feedback_overfitting_fixed_window_tuning`.

## What this checklist does NOT require

- It does not require adopting continuous-score/smooth-signal designs
  (the paper's actual strategy mechanism) -- that was explicitly rejected
  for import; see the sibling handoff doc.
- It does not require a fixed number of walk-forward folds or a specific
  training/test split length -- match the split to whatever OOS data
  this project already has for the ticker/window in question (usually
  the 2017-2019 backfill panel and/or the five-crisis dataset), rather
  than inventing a new backfill for every candidate.
- It does not replace the existing overfitting-avoidance rule already in
  memory (`feedback_overfitting_fixed_window_tuning`): more than 2-3
  tuning rounds on the *same* window still requires an independent OOS
  check before claiming improvement. This checklist is about breadth of
  validation angle: it doesn't lower the bar on how many times you're
  allowed to re-tune against the same data.

## How to apply going forward

Before writing a `production_ready` / `promotion_ready` / "do not
promote" verdict for any new Group A+ shadow candidate, confirm all
applicable checklist items were actually run and reported -- not just the
single aligned comparison window most existing `evaluate_*.py` scripts
default to today. If a candidate only clears the bar on the aligned window
and fails or is untested on any of the others, treat it the same way this
project already treats single-window evidence: a candidate for further
work, not a promotion-ready result. Item 5 applies specifically whenever
the comparison baseline is a2118 itself (not every candidate needs it --
only ones being compared against a2118's plain `run_a2118()` numbers).
Item 6 applies specifically whenever a *new* signal/interaction term is
being added to an *existing* candidate's mix (not the initial screen of a
brand-new candidate's first component). Item 7 applies specifically
whenever the candidate is (or introduces) a hard threshold gate on a
composite score built from independent sub-indicators -- not every
candidate has one. Item 8 applies specifically whenever a
directional-accuracy/hit-rate/win-rate metric is part of the candidate's
evidence -- not every candidate reports one (many report R²/Sharpe/return
deltas instead, which don't need this specific check, though a candidate
using both should still apply it to the hit-rate half). Item 9 applies
specifically whenever the candidate's claimed value is switching/timing/
defensive-tilt behavior -- a mean-return-only evaluation of such a
candidate is incomplete even if items 1-4 all pass, since crash-window
protection and unconditional mean alpha are different claims that don't
imply each other. Item 10 applies specifically whenever a candidate's
headline number was the winner of a multi-round/grid search on fixed
window(s) -- a single-shot candidate (no search, no coordinate descent)
doesn't need it, but should still get the plain (uncorrected)
`jobson_korkie_memmel_test`/`bootstrap_final_value_ci` treatment already
established. Item 11 applies specifically whenever a candidate's evidence
includes an observational (not randomized/backtest-mechanical) read of
"we sized up/down after signal X, and performance changed" -- not every
candidate makes this kind of claim. Items 12 and 13 apply specifically
whenever the candidate is an RL-trained policy or a formal
optimizer-based allocation rule (not every candidate is -- most GroupA+
shadow candidates are rule-based threshold/overlay changes, which don't
train a policy or solve an optimization problem, so items 12-13 don't
apply to them). Item 12's naive-baseline comparison should use the
simplest baseline of comparable scope to the candidate's own asset set
(equal-weight if the candidate allocates across multiple assets, or the
existing rule-based golden strategy if the candidate is meant to replace
it). Item 13's sweep only needs to cover hyperparameters that plausibly
drive the headline metric, not every configurable value.
