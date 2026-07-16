# GroupA+ Final Decision Memo - 2026-07-06

## Decision

Keep the current GroupA+ production/live allocation unchanged.

The reviewed candidates remain research-only. No candidate currently clears the combined promotion path:

- Daily live status is operational, but current data freshness is warning-level.
- NCF panel drift is materially above promotion limits.
- A21.18 NCF2330 overlay metrics do not pass the existing performance gate.
- No candidate passes the strict multi-window gate.
- The daily pipeline now reports this automatically through the promotion gate.

No strategy pointer, model weight, live signal, or allocation behavior was changed in this workstream.

## What Changed

### 1. Daily Status In The Pipeline

Updated `scripts/misc/check_group_a_plus_daily_status.py` and `scripts/run/run_ncf_daily_pipeline.py`.

The daily pipeline now produces live-mode GroupA+ status from the current live signal and writes:

- `results/group_a_plus_daily_status_<date>.json`
- `report/group_a_plus/latest/daily_status.json`

Current observed status for 2026-07-06:

- Overall status: `warn`
- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Main warning: actual data date 2026-07-02 versus check date 2026-07-06
- Soft source warning: `securities_lending_0050`

### 2. NCF Panel Drift Audit

Added:

- `scripts/evaluate/evaluate_ncf_panel_drift.py`
- `tests/test_evaluate_ncf_panel_drift.py`
- `GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md`

Compared:

- `results/ncf_00631l_panel_latest_20260630.csv`
- `results/ncf_00631l_panel_latest_20260703.csv`

Output:

- `results/ncf_00631l_panel_drift_20260630_vs_20260703.json`
- `results/ncf_00631l_panel_drift_20260630_vs_20260703.csv`

Key drift findings:

| Field | Max abs drift | Promotion limit |
| --- | ---: | ---: |
| `ensemble_prob_up` | 0.302322 | 0.05 |
| `h20_prob_up` | 0.298098 | 0.05 |
| `confidence` | 0.464781 | 0.05 |

Interpretation: trigger-based NCF promotion is not reliable until the panel generation/retraining path is stabilized or explicitly versioned.

### 3. Promotion Gate

Added:

- `scripts/evaluate/evaluate_group_a_plus_promotion_gate.py`
- `tests/test_evaluate_group_a_plus_promotion_gate.py`
- `tests/test_group_a_plus_governance_compare_extended.py`

Updated:

- `group_a_plus/governance/compare.py`

The promotion gate combines:

- Existing performance guardrails.
- NCF panel drift guardrails.
- Multi-window gate result.

Latest output:

- `results/group_a_plus_promotion_gate_a2118_ncf2330_overlay_20260706.json`
- `results/group_a_plus_promotion_gate_20260706.json`

Latest decision:

- `blocked_panel_drift_and_multi_window`

Metrics gate result:

- Status: `fail`
- Formal pass count: 0
- Watchlist pass count: 0
- Candidate rows checked: 48

Best Sharpe candidate still had final value drag:

| Metric | Baseline delta |
| --- | ---: |
| Final value | -61,285.52 |
| Sharpe | +0.0397 |
| Max drawdown | 0.0000 |
| Override days | 23 |

### 4. Multi-Window Gate

Added:

- `scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py`
- `tests/test_evaluate_group_a_plus_multi_window_gate.py`
- `GROUP_A_PLUS_MULTI_WINDOW_GATE_20260706.md`

Output:

- `results/group_a_plus_multi_window_gate_20260706.json`

Decision:

- `research_only_no_multi_window_pass`

Candidate summary:

| Candidate | Pass windows | Main blocker |
| --- | ---: | --- |
| `garch_selector_frozen` | 1/3 | Worse MDD in 2008 and 2020 |
| `garch_guard_frozen` | 2/3 | 2020 final value and Sharpe drag |
| `shadow_2008_candidate` | 0/1 | Recent Sharpe drag and slightly worse MDD |
| `best_by_final_value` | 0/1 | Recent final value drag > 2% |
| `best_by_max_drawdown` | 0/1 | Recent final value drag > 2% |
| `best_by_sharpe` | 0/1 | Recent final value drag > 2% |

### 5. Daily Pipeline Integration

Updated:

- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`

The daily pipeline now includes `promotion_gate` after `daily_status` and before `ncf_2330_checklist`.

New CLI controls:

- `--skip-promotion-gate`
- `--promotion-baseline`
- `--promotion-candidates`
- `--promotion-drift-audit`
- `--promotion-multi-window-gate`

Dry-run result for 2026-07-06:

- `promotion_gate` is step 9 of 10.
- Daily manifest will include `promotion_gate` output when the step is enabled.

## Current Blockers

### Blocker 1: NCF Panel Drift

The panel drift is too large for trigger promotion. The max drift in probability/confidence fields is several times larger than the current 0.05 governance limit.

This means a trigger date or trigger threshold optimized on one panel can disappear or materially change after refresh.

### Blocker 2: Performance Gate

The NCF2330 overlay improves Sharpe in the best case, but not enough to offset final value drag. It does not clear formal or watchlist criteria.

### Blocker 3: Multi-Window Stability

The broader candidate set does not pass across stress and recent windows. The strongest routing candidates still have drawdown or 2020 performance regressions.

## Recommended Next Research Order

1. Stabilize NCF panel generation.
   - Version the feature/model/panel configuration used by trigger sweeps.
   - Re-run panel drift audit after any model or feature change.
   - Treat old sweep results as invalid unless reproduced on the same panel version.

2. Rework NCF2330 overlay objective.
   - Do not optimize Sharpe alone.
   - Add final value floor and MDD non-worse constraints directly into sweep ranking.
   - Re-run A21.18 overlay sweep only after panel drift is controlled.

3. Improve 2020 behavior for GARCH routing candidates.
   - `garch_selector_frozen` needs MDD control.
   - `garch_guard_frozen` needs better 2020 final value and Sharpe behavior.
   - Any new routing candidate should run through the multi-window gate before promotion discussion.

4. Keep daily governance reporting enabled.
   - The daily pipeline now surfaces promotion blockers automatically.
   - Use `--skip-promotion-gate` only for operational debugging, not for promotion decisions.

## Verification

Focused commands run during this workstream:

```bash
.venv/bin/python -m py_compile \
  scripts/misc/check_group_a_plus_daily_status.py \
  scripts/run/run_ncf_daily_pipeline.py \
  scripts/evaluate/evaluate_ncf_panel_drift.py \
  scripts/evaluate/evaluate_group_a_plus_promotion_gate.py \
  scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py
```

Final related test set:

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

## Final State

GroupA+ governance is now stricter and more observable:

- Daily status is generated from live signal.
- Panel drift is measurable.
- Promotion decisions combine metrics, drift, and multi-window evidence.
- The daily pipeline emits promotion-gate output.

Current action remains: keep all reviewed candidates research-only.
