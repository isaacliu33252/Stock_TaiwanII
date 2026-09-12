# GroupA+ Guarded Retraining Candidate Shadow

- Generated: `2026-08-15T05:22:27`
- Status: `shadow_review`
- Policy: `research_only_no_latest_replacement`
- Backtest: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815.json`
- Inverse gate: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/inverse_etf_manual_review_gate.json`

## Base Gate

- Decision: `promotion_candidate`
- Rationale: `At least one GroupA+ variant keeps return and Sharpe close enough to the base approximation.`
- Best return variant: `GroupA+_cap_guard_no_inverse`
- Best risk variant: `GroupA+_cap_guard_no_inverse`

## Guarded Decision

- Decision: `guarded_promotion_candidate`
- Guarded retrain candidates: `[]`
- Guarded promotion candidates: `['GroupA+_cap_guard_no_inverse']`
- Inverse-blocked candidates: `[]`
- Blocking reasons: `[]`
- Replace latest: `False`
- Tune latest: `False`

## Notes

- Research-only shadow review.
- No latest strategy, live signal, execution plan, or order file was changed.
