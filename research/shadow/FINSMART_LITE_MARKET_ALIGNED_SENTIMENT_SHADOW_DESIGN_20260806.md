# FinSMART-lite / market_aligned_sentiment_shadow.json — Design Note (2026-08-06)

Status: research/shadow design note only. No production code, DB, or `report/latest/`
file has been written by this note. Follows on from
`GROUP_A_PLUS_20260805_LETF_PREDATION_PAPER_REVIEW_HANDOFF.md` section 8.

## 1. FinSMART PDF 重點與數據

arXiv:2607.28127, Iacovides/Zhou/Mandic (Imperial College London), 2026-07-30, 8 頁。

- 現有財經情緒LLM(FinBERT/FinGPT/FinLlama/FinDPO)都在靜態人工標註資料上訓練，跟市場實際反應脫鉤。
- FinSMART用GRPO直接拿**發布當天個股超額報酬(idiosyncratic alpha=個股報酬−大盤報酬)**當reward：`d=y且y≠0`(方向對)給+2.0、`d=y=0`(正確中性)給+0.1、`d=−y且y≠0`(方向錯)給−1.5、其餘(漏判/誤判)給−1.0。門檻`τ=0.5%`——alpha要超過這個才算「經濟上有意義」。刻意不對稱，避免模型collapse成一律中性。
- **核心方法論發現**：情緒與「發布當天」報酬的Pearson相關係數(TMF: 0.41, MarketWatch: 0.37)，換成「隔天」報酬後掉到0.03——訓練用當天報酬當reward，但評估交易報酬時仍用隔天報酬避免look-ahead bias。
- 結果(S&P500多空35%組合)：累積報酬264.9% vs FinDPO(現有SOTA)109.8%；Sharpe 1.97 vs 1.12；Sortino 2.40 vs 1.44；Calmar 4.23 vs 1.48；RankIC 0.061 vs 0.053。每半年retrain(expanding window)可擴大到406%累積報酬。
- 運算需求小：Llama-3-8B-Instruct + LoRA(rank16, 13.6M可訓練參數，約0.17%)，單張A6000 GPU，8小時訓練完成。

## 2. 可導入 Group A+ 的「FinSMART-lite」設計

**先講死一件事**：完整版(RL微調LLM)在這個repo做不到——見第5節readiness review的`llm_queries_allowed_at_test_time: false`硬性邊界，加上零GPU/PEFT/TRL/GRPO環境、新聞資料只有標題沒有內文。「FinSMART-lite」不是「訓練一個小一點的LLM」，而是**只借用reward-alignment這個方法論本身，完全不訓練任何模型**：

**設計核心：把「same-day alpha對齊」當成特徵選擇/校準準則，而不是訓練目標。**

1. **系統性關鍵字權重校準**（取代RL訓練）：現有`score_text_finbert_proxy`的正負詞表是手寫、從沒驗證過的。用`finsmart_reward_alignment_diagnostic.py`同一套「same-day idiosyncratic alpha corr」當校準準則，定期(例如每季)重新評估哪些詞條/組合對same-day alpha相關性最高，取代目前一次性寫死的詞表——這是傳統特徵工程校準，不是模型訓練，不觸碰`llm_queries_allowed_at_test_time`邊界。
2. **承認結構性限制，重新定位用途**：Group A+是每日收盤後批次跑pipeline，任何「當天」對齊的訊號，等到能被拿來用的時候，市場早就收盤了——這是FinSMART論文的S&P500日內多空策略沒有的限制。所以FinSMART-lite**不該**被塞進「預測隔天報酬」這個角色（已經實測是雜訊，見第3節），比較誠實的定位是：**當天收盤後，用來標記「今天的價格波動有沒有被找得到的新聞情緒解釋」**——一個事後歸因/異常偵測用途，不是預測用途。可以餵給`risk_mechanism_classifier`或`crash_risk_alert`當「這次波動是news-driven還是無法解釋的機械性波動」的輔助標籤，而不是餵進`daily_signal.py`的方向性風險分數。
3. **善用已驗證更強的訊號來源**：分股新聞(FinMind)比市場全體新聞(LTN)訊號強一倍(0.24 vs 0.11)。目前FinMind分股標籤只有0050/00631L/00632R/00679B四檔，可以擴大到2330——2330已經有`ncf_2330`這條**已經正式promote過**的leadership-score pipeline(見memory`project_ncf2330_leadership_score_promotion_20260707`)，把2330的same-day情緒當一個新特徵候選餵進那條**已驗證過**的既有管線，比開一條全新消費路徑風險小很多。

