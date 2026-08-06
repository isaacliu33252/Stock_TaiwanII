# Group A+ 交接記錄 — 2026-06-26

## 本次工作摘要

Active 策略維持不變：**A21.11（a2111_tight_entry_bond30c30）**  
本次新增三個 research candidate（A21.12、A21.13、A21.14），均不升格。

---

## 1. A21.12 — MA80 + low_risk_exit（被拒絕）

### 設計
| 參數 | 值 |
|------|----|
| MA window | 80（A21.11 是 100） |
| entry_gap | 0.003 |
| exit_gap | 0.010 |
| low_risk_exit | ma_gap=0.003，score≤1 時快速出場 |
| basket | bond30_cash30（與 A21.11 相同） |

### 回測結果（2025-01-02 ~ 2026-06-25）
| 指標 | A21.11（active） | A21.12（拒絕） |
|------|-----------------|---------------|
| Sharpe | 2.5216 | 2.4463 |
| MDD | -13.92% | -16.50% |
| Regime 切換 | 2 次 | 6 次 |

### 拒絕原因
MA80 在 2025 年 2 月造成 2 次額外假訊號進場（whipsaw），導致 4 次多餘切換。  
MA100 正確過濾這些假訊號。**MA80 窗口對當前市場過於敏感。**

### 程式碼
- `group_a_plus/runners/a2112.py`（status: research_candidate）
- `results/group_a_plus_runner_a2112.json`
- 24 個測試通過（`tests/test_group_a_plus_a2112.py`）

---

## 2. A21.13 — A21.11 + NCF Daily Overlay（不升格）

### 設計
歷史回測邏輯 = A21.11（不變）  
live 增強：每日根據 ncf_00631l / ncf_00632r 訊號調整 golden1 中的 00631L 配置

**NCF composite downside signal：**
```
downside = 0.6 × l_bear + 0.4 × r_bull
l_bear   = max(0, 0.5 − P(00631L↑)) × 2 × conf_631l
r_bull   = max(0, P(00632R↑) − 0.5) × 2 × conf_632r
adjusted_00631L = base × (1 − 0.5 × downside)  → 最多減倉 50%
```

### 回測結果（2025-01-02 ~ 2026-06-25）
| 指標 | A21.11（active） | A21.13 v3（最新） |
|------|-----------------|-----------------|
| Sharpe | 2.5216 | 2.5317 |
| MDD | -13.92% | -14.46% |
| 總報酬 | +133.4% | +114.6%（**-18.8pp**） |
| 年化報酬 | ~80% | 67.8% |

### 不升格原因（根本問題）
資料顯示 NCF 訊號在 golden1 期間方向性反轉：

| 情境 | 說明 |
|------|------|
| NCF 觸發（ensemble > 0.05），n=82 天 | 隔日 0050 報酬 **0.301%** |
| 無訊號，n=107 天 | 隔日 0050 報酬 0.285% |
| → | **NCF 觸發時市場反而更好** |

Golden1 期間 NCF 觸發率 59.8%（266 天中 159 天），每日削減 00631L 0.474%，累計 266 天造成 -18.8pp 總報酬損失。NCF 在真正熊市（2025-02/03：-14.9%）沉默，卻在最強多頭月（2026-04/05：+35.7%）大量觸發。

### 程式碼
- `group_a_plus/runners/a2113.py`（含 `--ncf-panel-631l/632r` 歷史回測模式）
- `group_a_plus/integrations/ncf.py`（NCF signal helper）
- `results/group_a_plus_runner_a2113_v3.json`（v2 panel 歷史回測，最新）
- 24 個測試通過（`tests/test_group_a_plus_ncf_integration.py`）

---

## 3. A21.14 — A21.11 + NCF Exit Gate（不升格，待未來驗證）

### 設計動機
A21.13 的根本問題是 NCF 每日干擾 golden1 配置。A21.14 改為：
- **Golden1 內部完全不動**（不做任何日內 allocation 調整）
- NCF 只用於「接近 MA100 時的提前出場」和「回復 golden1 的延遲進場」

### NCF Exit Gate 觸發條件（四個 AND）
1. 當前 regime = golden1
2. NCF H20 dual-confirm > 0.35（631L H20 < 0.40 且 632R H20 > 0.60 同時成立）
3. 連續 ≥ 3 個交易日信號持續
4. ma_gap < 3%（市場仍在 MA100 附近，非強勁多頭）

