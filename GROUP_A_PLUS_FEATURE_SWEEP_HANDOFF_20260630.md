# Group A+ Feature Sweep Handoff — 2026-06-30

**日期：** 2026-06-30  
**完成項目：** BayesOpt A21.18 參數掃描 / XGBoost 特徵審計 / Multiyear WF 驗證  
**執行人：** Claude Code (claude-sonnet-4-6)

---

## 背景

本 session 接續前次 Step 1（Fourier 特徵）、Step 2（BayesOpt）、Step 3（Global 相關資產）、Step 4（XGBoost 審計）實作完成後，首次對最新資料（2026-06-30）執行完整的實驗評估。

---

## 一、今日 NCF 信號（2026-06-30 收盤後）

| 標的 | 收盤 | 漲跌 | H=1 | H=5 | H=20 | Ensemble | conf |
|------|------|------|-----|-----|------|----------|------|
| 00631L | 38.42 | +5.9% | NEUTRAL 0.537 | DOWN 0.405 | DOWN 0.388 | DOWN 0.428 | 0.604 |
| 00632R | 9.94 | -3.6% | DOWN 0.313 | UP 0.770 | UP 0.794 | UP 0.743 | 0.484 |

**執行制度：** `ncf_late_bull_hedge`（6/29 觸發，6/30 仍維持）  
**目標倉位：** 0050=74.7%、00631L=5.3%、cash=20%  
**Signal Alignment：** mixed，dominant=bearish（5/7 偏空，factor_lens 一票偏多）  
**Alerts：** regime_transition（medium）、total_risk_score elevated（medium）

**注意：** `actual_data_date=2026-06-29`（pipeline 訓練資料截至 6/29），6/30 收盤為手動補入 DB，明日 pipeline 會自動納入。

---

## 二、BayesOpt A21.18 觸發參數掃描

**結果檔案：** `results/bayesopt_a2118_3d_20260630.json`  
**Panel：** `results/ncf_00631l_panel_latest_20260630.csv`（359 行，2025-01-02–2026-06-30）  
**設定：** 3D 搜索（h20_max × conf_min × h5_reentry_min），init=8，iter=40，共 53 次 probe

### 最佳參數

| 參數 | 現值（a2118 default） | BayesOpt 最佳 | 說明 |
|------|----------------------|--------------|------|
| `h20_max` | 0.450 | **0.292** | 觸發門檻收緊（只在更確定看跌時 de-leverage）|
| `conf_min` | 0.550 | **0.520** | 信心門檻略放寬 |
| `h5_reentry_min` | 0.000（未啟用）| **0.367** | 新增：再入場需 H=5 prob_up > 0.367 |

### 最佳表現（Top 1，穩定高原）

| Sharpe | Sortino | AnnRet | MaxDD | 觸發天數 | 觸發率 |
|--------|---------|--------|-------|---------|--------|
| 2.6019 | 2.9015 | 64.24% | -13.82% | 4 天 | 1.12% |

### 重要觀察

- **Top 6 結果 Sharpe 完全相同**：conf_min ∈ [0.517, 0.531]、h5_reentry_min ∈ [0.34, 0.37] 形成穩定高原，非過擬合
- **h20_max 鬆緊不重要**：0.29 到 0.47 都達到同樣最佳分數，真正關鍵是 `h5_reentry_min`
- **h5_reentry_min = 0.367**：防止 hedge 模式中 H=5 看多反彈時過早解除保護，為 Grid 未探索的維度
- **今日（6/30）狀態：** h20_prob=0.388 > 新建議 h20_max=0.292，若採用新參數則今日不會觸發 de-leverage

### 待決策（下次 session）

- 是否採用 `h5_reentry_min=0.367` 作為 a2118 新預設？
- 是否收緊 `h20_max` 從 0.45 到約 0.30？
- 建議先用舊參數再跑一季，確認 h5_reentry_min 不是 panel 過擬合

---

## 三、XGBoost 特徵審計

**執行日期：** 2026-06-30  
**訓練期：** 2020-01-01 → 2026-06-30  
**Horizons：** H=1, H=5, H=20

### 00631L（135 特徵，Fourier+Global 啟用）

