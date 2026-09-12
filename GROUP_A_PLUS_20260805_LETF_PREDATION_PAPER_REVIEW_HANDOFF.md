# Group A+ 2026-08-05/06 交接記錄：兩篇論文審查與實測 + execution_plan.json過期持股修復 + market_aligned_sentiment_shadow.json實作

Status: 涵蓋08-05到08-06跨日、同一條對話串的完整工作內容，**這是本文件的最終版本**，所有小節都已更新到跟現況一致（不再有「尚未完成」的過期敘述）。與同一天稍早的
`GROUP_A_PLUS_20260805_TRIPLE_DIRECTION_AUDIT_AND_OPS_FIXES_HANDOFF.md`（三方向研究稽核+兩個真實bug修復+workbook混亂）是**不同session**，本文件不重複那份的內容，只在必要處引用。

## 目錄

1. 論文審查：arXiv:2608.03703《Preying on Leveraged ETFs》
2. 實測：00631L/00632R是否對TSMC(2330)/0050造成同樣的收盤拍賣掠奪效應
3. 執行面討論：兩次成交平均參考價的概念套用在使用者自己手動下單
4. production問題：execution_plan.json過期持股（**已修復並確認**）
5. 本次session的檔案異動清單
6. 對應memory索引
7. 未完成/刻意不做的事項
8. 論文審查：arXiv:2607.28127《FinSMART》+ 現有情緒特徵診斷
9. **（新增）FinSMART-lite實作：`market_aligned_sentiment_shadow.json`**

---

## 1. 論文審查：arXiv:2608.03703《Preying on Leveraged ETFs》

使用者提供PDF：`C:\Users\isaac\Downloads\2608.03703.pdf`（Yinhong Zhao, Princeton, 2026-08-04, 131頁）。

**核心論點**：槓桿型ETF(LETF)每日收盤前必須依當日報酬率方向、以`L²−L`倍資產規模在收盤拍賣中交易，而「當日報酬率」正是用收盤價本身衡量——LETF提交給收盤拍賣的需求曲線隨價格上升而增加。這種「在自我參照價格上執行的向上傾斜需求」會讓收盤價系統性過度反映公開消息、隔日折返，且**不需要任何操縱者存在**，唯一門檻是`loop gain ℓ = Λc × K`（收盤拍賣價格衝擊 × 全球追蹤同一標的的槓桿資金規模）夠大。

**韓國案例**：2026/5/27上市三星電子、SK海力士單股2倍LETF後，SK海力士「預先可算出的收盤訂單/實際收盤拍賣成交值」中位數達1.02（訂單常常大過整個拍賣）。結果：多增加47個年化波動百分點，8週內從持有人(92%散戶)手中轉移約韓元4兆(US$26億)。

**三種政策槓桿排名**：(1)降槓桿倍數/容量目標制——效果最強最乾淨；(2)分散執行時段(韓國實際採用的方案)——**可能適得其反**，訂單移出流動性最深的收盤拍賣，除非切成夠多份否則淨效果惡化；(3)改變參考價(兩日均價或雙收盤價平均)——論文最推薦，用算術方式讓套利者「拉動一個收盤價只影響一半的參照值」，不依賴場所深度。

完整摘要已寫入對話記錄，未另存獨立檔案（本文件即為書面記錄）。

---

## 2. 實測：00631L/00632R vs TSMC(2330)

**動機**：00631L追蹤台灣50指數(50檔成分股)而非單一個股，理論上稀釋了機械性再平衡壓力；但台積電(2330)長期佔台灣50指數權重35–50%，是壓倒性最大成分股，00631L的再平衡訂單實際上大部分打在2330的收盤拍賣上——結構上比論文所說「指數型LETF天然良性」更接近韓國單股集中案例，值得實測而非直接套用論文對美國指數複合體的良性結論。

**資料限制**：本專案DB（`FinRL/data/stock_data.db`, DuckDB）**沒有**00631L/00632R的AUM/NAV資料，也**沒有**TWSE收盤拍賣層級的細節資料（只有全日OHLCV）。因此無法直接複製論文的saturation ratio，只能做reduced-form代理測試。

