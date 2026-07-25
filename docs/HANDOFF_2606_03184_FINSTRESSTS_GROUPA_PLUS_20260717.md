# Handoff: 2606.03184 FinStressTS for GroupA+（2026-07-17）

## Source

- PDF: `C:\Users\isaac\Downloads\2606.03184.pdf`
- Title: `FinStressTS: A Parametric Synthetic Benchmark for Time-Series Forecasting in Finance`
- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- 7/20 reference target: `0050.TW 50% / 00631L.TW 20% / cash 30%`

## Imported Benefit

Imported only as research / governance:

- mechanism-specific stress testing before model promotion
- controlled counterfactual financial time-series validation
- probabilistic calibration and tail-risk review
- data-efficiency / learning-curve requirement
- simple baseline before Transformer or density-head promotion
- failure attribution by volatility, heavy-tail, regime, and jump mechanisms

Not imported:

- synthetic returns as live alpha
- KDD benchmark rankings as Taiwan ETF evidence
- automatic model replacement
- automatic rebalance
- direct `00631L` add signal

## Artifacts

Review docs:

- `docs/2606_03184_FINSTRESSTS_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/FINSTRESSTS_COUNTERFACTUAL_SHADOW_20260717.md`
- `docs/FINSTRESSTS_BASELINE_COMPARE_SHADOW_20260717.md`
- `docs/FINSTRESSTS_DECISION_SNAPSHOT_20260717.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

Scripts:

- `scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py`
- `scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py`
- `scripts/evaluate/build_group_a_plus_finstressts_decision_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`

Tests:

- `tests/test_build_group_a_plus_finstressts_readiness_review.py`
- `tests/test_group_a_plus_finstressts_counterfactual_shadow.py`
- `tests/test_group_a_plus_finstressts_baseline_compare_shadow.py`
- `tests/test_build_group_a_plus_finstressts_decision_snapshot.py`
- `tests/test_run_ncf_daily_pipeline.py`

Reports:

- `report/group_a_plus/latest/finstressts_readiness_review_20260720.json`
- `report/group_a_plus/latest/finstressts_readiness_review.json`
- `report/group_a_plus/finstressts_readiness/history/20260720.json`
- `results/group_a_plus_finstressts_counterfactual_shadow_20260717.json`
- `report/group_a_plus/latest/finstressts_counterfactual_shadow.json`
- `results/group_a_plus_finstressts_baseline_compare_shadow_20260717.json`
- `report/group_a_plus/latest/finstressts_baseline_compare_shadow.json`
- `report/group_a_plus/latest/finstressts_decision_snapshot.json`

## Current Readiness Result

`finstressts_readiness_review_20260720.json`:

- `status = blocked`
- blocked mechanisms:
  - `heavy_tailed_shocks`
  - `self_exciting_jumps`
  - `zero_inflated_sparse_jumps`
  - `execution_under_stress`
- blockers:
  - `live_signal_execution_not_allowed`
  - `rebalance_review_disallows_target_weight_change`
  - `option_state_gate_not_passed`
  - `adversarial_market_integrity_not_passed`
  - `market_impact_readiness_not_passed`
  - `optimizer_readiness_not_passed`
  - `mechanism_stress_coverage_blocked`

Decision:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

## Counterfactual Shadow Result

Fixed-weight scenarios tested:

- `historical_baseline`
- `heavy_tailed_shocks`
- `regime_switch_down`
- `self_exciting_jumps`
- `zero_inflated_sparse_jumps`

Result:

- reference loses to no-`00631L`: `5 / 5` scenarios
- reference tail failures: `4 / 5` scenarios
- `allow_00631l_add = false`

Interpretation:

- The `2026-07-20` reference allocation
  `0050.TW 50% / 00631L.TW 20% / cash 30%` is more fragile than the
  no-`00631L` reference in every tested stress scenario.
- This reinforces the current GroupA+ decision: no rebalance, no `00631L` add,
  no live target-weight change.

## Daily Pipeline

Added best-effort steps:

- `finstressts_readiness_review`
- `finstressts_counterfactual_shadow`
- `finstressts_baseline_compare_shadow`
- `finstressts_decision_snapshot`

These are diagnostics only. Failures do not block downstream live status, and
success never unlocks execution.

## Baseline Compare Follow-up

Added:

- `scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py`
- `tests/test_group_a_plus_finstressts_baseline_compare_shadow.py`
- `docs/FINSTRESSTS_BASELINE_COMPARE_SHADOW_20260717.md`

Candidates:

- `reference_20260720`
- `no_00631l_reference_cash`
- `reduced_leverage`
- `rolling_vol_gate`
- `trend_gate`
- `combined_vol_trend_gate`

Result:

- best shadow candidate: `combined_vol_trend_gate`
- wins versus no-`00631L` on both ES95 and max drawdown: `0 / 5`
- tail failures:
  - `reference_20260720`: `4 / 5`
  - `reduced_leverage`: `4 / 5`
  - `rolling_vol_gate`: `2 / 5`
  - `trend_gate`: `1 / 5`
  - `combined_vol_trend_gate`: `1 / 5`

Interpretation:

- `combined_vol_trend_gate` is worth keeping as a research candidate because it
  reduces tail failures.
- It still does not beat no-`00631L` in any tested scenario on the strict
  ES95 + max-drawdown rule.
- Do not promote it to live.

## Consolidated Snapshot

Added:

- `scripts/evaluate/build_group_a_plus_finstressts_decision_snapshot.py`
- `tests/test_build_group_a_plus_finstressts_decision_snapshot.py`
- `docs/FINSTRESSTS_DECISION_SNAPSHOT_20260717.md`

Current result:

- `status = blocked`
- blockers:
  - `readiness_review_blocked`
  - `reference_loses_to_no_00631l_under_counterfactuals`
  - `reference_tail_failures_under_counterfactuals`
  - `no_baseline_beats_no_00631l`

Decision:

- `allow_00631l_add = false`
- `auto_rebalance_allowed = false`
- `target_weight_change_allowed = false`

Daily status integration:

- `scripts/misc/check_group_a_plus_daily_status.py` accepts
  `--finstressts-decision-snapshot`.
- `scripts/run/run_ncf_daily_pipeline.py` passes
  `report/group_a_plus/latest/finstressts_decision_snapshot.json` to daily
  status.
- Markdown daily status renders `## FinStressTS Shadow Snapshot` when the
  snapshot exists.

