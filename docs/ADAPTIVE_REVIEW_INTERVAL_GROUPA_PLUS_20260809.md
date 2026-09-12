# Adaptive Review Interval - Group A+ Review

**Status: shadow-only, not promoted. Real trade-off identified, mixed
result. User-proposed mechanism, 2026-08-09.**

## Background

User proposed a third, distinct mechanism from two that already exist:
`staged_buys`/buy-fraction (execution_plan.py, how fast to trade toward an
already-decided target) and `min_hold_days` (SwitchRule, blocks exiting a
regime for N days but still recomputes the signal daily). Adaptive review
interval is about how often to even **recompute** the signal at all: output
NEXT_REVIEW_1D/3D/5D based on regime stability, freeze the portfolio
between scheduled reviews, only re-look at the fresh signal on review days.

Confirmed via grep that no such mechanism existed before this (`min_hold`
and `staged_buys` are both real but answer different questions).

## What Was Built

`scripts/evaluate/evaluate_adaptive_review_interval_shadow.py`:

- `classify_review_interval()`: causal, single-day classifier using only
  that day's own a2118 frame data (`execution_regime`, `ma_gap`,
  `drawdown`, `tail_risk_score`) against A21.18's own switch-rule
  thresholds (`entry_ma_gap=-0.003`, `exit_ma_gap=0.010`,
  `dd_threshold=-0.11`, from `group_a_plus/runners/a2111.py`'s
  `_build_switch_rule()`, which a2118 imports unmodified):
  - `group_a_plus_recovery` regime, or drawdown within 3pp of the -11%
    trigger, or `tail_risk_score >= 5` -> 1-day review ("crash_or_recovery").
  - stable `golden1` (ma_gap and drawdown comfortably away from their
    entry/override thresholds) -> 3-day review.
  - stable `group_a_plus_defensive`, far from the +1% re-entry threshold
    -> 5-day review.
  - anything near a threshold or an unrecognized regime -> 1-day
    (conservative default).
- `simulate_adaptive_review()`: freezes the portfolio at the last-reviewed
  target between scheduled review days; a2118's own regime/target
  computation runs completely unchanged underneath (`golden1_0531` and
  A21.18's decision rule untouched -- this only decides which days' fresh
  outputs get acted on).
- Two arms compared via the same cost-aware simulator used throughout this
  session's shadow scripts: Daily Review (baseline, = current a2118) vs
  Adaptive Review.
- `_delayed_and_avoided_transitions()`: a diagnostic-only, post-hoc
  breakdown of days where the frozen target differed from the fresh one,
  tagged as "delayed useful transition" or "avoided false transition" based
  on that single day's realized 0050 return direction -- purely for
  reporting, not fed back into the simulation.

10 unit tests (`tests/test_evaluate_adaptive_review_interval_shadow.py`),
all passing.

## Result

Real end-to-end run, same 7 windows as this session's other 2026-08-09
shadow lines:

| window | review interval usage | regime flips | suppressed days | delta final_value | delta cost | delta turnover |
|---|---|---:|---:|---:|---:|---:|
| live_2024_2026 | 3d:148, 1d:160, 5d:1 | 6 | 1 | -15,343 | -140 | -60,786 |
| active_2025_2026 | 3d:90, 1d:102, 5d:1 | 6 | 1 | -4,664 | -41 | -18,023 |
| stress_2026 | 3d:37, 1d:28 | 3 | 0 | 0 | 0 | 0 |
| backfill_2020_covid | 3d:49, 1d:97 | 5 | 1 | **+485** | +19 | +6,606 |
| backfill_2021_may_correction | 3d:49, 1d:67, 5d:6 | **14** | 4 | **-2,656** | **-3,882** | **-1,598,381** |
| backfill_2022_rate_hike | 3d:9, 1d:175 | 1 | 0 | 0 | 0 | 0 |
| backfill_2024_aug_unwind | 3d:58, 1d:59 | 0 | 0 | 0 | 0 | 0 |

