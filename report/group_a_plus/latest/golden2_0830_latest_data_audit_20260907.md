# Golden2_0830 Latest Data Audit 2026-09-07

- requested check: confirm whether `golden2_0830` used latest data for the GroupA++ 2026-09-07 prediction.
- audit time: `2026-09-07`
- latest OHLCV available in DB: `2026-09-04`

## Finding

`golden2_0830` was **not fully using latest data** in the generated GroupA++ 2026-09-07 comparison.

The generated what-if runner:

- file: `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260907.json`
- backtest window end: `2026-09-04`
- GroupA++ 00713 NCF file: `results/ncf_00713_latest_20260907.json`
- 00713 NCF actual date: `2026-09-04`
- 00713 sleeve: `12%`

But the core frozen golden2 sources were still frozen at the release date:

- golden2 signal file: `results/golden2_0830/signal_group_a_golden2_0830_20260831.json`
- golden2 signal actual data date: `2026-08-28`
- golden2 00631L NCF panel: `results/golden2_0830/ncf_00631l_panel_golden2_0830.csv`
- golden2 00631L NCF panel last date: `2026-08-28`

## Important Distinction

`golden2_0830` is a frozen release. Its fixed source files are intentionally immutable and dated `2026-08-28`.

For the 2026-09-07 GroupA++ comparison:

- latest prices and share rounding used `2026-09-04` market prices.
- the replay window ran through `2026-09-04`.
- `ncf_00713` used the latest available `2026-09-04` signal.
- the frozen golden2 target signal and golden2 00631L NCF panel remained `2026-08-28`.

Therefore, the previous golden2 row should be read as:

> `golden2_0830` frozen-release weights replayed/rounded with latest 2026-09-04 market data plus latest 00713 sleeve gate.

It should **not** be read as:

> `golden2_0830` fully recomputed from latest 2026-09-04 data.

## Related File Name Caveat

The file below exists:

- `results/golden2_0830/group_a_plus_live_signal_v2_golden2_0830_predict_20260907_from_20260904_total_1m.json`

However, its content points to `results/group_a_combined_live_latest.json` and its target weights match the latest strategy, not golden2 frozen weights. It should not be used as the golden2 comparator.

## Decision

- Do not claim that `golden2_0830` fully references latest data.
- Keep `golden2_0830` as a frozen-release comparator only.
- Use `latest_groupA++` as the order source.
- If a true latest-data golden2 candidate is required, create a new non-frozen candidate name and regenerate its signal/panels instead of modifying `golden2_0830`.
