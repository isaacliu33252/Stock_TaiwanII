# 2609.04917 Controlled Adaptation Rollback Plan

- policy: shadow_only_rollback_plan_no_weight_change
- live_execution_effect: none
- applies_to: any future Group A++ candidate considered under the 2609.04917 controlled-adaptation gate

## Rollback Trigger

- A promoted candidate breaches its predeclared max drawdown, turnover, cost, or execution error limit.
- Same-date signal, execution plan, or broker reconciliation becomes unavailable.
- Any required data source loses point-in-time freshness.
- Human reviewer revokes approval.

## Rollback Action

- Stop using the candidate for live target-weight changes.
- Restore the latest pre-candidate Group A++/Group A+ strategy pointer.
- Keep generated reports and point-in-time snapshots append-only.
- Rebuild daily artifact integrity, profit deployment readiness, alpha-translation readiness, and controlled-adaptation reports after rollback.

## Boundary

This document is a rollback plan only. It does not approve promotion, does not create orders, and does not authorize target-weight changes.
