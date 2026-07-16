# GroupA+ 2026-07-14 1M Execution Decision Record

Date: 2026-07-13
Requested as-of: 2026-07-14
Timezone: Asia/Taipei
Status: latest strategy confirmed; hard data blockers refreshed; execution plan ready

## Active Strategy

The latest strategy manifest used for this run is:

- manifest: `report/group_a_plus/latest/strategy.json`
- strategy id: `a2118_a2111_ncf_late_bull_deleverage`
- runner: `group_a_plus.runners.a2118`
- active status: `active`
- NCF 00631L panel: `results/ncf_00631l_panel_latest_20260707.csv`

Production runner parameters:

- `h20_max=0.33`
- `conf_min=0.55`
- `h5_reentry_min=0.55`
- `chip_data_fallback_max_stale_days=10`
- `risk_score_lookback_days=5`
- `momentum_fast_exit_min=0.10`
- `momentum_fast_exit_ma_gap_min=-0.08`
- `exclude_zero_volume_rows=true`

The live signal and execution plan generated in this session both report:

- `strategy_id=a2118_a2111_ncf_late_bull_deleverage`
- `execution_regime=golden1`
- `actual_data_date=2026-07-13`

## Data Refresh

Initial 2026-07-14 signal was blocked by stale hard sources:

- `margin_0050`
- `market_margin`
- `foreign_shareholding_0050`
- `short_balance_0050`

The stale sources were refreshed for `2026-07-10` through `2026-07-13`.

Refresh commands run:

```bash
python3 FinRL/data/stock_db.py --add-margin 0050.TW --start 2026-07-10 --end 2026-07-13
python3 FinRL/data/stock_db.py --add-market-margin --start 2026-07-10 --end 2026-07-13
python3 scripts/fetch/fetch_finmind_chip_data.py --datasets foreign_shareholding --tickers 0050.TW --start 2026-07-10 --end 2026-07-13
python3 scripts/fetch/fetch_finmind_chip_data.py --datasets short_sale_balances --tickers 0050.TW --start 2026-07-10 --end 2026-07-13
```

Post-refresh table max dates:

- `margin_0050`: `2026-07-13`
- `market_margin`: `2026-07-13`
- `foreign_shareholding_0050`: `2026-07-13`
- `short_balance_0050`: `2026-07-13`

Note: an attempted parallel refresh hit DuckDB write-lock contention for two tasks. Those two tasks were rerun sequentially and completed successfully. Future DB write refreshes should be sequenced unless the writer is known to use independent databases.

## Live Signal

Output:

- `results/group_a_plus_live_signal_v2_20260714_1m_after_chip_refresh.json`
- latest pointer: `report/group_a_plus/latest/live_signal_20260714_1m_after_chip_refresh.json`

Command:

```bash
python3 -m group_a_plus.operations.daily_signal --as-of 2026-07-14 --portfolio-value 1000000 --output results/group_a_plus_live_signal_v2_20260714_1m_after_chip_refresh.json --latest-pointer report/group_a_plus/latest/live_signal_20260714_1m_after_chip_refresh.json
```

Signal status:

- `execution_allowed=true`
- hard `execution_guard_reasons=[]`
- `business_stale_days=1`
- `calendar_stale_days=1`

Target weights:

- `0050.TW`: `57.3738647879%`
- `00631L.TW`: `12.6261352121%`
- `00632R.TW`: `0%`
- `00679B.TWO`: `0%`
- cash: `30%`

Reference target shares before execution controls:

- `0050.TW`: `5412`
- `00631L.TW`: `3425`
- `00632R.TW`: `0`
- `00679B.TWO`: `0`

Latest prices used:

- `0050.TW`: `106.0`
- `00631L.TW`: `36.86000061035156`
- `00632R.TW`: `10.229999542236328`
- `00679B.TWO`: `26.760000228881836`

Soft warnings remain:

- `securities_lending_0050` stale or missing
- NCF live overlay skipped because latest NCF dates were `2026-07-10` while actual data date was `2026-07-13`

These are warnings, not hard blockers in the current policy.

## Alerts And Guards

Signal alerts include:

- `total_risk_score`
- `volatility_gate_high_vol`
- `signal_wide_divergence`
- `ncf_panel_stale`
- `factor_lens_stale`

The active execution-affecting guard is:

- `volatility_gate_high_vol`
- policy: `advisory_no_auto_weight_change`
- action: block new `00631L.TW` exposure
- `allow_00631l_add=false`
- volatility gate: `high_vol_defensive`
- reference 00631L scale: `0.5`

A21.18 extreme risk warning status:

- `a2118_extreme_risk_no_new_adds`: inactive
- no 0050 add block from the new warning-only overlay

Interpretation:

- The MPC/extreme-warning work did not force any trade change for 2026-07-14.
- The reason 00631L remains at zero in the execution plan is the legacy volatility pre-trade guard.

## Execution Plan

Output:

- `results/group_a_plus_execution_plan_v2_20260714_1m_after_chip_refresh.json`
- latest pointer: `report/group_a_plus/latest/execution_plan_20260714_1m_after_chip_refresh.json`

Command:

```bash
python3 -m group_a_plus.operations.execution_plan --as-of 2026-07-14 --cash-balance 598828 --output results/group_a_plus_execution_plan_v2_20260714_1m_after_chip_refresh.json --latest-pointer report/group_a_plus/latest/execution_plan_20260714_1m_after_chip_refresh.json
```

