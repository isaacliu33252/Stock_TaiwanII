# AlphaGen-lite Handoff — 2026-07-01

**日期：** 2026-07-01
**完成項目：** alphagen-master 原始碼審查 / AlphaGen-lite Shadow Test（寬候選公式挖掘）/ AlphaGen-lite 特徵池 vs 手動剪除比較
**執行人：** Claude Code (claude-sonnet-5)

---

## 背景

延續 [[STOCK_RNN_IMPORT_REVIEW_20260630.md]]、`STOCK_PREDICTION_MODELS_IMPORT_REVIEW_20260630.md` 建立的外部研究審查流程，本次審查 `C:\Users\isaac\Downloads\alphagen-master\alphagen-master`（KDD 2023 論文《Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning》官方實作）。

與前兩個外部 repo 不同：AlphaGen 的優化目標（IC/RankIC）跟 Group A+ 現有 `factor_lens_gate`（`ic_20d_recent_mean`、`ic_5d_positive` 等檢查）與 `scripts/misc/xgb_feature_audit.py`（IC + gain 綜合評分）**本質上是同一套邏輯**，不像 stock-rnn/Stock-Prediction-Models 用 MSE 價格預測這種跟策略目標不match的目標函數。因此本次不只是文件審查，而是做了兩輪實測 shadow test。

---

## 一、AlphaGen 原始碼分析摘要

**核心架構：**
- 運算子代數（`alphagen/data/expression.py`）：`Ref/Delta/Mean/Std/Skew/Kurt/WMA/EMA/Rank/CSRank/Corr/Cov` 等 WorldQuant 風格運算子，可組成任意深度公式樹
- RL（PPO, via stable-baselines3）搜尋運算子樹空間，以 IC/RankIC 為 reward
- `LinearAlphaPool`（`alphagen/models/linear_alpha_pool.py`）：找到的 alpha 用貪婪演算法建池——新候選加入 → 最小平方法重新擬合線性權重 → 檢查跟現有池子的 mutual IC（防止選到高度相關的重複因子）→ 若超過容量，砍掉權重貢獻最小的
- `AlphaCalculator` 介面（`alphagen/data/calculator.py`）：明確設計成可接外部 pipeline，不強制用 Qlib/baostock 資料格式

**關鍵限制：**
- `CSRank`/`Rank` 是橫截面運算子，需要大量標的才有意義。Group A+ 只交易 4 檔高度相關的台股 ETF（0050 + 00631L/00632R 互為槓桿反向 + 00679B 債券），橫截面排名幾乎無訊號量
- 完整 pipeline 需要 Qlib + baostock 資料層 + PyTorch/stable-baselines3 PPO 訓練迴圈，目前專案技術棧沒有這些依賴

**v1 匯入範圍（刻意縮小）：** 只搬運算子代數（純時間序列版，排除 CSRank/Rank）+ LinearAlphaPool 貪婪選池邏輯，不做 RL 搜尋（候選空間夠小可以窮舉評分）、不接 Qlib。

詳見 `ALPHAGEN_IMPORT_REVIEW_20260701.md`。

---

## 二、Shadow Test 1：寬候選公式挖掘

**實作：**
```
scripts/evaluate/evaluate_alphagen_lite_shadow.py
tests/test_evaluate_alphagen_lite_shadow.py
```

**結果檔案：** `results/alphagen_lite_shadow_latest_20260701.json`

**方法：** 用 6 個 panel 欄位（`prob_up_h20`/`h20_prob_up`/`confidence`/`prob_fwd_mdd_gt5_h20`/`prob_fwd_gain_gt5_h20`/`tail_reward_risk_score_h20`）+ 4 檔 ETF 的 close/volume 當 leaf，套用 Delta/mean-bias/std/WMA/EMA 運算子（window=5/10/20）+ 兩兩 rolling Corr（0050 vs 00631L、0050 vs 00632R），共生成 **228 個候選公式**。TimeSeriesSplit(n_splits=4, gap=5)，target 用連續值 `forward_gain_h20`（不是二元化，符合 AlphaGen 原始 IC 目標）。

**結果：**

| 指標 | Baseline (`prob_up_h20`) | AlphaGen-lite pool |
|---|---:|---:|
| 平均 IC | 0.2181 | 0.0008 |
| 平均 RankIC | 0.1546 | -0.0131 |

逐折 IC 在 -0.671 到 +0.497 之間亂跳，每折選中的候選式子幾乎都不同 → **典型樣本內過擬合**：228 個候選對上每折只有 150~250 列訓練資料，屬嚴重多重比較問題。

**結論：** `research_only`，`active_allocation_impact: none`。方法論本身沒錯（跟 factor_lens 同一套 IC 邏輯），但敗在樣本量太小；若未來 panel 拉到多年期，值得重新評估。

