# GroupA+ 2008 Stress / Parameter Tuning Handoff - 2026-07-03

## Executive Summary

This session checked whether the current GroupA+ stack should be changed after:

1. adding fine-grained market-state diagnostics,
2. backtesting the active A21.18 setup on 2025-01-02 to 2026-07-02,
3. sweeping A21.18 late-bull NCF trigger parameters,
4. running the TWII-derived 2008 proxy stress test,
5. sweeping 2008-specific GroupA+ overlay parameters.

Decision: keep the current active production parameters unchanged.

The 2008 proxy stress test supports the current latest production model plus GroupA+ overlay. A 2008-only micro-tuned overlay slightly improves the proxy result, but the gain is small and should remain a shadow candidate until it passes 2025-2026 and multi-window validation.

## Current Active Setup

Active strategy manifest:

- `report/group_a_plus/latest/strategy.json`
- active id: `a2118_a2111_ncf_late_bull_deleverage`
- runner: `group_a_plus.runners.a2118`
- active runner params:
  - `ncf_panel_631l_path = results/ncf_00631l_panel_latest_20260630.csv`
  - `h20_max = 0.33`
  - `conf_min = 0.55`
  - `h5_reentry_min = 0.55`

Do not change these active params yet.

## Code Changes Made

### 1. Fine-Grained Market State Diagnostics

Added:

- `group_a_plus/operations/market_state.py`
- `tests/test_group_a_plus_market_state.py`

Integrated into:

- `group_a_plus/operations/daily_signal.py`

Daily signal now includes:

- `market_state.state`
- `market_state.bucket`
- `market_state.label_zh`
- `market_state.allocation_bias`
- `market_state.risk_level`
- `market_state.inputs`
- `market_state.reason`

State split:

- `bull_acceleration`
- `bull_trend`
- `late_bull_overheat`
- `bull_pullback_shallow`
- `bull_pullback_deep`
- `recovery_early`
- `recovery_confirmed`
- `choppy_range_low_risk`
- `choppy_range_high_risk`
- `bear_breakdown`
- `crash_risk`

Important: this is reporting/diagnostic only. It does not change `execution_regime` or `target_weights`.

### 2. Data Freshness Improvement

Changed:

- `ncf_data_quality.py`
- `tests/test_ncf_data_quality.py`

NCF freshness now reports per-yfinance-ticker external market cache dates and lag days under:

- `source_details.external_market_ohlcv.ticker_dates`
- `source_details.external_market_ohlcv.ticker_lag_days_vs_reference`

Also filters external market freshness to `provider='yfinance'`.

### 3. 2008 Replay Compatibility Fixes

Changed:

- `evaluate_group_a_tdcc_overlay_variants.py`
- `compare_group_a_plus_2008_golden_latest.py`
- `scripts/sweep/sweep_group_a_plus_2008_turnover.py`

Why:

- `evaluate_group_a_tdcc_overlay_variants.py` still imported root-level `run_group_a_shareholding_shadow`, but the file now lives at `scripts/misc/run_group_a_shareholding_shadow.py`.
- `compare_group_a_plus_2008_golden_latest.py` could not load the latest PPO checkpoint because the 2008 proxy env observation dim was 41 while the checkpoint expected 43.
- The script now inspects checkpoint observation dim and adds enough available DJI shared proxy columns to match the model.
- `scripts/sweep/sweep_group_a_plus_2008_turnover.py` did not add project root to `sys.path`, so it failed when run from `scripts/sweep`.

These are replay harness fixes only; they do not change production strategy logic.

## Tests Run

```bash
.venv/bin/python -m pytest tests/test_ncf_external_cache.py tests/test_ncf_data_quality.py -q
```

Result:

- `11 passed`

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_market_state.py tests/test_group_a_plus_daily_signal_v2.py -q
```

Result:

- `28 passed`

## 2025-01-02 to 2026-07-02 Active Backtest

Command:

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-07-02 \
  --initial-value 1000000 \
  --output results/group_a_plus_runner_latest_20250102_20260702.json \
  --frame-output results/group_a_plus_runner_latest_20250102_20260702_frame.csv
```

Outputs:

- `results/group_a_plus_runner_latest_20250102_20260702.json`
- `results/group_a_plus_runner_latest_20250102_20260702_frame.csv`
- `results/group_a_plus_runner_latest_20250102_20260702_frame_market_state.csv`
- `results/group_a_plus_runner_latest_20250102_20260702_market_state_summary.json`

Metrics:

