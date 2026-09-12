# 2608.08405 Assigned Vs Realized Deployment Shadow

- status: blocked
- policy: research_only_assigned_realized_deployment_audit_no_weight_change
- live_signal_date: 2026-09-07
- execution_plan_date: 2026-08-31
- broker_sample_last_transaction_date: 2026-07-17
- assigned_live_targets_logged: True
- execution_plan_targets_logged: True
- realized_authoritative_positions_logged: False
- capacity_scaling_allowed: False

## Blocking Reasons
- execution_plan_stale_vs_live_signal
- broker_positions_not_authoritative
- broker_holdings_not_reconciled
- realized_fill_or_deployment_series_missing

## Comparison
- 0050.TW: assigned=4791, plan=5432, broker_sample=-2304, plan_minus_assigned=641, realized_minus_assigned=-7095
- 0056.TW: assigned=None, plan=None, broker_sample=4863, plan_minus_assigned=None, realized_minus_assigned=None
- 00631L.TW: assigned=4583, plan=2241, broker_sample=500, plan_minus_assigned=-2342, realized_minus_assigned=-4083
- 00632R.TW: assigned=0, plan=13078, broker_sample=None, plan_minus_assigned=13078, realized_minus_assigned=None
- 00646.TW: assigned=None, plan=None, broker_sample=1032, plan_minus_assigned=None, realized_minus_assigned=None
- 00679B.TWO: assigned=0, plan=0, broker_sample=3000, plan_minus_assigned=0, realized_minus_assigned=3000
- 00713.TW: assigned=1891, plan=None, broker_sample=500, plan_minus_assigned=None, realized_minus_assigned=-1391
- 00751B.TWO: assigned=None, plan=None, broker_sample=4000, plan_minus_assigned=None, realized_minus_assigned=None
- 00878.TW: assigned=None, plan=None, broker_sample=2747, plan_minus_assigned=None, realized_minus_assigned=None
- UNKNOWN:富邦台50: assigned=None, plan=None, broker_sample=-222, plan_minus_assigned=None, realized_minus_assigned=None
- UNKNOWN:日掦: assigned=None, plan=None, broker_sample=0, plan_minus_assigned=None, realized_minus_assigned=None
- UNKNOWN:普萊德: assigned=None, plan=None, broker_sample=-1000, plan_minus_assigned=None, realized_minus_assigned=None
- UNKNOWN:玉山金: assigned=None, plan=None, broker_sample=-71, plan_minus_assigned=None, realized_minus_assigned=None
- UNKNOWN:群益ESG投等債20+: assigned=None, plan=None, broker_sample=0, plan_minus_assigned=None, realized_minus_assigned=None

## Decision
Assigned targets are available, but realized deployment/fill evidence is not authoritative and reconciled. Treat capacity evidence as blocked until same-run assigned, planned, and realized deployment series are logged.
