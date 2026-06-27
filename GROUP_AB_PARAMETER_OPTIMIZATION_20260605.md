# Group A+B Parameter Optimization 2026-06-05

## Scope

- Window: 2024-01-02 to 2026-06-04
- Base inputs:
  - Group A: `hold_limit_00632r_10d_to_0050`
  - Group B: latest no-2884 curve
- Method: no retraining; grid search over A/B governance parameters only.
- Candidates evaluated: 768
- Output:
  - `results/group_ab_governance_optimization_20240102_20260604.json`
  - `results/group_ab_governance_optimization_20240102_20260604.csv`
  - `results/group_ab_governance_optimization_20240102_20260604_curve.csv`

## Best Balanced Candidate

Variant: `opt_lb126_b0.120_base0.600_lo0.55_hi0.70_min50000_cd10_nostress`

Metrics:

- Final value: `5,880,921.34`
- Annual return: `56.1490%`
- Sharpe: `2.5956`
- Sortino: `3.3078`
- Calmar: `2.9659`
- Max drawdown: `-18.9317%`
- Events: `7`
- Cost: `2,069.06`

Parameters:

- Dynamic lookback: `126`
- Dynamic band: `0.12`
- Base Group A weight: `0.60`
- Group A range: `0.55` to `0.70`
- Min transfer notional: `50,000`
- Cooldown: `10/20/30` all produced the same result in this window.
- Stress gate: disabled

## Highest Final Value Candidate

Variant: `opt_aggr_lb126_b0.080_base0.700_lo0.60_hi0.85_min50000_cd20_nostress`

Metrics:

- Final value: `6,192,321.28`
- Sharpe: `2.5148`
- Sortino: `3.2662`
- Max drawdown: `-19.5512%`

This is viable only as an aggressive profile. It improves final value, but reduces Sharpe and pushes drawdown closer to the `-20%` floor.

## Adopted Change

Added the balanced optimized candidate to the formal governed backtest as:

`dynamic_lb126_band012_base060_hold10_no2884_optimized`

Formal rerun result:

- Final value: `5,880,921.34`
- Sharpe: `2.5956`
- Max drawdown: `-18.9317%`

Comparison with previous practical best:

- Previous: `dynamic_lb126_band008_hold10_no2884_no_stress`
- Previous final value: `5,885,721.88`
- Previous Sharpe: `2.5780`
- Previous max drawdown: `-19.0103%`

Conclusion: the optimized version is now the best risk-adjusted production candidate. The previous version still has slightly higher final value, but the optimized version has better Sharpe and lower drawdown.

