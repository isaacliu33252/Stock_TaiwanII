# GroupA+ Multi-Window Gate - 2026-07-06

## Objective

Add a promotion gate that aggregates candidate evidence across multiple market windows before any GroupA+ candidate can be considered for promotion.

This is a research/governance gate only. It does not change live allocation, latest strategy pointers, or execution behavior.

## Implementation

- Added `scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py`.
- Added `tests/test_evaluate_group_a_plus_multi_window_gate.py`.
- Supported input schemas:
  - GARCH specialist fold reports with `fold.test_final_value`, `fold.test_sharpe`, and `fold.test_mdd`.
  - 2008 shadow candidate verify reports with `current_active_metrics` and `shadow_2008_candidate_metrics`.
  - Generic baseline plus summary reports with `baseline`/`metrics` and `summary.best_by_*`.
- Excluded GARCH reference benchmarks `a207` and `ma20` from candidate promotion scoring.

Default gate criteria:

- Every available window must pass (`min_pass_ratio=1.0`).
- Candidate final value may lag baseline by at most 2%.
- Candidate Sharpe must not be worse than baseline.
- Candidate max drawdown must not be worse than baseline.

## Real Run

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py \
  --results \
  results/garch_specialist_routing_2008_fold_20260705.json \
  results/garch_specialist_routing_2011_fold_20260705.json \
  results/garch_specialist_routing_2020_fold_20260705.json \
  results/group_a_plus_2008_shadow_candidate_vs_active_2025_2026_verify.json \
  results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json \
  --output results/group_a_plus_multi_window_gate_20260706.json
```

Output:

- `results/group_a_plus_multi_window_gate_20260706.json`
- Decision: `research_only_no_multi_window_pass`
- Rows evaluated: 10
- Candidates evaluated: 6

## Candidate Summary

| Candidate | Decision | Pass Windows | Key Failure |
| --- | --- | ---: | --- |
| `garch_selector_frozen` | `research_only_multi_window_unstable` | 1/3 | Worse MDD in 2008 and 2020 windows |
| `garch_guard_frozen` | `research_only_multi_window_unstable` | 2/3 | 2020 final value drag and Sharpe drag |
| `shadow_2008_candidate` | `research_only_multi_window_unstable` | 0/1 | Recent Sharpe drag and slightly worse MDD |
| `best_by_final_value` | `research_only_multi_window_unstable` | 0/1 | Recent final value drag exceeds 2% |
| `best_by_max_drawdown` | `research_only_multi_window_unstable` | 0/1 | Recent final value drag exceeds 2% |
| `best_by_sharpe` | `research_only_multi_window_unstable` | 0/1 | Recent final value drag exceeds 2% |

Key numeric details from the run:

- `garch_selector_frozen`: worst final delta +1.69%, worst Sharpe delta +0.0127, worst MDD delta -0.0123.
- `garch_guard_frozen`: worst final delta -3.33%, worst Sharpe delta -0.0271, worst MDD delta +0.0059.
- `shadow_2008_candidate`: final delta -0.31%, Sharpe delta -0.0332, MDD delta -0.0001.
- NCF overlay `best_by_*` candidates: final value drag ranged from -2.46% to -2.89%.

## Verification

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py
.venv/bin/python -m pytest -q tests/test_evaluate_group_a_plus_multi_window_gate.py
```

Result: 3 tests passed.

## Conclusion

No candidate currently clears the strict multi-window promotion gate. The work should remain research-only unless a candidate can pass the recession/stress windows and the recent live-like window without worse drawdown, worse Sharpe, or material final value drag.
