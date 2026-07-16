# A21.18 DFL Shadow Ops and Extended Backtest Handoff

Date: 2026-07-14
Status: keep as shadow/advisory only; do not promote to live allocation or execution-plan auto changes

## Executive Conclusion

The A21.18 decision-focused learning (DFL) finite-action candidate remains useful as a daily shadow/advisory signal, but it is not ready for automatic portfolio changes.

Current recommendation:

- Keep DFL as `shadow_only_no_auto_weight_change`.
- Show it in daily status and ops health.
- Do not wire DFL into live target weights.
- Do not let DFL modify `execution_plan.json`.
- Reassess only after more live shadow active dates accumulate.

The expanded tests show the DFL signal is not a broad always-on alpha model. It behaves more like a sparse `CAP10` risk-control tool for selected 00631L correction/re-risk timing windows.

## Fixed Candidate

The fixed candidate intentionally uses finite actions and stabilizers:

```text
actions = KEEP,NO_ADD,CAP10,REENTER
edge_threshold = 0.0005
adjustment_fraction = 0.75
turnover_cap = 0.05
stateful_actions = true
require_panel_signal = true
regret_clip = 0.02
min_train_days = 60
reenter_edge_threshold = -0.0005
```

Target:

```text
action_regret = Utility(action) - Utility(A21.18 / KEEP)

Utility =
  log(final wealth)
  - lambda * MDD
  - gamma * turnover
  - eta * missed rebound
```

Policy:

- Only finite actions are allowed.
- No arbitrary continuous weights.
- Model output is clipped by `regret_clip`.
- Partial adjustment and turnover control remain enabled.
- Any production use remains advisory only.

## Implemented This Round

DFL daily advisory:

- `scripts/run/build_a2118_dfl_advisory.py`
- output: `report/group_a_plus/latest/a2118_dfl_advisory.json`
- policy: `advisory_only_no_auto_weight_change`

DFL active-date audit:

- `scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py`
- tests: `tests/test_evaluate_a2118_dfl_active_date_audit.py`
- audits only non-KEEP active dates
- estimates per-1M notional cost
- checks panel alignment, edge threshold, clipping, price availability, action allowed, finite action set, and minimum trade notional
- treats stateful turnover-vs-A21.18 as a warning, not a hard failure, because non-KEEP decision rows store A21.18 base weight rather than prior live shadow allocation

Daily status integration:

- `scripts/misc/check_group_a_plus_daily_status.py`
- tests: `tests/test_check_group_a_plus_daily_status.py`
- added `--dfl-active-date-audit`
- Markdown now includes:
  - DFL advisory
  - DFL active-date audit conclusion
  - active days
  - hard-check status
  - warning days
  - existing guard overlap days
  - estimated cost bps per 1M

Pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py`
- tests: `tests/test_run_ncf_daily_pipeline.py`
- added best-effort step: `dfl_active_date_audit`
- default inputs:
  - `results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json`
  - `results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json`
- default output:
  - `results/a2118_dfl_active_date_audit_{date_stamp}.json`
- daily status consumes that output via `--dfl-active-date-audit`

Ops health integration:

- `group_a_plus/operations/ops_health.py`
- tests: `tests/test_group_a_plus_ops_health.py`
- added `artifact_health.dfl_active_date_audit`
- warnings:
  - `dfl_active_date_audit_missing`
  - `dfl_active_date_audit_unreadable`
  - `dfl_active_date_audit_not_research_only`
  - `dfl_active_date_audit_hard_checks_not_passing`
  - `dfl_active_date_audit_policy_not_shadow_only`

Latest real ops-health check:

```json
{
  "status": "ok",
  "audit_status": "research_only",
  "conclusion": "passes_replay_audit_with_warnings_shadow_only",
  "policy": "shadow_only_no_auto_weight_change",
  "active_days": 7,
  "all_checks_pass": true,
  "warning_days": 3,
  "existing_guard_overlap_days": 0,
  "total_estimated_cost_bps": 8.074904151886141
}
```

## Backtest Matrix

### 1. Fixed 7-window run

Output:

- `results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json`
- `results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json`
- `results/a2118_dfl_active_date_audit_20260714.json`

Windows:

- `covid_2020`
- `inflation_2022`
- `live_2024_2026`
- `active_2025_2026`
- `2017_bull`
- `2018_correction`
- `2019_recovery`

Result:

- triple-pass: `7/7`
- total final delta: about `+14,142`
- total Sharpe delta: about `+0.0350`
- active days: `7`
- all active actions: `CAP10`
- overlap with existing guards: `0/7`
- hard audit checks: pass
- warning days: `3`
- estimated cost: `8.0749 bps / 1M`
- audit conclusion: `passes_replay_audit_with_warnings_shadow_only`

Active dates:

- `2025-01-13`
- `2025-01-15`
- `2025-02-21`
- `2018-07-27`
- `2018-10-01`
- `2018-10-02`
- `2018-10-04`

Interpretation:

- Positive and clean enough for shadow monitoring.
- Too sparse to promote.
- It is not duplicated by volatility or A21.18 extreme-warning guards in this fixed 7-window evaluation.

### 2. Rolling half-year windows

Output:

- `results/a2118_decision_focused_action_shadow_fixed_rolling_half_20260714.json`
- `results/a2118_decision_focused_action_overlap_fixed_rolling_half_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_half_20260714.json`

Result:

- windows: `10`
- triple-pass: `10/10`
- active days: `15`
- all active actions: `CAP10`
- activity only in `2018_h2`
- `2018_h2` delta:
  - final: `+4,356`
  - Sharpe: `+0.0449`
  - MDD: `+0.0042`
- overlap: `6/15`
- hard audit checks: pass
- warning days: `13`
- estimated cost: `18.6806 bps / 1M`
- audit conclusion: `review_required_shadow_only`

Interpretation:

- Supports the view that DFL is a sparse correction-period CAP10 tool.
- Existing high-vol guard covers part of the 2018H2 cluster, but not all of it.
- The overlap means it is not purely independent in this expanded slicing.

### 3. Rolling quarter windows

Output:

- `results/a2118_decision_focused_action_shadow_fixed_rolling_quarter_20260714.json`
- `results/a2118_decision_focused_action_overlap_fixed_rolling_quarter_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_quarter_20260714.json`

Result:

- windows: `19`
- triple-pass: `19/19`
- active days: `0`
- all windows: `KEEP`
- audit conclusion: `review_required_shadow_only`

Interpretation:

- This is low-information because `min_train_days=60` consumes most of a quarter.
- Do not use this result as proof that DFL has no signal.
- It mainly confirms that quarterly windows are too short for this model configuration.

### 4. Rolling 6-month windows, quarterly step

Output:

- `results/a2118_decision_focused_action_shadow_fixed_rolling_6m_qstep_20260714.json`
- `results/a2118_decision_focused_action_overlap_fixed_rolling_6m_qstep_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_6m_qstep_20260714.json`

Result:

- windows: `17`
- triple-pass: `16/17`
- all active actions: `CAP10`
- active days: `35`
- total final delta across windows: `+21,631.89`
- total Sharpe delta across windows: `+0.3693`
- overlap: `7/35`
- hard audit checks: pass
- warning days: `27`
- estimated cost: `42.8887 bps / 1M`
- audit conclusion: `review_required_shadow_only`

Active windows:

- `2017q4_2018q1`
  - active days: `3`
  - final delta: `+1,034.72`
  - Sharpe delta: `+0.0442`
  - MDD delta: `+0.0033`
- `2018_q3q4`
  - active days: `15`
  - final delta: `+4,355.84`
  - Sharpe delta: `+0.0449`
  - MDD delta: `+0.0042`
- `2018q4_2019q1`
  - active days: `13`
  - final delta: `-70.95`
  - Sharpe delta: `-0.0010`
  - MDD delta: `0.0000`
  - this is the one failed window
- `2025q4_2026q1`
  - active days: `4`
  - final delta: `+16,312.28`
  - Sharpe delta: `+0.2811`
  - MDD delta: `+0.0151`

Active months:

```text
2018-01: 3
2018-09: 3
2018-10: 11
2018-12: 1
2019-02: 2
2019-03: 11
2026-02: 3
2026-03: 1
```

Interpretation:

- This is the most informative expanded validation.
- It introduces one small negative window, so promotion is not justified.
- It also shows that DFL can activate outside 2018, notably `2025q4_2026q1`.
- The `2025q4_2026q1` gain is large relative to the rest, so concentration risk remains.

## Commands Used

Fixed 7-window rerun:

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
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json
```