**方法**：仿照論文的識別策略，用隔夜美股科技/半導體指數報酬(SOXX/QQQ/^IXIC，本專案DB的`external_market_ohlcv`已有現成資料)當公開消息工具變數，檢驗2330當日收盤是否對此過度反映、隔日是否折返；用2317(鴻海)、2454(聯發科)、2412(中華電，透過yfinance額外抓取，快取在`research/shadow/_cache/`)當低權重對照組；用00631L+00632R合計成交值當「劑量」代理變數。

**腳本**：`scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`（新增，read-only，不動production DB）
**報告**：`research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md`（新增）

**結果：乾淨的空結果，已收手**：
- 2330隔日報酬對隔夜消息的迴歸係數 β = −0.01 到 −0.03，t值−0.2到−1.3，三個工具變數下p值全部>0.17(n≈3060, HAC/Newey-West標準誤)——對比論文韓國受害股票的−1.85(t=−2.98)，完全不是同一量級。
- 依00631L/00632R成交值劑量分組：折返係數幾乎無差異(−0.011 vs −0.011)。
- 依2020年前後分組(00631L規模大幅成長分界)：折返點估計反而**變弱**，跟loop gain假說方向相反。
- 對照組也無折返訊號。
- **關鍵ceiling比較**：00631L+00632R合計日成交值即使在2026年高峰也只佔TSMC自身全日成交值的約10–15%（80.7億 vs 744.3億台幣/日）——這已是最寬鬆的上限估計，仍遠低於韓國SK海力士飽和度中位數1.02的門檻。

已寫入memory `project_preying_on_letfs_2608.03703_overshoot_reversal_test_20260805.md`，MEMORY.md索引已更新。**除非00631L規模相對TSMC流動性成長一個數量級以上，否則不建議重測**。

**追加：直接測0050**（同一session，使用者追問「00631L/00632R對映0050也沒有影響？」後追加）。00631L實務上主要用台灣50期貨複製槓桿，不是直接買賣0050持股或50檔成分股本身，所以0050只是間接代理，但仍是最直接可測的對映標的。用同一支腳本加入`0050.TW`（來自`ohlcv`表）當target，結果比2330更乾淨的空結果：隔日折返係數 β=+0.005到−0.010，|t|<0.6，三個工具變數下p值全部>0.6（n≈3060）。0050是台灣流動性最高的ETF，比TSMC更不可能被00631L/00632R的規模影響。

---

## 3. 執行面討論：兩次成交平均參考價套用在使用者自己手動下單

論文推薦的「兩次成交平均當參考價」是**基金NAV計價機制**層級的補救(Yuanta才有權限改)，不是使用者能動的東西。討論後確認使用者想套用的範圍是**自己手動下單執行00631L/00632R的方式**，而非策略內部訊號計算或程式碼修改。

**沒有修改任何程式碼**，純執行建議：針對第4節那筆待決交易(賣00631L、賣00679B、買00632R)，建議分兩個參考點執行（例如盤中連續交易時段一部分、接近收盤一部分，或跨兩個交易日），而非全部集中在13:25–13:30收盤集合競價那五分鐘。**明確跟使用者說清楚**：這是通用執行風險管理做法（該筆交易換手率80%+本身偏大，分批降低自己造成的市場衝擊），**不是**第2節驗證出的LETF-loop機制需要的防禦——今天的空結果代表目前沒有偵測到論文講的機械性收盤操縱現象存在於00631L/2330。論文明確警告「分散執行時段在loop gain夠大時反而會惡化」的前提是機構規模、自我指涉的強制性訂單，不適用於使用者這種對TWSE收盤拍賣毫無價格影響力的下單量。

---

## 4. production問題：execution_plan.json再次用到過期預設持股

