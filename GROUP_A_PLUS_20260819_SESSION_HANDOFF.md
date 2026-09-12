# Group A+ 2026-08-19 Session 交接記錄

**日期**：2026-08-19（週三，session橫跨08-18深夜~08-19）
**涵蓋範圍**：arXiv:2510.14985 DeepAries interval（重提，確認已closed）；arXiv:2506.19200 LETF profit-triggered harvest（新建shadow test，抓到並修復一個feature warmup真bug，regime-gate過濾想法測試無效，收斂為mixed/closed）；arXiv:2607.16450尾端風險指標（第三次重提，發現7/8已wiring完成，補上1個真缺口`negative_semivariance`，`compare.py`新增markdown渲染）；arXiv:2601.21447股債相關性/defensive basket（重提，確認同日稍早已經promote，BAWS pilot結論一併回顧）；每日資料下載+完整daily pipeline執行（發現execution_blocked/ncf_panel過期兩個現況）；NCF late-bull-hedge trigger的h20-specific confidence根因分析+兩個shadow變體測試（拆年度後2/3勝、1/3敗，維持research-only）；golden1_0531 vs a2118（最新策略）8/19零持股$1M預測（過程中補抓過期institutional_data解除execution guard）；arXiv:2607.03669 overnight/intraday session-split事件表測試（phase 1 gate未過，closed research_only）。

## 一句話摘要

使用者延續前幾天的論文審查節奏，逐一重提6篇之前可能做過的論文/研究方向。這次的特點是**大多數提案在查證後發現「已經做過」或「已經promote」**，本session的實際新增工作集中在：(1)第一次真正完整測試2506.19200的profit-triggered harvest機制（跟既有4個risk-triggered overlay不同的新角度），抓到一個真的feature-lookback bug，(2)補完2607.16450尾端風險指標最後1個wiring缺口並加上markdown可讀輸出，(3)跑了一次真正的完整daily pipeline並發現兩個需要人工決定的現況（execution被institutional資料延遲擋住、ncf_panel_631l pin了23+個交易日沒更新），(4)深入拆解NCF late-bull-hedge trigger為什麼結構性從不觸發，做出兩個修正版本的shadow測試，拆成3個獨立年度後看到2/3勝1/3敗的mixed結果。**全部維持research-only或已在其他session promote，這個session本身沒有新的production程式碼變更。**

## 1. arXiv:2510.14985 DeepAries adaptive review interval — 重提，確認closed

使用者用「危機/regime boundary→1天、golden1穩定→3天、defensive穩定→3~5天」的敘述再次提出adaptive review interval機制，未察覺已經在08-14做完並在08-18(稍早的另一個session)補寫過memory（[[project_2510_14985_deeparies_interval_closed_20260814]]）。核對後回報：這個核心機制（regime-based review interval）已經被兩次獨立驗證證偽——08-09版本(1/3/5天)mixed result，08-14版本(1/5/20天，choppy fail-safe)在3窗口真holdout(2022/2023/2026)上0/3 pass，完全退化成跟daily review一樣。使用者提出的新數字組合(1/1/3/3-5)核心機制相同，未重新測試，維持closed。

## 2. arXiv:2506.19200 LETF profit-triggered de-risk — 新建shadow test，closed research_only

延續上方對話，使用者提出：跟既有4個00631L overlay（`_golden_tail_trim_weights`/`_apply_golden_follow_through_trim_overlay`/`_golden_leverage_cap_weights`/`_apply_golden_rebound_recapture_overlay`，全部risk-triggered：drawdown/tail_risk_score/realized_vol_ratio/VaR breach）不同，這篇提出**profit-triggered**方向——00631L已累積顯著trailing gain + compounding_effect(00631L跑贏2x的0050) + relative momentum從高點回落 → 小幅trim golden1內00631L，移入0050不進cash。

**查repo**：`profit_trim/gain_harvest/leverage_gain_lock`關鍵字全repo搜尋零命中，確認是新角度。

**新建**：`scripts/evaluate/evaluate_2506_19200_letf_profit_harvest_shadow.py`（純shadow，未動a2118.py/golden1_0531）。特徵：`trailing_gain`(60d)、`compounding_effect`(00631L 60d報酬 - 2×0050 60d報酬)、`relative_momentum`(20d)及其decay(20d rolling peak - current)。全部causal，用9窗口（6 tuning-style + 3真holdout：2022全年/2023/2026）。