| Metric | Value |
|---|---:|
| final value | 2,138,725.89 |
| total return | 113.87% |
| annual return | 66.29% |
| Sharpe | 2.5258 |
| Sortino | 2.7804 |
| max drawdown | -13.82% |
| worst daily return | -4.24% |
| rebalance count | 6 |

Execution regime counts:

| Regime | Days |
|---|---:|
| `golden1` | 286 |
| `group_a_plus_defensive` | 69 |
| `ncf_late_bull_hedge` | 5 |
| `group_a_plus_recovery` | 1 |

Fine market-state counts:

| State | Days |
|---|---:|
| `late_bull_overheat` | 161 |
| `bear_breakdown` | 44 |
| `bull_acceleration` | 43 |
| `bull_pullback_shallow` | 27 |
| `bull_trend` | 26 |
| `crash_risk` | 23 |
| `bull_pullback_deep` | 15 |
| `choppy_range_high_risk` | 13 |
| `choppy_range_low_risk` | 8 |
| `recovery_early` | 1 |

Latest date state on 2026-07-02:

- `late_bull_overheat`
- label: `多頭末段過熱`
- allocation bias: `0050 core with reduced 00631L`

Rough close-price buy-and-hold benchmark, no costs/dividends:

| Benchmark | Total Return | Max DD | Sharpe |
|---|---:|---:|---:|
| 0050 B&H | 124.27% | -28.47% | 2.2207 |
| 00631L B&H | 264.84% | -50.23% | 1.9536 |
| 0050/00631L 50/50 | 190.28% | -40.06% | 2.0553 |
| active strategy | 113.87% | -13.82% | 2.5258 |

Interpretation:

- Active strategy is defensive and risk-controlled.
- It underperforms pure bull-market holding return, but it materially reduces drawdown and improves Sharpe.

## A21.18 Late-Bull NCF Parameter Sweep

Command, pinned production panel:

```bash
.venv/bin/python scripts/sweep/bayesopt_a2118_trigger.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-07-02 \
  --init-points 8 \
  --n-iter 20 \
  --search-h5 \
  --max-trigger-rate 0.05 \
  --trigger-penalty 1.0 \
  --output results/bayesopt_a2118_3d_20250102_20260702.json \
  --top-n 12
```

Best pinned-panel candidate:

- `h20_max = 0.3228`
- `conf_min = 0.4886`
- `h5_reentry_min = 0.3929`

Exact reruns:

| Run | Final | Annual | Sharpe | Sortino | MDD | Hedge Days |
|---|---:|---:|---:|---:|---:|---:|
| active pinned 20260630 | 2,138,725.89 | 66.29% | 2.5258 | 2.7804 | -13.82% | 5 |
| tuned pinned same-day | 2,129,580.15 | 65.81% | 2.5734 | 2.8431 | -13.82% | 8 |
| tuned pinned delay1 | 2,092,289.27 | 63.86% | 2.5346 | 2.7821 | -13.82% | 8 |

Interpretation:

- Same-day tuned params improve Sharpe but reduce final value.
- Delay1, which is more live-realistic for NCF signals generated after close, weakens the result materially.
- Do not promote.

Fresh 20260702 panel sweep:

Command:

```bash
.venv/bin/python scripts/sweep/bayesopt_a2118_trigger.py \
  --panel results/ncf_00631l_panel_latest_20260702.csv \
  --start 2025-01-02 \
  --end 2026-07-02 \
  --init-points 8 \
  --n-iter 20 \
  --search-h5 \
  --max-trigger-rate 0.05 \
  --trigger-penalty 1.0 \
  --output results/bayesopt_a2118_3d_panel20260702_20250102_20260702.json \
  --top-n 12
```

Best fresh-panel candidate:

- `h20_max = 0.3455`
- `conf_min = 0.45`
- `h5_reentry_min = 0.70`

Exact reruns:

| Run | Final | Annual | Sharpe | Sortino | MDD | Hedge Days |
|---|---:|---:|---:|---:|---:|---:|
| active params on 20260702 panel | 2,194,740.87 | 69.19% | 2.5362 | 2.8065 | -13.82% | 11 |
| tuned 20260702 same-day | 2,146,163.38 | 66.67% | 2.6456 | 2.9641 | -13.82% | 40 |
| tuned 20260702 delay1 | 2,093,074.24 | 63.90% | 2.5753 | 2.8524 | -13.82% | 40 |

Interpretation:

- Fresh-panel tuned candidate is very conservative: hedge days rise to 40.
- Sharpe improves, but final value drops versus active params on the same panel.
- Delay1 still reduces return materially.
- Keep as shadow only.

