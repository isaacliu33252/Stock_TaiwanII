# NCF / Group A+ 交接記錄 — 2026-06-26

<!-- CODEX-HANDOFF: generated_by=Codex; date=2026-06-26; scope=NCF DB cache, tail reward/risk, interaction features, Group A+ NCF gate research -->

**Codex 標記**：本交接記錄由 Codex 產生，涵蓋 2026-06-26 NCF / Group A+ 研究與實作交接。

## 0. 核心結論

Active Group A+ 策略仍維持：

**A21.11 — `a2111_tight_entry_bond30c30`**

本輪新增 NCF DB cache、20d tail reward/risk、interaction features、hybrid selector，並完成多輪 Group A+ 回測。結論如下：

1. NCF 本身已改善，尤其 00631L v6 interaction 方向模型明顯變強。
2. NCF 可以作為 advisory / risk annotation。
3. NCF 目前仍不適合升級成 Group A+ 正式 execution gate。
4. 所有 gate / cap / hybrid selector 的共同問題是：Sharpe 可提高，但報酬犧牲過大，MDD 沒改善。
5. 下一個真正可能改善 Group A+ 的方向是 **opportunity-cost label**，直接預測「降 00631L / 切 defensive 是否會比原策略好」。

---

## 1. 版本狀態

### 已 staged

- `FinRL/data/stock_data.db`
- `ncf_external_cache.py`
- `ncf_00632r.py`
- `scripts/misc/ncf_00631l.py`

### 未加入版本的結果檔

`results/` 仍被 `.gitignore` 的 `/results/` 規則忽略。本輪所有回測輸出都保留在本機，但沒有強行 `git add -f`。

---

## 2. DB cache / 資料版本化

新增共用模組：

- `ncf_external_cache.py`

新增 DuckDB tables：

- `external_market_ohlcv`
- `external_data_version`

目前 DB 外部市場資料：

| ticker | rows | range |
|---|---:|---|
| `2330.TW` | 3038 | 2014-01-02 ~ 2026-06-26 |
| `QQQ` | 3138 | 2014-01-02 ~ 2026-06-25 |
| `SOXX` | 3138 | 2014-01-02 ~ 2026-06-25 |
| `TSM` | 3138 | 2014-01-02 ~ 2026-06-25 |
| `TWD=X` | 3250 | 2014-01-01 ~ 2026-06-26 |
| `^IXIC` | 3138 | 2014-01-02 ~ 2026-06-25 |
| `^TWII` | 3035 | 2014-01-02 ~ 2026-06-26 |
| `^VIX` | 3139 | 2014-01-02 ~ 2026-06-25 |

Total external rows：`25,014`

### 行為

NCF 現在讀 yfinance 外部特徵時：

1. 先讀 `external_market_ohlcv`
2. 若缺資料才下載
3. 下載後寫回 `external_market_ohlcv`
4. 在 `external_data_version` 紀錄 provider、ticker、range、row_count、yfinance version、purpose

已驗證：00631L / 00632R 可在無網路權限下使用 DB cache 重訓完成。

---

## 3. NCF 新增 tail reward/risk

兩支 NCF 都新增：

- `forward_drawdown_risk`
- `forward_upside_reward`
- `tail_reward_risk_score = P(20d gain > 5%) - P(20d MDD > 5%)`

Panel 新增欄位：

- `prob_fwd_mdd_gt5_h20`
- `actual_fwd_mdd_gt5_h20`
- `forward_mdd_h20`
- `prob_fwd_gain_gt5_h20`
- `actual_fwd_gain_gt5_h20`
- `forward_gain_h20`
- `tail_reward_risk_score_h20`

目的：避免只用 downside risk 錯殺「風險高但報酬也高」的 00631L 多頭段。

---

## 4. NCF v5 — DB cache baseline

輸出：

- `results/ncf_00631l_20260626_dbcache.json`
- `results/ncf_00631l_panel_2025_v5_dbcache.csv`
- `results/ncf_00632r_20260626_dbcache.json`
- `results/ncf_00632r_panel_2025_v5_dbcache.csv`

### 00631L v5