---

## 三、Shadow Test 2：AlphaGen-lite 特徵池 vs 手動剪除比較

**動機：** [[project_feature_sweep_20260630]] 記錄的 2026-06-30 XGB 審計標出 7 個「共識 D」特徵（兩檔標的皆為 D 級）：
```
n225_x_twii_ret, us_qqq_ret, twii_ret, vix_change,
vix_change_x_return1d, volume_ratio_5, above_ma20
```
計畫下季正式剪除。測試 Shadow Test 1 學到的 `greedy_pool_select` 能否當作自動化剪除工具，取代或交叉驗證手動審計。

**實作：**
```
scripts/evaluate/evaluate_alphagen_lite_feature_pool.py
```
（重用 `evaluate_alphagen_lite_shadow.py` 的 `greedy_pool_select`；順便修掉該函式原本在候選池為空時回傳 2-tuple、非空時回傳 4-tuple 的不一致，統一成固定 4-tuple 回傳，並更新對應測試）

**結果檔案：** `results/alphagen_lite_feature_pool_latest_20260701.json`

**方法：** 00631L、H=20、完整 135 個特徵（train_start=2020-01-01，Fourier+Global 啟用，跟 `xgb_audit_00631l_20260630.json` 同設定）。TimeSeriesSplit(n_splits=5, gap=5)，每折跑兩次 `greedy_pool_select`（capacity=12, ic_lower_bound=0.03, mutual_ic_threshold=0.7）：一次用全部 135 特徵，一次先剪掉 7 個共識 D 特徵再跑，比較 test IC 差異，並記錄全特徵池版本有沒有自己選到這 7 個特徵。

**結果：**

| | 全特徵池自動選 | 先手動剪 7 個再選 |
|---|---:|---:|
| 平均 test IC（5 折）| -0.0369 | -0.1113 |

逐折明細：

| Fold | Train列數 | 全池 IC | 剪除後 IC | 該折選中的共識D特徵 |
|---|---:|---:|---:|---|
| 1 | 210 | -0.050 | -0.050 | 無（兩池結果相同） |
| 2 | 422 | -0.551 | -0.551 | 無（兩池結果相同） |
| 3 | 634 | -0.037 | -0.135 | `above_ma20` |
| 4 | 846 | **+0.293** | +0.019 | `above_ma20` |
| 5 | 1058 | +0.160 | +0.160 | 無（兩池結果相同） |

共識 D 特徵在 5 折 × 7 特徵 = 35 個位置中只被選中 2 次（選中率 5.7%）。

**三個發現：**

1. **多數情況自動選池本來就不會選到共識 D 特徵**（5.7% 選中率）——對手動 XGB 審計判斷的獨立交叉驗證，大部分時候不用特地剪，工具自己會忽略。
2. **但 `above_ma20` 在 fold 3、4 被選中，且留著它明顯更好**（fold 4：留著 IC=0.293，剪掉只剩 0.019）。代表「共識 D」評分是用固定訓練窗算出的單一結論，不代表在所有時期都無用——趨勢類特徵可能在特定盤勢重新有效，**永久剪除可能丟掉 regime-dependent 訊號**。
3. **整體 IC 仍不穩定**，訓練列數越多越穩定（fold 4/5，846/1058 列時轉正；fold 1/2，210/422 列時是負的）——跟 Shadow Test 1 同一個病根：候選數相對樣本數偏多，早期歷史不夠長時過擬合。

**結論：** `research_only`，不建議直接拿 `greedy_pool_select` 取代手動 XGB 審計，但可以當「二次交叉檢查」：
- 若特徵被自動池排除，且訓練樣本 >600 列，可增加剪除信心
- 若特徵像 `above_ma20` 一樣偶爾被自動池選中且貢獻正 IC，建議降級為「監控」而非直接剪除

---

## 四、試導入紀錄（2026-07-01）

**導入範圍：** 只導入到 **AlphaGen-lite 特徵治理 / shadow audit 層**，不進入 A21.18 active allocation。

**程式變更：**
- `scripts/evaluate/evaluate_alphagen_lite_feature_pool.py`
  - 新增 `build_pruning_recommendation()`
  - 報告輸出新增 `pruning_recommendation`
  - 明確標示 `status=research_only`、`active_allocation_impact=none`
- `tests/test_evaluate_alphagen_lite_feature_pool.py`
  - 新增 feature pool 導入決策測試
  - 覆蓋「從未被選中 → prune_candidate」、「曾在 full pool 有貢獻 → monitor」兩種情境

**驗證：**
```bash
.venv/bin/python -m pytest -q tests/test_evaluate_alphagen_lite_shadow.py tests/test_evaluate_alphagen_lite_feature_pool.py
```

