# GroupA+ Promotion Blocked Diagnostic

- Promotion decision: `blocked_deployment_consistency_and_model_gates`
- Blocking gates: `['panel_drift', 'multi_window', 'deployment_consistency', 'deployment_summary']`
- Metrics status: `fail`
- Deployment summary gate: `fail`

## Panel Drift

- Status: `fail`
- Reason: `drift exceeds limits: h20_prob_up`
- `h20_prob_up` tier `trigger_critical` delta `0.1982313917525921` limit `0.15` date `2026-02-10`

## Multi-Window

- Status: `fail`
- Reason: `no candidate passed the multi-window gate`
- Criteria: `{'min_pass_ratio': 1.0, 'max_final_drawdown_pct': 0.02, 'min_sharpe_delta': 0.0, 'require_mdd_nonworse': True}`

## Deployment Consistency

- Status: `fail`
- `ops_health_errors_present`
- `gift_signed_approval_validator_smoke_failed`
- `deployment_consistency_status:blocked`
- `deployment_consistency_not_broker_actionable`

## Manual Approval Pending

- `gift_signed_approval_record_missing_or_invalid`
- `gift_human_exception_not_approved`
- `gift_signed_approval_manual_completion_pending`

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
