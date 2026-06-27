# NCF 00631L 預測模型 — 交接說明 V3
**日期：2026-06-27**
**涵蓋工作：TXO 特徵、Optuna 調參、多年走向驗證、Panel 延伸**
**主檔案：`scripts/misc/ncf_00631l.py`（2606 行）**
**前次交接：`NCF00631L_HANDOFF_20260624_V2.md`（Tasks 7-11）**

---

## 1. 本 Session 完成的工作

### 1.1 TXO 選擇權法人未平倉特徵（v7）

**動機**：台指選擇權法人 PUT/CALL 未平倉口數是晚期多頭（ma_gap > 15%）的重要看空領先指標，補充純技術面的盲點。

**資料來源**：`derivative_institutional_data` 表（DuckDB），`product_id='TXO'`

**時移處理**：TXO 資料於收盤後公布，全部做 `shift=1`（T-1 日資料預測 T 日方向，無前瞻偏差）

**新增 5 個原始特徵（EXT_FEATURES，L166-170）**：

| 特徵名稱 | 意義 | 看空方向 |
|---------|------|---------|
| `txo_foreign_put_oi` | 外資 PUT 淨多頭口數 | 正值 = 外資買保護 = 看空 |
| `txo_foreign_call_oi` | 外資 CALL 淨多頭口數 | 負值 = 賣出 CALL = 看空 |
| `txo_foreign_pc_spread` | 外資 PUT - CALL 口數差 | 正值 = 外資淨看空 |
| `txo_total_pcr` | 三大法人合計 PUT/CALL 比率 | > 1 = 看空壓力 |
| `txo_foreign_pc_spread_ma5` | `txo_foreign_pc_spread` 5日均線 | 看空趨勢平滑 |

**新增 3 個互動特徵（INTERACTION_FEATURES，L194-196）**：

| 特徵名稱 | 公式 | 意義 |
|---------|------|------|
| `txo_pcr_x_ma_gap` | `txo_total_pcr × close_ma200_dist`（均 clip≥0）| 晚期多頭 × 高 P/C 比率（最強看空組合）|
| `txo_foreign_pc_x_vix` | `txo_foreign_pc_spread × vix` | 外資看空 × VIX 恐慌確認 |
| `txo_foreign_pc_x_inst_net` | `txo_foreign_pc_spread × inst_foreign_net` | 選擇權 vs 現貨外資方向一致性 |

**互動特徵建立位置**：`_add_interaction_features()` 函數（L559-565）

**TXO 載入程式碼位置**：`load_external_df()` 函數（L340-385），在 `tx_night_ret` 區段之後

**AUC 改善（晚期多頭 MDD 分類器）**：
- v6（無 TXO）：0.8758
- v7（含 TXO）：0.8820（+0.006）
- Gain 分類器 AUC 不變（特徵對下行風險更有辨別力）

---

### 1.2 Bug 修復（同步於 v7）

#### 修復 1：`_PlattModel` 未定義（`stable_rf` 校準區段）
- **問題**：`train_classifier()` 中 `stable_rf` 的校準區段引用了 `_PlattModel`，但該 class 從未在 `ncf_00631l.py` 中定義（只存在於 V2 版本的 `_PlattModel` wrapper）
- **修復**：改用 `_IsotonicModel`（L1729），與主模型校準方式一致：
  ```python
  iso_stb = IsotonicRegression(out_of_bounds="clip")
  iso_stb.fit(raw_cal_stb, y_calib)
  stb_cal_m = _IsotonicModel(stb_fit, iso_stb)
  ```

#### 修復 2：Bear Regime 0 樣本導致 `StandardScaler` 崩潰
- **問題**：2026 年上半年全為多頭市場，`X_val_sel[~above_ma200_val]` = 0 行，`scaler.transform()` 拋出 `ValueError`
- **修復**：迴歸與分類均加入 fallback（L1970, L1999）：
  ```python
  if (~above_ma200_val).sum() == 0 or (~above_ma200_train).sum() < 20:
      reg_bear = reg_bull   # 熊市直接用牛市模型代替
  else:
      reg_bear = train_regressor(...)

  if (~above_ma200_val).sum() == 0 or (~above_ma200_train_clf).sum() < 20:
      clf_bear = clf_bull   # 同上
  else:
      clf_bear = train_classifier(...)
  ```

---

### 1.3 步驟 1 — Optuna 超參數調優

**腳本**：`scripts/misc/ncf_optuna_tune.py`（261 行，本 session 新建）

**設定**：75 trials × 5 模型（LGB/XGB/HGB/RF/ET）× 4-fold TimeSeriesSplit，訓練區間 2020-2024，H=20

