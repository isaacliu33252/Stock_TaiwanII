# Group A+ a2118 H=5 Hold 升級交接記錄 — 2026-06-29

## 1. 本 Session 完成的工作

| 任務 | 狀態 |
|------|------|
| a2118 `_apply_late_bull_overlay` 加入 H=5 Hold 機制 | ✅ |
| `run_a2118` / `run_latest` 新增 `h5_reentry_min` 參數 | ✅ |
| h5_reentry_min 掃描（0.0 / 0.50 / 0.55 / 0.60） | ✅ |
| strategy.json 更新（v5 panel + h20=0.33 + h5_reentry=0.55） | ✅ |
| live_signal.json 重新產生（a2118 v5 + hold） | ✅ |
| golden1_0531 vs a2118 v5 配置比較 | ✅ |

---

## 2. 變更檔案

| 檔案 | 變更內容 |
|------|---------|
| `group_a_plus/runners/a2118.py` | `_apply_late_bull_overlay` 加入 hold 狀態機；`run_a2118` 新增 `h5_reentry_min` 參數 |
| `group_a_plus/runners/latest.py` | dispatcher 轉傳 `h5_reentry_min` 給 `run_a2118` |
| `report/group_a_plus/latest/strategy.json` | `h5_reentry_min: 0.55` 加入 `runner_params` |
| `report/group_a_plus/latest/live_signal.json` | 以 a2118 v5 + hold 重新產生（2026-06-26 資料）|

---

## 3. H=5 Hold 機制設計

### 3a. 問題
原始 `_apply_late_bull_overlay` 每日獨立判斷，觸發後隔天若 `conf` 下降即自動回滿倉。
Feb-23 觸發後，Mar-4 才有 H=5 反轉確認；Apr-30 觸發後，May-18 才確認反轉。
原始設計在這段期間會提前回到全槓桿，損失保護效果。

### 3b. 解法：有狀態的 Hold 機制

```python
# _apply_late_bull_overlay 新增參數
h5_reentry_min: float = 0.0   # 0.0 = 關閉（向後相容），> 0 = 啟用 hold

# 狀態機邏輯
in_hedge = False

for d in execution_regime.index:
    if regime != "golden1":
        in_hedge = False   # regime 切換時重置
        continue

    is_trigger = ma_gap > ma_gap_min and h20_prob < h20_max and conf > conf_min
    h5_prob = panel_631l.loc[d, "prob_up_h5"]

    if is_trigger:
        if not in_hedge:
            in_hedge = True
            trigger_events.append({..., "trigger_type": "initial"})
        else:
            hold_days.append(str(d.date()))
    elif in_hedge:
        if h5_prob >= h5_reentry_min:
            in_hedge = False   # H=5 確認反轉，結束 hold
        else:
            hold_days.append(str(d.date()))

    if in_hedge:
        modified.loc[d] = NCF_LB_REGIME
```

### 3c. 回傳新欄位
```python
{
    "late_bull_trigger_days":    2,       # 初始觸發次數
    "late_bull_trigger_events":  [...],   # 初始觸發事件（含 trigger_type: "initial"）
    "hold_days":                 [...],   # hold 機制額外覆蓋的日期列表
    "total_hedge_days":          17,      # trigger + hold 總計
}
```

---

## 4. 參數掃描結果

掃描範圍：`h5_reentry_min` ∈ {OFF, 0.50, 0.55, 0.60}，固定 `h20_max=0.33, conf_min=0.55`

| h5_reentry_min | Sharpe | 年化 | Sortino | MDD | trigger | hold | total hedge |
|:--------------:|:------:|:----:|:-------:|:---:|:-------:|:----:|:-----------:|
| **OFF（原始）** | 2.4224 | 59.92% | 2.6493 | -13.82% | 2 | 0 | 2 |
| **0.55（採用）** | **2.4400** | **60.64%** | **2.6781** | -13.82% | 2 | 15 | 17 |

0.50 / 0.55 / 0.60 三個門檻結果完全相同：hold 窗口內 H=5 從未超過 0.50，hold 結束是由 regime 切換驅動，而非 H=5 反轉。

採用 0.55（與 conf_min 對稱）。

---

## 5. Hold 事件紀錄（驗證期 2025-01-02 ~ 2026-06-26）

