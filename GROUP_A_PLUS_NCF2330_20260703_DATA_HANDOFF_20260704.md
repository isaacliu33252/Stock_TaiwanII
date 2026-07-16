# GroupA+ ncf_2330 / 2026-07-03 Data Refresh Handoff

Date: 2026-07-04  
Workspace: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`

## Summary

This handoff records the work completed around adding `ncf_2330` as a TSMC/0050 reference signal and downloading 2026-07-03 data.

Main conclusion:

- `ncf_2330` is now integrated as a diagnostic/advisory input for live daily signal and signal alignment.
- It is not an automatic 00631L trading rule.
- Backtest/sweep did not support using `ncf_2330` to automatically trim 00631L.
- Core strategy data for 2026-07-03 has been downloaded into DuckDB.
- `external_market_ohlcv` for `2330.TW` via yfinance still only covers 2026-07-02.

## Code Changes

### `group_a_plus/operations/daily_signal.py`

Added:

- `TSMC_NCF_TAG = "2330"`
- `TSMC_0050_WEIGHT_ASSUMPTION = 0.55`
- `_latest_ncf_path()` now also finds `ncf_{tag}_improved_*.json`.
- `_tsmc_0050_health_snapshot()`
  - Loads 0050/00631L OHLCV from `ohlcv`.
  - Loads 2330 from `external_market_ohlcv`.
  - Computes 1d/5d/10d/20d returns for:
    - `2330.TW`
    - `0050.TW`
    - `00631L.TW`
    - `0050_ex_tsmc_proxy`
  - Classifies state:
    - `healthy_leadership`
    - `tsmc_led_narrow`
    - `tsmc_weak_confirmed`
    - `mixed`
    - `stale`
- `_tsmc_0050_reference_guidance()`
  - Converts health state into stable advisory fields:
    - `reference_action`
    - `reference_action_zh`
    - `trade_policy`
    - `manual_review_required`
    - `allow_00631l_add`
- `ncf_live_overlay["ncf_2330"]`
- `ncf_live_overlay["tsmc_0050_health"]`
- advisory alerts:
  - `tsmc_led_narrow_reference`
  - `tsmc_weak_manual_review`

Important behavior:

- No automatic target-weight change is applied from `ncf_2330`.
- `_apply_tsmc_weakness_trim()` exists for research/testing, but is not called in `build_daily_signal()`.

### `group_a_plus/integrations/signal_alignment.py`

Added source:

- `ncf_2330_tsmc`

Behavior:

- `healthy_leadership` -> bullish, strength 0.45
- `tsmc_led_narrow` -> neutral, strength 0.25
- `tsmc_weak_confirmed` -> bearish, strength 0.55
- missing/unavailable -> unavailable

### Tests

Updated:

- `tests/test_group_a_plus_daily_signal_v2.py`
- `tests/test_group_a_plus_signal_alignment.py`

Coverage added:

- `tsmc_led_narrow` does not trim 00631L.
- `tsmc_weak_confirmed` trim helper only trims when 00631L NCF also confirms weakness.
- `reference_guidance` emits `avoid_add_00631l` for narrow TSMC-led markets.
- advisory alerts are created without trade-weight changes.
- `ncf_2330_tsmc` participates in signal alignment.

Latest test command:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_daily_signal_v2.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_latest_strategy.py -q
```

Result:

```text
65 passed
```

## ncf_2330 Advisory Interpretation

Current recommended usage:

### `healthy_leadership`

Meaning:

- TSMC is up.
- 0050 is up.
- 00631L is up.
- 0050 ex-TSMC proxy is also positive.

Reference action:

- `allow_normal`
- 00631L follows the normal strategy.

### `tsmc_led_narrow`

Meaning:

- TSMC supports 0050.
- 0050 ex-TSMC proxy is weak or negative.

Reference action:

- `avoid_add_00631l`
- Do not add/追高 00631L just because 0050 headline price is strong.
- This is diagnostic only; target weights are not changed.

### `tsmc_weak_confirmed`

