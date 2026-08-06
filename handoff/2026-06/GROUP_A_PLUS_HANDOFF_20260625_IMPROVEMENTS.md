# Group A+ 改善記錄 — 2026-06-25

## 本次改善摘要（3 項）

---

## 改善 1：ncf_00631l.py — Confidence 公式換成 WF RF Acc

### 問題
原公式使用 WF H=1 HGB accuracy 作為第 4 個 confidence 分量：
- HGB 在 H=1 WF acc = **0.516**（幾乎等同隨機猜測）
- 造成 wf_conf = max(0, (0.516-0.5)*2) = **0.031**（幾乎沒有貢獻）

### 修正
改用 WF H=1 **RF accuracy**（全 horizon 最穩定的模型）：
- RF 在 H=1 WF acc = **0.683**（2026-06-25 驗證）
- wf_conf = max(0, (0.683-0.5)*2) = **0.366**（顯著有效的 confidence 訊號）

### 改變的程式碼
- `ncf_00631l.py` 行 ~1736：`wf_h1_hgb_acc` → `wf_h1_rf_acc`
- JSON 輸出 key：`wf_h1_hgb_accuracy` → `wf_h1_rf_accuracy`

### 公式（含 WF 時）
```
confidence = consensus×0.35 + prob_magnitude×0.35 + spread_conf×0.15 + wf_conf×0.15
wf_conf    = max(0, (wf_h1_rf_acc - 0.5) × 2)
```

---

## 改善 2：ncf_00631l.py — Walk-Forward 視窗 Regime Balance 修正

### 問題
Walk-forward 原本若 test 只有一個 regime（如只有 Bull），或 Bear 訓練樣本 < 10 筆，就直接跳過整個視窗。  
結果：WF-1（Bear 只有 8 筆）和 WF-5（test 只有 Bull）都被跳過，有效視窗不足。

### 修正
改為 **Combined Fallback 機制**：
- 若兩 regime 都足夠（≥5 筆、兩類別）且 test 也有兩 regime：使用 regime-conditioned 訓練（原行為）
- 否則：合併 Bull+Bear 成一個分類器，評估整體 test 準確率（combined mode）

### 改變的行為
| 情境 | 舊行為 | 新行為 |
|------|--------|--------|
| Bear train < 10 筆 | skip | combined fallback |
| Test 只有 Bull | skip | combined fallback |
| 兩 regime 都足夠 | regime-split | regime-split（不變） |

### 改變的程式碼
- `ncf_00631l.py` `walk_forward_evaluate()` 行 ~632-685
- 加入 `use_regime_split` 旗標和 combined mode 分支

---

## 改善 3：A21.11 新候選策略（Tight Entry + Bond30/Cash30）

### 邏輯
組合 A21.7 和 A21.4 的改善（兩者互相正交）：
- **A21.7 改善**：entry_gap=0.003（緊縮進場門檻），MA100，exit_gap=0.010
  → 減少多頭市場的假訊號（whipsaw）
- **A21.4 改善**：defensive basket 換成 bond30_cash30（0050 40% / 00679B 30% / cash 30%）
  → 進 defensive 時 MDD 更低（00631L→ bond 緩衝）

### 回測結果

#### 短視窗（2025-01-02 ~ 2026-06-25）
| 指標 | A21.3 | A21.4 | A21.11 |
|------|-------|-------|--------|
| Sharpe | 2.449 | **2.600** | 2.522 |
| Sortino | 2.619 | **2.884** | 2.804 |
| MDD | -22.84% | -14.76% | **-13.92%** ★ |
| Worst 20d | -16.89% | -9.72% | **-9.66%** |
| 年化報酬 | ~81% | 81.36% | 77.80% |
| Final Value | 2,376,415 | 2,380,037 | 2,334,165 |
| Rebalances | ~8 | — | 4 |

#### 長視窗（2020-01-02 ~ 2026-06-25）
| 指標 | A21.3 | A21.11 | 變化 |
|------|-------|--------|------|
| Sharpe | 1.309 | **1.383** | **+0.074** |
| Sortino | 1.287 | **1.383** | **+0.096** |
| MDD | -36.29% | **-31.26%** | **改善 5.03pp** |
| 年化報酬 | 31.88% | 29.96% | -1.92pp |
| Rebalances | 7 | 9 | +2 |

### 關鍵特點
★ **A21.11 在短視窗 MDD 是所有候選中最低（-13.92%）**，比 A21.4 再低 0.84pp  
★ **長視窗 MDD 改善 5.03pp**（-36.29% → -31.26%）  
✗ 年化報酬比 A21.4 低約 3.5pp（MA100 緊縮進場減少了若干多頭收益）

### 候選狀態
`status: research_candidate` — 需通過 RiskLabAI PSR/DSR/PBO 後才可升格

### 程式碼位置
- `group_a_plus/runners/a2111.py`（新建）
- `group_a_plus/runners/latest.py`（加入 A21.4 和 A21.11 dispatcher）
- 結果：`results/group_a_plus_runner_a2111.json`（短視窗）
- 結果：`results/group_a_plus_runner_a2111_long.json`（長視窗）

---

## 候選策略比較總表

### 短視窗 2025-01-02 ~ 2026-06-25
| 策略 | Sharpe | Sortino | MDD | Worst 20d | 年化 | Rebal |
|------|--------|---------|-----|-----------|------|-------|
| A21.3（正式） | 2.449 | 2.619 | -22.84% | -16.89% | ~81% | ~8 |
| A21.4（候選） | **2.600** | **2.884** | -14.76% | -9.72% | 81.36% | — |
| A21.7（候選） | 2.660 | — | -19.54% | — | — | 2 |
| A21.11（新候選） | 2.522 | 2.804 | **-13.92%** | **-9.66%** | 77.80% | 4 |

### 長視窗 2020-01-02 ~ 2026-06-25
| 策略 | Sharpe | MDD | 年化 |
|------|--------|-----|------|
| A21.3（正式） | 1.309 | -36.29% | 31.88% |
| A21.4（候選） | 1.374 | -36.39% | 32.90% |
| A21.11（新候選） | **1.383** | **-31.26%** | 29.96% |

---

## 下一步建議

1. **A21.4 升格評估**：Sharpe 最強（短視窗 2.600），是 A21.3 → A21.4 升格的最強候選。運行 RiskLabAI PSR/DSR 評估。
2. **A21.11 風險分析**：MDD 最低（-13.92%），長視窗 Sharpe 最高（1.383）。但年化報酬比 A21.4 低 3.5pp，需確認風險偏好。
3. **ncf_00631l.py 重跑 --walk-forward**：改善後的 WF（RF confidence + combined fallback）應產生更多有效視窗，confidence 估計更準。
4. **Group A+ 2020-2024 訓練**（延續 2026-06-23 handoff 下一步 3）

---

## 正式策略狀態（不變）
- 正式策略：`a213_cash30_recovery_ramp`（A21.3），MA75，cash30 basket
- 配置：0050 60% / 00631L 20% / cash 20%（golden1 regime）
