# Group A+ 改善 — 交接文件
**建立日期：2026-06-09**
**狀態：已暫停，等待 Isaac 確認方向**

---

## 一、最終成果（已完成驗證）

### Walk-Forward 驗證結果（同一 test 期：2025-06-01 ~ 2026-05-20）

| 模型 | 訓練期 | Train rows | Final | Sharpe | MDD | Vol |
|------|--------|-----------|-------|--------|-----|-----|
| **WF-C（Production 候選）** | **2022-01-03 ~ 2025-05-29** | **822** | **2,794,081** | **3.48** | **-16.05%** | **32.86%** |
| WF-B（Sharpe 最優） | 2021-01-04 ~ 2024-12-31 | 970 | 1,658,825 | 3.56 | -7.79% | 15.09% |
| WF-A（5年） | 2020-01-02 ~ 2024-12-31 | 1,215 | 2,059,680 | 2.95 | -15.71% | 26.96% |

### 實驗失敗記錄

| 實驗 | 結果 | 原因 |
|------|------|------|
| 訓練 2018-2024（7年） | **大幅變差**（final 1.76M vs 2.27M） | 太久遠的市場數據傷害模型 |
| 所有 TDCC overlay variants | **全部失敗**，overlay drag -13% | TDCC overlay 造成 drag |
| regime stability filter | **無效** | 機制無實質影響 |
| 延長 training 至 2025-05 | WF-C（2.79M）優於舊模型 | 近期數據更相關 |

### 核心發現

1. **Training 期越短越好**：WF-C（3.3年）>> WF-A（5年）直接證實 overfit
2. **所有 overlay 方向都失敗**：Base（無 overlay）是歷史最高
3. **2024 數據有效**：WF-C 訓練至 2025-05 包含 2024 下半年高點
4. **00631L/00632R 最早 2014-10-23**：無法做 2008 stress test

---

## 二、目前的最佳配置

### Production 模型（建議採用）

```
模型：group_a_wf_c.zip
訓練期：2022-01-03 ~ 2025-05-29（822 rows）
特點：final=2.79M，Sharpe=3.48，MDD=-16.05%
```

**Alternative（如果 Isaac 偏好低波動）：**

```
模型：group_a_wf_b.zip
訓練期：2021-01-04 ~ 2024-12-31（970 rows）
特點：Sharpe=3.56，MDD=-7.79%，但 final 只有 1.66M
```

### 對照組（歷史最佳）

```
Group A Base: final=2,268,193（2025-01-02~2026-05-20）
使用模型：group_a_seg（2020-2024 訓練）
Sharpe: 2.74
```

---

## 三、交接的關鍵檔案

### 模型檔案（已訓練完成）

```
models/portfolio/group_a_wf_c.zip   ← Production 建議用這個
models/portfolio/group_a_wf_b.zip   ← 低波動 alternative
models/portfolio/group_a_seg_2025_s05  ← 2020-2025 訓練（2.85M）
models/portfolio/group_a_seg_s05    ← 舊模型（2020-2024）
```

### 腳本

| 檔案 | 用途 |
|------|------|
| `walk_forward_validation.py` | Walk-forward 驗證腳本（3個 training 期） |
| `train_segments.py` | 主要訓練腳本（已修改 GROUP_A_TRAIN_START/END） |
| `backtest_group_a_plus_overlay.py` | Group A+ backtest 主腳本 |
| `train_group_a_extended.py` | 失敗的自定義環境訓練腳本（可刪除） |

---

## 四、train_segments.py 當前設定（已被修改）

**警告：以下設定偏離預設值，恢復預設需手動還原**

```python
# 當前設定（2026-06-09 修改）
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
GROUP_A_TRAIN_START = "2020-01-01"   # 已從 2020-01-01 改回（恢復預設）
GROUP_A_TRAIN_END = "2024-12-31"     # 已從 2025-05-31 改回（恢復預設）
GROUP_A_BASE_NAME = "group_a_seg_2025"  # 已從 group_a_seg 改為 group_a_seg_2025
SEG_TIMESTEPS = 20_000               # 已從 10_000 改為 20_000
TOTAL_SEGS = 5                       # 已從 10 改為 5
BACKTEST_START = "2025-01-01"       # 已從 2025-06-01 改回（恢復預設）

# 原始預設值（恢复方法：取消註釋並執行 patch）
# GROUP_A_TRAIN_START = "2020-01-01"
# GROUP_A_TRAIN_END = "2024-12-31"
# GROUP_A_BASE_NAME = "group_a_seg"
# SEG_TIMESTEPS = 10_000
# TOTAL_SEGS = 10
# BACKTEST_START = "2025-01-01"
```

