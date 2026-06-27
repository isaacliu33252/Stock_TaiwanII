# Group A+ 策略交接記錄 — 2026-06-25

## 策略升格摘要

| 項目 | 內容 |
|------|------|
| 升格策略 | **A21.11**（`a2111_tight_entry_bond30c30`） |
| 取代策略 | A21.7（`a217_tight_entry_mw100`，2026-06-23 升格） |
| 升格依據 | Sharpe +0.113、Sortino +0.216、MDD 改善 8.33pp，全面優於 A21.7 |
| Manifest 更新時間 | 2026-06-25 |

---

## 正式策略規格（A21.11）

### Switch Rule（與 A21.7 相同）
```
name:           risk_ma100_dd11_total3_eg3_xg10
ma_window:      100
entry_gap:      +0.003   （價格高於 MA100 才進攻，但 gap < 0.3% 即視為突破）
exit_gap:       +0.010   （恢復需要價格高於 MA100 超過 1%）
dd_threshold:   -11%
hold_days:      5
```

### 持倉配置
| Regime | 0050 | 00631L | 00679B | 現金 |
|--------|------|--------|--------|------|
| `golden1`（多頭） | 60% | 20% | 0% | 20% |
| `group_a_plus_defensive`（防禦） | **40%** | **0%** | **30%** | 30% |
| `group_a_plus_recovery`（復甦） | ~69.6% | ~10.3% | ~0.05% | ~20% |

> 與 A21.7 的唯一差異：防禦時 basket 換成 `bond30_cash30`
> - A21.7 defensive：0050 60% / 00631L 10% / cash 30%
> - A21.11 defensive：0050 40% / **00679B 30%** / cash 30%（00631L 降至 0%，加入債券 ETF 緩衝）

### Recovery Ramp 條件（不變）
- 觸發：base regime = defensive AND MA100 gap ≥ 0 AND exit_momentum > 0
- 行為：one-shot 切換，recovery 持倉 ≈ 最後一次 golden1 訊號持倉

---

## 回測結果

### 短視窗：2025-01-02 ~ 2026-06-24（355 個交易日）

| 指標 | A21.7（舊正式） | A21.11（新正式） | 改變 |
|------|----------------|----------------|------|
| Sharpe | 2.4086 | **2.5216** | **+0.113** |
| Sortino | 2.5875 | **2.8035** | **+0.216** |
| MDD | -22.25% | **-13.92%** | **+8.33pp** |
| Worst 20d | -16.69% | **-9.66%** | **+7.03pp** |
| 年化報酬 | 79.22% | 77.80% | -1.43pp |
| 最終淨值 | 2,361,785 | 2,334,165 | -27,620 |
| 波動度 | 26.98% | **25.26%** | -1.72pp |
| VaR 5% | -2.47% | **-2.38%** | +0.09pp |
| ETL 5% | -3.61% | **-3.30%** | +0.31pp |
| 換手次數 | 4 | 4 | — |
| 交易成本 | 2,523 | 5,011 | +2,488（00679B 入出較貴） |
| 換手金額 | 1,205,613 | 2,341,146 | +1,135,533 |

**短視窗 Regime 切換事件（兩者相同）：**
- 2025-02-25：golden1 → defensive（MA gap 觸發）
- 2025-06-09：defensive → recovery（MA gap ≥ 0 觸發）
- 2025-06-10：recovery → golden1

### 長視窗：2020-01-02 ~ 2026-06-24（1,570 個交易日）

| 指標 | A21.7（舊正式） | A21.11（新正式） | 改變 |
|------|----------------|----------------|------|
| Sharpe | 1.3568 | **1.3825** | **+0.026** |
| Sortino | 1.3511 | **1.3833** | **+0.032** |
| MDD | -31.26% | **-31.26%** | 持平 |
| Worst 20d | -21.18% | **-19.08%** | +2.10pp |
| 年化報酬 | 30.46% | 29.96% | -0.50pp |
| 最終淨值 | 5,593,912 | 5,456,002 | -137,910 |
| 波動度 | 22.23% | **21.40%** | -0.83pp |
| VaR 5% | -2.03% | **-1.97%** | +0.06pp |
| ETL 5% | -3.15% | **-3.03%** | +0.12pp |
| 換手次數 | 9 | 9 | — |
| 交易成本 | 6,800 | 18,829 | +12,029 |

**長視窗 Regime 切換事件（兩者相同）：**
- 2020-03-06：golden1 → defensive（COVID 崩盤）
- 2020-06-03：defensive → golden1
- 2021-09-29：golden1 → defensive
- 2021-10-26：defensive → recovery
- 2021-11-08：recovery → golden1
- 2025-02-25：golden1 → defensive（同短視窗）
- 2025-06-09：defensive → recovery
- 2025-06-10：recovery → golden1

> **注意**：長視窗 MDD 兩者相同（-31.26%），主因是 COVID 2020-03 的崩跌幅度太大，bond ETF 也無法完全防禦。A21.11 的 MDD 改善主要體現在短視窗（2025 年的 Trump 關稅衝擊）。

