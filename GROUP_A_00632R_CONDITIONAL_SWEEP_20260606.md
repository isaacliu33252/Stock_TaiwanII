# Group A 00632R Conditional Sweep 2026-06-06

資料區間：2024-01-02 至 2026-06-04。  
方法：不重訓 PPO，沿用 `Golden1_0531_tdcc_v1_destination_primary` 的 rebalance events，改寫 00632R target events / DCA history 後 replay。

## Scope

本輪改善針對「正常市場限制 00632R、壓力市場允許 hedge」：

- 新增複合壓力條件：
  - `stress_any`: `0050 below MA60` 或 `0050 21d momentum < 0` 或 `Group A drawdown <= -10%`
  - `stress_strict`: `0050 below MA60` 且 `momentum < 0` 或 `drawdown <= -10%`
  - `stress_price_only`: `0050 below MA60` 或 `0050 21d momentum < 0`
- 新增 stress-aware hold-limit：
  - 超過 5/10/20 天時，只有在非壓力條件下才把 00632R 轉到 0050。

## Baseline

| Variant | Final | Sharpe | MDD | 00632R Events | Max 00632R | DCA |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_destination_primary` | 3,168,631 | 2.1789 | -26.43% | 9 | 30.00% | 145,000 |

## Best Return Candidates

| Variant | Final | Delta Final | Sharpe | MDD | 00632R Events | DCA |
|---|---:|---:|---:|---:|---:|---:|
| `disable_00632r_to_0050_dca_double_group_dd10` | 3,638,689 | +470,058 | 2.2942 | -28.06% | 0 | 175,000 |
| `disable_00632r_to_0050_dca_double_below_ma60` | 3,603,604 | +434,973 | 2.2783 | -28.06% | 0 | 160,000 |
| `disable_00632r_to_0050` | 3,566,548 | +397,917 | 2.2622 | -28.30% | 0 | 145,000 |

Interpretation:

- These are aggressive 2024-2026 winners.
- They should not be production candidates without stronger 2008/stress validation, because prior 2008 proxy results do not support fully disabling 00632R.

## Balanced / Robust Candidates

| Variant | Final | Delta Final | Sharpe | MDD | 00632R Events | Max 00632R |
|---|---:|---:|---:|---:|---:|---:|
| `conditional_00632r_stress_any_cap10_to_0050` | 3,433,689 | +265,058 | 2.2481 | -27.63% | 6 | 10.00% |
| `conditional_00632r_below_ma60_cap10_to_0050` | 3,433,689 | +265,058 | 2.2481 | -27.63% | 6 | 10.00% |
| `cap_00632r_10_to_0050_dca_double_group_dd10` | 3,497,232 | +328,600 | 2.2816 | -27.50% | 9 | 10.00% |
| `hold_limit_00632r_10d_to_0050` | 3,323,211 | +154,579 | 2.2416 | -26.43% | 9 | 30.00% |

Recommendation after 2008 proxy tie-break:

- Primary robust candidate: `conditional_00632r_stress_strict_cap10_to_0050`
- Conservative candidate: `hold_limit_00632r_10d_to_0050`
- Aggressive research-only candidate: `disable_00632r_to_0050_dca_double_group_dd10`

## Best Drawdown Candidates With Baseline-Or-Better Final

| Variant | Final | Delta Final | Sharpe | MDD | DCA |
|---|---:|---:|---:|---:|---:|
| `conditional_00632r_below_ma60_to_0050_dca_double_below_ma60` | 3,210,941 | +42,309 | 2.1965 | -26.05% | 160,000 |
| `conditional_00632r_below_ma60_to_0050_dca_double_group_dd10` | 3,245,097 | +76,465 | 2.2148 | -26.06% | 175,000 |
| `dca_double_below_ma60` | 3,203,872 | +35,240 | 2.1966 | -26.17% | 160,000 |
| `dca_double_group_dd10` | 3,238,011 | +69,379 | 2.2149 | -26.17% | 175,000 |

Interpretation:

- DCA timing helped both return and MDD in this window.
- These are not pure allocation changes; they assume larger contributions during drawdown / below-MA regimes.

## Rejected / Weak Finding

Stress-aware hold-limit variants were identical to baseline in this 2024-2026 replay:

- `hold_limit_00632r_5d_unless_stress_*`
- `hold_limit_00632r_10d_unless_stress_*`
- `hold_limit_00632r_20d_unless_stress_*`

Reason:

- The 00632R events in this replay mostly occurred while the stress conditions were already true, so the `unless stress` exception prevented the hold-limit from acting.

## Decision

Do not replace production `Golden1_0531` yet.

Implementation status:

- Added live/shadow config: `group_a_00632r_conditional_cap_overlay_config.json`
- Integrated overlay in `run_group_a_tdcc_improved_signal.py`
- Current condition: `stress_strict`
- Runner order:
  1. base Group A signal
  2. TDCC `destination_primary`
  3. conditional 00632R cap overlay
  4. optional 00632R hold10 overlay
- Smoke output:
  - `results/group_a_tdcc_improved_signal_20260606_125001.json`
  - `results/group_a_tdcc_improved_signal_20260606_125001.csv`
  - `results/group_a_tdcc_improved_signal_20260606_125001_trade_log.csv`
  - `results/group_a_tdcc_improved_bundle_latest.json`

Next validation target:

1. Add walk-forward / epoch OOS validation before any production replacement.
2. Keep `hold_limit_00632r_10d_to_0050` as the conservative fallback because it improves 2024-2026 without worsening MDD.
3. Keep the 2008 conditional check as the stress-test tie-break: `stress_strict_cap10` beat `stress_any_cap10` on 2008 proxy event replay.

## Outputs

- Script: `backtest_group_a_00632r_dca_sweep.py`
- JSON: `results/group_a_00632r_conditional_sweep_20240102_20260604.json`
- CSV: `results/group_a_00632r_conditional_sweep_20240102_20260604.csv`
- Curve CSV: `results/group_a_00632r_conditional_sweep_20240102_20260604_curve.csv`
