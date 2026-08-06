# Group A+ Daily Artifact Integrity Handoff - 2026-07-30

## Context

The project had several recurring artifact-governance failures:

- `execution_plan.json` previously lost real production state after a latest pointer overwrite.
- `golden1_0531` release payloads were historically overwritten by unrelated model/pipeline runs.
- NCF panel drift refresh decisions were moved from manual review into `ncf_panel_refresh_recommendation`, but the daily pipeline still had no single check proving the latest recommendation artifact exists.
- `decision_confidence` calibration depends on DFL realized labels; after 2026-07-30 work, the data contract can report readiness, but the daily run still needed a guardrail that surfaces missing readiness blocks.

This change adds a repeatable daily artifact-integrity report. It is diagnostic/governance only and cannot create orders or change target weights.

## Implemented

### New daily integrity report

Added `scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py`.

It checks:

- `live_signal` exists and exposes `actual_data_date`.
- `execution_plan` exists and its `actual_data_date` matches `live_signal.actual_data_date`.
- `execution_plan` has a point-in-time snapshot for the execution plan actual date.
- `golden1_0531_release` has a point-in-time snapshot for `2026-05-31`.
- `ncf_panel_refresh_recommendation` exists and exposes `summary.recommendation`.
- `ncf_decision_calibration` exists and exposes `calibration_pair_readiness.status == "available"`.

Severity policy:

- `error`: missing live/execution plan, missing required dates, stale execution plan vs live signal, missing required PIT snapshots.
- `warning`: missing NCF panel refresh recommendation, missing/malformed calibration readiness, or calibration readiness not fully available.
- `ok`: all checks pass.

The report writes:

- `report/group_a_plus/latest/daily_artifact_integrity.json`
- `report/group_a_plus/latest/daily_artifact_integrity.md`
- history JSON under `report/group_a_plus/daily_artifact_integrity/history/`

Decision boundary is explicit in the payload:

- `policy = diagnostic_only_no_strategy_change_no_weight_change`
- `target_weight_change_allowed = false`
- `creates_orders = false`

### Daily pipeline wiring

Updated `scripts/run/run_ncf_daily_pipeline.py`.

New step:

- `daily_artifact_integrity`

Location:

- after `ncf_decision_calibration_shadow`
- before `research_shadow_decision_snapshot` and `daily_status`

The step is included in `BEST_EFFORT_STEP_NAMES`, because it is governance/reporting only and should not block live signal generation.

### Tests

Added `tests/test_build_group_a_plus_daily_artifact_integrity.py`.

Coverage:

- healthy artifacts plus PIT snapshots produce `status == "ok"`.
- stale execution plan date plus missing PIT snapshots produce `status == "error"`.
- missing realized-label readiness produces `status == "warning"`.

Updated `tests/test_run_ncf_daily_pipeline.py`.

Coverage:

- command order includes `daily_artifact_integrity`.
- command arguments point to live signal, latest execution plan, latest NCF refresh recommendation, dated NCF decision calibration output, and latest daily artifact integrity output.
- `daily_artifact_integrity` is best-effort.

## Real Run On Current Workspace

Command:

```bash
python3 scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py \
  --check-date 2026-07-30 \
  --ncf-decision-calibration results/ncf_decision_calibration_shadow_readiness_check_after_refresh_20260730.json
```

Result:

- Output: `report/group_a_plus/latest/daily_artifact_integrity.json`
- Status: `warning`
- Errors: none
- Warning: `NCF panel refresh recommendation artifact missing`

Passing checks from the real report:

- `live_signal.actual_data_date = 2026-07-27`
- `execution_plan.actual_data_date = 2026-07-27`
- execution plan PIT snapshot exists:
  `results/point_in_time_artifacts/execution_plan/2026/07/27/execution_plan_20260728T074526_c34b5c7635ad.json`
- golden1 release PIT snapshot exists:
  `results/point_in_time_artifacts/golden1_0531_release/2026/05/31/golden1_0531_release_20260730T084600_03a7ee22f97e.json`
- DFL calibration pair readiness is available with `total_pairs = 4803`.

The current warning is expected because `report/group_a_plus/latest/ncf_panel_refresh_recommendation.json` does not currently exist in this workspace. The daily pipeline is now wired to create it on future runs through the existing `ncf_panel_refresh_recommendation` step.

## Verification

Focused tests:

```bash
python3 -m pytest tests/test_build_group_a_plus_daily_artifact_integrity.py tests/test_run_ncf_daily_pipeline.py -q
```

Result:

- `24 passed in 15.78s`

## Follow-Up Candidates

- Add `daily_artifact_integrity` as an input to `check_group_a_plus_daily_status.py`, so final daily status can display artifact-integrity warnings directly.
- Add PIT coverage checks for additional latest pointers after their artifact names/as-of semantics are standardized.
- Make the NCF panel refresh recommendation script also write a dated `results/` copy for easier replay beside its latest pointer.

## Follow-Up Completed: Daily Status Integration

Later on 2026-07-30, the first follow-up was implemented.

### Implemented

Updated `scripts/misc/check_group_a_plus_daily_status.py`:

- Added optional `--daily-artifact-integrity`.
- Added `_artifact_integrity_summary()`.
- Added a `daily_artifact_integrity` row to daily status checks when the path is provided.
- Status mapping:
  - integrity `error` -> daily status `block`
  - integrity `warning` or missing report -> daily status `warn`
  - integrity `ok` -> daily status `ok`