### 交易成本增加的原因
A21.11 在進出 defensive 時需要買賣 00679B，00679B 流動性比 00631L 低，bid-ask spread 較大，導致 slippage 和 commission 較高。長視窗 3 次 defensive 合計多付約 1.2 萬的交易成本，但換取更低的 MDD 緩衝，風險調整後仍是划算的。

---

## 升格決策依據

### 為何選 A21.11 而非 A21.4？

候選策略完整比較（短視窗 2025-01-02 ~ 2026-06-25）：

| 策略 | Sharpe | Sortino | MDD | Worst 20d | 年化 | 特點 |
|------|--------|---------|-----|-----------|------|------|
| A21.3 | 2.449 | 2.619 | -22.84% | -16.89% | ~81% | 前正式策略（MA75 cash30） |
| A21.4 | 2.600 | 2.884 | -14.76% | -9.72% | 81.36% | MA60 + bond30_cash30 |
| A21.7 | 2.409 | 2.588 | -22.25% | -16.69% | 79.22% | MA100 tight entry（前正式） |
| **A21.11** | **2.522** | **2.804** | **-13.92%** | **-9.66%** | 77.80% | MA100 tight entry + bond30_cash30 |

- **A21.4**（MA60 + bond30_cash30）：Sharpe 2.600 最高，但 MA60 容易觸發較多 defensive 進出（whipsaw 風險）
- **A21.11**（MA100 tight entry + bond30_cash30）：繼承 A21.7 的 tight entry 機制（不 whipsaw）+ A21.4 的 bond 防禦 basket。MDD 最低（-13.92%），風險調整指標全面優於 A21.7

**核心原則：「數字較好就用」**
- vs A21.7（前正式）：Sharpe +0.113、Sortino +0.216、MDD +8.33pp → A21.11 全面勝出
- 代價：年化報酬 -1.43pp、交易成本略增

---

## 修改的檔案清單

| 檔案 | 類型 | 變更內容 |
|------|------|---------|
| `group_a_plus/runners/a2111.py` | 新建 | A21.11 策略 runner |
| `group_a_plus/runners/latest.py` | 修改 | 加入 a214、a2111 的 dispatch |
| `group_a_plus/governance/latest.py` | 修改 | SUPPORTED_STRATEGIES 加入 a214、a2111 |
| `report/group_a_plus/latest/strategy.json` | 修改 | active_strategy 改為 a2111 |
| `results/group_a_plus_runner_a2111.json` | 新建 | A21.11 短視窗回測結果 |
| `results/group_a_plus_runner_a2111_long.json` | 新建 | A21.11 長視窗回測結果 |
| `results/group_a_plus_runner_a2111_frame.csv` | 新建 | A21.11 日序列資料 |
| `results/group_a_plus_runner_a217_20260625.json` | 新建 | A21.7 短視窗（對比基準） |
| `results/group_a_plus_runner_a217_long_20260625.json` | 新建 | A21.7 長視窗（對比基準） |

---

## 執行計畫（下次交接前）

若要產生今日的 live signal，改用 A21.11 的配置：

```bash
# 驗證 latest 指向 A21.11
python3 -m group_a_plus.governance.latest

# 跑最新 live signal（使用 latest runner）
python3 -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end $(date +%Y-%m-%d) \
  --output results/group_a_plus_runner_latest_$(date +%Y%m%d).json
```

---

## 候選策略狀態總表（更新後）

| 策略 ID | 狀態 | 備注 |
|---------|------|------|
| a207 | legacy | A20.7，保留供 legacy consumer |
| a213_cash30_recovery_ramp | 退役 | 前前正式（MA75 cash30） |
| a214_bond30c30_mw60 | research_candidate | Sharpe 最高但 MA60 whipsaw 風險 |
| a215_cash40_mw80 | shadow | 未通過 RiskLabAI PSR/DSR |
| a217_tight_entry_mw100 | 退役 | 前正式（2026-06-23 ~ 2026-06-25） |
| **a2111_tight_entry_bond30c30** | **active** | **現行正式策略** |

---

## 下一步建議

1. **交易成本確認**：A21.11 的交易成本比 A21.7 多（+2,488 短視窗），主因是 00679B 入出的 slippage。若實際執行成本更高，考慮對 00679B 採用 limit order。
2. **A21.4 RiskLabAI 評估**：A21.4 Sharpe 2.600 最高，但 MA60 whipsaw 問題尚未量化。建議跑 PSR/DSR 評估 MA60 觸發頻率。
3. **2026 年後資料更新**：目前長視窗到 2026-06-24，待新資料進來後重新驗證 A21.11。
4. **Worst-case 壓力測試**：A21.11 的 bond30_cash30 在 2022 年升息環境（00679B 大跌）是否會造成 defensive 期間更大損失？建議跑 inflation_2022 stress scenario。
