# Group A Defensive Cap20 Handoff

Date: 2026-05-24
Status: Profile-specific cap-0.20 tuning handoff
Scope: Group A only

## 1. Source Of Truth

This handoff preserves the cap-0.20 tuning details. On 2026-05-24, this profile was promoted to the primary Group A profile; the current source of truth is documented in [`GROUP_A_LATEST_HANDOFF_2026-05-24.md`](GROUP_A_LATEST_HANDOFF_2026-05-24.md).

Current defensive profile artifacts:

- Best checkpoint:
  - [`models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`](models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip)
- Defensive runtime payload for signal generation:
  - [`results/group_a_runtime_payload_defensive_cap20_20260524.json`](results/group_a_runtime_payload_defensive_cap20_20260524.json)
- Runtime optimization evidence:
  - [`results/group_a_runtime_reopt_cap20_20260524.json`](results/group_a_runtime_reopt_cap20_20260524.json)
  - [`results/group_a_runtime_reopt_cap20_focused_20260524.json`](results/group_a_runtime_reopt_cap20_focused_20260524.json)
  - [`results/group_a_runtime_reopt_cap20_micro_20260524.json`](results/group_a_runtime_reopt_cap20_micro_20260524.json)
  - [`results/group_a_runtime_smoke_defensive_cap20_20260524.json`](results/group_a_runtime_smoke_defensive_cap20_20260524.json)
- Crash/production tradeoff reference:
  - [`results/group_a_leverage_cap_dual_objective_20260524.json`](results/group_a_leverage_cap_dual_objective_20260524.json)
  - [`GROUP_A_LEVERAGE_CAP_DUAL_OBJECTIVE_REPORT_2026-05-24.md`](GROUP_A_LEVERAGE_CAP_DUAL_OBJECTIVE_REPORT_2026-05-24.md)
- Defensive signal snapshot:
  - [`results/group_a_signal_defensive_cap20_asof_20260521.json`](results/group_a_signal_defensive_cap20_asof_20260521.json)
  - [`results/group_a_signal_defensive_cap20_asof_20260521.csv`](results/group_a_signal_defensive_cap20_asof_20260521.csv)
- Defensive 2008 proxy stress result:
  - [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json)

Important:

- No retraining was performed.
- The checkpoint is unchanged.
- This profile is intentionally more defensive than the `cap=0.30` production profile.
- `dca_day` remains `20`.

## 2. Defensive Runtime Config

Use the checkpoint above together with these runtime settings:

- `group_a_profile = default`
- `group_a_action_schema = triplet_v3_cash50`
- `min_rebalance_days = 5`
- `leverage_cap (00631L) = 0.20`
- `inverse_cap (00632R) = 0.30`
- `inverse_m_state_only = true`
- `inverse_max_holding_days = 5`
- `enable_pva_features = true`
- `enable_pva_sigmoid = true`
- `pva_weight = 0.32`
- `pva_j_state_weight = 0.19`
- `pva_m_state_weight = 1.00`
- `pva_drift_threshold = 0.05`
- `pva_s_state_drift_boost = 0.00`
- `pva_s_state_max_weight = 0.32`
- `pva_target_vol = 0.012`
- `pva_min_leverage_scale = 0.40`
- `pva_inverse_hedge_budget = 0.30`
- `pva_buy_dip_strength = 0.95`
- `group_a_enable_dca = true`
- `dca_day = 20`
- `dca_0050 = 5000`
- `group_a_enable_llm_sentiment = true`
- `sentiment_positive_leverage_boost = 0.00`

## 3. Optimization Reference

Cap-0.20 baseline before re-optimization, from [`results/group_a_runtime_reopt_cap20_20260524.json`](results/group_a_runtime_reopt_cap20_20260524.json):

- Backtest window:
  - `2024-01-02` to `2026-05-21`
- Baseline final value:
  - `3,668,019.31`
- Baseline Sharpe:
  - `2.440007`
- Baseline max drawdown:
  - `-20.3202%`
- Trades:
  - `99`

Final selected cap-0.20 runtime candidate, from [`results/group_a_runtime_reopt_cap20_focused_20260524.json`](results/group_a_runtime_reopt_cap20_focused_20260524.json) and confirmed unchanged by [`results/group_a_runtime_reopt_cap20_micro_20260524.json`](results/group_a_runtime_reopt_cap20_micro_20260524.json):

- Final value:
  - `3,682,144.74`
- Sharpe:
  - `2.452252`
- Max drawdown:
  - `-20.0003%`
- Trades:
  - `99`