Meaning:

- TSMC model or price action is weak.

Reference action:

- `manual_review`
- Check:
  - 00631L current weight
  - `total_risk_score`
  - `signal_alignment`
  - 00631L NCF state

No automatic trim is applied.

## Live Signal Verification

Generated file:

- `results/group_a_plus_live_signal_v2_tsmc_reference_20260703.json`

Command:

```bash
.venv/bin/python -m group_a_plus.operations.daily_signal \
  --as-of 2026-07-03 \
  --portfolio-value 1000000 \
  --output results/group_a_plus_live_signal_v2_tsmc_reference_20260703.json \
  --latest-pointer /tmp/group_a_plus_live_signal_tsmc_reference_latest.json
```

Result as of actual data date 2026-07-02:

```text
tsmc_0050_health.state = tsmc_led_narrow
reference_action = avoid_add_00631l
reference_action_zh = 只有台積支撐 0050，00631L 不追高、不加碼
target_weights unchanged
tsmc_weakness_trim_applied = None
bearish_high_risk_trim_applied = None
```

Target weights from verification output:

```json
{
  "0050.TW": 0.6949319837027067,
  "00631L.TW": 0.10391752151883793,
  "00632R.TW": 0.0,
  "00679B.TWO": 0.0,
  "cash": 0.2011504947784553
}
```

## Backtest / Sweep

Research script added:

- `scripts/misc/a2118_ncf_2330_tsmc_overlay_sweep.py`

Output:

- `results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json`

Window:

- 2025-01-02 to 2026-07-02
- 361 rows

Sweep space:

- `tsmc_h20_max`: 0.45, 0.50, 0.55
- `tsmc_tail_min`: 0.45, 0.50, 0.55
- `l631_h20_max`: 0.40, 0.45, 0.50
- `l631_tail_min`: 0.50, 0.55, 0.60
- `trim_fraction`: 0.15, 0.25, 0.35, 0.50

Baseline latest a2118 metrics:

```text
final_value = 2,138,725.8858
total_return = 113.87%
annual_return = 66.29%
sharpe_ratio = 2.5258
sortino_ratio = 2.7804
max_drawdown = -13.82%
```

Production-like overlay:

```text
tsmc_h20_max = 0.50
tsmc_tail_min = 0.50
l631_h20_max = 0.45
l631_tail_min = 0.50
trim_fraction = 0.25
trigger_days = 20
final_value_delta = -65,578.42
sharpe_delta = +0.0111
max_drawdown_delta = 0.0
```

Best-by-final-value overlay:

```text
tsmc_h20_max = 0.45
tsmc_tail_min = 0.45
l631_h20_max = 0.45
l631_tail_min = 0.60
trim_fraction = 0.15
trigger_days = 23
final_value_delta = -52,509.96
sharpe_delta = +0.0351
max_drawdown_delta = 0.0
```

Full sweep summary:

```text
all_variants_count = 324
variants_with_final_value_improvement = 0
variants_with_mdd_improvement = 0
variants_with_sharpe_improvement = 321
```

Conclusion:

- Do not promote `ncf_2330` as an automatic 00631L trim rule.
- It lowers volatility slightly in many variants but reduces final value and does not improve MDD.
- Keep as advisory/diagnostic only.

## Latest Strategy Backtest

Command:

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-07-03 \
  --initial-value 1000000 \
  --output results/group_a_plus_runner_latest_20250102_20260703.json \
  --frame-output results/group_a_plus_runner_latest_20250102_20260703_frame.csv
