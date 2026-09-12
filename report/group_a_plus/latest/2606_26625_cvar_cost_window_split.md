# 2606.26625 CVaR/Cost Window Split

- Status: `blocked_for_live_promotion`
- As of: `2026-09-07`
- Policy: `research_only_cvar_cost_window_split_no_optimizer_no_weight_change`
- Valid windows: `5`
- Latest loses to no-00631L windows: `5`
- Latest loses to no-LETF windows: `5`

| window | latest ES95 | no-00631L ES95 | no-LETF ES95 | latest MDD | no-00631L MDD | no-LETF MDD | latest STARR95 | latest loses? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| covid_2020 | 0.0391 | 0.0234 | 0.0234 | -0.2580 | -0.1599 | -0.1599 | 1.0686 | `True` |
| rate_hike_2022 | 0.0278 | 0.0173 | 0.0173 | -0.3323 | -0.2330 | -0.2330 | -7.9718 | `True` |
| post_2023 | 0.0330 | 0.0200 | 0.0200 | -0.2878 | -0.1767 | -0.1767 | 13.5476 | `True` |
| recent_2024_2026 | 0.0375 | 0.0226 | 0.0226 | -0.2825 | -0.1761 | -0.1761 | 13.7233 | `True` |
| active_2025_2026 | 0.0376 | 0.0221 | 0.0221 | -0.2760 | -0.1764 | -0.1764 | 15.6951 | `True` |

## Decision

- Research/shadow only.
- No optimizer promotion.
- No target-weight change.
- No automatic rebalance.
- No `00631L.TW` add.
- No `00632R.TW` open.
- No `00679B.TWO` add.
