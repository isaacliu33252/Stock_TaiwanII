# Group A 2008 Conditional 00632R Check 2026-06-06

資料區間：2007-07-02 至 2010-12-31。  
方法：TWII proxy post-target event replay。使用 baseline 2008 proxy run 的 target events，改寫 00632R target weights 後重放交易成本與 DCA。這不是完整 PPO environment rerun。

## Purpose

驗證 2024-2026 最佳條件式 00632R 改善是否通過 2008 型壓力市場：

- 2024-2026 中 `stress_any_cap10` 與 `stress_strict_cap10` 結果相同。
- 2008 proxy 用來區分哪個條件比較穩健。

## Results

| Variant | Final | Delta Final | Sharpe | Delta Sharpe | MDD | Delta MDD | 00632R Events | Max 00632R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_event_replay` | 1,531,603 | 0 | 0.6424 | 0.0000 | -48.62% | 0.00% | 8 | 11.61% |
| `disable_00632r_to_0050_replay` | 1,528,302 | -3,301 | 0.6373 | -0.0050 | -48.86% | -0.24% | 0 | 0.00% |
| `static_cap10_to_0050_replay` | 1,531,274 | -329 | 0.6421 | -0.0003 | -48.62% | 0.00% | 8 | 10.00% |
| `conditional_stress_any_cap10_to_0050_replay` | 1,529,239 | -2,365 | 0.6402 | -0.0022 | -48.61% | +0.01% | 7 | 6.67% |
| `conditional_stress_strict_cap10_to_0050_replay` | 1,534,950 | +3,347 | 0.6446 | +0.0022 | -48.61% | +0.01% | 6 | 6.31% |

## Conclusion

2008 proxy event replay favors:

- `conditional_stress_strict_cap10_to_0050`

This is stronger than `stress_any` because:

- 2024-2026: `stress_any_cap10` and `stress_strict_cap10` were tied.
- 2008 proxy: `stress_strict_cap10` improved final value, Sharpe, and MDD vs event-replay baseline.
- Fully disabling 00632R remained worse in 2008, consistent with the prior full-env static-cap check.

## Implementation Update

Updated live/shadow config:

- `group_a_00632r_conditional_cap_overlay_config.json`

Current condition:

- `stress_strict`

Definition:

- `0050` below 60-day moving average, and
- either 21-day momentum is negative or Group A drawdown is <= -10%.

## Current Recommendation

Use this as the primary next Group A shadow candidate:

- Base: `Golden1_0531_tdcc_v1_destination_primary`
- Overlay: `conditional_00632r_stress_strict_cap10_to_0050`
- Fallback / conservative benchmark: `hold_limit_00632r_10d_to_0050`

Do not production-replace `Golden1_0531` yet. Next validation should be walk-forward / epoch OOS.

## Outputs

- Script: `backtest_group_a_twii_proxy_2008_conditional_inverse.py`
- JSON: `results/group_a_twii_proxy_2008_conditional_inverse_20070701_20101231.json`
- CSV: `results/group_a_twii_proxy_2008_conditional_inverse_20070701_20101231.csv`
- Curve CSV: `results/group_a_twii_proxy_2008_conditional_inverse_20070701_20101231_curve.csv`