## 3. 本地 reward-alignment 診斷結果

腳本：`scripts/evaluate/finsmart_reward_alignment_diagnostic.py`。報告：`research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md`。

| 訊號來源 | n | 當天相關係數 | 隔天相關係數 |
|---|---|---|---|
| production `finbert_sentiment`(LTN，市場全體，rule_based_finbert_proxy) vs 0050 | 1555 | 0.1148 (t≈4.5, p<0.0001) | 0.0052(雜訊) |
| FinMind分股新聞(0050專屬)套同一評分器 vs 0050 | 354 | **0.2355** (t≈4.5, p<0.0001) | 0.0884 |
| production `llm_sentiment_score`(另一條LTN-based pipeline) vs 0050 | 1555 | −0.0203(雜訊) | −0.0252(雜訊) |

**追查production實際消費方式後的結論**：`finbert_sentiment_risk`(`daily_signal.py`權重0.03 + `≥0.55`旗標)是用「不晚於actual_data_date的最新一筆」，影響的是下一個交易日——正好落在隔天那格。額外測了「當波動度警示看」（更貼切的解讀，因為它是風險分數不是方向性下注）：`finbert_negative_ratio` vs 隔天|0050報酬| = 0.0026, t≈0.10——一樣是零。**結論：這個特徵目前實際被使用的時間點上，不管哪種解讀都測不到訊號**，0.03權重形同虛設但不是bug。

## 4. 新增/產出的程式、測試、report 路徑

| 路徑 | 性質 | 測試 |
|---|---|---|
| `scripts/evaluate/letf_close_auction_overshoot_reversal_test.py` | LETF論文實測腳本 | **無**——純研究腳本，未寫pytest |
| `research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md` | LETF實測報告 | n/a |
| `scripts/evaluate/finsmart_reward_alignment_diagnostic.py` | FinSMART診斷腳本 | **無**——同上 |
| `research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md` | 診斷報告 | n/a |
| `research/shadow/_cache/*.csv` | yfinance控制組價格快取 | n/a |
| 本檔案 | 本設計筆記 | n/a |

**明確缺口**：這兩支診斷腳本都沒有寫pytest測試，不符合repo其他production-adjacent腳本的慣例(例如`build_*_shadow.py`類別都配一支`tests/test_build_*.py`)。因為目前定位是一次性研究診斷，不是會被排進pipeline重跑的東西，暫時沒補——如果第7節的`market_aligned_sentiment_shadow.json`真的要建，那支腳本必須配測試，才符合repo慣例。

## 5. Readiness review 決策邊界

既有的`llm_state_reward_interface_readiness_review`(靈感來自另一篇論文arXiv:2606.08450 GIFT，不是FinSMART，但邊界規則適用於任何LLM衍生特徵/reward提案)是這個repo對「LLM相關訊號能做到多深」的**現行憲法**：

```
llm_may_propose_features: true          — LLM可以提特徵候選
feature_primitives_must_be_allowlisted: true
reward_terms_must_map_to_existing_risk_objectives: true
human_code_review_required: true
walk_forward_validation_required: true
interface_must_be_frozen_before_oos: true
llm_queries_allowed_at_test_time: false — 正式環境不能live呼叫LLM
llm_actions_allowed: false              — LLM不能直接下決策
```

明確**not_imported**（永遠不做）：`llm_trading_agent`、`ppo_live_allocator`、`generated_code_without_review`、`test_time_llm_updates`、`automatic_rebalance`、`automatic_target_weight_change`。

**現況**：這個gate本身狀態是`blocked`（2026-07-21起），卡在六個依賴組件(`rl_governance`/`market_impact`/`synthetic_augmentation_validation`/`dynamic_cvar_tail_cost`/`deployment_consistency`/`research_shadow_decision_snapshot`)全部`blocked`——**跟FinSMART-lite本身的品質無關**，是這個repo更大範圍的LLM治理閘門本來就沒開。意思是：就算FinSMART-lite設計得再乾淨，結構上現在也不可能被promote成任何會影響即時決策的東西，只能停在shadow/研究層級，跟`gjr_garch_shadow`、`risk_mechanism_classifier`那些純診斷模組同一個位階。

