# GroupA+ Ops 修復 + Re-entry Accelerator 研究 Handoff - 2026-07-10

## 一句話

使用者問「Group A+ 還有什麼可以改善」，逐一處理了 3 件事：(1) execution plan 過期 11.7 天且跟 volatility gate 沒對齊，已修復；(2) TSMC 在 0050 的權重假設從未校準，已用官方揭露資料校準；(3) 用回補的 NCF panel 對 A22_bad_vol_overlay 做真正 out-of-sample 驗證，**發現 6 輪調參是 overfitting，champion 配置在真實資料上失效，A22 這條線也暫停**。過程中意外修好一個 production 腳本的真 bug。後續使用者追問「de-risk 之後要有 re-entry accelerator」，發現這個機制已存在但從沒驗證過，測完後是「尚不足以 promote，但比 A22 健康」的結論。

## 1. execution plan 過期 + volatility gate 未對齊（已修復，操作性）

**問題**：`report/group_a_plus/latest/execution_plan.json` 停在 2026-06-28（用 `taiwan_stock_20260626.xlsx` 跑的），但實際持股 workbook 已經更新到 `taiwan_stock_20260710.xlsx`（0050 從 1,754 股變 2,394 股、00631L 從 10 股變 320 股，代表帳戶有真實交易但執行計畫沒跟上），落後 11.7 天（正常上限 3 天）。同時 `volatility_gate_active=true` 但 execution plan 沒反映當下的 pre-trade guard 狀態。

**修復**：

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260710.xlsx \
  --cash-balance 0
```

（`--latest-pointer` 預設值就是 `report/group_a_plus/latest/execution_plan.json`，不用另外指定）

因為 workbook 沒有現金欄位、使用者當下沒有立刻提供真實現金餘額，**這次用 `--cash-balance 0` 只是為了讓 ops_health 的過期警告消掉，不能拿去對照實際下單**。下次要出真正能拿去下單的 execution plan，必須用使用者提供的真實現金餘額重跑。

修復後 `ops_health` 驗證：`artifact_health.execution_plan_freshness` 從 `stale`(11.7天) 變 `fresh`，`volatility_gate_execution_guard` 從有警告變 `ok`(`execution_plan_aligned=true`)，正確顯示 `pre_trade_guard.status=blocked`（00631L 加碼被高波動 gate 擋住，`reference_00631l_scale=0.5`）。

## 2. TSMC 在 0050 權重假設校準（已修復，操作性）

**問題**：`group_a_plus/utils/tsmc_0050_weight.py`（2026-07-08 Fable audit 建的 single source of truth）`TSMC_0050_WEIGHT_ASSUMPTION=0.55` 且 `AS_OF=None`，從未校準過，`ops_health` 持續警告 `tsmc_0050_weight_assumption_uncalibrated`。

**先試了不可靠的方法**：用本地 DB 的 0050.TW 跟 `external_market_ohlcv` 的 2330.TW 日報酬做 OLS 迴歸估權重，60/120/252/504 天窗口都測了，結果 0.74~0.83，遠高於已知合理範圍(55-58%)。**判斷這個方法有系統性偏誤**：0050 裡其他大型權值股（聯發科、鴻海等）本身也跟 2330 同向連動（共同市場/半導體類股 beta），單一持股對指數報酬迴歸出來的 beta 會被這個共同因子放大。**已在程式碼註解記錄這個方法失敗的原因，避免以後重複嘗試。**

**改用真實揭露資料**：WebSearch + WebFetch 元大投信官方 0050 持股頁面(`https://www.yuantaetfs.com/product/detail/0050/ratio`)，資料日期 2026-07-09，台積電權重 **58.31%**。已更新常數為 `TSMC_0050_WEIGHT_ASSUMPTION=0.5831`、`TSMC_0050_WEIGHT_ASSUMPTION_AS_OF="2026-07-10"`，`MAX_AGE_DAYS=180` 不變（2027-01-06 左右要重查）。

更新了 `tests/test_group_a_plus_ops_health.py`：原本測「AS_OF=None 必須 warning」的測試改成測「校準後必須 ok」；新增獨立測試 `tsmc_0050_weight_assumption_is_stale()` 本身在 181 天後跟 30 天後的行為（用 `TSMC_0050_WEIGHT_ASSUMPTION_AS_OF` 動態算相對日期，避免 hardcode drift）。相關測試(ops_health/daily_signal_v2/signal_alignment/ncf_2330 系列)全過。

