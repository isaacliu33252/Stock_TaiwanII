# Group A / Group B Allocation Sweep

Date: 2026-06-05 request, using market data through 2026-06-04
Status: Shadow allocation study complete

## Scope

Run steps 1 and 2:

1. Sweep Group A / Group B capital allocation.
2. Apply practical top-level rebalancing:
   - quarterly calendar rebalance
   - drift threshold `5%`
   - transfer cost estimate `0.1425%`

This uses existing Group A and Group B daily equity curves and does not retrain either model.

## Inputs

- Source curve: `results/group_ab_latest_no2884_backtest_20240101_20260605_curve.csv`
- Window: `2024-01-02` to `2026-06-04`
- Rows: `584`
- Initial total capital: `2,000,000`
- Group B excludes 玉山金 (`2884.TW`)

## Main Sweep

| Allocation | Final value | Annual return | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `30A / 70B` | `4,924,888` | `45.11%` | `2.7475` | `-16.23%` | `10` | `694` |
| `40A / 60B` | `5,104,872` | `47.28%` | `2.6912` | `-17.31%` | `10` | `797` |
| `50A / 50B` | `5,286,493` | `49.42%` | `2.6116` | `-18.39%` | `10` | `835` |
| `60A / 40B` | `5,469,465` | `51.54%` | `2.5207` | `-19.47%` | `10` | `806` |
| `70A / 30B` | `5,653,480` | `53.62%` | `2.4265` | `-21.07%` | `10` | `708` |
| `80A / 20B` | `5,838,211` | `55.68%` | `2.3341` | `-22.88%` | `10` | `542` |

## Focused Sweep

| Allocation | Final value | Annual return | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `55A / 45B` | `5,377,829` | `50.48%` | `2.5670` | `-18.93%` | `10` | `829` |
| `60A / 40B` | `5,469,465` | `51.54%` | `2.5207` | `-19.47%` | `10` | `806` |
| `65A / 35B` | `5,561,362` | `52.59%` | `2.4736` | `-20.16%` | `10` | `766` |
| `70A / 30B` | `5,653,480` | `53.62%` | `2.4265` | `-21.07%` | `10` | `708` |
| `75A / 25B` | `5,745,777` | `54.66%` | `2.3798` | `-21.98%` | `10` | `634` |

## Interpretation

Group B is the stabilizer. Raising Group A weight improves final value and annual return, but lowers Sharpe and increases drawdown.

Best candidates:

- Balanced candidate: `60A / 40B`
  - Final `5.47M`
  - Sharpe `2.5207`
  - MDD `-19.47%`
- Return candidate: `70A / 30B`
  - Final `5.65M`
  - Sharpe `2.4265`
  - MDD `-21.07%`

Compared with the current `50A / 50B`, `60A / 40B` adds about `183k` final value while keeping MDD below `-20%`. This is the best next shadow allocation if the target is to improve return without giving up too much stability.

## Recommendation

Use `60% Group A / 40% Group B` as the next practical shadow allocator:

- Calendar rebalance: quarterly
- Drift threshold: `5%`
- Transfer cost rate: `0.1425%`
- Keep Group A and Group B model internals unchanged

Keep `70A / 30B` as the aggressive candidate for comparison.

## Outputs

- `results/group_ab_allocation_quarterly_drift05_sweep_20240102_20260604.json`
- `results/group_ab_allocation_quarterly_drift05_sweep_20240102_20260604.csv`
- `results/group_ab_allocation_quarterly_drift05_sweep_20240102_20260604_curve.csv`
- `results/group_ab_allocation_quarterly_drift05_focused_20240102_20260604.json`
- `results/group_ab_allocation_quarterly_drift05_focused_20240102_20260604.csv`
- `results/group_ab_allocation_quarterly_drift05_focused_20240102_20260604_curve.csv`
