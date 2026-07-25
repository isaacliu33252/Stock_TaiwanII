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
promote" verdict for any new Group A+ shadow candidate, confirm all six
checklist items were actually run and reported -- not just the single
aligned comparison window most existing `evaluate_*.py` scripts default
to today. If a candidate only clears the bar on the aligned window and
fails or is untested on any of the others, treat it the same way this
project already treats single-window evidence: a candidate for further
work, not a promotion-ready result. Item 5 applies specifically whenever
the comparison baseline is a2118 itself (not every candidate needs it --
only ones being compared against a2118's plain `run_a2118()` numbers).
Item 6 applies specifically whenever a *new* signal/interaction term is
being added to an *existing* candidate's mix (not the initial screen of a
brand-new candidate's first component).
