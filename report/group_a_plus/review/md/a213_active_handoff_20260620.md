# GroupA+ A21.3 Active Strategy Handoff

Date: 2026-06-20

Workspace: `C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main`

## Current State

Schema-v2 latest is active:

- strategy id: `a213_cash30_recovery_ramp`
- status: `active`
- manifest: `report/group_a_plus/latest/strategy.json`
- dispatcher: `group_a_plus.runners.latest`
- compatibility CLI: `group_a_plus_latest_runner.py`
- dedicated runner: `group_a_plus.runners.a213`
- decision record: `report/group_a_plus/decision/json/a213_promotion_candidate_20260620.json`

Active daily signal:

- module: `group_a_plus.operations.daily_signal`
- CLI: `group_a_plus_live_signal.py`
- pointer: `report/group_a_plus/latest/live_signal.json`
- stale data leaves theoretical targets visible but sets
  `execution_allowed=false`

Workbook execution planner:

- module: `group_a_plus.operations.execution_plan`
- CLI: `group_a_plus_execution_plan.py`
- pointer: `report/group_a_plus/latest/execution_plan.json`
- parses only `Group A++ / 即時庫存`
- does not call a broker API
- blocks automatic execution above 50% turnover

Legacy compatibility remains active:

- pointer: `report/group_a_plus/latest/switch_backtest.json`
- strategy: A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
- purpose: existing price-only, two-regime consumers
- do not overwrite or remove until downstream migration is complete

## A21.3 Rules

A20.7 entry and formal exit rules are unchanged:

- MA window: 75
- entry MA gap: -1.75%
- entry drawdown: -11%
- required total risk score: 6
- minimum hold: 5 trading days
- formal exit MA gap: +2%
- exit momentum: five-day return above zero
- exit total risk score: at most 6
- feature warmup: 180 calendar days

Three execution regimes:

| Regime | 0050 | 00631L | 00632R | 00679B | Cash |
| --- | ---: | ---: | ---: | ---: | ---: |
| `golden1` | 60% | 20% | 0% | 0% | 20% |
| `group_a_plus_defensive` | 60% | 10% | 0% | 0% | 30% |
| `group_a_plus_recovery` | 69.6210% | 10.3373% | 0% | 0.0484% | 19.9933% |

Recovery ramp:

- only while A20.7 remains defensive
- trigger when `ma_gap >= 0` and five-day momentum is positive
- one shot per defensive episode
- target is the original A20.7 defensive weights
- return to Golden1 still requires the unchanged A20.7 formal exit

Historical recovery dates:

- 2020-05-11
- 2025-05-14

## Execution Method

Backtests use:

- ETF total return from local `(close + dividend) / previous close`
- commission: 0.1425% on buys and sells
- slippage: 0.05% on buys and sells
- non-bond ETF sell tax: 0.1%
- 00679B bond ETF sell tax: 0% during the tested exemption period
- all costs deducted from portfolio value at each rebalance

These metrics are not directly comparable with old price-only A20.7 outputs.
Always use the matched A21 baseline in the defensive-basket reports.

## Promotion Evidence

Matched A21 baseline comparison:

| Window | Final delta | Sharpe delta | MDD delta | Core stress | Latency matrix |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020-2024 train | +9876 | +0.010 | 0.00pp | 4/4 | 16/16 |
| 2025-2026 validation | +7420 | +0.070 | +2.17pp | 4/4 | 16/16 |
| 2020-2026 long | +41817 | +0.020 | 0.00pp | 4/4 | 16/16 |

Latency tests independently vary entry and exit delay from zero through three
trading days. All 16 combinations improve final value and Sharpe while meeting
or improving MDD in all three windows after adding the recovery ramp.

## Latest Metrics

Window: 2025-01-02 through 2026-06-18

| Metric | Value |
| --- | ---: |
| Initial value | 1000000.00 |
| Final value | 2376415.33 |
| Sharpe | 2.449427 |
| Sortino | 2.619495 |
| Maximum drawdown | -22.8423% |
| Transaction cost | 2469.61 |
| Rebalances | 4 |

As of 2026-06-18:

- base regime: `golden1`
- execution regime: `golden1`
- MA75 gap: +20.55%
- five-day momentum: +7.46%
- total risk score: 2

## Core Commands

Resolve the active manifest:

```bash
python3 -m group_a_plus.governance.latest \
  --output results/group_a_plus_latest_strategy_resolved.json
```

Run the active latest strategy:

