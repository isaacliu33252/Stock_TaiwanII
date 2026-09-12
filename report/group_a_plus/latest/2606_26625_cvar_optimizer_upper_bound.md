# 2606.26625 CVaR-Optimizer Upper Bound (In-Sample, Diagnostic Only)

- Status: `diagnostic_only`
- As of: `2026-08-31`
- Valid windows: `5`
- Optimizer beats latest on ES95 in: `5` windows
- Optimizer beats latest on MDD in: `5` windows
- Mean ES95 gap (latest - optimizer): `0.0118`
- Mean MDD gap (optimizer - latest): `0.1075`

| window | latest ES95 | optimizer ES95 | ES95 gap | latest MDD | optimizer MDD | MDD gap |
|---|---:|---:|---:|---:|---:|---:|
| covid_2020 | 0.0204 | 0.0055 | 0.0149 | -0.1410 | -0.0256 | 0.1154 |
| rate_hike_2022 | 0.0149 | 0.0024 | 0.0125 | -0.1989 | -0.0192 | 0.1797 |
| post_2023 | 0.0170 | 0.0031 | 0.0138 | -0.1550 | -0.0364 | 0.1186 |
| recent_2024_2026 | 0.0193 | 0.0035 | 0.0157 | -0.1550 | -0.0391 | 0.1158 |
| active_2025_2026 | 0.0188 | 0.0168 | 0.0020 | -0.1550 | -0.1470 | 0.0080 |

## Boundary

- Diagnostic only: in-sample look-ahead upper bound, not walk-forward.
- Does not account for transaction costs.
- Not a live optimizer; no target-weight change, no orders, no rebalance.
