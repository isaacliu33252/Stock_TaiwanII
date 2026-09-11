# 2609.07946 Complementarity Promotion Gate

- generated_at: `2026-09-12T07:45:57`
- policy: `promotion_governance_only_no_orders_no_live_weight_change`
- any_ready_for_live_review: `False`
- min_observations: `20`
- min_triggers: `3`

| variant | observations | triggers | realized_triggers | avg_net_delta | ready_for_live_review |
|---|---:|---:|---:|---:|---:|
| stock_bond_gold | 1 | 0 | 0 |  | `False` |
| bond_only | 2 | 0 | 0 |  | `False` |

## Decision

- Do not change latest GroupA++ target weights, execution plans, or orders.
- Continue forward shadow until the gate has enough realized observations.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