Summary output:

- `results/a2118_parameter_tuning_20250102_20260702_summary.json`

## 2008 TWII Proxy Stress Test

Command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-groupa \
.venv/bin/python compare_group_a_plus_2008_golden_latest.py
```

Outputs:

- `results/group_a_plus_golden1_vs_latest_twii_proxy_2008_20260612.json`
- `results/group_a_plus_golden1_vs_latest_twii_proxy_2008_20260612.csv`

Actual proxy window:

- 2007-07-02 to 2010-12-31
- 873 rows

Proxy method:

- `0050.TW`: 1x TWII daily returns
- `00631L.TW`: 2x TWII daily returns
- `00632R.TW`: -1x TWII daily returns
- `00679B.TWO`: Group B style 0.45x TWII proxy with lower vol scale

Results:

| Strategy | Mode | Final | Annual | Sharpe | MDD | Vol | Rebalances |
|---|---|---:|---:|---:|---:|---:|---:|
| Golden1_0531 | base model | 1,494,398.92 | 12.31% | 0.5724 | -38.02% | 20.43% | 310 |
| Golden1_0531 | GroupA+ overlay | 1,300,945.64 | 7.81% | 0.4319 | -51.77% | 24.66% | 110 |
| latest production | base model | 1,358,851.30 | 9.27% | 0.4123 | -49.75% | 23.13% | 149 |
| latest production | GroupA+ overlay | 1,525,717.87 | 12.83% | 0.7154 | -38.26% | 19.81% | 155 |

Conclusion:

- Best 2008 proxy result is latest production plus GroupA+ overlay.
- Compared with Golden1 plus GroupA+ overlay:
  - final value: +224,772.23
  - Sharpe: +0.2836
  - MDD: +13.51pp improvement
  - volatility: -4.85pp
  - contribution return: +18.58pp

## 2008 Turnover Cap Sweep

Command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-groupa \
.venv/bin/python scripts/sweep/sweep_group_a_plus_2008_turnover.py
```

Outputs:

- `results/group_a_plus_2008_turnover_sweep_20260612.json`
- `results/group_a_plus_2008_turnover_sweep_20260612.csv`

Latest production plus GroupA+ overlay results:

| Turn Cap | Final | Sharpe | MDD | Vol |
|---:|---:|---:|---:|---:|
| 25% | 1,504,721.32 | 0.7002 | -39.67% | 19.61% |
| 20% | 1,510,873.15 | 0.7049 | -39.33% | 19.66% |
| 18% | 1,512,484.04 | 0.7057 | -39.20% | 19.69% |
| 15% | 1,519,204.06 | 0.7108 | -38.79% | 19.75% |
| 12% current | 1,525,717.87 | 0.7154 | -38.26% | 19.81% |
| 10% | 1,521,716.70 | 0.7105 | -37.93% | 19.85% |
| 8% | 1,517,576.70 | 0.7051 | -37.61% | 19.91% |

Interpretation:

- Current 12% turnover cap remains a good balanced point for 2008.
- 8% improves MDD but reduces final value and Sharpe.
- 10% improves MDD versus current but loses some final value in this single-parameter sweep.

## 2008 Latest-Only Micro Sweep

Command used an inline Python script to replay only latest production and sweep:

- risk-off 00679B weight
- severe 00679B weight
- risk-off/severe turnover cap
- fast risk-off cash floor

Outputs:

- `results/group_a_plus_2008_latest_micro_sweep_20260703.json`
- `results/group_a_plus_2008_latest_micro_sweep_20260703.csv`

Grid:

- `risk_off_bond`: `[0.00, 0.01, 0.02, 0.03, 0.04, 0.05]`
- `severe_bond`: `risk_off_bond + [0.00, 0.02, 0.04]`, capped at 0.10
- `turnover_cap`: `[0.08, 0.10, 0.12, 0.15]`
- `cash_floor`: `[0.25, 0.30, 0.35]`

Current 2008 overlay-equivalent row:

- mode: `bond02_sev04_turn12_cash30`
- final: 1,525,717.87
- annual: 12.8331%
- Sharpe: 0.715406
- MDD: -38.2630%
- vol: 19.8107%
- rebalances: 155

Best score and best final row:

- mode: `bond00_sev00_turn10_cash35`
- final: 1,530,155.05
- annual: 12.9268%
- Sharpe: 0.719725
- MDD: -37.8904%
- vol: 19.8074%
- rebalances: 154

Delta versus current:

- final: +4,437.17
- annual return: +0.0937pp
- Sharpe: +0.00432
- MDD: +0.3726pp improvement
- vol: -0.0033pp
- contribution return: +0.3667pp

