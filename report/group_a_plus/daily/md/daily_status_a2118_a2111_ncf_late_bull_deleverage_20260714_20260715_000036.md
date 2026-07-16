# GroupA+ Daily Status

Generated: `2026-07-15T00:00:36`
Check date: `2026-07-14`
Overall: `block`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `block` | required strategy sources are stale or missing: ['institutional_0050'] |
| data_freshness | `ok` | 0 business days stale, 0 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `block` | required strategy sources are stale or missing: ['institutional_0050']; institutional_0050 |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=300,419 |
| execution_plan_pre_trade_guard | `ok` | pre_trade_guards=blocked |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-14`
- Business stale days: `0`
- Calendar stale days: `0`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `300,419`

## Pre-Trade Guard

- Status: `blocked`
- 00631L add: `blocked`
- Policy: `advisory_no_auto_weight_change`
- Blocked: `00631L.TW` `buy` current `0` requested `560` guarded `0`

## A21.18 DFL Shadow Ensemble

- Level: `none`
- Manual review: `False`
- Policy: `shadow_only_no_auto_weight_change`
- `base` action `KEEP` active `False` reliability `None`
- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## 00631L Compounding Guard

- Status: `unavailable`
- 00631L add: `allowed`
- Regime: `None`
- Policy: `None`

## 00631L Compounding Regime

- Regime: `TRANSITIONAL`
- Policy: `maintain_a2118_no_active_overlay`
- Trend score: `3`
- Mean-reversion score: `2`
- AR1 5d / 20d: `-0.5899523246014116` / `0.07395513824913004`
- Variance ratio: `1.0612156114287676`
- 00631L vs 0050 relative momentum: `-0.02402539794240255`

## A21.18 DFL Advisory

- Action: `KEEP`
- Active: `False`
- Policy: `advisory_only_no_auto_weight_change`

### Selective Variants

- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## A21.18 DFL Active-Date Audit

- Conclusion: `passes_replay_audit_with_warnings_shadow_only`
- Active days: `7`
- Hard checks pass: `True`
- Warning days: `3`
- Existing guard overlap days: `0`
- Total estimated cost bps / 1M: `8.074904151886141`
- Policy: `shadow_only_no_auto_weight_change`