- Delta final value:
  - `+14,125.43`
- Delta Sharpe:
  - `+0.012245`
- Delta max drawdown:
  - Improved by about `+0.3199 pp`
- Best confirmed overrides:
  - `pva_weight = 0.32`
  - `pva_j_state_weight = 0.19`
  - `pva_drift_threshold = 0.05`
  - `pva_min_leverage_scale = 0.40`
- `pva_buy_dip_strength = 0.95`
- `dca_day = 20`

Interpretation:

- Lowering leverage cap to `0.20` does not by itself define the best defensive profile.
- A second-stage runtime re-opt recovered part of the recent-window performance while still improving drawdown.
- `pva_s_state_max_weight` is recorded as `0.32` here because the environment clamps it to at least `pva_weight`; keeping `0.30` in the payload would still execute as `0.32`.
- The final micro pass did not beat the focused-pass winner, so the selected values above are stable within the tested neighborhood.

## 4. 2008 Proxy Reference

The dual-objective comparison in [`results/group_a_leverage_cap_dual_objective_20260524.json`](results/group_a_leverage_cap_dual_objective_20260524.json) established that `cap=0.20` is the better crash-defense baseline, while `cap=0.30` remains the better recent-return production baseline.

After the cap-0.20 re-optimization, the final TWII proxy stress result in [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json) is:

- Proxy window:
  - `2007-07-02` to `2010-12-31`
- Final value:
  - `1,525,036.08`
- Sharpe:
  - `0.539510`
- Max drawdown:
  - `-50.4417%`
- Trades:
  - `147`
- PVA hits:
  - `86`
- DCA purchases:
  - `42`
- DCA total:
  - `210,000`

Delta vs the unoptimized cap-0.20 crash baseline from the dual-objective comparison:

- Final value:
  - `+3,998.93`
- Sharpe:
  - `+0.003577`
- Max drawdown:
  - Improved by about `+0.2144 pp`

Delta vs the cap-0.30 production profile on the same 2008 proxy path:

- Final value:
  - `+85,471.43`
- Sharpe:
  - `+0.085750`
- Max drawdown:
  - Improved by about `+3.7339 pp`

Interpretation:

- The re-optimized cap-0.20 payload remains clearly better than cap `0.30` on the 2008-style crash path.
- The extra runtime tuning on top of cap `0.20` is incremental rather than transformational, but it is still directionally positive on both recent and crash windows.

## 5. Operational Snapshot

Defensive signal snapshot from [`results/group_a_signal_defensive_cap20_asof_20260521.json`](results/group_a_signal_defensive_cap20_asof_20260521.json):

- Requested / actual date:
  - `2026-05-21`
- Signal status:
  - `hold`
- Reason:
  - `cooldown_2d`
- Current action label:
  - `rebalance_to_0050_70_00631L_30`
- Candidate weights:
  - `0050 88.3% / 00631L 11.7%`
- Effective replay weights:
  - `0050 50.2% / 00631L 20.4% / cash 29.4%`
- PVA state:
  - `J`
- PVA state weight:
  - `0.19`
- Strategy replay value:
  - `3,682,144.74`
- Relative vs 0050 buy-and-hold:
  - `+29.56%`

## 6. Commands

To reproduce the defensive signal snapshot:

```bash
python3 generate_dual_group_signal.py \
  --group group_a \
  --result-json results/group_a_runtime_payload_defensive_cap20_20260524.json \
  --download-end 2026-05-22 \
  --as-of-date 2026-05-21
```

To reproduce the defensive 2008 proxy stress test:

```bash
python3 backtest_group_a_twii_proxy_2008.py \
  --payload results/group_a_runtime_payload_defensive_cap20_20260524.json \
  --start 2007-07-01 \
  --end 2010-12-31
```

## 7. Recheck Status

Independent recheck on 2026-05-24 confirmed that the current defensive payload reproduces the expected outputs without drift:

- Recent-window replay smoke from [`results/group_a_runtime_smoke_defensive_cap20_20260524.json`](results/group_a_runtime_smoke_defensive_cap20_20260524.json):
  - `final_value = 3,682,144.74`
  - `sharpe = 2.452252`
  - `max_drawdown = -20.0003%`
  - `trades = 99`
- Signal replay stayed unchanged:
  - `hold / cooldown_2d`
  - candidate `0050 88.3% / 00631L 11.7%`
- TWII proxy crash replay stayed unchanged:
  - `final_value = 1,525,036.08`
  - `sharpe = 0.539510`
  - `max_drawdown = -50.4417%`
