# SRR-lite Shadow 交接記錄 - 2026-07-16

## 目前狀態

SRR-lite 已加入專案，但定位為 shadow diagnostic：

```text
用途：00631L no-add / crash watch 參考
狀態：research-only + live shadow
自動調倉：否
阻擋交易：否
改變 target weights：否
```

每日訊號會輸出 `srr_lite_shadow`，但只有在 `no_add_active=true` 時才會產生 alert。即使 alert 觸發，也只代表人工檢查與暫停新增 00631L 的參考，不會自動賣出、降權重或覆寫策略。

2026-07-16 追加導入第二層：

```text
crash_watch_active
```

`crash_watch_active` 是早期 crash watch 提示，只做人工檢查，不會阻擋 `00631L` 新增、不會改 target weights，也不會取代 `no_add_active`。

## 新增與修改檔案

### SRR-lite 診斷模組

```text
group_a_plus/integrations/srr_lite_shadow.py
```

功能：

- 讀取 `ohlcv` 與 `external_market_ohlcv`。
- 建立 7 日 Spearman correlation graph。
- 計算：
  - `systemic_fragility_score`
  - `graph_density`
  - `avg_abs_corr`
  - `density_z`
  - `graph_velocity`
  - `core_max_centrality`
- 輸出 shadow-only policy 欄位。

目前 live no-add 條件：

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

目前 live crash-watch 條件：

```text
systemic_fragility_score >= 0.75
graph_density >= 0.65
```

兩者差異：

```text
no_add_active:
  低頻、保守、可作為暫停新增 00631L 的人工參考

crash_watch_active:
  較早期、較敏感、只提示人工 crash risk review
  不阻擋交易
  不改權重
```

### Daily Signal 接入

```text
group_a_plus/operations/daily_signal.py
```

新增：

- `compute_srr_lite_shadow(...)`
- payload 欄位：`srr_lite_shadow`
- alert 類型：`srr_lite_systemic_fragility_shadow`
- alert 類型：`srr_lite_crash_watch_shadow`

alert 條件：

```text
srr_lite_shadow.no_add_active == true
```

crash-watch alert 條件：

```text
srr_lite_shadow.crash_watch_active == true
and
srr_lite_shadow.no_add_active != true
```

alert 語意：

```text
manual-review no-add reference for 00631L only
does not change target weights
```

crash-watch alert 語意：

```text
early manual-review hint only
does not block 00631L adds
does not change target weights
```

### 回測腳本

```text
scripts/evaluate/evaluate_srr_lite_shadow.py
```

功能：

- 指定 `--start` / `--end` 做 SRR-lite historical backtest。
- 產生 JSON summary。
- 產生逐日 `_frame.csv`。
- 計算 5 日與 10 日 forward label。
- 新增 `rule_sweep_top10`，比較不同 `score/density/velocity` 門檻。

標籤定義：

```text
no_add_label_h5/h10 =
  00631L forward relative return vs 0050 <= -1%
  or
  00631L forward MDD <= -5%
```

### 測試

```text
tests/test_group_a_plus_srr_lite_shadow.py
```

已覆蓋：

- 高相關尾端資料應觸發 fragility / no-add。
- 低相關資料不應誤觸 no-add。

## 變更原因

使用者提供論文：

```text
C:\Users\isaac\Downloads\2512.17185v1.pdf
Systemic Risk Radar: A Multi-Layer Graph Framework for Early Market Crash Prediction
```

評估後採用其中「市場相關網路作為系統性風險雷達」概念，但沒有直接導入完整 GNN / 多層圖模型，原因：

- 論文本身仍偏 preliminary。
- 實驗中 GNN 結果不穩定。
- 多層圖尚未完整驗證。
- 直接改變倉位風險太高。

因此採用 SRR-lite：

```text
correlation-layer only
shadow-only
no automatic allocation
```

## 門檻微調記錄

初版條件：

```text
systemic_fragility_score >= 0.65
```

全樣本 2025-01-02 ~ 2026-07-16 回測：

```text
active days = 38
H10 precision = 34.2%
H10 false positive rate = 9.2%
```

問題：

- 觸發天數偏多。
- 作為 no-add shadow 會造成過多人工檢查。

調整後條件：

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

全樣本 2025-01-02 ~ 2026-07-16 回測：

```text
active days = 8
H5 precision = 37.5%
H5 false positive rate = 1.69%
H10 precision = 50.0%
H10 false positive rate = 1.48%
```

選擇理由：

