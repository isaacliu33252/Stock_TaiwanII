# Adaptive Lookback Feature Window - Group A+ Review

**Status: shadow-only, inconclusive (not "fails", not "passes"). User-proposed
mechanism, 2026-08-09.**

## Background

User proposed replacing A21.18's several fixed lookback windows (MA100,
`risk_score_lookback_days=5`, 5-day momentum) with an adaptive, causal,
online window selection: pre-declare a fixed candidate set
{20, 40, 60, 120, 252}, and each day pick whichever candidate had the best
trailing directional hit-rate as of T-1 -- distinct from this project's
prior closed coordinate-descent parameter-tuning line (which searched for
one fixed "best" parameter set across a handful of backtest windows and was
closed as overfitting-prone): here the candidate set never changes, only
which member is used varies day to day, chosen from realized (past-only)
prediction quality.

User explicitly scoped this: **do not touch MA100 as a first step**, and
keep A21.18's decision rule fixed, only replace a feature-estimation
window. Investigated `risk_score_lookback_days` as a candidate first target
(it's literally named as a "fixed window" in the proposal) and found it
directly gates the golden1/defensive switch trigger itself
(`total_risk_ok` in `backtest_group_a_plus_switch_policy.py`) -- not a pure
downstream feature, so using it would violate "keep the decision rule
fixed." Instead used the narrow_lead trigger inside today's
ADD_0050_INSTEAD shadow guard (built earlier the same day, see
`docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md`) -- that guard
is itself shadow-only/additive on top of a2118's unchanged output, so
varying its internal window doesn't touch A21.18's core rule either.

## What Was Built

`scripts/evaluate/evaluate_adaptive_lookback_narrow_lead_shadow.py`:

- `select_adaptive_window()`: for each day, causally chooses among
  {20,40,60,120,252} whichever window's `concentration_divergence` sign
  best predicted the realized next-day 00631L-vs-0050 relative-return sign
  over the trailing 60 days -- using only outcomes known strictly before
  that day (an outcome on day *s* only becomes usable once day *s+1*
  closes, so the evaluation window for day *t* stops at *t-2*, not *t-1*).
- Simplified two-condition trigger (`ret_2330(window) > 0` AND
  `concentration_divergence(window) > 0`) used identically in both arms --
  daily_signal.py's exact 3-condition `narrow_lead` has a magnitude-gap
  condition (`ret_2330_5d - ret_0050_5d > 0.01`) calibrated for a 5-day
  window with no obvious scale-invariant generalization to a 252-day
  window, so it was dropped from both arms rather than guessed at, keeping
  the fixed-window and adaptive-window arms comparable on identical rule
  shape.
- `A21.18_fixed_window` (hardcoded 5-day, matching daily_signal.py's live
  window) vs `A21.18_adaptive_feature_window` compared via the same
  `_apply_add_0050_instead_from_trigger()` redirect mechanism as this
  morning's `evaluate_add_0050_instead_of_00631l_shadow.py`. `golden1_0531`
  and a2118's regime backtest are byte-identical between both arms and the
  baseline.

6 unit tests (`tests/test_evaluate_adaptive_lookback_narrow_lead_shadow.py`),
all passing.

## Result

Real end-to-end run, same 7 windows as this morning's TSMC/lead-lag work
(2020-2026 span), `eval_lookback=60`:

| window | fixed events | adaptive events | window_usage (top) | fixed delta (final/sharpe) | adaptive delta | adaptive-fixed |
|---|---:|---:|---|---|---|---|
| live_2024_2026 | 2 | 2 | 20:193, 40:134, 60:126 | +3,323 / +0.001 | +3,323 / +0.001 | 0 / 0 |
| active_2025_2026 | 2 | 2 | 20:138, 60:135, 252:49 | +1,485 / +0.010 | +1,485 / +0.010 | 0 / 0 |
| stress_2026 | 1 | 0 | 20:105, 60:33 | +2,631 / +0.058 | 0 / 0 | **-2,631 / -0.058** |
| backfill_2020_covid | 0 | 0 | 20:89, 40:78, 60:50 | 0 / 0 | 0 / 0 | 0 / 0 |
| backfill_2021_may_correction | 6 | 0 | 20:108, 60:65, 120:64 | **-4,855 / -0.086** | 0 / 0 | **+4,855 / +0.086** |
| backfill_2022_rate_hike | 0 | 0 | 20:132, 40:39, 60:31 | 0 / 0 | 0 / 0 | 0 / 0 |
| backfill_2024_aug_unwind | 0 | 0 | 20:94, 40:87, 60:51 | 0 / 0 | 0 / 0 | 0 / 0 |

**Summary**: `adaptive_beats_fixed_windows = 6/7`, but this headline number
is misleading on its own -- see interpretation below. `total_adaptive_events
= 4`, `total_fixed_events = 11` across all 7 windows combined (6+ years of
data). Decision: `research_only_not_promoted` (the summary rule requires
7/7, not 6/7, to promote to shadow queue).

## Interpretation -- inconclusive, not a clean pass or fail

The window-selection mechanism itself works correctly and is not
degenerate: `adaptive_window_usage_counts` shows real diversity across
every window tested (20/40/60/120/252 all get chosen in different periods,
never collapsing to always-pick-one-window). That part of the proposal is
validated as implemented as designed.

But the **backtest comparison itself is not informative enough to draw a
conclusion**, because it decomposes into:

- **3 windows (2020, 2022, 2024-aug-unwind)**: both arms fired zero events
  -- trivial ties, no information either way.
- **2 windows (live_2024_2026, active_2025_2026)**: both arms fired the
  *same* 2 events on the *same* dates, producing byte-identical results
  despite the adaptive selector using several different window values
  along the way -- plausible when a strong, sustained divergence shows the
  same directional sign across most/all candidate windows simultaneously,
  but this contributes zero differentiating information about whether
  adaptive selection is better or worse.
- **1 window (stress_2026)**: adaptive fired *fewer* events than fixed and
  missed the one profitable trigger fixed caught -- adaptive strictly
  worse here.
- **1 window (backfill_2021_may_correction)**: fixed fired 6 times and
  those trims were actively *harmful* (-4,855, -0.086 Sharpe); adaptive
  fired 0 times, so "doing nothing" outperformed by comparison -- this is
  adaptive avoiding a loss through inaction, not through a correct
  prediction, so it doesn't demonstrate the adaptive window chose *better*
  information, only that it was more conservative (or, at these window
  lengths, that its trailing-hit-rate criterion happened not to flag a
  trigger the shorter fixed window did).

**Root cause of the inconclusiveness**: this inherits the same sparsity
problem already documented for the underlying ADD_0050_INSTEAD guard
itself (see `docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md`)
-- across 6+ years and 7 windows, the combined trigger count is only 15
events total between both arms. That is far too few real differentiating
observations to validate whether causal adaptive-window selection is
better or worse than a fixed window for this specific trigger. The
adaptive-window *concept* was not given a fair test here; the *host
mechanism* it was attached to (narrow_lead / ADD_0050_INSTEAD) simply
doesn't fire often enough in this backtest history to generate enough
signal to evaluate a secondary refinement on top of it.

## Decision

**Not promoted, and correctly not claimed as validated either way.**
Per this project's signal-validation discipline, this is closed as
"insufficient evidence," distinct from the clean negative results reached
for the cross-market lead-lag relative-return targets earlier the same day
(where the null result was decisive, not sparse). If this line is
revisited, it needs either (a) a host trigger mechanism that fires more
often (so there's enough adaptive-vs-fixed differentiating events to
actually compare), or (b) direct evaluation of the window-selection
criterion's own trailing hit-rate accuracy (independent of any downstream
trading action) as a first-pass sanity check before wiring it into a
sparse guard again.