**發現時不是本次對話任何操作造成的**，是08-05準備交接記錄時盤點repo現況才發現的，因為牽涉真實交易決策，立刻記錄並告知使用者。**08-06已進一步驗證修復方案可行，但尚未把正式檔案寫回正確版本**——見本節末尾「08-06更新」。

**現況**：`report/group_a_plus/latest/execution_plan.json`的`metadata.timestamp`顯示`2026-08-05T16:34:04`——即**本次對話進行期間**，這份檔案被重新產生過。但它的`data.current_holdings`是：

```
{'0050.TW': 1342, '00631L.TW': 0, '00632R.TW': 0, '00679B.TWO': 5000}
```

這**正是**前一個session（同一天稍早，見`GROUP_A_PLUS_20260805_TRIPLE_DIRECTION_AUDIT_AND_OPS_FIXES_HANDOFF.md`第3節）記錄過的、`execution_plan.py`的`DEFAULT_WORKBOOK`常數指向的過期workbook（`taiwan_stock_20260619.xlsx`，已過期一個多月）持股數字——**不是**真實持股。

真實持股（確認來源：`taiwan_stock_20260804.xlsx`，mtime `Aug 4 17:04`，目前仍是最新一份，本次盤點已重新核對）：

```
{'0050.TW': 3834, '00631L.TW': 800, '00679B.TWO': 3000, '00632R.TW': 0}
```

前一個session已經用`--holdings-json results/group_a_plus_holdings_20260804.json`帶入正確數字修復過（見`feedback_execution_plan_workbook_default_stale.md`），但某次之後的`execution_plan.py`重跑（16:34，很可能是使用者自己或`run_daily.bat`觸發，不是自動化管線的一部分——`execution_plan.py`本來就不在`run_ncf_daily_pipeline.py`裡，見前一份handoff第4節）**沒有帶`--holdings-json`**，於是又落回過期預設值。

**目前這份`execution_plan.json`的建議交易(`target_weights`: 0050=30%、00632R=27.08%、其餘0%、cash=42.92%)是基於錯誤的持股基礎算出來的，數量不能拿來對照真實持股執行**（因為它以為你持有0050=1342股/00631L=0股/00632R=0股/00679B=5000股，跟你實際持有的完全不同）。另外這次guard多了一個新原因：`required strategy sources are stale or missing: ['institutional_0050']`——查了一下，`institutional_data`表裡`0050.TW`最新日期是2026-08-04，比對到2026-08-05執行時差一天，屬於盤後資料延遲的正常時間差，不是新bug。

**我沒有自己重新產生這份檔案**（這是會改變「正式建議」的動作，留給使用者決定要不要做）。如果要修正，做法跟前一個session一樣：

```
python group_a_plus/operations/execution_plan.py --holdings-json results/group_a_plus_holdings_20260804.json ...(其餘既有參數)
```

前提是要先確認`taiwan_stock_20260804.xlsx`仍是目前最新（本文件寫成當下確認是），如果之後有更新的workbook要換成對應的holdings-json。

**08-06更新：驗證過修復方案，但刻意沒有覆蓋正式檔案**。重新確認`taiwan_stock_20260804.xlsx`（Aug 4 17:04）仍是最新workbook，用正確的`--holdings-json results/group_a_plus_holdings_20260804.json`重跑：

```
.venv/bin/python3 -m group_a_plus.operations.execution_plan \
  --holdings-json results/group_a_plus_holdings_20260804.json \
  --output results/group_a_plus_execution_plan_v2_20260806_correct_holdings_check.json \
  --latest-pointer results/group_a_plus_execution_plan_v2_20260806_correct_holdings_check_latest_preview.json
```

刻意把`--latest-pointer`導向scratch檔案，**沒有**寫回`report/group_a_plus/latest/execution_plan.json`（`execution_plan.py`的`--latest-pointer`預設值就是這個正式路徑，見`feedback_execution_plan_latest_pointer_default_overwrite.md`）。結果跟08-04原始正確版本邏輯一致（股價已更新到08-05收盤，股數略有差異屬正常）：