**恢復預設方法：**

```bash
# 恢復 train_segments.py 預設設定
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main

# 恢復 Group A training 期間
sed -i 's/GROUP_A_TRAIN_START = "2020-01-01"/GROUP_A_TRAIN_START = "2020-01-01"/' train_segments.py
# （已一致，無需修改）

# 恢復 BASE_NAME
sed -i 's/GROUP_A_BASE_NAME = "group_a_seg_2025"/GROUP_A_BASE_NAME = "group_a_seg"/' train_segments.py

# 恢復訓練參數
sed -i 's/SEG_TIMESTEPS = 20_000/SEG_TIMESTEPS = 10_000/' train_segments.py
sed -i 's/TOTAL_SEGS = 5/TOTAL_SEGS = 10/' train_segments.py
```

---

## 五、尚未完成的工作

### 待確認方向

1. **Production 模型選擇**：WF-C（max final）vs WF-B（低波動/高Sharpe）
2. **是否需要 walk-forward 自動化**：每季自動重新訓練
3. **Group B 是否需要同樣優化**：目前 Group B 落後（final 1.18M vs Group A 2.79M）

### 待驗證

1. **WF-C 是否在真實 production 中維持 2.79M**：目前只是 backtest 結果
2. **WF-C 在 2015-2018 stress test 的表現**：可驗證模型在中國危機/川普貿易戰的穩健性
3. **Overlay 是否真的無效**：只有 regime_stable/minimal_dynamic/ultra_stable 測試過，沒測試過其他方向

---

## 六、數據狀態

### 可用數據範圍

| 標的 | 最早日期 | 最新日期 | 備註 |
|------|---------|---------|------|
| 0050.TW | 2009-01-02 | 2026-05-20 | DB 有完整數據 |
| 00631L.TW | 2014-10-23 | 2026-05-20 | yfinance fallback 可補 |
| 00632R.TW | 2014-10-23 | 2026-05-20 | yfinance fallback 可補 |

### 訓練期 vs 回測期不重疊確認

| 模型 | 訓練 end | Backtest start | 重疊 |
|------|---------|---------------|------|
| WF-A (2020-2024) | 2024-12-31 | 2025-06-01 | 無 |
| WF-B (2021-2024) | 2024-12-31 | 2025-06-01 | 無 |
| WF-C (2022-2025) | 2025-05-29 | 2025-06-01 | 無 |

---

## 七、快速啟動指令

### 重新跑 Walk-Forward 驗證

```bash
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main
python3 walk_forward_validation.py
```

### 重新訓練 Production 模型（WF-C）

```bash
# 修改 train_segments.py:
GROUP_A_TRAIN_START = "2022-01-01"
GROUP_A_TRAIN_END = "2025-05-31"
GROUP_A_BASE_NAME = "group_a_production"
SEG_TIMESTEPS = 20_000
TOTAL_SEGS = 5

# 執行訓練
python3 train_segments.py --group a

# 訓練完成後用新模型跑 Group A+ backtest
python3 backtest_group_a_plus_overlay.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260606_llmfilled.json \
  --dca-source results/group_a_meta_ensemble_real_backtest_20250101_20260606_llmfilled.json \
  --output results/group_a_plus_production_test.json \
  --variant base
```

### 恢復 train_segments.py 預設設定

```bash
sed -i 's/GROUP_A_BASE_NAME = "group_a_seg_2025"/GROUP_A_BASE_NAME = "group_a_seg"/' train_segments.py
sed -i 's/SEG_TIMESTEPS = 20_000/SEG_TIMESTEPS = 10_000/' train_segments.py
sed -i 's/TOTAL_SEGS = 5/TOTAL_SEGS = 10/' train_segments.py
```

---

## 八、Isaac 的溝通偏好（持續更新）

- 繁體中文回覆，不用簡體
- 喜歡直接執行，不需確認
- 單字回覆（"是"、"OK"、"做"）
- 立刻糾正錯誤（"不是"）
- 主動回報進度
- **輸出必須使用繁體中文**，MiniMax 模型傾向輸出簡體，必須主動轉換

---

*本文件為 2026-06-09 工作階段的完整交接記錄。*
*下次繼續時，請先確認 Isaac 選定的 Production 模型方向。*