### NCF Recovery Gate 觸發條件
A21.11 準備切回 golden1 時，若 NCF H20 dual-confirm > 0.30 → 延遲一天，次日重判。

### 回測結果（兩個期間）

**2025-01-02 ~ 2026-06-25（強多頭）**
| 指標 | A21.11 | A21.14 |
|------|--------|--------|
| Sharpe | 2.5216 | **2.5208（≈持平）** |
| MDD | -13.92% | **-13.92%（相同）** |
| 總報酬 | +133.4% | **+133.6%** |
| Exit gate 觸發 | — | **0 次** |

**2023-01-03 ~ 2026-05-27（含 2023 熊市）**
| 指標 | A21.11 | A21.14 |
|------|--------|--------|
| Sharpe | 2.0231 | **2.0245（+0.001）** |
| MDD | -24.00% | **-24.00%（相同）** |
| 總報酬 | +306.1% | **+306.8%（+0.7pp）** |
| Exit gate 觸發 | — | **0 次** |
| Recovery gate 觸發 | — | **4 天（2025-06-10 ~ 06-13）** |

### 為何 Exit Gate 未觸發

| 期間 | 原因 |
|------|------|
| 2025-2026 強多頭 | golden1 ma_gap 始終 > 3%，地理條件不滿足 → 正確沉默 |
| 2023-09~11 真熊市 | ma_gap 跌至 -4.4%，但 NCF H20 dual-confirm = 0.0（模型訓練到 2022 年底，2023 下跌看不到）|

### 重要機制說明
`_apply_ncf_gate()` 在呼叫 `_simulate_costed_curve` 前先預處理 `execution_regime` Series，不修改模擬邏輯本身，確保數值與 A21.11 一致。

### 程式碼
- `group_a_plus/runners/a2114.py`
- `results/group_a_plus_runner_a2114.json`（2025-2026）
- `results/group_a_plus_runner_a2114_2023_2026.json`（2023-2026）

---

## 4. NCF 模型 v2 升級

兩個 NCF 腳本均已升級，新增特徵與 Isotonic Regression 校準。

### AUC 改善（val period = 2025-01-02 ~ 2026-06-25）

**ncf_00631l（v1 → v2）**
| Horizon | 舊 AUC | 新 AUC | 差值 |
|---------|--------|--------|------|
| H1 | 0.540 | 0.566 | +0.026 |
| H5 | 0.592 | 0.641 | **+0.049** |
| H20 | 0.598 | 0.595 | 持平 |

**ncf_00632r（v1 → v2）**
| Horizon | 舊 AUC | 新 AUC | 差值 |
|---------|--------|--------|------|
| H1 | 0.546 | 0.557 | +0.011 |
| H5 | 0.592 | 0.663 | **+0.071** |
| H20 | 0.784 | 0.813 | **+0.029** |

### v2 改進內容（兩個腳本相同）
- 新特徵：`rsi_7`、`close_ma30_ratio`、`ma5_ma10_ratio`、`consecutive_up_days/down_days`
- 新外部特徵：`us_qqq_5d/10d_ret`、`vix_ma20_ratio`、`twii_5d_ret`、`eti0050_5d_ret`
- 00632R 額外：`eti0050_10d_ret`（inverse ETF 主要 driver）
- Isotonic Regression 校準（取代 Platt sigmoid）

### NCF Panel 生成指令
```bash
# v2 panel（A21.13/A21.14 歷史回測所需）
PYTHONPATH=. .venv/bin/python scripts/misc/ncf_00631l.py \
    --val-start 2025-01-02 \
    --val-predictions-output results/ncf_00631l_panel_2025_v2.csv

PYTHONPATH=. .venv/bin/python ncf_00632r.py \
    --val-start 2025-01-02 \
    --val-predictions-output results/ncf_00632r_panel_2025_v2.csv
```

### Panel 格式
| 欄位 | 說明 |
|------|------|
| `prob_up_h1/h5/h20` | 各 horizon UP 機率 |
| `ensemble_prob_up` | AUC 加權集成機率 |
| `direction` | UP / DOWN |
| `confidence` | 信心分數（0~1） |
| `h20_prob_up` | H20 UP 機率（v2 新增） |
| `h20_direction` | H20 方向（v2 新增） |