Workbook used:

- `taiwan_stock_20260619.xlsx`

Workbook holdings parsed:

- `0050.TW`: `1342`
- `00631L.TW`: `0`
- `00632R.TW`: `0`
- `00679B.TWO`: `5000`
- `00751B.TWO`: `4000`

Cash input:

- `598828`

This cash was chosen to make the workbook portfolio approximately 1M total assets:

- holdings market value: `401172.0038909912`
- current total assets: `1000000.0038909912`

Plan status:

- `planning_status=ready`
- `execution_allowed=true`
- execution guard reasons: `[]`

Final target shares after execution controls, buy staging, and guards:

- `0050.TW`: `2970`
- `00631L.TW`: `0`
- `00632R.TW`: `0`
- `00679B.TWO`: `0`
- `00751B.TWO`: `0`

Trades:

- sell `00679B.TWO`: `5000 -> 0`, notional `133800.0011`, estimated cost `257.5650`
- sell `00751B.TWO`: `4000 -> 0`, notional `125120.0027`, estimated cost `240.8560`
- buy `0050.TW`: `1342 -> 2970`, delta `+1628`, notional `172568.0`, estimated cost `332.1934`

Execution summary:

- buy notional: `172568.0`
- sell notional: `258920.0039`
- transaction cost estimate: `830.6144`
- turnover notional: `431488.0039`
- turnover ratio: `43.1488%`
- max automatic turnover ratio: `50%`
- estimated cash after execution: `684349.3895`

## User-Stated Holding Scenario

The user also stated a different current holding scenario:

- `0050.TW=2474`
- `00631L.TW=0`
- total assets: `1,000,000`

This differs from the workbook holdings. A what-if calculation was run using the same 2026-07-14 live signal and guards.

What-if result:

- theoretical target: `0050=5412`, `00631L=3425`
- buy staging would first stage `0050` to `3649`
- volatility guard blocks staged `00631L` buy and keeps `00631L=0`

What-if executable trade:

- buy `0050.TW`: `2474 -> 3649`
- delta: `+1175`
- notional: `124550`
- estimated cost: `239.76`

This scenario is not written as the official execution plan because the workbook currently stores `0050=1342`, not `2474`. To make the official plan match the user-stated holding scenario, the workbook or an alternate holdings input path must be updated first.

## MPC / Integrated Multi-Period Research Result

The user's proposed finite-path MPC idea was tested as research-only.

Main findings:

- Direct automatic trimming of `00631L` did not survive transaction costs and rebound risk.
- Full path-value and oracle variants showed that selling 00631L can improve some risk metrics but generally loses terminal value or overtrades.
- The most robust production-safe interpretation is warning-only: pause new risk adds during extreme A21.18 warning conditions; do not auto-sell.

Implemented components:

- `scripts/evaluate/evaluate_a2118_mpc_path_shadow.py`
- `scripts/evaluate/evaluate_a2118_warning_cashflow_guard.py`
- `group_a_plus/operations/daily_signal.py` emits `a2118_extreme_risk_warning`
- `group_a_plus/operations/execution_guard.py` includes `apply_risk_add_pre_trade_guard`
- `group_a_plus/operations/execution_plan.py` applies the new risk-add guard after the volatility guard

Key research reports:

- `results/a2118_mpc_path_shadow_warning_only_cashbuffer_h22_m85_20260713.json`
- `results/a2118_warning_cashflow_guard_daily_5000_20260713.json`
- `report/group_a_plus/review/md/a2118_extreme_risk_warning_handoff_20260713.md`

Warning-only validation:

- shadow warning-only report: 7/7 triple-pass windows
- active 2025-2026 warning days: 9
- 1-day hedge-help rate: 77.8%
- 5-day hedge-help rate: 66.7%
- 20-day hedge-help rate: 88.9%
- mean 20-day `00631L - 0050`: `-2.58%`

Cashflow guard backtest:

- monthly 10k contribution: no effect because contribution dates did not overlap warning days
- weekly contribution: small negative
- daily contribution: small positive, but economically tiny
- daily 5000 contribution, active 2025-2026: final value delta about `+589`, Sharpe delta about `+0.0008`

Conclusion:

- Keep the MPC-derived rule as a pre-trade risk-control warning only.
- Do not promote it into automatic sell/rebalance logic.
- For 2026-07-14, it is inactive; the active 00631L blocker is still the volatility gate.

## Verification

Tests and checks run during this session:

```bash
pytest -q tests/test_evaluate_a2118_warning_cashflow_guard.py tests/test_group_a_plus_execution_guard.py tests/test_group_a_plus_execution_plan_v2.py
```

Result:

- `19 passed`

```bash
pytest -q tests/test_group_a_plus_daily_signal_v2.py tests/test_evaluate_a2118_mpc_path_shadow.py
```

Result:

- `60 passed`

Additional compile check:

```bash
python3 -m py_compile scripts/evaluate/evaluate_a2118_warning_cashflow_guard.py
```

Result:

- passed

## Operational Decision

For 2026-07-14 using the workbook holdings and 1M total asset assumption:

- execution plan is ready
- do not buy `00631L.TW`
- sell `00679B.TWO`
- sell `00751B.TWO`
- buy staged `0050.TW`

For the user's stated `0050=2474` scenario:

- do not buy `00631L.TW`
- buy `0050.TW +1175`
- update the official holdings source before treating this as the canonical execution plan

