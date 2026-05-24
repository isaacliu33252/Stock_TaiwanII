# Group A Latest Handoff

Date: 2026-05-24
Status: Primary Group A runtime payload and signal snapshot
Scope: Group A only

## 1. Source Of Truth

This handoff supersedes both the earlier `cap=0.30` release reference and the separate defensive-profile note. As of 2026-05-24, the primary Group A profile is the re-optimized `cap=0.20` version.

Current source of truth:

- Best checkpoint:
  - [`models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`](models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip)
- Historical cap-0.30 payload retained for comparison:
  - [`results/group_a_runtime_payload_opt_20260524.json`](results/group_a_runtime_payload_opt_20260524.json)
- Primary runtime payload for signal generation:
  - [`results/group_a_runtime_payload_primary_20260524.json`](results/group_a_runtime_payload_primary_20260524.json)
- Primary signal snapshot:
  - [`results/group_a_signal_primary_asof_20260521.json`](results/group_a_signal_primary_asof_20260521.json)
  - [`results/group_a_signal_primary_asof_20260521.csv`](results/group_a_signal_primary_asof_20260521.csv)
- Primary recent-window replay:
  - [`results/group_a_backtest_20240102_20260522_defensive_cap20_20260524_233939.json`](results/group_a_backtest_20240102_20260522_defensive_cap20_20260524_233939.json)
- Crash-defense evidence:
  - [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json)
- Cap-0.20 optimization evidence:
  - [`results/group_a_runtime_reopt_cap20_20260524.json`](results/group_a_runtime_reopt_cap20_20260524.json)
  - [`results/group_a_runtime_reopt_cap20_focused_20260524.json`](results/group_a_runtime_reopt_cap20_focused_20260524.json)
  - [`results/group_a_runtime_reopt_cap20_micro_20260524.json`](results/group_a_runtime_reopt_cap20_micro_20260524.json)
  - [`results/group_a_runtime_micro_primary_20260524.json`](results/group_a_runtime_micro_primary_20260524.json)

Important:

- No retraining was performed.
- The checkpoint is unchanged.
- The main profile now favors lower drawdown and better crash behavior over maximum recent-window final value.
- `dca_day` remains `20`.

## 2. Primary Runtime Config

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

## 3. Performance Reference

Primary recent-window replay from [`results/group_a_backtest_20240102_20260522_defensive_cap20_20260524_233939.json`](results/group_a_backtest_20240102_20260522_defensive_cap20_20260524_233939.json):

- Requested backtest window:
  - `2024-01-02` to `2026-05-22`
- Actual replay window:
  - `2024-01-02` to `2026-05-21`
- Final value:
  - `3,682,144.74`
- Annual return:
  - `77.4050%`
- Sharpe:
  - `2.452252`
- Max drawdown:
  - `-20.0003%`
- Trades:
  - `99`
- DCA total:
  - `145,000`

Comparison vs the historical cap-0.30 canonical replay [`results/group_a_backtest_20240102_20260522_canonical_20260524_233602.json`](results/group_a_backtest_20240102_20260522_canonical_20260524_233602.json):

- Final value:
  - `-187,054.05`
- Annual return:
  - `-3.9085 pp`
- Sharpe:
  - `+0.04450`
- Max drawdown:
  - Improved by about `+2.0363 pp`
- Trades:
  - Unchanged

Interpretation:

- `cap=0.30` still wins on absolute final value.
- `cap=0.20` now serves as the main profile because it materially reduces drawdown while slightly improving Sharpe and preserving the same trade count.
- A focused local micro-sweep around the promoted primary payload found no better candidate, so the current `0.32 / 0.19 / 0.40 / 0.95 / dca_day=20` setting remains the local optimum inside the tested neighborhood.

## 4. Crash Reference

Primary 2008-style TWII proxy stress result from [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json):

- Proxy window:
  - `2007-07-02` to `2010-12-31`
- Final value:
  - `1,525,036.08`
- Sharpe:
  - `0.539510`
- Max drawdown:
  - `-50.4417%`

Delta vs the cap-0.30 profile on the same proxy path:

- Final value:
  - `+85,471.43`
- Sharpe:
  - `+0.085750`
- Max drawdown:
  - Improved by about `+3.7339 pp`

## 5. Operational Snapshot

Primary signal snapshot from [`results/group_a_signal_primary_asof_20260521.json`](results/group_a_signal_primary_asof_20260521.json):

- Requested / actual date:
  - `2026-05-21`
- Signal status:
  - `hold`
- Reason:
  - `cooldown_2d`
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

## 6. Commands

To reproduce the primary signal snapshot:

```bash
python3 generate_dual_group_signal.py \
  --group group_a \
  --result-json results/group_a_runtime_payload_primary_20260524.json \
  --download-end 2026-05-22 \
  --as-of-date 2026-05-21
```

To reproduce the primary 2008 proxy stress test:

```bash
python3 backtest_group_a_twii_proxy_2008.py \
  --payload results/group_a_runtime_payload_primary_20260524.json \
  --start 2007-07-01 \
  --end 2010-12-31
```