Overlap:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_overlap.py \
  --input results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json \
  --output results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json
```

Audit:

```bash
python3 scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py \
  --input results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json \
  --overlap results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json \
  --output results/a2118_dfl_active_date_audit_20260714.json
```

Additional expanded windows were run with the same fixed DFL parameters and different `--windows` definitions:

- half-year non-overlapping
- quarter
- 6-month with quarterly step

## Verification

New/updated tests run during this work:

```bash
pytest -q tests/test_evaluate_a2118_dfl_active_date_audit.py
```

Result:

- `4 passed`

```bash
pytest -q tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_evaluate_a2118_dfl_active_date_audit.py
```

Result:

- `23 passed`

```bash
pytest -q tests/test_group_a_plus_ops_health.py
```

Result:

- `24 passed`

Compile checks:

```bash
python3 -m py_compile \
  scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py \
  scripts/misc/check_group_a_plus_daily_status.py \
  scripts/run/run_ncf_daily_pipeline.py \
  group_a_plus/operations/ops_health.py
```

Result:

- passed

## Current Daily Advisory Snapshot

Latest built advisory:

- `report/group_a_plus/latest/a2118_dfl_advisory.json`

Latest snapshot at time of this handoff:

- `as_of`: `2026-07-09`
- action: `KEEP`
- advisory active: `false`
- recommended action: `keep_a2118`
- policy: `advisory_only_no_auto_weight_change`

Predicted regrets for latest advisory snapshot:

- `KEEP`: `0`
- `NO_ADD`: about `+0.000347`
- `CAP10`: about `-0.001380`
- `REENTER`: `0`

Because selected action is `KEEP`, there is no live allocation effect.

## Important Interpretation Notes

Do not treat `turnover_proxy_above_cap` warnings as direct proof that the backtest violated its turnover cap.

Reason:

- In stateful mode, non-KEEP decision rows record `base_00631l_weight` from A21.18 and `final_00631l_weight` from the shadow overlay.
- The audit's turnover proxy is therefore a deviation proxy versus A21.18.
- It is not exact same-day model turnover from prior shadow allocation.

This is why audit uses:

- hard checks for deployability constraints
- warning checks for deviation/turnover proxy

## Do Not Promote Conditions

Do not promote DFL while any of the following remain true:

- active dates are sparse and concentrated
- expanded 6M q-step validation has a negative window
- no strong `REENTER` behavior has been demonstrated
- estimated improvement depends heavily on a few windows
- DFL has not accumulated enough live shadow active dates
- DFL audit conclusion is `review_required_shadow_only`

## Selective Reliability Trial

Added after the initial handoff, still on 2026-07-14.

Motivation:

- A21.18 is already a strong baseline.
- The new module should mostly know when not to intervene.
- NCF `confidence` is not action-value calibrated, so it should not be used as the reliability gate.
- Reliability should estimate whether the current `action_regret` prediction is likely to be wrong.

Implementation:

- evaluator: `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
- added CLI:
  - `--selective-reliability`
  - `--reliability-max-error-percentile`
  - `--reliability-min-train-days`
- method:
  - train a second expanding ridge meta-model per action
  - target is past absolute prediction error:
    - `abs(predicted_action_regret - realized_action_regret)`
  - convert current predicted error into a percentile against past realized errors
  - if selected action's predicted error percentile is above threshold, reject to `KEEP`
- tested threshold:
  - `reliability_max_error_percentile = 0.70`

This is research-only. It is not wired into live allocation.

### Selective 7-window result

Output:

- `results/a2118_decision_focused_action_shadow_selective_p70_7win_20260714.json`
- `results/a2118_decision_focused_action_overlap_selective_p70_7win_20260714.json`
- `results/a2118_dfl_active_date_audit_selective_p70_7win_20260714.json`

Result:

