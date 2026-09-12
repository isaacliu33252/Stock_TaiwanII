# GroupA+ Execution Plan Pointer Alignment Record

- Recorded: 2026-09-01
- Scope: production artifact pointer alignment only
- Policy: no strategy change, no target-weight change, no automatic order

## Issue

`report/group_a_plus/latest/execution_plan.json` was still pointing to an
older plan:

- stale latest pointer actual data date: `2026-08-24`
- current live signal actual data date: `2026-08-31`

This caused:

- `daily_artifact_integrity`: `error`
- error reason: `execution_plan actual_data_date does not match live_signal`
- daily status: `block`
- deployment summary gate warning still referenced
  `execution_plan_date_mismatch`

## Root Cause

A refreshed execution plan had already been generated for the 2026-08-31 data
and 1.5m asset scenario:

`releases/golden2_0830/group_a_plus_execution_plan_golden2_0830_20260901_1500k.json`

That release artifact had:

- `requested_as_of_date`: `2026-09-01`
- `actual_data_date`: `2026-08-31`
- `current_total_assets`: `1500000.0`
- `holdings_source`: `results/holdings_group_a_plus_from_taiwan_stock_20260831.json`

The point-in-time execution-plan snapshots for 2026-08-31 also existed under:

`results/point_in_time_artifacts/execution_plan/2026/08/31/`

The stale state was therefore a latest-pointer alignment problem, not missing
data and not a strategy-generation failure.

## Remediation

The 2026-08-31 release plan was synced to:

`report/group_a_plus/latest/execution_plan.json`

Then the dependent governance artifacts were regenerated:

- `report/group_a_plus/latest/daily_artifact_integrity.json`
- `report/group_a_plus/latest/daily_artifact_integrity.md`
- `results/group_a_plus_daily_status_20260831.json`
- `results/group_a_plus_daily_status_20260831.md`
- `report/group_a_plus/latest/deployment_consistency_review.json`
- `report/group_a_plus/latest/deployment_summary.json`
- `report/group_a_plus/latest/deployment_summary.md`
- `results/group_a_plus_promotion_gate_20260831.json`
- `results/group_a_plus_daily_status_final_20260831.json`
- `results/group_a_plus_daily_status_final_20260831.md`
- managed latest daily status reports under `report/group_a_plus/daily/`
- canonical daily status at `outputs/group_a_plus/latest/daily_status.json`

## Result

After rerun:

- `daily_artifact_integrity`: `ok`
- `execution_plan_pre_trade_guard`: `ok`
- `promotion_gate_deployment_summary`: `ok`
- deployment summary gate: `pass`
- deployment summary blockers: `[]`
- `execution_plan_date_mismatch`: cleared

Final daily status remains:

- `overall_status`: `warn`

Remaining warnings are not caused by execution-plan staleness:

- DFL advisory frozen input is stale; frozen backtest last covers
  `2026-07-15`.
- Promotion gate remains blocked by model gates and manual approval state:
  - panel drift gate failed: `h20_prob_up`
  - multi-window gate failed: no candidate passed
  - manual approval pending

## Decision Boundary

This remediation only updates governance/reporting pointers to the already
generated 2026-08-31 execution plan. It does not:

- change GroupA+ target weights;
- promote 2608.20179 into live strategy;
- override CVaR / tail / promotion blockers;
- create executable broker orders.

## DFL Refresh Follow-Up

After review, the `2026-07-15` DFL coverage was judged stale for a 2026-08-31
live-signal run. The DFL shadow windows in
`scripts/run/run_ncf_daily_pipeline.py` were updated so the live/active windows
use the current daily NCF panel:

`results/ncf_00631l_panel_latest_YYYYMMDD.csv`

and resolve their end date through `latest` instead of the fixed
`2026-07-15` cutoff.

The DFL artifacts were then regenerated against:

`results/ncf_00631l_panel_latest_20260831.csv`

Updated DFL outputs:

- `results/a2118_decision_focused_action_shadow_dfl_main_latest.json`
- `results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json`
- `results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json`
- `report/group_a_plus/latest/a2118_dfl_advisory.json`
- `results/a2118_decision_focused_action_overlap_dfl_latest.json`
- `results/a2118_dfl_active_date_audit_20260831.json`
- `report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json`

Latest DFL result:

| variant | triple-pass windows | notable failure | decision |
|---|---:|---|---|
| main | 4/7 | live and active windows lost value | keep research-only |
| p50 | 6/7 | active_2025_2026 final value -8,467 | keep research-only |
| p70 | 6/7 | active_2025_2026 final value -38,266 | keep research-only |

DFL advisory for the 2026-08-31 live signal:

- `status`: `available`
- `action`: `KEEP`
- `advisory_active`: `false`
- `recommended_action`: `keep_a2118`

DFL active-date audit:

- active days: `45`
- existing guard overlap: `20`
- estimated cost: `6.4669` bps
- all checks pass: `false`
- conclusion: `review_required_shadow_only`

After the DFL rerun and report regeneration:

- final daily status: `ok`
- DFL frozen input staleness: `ok`
- DFL latest coverage: `2026-08-31`
- calendar gap: `0`
- daily artifact integrity: `ok`
- promotion-gate deployment summary: `ok`

Promotion gate still does not promote the model:

- decision: `blocked_model_gates_manual_approval_pending`
- panel drift gate failed: `h20_prob_up`
- multi-window gate failed: no candidate passed

Validation:

- `pytest` passed:
  `tests/test_run_ncf_daily_pipeline.py`
  `tests/test_check_group_a_plus_daily_status.py`
  -> `49 passed in 56.08s`.

## Promotion Candidate Follow-Up

After DFL freshness was fixed, the next blocker was promotion-gate evidence
quality. A new diagnostic was added:

`scripts/evaluate/build_group_a_plus_golden2_promotion_candidate_review.py`

Generated outputs:

- `report/group_a_plus/latest/golden2_promotion_candidate_review.json`
- `report/group_a_plus/latest/golden2_promotion_candidate_review.md`
- `report/group_a_plus/golden2_promotion_candidate_review/history/golden2_promotion_candidate_review_20260831.json`

The diagnostic is now wired into `scripts/run/run_ncf_daily_pipeline.py` after
`promotion_gate`, so it can read the current gate result instead of stale
manual notes.

Latest result:

- `status`: `blocked_prepare_multi_window_backtest`
- compatible golden2 promotion candidates: `0`
- daily status: `ok`
- promotion gate decision: `blocked_model_gates_manual_approval_pending`
- dynamic CVaR forward validation passed: `false`

Blocking reasons:

- `no_golden2_promotion_compatible_candidate_rows`
- `promotion_metrics_gate_failed`
- `panel_drift_gate_failed`
- `multi_window_gate_failed`
- `no_multi_window_candidate_available`
- `dfl_latest_audit_not_promotion_ready`
- `dynamic_cvar_forward_validation_blocks_live_weight_change`

Interpretation:

- `golden2_0830` currently has release/live-signal/execution-plan artifacts,
  but not same-window promotion-compatible candidate rows.
- Directly feeding the frozen golden2 live signal or execution plan into
  `evaluate_group_a_plus_promotion_gate.py` would not create a valid promotion
  comparison.
- The next required experiment is a same-window candidate backtest set for
  2020 COVID, 2022 rate-hike, 2024-2026, and 2025-2026, then rerun
  `evaluate_group_a_plus_multi_window_gate.py` on those rows.

Additional validation:

- `pytest` passed:
  `tests/test_build_group_a_plus_golden2_promotion_candidate_review.py`
  `tests/test_run_ncf_daily_pipeline.py`
  -> `24 passed in 48.09s`.

## Golden2 Same-Window Candidate Rows Follow-Up (2026-09-01, later session)

The "next required experiment" above was completed in a later pass of the
same day, after a context-compaction gap:

- `scripts/evaluate/build_group_a_plus_golden2_same_window_candidate_backtests.py`
  was run for real (it already existed with passing tests, but had never
  been executed -- no output file existed yet). It produces same-window
  golden2-vs-latest candidate reports for `2020_covid`, `2022_rate_hike`,
  `live_2024_2026`, and `active_2025_2026`, plus a per-window split under
  `report/group_a_plus/latest/golden2_same_window_candidate_backtests/`.
- `scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py` was run
  against those four per-window files, producing
  `report/group_a_plus/latest/golden2_multi_window_gate.json`.
- `scripts/evaluate/build_group_a_plus_golden2_promotion_candidate_review.py`
  was extended with a `--golden2-same-window-dir` parameter (default: the
  directory above) and its `--multi-window-gate` default was repointed from
  the generic, pre-golden2 `results/group_a_plus_multi_window_gate_20260706.json`
  to the golden2-specific gate file above. The previously-hardcoded
  `next_required_work` checklist (which described this exact gap) is now
  generated dynamically from the real remaining blockers.
- All three steps were wired into `scripts/run/run_ncf_daily_pipeline.py`
  (`golden2_same_window_candidate_backtests` -> `golden2_multi_window_gate`
  -> `golden2_promotion_candidate_review`, in that order) so this refreshes
  automatically every day instead of needing another manual re-run.

Result after the fix:

- `compatible_candidate_count`: `0` -> `4`.
- `no_golden2_promotion_compatible_candidate_rows` blocker: cleared (it was a
  real data-availability gap, now closed).
- Golden2 multi-window gate: `research_only_multi_window_unstable`, passes
  `2/4` windows (`2020_covid`, `2022_rate_hike` -- identical to latest, since
  those windows predate the golden2 freeze point; `live_2024_2026`,
  `active_2025_2026` -- golden2 underperforms the continuously-updating
  latest strategy by `-10.45%` final value in both, since a frozen strategy
  snapshot cannot benefit from panel/model refinements made after its freeze
  date).
- `golden2_0830` remains `blocked_prepare_multi_window_backtest` -- but now
  for a substantively correct reason (fails the multi-window stability gate
  and several other independent governance gates), not a data-availability
  placeholder.

Validation: `tests/test_build_group_a_plus_golden2_promotion_candidate_review.py`
(5 tests, incl. 3 new), `tests/test_build_group_a_plus_golden2_same_window_candidate_backtests.py`,
`tests/test_evaluate_group_a_plus_multi_window_gate.py`, and
`tests/test_run_ncf_daily_pipeline.py` (33 total) all passed.

No target-weight change, no auto-rebalance, no order. `golden1_0531` and the
frozen `golden2_0830` release artifacts themselves were not modified -- only
the governance/review scripts that evaluate golden2 as a promotion
candidate.
