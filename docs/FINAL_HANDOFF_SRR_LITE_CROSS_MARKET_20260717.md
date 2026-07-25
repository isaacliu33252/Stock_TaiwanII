# 最終交接記錄：SRR-lite / Cross-Market Shadow - 2026-07-17

## 最終結論

目前不要再升級。

2026-07-19 補充：和 `2004.01917` daily OHLCV illiquidity proxy overlap
後，SRR-lite 仍比該 proxy 更適合作為 shadow no-add 診斷。不要用
illiquidity proxy 修改 SRR 門檻，也不要因為 SRR 較有用就升級成自動
減碼或 rebalance。詳細記錄：

```text
docs/SRR_LITE_VS_ILLIQUIDITY_PROXY_DECISION_20260719.md
```

保留：

```text
SRR no_add_active:
  保守 no-add shadow
  可留在 daily signal
  不自動調倉

SRR crash_watch_active:
  low-level crash watch
  可留在 daily signal
  只做人工檢查
  不阻擋交易
```

不升級：

```text
cross-market graph:
  research-only
  不接 live alert
  不當 SRR 確認條件

ensemble:
  research-only
  不接 live guard
  不覆蓋 SRR crash_watch_active
```

## 決策理由

目前 SRR-lite 是最有實用性的 shadow 訊號，但仍不足以作為自動交易規則：

```text
SRR no-add:
  誤報低，但 recall 低。

SRR crash-watch:
  可補 2020 / 2018 部分 crash window。
  但全樣本不夠穩。

Ensemble:
  在 2018 / 2020 的 precision 很好。
  但 2026 Q1/Q2 與 2026 Recent 會漏掉 SRR 自己有效的提示。

Cross-market graph:
  主要只在 2022 有用。
  2025 完全不觸發。
  2026 唯一觸發是 false positive。
  threshold / margin sweep 也沒有找到可升級門檻。
```

因此目前版本是：

```text
保守可用版
不是最佳自動交易版
不是 live guard
不是自動調倉規則
```

## 已導入 Live Shadow 的內容

### SRR no_add_active

檔案：

```text
group_a_plus/integrations/srr_lite_shadow.py
group_a_plus/operations/daily_signal.py
```

條件：

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

用途：

```text
manual-review no-add reference for 00631L only
does not change target weights
```

### SRR crash_watch_active

檔案：

```text
group_a_plus/integrations/srr_lite_shadow.py
group_a_plus/operations/daily_signal.py
```

條件：

```text
systemic_fragility_score >= 0.75
graph_density >= 0.65
```

用途：

```text
early manual-review crash watch
low-level alert
不阻擋 00631L 新增
不改 target weights
```

## 不可做的事

除非未來有新的 walk-forward / out-of-sample 證據，不要做以下升級：

```text
不要讓 SRR-lite 自動減碼 00631L。
不要讓 SRR-lite 直接改 target weights。
不要讓 SRR crash_watch_active 覆蓋 no_add_active。
不要把 cross-market graph 接成 live alert。
不要用 cross-market graph 當 SRR crash-watch 的必要確認條件。
不要把 ensemble 接成 live guard。
不要用 2022 單一年結果決定升級 cross-market graph。
```

## 主要新增 / 修改檔案

SRR-lite：

```text
group_a_plus/integrations/srr_lite_shadow.py
group_a_plus/operations/daily_signal.py
tests/test_group_a_plus_srr_lite_shadow.py
scripts/evaluate/evaluate_srr_lite_shadow.py
```

SRR ensemble：

```text
scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py
```

Cross-market daily frame 與 scorecard：

```text
scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py
scripts/evaluate/export_cross_market_graph_prediction_frame.py
scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py
scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py
```

相容性清理：

```text
group_a_plus/integrations/leveraged_compounding_regime.py
```

## 主要文件