修復後 `ops_health.warnings` 從 4 項降到 2 項（剩 `pipeline_health`、`external_data_freshness`，跟這次修復無關；`errors` 仍有 `system_resources` 磁碟，使用者已明確要求不要碰不要提）。

## 3. A22_bad_vol_overlay out-of-sample 驗證 — champion 配置失效，這條線也暫停

完整時間軸見 `GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md` 附錄末尾。摘要：

- A22 champion（`good_drawdown_min=-0.06` + `bad_cap=bad_no_vol_cap=0.0` + `neutral_cap` no-op + `bad_persistence_days=8`）在 covid_2020/inflation_2022/live_2024_2026/active_2025_2026 這 4 個固定窗口上跑了 6 輪 coordinate descent，sum Sharpe 從 +0.001 推進到 +0.045，看起來持續在進步。
- 使用者要求「現在就做」NCF panel 回補以取得真正 out-of-sample 驗證。用 `scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start 2017-01-01 --val-end 2019-12-31 --full-panel` 回補。
- **第一次跑直接 crash**：`ValueError: Length of values (605) does not match length of index (125)`。定位到 production 腳本一個真 bug：熊市 regime 的 fallback 邏輯 `if (~above_ma200_val).sum()==0 or (~above_ma200_train_clf).sum()<20: clf_bear = clf_bull`，這個 OR 條件在「熊市訓練樣本 <20 天」時也會誤觸發 fallback，即使驗證集熊市天數充足（這次 n_bull=605/n_bear=125）。後果：熊市預測陣列借用長度不對的牛市陣列，`--full-panel` 模式崩潰。**已修復**（`scripts/misc/ncf_00631l.py` 兩處消費 `clf_bear["ensemble"]["proba"]` 的地方，偵測到 `clf_bear is clf_bull` 時改用長度正確的中性 0.5 機率陣列），2020-2026 production 路徑沒受影響（沒撞到這個分支）。
- 修好後產出 `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`（2017-01-03~2019-12-31，731 天，之前完全不存在）。
- 用這份全新 panel 對 A22 champion 測 2017/2018/2019 三個完整年度：三年加總 **Δfinal_value=-17,691、ΔSharpe=-0.058**，完全沒有重現 4 個 tuned windows 上的正向結果。

**結論：A22_bad_vol_overlay 也暫停，不可 promote。這是本次 session 最重要的方法論教訓**：同一組固定窗口上超過 2-3 輪參數搜尋後，進步的可信度要打折扣，必須做 out-of-sample 驗證才能宣稱真的變好。已寫成獨立記憶 `feedback_overfitting_fixed_window_tuning`，適用於未來任何策略研究。

## 4. Re-entry accelerator（a2124）研究 — 尚不足以 promote，但比 A22 健康

使用者追問「de-risk 之後要有 re-entry accelerator，有這種東西?」

**發現**：已存在，從沒被評估過。`group_a_plus/runners/a2118.py` 的 `_apply_golden_rebound_recapture_overlay`：偵測到「急殺後反彈確認」就把 00631L 權重短暫 boost。`group_a_plus/runners/a2124.py`（shadow candidate，`status=research_candidate`）把這個跟「急殺後續跌小幅減碼」(follow-through trim) 綁在一起，是完整的「de-risk → 反彈確認 → 加速回補」組合。跟 a2126 一樣，是先前 session 留下的 uncommitted 草稿，沒有評估腳本測過。

**第一輪測試**（用 a2124 內建、從沒調過的預設參數，`scripts/evaluate/evaluate_group_a_plus_a2124_rebound_recapture.py`，從一開始就同時測 4 個 tuning windows + 2017/2018/2019 三個 OOS windows）：

| | tuning windows 加總 | OOS windows 加總 |
|---|---:|---:|
| ΔSharpe | +0.108 | -0.0003（幾乎零） |
| Δfinal_value | -176,935 | -3,368 |

**最大問題：trigger 太少**——7 個窗口、橫跨約 6.5 年資料，recapture 總共只觸發 **3 次**，follow-through trim 總共只觸發 **8 次**。樣本量太小，無法下結論（不算通過，也不算否決）。