**抓到並修復一個真bug**：第一版feature直接在每個窗口自己的`prices`序列上算，序列被硬切在窗口`start`——導致每個窗口開頭前2-3個月的feature全部NaN，無法觸發，即使那些早期日期本來有前一年真實資料可算60天報酬。修法：額外抓150天warmup期價格（`_load_prices`+`_warmup_start`）算feature，再切回顯示窗口。

修復前後對比：
- 修前：9窗口只有3個觸發（2020/2021/2023holdout），1勝2敗
- 修後：新增live_2024_2026(+48,853, Sharpe+0.132)、active_2025_2026(+37,652, Sharpe+0.229)、holdout_2026(+21,930, Sharpe+0.274, MDD+0.021三項全贏)三個窗口的觸發，全部落在2025-07~2026-06這段00631L暴漲期(trailing gain最高99%)。變成4個獨立episode：2020虧、2021小賺、2023holdout虧、2025-26大賺，holdout 2/3 pass（僅holdout_2023 fail）。

**後續測試**：用既有`group_a_plus/integrations/leveraged_compounding_regime.py`的`classify_compounding_regime`當gate（只在非TREND_PERSISTENT時才harvest），設想濾掉"上升趨勢中的正常拉回被誤判"。實測4個episode每天的分類：TREND_PERSISTENT跟MEAN_REVERTING在虧損組(2020/2023)跟大賺組(2025-26)都混著出現，且2025-26**最賺錢**的三天(06-23/24/25)恰好都是TREND_PERSISTENT——這個filter沒有分離度，會濾掉最好的訊號，濾不乾淨壞的。**沒有繼續調**（只有4個episode，繼續調就是對著答案overfitting，跟[[feedback_overfitting_fixed_window_tuning]]同一個陷阱）。

**結論**：closed，research_only，不promote。Memory：[[project_2506_19200_letf_profit_harvest_mixed_closed_20260818]]。

## 3. arXiv:2607.16450 尾端風險指標 — 第三次重提，補完最後1個缺口

使用者第三次提出同一篇論文（延續08-01骨架、08-18稍早另一session完成的wiring，見[[project_tail_risk_metrics_wired_and_oos_refuted_20260818]]），用「Final Value/Sharpe/MDD之外固定增加8個尾端風險指標」的說法再問一次，未察覺已完成。

**核對現況**：7/8已經在`backtest_group_a_plus_switch_policy.py`/`backtest_group_a_plus_overlay.py`的`_metrics()` → `group_a_plus/governance/compare.py`的`TAIL_RISK_METRIC_KEYS`跑通。

**抓到並修復2個真缺口**：
1. `negative_semivariance`——`_metrics()`本來就有算，但沒被列進`TAIL_RISK_METRIC_KEYS`，governance報告看不到。已補上一行dict entry。
2. `tail_risk_metrics`區塊只存在JSON裡，沒有任何下游腳本渲染成markdown表。新增`compare.py`的`_write_md()`函式 + CLI新增`--output-md`（預設None，不傳不影響既有呼叫者的行為），輸出兩張表：既有promotion gate表（final/sharpe/mdd，決策邏輯不變）+ tail-risk診斷表（8指標，advisory-only），表尾附上OOS結論摘要（ES95/negative_semivariance方向一致但p=0.07~0.11未達顯著，Sharpe/STARR/final_value在乾淨獨立年度下不穩定，2022反轉），避免有人看markdown表格誤以為這些指標已經在gate決策裡生效。

**驗證**：用合成baseline/candidate JSON端對端測過真的CLI路徑，`tests/test_group_a_plus_governance_compare*.py`（8個）+ 更廣的`-k compare`（14個，含較慢整合測試，38分鐘跑完）全過。

也順帶澄清：「CVaR 95%」跟「Expected Shortfall 95%」是同一統計量的兩種叫法（連續分布下ES=CVaR），沒有另外實作。

**改動檔案**：`group_a_plus/governance/compare.py`（`TAIL_RISK_METRIC_KEYS`+`_write_md`+`--output-md` CLI參數，全部向後相容、非破壞性新增）。狀態：uncommitted。