```text
docs/CHANGELOG_20260716_SRR_LITE_SHADOW.md
docs/SRR_LITE_CRASH_WINDOW_BACKTEST_20260716.md
docs/SRR_LITE_ENSEMBLE_SHADOW_20260716.md
docs/CROSS_MARKET_GRAPH_DAILY_SCORECARD_20260716.md
docs/HANDOFF_SRR_LITE_SHADOW_20260716.md
docs/FINAL_HANDOFF_SRR_LITE_CROSS_MARKET_20260717.md
```

## 主要輸出檔

SRR 全樣本：

```text
results/srr_lite_shadow_backtest_20250102_20260716_tuned.json
results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv
```

SRR crash windows：

```text
results/srr_lite_shadow_crash_2015_china_20150601_20160229.json
results/srr_lite_shadow_crash_2018_trade_war_20180101_20181231.json
results/srr_lite_shadow_crash_2020_covid_20200102_20200630.json
results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031.json
results/srr_lite_shadow_crash_2026_q1q2_20260201_20260430.json
results/srr_lite_shadow_crash_2026_recent_20260515_20260716.json
```

SRR ensemble：

```text
results/srr_lite_ensemble_shadow_20250102_20260716.json
results/srr_lite_ensemble_shadow_2018_trade_war_20180101_20181231.json
results/srr_lite_ensemble_shadow_2020_covid_20200102_20200630.json
results/srr_lite_ensemble_shadow_2026_q1q2_20260201_20260430.json
results/srr_lite_ensemble_shadow_2026_recent_20260515_20260716.json
```

Cross-market：

```text
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
results/srr_lite_ensemble_shadow_with_cross_market_full_20250102_20260716.json
results/cross_market_graph_daily_scorecard_20260716.json
results/cross_market_graph_threshold_sweep_20260716.json
```

Daily signal smoke：

```text
results/group_a_plus_latest_strategy_predict_20260717_srr_lite_crash_watch.json
results/group_a_plus_latest_strategy_predict_20260717_srr_lite_crash_watch_latest_pointer.json
```

## 關鍵回測摘要

### SRR no-add，全樣本 2025-01-02 ~ 2026-07-16

```text
active_days = 8
H10 precision = 50.0%
H10 recall = 3.1%
H10 FPR = 1.5%
```

### SRR crash-watch，2020 COVID

```text
active_days = 7
H10 precision = 85.7%
H10 recall = 17.1%
H10 FPR = 1.1%
```

### SRR crash + GARCH，2020 COVID

```text
active_days = 3
H10 precision = 100.0%
H10 recall = 8.6%
H10 FPR = 0.0%
```

但不升級，因為 2026 Q1/Q2 與 2026 Recent 會漏掉 SRR 有效提示。

### Cross-market graph，整體 2021-01-28 ~ 2026-07-08

```text
active_days = 25
precision = 40.0%
recall = 2.7%
FPR = 1.6%
```

### Cross-market threshold / margin sweep

最佳規則：

```text
prob_NO_ADD >= 0.65
margin >= 0.10

active_days = 21
precision = 47.6%
recall = 2.7%
FPR = 1.2%
```

沒有 practical candidate。

## 已執行驗證

最後驗證：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_cross_market_graph_shadow.py tests/test_leveraged_compounding_regime.py tests/test_group_a_plus_srr_lite_shadow.py -q
```

結果：

```text
10 passed
```

也已對新增 evaluate/export/sweep 腳本執行 `py_compile`，皆通過。

## 後續建議

短期：

```text
停止升級。
觀察 daily signal 的 SRR shadow 欄位。
不要接新的 live guard。
```

中期：

```text
累積 2026-2027 新樣本。
重新跑 SRR crash-watch 與 cross-market scorecard。
檢查 crash_watch_active 是否常常單獨誤報。
```

長期：

```text
若要追求「最佳」，需做 walk-forward threshold calibration。
需拆 train / validation / holdout crisis windows。
需納入實際交易成本、turnover 與 decision impact。
在此之前，不應稱為最佳自動交易策略。
```