- Added `group_a_plus.daily_artifact_integrity` summary to the JSON report.
- Added an `Artifact Integrity` markdown section.

Updated `scripts/run/run_ncf_daily_pipeline.py`:

- The `daily_status` command now passes:
  `--daily-artifact-integrity report/group_a_plus/latest/daily_artifact_integrity.json`
- `daily_status_final` inherits the same argument because it is copied from `daily_status`.

Added test coverage:

- `tests/test_check_group_a_plus_daily_status.py`
  - verifies that an integrity warning appears in `checks`, pulls `overall_status` to `warn`, and renders in markdown.
- `tests/test_run_ncf_daily_pipeline.py`
  - verifies the pipeline passes `--daily-artifact-integrity`.

### Real Run

Command:

```bash
python3 scripts/misc/check_group_a_plus_daily_status.py \
  --mode live \
  --live-signal report/group_a_plus/latest/live_signal.json \
  --execution-plan report/group_a_plus/latest/execution_plan.json \
  --daily-artifact-integrity report/group_a_plus/latest/daily_artifact_integrity.json \
  --check-date 2026-07-30 \
  --status-stage pre_promotion \
  --output-prefix results/group_a_plus_daily_status_artifact_integrity_check_20260730 \
  --canonical-output '' \
  --skip-managed-report
```

Result:

- `results/group_a_plus_daily_status_artifact_integrity_check_20260730.json`
- `results/group_a_plus_daily_status_artifact_integrity_check_20260730.md`
- `Overall: warn`
- Artifact integrity check row:
  `daily_artifact_integrity: warn - status=warning, errors=0, warnings=1`

The warning source remains the same known issue from the real integrity report:

- `NCF panel refresh recommendation artifact missing`

### Verification

```bash
python3 -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py -q
```

Result:

- `48 passed in 16.72s`

## Follow-Up Completed: NCF Refresh Recommendation Snapshot + Backfill

Later on 2026-07-30, the remaining live warning from `daily_artifact_integrity` was addressed.

### Implemented

Updated `scripts/evaluate/build_ncf_panel_refresh_recommendation.py`:

- Added `--snapshot-output`.
- `write_outputs()` now writes:
  - latest JSON
  - latest markdown
  - optional dated/replay JSON snapshot
  - existing history JSON

Updated `scripts/run/run_ncf_daily_pipeline.py`:

- The `ncf_panel_refresh_recommendation` step now writes:
  `results/ncf_panel_refresh_recommendation_<stamp>.json`
- It still writes latest pointers:
  - `report/group_a_plus/latest/ncf_panel_refresh_recommendation.json`
  - `report/group_a_plus/latest/ncf_panel_refresh_recommendation.md`

Added test coverage:

- `tests/test_build_ncf_panel_refresh_recommendation.py`
  - verifies `write_outputs()` writes latest JSON, markdown, history, and snapshot output.
- `tests/test_run_ncf_daily_pipeline.py`
  - verifies pipeline command passes `--snapshot-output`.

### Backfill

Command:

```bash
python3 scripts/evaluate/build_ncf_panel_refresh_recommendation.py \
  --drift-audit results/ncf_panel_drift_active_vs_20260725_outcome_aware_20260730.json \
  --output report/group_a_plus/latest/ncf_panel_refresh_recommendation.json \
  --output-md report/group_a_plus/latest/ncf_panel_refresh_recommendation.md \
  --snapshot-output results/ncf_panel_refresh_recommendation_latest_backfill_20260730.json
```

Result:

- Recommendation: `keep_current_pin`
- Reason: `candidate_not_more_accurate_on_resolved_outcomes`
- Low-accuracy columns:
  - `h20_prob_up`
  - `prob_fwd_mdd_gt5_h20`
  - `prob_fwd_gain_gt5_h20`

Generated:

- `report/group_a_plus/latest/ncf_panel_refresh_recommendation.json`
- `report/group_a_plus/latest/ncf_panel_refresh_recommendation.md`
- `results/ncf_panel_refresh_recommendation_latest_backfill_20260730.json`

### Integrity Recheck

Command:

```bash
python3 scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py \
  --check-date 2026-07-30 \
  --ncf-decision-calibration results/ncf_decision_calibration_shadow_readiness_check_after_refresh_20260730.json
```

Result:

- `daily_artifact_integrity.status = ok`
- errors: none
- warnings: none

### Daily Status Recheck

Command:

```bash
python3 scripts/misc/check_group_a_plus_daily_status.py \
  --mode live \
  --live-signal report/group_a_plus/latest/live_signal.json \
  --execution-plan report/group_a_plus/latest/execution_plan.json \
  --daily-artifact-integrity report/group_a_plus/latest/daily_artifact_integrity.json \
  --check-date 2026-07-30 \
  --status-stage pre_promotion \
  --output-prefix results/group_a_plus_daily_status_artifact_integrity_check_20260730 \
  --canonical-output '' \
  --skip-managed-report
```

Result:

- `daily_artifact_integrity: ok - status=ok, errors=0, warnings=0`
- Overall remains `warn`, but no longer because of artifact integrity. Remaining warning sources:
  - `dfl_advisory_frozen_input_staleness`
  - `promotion_gate_deployment_summary`

### Verification

```bash
python3 -m pytest tests/test_build_ncf_panel_refresh_recommendation.py tests/test_run_ncf_daily_pipeline.py -q
```

Result:

- `25 passed in 16.05s`