結果：`6 passed in 5.63s`

**重新輸出：** `results/alphagen_lite_feature_pool_latest_20260701.json`

**結構化建議：**

| 類別 | 特徵 |
|---|---|
| 可列入下輪重訓剪除候選 | `n225_x_twii_ret`, `us_qqq_ret`, `twii_ret`, `vix_change`, `vix_change_x_return1d`, `volume_ratio_5` |
| 暫緩剪除、列入監控 | `above_ma20` |

**最終決策：**
- AlphaGen-lite 導入成功，但定位為 `research_only`
- 用於下一輪 NCF feature governance / XGB audit 二次交叉檢查
- 不改 A21.18 實盤策略、不改 live target weights、不改 NCF overlay 觸發規則
- 若未來要把剪除候選正式移出訓練集，必須另做 retraining + walk-forward backtest

---

## 五、結果檔案一覽

| 檔案 | 說明 |
|---|---|
| `ALPHAGEN_IMPORT_REVIEW_20260701.md` | AlphaGen 原始碼審查 + Shadow Test 1 完整記錄 |
| `scripts/evaluate/evaluate_alphagen_lite_shadow.py` | Shadow Test 1：寬候選公式挖掘（228 候選）|
| `scripts/evaluate/evaluate_alphagen_lite_feature_pool.py` | Shadow Test 2：特徵池 vs 手動剪除比較；已新增 `pruning_recommendation` |
| `tests/test_evaluate_alphagen_lite_shadow.py` | Shadow Test 1 單元測試（4 項，皆過）|
| `tests/test_evaluate_alphagen_lite_feature_pool.py` | Shadow Test 2 導入決策測試（2 項，皆過）|
| `results/alphagen_lite_shadow_latest_20260701.json` | Shadow Test 1 輸出 |
| `results/alphagen_lite_feature_pool_latest_20260701.json` | Shadow Test 2 輸出；含 feature pruning recommendation |
| `results/xgb_audit_00631l_20260630.json` | 對照：原始手動 XGB 審計（135 特徵分級）|

---

## 六、待決策事項（下次 session 處理）

### 優先級 Medium

1. **共識 D 特徵剪除計畫調整**：原計畫（[[project_feature_sweep_20260630]]）下季直接剪除全部 7 個。根據 AlphaGen-lite 試導入後的結構化建議，調整為：
   - `n225_x_twii_ret, us_qqq_ret, twii_ret, vix_change, vix_change_x_return1d, volume_ratio_5`（6 個，從未被自動池選中）：可正式剪除
   - `above_ma20`（1 個，在 2 折被自動池選中且貢獻正 IC）：**降級為監控，暫緩剪除**，下季審計時再觀察是否持續在後段折數被選中

2. **剪除候選正式移出訓練集前需重訓驗證**：AlphaGen-lite 目前只給 feature governance 建議。若要正式移除 6 個 prune candidates，需跑 NCF retraining + walk-forward backtest，確認 AUC、IC、live overlay 行為沒有退化。

### 優先級 Low

3. **多年期重跑 Shadow Test 1**：兩次測試都指向「候選數相對樣本數過多 → 過擬合」，且訓練列數越多結果越穩定的訊號一致。若 panel 未來擴充到多年期（目前只有 291~359 列），值得重新跑一次驗證過擬合問題是否緩解。
4. 不建議投入 RL/PPO 搜尋或 Qlib 整合；4 檔標的的資產池規模用不上這套框架的核心優勢（橫截面選股）。

---

## 七、本次 session 實作項目回顧

| 項目 | 狀態 |
|---|---|
| alphagen-master 原始碼審查（expression.py / calculator.py / linear_alpha_pool.py / README）| ✅ 完成 |
| Shadow Test 1：寬候選公式挖掘 + 貪婪選池 | ✅ 完成，`research_only` |
| Shadow Test 2：特徵池 vs 手動剪除比較（00631L, 135 特徵）| ✅ 完成，`research_only`，發現 `above_ma20` 例外 |
| `greedy_pool_select` 回傳值 2-tuple/4-tuple 不一致修復 | ✅ 完成 |
| `evaluate_alphagen_lite_feature_pool.py` 結構化導入建議 | ✅ 完成，新增 `pruning_recommendation` |
| `tests/test_evaluate_alphagen_lite_feature_pool.py` | ✅ 完成，2 項測試通過 |
| `ALPHAGEN_IMPORT_REVIEW_20260701.md` | ✅ 完成 |
| Group A+ 實盤配置變更 | ❌ 無變更（`active_allocation_impact: none`）|

---

*Generated by Claude Code — 2026-07-01*