**Summary**: 4 of 7 windows triple-pass, aggregate cost/turnover reduced
(`net_cost_pass: true`, -4,044 total cost, -1.67M total turnover), but
`decision: research_only_not_promoted` since 3 of 7 windows don't pass.

The classifier mechanism itself is verified working correctly, not
degenerate -- real 1d/3d/5d diversity across every window, and review
counts scale sensibly with regime volatility (65 reviews in the calm
`stress_2026` window vs 309 in the choppier `live_2024_2026` window).

## Interpretation -- a real trade-off, not a bug and not a clean win

Three windows (`stress_2026`, `backfill_2022_rate_hike`,
`backfill_2024_aug_unwind`) show zero suppressed days -- the underlying
regime simply never changed between scheduled review points during these
periods, so the two arms are trivially identical. No information either
way.

**`backfill_2020_covid`**: the one clean positive result. One suppressed
day, tagged "avoided_false_transition," and the outcome matches -- final
value +485, cost and turnover both *higher* (adaptive actually traded a
little more here, interestingly, likely from a delayed catch-up trade), but
performance still improved.

**`live_2024_2026` / `active_2025_2026`**: cost and turnover both went
*down* (fewer/cheaper trades, as the mechanism is designed to produce) but
performance also went *down*. Only 1 suppressed day was flagged in each,
yet the final-value impact is disproportionately large (-15,343 on a
~$1M portfolio) -- a reminder that the single-day "suppressed_days" count
understates the true economic impact: one day of frozen (stale) weights
changes the portfolio's actual holdings for every subsequent day until the
next review, so its effect compounds rather than being a one-day cost.

**`backfill_2021_may_correction`**: the clear loser, and the most
informative result. This window has by far the most regime flips (14, vs
0-6 everywhere else) -- a genuinely choppy, fast-changing period. 4
suppressed days (1 "delayed useful," 3 "avoided false" by the day-level
heuristic), but the net effect is a real loss: final value -2,656, Sharpe
-0.045, *and* substantially lower cost/turnover (2 fewer rebalances,
-1.6M less turnover) -- meaning the adaptive review genuinely missed real,
needed regime transitions during a period the review-interval classifier
did not recognize as "crash-like" often enough to force daily review
throughout. This is exactly the failure mode the user's own proposal
anticipated needing to guard against (crash/recovery -> daily review), but
the specific threshold calibration used here (`crash_dd_buffer=0.03`,
`crash_tail_risk_score_min=5`) wasn't sensitive enough to catch this
particular period's whipsaw character.

## Decision

**Not promoted.** A genuine, understood trade-off: the mechanism reduces
turnover/cost as designed, and shows one clean win, but loses meaningfully
in a genuinely choppy period because the current crash-detection threshold
under-reacts to whipsaw conditions that don't cross the drawdown/tail-risk
bar but still involve frequent regime changes.

**Deliberately not re-tuning the crash-detection thresholds
(`crash_dd_buffer`, `crash_tail_risk_score_min`, the stability buffers) to
fix the 2021 result** -- doing so on this same handful of backtest windows
would be exactly the coordinate-descent-over-a-few-windows pattern the
user's own proposal explicitly wanted to avoid repeating (see this
project's already-closed prior parameter-tuning line,
[[feedback_overfitting_fixed_window_tuning]]). Reporting the finding
as-is rather than hand-tuning toward a better number on this specific
window set.

If revisited, the honest next step is either (a) a regime-volatility-aware
trigger for the crash-detection condition itself (e.g., flag "choppy"
directly via recent regime-flip frequency, not just drawdown/tail-risk
level) tested on a genuinely wider set of windows before any threshold
value is chosen, or (b) accepting the mechanism only where its downside is
structurally bounded (e.g., a much lower default interval ceiling than
5 days) rather than trying to tune away the 2021 failure mode specifically.
