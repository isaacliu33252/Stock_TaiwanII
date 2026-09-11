# GroupA+ Frozen Release: golden2_0830

Date: 2026-08-30
Status: frozen release
Scope: GroupA+ latest strategy snapshot

## Release Name

The current latest GroupA+ strategy state has been copied and frozen as:

- `golden2_0830`

This release is fixed. Do not modify, overwrite, or reuse these filenames for future daily refreshes.

## Frozen Strategy State

- Strategy ID: `a2118_a2111_ncf_late_bull_deleverage`
- Strategy status: `active`
- Requested execution date: `2026-08-31`
- Actual data date: `2026-08-28`
- Base regime: `golden1`
- Execution regime: `golden1`
- Market state: `bull_trend` / `多頭趨勢`
- Risk level: `risk_on`
- Action: `hold_or_align_to_target`

Target weights from the frozen total-1m live signal:

| Asset | Weight |
| --- | ---: |
| `0050.TW` | `47.0000%` |
| `00631L.TW` | `10.0979%` |
| `00632R.TW` | `16.4782%` |
| `00679B.TWO` | `0.0000%` |
| cash | `26.4239%` |

## Frozen Files

Release manifest:

- `results/group_a_plus_release_golden2_0830.json`

Human-readable strategy snapshots:

- `releases/golden2_0830/group_a_plus_strategy_golden2_0830.json`
- `releases/golden2_0830/group_a_plus_live_signal_golden2_0830_20260831.json`

Group A combined signal snapshots:

- `results/golden2_0830/group_a_combined_live_golden2_0830.json`
- `results/golden2_0830/group_a_combined_live_golden2_0830.csv`
- `results/golden2_0830/group_a_combined_bundle_golden2_0830.json`
- `results/golden2_0830/signal_group_a_golden2_0830_20260831.json`
- `results/golden2_0830/signal_group_a_golden2_0830_20260831.csv`

GroupA+ live signal snapshot:

- `results/golden2_0830/group_a_plus_live_signal_v2_golden2_0830_20260831_total_1m.json`

Model and source payload snapshots:

- `models/portfolio/golden2_0830/last_ppo_group_a_100k_golden2_0830.zip`
- `results/golden2_0830/last_ppo_group_a_backtest_golden2_0830.json`

NCF snapshots:

- `results/golden2_0830/ncf_0050_golden2_0830.json`
- `results/golden2_0830/ncf_0050_panel_golden2_0830.csv`
- `results/golden2_0830/ncf_00631l_golden2_0830.json`
- `results/golden2_0830/ncf_00631l_panel_golden2_0830.csv`
- `results/golden2_0830/ncf_00632r_golden2_0830.json`
- `results/golden2_0830/ncf_00632r_panel_golden2_0830.csv`
- `results/golden2_0830/ncf_2330_golden2_0830.json`
- `results/golden2_0830/ncf_2330_panel_golden2_0830.csv`
- `results/golden2_0830/ncf_advisory_panel_golden2_0830.csv`
- `results/golden2_0830/ncf_panel_manifest_golden2_0830.json`

## Immutability Rule

- `golden2_0830` is a frozen snapshot.
- Daily `latest` pointers can continue updating independently.
- Future experiments, papers, backtests, and strategy changes must not alter these files.
- If a future strategy is promoted, create a new release name instead of editing `golden2_0830`.

## Notes

- `golden1_0531` was not modified.
- The frozen signal uses the latest available market data at creation time: `2026-08-28`.
- The `00632R.TW` allocation in this snapshot is the PVA hedge leg, not a directional long-alpha signal.