| item | value |
|---|---:|
| Horizon ensemble | DOWN |
| combined prob up | 0.4722 |
| confidence | 0.3834 |
| weighted return | -0.9913% |
| H1 AUC | 0.5653 |
| H5 AUC | 0.6441 |
| H20 AUC | 0.5876 |
| downside prob | 0.6583 |
| downside AUC | 0.6280 |
| upside prob | 0.2969 |
| upside AUC | 0.6199 |
| tail score | -0.3614 |

### 00632R v5

| item | value |
|---|---:|
| Horizon ensemble | UP |
| combined prob up | 0.7384 |
| confidence | 0.5331 |
| weighted return | -1.3573% |
| H1 AUC | 0.5418 |
| H5 AUC | 0.6378 |
| H20 AUC | 0.8040 |
| downside prob | 0.3791 |
| downside AUC | 0.5963 |
| upside prob | 0.5403 |
| upside AUC | 0.6432 |
| tail score | 0.1612 |

---

## 5. NCF v6 — interaction features

新增 interaction features。

### 00631L 新增 16 個

- `vol20_x_bb_width`
- `vol20_x_close_ma200_dist`
- `momentum21_x_above_ma200`
- `return5_x_vol20`
- `rsi14_x_close_ma50_dist`
- `vix_spike_x_vol20`
- `vix_change_x_return1d`
- `qqq5d_x_momentum21`
- `twii5d_x_close_ma200_dist`
- `twii_ret_x_return1d`
- `tsmc0050spread_x_momentum5`
- `usdtwd_x_vix_change`
- `tx_night_x_gap`
- `foreign_x_margin_chg`
- `inst_total_x_short_chg`
- `margin_short_x_rsi14`

### 00632R 新增 19 個

包含 00631L 的 16 個，再加：

- `eti0050_gap_x_momentum21`
- `eti0050_gap_x_vix_spike`
- `eti0050_10d_x_return5`

### NaN 修正

00632R 初次重訓時 ElasticNet 遇到 interaction 欄位 NaN。已修正：

```python
interaction_cols = [f for f in INTERACTION_FEATURES if f in X.columns]
X[interaction_cols] = X[interaction_cols].fillna(0.0)
```

此修正同時套用在 00631L / 00632R 的 `build_dataset()` 與 `build_feature_matrix()`。

---

## 6. NCF v6 重訓結果

輸出：

- `results/ncf_00631l_20260626_interactions.json`
- `results/ncf_00631l_panel_2025_v6_interactions.csv`
- `results/ncf_00632r_20260626_interactions.json`
- `results/ncf_00632r_panel_2025_v6_interactions.csv`

### 00631L v5 -> v6

| metric | v5 | v6 | delta |
|---|---:|---:|---:|
| H1 AUC | 0.5653 | 0.5848 | +0.0195 |
| H5 AUC | 0.6441 | 0.6747 | +0.0306 |
| H20 AUC | 0.5876 | 0.5899 | +0.0023 |
| confidence | 0.3834 | 0.6598 | +0.2764 |
| combined prob up | 0.4722 | 0.3821 | more bearish |
| weighted return | -0.9913% | -0.8964% | slight improvement |
| downside AUC | 0.6280 | 0.6291 | +0.0010 |
| upside AUC | 0.6199 | 0.6315 | +0.0115 |
| tail score | -0.3614 | -0.3828 | more negative |

Conclusion：00631L v6 明顯優於 v5，尤其 H1/H5 direction 與 confidence。

### 00632R v5 -> v6

| metric | v5 | v6 | delta |
|---|---:|---:|---:|
| H1 AUC | 0.5418 | 0.5418 | 0 |
| H5 AUC | 0.6378 | 0.6103 | -0.0275 |
| H20 AUC | 0.8040 | 0.8092 | +0.0052 |
| confidence | 0.5331 | 0.5476 | +0.0145 |
| combined prob up | 0.7384 | 0.7217 | slightly lower |
| weighted return | -1.3573% | -0.8707% | improved |
| downside AUC | 0.5963 | 0.5991 | +0.0027 |
| upside AUC | 0.6432 | 0.6166 | -0.0267 |
| tail score | 0.1612 | 0.0138 | much weaker |

Conclusion：00632R 不適合全量升 v6。v6 只適合 H20 direction，tail reward/risk 應保留 v5。

---

## 7. Group A+ 回測：20d MDD >5% downside gate

最初版本只使用 `P(20d MDD > 5%)`。

輸出：

