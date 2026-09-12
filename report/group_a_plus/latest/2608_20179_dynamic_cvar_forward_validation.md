# 2608.20179 Dynamic CVaR Forward Validation

- Status: `blocked_for_live_promotion`
- As of: `2026-09-07`
- Forward validation passed: `False`
- Pass windows: `0` / `3`
- Policy: `research_only_dynamic_cvar_forward_validation_no_weight_change`

| window | horizon | breach n | non-breach n | underperform lift | latest-no00631L lift | passed |
|---:|---:|---:|---:|---:|---:|---:|
| 63 | 5 | 772 | 0 | NA | NA | `False` |
| 63 | 10 | 767 | 0 | NA | NA | `False` |
| 63 | 20 | 757 | 0 | NA | NA | `False` |
| 126 | 5 | 709 | 0 | NA | NA | `False` |
| 126 | 10 | 704 | 0 | NA | NA | `False` |
| 126 | 20 | 694 | 0 | NA | NA | `False` |
| 252 | 5 | 583 | 0 | NA | NA | `False` |
| 252 | 10 | 578 | 0 | NA | NA | `False` |
| 252 | 20 | 568 | 0 | NA | NA | `False` |

## Residual Rank Split

| window | horizon | high n | low n | high-low underperform | high-low latest-no00631L | rank passed |
|---:|---:|---:|---:|---:|---:|---:|
| 63 | 5 | 160 | 169 | -0.0951 | 0.0036 | `False` |
| 63 | 10 | 160 | 169 | -0.0599 | 0.0060 | `False` |
| 63 | 20 | 160 | 169 | -0.1109 | 0.0121 | `False` |
| 126 | 5 | 164 | 143 | -0.0674 | 0.0032 | `False` |
| 126 | 10 | 164 | 141 | -0.1019 | 0.0057 | `False` |
| 126 | 20 | 164 | 141 | -0.0654 | 0.0073 | `False` |
| 252 | 5 | 122 | 122 | -0.0984 | 0.0022 | `False` |
| 252 | 10 | 122 | 122 | -0.1885 | 0.0040 | `False` |
| 252 | 20 | 122 | 115 | -0.3145 | 0.0117 | `False` |

## Boundary

- Shadow validation only.
- No target-weight change.
- No automatic rebalance.
- No order generation.
