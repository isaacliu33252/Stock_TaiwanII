# 2608.20179 Dynamic CVaR Constraint Shadow

- Status: `blocked_for_live_promotion`
- As of: `2026-09-07`
- 00631L add: `blocked`
- Recommended 00631L add pacing: `0.0000`
- CVaR residual breach windows: `3`
- Latest worse than no-00631L ES95 windows: `3`
- Latest worse than no-LETF ES95 windows: `3`
- Policy: `research_only_dynamic_cvar_constraint_shadow_no_weight_change`

| window | ES95 | budget95 | residual95 | ES99 | budget99 | residual99 | state | pacing |
|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 63 | 0.0442 | 0.0304 | 0.0138 | 0.0618 | 0.0449 | 0.0168 | `adverse_cvar_breach` | 0.0000 |
| 126 | 0.0381 | 0.0233 | 0.0149 | 0.0522 | 0.0373 | 0.0149 | `adverse_cvar_breach` | 0.0000 |
| 252 | 0.0352 | 0.0200 | 0.0152 | 0.0498 | 0.0381 | 0.0117 | `adverse_cvar_breach` | 0.0000 |

## Baseline Relative ES95

| window | no-00631L delta | no-LETF delta | golden1_0531 delta | golden2_0830 delta |
|---:|---:|---:|---:|---:|
| 63 | 0.0180 | 0.0180 | 0.0040 | 0.0222 |
| 126 | 0.0156 | 0.0156 | 0.0035 | 0.0191 |
| 252 | 0.0146 | 0.0146 | 0.0032 | 0.0177 |

## Budget Sensitivity

| buffer | breach windows |
|---:|---:|
| 0.00 | 3 |
| 0.05 | 3 |
| 0.10 | 3 |
| 0.15 | 3 |
| 0.20 | 3 |

## Boundary

- Shadow monitoring only.
- No target-weight change.
- No automatic rebalance.
- No order generation.
