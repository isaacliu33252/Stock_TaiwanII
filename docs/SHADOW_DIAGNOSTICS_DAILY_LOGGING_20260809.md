# Shadow Diagnostics Daily Logging — 2026-08-09

**Status: shipped, wired into daily pipeline as best-effort steps. Detection-only, no execution/weight impact.**

## Motivation

Three shadow diagnostics built earlier the same day (TSMC concentration
divergence's ADD_0050_INSTEAD guard, adaptive review interval, adaptive
lookback window) all hit the same wall: their backtests were repeatedly
too sparse to validate the mechanism either way (3 trigger events in 6+
years for ADD_0050_INSTEAD; 3 of 7 windows with zero suppressed days for
adaptive review interval). Rather than wait indefinitely on more backfill
data that may not exist, the established pattern already used in this
project for the same problem (`recovery_boost_spillover_gate_shadow_log.py`,
`trough_override_eligibility_shadow_log.py`, both from the 2026-07-16
Fable audit) is to log the mechanism's causal daily decision at live speed,
accumulating real observations going forward.

## What was built

Two new pure-logging daily accumulators, following the exact established
pattern (integration module with `build_shadow_log_row()`/
`append_shadow_log_row()` [JSONL, deduped by date] + a `scripts/run/`
CLI runner + a `BEST_EFFORT_STEP_NAMES` pipeline entry):

- **`group_a_plus/integrations/add_0050_instead_shadow_log.py`** +
  `scripts/run/build_group_a_plus_add_0050_instead_shadow_log.py`: reuses
  `_targets_from_report()` and `_load_narrow_lead_series()` from
  `scripts/evaluate/evaluate_add_0050_instead_of_00631l_shadow.py`
  unmodified, over a 90-day trailing `run_a2118()` window, and logs only
  the last day's row: `narrow_lead`, today's/yesterday's 00631L target
  weight, whether it's increasing, and whether the guard would have
  triggered.
- **`group_a_plus/integrations/adaptive_review_interval_shadow_log.py`** +
  `scripts/run/build_group_a_plus_adaptive_review_interval_shadow_log.py`:
  runs the same 90-day `run_a2118()` window, calls
  `classify_review_interval()` from
  `scripts/evaluate/evaluate_adaptive_review_interval_shadow.py`
  unmodified on today's row, and logs `execution_regime`/`ma_gap`/
  `drawdown`/`tail_risk_score`/`review_interval_days`/`review_interval_label`.
  Deliberately kept the classifier import in the `scripts/run/` runner
  (not the `group_a_plus/integrations/` module) to match this project's
  existing layering convention — sibling modules
  (`recovery_boost_spillover_gate_shadow.py`) take already-computed plain
  data, never import from `scripts/`.

**TSMC breadth (`top5_breadth_snapshot()`) needed no new work** — it was
already added to `daily_signal.py`'s health snapshot earlier the same day,
and `daily_signal.py`'s output is already written to a date-stamped
`results/group_a_plus_live_signal_v2_{stamp}.json` file every day via the
existing `commands["daily_signal"]` pipeline step, so it has been
accumulating daily archived observations since that change landed with
zero further action needed.

Both new steps added to `run_ncf_daily_pipeline.py`'s
`BEST_EFFORT_STEP_NAMES` (a failure here must never block daily_status/
promotion_gate/anything else downstream, matching every other shadow-log
step) immediately after `trough_override_eligibility_shadow_log`.

## Verification

17 new unit tests (11 for `add_0050_instead_shadow_log`, 6 for
`adaptive_review_interval_shadow_log`) covering: correct trigger/no-trigger
classification, insufficient-history/empty-frame `unavailable` handling,
NaN-field cleaning, and JSONL append-dedup-by-date behavior. Both scripts
run end-to-end against real production DB data (redirected output),
producing correctly-classified rows cross-checked by hand against
`classify_review_interval()`'s actual threshold logic. Pipeline
step-order test (`tests/test_run_ncf_daily_pipeline.py`) updated with the
two new step names and matching `--panel`/`BEST_EFFORT_STEP_NAMES`
assertions, following the exact pattern used for every neighboring step.

## Design choices worth remembering

- Kept both new modules' daily-log builder functions taking already-computed
  primitives (target weights + narrow_lead series; frame + interval/label)
  rather than importing the classifier logic themselves — matches this
  project's existing convention of keeping `group_a_plus/integrations/`
  free of `scripts/`-layer dependencies, with the cross-import happening
  only in the `scripts/run/` CLI runner.
- Detection-only, matching every other shadow-log step in this pipeline —
  never touches target weights, execution guards, or the live signal.
- These logs are deliberately NOT reprocessed into a promotion decision by
  this task; they exist purely to grow the future validation dataset.
  Revisit once enough real trigger events (ADD_0050_INSTEAD) or enough real
  review-interval/regime-transition coincidences (adaptive review interval)
  accumulate to re-run the backtests with materially more evidence.