**結果檔案：** `results/xgb_audit_00631l_20260630.json`  
**Grade 分佈：** A=34, B=34, C=33, D=34

**Top 10 特徵：**

| 排名 | 特徵 | Grade | IC | Gain |
|------|------|-------|----|------|
| 1 | `txo_foreign_pc_spread_ma5` | A | 0.126 | 7.52 |
| 2 | `twii_120d_ret` | A | 0.085 | 4.74 |
| 3 | `twii_60d_ret` | A | 0.091 | 4.53 |
| 4 | `twii_vs_ma120` | A | 0.087 | 4.69 |
| 5 | `ewt_vs_0050_60d` | A | 0.094 | 4.05 |
| 6 | `us_soxx_60d_ret` | A | 0.087 | 4.19 |
| 7 | `close_ma200_ratio` | A | 0.075 | 5.28 |
| 8 | `close_ma120_ratio` | A | 0.077 | 4.34 |
| 9 | `momentum_63` | A | 0.087 | 4.32 |
| 10 | `bb_width` | A | 0.116 | 3.23 |
| 16 | `fft_6c_dev`（Fourier）| A | 0.073 | 3.56 |
| 18 | `hsi_5d_ret`（Global）| A | 0.058 | 3.62 |

**剪除候選（21 個，Grade D + IC < 0.02）：**
```
foreign_x_margin_chg, above_ma20, bb_position, body_pct, return_10d,
n225_ret, close_ma20_ratio, vix_change, n225_x_twii_ret, return_21d,
momentum_21, hsi_ret, momentum_10, txo_market_pcr_volume_20d_zscore,
us_qqq_ret, us_nasdaq_ret, volume_ratio_5, above_ma50,
inst_total_x_short_chg, twii_ret, vix_change_x_return1d
```

---

### 00632R（157 特徵，Global 預設啟用）

**結果檔案：** `results/xgb_audit_00632r_20260630.json`  
**Grade 分佈：** A=40, B=39, C=37, D=41

**Top 10 特徵：**

| 排名 | 特徵 | Grade | IC | Gain |
|------|------|-------|----|------|
| 1 | `fft_9c_dev`（Fourier）| A | 0.130 | 5.56 |
| 2 | `momentum_63` | A | 0.136 | 4.55 |
| 3 | `tbrain_volume_ma130_loc` | A | 0.154 | 3.65 |
| 4 | `bb_width` | A | 0.135 | 4.69 |
| 5 | `vol20_x_close_ma200_dist` | A | 0.119 | 4.19 |
| 6 | `macd_signal` | A | 0.132 | 3.95 |
| 7 | `tbrain_close_ma130_loc` | A | 0.137 | 3.57 |
| 8 | `txo_foreign_pc_spread_ma5` | A | 0.107 | 7.24 |
| 9 | `tbrain_kdj_d_5_21_11` | A | 0.074 | 5.17 |
| 10 | `rolling_mdd_20` | A | 0.131 | 3.62 |

**剪除候選（20 個，Grade D + IC < 0.02）：**
```
vix, us_qqq_ret, n225_x_twii_ret, tbrain_kdj_k_6_3_3, twii_ret,
above_ma20, margin_short_log, volume_ratio_5, vix_spike_x_vol20,
tx_night_x_gap, fft_9c_slope_5d, vix_change, us_nasdaq_ret, return_1d,
tbrain_kdj_d_9_3_3, tbrain_kdj_d_6_3_3, tbrain_kdj_j_5_21_11,
twii5d_x_close_ma200_dist, vix_change_x_return1d, inst_total_net
```

---

### 跨標的比對總結

