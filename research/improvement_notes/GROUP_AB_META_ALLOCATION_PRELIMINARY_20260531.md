# Group A / Group B Meta-Allocation Preliminary Study

Date: 2026-05-31
Status: Preliminary shadow research only

## 1. Question

Can Group A `Golden1_0531` benefit from considering Group B at the total-portfolio level?

Yes. The appropriate first design is a meta-allocation overlay above the existing Group A and Group B strategies. Do not merge both PPO models or alter the `Golden1_0531` production rules during its three-month trial.

## 2. Current Architecture

- Group A and Group B are currently evaluated with separate `initial_cash_per_group` accounts.
- Each group produces its own target allocation.
- There is no production capital allocator deciding how much total capital should be assigned to Group A versus Group B.

## 3. Preliminary Evidence

Inputs:

- Group A:
  - [`results/group_a_backtest_20250101_20260525_20260526_193252.json`](results/group_a_backtest_20250101_20260525_20260526_193252.json)
- Group B:
  - [`results/group_b_backtest_20240101_20260508_20260530_110011.json`](results/group_b_backtest_20240101_20260508_20260530_110011.json)

Method:

- Use the common OOS window from `2025-01-02` to `2026-05-08`.
- Remove recorded external DCA contributions from daily return calculations.
- Test idealized daily-rebalanced static Group A / Group B capital weights.

Observed daily-return correlation:

- `0.6141`

Selected static-weight results:

| Group A | Group B | Total return | Annual return | Sharpe | Max drawdown | Volatility |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `100%` | `0%` | `83.96%` | `61.13%` | `2.114` | `-25.99%` | `23.95%` |
| `80%` | `20%` | `66.80%` | `49.24%` | `2.019` | `-23.40%` | `20.98%` |
| `70%` | `30%` | `58.73%` | `43.56%` | `1.950` | `-22.08%` | `19.60%` |
| `60%` | `40%` | `50.97%` | `38.04%` | `1.861` | `-20.85%` | `18.32%` |
| `50%` | `50%` | `43.53%` | `32.68%` | `1.747` | `-19.81%` | `17.14%` |

## 4. Interpretation

- Group A remains the return engine.
- Group B acts as a lower-volatility stabilizer.
- A static `70% Group A / 30% Group B` shadow allocation is a reasonable first candidate when the goal is to preserve most of Group A's return while reducing drawdown.
- A static `60% Group A / 40% Group B` shadow allocation is a more defensive candidate.

## 5. Limitations

This is not production evidence:

- The calculation uses idealized daily rebalancing between groups.
- Group B's current primary evidence ends on `2026-05-08`, earlier than the latest Group A signal.
- The study does not yet include realistic cross-group rebalance thresholds, fees, tax, or a monthly allocation schedule.
- The study does not yet test whether Group B signals should influence the Group A risk gate.

## 6. Recommended Research Direction

Keep `Golden1_0531` frozen and run a separate shadow allocator:

- Normal regime:
  - `70% Group A / 30% Group B`
- Risk-off candidate:
  - `50% Group A / 50% Group B`
- Severe candidate:
  - `30% Group A / 70% Group B`

The allocator should rebalance only when the regime changes or when the group-weight drift exceeds a threshold. It should be validated with realistic fees before any promotion decision.
