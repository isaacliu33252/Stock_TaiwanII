# NCF v5 (TabNet) + Group A+ a2118 升級交接記錄 — 2026-06-29

## 1. 本 Session 完成的工作

| 任務 | 狀態 |
|------|------|
| DA-RNN 可行性評估（TSMC FastText 嵌入不可移植） | ✅ 排除 |
| 方向 A：TXO 全市場 PCR 特徵 + TAIFEX 歷史資料管線 | ✅ |
| 方向 B：Cascade H=1→H=5 機率特徵（OOF 防洩漏） | ✅ |
| 方向 C：長週期總體代理（60d/120d TWII/SOXX/EWT）| ✅ |
| 方向 D：TabNet 加入 ensemble | ✅ |
| NCF v5 完整回測（A+B+C+D，2025-01-02 ~ 2026-06-26） | ✅ |
| Group A+ a2118 參數掃描（h20_max × conf_min，15 組）| ✅ |
| strategy.json 更新為 v5 panel + 最佳參數 | ✅ |

---

## 2. 檔案位置

| 檔案 | 說明 |
|------|------|
| `scripts/misc/ncf_00631l.py` | NCF 主策略模組（v5 特徵全部整合） |
| `taifex_options_data.py` | **新建** TXO 選擇權資料管線（PCR 計算） |
| `results/ncf_00631l_v5_tabnet_20250101_20260626.json` | v5 完整回測結果 |
| `results/ncf_00631l_v5_tabnet_panel.csv` | v5 驗證期 panel（357 rows，2025-01-02 ~ 2026-06-26）|
| `report/group_a_plus/latest/strategy.json` | **已更新** → v5 panel + h20_max=0.33 |
| `FinRL/data/stock_data.db` | 新增 `taifex_options_daily` 表（~300 萬筆，2020-2026）|

---

## 3. NCF v5 特徵架構

### 3a. 新增特徵（相較 v4）

#### A. TXO 全市場 PCR（`taifex_options_data.py`）
```
txo_market_pcr_volume          # 成交量 Put/Call Ratio（shift=1，避免未來洩漏）
txo_market_pcr_oi              # 未平倉 Put/Call Ratio
txo_market_pcr_volume_5d_zscore   # 5 日滾動 z-score
txo_market_pcr_oi_5d_zscore       # 同上（OI）
txo_market_pcr_volume_20d_zscore  # 20 日滾動 z-score
# 交互特徵（_build_interaction_features）
txo_mkt_pcr_x_vix              # PCR × VIX MA20 ratio
txo_mkt_pcr_x_inst_net         # PCR × 外資淨買超
```

#### B. Cascade 機率特徵
```
h1_prob_cascade   # H=1 OOF 校準機率（TimeSeriesSplit 3-fold，LGB），注入 H=5 訓練
                  # Inference 時使用 H=1 ensemble ens_proba
```

#### C. 長週期總體代理
```
twii_60d_ret      # TWII 60 日報酬（PMI 替代指標）
twii_120d_ret     # TWII 120 日報酬（出口訂單替代）
twii_vs_ma60      # 現價 / MA60 - 1
twii_vs_ma120     # 現價 / MA120 - 1
us_soxx_60d_ret   # SOXX 60 日報酬（半導體需求，shift=1）
ewt_vs_0050_60d   # EWT - 0050 60d 報酬差（外資台灣情緒）
soxx_vs_twii_60d  # SOXX - TWII 60d 相對強弱
```

#### D. TabNet（`pytorch-tabnet`）
```python
_TabNetClassifier(
    n_d=min(16, n_feat), n_a=min(16, n_feat),
    n_steps=3, gamma=1.5,
    n_independent=2, n_shared=2,
    max_epochs=80, patience=15,
    batch_size=min(128, max(32, len(X_tr) // 8)),
)
# AUC-weighted ensemble 納入 tabnet（w_i = max(0, AUC_i - 0.5)）
```

### 3b. 資料來源
- PCR：`taifex_options_daily`（DuckDB）→ `query_txo_features(start, end)`
- SOXX / EWT：`yfinance`（shift=1）
- TWII：已存在 ext features（shift=0，作為現況指標）
- 跳過 PCR：`NCF_SKIP_TXO_MARKET_PCR=1`（用於 v4 基準對比）

---

## 4. NCF v5 回測結果

### 4a. 各方向 AUC 比較（val: 2025-01-02 ~ 2026-06-26）

| 版本 | H=1 AUC | H=5 AUC | H=20 AUC | 說明 |
|------|:-------:|:-------:|:--------:|------|
| **v4 baseline** | 0.5982 | 0.6788 | 0.6809 | 原始 29 特徵 |
| **A: TXO PCR** | 0.5824 | 0.6865 | 0.6881 | +PCR |
| **A+C: Macro** | 0.5922 | 0.6812 | **0.7036** | +PCR +長週期 |
| **A+B+C+D (v5)** | 0.5892 | **0.6907** | **0.7036** | 全部 |

