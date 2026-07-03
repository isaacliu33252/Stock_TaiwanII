# Group A+ BB Features & NCF Retrain 交接記錄
**日期：2026-06-30**
**涵蓋：2026-06-29 ~ 2026-06-30 工作**

---

## 1. 本次工作摘要

本次在 stockpredictionai 分析基礎上，為 NCF 模型加入 **Bollinger Band 外部特徵**，並完成 **NCF 重新訓練**與**回測驗證**。

---

## 2. 新增特徵（`scripts/misc/ncf_00631l.py`）

### 2.1 EXT_FEATURES（外部特徵，第 166-167 行）

```python
"eti0050_bb_pct",    # 0050 Bollinger Band %B (0-1 percentile, 20-day)
"eti0050_bb_width",  # 0050 Bollinger Band width (2*std/ma20)
```

**計算邏輯（`load_external_df()`，第 315-321 行）：**

```python
_et50_ma20  = et50_s.rolling(20).mean()
_et50_std20 = et50_s.rolling(20).std()
_bb_upper   = _et50_ma20 + 2 * _et50_std20
_bb_lower   = _et50_ma20 - 2 * _et50_std20
_bb_range   = (_bb_upper - _bb_lower).clip(lower=1e-10)
ext["eti0050_bb_pct"]   = _align((et50_s - _bb_lower) / _bb_range, shift_n=0)
ext["eti0050_bb_width"] = _align((2 * _et50_std20) / _et50_ma20, shift_n=0)
```

| 特徵 | 說明 | 典型範圍 |
|------|------|---------|
| `eti0050_bb_pct` | 0050 在布林通道的 0-1 位置 (>0.8=過熱, <0.2=超賣) | [-0.28, 1.29] |
| `eti0050_bb_width` | 布林通道寬度，波動率代理 | [0.009, 0.135] |

### 2.2 INTERACTION_FEATURES（互動特徵，第 229 行）

```python
"bb0050_x_vix",   # 0050 BB overbought × VIX spike
```

**計算邏輯（`_add_interaction_features()`，第 665-666 行）：**

```python
if {"eti0050_bb_pct", "vix_ma20_ratio"} <= set(df.columns):
    df["bb0050_x_vix"] = df["eti0050_bb_pct"] * (df["vix_ma20_ratio"] - 1.0)
```

**經濟意義**：`eti0050_bb_pct` 接近 1（上軌）且 VIX 相對 MA20 飆升時，`bb0050_x_vix` 為大正值，代表「0050 過熱 + 恐慌升溫」→ 晚期多頭最強看空組合信號。

---

## 3. Bayesian Optimization（Optuna）

### 3.1 現況

`scripts/misc/ncf_optuna_tune.py` 已完整實作，可直接執行。
`results/ncf_optuna_best_params.json` 現存版本是 **99 特徵**（2026-06-26 跑的舊版）。

### 3.2 待辦：用新特徵重跑

```bash
# 約 30-60 分鐘
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py \
  --trials 75 --horizon 20
```

完成後再重訓 NCF：

```bash
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2020-01-01 --val-start 2025-01-02 \
  --full-panel \
  --val-predictions-output results/ncf_00631l_v5_tabnet_panel.csv \
  --optuna-params results/ncf_optuna_best_params.json
```

---

## 4. NCF 重訓結果（2026-06-30 08:15）

### 4.1 模型指標對比

| 指標 | 舊模型（99 特徵） | 新模型（107 特徵） | 變化 |
|------|-----------------|-----------------|------|
| H=1 AUC | 0.57 | **0.5813** | +0.011 |
| H=5 AUC | 0.63 | **0.6878** | +0.058 |
| H=20 AUC | 0.70 | **0.7078** | +0.008 |

### 4.2 回測指標對比（2025-01-02 ~ 2026-06-18，a2118 策略）

| 指標 | 舊模型 | 新模型 | 變化 |
|------|--------|--------|------|
| Sharpe | 2.6484 | 2.6032 | -0.045 |
| Sortino | 2.9500 | 2.9026 | -0.047 |
| 年化報酬 | 66.02% | **70.62%** | **+4.6pp** |
| MDD | -13.82% | -13.82% | 持平 |
| 最終資產 | 2,092,482 | **2,177,429** | **+84,947** |
| late-bull 觸發次數 | 2 | 0 | 新模型看多，不觸發避險 |