```bash
python3 -m group_a_plus.runners.latest \
  --start 2025-01-02 --end 2026-06-18 \
  --output results/group_a_plus_runner_latest.json \
  --frame-output results/group_a_plus_runner_latest_frame.csv
```

Run A21.3 directly:

```bash
python3 -m group_a_plus.runners.a213 \
  --start 2025-01-02 --end 2026-06-18 \
  --output results/group_a_plus_runner_a213.json \
  --frame-output results/group_a_plus_runner_a213_frame.csv
```

Generate the guarded daily target:

```bash
python3 -m group_a_plus.operations.daily_signal \
  --as-of 2026-06-20 --portfolio-value 1000000 \
  --output results/group_a_plus_live_signal_v2.json \
  --latest-pointer report/group_a_plus/latest/live_signal.json
```

Generate a holdings-aware execution plan:

```bash
python3 -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260619.xlsx \
  --as-of 2026-06-20 --cash-balance 0 \
  --output results/group_a_plus_execution_plan_v2.json \
  --latest-pointer report/group_a_plus/latest/execution_plan.json
```

Reproduce matched research evidence:

```bash
python3 backtest_group_a_plus_defensive_basket.py \
  --start 2020-01-02 --end 2024-12-31 \
  --recovery-ramp \
  --output-prefix results/group_a_plus_defensive_basket_recovery_train

python3 backtest_group_a_plus_defensive_basket.py \
  --start 2025-01-02 --end 2026-06-18 \
  --latency-basket cash30 --recovery-ramp \
  --output-prefix results/group_a_plus_defensive_basket_recovery_recent
```

## Important Files

Runtime:

- `report/group_a_plus/latest/strategy.json`
- `group_a_plus/governance/latest.py`
- `group_a_plus/runners/latest.py`
- `group_a_plus/runners/a213.py`
- `group_a_plus_latest_runner.py`
- `group_a_plus_a213_runner.py`
- `group_a_plus/operations/daily_signal.py`
- `group_a_plus_live_signal.py`
- `report/group_a_plus/latest/live_signal.json`
- `group_a_plus/operations/execution_plan.py`
- `group_a_plus_execution_plan.py`
- `report/group_a_plus/latest/execution_plan.json`

Research and governance:

- `backtest_group_a_plus_defensive_basket.py`
- `group_a_plus/governance/catalog.py`
- `test_group_a_plus_defensive_basket.py`
- `test_group_a_plus_latest_strategy.py`
- `report/group_a_plus/decision/json/a213_promotion_candidate_20260620.json`

Evidence:

- `results/group_a_plus_defensive_basket_recovery_train_20260620.json`
- `results/group_a_plus_defensive_basket_recovery_recent_20260620.json`
- `results/group_a_plus_defensive_basket_recovery_long_20260620.json`
- `results/group_a_plus_runner_a213_recent_20260620.json`
- `results/group_a_plus_runner_a213_long_20260620.json`
- `results/group_a_plus_runner_latest_a213_20260620.json`
- `results/group_a_plus_runner_catalog_latest_v2_20260620.json`

## Data Corrections Already Applied

- daily feature forward-fill is limited to five trading days
- TDCC forward-fill is limited to ten trading days
- TDCC changes across observation gaps over 21 calendar days are reset to zero
- all strategy features/state are calculated before trimming the evaluation
  window
- recent and long warmup runs have exact overlapping feature/regime values

## Verification

Final verification on 2026-06-20:

- 25 related unit tests passed
- latest manifest resolver passed
- latest dispatcher smoke test passed
- latest runner and dedicated A21.3 runner metrics match exactly
- schema-v2 catalog contains 15 runners/operations
- legacy A20.7 pointer remains unchanged
- edited files contain no trailing whitespace

Daily operation verification:

- 2026-06-20 signal is executable with one business stale day
- all 12 strategy-specific sources pass freshness checks
- a 2026-06-30 stale-data negative test correctly blocks execution

Current workbook plan verification:

- Group B holdings are excluded
- estimated execution cost is TWD 859.98
- estimated post-trade cash is TWD 80875.11
- turnover is 109.43%, above the 50% automatic limit
- status is `manual_review_required`; no orders were sent

## Remaining Work

1. Migrate every external consumer from `latest/switch_backtest.json` to
   `latest/strategy.json`.
2. Add broker-specific commission discounts if actual account rates are known.
3. Recheck the bond ETF tax assumption after 2026-12-31.
4. Refresh OHLCV, dividends, institutional, derivative, and TDCC data before
   every live run.
5. Do not tune A21.3 thresholds using the existing 2025-2026 validation window.
6. Require a new independent period before changing cash30 or the recovery
   trigger.