- 保留原本 `score >= 0.65` 語意。
- 要求市場連動密度夠高。
- 要求相關結構近期有明顯變化。
- 相比直接拉高到 `score >= 0.75`，較不容易只對少數歷史窗口過度配適。

## Crash Window 回測記錄

詳細報告：

```text
docs/SRR_LITE_CRASH_WINDOW_BACKTEST_20260716.md
```

跑過的 window：

```text
2015 China crash: 2015-06-01 ~ 2016-02-29
2018 Trade War: 2018-01-01 ~ 2018-12-31
2020 COVID: 2020-01-02 ~ 2020-06-30
2022 Rate Hike: 2022-01-03 ~ 2022-10-31
2026 Q1/Q2: 2026-02-02 ~ 2026-04-30
2026 Recent: 2026-05-15 ~ 2026-07-16
```

結果摘要：

```text
2015 China:
  active days = 4
  H10 precision = 25.0%
  H10 FPR = 2.3%

2018 Trade War:
  active days = 6
  H10 precision = 16.7%
  H10 FPR = 2.9%

2020 COVID:
  active days = 0
  H10 recall = 0.0%

2022 Rate Hike:
  active days = 1
  H10 precision = 100.0%
  H10 FPR = 0.0%

2026 Q1/Q2:
  active days = 3
  H10 precision = 66.7%
  H10 FPR = 2.1%

2026 Recent:
  active days = 1
  H10 precision = 100.0%
  H10 FPR = 0.0%
```

解讀：

- 現行 live 規則非常保守。
- 近期 2026 壓力區效果不錯。
- 2022 效果不錯但 recall 很低。
- 2018 偏弱。
- 2020 COVID 完全沒有觸發。

結論：

```text
可作為低頻 no-add shadow。
不可視為完整 crash detector。
```

## Crash Variant 檢查

額外檢查候選規則：

```text
systemic_fragility_score >= 0.75
graph_density >= 0.65
velocity 不強制
```

優點：

```text
2020 COVID:
  active days = 7
  H10 precision = 85.7%
  H10 FPR = 1.1%

2018 Trade War:
  active days = 19
  H10 precision = 68.4%
  H10 FPR = 3.5%

2026 Recent:
  active days = 2
  H10 precision = 100.0%
  H10 FPR = 0.0%
```

缺點：

```text
2025-01-02 ~ 2026-07-16 full sample:
  active days = 18
  H10 precision = 27.8%
  H10 FPR = 4.8%
  active days 的 H10 平均相對 0050 報酬為正
```

決策：

```text
不升級為 live no-add。
導入為第二層 crash_watch_active。
只做人工檢查提示，不阻擋策略、不改權重。
```

2026-07-16 導入後驗證 2020 COVID：

```text
crash_watch_active days = 7
dates =
  2020-02-11
  2020-02-13
  2020-02-14
  2020-02-17
  2020-02-18
  2020-02-19
  2020-03-16
```

## 2026-07-17 Daily Signal Smoke

輸出：

```text
results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned.json
results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned_latest_pointer.json
```

SRR-lite 結果：

```text
actual_date = 2026-07-16
systemic_fragility_score = 0.3694
fragility_level = normal
no_add_active = false
crash_watch_active = false
allow_auto_weight_change = false
allow_crash_watch_auto_weight_change = false
allow_00631l_add_reference = true
signal_alerts = []
```

target weights：

```text
0050.TW = 50.0%
00631L.TW = 約 19.989%
cash = 約 30.011%
```

## 驗證