- triple-pass: `7/7`
- candidate non-KEEP days before reliability: `7`
- rejected to KEEP: `3`
- accepted active days: `4`
- overall KEEP rate: `99.81%`
- total final delta: `+13,935.57`
- total Sharpe delta: `+0.0336`
- total MDD delta: `+0.0060`
- overlap: `0/4`
- audit hard checks: pass
- estimated cost: `4.3584 bps / 1M`
- audit conclusion: `passes_replay_audit_with_warnings_shadow_only`

Interpretation:

- Reliability gate is conservative.
- It preserved the 2025 active dates and rejected 3 of the 4 2018 correction dates.
- Final delta is slightly lower than the non-selective fixed 7-window run, but cost and interventions are also lower.

### Selective rolling 6M q-step result

Output:

- `results/a2118_decision_focused_action_shadow_selective_p70_rolling_6m_qstep_20260714.json`
- `results/a2118_decision_focused_action_overlap_selective_p70_rolling_6m_qstep_20260714.json`
- `results/a2118_dfl_active_date_audit_selective_p70_rolling_6m_qstep_20260714.json`

Result:

- windows: `17`
- triple-pass: `17/17`
- candidate non-KEEP days before reliability: `35`
- rejected to KEEP: `18`
- accepted active days: `17`
- overall KEEP rate: `99.14%`
- total final delta: `+21,713.21`
- total Sharpe delta: `+0.3706`
- total MDD delta: `+0.0226`
- overlap: `4/17`
- audit hard checks: pass
- warning days: `11`
- estimated cost: `20.3871 bps / 1M`
- audit conclusion: `review_required_shadow_only`

Important change versus non-selective 6M q-step:

- non-selective:
  - triple-pass: `16/17`
  - active days: `35`
  - failed window: `2018q4_2019q1`, final delta `-70.95`, Sharpe delta `-0.0010`
- selective p70:
  - triple-pass: `17/17`
  - active days: `17`
  - `2018q4_2019q1` rejected to KEEP
  - total final delta improved from `+21,631.89` to `+21,713.21`

Interpretation:

- Selective reliability did the intended job in the expanded validation.
- It rejected the weak negative cluster while keeping the stronger 2018 and 2026 clusters.
- It is still not ready for live trading because overlap remains nonzero and the result is still based on sparse historical active clusters.

Selective trial conclusion:

```text
Selective reliability is promising as an additional research gate.
Keep it shadow-only. Do not promote.
```

### Selective threshold sweep

Follow-up sweep, still fixed action-value model:

- only `reliability_max_error_percentile` changed
- tested thresholds: `p50`, `p60`, `p70`, `p80`, `p90`
- primary validation: rolling 6M q-step
- purpose: check robustness, not maximize in-sample return

Rolling 6M q-step comparison:

| Gate | Triple-pass | Failed windows | Candidate days | Rejected | Active days | KEEP rate | Total final delta | Total Sharpe delta | Overlap | Cost bps / 1M |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 16/17 | 1 | 35 | 0 | 35 | 98.23% | +21,631.89 | +0.3693 | 7/35 | 42.8887 |
| p50 | 17/17 | 0 | 35 | 27 | 8 | 99.60% | +22,454.14 | +0.3668 | 1/8 | 9.0302 |
| p60 | 17/17 | 0 | 35 | 27 | 8 | 99.60% | +22,454.14 | +0.3668 | 1/8 | 9.0302 |
| p70 | 17/17 | 0 | 35 | 18 | 17 | 99.14% | +21,713.21 | +0.3706 | 4/17 | 20.3871 |
| p80 | 17/17 | 0 | 35 | 16 | 19 | 99.04% | +21,546.25 | +0.3703 | 5/19 | 22.9345 |
| p90 | 17/17 | 0 | 35 | 6 | 29 | 98.54% | +21,729.93 | +0.3706 | 7/29 | 35.2467 |

Additional p50 fixed 7-window check:

- output:
  - `results/a2118_decision_focused_action_shadow_selective_p50_7win_20260714.json`
  - `results/a2118_decision_focused_action_overlap_selective_p50_7win_20260714.json`
  - `results/a2118_dfl_active_date_audit_selective_p50_7win_20260714.json`
- triple-pass: `7/7`
- candidate days: `7`
- rejected: `5`
- active days: `2`
- final delta: `+8,586`
- overlap: `0/2`
- audit hard checks: pass
- cost: `2.1493 bps / 1M`
- audit conclusion: `passes_replay_audit_shadow_only`