## 4. arXiv:2601.21447 股債相關性/defensive basket — 重提，確認同日稍早已promote

使用者提出「00679B/Cash Router」動態切換提案（DCC/conditional correlation模型），列出`bond30/30`現行 vs `bond15/45`候選 vs `bond0/60`候選三選一，並自稱「這是目前最推薦先測的新策略機制」。核對後發現：**同一天稍早的另一個session已經完整做完並promote**（[[project_a2118_defensive_basket_00679b_removed_promoted_20260818]]）。

原封不動的三選一grid結果：bond0_cash60嚴格獲勝（final $5,117,950→$5,492,297，Sharpe 1.326→1.396，MDD -26.80%→-23.90%，ES95/半變異數/回補天數全部同方向），根因是7次防禦episode只有2020 COVID一次00679B真正避到險，2022跟2025-03反而跌得比0050兇。**已經真的promote進`group_a_plus/runners/a2118.py`**（defensive basket = `bond0_cash60`），策略層級端到端驗證final_value+11.3%/Sharpe 1.253→1.387/MDD改善4.6pp/drawdown duration砍半。

使用者提到的「conditional correlation/DCC」動態切換部分也已經pilot過（[[project_baws_adaptive_window_pilot_20260818]]）：Fisher z-test版BAWS正確、即時偵測到全部3次已知regime break，但拿來動態切換bond/cash比例，3個threshold測試都沒打贏已promote的「一刀切bond0_cash60」（最好只贏$9k/+0.17%，尾端指標反而略輸，換手多23次），維持shadow-only。

**兩個待注意狀態（非本session造成，原記錄複述）**：(a) `.py`原始碼已改但`execution_plan.json`/`live_signal.json`當時還是08-14 cache沒重新產生，要等下次daily pipeline真的跑且regime觸發defensive才會第一次生效；(b) 這些改動當時全部uncommitted。

## 5. 每日資料下載 + 完整daily pipeline執行

**Step 1 — 只下載資料**：`scripts/run/run_ncf_daily_pipeline.py --only-refresh`（背景執行，18/18步驟成功）。OHLCV更新到2026-08-18；`institutional_data`（法人買賣超）只到08-17，晚一天——來源發布時間差，非抓取失敗。

**Step 2 — 完整pipeline**（使用者透過AskUserQuestion確認要跑完整版，非只補新聞）：沿用`run_daily.bat`的正式指令`--skip-refresh --refresh-external-cache`（背景執行，105/105步驟成功，exit 0）。

**結果**：
- Regime維持golden1，**沒有觸發defensive**——新promote的bond0_cash60 basket這次還沒真正上場。
- 三個NCF模型方向：00631L看多(prob_up=0.6016，但freshness=`degraded_stale`)、00632R看空(prob_up=0.3316)、0050看多(prob_up=0.525)。
- **`execution_allowed=False`**：`execution_guard_reasons=["required strategy sources are stale or missing: ['institutional_0050']"]`——跟Step 1發現的institutional資料1天延遲是同一個根因。`execution_risk score=0.397`（high level）。
- **`execution_plan.json`沒有被這次pipeline重新產生**，還停在08-14——pipeline只更新了`live_signal.json`（08-19 22:55新產生，注意這是先前一輪對話中的timestamp，實際請以檔案mtime為準）。alert明確標示"regenerate it manually"。
- **`strategy_trust_gate = ABSTAIN`**：因model ensemble方向不一致(signal_alignment=mixed) + 上述資料品質問題(feature_table_sync error)。
- `ncf_panel_631l`落後23個交易日（最後涵蓋到07-16）——見下方第6節深入分析。
- 新聞抓取：LTN 161篇、Yahoo 77篇、SETN 334篇、FinMind 318篇。
- ops_health：`errors=['system_resources'（磁碟，依既有[[feedback_no_disk_warning_topic]]規則不主動提醒), 'feature_table_sync'（即institutional延遲）]`，`warnings=['artifact_health','module_health','readiness_review_freshness']`。

**未完成**：execution_plan.json尚未手動重新產生；institutional_0050延遲資料尚未重新抓取確認是否已補齊。

## 6. ncf_panel_631l 過期根因分析

使用者追問「為什麼都沒差」（為何pin在07-16的panel跟今天最新的panel實際上不影響任何決策）。

