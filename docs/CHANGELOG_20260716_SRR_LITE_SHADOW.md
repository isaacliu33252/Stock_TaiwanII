# 2026-07-16 SRR-lite Shadow 微調變更記錄

## 背景

使用者提供 `2512.17185v1.pdf` 後，評估該論文的 Systemic Risk Radar 概念可作為「系統性風險雷達」。因原論文仍偏研究型，且 GNN/多層圖結果尚未足以直接改變交易權重，本專案採用保守做法：只新增 SRR-lite shadow 診斷，不自動改變 `0050`、`00631L` 或現金權重。

## 本次變更

1. 新增 SRR-lite shadow 診斷模組：
   - 檔案：`group_a_plus/integrations/srr_lite_shadow.py`
   - 使用近 7 日 Spearman 相關係數建立市場相關網路。
   - 觀察圖密度、平均絕對相關、密度突增、圖速度與核心商品中心性。
   - 輸出 `systemic_fragility_score`、`fragility_level`、`no_add_active`、`metrics`、`thresholds`。

2. 接入每日訊號：
   - 檔案：`group_a_plus/operations/daily_signal.py`
   - 每日訊號 payload 增加 `srr_lite_shadow`。
   - 僅當 `no_add_active=true` 時新增 `srr_lite_systemic_fragility_shadow` alert。
   - alert 明確標示 `shadow_only_no_weight_change`，不會自動改變 target weights。

3. 新增 SRR-lite 測試：
   - 檔案：`tests/test_group_a_plus_srr_lite_shadow.py`
   - 驗證高度相關尾端資料會產生風險提示。
   - 驗證低相關資料不會誤觸 no-add。

4. 新增 SRR-lite 回測工具：
   - 檔案：`scripts/evaluate/evaluate_srr_lite_shadow.py`
   - 輸出 JSON 報告與逐日 frame CSV。
   - 評估 5 日與 10 日後 `00631L` 相對 `0050` 弱勢或前瞻最大跌幅。
   - 新增 `rule_sweep_top10`，比較不同 `score/density/velocity` 門檻組合。

## 微調內容

初版 no-add 條件只有：

```text
systemic_fragility_score >= 0.65
```

回測顯示此規則在 2025-01-02 到 2026-07-16 期間觸發 38 天，10 日 false positive rate 約 9.2%，警示偏多。

本次改成：

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

選這組的原因：

- 保留原本 `score >= 0.65`，避免過度大幅改變既有語意。
- 加入 `graph_density >= 0.65`，要求市場連動真的夠密。
- 加入 `graph_velocity >= 0.18`，要求相關結構近期有明顯變化。
- 相比直接升到 `score >= 0.75`，此版本較不容易因樣本少而過度配適。

## 回測摘要

輸出：

- `results/srr_lite_shadow_backtest_20250102_20260716_tuned.json`
- `results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv`

期間：2025-01-02 到 2026-07-16，共 399 筆。

調整後預設規則：

- active days：8 天
- 5 日 precision：37.5%
- 5 日 false positive rate：1.69%
- 10 日 precision：50.0%
- 10 日 false positive rate：1.48%
- active days 的 10 日平均 `00631L` 前瞻 MDD：約 -4.97%
- inactive days 的 10 日平均 `00631L` 前瞻 MDD：約 -3.62%

與初版 `score >= 0.65` 相比：

- active days：38 天降到 8 天
- 10 日 precision：34.2% 升到 50.0%
- 10 日 false positive rate：9.2% 降到 1.5%
- recall 仍低，因此它不適合作為完整風險偵測器，只適合作為低頻 no-add shadow。

## 2026-07-17 smoke 結果

輸出：

- `results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned.json`
- `results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned_latest_pointer.json`

SRR-lite 狀態：

- `systemic_fragility_score`: 0.3694
- `fragility_level`: `normal`
- `no_add_active`: `false`
- `allow_auto_weight_change`: `false`
- `signal_alerts`: 無 SRR-lite alert

target weights 維持：

- `0050.TW`: 50.0%
- `00631L.TW`: 約 19.989%
- `cash`: 約 30.011%

## 風險與限制

- SRR-lite 仍為 shadow 診斷，不應直接拿來賣出或降槓桿。
- 目前樣本只有 2025-01-02 到 2026-07-16，重大危機樣本不足。
- `rule_sweep_top10` 是研究輔助，不代表最佳未來規則。
- 若未來要正式加入倉位調整，需先做 walk-forward、out-of-sample 與交易成本測試。

## 驗證

已執行：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_srr_lite_shadow.py -q
.venv/bin/python scripts/evaluate/evaluate_srr_lite_shadow.py --output results/srr_lite_shadow_backtest_20250102_20260716_tuned.json
.venv/bin/python -m group_a_plus.operations.daily_signal --as-of 2026-07-17 --portfolio-value 1000000 --output results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned.json --latest-pointer results/group_a_plus_latest_strategy_predict_20260717_srr_lite_tuned_latest_pointer.json
```

結果：

- SRR-lite 單元測試：2 passed
- 回測報告成功輸出
- 2026-07-17 每日訊號 smoke 成功輸出