- `results/group_a_plus_a2115_mdd_gate_sweep_20260626.csv`
- `results/group_a_plus_a2115_mdd_gate_20260626.json`
- `results/group_a_plus_a2115_mdd_gate_20260626_frame.csv`

### 結果

Base A21.11：

| metric | value |
|---|---:|
| total return | +133.64% |
| Sharpe | 2.5208 |
| MDD | -13.92% |

最佳 Sharpe downside gate：

| metric | value |
|---|---:|
| total return | +102.80% |
| Sharpe | 2.8483 |
| MDD | -13.92% |
| ret delta | -30.84pp |

結論：Sharpe 提升，但報酬犧牲過大，MDD 沒改善。不升格。

---

## 8. Group A+ 回測：20d MDD >5% sizing cap

測試：在 golden1 中，NCF 風險高時只降低 00631L 權重上限，不切 defensive。

輸出：

- `results/group_a_plus_a2115_mdd_sizing_sweep_20260626.csv`
- `results/group_a_plus_a2115_mdd_sizing_20260626.json`
- `results/group_a_plus_a2115_mdd_sizing_20260626_frame.csv`

最佳低損耗版本：

| config | value |
|---|---|
| risk631 | >= 0.65 |
| risk632 | <= 0.45 |
| ma_gap | <= 10% |
| consecutive | 2 days |
| 00631L cap | 15% |

| metric | value |
|---|---:|
| total return | +130.60% |
| Sharpe | 2.5093 |
| MDD | -13.92% |
| ret delta | -3.05pp |
| Sharpe delta | -0.0115 |
| worst 20d improve | +0.13pp |

結論：比 defensive gate 溫和，但 Sharpe 沒改善，MDD 沒改善。不升格。

---

## 9. Group A+ 回測：A21.16 tail reward/risk score

使用：

```text
tail_reward_risk_score_h20 = P(20d gain > 5%) - P(20d MDD > 5%)
```

輸出：

- `results/group_a_plus_a2116_tail_score_sweep_20260626.csv`
- `results/group_a_plus_a2116_tail_score_20260626.json`
- `results/group_a_plus_a2116_tail_score_20260626_frame.csv`

最佳 Sharpe：

| metric | A21.11 | A21.16 |
|---|---:|---:|
| total return | +133.64% | +122.50% |
| Sharpe | 2.5208 | 2.8189 |
| MDD | -13.92% | -13.92% |
| worst 20d | -9.66% | -9.47% |

| delta | value |
|---|---:|
| ret delta | -11.14pp |
| Sharpe delta | +0.2981 |
| MDD improve | 0 |
| worst20 improve | +0.20pp |

Best config：

```json
{
  "kind": "defensive",
  "thr631": -0.4,
  "thr632": 0.1,
  "ma_gap_max": 999.0,
  "consecutive": 1
}
```

Events：

- 2026-02-26 defensive ON
- 2026-03-04 defensive OFF
- 2026-05-04 defensive ON

結論：Sharpe 提升，但報酬少 11.14pp，MDD 沒改善。不升格。

---

## 10. NCF hybrid selector

Profile：

- `00631L`: v6 interactions for direction + tail
- `00632R`: v6 interactions for H20 direction, v5 dbcache for tail

輸出：

- `results/ncf_hybrid_profile_20260626.json`
- `results/ncf_hybrid_panel_2025_20260626.csv`
- `results/group_a_plus_a2117_ncf_hybrid_sweep_20260626.csv`
- `results/group_a_plus_a2117_ncf_hybrid_20260626.json`
- `results/group_a_plus_a2117_ncf_hybrid_20260626_frame.csv`

### Hybrid current signals

| ticker | signal |
|---|---|
| 00631L | DOWN |
| 00631L prob up | 0.3821 |
| 00631L confidence | 0.6598 |
| 00631L tail score | -0.3828 |
| 00632R | UP |
| 00632R prob up | 0.7217 |
| 00632R confidence | 0.5476 |
| 00632R H20 AUC | 0.8092 |
| 00632R tail score | 0.1612 |

### A21.17 回測結果

| metric | A21.11 | A21.17 hybrid |
|---|---:|---:|
| total return | +133.64% | +122.50% |
| Sharpe | 2.5208 | 2.8189 |
| MDD | -13.92% | -13.92% |
| worst 20d | -9.66% | -9.47% |

