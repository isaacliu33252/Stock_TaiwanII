# Group A+ 2026-08-09 交接記錄：1706.10059 PVM/cost-recovery shadow候選完整驗證

## 目錄

1. 背景
2. 起點狀態(另一session留下的初版)
3. 逐輪驗證記錄(#1-#9)
4. 最終結論
5. 本次session的檔案異動清單
6. 對應memory索引
7. 未完成/刻意不做的事項
8. 如果之後要重啟這條線,下一步建議

## 1. 背景

使用者要求分析`C:\Users\isaac\Downloads\1706.10059.pdf`(Jiang, Xu, Liang,
"Deep Portfolio Management: A Deep Reinforcement Learning Framework for the
Financial Portfolio Management Problem")是否有優點可導入Group A+最新策略。
查repo後發現這篇論文**已經被另一個並行session在幾分鐘前分析並做了初版
shadow實作**(時間戳2026-08-08 23:48~2026-08-09 00:00),本session沒有重
做分析,而是完整讀取現有結果並回報,接著在使用者連續多次「繼續」指示下,
把該review文件自己列出的「下一步驗證」清單逐項做完。

主文件:`docs/1706_10059_DEEP_PORTFOLIO_MANAGEMENT_GROUPA_PLUS_REVIEW_20260808.md`
(本次session在原文後面附加了9段「2026-08-09 Follow-Up」,並在文件最上方
加了狀態banner指向最新結論)。

## 2. 起點狀態(另一session留下的初版)

論文核心：model-free RL直接輸出weights、PVM(前期weights回饋進state)、
EIIE(共享網路評估器)、OSBL(線上批次學習),reward是扣成本後的log報酬。
實驗用加密貨幣日內資料,報酬數字不可直接套用。

判定：架構紀律有用,不建議照搬RL allocator。5個候選匯入項目裡,已用初版
shadow腳本`scripts/evaluate/evaluate_1706_10059_pvm_cost_shadow.py`測試了
一個「cost_recovery」gate——擋掉00631L/00632R大幅翻倉,除非該翻倉近5日的
trailing優勢≥3倍估計交易成本。初版在3個live/近期窗口(2024-2026)下
3/3通過,`decision: candidate_for_latest_strategy_shadow_queue`。

該文件自己列出4項「下一步驗證」：
1. 加更多OOS窗口,含2017-2019(若有對應NCF資料)
2. 測參數敏感度(lookback 3/5/10、cost multiplier 2/3/5)
3. 加workbook-aware真實持股狀態
4. 確認不影響latest 8/10 execution-plan流程

本session把這4項全部做完,過程中又衍生出5個子發現。以下逐一記錄。

## 3. 逐輪驗證記錄

### #1 補測試

初版腳本完全沒有對應的`tests/`檔案。新增
`tests/test_evaluate_1706_10059_pvm_cost_shadow.py`,涵蓋純邏輯函式
`_weight_turnover`、`_pvm_delay_targets`、`_pvm_cost_recovery_targets`
(含block/allow/max-block-days強制放行等邊界情況)、`_summarize`的4種
decision分支。跑的過程中抓到自己寫的測試斷言時機錯(對delay/block的
loop逐日語意理解有誤),修正後全過。

### #2 加2017-2019真OOS窗口(對應驗證清單第1項)

擴充`evaluate_window()`支援傳入`ncf_panel_631l_path`(CLI `--window`格式
擴充為`label:start:end[:bucket[:ncf_panel_631l_path]]`),用既有的
`results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`加一個
`backfill_2017_2019`窗口。若不傳panel路徑,`run_a2118()`對任意日期範圍都
會退回到最新的live NCF快照,等於這個窗口完全沒有NCF驅動的避險regime可
測——這是實作這一步時發現的真實陷阱,不是理論假設。

單獨測這個窗口：metrics全過但成本反而略增(+14.79元、換手+5590),
`net_cost_pass=false`。併入原本3窗口後,整體結果沒有被推翻(`net_cost_pass`
依然true)。

### #3 參數敏感度掃描(對應驗證清單第2項)

lookback∈{3,5,10} × cost_multiplier∈{2,3,5}共9組,跑過4個窗口(含新加的
2017-2019)。**這是第一個關鍵發現**:只有4/9組合(44%)真的通過
`candidate_for_latest_strategy_shadow_queue`。`cost_multiplier=5.0`在任何
lookback下全部失敗;`lookback=10`在任何cost_multiplier下也全部失敗,而且
是連final value/Sharpe/drawdown本身都變差,不只是成本問題。當時的
production預設值(lookback=5, mult=3.0)剛好落在能過關的邊緣。

### #4 確認不影響8/10 execution-plan流程(對應驗證清單第4項)

全repo grep確認`evaluate_1706_10059_pvm_cost_shadow.py`沒有被
`run_ncf_daily_pipeline.py`或`execution_plan.py`引用;也檢查了兩者的glob
掃描邏輯(只掃`results/00631l_leveraged_compounding_regime_*.json`和
`results/group_a_plus_promotion_gate_*.json`),跟這支shadow腳本的輸出路徑
(`report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`)完全不重疊。
確認無論如何都不會被production流程意外撿到。

### #5 診斷lookback=10失效的機制

前一步只知道lookback=10「不過」,沒解釋為什麼。逐窗口拆解lookback=10、
cost_multiplier=3.0的結果:平穩趨勢窗口(live_2024_2026、
active_2025_2026)metrics其實還變好、只是成本變高;但含真正regime轉折點的
窗口(stress_2026、backfill_2017_2019)final value、Sharpe、drawdown**全部**
變差。

根因：gate用來判斷「這次翻倉有沒有被證明值得」的`prior_advantage`是
trailing N日報酬估計,N越大這個估計越舊。平穩趨勢窗口裡舊一點沒差,但在
真正轉折點,10天的trailing window量到的是**上一個regime快結束時**的行為,
判斷最容易在最關鍵時刻出錯。這是trailing-return proxy這類設計天生的
lookback/staleness trade-off,不是bug——但也代表當時能過關的{lookback=3,5}
區間不能假設對其他轉折點更多的窗口組合也安全。

### #6 擴大OOS到含2020 COVID崩盤+2022升息熊市(對應驗證清單第1項的深化)

直接測上一步的推論：加入`backfill_2020_covid`(2020整年COVID崩盤)和
`backfill_2022_rate_hike`(2022年升息熊市)兩個真正尖銳的regime轉折窗口,
重跑先前通過的{lookback=3,5}×{mult=2,3}象限。

**結果印證了機制診斷**：**production預設值(lookback=5, cost_multiplier=3.0)
在加入2020 COVID窗口後直接不過關**——`backfill_2020_covid`的final_value_delta
=-6,335.5、sharpe_delta=-0.0947,真實regress不是成本artifact。只有
lookback=3撐過(6/6)。2022升息窗口在每個cell都是零事件零delta——後來
第9步查出原因。

當場把腳本的`--lookback-days`CLI預設值從5改成3、`DEFAULT_WINDOWS`永久加入
這兩個窗口,並重新產生`report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`
(純shadow腳本,零production影響,只是讓「latest」快照跟新預設值一致)。

### #7 查證2022升息窗口零事件的原因

直接呼叫`run_a2118()`檢查2022-01-03~2022-10-31:`execution_regime`只出現
`golden1`(31天)跟`group_a_plus_defensive`(171天),`ncf_late_bull_hedge`
regime出現0次;`ma_gap`整段期間平均-5.8%、最高只到+8.3%,從沒碰到觸發
late-bull避險所需的10%門檻。

結論：a2118的NCF late-bull避險機制(以及這個PVM gate要管的00631L↔00632R
翻倉)本質上是「深度末端多頭市場」專屬機制,持續下跌的熊市年份結構上就不會
觸發它。不是bug,是釐清了這個gate的測試範圍——之後要壓力測試這個gate,
要找「末端多頭噴出後反轉」的窗口,不是熊市窗口。

### #8 再加2021年5月修正+2024年8月急殺兩個「末端多頭反轉」窗口

依上一步的釐清,用0050.TW逐年最大回撤篩選：2021年(+17.0%全年報酬,
2021-05-17附近-11.5%回撤,台灣本土疫情首度爆發)、2024年(+45.1%全年報酬,
2024-08-05附近-21.7%回撤,即現實中2024年8月全球利差交易平倉崩盤,是目前
測過最尖銳的回撤)。

`backfill_2021_may_correction`確實有訊號(29-33個事件),而且**這是第二個
獨立窗口顯示lookback=5會regress**(sharpe_delta=-0.0704),同一窗口在
lookback=3下卻是全套裡表現最強的(final_value+18,283.8、sharpe+0.1587)。
`backfill_2024_aug_unwind`又是零事件——但這次原因跟2022不同:regime整年
100% golden1、ma_gap也真的衝過門檻(最高23.7%),但NCF訊號自己的h20機率/
信心度條件從沒跟高ma_gap的日子對上,沒有進一步深究。

完整8窗口下：`lookback=3`兩個cost_multiplier都8/8全過;`lookback=5`
(舊預設)只剩6-7/8。`DEFAULT_WINDOWS`永久加入這兩個窗口(現在共8個,
跨2017-2026),重新產生`latest`快照(8/8通過)。

### #9 實作workbook-aware真實持股狀態(對應驗證清單第3項)

原始review文件的「候選匯入項目#1」從沒真的實作過——之前的backtest只用
`run_a2118()`模擬出的target weights序列,從沒碰過真實持股。新增
`build_workbook_aware_snapshot()`函式+`--workbook-snapshot
<execution_plan.json>`CLI參數:讀執行計畫payload裡的
`current_holdings`/`current_prices`/`current_total_assets`/`target_weights`/
`staged_target_shares_before_guards`跟真實歷史收盤價,純診斷回報「今天
真實持股轉去target會不會觸發cost-recovery gate」,絕不寫回execution_plan.json
或改任何live weight。

用真實production的`execution_plan.json`(2026-08-07資料)測試：目前實際
持股0050=41.1%/00632R=2.1%/00679B=7.9%/cash=48.9%,完全沒有00631L部位;
target要0050=30%/00632R=27.1%/cash=42.9%。雖然換手率高達50%,但
`large_flip_detected: false`——這是**正確**判斷不是漏偵測,因為這個gate
專門盯00631L↔00632R翻倉,現在根本沒有00631L部位可以翻,目前的00632R
加碼是從cash新進場,不是這個gate要管的模式。

新增3個測試(缺欄位早退路徑、合成「無631L高換手」情境確認不誤觸發、合成
「真實631L→632R翻倉」情境確認gate真的會介入且必定resolve成block或
allow二選一,不會靜默不作為)。測試檔總數來到18個測試(含前面的15個)。

**至此,原始review文件列的4項「下一步驗證」全部做完。**

## 4. 最終結論

**維持shadow-only,不promote**。這是這個專案的既有紀律
(見memory `feedback_overfitting_fixed_window_tuning`:超過2-3輪同組窗口
調參後必須OOS驗證才能宣稱進步)——即使證據隨著驗證逐步變強,也不代表可以
直接接進latest strategy。

如果之後要重新考慮這條線：
- 起點應該用`lookback_days=3`,不是舊的`5`——這已經有紮實證據支持
  (撐過3個獨立、橫跨2020-2026的真實尖銳反轉事件:COVID 2020、2021年5月
  修正、2026壓力窗口),而`lookback=5`在其中2個都regress。
- `backfill_2024_aug_unwind`(目前測過最尖銳的回撤)還沒有真正測到這個
  gate,原因是NCF訊號自己的觸發條件沒對上——值得之後深究,可能發現這個
  gate在史上最極端的環境下究竟表現如何。
- workbook-aware診斷已經證實在真實現況下(無00631L部位)這個gate不會
  誤觸發,但還沒有機會在「真的持有00631L部位時」用真實(非合成)資料
  驗證過,等未來某天production真的持有00631L時可以重跑
  `--workbook-snapshot`看真實結果。

## 5. 本次session的檔案異動清單

程式碼:
- `scripts/evaluate/evaluate_1706_10059_pvm_cost_shadow.py`——加
  `ncf_panel_631l_path`per-window支援、`--lookback-days`預設值5→3、
  `DEFAULT_WINDOWS`從3個擴到8個、新增`build_workbook_aware_snapshot()`+
  `--workbook-snapshot`參數
- `tests/test_evaluate_1706_10059_pvm_cost_shadow.py`(新增)——18個測試

文件:
- `docs/1706_10059_DEEP_PORTFOLIO_MANAGEMENT_GROUPA_PLUS_REVIEW_20260808.md`
  ——附加9段「2026-08-09 Follow-Up」+文件最上方狀態banner
- `GROUP_A_PLUS_20260809_PVM_COST_SHADOW_1706_10059_VALIDATION_HANDOFF.md`
  (本文件)

輸出(regenerated,純shadow報表,零production影響):
- `report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`——現在反映
  lookback=3、8窗口、含workbook_aware_snapshot欄位

## 6. 對應memory索引

`project_1706_10059_pvm_cost_shadow_followup_20260809.md`——完整記錄這9個
子步驟,已連結進`MEMORY.md`索引第一條。

## 7. 未完成/刻意不做的事項

1. `backfill_2024_aug_unwind`的零事件原因(NCF訊號h20/信心度條件沒跟高
   ma_gap的日子對上)沒有深挖到底——只確認了「不是2022那種ma_gap不夠高」
   的原因,沒有再往下查NCF訊號本身在2024年的行為。
2. `backfill_2023_...`面板存在但沒有加入測試(2023年0050.TW最大回撤只
   -8.4%,判斷訊號強度可能跟已經覆蓋的平穩趨勢窗口類似,優先度較低,
   沒有做)。
3. workbook-aware診斷還沒有機會在「真的持有00631L部位」的真實情境下
   驗證過(目前production持股剛好沒有00631L)。

## 8. 如果之後要重啟這條線,下一步建議

依優先順序:
1. 深挖`backfill_2024_aug_unwind`零事件的真正原因——史上最尖銳的回撤
   窗口卻沒測到這個gate,值得搞清楚NCF訊號在那段期間到底在做什麼。
2. 若之後production真的建立00631L部位,重跑一次`--workbook-snapshot`
   看真實(非合成)資料下的結果。
3. 若要正式考慮promotion,需要比目前更長的觀察期,且要先確認這個決定
   符合[[project_signal_validation_checklist_adopted_20260723]]的四項
   紀律(walk-forward、crisis獨立性、成本敏感度、後續OOS驗證)。