**根因**：`strategy.json`的`active_strategy.runner_params.ncf_panel_631l_path`寫死指向`results/ncf_00631l_panel_latest_20260716.csv`——這是2026-07-02 Fable audit（M3）刻意的governance設計：panel pin視同策略變更，須人工決定才更新，避免NCF hedge決策隨模型每日retrain默默漂移。daily pipeline其實每天都有正常產生新panel（`ncf_00631l_panel_latest_20260818.csv`確認存在），但不會自動repin回strategy.json。`ncf_panel_stale`這個alert（見`group_a_plus/operations/daily_signal.py`約1404-1430行）就是設計來提醒這件事，本身沒有故障。

**用今天最新panel驗證refresh pin不影響任何決策**：trigger條件`h20_prob_up<0.33 AND confidence>=0.55`，2025-01-02至今394天，**0天符合**（現在h20_prob_up=0.72~0.77明顯偏多、confidence只有0.28~0.41），跟strategy.json自己記錄的07-22舊研究結論（6個panel快照全部0觸發，NCF overlay對production數字貢獻剛好是0）完全一致。

**更深入的機制拆解**（使用者追問「為什麼」）：confidence欄位是`(ensemble_prob_up-0.5).abs()*2`，而`ensemble_prob_up`是h1(~20%)+h5(~30%)+h20(~49%)權重混合，**不是h20單獨的**。79天h20_prob_up<0.33（h20確信看空）的日子裡，prob_up_h1平均0.473、prob_up_h5平均0.455（近乎丟銅板，未同步看空）——短期horizon把混合值拉回中性，confidence在這79天最高只到0.538，永遠到不了0.55。這是trigger設計上「方向看h20單一horizon、把握看多horizon混合ensemble」的結構性錯位，不是panel內容新舊的問題，也不是模型壞掉。

## 7. NCF late-bull-hedge h20-specific confidence 修正方案 — 兩個shadow變體測試

使用者問「有什麼可以改善的」，討論後選定「把confidence改成h20專屬的magnitude」為優先pilot方向。使用者確認後，新建`scripts/evaluate/evaluate_a2118_h20_specific_confidence_shadow.py`。

**方法**：不修改`_apply_late_bull_overlay`本體（保持production邏輯完全不動），只把panel CSV的`confidence`欄位換成不同定義後另存一份variant檔，用`run_a2118(ncf_panel_631l_path=variant_path)`跑完整a2118 pipeline（含正式參數`h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55`），跟baseline（原始confidence欄位，全部窗口0觸發）比較。7個窗口：4個backfill(2020/2021/2022 Jan-Oct/2024) + active_2025_2026(latest panel) + holdout_2023 + holdout_2026。

**變體1 `h20_magnitude`**：`confidence = |prob_up_h20-0.5|*2`（純h20單一horizon的信心度，不混合h1/h5）。結果：全部窗口baseline仍0觸發（驗證診斷正確）；variant只有2個真正獨立事件觸發（2024-05-29、2026-02-10，其餘窗口皆0）。兩次都是「final_value小跌、Sharpe跟MDD同步改善」的保險費特徵，方向一致但n=2遠不足以下結論。

**變體2 `h1h5_agree`**：`confidence = 1.0 if (prob_up_h1<0.5 AND prob_up_h5<0.5) else 0.0`（只要求短期不唱反調，不要求混合幅度）——同一個`conf>0.55`閘門，用0/1直接對應pass/fail。觸發次數大增到24天（後補測2025單獨年度後總計28天）。

用真正的promotion gate標準（`compare.py`的98%值下限，比我原先腳本自己寫的「delta≥0」門檻更寬鬆）重算，拆成3個獨立年度：

| 年度 | 觸發次數 | final_value | Sharpe | MDD |
|---|---|---|---|---|
| 2024 | 4次 | -1.27%（過98%門檻） | 1.638→1.764 改善 | -17.1%→-14.7% 改善2.4pp |
| 2025（單獨） | 4次 | -1.68%（過98%門檻） | 2.031→**1.991 變差** | -12.19%→-12.19% **無改善** |
| 2026 | 8次 | -1.50%（過98%門檻） | 2.267→2.451 改善 | -12.3%→-10.0% 改善2.3pp |