```

Actual window:

```text
2025-01-02 to 2026-07-02
rows = 361
```

Metrics:

```text
strategy = a2118_a2111_ncf_late_bull_deleverage
status = active
today_regime = golden1
final_value = 2,138,725.8858
total_return = 113.87%
annual_return = 66.29%
volatility = 22.09%
sharpe_ratio = 2.5258
sortino_ratio = 2.7804
max_drawdown = -13.82%
worst_daily_return = -4.24%
worst_20d_return = -9.47%
rebalance_count = 6
transaction_cost = 5,264.95
late_bull_trigger_days = 1
total_hedge_days = 5
```

Live weights from runner:

```json
{
  "0050.TW": 0.6949319837027067,
  "00631L.TW": 0.10506801629729329,
  "00632R.TW": 0.0,
  "00679B.TWO": 0.0,
  "cash": 0.19999999999999996
}
```

## Latest vs golden1_0531

Generated:

- `results/group_a_plus_switch_policy_compare_golden1_20250102_20260703.json`
- `results/group_a_plus_latest_vs_golden1_0531_20250102_20260703.json`
- `results/group_a_plus_latest_vs_golden1_0531_20250102_20260703.csv`

Actual comparison window:

- 2025-01-02 to 2026-07-02

Comparison:

| Metric | Latest a2118 | golden1_0531_1m | Latest - golden |
|---|---:|---:|---:|
| Final value | 2,138,725.89 | 2,275,306.17 | -136,580.28 |
| Total return | 113.87% | 127.53% | -13.66pp |
| Annual return | 66.29% | 73.32% | -7.03pp |
| Volatility | 22.09% | 28.44% | -6.35pp |
| Sharpe | 2.5258 | 2.1673 | +0.3585 |
| Sortino | 2.7804 | 2.2518 | +0.5286 |
| MDD | -13.82% | -27.54% | +13.72pp |
| Worst daily | -4.24% | -9.68% | +5.44pp |
| Worst 20d | -9.47% | -21.14% | +11.67pp |

Conclusion:

- `golden1_0531_1m` has higher return.
- latest a2118 has materially better risk control and risk-adjusted metrics.

## 2026-07-03 Data Refresh

### Commands run

Group A:

```bash
.venv/bin/python refresh_group_data.py \
  --group a \
  --target-date 2026-07-03 \
  --strict \
  --force \
  --summary-path results/refresh_group_a_20260703_summary.json
```

Group B:

```bash
.venv/bin/python refresh_group_data.py \
  --group b \
  --target-date 2026-07-03 \
  --strict \
  --force \
  --summary-path results/refresh_group_b_20260703_summary.json
```

FinMind core chip:

```bash
.venv/bin/python scripts/fetch/fetch_finmind_chip_data.py \
  --tickers 0050,00631L,00632R,00679B \
  --start 2026-07-03 \
  --end 2026-07-03 \
  --datasets institutional,margin,shareholding,foreign_shareholding,derivative_institutional,securities_lending,short_sale_balances,day_trading,dealer_futures,dealer_options
```

This failed at `shareholding` due FinMind account level restriction after successfully writing institutional and margin rows. Then ran without `shareholding`.

Follow-up successful single dataset command:

```bash
.venv/bin/python scripts/fetch/fetch_finmind_chip_data.py \
  --tickers 0050 \
  --option-ids TXO \
  --start 2026-07-03 \
  --end 2026-07-03 \
  --datasets dealer_options
```

Market margin:

```bash
python3 FinRL/data/stock_db.py \
  --add-market-margin \
  --start-date 2026-07-03 \
  --end-date 2026-07-03
```

TAIFEX futures:

```bash
python3 taifex_futures_data.py \
  --refresh-latest \
  --output results/taifex_futures_latest_20260703_refresh.json
```

TAIFEX options:

```bash
python3 taifex_options_data.py \
  --refresh-latest \
  --output results/taifex_options_latest_20260703_refresh.json
```

The options command first failed inside the sandbox with DNS error, then succeeded with approved network escalation.

External yfinance cache:

```bash
.venv/bin/python - <<'PY'
from ncf_external_cache import fetch_yf_close_cached
from backtest_group_a_plus_switch_policy import DB_PATH
for ticker in ['2330.TW','TSM','TWD=X','EWT','SOXX','QQQ']:
    s = fetch_yf_close_cached(
        ticker,
        '2026-06-25',
        '2026-07-04',
        DB_PATH,
        purpose='manual_refresh_20260703',
        allow_download=True,
    )
    print(ticker, len(s), None if s.empty else s.index.max().date())