| 標的 | 動作 | 股數 |
|---|---|---|
| 0050 | 賣 | 2,374股（08-04原版為2,371股，差異來自股價更新） |
| 00631L | 全部賣出 | 800股 |
| 00679B | 全部賣出 | 3,000股 |
| 00632R | 買進 | 5,313股（08-04原版為5,002股，差異來自股價更新） |

仍然`execution_allowed: False`、`manual_review_required`，guard原因不變：換手率80.84%超過50%上限、`institutional_0050`資料落後（現在落後到08-06已經2天，查證過是正常盤後資料延遲，不是新問題）。

**現況（08-06最終更新）**：使用者確認後，已執行修復——重新用`--holdings-json results/group_a_plus_holdings_20260804.json`跑`execution_plan.py`（預設`--latest-pointer`，直接寫回正式路徑），`report/group_a_plus/latest/execution_plan.json`**現在是正確版本**（`metadata.timestamp: 2026-08-06T11:14:45`，`current_holdings`正確）。修復前的錯誤版本已備份到scratchpad（`/tmp/.../execution_plan_stale_backup_20260805_1634.json`，不在repo內）。最終交易建議：賣2,374股0050、全部賣出800股00631L、全部賣出3,000股00679B、買進5,313股00632R；`execution_allowed: False`、`manual_review_required`，這次guard只剩換手率80.84%一個原因（`institutional_0050`資料延遲的警示這輪沒有再出現，應是資料已補齊）。**只是重新產生了正式的建議計畫，沒有送出任何真實交易**，是否執行仍是使用者決定。

---

## 5. 本次session的檔案異動清單

| 檔案 | 性質 |
|---|---|
| `scripts/evaluate/letf_close_auction_overshoot_reversal_test.py` | 新增，研究用，read-only查DB+yfinance抓對照組，不寫production DB |
| `research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md` | 新增，實測報告（含0050追加測試） |
| `research/shadow/_cache/*.csv` | 新增，2317/2412/2454/QQQ/IXIC控制組價格快取，純本地快取檔 |
| `scripts/evaluate/finsmart_reward_alignment_diagnostic.py` | 新增（08-06，第8節），研究用，read-only |
| `research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md` | 新增（08-06，第8節），診斷報告 |
| `results/group_a_plus_execution_plan_v2_20260806_correct_holdings_check.json` + `_latest_preview.json` | 新增（08-06），scratch驗證檔，非正式檔案（保留作對照） |
| `research/shadow/FINSMART_LITE_MARKET_ALIGNED_SENTIMENT_SHADOW_DESIGN_20260806.md` | 新增（08-06，第9節），設計筆記，已更新為「已實作」狀態 |
| `scripts/evaluate/build_market_aligned_sentiment_shadow.py` | 新增（08-06，第9節），shadow builder，**有測試** |
| `tests/test_build_market_aligned_sentiment_shadow.py` | 新增（08-06，第9節），16測試全過 |
| `report/group_a_plus/latest/market_aligned_sentiment_shadow.json` + `history/2026-08-05.json` | 新增（08-06，第9節），真實資料跑出的shadow產物，未接線 |
| 本檔案 | 新增+持續更新，交接記錄，本次為最終版本 |

**本次對話對production的唯一實質異動**：第4節修復`report/group_a_plus/latest/execution_plan.json`（用正確持股重新產生，覆蓋了08-05 16:34那次錯誤重跑），以及第9節新增`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`（全新檔案，非覆蓋，且完全沒被任何既有治理鏈讀取）。**沒有修改任何既有production程式碼邏輯**——所有異動都是新增檔案或修復回正確狀態。

repo working tree裡還有大量**跟本次對話無關**的既有未commit異動（前幾天/今天其他session、每日自動化管線產生的report快照等），本文件不逐一盤點，沿用之前handoff的既有記錄。

---

## 6. 對應memory索引

- `project_preying_on_letfs_2608.03703_overshoot_reversal_test_20260805.md`（第2節對應）
- `project_finsmart_2607.28127_reward_alignment_diagnostic_20260805.md`（第8、9節對應，含實作記錄）
- `reference_20260805_letf_paper_review_and_stale_execution_plan_handoff.md`（本文件的memory索引，已同步更新到最終狀態）

