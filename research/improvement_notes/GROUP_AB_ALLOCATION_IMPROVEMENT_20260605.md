# Group A / Group B Allocation Improvement

Date: 2026-06-05
Status: Shadow improvement complete

## Scope

Continue improving the Group A / Group B allocator after the first quarterly/drift sweep.

Tested:

- Regime-based allocator using previous-day Group A drawdown and 21-day momentum.
- Finer static allocation sweep around `60A / 40B`.

No model retraining was performed.

## Regime Allocator Result

The first dynamic allocator changed weights among:

- normal: `70A / 30B`
- caution: `60A / 40B`
- risk-off: `40A / 60B`

It did not improve the strategy.

| Variant | Final value | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `70/60/40 default` | `5,379,082` | `2.3998` | `-20.73%` | `64` | `30,798` |
| `70/60/50 conservative` | `5,499,351` | `2.3763` | `-20.92%` | `35` | `10,410` |
| `65/60/50 conservative` | `5,447,241` | `2.4244` | `-20.29%` | `35` | `7,105` |
| `70/60/55 slow` | `5,550,260` | `2.3952` | `-21.22%` | `32` | `7,885` |

Interpretation:

- The dynamic allocator is too reactive for this window.
- Transfer cost and late de-risking reduce performance.
- Fixed quarterly allocation is currently superior.

## Static Micro Sweep

Quarterly-or-drift, drift threshold `5%`, transfer cost `0.1425%`.

| Allocation | Final value | Annual return | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `60A / 40B` | `5,469,465` | `51.54%` | `2.5207` | `-19.47%` | `10` | `806` |
| `62.5A / 37.5B` | `5,515,384` | `52.06%` | `2.4972` | `-19.75%` | `10` | `788` |
| `65A / 35B` | `5,561,362` | `52.59%` | `2.4736` | `-20.16%` | `10` | `766` |
| `67.5A / 32.5B` | `5,607,396` | `53.11%` | `2.4500` | `-20.62%` | `10` | `739` |
| `70A / 30B` | `5,653,480` | `53.62%` | `2.4265` | `-21.07%` | `10` | `708` |

## Recommendation

Use fixed quarterly allocation, not regime allocation, for the next shadow cycle.

Recommended candidate:

- `62.5% Group A / 37.5% Group B`
- Quarterly rebalance
- Drift threshold `5%`
- Transfer cost `0.1425%`

Reason:

- It improves final value by about `46k` versus `60A / 40B`.
- MDD stays under `-20%`.
- Rebalance count remains only `10`.

Aggressive candidate:

- `65% Group A / 35% Group B`
- Final value improves another `46k` versus `62.5A / 37.5B`.
- MDD worsens slightly to `-20.16%`.

## Outputs

- `results/group_ab_allocation_quarterly_drift05_micro_20240102_20260604.json`
- `results/group_ab_allocation_quarterly_drift05_micro_20240102_20260604.csv`
- `results/group_ab_allocation_quarterly_drift05_micro_20240102_20260604_curve.csv`
- `results/group_ab_regime_allocator_70_60_40_20240102_20260604.json`
- `results/group_ab_regime_allocator_70_60_50_conservative_20240102_20260604.json`
- `results/group_ab_regime_allocator_65_60_50_conservative_20240102_20260604.json`
- `results/group_ab_regime_allocator_70_60_55_slow_20240102_20260604.json`
