# SRR-lite Crash Window 回測報告 - 2026-07-16

## 目的

針對 SRR-lite shadow no-add 診斷，在歷史壓力區間做分段回測，確認目前 live 規則是否能在 crash window 中提前標示 `00631L` 風險。

本報告只評估 shadow 訊號，不改變策略權重、不改變 daily signal 行為。

## 資料限制

SRR-lite 使用以下節點：

```text
0050.TW, 00631L.TW, 00632R.TW, 00679B.TWO, 2330.TW, SOXX, TSM, TWD=X
```

目前資料覆蓋：

- `00631L.TW`：2015-01-05 起。
- `2330.TW`, `SOXX`, `TSM`, `TWD=X`：2014 起。
- `00679B.TWO`：2017-01-11 起，不足時會被 SRR-lite 自動排除。

因此 2008/2011 不能用同一組真實 SRR-lite 節點公平回測；本次只跑 2015 之後有足夠資料的 crash windows。

## Live 規則

目前 live no-add 條件：

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

標籤定義：

```text
no_add_label_h5/h10 = 00631L 相對 0050 前瞻報酬 <= -1%
                    或 00631L 前瞻 MDD <= -5%
```

## 分段結果

| Window | 日期 | Rows | Active days | H5 Precision | H5 Recall | H5 FPR | H10 Precision | H10 Recall | H10 FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 China crash | 2015-06-01 ~ 2016-02-29 | 197 | 4 | 50.0% | 4.4% | 1.3% | 25.0% | 1.6% | 2.3% |
| 2018 Trade War | 2018-01-01 ~ 2018-12-31 | 261 | 6 | 16.7% | 1.6% | 2.5% | 16.7% | 1.1% | 2.9% |
| 2020 COVID | 2020-01-02 ~ 2020-06-30 | 129 | 0 | 無觸發 | 0.0% | 0.0% | 無觸發 | 0.0% | 0.0% |
| 2022 Rate Hike | 2022-01-03 ~ 2022-10-31 | 216 | 1 | 100.0% | 1.2% | 0.0% | 100.0% | 0.8% | 0.0% |
| 2026 Q1/Q2 | 2026-02-02 ~ 2026-04-30 | 64 | 3 | 66.7% | 14.3% | 2.0% | 66.7% | 11.8% | 2.1% |
| 2026 Recent | 2026-05-15 ~ 2026-07-16 | 45 | 1 | 100.0% | 5.9% | 0.0% | 100.0% | 4.2% | 0.0% |

## Active Dates

2015 China crash：

```text
2015-06-29, 2015-07-30, 2015-11-13, 2016-01-07
```

2018 Trade War：

```text
2018-01-10, 2018-05-03, 2018-06-04, 2018-08-13, 2018-08-22, 2018-12-05
```

2020 COVID：

```text
無
```

2022 Rate Hike：

```text
2022-10-07
```

2026 Q1/Q2：

```text
2026-02-24, 2026-03-03, 2026-04-09
```

2026 Recent：

```text
2026-06-25
```

## 解讀

目前 live 規則非常保守：

- 優點：false positive rate 很低，2022 與 2026 壓力區間觸發品質不錯。
- 缺點：recall 很低，2020 COVID 完全沒有觸發，2018 Trade War 也偏弱。

這表示目前規則適合作為「低頻 no-add shadow」，不適合作為完整 crash detector。

## Crash Variant 檢查

另評估候選：

```text
systemic_fragility_score >= 0.75
graph_density >= 0.65
```

結果：

- 2020 COVID：active 7 天，H10 precision 85.7%，H10 FPR 1.1%。
- 2018 Trade War：active 19 天，H10 precision 68.4%，H10 FPR 3.5%。
- 2026 Recent：active 2 天，H10 precision 100.0%，H10 FPR 0.0%。

但在 2025-01-02 ~ 2026-07-16 全樣本：

- active 18 天。
- H10 precision 27.8%。
- H10 FPR 4.8%。
- active days 的 H10 平均相對 0050 報酬為正，並不穩定。

因此此候選不直接升級 live。它可作為後續「crash-mode 二階 alert」研究，但不能直接取代目前 live no-add 規則。

## 結論

不建議把 SRR-lite 改成主動倉位控制。

建議維持目前 live 規則：

```text
score >= 0.65
density >= 0.65
velocity >= 0.18
```

並把 crash variant 留在研究清單：

```text
score >= 0.75
density >= 0.65
velocity 不強制
```

後續若要改善 crash recall，應該做雙層 shadow：

- `no_add_active`：維持目前保守規則。
- `crash_watch_active`：使用 high-score/high-density 規則，只做更早期的人工檢查提示，不阻擋每日策略。

## 輸出檔案

```text
results/srr_lite_shadow_crash_2015_china_20150601_20160229.json
results/srr_lite_shadow_crash_2018_trade_war_20180101_20181231.json
results/srr_lite_shadow_crash_2020_covid_20200102_20200630.json
results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031.json
results/srr_lite_shadow_crash_2026_q1q2_20260201_20260430.json
results/srr_lite_shadow_crash_2026_recent_20260515_20260716.json
```

每個 JSON 旁邊都有同名 `_frame.csv`，可查逐日 score、density、velocity、label 與 forward return。

## 執行指令

```bash
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2015-06-01 --end 2016-02-29 --load-lookback-days 900 --output results/srr_lite_shadow_crash_2015_china_20150601_20160229.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2018-01-01 --end 2018-12-31 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2018_trade_war_20180101_20181231.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2020-01-02 --end 2020-06-30 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2020_covid_20200102_20200630.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2022-01-03 --end 2022-10-31 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2026-02-01 --end 2026-04-30 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2026_q1q2_20260201_20260430.json
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --start 2026-05-15 --end 2026-07-16 --load-lookback-days 1200 --output results/srr_lite_shadow_crash_2026_recent_20260515_20260716.json
```
