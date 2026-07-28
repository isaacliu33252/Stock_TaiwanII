# Daily Pipeline: Same-Method-Baseline Governance Chain Crash — Root Cause and Fix — 2026-07-27

## Status

**Root-caused, fixed, and verified against a real full pipeline run for
today's date stamp. Does not touch a2118's live target weights.** This is
Thread 5 of `GROUP_A_PLUS_20260727_SESSION_HANDOFF_INDEX.md`, opened after
the user asked to manually trigger today's data download ("下載今天的
資料") and NCF training ("開始訓練") ahead of the 23:00/23:30 scheduled
run, and the training run crashed partway through.

## Origin

User requested a manual run of the exact commands the Windows Task
Scheduler runs nightly (`run_fetch.bat` then `run_daily.bat`, both of
which just `wsl bash -lc` into `scripts/run/run_ncf_daily_pipeline.py`).
The fetch (`--only-refresh`, 18 steps) completed cleanly. The training run
(`--skip-refresh`, 72 steps at the time) crashed at step 13/72 with
`EXIT_CODE=1` -- masked at first because the wrapper command appended
`echo "EXIT_CODE=$?"` as a separate command, so the background-task
notification reported the wrapper's own exit code (0, from `echo`) rather
than the real pipeline failure. Caught by reading the actual output log
rather than trusting the notification summary.

## Root cause

The crash was in `ncf_panel_external_feature_sensitivity_governance`
(`scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py`),
with `FileNotFoundError` on
`results/ncf_panel_same_method_baseline_manifest_20260727.json`.

Traced with `git log -S`/`grep` across `scripts/run/run_ncf_daily_pipeline.py`:
three files --
`ncf_panel_same_method_baseline_manifest_{stamp}.json`,
`ncf_panel_drift_model_set_isolation_report_{stamp}.json`, and
`ncf_panel_drift_no_tabnet_baseline_vs_{stamp}.json` -- were referenced as
**inputs** by automated pipeline steps (`ncf_panel_external_feature_sensitivity_governance`,
`ncf_panel_drift_remediation_plan`), but **no automated step ever
generated them**. Confirmed via `git log -S` on the generating scripts'
filenames (`build_ncf_panel_same_method_baseline_manifest.py`,
`build_ncf_panel_drift_model_set_isolation_report.py`,
`evaluate_ncf_panel_drift.py` with the no-TabNet baseline) -- zero matches
in `run_ncf_daily_pipeline.py`'s `commands` dict. Historical copies of
these files only exist for dates someone happened to run the generating
commands by hand that same day (`_20260722.json`, `_20260725.json` --
matching `docs/HANDOFF_GROUPA_PLUS_EXTERNAL_SENSITIVITY_OBSERVATION_20260722.md`'s
"本輪實際重建的 outputs" section, which shows these were manual
reconstructions, not automated output). On any day nobody did that
manual step, the automated pipeline would crash here -- 2026-07-27 is
simply the first day this was caught in the act rather than quietly
patched around.

**Second, compounding problem**: `run_pipeline_commands()` aborts the
*entire remaining pipeline* on the first step outside
`BEST_EFFORT_STEP_NAMES` that raises. This governance chain was not in
that set, so its crash also prevented every step after it from running --
including `daily_signal`, `execution_plan`-adjacent steps,
`alert_state`, and `daily_status` for that day. This is despite the
chain itself having zero bearing on a2118's live signal: the manifest's
own `permissions` block explicitly records
`"promote_to_live": false, "training_allowed": false,
"target_weight_change_allowed": false` -- it exists purely to track a
*different* candidate model's TabNet-vs-no-TabNet promotion-gate status
(a research/governance question, not a live-trading one).

## Fix

Both problems fixed in `scripts/run/run_ncf_daily_pipeline.py`:

**1. Wire in the three missing generation steps**, inserted right after
`ncf_panel_drift_remediation_plan_initial` and before
`external_sensitivity_observation_log` (so both of that chain's
consumers have the file by the time they run):

- `ncf_panel_drift_no_tabnet_baseline_vs_today`: `evaluate_ncf_panel_drift.py`
  comparing the fixed `ncf_00631l_panel_latest_20260630_no_tabnet.csv`
  baseline against today's real panel (`ncf_00631l_panel_latest_{stamp}.csv`,
  already produced earlier in the same run by the `ncf_00631l` step).
- `ncf_panel_drift_model_set_isolation_report`: `build_ncf_panel_drift_model_set_isolation_report.py`,
  combining that with the already-automated `ncf_panel_drift_active_vs_{stamp}.json`
  (from the pre-existing `ncf_panel_drift` step) and the permanently-static
  `ncf_panel_drift_tabnet_vs_no_tabnet_20260630.json` (both sides pinned
  to 2026-06-30, never changes).
- `ncf_panel_same_method_baseline_manifest`: `build_ncf_panel_same_method_baseline_manifest.py`,
  combining the above two plus the static `ncf_00631l_panel_latest_20260630.csv`
  /`ncf_00631l_panel_latest_20260630_no_tabnet.csv`/`ncf_00631l_latest_20260630_no_tabnet.json`
  baseline trio.

None of these three needed new computation logic -- all three generating
scripts already existed (built in the 2026-07-22 session) and just needed
their existing CLI wired into the daily pipeline with today's `stamp`
instead of being run by hand.

**2. Mark the whole chain `BEST_EFFORT_STEP_NAMES`** (defense in depth,
matching the file's own established pattern for ~40 other research/
governance-only steps, each with its own justifying comment): the 3 new
steps above, plus the 3 pre-existing consumers
(`ncf_panel_external_feature_sensitivity_governance`,
`ncf_panel_drift_remediation_plan`, `panel_drift_resolution_progress`).
Even if this chain breaks again for some unrelated future reason, it will
now log-and-continue instead of aborting `daily_signal`/`execution_plan`/
`alert_state`/`daily_status` downstream of it.