## 6. 8/6 golden1_0531 / latest strategy 背景

以現有最新落地的資料(`actual_data_date`最新到08-05，08-06當天pipeline尚未產出新的`live_signal`)為準：

- **`risk_mechanism.json`(as_of 2026-08-05)**：`mechanism: FAST_CRASH`，`market_state.state=choppy_range_low_risk`，`market_state.bucket=choppy_range`，`crash_risk_alert`2-of-3觸發，stress score=3，active families=`['cross_market_shock','liquidity_forced_selling','options_tail']`。
- **正式`execution_plan.json`(今天已修復，見交接記錄第4節)**：策略是a2118(latest strategy)，建議賣2374股0050、全賣800股00631L、全賣3000股00679B、買5313股00632R(避險部位拉到27.08%)，`execution_allowed: False`卡在換手率80.84%，等人工複核。
- **golden1_0531參考基準**：本次對話沒有重新跑今天的$1M預測（那是使用者另一個固定請求模式，這次沒被觸發）。上一次(08-05)的分歧記錄在`project_golden1_0531_a2118_20260805_predict_divergence_20260805`：golden1_0531傾向加碼00631L、a2118(正式策略)傾向全出清——00631L方向共識較弱，其餘方向(減0050、加00632R避險)一致。
- **對market_aligned_sentiment_shadow的意義**：目前是`crash_risk_alert`啟動、PVA/SJM避險層主導的防禦格局，正是FinSMART-lite定位為「事後歸因」最有意義的時候——如果能標記出「這次波動有多少是能被新聞情緒解釋的」，對治理層(`risk_mechanism_classifier`)判斷FAST_CRASH是真實籌碼/總經驅動還是雜訊會有輔助價值，但**這個假設本身還沒驗證過**，只是設計動機，不是結論。

## 7. 建立 market_aligned_sentiment_shadow.json 的具體做法

**已實作**（本節原為設計草案，2026-08-06同一session完成實作，以下更新為實際狀態）。

- **腳本**：`scripts/evaluate/build_market_aligned_sentiment_shadow.py`（新增），比照`trough_override_eligibility_shadow.json`的既有shadow builder模式(純函式+CLI包裝，輸出到`report/group_a_plus/latest/`+`history/`目錄)。
- **資料源**：FinMind分股新聞，**改為同時讀`finmind_stock_news_merged_full.jsonl`+`finmind_stock_news_rolling.jsonl`兩個檔案union後dedupe**——實作時發現`merged_full.jsonl`本身停在2026-06-30，比對話當下(08-06)舊了超過一個月，`rolling.jsonl`才有到08-05的資料，這是獨立於本次任務、上游合併腳本沒有定期重跑的既有staleness問題，本次只在`build_market_aligned_sentiment_shadow.py`內部union兩個來源繞過，**沒有**去修上游合併腳本本身。用`score_text_finbert_proxy`逐篇評分、先去重(`dedupe_headlines`，比對(date, ticker, 標題去掉來源後綴)判斷)再日內平均。
- **實際schema**（跟第7節原草案的差異：欄位名改用`same_day_return`不是`same_day_alpha`，因為00631L/00632R/00679B都不是個股，用「相對大盤超額報酬」意義不大，改用各標的自身報酬）：
  ```json
  {
    "schema_version": 1, "status": "available",
    "research_only": true, "production_effect": "none",
    "date": "2026-08-05", "alpha_threshold": 0.005, "rolling_window_days": 63,
    "per_ticker": {
      "0050.TW": {"same_day_sentiment_score": -0.0871, "same_day_news_intensity": 11,
                   "same_day_return": 0.0313, "move_explained_by_news": false,
                   "rolling_63d_sentiment_return_corr": 0.4001},
      "00631L.TW": {"same_day_sentiment_score": 0.0667, "same_day_news_intensity": 4,
                     "same_day_return": 0.0622, "move_explained_by_news": true,
                     "rolling_63d_sentiment_return_corr": 0.147},
      "00632R.TW": {"same_day_sentiment_score": null, "same_day_news_intensity": 0, ...},
      "00679B.TWO": {"same_day_sentiment_score": null, "same_day_news_intensity": 0, ...}
    },
    "next_day_prediction": null,
    "next_day_prediction_note": "intentionally null -- ...",
    "raw_headline_count": 6506, "deduped_headline_count": 5782, "dropped_duplicate_count": 724
  }
  ```
  `next_day_prediction`寫死`null`並附註原因，避免以後有人忘記這是空結果又重新去加方向性預測欄位。00632R/00679B今天(08-05)沒有分股新聞覆蓋，所有情緒欄位正確回傳`null`而非0（測試有覆蓋這個情境）。