Best MDD row:

- mode: `bond00_sev02_turn08_cash35`
- final: 1,525,117.66
- Sharpe: 0.713533
- MDD: -37.4922%

Interpretation:

- For 2008 proxy only, the best micro-tuned profile removes the synthetic 00679B sleeve in risk-off/severe, lowers turnover cap to 10%, and raises fast risk-off cash floor to 35%.
- Improvement is small but directionally clean.
- It suggests that in a 2008-style crash, cash was more useful than the synthetic 00679B proxy.

Do not promote this directly. It is 2008-proxy-only and must pass modern and multi-window checks.

## Candidate Shadow Config

Name suggestion:

- `group_a_plus_2008_stress_shadow_bond00_turn10_cash35`

Parameter patch:

```json
{
  "overlay": {
    "dynamic_weight_bands": {
      "risk_on": 0.0,
      "caution": 0.01,
      "risk_off": 0.0,
      "severe": 0.0
    }
  },
  "execution_control": {
    "max_turnover_ratio_by_regime": {
      "risk_on": 1.0,
      "caution": 1.0,
      "risk_off": 0.10,
      "severe": 0.10
    }
  },
  "fast_risk_off_control": {
    "cash_floor": 0.35
  }
}
```

Do not overwrite `group_a_plus_config.json` yet.

## Important Limitations

1. The 2008 run is a TWII-derived proxy, not exact ETF history.
2. 00631L, 00632R, and 00679B did not have full real 2008 trading histories in this setup.
3. 00679B is synthetic and may not reflect real long-Treasury behavior in an actual Taiwan portfolio.
4. Missing historical TDCC/institutional/margin/LLM inputs are proxied or zero-filled.
5. A21.18 NCF late-bull trigger sweeps are sensitive to panel version and same-day versus delay1 execution assumptions.
6. The 2008 micro-sweep is intentionally stress-only and may overfit crash dynamics.

## Recommended Next Steps

### 1. Validate 2008 shadow candidate on 2025-2026

Run a modern replay with the same shadow config patch and compare against current.

Target acceptance:

- final value does not drop materially,
- Sharpe does not fall below current by more than 0.02,
- MDD not worse,
- turnover not materially higher.

### 2. Multi-window stress

Run existing multi-window stress harness if available:

- `scripts/misc/stress_group_a_plus_multi_windows.py`
- `scripts/evaluate/evaluate_group_a_plus_a17_a18_a19_stress.py`

Target windows:

- 2008 proxy
- 2015 China FX
- 2016 stress
- 2020 COVID
- 2022 inflation
- 2025-2026 recent bull/late-bull

### 3. Keep A21.18 trigger tuning as shadow only

Do not change active:

- `h20_max = 0.33`
- `conf_min = 0.55`
- `h5_reentry_min = 0.55`

Shadow candidates to track:

- pinned 20260630 panel: `h20=0.3228, conf=0.4886, h5=0.3929`
- 20260702 panel: `h20=0.3455, conf=0.45, h5=0.70`

But both need delay1 and longer OOS validation.

## Repro Commands

### Active latest backtest

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-07-02 \
  --initial-value 1000000 \
  --output results/group_a_plus_runner_latest_20250102_20260702.json \
  --frame-output results/group_a_plus_runner_latest_20250102_20260702_frame.csv
```

### A21.18 pinned-panel sweep

```bash
.venv/bin/python scripts/sweep/bayesopt_a2118_trigger.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 \
  --end 2026-07-02 \
  --init-points 8 \
  --n-iter 20 \
  --search-h5 \
  --max-trigger-rate 0.05 \
  --trigger-penalty 1.0 \
  --output results/bayesopt_a2118_3d_20250102_20260702.json \
  --top-n 12
```

### 2008 proxy compare

```bash
MPLCONFIGDIR=/tmp/matplotlib-groupa \
.venv/bin/python compare_group_a_plus_2008_golden_latest.py
```

### 2008 turnover sweep

```bash
MPLCONFIGDIR=/tmp/matplotlib-groupa \
.venv/bin/python scripts/sweep/sweep_group_a_plus_2008_turnover.py
```

## Final Decision

Keep current active setup.

Use the 2008 micro-tuned overlay as a shadow candidate only:

- `risk_off_bond = 0.00`
- `severe_bond = 0.00`
- `risk_off/severe turnover_cap = 0.10`
- `fast_risk_off cash_floor = 0.35`

Promotion requires modern replay and multi-window stress validation.