**結果**：

| 模型 | Best CV AUC |
|------|------------|
| LGB | 0.5190 |
| XGB | 0.5347 |
| HGB | 0.5069 |
| RF | 0.5107 |
| ET | 0.5433 |

**Best params 儲存路徑**：`results/ncf_optuna_best_params.json`

**決策**：**不採用 Optuna 參數**。CV AUC 只有 0.51-0.54，在 2025+ val set 上實際表現比 v7 預設參數略差（H=20 late-bull AUC：0.8357 vs v7 的 0.8493）。根本原因：5-fold TSS 在 4 年訓練資料上 fold 太小，CV 分數與真實 OOS 不相關。

**新增 CLI 參數**：`--optuna-params <path>` (L1822)，可選擇性載入 best params JSON，**平時不傳此參數即使用預設**。

---

### 1.4 步驟 2 — 多年走向驗證（2022-2026）

**腳本**：`scripts/sweep/ncf_multiyear_wf.py`（220 行，本 session 修正）

**方法**：每年一個 fold，訓練所有該年之前的資料，驗證當年 1-12 月（2026 fold 驗證至今日）

**結果**：

| 年份 | H=1 AUC | H=5 AUC | H=20 AUC | 市況 |
|------|---------|---------|---------|------|
| 2022 | 0.5772 | **0.7295** | **0.7955** | 熊市（聯準會升息）|
| 2023 | **0.6129** | 0.5915 | 0.6128 | 盤整轉多 |
| 2024 | 0.5668 | 0.5120 | 0.6330 | 全年多頭 |
| 2025 | **0.6220** | **0.6681** | 0.5834 | 多頭 + 川普關稅波動 |
| 2026（至今）| 0.4864 | 0.6597 | **0.7788** | 急升後高點盤整 |

**結論**：
- H=20 全部 5 年 AUC ≥ 0.58（最低 2025），**模型跨年穩定，無過擬合**
- H=1 2026 年 AUC = 0.49（接近隨機），短線訊號在高點橫盤期間雜訊大
- 熊市（2022）和急跌後（2026）AUC 最高，模型對方向性市場辨別力最強

**修正的 Bug**：`_extract_auc()` 路徑錯誤（舊版找 `regime_classification.bull.ensemble.auc`，實際 JSON 為 `classification.val_auc`）

**輸出**：`results/ncf_multiyear_wf_00631l.json`

---

### 1.5 步驟 3 — Panel 延伸至 2026-06-25（`--full-panel`）

**問題**：H=20 需要 20 交易日的前瞻標籤，因此 `build_dataset()` 末尾 20 行無法標記。2026-05-27 是最後一筆有標籤的資料，之後的 20 個交易日（2026-05-28 至 2026-06-25）無法正常納入 panel。

**解決方案**：`--full-panel` flag（L1822）

**機制**：
1. 訓練完成後，將各 horizon 的 `clf_bull`/`clf_bear` 及 `sel_features` 存入 `all_clf_models[h]`（L2007）
2. `--full-panel` 啟動後，重建完整特徵（含 TXO 外部特徵與互動特徵）
3. 取 `panel_df.index[-1]` 之後的 tail rows，逐 horizon / 逐 regime 呼叫 `predict_proba()`
4. 以 ensemble weights 加權，得到每日的 `prob_up_h1/h5/h20`
5. 標記 `is_live=True`，concat 至 panel_df 後儲存

**關鍵實作細節（避免 0.0 預測的陷阱）**：
- `sel_features` 不含 regime cols（`above_ma200` 等），但模型訓練時有 regime cols，所以需：
  ```python
  _sf_full = _sf + [c for c in _REGIME_COLS if c in _tail.columns and c not in _sf]
  ```
- Per-model feature subsetting（stable_rf 用不同特徵集）：
  ```python
  _nm_feats = _clf.get(_nm, {}).get("features")
  _sub_nm = _sub[_nm_feats] if _nm_feats else _sub
  ```

**Panel 結果**：

```
ncf_00631l_panel_2025_v7_full.csv
  Labeled rows: 336  (2025-01-02 ~ 2026-05-27)  is_live=False
  Live rows:     20  (2026-05-28 ~ 2026-06-25)  is_live=True
  總計:         356 行
```

**最近 Live Tail 訊號摘要（2026-06-16 至 2026-06-25）**：

