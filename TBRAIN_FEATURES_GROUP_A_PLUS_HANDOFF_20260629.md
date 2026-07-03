# TBrainETF Features for GroupA+ 交接記錄 — 2026-06-29

## 1. 背景

使用者要求分析：

```text
C:\Users\isaac\Downloads\TBrainETF-master\TBrainETF-master
```

該專案是 **TBrain 台灣 ETF 價格預測競賽** 解法，README 標題為「台灣ETF價格預測競賽」。任務重點是 18 檔 ETF 的短期價格與漲跌方向預測，常見輸出為週一至週五的漲跌方向與收盤價。

原專案技術棧很舊，不適合直接搬模型：

- PyTorch 0.3.1
- TensorFlow 1.4.0 / Keras
- Jupyter notebook competition workflow
- 2018 競賽週預測格式

本次只導入其可重用的特徵與 ensemble 思路，不導入舊 LSTM/CNN 模型。

## 2. 導入內容

已導入 4 類 TBrainETF 優點：

| 項目 | 導入狀態 | 說明 |
|---|---|---|
| 多週期技術特徵 | 完成 | KDJ 多參數組與 MA/volume location |
| 法人籌碼 squash | 完成 | 提供 row-wise flow squashing helper |
| score-weighted ensemble | 完成 | 以 validation score edge 加權 scalar prediction |
| 方向 + 幅度 gate | 完成 | 檢查 probability direction 與 predicted return 是否一致 |

新增共用模組：

```text
group_a_plus/integrations/tbrain_features.py
```

主要 helper：

```python
add_tbrain_features()
add_multi_kdj_features()
add_location_features()
add_institutional_squash_features()
squash_vector()
score_weighted_ensemble()
direction_magnitude_gate()
latest_tbrain_snapshot()
```

## 3. 目前正式決策

### 00632R

**保留 TBrain features 預設啟用。**

原因：

- 多年 A/B 回測整體有改善。
- H1 最穩，5 年有 4 年改善。
- H20 平均也有小幅改善。
- 00632R 是反向 ETF，TBrain 的 price-location / KDJ 特徵對短中期反轉辨識比較有幫助。

目前 `ncf_00632r.py`：

- TBrain features 預設啟用。
- 可用 `--no-tbrain-features` 關閉。

### 00631L

**不保留預設啟用，只保留 opt-in 實驗開關。**

原因：

- 單窗格 2025-2026 回測中，H20 AUC 明顯變差。
- 多年回測平均只小幅改善，且年度不穩定。
- 最新策略非常重視 00631L H20 / late-bull 判斷，不適合讓不穩定特徵進正式預設。

目前 `scripts/misc/ncf_00631l.py`：

- TBrain features 預設關閉。
- 只有加 `--tbrain-features` 才啟用。
- 可加 `--no-tbrain-features` 明確關閉。

## 4. 修改檔案

### 新增

```text
group_a_plus/integrations/tbrain_features.py
tests/test_tbrain_features.py
TBRAIN_FEATURES_GROUP_A_PLUS_HANDOFF_20260629.md
```

### 修改

```text
scripts/misc/ncf_00631l.py
ncf_00632r.py
scripts/sweep/ncf_multiyear_wf.py
group_a_plus/integrations/ncf.py
group_a_plus/operations/daily_signal.py
tests/test_group_a_plus_ncf_integration.py
tests/test_group_a_plus_daily_signal_v2.py
```

## 5. NCF 腳本開關

### 00631L

預設不啟用 TBrain features：

```bash
.venv/bin/python scripts/misc/ncf_00631l.py \
  --no-external-features \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00631l_baseline.json
```

手動實驗啟用：

```bash
.venv/bin/python scripts/misc/ncf_00631l.py \
  --no-external-features \
  --tbrain-features \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00631l_tbrain.json
```

### 00632R

預設啟用 TBrain features：