**觸發次數 0 的含義**：新模型在 2026-02-23 和 2026-04-30 兩個歷史觸發點，H20 prob > 0.33 或 conf < 0.55，因此不觸發 hard overlay。這代表新 BB 特徵讓模型在那兩個時點更偏看多——實際是否比舊模型正確，需等 OOS 累積更多樣本確認。

### 4.3 關鍵檔案

| 檔案 | 更新時間 | 內容 |
|------|---------|------|
| `results/ncf_00631l_v5_tabnet_panel.csv` | 2026-06-30 08:33 | 107 特徵 panel（2025-01-02 ~ 2026-06-29）|
| `results/ncf_00631l_20260630.json` | 2026-06-30 08:15 | 今日 live 預測 JSON |

---

## 5. 今日 Live Signal（2026-06-30）

**資料日期**：2026-06-29（最新收盤）

### 5.1 NCF 00631L 預測

| 指標 | 數值 |
|------|------|
| 方向 | **DOWN** |
| calibrated_prob_up | 0.3846 |
| H=1 AUC/prob | 0.5813 / 0.4618 |
| H=5 AUC/prob | 0.6878 / 0.3808 |
| H=20 AUC/prob | 0.7078 / **0.2423** |
| confidence | **0.6498** |
| gain_prob (>5% in 20d) | 0.374 |
| mdd_prob (>5% DD in 20d) | **0.542** |
| tail_reward_risk_score | **-0.168**（負值=風險>報酬）|

### 5.2 A2118 Trigger 狀態

| 條件 | 數值 | 結果 |
|------|------|------|
| MA gap > 10% | 19.5% | ✓ |
| H20 prob < 0.33 | 0.242 | ✓ |
| confidence > 0.55 | 0.650 | ✓ |
| **Hard Overlay 觸發** | | **✓ YES** |

### 5.3 今日執行配置

| 標的 | 配置 |
|------|------|
| 0050.TW | 74.7% |
| **00631L.TW** | **5.3%**（hard hedge，降槓）|
| 00632R.TW | 0.0% |
| cash | 20.0% |

---

## 6. A2120 Shadow Candidate 現況

**a2120**（3-tier rally-aware gate）在 a2118 基礎上加入：
- `gain_prob < 0.30` → hard hedge（同 a2118）
- `0.30 ≤ gain_prob < 0.50` → soft hedge（intensity=0.25）
- `gain_prob ≥ 0.50` → **suppress**（不降槓）

今日 `gain_prob = 0.374`（在 [0.30, 0.50)）→ a2120 會**改為 soft hedge**，而非 a2118 的 hard hedge。

**升級條件**：累積 ≥ 5 次初始觸發後，比較 a2118 vs a2120 實際表現再決定。

---

## 7. 待辦清單

| 優先 | 事項 | 說明 |
|------|------|------|
| 高 | Optuna 重跑（107 特徵）| 現有 `ncf_optuna_best_params.json` 是 99 特徵舊版 |
| 中 | 用 Optuna 結果重訓 NCF | 預期進一步提升 AUC |
| 中 | 累積 a2120 觸發樣本 | 目前僅 2 次觸發（新模型 0 次），需 ≥5 次 |
| 低 | `confidence` live row 缺值修正 | panel CSV 的 is_live=True row 無 confidence，但 NCF JSON 有，live signal 正常運作 |

---

## 8. 目前策略版本

```
active:   a2118_a2111_ncf_late_bull_deleverage
shadow:   a2120_a2111_ncf_late_bull_rally_aware
ncf:      v5_tabnet（107 特徵，含 BB）
panel:    results/ncf_00631l_v5_tabnet_panel.csv（2026-06-30 更新）
```

---

## 9. 測試狀態

```
79 passed, 0 failed（2026-06-30 驗證）
```

測試覆蓋：A2118 hard overlay、A2120 rally-aware 3-tier（4 個測試）、daily signal alerts、latest strategy 等。

---

*生成：Claude Sonnet 4.6 | 2026-06-30*
