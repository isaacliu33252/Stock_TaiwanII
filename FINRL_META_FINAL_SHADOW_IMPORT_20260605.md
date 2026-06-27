# FinRL-Meta Final Shadow Import 2026-06-05

## Imported Shadow Tools

Implemented the last requested import pass as a non-production shadow layer:

- Taiwan turbulence index
- Benchmark-relative risk gate vs 0050
- Square-root market impact cost estimate using 0050 dollar volume
- Promotion gate checks

Main script:

- `backtest_group_ab_shadow_risk_tools.py`

Outputs:

- `results/group_ab_shadow_risk_tools_20240102_20260604.json`
- `results/group_ab_shadow_risk_tools_20240102_20260604.csv`
- `results/group_ab_shadow_risk_tools_20240102_20260604_risk_diagnostic.csv`
- `results/group_ab_shadow_risk_tools_20240102_20260604_impact_log.csv`

## Backtest Window

2024-01-02 to 2026-06-04.

## Results

| Variant | Final | Sharpe | Sortino | Calmar | MDD | Events | Cost | Sqrt Impact |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base dynamic no-stress | 5,885,722 | 2.5780 | 3.2795 | 2.9564 | -19.01% | 7 | 1,866 | 26 |
| turbulence cap55 shadow | 5,806,863 | 2.6047 | 3.3001 | 2.9329 | -18.87% | 16 | 14,239 | 380 |
| benchmark underperf cap55 shadow | 5,885,722 | 2.5780 | 3.2795 | 2.9564 | -19.01% | 7 | 1,866 | 26 |
| turbulence or benchmark cap55 shadow | 5,806,863 | 2.6047 | 3.3001 | 2.9329 | -18.87% | 16 | 14,239 | 380 |

## Risk Diagnostics

- Turbulence risk-off days: 49 / 584
- Benchmark relative underperformance days: 0 / 584

The benchmark-relative gate did not trigger because the current A+B curve did not lag 0050 by more than the configured threshold.

## Promotion Gate

Promotion gate passed for the shadow candidate by rule:

- 2024-2026 Sharpe >= 2.50
- 2024-2026 MDD >= -20%
- Group A 2008 check keeps baseline 00632R hedge as the best stress result

However, the gate should be treated as a minimum eligibility check, not an automatic production promotion.

## Interpretation

The turbulence cap55 shadow improves Sharpe and slightly improves MDD, but lowers final value by about 78,859 and increases rebalance events/costs.

Therefore:

- Keep current live default:
  - `dynamic_lb126_band008_hold10_no2884_no_stress`
- Keep turbulence cap55 as a monitored defensive shadow:
  - useful if risk-adjusted stability becomes more important than final value
- Keep benchmark-relative gate enabled only as diagnostics for now:
  - it did not trigger in this window
- Keep square-root impact model as reporting/cost realism:
  - do not use it to change signals yet

## Recommendation

No change to the latest best production candidate.

The best current stack remains:

`Group A hold10 + Group B no2884 + A/B dynamic lb126 band0.080 no-stress`

The newly imported tools should remain in shadow reporting until validated on additional stress windows.