- **實作中抓到一個真bug**：`00679B`是上櫃(TPEx)不是上市(TWSE)，`ohlcv`表裡存的ticker是`00679B.TWO`不是`00679B.TW`，第一版程式碼寫死`.TW`後綴，導致這檔的價格/報酬整組回傳`None`卻不報錯——已修復(`TICKER_EXCHANGE_SUFFIX`映射)，並補上regression test鎖住這個行為。
- **測試**：`tests/test_build_market_aligned_sentiment_shadow.py`（新增，16個測試，全過），涵蓋去重邏輯、聚合邏輯、`move_explained_by_news`的四種情境(含門檻以下回傳null而非false)、rolling correlation的樣本量門檻、多檔案union、以及上述TWO後綴regression test。全部用小型fixture，不打真實DB/檔案。
- **驗證門檻**：正式接進`research_shadow_decision_snapshot.json`之前，要先過第5節readiness review邊界的`walk_forward_validation_required`——但如前述，這個gate本身`blocked`，所以就算做完也只能停在單獨的shadow json層級，不會自動被任何治理鏈讀取，除非額外手動接線（且目前沒有理由這樣做）。**目前完全沒有接線**，`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`是一個獨立存在的檔案，`daily_signal.py`/`research_shadow_decision_snapshot.py`都沒有讀它。

## 8. 明確未做事項與風險

**未做**：
- 沒有重新跑今天(08-06)的golden1_0531 vs a2118 $1M預測（使用者沒有觸發這個固定請求）。
- FinMind分股新聞涵蓋範圍擴大到2330——只是提案，沒有去改`scripts/fetch/fetch_finmind_stock_news.py`的watchlist。
- 沒有把FinSMART-lite的「事後歸因」用途跟`risk_mechanism_classifier`實際接線測試過，只是設計動機，`market_aligned_sentiment_shadow.json`目前是孤立檔案。
- 上游`finmind_stock_news_merged_full.jsonl`合併腳本本身的staleness(停在06-30)沒有修，只在新腳本內部繞過。
- 現有兩支LETF診斷腳本(`letf_close_auction_overshoot_reversal_test.py`/`finsmart_reward_alignment_diagnostic.py`)仍然沒有pytest測試——跟新建的`build_market_aligned_sentiment_shadow.py`不同，那兩支保持一次性研究腳本定位，沒有補測試。

**風險（含dedupe後用真實資料重新驗證的結果）**：
- **FinMind新聞重複標題，已修正並重新驗證**：0050分股新聞中約12.6%(724/5729，union兩檔案後的比例，跟原本單一檔案的14.5%相近)是同一天、同一則新聞被不同來源重複轉載。修正後用真實資料重跑：same-day相關係數從**0.2384降到0.2299**(n=363，dedupe前後皆同一組日期)——變化不大，證實原本的方向性結論(FinMind分股訊號比LTN市場全體訊號強)沒有被推翻，但這是修正後的乾淨數字，不是08-05報告裡未修正的舊數字。
- **樣本量偏薄**：FinMind分股新聞覆蓋約1.5年(2025-01到2026-08)，沒有涵蓋2020 COVID崩盤或更早的危機窗口，同一相關係數在不同regime下是否穩定沒有測過。
- **過擬合風險**：如果真的按第2節提案去重新校準關鍵字權重，屬於「固定窗口多輪調參」的模式(見`feedback_overfitting_fixed_window_tuning`)，正式導入前必須有全新OOS窗口驗證，不能只在同一批資料上反覆調。
- **治理邊界風險**：即使全部驗證通過，第5節的gate本身處於blocked狀態且跟FinSMART無關，代表這條線目前結構上就是走不到「影響即時決策」那一步，投入資源前要對這個天花板有心理準備。
