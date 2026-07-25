# GroupA+ Promotion Blocked Diagnostic

- Promotion decision: `blocked_model_gates_manual_approval_pending`
- Blocking gates: `['panel_drift', 'multi_window']`
- Metrics status: `fail`
- Deployment summary gate: `pass`

## Panel Drift

- Status: `fail`
- Reason: `drift exceeds limits: ensemble_prob_up, h20_prob_up, confidence`
- `ensemble_prob_up` tier `diagnostic` delta `0.24570435280144232` limit `0.15` date `2025-05-09`
- `h20_prob_up` tier `trigger_critical` delta `0.26368676066031893` limit `0.15` date `2025-09-18`
- `confidence` tier `trigger_critical` delta `0.49140870560288463` limit `0.28` date `2025-05-09`

## Multi-Window

- Status: `fail`
- Reason: `no candidate passed the multi-window gate`
- Criteria: `{'min_pass_ratio': 1.0, 'max_final_drawdown_pct': 0.02, 'min_sharpe_delta': 0.0, 'require_mdd_nonworse': True}`

## Deployment Consistency

- Status: `pass`

## Manual Approval Pending

- `gift_signed_approval_record_missing_or_invalid`
- `gift_human_exception_not_approved`
- `gift_signed_approval_manual_completion_pending`

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