Does not touch A21.18's decision rule, `golden1_0531`, or MA100 in any way
-- per the user's explicit scoping instruction, none of those were touched
this pass.

## 2026-08-09 Follow-Up: Direct Hit-Rate Comparison (Removes the Sparsity Problem)

Built `scripts/evaluate/evaluate_adaptive_window_hit_rate_comparison.py` to
directly test the adaptive-window concept without gating on the sparse
ADD_0050_INSTEAD trigger -- scores every trading day's
`sign(concentration_divergence(window))` against the realized next-day
00631L-vs-0050 relative-return sign, for each individual fixed window in
{5,20,40,60,120,252} and for the adaptively-selected window, over
2019-2026-08-07 (~1,543-1,543 observations per arm, two orders of
magnitude more than the 15-event backtest above).

| window | n | hit rate | z vs 50% | significant (5%) |
|---|---:|---:|---:|---|
| fixed 5d | 1,537 | 49.8% | -0.13 | no |
| fixed 20d | 1,543 | 52.9% | 2.32 | **yes** |
| fixed 40d | 1,543 | 52.4% | 1.86 | no |
| fixed 60d | 1,543 | 52.9% | 2.27 | **yes** |
| fixed 120d | 1,543 | 55.3% | 4.20 | **yes** |
| fixed 252d | 1,543 | **56.4%** | 5.02 | **yes** |
| adaptive | 1,543 | 55.1% | 4.00 | **yes** |

