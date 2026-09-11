# 2609.07946 Stock/Bond/Gold Forward Shadow

- generated_at: `2026-09-12T07:44:23`
- signal_date: `2026-09-10`
- policy: `forward_shadow_only_no_orders_no_live_weight_change`
- universe: `bond_plus_00635u`
- candidates: `00679B.TWO, 00751B.TWO, 00635U.TW`
- triggered: `False`
- best_complement: `00679B.TWO`
- best_complement_type: `bond`
- score_gap: `1.720505`
- threshold_passes: `False`
- momentum_5d_00631l: `0.049139`
- momentum_gate_passes: `False`
- realized_next_day_available: `False`
- net_delta_return: `None`

## Weights Delta

```json
{
  "0050.TW": 0.0,
  "00631L.TW": 0.0,
  "00632R.TW": 0.0,
  "00635U.TW": 0.0,
  "00679B.TWO": 0.0,
  "00713.TW": 0.0,
  "00751B.TWO": 0.0,
  "00878.TW": 0.0,
  "GC=F": 0.0,
  "cash": 0.0
}
```

## Decision

- Keep as forward shadow only.
- Do not change latest GroupA++ live weights, execution plans, or orders.
- `00635U.TW` executable use requires separate instrument review before any watchlist/core addition.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
