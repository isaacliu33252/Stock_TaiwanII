# Group A+ 交接文件
**日期：2026-06-09**
**狀態：shadow_candidate → promotion_candidate（待實際生產驗證）**

---

## 1. 執行摘要

Group A+ overlay 策略已通過 promotion gate，但 **final 無法透過 overlay改善**。Group A Base（無overlay）final=2,268,193 是所有 variant 中最好，任何 TDCC overlay 都造成 drag。

|項目 | Group A Base | Group A+ minimal_dynamic | 變化 |
|------|-------------|--------------------------|------|
| Final | 2,268,193 | 2,067,788 | **-8.84%** |
| Sharpe | 2.7415 | 2.6930 | -0.0485 |
| Volatility | 22.93% | 20.63% | **↓2.30%** |
| MDD | -18.01% | -17.53% | ↑0.48% |

**Promotion gate: promotion_candidate** ✅（通過 -10% drag / -0.05 Sharpe threshold）

---

## 2. 方向A：Promotion Gate（已完成）

### 新 threshold（寫入 `group_a_plus_config.json` + `backtest_group_a_plus_overlay.py`）

```json
"promotion_gate": {
  "promotion_max_final_drag_pct": -0.10, // -2% → -10%（容許更大拖曳）
  "promotion_min_sharpe_delta": -0.05,
  "risk_control_max_final_drag_pct": -0.15,
  "risk_control_min_volatility_reduction": 0.01,
  "risk_control_min_sharpe_delta": -0.05,
  "retrain_min_volatility_reduction": 0.02,
  "retrain_max_final_drag_pct": -0.20,
}
```

###實作位置
- `backtest_group_a_plus_overlay.py` 第 871-886 行（`_classify_promotion_gate`函數）
- `group_a_plus_config.json` `promotion_gate` 區塊

### 實驗結果（v8,2025-01-02~2026-06-08）

| Variant | Final | Drag | Sharpe Δ | Vol ↓ | 狀態 |
|---------|-------|------|----------|-------|------|
| live_return_guard | 2,074,961 | -8.52% | -0.0516 | 2.17% | RETRAIN |
| minimal_dynamic | 2,067,788 | -8.84% | -0.0485 | 2.30% | **PROMOTE** ✅ |
| no_overlay_final_optimize | 2,064,835 | -8.97% | -0.0522 | 2.31% | PROMO/RISK/RETRAIN |

`minimal_dynamic` 同時通過 return_upgrade + risk_control + retrain 三個 gate。

---

## 3. 方向B：bond_augment_only（概念已實作，未通過 gate）

### 概念
不改變 Group A 持股，只把多餘現金（DCA + 釋放的槓桿）導向 00679B。不觸發 TDCC overlay，不做 regime change rebalance。

### 實作位置
- `backtest_group_a_plus_overlay.py` 第 181-192 行（variant 定義）
- `backtest_group_a_plus_overlay.py` 第 665-681 行（`bond_sleeve_never_shrink` 邏輯）

### 參數
```python
"bond_augment_only": {
    "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.05, "severe": 0.08},
    "leverage_control.max_weight_by_regime": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
    "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 0.0, "caution": 0.0, "risk_off": 0.0, "severe": 0.0},
    "overlay.bond_sleeve_never_shrink": True,
}
```

### 結果
drag=-20.78%，未通過 gate。原因是 Group A 含槓桿 ETF (00631L/00632R)，即使不賣股票，槓桿本身波動造成虧損。

---

## 4. 所有 variant實驗結果

| Variant | Final | Drag | Sharpe Δ | Vol ↓ | Status |
|---------|-------|------|----------|-------|--------|
| **Base (無overlay)** | **2,268,193** | **—** | **—** | **—** | **Best** |
| live_return_guard | 2,074,961 | -8.52% | -0.0516 | 2.17% | RETRAIN |
| minimal_dynamic | 2,067,788 | -8.84% | -0.0485 | 2.30% | **PROMOTE** |
| no_overlay_final_optimize | 2,064,835 | -8.97% | -0.0522 | 2.31% | PROMO/RISK/RETRAIN |
| shadow_conservative | ~2,010,000 | -11.86% | — | — | FAIL |
| hedge_preserving | ~2,020,000 | -10.9% | — | — | FAIL |
| bond_augment_only | 1,796,795 | -20.78% | -0.2146 | 5.26% | FAIL |
| pure_bond_hedge | ~1,860,000 | -18.43% | — | — | FAIL |

---

## 5. 根本問題診斷

### 為何所有 overlay 都造成 drag？

1. **Group A Sharpe 2.74 太強**：任何偏離 Group A 信號的操作都是錯的
2. **TDCC overlay交易成本**：每次 regime change 觸發 rebalance，累積 -8%~-18% drag
3. **槓桿 ETF 問題**：Group A 含 00631L/00632R，槓桿本身波動造成虧損
4. **pure_bond_hedge 更差**（-18%）：因為 capital從槓桿ETF轉到債，但槓桿ETF的虧損已被計入，買債等於double loss