Threshold sweep interpretation:

- `p50`/`p60` are the cleanest and most selective in rolling 6M q-step.
- `p50` also gives the cleanest fixed 7-window audit.
- `p70` is a more balanced setting if preserving more active dates is preferred.
- `p90` is probably too permissive; it keeps too many actions and cost rises materially.
- Do not pick a threshold for live trading yet. For shadow monitoring, track both `p50` and `p70` candidates:
  - `p50`: conservative reliability gate
  - `p70`: balanced reliability gate

Updated selective recommendation:

```text
Best research setting for safety: p50/p60.
Best research setting for balance: p70.
Production status: still shadow-only.
```

### Event windows and cost stress

Follow-up validation after threshold sweep.

Event windows:

- `2017q4_2018q1`
- `2018_q3q4`
- `2018q4_2019q1`
- `2025q4_2026q1`

Outputs:

- `results/a2118_decision_focused_action_shadow_selective_p50_event_windows_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p70_event_windows_20260714.json`

Event-window result:

| Gate | Triple-pass | Active days | Rejected | Notes |
| --- | ---: | ---: | ---: | --- |
| p50 | 4/4 | 8 | 27 | rejects `2018q4_2019q1` to KEEP |
| p70 | 4/4 | 17 | 18 | rejects `2018q4_2019q1` to KEEP |

Both p50 and p70 pass the hand-picked event windows. The important result is that the previously weak `2018q4_2019q1` window becomes all KEEP under both selective settings.

Cost stress, rolling 6M q-step:

| Gate | Cost | Triple-pass | Failed windows | Active days | Total final delta | Total Sharpe delta | Total MDD delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p50 | 1x | 17/17 | 0 | 8 | +22,454.14 | +0.3668 | +0.0239 |
| p50 | 2x | 17/17 | 0 | 8 | +21,888.27 | +0.3605 | +0.0237 |
| p50 | 3x | 17/17 | 0 | 8 | +21,323.38 | +0.3543 | +0.0235 |
| p70 | 1x | 17/17 | 0 | 17 | +21,713.21 | +0.3706 | +0.0226 |
| p70 | 2x | 17/17 | 0 | 17 | +21,022.17 | +0.3626 | +0.0223 |
| p70 | 3x | 17/17 | 0 | 17 | +20,332.64 | +0.3546 | +0.0219 |

Cost-stress interpretation:

- Both p50 and p70 remain robust under 2x and 3x cost assumptions.
- p50 is cleaner and less cost-sensitive because it trades only 8 days.
- p70 has similar risk-adjusted behavior but keeps more active dates and therefore higher cost exposure.
- This strengthens the case for tracking p50 as the primary safety shadow.

Updated best research shadow choice:

```text
Primary shadow: selective p50.
Secondary comparison shadow: selective p70.
Still no automatic trading.
```

## Daily Shadow Ensemble Log

Added after the selective reliability and cost-stress work.

Purpose:

- Track base DFL, selective p50, and selective p70 every day.
- Convert multiple shadow variants into a simple observation level.
- Preserve a date-keyed JSONL history for later live-shadow evaluation.
- Keep everything advisory-only.

Implementation:

- builder: `scripts/run/build_a2118_dfl_shadow_ensemble_log.py`
- latest snapshot: `report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json`
- append-only log: `results/a2118_dfl_shadow_ensemble_log.jsonl`
- tests: `tests/test_build_a2118_dfl_shadow_ensemble_log.py`

