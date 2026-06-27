# Group A TDCC Improvement Branch

Date: 2026-06-01
Status: Shadow candidate

## Strategy

`Golden1_0531_tdcc_v1` keeps the production `Golden1_0531` PPO, sentiment, PVA,
and local-regime logic unchanged. It adds a TDCC leverage-ETF crowding overlay
after the base signal is generated.

The overlay reads weekly TDCC distribution data for `0050`, `00631L`, and
`00632R`. It uses the `00631L` minority-holder percentage and holder-count
changes over eight observations:

- `normal`: keep the base allocation.
- `caution`: cap `00631L` at `10%`.
- `risk_off`: cap `00631L` at `0%`.

Released leverage budget remains as cash. The candidate does not overwrite the
stable `Golden1_0531` outputs.

## Run

```bash
python3 run_group_a_tdcc_improved_signal.py \
  --xlsx Group_A_history.xlsx \
  --override-holdings-json '{"0050":172,"00631L":0,"00632R":0}' \
  --as-of-date 2026-06-02 \
  --download-end 2026-06-01
```

Stable candidate outputs:

- `results/group_a_tdcc_improved_live_latest.json`
- `results/group_a_tdcc_improved_live_latest.csv`
- `results/group_a_tdcc_improved_bundle_latest.json`

## Promotion Rule

Keep this branch shadow-only until it has been backtested with historical TDCC
availability lags, turnover, fees, drawdown, and missed-upside comparisons.