已執行：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_srr_lite_shadow.py -q
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --output results/srr_lite_shadow_backtest_20250102_20260716_tuned.json
.venv/bin/python -m group_a_plus.operations.daily_signal --as-of 2026-07-17 --portfolio-value 1000000 --output results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned.json --latest-pointer results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned_latest_pointer.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2020-01-02 --end 2020-06-30 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2020_covid_20200102_20200630_crash_watch.json
.venv/bin/python -m group_a_plus.operations.daily_signal --as-of 2026-07-17 --portfolio-value 1000000 --output results/group_a_plus_latest_strategy_predict_20260717_srr_lite_crash_watch.json --latest-pointer results/group_a_plus_latest_strategy_predict_20260717_srr_lite_crash_watch_latest_pointer.json
```

結果：

```text
SRR-lite unit tests: 2 passed
Full-sample backtest: 成功
2026-07-17 daily signal smoke: 成功
Crash-window backtests: 成功
2020 COVID crash-watch backtest: 成功
```

## 輸出檔案

全樣本：

```text
results/srr_lite_shadow_backtest_20250102_20260716_tuned.json
results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv
```

Crash windows：

```text
results/srr_lite_shadow_crash_2015_china_20150601_20160229.json
results/srr_lite_shadow_crash_2015_china_20150601_20160229_frame.csv
results/srr_lite_shadow_crash_2018_trade_war_20180101_20181231.json
results/srr_lite_shadow_crash_2018_trade_war_20180101_20181231_frame.csv
results/srr_lite_shadow_crash_2020_covid_20200102_20200630.json
results/srr_lite_shadow_crash_2020_covid_20200102_20200630_frame.csv
results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031.json
results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031_frame.csv
results/srr_lite_shadow_crash_2026_q1q2_20260201_20260430.json
results/srr_lite_shadow_crash_2026_q1q2_20260201_20260430_frame.csv
results/srr_lite_shadow_crash_2026_recent_20260515_20260716.json
results/srr_lite_shadow_crash_2026_recent_20260515_20260716_frame.csv
results/srr_lite_shadow_crash_2020_covid_20200102_20200630_crash_watch.json
results/srr_lite_shadow_crash_2020_covid_20200102_20200630_crash_watch_frame.csv
```

文件：

```text
docs/CHANGELOG_20260716_SRR_LITE_SHADOW.md
docs/SRR_LITE_CRASH_WINDOW_BACKTEST_20260716.md
docs/SRR_LITE_ENSEMBLE_SHADOW_20260716.md
docs/HANDOFF_SRR_LITE_SHADOW_20260716.md
docs/FINAL_HANDOFF_SRR_LITE_CROSS_MARKET_20260717.md
```

## 後續建議

2026-07-16 已完成第一版 ensemble 評估：

```text
scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py
docs/SRR_LITE_ENSEMBLE_SHADOW_20260716.md
```

結論：

```text
SRR crash + GARCH 在 2018/2020 precision 很高。
但在 2026 Q1/Q2 與 2026 Recent 會漏掉 SRR 自己有效的提示。
因此不建議把 ensemble 接入 live guard。
```

同日也完成 cross-market graph daily frame 工具：

```text
scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py
  新增 action_model.prediction_frame

scripts/evaluate/export_cross_market_graph_prediction_frame.py
  將 prediction_frame 匯出 CSV
```

完整 production-like 長窗口 frame 已完成：

```text
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json
results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv
results/srr_lite_ensemble_shadow_with_cross_market_full_20250102_20260716.json
```

結論：

```text
cross-market graph 在 2022 有獨立 NO_ADD 訊號。
但它沒有覆蓋 2020 COVID，也沒有覆蓋 2026 Recent 的 SRR 有效提示。
SRR crash + cross-market 在 2025-2026 全樣本 active days = 0。
因此不建議把 cross-market 當成 SRR crash_watch_active 的必要確認條件。
```

cross-market 獨立 daily scorecard 也已完成：

```text
docs/CROSS_MARKET_GRAPH_DAILY_SCORECARD_20260716.md
results/cross_market_graph_daily_scorecard_20260716.json
results/cross_market_graph_threshold_sweep_20260716.json
```

結論：

```text
整體 precision = 40.0%，recall = 2.7%。
訊號主要集中在 2022。
2025 完全不觸發。
2026 唯一觸發是 false positive。
因此也不建議升級為 live alert。
```

Threshold / margin sweep 結論：

```text
最佳規則 = prob_NO_ADD>=0.65 and margin>=0.10
active_days = 21
precision = 47.6%
recall = 2.7%
FPR = 1.2%

2022 Rate Hike precision = 57.1%
2025-2026 active_days = 0
2026 Q1/Q2 active_days = 0
2026 Recent active_days = 0

沒有 practical candidate。
```

短期：

```text
維持目前 live no-add 規則。
不要讓 SRR-lite 直接改倉位。
crash_watch_active 已導入，但只做人工檢查提示。
不要用 crash_watch_active 覆蓋 live no-add。
不要用 ensemble 覆蓋 crash_watch_active。
```

中期：

```text
觀察 crash_watch_active 與其他 shadow 訊號是否重疊。
若 crash_watch_active 經常單獨觸發但後續無風險，需再提高門檻或加 regime filter。
```

長期：

```text
做 walk-forward / out-of-sample 門檻校準。
加入更多 crisis 樣本。
若要再推進 ensemble，應研究 cross-market 作為獨立 advisory，而不是 SRR 的確認條件。
cross-market graph 下一步應做 threshold/margin sweep，而不是接 live。
threshold/margin sweep 已完成，仍不支持接 live。
```
