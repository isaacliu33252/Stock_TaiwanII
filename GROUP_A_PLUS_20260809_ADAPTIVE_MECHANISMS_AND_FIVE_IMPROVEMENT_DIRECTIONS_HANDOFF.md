# Group A+ 2026-08-09 交接記錄(續篇):自適應機制#7-8 + 五個系統改善方向

## 目錄

1. 背景
2. 使用者自提機制(續) #7-8
3. 五個系統改善方向(Task #19-23)
4. 本次異動檔案清單
5. 對應memory索引
6. 過程中的教訓
7. 未完成/刻意不做的事項(累積)

## 1. 背景

接續`GROUP_A_PLUS_20260809_PAPER_REVIEWS_AND_USER_PROPOSED_MECHANISMS_HANDOFF.md`
(#1-6:3篇論文審查+00646評估+TSMC濃度分歧+美台先行網路)。使用者接著提出
第7、8個機制構想(Adaptive Lookback、Adaptive Review Interval),兩個都
做完驗證後,使用者要求「針對目錄內的project,提岀5個改善方向」,再指示
「一步一步做完」——本文件記錄這兩部分的完整過程。

## 2. 使用者自提機制(續)

### #7 Adaptive Lookback:讓觀察窗口隨市場結構改變

使用者提議:把A21.18固定的觀察窗口(如`risk_score_lookback_days=5`)換成
因果的自適應選窗——固定候選集`{20,40,60,120,252}`,每天挑trailing
命中率最好的那個,明確區分於本專案已關閉的「coordinate-descent找單一
固定最佳窗口」調參模式(候選集本身不變,只是每天選哪個成員會變)。

查證後發現`risk_score_lookback_days`直接影響golden1/defensive切換決策
本身(`total_risk_ok`),違反使用者「決策規則要保持固定,只變feature
window」的明確要求,改用同一天早上剛建的ADD_0050_INSTEAD guard內部的
narrow_lead trigger窗口(本身已是shadow-only/純附加,改它的內部窗口
不會碰到A21.18核心規則)。

建了`scripts/evaluate/evaluate_adaptive_lookback_narrow_lead_shadow.py`
(6測試)。**初次結果不確定**——7個窗口裡3個零事件平手、2個路徑不同但
結果相同、1個adaptive錯過fixed抓到的獲利觸發(較差)、1個adaptive避開
fixed造成的傷害觸發(較好,但靠的是不作為不是正確預測),合計兩邊
加起來只有15次觸發事件,樣本太少。

**使用者問「回測,全測了?」**,促成同一天的決定性後續驗證,建了
`scripts/evaluate/evaluate_adaptive_window_hit_rate_comparison.py`(6測試),
不受稀疏trigger限制,對全部1543個交易日直接打分:固定窗口全部顯示
「統計顯著」命中率(252日窗口56.4%,z=5.0),adaptive窗口(55.1%)反而
輸給固定最長窗口——結果跟提案期望相反。但**這個顯著性本身就是同一天
在美台先行網路那條線發現的同一種base-rate假象**:把252日窗口的預測
按「哪邊實際贏」拆解,00631L贏時88.1%命中(n=888)、0050贏時只有13.4%
命中(n=655)——因為252日濃度分歧訊號87.4%的時間都預測「00631L贏」,
只是在讀多年結構性上漲,不是真的在預測。

追加對adaptive selector自己的調參參數`eval_lookback∈{20,40,60,90,120,180}`
掃了一輪確認穩健性:`fixed_252d`在每一組設定下都是最好或並列最好的
單一固定窗口,adaptive只在6組裡贏2組,且贏幅<0.5個百分點(雜訊等級)。

**最終結論:乾淨的空結果(取代原本「證據不足」的結論)**——修正
mean-bias後,不管固定窗口還是adaptive選窗,都沒有真實的雙向次日相對
報酬預測力,跟同一天的美台先行網路結論互相印證。

文件:`docs/ADAPTIVE_LOOKBACK_NARROW_LEAD_GROUPA_PLUS_20260809.md`

### #8 Adaptive Review Interval:讓訊號重算頻率隨regime穩定度改變

使用者提出第三個獨立機制(區別於已存在的`min_hold_days`——擋住離開
regime但仍每天重算訊號,以及`staged_buys`/buy_fraction——決定多快
交易到已定target,兩者回答的都是不同問題):多久才需要重新看一次新鮮
訊號,輸出NEXT_REVIEW_1D/3D/5D,兩次review之間凍結target weights。

建了`scripts/evaluate/evaluate_adaptive_review_interval_shadow.py`
(10測試):`classify_review_interval()`是因果的單日分類器,只用當天
自己的`execution_regime`/`ma_gap`/`drawdown`/`tail_risk_score`對照
A21.18自己的switch-rule門檻(`entry_ma_gap=-0.003`、
`exit_ma_gap=0.010`、`dd_threshold=-0.11`,來自`a2111.py`的
`_build_switch_rule()`,A21.18原封不動引用)——crash/recovery→1日、
穩定golden1→3日、穩定defensive遠離re-entry門檻→5日,任何接近門檻或
未知regime→保守預設1日。`simulate_adaptive_review()`凍結review之間
的weights,golden1_0531與A21.18的決策規則完全未動。

**7個窗口(2020-2026)結果:4/7三項指標全過,總成本降低
(net_cost_pass=true,-4,044總成本,-1.67M總turnover),但3/7窗口不過**
→`research_only_not_promoted`。分類器本身驗證正常運作(真實1d/3d/5d
分佈多樣,review次數隨波動度合理縮放)。

**逐窗口解讀**:3個窗口(`stress_2026`/`backfill_2022_rate_hike`/
`backfill_2024_aug_unwind`)兩次review之間regime根本沒變,兩個arm
trivially相同,沒有資訊量。`backfill_2020_covid`是唯一乾淨的正面
結果(+485)。`live_2024_2026`/`active_2025_2026`成本/turnover確實下降
但績效也下降,且只有1個suppressed day就造成不成比例的最終值影響
(-15,343在約$100萬本金上)——凍結的weight會持續影響到下次review為止,
不是單日成本。**`backfill_2021_may_correction`是最有資訊量的輸家**:
這個窗口regime flip次數最多(14次,其他窗口0-6次),4個suppressed day,
但淨效果是真實虧損(-2,656最終值,-0.045 Sharpe),即使成本/turnover
確實比較低——代表crash偵測門檻沒能在這段真正的高頻切換期間辨識出
足夠「像crash」需要天天review的狀態。

**刻意沒有為了修2021窗口的結果重調`crash_dd_buffer`/
`crash_tail_risk_score_min`等門檻**——使用者自己的提案文字就明確表示
不想重蹈本專案已關閉的coordinate-descent-over-a-few-windows
overfitting覆轍([[feedback_overfitting_fixed_window_tuning]])。照實
回報結果,不手調數字讓它看起來更好。

**判定:不promote,真實理解的trade-off**(不是乾淨過關、不是乾淨否決、
也不是「證據不足」——是真實、樣本充足的混合結果)。若之後重啟:要嘛把
crash偵測條件本身改成對regime波動度敏感(例如用近期flip頻率而非單純
drawdown/tail-risk水準)並在更大範圍窗口上測試,要嘛乾脆結構性地把
review interval上限訂得比5日更低,而不是試圖調參調掉2021這個失敗模式。

文件:`docs/ADAPTIVE_REVIEW_INTERVAL_GROUPA_PLUS_20260809.md`

## 3. 五個系統改善方向(Task #19-23)

兩個機制驗證完後,使用者要求「針對目錄內的project,提岀5個改善方向」,
然後「一步一步做完」——以下依序完成,每項都有獨立文件與memory記錄。

### Task #19:readiness review staleness系統性根因修復

**根因比原本(2026-08-08稽核)以為的更深,分3層,都是同一種
「寫死日期檔名冒充latest pointer」反模式**:

1. Producer(`scripts/evaluate/build_group_a_plus_rebalance_review.py`):
   `DEFAULT_LIVE_SIGNAL`(輸入)跟`DEFAULT_OUTPUT`(輸出)都寫死
   `*_20260720*`檔名,且這支腳本本身從未接進`run_ncf_daily_pipeline.py`
   (上次手動跑是2026-07-17)。另外還有2處藏在`build_review()`的payload
   裡的硬編碼日期字串(`current_weights_reliable_for_20260720`這個
   key名稱本身就帶日期、`decision.summary`裡寫死「2026-07-20」),這種
   不會出現在路徑grep裡,只能靠讀函式本體才找得到。
2. **9支consumer**各自的`DEFAULT_REBALANCE`都指向producer的舊檔名。
3. **9支consumer裡有6支還各自獨立寫死了自己的`DEFAULT_LIVE_SIGNAL`**,
   指向另一份`live_signal_20260720_estimate.json`——這是驗證過程
   重跑其中一支consumer後,發現`as_of`還是卡在07-20才發現的第三層。

**修復**:12個檔案全部把寫死日期路徑改成undated latest pointer;
producer的兩個硬編碼字串改成用`actual_date`/`execution_plan_stale`
動態算;`rebalance_review`步驟接進`run_ncf_daily_pipeline.py`,緊接在
`daily_signal`後面(靠dict insertion order = 執行順序)。

**驗證**:producer直接跑,`requested_as_of_date`/`actual_data_date`
回到真實今天日期(不再是07-20);重跑2支consumer確認`as_of`回到
2026-08-09;有專屬測試的4支consumer全過;無專屬測試的2支smoke test過。
全套1909測試跑完,3個失敗全部診斷完畢——2個是新增
`rebalance_review`步驟的預期連帶效應(pipeline測試斷言精確步驟順序
清單,已修測試),1個是無關的flaky測試(獨立重跑就過)。

文件:`docs/READINESS_REVIEW_AS_OF_STALENESS_AUDIT_20260808.md`(更新)

### Task #20:資料新鮮度看門狗

**動機**:Task #19修的bug之所以能存活3週,是因為既有的freshness
基礎建設(`ops_health.py`的好幾個`*_freshness` helper、
`alert_state.py`、`check_ohlcv_freshness.py`)全部只比對**mtime**
(檔案A vs 檔案B,或檔案 vs 現在時間),沒有一個會去看JSON payload
本身回報的`as_of`欄位——這正是這個bug隱形3週的原因:`generated_at`
每天都新,但payload裡的`as_of`凍結。

**建成**:`ops_health.py`新增`collect_readiness_review_freshness()`——
掃`report/group_a_plus/latest/*.json`,用多重key路徑(`as_of`、
`dates.requested_as_of_date`、`dates.actual_data_date`等)抓每個檔案
自己回報的as_of,跟`run_ncf_daily_pipeline.py`原始碼比對(regex掃
原始碼文字,不import/執行整個pipeline,保持這個檢查便宜且唯讀)哪些
檔案有真的被排程寫入。兩種失效模式:`stale_despite_wiring`(error——
有排程但as_of凍結,就是剛修的bug類型)、`orphaned_stale`(warning——
從沒排程,除非在新建的`KNOWN_FROZEN_LATEST_ARTIFACTS`已知清單裡則是
`frozen_expected`不算警告)。接進`build_ops_health()`的section
彙整,也接進`alert_state.py`新增`ops_health_readiness_review_stale`
alert(medium等級)。

**首次真實資料驗證(255檔全掃)就抓到2個全新案例**,查完根因都不是新
bug:
- `synthetic_augmentation_validation_readiness_review.json`——是
  `dynamic_cvar_tail_cost_readiness_review.json`(Task #19已修的
  rebalance_review家族成員)的cascade,兩檔`as_of`一樣卡在07-20、
  `generated_at`幾乎同一秒,等真實pipeline重跑會自動一起變新。
- `broker_holdings_reconciliation_review.json`——真的不是code bug,
  老實反映手動維護的broker交易匯出檔`isaac_tra_20260718.xlsx`裡最後
  一筆交易日期,查過整個repo確認沒有更新版匯出檔存在。跟
  `execution_plan.json`手動workbook同一類已知模式。**順便發現並修正
  watchdog自己的誤判**——原本把這種「有排程但內容天生受限於手動資料」
  的案例跟真正的code bug同等級當成error,新增
  `MANUALLY_SOURCED_LATEST_ARTIFACTS`分類降級成warning
  (`manually_sourced_stale`)。

7個測試(含1個修正分類的追加測試),63個測試全過。

文件:`docs/READINESS_REVIEW_FRESHNESS_WATCHDOG_20260809.md`

### Task #21:shadow診斷接純logging進daily pipeline

**動機**:機制#4(ADD_0050_INSTEAD guard)跟#8(Adaptive Review
Interval)都是「真實但backtest證據太薄」的結論——前者6年多只觸發3次
事件,後者7窗口裡3個零suppressed day。與其等更多可能根本不存在的
歷史回填資料,照本專案已有的先例
(`recovery_boost_spillover_gate_shadow_log.py`、
`trough_override_eligibility_shadow_log.py`,2026-07-16 Fable稽核
建立的模式)在正式pipeline裡純logging累積真實觀察。

**建成**:
- `group_a_plus/integrations/add_0050_instead_shadow_log.py` +
  `scripts/run/build_group_a_plus_add_0050_instead_shadow_log.py`——
  重用`_targets_from_report()`/`_load_narrow_lead_series()`(原評估
  腳本函式,未修改),每天記錄narrow_lead狀態+00631L target weight
  升降+guard是否會觸發。
- `group_a_plus/integrations/adaptive_review_interval_shadow_log.py` +
  `scripts/run/build_group_a_plus_adaptive_review_interval_shadow_log.py`——
  重用`classify_review_interval()`(未修改),每天記錄regime/ma_gap/
  drawdown/tail_risk_score+分類出的review interval。分類器import
  刻意放在`scripts/run/`的runner而不是`group_a_plus/integrations/`
  模組裡,對齊既有兄弟模組(`recovery_boost_spillover_gate_shadow.py`)
  只吃已算好的plain data、不import `scripts/`層的慣例。
- **TSMC breadth不用做任何新工作**——Task #4驗證中已經把
  `top5_breadth_snapshot()`接進`daily_signal.py`的健康快照,而
  `daily_signal.py`輸出本身就是每天存檔(date-stamped,不覆蓋),已經
  在累積,查過確認沒有缺口。

兩個新腳本都加進`run_ncf_daily_pipeline.py`的`BEST_EFFORT_STEP_NAMES`
(失敗不擋任何下游),17個新測試全過,真實資料端到端跑過並人工核對
分類邏輯正確(例:`ma_gap=0.079`但`drawdown=-0.0747`不滿足golden1
stable的drawdown buffer要求,正確分類成`golden1_near_threshold`/1日),
pipeline測試(21個,含2個新增的`--panel`/`BEST_EFFORT_STEP_NAMES`
斷言)全過。

文件:`docs/SHADOW_DIAGNOSTICS_DAILY_LOGGING_20260809.md`

### Task #22:production pointer寫入保護機制

**動機**:同一天稍早驗證TSMC濃度分歧時,`daily_signal.py`沒重導向
`--output`意外覆蓋了production的`live_signal.json`
([[feedback_production_pointer_scripts_need_output_redirect_for_testing]])。
既有修法純程序性(記得測試前重導向),這次加一個真正的機制:一步式
undo路徑。

**建成**:`tw_output_standard.py`新增公開函式
`backup_latest_pointer_before_overwrite(target)`——覆蓋
`report/group_a_plus/latest/*`底下的檔案前,先把舊內容存一份
`<name>.json.bak`(rolling單代,不是累積歷史,刻意控制磁碟成本——見
[[feedback_no_disk_warning_topic]])。自動接進`write_standard_output()`
(本專案絕大多數腳本共用的JSON輸出helper),等於零額外程式碼就涵蓋了
`live_signal.json`(原始事故的檔案)、`execution_plan.json`、
`alert_state.json`、`rebalance_review.json`等大部分production pointer。

**中途發現不少腳本繞過`write_standard_output`自己直接`.write_text()`**
——補上發現的高價值治理artifact:`watchlist_news.py`的寫入函式,以及
`run_ncf_daily_pipeline.py`本身內嵌的5處直寫(`strategy_env_health.json`、
`ops_health.json`、`risk_mechanism.json`、`strategy_trust.json`、
watchlist_news的FinMind fallback分支)。**刻意沒有做全repo徹底
掃描/修補每一處直寫**——明確記錄未覆蓋範圍(4支本次新建的shadow-log
「latest」輸出、`relative_reentry_opportunity`/
`cvar_tail_risk_diagnostic`的latest_output、`rebalance_audit.py`的
`rebalance_plan.json`未逐一審查),不假裝全覆蓋,對齊本次session一貫
的誠實記錄scope邊界作法。

`.gitignore`加`*.bak`(這個repo的`report/group_a_plus/latest/*`是
git-tracked的,不排除的話`.bak`會變成每次`git status`都看得到的
untracked檔案)。

6個新測試,加上既有pipeline(21)+watchlist_news(5)測試全過確認backup
side-effect不改變任何既有寫入的實際內容。全套1938測試最終跑完
(1937過、9 skip、1個flaky——跟本次改動無關,獨立重跑就過)。

文件:`docs/PRODUCTION_POINTER_BACKUP_PROTECTION_20260809.md`

### Task #23:多頭偏誤檢測列進訊號驗證檢查清單

**動機**:同一種base-rate/mean-bias假象(表面統計顯著的方向準確率/
命中率,拆解後發現是讀多頭趨勢的多數類別而非真預測)在同一天被獨立
撞見**兩次**——一次在美台先行網路(#6),一次在Adaptive Lookback
Window(#7)。獨立撞見兩次代表這是值得正式寫進流程紀律的檢查項目,
不是單一線的巧合。

**做法**:在既有活文件`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`
(原本4項,7/24~7/26陸續擴充到7項)新增**第8項**:任何候選人回報
directional-accuracy/hit-rate類指標時,必須額外按「當天實際哪邊贏」
拆解成兩半分別回報,並附上這次兩個真實案例作為具體例子。同步更新
「How to apply going forward」段落說明第8項適用條件(只在候選人有回報
hit-rate類指標時適用,不是每個候選人都要跑)。

沒有寫新程式碼——這是流程文件更新,不是策略邏輯或程式碼異動。

## 4. 本次異動檔案清單

**新增程式碼**:
- `scripts/evaluate/evaluate_adaptive_lookback_narrow_lead_shadow.py`(6測試)
- `scripts/evaluate/evaluate_adaptive_window_hit_rate_comparison.py`(6測試)
- `scripts/evaluate/evaluate_adaptive_review_interval_shadow.py`(10測試)
- `group_a_plus/integrations/add_0050_instead_shadow_log.py`
- `scripts/run/build_group_a_plus_add_0050_instead_shadow_log.py`
- `group_a_plus/integrations/adaptive_review_interval_shadow_log.py`
- `scripts/run/build_group_a_plus_adaptive_review_interval_shadow_log.py`
- `tests/test_group_a_plus_add_0050_instead_shadow_log.py`(8測試)
- `tests/test_group_a_plus_adaptive_review_interval_shadow_log.py`(6測試)
- `tests/test_tw_output_standard.py`(6測試)

**修改程式碼**:
- `scripts/evaluate/build_group_a_plus_rebalance_review.py`——undated
  路徑+移除2處硬編碼日期字串
- 9支consumer腳本的`DEFAULT_REBALANCE`/`DEFAULT_REBALANCE_REVIEW`
- 其中6支consumer的`DEFAULT_LIVE_SIGNAL`
- `group_a_plus/operations/ops_health.py`——新增
  `collect_readiness_review_freshness()`+
  `KNOWN_FROZEN_LATEST_ARTIFACTS`+`MANUALLY_SOURCED_LATEST_ARTIFACTS`
- `group_a_plus/operations/alert_state.py`——新增
  `ops_health_readiness_review_stale` alert
- `tw_output_standard.py`——新增`backup_latest_pointer_before_overwrite()`
- `group_a_plus/integrations/watchlist_news.py`——接上backup呼叫
- `scripts/run/run_ncf_daily_pipeline.py`——新增`rebalance_review`/
  `add_0050_instead_shadow_log`/`adaptive_review_interval_shadow_log`
  三個步驟+5處直寫接上backup呼叫
- `.gitignore`——加`*.bak`
- `tests/test_group_a_plus_ops_health.py`(+7測試)、
  `tests/test_group_a_plus_alert_state.py`(+2測試)、
  `tests/test_run_ncf_daily_pipeline.py`(斷言更新)

**新增文件**:
- `docs/ADAPTIVE_LOOKBACK_NARROW_LEAD_GROUPA_PLUS_20260809.md`
- `docs/ADAPTIVE_REVIEW_INTERVAL_GROUPA_PLUS_20260809.md`
- `docs/READINESS_REVIEW_FRESHNESS_WATCHDOG_20260809.md`
- `docs/SHADOW_DIAGNOSTICS_DAILY_LOGGING_20260809.md`
- `docs/PRODUCTION_POINTER_BACKUP_PROTECTION_20260809.md`
- 本文件

**更新既有文件**:
- `docs/READINESS_REVIEW_AS_OF_STALENESS_AUDIT_20260808.md`——加上
  「Fixed 2026-08-09」段落
- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`——新增第8項
- `GROUP_A_PLUS_20260809_PAPER_REVIEWS_AND_USER_PROPOSED_MECHANISMS_HANDOFF.md`
  ——第7節item 5標記已修復,指向本文件

## 5. 對應memory索引

- `project_adaptive_lookback_window_20260809.md`
- `project_adaptive_review_interval_20260809.md`
- `project_readiness_review_as_of_staleness_fixed_20260809.md`
- `project_readiness_review_freshness_watchdog_20260809.md`
- `project_shadow_diagnostics_daily_logging_20260809.md`
- `project_production_pointer_backup_protection_20260809.md`
- `project_signal_validation_checklist_adopted_20260723.md`(更新)
- `project_readiness_review_as_of_staleness_20260808.md`(更新,指向fix)
- `feedback_production_pointer_scripts_need_output_redirect_for_testing.md`
  (更新,指向backup mitigation)
- `feedback_long_running_command_progress.md`(更新,見第6節)

## 6. 過程中的教訓

**重複違反已記錄的規則:背景長指令要能看進度**。這個session兩次用
`pytest -q | tail -30`背景執行全套測試,而這個確切的反模式早在
2026-07-07就已經寫進`feedback_long_running_command_progress.md`
(`tail`會buffer,upstream沒結束前capture到的檔案是空的)。使用者問
「跑多少了」時完全答不出來,後來甚至因為要kill掉其中一次背景執行,
結果`tail`的buffering讓那次執行連最終結果都沒留下(0 bytes,不是
「沒進度」而是「完全沒有任何輸出」,比原始2026-07-07事故更嚴重的
示範)。修法:拿掉`| tail -30`、改用`python3 -u`強制不緩衝——之後
確認生效(pytest的dot progress確實開始即時寫入),但也發現了一個新
的混淆點:pytest對1900+測試的collection階段本身要1-2分鐘,這段時間
輸出檔案本來就是空的,不代表機制沒生效,已經寫進memory區分清楚。

**Watchdog抓到自己的分類錯誤**(Task #20正文已述)——建好後首次真實
資料驗證,不只抓到2個新的staleness案例,還讓自己發現一個誤判
(`broker_holdings_reconciliation_review.json`被錯誤歸類成跟code bug
同等級的error),當場修正分類邏輯,而不是先報告有問題再事後補。

**Scope邊界要明說,不要暗示全覆蓋**——Task #22(production pointer
保護)發現繞過共用helper的直寫腳本比預期多很多,做了取捨:只補高
價值的治理artifact,明確在文件+memory裡列出哪些故意沒碰,而不是
悄悄擴大範圍去追每一個,也不假裝「已完成」代表「全部涵蓋」。

## 7. 未完成/刻意不做的事項(累積)

延續前一篇文件第7節未解決的項目,加上本次新發現/刻意擱置的:

1. `heterogeneous_vol_regime_advisory.json`——22天沒更新(卡在07-17),
   從未接進daily pipeline,跟readiness review staleness同一種
   「從沒排程」模式但刻意排除在Task #19修復範圍外,避免scope
   creep,已加進Task #20 watchdog的`KNOWN_FROZEN_LATEST_ARTIFACTS`
   讓它不再產生誤導性錯誤,但根本沒被自動刷新的問題本身沒解決。
2. `broker_holdings_reconciliation_review.json`需要使用者提供新的
   broker交易匯出檔(`isaac_tra_*.xlsx`)才能真正變新——這不是code能
   解決的,需要使用者動作。
3. Production pointer寫入保護明確沒覆蓋的檔案(見Task #22正文):4支
   shadow-log latest輸出(recovery_boost/trough_override/
   add_0050_instead/adaptive_review_interval)、
   `relative_reentry_opportunity`與`cvar_tail_risk_diagnostic`的
   latest_output、`rebalance_audit.py`的`rebalance_plan.json`
   (未審查是否有下游把它當權威來源)。若想要徹底覆蓋,下一步是系統性
   grep全repo每一處`Path.write_text()`寫進`report/group_a_plus/latest/`
   的呼叫點。
4. ADD_0050_INSTEAD guard與Adaptive Review Interval的shadow log才剛
   接上,目前累積的真實觀察筆數還是0——這兩條線要等累積數週/數月的
   真實資料後才有辦法重新評估。
5. `evaluate_adaptive_lookback_narrow_lead_shadow.py`跟
   `evaluate_add_0050_instead_of_00631l_shadow.py`共用的narrow_lead
   trigger本身樣本量從頭到尾都稀薄(3-15次事件),這個限制沒有解決,
   只是換了個方式(daily logging累積)去處理。
6. Task #20的freshness watchdog沒有獨立排程步驟,只接進
   `build_ops_health()`。`run_ncf_daily_pipeline.py`裡確認有
   `build_ops_health()`的inline呼叫(`print("\n[ops-health]")`那段),
   但沒有進一步確認這段是否在每一種pipeline呼叫模式(例如
   `--only-refresh`)下都會執行到——沒有做這個層級的驗證。
