# SRR-lite Ensemble Shadow 回測 - 2026-07-16

## 目的

評估 SRR-lite `crash_watch_active` 是否需要其他 shadow 訊號確認，避免單一模型誤報。

本次只做研究回測，不改 daily signal、不改權重、不新增 live guard。

## 新增工具

```text
scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py
```

此工具先建立 SRR-lite historical frame，再加入三個同日 risk proxy：

```text
tail_proxy_active:
  00631L ret5<-8%
  or 00631L drawdown252<-14%
  or 00631L vol20/vol60>1.60

garch_proxy_high_vol_active:
  0050 vol20/vol60>=1.05
  or 0050 vol20 percentile>=70%
  and 0050 ret5<0

compounding_mean_reverting_active:
  00631L compounding regime = MEAN_REVERTING
  rolling_AR1_20d<=-0.15
  mean_reversion_score>=5
```

比較的 ensemble：

```text
srr_no_add_active
srr_crash_watch_active
tail_proxy_active
garch_proxy_high_vol_active
compounding_mean_reverting_active
ensemble_srr_crash_and_any_other
ensemble_srr_crash_and_tail
ensemble_srr_crash_and_garch
ensemble_srr_crash_and_compounding
ensemble_srr_noadd_or_crash_confirmed
```

2026-07-16 追加：

```text
scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py
```

新增 `action_model.prediction_frame`，讓 cross-market graph shadow 可輸出逐日：

```text
date
prob_REENTER
prob_NO_ADD
label_REENTER
label_NO_ADD
no_add_active
shadow_action
condition_*
```

並新增匯出工具：

```text
scripts/evaluate/export_cross_market_graph_prediction_frame.py
```

2026-07-16 後續優化 `select_directed_edges`，將 rolling OLS 從 pandas concat 改為 numpy 陣列計算。優化後完整 production-like cross-market walk-forward 已可在互動回合內完成。

## 全樣本結果

期間：

```text
2025-01-02 ~ 2026-07-16
```

輸出：

```text
results/srr_lite_ensemble_shadow_20250102_20260716.json
results/srr_lite_ensemble_shadow_20250102_20260716_frame.csv
```

重點：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | 8 | 50.0% | 3.1% | 1.5% |
| SRR crash-watch | 18 | 27.8% | 3.9% | 4.8% |
| GARCH proxy | 70 | 40.0% | 21.9% | 15.5% |
| SRR crash + any other | 3 | 66.7% | 1.6% | 0.4% |
| SRR crash + GARCH | 2 | 100.0% | 1.6% | 0.0% |

解讀：

- `SRR crash + GARCH` 非常乾淨，但 active days 太少。
- `SRR crash + any other` 可降低誤報，但 recall 更低。
- 目前不適合升級為 live guard。

## 2018 Trade War

輸出：

```text
results/srr_lite_ensemble_shadow_2018_trade_war_20180101_20181231.json
results/srr_lite_ensemble_shadow_2018_trade_war_20180101_20181231_frame.csv
```

重點：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | 6 | 16.7% | 1.1% | 2.9% |
| SRR crash-watch | 19 | 68.4% | 14.4% | 3.5% |
| SRR crash + any other | 11 | 90.9% | 11.1% | 0.6% |
| SRR crash + GARCH | 5 | 100.0% | 5.6% | 0.0% |
| SRR crash + compounding | 2 | 100.0% | 2.2% | 0.0% |

解讀：

- ensemble 在 2018 非常有效。
- `SRR crash + any other` 比單獨 SRR crash-watch 更乾淨。
- 若只看 2018，ensemble 值得升級；但不能只用單一 stress year 決策。

## 2020 COVID

輸出：

```text
results/srr_lite_ensemble_shadow_2020_covid_20200102_20200630.json
results/srr_lite_ensemble_shadow_2020_covid_20200102_20200630_frame.csv
```

重點：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | 0 | 無 | 0.0% | 0.0% |
| SRR crash-watch | 7 | 85.7% | 17.1% | 1.1% |
| GARCH proxy | 21 | 81.0% | 48.6% | 4.3% |
| SRR crash + any other | 3 | 100.0% | 8.6% | 0.0% |
| SRR crash + GARCH | 3 | 100.0% | 8.6% | 0.0% |

解讀：

- COVID 中 `SRR crash-watch` 本身已很強。
- 加 GARCH 可讓 precision 更高，但 active days 從 7 降到 3，recall 下降。
- 若目標是早期 warning，不宜強制 ensemble；若目標是低誤報 medium alert，可以用 ensemble。

## 2026 Q1/Q2

輸出：

```text
results/srr_lite_ensemble_shadow_2026_q1q2_20260201_20260430.json
results/srr_lite_ensemble_shadow_2026_q1q2_20260201_20260430_frame.csv
```

重點：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | 3 | 66.7% | 11.8% | 2.1% |
| SRR crash-watch | 4 | 50.0% | 11.8% | 4.3% |
| GARCH proxy | 7 | 42.9% | 17.6% | 8.5% |
| SRR crash + any other | 0 | 無 | 0.0% | 0.0% |

解讀：

- 2026 Q1/Q2 不支援強制 ensemble。
- SRR no-add 已比 SRR crash-watch 乾淨。
- 強制其他 shadow 確認會完全漏掉此段有效訊號。

## 2026 Recent

輸出：

```text
results/srr_lite_ensemble_shadow_2026_recent_20260515_20260716.json
results/srr_lite_ensemble_shadow_2026_recent_20260515_20260716_frame.csv
```