| 日期 | prob_up_h1 | prob_up_h5 | prob_up_h20 | 解讀 |
|------|-----------|-----------|------------|------|
| 2026-06-16 | **0.733** | **0.743** | 0.335 | 短/中線強多，月線仍偏空 |
| 2026-06-22 | 0.213 | 0.447 | 0.300 | 全線轉弱 |
| 2026-06-23 | 0.418 | 0.416 | 0.291 | 月線持續偏空 |
| 2026-06-24 | 0.350 | 0.495 | 0.371 | 中性 |
| 2026-06-25 | **0.627** | **0.570** | 0.308 | 短線多，月線偏空 |

**解讀**：tail 期間 `prob_up_h20` 持續在 0.29-0.40，月線方向偏空；`prob_up_h1/h5` 波動較大，短線有多有空。

---

## 2. 目前模型架構（v7 + TXO，2026-06-27）

### 2.1 驗證集效能（val = 2025-01-02 ~ 2026-06-25）

| Horizon | Val AUC | Direction | Prob Up |
|---------|---------|-----------|---------|
| H=1 | 0.598 | DOWN | 0.350 |
| H=5 | 0.682 | NEUTRAL | 0.454 |
| H=20 | 0.683 | DOWN | 0.333 |

**Horizon Ensemble（AUC-weighted direction）**：DOWN，combined prob=0.397，confidence=0.64

| | H=1 | H=5 | H=20 |
|-|-----|-----|------|
| 方向 weight（AUC-based）| 24% | 49% | 27% |
| 報酬 weight（MAE²-based）| 83% | 14% | 3% |
| AUC | 0.583 | 0.674 | 0.595 |

### 2.2 H=20 Bull Regime 分類模型（last val = 2026-06-25）

| 模型 | 機率 | Ensemble Weight |
|------|------|----------------|
| RF | 0.409 | 9.8% |
| ET | 0.496 | **51.8%** |
| HGB | 0.021 | 6.8% |
| GB | 0.031 | 7.8% |
| LGB | 0.021 | 7.9% |
| XGB | 0.189 | 16.1% |
| CAT | 0.415 | 0%（AUC < threshold）|
| stable_rf | 0.562 | 0%（AUC < threshold）|

### 2.3 外部特徵載入狀態（EXT_FEATURES）

外部特徵共 **34 個**（原本 29 個 + 5 個 TXO），由 `load_external_df()` 自 DuckDB 載入：
- 基礎：VIX、US10Y、USD/TWD、TWII overnight return、tx_night_ret
- 法人：inst_foreign_net、inst_dealer_net、inst_trust_net
- 技術衍生：close_ma200_dist（用於 late-bull 校準）
- TXO（新增）：5 個（見 1.1 節）

---

## 3. 執行指令

```bash
# 標準執行（v7 預設，含 TXO 特徵，val 至今日）
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2020-01-01 \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00631l_v7_$(date +%Y%m%d).json \
  --val-predictions-output results/ncf_00631l_panel_$(date +%Y%m%d).csv

# 含完整 live tail 延伸（--full-panel）
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2020-01-01 \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00631l_v7_full_$(date +%Y%m%d).json \
  --val-predictions-output results/ncf_00631l_panel_$(date +%Y%m%d)_full.csv \
  --full-panel

# Optuna 調參（需要時，75 trials，約 20-30 分鐘）
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py \
  --trials 75 --horizon 20 \
  --output results/ncf_optuna_best_params.json

# 多年走向驗證（5 folds × 3 horizons，約 30-40 分鐘）
PYTHONPATH=. .venv/bin/python scripts/sweep/ncf_multiyear_wf.py \
  --ticker 00631L \
  --output results/ncf_multiyear_wf_00631l.json
```

---

## 4. 程式碼位置速查

| 功能 | 檔案 | 行號 |
|------|------|------|
| `EXT_FEATURES` 清單（含 TXO） | `ncf_00631l.py` | L164-172 |
| `INTERACTION_FEATURES` 清單（含 TXO）| `ncf_00631l.py` | L192-197 |
| TXO 資料載入（`load_external_df`）| `ncf_00631l.py` | L340-385 |
| TXO 互動特徵建立（`_add_interaction_features`）| `ncf_00631l.py` | L559-565 |
| `_IsotonicModel` class | `ncf_00631l.py` | L1540 |
| `train_classifier` 函數簽名（含 `optuna_params`）| `ncf_00631l.py` | L1408-1413 |
| Optuna 參數覆寫區段 | `ncf_00631l.py` | L1487-1505 |
| Bear regime 0 樣本 fallback（迴歸）| `ncf_00631l.py` | L1970 |
| Bear regime 0 樣本 fallback（分類）| `ncf_00631l.py` | L1999 |
| `all_clf_models` 儲存（for `--full-panel`）| `ncf_00631l.py` | L2007-2013 |
| Full panel tail extension 區段 | `ncf_00631l.py` | L2190-2260 |
| `--full-panel` CLI 參數 | `ncf_00631l.py` | L1822 |
| `--optuna-params` CLI 參數 | `ncf_00631l.py` | L1823 |

