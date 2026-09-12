# GroupA++ Source Mode Split Predict 2026-09-08

- generated_at: `2026-09-07T13:19:16`
- actual_data_date: `2026-09-04`
- portfolio_value: `1,000,000`

| source | mode | signal data | market data | ncf631L | ncf00713 | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| golden1_0531_frozen_pinned | frozen/pinned signal + latest market replay | 2026-07-06 | 2026-09-04 | 2026-09-04 | 2026-09-04 | 69.1629% | 10.8371% | 0.0000% | 0.0000% | 12.0000% | 8.0000% | 6409 | 2957 | 0 | 1891 |
| golden1_0531_latestdata_rerun | latest-data rerun | 2026-09-04 | 2026-09-04 | 2026-09-04 | 2026-09-04 | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 |
| golden2_0830_frozen_pinned | frozen/pinned signal + latest market replay | 2026-08-28 | 2026-09-04 | 2026-08-28 | 2026-09-04 | 47.0000% | 10.1039% | 16.4782% | 0.0000% | 12.0000% | 14.4179% | 4355 | 2757 | 16797 | 1891 |
| golden2_0830_latestdata_rerun | latest-data rerun | 2026-09-04 | 2026-09-04 | 2026-09-04 | 2026-09-04 | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 |
| latest_groupA++ | active latest strategy | 2026-09-04 | 2026-09-04 | 2026-09-04 | 2026-09-04 | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 12.0000% | 18.0000% | 4883 | 4722 | 0 | 1891 |

## Explanation

- Why latest-data rows match: Golden1 latest-data rerun, Golden2 latest-data rerun, and latest all use the same Golden1/last PPO mainline under current artifacts, then the same GroupA++ 00713 sleeve.
- Why frozen rows differ: Frozen/pinned rows keep older signal dates and therefore preserve historical weights.
- Use `latest_groupA++` for orders.

## Source Notes

- `golden1_0531_frozen_pinned`: Keeps the pinned Golden1 signal; useful for version comparison, not a latest-data rerun. Path: `results/group_a_plusplus_golden1_0531_override_runner_20260908_current12.json`
- `golden1_0531_latestdata_rerun`: Regenerated from latest available data; expected to match latest base line when the same Golden1/last PPO mainline is used. Path: `results/group_a_plusplus_golden1_0531_override_runner_latestdata_20260908_current12.json`
- `golden2_0830_frozen_pinned`: Keeps the frozen 2026-08-28 Golden2 signal; preserves the historical 00632R leg. Path: `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260908_current12.json`
- `golden2_0830_latestdata_rerun`: Regenerated from latest data. Current frozen Golden2 model/result artifact is byte-identical to Golden1/last PPO, so it converges. Path: `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_latestdata_20260908_current12.json`
- `latest_groupA++`: Order source. Path: `results/group_a_plusplus_live_signal_v2_predict_20260908_from_20260904_total1000000_latest_strategy_current12.json`
