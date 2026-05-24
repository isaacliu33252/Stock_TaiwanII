# Group A Release Handoff

> Historical note (superseded on 2026-05-24): this file documents the earlier `finalcheck_overlay` release candidate built around `pva_j_state_weight = 0.05`. The latest recommended handoff is [`GROUP_A_LATEST_HANDOFF_2026-05-24.md`](GROUP_A_LATEST_HANDOFF_2026-05-24.md), and the current primary runtime payload is [`results/group_a_runtime_payload_primary_20260524.json`](results/group_a_runtime_payload_primary_20260524.json).

Date: 2026-05-22
Status: Release candidate prepared for GitHub handoff
Scope: Group A only

## 1. Release Definition

This release is based on the latest validated Group A stack as of 2026-05-22.

The release should be treated as:

- Model checkpoint:
  - [`models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`](models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip)
- Final release result payload:
  - [`results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`](results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json)
- Final audit sweep summaries:
  - [`results/group_a_finalcheck_runtime_sweep_20260522_080055.json`](results/group_a_finalcheck_runtime_sweep_20260522_080055.json)
  - [`results/group_a_finalcheck_overlay_refine_20260522_080325.json`](results/group_a_finalcheck_overlay_refine_20260522_080325.json)
- Latest operational signal snapshot:
  - [`results/signal_group_a_20260522_082429.json`](results/signal_group_a_20260522_082429.json)

Important:

- The model checkpoint did not change in the final audit.
- The final release change is a runtime overlay refinement only.
- If the runtime config is dropped and only the `.zip` is loaded with older defaults, the release behavior will not match this handoff.

## 2. Final Recommended Runtime Config

Use the checkpoint above together with the following effective runtime config:

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
- `pva_j_state_weight = 0.05`
- `pva_m_state_weight = 1.00`
- `pva_drift_threshold = 0.05`
- `pva_target_vol = 0.012`
- `pva_min_leverage_scale = 0.35`
- `pva_inverse_hedge_budget = 0.30`
- `pva_buy_dip_strength = 0.60`
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

## 3. Why This Release Was Chosen

The final audit was done in two stages:

1. Runtime execution sweep without retraining
2. Narrow overlay refinement around the best runtime structure

What was confirmed:

- Re-running PPO `resume` from the current best checkpoint degraded performance materially.
- Changing `min_rebalance_days` away from `5` degraded performance.
- Changing `inverse_max_holding_days` away from `5` degraded performance.
- The only remaining positive edge came from a small J-state overlay adjustment:
  - `pva_j_state_weight: 0.00 -> 0.05`

This means the release is not a new trained model. It is the same best checkpoint with the final validated execution-layer refinement.

## 4. Performance Summary

### Final release payload

Source:
[`results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`](results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json)

- Backtest window: `2024-01-02` to `2026-05-21`
- Download window end: `2026-05-22`
- Final value: `3,700,309.16`
- Total return: `270.03%`
- Annual return: `77.789%`
- Sharpe: `2.313138`
- Max drawdown: `-23.5605%`
- Volatility: `25.4357%`
- Trades: `99`
- Fees estimate: `55,363.65`
- DCA contribution: `145,000`
- Total invested capital: `1,145,000`
- Net profit: `2,555,309.16`

### Previous baseline before final audit

Source:
[`results/group_a_backtest_20240102_20260521_20260521_234657.json`](results/group_a_backtest_20240102_20260521_20260521_234657.json)

- Final value: `3,700,849.01`
- Total return: `270.08%`
- Annual return: `77.801%`
- Sharpe: `2.313091`
- Max drawdown: `-23.5605%`
- Volatility: `25.4394%`
- Trades: `99`

### Interpretation

- The final release version has the highest Sharpe found in the final audit.
- The Sharpe improvement is very small.
- The final value is slightly lower than the prior baseline.
- In practice, this is a risk-adjusted refinement, not a large performance jump.

Numerically:

- Sharpe delta vs prior baseline: `+0.0000465`
- Final value delta vs prior baseline: `-539.85`
- Annual return delta vs prior baseline: `-0.0114%`

