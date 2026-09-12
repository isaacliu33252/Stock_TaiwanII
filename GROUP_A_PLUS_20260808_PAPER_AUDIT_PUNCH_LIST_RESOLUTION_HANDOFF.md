# Group A+ 2026-08-08/09 交接記錄：Fable論文稽核7項action items逐一解決

## 目錄

1. 背景與來源
2. 逐項解決記錄(#1-#7)
3. 本次session的檔案異動清單
4. 驗證紀錄
5. 對應memory索引
6. 未完成/刻意不做的事項
7. 下一步建議

## 1. 背景與來源

這份記錄接續一個更早的大型工作:在同一個長running session中,使用者要求「使用fable 針對目前目錄的project,groupA+的最新策略分析,對比下載的文件(C:\Users\isaac\Downloads),確認優點是否都已經導入」。該次稽核涵蓋42+篇論文,分Part A(已知已導入的優點是否真的接上)與Part B(是否有論文被完全遺漏)兩部分,由一個Fable背景agent執行,期間有兩次真的方法論落差被抓到並修正(Part A搜尋範圍漏掉`environments/*.py`與根目錄`*.py`;Part B的gap-list原始grep漏查`docs/`底下既有記錄)。

該次稽核最終產出一份7項的action items清單。使用者接著明確指示「一項一項解決」,本記錄就是這7項的逐一處理過程與結果。第7項(a2118.py架構缺口)本身在任務描述中就註明「這項要最後做,而且要在動手前跟使用者確認修復方向」,故最後才處理且先詢問了使用者。

**注意**:這份稽核產生的原始「7項清單」本身只存在於對話與TaskCreate/TaskUpdate的任務狀態中,沒有留下獨立檔案。若之後需要回溯原始稽核的完整42+篇論文逐篇結論,目前唯一可信來源是這次session的完整transcript,不在任何repo檔案裡——這是本記錄要補上的第一個缺口,詳見第6節。

## 2. 逐項解決記錄

### #1 execution_plan.py guard預設值不一致(2606.18199 paper-audit cross-check)

**發現**:`group_a_plus/operations/execution_plan.py::build_execution_plan()`函式層級的`enforce_advisory_pre_trade_guards`預設值是`True`,但CLI argparse的預設值是`False`(`action="store_true", default=False`——也就是實際production執行的預設行為)。`scripts/evaluate/build_group_a_plus_manual_holdings_execution_sensitivity.py`呼叫`build_execution_plan()`時沒有明確傳這個參數,會靜默撿到函式層級的`True`,跟production實際行為(`False`)不一致。

**修復**:在該呼叫點明確加上`enforce_advisory_pre_trade_guards=False`,並附註解說明為何要這樣做、這個落差是何時發現的。

**驗證**:確認全repo只有這一個呼叫點沒傳這個kwarg(`group_a_plus/core/signal_contract.py`只在docstring提到函式名稱,沒有實際呼叫);`py_compile`過;`tests/test_build_group_a_plus_manual_holdings_execution_sensitivity.py`2個測試通過(誠實註明:這兩個測試是helper函式的unit test,不是`build_execution_plan()`本身的整合測試)。

### #2 leveraged_compounding_regime文件標籤不符實際行為(2504.20116)

**發現**:`group_a_plus/operations/execution_guard.py::apply_compounding_regime_pre_trade_guard()`的docstring寫「這是leverage-addition guard,不改model weights,永不強制減倉00631L」——這部分是對的。但函式回傳的guard dict裡`"policy"`欄位寫的是`"diagnostic_no_auto_weight_change"`,卻在同一個函式裡真的執行了`guarded_targets[ticker] = current`(把00631L的buy target鎖在目前持股不動)——也就是說,這個guard**確實會**自動擋掉新增00631L買單,只是不會強制賣出。標籤字串低估了它實際的live-enforcing行為。

**修復**:
1. 把`"policy"`字串改成`"auto_blocks_00631l_buy_additions_only_never_forces_sells"`,加註解說明為何改、原字串低估了什麼。
2. 在兩份相關的舊handoff文件加上更新提示banner,不動原文內容,只在最前面插入一段說明「這份文件寫的『production allocation未改變』在寫作當下(07-13/07-15)是對的,但現在不是了,請看execution_guard.py的policy欄位取得目前真實狀態」:
   - `GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`
   - `docs/a2120_letf_compounding_regime_shadow_20260715.md`

**驗證**:全repo grep確認`"diagnostic_no_auto_weight_change"`字串只出現在這一處程式碼(其他都是`report/group_a_plus/daily/json/*.json`底下的歷史輸出快照,正確地沒有動它們——那些是歷史紀錄不是活的程式);沒有測試斷言這個確切字串;`tests/test_group_a_plus_execution_guard.py`、`tests/test_group_a_plus_moira_execution_guard_backtest.py`、`tests/test_backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py`共15個測試全過,包含直接測這個函式邏輯的`test_mean_reverting_compounding_regime_blocks_00631l_add_only`(確認改標籤沒改到行為)。

### #3 ssrn-5140633趨勢跟隨腳本補交接文件

**發現**:`scripts/evaluate/evaluate_time_series_momentum_return_timing.py`自2026-07-12就存在(測AQR時間序列動能文獻的own-asset trailing return是否預測own-asset forward return,用跟這個session其他return-timing測試一致的Newey-West/Bartlett-HAC OLS檢定),而且**已經有**存檔的結果(`results/time_series_momentum_0050_latest.json`、`results/time_series_momentum_00631l_latest.json`),但從來沒有寫成交接文件。

**結果**:讀取現有結果檔——0050.TW與00631L.TW,3種lookback(1/3/12個月)×3種horizon(5/10/20日)共18組測試,**每一組p-value都遠大於0.05**(最小是0050的3個月/20日,p=0.145,仍不顯著),正負號也不一致(0050全正、00631L 1個月組是負的)。結論:own-asset動能在這兩檔標的上完全沒有預測力,吻合這個專案這條研究線一貫的「簡單return predictability訊號在這些標的上很弱到沒有」的模式。

**產出**:新增`docs/SSRN_5140633_TIME_SERIES_MOMENTUM_GROUPA_PLUS_REVIEW_20260808.md`,記錄方法、完整18組結果表、結論——closed,無後續。沒有動任何程式碼。

### #4 4份readiness review的as_of staleness查證(2107.09048/2511.12476/2512.10913/2606.26625)

**發現**:原始稽核抓到這4篇論文對應的readiness review JSON全部顯示`as_of=2026-07-20`,懷疑是staleness。深入查證後發現這**不是單一問題,是兩種完全不同的情況**:

- **2107.09048(reduced_rank_correlation)、2512.10913(rl_governance)**——這兩份是一次性手動研究產物,`build_group_a_plus_reduced_rank_correlation_readiness_review.py`和`build_group_a_plus_rl_governance_readiness_review.py`都從未被`run_ncf_daily_pipeline.py`或`check_group_a_plus_daily_status.py`引用過,檔案mtime自07-19/07-20後就沒再動過。**這是預期行為,不是bug**——沒有東西會自動重跑它,凍結是正常的。

- **2511.12476(asian_etf_tail_analytics)、2606.26625(dynamic_cvar_tail_cost)——真bug**。這兩支腳本**確實**每天在daily pipeline裡重跑(確認`generated_at: 2026-08-06T03:0x`,比另外兩份新),但`as_of`欄位卻仍然卡在2026-07-20。根因:兩支腳本都從`DEFAULT_REBALANCE = report/group_a_plus/latest/rebalance_review_20260720.json`讀取`dates.requested_as_of_date`當作自己的`as_of`——但這個檔名本身就是寫死的日期字串,不是一個真正的「latest」undated pointer。它的產生腳本`build_group_a_plus_rebalance_review.py`本身的`DEFAULT_OUTPUT`也寫死同一個帶日期檔名(而不是undated的latest路徑),而且這支產生腳本**從未被daily pipeline呼叫過**(檔案mtime停在2026-07-17,一次性手動跑過就沒再跑)。結果就是:兩份會員天重算的readiness review,`as_of`標籤已經連續超過3週靜默凍結在2026-07-20,而且不會自己修正,只會繼續錯下去。

進一步發現:同樣依賴這個寫死檔名的腳本至少還有8支(`build_group_a_plus_deep_hedging_overlay_review.py`、`adversarial_market_integrity_review.py`、`sciphyrl_readiness_review.py`、`finpilot_lite_planning_review.py`、`intervention_fatigue_risk_budget_readiness_review.py`、`finstressts_readiness_review.py`、`market_impact_readiness_review.py`),但這次沒有逐一查它們是否也接了daily pipeline、是否也中招——範圍比原始punch list估計的大很多。

**影響評估**:不影響實際交易——受影響的全是research_only/blocked狀態的promotion gate文件,沒有一個直接餵進target weights。真正的風險是metadata誤導判讀:任何人看`asian_etf_tail_analytics_readiness_review.json`的`as_of`欄位判斷新鮮度,會被誤導以為是07-20的資料,實際上裡面的診斷數字是當天算的。

**決定**:這次**沒有修**,只記錄。理由是這個修復牽涉到重新命名10支腳本的輸出路徑約定(把寫死日期檔名換成undated latest pointer)+可能要把`build_group_a_plus_rebalance_review.py`接進daily pipeline,範圍比這次punch list其他項目都大,而且沒有一個受影響的東西在活交易路徑上,值得單獨排時間做而不是順手改。

**產出**:`docs/READINESS_REVIEW_AS_OF_STALENESS_AUDIT_20260808.md`。

### #5 foundation_volatility_shadow.py(2505.11163 TimesFM骨架)未完成狀態記錄

**發現**:`group_a_plus/integrations/foundation_volatility_shadow.py`自2026-07-16就存在,docstring自稱是「TimesFM等foundation time-series volatility model的第一步整合,先用HAR-RV context變體讓pipeline驗證schema/evaluation/policy hook,之後只要換掉producer就能接上真model」。但檢查後發現:**「換掉producer」這一步從來沒發生過**——整支檔案完全沒有TimesFM模型、沒有checkpoint、沒有推論呼叫,`requirements`裡也沒有任何foundation-model套件;`latest_foundation_vol_snapshot()`回傳的`model_family`欄位直接寫死`"har_rv_context_shadow"`,連資料契約層級都沒假裝自己是foundation model輸出。

也就是說,這是一個「schema/管線骨架蓋好了,但論文真正的貢獻(預訓練foundation model做預測)從沒被實作」的半成品,不是一個部分驗證過的模型。

**wiring狀況**:沒有進daily pipeline;唯一的消費者是`scripts/evaluate/evaluate_group_a_plus_reentry_accelerator_clean.py`(也不在daily pipeline裡),而且那支腳本自己的結論就是`"research_only": True`、`"decision": "do_not_promote_keep_shadow"`。

**產出**:`docs/2505_11163_TIMESFM_FOUNDATION_VOLATILITY_SHADOW_GROUPA_PLUS_REVIEW_20260808.md`。沒有動任何程式碼——只是記錄現況,不是恢復這條研究線。

### #6 SPO姊妹論文2605.01176 v1與v4版本差異diff

**背景**:2026-07-26的session已經審查過並關閉這篇論文(v4版本),memory記錄「診斷的病灶(SPO+訓練predictor自我膨脹以強迫決策性排序)在Group A+完全沒有對應機制——NCF模型訓練在bounded的AUC/Brier分類目標上,target_weights來自手調regime表+bounded離散trim fraction,沒有連續無界的『預測報酬向量』給clipping/rescaling套用」。這次發現Downloads資料夾裡v1、v4兩個版本都存在,原始稽核想確認v1是否有v4沒有的內容會影響這個判定。

**方法**:直接讀兩份PDF全文逐段比對(非grep關鍵字,是完整內容比對)。

**發現的差異**(共5處,詳見`docs/2605_01176_V1_V4_DIFF_GROUPA_PLUS_REVIEW_20260808.md`):
1. Table 1週轉率結果從v1的單次run數字,升級為v4的5-seed mean±std——結果數字略有變動但方向不變、且更穩健(seed-stable)地確認了原本的結論。
2. Table 2新增明確的`Fee rate κ=0.005`揭露欄位——純reproducibility補充。
3. Table 3的λ=50.0那一列有小幅數字修正,但沒有任何一個粗體最佳指標的贏家因此改變。
4. Section 2.2的regret公式改寫得更明確(引入`U_t`符號),數學實質不變。
5. **唯一算實質的差異**:Section 6 Future Work從v1的「加碼型」建議(設計更好的ranking-based loss、加更多財務動機的修正機制)改成v4更謹慎的自我提問——「觀察到的週轉率膨脹是不是這個特定penalty formulation跟linear predictor的產物,還是SPO-based learning本身的內在問題?」。v4的作者對自己發現能否推廣到其他設定,比v1更沒把握。

**結論**:這些差異都不影響論文診斷的核心機制(SPO+訓練predictor在transaction-cost調整後marginal score排序下自我膨脹)跟三個穩定化手段(clipping/rescaling/partial adjustment)本身,原本關閉判定的推理鏈只依賴這個沒變的機制,不依賴v1↔v4之間變動的週轉率百分比或Future Work措辭。v4新增的自我懷疑(差異5)反而是原判定夠謹慎而非不夠謹慎的佐證。**不重開,07-26的v4審查維持有效。**

### #7 a2118.py backtest未呼叫ncf_overlay_summary的架構缺口(2603.21330)——已依使用者選擇的方向修復

**發現**:`group_a_plus/runners/a2118.py`第86行`from group_a_plus.integrations.ncf import load_ncf_signal, ncf_overlay_summary`——`ncf_overlay_summary`被import但整支檔案**從未呼叫**,是個dead import。深入看發現這不是「補一行呼叫」能解決的小事:

- a2118.py現有的NCF避險邏輯(`late_bull_triggered`/`rally_suppressed`/`soft_hedge_triggered`,約969-1015行)是完全手刻的,**只讀00631L的訊號**,從頭到尾沒有載入或用到00632R的NCF訊號。
- 但`ncf_overlay_summary()`需要同時吃`ncf_00631l`跟`ncf_00632r`兩份訊號,做cross-ticker一致性檢查,回傳`action`(reduce_00631l/hold)、調整後權重、人類可讀摘要。
- 兄弟runner`a2113.py`、`a2114.py`、`a2115.py`都已經在用這個函式(`ncf_overlay_summary(sig_631l, sig_632r, golden_weights, today_regime)`的固定呼叫模式),唯獨a2118.py(目前的active live策略)沒接。
- 原始2603.21330(FinRL-X)論文審查文件本身完全沒提到`ncf_overlay_summary`——這個落差是Fable稽核自己交叉比對抓出來的,不是論文要求的功能,單純是程式碼一致性缺口。

**跟使用者確認方向**:因為這個發現有多種可能的修法(從單純刪掉dead import,到把cross-ticker邏輯真的接進即時避險判斷,風險差異很大),依照原始punch list的指示,動手前用`AskUserQuestion`列了4個選項讓使用者選:(a)純附加診斷(推薦)(b)刪掉dead import(c)只記錄不處理(d)整合進避險觸發邏輯。**使用者選了(a)純附加診斷。**

**實作**(依a2113/a2114/a2115既有的呼叫模式做,不是自創新寫法):
1. `run_a2118()`新增`ncf_00632r_path: str | None = None`參數(插在`ncf_panel_631l_path`之後)。
2. 用既有的`_resolve_ncf_path(ncf_00632r_path, "00632r")`(這個helper函式本來就支援任意ticker_tag,不用改)自動解析00632R訊號檔路徑,跟現有的00631L路徑解析並排。
3. 在現有`ncf_live`(00631L專屬的手刻避險邏輯)算完之後,**另外**加一段完全獨立的區塊:當00631L跟00632R兩份訊號都能解析到時,呼叫`ncf_overlay_summary(sig_631l, sig_632r, golden_weights, today_regime, ma_gap=today_ma_gap)`,結果存進新的`ncf_overlay_diagnostic`欄位,不覆寫、不合併進`ncf_live`。
4. 這個新區塊在`curve`/`sim_result`/`executed_regime`都已經算完之後才執行,程式碼位置上物理保證不可能反過來影響回測模擬結果或即時交易決策——純觀察用。
5. CLI新增`--ncf-00632r`參數,對應到`args.ncf_00632r`,傳進`run_a2118()`。
6. 加註解清楚標記這段是2603.21330稽核發現+2026-08-08修復,並解釋為何刻意不動現有避險邏輯。

**驗證**(全部針對真實資料/真實邏輯,非猜測):
- `py_compile`過。
- 用真實DB跑了一次完整`.venv/bin/python3 -m group_a_plus.runners.a2118 --start 2015-01-01 --end 2026-08-08 ...`,確認:
  - `ncf_overlay_diagnostic`正確填入(2026-08-07訊號:00631L direction=UP、00632R direction=DOWN、`direction_conflict: true`但`cross_ticker_consistency.conflict_flag: false`、agreement_score=0.89、`action: "hold"`——今天兩檔訊號有點方向分歧但還在可接受一致性範圍內)。
  - `metrics`(final_value/sharpe_ratio/sortino_ratio等)跟改動前完全一致——因為新區塊物理上在curve算完之後才跑,不可能改到它。
- 相關測試全過:`test_a2118_strategy_logic.py`(7)、`test_a2118_composite_confidence_sweep.py`+`test_a2118_finrl_dual_engine_reconciliation.py`+`test_bayesopt_a2118_trigger.py`+`test_build_a2118_dfl_advisory.py`+`test_build_a2118_dfl_shadow_ensemble_log.py`+`test_evaluate_a2118_attribution.py`(合計32)、`test_group_a_plus_ncf_integration.py`+5個a2118 evaluate測試(合計126)——**共165個測試全過**。
- 全repo掃描`run_a2118(`的72處呼叫點,確認全部都是keyword-argument呼叫風格(沒有任何一處用超過4個positional參數,而新參數插在第9個位置),新增這個keyword-only-by-convention參數不會破壞任何既有呼叫端。

## 3. 本次session的檔案異動清單

程式碼:
- `scripts/evaluate/build_group_a_plus_manual_holdings_execution_sensitivity.py`——加`enforce_advisory_pre_trade_guards=False`
- `group_a_plus/operations/execution_guard.py`——`policy`字串重新命名+註解
- `group_a_plus/runners/a2118.py`——新增00632R訊號載入+`ncf_overlay_diagnostic`欄位+CLI參數`--ncf-00632r`

文件(新增):
- `docs/SSRN_5140633_TIME_SERIES_MOMENTUM_GROUPA_PLUS_REVIEW_20260808.md`
- `docs/READINESS_REVIEW_AS_OF_STALENESS_AUDIT_20260808.md`
- `docs/2505_11163_TIMESFM_FOUNDATION_VOLATILITY_SHADOW_GROUPA_PLUS_REVIEW_20260808.md`
- `docs/2605_01176_V1_V4_DIFF_GROUPA_PLUS_REVIEW_20260808.md`
- `GROUP_A_PLUS_20260808_PAPER_AUDIT_PUNCH_LIST_RESOLUTION_HANDOFF.md`(本文件)

文件(更新,加banner不動原文):
- `GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`
- `docs/a2120_letf_compounding_regime_shadow_20260715.md`

## 4. 驗證紀錄

所有7項都做了對應真實資料/真實邏輯的驗證(不是只看程式碼推論),細節見各項小節。彙總:
- `py_compile`:3支被改的.py檔全過。
- pytest:直接相關測試累計165+個(a2118策略邏輯、ncf整合、execution_guard、moira guard、manual holdings sensitivity),全過。
- 真實資料端到端跑:a2118.py用真實DuckDB從2015到2026-08-08完整跑過一次,新診斷欄位正確產出,回測績效數字(final_value/sharpe等)確認與改動前一致。
- 全repo grep交叉檢查:policy字串改名前的全域唯一性確認、`run_a2118`所有72處呼叫的positional/keyword風格確認。

## 5. 對應memory索引

這7項本身尚未各自寫進memory index(除了這份總索引之外)。建議下次session開頭時把以下逐條存進memory:
- 第2項的execution_guard policy重新命名(feedback/project類型都可以)
- 第4項的readiness review staleness系統性根因(project類型,標記「未修,範圍較大,值得之後單獨排」)
- 第7項的a2118.py ncf_overlay_diagnostic新增(project類型,標記「純附加,不影響交易行為」)

## 6. 未完成/刻意不做的事項

1. **第4項(readiness review staleness)的實際修復未做**——只記錄根因與影響範圍。要修的話需要:(a)把`build_group_a_plus_rebalance_review.py`的`DEFAULT_OUTPUT`從寫死日期檔名改成undated的`rebalance_review.json`latest pointer;(b)同步修改至少10支消費者腳本的`DEFAULT_REBALANCE`;(c)決定要不要把`build_group_a_plus_rebalance_review.py`接進daily pipeline,或改成消費者腳本改用其他既有的、確實每天更新的欄位(例如`hmm_wj.get("as_of")`)當作`as_of`來源。這幾支腳本裡有多少支真的接了daily pipeline也沒有逐一查完。
2. **原始42+篇論文稽核的完整逐篇結論**沒有獨立存成repo檔案,只存在session transcript裡——如果之後需要,得回頭爬transcript整理,這本身可能值得排一個小任務單獨做。
3. 第5項(foundation_volatility_shadow)跟第6項(SPO diff)都是「記錄現況,不恢復/不重做」的決定,不是遺留工作。

## 7. 下一步建議

依優先順序:
1. 若要動第4項的readiness review修復,先確認除了asian_etf_tail_analytics跟dynamic_cvar_tail_cost之外,還有哪幾支其餘8支腳本真的接了daily pipeline(這次沒查完)——決定實際受影響範圍後再評估是否值得做。
2. 把第5節提到的3條memory補上。
3. 若之後有新論文要審查,可以直接沿用這次確立的「先讀完整PDF而非只grep關鍵字」的比對方法(第6項SPO diff就是這樣做的),比單純比對版本號或摘要可靠。
