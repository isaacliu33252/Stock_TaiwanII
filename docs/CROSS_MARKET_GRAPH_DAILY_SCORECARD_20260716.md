# Cross-Market Graph Daily Scorecard - 2026-07-16

## 目的

評估 cross-market graph daily `NO_ADD` 是否值得成為獨立 advisory。

本報告只做研究，不改 daily signal、不改權重、不新增 live guard。

## 輸入

正式 cross-market daily frame：

```text
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
```

評估腳本：

```text
scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py
```

輸出：

```text
results/cross_market_graph_daily_scorecard_20260716.json
```

## 整體結果

期間：

```text
2021-01-28 ~ 2026-07-08
```

結果：

```text
rows = 1317
active_days = 25
event_days = 364
precision = 40.0%
recall = 2.7%
false_positive_rate = 1.6%
```

解讀：

```text
訊號非常低頻。
precision 尚可，但 recall 很低。
適合研究觀察，不適合單獨做 live alert。
```

## 年度結果

| Year | Rows | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|---:|
| 2021 | 225 | 4 | 25.0% | 1.9% | 1.7% |
| 2022 | 246 | 18 | 44.4% | 8.3% | 6.7% |
| 2023 | 239 | 0 | 無 | 0.0% | 0.0% |
| 2024 | 242 | 2 | 50.0% | 1.7% | 0.5% |
| 2025 | 243 | 0 | 無 | 0.0% | 0.0% |
| 2026 | 122 | 1 | 0.0% | 0.0% | 1.3% |

解讀：

```text
cross-market graph 的 NO_ADD 幾乎集中在 2022。
2025 沒有觸發。
2026 唯一觸發是 false positive。
跨年度穩定性不足。
```

## 壓力窗口

| Window | Rows | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|---:|
| 2020 COVID | 0 | 0 | 無 | 無 | 無 |
| 2022 Rate Hike | 202 | 17 | 47.1% | 9.4% | 7.7% |
| 2025-2026 Full | 365 | 1 | 0.0% | 0.0% | 0.4% |
| 2026 Q1/Q2 | 54 | 1 | 0.0% | 0.0% | 2.5% |
| 2026 Recent | 38 | 0 | 無 | 0.0% | 0.0% |

解讀：

```text
2020 COVID 沒有 OOS coverage，不能評估。
2022 有一些 NO_ADD 訊號，但 precision 未達可升級標準。
2025-2026 與 2026 最近壓力段都不支持升級。
```

## 結論

不建議將 cross-market graph daily NO_ADD 升級為 live alert。

目前定位應維持：

```text
research-only independent advisory
not SRR confirmation
not live guard
not target-weight input
```

原因：

```text
1. 2022 有訊號，但不是跨年度穩定。
2. 2025-2026 幾乎不觸發。
3. 2026 唯一觸發為 false positive。
4. 無法覆蓋 2020 COVID。
5. 與 SRR crash_watch_active 重疊不足。
```

## 後續建議

短期：

```text
不接 daily signal alert。
不拿來確認或壓制 SRR crash_watch_active。
保留 daily frame 與 scorecard，之後累積新樣本再評估。
```

中期：

```text
若要改善 cross-market graph，優先做 threshold sweep：
  NO_ADD probability threshold 0.60 / 0.65 / 0.70
  require NO_ADD > REENTER
  require NO_ADD - REENTER margin
```

長期：

```text
把 2022 作為 stress validation，不要用 2022 單一年決策。
若未來 2026-2027 新樣本顯示穩定，再考慮 low-level advisory alert。
```

## Threshold / Margin Sweep

新增腳本：

```text
scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py
```

輸出：

```text
results/cross_market_graph_threshold_sweep_20260716.json
```

搜尋條件：

```text
prob_NO_ADD threshold = 0.55 / 0.60 / 0.65 / 0.70 / 0.75
margin = prob_NO_ADD - prob_REENTER
margin threshold = 0.00 / 0.03 / 0.05 / 0.08 / 0.10
optional top N by probability = 5 / 10 / 20
```

最佳整體規則：

```text
prob_NO_ADD >= 0.65
margin >= 0.10

active_days = 21
precision = 47.6%
recall = 2.7%
false_positive_rate = 1.2%
```

分窗口：

```text
2022 Rate Hike:
  active_days = 14
  precision = 57.1%
  recall = 9.4%
  false_positive_rate = 5.1%

2025-2026 Full:
  active_days = 0

2026 Q1/Q2:
  active_days = 0

2026 Recent:
  active_days = 0
```

Sweep 結論：

```text
沒有 practical candidate。
最佳整體 precision 未達 50%。
可用訊號仍集中在 2022，無法泛化到 2025-2026。
因此 threshold / margin sweep 也不支持升級 live alert。
```

## 驗證

已執行：

```bash
.venv/bin/python scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py \
  --input results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv \
  --output results/cross_market_graph_daily_scorecard_20260716.json

.venv/bin/python scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py \
  --input results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv \
  --output results/cross_market_graph_threshold_sweep_20260716.json
```

結果：

```text
scorecard 成功輸出。
threshold sweep 成功輸出，但無 practical candidate。
```
