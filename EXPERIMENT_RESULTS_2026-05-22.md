# Experiment Results And Conclusions

Date: 2026-05-22
Scope: Group A runtime-only release validation
Status: Keep as experiment record and handoff conclusion

## 1. Final Conclusion

Latest recommended Group A release:

- Keep the existing best checkpoint:
  - `models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`
- Keep the previous canonical release payload as the baseline replay artifact:
  - `results/group_a_release_runtime_j15_20260522.json`
- Promote the latest runtime-only optimized config from:
  - `results/group_a_runtime_opt_sweep_20260522.json`
- Keep the optimization note:
  - `GROUP_A_OPTIMIZATION_2026-05-22.md`
- Current signal snapshot remains the prior snapshot and has not been regenerated after the latest optimized overrides:
  - `results/group_a_signal_release_runtime_j15_asof_20260521.json`
  - `results/group_a_signal_release_runtime_j15_asof_20260521.csv`
- Do not retrain for this release.
- The latest promoted change is a runtime overlay update:
  - `pva_j_state_weight: 0.15 -> 0.17`
  - `pva_min_leverage_scale: 0.35 -> 0.40`
  - `pva_buy_dip_strength: 0.60 -> 0.70`
- Keep `positive_leverage_boost = 0.00`.
- Keep `pva_target_vol = 0.012`.
- Keep inverse hedge settings at:
  - `inverse_cap = 0.30`
  - `pva_inverse_hedge_budget = 0.30`
  - `inverse_max_holding_days = 5`

Operational signal as of `2026-05-21` close:

- Signal status: `hold`
- Reason: `cooldown_2d`
- Current executable status: `hold_current`
- Candidate strategy weights before execution guard:
  - `0050.TW`: 82.01%
  - `00631L.TW`: 17.99%
  - `00632R.TW`: 0.00%
- Actual target after hold guard:
  - Keep current 100% `0050.TW`

## 2. Final Performance Record

Previous release source:

- `results/group_a_release_runtime_j15_20260522.json`

Latest optimized runtime source:

- `results/group_a_runtime_opt_sweep_20260522.json`

Backtest window:

- `2024-01-02` to `2026-05-21`

Metrics:

| Metric | Previous release | Optimized runtime |
|---|---:|---:|
| Final value | 3,701,904.44 | 3,720,143.22 |
| Annual return | 77.8230% | 78.2078% |
| Sharpe | 2.314227 | 2.330360 |
| Max drawdown | -23.5605% | -23.0082% |
| Volatility | 25.4315% | 25.3379% |
| Trades | 99 | 99 |
| PVA activations | 52 | 54 |
| Estimated fees | 55,595.82 | 56,249.14 |
| Total invested capital | 1,145,000.00 | 1,145,000.00 |
| Net profit | 2,556,904.44 | 2,575,143.22 |

Delta versus previous promoted runtime:

- Baseline payload:
  - `results/group_a_release_runtime_j15_20260522.json`
- Final value improved by `+18,238.79`.
- Sharpe improved by `+0.016133`.
- Max drawdown improved by about `+0.5523 pp`.
- Trade count was unchanged.

Interpretation:

- The improvement is larger than the prior J-state-only release refinement and improves final value, Sharpe, drawdown, and volatility without increasing turnover.
- This is a runtime refinement, not a new model release.

## 3. Experiment Log

### Runtime J-state / S-state sweep

Source:

- `results/group_a_runtime_sweep_jgrid_sboost_20260522_150634.json`

Result:

- Best run: `j15_s00`
- Runtime override:
  - `pva_j_state_weight = 0.15`
  - `pva_s_state_drift_boost = 0.00`
  - `pva_s_state_max_weight = 0.30`
- Final value: `3,701,904.44`
- Sharpe: `2.314227`
- Max drawdown: `-23.5605%`

Conclusion:

- Promote `pva_j_state_weight = 0.15`.
- Do not enable S-state drift boost. All tested `s15` variants reduced final value and worsened drawdown.

### Inverse hedge sweep

Source:

- `results/group_a_inverse_sweep_20260522_153846.json`

Result:

- Best run stayed at baseline:
  - `inverse_cap = 0.30`
  - `pva_inverse_hedge_budget = 0.30`
  - `inverse_max_holding_days = 5`
- Raising cap/budget to `0.40` had no practical effect.
- Extending inverse holding to `7` days reduced final value by `-137,949.61`, reduced Sharpe by `-0.075115`, and worsened max drawdown by about `-3.17%`.

Conclusion:

- Keep current inverse hedge settings.
- Do not extend inverse holding period beyond 5 days for this release.

### Positive sentiment leverage boost sweep

Source:

- `results/group_a_sentiment_positive_sweep_20260522_155800.json`

Result:

