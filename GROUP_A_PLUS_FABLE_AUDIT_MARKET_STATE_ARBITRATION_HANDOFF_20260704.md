# GroupA+ Fable Audit + Market-State Arbitration Handoff - 2026-07-04

## Executive Summary

Follow-up to the 2026-07-02 Fable 5 audit (`GROUP_A_PLUS_FABLE5_AUDIT_A214_REVERT_HANDOFF_20260702.md`).
A second open-ended Fable audit found and fixed 3 new issues (all in the 07-03-added
`market_state.py` diagnostic module and its interaction with a2118's dual panel/live trigger
paths). Follow-up work then addressed one of the audit's decision items — whether/how to
arbitrate disagreements between `market_state.py`'s advisory classification and a2118's actual
execution — with two backtests (2025-2026 real data, 2008 TWII proxy).

**Most important result: not the market_state question itself, but an incidental discovery that
a2118's real SwitchRule would stay fully levered (`golden1`) through an entire crash if chip/
derivative data is unavailable**, because `total_risk_score >= 6` is a hard gate for entering
`group_a_plus_defensive` and that score is 0 whenever chip inputs are missing — which is exactly
the 2008 proxy's situation, and plausibly correlates with real-world data-outage-during-crisis
scenarios. This is flagged as a decision item for the user, not fixed (would change live
behavior).

## Part 1: Fable Audit Fixes (Diagnostic-Only, No Live-Behavior Change)

1. **`market_state.py` hedge-regime misclassification**: when `ma_gap` in (0.10, 0.12) and
   `total_risk_score < 6`, the classifier could score `bull_acceleration`/`bull_trend`
   ("00631L high weight") even while `ncf_late_bull_hedge` was active. Fixed by removing an
   extraneous risk-score condition from the hedge branch. Verified against all 11 historical
   hedge/soft-hedge days.
2. **`market_state` didn't see a2118's live-only hard overlay** (the more consequential of the
   two): a2118 has two trigger paths — the panel-baked `execution_regime` string, and a fresher
   live-JSON-driven hard overlay (`trigger`/`h5_hold`/`stale_fail_closed`/`panel_trigger`). When
   the live overlay fires but the panel hasn't caught up yet (panel drift, previously documented
   in `project_ncf_panel_global_weight_drift_20260702`), `target_weights` already reflect the
   hedge but `classify_market_state` was still being fed the stale `"golden1"` label. Fixed via
   a new `_market_state_regime()` helper in `daily_signal.py` that substitutes
   `"ncf_late_bull_hedge"` whenever `ncf_live_overlay["a2118_late_bull_hard_overlay_applied"]`
   is true.
3. **`DEFAULT_LIVE_SIGNAL` path not anchored to `PROJECT_ROOT`**: a manual invocation from a
   different working directory would silently fail to find the previous live signal, disabling
   the H5/stale-fail-closed hold-carryover guard. Fixed to an absolute path.

138 relevant tests + full 545-test collection pass. Files changed: `market_state.py`,
`daily_signal.py`, `test_group_a_plus_market_state.py`, `test_group_a_plus_daily_signal_v2.py`.

Confirmed clean (no new issues): `signal_alignment.py`'s M7 fix, `execution_plan.py`, `ncf.py`,
`ops_health.py`/`alert_state.py`/`model_weight_health.py` (all correctly diagnostic-only),
`governance/latest.py`, `runners/latest.py`.

Also flagged (not fixed, informational): the alert pipeline (`signal_alerts` /
`alert_state.py`) has no actual push channel (Telegram/LINE/email) wired into the unattended
23:00/23:30 daily pipeline — high-severity alerts (including fail-closed triggers) only land in
a JSON file today.

## Part 2: Decision Item A — Should market_state.py Ever Override Execution?

`market_state.py`'s `crash_risk` state recommends "00632R hedge or full defense," which
conflicts with a2118's deliberate design (75% of historical late-bull trigger days were still
up >5% at 20 days — a2118 intentionally avoids fully exiting). A 361-day replay
(2025-01-02~2026-07-02) found `crash_risk` fired 23 times, 9-10 of which were while
`execution_regime` was still `golden1` (full leverage, no defense).

### Step 1 (done): formalize "a2118 wins" as the explicit, tested default

Added an explicit arbitration-policy docstring to `market_state.py` stating that its output must
never feed into weight calculations without an explicit, backtested arbitration rule. Added a
pinned regression test (`test_crash_risk_can_fire_while_execution_regime_stays_golden1_by_design`
in `tests/test_group_a_plus_market_state.py`) that locks in the known disagreement case so a
future accidental change can't silently alter this behavior without review.

### Step 2 (done): backtest an "N-day persistence" arbitration rule on 2025-2026 data

Script: `scripts/misc/market_state_persistence_backtest.py`. Output:
`results/market_state_persistence_backtest_20260704.json`.

