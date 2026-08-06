# GroupA+ Decision Confidence Realized-Label Readiness Handoff - 2026-07-30

## Status

Completed. The original concern is directionally valid, but the precise root
cause had changed since 2026-07-27:

- The DFL evaluator code already has a `calibration_pairs` export with
  realized labels.
- The current stable DFL artifact in the workspace did not yet contain that
  field, so downstream calibration could still silently operate without the
  realized-label foundation.

This session added a machine-readable readiness check to the
`ncf_decision_calibration` shadow report and regenerated the main stable DFL
shadow artifact so the current workspace now has realized-regret labels.

No production weight, guard, live signal, or execution-plan behavior was
changed.

## Starting Point

User asked whether this was reasonable:

- Two `decision_confidence` calibration attempts had failed OOS:
  pooled/regime-non-migration and `total_risk_score` regime-conditioned.
- Rather than trying more calibration algorithms, the better priority might be
  fixing the DFL evaluator's realized-label export so calibration can be based
  on true outcomes rather than a rank proxy.

Verification found:

- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py` already
  defines `_build_calibration_pairs(...)`.
- `evaluate_window()` already returns a `calibration_pairs` key.
- Tests already cover:
  - cold-start days are excluded;
  - KEEP is excluded;
  - dates without realized labels are skipped;
  - `total_risk_score` is attached when features are passed.
- `GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md` documents the
  2026-07-27 implementation and OOS rejection.

But the stable current artifact was stale:

```text
results/a2118_decision_focused_action_shadow_dfl_main_latest.json
```

Before refresh, inspection showed:

- 7 result windows.
- `calibration_pairs` key missing from sampled windows.
- `calibration_pair_readiness = missing_calibration_pairs`.
- `0/0` realized labels across `0/7` windows.

## Decision

Do not add another calibration algorithm.

Instead:

1. Make realized-label export availability explicit in the shadow calibration
   report.
2. Regenerate the stable DFL main artifact using the current evaluator, so the
   workspace artifact actually carries calibration pairs.
3. Keep empirical probability calibration formally closed as
   `closed_failed_oos`; this work is data-readiness/governance only.

## Code Changes

Files changed:

- `group_a_plus/integrations/ncf_decision_calibration.py`
- `scripts/evaluate/evaluate_ncf_decision_calibration.py`
- `tests/test_ncf_decision_calibration.py`

### Readiness Summary

Added:

```python
calibration_pair_readiness_summary(dfl_shadow_path)
```

It reports:

- `status`
  - `missing_dfl_shadow`
  - `missing_calibration_pairs`
  - `partial_realized_labels`
  - `available`
- `window_count`
- `windows_with_calibration_pairs_key`
- `total_pairs`
- `pairs_with_realized_regret`
- `pairs_with_total_risk_score`
- per-action pair counts
- examples of missing realized labels if present
- `recommended_action`

Purpose:

- Distinguish a stale/pre-2026-07-27 DFL artifact from a current artifact
  containing true realized-regret labels.
- Prevent downstream shadow calibration from silently looking normal when the
  realized-label data foundation is missing.

### Calibration Shadow Output

`scripts/evaluate/evaluate_ncf_decision_calibration.py` now prints and writes:

```json
"calibration_pair_readiness": {...}
```

It also includes the existing governance status in the output:

```json
"calibration_governance": {
  "status": "closed_failed_oos",
  ...
}
```

Important boundary:

- This does not turn on `--use-calibration-model`.
- `decision_confidence` remains a rank proxy by default.
- The empirical calibration path remains opt-in research reproduction only.

## Artifact Refresh

Command run:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.0005 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.75 \
  --turnover-cap 0.05 \
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_backfill_2020_20260716.csv:out_of_sample,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:out_of_sample,live_2024_2026:2024-01-02:2026-07-15:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:2026-07-15:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_dfl_main_latest.json
```

Result:

```text
Triple-pass windows: 7/7
total_candidate_non_keep_days: 0
```

After refresh:

- `calibration_pair_readiness = available`
- `4803/4803` calibration pairs have realized labels.
- `7/7` windows have `calibration_pairs`.
- All pairs include `total_risk_score` where available through the evaluator's
  feature attachment path.

Window pair counts:

- `covid_2020`: 492 pairs
- `inflation_2022`: 498 pairs
- `live_2024_2026`: 1536 pairs
- `active_2025_2026`: 840 pairs
- `2017_bull`: 459 pairs
- `2018_correction`: 495 pairs
- `2019_recovery`: 483 pairs

Important observation:

- The refreshed artifact currently has `total_candidate_non_keep_days = 0`,
  so the historical selected-candidate rank distribution is empty.
- This reinforces the existing governance boundary: `decision_confidence`
  should not be interpreted as a calibrated probability or production gate.

## Validation

Focused tests:

```bash
python3 -m pytest \
  tests/test_ncf_decision_calibration.py \
  tests/test_evaluate_a2118_decision_focused_action_shadow.py \
  tests/test_run_ncf_daily_pipeline.py \
  -q
```

Result:

```text
71 passed
```

Additional focused test run:

```bash
python3 -m pytest tests/test_ncf_decision_calibration.py tests/test_run_ncf_daily_pipeline.py -q
```

Result:

```text
50 passed
```

Readiness check before refresh:

```text
calibration_pair_readiness: missing_calibration_pairs
calibration_pairs: 0/0 realized labels across 0/7 windows
```

Readiness check after refresh:

```text
calibration_pair_readiness: available
calibration_pairs: 4803/4803 realized labels across 7/7 windows
```

## Files Touched In This Session

- `group_a_plus/integrations/ncf_decision_calibration.py`
- `scripts/evaluate/evaluate_ncf_decision_calibration.py`
- `tests/test_ncf_decision_calibration.py`
- `results/a2118_decision_focused_action_shadow_dfl_main_latest.json`
- `results/ncf_decision_calibration_shadow_readiness_check_20260730.json`
- `results/ncf_decision_calibration_shadow_readiness_check_after_refresh_20260730.json`
- `handoff/2026-07/GROUP_A_PLUS_DECISION_CONFIDENCE_LABEL_READINESS_HANDOFF_20260730.md`

## Residual Risk / Follow-Up

- Full repo test suite was not run.
- The DFL artifact refresh produced 0 non-KEEP candidate days under the current
  command/config. That should be treated as a separate DFL behavior observation
  if it matters operationally; it is not a reason to turn calibration on.
- Any future attempt to revive probability calibration should first use the
  readiness summary to confirm realized labels are available, then require a
  fresh OOS validation set. Do not keep iterating calibration variants against
  the same 2017/2018/2019 OOS slice.

