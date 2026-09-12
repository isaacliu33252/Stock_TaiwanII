# Group A+ Daily Artifact Integrity

- Status: `error`
- Check date: `2026-09-09`
- Policy: `diagnostic_only_no_strategy_change_no_weight_change`

## Checks

- `ok` live_signal artifact available
- `error` execution_plan actual_data_date does not match live_signal
- `ok` execution_plan PIT snapshot available
- `ok` golden1_0531_release PIT snapshot available
- `ok` NCF panel refresh recommendation available
- `ok` NCF decision calibration realized labels available

## Errors

- execution_plan actual_data_date does not match live_signal

## Decision Boundary

- Target weight change allowed: `False`
- Creates orders: `False`
