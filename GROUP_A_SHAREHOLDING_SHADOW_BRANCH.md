# Group A Shareholding Shadow Branch

Date: 2026-06-01
Status: Research only

## Isolation

This branch is independent from the `Golden1_0531` production bundle.

- It does not call `run_group_a_combined_signal.py`.
- It does not overwrite `results/group_a_combined_live_latest.json` or its CSV.
- It emits advisory states only: `normal`, `caution`, `risk_off`, or `insufficient_data`.
- It never emits target shares and does not alter production orders.

## Inputs

The branch reads TDCC shareholding distribution rows from:

- `FinRL/data/stock_data.db`

The initial indicators are calculated for `0050`, `00631L`, and `00632R`:

- Minority holder percentage
- Major holder percentage
- Total holder count
- Changes over the configured weekly lookback window

To avoid same-day look-ahead, the default availability cutoff is one calendar day before the requested as-of date.

## Run

```bash
python3 run_group_a_shareholding_shadow.py --as-of-date 2026-06-01
```

Outputs:

- `results/group_a_shareholding_shadow_latest.json`
- `results/group_a_shareholding_shadow_history.jsonl`
- Timestamped JSON snapshots under `results/`

Thresholds and tracked tickers are isolated in:

- `group_a_shareholding_shadow_config.json`

## Improvement Loop

Keep the branch shadow-only while accumulating weekly records. Evaluate threshold changes against drawdown, turnover, and missed upside before creating a separately named candidate. Promotion into any future trading strategy requires an explicit review and must not modify `Golden1_0531` during its trial.