重點：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | 1 | 100.0% | 4.2% | 0.0% |
| SRR crash-watch | 2 | 100.0% | 8.3% | 0.0% |
| Tail proxy | 4 | 0.0% | 0.0% | 19.0% |
| SRR crash + any other | 0 | 無 | 0.0% | 0.0% |

解讀：

- 近期資料顯示 SRR crash-watch 自己有效。
- tail proxy 在近期誤報高。
- ensemble 會漏掉 SRR 的有效提示。

## 結論

不建議把 ensemble 接入 live guard。

建議維持：

```text
no_add_active:
  保守 no-add shadow

crash_watch_active:
  low-level early warning
```

可以新增研究用 score：

```text
crash_watch_confirmed =
  crash_watch_active
  and garch_proxy_high_vol_active
```

但目前只適合研究報告或人工檢查排序，不適合阻擋交易。原因：

- 2018 / 2020 precision 很好。
- 2026 Q1/Q2 與近期會漏掉有效 SRR 訊號。
- 全樣本 active days 太少，recall 過低。

## Cross-Market 正式對齊

正式參數：

```text
start = 2019-01-02
end = 2026-07-15
edge_window = 250
min_windows = 3
walk_forward_edge_selection = true
min_train_days = 504
retrain_step = 252
```

輸出：

```text
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
results/srr_lite_ensemble_shadow_with_cross_market_full_20250102_20260716.json
results/srr_lite_ensemble_shadow_with_cross_market_full_20250102_20260716_frame.csv
```

cross-market frame：

```text
rows = 1317
start = 2021-01-28
end = 2026-07-08
no_add_active_days = 25
mean_prob_NO_ADD = 0.4994
mean_prob_REENTER = 0.5016
```

全樣本 2025-01-02 ~ 2026-07-16 對齊後：

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| cross-market no-add | 1 | 0.0% | 0.0% | 0.4% |
| SRR crash + cross-market | 0 | 無 | 0.0% | 0.0% |
| SRR no-add or confirmed crash | 8 | 50.0% | 3.1% | 1.5% |

其他窗口：

```text
2020 COVID:
  cross-market no-add active days = 0
  SRR crash + cross-market active days = 0

2022 Rate Hike:
  cross-market no-add active days = 17
  H10 precision = 70.6%
  SRR crash + cross-market active days = 1
  H10 precision = 100.0%

2026 Recent:
  cross-market no-add active days = 0
  SRR crash + cross-market active days = 0
```

解讀：

```text
cross-market graph 在 2022 有獨立 NO_ADD 訊號。
但它沒有覆蓋 2020 COVID，也沒有覆蓋 2026 Recent 的 SRR 有效提示。
因此不適合作為 SRR crash_watch_active 的必要確認條件。
```

獨立 daily scorecard：

```text
docs/CROSS_MARKET_GRAPH_DAILY_SCORECARD_20260716.md
results/cross_market_graph_daily_scorecard_20260716.json
```

scorecard 結論：

```text
整體 precision = 40.0%，recall = 2.7%，active days = 25。
2022 有主要訊號，但 2025 完全不觸發，2026 唯一觸發是 false positive。
因此 cross-market graph 暫不升級 live alert。
```

正式重跑指令：

```bash
.venv/bin/python scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py \
  --start 2019-01-02 \
  --end 2026-07-15 \
  --edge-window 250 \
  --tstat-threshold 2.0 \
  --stability-threshold 0.20 \
  --min-windows 3 \
  --walk-forward-edge-selection \
  --min-train-days 504 \
  --retrain-step 252 \
  --output results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json

.venv/bin/python scripts/evaluate/export_cross_market_graph_prediction_frame.py \
  --report results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json \
  --output results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
```

## 驗證

已執行：

```bash
.venv/bin/python -m pytest tests/test_leveraged_compounding_regime.py tests/test_group_a_plus_srr_lite_shadow.py -q
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2025-01-02 --end 2026-07-16 --load-lookback-days 900 --output results/srr_lite_ensemble_shadow_20250102_20260716.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2018-01-01 --end 2018-12-31 --load-lookback-days 1200 --output results/srr_lite_ensemble_shadow_2018_trade_war_20180101_20181231.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2020-01-02 --end 2020-06-30 --load-lookback-days 1200 --output results/srr_lite_ensemble_shadow_2020_covid_20200102_20200630.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2026-02-01 --end 2026-04-30 --load-lookback-days 1200 --output results/srr_lite_ensemble_shadow_2026_q1q2_20260201_20260430.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2026-05-15 --end 2026-07-16 --load-lookback-days 1200 --output results/srr_lite_ensemble_shadow_2026_recent_20260515_20260716.json
.venv/bin/python scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py --start 2019-01-02 --end 2026-07-15 --edge-window 250 --tstat-threshold 2.0 --stability-threshold 0.20 --min-windows 3 --walk-forward-edge-selection --min-train-days 504 --retrain-step 252 --output results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json
.venv/bin/python scripts/evaluate/export_cross_market_graph_prediction_frame.py --report results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json --output results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
.venv/bin/python scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py --start 2025-01-02 --end 2026-07-16 --load-lookback-days 900 --cross-market-frame results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv --output results/srr_lite_ensemble_shadow_with_cross_market_full_20250102_20260716.json
```

結果：

```text
tests: 6 passed
ensemble reports: 成功輸出
cross-market full prediction frame: 成功輸出
```
