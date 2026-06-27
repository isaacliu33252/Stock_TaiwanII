# Group A / Group B Improvement Research 2026-06-05

回測資料區間：2024-01-02 至 2026-06-04。  
方法：不重訓模型，使用既有 Group A TDCC latest 與 Group B no-2884 equity curve。

## Executive Decision

可採用：**A/B 季度動態權重**。

暫不採用：**Group A 單標的風控 haircut**。  
原因是近似回放下報酬、Sharpe、MDD 都輸給原本 TDCC latest，而且交易成本高。

維持：**62.5% A / 37.5% B** 可以作為保守正式版；動態 A/B 可作為改善版候選。

## 1. Dynamic Group A / Group B

規則：

- 只在季初更新 A/B 目標權重。
- 權重限制在 55% / 62.5% / 70% Group A。
- 用前一日可得的 126 日相對強弱與 rolling Sharpe 差決定偏向 A 或 B。
- 季中只因 drift 觸發再平衡。
- 轉換成本：0.1425%。

最佳結果：

| Variant | Final | Annual | Sharpe | MDD | Events | Cost |
|---|---:|---:|---:|---:|---:|---:|
| Fixed 62.5A / 37.5B | 5,515,384 | 52.06% | 2.4972 | -19.75% | 10 | 788 |
| Dynamic 126d | 5,636,020 | 53.43% | 2.5203 | -19.01% | 6 | 1,169 |

改善幅度：

- Final +120,637
- Annual +1.37 pct
- Sharpe +0.0231
- MDD 改善 0.74 pct
- Rebalance 次數 10 降到 6

這是目前四項中唯一值得納入下一版正式候選的改善。

## 2. Group A Component Risk

測試內容：

- 對 0050 / 00631L / 00632R 做單標的 drawdown + 21 日動能風控。
- 弱勢時將該標的目標權重打 5 折或 7 折，釋放到 cash。
- 因來源 JSON 沒有完整每日 shares，此項是事件權重近似回放，不是完全等同原 PPO 執行。

最佳近似結果：

| Variant | Final | Annual | Sharpe | MDD | Events | Cost |
|---|---:|---:|---:|---:|---:|---:|
| Group A TDCC latest | 3,104,211 | 59.68% | 2.1641 | -26.43% | 80 | 36,231 |
| Component haircut best | 2,737,877 | 51.61% | 2.0052 | -27.29% | 77 | 46,769 |

結論：不採用。它不是降低 Group A 風險的好方法。

## 3. Execution Threshold

固定 62.5A / 37.5B 下，測不同最小轉換金額：

| Variant | Final | Annual | Sharpe | MDD | Events | Cost |
|---|---:|---:|---:|---:|---:|---:|
| no min transfer | 5,515,384 | 52.06% | 2.4972 | -19.75% | 10 | 788 |
| min 50,000 | 5,521,114 | 52.13% | 2.4950 | -19.84% | 6 | 735 |
| min 100,000 | 5,496,834 | 51.85% | 2.4698 | -19.89% | 2 | 505 |

結論：`min_transfer_notional=50,000` 可作為實盤執行優化，final 稍高、交易次數更少，但 Sharpe 和 MDD 略差。正式回測排名仍以 no-min 的 62.5/37.5 當基準。

## 4. Segment Stability

年度穩定性：

| Strategy | 2024 Sharpe / MDD | 2025 Sharpe / MDD | 2026 YTD Sharpe / MDD |
|---|---:|---:|---:|
| Group A TDCC | 1.8967 / -20.30% | 1.2970 / -26.43% | 4.3258 / -10.31% |
| Group B no-2884 | 3.6007 / -3.45% | 1.4204 / -13.69% | 5.1963 / -3.60% |
| Fixed 62.5A/37.5B | 2.4563 / -13.86% | 1.4762 / -19.75% | 4.6915 / -7.77% |
| Dynamic A/B | 2.4614 / -13.86% | 1.5120 / -19.01% | 4.6047 / -8.30% |

觀察：

- 2025 是主要壓力年，Group A 的 -26.43% MDD 是組合風險來源。
- Group B 明顯提供穩定器效果。
- Dynamic A/B 的主要價值是在 2025 把 MDD 與 Sharpe 都略改善，同時 2026 final 更高。

## Recommendation

下一版候選策略：

- **正式保守版**：Fixed 62.5% Group A / 37.5% Group B，季再平衡，5% drift。
- **改善候選版**：Dynamic 126d A/B，季度更新權重，權重只允許 55% / 62.5% / 70% Group A，5% drift。
- **實盤執行選項**：若想降低小額換手，可加 `min_transfer_notional=50,000`。

不建議：

- Group A 內部單標的 haircut。
- Group A 動態 00679B selector。
- 再調 buy-dip / cap / clear 這類 PPO payload 小參數。

## Outputs

- Script: `research_group_ab_group_a_improvements.py`
- JSON: `results/group_ab_group_a_improvement_research_20240102_20260604.json`
- CSV: `results/group_ab_group_a_improvement_research_20240102_20260604.csv`
- Curves: `results/group_ab_group_a_improvement_research_20240102_20260604_curve.csv`
