# GroupA++ Strategy Source Comparison

- generated_at: `2026-09-05T22:07:15`
- as_of: `2026-09-08`
- actual_data_date: `2026-09-04`
- portfolio_value: `1000000.00`

## Decision

- Can run: `True`
- Use for orders: `groupA++_latest_strategy`
- Golden2 gate: `research_only_no_multi_window_pass`
- Golden2 pass ratio: `2/4`

## Weights And Shares

| source | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00713 sh | cash after rounding | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| golden1_0531_current_resolved | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 0.0000% | 30.0000% | 4883 | 4722 | 0 | 300110.22 | production_source |
| golden1_0531_frozen_release_snapshot | 58.9243% | 11.0757% | 0.0000% | 0.0000% | 0.0000% | 30.0000% | 5461 | 3022 | 0 | 300032.01 | production_implementation_release |
| golden2_0830_prediction | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 0.0000% | 30.0000% | 4883 | 4722 | 0 | 300110.22 | research_only_no_multi_window_pass |
| groupA++_latest_strategy | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 5.0000% | 25.0000% | 4883 | 4722 | 788 | 250111.61 | active |

## Notes

- `groupA++_latest_strategy` is the execution source.
- `golden2_0830` remains research-only because its multi-window gate did not pass.
- `00713.TW` is funded from cash at 5%; `0050.TW` and `00631L.TW` are not reduced.
