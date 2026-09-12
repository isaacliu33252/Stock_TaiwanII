# GroupA+ Guarded Retraining Candidate Shadow

- Generated: `2026-08-15T00:54:14`
- Status: `blocked`
- Policy: `research_only_no_latest_replacement`
- Backtest: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815.json`
- Inverse gate: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/inverse_etf_manual_review_gate.json`

## Base Gate

- Decision: `promotion_candidate`
- Rationale: `At least one GroupA+ variant keeps return and Sharpe close enough to the base approximation.`
- Best return variant: `GroupA+_focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03`
- Best risk variant: `GroupA+_focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03`

## Guarded Decision

- Decision: `blocked_by_inverse_etf_governance`
- Guarded retrain candidates: `[]`
- Guarded promotion candidates: `[]`
- Inverse-blocked candidates: `['GroupA+_cap_guard_optimized', 'GroupA+_focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03']`
- Blocking reasons: `['inverse_etf_candidates_blocked_before_retraining_review']`
- Replace latest: `False`
- Tune latest: `False`

## Notes

- Research-only shadow review.
- No latest strategy, live signal, execution plan, or order file was changed.
