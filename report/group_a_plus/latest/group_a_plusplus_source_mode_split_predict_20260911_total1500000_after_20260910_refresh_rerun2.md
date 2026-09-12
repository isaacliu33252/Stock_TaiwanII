# GroupA++ Source Mode Split Predict 2026-09-11

- generated_at: `2026-09-10T22:57:53`
- actual_data_date: `2026-09-10`
- portfolio_value: `1,500,000`

| source | mode | signal data | market data | ncf631L | ncf00713 | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| golden1_0531_frozen_pinned | frozen/pinned signal + latest market replay | 2026-07-06 | 2026-09-08 | 2026-09-04 | 2026-09-08 | 69.1629% | 10.8371% | 0.0000% | 0.0000% | 12.0000% | 8.0000% | 9504 | 4375 | 0 | 2827 |
| golden1_0531_latestdata_rerun | latest-data rerun | 2026-07-06 | 2026-09-10 | 2026-09-07 | 2026-09-10 | 69.1629% | 10.8371% | 0.0000% | 0.0000% | 12.0000% | 8.0000% | 9504 | 4375 | 0 | 2827 |
| golden2_0830_frozen_pinned | frozen/pinned signal + latest market replay | 2026-08-28 | 2026-09-08 | 2026-08-28 | 2026-09-08 | 47.0000% | 10.1039% | 16.4782% | 0.0000% | 12.0000% | 14.4179% | 6459 | 4079 | 25403 | 2827 |
| golden2_0830_latestdata_rerun | latest-data rerun | 2026-08-28 | 2026-09-10 | 2026-08-28 | 2026-09-10 | 47.0000% | 10.1039% | 16.4782% | 0.0000% | 12.0000% | 14.4179% | 6459 | 4079 | 25403 | 2827 |
| latest_groupA++ | active latest strategy | 2026-09-07 | 2026-09-10 | None | 2026-09-10 | 53.0000% | 17.1668% | 0.0000% | 0.0000% | 12.0000% | 17.8332% | 7283 | 6931 | 0 | 2827 |

## Explanation

- Why latest-data rows match: Golden1 latest-data rerun, Golden2 latest-data rerun, and latest all use the same Golden1/last PPO mainline under current artifacts, then the same GroupA++ 00713 sleeve.
- Why frozen rows differ: Frozen/pinned rows keep older signal dates and therefore preserve historical weights.
- Use `latest_groupA++` for orders.

## Source Notes

- `golden1_0531_frozen_pinned`: Keeps the pinned Golden1 signal; useful for version comparison, not a latest-data rerun. Path: `results/group_a_plusplus_golden1_0531_override_runner_20260911_total1500000.json`
- `golden1_0531_latestdata_rerun`: Regenerated from latest available data; expected to match latest base line when the same Golden1/last PPO mainline is used. Path: `results/group_a_plusplus_golden1_0531_override_runner_latestdata_20260911_total1500000_after_20260910_refresh_rerun.json`
- `golden2_0830_frozen_pinned`: Keeps the frozen 2026-08-28 Golden2 signal; preserves the historical 00632R leg. Path: `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260911_total1500000.json`
- `golden2_0830_latestdata_rerun`: Regenerated from latest data. Current frozen Golden2 model/result artifact is byte-identical to Golden1/last PPO, so it converges. Path: `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_latestdata_20260911_total1500000_after_20260910_refresh_rerun.json`
- `latest_groupA++`: Order source. Path: `results/group_a_plus_live_signal_v2_20260911_total1500000_after_20260910_refresh_rerun.json`
