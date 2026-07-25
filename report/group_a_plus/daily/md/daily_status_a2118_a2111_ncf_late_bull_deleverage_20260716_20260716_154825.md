# GroupA+ Daily Status

Generated: `2026-07-16T15:48:25`
Check date: `2026-07-16`
Overall: `ok`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| live_signal_success | `ok` | live signal loaded |
| execution_allowed | `ok` | allowed |
| data_freshness | `ok` | 1 business days stale, 1 calendar days stale |
| strategy_status | `ok` | strategy_status=active, strategy_id=a2118_a2111_ncf_late_bull_deleverage |
| source_freshness | `ok` | all required sources ok |
| cash_constraint | `ok` | estimated_cash_after_rounding_before_cost=300,289 |
| execution_plan_pre_trade_guard | `ok` | pre_trade_guards= |
| dfl_advisory_frozen_input_staleness | `ok` | frozen backtest last covers 2026-07-13 (3 calendar days behind check_date); matched_decision_count is structurally 0 until this is re-run |

## Signal

- Group A status: `hold_or_align_to_target`
- Reason: `A20.7 formal defensive state is inactive`
- Actual data date: `2026-07-15`
- Business stale days: `1`
- Calendar stale days: `1`

## GroupA+

- Profile: `a2118_a2111_ncf_late_bull_deleverage`
- Overlay regime: `golden1`
- 00679B target weight: `0.00%`
- Cash after cost: `300,289`

## Pre-Trade Guard

- Status: `inactive`
- 00631L add: `allowed`
- Policy: `advisory_no_auto_weight_change`

## A21.18 DFL Shadow Ensemble

- Level: `none`
- Manual review: `False`
- Policy: `shadow_only_no_auto_weight_change`
- `base` action `KEEP` active `False` reliability `None`
- `p50` action `KEEP` active `False` reliability `None`
- `p70` action `KEEP` active `False` reliability `None`

## 00631L Compounding Guard

- Status: `inactive`
- 00631L add: `allowed`
- Regime: `TRANSITIONAL`
- Policy: `maintain_a2118_no_active_overlay`

## 00631L Compounding Regime

- Regime: `TRANSITIONAL`
- Policy: `maintain_a2118_no_active_overlay`
- Trend score: `1`
- Mean-reversion score: `2`
- AR1 5d / 20d: `-0.8976991083904954` / `0.03393544506771231`
- Variance ratio: `1.0061380506533284`
- 00631L vs 0050 relative momentum: `-0.011013840383404583`

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