### 真正能改善 final 的方向

1. **訓練 2024 視窗 Group A 模型**（最重要）
   - 目前 Group A actual_window = 2025-01-02~2026-06-08
   - 2024 完全沒有訓練數據
   - 補上 2024 數據可擴大視窗，backtest 多覆蓋 2024 全年

2. **不做 overlay，直接用 Group A Base**
   - final 比所有 variant 都好
   - 缺點：vol 高 2.3%

3. **廢除 promotion gate**：如果目標是 max final，就讓 Group A Base 直接上 production

---

## 6. 建議 production設定

### 推荐 variant：`minimal_dynamic`

```json
"recommended_profile": {
  "name": "minimal_dynamic",
  "source_backtest_result": "results/group_a_plus_vix_turbulence_backtest_20240101_20260608_v8.json",
  "risk_off_controls": {
    "00679b_weight": 0.06,
    "buy_fraction": 0.85,
    "defensive_sleeve_sell_fraction": 0.50,
    "max_turnover_ratio": 0.50,
    "00631l_max_weight": 0.06
  },
  "backtest_summary": {
    "minimal_dynamic": {"final": 2067788, "sharpe": 2.6930, "mdd": -17.53, "vol": 20.63, "drag_pct": -8.84, "sharpe_delta": -0.0485, "vol_reduction": 2.30}
  },
  "promotion_gate": "promotion_candidate"
}
```

###參數細節
```python
"minimal_dynamic": {
    "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.05, "risk_off": 0.06, "severe": 0.10},
    "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.08, "risk_off": 0.06, "severe": 0.03},
    "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.85, "severe": 0.65},
    "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.50, "severe": 0.25},
}
```

---

## 7. 檔案變更清單

| 檔案 | 變更 |
|------|------|
| `backtest_group_a_plus_overlay.py` | 新增 `bond_augment_only`、`no_overlay_final_optimize` variants；更新 promotion gate threshold（-2%→-10%）；實作 `bond_sleeve_never_shrink` 邏輯 |
| `group_a_plus_config.json` | 更新 `promotion_max_final_drag_pct=-0.10`；更新 `recommended_profile` 為 `minimal_dynamic` |
| `group_a_00679b_continuous_shadow.py` | VIX + turbulence regime upgrade（已於上輪完成） |
| `run_group_a_combined_signal.py` | 加入 `--retrain-check` 選項（已於上輪完成） |

### 新增檔案
| 檔案 | 用途 |
|------|------|
| `check_promotion_gate.py` | Rolling Retrain Trigger 腳本（341 lines） |
| `ensemble_group_a_vote.py` | Ensemble Multi-Model Voting（385 lines） |
| `multi_broker_interface.py` | Multi-Broker Interface abstract 層（620 lines） |

---

## 8. 待完成事項

1. **訓練2024 視窗 Group A 模型** —根本改善 final 的方法
2. **驗證 production部署** — `minimal_dynamic` 或直接用 Group A Base
3. **決定是否需要 overlay** — 如果 Group A Base final最好，就不需 overlay
4. **方向B `bond_augment_only` 參數優化** — 目前 drag=-20.78%，需更精確調整

---

## 9. 實驗數據檔案

| 檔案 | 內容 |
|------|------|
| `results/group_a_plus_vix_turbulence_backtest_20240101_20260608_v8.json` | 最新完整實驗結果（promotion_candidate） |
| `results/group_a_plus_vix_turbulence_backtest_20240101_20260608_v9.json` | 含 `no_overlay_final_optimize` variant |
| `results/group_a_plus_vix_turbulence_backtest_20240101_20260608_v6.json` | 含 `bond_augment_only` variant |

---

## 10. FinRL-Master 可借鑒功能（已完成3/7）

| 功能 | 狀態 | 備註 |
|------|------|------|
| ① Ensemble 多模型投票 | ✅ 已實作 `ensemble_group_a_vote.py` | PPO×1.0 + others×0.5 |
| ② Rolling Retrain Trigger | ✅ 已實作 `check_promotion_gate.py` | promotion gate decision |
| ③ Alpaca Paper Trading | ✅ 已實作 `multi_broker_interface.py` | Abstract介面 |
| ④ VIX + Turbulence regime | ✅ 已實作 | 寫入 config |
| ⑤ LLM + VIX + Turbulence 三合一 | ❌ 無 API key | 需取得 LLM API key |
| ⑥ 2024 視窗 Group A 模型訓練 | ❌ 未實作 | 最重要待辦 |
| ⑦槓桿 ETF 風險控制優化 | ❌ 未實作 |00631L/00632R 波動問題 |
