# GroupA+/GroupA++ Session Handoff - 2026-09-06

## Status

**已完結**。本文件彙整2026-09-06這次對話涵蓋的所有工作線，每條線都有獨立
的詳細記錄（連結見下），本檔案是導覽索引+關鍵決策摘要，供之後接手快速
掌握全貌，不必重讀整個對話。

## 一、論文審查：2604.24486（DRL/GNN/Transformer/Autoencoder portfolio比較）

**判定：closed_negative**，快速收斂（未展開全套Fable複查），理由是命中
三個已知瓶頸之一即可判定：(a) GroupA+資產池太小太相關，跨資產關係學習
類方法(GNN)無結構可學；(b) standalone RL policy不可靠，這是第三次在不同
論文/場景見到同一結論；(c) MVO類方法已被2606.26625證偽為overfitting假象。

詳細記錄：`project_2604_24486_dl_portfolio_comparative_desk_review_20260906.md`（記憶）

## 二、真實交易紀錄分析後續：00632R防守用途確認錯誤

使用者反思自己過去操作00632R虧損（見前一天`0501_0904.xlsx`分析），提出
「應該用現金取代00632R當防守」的假設。查證後確認：**production早在
2026-08-18就已經是這樣做**（`bond0_cash60`：0050 40%/cash 60%，無公債
無反向ETF），且唯一含00632R的候選`inverse10_bond20`在全歷史回測裡
**0/4壓力情境通過**。使用者的直覺跟已promote的設計一致。

詳細記錄：`project_00632r_defensive_use_confirmed_wrong_20260905.md`（記憶）

## 三、發現「GroupA++」：另一session已完整實作的00713現金sleeve機制

使用者提到「groupA++」，釐清是「GroupA+核心+00713常態持有」的自訂命名。
查證發現**另一個session已在2026-09-05完整實作、回測、驗證並正式上線**：

- 00713（元大台灣高息低波）以**純現金撥款**方式（不動0050/00631L）加入
  latest strategy，原始設定**10%**
- 額外做了NCF籌碼流動態閘門(`ncf_00713`)，但閘門本身**未證明能加值**
  （官方定位是風險閥門，非alpha來源）
- 完整技術文件：`GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md`

**我自己的失誤（已修正）**：一開始嘗試自己回測「00713從0050切一部分」的
假設完全錯誤（實際設計是從cash撥款）；且腳本monkey-patch共用的`TICKERS`
常數時沒發現它已經被改過，造成ticker重複、雙重計算，跑出不合理的誇張
數字——已刪除該腳本，改採信另一session的正確設計跟真實驗證結果。

**程式碼審查**：逐行讀完`_add_00713_cash_sleeve`/`_resize_00713_cash_sleeve`/
`ncf_00713_cash_sleeve_decision`三個核心函數，**乾淨無bug**——現金撥款
有上限保護、閘門disabled/訊號缺失都會fail-safe回base weight而非歸零。

詳細記錄：`project_groupa_plusplus_00713_discovery_and_gap_20260906.md`（記憶）

## 四、真實交易 vs 正式10%目標的落差分析

用使用者2026-05~09的真實交易紀錄反推：00713定期定額實際投入14,926元，
按當時10%目標比例應投入62,024元，**達成率僅24.1%，缺口47,098元**。
結論：使用者的00713定期定額方向正確（不是先前誤判的「策略外資金」），
只是金額遠低於正式目標。

（同收錄於：`project_groupa_plusplus_00713_discovery_and_gap_20260906.md`）

## 五、00713 sleeve權重決策：10% → 12%（正式生效）

使用者要求依序回測15%、12% vs 現行10%，並特別要求驗證COVID崩盤期間。

**方法**：`run_a2118(ncf_enabled=False)`隔離權重效果，測6個窗口（4個既有
標準窗口 + COVID全年 + COVID崩盤段獨立驗證）。