Re-replayed 361 days with the now-bug-fixed `market_state.py` (not reusing the pre-fix
`*_frame_market_state.csv`). `crash_risk` count matched the audit (23), but the
golden1-concurrent count came out as 10, not 9 (1-day discrepancy, not chased down further;
doesn't change the conclusion).

Tested requiring N consecutive `crash_risk` days before treating a trigger as "confirmed,"
N ∈ {1,2,3,5}, comparing 20-day forward return of holding vs. cash vs. switching to 00632R:

| N (golden1-concurrent) | Triggers | Hold mean | 00632R mean | Hold beats cash |
|---|---:|---:|---:|---:|
| 1 | 10 (9 usable) | +2.88% | -3.36% | 77.8% |
| 2 | 2 | +7.86% | -8.78% | 100% |
| 3 | 0 | — | — | — |
| 5 | 0 | — | — | — |

At N≥3 the golden1-concurrent trigger count hits zero — persistence-filtering strong enough to
be statistically comforting also erases the "early warning" the mechanism exists to provide.
At N=1, holding wins most of the time (supports a2118's philosophy) but on only 9-10 samples —
not enough to conclude anything. **Recommendation at this step: do not adopt a persistence
rule; the 2025-2026 sample is too small and too bull-skewed either way.**

### Step 3 (done): backtest the same mechanism on the 2008 TWII proxy (a genuine crash sample)

Script: `scripts/misc/market_state_2008_proxy_backtest.py`. Output:
`results/market_state_2008_proxy_backtest_20260704.json`.

**Unexpected, higher-priority finding**: the 2008 proxy period has no real chip/derivative data
at all. `total_risk_score` (and `chip_score`/`derivative_score`) come out as a hard 0 throughout
the entire window (verified with an assertion). a2118's actual `SwitchRule` requires
`total_risk_score >= 6` to *enter* `group_a_plus_defensive`. **That condition is structurally
unsatisfiable when total_risk_score is stuck at 0 — meaning if a2118's real rule were applied
unmodified to this data, it would stay in `golden1` (full leverage) through the entire 2008
crash, purely because chip data was unavailable, independent of price action.** This is
plausibly relevant beyond the 2008 proxy specifically: any real-world scenario where chip/
derivative data ingestion breaks down for an extended period (which historically tends to
correlate with market stress, not be independent of it) could leave a2118 unable to ever trigger
its own defensive switch. The script computed two regime variants to keep the rest of the
analysis meaningful: `real_rule` (faithful to a2118, stays `golden1` throughout) and
`idealized` (chip/total-risk gate removed, MA100/drawdown only, used for the persistence
backtest below).

`crash_risk`'s own trigger logic doesn't depend on regime (the tail-risk/ma_gap branches are
checked before the regime branches), so it fired identically under both variants: 96 times over
875 days, clustered around 2007-08, 2007-11~12, **2008-06~11 (the Lehman core crash)**, and
2009-01 — a sensible distribution for a real crash period.

N=1/2/3/5 persistence, 20-day forward return, `idealized` regime (95/96 defensive):

| N | Triggers | Hold (00631L) mean | 00632R mean | Hold beats cash |
|---|---:|---:|---:|---:|
| 1 | 25 | -4.88% | +2.61% | 36% |
| 2 | 16 | -5.66% | +2.94% | 37.5% |
| 3 | 11 | -9.26% | +4.51% | 27.3% |
| 5 | 7 | -3.58% | +1.18% | 42.9% |

**Every N shows the opposite direction from the 2025-2026 result**: holding loses money on
average, switching to 00632R gains, win-rate-vs-cash mostly below 50%.

## Consolidated Conclusion on Decision Item A

- 2025-2026 (bull-skewed): holding through a `crash_risk` signal was directionally *better* than
  defending, consistent with a2118's own design lesson, but on too few samples to be conclusive.
- 2008 proxy (genuine crash): defending was directionally *better* than holding, consistent
  with the intuitive purpose of a `crash_risk` state, also not statistically conclusive (proxy
  data, small samples) but pointing the opposite way.
- Put together, this is consistent with a **regime-dependent arbitration rule** (defer to a2118
  in ambiguous/bull-skewed conditions, give market_state's advisory more weight in a genuine,
  confirmed crisis) being more sensible than either "always defer to a2118" or "always defer to
  market_state" as a fixed rule — but this is not yet backed by strong enough evidence to
  implement. 2008 is a proxy, not real ETF history, and both backtests have small-sample caveats.
- **The a2118-stays-golden1-when-chip-data-is-missing finding is the more urgent, independently
  actionable item here** — it's a real robustness gap in the live strategy's defensive trigger,
  not a question about whether to trust a new diagnostic module.

## Recommendation / Open Items for User Decision

1. **(New, higher priority) Should a2118's `total_risk_score >= 6` defensive gate have a
   fallback when chip/derivative data is missing for an extended period?** Currently, silent
   chip-data unavailability structurally disables the defensive switch, and data outages are not
   obviously independent of market stress. Not fixed — would change live behavior, needs its own
   design + backtest before touching `a2118.py`.
2. **market_state.py arbitration**: keep the current default (a2118 always wins, market_state
   advisory-only) for now. Do not build a regime-dependent override without a much larger/more
   realistic crash sample (real 2008 ETF-equivalent history if obtainable, or other historical
   crisis windows per the original Fable audit's "multi-window stress" recommendation).
3. Alert push-notification gap (from Part 1) remains open and is an operational, not
   correctness, decision.

## Files Produced

- Modified (Part 1, with tests): `group_a_plus/operations/market_state.py`,
  `group_a_plus/operations/daily_signal.py`, `tests/test_group_a_plus_market_state.py`,
  `tests/test_group_a_plus_daily_signal_v2.py`
- New: `scripts/misc/market_state_persistence_backtest.py`,
  `scripts/misc/market_state_2008_proxy_backtest.py`
- New results: `results/market_state_persistence_backtest_20260704.json`,
  `results/market_state_2008_proxy_backtest_20260704.json`

## No Other Production Changes

`group_a_plus/runners/a2118.py`, `group_a_plus_config.json`, and
`report/group_a_plus/latest/*` were not modified. No git commits were created.
