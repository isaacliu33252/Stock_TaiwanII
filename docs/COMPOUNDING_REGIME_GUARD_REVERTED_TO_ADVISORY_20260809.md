# Compounding Regime Guard Reverted to Advisory-Only — 2026-08-09

**Status: fixed. `apply_compounding_regime_pre_trade_guard()`'s buy-blocking effect on real 00631L target shares is disabled; downgraded to advisory-only unconditionally.**

## What was found

While comparing the 2310.02084 (robust LETF leverage) paper review against
this project's existing live solution to the adjacent question — the
2504.20116-derived compounding regime classifier
(`GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`,
`docs/a2120_letf_compounding_regime_shadow_20260715.md`) — an initial claim
that the mechanism was "already validated and live in production" turned
out to be wrong in an important way on closer inspection:

1. **The daily pipeline feeds the guard the untuned default-threshold
   classifier.** `run_ncf_daily_pipeline.py`'s `commands["compounding_regime"]`
   step runs `evaluate_00631l_leveraged_compounding_regime.py` with no
   threshold overrides (`--end latest --output ... --csv ...` only).
2. **This project's own validation (Step 1, "Baseline Threshold Result" in
   the 07-15 doc) found that exact untuned MEAN_REVERTING-block
   configuration backtests negative**: `delta_final_value_sum = -8281.77`,
   only 2/5 positive windows.
3. The positive, eventually 7/7-window-validated candidate
   (`score3/ar0/persist50/rev50` thresholds, Steps 2-9) required **both**
   tuned thresholds **and** a trend-persistent fast-reentry acceleration
   half (Step 3's own interpretation: "Most of the improvement comes from
   TREND_PERSISTENT faster reentry, not from MEAN_REVERTING no-add" — the
   no-add-only variant's total delta was a negligible +13.17) that
   `apply_compounding_regime_pre_trade_guard()` never implemented at all.
4. **Even that fully-validated candidate's own promotion-gate scorecard**
   (Step 13, `build_a2120_letf_compounding_shadow_scorecard.py`) concluded
   `production = do_not_promote`, `production_upgrade_pass = false`,
   recommending `daily_advisory_shadow_only` instead, with explicit unmet
   blockers (`requires_t_plus_1_execution_alignment_audit`,
   `requires_rolling_window_shadow_monitoring_before_production`, etc.).

Despite all of the above, a 2026-08-08 change (found during that day's
paper-audit cross-check) had renamed this guard's `policy` field from
`"diagnostic_no_auto_weight_change"` to
`"auto_blocks_00631l_buy_additions_only_never_forces_sells"` — correctly
describing what the code does, but not questioning whether it *should*.
The function had, at some point, been wired to actually cap real 00631L
target shares to current holdings whenever the untuned classifier read
MEAN_REVERTING — the exact configuration shown to backtest negative, using
a mechanism explicitly not cleared for production by its own gate.

This is the same failure pattern as `feedback_strategy_promotion_caution`
memory's a214 mis-promotion incident: "looked reasonable, was live, wasn't
actually validated for the configuration that was live."

## Fix

Given the user's explicit choice ("先關閉live guard，改回純診斷") among four
options (disable-and-revert / wire in the validated tuned config / re-run
baseline validation on current data first / defer entirely), disabled the
guard's real-target-capping effect:

- **Did not touch `apply_compounding_regime_pre_trade_guard()`'s own
  schema/behavior** — it was tempting to add a new "diagnostic-only" status
  string directly there, but that function's `status`/`blocked_trades`
  schema (`status: "blocked"`, `blocked_trades[].blocked_delta_shares`) is
  read generically alongside the volatility and risk-add guards by several
  consumers (`_build_guard_impact_summary`'s `blocked_guard_names`,
  `_trough_high_vol_override_watch`'s `compounding_blocks_631l`, multiple
  test files) — changing it there would have required auditing and
  touching every generic guard consumer for a single guard's
  reconsideration.
- **Reused this project's existing advisory-downgrade pattern instead.**
  `execution_plan.py` already has a well-tested mechanism for exactly this
  — when `enforce_advisory_pre_trade_guards=False` (manual-order mode), it
  downgrades a guard's `status` to `"flagged_advisory_only"`, sets
  `enforced=False`, moves `blocked_trades` to `advisory_trades`, and keeps
  the full recommended target for human review. Applied this same
  transformation to `compounding_regime_pre_trade_guard`
  **unconditionally** (before, not inside, the
  `if not enforce_advisory_pre_trade_guards:` branch), so it's always
  advisory regardless of manual/automated execution mode — the volatility
  and risk-add guards are unaffected and keep their existing
  flag-dependent behavior.
- `compounding_guarded_targets` is now always `dict(staged_target_shares)`
  (never applies the compounding cap), matching the pattern already used
  for the manual-mode downgrade of the other guards.

## Verification

Updated 2 tests in `tests/test_group_a_plus_execution_plan_v2.py` that
asserted the old capping behavior
(`test_execution_plan_compounding_regime_guard_is_advisory_only_2026_08_09`,
formerly `..._end_to_end`; and
`test_execution_plan_reports_both_volatility_and_compounding_guards_when_both_block`)
to assert the new advisory-only shape instead. Confirmed
`apply_compounding_regime_pre_trade_guard()` itself is completely
untouched — its own 10-test file
(`tests/test_group_a_plus_execution_guard.py`) passes unchanged, proving
the fix is entirely in how `execution_plan.py` *uses* the guard's output,
not in the guard's own logic. `tests/test_check_group_a_plus_daily_status.py`
(33 tests) and `tests/test_group_a_plus_governance_catalog.py` also pass
unchanged. Full repo test suite run as final confirmation (see session
notes for pass/fail counts).

## Not done

- Did not wire in the actually-validated tuned thresholds
  (`score3/ar0/persist50/rev50` + trend-persistent fast-reentry) — that
  candidate's own scorecard says `do_not_promote` for good, listed reasons
  that remain unaddressed (T+1 execution-alignment audit, rolling-window
  shadow monitoring). Doing so now would repeat exactly the mistake being
  corrected here.
- Did not re-run the baseline validation against current (2026-08-09) data
  to check whether the -8281.77 negative finding still holds — the fix
  here doesn't depend on that number changing; the guard is advisory
  regardless of what a fresh baseline run would show, until a config is
  actually promoted through the existing gate.
- Did not audit `_trough_high_vol_override_watch()`'s
  `compounding_blocks_631l` check, which reads
  `compounding_regime_pre_trade_guard["blocked_trades"]` (now always
  empty) as one of several AND-conditions for its own `active` flag. This
  diagnostic is explicitly `"research_only": True,
  "live_execution_effect": "none"` per its own docstring, so losing this
  one AND-condition doesn't affect production; left as a known, minor,
  accepted side effect rather than expanding scope into a second
  diagnostic's exact semantics.
