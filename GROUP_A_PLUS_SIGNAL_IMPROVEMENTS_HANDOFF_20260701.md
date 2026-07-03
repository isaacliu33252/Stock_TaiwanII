# Group A+ Signal System Improvements — 交接記錄 2026-07-01

## 本次工作摘要

本次會話完成了兩輪系統改進，並生成 7/1 預測。所有修改皆已套用至 working tree（未 commit）。

---

## 一、修改清單（6 個文件）

### 1. `group_a_plus/operations/daily_signal.py`

**修改一：execution_risk 公式 v1 → v2**
- `total_risk_score` 正規化從 `/8` 改為 `/10`（最大值本來就是 10）
- 權重調整：`total_risk 0.15→0.20`、`leverage 0.15→0.12`、`soft_data 0.10→0.08`
- 加入 floor 邏輯：`raw_risk_score >= 9` → level 至少為 "medium"（修正 risk=10 卻顯示 low 的問題）

**修改二：`_apply_bearish_high_risk_trim` 動態縮減**
- 預設 `trim_fraction` 從 0.25 → 0.20
- 加入動態縮放：`scale = 1.0 + 0.5 * max(0, raw_risk - 9)`，risk=10 時 trim 為 30%
- 觸發條件加入 `"mixed"` alignment（原僅 `wide_divergence` 和 `bearish_alignment`）

**修改三：tbrain_shadow 傳入 build_signal_alignment()**
- 這是本次最重要的 bug fix
- `build_signal_alignment()` 呼叫時缺少 `"tbrain_shadow": tbrain_shadow`，導致 tbrain_kdj 永遠顯示 neutral/0.000
- 修正後 tbrain_kdj 正常貢獻信號（7/1 實測：bearish 0.318）

### 2. `group_a_plus/integrations/ncf.py`

**direction_conflict 欄位**
- 預先計算 `_gate = direction_magnitude_gate(...)` 避免雙重呼叫
- 新增 `direction_conflict` 欄位：`return_side` 不是 FLAT 且與 `direction` 相反時為 True
- `ncf_downside_signal()`：`direction_conflict=True` 時 r_bull / l_bear 歸零
- `ncf_upside_signal()`：`direction_conflict=True` 時 l_bull / r_bear 歸零
- `ncf_overlay_summary()`：在 ncf_00631l / ncf_00632r block 輸出 `direction_conflict`

### 3. `group_a_plus/integrations/signal_alignment.py`

**factor_lens 過期懲罰**
- 新增 `_factor_lens_stale_days()` helper
- stale 1 天 → strength × 0.5；stale 2+ 天 → direction 強制 neutral、strength=0.10

**ncf_00632r_inverse direction_conflict 處理**
- `direction_conflict=True` 時：direction=neutral、strength=0.10（避免衝突信號污染投票）

**新增 `_tbrain_source()`**
- 讀取 `tbrain_shadow.features` 中的 KDJ 快(9,3,3) 與慢(5,21,11)
- J < 0.30 且 K < D → bearish；J > 0.70 且 K > D → bullish；否則 neutral
- 快慢方向不一致時 strength 減半
- 已加入 `build_signal_alignment()` sources 清單

### 4. `group_a_plus/runners/a2118.py`

**backtest_live_discrepancy 文件化**
- 在 report output 中加入 `backtest_live_discrepancy` dict
- 記錄 `bearish_high_risk_trim` 在 backtest 中不存在的原因（需要即時多源信號，歷史重建會有 lookahead bias）
- 計算 `high_chip_golden1_days`（chip≥9 且 regime=golden1 的歷史天數，作為潛在影響評估）

### 5. `scripts/run/run_ncf_daily_pipeline.py`

**自動化 pipeline 新增兩步驟**
- `factor_lens`：每日自動執行 `evaluate_group_a_plus_factor_lens.py`，解決 factor_lens 報告變舊問題
- `daily_signal`：每日自動執行 `daily_signal.py`，輸出 `group_a_plus_live_signal_v2_{stamp}.json`
- 兩者均加入 `summary["outputs"]` dict

