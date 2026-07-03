# Group A+ 策略改善 Session 交接紀錄 — 2026-07-02

**執行人：** Claude Code
**範圍：** 使用者要求「針對最新策略分析、改善」，本 session 涵蓋一個資料管線修復 + 一個已 commit 的訊號層改進
+ 三個實測後否決的改善候選 + 一個架構層根因發現。

---

## 一、資料管線修復（已完成，已生效）

**問題：** 今日（7/1）live_signal 的 `execution_allowed=false`，guard 訊息是 `foreign_tx_oi`/`foreign_txo_oi`
過期。查 DuckDB `derivative_institutional_data` 表最後一筆是 2026-06-25，卡了 4 個營業日。

**根因：** 這張表（FinMind `TaiwanFuturesInstitutionalInvestors`/`TaiwanOptionInstitutionalInvestors`，也是
v5 TabNet 升級主打的 TXO PCR 特徵來源）的抓取腳本 `scripts/fetch/fetch_finmind_chip_data.py` **從未被排進
每天 23:00 的自動化 `run_fetch.bat --only-refresh` 流程**，是一支手動跑、沒人記得跑的腳本。

**已完成的修正：**
1. 手動回補 2026-06-26 ~ 2026-07-01 資料，`execution_allowed` 已恢復 `true`。
2. `scripts/run/run_ncf_daily_pipeline.py`：在 `--only-refresh` 區塊新增 `refresh_derivative_institutional`
   步驟，用跟其他籌碼資料一樣的 21 天滾動窗口自動回補，之後每天 23:00 自動執行。
3. `~/.profile` 新增 `FINMIND_API_TOKEN` 環境變數——因為排程用 `wsl bash -lc "..."`（非互動 login shell），
   會跳過 `~/.bashrc`（有 `case $- in *i*)` 提前 return），必須寫在 `.profile` 才會生效。已用
   `bash -lc 'echo $FINMIND_API_TOKEN'` 驗證確實生效。

**驗證：** `--dry-run` 確認新步驟正確插入 pipeline 第 6/8 步；隔夜自動化已成功產生含 7/1 資料的新 panel
（`results/ncf_00631l_panel_latest_20260701.csv`），證實修正有效。

---

## 二、訊號層改進（已 commit，commit 783b6bb）

7/1 完成但當時未 commit 的一批訊號系統改進，本 session 驗證測試後正式 commit。**16 個檔案**（5 個直接改動 +
10 個必要依賴模組 + 1 個 `__init__.py`，確保 commit 單獨 checkout 也能 import 成功）：

- `group_a_plus/operations/daily_signal.py`：execution_risk v2 公式、bearish_high_risk_trim、
  修正 `tbrain_kdj` 因未傳入 `tbrain_shadow` 而永遠中性的 bug
- `group_a_plus/integrations/ncf.py`：新增 `direction_conflict` 偵測
- `group_a_plus/integrations/signal_alignment.py`（新）：10 來源訊號一致性報告
- `group_a_plus/integrations/factor_lens.py`、`finbert.py`、`lm_dictionary_sentiment.py`、
  `tbrain_features.py`、`watchlist_news.py`、`llm_commentary.py`（新）：對應的資料來源整合
- `group_a_plus/operations/alert_state.py`、`ops_health.py`、`strategy_env.py`（新）：健康檢查
- `scripts/run/run_ncf_daily_pipeline.py`（新，同時是上面一節的自動化修正檔）

驗證：116 個直接相關測試全過。完整 `tests/` 套件因混了很多跟這批改動無關的其他實驗性測試，跑不完 300 秒
timeout，未阻斷 commit（風險評估：純推論層改動，不影響模型權重）。

---

## 三、否決的改善候選（三項，均有實測數據支持否決）

### 3.1 BayesOpt a2118 新參數 — 否決

`results/bayesopt_a2118_3d_20260630.json` 建議 `h20_max=0.2922, conf_min=0.520, h5_reentry_min=0.3673`
（vs 現行 `h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55`）。

用真正的 `group_a_plus/runners/a2118.py`（非簡化版機會成本網格）跑最新 panel（含 7/1 資料）的完整回測：
active 與 BayesOpt shadow **兩組參數結果完全一樣**（0 次觸發、Sharpe/AnnRet/MaxDD 全部相同）。深入追查發現
唯一可比較的歷史觸發事件（2025-10-29）的 confidence 在只多兩天資料的新 panel 裡從 0.5613 掉到 0.4635，兩組
門檻都過不了了——不是「證據不夠強」，是現在的證據直接對調換不出差異。**active 維持 0.33/0.55/0.55 不變。**

### 3.2 NCF ensemble 校準 calib_frac 0.20→0.30 — 否決

延續 `NCF_ENSEMBLE_CALIBRATION_HANDOFF_20260701.md` 的建議下一步。用同一份 V2 校準程式碼、同一資料窗口，
比較正式會進 `live_signal` 的 `val_auc`：

| | H1 | H5 | H20 |
|---|---|---|---|
| 00631L | -0.0197 | -0.0070 | 0.0000 |
| 00632R | -0.0066 | 0.0000 | 0.0000 |

