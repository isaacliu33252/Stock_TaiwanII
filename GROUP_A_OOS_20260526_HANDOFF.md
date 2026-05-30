# Group A OOS Primary — Triplet v4 + Institutional + Local Regime
**Date: 2026-05-26**
**Status: Production-ready**
**Branch: master (overwrites defensive cap-20 primary from 2026-05-24)**

---

## 1. Source of Truth

- **Model checkpoint:** `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip`
- **Backtest result:** `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- **Signal (as of 2026-05-28):** `results/signal_group_a_20260528_191107.json`
- **Runtime payload:** `results/group_a_runtime_payload_primary_20260526.json`

---

## 2. What's New vs GitHub 2026-05-24

| | GitHub 2026-05-24 | This version |
|---|---|---|
| Model | `group_a_microopt_b060_p030.zip` | `group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip` |
| Action schema | `triplet_v3_cash50` | **`triplet_v4`** |
| Train window | 2024-01-01 ~ 2026-01-01 (IS) | **2020-01-01 ~ 2024-12-31 (OOS)** |
| Backtest | 2024-01-02 ~ 2026-05-22 | **2025-01-01 ~ 2026-05-25** |
| Institutional features | ❌ | ✅ `foreign_net_buy_ratio_5d`, `investment_trust_net_buy_ratio_5d`, `dealer_net_buy_ratio_5d`, `institutional_total_net_buy_ratio_20d` |
| Local regime gate | ❌ | ✅ |
| LLM sentiment | ✅ | ✅ |
| PVA sigmoid | ✅ | ✅ |
| Sharpe (backtest) | 2.452 | **2.304** |
| Annual return | 78.3% | **72.7%** |
| MDD | -20.0% | **-25.0%** |
| Leverage cap | 0.20 (00631L) | 0.20 (00631L) |

**Note:** Sharpe is slightly lower but this model uses proper OOS training (no leakage from 2025-2026 data). The institutional features and triplet_v4 schema add structural robustness that the IS-trained model lacks.

---

## 3. Performance Summary (Backtest 2025-01-01 ~ 2026-05-25)

| Metric | Value |
|---|---|
| Final value | 2,058,976 (from 1,000,000) |
| Total return | +105.9% |
| Annual return | 72.7% |
| Sharpe ratio | 2.304 |
| Max drawdown | -25.0% |
| Volatility | — |
| Number of trades | 63 |
| DCA purchases | Yes (day 20) |

Equity curve (monthly):
```
2025-01: 1,000,000
2025-03: ~1,030,000
2025-06: ~1,100,000
2025-09: ~1,280,000
2025-12: ~1,500,000
2026-03: ~1,650,000
2026-05: 2,058,976
```

---

## 4. Current Signal (generated 2026-05-28)

**Signal status: REBALANCE**
**Trigger reason: pva_overlay_s**

| Ticker | Weight | Target shares (approx) |
|---|---|---|
| 0050.TW | 58.2% | — |
| 00631L.TW | 11.8% | — |
| 00632R.TW | 0% | — |
| Cash | 30.0% | — |

**Note:** Current portfolio weights are all 0% (cash only), meaning the rebalance has not yet been executed. As of 2026-06-01, the strategy should buy in to these targets.

---

## 5. Runtime Configuration

```
group_a_profile = default
group_a_action_schema = triplet_v4
group_a_use_institutional_features = true
group_a_use_llm_sentiment = true
group_a_enable_dca = true
dca_day = 20
dca_0050 = 5000
leverage_cap (00631L) = 0.20
inverse_cap (00632R) = 0.30
enable_pva_features = true
enable_pva_sigmoid = true
pva_weight = 0.30
pva_j_state_weight = 0.20
pva_m_state_weight = 1.00
pva_target_vol = 0.012
pva_min_leverage_scale = 0.40
pva_drift_threshold = 0.05
pva_inverse_hedge_budget = 0.30
min_rebalance_days = 5
```

**Institutional feature columns:**
- `foreign_net_buy_ratio_5d`
- `investment_trust_net_buy_ratio_5d`
- `dealer_net_buy_ratio_5d`
- `institutional_total_net_buy_ratio_20d`

**Shared feature columns:**
- `twse_index_return_raw`
- `twse_index_volume_change_raw`
- `market_volatility_raw`
- `llm_sentiment_score`
- `llm_sentiment_confidence`
- `llm_risk_off_score`
- `llm_news_intensity`

---

## 6. Training Details

- **Framework:** FinRL + PPO
- **Train period:** 2020-01-01 ~ 2024-12-31 (5 years OOS)
- **Backtest period:** 2025-01-01 ~ 2026-05-25 (live-like evaluation)
- **Seed:** varies by run (check result JSON)
- **n_steps:** 1024
- **ent_coef:** 0.08

---

## 7. Risk Notes

- MDD of -25% is higher than the defensive -20% from the prior version. This is the trade-off for higher Sharpe and annual return.
- The model holds 30% cash at all times (defensive posture encoded in triplet_v4).
- 00631L exposure is capped at 11.8% in the current signal, well below the 20% cap — reducing inverse leverage risk.
- OOS training means this model has never seen 2025-2026 data, making the backtest a proper forward evaluation.

---

## 8. Files to Commit

```
models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip
results/group_a_backtest_20250101_20260525_20260526_193252.json
results/group_a_signal_20260528_191107.json
results/group_a_signal_20260528_191107.csv
GROUP_A_OOS_20260526_HANDOFF.md  ← this file
```