---

## 5. 輸出檔案索引

| 檔案 | 說明 | 更新日 |
|------|------|------|
| `results/ncf_00631l_v7_final.json` | v7+TXO 最終訓練輸出（全量 JSON）| 2026-06-27 |
| `results/ncf_00631l_panel_2025_v7_full.csv` | 完整 panel，336 標記 + 20 live tail | 2026-06-27 |
| `results/ncf_optuna_best_params.json` | Optuna 最佳超參數（**不採用**，備查）| 2026-06-27 |
| `results/ncf_multiyear_wf_00631l.json` | 多年走向驗證結果（2022-2026）| 2026-06-27 |
| `scripts/misc/ncf_optuna_tune.py` | Optuna 調參腳本（新建）| 2026-06-27 |
| `scripts/sweep/ncf_multiyear_wf.py` | 多年走向驗證腳本（修正 `_extract_auc`）| 2026-06-27 |

---

## 6. 已知限制

### 6.1 H=20 HGB/LGB/XGB Brier 偏高
- Boosting 模型輸出極端機率（如 0.021），Isotonic 校準改善有限
- ET 在 Bull regime 幾乎獨大（weight 52%），造成 ensemble 集中度偏高
- 緩解方案：考慮對 boosting 模型加 `min_child_samples` 限制（已在 Optuna 搜索，但 CV AUC 無顯著差異）

### 6.2 Bear Regime 資料稀少（~90 筆訓練）
- `stable_rf` 在 Bear 幫助最大（AUC = 0.85），但 Bull 反而 < 0.5（自動 weight = 0）
- 2026 年至今全為多頭，Bear 模型完全 fallback 至 Bull 模型

### 6.3 TXO 資料覆蓋率
- `derivative_institutional_data` 較早期資料可能有缺漏（2015-2019 年 TXO 欄位可能全為 NaN）
- `load_external_df()` 採用 `ffill` + `shift(1)` 處理，NaN 自動補前值
- 建議定期確認 `derivative_institutional_data` 是否有每日新增

### 6.4 `--full-panel` tail 無 MDD/Gain 機率
- Live tail rows 只有 `prob_up_h1/h5/h20`，沒有 `prob_fwd_mdd_gt5_h20` 等下行風險欄位
- 下行風險分類器（MDD/Gain）需要 H=20 前瞻標籤才能訓練，tail 期間無法推論
- 若需要，可考慮用 `prob_up_h20 < 0.35` 作為高 MDD 風險的近似替代

---

## 7. 未來改善方向

### 高優先
- **TXO 覆蓋率確認**：執行前先 `SELECT MIN(dt), MAX(dt), COUNT(*) FROM derivative_institutional_data WHERE product_id='TXO'` 確認資料完整
- **`--full-panel` 加入 MDD/Gain 延伸**：用歷史統計或另訓 proxy 模型估算 live tail 的下行風險機率
- **00632R 多年走向驗證**：本 session 只跑了 00631L，00632R 的 walk-forward 尚未執行

### 中優先
- **Bear regime 增強**：用大盤指數（0050 / TWII）的熊市期間做 transfer / augmentation，解決訓練資料 ~90 筆過少的問題
- **Live tail 的 `prob_fwd_mdd_gt5_h20`**：新增 rule-based 近似（如 `txo_pcr_x_ma_gap > threshold` 且 `vix > 20` → 高 MDD risk）

### 低優先
- **Optuna 改善**：嘗試更長訓練窗口（2015-2024）和更多 trials（150+），或改用 WalkForwardCV 而非 TimeSeriesSplit，使 CV AUC 更接近真實 OOS

---

## 8. 與前次交接的差異對照

| 項目 | V2（2026-06-24）| V3（2026-06-27，本文）|
|------|----------------|----------------------|
| 特徵數（外部）| 29 | **34**（+5 TXO）|
| 互動特徵 | 9 個 | **12 個**（+3 TXO 互動）|
| stable_rf 校準 | _PlattModel（未定義，Bug）| **_IsotonicModel**（已修復）|
| Bear 0 樣本 | ValueError 崩潰（Bug）| **fallback to bull**（已修復）|
| Panel 最後日期 | 2026-05-27（無 tail）| **2026-06-25（+20 live rows）**|
| Optuna | 未執行 | **已執行，決定不採用** |
| 多年驗證 | 未執行 | **已執行（2022-2026，H=20 AUC 0.58-0.80）**|
