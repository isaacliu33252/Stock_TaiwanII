# GroupA+ 2026-07-20 Manual Holdings Execution Plan Record

Date generated: `2026-07-19`

## Purpose

After the 2026-07-20 estimate data refresh, the live signal improved from
`block` to `warn`:

- `execution_allowed`: `true`
- `source_freshness`: `ok`
- remaining warning: 2026-07-20 is a future trading date estimate while the
  latest formal market data is 2026-07-17.

The old `report/group_a_plus/latest/execution_plan.json` was still based on an
older requested date / workbook snapshot. A manual holdings scenario was
therefore generated without overwriting the latest execution-plan pointer.

## Inputs

Manual holdings file:

- `config/group_a_plus_holdings_20260720_manual.json`

Assumptions:

- `0050.TW`: `2794` shares, from user-provided current holding.
- `00631L.TW`: `500` shares, from user-provided current holding.
- `00632R.TW`: `0` shares.
- `00679B.TWO`: `3000` shares, estimated from
  `isaac_tra_20260718.xlsx` transaction history.
- cash balance: `0`.

Generated output:

- `results/group_a_plus_execution_plan_v2_20260720_manual_holdings.json`
- `results/group_a_plus_daily_status_20260720_manual_holdings.json`
- `results/group_a_plus_daily_status_20260720_manual_holdings.md`
- `results/group_a_plus_manual_holdings_execution_sensitivity_20260720.json`
- `results/group_a_plus_manual_holdings_execution_sensitivity_20260720.csv`

Command:

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --as-of 2026-07-20 \
  --holdings-json config/group_a_plus_holdings_20260720_manual.json \
  --cash-balance 0 \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260720.json \
  --output results/group_a_plus_execution_plan_v2_20260720_manual_holdings.json \
  --latest-pointer /tmp/group_a_plus_execution_plan_v2_20260720_manual_holdings_latest_pointer.json
```

## Result

Current holdings:

- `0050.TW`: `2794`
- `00631L.TW`: `500`
- `00632R.TW`: `0`
- `00679B.TWO`: `3000`

Theoretical target shares:

- `0050.TW`: `1880`
- `00631L.TW`: `2336`
- `00632R.TW`: `0`
- `00679B.TWO`: `0`

Staged target before guards:

- `0050.TW`: `1880`
- `00631L.TW`: `1234`
- `00632R.TW`: `0`
- `00679B.TWO`: `0`

Final guarded target shares:

- `0050.TW`: `1880`
- `00631L.TW`: `500`
- `00632R.TW`: `0`
- `00679B.TWO`: `0`

Guard result:

- `volatility_gate_no_00631l_add`: blocked.
- `compounding_regime_no_00631l_add`: blocked.
- blocked `00631L` add: `734` shares, about `23612.78`.

Trades in this manual scenario:

- sell `0050.TW`: `914` shares.
- sell `00679B.TWO`: `3000` shares.
- no `00631L` add.
- no `00632R` open.

Manual daily-status check:

- overall: `warn`;
- `execution_allowed`: `ok`;
- `source_freshness`: `ok`;
- `execution_plan_pre_trade_guard`: `ok`;
- remaining warning: `2026-07-20` is still an estimate using latest formal data
  through `2026-07-17`.

## Sensitivity Improvement

Because actual cash and final `00679B.TWO` shares are not yet confirmed, a
manual-holdings sensitivity grid was added:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_manual_holdings_execution_sensitivity.py \
  --cash-balances 0,100000,300000 \
  --00679b-shares 0,3000,5000 \
  --as-of 2026-07-20 \
  --output results/group_a_plus_manual_holdings_execution_sensitivity_20260720.json \
  --csv-output results/group_a_plus_manual_holdings_execution_sensitivity_20260720.csv
```

Grid result:

- scenario count: `9`;
- all scenarios block `00631L` add: `true`;
- any scenario opens `00632R`: `false`;
- all scenarios keep final `00631L.TW` at `500` shares;
- all scenarios keep final `00632R.TW` at `0` shares.

Key sensitivity:

- cash `0`, `00679B.TWO` `3000`: sell `0050.TW` `914`, sell `00679B.TWO`
  `3000`, keep `00631L.TW` `500`.
- cash `100000`, `00679B.TWO` `3000`: sell `0050.TW` `414`, sell
  `00679B.TWO` `3000`, keep `00631L.TW` `500`.
- cash `300000`, `00679B.TWO` `3000`: sell `0050.TW` `0`, sell
  `00679B.TWO` `3000`, keep `00631L.TW` `500`.

## Decision

This scenario confirms the existing defensive stance:

- keep `00631L` at `500` shares under the current guards;
- do not open `00632R`;
- improve the decision process by using the sensitivity grid before promoting
  any manual holdings plan to the formal execution plan;
- do not use the stale `execution_plan.json` as the active 2026-07-20 plan;
- do not overwrite the latest execution-plan pointer until actual cash and
  final current holdings are confirmed.
- the manual daily-status files are retained as a scenario check only; the
  formal latest daily-status pointer was restored to the standard
  `results/group_a_plus_daily_status_20260720.*` output.