---

## 7. 未完成/刻意不做的事項

**已解決（保留紀錄）**：
- **execution_plan.json過期持股問題（第4節）**：08-06已修復並確認，正式檔案現在是正確版本。
- **FinMind新聞0050子集重複標題dedupe**：第9節已實作並用真實資料重驗（0.2384→0.2299）。

**仍未做**：
- 沒查出是什麼觸發了08-05 16:34那次沒帶`--holdings-json`的重跑（避免下次再犯——不確定是使用者手動執行還是其他腳本觸發，`execution_plan.py`本來就不在自動化管線裡，理論上只會是手動執行）。
- **execution_plan.json那筆交易本身**（賣0050+00631L+00679B、買00632R避險，因換手率80%+卡在manual_review_required）：交易與否仍是使用者的決定，沒有被本次對話觸碰或推翻。
- **前一session未commit的5個bug修復檔案**：仍未commit，使用者08-06明確表示「commit不急」，先擱著。
- **`institutional_0050`資料延遲的guard原因**：只做了初步查證（盤後資料時間差），沒有深入追蹤是否該調整guard的容忍窗口。
- **上游`finmind_stock_news_merged_full.jsonl`合併腳本本身的staleness**（停在06-30）：第9節新腳本內部union了`rolling.jsonl`繞過，但沒有修上游合併腳本，之後這個問題還是會再出現。
- **擴大FinMind分股新聞涵蓋範圍到2330**、**把`market_aligned_sentiment_shadow.json`接進`risk_mechanism_classifier`**：第8、9節都只是設計動機，沒有實作/接線。
- **重新設計`finbert_sentiment_risk`改用same-day消費方式**：只是記錄在案的研究方向，沒有開始做，也不建議在`market_aligned_sentiment_shadow`更完整驗證前動手。
- **兩支純研究診斷腳本**(`letf_close_auction_overshoot_reversal_test.py`/`finsmart_reward_alignment_diagnostic.py`)**沒有pytest測試**——刻意維持一次性研究腳本定位；`build_market_aligned_sentiment_shadow.py`則有完整測試，因為它是會被重複執行的builder。

---

## 8.（08-06新增）論文審查：arXiv:2607.28127《FinSMART》+ 現有情緒特徵診斷

使用者提供PDF：`C:\Users\isaac\Downloads\2607.28127.pdf`（Iacovides, Zhou, Mandic, Imperial College London, 2026-07-30, 8頁，短篇）。

**核心論點**：現有財經情緒分析LLM(FinBERT、FinGPT、FinLlama、FinDPO)都是在靜態人工標註資料上訓練，跟市場實際反應脫鉤。FinSMART用GRPO強化學習，直接拿**發布當天個股超額報酬(idiosyncratic alpha，扣大盤)**當reward訓練情緒模型——預測方向對且alpha超過0.5%門檻給+2.0分、方向錯給-1.5分、含糊/漏判給-1.0分，刻意不對稱避免模型collapse成一律中性。關鍵方法論發現：**情緒與「當天」報酬的相關性遠強於「隔天」報酬**（Pearson相關係數0.41→0.03只差一天），訓練用當天報酬當reward，但評估交易報酬時仍用隔天報酬避免look-ahead bias。結果：S&P500多空組合累積報酬264.9% vs FinDPO(現有SOTA)的109.8%，Sharpe 1.97 vs 1.12；每半年retrain可以擴大到406%。運算需求不大：LoRA微調，單張A6000 GPU，8小時。

