# Group A Latest Handoff

> Superseded on 2026-05-24 by [`GROUP_A_LATEST_HANDOFF_2026-05-24.md`](GROUP_A_LATEST_HANDOFF_2026-05-24.md). Keep this file as the 2026-05-22 handoff record.

Date: 2026-05-22
Status: Latest recommended Group A runtime-only handoff
Scope: Group A only

## 1. Source Of Truth

This handoff supersedes the earlier release-candidate note in [`GROUP_A_RELEASE_HANDOFF_2026-05-22.md`](GROUP_A_RELEASE_HANDOFF_2026-05-22.md).

Current source of truth:

- Model checkpoint:
  - [`models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`](models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip)
- Experiment conclusion record:
  - [`EXPERIMENT_RESULTS_2026-05-22.md`](EXPERIMENT_RESULTS_2026-05-22.md)
- Latest optimization record:
  - [`GROUP_A_OPTIMIZATION_2026-05-22.md`](GROUP_A_OPTIMIZATION_2026-05-22.md)
- Latest optimization sweep evidence:
  - [`results/group_a_runtime_opt_sweep_20260522.json`](results/group_a_runtime_opt_sweep_20260522.json)
- Previous canonical release payload:
  - [`results/group_a_release_runtime_j15_20260522.json`](results/group_a_release_runtime_j15_20260522.json)
- Best runtime comparison summary:
  - [`results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json`](results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json)
- Previous baseline release payload:
  - [`results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`](results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json)
- Canonical signal snapshot generated from the release payload:
  - [`results/group_a_signal_release_runtime_j15_asof_20260521.json`](results/group_a_signal_release_runtime_j15_asof_20260521.json)

Important:

- No retraining is recommended.
- The best checkpoint did not change.
- The latest promoted production change remains runtime-only:
  - `pva_j_state_weight: 0.15 -> 0.17`
  - `pva_min_leverage_scale: 0.35 -> 0.40`
  - `pva_buy_dip_strength: 0.60 -> 0.70`
- The previous canonical release payload is retained as the replay baseline, but does not include the latest optimized runtime overrides.

## 2. Canonical Files To Keep

Keep these files for handoff:

- Handoff doc:
  - [`GROUP_A_LATEST_HANDOFF_2026-05-22.md`](GROUP_A_LATEST_HANDOFF_2026-05-22.md)
- Optimization doc:
  - [`GROUP_A_OPTIMIZATION_2026-05-22.md`](GROUP_A_OPTIMIZATION_2026-05-22.md)
- Historical release doc:
  - [`GROUP_A_RELEASE_HANDOFF_2026-05-22.md`](GROUP_A_RELEASE_HANDOFF_2026-05-22.md)
- Release payload for replay/signal generation:
  - [`results/group_a_release_runtime_j15_20260522.json`](results/group_a_release_runtime_j15_20260522.json)
- Canonical signal snapshot:
  - [`results/group_a_signal_release_runtime_j15_asof_20260521.json`](results/group_a_signal_release_runtime_j15_asof_20260521.json)
  - [`results/group_a_signal_release_runtime_j15_asof_20260521.csv`](results/group_a_signal_release_runtime_j15_asof_20260521.csv)
- Best checkpoint:
  - [`models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`](models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip)
- Runtime sweep evidence:
  - [`results/group_a_runtime_sweep_jgrid_sboost_20260522_150634.json`](results/group_a_runtime_sweep_jgrid_sboost_20260522_150634.json)
- Inverse sweep evidence:
  - [`results/group_a_inverse_sweep_20260522_153846.json`](results/group_a_inverse_sweep_20260522_153846.json)
- Positive sentiment sweep evidence:
  - [`results/group_a_sentiment_positive_sweep_20260522_155800.json`](results/group_a_sentiment_positive_sweep_20260522_155800.json)
- PVA target-vol sweep evidence:
  - [`results/group_a_pva_target_vol_sweep_20260522_174047.json`](results/group_a_pva_target_vol_sweep_20260522_174047.json)
- Latest optimized runtime sweep evidence:
  - [`results/group_a_runtime_opt_sweep_20260522.json`](results/group_a_runtime_opt_sweep_20260522.json)
- Baseline smoke validation:
  - [`results/group_a_runtime_opt_smoke_20260522.json`](results/group_a_runtime_opt_smoke_20260522.json)

Files to treat as analysis artifacts, not release payloads:

- [`results/group_a_backtest_20240102_20260521_j12_sboost15_20260522_150433.json`](results/group_a_backtest_20240102_20260521_j12_sboost15_20260522_150433.json)
- [`results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json`](results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json)

## 3. Recommended Runtime Config

Use the checkpoint above together with the optimized runtime overrides below. The previous canonical payload is retained as a baseline artifact and should not be treated as carrying these latest overrides unless it is updated.