---

## 二、7/1 預測結果

**資料日期：2026-06-30 ｜ 執行機制：golden1**

| 標的 | 目標權重 |
|------|---------|
| 0050.TW | 69.5% |
| 00631L.TW | 7.2% |
| 現金 | 23.3% |
| 00632R / 00679B | 0% |

**信號對齊：mixed（看空主導 61.4%）**

| 信號來源 | 方向 | 強度 | 備註 |
|---------|------|------|------|
| ncf_00631l | neutral | 0.179 | prob_up=0.4887 |
| ncf_00632r_inverse | neutral | 0.100 | direction_conflict → 不可信 |
| ncf_cross_ticker | bearish | 0.344 | market_prob 偏低 |
| finbert_sentiment | neutral | 0.139 | risk=0.519 |
| composite_risk_score | bearish | 1.000 | total_risk=10, chip=9 |
| factor_lens | bullish | 0.275 | 報告過期 → strength 已減半 |
| tbrain_kdj | bearish | 0.318 | J=0.234，K(0.429)<D(0.526) |
| execution_regime | bullish | 0.350 | golden1 長期多頭 |

**觸發邏輯：**
- A21.18 已觸發（ma_gap=22.8% > 10% + H20 DOWN + conf>0.55）→ 00631L 10%
- bearish_high_risk_trim 啟動（risk=10，dynamic scale=1.5）→ 額外削減 30% → 00631L 7.2%
- 警示：🔴 total_risk=10 ｜🟡 execution_risk medium ｜🟡 factor_lens stale

**預測輸出路徑：** `results/group_a_plus_live_signal_v2_20260701_preview.json`

---

## 三、待決策事項（繼承自上次）

### 3.1 h5_reentry_min 決策
- BayesOpt 建議 **0.367**，現行值 **0.55**
- 影響：H=5 再進場門檻降低，可能增加交易次數
- 待 backtest 驗證後決定是否調整

### 3.2 XGB 7 個共識 D 特徵剪除
- 來自 `project_feature_sweep_20260630.md`
- 7 個被多次審計評為最弱的特徵，建議從訓練集移除
- 需配合重訓練

### 3.3 direction_magnitude_gate 閾值調整
- 現行：predicted_return 絕對值 < threshold 時認為 FLAT
- 00632R 連續出現 conflict（prob_up > 0.5 但 return < 0）→ 可考慮調低閾值或調整 confidence 懲罰

### 3.4 Factor Lens 自動化更新
- pipeline 已加入自動執行，但需確認每日排程（23:30 任務）是否正常觸發
- 驗證方式：次日執行後確認 `factor_lens_gate.report_generated_at` 等於當日日期

---

## 四、是否需要重訓練？

**結論：本輪改動不需要重訓練。**

所有修改都在 inference/signal 層，不涉及模型權重：
- `daily_signal.py`：純信號組合邏輯
- `ncf.py`：inference 後處理（direction_conflict 是 post-hoc 計算）
- `signal_alignment.py`：投票聚合層
- `run_ncf_daily_pipeline.py`：流程編排

若未來採納 h5_reentry_min=0.367 或剪除 7 個 D 特徵，才需要重訓練。

---

## 五、系統健康狀態（2026-07-01）

| 項目 | 狀態 |
|------|------|
| NCF 00631L AUC H=20 | 0.7036 |
| NCF 00632R AUC H=5 | 0.6907 |
| 每日排程（Windows 工作排程器） | 23:00 下載 / 23:30 跑 NCF |
| Factor Lens 自動刷新 | ✅ 已加入 pipeline |
| daily_signal 自動輸出 | ✅ 已加入 pipeline |
| backtest/live 差異文件化 | ✅ a2118.py 已記錄 |

---

*生成時間：2026-07-01*