（先前合併看的active_2025_2026含2025全年+2026，final_value delta -6.88%不過98%門檻——是2025下半年虧損段跟2026大賺段混在一起的假象，拆開年度後才看清楚。）

**結論**：2/3年有效(2024/2026)，1/3年(2025)不只沒賺、風險指標也一起變差，不是雜訊等級的差異。3個獨立年度樣本量仍偏小，2020-2023完全無trigger樣本（該機制本來就設計成鎖定"late bull"特徵：ma_gap持續偏高+h20中期轉弱，這個組合在2020-2023沒出現過，不算異常）。**維持research_only，不promote**，跟這個repo這輪session大多數研究線收斂到同一種「方向不是全錯、證據不夠乾淨」狀態。

## 8. golden1_0531 vs a2118（最新策略）8/19零持股$1,000,000預測

延續固定「使用golden1_0531及最新策略，以1百萬，預測X」請求模式，這次未提供持股xlsx，視為零持股起始。資料截至2026-08-18收盤（08-19當天資料尚未產生）。全程輸出到scratch路徑，production（`report/group_a_plus/latest/execution_plan.json`仍08-14、`live_signal.json`仍08-18 22:55）確認未被覆寫。

**golden1_0531**（`generate_dual_group_signal.py --group group_a --live-start --extra-cash 1000000 --override-holdings-json '{}' --download-end 2026-08-18`）：`rebalance`，PVA連續風險縮放疊加生效(S狀態)，candidate/effective target 0050 61.6%(5,874股)/00631L 8.4%(2,409股)/cash 30%($300,000)，data_date=2026-08-18 stale_days=0。

**a2118**（`python3 -m group_a_plus.operations.execution_plan --holdings-json <zero_holdings.json> --cash-balance 1000000 --as-of 2026-08-19`，output/latest-pointer導向scratch）：第一次跑`execution_allowed=False`，guard reason `institutional_0050` stale——跟第5節pipeline發現的1天發布延遲同一根因，這次直接手動補抓（`FinRL/data/stock_db.py --add-institutional 0050.TW,00631L.TW,00632R.TW,00679B.TWO --start 2026-08-15 --end 2026-08-19`）確認更新到08-18後，`execution_allowed=True`。

regime=golden1，讀golden signal快取理論目標0050 53%/00631L 8.39%/cash 38.6%（跟golden1_0531現算的61.6%/8.4%不同，已知H3快取落差，方向一致）。因零持股第一天觸發`large_buy_staged`（`max_initial_buy_fraction=0.4`），實際下單只有理論目標的40%：
- 買0050 2,020股（$211,898，理論目標5,052股，**deferred 3,032股/$318,057留到後續**）
- 買00631L 963股（$33,522，理論目標2,409股，**deferred 1,446股/$50,335留到後續**）
- 換手率24.5%，執行成本$472，執行後現金$754,108

**使用者追問「買股差這麼多」**：解釋兩層原因——(1)golden1_0531現算70%投入 vs a2118讀快取61.4%投入，H3落差；(2)golden1_0531是純訊號工具直接回報完整目標，a2118的execution_plan.py額外有零持股大額建倉分批進場風控(`max_initial_buy_fraction=0.4`)，第一天只執行理論目標的40%，不是策略分歧變大。

## 9. arXiv:2607.03669 Overnight/Intraday Session-Split — phase 1測試，closed research_only

完整記錄：`GROUP_A_PLUS_20260819_2607_03669_OVERNIGHT_INTRADAY_SESSION_SPLIT_HANDOFF.md`（同目錄，本次新建）。

使用者提案：論文主張overnight跟intraday報酬不該當同一隨機過程，兩session厚尾程度顯著不同，混在一起會扭曲動態相關性估計。提議把每天拆成`overnight_ret=today_open/yesterday_close-1`與`intraday_ret=today_close/today_open-1`，先做4類事件表（GapDown/GapUp × IntradayUp/IntradayDown），測00631L/0050 next 1/3/5d跟future drawdown，「如果四類差異很大，再值得建正式模型」（使用者自訂的phase 1 gate）。

**查repo**：無重複，唯一相關命中是純執行層的`pause_open_gap_down`暫停下單機制，跟這次的事件分類+forward return研究不衝突。