| Boost | Final value | Sharpe | Delta final value | Delta Sharpe |
|---:|---:|---:|---:|---:|
| 0.00 | 3,701,904.44 | 2.314227 | 0.00 | 0.000000 |
| 0.03 | 3,696,314.23 | 2.310427 | -5,590.21 | -0.003800 |
| 0.05 | 3,524,346.17 | 2.212232 | -177,558.26 | -0.101995 |
| 0.08 | 3,518,353.13 | 2.208157 | -183,551.31 | -0.106071 |

Conclusion:

- Positive sentiment boost support can remain in code, but release config must keep `positive_leverage_boost = 0.00`.
- Positive boost degraded both return and Sharpe in every tested nonzero setting.

### PVA target volatility sweep

Source:

- `results/group_a_pva_target_vol_sweep_20260522_174047.json`

Result:

| Target vol | Final value | Sharpe | Delta final value | Delta Sharpe |
|---:|---:|---:|---:|---:|
| 0.0120 | 3,701,904.44 | 2.314227 | 0.00 | 0.000000 |
| 0.0140 | 3,671,779.43 | 2.288607 | -30,125.00 | -0.025620 |
| 0.0150 | 3,666,903.33 | 2.281818 | -35,001.11 | -0.032409 |
| 0.0165 | 3,655,615.31 | 2.252461 | -46,289.13 | -0.061766 |
| 0.0180 | 3,661,146.14 | 2.252445 | -40,758.29 | -0.061782 |
| 0.0200 | 3,662,526.84 | 2.251422 | -39,377.60 | -0.062805 |

Conclusion:

- Keep `pva_target_vol = 0.012`.
- Higher target volatility consistently reduced final value and Sharpe while slightly worsening drawdown.

### Local runtime optimization sweep

Source:

- `results/group_a_runtime_opt_sweep_20260522.json`
- Baseline smoke:
  - `results/group_a_runtime_opt_smoke_20260522.json`
- Summary note:
  - `GROUP_A_OPTIMIZATION_2026-05-22.md`

Result:

- Best run kept the checkpoint unchanged and promoted these runtime overrides:
  - `pva_weight = 0.30`
  - `pva_j_state_weight = 0.17`
  - `pva_drift_threshold = 0.05`
  - `pva_min_leverage_scale = 0.40`
  - `pva_buy_dip_strength = 0.70`
  - `dca_day = 20`

| Metric | Previous release | Optimized candidate | Delta |
|---|---:|---:|---:|
| Final value | 3,701,904.44 | 3,720,143.22 | +18,238.79 |
| Sharpe | 2.314227 | 2.330360 | +0.016133 |
| Max drawdown | -23.5605% | -23.0082% | +0.5523 pp |
| Trades | 99 | 99 | 0 |
| PVA activations | 52 | 54 | +2 |

Conclusion:

- Promote the optimized runtime overrides above.
- Do not retrain PPO for this change.
- Keep `pva_target_vol = 0.012`, inverse hedge settings unchanged, and `positive_leverage_boost = 0.00`.
- The previous canonical release payload remains useful for replay baseline comparison but does not carry the latest optimized overrides.

## 4. Files To Keep

Primary handoff files:

- `GROUP_A_LATEST_HANDOFF_2026-05-22.md`
- `GROUP_A_OPTIMIZATION_2026-05-22.md`
- `EXPERIMENT_RESULTS_2026-05-22.md`
- `results/group_a_release_runtime_j15_20260522.json`
- `results/group_a_signal_release_runtime_j15_asof_20260521.json`
- `results/group_a_signal_release_runtime_j15_asof_20260521.csv`
- `models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`

Supporting evidence:

- `results/group_a_runtime_sweep_jgrid_sboost_20260522_150634.json`
- `results/group_a_inverse_sweep_20260522_153846.json`
- `results/group_a_sentiment_positive_sweep_20260522_155800.json`
- `results/group_a_pva_target_vol_sweep_20260522_174047.json`
- `results/group_a_runtime_opt_sweep_20260522.json`
- `results/group_a_runtime_opt_smoke_20260522.json`

Do not use these as the production signal source:

- `results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json`
- `results/group_a_backtest_20240102_20260521_j12_sboost15_20260522_150433.json`

Reason:

- They are comparison/evidence payloads, not the canonical release payload schema.

## 5. Next Review Checklist

Before changing the release again:

- Create or update a runtime payload that carries the optimized overrides before signal generation.
- Re-run signal generation from that optimized runtime payload.
- Compare against `results/group_a_runtime_opt_sweep_20260522.json` and keep `results/group_a_release_runtime_j15_20260522.json` as the prior-release baseline.
- Require improvement in final value or Sharpe without worse drawdown or higher trade count.
- Treat any new PPO resume training as a separate experiment, not a release replacement, unless it beats this runtime release cleanly.
