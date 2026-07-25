# FinStressTS Decision Snapshot（2026-07-17）

## Purpose

This daily-readable snapshot consolidates the three FinStressTS shadow reports:

- `finstressts_readiness_review`
- `finstressts_counterfactual_shadow`
- `finstressts_baseline_compare_shadow`

It is a research/governance summary only.

## Output

- Script: `scripts/evaluate/build_group_a_plus_finstressts_decision_snapshot.py`
- Latest report: `report/group_a_plus/latest/finstressts_decision_snapshot.json`
- Daily pipeline: `finstressts_decision_snapshot` runs as a best-effort
  diagnostic after the three upstream FinStressTS reports.
- Daily status: `scripts/misc/check_group_a_plus_daily_status.py` includes the
  snapshot in `group_a_plus.finstressts_decision_snapshot` and renders a
  `FinStressTS Shadow Snapshot` Markdown section when the file is present.

## Decision Policy

The snapshot can summarize blockers, but it cannot unlock execution.

- no live target-weight change
- no auto-rebalance
- no `00631L` add
- keep `Golden1_0531` unchanged

## 2026-07-17 Result

Current snapshot:

- `status = blocked`
- `allow_00631l_add = false`
- blockers:
  - `readiness_review_blocked`
  - `reference_loses_to_no_00631l_under_counterfactuals`
  - `reference_tail_failures_under_counterfactuals`
  - `no_baseline_beats_no_00631l`

Conclusion:

- FinStressTS evidence strengthens the no-rebalance / no-`00631L` decision.
- No synthetic or counterfactual result is promoted to live alpha.