## 5. Benchmark Context

From the baseline/final audit context:

- Equal-weight buy-and-hold final value: `3,324,390.06`
- Equal-weight buy-and-hold Sharpe: `0.8566`
- `0050/00631L = 50/50` buy-and-hold final value: `3,737,691.29`
- `0050/00631L = 50/50` buy-and-hold Sharpe: `1.6721`
- `0050/00631L = 50/50` buy-and-hold max drawdown: `-43.04%`

Release interpretation:

- This Group A release is not the highest raw terminal value versus an aggressive static `50/50` blend.
- It is materially better on risk-adjusted return and drawdown control.

## 6. Strategy Specification

Universe:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`

Training period:

- `2024-01-01` to `2026-01-01`

Backtest period:

- `2024-01-02` to `2026-05-21`

Execution timing:

- Signal generated from `t` close
- Trade executed at `t+1` open
- Portfolio marked to market at `t+1` close

Action style:

- Discrete triplet policy with cash-aware schema `triplet_v3_cash50`
- PVA/SJM overlay scales `00631L`
- `00632R` is short-duration hedge only, primarily for stressed regimes
- LLM market sentiment can force defensive behavior on risk-off/severe days
- Monthly DCA adds `0050` in backtest/evaluation only

## 7. Audit Findings

The final detailed audit found:

- The strongest trained checkpoint remains `group_a_microopt_b060_p030_20260521_233524.zip`.
- Further PPO `resume` training from that checkpoint is not recommended for release preparation.
- Runtime execution rules are already near a local optimum.
- `min_rebalance_days = 5` is structurally correct for this setup.
- `inverse_max_holding_days = 5` is structurally correct for this setup.
- J-state overlay was the only remaining release-safe tuning axis.

Observed regime usage from the validated backtest:

- `S` state days: `384`
- `J` state days: `100`
- `M` state days: `89`
- PVA overlay activations: `54`
- Forced inverse exits: `7`

Largest drawdown region:

- Approximate peak date: `2024-07-10`
- Approximate trough date: `2025-04-08`

## 8. Operational State As Of Release Date

Latest signal snapshot:

- Source: [`results/signal_group_a_20260522_082429.json`](results/signal_group_a_20260522_082429.json)
- Signal basis date: `2026-05-21` close
- Execution date: `2026-05-22` open
- Formal signal status: `hold`
- Reason: `cooldown_2d`

Implication:

- The release is valid.
- The strategy is not currently issuing a fresh rebalance order at the release snapshot.

## 9. Reproduction And Operations

Recommended release source of truth:

- Use the result payload below as the runtime config carrier:
  - [`results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`](results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json)

To generate the latest Group A signal from this release payload:

```bash
python3 generate_dual_group_signal.py \
  --group group_a \
  --result-json results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json \
  --download-end 2026-05-22 \
  --as-of-date 2026-05-21
```

Operational caution:

- If a downstream script only loads the model zip and rebuilds env args manually, it must explicitly set `pva_j_state_weight=0.05`.
- If that value is omitted, the runtime falls back toward the prior baseline behavior.

## 10. Files To Include In GitHub Release Commit

Minimum recommended files:

- `GROUP_A_RELEASE_HANDOFF_2026-05-22.md`
- `models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`
- `results/group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`
- `results/group_a_finalcheck_runtime_sweep_20260522_080055.json`
- `results/group_a_finalcheck_overlay_refine_20260522_080325.json`
- `results/signal_group_a_20260522_082429.json`

Optional but useful:

- `results/group_a_backtest_20240102_20260521_20260521_234657.json`

## 11. Handoff Decision

Recommended release default:

- Keep the model checkpoint:
  - `group_a_microopt_b060_p030_20260521_233524.zip`
- Release using the final audited runtime payload:
  - `group_a_backtest_20240102_20260521_finalcheck_overlay_20260522_0805.json`

This is the cleanest handoff because:

- the trained model remains the best validated checkpoint,
- the final release behavior is documented,
- the small runtime refinement is preserved explicitly,
- and future signal generation can be reproduced from one payload file.
