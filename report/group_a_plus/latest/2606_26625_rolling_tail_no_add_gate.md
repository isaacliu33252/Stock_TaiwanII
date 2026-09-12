# 2606.26625 Rolling Tail No-Add Gate

- Status: `available_for_shadow_monitoring`
- As of: `2026-09-07`
- 00631L add: `blocked`
- 00632R open: `allowed`
- Policy: `research_only_rolling_tail_no_add_gate_no_weight_change`

| window | latest ES95 | no-00631L ES95 | no-00632R ES95 | no-LETF ES95 | Hill xi95 | block 00631L | block 00632R |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 63 | 0.0442 | 0.0262 | 0.0442 | 0.0262 | NA | `True` | `False` |
| 126 | 0.0381 | 0.0226 | 0.0381 | 0.0226 | NA | `True` | `False` |
| 252 | 0.0352 | 0.0206 | 0.0352 | 0.0206 | 0.2344 | `True` | `False` |

## Boundary

- Shadow monitoring only.
- No target-weight change.
- No automatic rebalance.
- No order generation.