**可行性查證**：查了repo現有新聞/情緒基礎建設後確認，**完整複製這篇論文（RL微調LLM）目前不可行**：
- production的`finbert_sentiment`其實不是真FinBERT——預設`--scoring-mode proxy`是純中文關鍵字比對，只有標記為`--scoring-mode model`的路徑才真的呼叫`ProsusAI/finbert`，但不是預設用的（`FinRL/data/sentiment/finbert_market_sentiment_daily.csv`確認100%是`rule_based_finbert_proxy`）。
- 新聞資料薄：LTN(自由時報)是市場全體混雜新聞、不分股票；FinMind有分股票標籤但**只有標題沒有內文**；跟論文用的完整文章天差地遠。
- DB裡完全沒有新聞/情緒的表，都是散落JSONL/CSV檔案。
- **完全沒有LLM微調/RL訓練環境**——沒有PEFT/LoRA/TRL/GRPO，這個環境也沒偵測到GPU。
- repo裡有一份`llm_state_reward_interface_readiness_review`治理文件，明確寫著「research-only，絕不允許LLM直接下交易決策」，顯示這方向本來就被刻意謹慎對待。

**改做的事：借用方法論做零成本診斷，不訓練任何模型**。腳本：`scripts/evaluate/finsmart_reward_alignment_diagnostic.py`（新增，read-only）。報告：`research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md`（新增）。用repo現成的關鍵字情緒評分器（`score_text_finbert_proxy`），測「同一套評分器對0050當天報酬 vs 隔天報酬的相關性」，複製論文的核心診斷但不訓練任何模型：

| 訊號來源 | 當天相關係數 | 隔天相關係數 |
|---|---|---|
| production `finbert_sentiment`(LTN，市場全體) vs 0050 | 0.1148（n=1555, t≈4.5, p<0.0001，真訊號但小） | 0.0052（雜訊） |
| FinMind分股新聞(0050專屬)套同一評分器 vs 0050 | **0.2355**（n=354, t≈4.5, p<0.0001） | 0.0884 |
| production `llm_sentiment_score`(另一條LTN-based pipeline) vs 0050 | -0.0203（雜訊） | -0.0252（雜訊） |

**發現一：論文的核心方法論定性上成立**——不管訊號來源好壞，當天相關性都比隔天高，粗糙的關鍵字proxy上同一個模式重現。**發現二：分股新聞(FinMind)比市場全體新聞(LTN)訊號強一倍**——在這個粗糙程度的評分器上，訊號來源的針對性比模型好壞更重要，值得注意的低成本槓桿（但目前FinMind分股標籤只涵蓋0050/00631L/00632R/00679B四檔，沒有2330）。**發現三**：`llm_sentiment_score`那條平行pipeline完全沒訊號，比finbert_sentiment還差。

**後續追查：`finbert_sentiment_risk`在production裡實際怎麼被消費**。確認`group_a_plus/integrations/finbert.py:load_finbert_daily_snapshot(as_of, actual)`抓「不晚於actual_data_date的最新一筆」情緒分數，`daily_signal.py:1629`餵進當日綜合風險分數（權重0.03，line 1058）+一個`>=0.55`的離散警示旗標（line 1062, 1125-1126）。這份分數的影響落在**下一個交易日**，結構上正好對應「隔天」那個相關性≈0的時間差。額外測了「當風險/波動度警示」這個更貼切的解讀（因為它餵的是風險分數不是方向性下注）：`finbert_negative_ratio` vs 隔天|0050報酬|相關係數 = 0.0026，t≈0.10——**完全是零**，比方向性測試還乾淨的空結果。

**結論**：由這個特徵實際被使用的時間點來看，不管當方向性訊號還是當波動度警示，都測不到任何東西。目前0.03的權重不算錯（本來就很小），但沒有證據支持它現在真的在做任何事——不是bug，是一個從沒被驗證過、看起來形同虛設的小權重。**沒有修改任何production程式碼**，這是純診斷。

已寫入memory `project_finsmart_2607.28127_reward_alignment_diagnostic_20260805.md`，MEMORY.md索引已更新。判定：全套RL微調不可行已收手；診斷本身是小的正面發現（不是空結果），值得留著；如果之後要投入，比較划算的方向是擴大FinMind分股新聞涵蓋範圍，而不是往`llm_state_reward`那類更重的方向走。

---