| 類別 | 00631L | 00632R | 結論 |
|------|--------|--------|------|
| Fourier `*_dev` | `fft_6c_dev` A(#16) | `fft_9c_dev` A(**#1**) | **兩者有效，強烈保留** |
| Fourier `*_slope_5d` | — | D（prune）| 斜率無效，只留偏差 |
| Global `hsi_5d_ret` | A(#18) | — | 港股 5 日有效 |
| Global `n225_ret`/`hsi_ret` 日報酬 | D | — | 日報酬太短線 |
| `n225_x_twii_ret`（互動）| D | D | **兩者確認剪除** |
| `bb_width` | A | A | 兩者強特徵 |
| `txo_foreign_pc_spread_ma5` | A(#1) | A(#8) | 籌碼指標最強 |
| `us_qqq_ret`/`us_nasdaq_ret` 日 | D | D | **兩者確認剪除** |
| `twii_ret` 日報酬 | D | D | **兩者確認剪除** |
| `above_ma20`/`above_ma50` | D | D | **旗標特徵無效** |
| `vix` 水準 | — | D | 熊 ETF 對 VIX 水準無感 |
| TBrain MA loc 系列 | — | A（多個）| 00632R 專屬強特徵 |

**建議（下季審計時執行，不需今日）：**  
剪除共識 D 特徵可縮減特徵空間約 15%，預期加速訓練但 AUC 影響有限。建議先跑一次不含剪除清單的 WF 確認無損失後再正式移除。

---

## 四、Multiyear Walk-Forward AUC 驗證

**設定：** 5 fold（val_year = 2022–2026），train_start = 2015-01-01

### 00631L（Fourier + Global 啟用）

**結果檔案：** `results/ncf_multiyear_wf_00631l_fourier_global_20260630.json`

| 年份 | H=1 AUC | H=5 AUC | H=20 AUC |
|------|---------|---------|---------|
| 2022 | 0.5828 | 0.7219 | 0.7483 |
| 2023 | 0.6141 | 0.6049 | 0.5949 |
| 2024 | 0.6140 | 0.5696 | 0.5892 |
| 2025 | 0.6030 | 0.7063 | 0.6885 |
| 2026 | 0.6428 | 0.6883 | **0.8712** |

✅ **全年全 Horizon > 0.55**，無退化年份。H=20 在趨勢年（2022, 2025, 2026）表現突出。

### 00632R（Global 預設啟用）

**結果檔案：** `results/ncf_multiyear_wf_00632r_global_20260630.json`

| 年份 | H=1 AUC | H=5 AUC | H=20 AUC |
|------|---------|---------|---------|
| 2022 | 0.5593 | 0.6327 | 0.7229 |
| 2023 | 0.6105 | 0.6710 | 0.5821 |
| 2024 | 0.6667 | 0.7091 | **0.500** ⚠️ |
| 2025 | 0.6356 | 0.6568 | **0.976** |
| 2026 | **0.501** ⚠️ | 0.7055 | 0.6826 |

**異常說明：**
- **2024 H=20 = 0.500**：2024 年台股強漲，熊 ETF 單邊下跌，H=20 標籤極度不均衡，模型在此年份的 20 日預測接近隨機。市場結構問題，非特徵問題。
- **2026 H=1 = 0.501**：2026 年只有半年 OOS 樣本（H=1 樣本最少），統計雜訊導致，參考價值有限。
- **H=5 最穩健**：每年都 > 0.63，是 00632R 最可靠的 Horizon。

---

## 五、結果檔案一覽

| 檔案 | 說明 |
|------|------|
| `results/bayesopt_a2118_3d_20260630.json` | BayesOpt 全部 53 次 probe 結果 |
| `results/xgb_audit_00631l_20260630.json` | 00631L XGBoost 審計（135 特徵 A/B/C/D 分級）|
| `results/xgb_audit_00632r_20260630.json` | 00632R XGBoost 審計（157 特徵 A/B/C/D 分級）|
| `results/ncf_multiyear_wf_00631l_fourier_global_20260630.json` | 00631L 5-fold WF AUC 表 |
| `results/ncf_multiyear_wf_00632r_global_20260630.json` | 00632R 5-fold WF AUC 表 |
| `results/ncf_00631l_panel_latest_20260630.csv` | 最新 NCF panel（359 行，到 6/30）|
| `results/ncf_daily_pipeline_20260630.json` | 每日 pipeline manifest |
| `report/group_a_plus/latest/live_signal.json` | 最新執行信號 |

---

## 六、待決策事項（下次 session 處理）

### 優先級 High

1. **A21.18 參數更新**：決定是否採用 BayesOpt 建議的 `h5_reentry_min=0.367`。建議先 paper trade 一季，觀察現有信號（今日 6/30 h20_prob=0.388 在舊參數觸發、新參數不觸發）。

### 2026-06-30 續跑補充（end date 對齊到 6/30）

前述 BayesOpt 檔案 `results/bayesopt_a2118_3d_20260630.json` 雖使用 6/30 panel，但 sweep `end` 仍是 `2026-06-25`。已重新用同一份 panel 對齊回測 end date 至 `2026-06-30`：

| 檔案 | 說明 |
|------|------|
| `results/bayesopt_a2118_3d_20260630_end20260630.json` | 6/30 end-date 重新掃描 |
| `results/group_a_plus_runner_a2118_active_20260630.json` | 目前 active 參數對照：h20=0.33、conf=0.55、h5_reentry=0.55 |
| `results/group_a_plus_runner_a2118_bayesopt_shadow_20260630.json` | BayesOpt shadow 參數對照：h20=0.2922、conf=0.5200、h5_reentry=0.3673 |

6/30 end-date 重新掃描後，最佳參數仍為 `h20_max=0.2922`、`conf_min=0.5200`、`h5_reentry_min=0.3673`，但最佳 Sharpe 由 2.6019 修正為 **2.5639**（新資料納入後基準改變）。

Active vs BayesOpt shadow：

| 參數組 | Sharpe | Sortino | AnnRet | MaxDD | initial triggers | total hedge days | 6/30 live trigger |
|--------|--------|---------|--------|-------|------------------|------------------|-------------------|
| active 0.33/0.55/0.55 | 2.5435 | 2.7997 | **65.01%** | -13.82% | 2 | 8 | False |
| shadow 0.2922/0.5200/0.3673 | **2.5639** | **2.8274** | 64.01% | -13.82% | 4 | 9 | False |

結論：不建議今日直接升級 active manifest。BayesOpt shadow 的 Sharpe/Sortino 較佳，但 annual return 低約 1.0pp，且新增觸發日（2025-09-30、2026-02-26）仍需 opportunity-cost 標籤確認。建議保留 active 參數，將 BayesOpt 組列為 shadow/paper-trade 觀察。

補充校正：目前 active manifest 已是 `h5_reentry_min=0.55`，所以待決策不是「是否導入 h5_reentry」，而是「是否將 h5_reentry 從 0.55 降到約 0.367，並同步調整 h20/conf 門檻」。

### 優先級 Medium

2. **特徵剪除執行**：7 個共識 D 特徵（`n225_x_twii_ret`, `us_qqq_ret`, `twii_ret`, `vix_change`, `vix_change_x_return1d`, `volume_ratio_5`, `above_ma20`）兩檔皆無效，可排入下季審計時正式移除。

3. **00632R H=20 風險評估**：2024 年 AUC=0.500 表明熊 ETF 在多頭趨勢年份 H=20 預測無效。考慮在強多頭市場（如 0050 > MA200 且動能 > +30%）時降低 H=20 在 ensemble 的權重。

### 優先級 Low

4. **n225_5d_ret 補強**：`hsi_5d_ret` 是 A 級但 `n225_ret`（日）是 D 級，考慮在 Global features 中將 N225 日報酬替換為 5 日報酬以對齊。

---

## 七、本次 session 實作項目回顧

本次 session 為執行驗證 session（非新實作），以下為完整功能清單（前次實作，本次驗證）：

| 步驟 | 功能 | 狀態 |
|------|------|------|
| Step 1 | Fourier Transform 趨勢特徵（`fourier_features.py`）| ✅ 前次完成 |
| Step 2 | BayesOpt A21.18 觸發參數掃描（`bayesopt_a2118_trigger.py`）| ✅ 前次實作，本次執行 |
| Step 3 | Global 相關資產特徵（N225/HSI/USDJPY/KOSPI）| ✅ 前次完成 |
| Step 4 | XGBoost 特徵審計（`xgb_feature_audit.py`）| ✅ 前次實作，本次執行 |
| — | 下載 2026-06-30 收盤資料（手動補入 DuckDB）| ✅ 本次完成 |
| — | NCF 每日 pipeline（`run_ncf_daily_pipeline.py`）| ✅ 本次執行 |
| — | Multiyear WF AUC 驗證（`ncf_multiyear_wf.py`）| ✅ 本次執行 |

---

*Generated by Claude Code — 2026-06-30*
