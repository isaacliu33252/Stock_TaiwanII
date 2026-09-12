# Group A+ 2026-08-09 交接記錄：3篇論文審查 + 3個使用者自提機制的完整驗證

## 目錄

1. 背景
2. 論文審查(#1-3)
3. 使用者自提機制(#4-6)
4. 本次session的檔案異動清單
5. 對應memory索引
6. 重要教訓：production pointer事故
7. 未完成/刻意不做的事項

## 1. 背景

接續同一個長running session。前段已經完成7項punch list(見
`GROUP_A_PLUS_20260808_PAPER_AUDIT_PUNCH_LIST_RESOLUTION_HANDOFF.md`)跟
1706.10059 PVM shadow候選的完整驗證(見
`GROUP_A_PLUS_20260809_PVM_COST_SHADOW_1706_10059_VALIDATION_HANDOFF.md`)。
本文件記錄接下來的工作:3篇新論文分析、以及使用者自己提出的3個具體機制構想
(00646加入評估、TSMC濃度分歧、稀疏美台先行網路),全部經過完整驗證流程
(先查現有prior art、真實資料回測、參數敏感度掃描)。

## 2. 論文審查

### #1 2105.08664 DeepPocket(Graph Convolutional RL)

**乾淨關閉,沒寫任何程式碼。** 三個核心機制對Group A+都不適用或已測過:
- GCN相關性建模——Group A+只有4檔標的,00631L/00632R本來就是0050的機制性
  衍生品,沒有足夠獨立的相關性結構可學,判定跟已關閉的GNHAR網路波動度
  預測(20260711)同一個結論
- 直接神經網路輸出weights的RL架構——同一天稍早才完整驗證過的1706.10059
  就是同一個核心主張,不重複驗證
- RSAE特徵壓縮——解決的是Group A+根本沒有的問題(每天訓練大型神經網路的
  成本)

文件:`docs/2105_08664_DEEPPOCKET_GROUPA_PLUS_REVIEW_20260809.md`

### #2 1909.03278 Low-risk DQN Trading Agent

**乾淨關閉,沒寫任何程式碼。** 同一天第三篇「train神經網路直接輸出交易
動作」類論文,同樣的架構缺口。唯一跟前兩篇不同的技巧(溫度縮放softmax
TD target,讓訓練目標偏向風險趨避動作)本質上是在改Q-network訓練時的
label算法,沒有訓練迴圈可以掛,不足以開shadow線。

文件:`docs/1909_03278_LOW_RISK_DQN_TRADING_AGENT_GROUPA_PLUS_REVIEW_20260809.md`

### #3(補充,非論文)00646加入Group A+評估

使用者問「00646加入groupA+的評估?」——查出這個題目部分已經在2026-07-26
的「groupFull」探索中測過(8檔全持股classical optimizer,使用者最後決定
「算了,還是做groupA+」)。這次縮小範圍成使用者指定的更窄問題:**保留
Group A+現有regime table機制不動,只從0050 sleeve裡切一部分給00646
(元大S&P500,美元避險)**。

建了`scripts/evaluate/evaluate_00646_sp500_addition_shadow.py`,測5組
carve fraction(0/0.25/0.5/0.75/1.0)×7個窗口(2020-2026)。結果:
**5個窗口carve越多虧越多**(0050這幾年多半跑贏00646),**2個窗口
(2022升息熊市、2024年8月利差交易平倉崩盤)carve越多越好**——真實的
分散投資trade-off,不是雜訊,但naive固定比例設計整體是淨拖累。

無獨立handoff文件,結果記錄在對話記錄與`report/group_a_plus/latest/00646_sp500_addition_shadow.json`。

## 3. 使用者自提機制

### #4 TSMC濃度分歧(ADD_0050_INSTEAD vs ADD_00631L)

使用者提出:區分0050上漲是台積電單獨拉動還是大盤廣泛參與,只在A21.18
準備加碼00631L時介入決策。**查證後發現大半機制已經存在**於
`daily_signal.py`(`0050_ex_tsmc_proxy`、`narrow_lead`/`tsmc_led_narrow`
分類),只是純diagnostic從未接上任何真的會動weight的邏輯。

完整做了「都做」(使用者原話)兩件事:

1. **ADD_0050_INSTEAD shadow guard**——`evaluate_add_0050_instead_of_00631l_shadow.py`,
   7窗口(2020-2026)全部三項指標過關,但**6年多只觸發3次事件**,4個窗口
   零事件——證據太薄弱,誠實記錄不是有效驗證。
2. **廣度指標**——資料庫沒有0050完整50檔成分股資料,降scope成top-5大型股
   proxy(TSMC+鴻海+聯發科+台達電+廣達,約71%權重)。過程中發現這4檔
   大型股資料卡在07-15已3.5週未更新,**當場修復**(加進
   `fetch_cross_market_ohlcv.py`每日清單,回填2019年至今)。

後續(使用者說「下一步」後主動做的):把`top5_breadth_snapshot()`接進
`daily_signal.py`的`tsmc_0050_health`診斷,純附加advisory欄位。驗證過程
中發生一次意外(見第6節)。

文件:`docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md`

### #5(#4衍生,非獨立論文)refresh_cross_market_ohlcv資料修復

同上,已併入#4記錄。新增4檔ticker到每日排程,消弭一個潛在的長期靜默過期
問題(跟稍早發現的readiness review staleness是同一類bug)。

### #6 Sparse美台先行網路(Lead-Lag Graph)

使用者提出用rolling hypothesis test篩選穩定的美→台先行邊,預測兩個窄
目標(次日00631L相對0050報酬、次日台積電相對0050_ex_TSMC報酬)。**查證
後發現這條線已經在2026-07-15/16被大量測試過**
(`docs/cross_market_graph_shadow_20260715.md`,30幾份結果檔案,節點跟
方法幾乎跟這次提案一樣,現在還活著在production裡跑,advisory-only,
結論是「5日NO_ADD訊號弱但真實,REENTER不能用」)。

真正新的部分:1日horizon(不是5日)+連續回歸目標(不是二元分類)+
TSMC-vs-ex-TSMC這個全新目標。建了
`evaluate_cross_market_lead_lag_relative_return_shadow.py`,**重用既有
`select_directed_edges()`完全未修改**,只新增約150行(目標公式+回歸版
walk-forward評估器)。

**結果:乾淨空結果,而且經過兩輪加強驗證後更加確定**:
- 主結果:兩個目標R²皆為負(-0.007、-0.006),相關係數趨近0,方向準確率
  50-53%接近隨機
- 使用者問「反過來0050相對00631L?」——證明數學上sign flip對線性模型
  完全等價(R²/相關係數/方向準確率/邊選擇結果都不變),不用重跑
- 使用者要求測不對稱版本——加了條件式拆解(依實際哪邊贏分組評估),
  發現表面53%方向準確率其實是「贏家那邊84% vs 輸家那邊13%」的多頭
  偏誤假象(2019-2026台股/半導體結構性上漲),條件式R²全部嚴重負值
  (-0.86到-1.74),證實完全沒有真實預測力
- 使用者問「全測了?」——補跑9組參數敏感度掃描(edge_window×tstat_threshold),
  確認R²全部維持在-0.018到+0.002的窄帶內,方向準確率全部49-56%,結果
  穩健不是單一參數設定的巧合

**不影響既有`cross_market_graph_shadow`的5日NO_ADD訊號**,那個維持
原狀不動。

文件:`docs/CROSS_MARKET_LEAD_LAG_RELATIVE_RETURN_GROUPA_PLUS_20260809.md`

## 4. 本次session的檔案異動清單

新增程式碼:
- `scripts/evaluate/evaluate_00646_sp500_addition_shadow.py`
- `group_a_plus/integrations/tsmc_concentration_divergence.py`
- `scripts/evaluate/build_tsmc_concentration_divergence_breadth_snapshot.py`
- `scripts/evaluate/evaluate_add_0050_instead_of_00631l_shadow.py`
- `scripts/evaluate/evaluate_cross_market_lead_lag_relative_return_shadow.py`
- `tests/test_tsmc_concentration_divergence.py`(13測試)
- `tests/test_evaluate_1706_10059_pvm_cost_shadow.py`後續已含(前段work)
- `tests/test_evaluate_cross_market_lead_lag_relative_return_shadow.py`(9測試)

修改程式碼:
- `scripts/fetch/fetch_cross_market_ohlcv.py`——加2317/2454/2308/2382
- `group_a_plus/operations/daily_signal.py`——`_tsmc_0050_health_snapshot()`
  新增`top5_breadth`欄位,純附加

新增文件:
- `docs/2105_08664_DEEPPOCKET_GROUPA_PLUS_REVIEW_20260809.md`
- `docs/1909_03278_LOW_RISK_DQN_TRADING_AGENT_GROUPA_PLUS_REVIEW_20260809.md`
- `docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md`
- `docs/CROSS_MARKET_LEAD_LAG_RELATIVE_RETURN_GROUPA_PLUS_20260809.md`
- `GROUP_A_PLUS_20260809_PAPER_REVIEWS_AND_USER_PROPOSED_MECHANISMS_HANDOFF.md`(本文件)

輸出(shadow報表,零production影響,除第6節提到的意外之外):
- `report/group_a_plus/latest/00646_sp500_addition_shadow.json`
- `report/group_a_plus/latest/tsmc_concentration_divergence_breadth.json`
- `report/group_a_plus/latest/add_0050_instead_of_00631l_shadow.json`
- `results/cross_market_lead_lag_relative_return_shadow_latest.json`

## 5. 對應memory索引

- `project_1706_10059_pvm_cost_shadow_followup_20260809.md`(前段work)
- `project_tsmc_concentration_divergence_20260809.md`
- `project_cross_market_lead_lag_relative_return_20260809.md`
- `feedback_production_pointer_scripts_need_output_redirect_for_testing.md`
  (見第6節)

## 6. 重要教訓：production pointer事故

驗證TSMC濃度分歧的`daily_signal.py`接線時,跑了一次真實end-to-end測試
但沒有重導向`--output`,預設值就是production在用的
`report/group_a_plus/latest/live_signal.json`,意外把它蓋過去了。

**事後查證**:內容判斷是無害的合理刷新(regime維持golden1不變,只是把
本來就過期3天的舊快照用真實資料重新算過,外加新欄位),沒有動到
`execution_plan.json`(那個檔案的修改時間比這次操作早14小時,是別的東西
動的)。使用者知情後選擇保留刷新版本,不要求還原。

**過程中發現一個更大的背景事實**:這個repo目前有**其他並行session同時
在跑**——`git status`裡出現大量本session完全沒碰過的未追蹤檔案
(`harlf_*`、`moira_*`、`adaptive_quantile_risk_gate_*`、
`regime_weighted_tail_conformal_*`等等)。這代表`report/group_a_plus/latest/`
底下的東西隨時可能被別的session寫入,不是這個session獨佔的靜態基準。

已經把這個教訓概化寫進
`feedback_production_pointer_scripts_need_output_redirect_for_testing.md`:
之後任何要測試、預設輸出路徑是production pointer的腳本,一律先重導向到
scratchpad再跑,不管測試動機看起來多麼「唯讀」。

## 7. 未完成/刻意不做的事項

1. `00646_sp500_addition_shadow`沒有做regime-aware觸發版本(只在偵測到
   系統性風險升高時才切換,平常不切)——使用者當時沒有要求繼續往這個
   方向做。
2. TSMC濃度分歧的完整50檔成分股廣度指標(等權重vs市值權重全比較)沒有
   做——需要新的成分股清單+個股OHLCV抓取pipeline,只做了top-5大型股
   proxy。
3. TSMC濃度分歧的workbook-aware診斷還沒有機會在「真的持有00631L部位」
   的真實情境下驗證過(目前production持股剛好沒有00631L)。
4. `backfill_2024_aug_unwind`(1706.10059那條線裡,史上最尖銳的回撤
   窗口)零事件的真正原因沒有深挖到底。
5. ~~readiness review staleness(punch list第4項,牽連約10支腳本)依然
   沒修,範圍太大,值得之後單獨排時間。~~ **已修復** — 見
   `GROUP_A_PLUS_20260809_ADAPTIVE_MECHANISMS_AND_FIVE_IMPROVEMENT_DIRECTIONS_HANDOFF.md`
   第3節。這份文件的內容到此為止(#1-6);後續的#7、#8機制與五個改善
   方向都記錄在那份接續文件裡。
