# Group A+ Daily Artifact Integrity

- Status: `warning`
- Check date: `2026-08-24`
- Policy: `diagnostic_only_no_strategy_change_no_weight_change`

## Checks

- `ok` live_signal artifact available
- `ok` execution_plan artifact date aligned
- `ok` execution_plan PIT snapshot available
- `ok` golden1_0531_release PIT snapshot available
- `ok` NCF panel refresh recommendation available
- `warning` NCF decision calibration artifact missing

## Warnings

- NCF decision calibration artifact missing

## Decision Boundary

- Target weight change allowed: `False`
- Creates orders: `False`