Both changes are additive-only to the pipeline definition: no existing
step's command arguments, order relative to each other, or behavior
changed; only new steps were inserted and new names added to an existing
frozenset.

## Tests

`tests/test_run_ncf_daily_pipeline.py`:
- Updated the two `list(commands) == [...]` full-order assertions (one per
  test function) to include the 3 new step names at their insertion point.
- Added assertions verifying each new command's script path and key
  arguments (`--baseline-panel`/`--candidate-panel`/`--output` for the
  drift-audit step; `--original-vs-today`/`--original-vs-no-tabnet`/
  `--no-tabnet-vs-today` for the isolation-report step; all 6 arguments
  for the manifest step).
- Added a loop asserting all 6 governance-chain step names (3 new + 3
  pre-existing) are present in `module.BEST_EFFORT_STEP_NAMES`.

`tests/test_run_ncf_daily_pipeline.py`: 19/19 passing.
`-k "run_ncf_daily_pipeline or panel_drift or same_method"`: 36/36 passing.
Full repo suite: 1457 passed, 9 skipped, 0 failed (up from 1452 passed
earlier the same day -- the +5 are this thread's new assertions plus
Thread 3's calibration tests from earlier in the day).

## Verification against a real run

Re-ran the actual pipeline for the same date stamp the crashed run had
used (`--date-stamp 20260727 --ohlcv-target-date 2026-07-27 --skip-refresh
--refresh-external-cache`, i.e. resuming that day's run rather than
starting a fresh one under the now-rolled-over wall-clock date):

**75/75 steps completed, `EXIT_CODE=0`.** Confirmed via
`report/group_a_plus/latest/alert_state.json` that the specific alert
last night's crash had produced (`ops_health_pipeline`, **high**
severity, "Ops health: pipeline manifest error") is now `resolved`. Two
new alerts emitted this run (`specialist_router_semiconductor_risk`
medium, `tsmc_led_narrow_reference` low -- both pre-existing diagnostic
alert types, unrelated to this fix). `ncf_panel_stale` and 3 other
previously-known warnings remain present but suppressed (unchanged
severity, matching `GROUP_A_PLUS_OPS_HEALTH_PANEL_DRIFT_20260727.md`'s
earlier-in-the-day finding -- not something this fix was meant to
address).

Today's (2026-07-27) live signal, successfully regenerated:
- `00631L.TW`: UP, `prob_up=0.637`
- `00632R.TW`: DOWN, `prob_up=0.2198`
- Deleverage commentary: INACTIVE (NCF H=20 prob=0.455, below trigger)
- `crash_risk_alert`: `watch_level=medium`, `score=2`, not active
- `signal_alignment`: mixed, dominant=bullish

## What was NOT done

- Did not investigate why the `ncf_panel_external_feature_sensitivity_governance`
  chain's own underlying finding (`status: blocked_observation_required`,
  per the 2026-07-22 handoff) has or hasn't progressed since -- out of
  scope; this thread only fixed the automation gap, not the governance
  question itself.
- Did not backfill the missing same-day files for any date between
  2026-07-22 and 2026-07-27 (e.g. 07-23/07-24/07-26) -- only today's run
  was fixed and re-verified going forward.
- Did not investigate whether `external_sensitivity_observation_log`
  (which optionally reads the same manifest but already handles a missing
  one gracefully via its own `if not path.exists()` check) needs the same
  best-effort treatment -- left as-is since it was not the source of any
  crash and already degrades safely.
- Did not change `strategy.json`'s pinned NCF panel path (`20260716`) --
  unrelated to this fix; see `GROUP_A_PLUS_OPS_HEALTH_PANEL_DRIFT_20260727.md`
  for that separate, already-closed thread from earlier the same day.

## Reproduction

```bash
# Full relevant test coverage
python3 -m pytest tests/test_run_ncf_daily_pipeline.py -q
python3 -m pytest tests/ -k "run_ncf_daily_pipeline or panel_drift or same_method" -q

# Re-run today's pipeline end to end (matches run_daily.bat's flags, but
# with an explicit date stamp instead of recomputing "today" from the
# wall clock -- use this form when resuming a specific day's run rather
# than starting a fresh one)
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260727 --ohlcv-target-date 2026-07-27 \
  --skip-refresh --refresh-external-cache
```

## Files referenced

Modified:
- `scripts/run/run_ncf_daily_pipeline.py` -- 3 new `commands[...]` entries,
  6 names added to `BEST_EFFORT_STEP_NAMES`.
- `tests/test_run_ncf_daily_pipeline.py` -- order assertions updated, new
  content/best-effort-membership assertions added.

Read/analyzed, not modified:
- `scripts/evaluate/build_ncf_panel_same_method_baseline_manifest.py`,
  `build_ncf_panel_drift_model_set_isolation_report.py`,
  `evaluate_ncf_panel_drift.py` (all pre-existing, unchanged).
- `docs/HANDOFF_GROUPA_PLUS_EXTERNAL_SENSITIVITY_OBSERVATION_20260722.md`
  (source of the original, never-automated manual commands).
- `report/group_a_plus/latest/alert_state.json`,
  `strategy.json` (verification only).

Output (from the real verification run, not committed to any pipeline):
- `results/ncf_panel_drift_no_tabnet_baseline_vs_20260727.json`
- `results/ncf_panel_drift_model_set_isolation_report_20260727.json`
- `results/ncf_panel_same_method_baseline_manifest_20260727.json`