兩檔 × 三個 horizon，6 組結果沒有任何一組改善，H1 還都明顯變差。**不採用 calib_frac=0.30。** 順手給
`ncf_00632r.py` 補上 `--calib-frac` CLI flag（原本沒有、硬編碼 0.20，00631L 早就有），保留，預設值不變無害。

### 3.3 XGB 特徵剪除（6 個共識 D 級特徵）— 否決

`GROUP_A_PLUS_FEATURE_SWEEP_HANDOFF_20260630.md` 的待辦事項。實際剪除
`volume_ratio_5/us_qqq_ret/vix_change/twii_ret/vix_change_x_return1d/n225_x_twii_ret` 並重訓驗證：

| | H1 | H5 | H20 |
|---|---|---|---|
| 00631L | +0.0103 | -0.0053 | **-0.0107** |
| 00632R | +0.0114 | -0.0083 | **-0.0157** |

H1 進步，但 H5、H20（a2118 觸發邏輯最依賴的 horizon）兩檔都退步。**不採用，程式碼已完整還原**
（`scripts/misc/ncf_00631l.py`、`ncf_00632r.py`、`group_a_plus/integrations/global_features.py`），
還原後測試全過。推測原因：XGB 單模型審計的 IC/gain 排名不能直接轉移到 8 模型 blended ensemble 的實際貢獻。

---

## 四、架構層發現：Ensemble 全樣本權重導致 Panel 漂移（詳見同名 handoff）

在驗證 3.1 時意外發現：`scripts/misc/ncf_00631l.py`（~1888-1910 行）的 ensemble 權重是用**整個驗證集**算出
的單一組 AUC/Brier 權重，套用到 panel 裡每一天的預測。驗證集每多一天，全部 8 個模型的 AUC/Brier 微幅變動 →
權重重分配 → panel 裡**所有歷史日期**的機率/信心值全部跟著漂移，即使那天的特徵完全沒變。已排除隨機性
（所有模型都 `random_state=42`/`seed=42`）。

**影響範圍比任何單一參數決策都更根本**：BayesOpt sweep、機會成本網格、multiyear walk-forward 這些依賴
「固定歷史 panel 觸發日期」的分析方法，都建立在一個會漂移的地基上。

架構修正（改成 rolling/expanding-window 權重）範圍很大，會讓所有下游分析結論都要重新驗證，**本 session
決定先記錄不立刻動**。完整細節、下次要修正時的建議做法見 `NCF_PANEL_GLOBAL_WEIGHT_DRIFT_HANDOFF_20260702.md`。

---

## 五、順手修正的小 bug

`group_a_plus/runners/a2118.py`、`group_a_plus/runners/a2111.py` 的 `--end` CLI 參數預設值原本寫死
`"2026-06-25"`，不會自動抓最新日期，跑回測沒帶 `--end` 會 silently 少算最近幾天資料。已改成預設 `"latest"`，
新增 `_resolve_end_date()` 解析成 DB 裡最新的 OHLCV 日期（跟 `ncf_00631l.py` 的 `resolve_end_date()` 同樣邏輯）。
77 個相關測試全過。這兩個檔案本身仍是跟 bond30c30/tight entry 等其他分支工作混在一起的未 commit WIP 狀態，
這次的小修正沒有另外 commit。

---

## 六、目前 Repo 狀態總結

- **git HEAD：** `783b6bb`（本 session 唯一的 commit，訊號層改進）
- **Active a2118 參數：** `h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55`（未變動）
- **仍未 commit 的檔案：** 大量其他分頭實驗（feature sweep 相關腳本、alphagen-lite、event-driven sentiment 等），
  跟本 session 處理的項目是不同主題，未動它們。
- **待決策/待辦事項：**
  1. 是否要投入資源重寫 ensemble 權重為 rolling/expanding-window（架構層改動，範圍大）
  2. XGB 特徵剪除若要重試，建議先做 permutation importance on full blended ensemble，而非單一 XGB gain/IC
  3. `NCF_ENSEMBLE_CALIBRATION_HANDOFF_20260701.md` 原本規劃的「把校準接受條件跟權重公式拆開分別驗證」尚未做

## 相關檔案索引

| 檔案 | 說明 |
|------|------|
| `NCF_PANEL_GLOBAL_WEIGHT_DRIFT_HANDOFF_20260702.md` | 第四節根因發現的完整細節 |
| `NCF_ENSEMBLE_CALIBRATION_HANDOFF_20260701.md` | calib_frac 實驗的原始背景與程式碼改動細節 |
| `GROUP_A_PLUS_FEATURE_SWEEP_HANDOFF_20260630.md` | BayesOpt 與 XGB 審計原始分析 |
| `results/ncf_00631l_panel_latest_20260701.csv` | 含 7/1 資料的最新 panel（回補後自動化產生）|
| `report/group_a_plus/latest/strategy.json` | 目前生效策略與參數 |

---
*Generated by Claude Code — 2026-07-02*