```bash
.venv/bin/python ncf_00632r.py \
  --no-external-features \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00632r_tbrain.json
```

手動關閉：

```bash
.venv/bin/python ncf_00632r.py \
  --no-external-features \
  --no-tbrain-features \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00632r_baseline.json
```

## 6. 單窗格 A/B 回測

設定：

- Validation: `2025-01-02` 至 `2026-06-26`
- `--no-external-features`
- 目的：單獨評估 TBrain features，不混入外部市場資料。

輸出：

```text
results/ncf_ab_00631l_baseline_20260629.json
results/ncf_ab_00631l_tbrain_20260629.json
results/ncf_ab_00632r_baseline_20260629.json
results/ncf_ab_00632r_tbrain_20260629.json
results/ncf_tbrain_ab_compare_20260629.json
results/ncf_tbrain_ab_compare_20260629.csv
```

### 單窗格結果

| Ticker | Variant | H1 AUC | H5 AUC | H20 AUC | Ensemble | Prob Up | Confidence | Weighted Return |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| 00631L | baseline | 0.5459 | 0.6047 | 0.7325 | UP | 0.5277 | 0.4410 | -0.007643 |
| 00631L | TBrain | 0.5701 | 0.6080 | 0.6686 | DOWN | 0.3617 | 0.6906 | -0.006823 |
| 00632R | baseline | 0.5440 | 0.6313 | 0.8028 | UP | 0.6925 | 0.5056 | 0.004072 |
| 00632R | TBrain | 0.5774 | 0.6587 | 0.8357 | UP | 0.6842 | 0.4947 | 0.003209 |

單窗格判斷：

- `00631L`: H1/H5 小幅改善，但 H20 AUC 下降 `-0.0639`，不可預設啟用。
- `00632R`: H1/H5/H20 全部改善，保留預設啟用。

## 7. 多年 A/B 回測

設定：

- Yearly OOS folds: `2022, 2023, 2024, 2025, 2026`
- `--no-external-features`
- 每個 fold 使用該年度作 validation。

輸出：

```text
results/ncf_multiyear_00631l_baseline_noext_20260629.json
results/ncf_multiyear_00631l_tbrain_noext_20260629.json
results/ncf_multiyear_00632r_baseline_noext_20260629.json
results/ncf_multiyear_00632r_tbrain_noext_20260629.json
results/ncf_multiyear_tbrain_ab_compare_20260629.json
results/ncf_multiyear_tbrain_ab_compare_20260629.csv
```

### 00631L 多年差異

| Year | H1 Δ | H5 Δ | H20 Δ |
|---:|---:|---:|---:|
| 2022 | -0.0081 | -0.0072 | -0.0138 |
| 2023 | -0.0278 | +0.0004 | -0.0634 |
| 2024 | -0.0024 | +0.0216 | +0.0013 |
| 2025 | +0.0076 | +0.0145 | -0.0501 |
| 2026 | +0.1140 | -0.0725 | +0.1300 |

Summary:

| Horizon | Mean Δ | Median Δ | Positive Years | Baseline Mean AUC | TBrain Mean AUC |
|---|---:|---:|---:|---:|---:|
| H1 | +0.0167 | -0.0024 | 2/5 | 0.5804 | 0.5971 |
| H5 | -0.0086 | +0.0004 | 3/5 | 0.6367 | 0.6280 |
| H20 | +0.0008 | -0.0138 | 2/5 | 0.7030 | 0.7038 |
| All | +0.0029 | n/a | 7/15 | n/a | n/a |

00631L 結論：

- 2026 很強，但不是跨年度穩定改善。
- H5 平均變差。
- H20 平均幾乎持平，且 2023/2025 明顯變差。
- 正式策略不應預設啟用。

### 00632R 多年差異