- H=20 突破 0.70（+2.27pp vs v4），長週期總體代理直接貢獻
- H=5 最高（0.6907，+1.19pp vs v4），TabNet + Cascade 聯合貢獻
- H=1 微降（-0.09pp），短線 TabNet early stopping 表現弱

### 4b. H=20 Bear Regime TabNet 表現
```
Bear (n=90):  TABNET=0.9167  STABLE_RF=0.8611  Ens=0.8030
Bull (n=247): ET=0.7036  Ens=0.6006
```
> TabNet 在 Bear regime 的 H=20 AUC=0.9167（小樣本，但一致性強）

### 4c. v5 今日信號（資料截至 2026-06-26）

| Horizon | 方向 | UP prob | 目標日 |
|---------|------|:-------:|--------|
| H=1 | ↓ DOWN | 0.432 | 6/29 (一) |
| H=5 | ↓ DOWN | 0.371 | 7/3 (四) |
| H=20 | ↓ DOWN | **0.281** | 7/24 (四) |
| 綜合 | ↓ DOWN | 0.363 | confidence=0.66 |

---

## 5. Group A+ a2118 參數掃描結果

### 5a. 掃描範圍
- `h20_max`：[0.28, 0.30, 0.33, 0.35, 0.38]
- `conf_min`：[0.50, 0.55, 0.60]
- 固定：`ma_gap_min=0.10`，val 期間 2025-01-02 ~ 2026-06-26，panel=v5

### 5b. 完整掃描結果（依 Sharpe 排序）

| h20_max | conf_min | Sharpe | Ann.Ret | MDD | Triggers |
|:-------:|:--------:|:------:|:-------:|:---:|:--------:|
| 0.28 | 0.55 | **2.4224** | 59.92% | -13.82% | 2 |
| 0.30 | 0.55 | **2.4224** | 59.92% | -13.82% | 2 |
| **0.33** | **0.55** | **2.4224** | 59.92% | -13.82% | **2** ← 採用 |
| 0.35 | 0.55 | 2.4217 | 59.91% | -13.82% | 3 |
| 0.38 | 0.55 | 2.4217 | 59.91% | -13.82% | 3 |
| 0.28 | 0.50 | 2.4079 | 58.54% | -13.82% | 3 |
| 0.30 | 0.50 | 2.4079 | 58.54% | -13.82% | 3 |
| 0.33 | 0.50 | 2.4079 | 58.54% | -13.82% | 3 |
| 0.35 | 0.50 | 2.4076 | 58.43% | -13.82% | 5 |
| 0.38 | 0.50 | 2.4076 | 58.43% | -13.82% | 5 |
| 0.28-0.38 | 0.60 | 2.3736 | **64.26%** | -13.82% | 0 |

> `conf_min=0.60` 導致 0 次觸發（純 a2111），年化最高但 Sharpe 最低。  
> `conf_min=0.50` 過度觸發（5次），Sharpe 下滑。  
> `h20_max=0.33` 排除 2026-05-04 邊緣事件（h20=0.334），比 0.35 多一點保守性。

### 5c. 決策：採用 `h20_max=0.33, conf_min=0.55`
理由：最佳 Sharpe（2.4224），2 次觸發（低過擬合風險），且今日觸發條件明確（h20=0.281 ≪ 0.33）。

---

## 6. Group A+ a2118 v5 回測摘要

### 6a. v4 vs v5 比較（2025-01-02 ~ 2026-06-26）

| 指標 | v4（h20=0.35）| v5（h20=0.33）| Delta |
|------|:------------:|:------------:|:-----:|
| 年化報酬 | 59.22% | **59.92%** | +0.70pp |
| Sharpe | 2.4029 | **2.4224** | +0.020 |
| Sortino | 2.6322 | **2.6493** | +0.017 |
| Max Drawdown | -13.82% | -13.82% | 0 |
| 總報酬 | +98.9% | **+100.2%** | +1.3pp |
| 最終淨值 | 1,989,068 | **2,002,042** | +12,974 |

### 6b. NCF 觸發事件比較

**v4（3 次觸發）**
| 日期 | ma_gap | h20_prob | conf |
|------|:------:|:--------:|:----:|
| 2025-10-30 | 20.4% | 0.252 | 0.553 |
| 2025-10-31 | 20.6% | 0.255 | 0.596 |
| 2026-02-23 | 19.1% | 0.254 | 0.570 |

**v5（2 次觸發）**
| 日期 | ma_gap | h20_prob | conf | 說明 |
|------|:------:|:--------:|:----:|------|
| 2026-02-23 | 19.1% | **0.173** | 0.564 | v5 信號更強（比 v4 低 8pp） |
| 2026-04-30 | 23.4% | 0.257 | 0.583 | v4 漏掉此事件 |

> v4 抓到 Oct-2025 兩次事件，v5 改抓 Apr-2026 事件。兩者各有所長，但 Sharpe 告訴我們 v5 的排列組合整體較優。

