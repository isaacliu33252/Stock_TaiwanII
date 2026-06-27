# Group A Handoff

Date: 2026-06-05
Status: Handoff / operational record

## 1. Current Production Strategy

Production Group A strategy remains:

- `Golden1_0531`

Production files:

- Release note: `GROUP_A_GOLDEN1_0531_RELEASE.md`
- Runner: `run_group_a_combined_signal.py`
- Model: `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip`
- Payload: `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- Latest signal bundle:
  - `results/group_a_combined_live_latest.json`
  - `results/group_a_combined_live_latest.csv`
  - `results/group_a_combined_bundle_latest.json`

No production replacement was made.

## 2. Data Refresh

Ran data refresh for target date `2026-06-04`:

```bash
python3 refresh_group_data.py --group both --target-date 2026-06-04 --summary-path results/data_refresh_both_20260604.json
```

Result:

- Group A caches updated through `2026-06-04`
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
- Group B caches updated through `2026-06-04`
  - `0056.TW`
  - `00646.TW`
  - `00679B.TWO`
  - `00713.TW`
  - `00751B.TWO`
  - `00878.TW`
- Market caches updated through `2026-06-04`
- DuckDB rows written and validated with `has_target_date: true`

Refresh summary:

- `results/data_refresh_both_20260604.json`

## 3. Workbook State

Workbook:

- `Group_A_history.xlsx`

Latest parsed actual row:

- `2026/6/4 實際`
- `0050 = 492`
- `00631L = 0`
- `00632R = 0`

Because `Group_A_history.xlsx` is an execution-history workbook, live signal generation still requires `--override-holdings-json`.

## 4. Golden1_0531 Signal For 2026-06-05

Command used for total Group A assets of `1,000,000`:

```bash
python3 run_group_a_combined_signal.py \
  --xlsx Group_A_history.xlsx \
  --override-holdings-json '{"0050":492,"00631L":0,"00632R":0}' \
  --as-of-date 2026-06-05 \
  --download-end 2026-06-04 \
  --extra-cash 947798.8007507324
```

Output:

- `results/signal_group_a_20260604_183007.json`
- `results/signal_group_a_20260604_183007.csv`

Signal:

- Status: `rebalance`
- Reason: `pva_overlay_j`
- Data date: `2026-06-04`
- Execution date: `2026-06-05`
- Target allocation:
  - `0050.TW = 58.0373%`
  - `00631L.TW = 11.9627%`
  - `00632R.TW = 0.0000%`
  - cash = `30.0000%`

Target shares for Group A assets of `1,000,000`:

| Ticker | Current | Target | Delta |
| --- | ---: | ---: | ---: |
| `0050.TW` | `492` | `5,470` | `+4,978` |
| `00631L.TW` | `0` | `3,123` | `+3,123` |
| `00632R.TW` | `0` | `0` | `0` |

## 5. 00679B Overlay Research

00679B is treated as an external stabilizer / portfolio overlay, not part of the current Golden1 production model.

Earlier shadow results:

- Idealized daily-rebalanced overlay:
  - `GROUP_A_00679B_OVERLAY_SHADOW_20260604.md`
  - `results/group_a_679b_overlay_shadow_20260604.json`
  - `results/group_a_679b_overlay_shadow_20260604.csv`
- Monthly/drift rebalance with fees:
  - `GROUP_A_00679B_REBALANCE_FEE_SHADOW_20260604.md`
  - `results/group_a_679b_overlay_rebalance_fee_20260604.json`
  - `results/group_a_679b_overlay_rebalance_fee_20260604.csv`

Main finding:

- `80% Group A / 20% 00679B` is the best initial shadow candidate.
- It lowers volatility and drawdown but reduces expected return.
- It should remain shadow until validated under live-style execution.

## 6. FinRL-Meta Import Review

Reviewed local repo:

- `C:\Users\isaac\Downloads\FinRL-Meta-master\FinRL-Meta-master`

Items selected for Group A shadow/reporting layer:

1. Continuous portfolio-weight overlay concept.
2. `last_action` / current-weight turnover control.
3. Transaction cost, sell tax, slippage, and batch execution reporting.
4. Turbulence/market stress concept reserved for later as a possible extra guard.

Not imported:

- FinRL-Meta Yahoo cleaner, because it is NYSE-calendar oriented.
- Full DataProcessor stack, because this project already has `refresh_group_data.py`, caches, and DuckDB.
- Alpaca/crypto/futures paths.
- Full FinRL-Meta agent wrapper.

## 7. New Shadow Tool

Added:

- `group_a_00679b_continuous_shadow.py`

Purpose:

- Read an existing Group A signal JSON.
- Add 00679B as a continuous overlay sleeve.
- Apply turnover control using current weights as `last_action`.
- Estimate:
  - commission
  - ETF sell tax
  - slippage
  - total execution cost
  - batch execution plan
- Export CSV, JSON, and Markdown.

This tool does not alter Golden1 production behavior.

Syntax check passed:

```bash
python3 -m py_compile group_a_00679b_continuous_shadow.py
```

## 8. 2026-06-05 Continuous Shadow Result

Scenario:

- Total assets: `1,250,000`
- Current 00679B: `10,000` shares
- Overlay target: `80% Group A / 20% 00679B`
- Source Group A signal:
  - `results/signal_group_a_20260604_184447.json`

Raw 80/20 output:

- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.csv`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.md`

Raw 80/20 recommendation:

| Ticker | Current | Target | Delta |
| --- | ---: | ---: | ---: |
| `0050.TW` | `492` | `5,470` | `+4,978` |
| `00631L.TW` | `0` | `3,123` | `+3,123` |
| `00632R.TW` | `0` | `0` | `0` |
| `00679B.TWO` | `10,000` | `9,437` | `-563` |

Turnover-controlled output:

- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.csv`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.md`

Turnover-controlled settings:

- `turnover_penalty = 0.25`
- `slippage_rate = 0.05%`
- batch count = `3` when trade notional is at least `100,000`

Turnover-controlled recommendation:

| Ticker | Current | Target | Delta | Trade notional | Batches |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0050.TW` | `492` | `4,225` | `+3,733` | `396,071` | `3` |
| `00631L.TW` | `0` | `2,342` | `+2,342` | `89,699` | `1` |
| `00632R.TW` | `0` | `0` | `0` | `0` | `1` |
| `00679B.TWO` | `10,000` | `9,578` | `-422` | `11,179` | `1` |

Cost estimate for turnover-controlled version:

- Buy notional: `485,770`
- Sell notional: `11,179`
- Commission: `708`
- ETF sell tax: `11`
- Slippage estimate: `248`
- Total execution cost: `968`
- Cash after cost: `457,340`

Integrated report:

- `GROUP_A_00679B_CONTINUOUS_SHADOW_20260605.md`

## 9. Practical Recommendation

For production:

- Keep `Golden1_0531` unchanged.
- Keep using `run_group_a_combined_signal.py` as the production signal path.

For shadow:

- Track `80% Group A / 20% 00679B`.
- Prefer the turnover-controlled recommendation for staged execution.
- Treat raw 80/20 as the long-run target reference.

For next development:

1. Add a persisted shadow history JSONL for `group_a_00679b_continuous_shadow.py`.
2. Add a replay/backtest mode for the continuous overlay tool.
3. Add a Taiwan-market turbulence/stress guard only after backtesting it against existing local regime/PVA gates.
4. Do not retrain Group A with 00679B until the overlay proves useful in shadow.
