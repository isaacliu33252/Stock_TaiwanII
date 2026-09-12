# GroupA++ Golden1 / Golden2 / Latest Predict 2026-09-07

- generated_at: `2026-09-07T07:59:56`
- actual_data_date: `2026-09-04`
- portfolio_value: `1,000,000`
- latest_strategy_00713_sleeve: `12.00%`

| source | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh | ncf_00713 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| golden1_0531_groupA++ | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 | full_sleeve_allowed |
| golden2_0830_groupA++_whatif | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 | full_sleeve_allowed |
| latest_groupA++ | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 | full_sleeve_allowed |

## Decision

- Use `latest_groupA++` for orders.
- `golden1_0531_groupA++` and `golden2_0830_groupA++_whatif` are comparators.
- `golden2_0830` frozen release files were not modified.

## Latest Data Confirmation

- `golden1_0531_groupA++` base signal was regenerated from latest available data through `2026-09-04`.
- `golden2_0830_groupA++_whatif` base signal was regenerated from latest available data through `2026-09-04`.
- Both comparator runners used `results/ncf_00631l_panel_latest_20260907.csv`, whose last panel date is `2026-09-04`.
- `ncf_00713` used `results/ncf_00713_latest_20260907.json`, with actual signal date `2026-09-04`.
- The prior `2026-08-28` frozen golden2 signal/panel was not used for this latest-data rerun.