| Year | H1 Δ | H5 Δ | H20 Δ |
|---:|---:|---:|---:|
| 2022 | +0.0241 | -0.0371 | +0.0345 |
| 2023 | +0.0147 | -0.0128 | -0.0266 |
| 2024 | +0.0595 | +0.0000 | +0.0000 |
| 2025 | +0.0162 | +0.0227 | +0.0697 |
| 2026 | -0.0110 | +0.0108 | -0.0059 |

Summary:

| Horizon | Mean Δ | Median Δ | Positive Years | Baseline Mean AUC | TBrain Mean AUC |
|---|---:|---:|---:|---:|---:|
| H1 | +0.0207 | +0.0162 | 4/5 | 0.5894 | 0.6101 |
| H5 | -0.0033 | +0.0000 | 2/5 | 0.6822 | 0.6789 |
| H20 | +0.0143 | +0.0000 | 2/5 | 0.6783 | 0.6927 |
| All | +0.0106 | n/a | 8/15 | n/a | n/a |

00632R 結論：

- H1 最穩，5 年中 4 年改善。
- H20 平均小幅改善。
- H5 幾乎持平，平均小幅變差。
- 全體 15 cells 中 8 cells 改善，平均 AUC delta `+0.0106`。
- 改善不是巨大，但足以保留為 `00632R` NCF feature enhancement。

## 8. daily_signal 變更

`group_a_plus/operations/daily_signal.py` 新增 `tbrain_shadow` 區塊：

```json
"tbrain_shadow": {
  "status": "available",
  "ticker": "0050.TW",
  "date": "...",
  "features": {
    "tbrain_close_ma22_loc": "...",
    "tbrain_kdj_k_9_3_3": "..."
  },
  "method": "tbrain_multi_kdj_location_shadow_v1"
}
```

用途：

- 只做診斷與觀察。
- 不影響 `execution_allowed`。
- 不改正式 target weights。

## 9. NCF overlay 變更

`group_a_plus/integrations/ncf.py` 已在 `load_ncf_signal()` 載入：

- horizon probabilities
- horizon validation AUCs
- direction weights
- direction/magnitude gate

`ncf_overlay_summary()` 已輸出：

- `dynamic_horizon_00631l`
- `dynamic_horizon_00632r`
- `cross_ticker_consistency`
- each ticker 的 `direction_magnitude_gate`

注意：這些是 advisory / diagnostics，不是本次 TBrain 特徵保留決策的唯一依據。

## 10. 驗證

最後驗證：

```bash
.venv/bin/python -m pytest \
  tests/test_tbrain_features.py \
  tests/test_group_a_plus_ncf_integration.py \
  tests/test_group_a_plus_daily_signal_v2.py \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_ncf_multiyear_wf.py
```

結果：

```text
69 passed
```

並通過：

```bash
.venv/bin/python -m py_compile \
  scripts/misc/ncf_00631l.py \
  ncf_00632r.py \
  scripts/sweep/ncf_multiyear_wf.py
```

## 11. 後續建議

1. `00632R` 保留 TBrain features，但不要調高策略權重。
2. `00631L` 只在研究模式用 `--tbrain-features` 手動測。
3. 若未來加入 external features 後要重評，需重跑同樣 A/B：

```bash
.venv/bin/python scripts/sweep/ncf_multiyear_wf.py \
  --ticker 00632R \
  --years 2022 2023 2024 2025 2026 \
  --output results/ncf_multiyear_00632r_tbrain_ext_YYYYMMDD.json
```

4. 若想升級正式策略版本，至少要求：

- 00632R TBrain 在 external features 開啟後仍保持正向。
- 多年 positive cells 明顯高於 8/15。
- H5 不再小幅拖累，或能透過 horizon weighting 降低 H5 權重。

## 12. 最終狀態

截至 2026-06-29：

```text
00632R: TBrain features retained by default.
00631L: TBrain features disabled by default, opt-in only.
daily_signal: TBrain shadow diagnostics retained.
strategy weights: unchanged by this work.
```
