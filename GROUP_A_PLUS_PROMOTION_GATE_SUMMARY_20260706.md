# GroupA+ Promotion Gate Summary - 2026-07-06

## Summary

Added a promotion-gate report that combines existing GroupA+ performance guardrails with the NCF panel-drift audit and the multi-window promotion gate.

New files:

- `scripts/evaluate/evaluate_group_a_plus_promotion_gate.py`
- `tests/test_evaluate_group_a_plus_promotion_gate.py`
- `tests/test_group_a_plus_governance_compare_extended.py`
- `scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py`
- `tests/test_evaluate_group_a_plus_multi_window_gate.py`

Updated:

- `group_a_plus/governance/compare.py`
  - Supports reports whose baseline metrics live under `baseline.metrics`.
  - Supports candidate rows under `summary.best_by_final_value`, `summary.best_by_max_drawdown`, `summary.best_by_sharpe`, and `top_by_*`.
  - Allows one combined file to be used as both `--baseline` and `--candidates` when it contains embedded baseline and candidate sections.
- `scripts/run/run_ncf_daily_pipeline.py`
  - Adds a daily `promotion_gate` step after `daily_status`.
  - Adds `--skip-promotion-gate` plus configurable promotion baseline, candidate, drift-audit, and multi-window gate inputs.
  - Adds the daily promotion gate output to the pipeline manifest.

No strategy pointer, model weight, live signal, or allocation logic was changed.

## Gate Rules

The report applies three independent gates:

1. Metrics gate, reusing the existing formal guardrails:
   - candidate final value >= baseline final value
   - candidate Sharpe >= baseline Sharpe
   - candidate max drawdown >= baseline max drawdown
   - effective override days > 0

2. NCF panel-drift gate:
   - `ensemble_prob_up` max drift <= 0.05
   - `h20_prob_up` max drift <= 0.05
   - `confidence` max drift <= 0.05

3. Multi-window gate:
   - candidate must pass every available window by default
   - final value drag may not exceed 2%
   - Sharpe must not be worse
   - max drawdown must not be worse

If panel drift and multi-window both fail, the final decision is `blocked_panel_drift_and_multi_window`.

## Real Run

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_promotion_gate.py \
  --baseline results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json \
  --candidates results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json \
  --drift-audit results/ncf_00631l_panel_drift_20260630_vs_20260703.json \
  --multi-window-gate results/group_a_plus_multi_window_gate_20260706.json \
  --output results/group_a_plus_promotion_gate_a2118_ncf2330_overlay_20260706.json
```

Output:

- `results/group_a_plus_promotion_gate_a2118_ncf2330_overlay_20260706.json`
- `results/group_a_plus_promotion_gate_20260706.json` from the daily-style pipeline command

Decision:

- `blocked_panel_drift_and_multi_window`

Metrics gate:

- Status: `fail`
- Formal pass count: 0
- Watchlist pass count: 0
- Candidate rows checked: 48

Best Sharpe candidate:

| Metric | Baseline delta |
| --- | ---: |
| final value | -61,285.52 |
| Sharpe | +0.0397 |
| max drawdown | 0.0000 |
| override days | 23 |

The Sharpe improves, but final value drops below the research-watchlist floor, so metrics gate does not pass.

Panel drift gate:

| Column | Max abs drift | Limit | Status |
| --- | ---: | ---: | --- |
| `ensemble_prob_up` | 0.302322 | 0.05 | fail |
| `h20_prob_up` | 0.298098 | 0.05 | fail |
| `confidence` | 0.464781 | 0.05 | fail |

Multi-window gate:

- Status: `fail`
- Reason: no candidate passed the multi-window gate
- Source: `results/group_a_plus_multi_window_gate_20260706.json`
- Multi-window decision: `research_only_no_multi_window_pass`

## Interpretation

The NCF2330 overlay should remain research-only. It does not pass existing performance guardrails, the NCF panel it depends on is unstable enough that trigger-based promotion would be unsafe, and the broader candidate set does not pass the strict multi-window promotion gate.

The gate is now reusable for future NCF-trigger candidates before any promotion discussion.

## Verification

```bash
.venv/bin/python -m py_compile \
  group_a_plus/governance/compare.py \
  scripts/evaluate/evaluate_group_a_plus_promotion_gate.py \
  scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py

.venv/bin/python -m pytest -q \
  tests/test_group_a_plus_governance_compare_extended.py \
  tests/test_evaluate_group_a_plus_promotion_gate.py \
  tests/test_evaluate_ncf_panel_drift.py \
  tests/test_evaluate_group_a_plus_multi_window_gate.py
```

Result: 8 passed for the focused promotion/multi-window set; 17 passed for the broader daily status, drift, governance, promotion, and multi-window set.

Pipeline dry-run verification:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260706 \
  --skip-refresh \
  --skip-commentary \
  --dry-run
```

Result: daily command order now includes `promotion_gate` as step 9 of 10, before `ncf_2330_checklist`.
