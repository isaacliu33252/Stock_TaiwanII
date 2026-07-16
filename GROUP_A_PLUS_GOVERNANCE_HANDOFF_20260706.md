# GroupA+ Governance Handoff - 2026-07-06

## Status

This workstream is complete.

Final decision: keep all reviewed GroupA+ candidates research-only. Do not change live allocation, strategy pointer, model weights, or live signal behavior.

Latest combined decision:

- `blocked_panel_drift_and_multi_window`

Primary reference memo:

- `GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`

## What Was Added

### Daily Status

Updated:

- `scripts/misc/check_group_a_plus_daily_status.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`

Purpose:

- Generate live-mode daily status from the current live signal.
- Add `daily_status` to the daily pipeline command order and manifest outputs.

Current observed status:

- Overall: `warn`
- Main reason: actual data date 2026-07-02 versus check date 2026-07-06.
- Soft warning: `securities_lending_0050`.

### NCF Panel Drift Audit

Added:

- `scripts/evaluate/evaluate_ncf_panel_drift.py`
- `tests/test_evaluate_ncf_panel_drift.py`
- `GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md`

Outputs:

- `results/ncf_00631l_panel_drift_20260630_vs_20260703.json`
- `results/ncf_00631l_panel_drift_20260630_vs_20260703.csv`

Key result:

- `ensemble_prob_up` max drift: 0.302322
- `h20_prob_up` max drift: 0.298098
- `confidence` max drift: 0.464781

Promotion limit used by gate: 0.05 for each field.

### Promotion Gate

Added:

- `scripts/evaluate/evaluate_group_a_plus_promotion_gate.py`
- `tests/test_evaluate_group_a_plus_promotion_gate.py`

Updated:

- `group_a_plus/governance/compare.py`
- `GROUP_A_PLUS_PROMOTION_GATE_SUMMARY_20260706.md`

Outputs:

- `results/group_a_plus_promotion_gate_a2118_ncf2330_overlay_20260706.json`
- `results/group_a_plus_promotion_gate_20260706.json`

Latest result:

- Decision: `blocked_panel_drift_and_multi_window`
- Metrics gate: `fail`
- Panel drift gate: `fail`
- Multi-window gate: `fail`

### Multi-Window Gate

Added:

- `scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py`
- `tests/test_evaluate_group_a_plus_multi_window_gate.py`
- `GROUP_A_PLUS_MULTI_WINDOW_GATE_20260706.md`

Output:

- `results/group_a_plus_multi_window_gate_20260706.json`

Latest result:

- Decision: `research_only_no_multi_window_pass`

Candidate notes:

- `garch_selector_frozen`: 1/3 windows passed; MDD worse in 2008 and 2020.
- `garch_guard_frozen`: 2/3 windows passed; 2020 final value and Sharpe drag.
- `shadow_2008_candidate`: 0/1 windows passed; recent Sharpe drag and slightly worse MDD.
- NCF overlay `best_by_*`: 0/1 windows passed; recent final value drag above 2%.

### Daily Pipeline Integration

Updated:

- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`

New daily step:

- `promotion_gate`, after `daily_status` and before `ncf_2330_checklist`.

New CLI flags:

- `--skip-promotion-gate`
- `--promotion-baseline`
- `--promotion-candidates`
- `--promotion-drift-audit`
- `--promotion-multi-window-gate`

Dry-run checked:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260706 \
  --skip-refresh \
  --skip-commentary \
  --dry-run
```

Result:

- `promotion_gate` is step 9 of 10.
- Daily manifest will include `promotion_gate` output when enabled.

## Verification

Final related test command:

```bash
.venv/bin/python -m pytest -q \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_evaluate_ncf_panel_drift.py \
  tests/test_group_a_plus_governance_compare_extended.py \
  tests/test_evaluate_group_a_plus_promotion_gate.py \
  tests/test_evaluate_group_a_plus_multi_window_gate.py
```

Result:

- `20 passed`

## Important Files To Read First

1. `GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`
2. `GROUP_A_PLUS_PROMOTION_GATE_SUMMARY_20260706.md`
3. `GROUP_A_PLUS_MULTI_WINDOW_GATE_20260706.md`
4. `GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md`

## Next Research Recommendations

1. Stabilize or version NCF panel generation before trusting trigger sweeps.
2. Re-run NCF panel drift audit after any feature/model/panel change.
3. Rework NCF2330 overlay objective to penalize final value drag and worse MDD directly.
4. Improve GARCH routing behavior in the 2020 window before another promotion attempt.
5. Keep promotion gate enabled in daily runs; use `--skip-promotion-gate` only for operational debugging.

## Operational Caution

Do not promote any candidate based only on Sharpe improvement. Current governance requires the combined evidence path:

- performance gate,
- panel drift gate,
- multi-window gate.

As of this handoff, that combined path fails.