**關鍵發現——COVID崩盤段揭穿「權重越高越好」是溫和窗口的假象**：4個標準
窗口裡15%全面贏10%，但**只看崩盤段（不含後續反彈）**，權重越高
final value跟MDD都單調變差——00713終究是股票beta，取代現金會讓崩盤緩衝
變薄。2020全年數字好看只是後續反彈補回來掩蓋了崩盤當下的代價。

**最終決策**：12%（15%漲幅打對折，但崩盤段MDD代價只有15%的約4成，
-0.48pp vs -1.20pp），使用者知情取捨後選定。

**已執行的變更**：
1. `report/group_a_plus/latest/strategy.json`：
   `group_a_plusplus_00713_cash_sleeve_weight` 0.10 → 0.12
2. 重新跑`python3 -m group_a_plus.operations.daily_signal --as-of 2026-09-07
   --portfolio-value 1000000`，**正式regenerate了production
   `report/group_a_plus/latest/live_signal.json`**，確認target_weights
   的00713已經反映新的12%（120,000/1,000,000）

詳細記錄：
- `GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md`「2026-09-06 Follow-Up -
  Sleeve Weight Changed From 10% To 12%」段落（完整6窗口數據表）
- `project_groupa_plusplus_00713_weight_12pct_promoted_20260906.md`（記憶）

## 六、流程失誤：execution_plan.py再次覆蓋production latest pointer

測試「1.5M總額、只算GroupA++核心5檔」的09/07假設性情境時，用
`group_a_plus.operations.execution_plan`只設了`--output`到scratch，
**沒設`--latest-pointer`，導致真正的
`report/group_a_plus/latest/execution_plan.json`被假設性情境覆蓋**。
這正是`feedback_execution_plan_latest_pointer_default_overwrite`
（2026-07-27已記錄過）的同一個失敗模式，這次又踩到一次。

**發現方式**：工具本身印出"Latest pointer: report/group_a_plus/latest/
execution_plan.json"才注意到。

**修復**：用自動產生的`execution_plan.json.bak`立即復原到覆蓋前狀態
（2026-08-31，覆蓋前的真實production值）。之後所有what-if情境都改為
`--output`跟`--latest-pointer`都明確重導向到scratch，全部驗證production
未受影響。

## 檔案清單

本次對話新增/修改：
- `report/group_a_plus/latest/strategy.json`：00713 sleeve權重0.10→0.12
  **（正式production變更，已生效）**
- `report/group_a_plus/latest/live_signal.json`：重新regenerate反映12%
  **（正式production變更，已生效）**
- `report/group_a_plus/latest/execution_plan.json`：曾被誤覆蓋，已從
  `.bak`復原到覆蓋前狀態（未淨變更）
- `GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md`：新增今日6窗口回測+
  權重決策+流程失誤記錄章節
- 本檔案

新增記憶（4篇）：
- `project_2604_24486_dl_portfolio_comparative_desk_review_20260906.md`
- `project_00632r_defensive_use_confirmed_wrong_20260905.md`
- `project_groupa_plusplus_00713_discovery_and_gap_20260906.md`
- `project_groupa_plusplus_00713_weight_12pct_promoted_20260906.md`

已刪除（我自己的錯誤腳本，不採用）：
- `scripts/misc/evaluate_group_a_plus_golden1_lowvol_00713_carveout_20260906.py`
- `results/group_a_plus_golden1_lowvol_00713_carveout_20260906.json`

## 未做的事 / 可選後續

- 使用者尚未提供真實完整持股（含00679B/00631L/00632R以外的既有部位）
  去跑一次**真正會生效**的execution_plan——目前只在scratch算過「假設
  1.5M只算GroupA++核心5檔」的09/07試算，沒有寫回production。若使用者
  要實際下單，需要提供真實現有持股，明確要求「這次要寫回production」
  才執行。
- COVID崩盤段驗證目前只做了0%/10%/15%，12%的崩盤段數字已經算出（見上
  表），但如果之後還要往上測（例如20%），優先比照同一套COVID崩盤段
  方法論驗證，不要只看溫和窗口。