- `group_a_profile = default`
- `group_a_action_schema = triplet_v3_cash50`
- `min_rebalance_days = 5`
- `leverage_cap (00631L) = 0.30`
- `inverse_cap (00632R) = 0.30`
- `inverse_m_state_only = true`
- `inverse_max_holding_days = 5`
- `enable_pva_features = true`
- `enable_pva_sigmoid = true`
- `pva_weight = 0.30`
- `pva_j_state_weight = 0.17`
- `pva_m_state_weight = 1.00`
- `pva_drift_threshold = 0.05`
- `pva_s_state_drift_boost = 0.00`
- `pva_s_state_max_weight = 0.30`
- `pva_target_vol = 0.012`
- `pva_min_leverage_scale = 0.40`
- `pva_inverse_hedge_budget = 0.30`
- `pva_buy_dip_strength = 0.70`
- `group_a_enable_dca = true`
- `dca_day = 20`
- `dca_0050 = 5000`
- `group_a_enable_llm_sentiment = true`
- `sentiment_risk_off_threshold = 0.10`
- `sentiment_severe_threshold = 0.15`
- `sentiment_min_confidence = 0.40`
- `sentiment_min_intensity = 0.00`
- `sentiment_risk_off_inverse_floor = 0.15`
- `sentiment_severe_inverse_floor = 0.30`
- `sentiment_positive_min_confidence = 0.30`
- `sentiment_positive_threshold = 0.10`
- `sentiment_positive_max_risk_off_score = 0.10`
- `sentiment_positive_leverage_boost = 0.00`

Interpretation:

- Positive LLM boost support exists in code.
- The validated release keeps that boost disabled.

## 4. Performance Summary

Latest optimized runtime:

- Source:
  - [`results/group_a_runtime_opt_sweep_20260522.json`](results/group_a_runtime_opt_sweep_20260522.json)
- Backtest window:
  - `2024-01-02` to `2026-05-21`
- Final value:
  - `3,720,143.22`
- Annual return:
  - `78.2078%`
- Sharpe:
  - `2.330360`
- Max drawdown:
  - `-23.0082%`
- Trades:
  - `99`
- PVA activations:
  - `54`

Delta vs previous runtime release [`results/group_a_release_runtime_j15_20260522.json`](results/group_a_release_runtime_j15_20260522.json):

- Final value:
  - `+18,238.79`
- Sharpe:
  - `+0.016133`
- Max drawdown:
  - Improved by about `+0.5523 pp`
- Trades:
  - Unchanged

## 5. What Was Rejected

These ideas were tested and should stay off in the release payload:

- `S-state drift boost`
  - degraded performance across the sweep
- `inverse_cap = 0.40`
  - had no practical effect because realized `00632R` sizing never hit the old cap
- `inverse_max_holding_days = 7`
  - clearly worsened return and drawdown
- `positive LLM sentiment leverage boost`
  - implementation exists, but every tested nonzero boost degraded performance
- `pva_target_vol > 0.012`
  - `0.014 / 0.015 / 0.0165 / 0.018 / 0.020` all underperformed the current `0.012` baseline on both final value and Sharpe
  - the best runtime remains `pva_target_vol = 0.012`

## 6. Suggested File Names For Handoff

If you want a minimal bundle for GitHub or manual delivery, use these names as the primary references:

- `GROUP_A_LATEST_HANDOFF_2026-05-22.md`
- `GROUP_A_OPTIMIZATION_2026-05-22.md`
- `results/group_a_runtime_opt_sweep_20260522.json`
- `results/group_a_release_runtime_j15_20260522.json`
- `models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`

Optional supporting files:

- `GROUP_A_OPTIMIZATION_2026-05-22.md`
- `results/group_a_runtime_opt_sweep_20260522.json`
- `results/group_a_runtime_opt_smoke_20260522.json`
- `results/group_a_runtime_sweep_jgrid_sboost_20260522_150634.json`
- `results/group_a_inverse_sweep_20260522_153846.json`
- `results/group_a_sentiment_positive_sweep_20260522_155800.json`
- `results/group_a_pva_target_vol_sweep_20260522_174047.json`

## 7. Operational Snapshot

Current signal snapshot from the previous release payload:

- JSON:
  - [`results/group_a_signal_release_runtime_j15_asof_20260521.json`](results/group_a_signal_release_runtime_j15_asof_20260521.json)
- CSV:
  - [`results/group_a_signal_release_runtime_j15_asof_20260521.csv`](results/group_a_signal_release_runtime_j15_asof_20260521.csv)

As of `2026-05-21` close:

- Signal status:
  - `hold`
- Reason:
  - `cooldown_2d`
- Data staleness:
  - `0d`
- Current action label:
  - `rebalance_to_0050_70_00631L_30`
- Candidate weights:
  - `0050 82% / 00631L 18%`
- Executable status:
  - `hold_current`

## 8. Replay / Signal Generation

The latest optimization sweep JSON is evidence, not a full signal-generation payload.

For production signal generation, first create or update a runtime payload that carries these optimized overrides:

- `pva_j_state_weight = 0.17`
- `pva_min_leverage_scale = 0.40`
- `pva_buy_dip_strength = 0.70`
- `dca_day = 20`

The previous release payload below remains valid as a baseline replay artifact, but by itself it carries the older runtime settings:

```bash
python3 generate_dual_group_signal.py \
  --group group_a \
  --result-json results/group_a_release_runtime_j15_20260522.json \
  --download-end 2026-05-22 \
  --as-of-date 2026-05-21
```

Do not use the following file directly for signal generation:

- `results/group_a_backtest_20240102_20260521_j15_s00_20260522_150739.json`
- `results/group_a_runtime_opt_sweep_20260522.json`

Reason:

- These are comparison/evidence summaries, not the full release payload schema.