| delta | value |
|---|---:|
| ret delta | -11.14pp |
| Sharpe delta | +0.2981 |
| MDD improve | 0 |
| worst20 improve | +0.20pp |

Best config：

```json
{
  "kind": "defensive",
  "thr631": -0.5,
  "thr632_tail": 0.0,
  "thr632_h20": 0.65,
  "ma_gap_max": 999.0,
  "consecutive": 1
}
```

Events：

- 2026-02-26 defensive ON
  - score631 = -0.6012
  - score632 = 0.1068
  - h20_632 = 0.6919
  - ma_gap = 0.2352
- 2026-03-04 defensive OFF
- 2026-05-04 defensive ON
  - score631 = -0.6679
  - score632 = 0.2473
  - h20_632 = 0.7803
  - ma_gap = 0.2840

### Hybrid 結論

Hybrid selector 與 A21.16 結果幾乎一致。它能提升 Sharpe，但不是靠避開主要 MDD，而是靠降低曝險；報酬犧牲仍太大。

沒有找到 `ret_delta >= -5%` 的有效組合。

`ma_gap <= 10%` 條件完全沒有觸發。

不升格。

---

## 11. 測試 / 驗證

本輪多次執行以下測試，最後一次結果：

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf-hybrid-final .venv/bin/python -m pytest -q \
  tests/test_group_a_plus_ncf_integration.py \
  tests/test_group_a_plus_latest_strategy.py
```

結果：

```text
28 passed
```

另外執行過：

- `py_compile scripts/misc/ncf_00631l.py ncf_00632r.py`
- feature matrix smoke test
- DB cache smoke test
- DB external table row count check

---

## 12. 目前建議

### 可採用

1. 保留 NCF DB cache / data versioning。
2. 保留 NCF tail reward/risk 輸出。
3. 00631L 可以採 v6 interaction 作為 current advisory signal。
4. 00632R 可採 hybrid：
   - H20 direction 用 v6
   - tail reward/risk 用 v5

### 不建議

1. 不建議把 NCF downside gate 升為正式 Group A+ execution gate。
2. 不建議把 tail score defensive gate 升為正式策略。
3. 不建議在 golden1 中用 NCF 大幅降 00631L，除非有新的 opportunity-cost label 支持。

---

## 13. 下一步建議

### Priority 1 — Opportunity-cost label

目前所有 NCF gate 的問題都是「會降低曝險，但不一定提高策略效用」。下一步應直接訓練：

- `cap_00631l_15pct_beats_base_next20d`
- `defensive_beats_base_next20d`
- `cash_or_bond_beats_00631l_next20d`
- `00632r_overlay_compensates_00631l_cut_next20d`

這比繼續預測 `MDD > 5%` 更接近 Group A+ 實際決策。

### Priority 2 — Regime-specific calibration

分 regime 校準 NCF probability：

- bull
- late bull / high `ma_gap`
- bear
- near MA100 / near MA200

尤其 00631L 在 `ma_gap > 20%` 時，risk 高不代表該降槓桿。

### Priority 3 — Multi-year purged walk-forward panel

目前 panel 主要是 2025-2026 validation。應產生：

- train <= 2021, val 2022
- train <= 2022, val 2023
- train <= 2023, val 2024
- train <= 2024, val 2025
- train <= 2025, val 2026

確認 v6 interaction 是否跨年度穩定。

---

## 14. 常用重跑命令

### 00631L v6 interaction

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf-interactions-train PYTHONPATH=. \
.venv/bin/python scripts/misc/ncf_00631l.py \
  --val-start 2025-01-02 \
  --val-predictions-output results/ncf_00631l_panel_2025_v6_interactions.csv \
  --output results/ncf_00631l_20260626_interactions.json
```

### 00632R v6 interaction

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf-interactions-train PYTHONPATH=. \
.venv/bin/python ncf_00632r.py \
  --val-start 2025-01-02 \
  --val-predictions-output results/ncf_00632r_panel_2025_v6_interactions.csv \
  --output results/ncf_00632r_20260626_interactions.json
```

### 最小測試

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf-final .venv/bin/python -m pytest -q \
  tests/test_group_a_plus_ncf_integration.py \
  tests/test_group_a_plus_latest_strategy.py
```
