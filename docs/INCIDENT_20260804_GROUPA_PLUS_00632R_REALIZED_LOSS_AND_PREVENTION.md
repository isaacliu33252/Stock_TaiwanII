# INCIDENT - 2026-08-04 GroupA+ 00632R Realized Loss

Date recorded: 2026-08-14  
Scope: GroupA+ 8/4 issue loss attribution and prevention record  
User-confirmed realized loss: `00632R` sell loss `-7,250 TWD`  

## Status

This is an incident / prevention record. It does not change live strategy,
target weights, execution plans, or orders.

- `golden1_0531`: unchanged
- GroupA+ latest strategy: unchanged
- A21.18/a2118 decision rule: unchanged
- live signal: unchanged
- execution plan: unchanged
- orders: unchanged

## Confirmed Loss

The user confirmed that selling `00632R` caused a realized loss:

```text
00632R realized sell loss = -7,250 TWD
```

This value is treated as user-confirmed realized P&L. The local market-data
calculation cannot reconstruct exact realized P&L without the broker cost
basis, lot-level buy date, sell date, sell price, fees, and tax, so the broker
/ user-confirmed value is authoritative for this incident record.

## Prior Calculation Gap

The first local attribution only calculated mark-to-market P&L for the current
holdings from 2026-08-04 close to 2026-08-13 close:

| Asset | Current shares used | 2026-08-04 close | 2026-08-13 close | P&L |
|---|---:|---:|---:|---:|
| `0050.TW` | 3994 | 100.65 | 106.70 | +24,163.68 |
| `00631L.TW` | 0 | 32.15 | 36.29 | 0.00 |
| `00632R.TW` | 0 | 10.63 | 9.95 | 0.00 |
| `00679B.TWO` | 100 | 26.45 | 26.35 | -10.00 |

Current-holdings mark-to-market total:

```text
+24,153.68 TWD
```

That calculation missed realized P&L from closed trades. Because `00632R` had
already been sold, it was no longer visible in current holdings and therefore
did not appear in the mark-to-market table.

Corrected accounting:

```text
Current-holdings mark-to-market P&L, 2026-08-04 to 2026-08-13: +24,153.68
User-confirmed 00632R realized sell loss:                         -7,250.00
---------------------------------------------------------------------------
Net after including confirmed realized loss:                       +16,903.68
```

Issue-specific damage should include at least:

```text
00632R realized sell loss: -7,250 TWD
```

If opportunity cost is included, one additional item was identified:

```text
Missed 00631L 800-share upside, 2026-08-04 to 2026-08-13:
800 * (36.29 - 32.15) = +3,312 TWD opportunity cost
```

Issue-impact estimate including realized loss and this opportunity cost:

```text
-7,250 - 3,312 = -10,562 TWD
```

## 8/4 Context From Local Artifacts

Relevant local holdings artifact:

- `results/group_a_plus_holdings_from_taiwan_stock_20260804.json`

It records 2026-08-04 workbook holdings:

```json
{
  "0050.TW": 3834,
  "00631L.TW": 800,
  "00632R.TW": 0,
  "00679B.TWO": 3000
}
```

Relevant 2026-08-04 / 2026-08-05 execution artifact:

- `results/group_a_plus_execution_plan_20260805_latest_strategy_after_refresh_from_taiwan_stock_20260804.json`

Important fields:

- `requested_as_of_date`: `2026-08-05`
- `actual_data_date`: `2026-08-04`
- holdings source: `results/group_a_plus_holdings_from_taiwan_stock_20260804.json`
- `execution_regime`: `golden1`
- target weights:
  - `0050.TW`: `0.30`
  - `00631L.TW`: `0.00`
  - `00632R.TW`: `0.2707873391613097`
  - `00679B.TWO`: `0.00`
  - cash: `0.42921266083869036`
- staged target shares:
  - `0050.TW`: `2980`
  - `00631L.TW`: `0`
  - `00632R.TW`: `10189`
  - `00679B.TWO`: `0`

This confirms that the local GroupA+ target around the 8/4 issue included
`00632R` exposure. The later realized sale loss in `00632R` is therefore
recorded as part of this incident's execution/decision impact.

## Prevention Rules

These rules should be followed before any future GroupA+ action involving
`00632R` or another inverse / hedge ETF.

1. Never assess issue impact from current holdings alone.

   Required P&L fields:

   - current open-position mark-to-market P&L;
   - closed-trade realized P&L;
   - opportunity cost versus the intended benchmark;
   - fees, tax, slippage if available.

2. Any `00632R` trade requires explicit realized-P&L / cost-basis review.

   Before selling or buying `00632R`, check:

   - current shares;
   - average cost or lot-level cost basis;
   - intended sell/buy price;
   - estimated realized P&L;
   - reason for holding inverse exposure;
   - reason for exit;
   - whether the signal is from production latest or a scratch/preview run.

3. Do not act on stale or preview artifacts.

   A candidate plan is not executable if any of these are true:

   - `planning_status = manual_review_required`;
   - `manual_confirmation_required = true`;
   - workbook source is not the current user-confirmed workbook;
   - `actual_data_date` does not match expected latest market data;
   - holdings were parsed from the wrong workbook;
   - holdings came from nested JSON that can be misread as all zero;
   - artifact is in `scratch_predict_*` unless explicitly confirmed for
     manual use.

