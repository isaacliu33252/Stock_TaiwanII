# GroupA+ 00632R Inverse ETF Manual-Review Gate

- Generated: `2026-08-15T00:50:02`
- Status: `blocked`
- Policy: `research_only_inverse_etf_gate_no_live_weight_change`
- Execution plan: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/group_a_plus_execution_plan_20260805_latest_strategy_after_refresh_from_taiwan_stock_20260804.json`

## Plan Snapshot

- Requested as-of: `2026-08-05`
- Actual data date: `2026-08-04`
- Planning status: `ready`
- Manual confirmation required: `False`
- Current 00632R shares: `0`
- Target 00632R shares: `10189`

## Gate

- Gate status: `blocked`
- Side: `buy`
- Missing checks: `['artifact_freshness_verified', 'cost_basis_available', 'hedge_rationale_available', 'manual_approval_record_available', 'realized_pnl_review_available']`
- Allow 00632R auto trade: `False`

## Blocking Reasons

- `inverse_etf_trade_requires_manual_review`
- `missing_artifact_freshness_verified`
- `missing_cost_basis_available`
- `missing_hedge_rationale_available`
- `missing_manual_approval_record_available`
- `missing_realized_pnl_review_available`

## Decision

- Recommended use: `shadow_gate_input_for_retraining_candidate_review`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- No latest strategy, live signal, execution plan, or order file was changed.
