# GroupA++ Golden1 / Golden2 / Latest Predict 2026-09-11

- generated_at: `2026-09-10T22:55:58`
- actual_data_date: `2026-09-10`
- portfolio_value: `1,500,000`
- latest_strategy_00713_sleeve: `12.00%`

| source | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh | ncf_00713 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| golden1_0531_groupA++ | 69.1629% | 10.8371% | 0.0000% | 0.0000% | 12.0000% | 8.0000% | 9504 | 4375 | 0 | 2827 | date_mismatch_keep_base |
| golden2_0830_groupA++_whatif | 47.0000% | 10.1039% | 16.4782% | 0.0000% | 12.0000% | 14.4179% | 6459 | 4079 | 25403 | 2827 | date_mismatch_keep_base |
| latest_groupA++ | 53.0000% | 17.1668% | 0.0000% | 0.0000% | 12.0000% | 17.8332% | 7283 | 6931 | 0 | 2827 | date_mismatch_keep_base |

## Decision

- `latest_groupA++` is the active strategy source, but order execution still requires `execution_allowed=true`.
- `golden1_0531_groupA++` and `golden2_0830_groupA++_whatif` are lockdown comparators.
- `golden1_0531` and `golden2_0830` frozen release files were not modified.