4. Treat inverse ETF exposure as a separate risk class.

   `00632R` is not equivalent to cash or a generic hedge. It can lose money
   quickly in rebounds. Any target that opens, increases, or closes `00632R`
   must have a separate hedge-exposure rationale.

5. If the system recommends both deleting leverage and adding inverse exposure,
   require a manual contradiction check.

   The review must answer:

   - is this a true risk-off hedge, or a stale signal artifact?
   - is the market already rebounding?
   - does current `00631L`/`00632R` exposure reflect the latest holdings?
   - would doing nothing be safer than forced churn?

6. Future loss attribution must include user-confirmed realized trades.

   If the broker statement says a closed trade lost money, that number must be
   included even when the symbol no longer appears in current holdings.

## Non-Recurrence Checklist

Before giving a future GroupA+ execution recommendation:

- read latest execution plan and live signal;
- verify `requested_as_of_date` and `actual_data_date`;
- verify holdings source and parsed holdings;
- compare against broker/user-confirmed current holdings;
- identify any closed trades since the issue date;
- include realized P&L for closed trades;
- separately flag `00632R` / inverse ETF actions;
- explicitly state whether the plan is production, preview, scratch, or
  manual-review-only.

If any item is missing, the answer must say:

```text
realized P&L attribution incomplete; do not treat current-holdings-only P&L as total issue impact
```

## Current Final Attribution

As of this record:

```text
Confirmed realized issue loss:
00632R sell loss = -7,250 TWD

Current-holdings 2026-08-04 to 2026-08-13 mark-to-market:
+24,153.68 TWD

Optional opportunity cost:
missed 00631L 800-share upside = -3,312 TWD

Issue-specific realized + opportunity impact:
-10,562 TWD
```

This record should be referenced in future GroupA+ P&L attribution work around
the 2026-08-04 issue.

## 2026-08-15 Prevention Gate Implementation

Implemented a research-only `00632R` / inverse ETF manual-review gate before
any retraining-candidate shadow backtest or latest-strategy replacement work.
This preserves the agreed sequence:

```text
1. 00632R / inverse ETF prevention gate
2. retraining candidate shadow backtest
3. only then consider latest replacement or parameter tuning
```

Changed / added files:

- `group_a_plus/operations/execution_guard.py`
  - added `apply_inverse_etf_manual_review_gate`;
  - default ticker: `00632R.TW`;
  - blocks opening, increasing, reducing, or closing `00632R` from automatic
    execution;
  - requires artifact freshness, cost basis, realized P&L review, hedge
    rationale, and manual approval before any broker action;
  - does not mutate model target weights.
- `scripts/evaluate/build_group_a_plus_inverse_etf_manual_review_gate.py`
  - builds JSON / Markdown shadow reports from an execution plan;
  - writes latest report to
    `report/group_a_plus/latest/inverse_etf_manual_review_gate.json`;
  - writes Markdown report to
    `report/group_a_plus/latest/inverse_etf_manual_review_gate.md`;
  - writes dated history by default.
- `tests/test_inverse_etf_manual_review_gate.py`
  - unit coverage for opening, closing, and unchanged `00632R`.
- `tests/test_build_group_a_plus_inverse_etf_manual_review_gate.py`
  - report-builder coverage for blocked target changes and unchanged
    `00632R`.

Verification commands run:

```text
.venv/bin/python -m py_compile group_a_plus/operations/execution_guard.py scripts/evaluate/build_group_a_plus_inverse_etf_manual_review_gate.py
.venv/bin/python -m pytest tests/test_inverse_etf_manual_review_gate.py tests/test_build_group_a_plus_inverse_etf_manual_review_gate.py -q
```

Result:

```text
6 passed
```

Shadow report results:

- latest execution plan:
  - report:
    `report/group_a_plus/latest/inverse_etf_manual_review_gate.md`
  - current `00632R.TW`: `0`
  - target `00632R.TW`: `0`
  - gate status: `inactive`
  - report status: `blocked` only because the source execution plan itself is
    `manual_review_required` / `manual_confirmation_required`;
  - blocker is not caused by an inverse ETF target change.
- 2026-08-04 incident replay:
  - source plan:
    `results/group_a_plus_execution_plan_20260805_latest_strategy_after_refresh_from_taiwan_stock_20260804.json`
  - replay report:
    `report/group_a_plus/latest/inverse_etf_manual_review_gate_20260804_incident_replay.md`
  - current `00632R.TW`: `0`
  - target `00632R.TW`: `10189`
  - gate status: `blocked`
  - blocked reason:
    `inverse_etf_trade_requires_manual_review`
  - this confirms the 2026-08-04 style `00632R` action would now be stopped
    before automatic execution.

Important production note:

```text
This gate was created as a research-only / shadow safety artifact.
It has not been wired into live execution, has not changed golden1_0531,
has not changed latest strategy, has not changed live signal, has not changed
execution plan, and has not generated orders.
```

Next required step after this record:

```text
Run retraining-candidate shadow backtest under the new inverse ETF governance
constraint. Do not replace or tune latest until the shadow backtest result is
available and explicitly reviewed.
```