At face value this looks like a real, statistically significant finding --
and notably, the *adaptive* window (55.1%) actually **underperforms simply
always using the longest fixed window** (252d, 56.4%), the opposite of what
the proposal would want to show.

**But this is the same base-rate artifact found in the cross-market
lead-lag review earlier the same day, confirmed directly**: split the
252-day window's predictions by which side actually won.

| realized outcome | n | hit rate |
|---|---:|---:|
| 00631L wins | 888 | **88.1%** |
| 0050 wins | 655 | **13.4%** |

The 252-day divergence signal is positive (predicting "00631L wins") on
87.4% of all days -- it is not a forecast, it is a near-constant readout of
the multi-year structural uptrend a 252-day trailing return captures almost
by definition. The apparent "56.4% hit rate, z=5.0" is entirely explained
by this near-constant prediction matching the majority outcome most of the
time; it collapses to 13.4% (far worse than 50-50) on the minority days
0050 actually wins. **There is no genuine bidirectional predictive skill at
any fixed window or in the adaptive selector** -- only structural drift,
more strongly captured by longer windows precisely because they average
over more of the persistent trend rather than reacting to it.

## 2026-08-09 Follow-Up: eval_lookback Parameter Sweep

Swept the adaptive selector's own tuning parameter (`eval_lookback` in
{20, 40, 60, 90, 120, 180}) to confirm "adaptive doesn't reliably beat the
best single fixed window" is robust, not an artifact of the one
`eval_lookback=60` setting tested above.

| eval_lookback | adaptive hit rate | best fixed (always 252d) | adaptive beats best fixed |
|---:|---:|---:|---|
| 20 | 54.5% | 55.9% | no |
| 40 | 54.3% | 56.1% | no |
| 60 | 55.1% | 56.4% | no |
| 90 | 55.5% | 56.0% | no |
| 120 | 56.1% | 55.7% | yes (margin 0.4pp) |
| 180 | 55.5% | 55.5% | yes (margin 0.1pp) |

**Confirmed robust.** `fixed_252d` is the best or tied-best single fixed
window at every setting tested. Adaptive selection beats it in only 2 of 6
settings, and even those "wins" are by a fraction of a percentage point --
noise-level given the underlying signal has already been shown to be a
base-rate/trend-bias artifact rather than genuine skill (see above). No
parameter setting changes the fundamental conclusion: adaptive window
selection over this candidate set does not reliably outperform simply
using the longest available fixed window, and neither has real
bidirectional predictive power once the multi-year uptrend bias is
accounted for.

## Final Decision (Supersedes the "Inconclusive" Verdict Above)

**Closed, decisive null result once corrected for the base-rate artifact.**
The "inconclusive due to sparse triggers" finding from the ADD_0050_INSTEAD
-backtest comparison above is now understood in a stronger light: it wasn't
just under-sampled, the underlying signal it was trying to differentiate
between candidate windows on doesn't have real bidirectional skill in the
first place. Neither the adaptive window-selection mechanism nor any
individual fixed window (including the best-looking one) provides genuine
next-day relative-return predictability once mean-bias is accounted for --
consistent with, and reinforcing, the same-day cross-market lead-lag
review's conclusion. Not promoted. Closed.