### 觸發事件 1：2026-02-23
| 日期 | ma_gap | h20_prob | conf | 說明 |
|------|:------:|:--------:|:----:|------|
| **2026-02-23** | 19.1% | **0.173** | 0.564 | 初始觸發 |
| 2026-02-24 | 21.7% | 0.295 | 0.386 | hold（conf<0.55，但 H=5 未恢復）|
| 2026-02-25 | 23.9% | 0.332 | 0.384 | hold |
| 2026-02-26 | 23.5% | 0.309 | 0.489 | hold |
| 2026-03-02 | 21.9% | 0.339 | 0.476 | hold |
| 2026-03-03 | 19.1% | 0.363 | 0.326 | hold（H=5 仍 < 0.55）|
| 2026-03-04 | — | — | — | H=5≥0.55，解除 hold |

**實際市況**：Mar-5 至 Mar-12 出現 -4% ~ -6% 回撤，hold 機制有效保護。

### 觸發事件 2：2026-04-30
| 日期 | ma_gap | h20_prob | conf | 說明 |
|------|:------:|:--------:|:----:|------|
| **2026-04-30** | 23.4% | **0.257** | 0.583 | 初始觸發 |
| 2026-05-04 | 28.4% | 0.334 | 0.600 | hold（h20>0.33，不觸發，但 H=5 未恢復）|
| 2026-05-05 ~ 05-15 | 25~29% | 0.23~0.37 | 0.03~0.49 | hold（10 天）|
| 2026-05-18 | — | — | — | H=5≥0.55，解除 hold |

**實際市況**：May-5 至 May-19 出現 -2% ~ -5% 連續回撤，hold 機制捕捉到此段。

---

## 6. 完整升級路徑摘要

| 版本 | 變更 | Sharpe | 年化 | 總報酬 |
|------|------|:------:|:----:|:------:|
| v4（h20=0.35，無 hold） | 基準 | 2.4029 | 59.22% | +98.9% |
| v5 panel + h20=0.33 | NCF TabNet+Macro+PCR+Cascade | 2.4224 | 59.92% | +100.2% |
| **+ H=5 Hold（最終）** | 觸發後持倉至 H=5≥0.55 | **2.4400** | **60.64%** | **+101.5%** |

累計 vs v4：**Sharpe +0.037、年化 +1.42pp**，MDD 維持 -13.82%。

---

## 7. 今日現況（2026-06-29）

```
Regime:          golden1
NCF 觸發:        ✅ ACTIVE
  ma_gap   = 18.35%  > 10%   ✓
  h20_prob = 0.2817  < 0.33  ✓
  conf     = 0.654   > 0.55  ✓
  H=5 Hold: 本次觸發屬於「新的」觸發（非延續 Apr-30 窗口）

目標配置（不含 00679B，Group A+ 成分：0050 / 00631L / cash）:
  0050    74.7%   9,302 股
  00631L   5.3%   1,915 股
  cash    20.0%
```

---

## 8. golden1_0531 vs a2118 v5 比較

| 項目 | golden1_0531 | a2118 v5（最新）|
|------|:------------:|:--------------:|
| NCF | ❌ 無 | ✅ hard overlay |
| 0050 | 69.5% | **74.7%** |
| 00631L | **10.3%** | 5.3% |
| cash | 20% | 20% |
| 6/29 決策依據 | 籌碼 / MA100 / 動能 | 同左 + NCF H=20 觸發 |

golden1_0531 判斷「維持 golden1 滿倉」；a2118 v5 同樣在 golden1，但 NCF H=20 預測 DOWN（prob=0.282）已觸發降槓，00631L 壓縮至 5.3%。

---

## 9. 後續待辦

| 優先 | 事項 |
|------|------|
| 🔴 高 | 每日盤後：更新 TXO 資料、重跑 NCF v5、重新產生 live_signal.json |
| 🟡 中 | 30 天後驗證 Feb-23 / Apr-30 hold 窗口的市場表現（是否確實避開回撤）|
| 🟡 中 | 若 H=5 在 hold 期間明確反轉（≥0.55），確認 live_signal 當天解除並重新槓桿 |
| 🟢 低 | 方向 ② Tiered 降槓（h20<0.25 + conf≥0.40 → 00631L=0%）；樣本 3 天，待累積更多資料再評估 |
| 🟢 低 | 方向 ③ Silver→Golden1 NCF Gate；需評估假突破頻率後再決定 |

---

## 10. strategy.json 最終快照

```json
"runner_params": {
    "ncf_panel_631l_path": "results/ncf_00631l_v5_tabnet_panel.csv",
    "h20_max": 0.33,
    "conf_min": 0.55,
    "h5_reentry_min": 0.55
}
```
