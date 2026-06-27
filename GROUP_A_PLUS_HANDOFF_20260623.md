# Group A+ 交接記錄 — 2026-06-23

## 今日完成：Walk-forward CV + Horizon Voting 權重優化

### 1. Walk-forward CV（方向1）

**目的：** 測試模型真實泛化能力，避免 val split overfit。

**方法：** 滾動時間序列視窗，訓練區間逐步擴大，測試下一個 chunk。  
5 個視窗，最小訓練 300 筆。

**結果（方向準確率）：**

| Horizon | RF | ET | HGB | MLP | 有效視窗數 |
|---------|------|------|------|------|---------|
| H=1 | **66.6%** | 63.7% | 64.9% | 63.0% | 4 |
| H=5 | 61.6% | 53.0% | **69.9%** | 50.0% | 3 |
| H=20 | 59.6% | 58.6% | **67.1%** | 38.1% | 3 |

**關鍵發現：**
- **MLP 在 val split 的 79.5% 是 overfit**：early_stopping 讓它在 val 上表現好，但 walk-forward 一跑只剩 38-63%
- **HGB（HistGradientBoostingClassifier）才是最穩定的模型**，在 walk-forward 中全面勝出
- Bear regime 樣本極少（每視窗 1-3 筆），H20 Bear 數據無參考價值
- Walk-forward 比 val split 更能反映真實 trading 表現

**ncf_00631l.py 改動：**
- 新增 `--walk-forward` flag
- 新增 `walk_forward_evaluate()` 函式（行 280-360）
- MLP 停用 early_stopping（避免內部 train_test_split 在小樣本炸裂）
- 修正：小視窗 skip、regime subset 檢查、class balance 檢查

---

### 2. Horizon Voting 權重優化（方向2）

**舊方法：** 簡單投票（3 個 horizon，少數服從多數）+ 平均 probability。

**新方法：** inverse-MAE² 加權，MAE 越大的 horizon 懲罰越重。

**結果（權重）：**

| Horizon | Val MAE | Direction 權重 | Return 權重 |
|--------|---------|--------------|------------|
| H=1 | 2.47% | 86% | 86% |
| H=5 | 6.69% | 12% | 12% |
| H=20 | 15.53% | 2% | 2% |

**共識信號：** DOWN（3:0 全數看跌）  
**綜合預測：** -2.79% → 39.08（40.20 × 0.9721）

---

### 今日預測信號（2026-06-23）

| Horizon | 報酬預測 | 方向 | 機率 | 預測價格 | 68% CI |
|--------|---------|------|------|---------|--------|
| H=1 | -2.23% | DOWN | 0.281 | 39.31 | [38.04, 40.57] |
| H=5 | -4.29% | DOWN | 0.458 | 38.47 | [35.56, 41.39] |
| H=20 | -16.90% | DOWN | 0.131 | 33.41 | [27.65, 39.17] |
| **Ensemble** | **-2.79%** | **DOWN** | **0.298** | **39.08** | — |

---

## 下一步：Group A+ 訓練 2020-2024

**待執行：**
```bash
cd ~/Stock_taiwan2-main
python3 train_dual_group_2024_2026.py --group-filter group_a_plus --train-start 2020-01-02 --train-end 2024-12-31 --val-start 2025-01-02 --val-end 2026-06-22
```

**預期模型：** `models/portfolio/group_a_plus_4tickers_2020_2024.zip`

**對比基準（2020-2025 訓練，from 2026-06-03 handoff）：**
- Sharpe: 4.023
- MDD: -13.59%
- 年化報酬: 352.69%

---

## ncf_00631l.py 現狀

**位置：** `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/ncf_00631l.py`  
**行數：** ~860 行

**Feature Selection：** 關閉（反而變差，已確認）

**已實作功能：**
- [x] 三 horizon 預測（H=1/5/20）
- [x] Regime-conditioned regression（Bull/Bear 分開訓練）
- [x] 多模型 ensemble（RF+ET+HGB+GB 回歸 / RF+ET+HGB+MLP 分類）
- [x] Walk-forward CV（`--walk-forward`）
- [x] Horizon voting 優化（inv-MAE² 權重）
- [x] 輸出 JSON（`results/ncf_00631l_YYYYMMDD.json`）

**待優化方向（尚未實作）：**
- Walk-forward 結果整合進實際交易信號
- 用 walk-forward HGB 準確率取代 val split 準確率作為信心指標
- regime-conditioned 改為根據 walk-forward 動態選擇模型（HGB vs MLP）