PY
```

### Data status after refresh

Core OHLCV:

```text
0050.TW      max_dt = 2026-07-03
00631L.TW    max_dt = 2026-07-03
00632R.TW    max_dt = 2026-07-03
00679B.TWO   max_dt = 2026-07-03
```

Chip tables:

```text
institutional_data        max_dt = 2026-07-03, hits_0703 = 4
margin_data               max_dt = 2026-07-03, hits_0703 = 4
foreign_shareholding_data max_dt = 2026-07-03, hits_0703 = 4
short_sale_balance_data   max_dt = 2026-07-03, hits_0703 = 4
day_trading_data          max_dt = 2026-07-03, hits_0703 = 4
securities_lending_data   max_dt = 2026-07-03, hits_0703 = 3
```

Note:

- `00631L.TW` had no `securities_lending_data` row for 2026-07-03 from FinMind.

Market / derivatives:

```text
market_margin_data              max_dt = 2026-07-03, hits_0703 = 1
derivative_institutional_data   max_dt = 2026-07-03, hits_0703 = 9
dealer_futures_data             max_dt = 2026-07-03, hits_0703 = 96
dealer_options_data             max_dt = 2026-07-03, hits_0703 = 83
taifex_futures_daily            max_dt = 2026-07-03, hits_0703 = 17
taifex_futures_institutional    max_dt = 2026-07-03, hits_0703 = 3
taifex_options_daily            max_dt = 2026-07-03, hits_0703 = 6424
```

External market OHLCV:

```text
2330.TW max_dt = 2026-07-02
TSM     max_dt = 2026-07-02
EWT     max_dt = 2026-07-02
SOXX    max_dt = 2026-07-02
QQQ     max_dt = 2026-07-02
TWD=X   max_dt = 2026-06-30
```

This is source availability, not a local refresh miss. Re-fetching with yfinance still returned only those dates.

### Refresh output files

- `results/refresh_group_a_20260703_summary.json`
- `results/refresh_group_b_20260703_summary.json`
- `results/taifex_futures_latest_20260703_refresh.json`
- `results/taifex_options_latest_20260703_refresh.json`

## Known Issues / Caveats

1. `external_market_ohlcv` for `2330.TW` does not yet have 2026-07-03.
   - `ncf_2330` and `tsmc_0050_health` will still be effectively 2026-07-02 until the external cache provides 7/3.

2. FinMind `shareholding` failed:
   - Dataset: `TaiwanStockHoldingSharesPer`
   - Error: account level restriction.
   - Existing TDCC/shareholding freshness may remain stale unless another source/file is imported.

3. A combined FinMind command was interrupted after hanging at `dealer_options`.
   - It had already written several datasets.
   - `dealer_options` was subsequently fetched successfully as a single dataset.

4. `securities_lending_data` has 7/3 rows for 3 of 4 core tickers.
   - `00631L.TW` had no FinMind row for 2026-07-03.
   - The daily signal treats securities lending as a soft source.

## Suggested Next Steps

1. Re-run latest strategy after 7/3 data refresh:

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-07-03 \
  --initial-value 1000000 \
  --output results/group_a_plus_runner_latest_20250102_20260703_refreshed.json \
  --frame-output results/group_a_plus_runner_latest_20250102_20260703_refreshed_frame.csv
```

2. Re-run daily signal:

```bash
.venv/bin/python -m group_a_plus.operations.daily_signal \
  --as-of 2026-07-03 \
  --portfolio-value 1000000 \
  --output results/group_a_plus_live_signal_v2_20260703_refreshed.json \
  --latest-pointer /tmp/group_a_plus_live_signal_20260703_refreshed_latest.json
```

3. When yfinance provides `2330.TW` 2026-07-03, refresh external cache again and rerun `ncf_2330`.

4. Keep `ncf_2330` advisory-only unless a future longer-window sweep shows:
   - final value improvement, or
   - MDD improvement, with acceptable opportunity cost.