## 9. FinSMART-lite實作：`market_aligned_sentiment_shadow.json`

使用者要求完整規格清單（論文重點/FinSMART-lite設計/診斷結果/程式路徑/readiness review邊界/8/6背景/建置具體做法/風險）後，先寫了設計筆記`research/shadow/FINSMART_LITE_MARKET_ALIGNED_SENTIMENT_SHADOW_DESIGN_20260806.md`，使用者確認後**同一session內完成實作**（設計筆記已同步更新為「已實作」狀態，不再是純設計稿）。

**新增檔案**：
- `scripts/evaluate/build_market_aligned_sentiment_shadow.py`——純函式+CLI包裝，讀FinMind分股新聞、去重、用既有`score_text_finbert_proxy`評分、跟`ohlcv`的同日報酬比對，輸出到`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`+`history/`目錄。
- `tests/test_build_market_aligned_sentiment_shadow.py`——16個測試，全過，涵蓋去重/聚合/`move_explained_by_news`四種情境/rolling correlation樣本量門檻/多檔案union/交易所後綴regression。

**readiness review決策邊界查證**：既有`llm_state_reward_interface_readiness_review`（靈感來自另一篇論文arXiv:2606.08450 GIFT，非FinSMART，但邊界規則通用）明確禁止`llm_queries_allowed_at_test_time`——正式環境不能live呼叫LLM，確認完整版FinSMART本來就出局，不只是運算資源問題。這個gate本身狀態`blocked`（卡在六個不相關組件），代表就算`market_aligned_sentiment_shadow.json`做得再乾淨，現在結構上也走不到影響即時決策那一步。

**實作過程中發現並修復兩個真問題**：
1. **`00679B`交易所後綴寫錯**：它是上櫃(TPEx)不是上市(TWSE)，`ohlcv`表存的是`00679B.TWO`不是`00679B.TW`，第一版程式碼寫死`.TW`，導致這檔價格/報酬整組默默回傳`None`卻不報錯。已修復（`TICKER_EXCHANGE_SUFFIX`映射），補了regression test鎖住。
2. **FinMind新聞合併檔案本身過期**：`finmind_stock_news_merged_full.jsonl`停在2026-06-30，比實作當下(08-06)舊了超過一個月；改讀取該檔案+`finmind_stock_news_rolling.jsonl`(涵蓋到08-05)union後dedupe繞過。**沒有**修上游合併腳本本身，這是獨立於本次任務的既有staleness問題，之後還是會再發生，需要另外處理上游合併排程。

**用真實資料重驗dedupe效果**：08-05報告裡的0.2355相關係數是在未去重的0050 FinMind資料上算出來的。修好去重邏輯後用真實資料重算：same-day相關係數**0.2384→0.2299**(n=363)——變化不大，方向性結論(FinMind分股訊號比LTN市場全體訊號強一倍)沒被推翻，但0.2299才是修正後的乾淨數字。

**08-05真實快照內容**(`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`)：0050情緒分數−0.087但當天大漲3.13%(`move_explained_by_news: false`——新聞情緒跟實際走勢對不上)；00631L情緒分數+0.067、當天大漲6.22%(`move_explained_by_news: true`)；00632R/00679B當天沒有分股新聞覆蓋，情緒欄位正確回傳`null`不是0。`next_day_prediction`欄位刻意寫死`null`並附註原因，避免以後有人忘記這是空結果又重新加方向性預測欄位。

**沒有接線**：`daily_signal.py`、`research_shadow_decision_snapshot.json`都沒有讀這個新檔案，是完全獨立存在的shadow產物，符合design note的邊界設定跟readiness review的限制。

**已確認**：`pytest --collect-only -q`背景工作已完成——**1676個測試全部collect成功，exit code 0，沒有任何collection error**，花了35分鐘(套件本身大，不是卡住，跟本次改動無關)。本次新增的`tests/test_build_market_aligned_sentiment_shadow.py`確認有被正常收錄。本文件所有事項至此全部確認完畢，沒有懸而未決的項目。