**第二輪：放寬觸發條件**（先驗性地把每個門檻大致砍半，不是看結果調的；sizing 不動）。為此把 `_apply_golden_rebound_recapture_overlay` 裡原本寫死的 shock 判斷門檻(`tail_risk_score>=2`、`return<=-0.03`)改成參數 `shock_tail_risk_score_min`/`shock_return_max`，串進 `run_a2118` 的 kwargs 跟 CLI（`--golden-rebound-recapture-shock-tail-risk-score-min`/`--golden-rebound-recapture-shock-return-max`，預設值不變，不影響既有呼叫）：

| | a2124 預設 | 放寬觸發 |
|---|---:|---:|
| 總 trim/recapture 天數 | 8 / 3 | 56 / 18 |
| tuning sum ΔSharpe | +0.108 | +0.050 |
| OOS sum ΔSharpe | -0.0003 | **+0.0040（轉正）** |
| tuning/OOS sum Δfv | -176,935 / -3,368 | -261,065 / -6,531 |

**判斷**：樣本量明顯改善，且 Sharpe 方向在 tuning 跟 OOS 之間變得一致（都是小幅正值）——跟 A22「tuning 正、OOS 大幅反轉負」完全不同，是健康很多的訊號，看起來不是 overfitting 產物。但 final value 在 tuning 跟 OOS 兩邊都持續變差，且放寬後虧損幅度變大——這是真實、一致的「犧牲一點絕對報酬換取風險調整後報酬小幅改善」的 trade-off。18 次事件仍偏少、OOS 的 Sharpe 改善幅度(+0.004)相對雜訊很小，**尚不足以宣稱驗證通過**。

## 主要檔案

Ops 修復：

- `group_a_plus/utils/tsmc_0050_weight.py`（已校準）
- `tests/test_group_a_plus_ops_health.py`（已更新對應測試）
- `report/group_a_plus/latest/execution_plan.json`（已刷新，注意 cash-balance=0 是驗證版本）

A22 out-of-sample + ncf_00631l bug 修復：

- `scripts/misc/ncf_00631l.py`（熊市 fallback 長度不匹配 bug 已修復）
- `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`（新回補的 2017-2019 panel，永久可重用）
- `tests/test_ncf_00631l_paths.py`（既有測試，驗證無 regression）

Re-entry accelerator：

- `group_a_plus/runners/a2118.py`（`_apply_golden_rebound_recapture_overlay` 新增 `shock_tail_risk_score_min`/`shock_return_max` 參數 + CLI）
- `group_a_plus/runners/a2124.py`（既有 shadow candidate，本次才第一次被評估）
- `scripts/evaluate/evaluate_group_a_plus_a2124_rebound_recapture.py`（新腳本，同時跑 tuning + OOS windows，含 `a2124_default`/`loosened_trigger` 兩個 variant）
- `tests/test_group_a_plus_a2124.py`（既有測試，驗證無 regression）
- `results/group_a_plus_a2124_rebound_recapture_20260710.json`

## 目前風險與注意事項

- execution plan 的 cash-balance=0 版本**不能拿去對照實際下單**，下次正式下單前要用真實現金餘額重跑。
- TSMC 權重 180 天內(到 2027-01-06 左右)不用再查，之後 `tsmc_0050_weight_assumption_is_stale()` 會自動再警告。
- **A22_bad_vol_overlay 全線暫停，不可 promote**（race classifier 線也是，理由不同：前者是 OOS 驗證失敗，後者是四輪嘗試都推翻）。
- a2124 re-entry accelerator 是獨立候選，尚不足以 promote，但方向性比 A22 健康，值得未來持續累積真實 trigger 事件觀察。
- 不要重複嘗試用 0050/2330 報酬迴歸校準 TSMC 權重，已證實有系統性高估偏誤。

## 下一步建議

1. 下次正式下單前，重跑一次帶真實現金餘額的 execution plan。
2. `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv` 是最有價值的既有資產——任何後續 00631L 相關研究都應該先用它做 out-of-sample check，而不是又在 2025-2026 那組窗口上疊代。
3. a2124 re-entry accelerator 如果要繼續投入，優先方向是累積更多真實 trigger 事件（可能需要更長歷史、或進一步審視觸發條件設計），而不是繼續調 sizing 參數。
4. `group_a_plus/runners/a2126.py`（golden1 leverage cap）也是同一批未評估的 uncommitted 草稿，其 15% 上限預設值是 no-op（golden1 本身 00631L 只有 ~10.9%），如果之後要用它要先修這個參數才有意義，且應該用同樣的 tuning+OOS 雙軌驗證方式。