Smoke output:

- `results/group_a_plus_daily_status_20260720_finstressts_smoke.json`
- `results/group_a_plus_daily_status_20260720_finstressts_smoke.md`

Smoke result:

- `overall_status = block`
- daily status includes `group_a_plus.finstressts_decision_snapshot`
- Markdown includes `## FinStressTS Shadow Snapshot`
- `00631L add = blocked`
- `reference_loses_to_no_00631l_scenarios = 5`
- `reference_tail_failure_scenarios = 4`

## Verification

Commands run:

- `.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py scripts/run/run_ncf_daily_pipeline.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_finstressts_readiness_review.py tests/test_group_a_plus_finstressts_counterfactual_shadow.py tests/test_run_ncf_daily_pipeline.py`
- `.venv/bin/python -m pytest tests/test_group_a_plus_finstressts_baseline_compare_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_finstressts_decision_snapshot.py`

Latest verified subset:

- `17 passed` for pipeline + counterfactual tests after daily pipeline wiring.

## Final Decision

Keep unchanged:

- GroupA+ latest strategy
- `Golden1_0531`
- `2026-07-20` execution block

Do not:

- auto-rebalance
- add `00631L`
- promote synthetic stress results to live alpha

Next possible research step:

- compare NCF / density-head / simple linear baseline under the same
  counterfactual scenarios, still as shadow only.
