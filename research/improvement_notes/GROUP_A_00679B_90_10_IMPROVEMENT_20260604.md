# Group A + 00679B 90/10 Improvement

Date: 2026-06-04
Status: Shadow research only

## Purpose

Continue the `90% Group A / 10% 00679B` branch as the practical defensive overlay candidate. `Golden1_0531` production remains unchanged.

## Backtest Window

- Requested: `2024-01-01` to `2026-06-04`
- Actual trading window: `2024-01-02` to `2026-06-04`
- Rows: `584`
- Source Group A curve: `results/group_a_tdcc_latest_backtest_20240101_20260604.json`

## Improvement

The previous 90/10 check used idealized daily rebalancing. The new reusable harness evaluates:

- ideal daily rebalancing
- practical calendar/drift rebalancing
- commission `0.1425%`
- 00679B sell tax `0.1%`

New harness:

- `backtest_group_a_00679b_overlay.py`

## Quarterly 90/10 Result

Using quarterly-or-drift rebalancing with drift threshold `5%`:

| Strategy | Final value | Sharpe | MDD | Rebalances | Total cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `100% Group A` | `3,151,915` | `2.1551` | `-28.15%` | `0` | `0` |
| `90% Group A / 10% 00679B` | `2,814,116` | `2.1486` | `-25.81%` | `10` | `554` |

Compared with `100% Group A`, quarterly 90/10:

- reduces MDD by about `2.34` percentage points
- keeps Sharpe nearly flat (`-0.0065`)
- gives up about `337,799` final value
- needs only `10` overlay rebalances across the full window

## Weight Sweep

Quarterly-or-drift, drift threshold `5%`:

| Variant | Final value | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `95/5` | `2,979,390` | `2.1533` | `-26.90%` | `10` | `298` |
| `92.5/7.5` | `2,895,858` | `2.1514` | `-26.35%` | `10` | `431` |
| `90/10` | `2,814,116` | `2.1486` | `-25.81%` | `10` | `554` |
| `87.5/12.5` | `2,734,139` | `2.1450` | `-25.26%` | `10` | `668` |
| `85/15` | `2,655,905` | `2.1404` | `-24.72%` | `10` | `771` |

## Interpretation

`90/10` is still a good practical candidate if the goal is visible drawdown reduction without turning the strategy into a low-return defensive allocation.

`95/5` is better if the goal is to preserve return and Sharpe while adding a small stabilizer. `85/15` is better only if reducing drawdown is more important than preserving return.

## Recommendation

Promote the shadow focus from `80/20` to `90/10 quarterly-or-drift` for the next observation cycle.

Recommended shadow settings:

- Group A sleeve: `90%`
- 00679B sleeve: `10%`
- Calendar rebalance: `quarterly`
- Drift threshold: `5%`
- Keep production `Golden1_0531` unchanged

## Outputs

- `results/group_a_00679b_overlay_quarterly_90_10_sweep_20240102_20260604.json`
- `results/group_a_00679b_overlay_quarterly_90_10_sweep_20240102_20260604.csv`
- `results/group_a_00679b_overlay_quarterly_90_10_sweep_20240102_20260604_curve.csv`
- `results/group_a_00679b_overlay_90_10_quarterly_drift05_20240102_20260604.json`
