# GroupA+ Final Governance Snapshot

- As of: `2026-08-06`
- Actual data date: `2026-08-05`
- Strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Daily status: `warn` stage `final`
- Ops pipeline: `ok` date `20260805`
- Promotion decision: `blocked_deployment_consistency_and_model_gates`
- Promotion blocking gates: `['panel_drift', 'multi_window', 'deployment_consistency', 'deployment_summary']`
- Deployment summary gate: `fail`
- Deployment consistency gate: `fail`
- Deployment summary consistency: `ok`
- Promotion diagnostic: `blocked`
- Broker actionable: `False`

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- 00631L add allowed: `False`
- 00632R open allowed: `False`
- Golden1_0531 unchanged: `True`

## Deployment Warnings

- `gift_signed_approval_record_missing_or_invalid`
- `gift_human_exception_not_approved`
- `gift_signed_approval_manual_completion_pending`
- `cash_balance_zero_with_nonzero_trades`
- `execution_plan_not_allowed`
- `manual_confirmation_required`