Daily pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py`
- new step: `dfl_shadow_ensemble`
- sequence:
  - `dfl_advisory`
  - `dfl_active_date_audit`
  - `dfl_shadow_ensemble`
  - `daily_status`

Daily status integration:

- `scripts/misc/check_group_a_plus_daily_status.py`
- new optional CLI:
  - `--dfl-shadow-ensemble`
- Markdown section:
  - `A21.18 DFL Shadow Ensemble`

Ensemble levels:

| Level | Meaning |
| --- | --- |
| `none` | base, p50, and p70 all say KEEP |
| `watch` | base or p70 has non-KEEP, but p50 does not |
| `strong_watch` | p50 and p70 both have non-KEEP |
| `conflict` | non-KEEP actions conflict, or p50 triggers without p70 |

Current latest snapshot at handoff time:

```json
{
  "as_of": "2026-07-09",
  "ensemble_level": "none",
  "manual_review_required": false,
  "signals": {
    "base": {"action": "KEEP", "active": false},
    "p50": {"action": "KEEP", "active": false},
    "p70": {"action": "KEEP", "active": false}
  },
  "policy": "shadow_only_no_auto_weight_change",
  "active_allocation_impact": "none"
}
```

Important operational boundary:

- This ensemble is an observation dashboard, not a portfolio engine.
- `strong_watch` is not a trade instruction.
- `watch` is not a trade instruction.
- `conflict` is not a trade instruction.
- All levels are for manual review only.

## Promotion Boundary

These additions do not count as a live strategy promotion.

Allowed shadow/advisory additions:

- `base DFL advisory`
- `selective p50 advisory`
- `selective p70 advisory`
- `DFL active-date audit`
- `DFL shadow ensemble latest JSON`
- `DFL shadow ensemble JSONL log`
- daily status display
- ops health visibility
- pipeline best-effort generation

Still prohibited without a separate promotion decision:

- DFL changing A21.18 target weights
- DFL changing `execution_plan.json`
- DFL triggering automatic CAP10 trades
- DFL blocking or forcing 00631L trades
- ensemble level changing pre-trade guards
- p50/p70 voting used as independent model evidence for auto execution

The invariant remains:

```text
active_allocation_impact = none
policy = shadow_only_no_auto_weight_change
```

## Promotion Criteria For Future Review

Before considering live execution-plan integration, require at minimum:

- at least 30 to 50 new live shadow observations with some non-KEEP active dates
- no material negative active-window cluster after costs
- DFL active-date audit hard checks pass
- no evidence that DFL mostly duplicates existing guards
- explicit manual review of any `CAP10` recommendation
- clear behavior for re-entry after CAP10
- portfolio-level turnover control confirmed from actual holdings, not just weight proxy

## Files To Know

Core evaluators:

- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
- `scripts/evaluate/evaluate_a2118_decision_focused_overlap.py`
- `scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py`

Ops integration:

- `scripts/run/build_a2118_dfl_advisory.py`
- `scripts/run/build_a2118_dfl_shadow_ensemble_log.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `group_a_plus/operations/ops_health.py`

Tests:

- `tests/test_evaluate_a2118_decision_focused_action_shadow.py`
- `tests/test_evaluate_a2118_decision_focused_overlap.py`
- `tests/test_evaluate_a2118_dfl_active_date_audit.py`
- `tests/test_build_a2118_dfl_advisory.py`
- `tests/test_build_a2118_dfl_shadow_ensemble_log.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_group_a_plus_ops_health.py`

Primary result artifacts:

- `results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json`
- `results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json`
- `results/a2118_dfl_active_date_audit_20260714.json`
- `results/a2118_decision_focused_action_shadow_fixed_rolling_half_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_half_20260714.json`
- `results/a2118_decision_focused_action_shadow_fixed_rolling_quarter_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_quarter_20260714.json`
- `results/a2118_decision_focused_action_shadow_fixed_rolling_6m_qstep_20260714.json`
- `results/a2118_decision_focused_action_overlap_fixed_rolling_6m_qstep_20260714.json`
- `results/a2118_dfl_active_date_audit_rolling_6m_qstep_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p50_7win_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p70_7win_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p50_rolling_6m_qstep_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p70_rolling_6m_qstep_20260714.json`
- `report/group_a_plus/latest/a2118_dfl_advisory.json`
- `report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json`
- `results/a2118_dfl_shadow_ensemble_log.jsonl`

## Final Handoff Decision

DFL should remain in the system as a monitored shadow tool.

The correct current behavior is:

- daily signal remains A21.18-driven
- execution plan remains unaffected by DFL
- DFL advisory is visible
- DFL selective p50 and p70 variants are visible
- DFL shadow ensemble level is visible and logged
- DFL audit health is visible
- DFL does not change target weights
- DFL does not automatically block or force trades

Short version:

```text
Keep DFL. Watch it daily. Do not trade it automatically.
```