**資料**：`ohlcv`表本有`open`欄位，0050回溯2009-01-02、00631L回溯2014-10-23，皆無股票分割需處理。

**測試**：(a)全樣本(n=2,876)單純正負號4分類，ANOVA全部p=0.44~0.996；(b)使用者具體舉例的shock版本(overnight≤-1%/≥+1%再依intraday方向細分reversal/continuation，各組n=48~101)，Welch's t-test全部p=0.27~0.97。兩種粒度、8組forward指標(0050/00631L的fwd1/fwd3/fwd5/fwdmin5)全部無統計顯著差異。

**結論**：phase 1 gate未過，不建正式模型，closed research_only。澄清這不是推翻論文本身——論文講的是報酬分布形狀(厚尾/波動率動態)該不該分session估計，這次測的是「session組合能否預測forward return」，是不同問題，這次null result只回答後者。

未建立任何repo檔案（純exploratory one-off，中間結果`/tmp/overnight_intraday_events.csv`為session-scoped temp，非repo正式產出）。

## 本session改動檔案清單

**新建**（research/shadow，全部uncommitted）：
- `scripts/evaluate/evaluate_2506_19200_letf_profit_harvest_shadow.py`
- `scripts/evaluate/evaluate_a2118_h20_specific_confidence_shadow.py`
- `results/2506_19200_letf_profit_harvest_shadow.json` + `report/group_a_plus/latest/2506_19200_letf_profit_harvest_shadow.md`
- `results/a2118_h20_specific_confidence_shadow.json` + `report/group_a_plus/latest/a2118_h20_specific_confidence_shadow.md`
- `results/a2118_h1h5_agree_confidence_shadow.json` + `report/group_a_plus/latest/a2118_h1h5_agree_confidence_shadow.md`
- 各panel variant CSV（`results/*_h20_magnitude_variant.csv`、`results/*_h1h5_agree_variant.csv`）——純研究用途，不影響production panel
- `GROUP_A_PLUS_20260819_2607_03669_OVERNIGHT_INTRADAY_SESSION_SPLIT_HANDOFF.md`（本次新建的獨立主題handoff doc）

**修改**（uncommitted）：
- `group_a_plus/governance/compare.py`：`TAIL_RISK_METRIC_KEYS`新增`negative_semivariance`；新增`_write_md()`+`--output-md` CLI參數

**Production資料狀態變更**（透過daily pipeline/手動補抓正常執行產生，非程式碼變更）：
- `report/group_a_plus/latest/live_signal.json`（08-19重新產生，第5節）
- `results/ncf_00631l_panel_latest_20260818.csv`等當日panel/chip資料
- `institutional_data`表0050.TW/00631L.TW/00632R.TW/00679B.TWO已補抓到08-18（第8節，透過`FinRL/data/stock_db.py --add-institutional`手動補齊）

**Scratch產出**（不影響production，僅供這次預測參考）：
- `results/whatif_signal_group_a_20260819_020338.json`（golden1_0531 8/19零持股預測）
- 執行計畫scratch檔案位於session temp目錄，未落入repo正式路徑

## 待辦 / 下次session注意事項

1. `execution_plan.json`仍是08-14舊版，production的`execution_allowed`狀態需要重新跑一次正式（非scratch）的execution plan才會反映——這次第8節已經手動補齊institutional_data到08-18，理論上下次重新產生時應該不會再被同一個原因擋。
2. `ncf_panel_631l_path`的pin目前確認不影響任何決策（trigger 0/394天），但如果之後有人想真正啟用h20-specific confidence修正（第7節變體1或2），需要同步考慮是否連帶更新這個pin，並且先在真正的holdout（例如2027年出現後）驗證，不要用已經看過的2024/2025/2026再調參數。
3. 2607.16450的markdown渲染(`compare.py --output-md`)還沒被daily pipeline實際呼叫過，只在手動CLI測試中驗證，之後可考慮是否要接進`run_ncf_daily_pipeline.py`的promotion_gate步驟。
4. 2607.03669的overnight/intraday分析是session-scoped exploratory，中間結果`/tmp/overnight_intraday_events.csv`不會保留到下次session——若要重跑，直接複製對應handoff doc第3-5節的程式碼即可，不需要額外查證。
5. 本session所有.py/.md新建與修改檔案均為uncommitted，尚未詢問使用者是否要commit。