已生成 panel：
- `results/ncf_00631l_panel_2025_v2.csv`（336 rows）
- `results/ncf_00632r_panel_2025_v2.csv`（336 rows）
- `results/ncf_00631l_panel_2023.csv`（817 rows，2023-01 起，AUC 較低）
- `results/ncf_00632r_panel_2023.csv`（816 rows，同上）

---

## 5. A21.11 已知弱點

在 2020-2024 回測中發現：

| 期間 | Sharpe | MDD | 說明 |
|------|--------|-----|------|
| 2025-01~2026-06 | 2.5216 | -13.92% | 強多頭，表現良好 |
| 2023-01~2026-05 | 2.0231 | -24.00% | 2023-08 回撤造成 MDD |
| 2020-07~2024-12 | 1.1197 | **-31.26%** | **2022 整年留在 golden1** |

**2022 年熊市問題**：A21.11 的防禦切換需要 `total_risk_score ≥ 6`（chip + derivative + tail 綜合分），2022 年實際分數多在 2~4，導致 ma_gap 跌至 -16.3% 卻無法切換。NCF exit gate（A21.14）亦無法補救，因 NCF 模型本身訓練數據不足以預測 2022 那類緩慢大跌。

---

## 現狀總覽

| 策略 | 狀態 | 短窗口 Sharpe | MDD | 總報酬 |
|------|------|------------|-----|--------|
| A21.3 | 已下架 | 2.449 | -22.84% | — |
| A21.4 | research_candidate | 2.600 | -14.76% | — |
| **A21.11** | **active** | **2.5216** | **-13.92%** | **+133.4%** |
| A21.12 | research_candidate（拒絕） | 2.4463 | -16.50% | — |
| A21.13 | research_candidate（不升格） | 2.5317 | -14.46% | +114.6%（-18.8pp） |
| A21.14 | research_candidate（待驗證） | 2.5208 | -13.92% | +133.6%（≈A21.11） |

---

## 下一步建議

### 優先順序

1. **A21.14 未來驗證條件**  
   Exit gate 觸發需要：市場在 golden1 但 ma_gap < 3%（接近 MA100）+ NCF H20 dual-confirm 連續 3 天。  
   歷史上此條件在 2022 年最可能滿足，但 NCF 需要更早的訓練窗口。  
   → 當下次市場接近 MA100 時，觀察 NCF H20 dual-confirm 是否有效。

2. **NCF 模型改進方向**  
   現有模型對「緩慢熊市」（2022 類型）預測力不足（H20 AUC 0.51~0.52 for 2023 val set）。  
   可考慮：以「未來 20 日最大回撤 > 5%」為 label 重新訓練，而非方向預測。

3. **A21.4 PSR/DSR 評估**  
   短視窗 Sharpe 最高（2.600），需與 A21.11 做統計顯著性比較（`evaluate_group_a_plus_risklab.py`）。

4. **risk_score 補強**  
   A21.11 在 risk_score 低（2022 類型市場）時無法切換防禦，是最大已知盲點。  
   可考慮加入 `total_risk_score ≥ 3` 的較寬鬆防禦條件作為 A21.15。

---

## 程式碼異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `group_a_plus/runners/a2112.py` | 新建 | A21.12 runner（MA80+lrx） |
| `group_a_plus/runners/a2113.py` | 新建 | A21.13 runner（A21.11+NCF daily overlay） |
| `group_a_plus/runners/a2114.py` | 新建 | A21.14 runner（NCF exit gate only） |
| `group_a_plus/integrations/ncf.py` | 新建 | NCF signal helper（downside/upside/overlay） |
| `group_a_plus/runners/latest.py` | 修改 | 加入 a2112/a2113/a2114 dispatcher |
| `group_a_plus/governance/latest.py` | 修改 | 加入 a2112/a2113/a2114 SUPPORTED_STRATEGIES |
| `scripts/misc/ncf_00631l.py` | 修改 | v2：QQQ/TWII/VIX 外部特徵、RSI7、MA30、streak、Isotonic 校準、--val-predictions-output |
| `ncf_00632r.py` | 修改 | v2：同 631L + eti0050_10d_ret；AUC H5 +0.071、H20 +0.029 |
| `tests/test_group_a_plus_a2112.py` | 新建 | A21.12 測試（24 tests） |
| `tests/test_group_a_plus_ncf_integration.py` | 新建 | NCF 整合測試（24 tests） |
| `scripts/evaluate/evaluate_group_a_plus_risklab.py` | 修改 | BASE=A21.11，CANDIDATE=A21.12 |