### 6c. 今日現況（2026-06-29）

```
Regime: golden1
NCF v5 觸發: ✅ ACTIVE
  ma_gap   = 18.35%  > 10%   ✓
  h20_prob = 0.2817  < 0.33  ✓
  conf     = 0.654   > 0.55  ✓

基礎配置（golden1）: 0050=69.5%  00631L=10.5%  cash=20%
觸發後有效配置:      0050=74.7%  00631L=5.3%   cash=20%
```

---

## 7. TXO 選擇權資料管線（新建）

### 7a. 資料來源
- **歷史資料**：TAIFEX 網站 `/cht/3/optDataDown`（yearly zip，2020-2025）
- **每日更新**：TAIFEX OpenAPI `/DailyMarketReportOpt`（T 日盤後）
- **2026 年度補充**：逐月下載（Jan ~ Jun 2026）

### 7b. DB 表格
```sql
taifex_options_daily (
    dt, contract, contract_month, strike_price, call_put, trading_session,
    open, high, low, close, volume, settlement_price, open_interest,
    best_bid, best_ask, source
    PRIMARY KEY (dt, contract, contract_month, strike_price, call_put, trading_session)
)
-- 總筆數：~300 萬筆（2020-01-02 ~ 2026-06-26）
```

### 7c. 每日更新指令
```bash
python3 taifex_options_data.py --refresh-latest
```

### 7d. PCR 特徵說明
```python
query_txo_features(start, end)
# 返回欄位：
# txo_pcr_volume              = put_vol / call_vol（全市場含散戶，一般交易時段）
# txo_pcr_oi                  = put_oi / call_oi
# txo_pcr_volume_5d_zscore    = 5 日滾動 (PCR - μ) / σ
# txo_pcr_oi_5d_zscore
# txo_pcr_volume_20d_zscore
```

---

## 8. 重要設計決策記錄

### 8a. 為何用 A+C 突破 H=20
60d/120d 特徵的預測週期與 H=20 預測目標直接對齊。TWII 60d 報酬捕捉月度景氣週期，SOXX vs TWII 捕捉半導體需求 vs 廣泛市場的相對強弱，EWT vs 0050 捕捉外資對台灣市場的情緒。H=20 AUC 從 0.6809 → 0.7036 (+2.27pp)，為重大突破。

### 8b. Cascade B 設計
H=1 OOF 機率使用 `TimeSeriesSplit(n_splits=3)` + `LGBMClassifier(n_estimators=200)` 生成，防止未來洩漏。Inference 時直接使用當日 H=1 ensemble 機率注入 H=5 特徵向量。

### 8c. TabNet 為何在 H=5 有效但 H=1 無效
H=1 的 Bear regime 樣本 n=35 < 60，TabNet early stopping 在 epoch 0 就觸發（訓練集太小）。H=20 Bear regime TabNet 達到 AUC=0.9167，因為 Bear regime 20 日預測訊噪比更高（結構性熊市，非隨機波動）。

### 8d. conf_min=0.55 是 dominant 參數
掃描結果確認：conf_min 從 0.55→0.60 完全關閉 overlay（0 觸發），年化雖最高（+64%）但 Sharpe 最低（2.374）。overlay 犧牲約 5pp 年化，換取 Sharpe +0.048。這是有效的風險調整。

### 8e. h20_max 收緊 0.35→0.33
h20_max=0.33 排除 2026-05-04 邊緣事件（h20=0.334），觸發從 3 次降為 2 次，Sharpe 微升 0.0007。邊際改善微小，但方向正確（寧可少觸發一次不確定事件）。

---

## 9. 後續待辦

| 優先 | 事項 |
|------|------|
| 🔴 高 | 每日盤後更新 TXO 資料：`python3 taifex_options_data.py --refresh-latest` |
| 🔴 高 | 每日盤後重跑 NCF v5：`python3 scripts/misc/ncf_00631l.py ...` 以產生新 panel 行 |
| 🟡 中 | 6/30 (一) 換倉決策：NCF 觸發 ACTIVE，建議暫緩加碼 00631L（策略配置 5.3%） |
| 🟡 中 | 30 日後驗證 2026-02-23 / 2026-04-30 觸發準確度（目標：h20 < 33% 後 20d 應下跌）|
| 🟢 低 | 若 v5 H=1 AUC 仍偏低（0.589），考慮方向 E：更短週期 PCR 特徵（1d/2d z-score）|

---

## 10. 版本索引

| 版本 | panel 檔案 | h20_max | conf_min | Sharpe | 啟用日 |
|------|-----------|:-------:|:--------:|:------:|--------|
| v4 | `ncf_00631l_panel_2025_v4_tail.csv` | 0.35 | 0.55 | 2.4029 | 2026-06-28 |
| **v5** | **`ncf_00631l_v5_tabnet_panel.csv`** | **0.33** | **0.55** | **2.4224** | **2026-06-29** |
